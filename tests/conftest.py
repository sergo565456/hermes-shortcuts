"""Load the plugin as a package with minimal stand-ins for the Hermes modules it imports."""
import importlib.util
import pathlib
import sys
import tempfile
import types
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRETS: dict = {}
SESSION_ENV: dict = {}
CACHE = pathlib.Path(tempfile.mkdtemp(prefix="hs-cache-"))


def _install_stubs():
    if "gateway.platforms.base" in sys.modules:
        return
    gw = types.ModuleType("gateway"); gw.__path__ = []
    cfg = types.ModuleType("gateway.config")
    plats = types.ModuleType("gateway.platforms"); plats.__path__ = []
    base = types.ModuleType("gateway.platforms.base")
    ev = types.ModuleType("gateway.platforms.event")
    shared = types.ModuleType("gateway.platforms._shared")
    agent = types.ModuleType("agent"); agent.__path__ = []
    scope = types.ModuleType("agent.secret_scope")
    sctx = types.ModuleType("gateway.session_context")
    sctx.get_session_env = lambda name, default="": SESSION_ENV.get(name, default)

    class Platform(str):
        def __new__(cls, v):
            return str.__new__(cls, v)

    class PlatformConfig:
        def __init__(self, extra=None):
            self.extra = extra or {}

    class SendResult:
        def __init__(self, success=True, message_id=None, error=None):
            self.success, self.message_id, self.error = success, message_id, error

    class BasePlatformAdapter:
        def __init__(self, config, platform):
            self.config, self.platform, self.fatal = config, platform, None
            self.gateway_runner = None

        def _mark_connected(self): pass
        def _mark_disconnected(self): pass
        def _wire_plugin_handlers(self, _): pass
        def _set_fatal_error(self, code, msg, retryable=False): self.fatal = code

        def build_source(self, chat_id, **kw):
            return types.SimpleNamespace(chat_id=chat_id, **kw)

        async def handle_message(self, event):
            self.last_event = event
            await self.send(event.source.chat_id, "reply:" + event.text[:20])
            await self.on_processing_complete(event, ProcessingOutcome.SUCCESS)

    def _write(prefix, ext, data):
        p = CACHE / f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
        p.write_bytes(data)
        return str(p)

    def cache_image_from_bytes(data, ext=".jpg"):
        return _write("img", ext, data)

    def cache_audio_from_bytes(data, ext=".ogg"):
        return _write("audio", ext, data)

    def cache_document_from_bytes(data, filename):
        name = pathlib.Path(filename).name
        p = CACHE / f"doc_{uuid.uuid4().hex[:8]}_{name}"
        p.write_bytes(data)  # OSError for over-long names, like the real helper
        return str(p)

    class MessageType:
        TEXT, PHOTO, VOICE, DOCUMENT = "text", "photo", "voice", "document"

    class ProcessingOutcome:
        SUCCESS, FAILURE = "success", "failure"

    class MessageEvent:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def get_secret(name, default=None):
        return SECRETS.get(name, default)

    cfg.Platform, cfg.PlatformConfig = Platform, PlatformConfig
    base.BasePlatformAdapter, base.SendResult = BasePlatformAdapter, SendResult
    base.cache_image_from_bytes = cache_image_from_bytes
    base.cache_audio_from_bytes = cache_audio_from_bytes
    base.cache_document_from_bytes = cache_document_from_bytes
    ev.MessageEvent, ev.MessageType, ev.ProcessingOutcome = MessageEvent, MessageType, ProcessingOutcome
    shared.get_scoped_secret = get_secret
    scope.get_secret = get_secret
    for name, mod in {"gateway": gw, "gateway.config": cfg, "gateway.platforms": plats,
                      "gateway.platforms.base": base, "gateway.platforms.event": ev,
                      "gateway.platforms._shared": shared, "gateway.session_context": sctx, "agent": agent, "agent.secret_scope": scope}.items():
        sys.modules[name] = mod


def load_plugin():
    _install_stubs()
    if "hermes_shortcuts" in sys.modules:
        return sys.modules["hermes_shortcuts"]
    spec = importlib.util.spec_from_file_location("hermes_shortcuts", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_shortcuts"] = mod
    spec.loader.exec_module(mod)
    return mod
