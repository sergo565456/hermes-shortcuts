"""Redaction, HEIC, source labels, private URLs, and the settings schema."""
import asyncio
import logging
import pathlib
import sys

import aiohttp
import pytest

import conftest as C

C.load_plugin()
AD = sys.modules["hermes_shortcuts.adapter"]
A = sys.modules["hermes_shortcuts.actions"]
from test_security import GOOD, H, _with_adapter, run

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRET = "sk-abcdefghijklmnopqrstuvwxyz"
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"


class _Ctx:
    def __init__(self, redact):
        self._redact = redact
        self.surface = "shortcuts"
        self.client = None

    def redact_text(self, text, force=False):
        return self._redact(text, force)

    def session_surface(self):
        return self.surface

    def turn_client(self):
        return self.client

    def get_config(self, key, default=None):
        return getattr(self, "settings", {}).get(key, default)


def test_manifest_config_schema_marks_the_token_secret():
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert "config_schema:" in text
    assert "type: secret" in text
    assert "env: SHORTCUTS_TOKEN" in text
    assert 'requires_hermes: ">=0.23.1"' in text
    assert "pre_llm_call" in text


def test_fallback_redact_and_public_urls():
    assert "sk-" not in A.fallback_redact("note " + SECRET)
    assert "«redacted»" in A.fallback_redact("note " + SECRET)
    assert "user:pass@" not in A.fallback_redact("https://user:pass@example.com/a")
    assert A.fallback_redact("hello") == "hello"
    assert A.strip_secret_value("token " + GOOD, GOOD) == "token «redacted:shortcuts-token»"
    assert A.strip_secret_value("nope", GOOD) == "nope"
    assert A.is_public_http_url("https://example.com/a")
    assert not A.is_public_http_url("http://169.254.169.254/latest")
    assert not A.is_public_http_url("http://127.0.0.1/")
    assert not A.is_public_http_url("http://10.1.2.3/")
    assert not A.is_public_http_url("http://[::1]/")
    assert not A.is_public_http_url("https://user:secret@example.com/a")
    assert not A.is_public_http_url("http://metadata.google.internal/")
    assert not A.is_public_http_url("file:///etc/passwd")
    assert A.classify_source("ask", False) == "siri"
    assert A.classify_source("ask", True) == "photo"
    assert A.classify_source("share", False) == "share-sheet"
    assert A.classify_source("event", False) == "event"
    assert A.source_client("siri") == {"name": "siri", "kind": "mobile"}
    assert A.query_has_token({"Token": "x"}) and not A.query_has_token({"text": "x"})


def test_plugin_settings_apply_when_env_is_unset():
    ctx = _Ctx(lambda text, force=False: text)
    ctx.settings = {"tool_profile": "full", "sync_timeout": 40}
    saved = AD._CTX
    AD._CTX = ctx
    try:
        ad = AD.ShortcutsAdapter(sys.modules["gateway.config"].PlatformConfig({}))
        assert ad._tool_profile == "full"
        assert ad._sync_timeout == 40
    finally:
        AD._CTX = saved


def test_env_still_wins_over_plugin_settings():
    ctx = _Ctx(lambda text, force=False: text)
    ctx.settings = {"port": 9999}

    async def fn(ad, ok, s, u):
        assert ad._port != 9999  # SHORTCUTS_PORT from the test env wins
    saved = AD._CTX
    AD._CTX = ctx
    try:
        run(_with_adapter(fn))
    finally:
        AD._CTX = saved


def test_shared_secrets_are_scrubbed_with_force_before_prompt_forward_and_memory(caplog):
    def redact(text, force=False):
        assert force is True
        return text.replace(SECRET, "«redacted:sk-»").replace(GOOD, "«redacted:shortcuts-token»")

    ctx = _Ctx(redact)
    saved = AD._CTX
    AD._CTX = ctx
    caplog.set_level(logging.INFO, logger="hermes_shortcuts.adapter")
    try:
        async def fn(ad, ok, s, u):
            r = await s.post(u + "/v1/share", json={
                "action": "remember", "text": "keep " + SECRET + " and " + GOOD, "notify": False,
                "url": "http://169.254.169.254/latest/meta-data",
            }, headers=H)
            body = await r.json()
            assert r.status == 200 and body["source"] == "share-sheet"
            assert SECRET not in ad.last_event.text and GOOD not in ad.last_event.text
            assert "169.254.169.254" not in ad.last_event.text
            assert "Phone source: Share Sheet" in ad.last_event.text
            assert ad.last_event.user_name == "Share Sheet"
            assert ad.last_event.metadata["shortcuts_client"]["name"] == "share-sheet"

            sent = []

            class TG:
                async def send(self, chat_id, content, metadata=None):
                    sent.append(content)
                    return type("R", (), {"success": True, "message_id": "9"})()

            class Runner:
                adapters = {"telegram": TG()}
                config = type("C", (), {"get_home_channel": lambda self, plat: type("H", (), {"chat_id": "1", "thread_id": None})()})()

            ad.gateway_runner = Runner()
            ad._notify_target = "telegram"
            assert await ad._forward("remember", "echo " + SECRET, "share-sheet") == "telegram"
            assert SECRET not in sent[0] and "Share Sheet" in sent[0]

            C.SESSION_ENV.update({"HERMES_SESSION_PLATFORM": "shortcuts", "HERMES_SESSION_CHAT_ID": "sc-mem"})
            ad._pending["sc-mem"] = AD._Pending(action="remember", notify=False,
                                                future=asyncio.get_running_loop().create_future(),
                                                source_id="share-sheet")
            decision = AD._on_pre_tool_call("memory", {"action": "add", "content": "save " + SECRET})
            assert decision["action"] == "modify"
            assert SECRET not in decision["args"]["content"]
            # a non-memory tool only loses the bearer token, not an unrelated string
            plain = AD._on_pre_tool_call("web_search", {"query": "weather"})
            assert plain is None

            ctx.client = {"name": "siri", "kind": "mobile"}
            AD._LOGGED_TURNS.clear()
            AD._on_pre_llm_call()
            assert any("source=share-sheet" in rec.message and "surface=shortcuts" in rec.message
                       and "client=siri" in rec.message for rec in caplog.records)
        run(_with_adapter(fn))
    finally:
        AD._CTX = saved
        AD._LOGGED_TURNS.clear()
        C.SESSION_ENV.clear()


def test_sources_and_query_token_and_executables():
    async def fn(ad, ok, s, u):
        r = await s.post(u + "/v1/ask", json={"text": "hi", "notify": False}, headers=H)
        body = await r.json()
        assert body["source"] == "siri" and ad.last_event.user_name == "Siri"
        assert ad.last_event.text.startswith("[Phone source: Siri]\n")
        r = await s.post(u + "/v1/event", json={"event": "alarm_off", "notify": False}, headers=H)
        assert (await r.json())["source"] == "event"
        assert ad.last_event.user_name == "Event"
        r = await s.post(u + "/v1/ask?token=should-not-appear", json={"text": "hi"}, headers=H)
        err = await r.json()
        assert r.status == 400 and "URL" in err["error"] and "should-not-appear" not in err["error"]
        form = aiohttp.FormData()
        form.add_field("action", "document")
        form.add_field("file", b"\x7fELF" + b"\x00" * 8, filename="x")
        r = await s.post(u + "/v1/share", data=form, headers=H)
        assert r.status == 415
    run(_with_adapter(fn))


def test_heic_converts_when_decoder_exists_and_fails_closed_when_it_does_not(monkeypatch):
    jpeg = b"\xff\xd8\xff\x00converted"

    async def ok_path(ad, ok, s, u):
        monkeypatch.setattr(AD, "convert_heif_to_jpeg", lambda data, max_bytes, **k: jpeg)
        form = aiohttp.FormData()
        form.add_field("action", "receipt")
        form.add_field("file", HEIC, filename="IMG_1.HEIC", content_type="image/heic")
        r = await s.post(u + "/v1/share", data=form, headers=H)
        body = await r.json()
        assert r.status == 200 and body["source"] == "photo"
        assert ad.last_event.user_name == "Photo"
        assert ad.last_event.media_types == ["image/jpeg"]
        assert pathlib.Path(ad.last_event.media_urls[0]).read_bytes() == jpeg

    async def missing(ad, ok, s, u):
        def boom(data, max_bytes, **k):
            raise AD.HeifUnavailable()
        monkeypatch.setattr(AD, "convert_heif_to_jpeg", boom)
        form = aiohttp.FormData()
        form.add_field("action", "document")
        form.add_field("file", HEIC, filename="p.heic")
        r = await s.post(u + "/v1/share", data=form, headers=H)
        assert r.status == 415 and "pillow-heif" in (await r.json())["error"]

    async def huge(ad, ok, s, u):
        def boom(data, max_bytes, **k):
            raise AD.HeifRejected("too-large")
        monkeypatch.setattr(AD, "convert_heif_to_jpeg", boom)
        form = aiohttp.FormData()
        form.add_field("action", "document")
        form.add_field("file", HEIC, filename="p.heic")
        r = await s.post(u + "/v1/share", data=form, headers=H)
        assert r.status == 413

    run(_with_adapter(ok_path))
    run(_with_adapter(missing))
    run(_with_adapter(huge))


def test_convert_enforces_pixel_cap_and_restores_limit(monkeypatch):
    class Img:
        size = (20, 10)
        mode = "RGBA"

        def load(self):
            return None

        def convert(self, mode):
            self.mode = mode
            return self

        def save(self, buf, format, quality):
            buf.write(b"\xff\xd8\xffok")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Image:
        MAX_IMAGE_PIXELS = 321
        DecompressionBombError = type("DecompressionBombError", (Exception,), {})

        @staticmethod
        def open(_buf):
            return Img()

    monkeypatch.setattr(AD, "_load_heif", lambda: Image)
    assert AD.convert_heif_to_jpeg(b"heic", 1000).startswith(b"\xff\xd8\xff")
    assert Image.MAX_IMAGE_PIXELS == 321

    class Huge(Img):
        size = (9000, 10)

    class ImageHuge(Image):
        @staticmethod
        def open(_buf):
            return Huge()

    monkeypatch.setattr(AD, "_load_heif", lambda: ImageHuge)
    with pytest.raises(AD.HeifRejected) as err:
        AD.convert_heif_to_jpeg(b"heic", 1000)
    assert err.value.reason == "too-large"
    assert ImageHuge.MAX_IMAGE_PIXELS == 321


def test_sniff_heif_compatible_brands_and_audio():
    heic = b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00heic"
    avif = b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00avif"
    audio = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00mp42"
    assert AD.sniff(heic)[0] == "heic"
    assert AD.sniff(avif)[0] == "avif"
    assert AD.sniff(audio)[0] == "audio"
    assert AD.sniff(b"\xff\xd8\xff\x00")[0] == "image"


def test_local_scrubber_when_context_has_no_redact_text():
    saved = AD._CTX
    AD._CTX = type("Old", (), {})()  # Hermes < 0.23.2: no redact_text
    try:
        assert SECRET not in AD.ShortcutsAdapter._redact(AD.ShortcutsAdapter, "see " + SECRET)
    finally:
        AD._CTX = saved
