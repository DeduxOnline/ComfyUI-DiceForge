# Model info and the model browsers (DiceForge/model_info.py): the info files, Civitai data, card data, local previews and the server routes. Civitai
# is replaced by a stand-in, so the tests never go online.
import hashlib
import json
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


def test_civitai_summary_keeps_how_each_image_was_made():
    meta = {"prompt": "1girl, solo", "negativePrompt": "lowres", "seed": 3032258275, "steps": 30, "cfgScale": 4, "sampler": "Euler a", "Model": "base",
            "hashes": {"model": "x"}, "resources": [{"name": "a"}], "Size": "", "Clip skip": True, "VAE": None}
    version = {**CIVITAI_VERSION, "images": [{"url": "https://image.civitai.com/x/original=true/64739376.jpeg", "type": "image", "hasMeta": True, "meta": meta},
                                             {"url": "https://image.civitai.com/x/original=true/name.jpeg", "hasMeta": False, "meta": None}, "junk"]}
    first, second = civitai_summary(version)["images"]
    assert first["meta"] == {"prompt": "1girl, solo", "negativePrompt": "lowres", "seed": 3032258275, "steps": 30, "cfgScale": 4, "sampler": "Euler a", "Model": "base"}
    assert first["page"] == "https://civitai.com/images/64739376" and first["hasMeta"] is True
    assert second["meta"] == {} and second["page"] is None # No number in the file name: no page link.


def test_damaged_image_meta_in_an_info_file_is_cleaned():
    info = model_info.clean_info({"civitai": {"images": [{"url": "u", "meta": {"seed": [1], "prompt": {"a": 1}, "steps": 20}}, {"url": "v", "meta": "text"}, {"url": "w"}]}})
    assert [image["meta"] for image in info["civitai"]["images"]] == [{"steps": 20}, {}, {}]


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


def test_info_saved_before_image_meta_is_looked_up_once_more(api, models, civitai):
    path = models("loras", "old.safetensors", b"weights")
    stat = os.stat(path)
    old = {"found": True, "model_name": "Ink", "images": [{"url": "https://image.civitai.com/x/width=450/1.jpeg"}], "checked": 1.0} # No "page", no "meta".
    write_info("loras", "old.safetensors", {"size": stat.st_size, "mtime": stat.st_mtime, "sha256": "abc", "civitai": old})
    info = api("GET", "/diceforge/model-info?kind=loras&file=old.safetensors")[1]
    assert len(civitai) == 1 and all("page" in image for image in info["civitai"]["images"])
    api("GET", "/diceforge/model-info?kind=loras&file=old.safetensors")
    assert len(civitai) == 1 # Once: now it has them.


INK_PAGE = {
    "id": 11, "name": "Ink", "tags": ["anime", "ink", 5, "", None, "x" * 99], "creator": {"username": "inkmaker"},
    "stats": {"downloadCount": 71087, "thumbsUpCount": 2770, "tippedAmountCount": 920, "commentCount": True},
    "modelVersions": [{"id": 23, "name": "v3", "baseModel": "Illustrious", "publishedAt": "2026-05-26T18:39:52.929Z", "stats": {"downloadCount": 52275}},
                      {"id": 22, "name": "v2", "baseModel": "Illustrious", "publishedAt": "2026-04-20T22:36:19.392Z"}, "junk", {"name": "no id"}],
}


def test_civitai_details_keep_tags_counts_creator_and_versions():
    details = model_info.civitai_details(INK_PAGE)
    assert details["tags"] == ["anime", "ink", "5", "x" * 40]
    assert details["stats"] == {"likes": 2770, "downloads": 71087, "tips": 920, "comments": 0} # Not a number: 0.
    assert details["creator"] == "inkmaker" and details["updated"] == "2026-05-26T18:39:52.929Z"
    assert [(version["id"], version["name"], version["downloads"]) for version in details["versions"]] == [(23, "v3", 52275), (22, "v2", 0)]
    for junk in (None, "x", [], {"stats": 5, "creator": "x", "modelVersions": 7, "tags": "abc"}):
        assert model_info.civitai_details(junk) in ({}, {"tags": [], "stats": {"likes": 0, "downloads": 0, "tips": 0, "comments": 0}, "creator": "",
                                                          "versions": [], "updated": ""})


def test_a_newer_version_than_yours_is_named():
    civitai = {**civitai_summary(CIVITAI_VERSION), **model_info.civitai_details(INK_PAGE)}
    assert model_info.newer_version(civitai) == {"id": 23, "name": "v3", "url": "https://civitai.com/models/11?modelVersionId=23"}
    assert model_info.newer_version({**civitai, "version_id": 23}) is None # Yours is the newest.
    assert model_info.newer_version({**civitai, "version_id": 999}) is None # Yours isn't listed (removed): nothing to compare.
    assert model_info.newer_version({**civitai, "versions": []}) is None


def test_browser_cards_carry_the_civitai_page(api, models, civitai, monkeypatch):
    async def details(session, model_id):
        return {**model_info.civitai_details(INK_PAGE), "details_checked": 1.0}
    monkeypatch.setattr(model_info, "civitai_model_details", details)
    models("loras", "ink.safetensors", b"ink")
    api("GET", "/diceforge/model-info?kind=loras&file=ink.safetensors") # The lookup (faked by civitai: the version only)...
    api("GET", "/diceforge/model-info?kind=loras&file=ink.safetensors") # ...then the page, which it lacks.
    entry = next(item for item in api("GET", "/diceforge/model-browser?kind=loras")[1]["files"] if item["file"] == "ink.safetensors")
    assert entry["tags"][:2] == ["anime", "ink"] and entry["stats"]["likes"] == 2770 and entry["creator"] == "inkmaker"
    assert entry["newer"]["name"] == "v3"
    assert entry["sha256"] == hashlib.sha256(b"ink").hexdigest() # Looked up: the browsers find duplicates by it.
    models("loras", "copy of ink.safetensors", b"ink")
    copy = next(item for item in api("GET", "/diceforge/model-browser?kind=loras")[1]["files"] if item["file"] == "copy of ink.safetensors")
    assert copy["sha256"] == "" # Not looked up yet.


def test_info_looked_up_before_the_page_was_kept_gets_only_the_page(api, models, civitai, monkeypatch):
    asked = []

    async def details(session, model_id):
        asked.append(model_id)
        return {"tags": ["anime"], "details_checked": 1.0}
    monkeypatch.setattr(model_info, "civitai_model_details", details)
    path = models("loras", "old.safetensors", b"weights")
    stat = os.stat(path)
    old = {**civitai_summary(CIVITAI_VERSION), "checked": 1.0} # Images with "page": no new lookup for them.
    write_info("loras", "old.safetensors", {"size": stat.st_size, "mtime": stat.st_mtime, "sha256": "abc", "civitai": old})
    info = api("GET", "/diceforge/model-info?kind=loras&file=old.safetensors")[1]
    assert civitai == [] and asked == [11] and info["civitai"]["tags"] == ["anime"] and info["civitai"]["model_name"] == "Ink"
    api("GET", "/diceforge/model-info?kind=loras&file=old.safetensors")
    assert asked == [11] # Once.


def test_civitai_lookup_adds_the_page_and_survives_its_failure(monkeypatch):
    import asyncio
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            pages = {"/by-hash/a": (200, CIVITAI_VERSION), "/by-hash/b": (200, {**CIVITAI_VERSION, "modelId": 12}), "/by-hash/c": (200, {**CIVITAI_VERSION, "modelId": 13}),
                     "/models/11": (200, INK_PAGE), "/models/12": (500, {"error": "down"}), "/models/13": (404, {"error": "gone"})}
            status, body = pages.get(self.path, (404, {"error": "nope"}))
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        host = f"http://127.0.0.1:{server.server_port}"
        monkeypatch.setattr(model_info, "CIVITAI_BY_HASH", host + "/by-hash/{}")
        monkeypatch.setattr(model_info, "CIVITAI_MODEL", host + "/models/{}")
        found = asyncio.run(model_info.civitai_lookup("a"))
        assert found["found"] and found["tags"] == ["anime", "ink", "5", "x" * 40] and found["details_checked"] and found["versions"][0]["name"] == "v3"
        failed = asyncio.run(model_info.civitai_lookup("b")) # The page failed: the version is kept, the page asked again next time.
        assert failed["found"] and failed["model_name"] == "Ink" and "tags" not in failed and "details_checked" not in failed
        gone = asyncio.run(model_info.civitai_lookup("c")) # No page (404): nothing to add, not asked again.
        assert gone["found"] and "tags" not in gone and gone["details_checked"]
        assert asyncio.run(model_info.civitai_lookup("zzz")) == {"found": False, "checked": pytest.approx(gone["checked"], abs=60)}
    finally:
        server.shutdown()
