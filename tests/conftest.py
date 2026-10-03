# Test setup: the DiceForge nodes run inside ComfyUI (folder_paths, comfy_api, nodes), so the tests import a real ComfyUI checkout. Set COMFYUI_PATH to
# its folder, or keep this repository next to it (../ComfyUI) or inside its custom_nodes. Everything the nodes write (seed memory, model info, presets,
# grids, saved images) goes to a temporary folder instead of ComfyUI's user and output folders, and the model and wildcard folders the tests use are
# temporary too, so the tests never touch your ComfyUI.
import asyncio
import json as json_module
import os
import shutil
import sys
import tempfile
import types
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_comfyui():
    candidates = [os.environ.get("COMFYUI_PATH"), os.path.join(os.path.dirname(REPO), "ComfyUI"), os.path.dirname(os.path.dirname(REPO))]
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, "folder_paths.py")) and os.path.isdir(os.path.join(path, "comfy_api")):
            return os.path.abspath(path)
    return None


COMFYUI = find_comfyui()
if COMFYUI is None:
    pytest.exit("DiceForge tests need a ComfyUI checkout: set COMFYUI_PATH to its folder (the one with main.py), for example\n"
                "  COMFYUI_PATH=~/ComfyUI python -m pytest tests", returncode=4)
sys.path[:0] = [COMFYUI, REPO]
TEMP = tempfile.mkdtemp(prefix="diceforge-tests-")

# ComfyUI reads its command line when comfy.cli_args is first imported: --cpu, so the tests run without a GPU.
_argv = sys.argv
sys.argv = [_argv[0], "--cpu"]
import comfy.options  # noqa: E402

comfy.options.enable_args_parsing()
import comfy.cli_args  # noqa: E402,F401

sys.argv = _argv
import folder_paths  # noqa: E402

folder_paths.set_user_directory(os.path.join(TEMP, "user")) # Before DiceForge is imported: its memory and info folders are set at import.
folder_paths.set_output_directory(os.path.join(TEMP, "output"))
folder_paths.set_input_directory(os.path.join(TEMP, "input"))
for kind in ("checkpoints", "loras", "vae", "diffusion_models", "text_encoders", "embeddings"):
    folder_paths.folder_names_and_paths[kind] = ([os.path.join(TEMP, "models", kind)], folder_paths.supported_pt_extensions)
    os.makedirs(os.path.join(TEMP, "models", kind), exist_ok=True)

import DiceForge  # noqa: E402,F401  (the package, as ComfyUI loads it: every node module and its server routes)
from DiceForge import clip_text_encode_pos_neg as prompts  # noqa: E402
from DiceForge import seed_modes  # noqa: E402

folder_paths.folder_names_and_paths["wildcards"] = ([os.path.join(TEMP, "wildcards")], set())


# Property-based tests (Hypothesis): many generated inputs per test. Profiles: "default" (random examples, a different search each run), "ci" (the
# same examples every run, so CI never fails by chance), "thorough" (many more examples, for a long hunt). Pick one with HYPOTHESIS_PROFILE.
from hypothesis import HealthCheck, settings  # noqa: E402

_common = dict(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow, HealthCheck.data_too_large])
settings.register_profile("default", max_examples=200, **_common)
settings.register_profile("ci", max_examples=200, derandomize=True, database=None, print_blob=True, **_common)
settings.register_profile("thorough", max_examples=3000, **_common)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TEMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def fresh_memory():
    """Every test starts with an empty seed memory (shuffle, balanced, mutate)."""
    memory = seed_modes.MEMORY
    with memory.lock:
        if memory.connection is not None:
            memory.connection.close()
            memory.connection = None
    if os.path.exists(memory.path):
        os.remove(memory.path)
    yield


@pytest.fixture(autouse=True)
def offline_civitai(monkeypatch, tmp_path):
    """No test goes online: Civitai is a closed local port unless a test starts the stand-in (civitai_server). No API key, no downloads left over."""
    from DiceForge import model_info, model_manager
    monkeypatch.setattr(model_manager, "CIVITAI_API", "http://127.0.0.1:9/api/v1")
    monkeypatch.setattr(model_info, "CIVITAI_MODEL", "http://127.0.0.1:9/api/v1/models/{}")
    monkeypatch.setattr(model_manager, "KEY_FILE", str(tmp_path / "civitai.json"))
    for variable in ("CIVITAI_API_KEY", "DICEFORGE_CIVITAI_KEY"):
        monkeypatch.delenv(variable, raising=False)
    for variable in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(variable, ",".join(filter(None, ["127.0.0.1", "localhost", os.environ.get(variable)])))
    model_manager.JOBS.clear()
    yield
    model_manager.JOBS.clear()


@pytest.fixture(autouse=True)
def own_sampler_presets(monkeypatch, tmp_path):
    """Saved sampler presets go to the test's folder, not the ComfyUI user folder."""
    from DiceForge import sampler_presets
    monkeypatch.setattr(sampler_presets, "PRESETS_FILE", str(tmp_path / "sampler_presets.json"))


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    return path


@pytest.fixture
def wildcards(tmp_path, monkeypatch):
    """An empty wildcards folder; returns a function that writes name.txt (or any file) into it."""
    folder = tmp_path / "wildcards"
    folder.mkdir()
    monkeypatch.setitem(folder_paths.folder_names_and_paths, "wildcards", ([str(folder)], set()))
    from DiceForge import wildcards_api
    monkeypatch.setattr(wildcards_api, "FAVORITES_FILE", str(tmp_path / "wildcard_favorites.json")) # Each test starts with no favorites.
    prompts.index_cache.update(signature=None, entries={})

    def add(name, text):
        path = write(str(folder / name), text)
        prompts.wildcard_index(refresh=True)
        return path

    add.folder = folder
    return add


@pytest.fixture
def models(tmp_path, monkeypatch):
    """Empty model folders (loras, checkpoints...); returns a function that creates a model file of a kind, with optional content."""
    for kind in ("checkpoints", "loras", "vae", "diffusion_models", "text_encoders"):
        (tmp_path / kind).mkdir()
        monkeypatch.setitem(folder_paths.folder_names_and_paths, kind, ([str(tmp_path / kind)], folder_paths.supported_pt_extensions))
    folder_paths.filename_list_cache.clear()

    def add(kind, name, content=b"model"):
        path = tmp_path / kind / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        folder_paths.filename_list_cache.clear()
        return str(path)

    add.root = tmp_path
    return add


@pytest.fixture
def api():
    """The DiceForge server routes on a test server: api(method, path, json=...) returns (status, body): JSON, text or bytes. data=... sends a raw
    body instead (text or bytes, for requests that aren't JSON)."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from DiceForge import lora_stack, model_info, model_manager, sampler_presets, wildcards_api, xy_plot

    routes = web.RouteTableDef()
    fake_server = types.ModuleType("server")
    fake_server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes))
    real_server = sys.modules.get("server")
    sys.modules["server"] = fake_server
    try:
        for module in (wildcards_api, model_info, lora_stack, model_manager, sampler_presets, xy_plot):
            module.register_routes()
    finally:
        if real_server is None:
            sys.modules.pop("server", None)
        else:
            sys.modules["server"] = real_server

    def call(method, path, json=None, data=None):
        async def run():
            app = web.Application() # One per call: an application belongs to the event loop it first runs in.
            app.add_routes(routes)
            async with TestClient(TestServer(app)) as client:
                response = await (client.request(method, path, data=data) if data is not None else client.request(method, path, json=json))
                raw = await response.read()
                await asyncio.gather(*model_manager.TASKS.values(), return_exceptions=True) # Downloads it started finish before this loop closes.
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    return response.status, raw # A file, like a preview image.
                try:
                    return response.status, json_module.loads(text)
                except ValueError:
                    return response.status, text
        return asyncio.run(run())

    return call
