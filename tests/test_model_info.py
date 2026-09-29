# Model info and the model browsers (DiceForge/model_info.py): the info files, Civitai data, card data, local previews and the server routes. Civitai
# is replaced by a stand-in, so the tests never go online.
import hashlib
import os
import pytest
from aiohttp import web
from DiceForge import model_info
from DiceForge.model_info import browser_entry, civitai_summary, info_file, local_preview, read_info, sha256_of, thumbnail, write_info

CIVITAI_VERSION = {
    "id": 22, "modelId": 11, "name": "v2", "baseModel": "Illustrious", "trainedWords": ["ink style"],
    "model": {"name": "Ink", "type": "LORA"},
    "images": [{"url": f"https://image.civitai.com/x/original=true/{index}.jpeg", "type": "image", "nsfwLevel": index, "width": 1, "height": 1} for index in range(15)],
}


@pytest.fixture
def civitai(monkeypatch):
    """Civitai stand-in: answers with CIVITAI_VERSION and counts the lookups."""
    calls = []

    async def lookup(sha256):
        calls.append(sha256)
        return {**civitai_summary(CIVITAI_VERSION), "checked": 1.0}
    monkeypatch.setattr(model_info, "civitai_lookup", lookup)
    return calls


def test_info_files_stay_inside_the_info_folder():
    assert info_file("loras", "style/a.safetensors").endswith(os.path.join("loras", "style", "a.safetensors.json"))
    with pytest.raises(web.HTTPBadRequest):
        info_file("loras", "../../outside")


def test_info_round_trip_and_missing_info():
    write_info("vae", "x.safetensors", {"user": {"notes": "ünïcode"}})
    assert read_info("vae", "x.safetensors") == {"user": {"notes": "ünïcode"}}
    assert read_info("vae", "never.safetensors") == {}


def test_sha256_of_a_file(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"abc" * 1000)
    assert sha256_of(str(path)) == hashlib.sha256(b"abc" * 1000).hexdigest()


def test_civitai_summary_and_thumbnails():
    summary = civitai_summary(CIVITAI_VERSION)
    assert summary["model_name"] == "Ink" and summary["version_name"] == "v2" and summary["base_model"] == "Illustrious"
    assert summary["trigger_words"] == ["ink style"] and summary["url"] == "https://civitai.com/models/11?modelVersionId=22"
    assert len(summary["images"]) == 12
    assert summary["images"][0]["url"].endswith("/width=450/0.jpeg") and summary["images"][0]["full"].endswith("/original=true/0.jpeg")
    assert thumbnail("https://a/original=true/b.png") == "https://a/width=450/b.png"


def test_local_preview_prefers_name_preview_png(tmp_path):
    model = str(tmp_path / "a.safetensors")
    assert local_preview(model, {"a.png", "a.preview.png"}).endswith("a.preview.png")
    assert local_preview(model, {"a.webp"}).endswith("a.webp")
    assert local_preview(model, {"b.png"}) is None


def test_card_data_uses_only_fresh_info(models):
    path = models("loras", "ink.safetensors")
    stat = os.stat(path)
    write_info("loras", "ink.safetensors", {"size": stat.st_size, "mtime": stat.st_mtime, "civitai": {**civitai_summary(CIVITAI_VERSION), "checked": 1.0},
                                             "user": {"trigger_words": "mine, also mine", "settings": " 30 steps "}})
    entry = browser_entry("loras", "ink.safetensors", path, set())
    assert entry["checked"] and entry["found"] and entry["name"] == "Ink - v2" and entry["base_model"] == "Illustrious"
    assert entry["trigger_words"] == ["mine", "also mine"] and entry["settings"] == "30 steps"
    assert entry["image"]["url"].endswith("0.jpeg") and entry["preview"] is False
    write_info("loras", "ink.safetensors", {**read_info("loras", "ink.safetensors"), "size": stat.st_size + 1}) # The file changed since the lookup.
    stale = browser_entry("loras", "ink.safetensors", path, {"ink.png"})
    assert not stale["checked"] and stale["base_model"] == "" and stale["preview"] is True and stale["trigger_words"] == ["mine", "also mine"]


def test_model_info_route_hashes_once_and_keeps_your_notes(api, models, civitai):
    path = models("checkpoints", "sdxl/base.safetensors", b"weights")
    status, info = api("GET", "/diceforge/model-info?kind=checkpoints&file=sdxl/base.safetensors")
    assert status == 200 and info["sha256"] == hashlib.sha256(b"weights").hexdigest() and info["civitai"]["base_model"] == "Illustrious"
    api("GET", "/diceforge/model-info?kind=checkpoints&file=sdxl/base.safetensors")
    assert len(civitai) == 1 # Cached: asked once.
    api("GET", "/diceforge/model-info?kind=checkpoints&file=sdxl/base.safetensors&refresh=1")
    assert len(civitai) == 2
    status, _ = api("POST", "/diceforge/model-info", {"kind": "checkpoints", "file": "sdxl/base.safetensors", "user": {"notes": "x" * 20000, "evil": "no", "name": "Base"}})
    assert status == 200
    user = read_info("checkpoints", "sdxl/base.safetensors")["user"]
    assert user == {"notes": "x" * 10000, "name": "Base"}
    with open(path, "wb") as file:
        file.write(b"new weights, new size")
    _, info = api("GET", "/diceforge/model-info?kind=checkpoints&file=sdxl/base.safetensors")
    assert info["sha256"] == hashlib.sha256(b"new weights, new size").hexdigest() and info["user"]["name"] == "Base" and len(civitai) == 3


def test_model_info_route_errors(api, models):
    assert api("GET", "/diceforge/model-info?kind=nope&file=x")[0] == 400
    assert api("GET", "/diceforge/model-info?kind=loras&file=missing.safetensors")[0] == 404
    assert api("POST", "/diceforge/model-info", {"kind": "loras", "file": "missing.safetensors", "user": {}})[0] == 404


def test_model_browser_and_preview_routes(api, models):
    path = models("loras", "anime/ink.safetensors")
    with open(os.path.splitext(path)[0] + ".preview.png", "wb") as file:
        file.write(b"\x89PNG fake")
    models("loras", "plain.safetensors")
    status, body = api("GET", "/diceforge/model-browser?kind=loras")
    assert status == 200 and [(entry["file"].replace("\\", "/"), entry["preview"]) for entry in body["files"]] == [("anime/ink.safetensors", True), ("plain.safetensors", False)]
    assert api("GET", "/diceforge/model-preview?kind=loras&file=anime/ink.safetensors") == (200, b"\x89PNG fake")
    assert api("GET", "/diceforge/model-preview?kind=loras&file=plain.safetensors")[0] == 404
    assert api("GET", "/diceforge/model-browser?kind=nope")[0] == 400
