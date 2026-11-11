"""``hermes shortcuts pair``: print a QR code that pairs the iPhone "Hermes Setup" shortcut with this server.

The QR encodes ``{"v":1,"url":"https://…","token":"…"}``. The Setup shortcut scans it and saves it as
``hermes.json`` in the Shortcuts folder of iCloud Drive; every other Hermes shortcut reads that file, so
the shortcuts you share (iCloud links) never contain a token.

Security: the token is read through Hermes' secret scope (like the adapter), never logged, and printed
only inside the QR (``--show-token`` prints it as text, off by default). ``--png`` writes a 0600 file.
The plugin makes no network calls except the optional local auto-detect of a cloudflared quick tunnel
on 127.0.0.1 (cloudflared's metrics endpoint).
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import struct
import sys
import urllib.parse
import urllib.request
import zlib
from typing import Iterable, Optional

try:  # loaded as part of the plugin package (hermes shortcuts pair)
    from . import actions as A
    from . import _qrcodegen as Q
except ImportError:  # pragma: no cover - run as a plain script: python3 pair.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import actions as A  # type: ignore[no-redef]
    import _qrcodegen as Q  # type: ignore[no-redef]

PAYLOAD_VERSION = 1
CONFIG_FILE = "hermes.json"
METRICS_PORTS = tuple(range(20241, 20246))  # cloudflared's default metrics ports (first free one is used)
_QUICK_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com$")
WARNING = ("This QR code contains your Shortcuts token. Don't screenshot, photograph or share it; "
           "anyone who scans it can act as you. Clear the terminal (`clear`) after pairing.")


class PairError(Exception):
    """A user-facing pairing problem (message never contains the token)."""


# -- token / URL --------------------------------------------------------------------------------------

def _standalone_secret(name: str) -> Optional[str]:
    """Outside the plugin package: Hermes' secret scope when importable, else None. Never os.environ."""
    try:
        from agent.secret_scope import get_secret
    except Exception:
        return None
    try:
        val = get_secret(name, None)
    except Exception:
        return None
    return None if val is None else str(val).strip()


def read_token() -> str:
    """The configured SHORTCUTS_TOKEN, through the same secret route the adapter uses
    (agent.secret_scope.get_secret; never os.environ or .env files). Run as a plain script with a Python
    that cannot import Hermes, the token is asked for on the terminal (not echoed)."""
    try:
        from .adapter import _secret  # type: ignore[attr-defined]
        return _secret("SHORTCUTS_TOKEN", "")
    except ImportError:
        pass
    val = _standalone_secret("SHORTCUTS_TOKEN")
    if val:
        return val
    if sys.stdin.isatty():
        import getpass
        return getpass.getpass("SHORTCUTS_TOKEN (input hidden): ").strip()
    return ""


def normalize_url(raw: str, allow_http: bool = False) -> str:
    """Validate a public base URL and return it as ``scheme://host[:port][/path]`` without a trailing slash."""
    raw = (raw or "").strip()
    if not raw:
        raise PairError("empty URL")
    if "://" not in raw:
        raw = "https://" + raw
    try:
        u = urllib.parse.urlsplit(raw)
        port = u.port  # raises ValueError on a bad port
    except ValueError as exc:
        raise PairError(f"invalid URL: {exc}") from None
    if u.scheme not in ("https", "http"):
        raise PairError("URL must start with https://")
    if not u.hostname:
        raise PairError("URL has no host")
    if u.username or u.password:
        raise PairError("URL must not contain a user name or password")
    if u.query or u.fragment:
        raise PairError("URL must not contain ?query or #fragment (never put the token in a URL)")
    if u.scheme == "http" and not allow_http and not _is_private_host(u.hostname):
        raise PairError("plain http:// over the internet would expose your token; use your HTTPS tunnel URL "
                        "(or pass --allow-http for a private network such as Tailscale)")
    host = u.hostname.lower()
    netloc = (f"[{host}]" if ":" in host else host) + (f":{port}" if port else "")
    path = u.path.rstrip("/")
    for suffix in ("/v1/ask", "/v1/share", "/v1/event", "/health"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return f"{u.scheme}://{netloc}{path}"


def _is_private_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith(".ts.net") or host == "localhost"
    cgnat = ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10")  # Tailscale addresses
    return ip.is_private or ip.is_loopback or cgnat


def detect_quick_tunnel_url(ports: Iterable[int] = METRICS_PORTS, timeout: float = 1.0,
                            opener=None) -> Optional[str]:
    """Ask a local cloudflared (metrics endpoint, 127.0.0.1 only) for its quick-tunnel hostname."""
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy
    for port in ports:
        try:
            with opener.open(f"http://127.0.0.1:{int(port)}/quicktunnel", timeout=timeout) as resp:
                data = json.loads(resp.read(4096).decode("utf-8", "replace"))
        except Exception:
            continue
        host = str((data or {}).get("hostname") or "").strip().lower() if isinstance(data, dict) else ""
        if _QUICK_HOST.match(host):
            return f"https://{host}"
    return None


def resolve_url(cli_url: Optional[str], allow_http: bool = False, detect=detect_quick_tunnel_url) -> tuple[str, str]:
    """(base URL, where it came from): --url, then SHORTCUTS_PUBLIC_URL, then a local quick tunnel."""
    if cli_url:
        return normalize_url(cli_url, allow_http), "--url"
    try:  # declared optional_env: read through Hermes' secret scope (profile-aware)
        from .adapter import _secret  # type: ignore[attr-defined]
        env_url = _secret("SHORTCUTS_PUBLIC_URL", "")
    except ImportError:  # plain script: Hermes' scope if importable, else the process environment (not a secret)
        env_url = _standalone_secret("SHORTCUTS_PUBLIC_URL") or os.environ.get("SHORTCUTS_PUBLIC_URL", "").strip()
    if env_url:
        return normalize_url(env_url, allow_http), "SHORTCUTS_PUBLIC_URL"
    found = detect()
    if found:
        return normalize_url(found), "cloudflared quick tunnel (changes when cloudflared restarts)"
    raise PairError("no public URL: pass --url https://your-host, set SHORTCUTS_PUBLIC_URL, or start a "
                    "cloudflared tunnel to http://127.0.0.1:8645")


def build_payload(url: str, token: str) -> str:
    """Compact JSON for the QR. Keys match what the iPhone shortcuts read: ``url`` and ``token``."""
    problem = A.token_problem(token)
    if problem is not None:
        raise PairError(f"SHORTCUTS_TOKEN is {problem}; set a strong one first: "
                        "hermes config set SHORTCUTS_TOKEN \"$(openssl rand -hex 32)\" && hermes gateway restart")
    return json.dumps({"v": PAYLOAD_VERSION, "url": url, "token": token}, separators=(",", ":"))


# -- rendering ----------------------------------------------------------------------------------------

def make_qr(payload: str):
    return Q.QrCode.encode_text(payload, Q.QrCode.Ecc.MEDIUM)


def render_terminal(qr, border: int = 4, invert: bool = False) -> str:
    """Half-block rendering (two modules per character). Default suits dark terminals (light quiet zone)."""
    n = qr.get_size()

    def light(x: int, y: int) -> bool:
        dark = 0 <= x < n and 0 <= y < n and qr.get_module(x, y)
        return dark if invert else not dark

    glyph = {(True, True): "\u2588", (True, False): "\u2580", (False, True): "\u2584", (False, False): " "}
    rows = []
    for y in range(-border, n + border, 2):
        rows.append("".join(glyph[(light(x, y), light(x, y + 1))] for x in range(-border, n + border)))
    return "\n".join(rows)


def png_bytes(qr, scale: int = 8, border: int = 4) -> bytes:
    """A black-on-white 1-bit PNG, stdlib only."""
    n = qr.get_size()
    side = (n + 2 * border) * scale
    raw = bytearray()
    for py in range(side):
        y = py // scale - border
        bits = [(0 <= y < n and 0 <= px // scale - border < n and qr.get_module(px // scale - border, y))
                for px in range(side)]
        row = bytearray(b"\x00")  # filter type 0
        for i in range(0, side, 8):
            byte = 0
            for j, dark in enumerate(bits[i:i + 8]):
                if not dark:  # bit 1 = white in a 1-bit grayscale PNG
                    byte |= 0x80 >> j
            row.append(byte)
        raw += row

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 1, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def write_private(path: str, data: bytes) -> None:
    """Write ``data`` with mode 0600, refusing to follow a symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, data)
    finally:
        os.close(fd)


# -- CLI ----------------------------------------------------------------------------------------------

def setup_parser(parser: argparse.ArgumentParser) -> None:
    """argparse tree for ``hermes shortcuts …`` (also used by ``python3 pair.py``)."""
    sub = parser.add_subparsers(dest="shortcuts_command", metavar="COMMAND")
    p = sub.add_parser("pair", help="Show a QR code that pairs the iPhone 'Hermes Setup' shortcut",
                       description="Print a QR code with this server's public URL and your SHORTCUTS_TOKEN. "
                                   "Scan it with the 'Hermes Setup' shortcut on your iPhone.")
    p.add_argument("--url", help="public HTTPS base URL (default: SHORTCUTS_PUBLIC_URL, else the local "
                                 "cloudflared quick tunnel)")
    p.add_argument("--png", metavar="PATH", help="also save the QR as a PNG (mode 0600; delete it after pairing)")
    p.add_argument("--show-token", action="store_true", help="also print the token as text (off by default)")
    p.add_argument("--invert", action="store_true", help="for terminals with a light background")
    p.add_argument("--allow-http", action="store_true", help="allow a plain http:// URL (private networks only)")


def run_pair(args, out=None) -> int:
    out = out or sys.stdout
    try:
        url, source = resolve_url(getattr(args, "url", None), getattr(args, "allow_http", False))
        payload = build_payload(url, read_token())
        qr = make_qr(payload)
    except PairError as exc:
        print(f"hermes shortcuts pair: {exc}", file=sys.stderr)
        return 1
    print(f"Server URL: {url}  (from {source})", file=out)
    print("Token: inside the QR code" + ("" if getattr(args, "show_token", False) else " (not shown)"), file=out)
    print("", file=out)
    print("WARNING: " + WARNING, file=out)
    print("", file=out)
    print(render_terminal(qr, invert=getattr(args, "invert", False)), file=out)
    print("", file=out)
    print("On your iPhone: run the 'Hermes Setup' shortcut and scan this code. It saves the URL and token to "
          f"iCloud Drive > Shortcuts > {CONFIG_FILE}; the other Hermes shortcuts read it from there.", file=out)
    print("Can't scan it (terminal font too wide)? Re-run with --invert, zoom out, or use --png FILE.", file=out)
    if getattr(args, "show_token", False):
        print(f"Token: {json.loads(payload)['token']}", file=out)
    png = getattr(args, "png", None)
    if png:
        try:
            write_private(png, png_bytes(qr))
        except OSError as exc:
            print(f"hermes shortcuts pair: could not write PNG: {exc.strerror}", file=sys.stderr)
            return 1
        print(f"PNG saved to {png} (mode 0600). It contains your token: delete it after pairing.", file=out)
    if source.startswith("cloudflared"):
        print("Note: a quick-tunnel URL changes whenever cloudflared restarts; then run this again and re-scan.",
              file=out)
    return 0


def cli_handler(args) -> int:
    if getattr(args, "shortcuts_command", None) == "pair":
        return run_pair(args)
    print("usage: hermes shortcuts pair [--url URL] [--png PATH] [--show-token] [--invert]", file=sys.stderr)
    return 2


def main(argv=None) -> int:  # python3 pair.py pair …
    parser = argparse.ArgumentParser(prog="pair.py")
    setup_parser(parser)
    return cli_handler(parser.parse_args(argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
