# The routes leave their work with files to a thread (model_info.in_thread): a file opened, a folder listed or walked on the event loop holds
# up every other request of ComfyUI and the progress of a run meanwhile. Sonar (S7493) only sees an open() written in the handler itself, so
# this test calls every DiceForge route, with real files where it needs them, and records each file of the test's folders opened, listed or
# walked on the loop's own thread.
import asyncio
import builtins
import os
import tempfile
import pytest
from test_robustness import ROUTES


@pytest.fixture
def on_the_loop(monkeypatch):
    found, root = [], os.path.realpath(tempfile.gettempdir())

    def watched(name, real):
        def call(path=".", *args, **kwargs):
            try:
                asyncio.get_running_loop()
            except RuntimeError: # A thread without a loop: where file work belongs.
                return real(path, *args, **kwargs)
            if isinstance(path, (str, bytes, os.PathLike)) and os.path.realpath(os.fsdecode(path)).startswith(root):
                found.append(f"{name}({os.fsdecode(path)})")
            return real(path, *args, **kwargs)
        return call
    monkeypatch.setattr(builtins, "open", watched("open", builtins.open))
    monkeypatch.setattr(os, "listdir", watched("listdir", os.listdir))
    monkeypatch.setattr(os, "scandir", watched("scandir", os.scandir)) # os.walk too.
    return found


def test_no_route_works_with_files_on_the_event_loop(api, wildcards, models, on_the_loop):
    wildcards("color.txt", "red\nblue\n")
    wildcards("pack.yaml", "pack:\n  pose: [sitting, standing]\n")
    models("loras", "style/ink.safetensors")
    ink = "kind=loras&file=style/ink.safetensors"
    calls = [("GET", "/diceforge/wildcards", None), ("GET", "/diceforge/wildcards/file?name=color", None),
             ("POST", "/diceforge/wildcards/file", {"name": "made", "text": "a\nb"}), ("POST", "/diceforge/wildcards/rename", {"name": "made", "to": "moved/made"}),
             ("DELETE", "/diceforge/wildcards/file?name=moved/made", None), ("GET", "/diceforge/wildcards/yaml?file=pack.yaml", None),
             ("POST", "/diceforge/wildcards/yaml", {"file": "pack.yaml", "text": "pack:\n  pose: [sitting]\n"}), ("GET", "/diceforge/wildcards/cards", None),
             ("POST", "/diceforge/wildcards/favorite", {"name": "color", "favorite": True}), ("GET", "/diceforge/wildcards/picture?name=pack/pose", None),
             ("DELETE", "/diceforge/wildcards/picture?name=pack/pose", None), ("GET", "/diceforge/wildcards/search?q=re", None),
             ("POST", "/diceforge/wildcards/convert", {"name": "color", "to": "yaml"}), ("GET", "/diceforge/wildcards/export", None),
             ("GET", "/diceforge/model-browser?kind=loras", None), ("GET", f"/diceforge/model-info?{ink}", None), ("GET", f"/diceforge/model-preview?{ink}", None),
             ("POST", "/diceforge/model-favorite", {"kind": "loras", "file": "style/ink.safetensors", "favorite": True}),
             ("POST", "/diceforge/model-info", {"kind": "loras", "file": "style/ink.safetensors", "user": {"notes": "x"}}),
             ("POST", "/diceforge/lora-presets", {"name": "p", "stack": {"rows": []}}), ("GET", "/diceforge/lora-presets", None),
             ("GET", "/diceforge/lora-presets/file?name=p", None), ("DELETE", "/diceforge/lora-presets?name=p", None),
             ("POST", "/diceforge/lora-triggers", {"loras": ["style/ink.safetensors"]}), ("GET", "/diceforge/grid?node=1", None),
             ("GET", "/diceforge/civitai/key", None), ("POST", "/diceforge/civitai/key", {"key": ""})]
    calls += [(method, path, {}) for method, path in ROUTES] # And every route with nothing in it.
    for method, path, body in calls:
        api(method, path, body)
    assert on_the_loop == []
