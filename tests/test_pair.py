"""Pairing QR: payload, URL resolution, cloudflared detection, rendering, and no token leaks."""
import io
import json
import logging
import os
import stat
import types
import zlib

import pytest

from conftest import SECRETS, load_plugin

P = load_plugin()
pair = __import__("hermes_shortcuts.pair", fromlist=["pair"])
TOKEN = "f3a9c1e07b5d2846aa91c3e5d7f0b2c4e6a8d0f2b4c6e8a0d2f4b6c8e0a2c4e6"


def test_payload_keys_and_values():
    data = json.loads(pair.build_payload("https://x.example.com", TOKEN))
    assert data == {"v": 1, "url": "https://x.example.com", "token": TOKEN}
    assert set(data) == {"v", "url", "token"}  # the iPhone shortcuts read exactly `url` and `token`


@pytest.mark.parametrize("bad", ["", "Tok3nX", "changeme" * 5, "a" * 40])
def test_payload_refuses_weak_token_without_echoing_it(bad):
    with pytest.raises(pair.PairError) as exc:
        pair.build_payload("https://x.example.com", bad)
    assert not bad or bad not in str(exc.value)


@pytest.mark.parametrize("raw,want", [
    ("https://abc.trycloudflare.com/", "https://abc.trycloudflare.com"),
    ("abc.trycloudflare.com", "https://abc.trycloudflare.com"),
    ("https://Host.Example.com:8443/hermes/v1/ask", "https://host.example.com:8443/hermes"),
    ("http://100.101.102.103:8645", "http://100.101.102.103:8645"),
    ("http://box.tail1234.ts.net", "http://box.tail1234.ts.net"),
])
def test_normalize_url(raw, want):
    assert pair.normalize_url(raw) == want


@pytest.mark.parametrize("raw", ["http://example.com", "ftp://x.com", "https://u:p@x.com",
                                 "https://x.com/?token=abc", "https://x.com/#t", "https://:99999"])
def test_normalize_url_rejects(raw):
    with pytest.raises(pair.PairError):
        pair.normalize_url(raw)


def test_allow_http_opt_in():
    assert pair.normalize_url("http://example.com", allow_http=True) == "http://example.com"


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Opener:
    def __init__(self, answers): self.answers, self.calls = answers, []

    def open(self, url, timeout=None):
        self.calls.append(url)
        ans = self.answers.get(url)
        if ans is None:
            raise OSError("refused")
        return _Resp(ans)


def test_detect_quick_tunnel_scans_local_ports():
    op = _Opener({"http://127.0.0.1:20242/quicktunnel": b'{"hostname":"adsl-foo-bar.trycloudflare.com"}'})
    assert pair.detect_quick_tunnel_url(opener=op) == "https://adsl-foo-bar.trycloudflare.com"
    assert all(c.startswith("http://127.0.0.1:") for c in op.calls)


@pytest.mark.parametrize("body", [b'{"hostname":""}', b'{"hostname":"evil.com"}', b"not json",
                                  b'{"hostname":"x.trycloudflare.com.evil.com"}', b'["x"]',
                                  b'{"hostname":"a/b.trycloudflare.com"}'])
def test_detect_ignores_bad_answers(body):
    op = _Opener({"http://127.0.0.1:20241/quicktunnel": body})
    assert pair.detect_quick_tunnel_url(opener=op) is None


def test_resolve_order(monkeypatch):
    monkeypatch.setenv("SHORTCUTS_PUBLIC_URL", "https://env.example.com/")
    det = lambda: "https://q.trycloudflare.com"
    assert pair.resolve_url("https://cli.example.com", detect=det)[0] == "https://cli.example.com"
    assert pair.resolve_url(None, detect=det)[0] == "https://env.example.com"
    monkeypatch.delenv("SHORTCUTS_PUBLIC_URL")
    assert pair.resolve_url(None, detect=det) [0] == "https://q.trycloudflare.com"
    with pytest.raises(pair.PairError):
        pair.resolve_url(None, detect=lambda: None)


def _modules(qr):
    n = qr.get_size()
    return [[qr.get_module(x, y) for x in range(n)] for y in range(n)]


def test_terminal_render_shape_and_no_plain_token():
    qr = pair.make_qr(pair.build_payload("https://abc.trycloudflare.com", TOKEN))
    txt = pair.render_terminal(qr)
    n = qr.get_size()
    lines = txt.splitlines()
    assert len(lines) == (n + 8 + 1) // 2 and all(len(line) == n + 8 for line in lines)
    assert TOKEN not in txt and set(txt) <= set("\u2588\u2580\u2584 \n")
    assert pair.render_terminal(qr, invert=True) != txt


def test_png_valid_and_private(tmp_path):
    qr = pair.make_qr(pair.build_payload("https://abc.trycloudflare.com", TOKEN))
    data = pair.png_bytes(qr, scale=2, border=4)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    side = (qr.get_size() + 8) * 2
    assert int.from_bytes(data[16:20], "big") == side
    idat = data[data.index(b"IDAT") + 4:data.index(b"IEND") - 8]
    raw = zlib.decompress(idat)
    assert len(raw) == side * (1 + (side + 7) // 8)
    f = tmp_path / "qr.png"
    f.write_bytes(b"old")
    os.chmod(f, 0o644)
    pair.write_private(str(f), data)
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and f.read_bytes() == data


def test_write_private_refuses_symlink(tmp_path):
    target = tmp_path / "target"; target.write_text("keep")
    link = tmp_path / "link"; link.symlink_to(target)
    with pytest.raises(OSError):
        pair.write_private(str(link), b"x")
    assert target.read_text() == "keep"


def _args(**kw):
    base = dict(url="https://abc.trycloudflare.com", png=None, show_token=False, invert=False, allow_http=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_run_pair_never_prints_or_logs_token(monkeypatch, capsys, caplog, tmp_path):
    monkeypatch.setitem(SECRETS, "SHORTCUTS_TOKEN", TOKEN)
    caplog.set_level(logging.DEBUG)
    out = io.StringIO()
    png = tmp_path / "p.png"
    assert pair.run_pair(_args(png=str(png)), out=out) == 0
    text = out.getvalue()
    err = capsys.readouterr()
    assert TOKEN not in text and TOKEN not in err.out and TOKEN not in err.err
    assert TOKEN not in caplog.text
    assert "https://abc.trycloudflare.com" in text and "contains your Shortcuts token" in text
    assert stat.S_IMODE(png.stat().st_mode) == 0o600


def test_run_pair_show_token_opt_in(monkeypatch):
    monkeypatch.setitem(SECRETS, "SHORTCUTS_TOKEN", TOKEN)
    out = io.StringIO()
    assert pair.run_pair(_args(show_token=True), out=out) == 0
    assert TOKEN in out.getvalue()


def test_run_pair_weak_token_fails(monkeypatch, capsys):
    monkeypatch.setitem(SECRETS, "SHORTCUTS_TOKEN", "Tok3nX")
    out = io.StringIO()
    assert pair.run_pair(_args(), out=out) == 1
    err = capsys.readouterr().err
    assert "Tok3nX" not in err and "Tok3nX" not in out.getvalue() and "shorter than" in err


def test_register_adds_cli_command():
    seen = {}

    class Ctx:
        def register_hook(self, *a, **k): pass
        def register_platform(self, *a, **k): pass
        def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
            seen.update(name=name, setup=setup_fn, handler=handler_fn)

    P.register(Ctx())
    assert seen["name"] == "shortcuts" and seen["handler"] is pair.cli_handler
    import argparse
    ap = argparse.ArgumentParser(); seen["setup"](ap)
    a = ap.parse_args(["pair", "--url", "https://h.example.com", "--png", "/tmp/x.png"])
    assert a.shortcuts_command == "pair" and a.url == "https://h.example.com" and not a.show_token


def test_register_without_cli_support():
    class Ctx:  # older Hermes: no register_cli_command
        def register_hook(self, *a, **k): pass
        def register_platform(self, *a, **k): pass
    P.register(Ctx())
