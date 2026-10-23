# The routes leave their work with files to a thread (routes.in_thread): a file opened, a folder listed or walked on the event loop holds
# up every other request of ComfyUI and the progress of a run meanwhile. Sonar (S7493) only sees an open() written in the handler itself, so
# this test calls every DiceForge route, with real files where it needs them, and records each file of the test's folders opened, listed or
# walked on the loop's own thread. In threads, two requests can change the same file at once: the changes that read, change and write a
# shared file go one at a time, and keep each other's changes.
import asyncio
import builtins
import io
import os
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
import pytest
from PIL import Image
from DiceForge import dice_grid, lora_stack, model_info, wildcards_api
from test_robustness import ROUTES

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


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


def zipped(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def a_grid(node):
    store = dice_grid.GridStore(dice_grid.grid_key("grid", node))
    store.clear()
    store.add(Image.new("RGB", (64, 64)), "ink", "", Image.new("RGB", (128, 128)))
    store.save()


def test_no_route_works_with_files_on_the_event_loop(api, wildcards, models, on_the_loop):
    wildcards("color.txt", "red\nblue\n")
    wildcards("pack.yaml", "pack:\n  pose: [sitting, standing]\n  other: [x]\n")
    wildcards("folder/a.txt", "a\n")
    models("loras", "style/ink.safetensors")
    models("loras", "style/old.safetensors")
    a_grid("1")
    ink = "kind=loras&file=style/ink.safetensors"
    done = []

    def call(method, path, body=None, data=None):
        status, answer = api(method, path, body, data) if data is not None else api(method, path, body)
        assert status < 400, (method, path, status, answer) # The route did its work, not refused it before any file.
        done.append(path)
        return answer
    # The Wildcard Browser.
    call("GET", "/diceforge/wildcards")
    call("GET", "/diceforge/wildcards/file?name=color")
    call("POST", "/diceforge/wildcards/file", {"name": "made", "text": "a\nb"})
    call("POST", "/diceforge/wildcards/rename", {"name": "made", "to": "moved/made"})
    undo = call("DELETE", "/diceforge/wildcards/file?name=moved/made")["undo"]
    call("POST", "/diceforge/wildcards/restore", {"id": undo})
    call("GET", "/diceforge/wildcards/yaml?file=pack.yaml")
    call("POST", "/diceforge/wildcards/yaml", {"file": "pack.yaml", "text": "pack:\n  pose: [sitting, standing]\n  other: [x, y]\n"})
    call("POST", "/diceforge/wildcards/picture?name=pack/pose", data=PNG)
    call("GET", "/diceforge/wildcards/picture?name=pack/pose")
    call("DELETE", "/diceforge/wildcards/picture?name=pack/pose")
    call("GET", "/diceforge/wildcards/cards")
    call("POST", "/diceforge/wildcards/favorite", {"name": "color", "favorite": True})
    call("GET", "/diceforge/wildcards/search?q=re")
    call("GET", "/diceforge/wildcards/preview?name=color")
    call("POST", "/diceforge/wildcards/replace", {"find": "blue", "replace": "navy", "apply": True})
    call("POST", "/diceforge/wildcards/convert", {"name": "folder", "to": "yaml"})
    call("POST", "/diceforge/wildcards/convert", {"name": "folder", "to": "txt"})
    call("POST", "/diceforge/wildcards/import", data=zipped({"zipped/z.txt": "z\n"}))
    call("GET", "/diceforge/wildcards/export")
    call("DELETE", "/diceforge/wildcards/yaml?file=pack.yaml")
    # Models: Model info, the browsers, files, LoRA Stack presets, the Civitai key.
    call("GET", "/diceforge/model-browser?kind=loras")
    call("GET", f"/diceforge/model-info?{ink}")
    call("POST", "/diceforge/model-favorite", {"kind": "loras", "file": "style/ink.safetensors", "favorite": True})
    call("POST", "/diceforge/model-info", {"kind": "loras", "file": "style/ink.safetensors", "user": {"notes": "x"}})
    call("POST", "/diceforge/model-bases", {"items": [{"kind": "loras", "file": "style/ink.safetensors"}]})
    call("POST", "/diceforge/lora-triggers", {"loras": ["style/ink.safetensors"]})
    call("POST", "/diceforge/lora-presets", {"name": "p", "stack": {"rows": []}})
    call("GET", "/diceforge/lora-presets")
    call("GET", "/diceforge/lora-presets/file?name=p")
    call("DELETE", "/diceforge/lora-presets?name=p")
    call("POST", "/diceforge/models/rename", {"kind": "loras", "file": "style/old.safetensors", "to": "style/older"})
    undo = call("DELETE", "/diceforge/models/file?kind=loras&file=style/older.safetensors")["undo"]
    call("POST", "/diceforge/models/restore", {"kind": "loras", "id": undo})
    call("POST", "/diceforge/civitai/key", {"key": ""})
    call("GET", "/diceforge/civitai/key")
    # XY Plot's preview with a LoRA axis (the LoRA files are listed), and Dice Grid's cells.
    models("loras", "style/new.safetensors") # The LoRA list is listed again.
    call("POST", "/diceforge/xy-plot", {"x_type": "lora", "x_values": "style/*", "y_type": "none", "y_values": ""})
    call("GET", "/diceforge/grid?node=1")
    call("GET", "/diceforge/grid/image?node=1&file=00000.png&full=1")
    call("POST", "/diceforge/grid/keep", {"node": "1", "file": "00000.png", "kept": True})
    call("POST", "/diceforge/grid/save", {"node": "1"})
    for method, path in ROUTES: # And every route with nothing in it.
        api(method, path, {})
    assert on_the_loop == []


def test_stars_clicked_at_once_are_all_kept(wildcards):
    names = [f"w{index}" for index in range(24)]
    for name in names:
        wildcards(f"{name}.txt", "x\n")
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda name: wildcards_api.set_favorite(name, True), names))
    assert wildcards_api.read_favorites() == set(names)


def test_a_lookup_keeps_the_star_and_notes_saved_while_it_ran(api, models, monkeypatch):
    models("loras", "ink.safetensors")

    async def lookup(sha256): # Civitai answers while the user stars the model and writes a note.
        await asyncio.get_running_loop().run_in_executor(None, model_info.update_info, "loras", "ink.safetensors",
                                                         lambda info: info.update(favorite=True, user={"notes": "mine"}))
        return {"found": False, "checked": 1.0}
    monkeypatch.setattr(model_info, "civitai_lookup", lookup)
    status, body = api("GET", "/diceforge/model-info?kind=loras&file=ink.safetensors")
    assert status == 200 and body["favorite"] is True and body["user"] == {"notes": "mine"}
    saved = model_info.read_info("loras", "ink.safetensors")
    assert saved["favorite"] is True and saved["user"] == {"notes": "mine"} and saved["sha256"] == body["sha256"]


def test_a_preset_that_cant_be_read_says_why(api, monkeypatch):
    assert api("POST", "/diceforge/lora-presets", {"name": "locked", "stack": {"rows": []}})[0] == 200
    try:
        def refuse(path):
            raise PermissionError(13, "Permission denied", path)
        monkeypatch.setattr(lora_stack, "read_json", refuse)
        status, text = api("GET", "/diceforge/lora-presets/file?name=locked")
        assert status == 400 and "Permission denied" in text
        assert api("GET", "/diceforge/lora-presets/file?name=nothing")[0] == 404
    finally:
        api("DELETE", "/diceforge/lora-presets?name=locked")
