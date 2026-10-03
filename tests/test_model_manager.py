# Managing LoRA files (DiceForge/model_manager.py): Create (Civitai search and download), Update (rename and move) and Delete, through the server
# routes. Civitai is a small stand-in on the local machine that answers like its API, so nothing goes online.
import asyncio
import hashlib
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import pytest
from DiceForge import model_manager
from DiceForge.model_info import info_file, read_info, write_info

NEON = b"neon lora weights"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c4944415408d763f8cfc000000301010018dd8db40000000049454e44ae426082")


def version(number, *, name="v1", model="Neon", kind="LORA", file="neon_style.safetensors", content=NEON, sha=None, base="Illustrious", host=""):
    return {"id": number, "modelId": 30, "name": name, "baseModel": base, "trainedWords": ["neon glow"], "model": {"name": model, "type": kind},
            "availability": "EarlyAccess" if number == 302 else "Public",
            "files": [{"id": number, "name": file, "sizeKB": len(content) / 1024, "primary": True, "type": "Model",
                       "hashes": {"SHA256": (sha or hashlib.sha256(content).hexdigest()).upper()}, "downloadUrl": f"{host}/download/{number}"}],
            "images": [{"url": f"{host}/image/original=true/1.png", "type": "image", "nsfwLevel": 1, "width": 1, "height": 1}]}


class CivitaiStandIn(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, status, body, content_type="application/json"):
        data = json.dumps(body).encode() if content_type == "application/json" else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        host = f"http://127.0.0.1:{self.server.server_port}"
        url = urlsplit(self.path)
        self.server.requests.append((url.path, parse_qs(url.query), self.headers.get("Authorization")))
        versions = {301: version(301, host=host), 302: version(302, model="Locked", file="locked.safetensors", content=b"locked", host=host),
                    303: version(303, model="Base model", kind="Checkpoint", host=host), 304: version(304, file="bad.safetensors", sha="0" * 64, host=host),
                    305: version(305, file="archive.zip", host=host), 306: version(306, file="slow.safetensors", content=b"s" * 4096, host=host)}
        if url.path == "/api/v1/models" and parse_qs(url.query).get("baseModels") == ["Nope"]:
            return self.answer(400, {"error": "Invalid enum value for baseModels: Nope"})
        if url.path == "/api/v1/models":
            item = {"id": 30, "name": "Neon", "type": "LORA", "nsfw": False, "creator": {"username": "maker"}, "stats": {"downloadCount": 5, "thumbsUpCount": 2},
                    "modelVersions": [versions[301], version(310, name="v0", file="neon_old.safetensors", content=b"old", host=host), "junk"]}
            return self.answer(200, {"items": [item, 5, None], "metadata": {"nextCursor": "page2"}})
        if url.path.startswith("/api/v1/model-versions/"):
            number = int(url.path.rsplit("/", 1)[1])
            return self.answer(200, versions[number]) if number in versions else self.answer(404, {"error": "not found"})
        if url.path.startswith("/download/"):
            number = int(url.path.rsplit("/", 1)[1])
            if number == 302 and self.headers.get("Authorization") != "Bearer goodkey123":
                return self.answer(401, {"error": "login required"})
            if number == 306: # Slow: long enough to be stopped.
                self.send_response(200)
                self.send_header("Content-Length", "4096")
                self.end_headers()
                for _ in range(32):
                    time.sleep(0.05)
                    try:
                        self.wfile.write(b"s" * 128)
                        self.wfile.flush()
                    except OSError:
                        return
                return
            content = {301: NEON, 302: b"locked", 303: NEON, 304: b"not what Civitai says"}[number]
            return self.answer(200, content, "application/octet-stream")
        if url.path.startswith("/image/"):
            return self.answer(200, PNG, "image/png")
        return self.answer(404, {"error": "nope"})


@pytest.fixture
def civitai(monkeypatch):
    """The Civitai stand-in, running; returns the server (server.requests: path, query and Authorization of each request)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), CivitaiStandIn)
    server.requests = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(model_manager, "CIVITAI_API", f"http://127.0.0.1:{server.server_port}/api/v1")
    yield server
    server.shutdown()
    server.server_close()


def download(api, version_id, folder=""):
    status, job = api("POST", "/diceforge/civitai/download", {"kind": "loras", "version_id": version_id, "folder": folder})
    assert status == 200, job
    return model_manager.JOBS[job["id"]]


def test_search_shapes_civitai_answer_and_marks_what_is_here(api, models, civitai):
    models("loras", "mine/neon_style.safetensors", b"another copy, other bytes") # The same file name.
    old = models("loras", "renamed_old.safetensors", b"old") # Civitai's file under another name: known by its hash.
    stat = os.stat(old)
    write_info("loras", "renamed_old.safetensors", {"size": stat.st_size, "mtime": stat.st_mtime, "sha256": hashlib.sha256(b"old").hexdigest()})
    status, body = api("GET", "/diceforge/civitai/search?kind=loras&query=neon&base=Illustrious&sort=Newest&nsfw=1")
    assert status == 200 and body["next"] == "page2" and len(body["items"]) == 1
    item = body["items"][0]
    assert item["name"] == "Neon" and item["creator"] == "maker" and item["downloads"] == 5 and item["url"] == "https://civitai.com/models/30"
    assert [entry["installed"] for entry in item["versions"]] == ["mine/neon_style.safetensors", "renamed_old.safetensors"]
    first = item["versions"][0]
    assert first["base_model"] == "Illustrious" and first["trigger_words"] == ["neon glow"] and first["file"] == {"name": "neon_style.safetensors", "size": len(NEON)}
    assert first["images"][0]["url"].endswith("/image/width=450/1.png")
    path, query, _auth = civitai.requests[-1]
    assert path == "/api/v1/models" and query["types"] == ["LORA", "LoCon", "DoRA"] and query["query"] == ["neon"]
    assert query["baseModels"] == ["Illustrious"] and query["sort"] == ["Newest"] and query["nsfw"] == ["true"]
    api("GET", "/diceforge/civitai/search?sort=Best&cursor=page2")
    assert civitai.requests[-1][1]["sort"] == ["Highest Rated"] and civitai.requests[-1][1]["nsfw"] == ["false"] and civitai.requests[-1][1]["cursor"] == ["page2"]


def test_search_without_civitai_is_a_clear_error(api, models):
    status, text = api("GET", "/diceforge/civitai/search?query=x")
    assert status == 502 and "Civitai could not be reached" in text
    assert api("GET", "/diceforge/civitai/search?kind=vae")[0] == 400 # LoRAs, checkpoints and diffusion models only.


def test_download_saves_the_file_its_civitai_data_and_a_preview(api, models, civitai):
    job = download(api, 301, "styles/neon")
    assert job["status"] == "done" and job["file"] == "styles/neon/neon_style.safetensors" and job["done"] == len(NEON)
    folder = models.root / "loras" / "styles" / "neon"
    assert sorted(os.listdir(folder)) == ["neon_style.preview.png", "neon_style.safetensors"] # No .part left.
    assert (folder / "neon_style.safetensors").read_bytes() == NEON and (folder / "neon_style.preview.png").read_bytes() == PNG
    info = read_info("loras", "styles/neon/neon_style.safetensors")
    assert info["sha256"] == hashlib.sha256(NEON).hexdigest() and info["civitai"]["model_name"] == "Neon" and info["civitai"]["base_model"] == "Illustrious"
    status, listing = api("GET", "/diceforge/model-browser?kind=loras") # The browser shows it at once, looked up, with its preview.
    entry = next(entry for entry in listing["files"] if entry["file"] == "styles/neon/neon_style.safetensors")
    assert entry["found"] and entry["checked"] and entry["preview"] and entry["name"] == "Neon - v1" and entry["trigger_words"] == ["neon glow"]
    status, body = api("GET", "/diceforge/civitai/downloads")
    assert status == 200 and body["jobs"][0]["status"] == "done" and "path" not in body["jobs"][0]
    assert api("POST", "/diceforge/civitai/download", {"version_id": 301, "folder": "styles/neon"})[0] == 409 # Already there.


@pytest.mark.parametrize("body, status", [
    ({"version_id": "301"}, 400), ({"version_id": True}, 400), ({"version_id": -1}, 400), ({"version_id": None}, 400),
    ({"version_id": 301, "folder": "../out"}, 400), ({"version_id": 301, "folder": "a//b"}, 400), ({"version_id": 301, "folder": 'a"b'}, 400),
    ({"version_id": 301, "kind": "checkpoints"}, 400), ({"version_id": 303, "kind": "vae"}, 400), ({"version_id": 303}, 400), ({"version_id": 305}, 400), ({"version_id": 999}, 404)])
def test_download_refusals(body, status, api, models, civitai):
    answer = api("POST", "/diceforge/civitai/download", body)
    assert answer[0] == status and answer[1]
    assert not model_manager.JOBS and os.listdir(models.root / "loras") == []


def test_a_download_that_needs_a_key_and_the_key(api, models, civitai):
    job = download(api, 302)
    assert job["status"] == "error" and "API key" in job["error"]
    assert os.listdir(models.root / "loras") == [] # Nothing half-written.
    assert api("POST", "/diceforge/civitai/key", {"key": "not a key!"})[0] == 400
    status, body = api("POST", "/diceforge/civitai/key", {"key": "goodkey123"})
    assert status == 200 and body == {"set": True, "source": "settings"}
    assert api("GET", "/diceforge/civitai/key")[1] == {"set": True, "source": "settings"} # The key itself never goes back to the browser.
    assert download(api, 302)["status"] == "done"
    assert os.path.isfile(models.root / "loras" / "locked.safetensors")
    assert ("/download/302", {}, "Bearer goodkey123") in civitai.requests
    assert all(auth is None for path, _query, auth in civitai.requests if path.startswith("/image/")) # Images need no key: none is sent.
    assert api("POST", "/diceforge/civitai/key", {"key": ""})[1] == {"set": False, "source": None}
    assert not os.path.exists(model_manager.KEY_FILE)


def test_the_key_goes_only_to_civitai(monkeypatch):
    monkeypatch.setenv("CIVITAI_API_KEY", "envkey1234")
    monkeypatch.setattr(model_manager, "CIVITAI_API", "https://civitai.com/api/v1")
    assert model_manager.api_key() == ("envkey1234", "environment")
    assert model_manager.auth_headers("https://civitai.com/api/download/models/1") == {"Authorization": "Bearer envkey1234"}
    for url in ("https://example.com/file", "http://civitai.com/api", "https://civitai.com.evil.net/x", "https://image.civitai.com/x.png"):
        assert model_manager.auth_headers(url) == {}


def test_a_damaged_download_is_not_kept(api, models, civitai):
    job = download(api, 304)
    assert job["status"] == "error" and "damaged" in job["error"]
    assert os.listdir(models.root / "loras") == []
    assert not os.path.exists(info_file("loras", "bad.safetensors"))


def test_a_download_can_be_stopped(models, civitai):
    async def run():
        job = model_manager.JOBS[(await model_manager.start_download("loras", 306))["id"]] # The live job (the answer is a copy).
        for _ in range(500):
            if job["done"] or job["status"] != "downloading":
                break
            await asyncio.sleep(0.01)
        assert job["status"] == "downloading" and 0 < job["done"] < 4096
        model_manager.cancel_download(job["id"])
        await asyncio.gather(*model_manager.TASKS.values(), return_exceptions=True)
        return job
    job = asyncio.run(run())
    assert job["status"] == "cancelled" and os.listdir(models.root / "loras") == []
    model_manager.cancel_download(job["id"]) # A finished one is cleared from the list.
    assert job["id"] not in model_manager.JOBS


def test_downloads_list_and_clear(api, models, civitai):
    assert api("GET", "/diceforge/civitai/downloads")[1] == {"jobs": []}
    job = download(api, 301)
    assert api("DELETE", f"/diceforge/civitai/downloads?id={job['id']}")[0] == 200
    assert api("GET", "/diceforge/civitai/downloads")[1] == {"jobs": []}
    assert api("DELETE", "/diceforge/civitai/downloads?id=nope")[0] == 404


def test_rename_moves_the_file_with_its_preview_and_info(api, models):
    path = models("loras", "style/ink.safetensors", b"ink")
    for ending in (".preview.png", ".civitai.info"):
        with open(path[:-len(".safetensors")] + ending, "wb") as file:
            file.write(b"x")
    models("loras", "style/keep.safetensors")
    stat = os.stat(path)
    write_info("loras", "style/ink.safetensors", {"user": {"notes": "mine"}, "size": stat.st_size, "mtime": stat.st_mtime, "sha256": "abc"})
    status, body = api("POST", "/diceforge/models/rename", {"kind": "loras", "file": "style/ink.safetensors", "to": "ink/ink v2"})
    assert status == 200 and body == {"renamed": "style/ink.safetensors", "to": "ink/ink v2.safetensors"}
    loras = models.root / "loras"
    assert sorted(os.listdir(loras / "ink")) == ["ink v2.civitai.info", "ink v2.preview.png", "ink v2.safetensors"]
    assert os.listdir(loras / "style") == ["keep.safetensors"]
    assert read_info("loras", "ink/ink v2.safetensors")["user"] == {"notes": "mine"} and read_info("loras", "style/ink.safetensors") == {}
    listing = {entry["file"]: entry for entry in api("GET", "/diceforge/model-browser?kind=loras")[1]["files"]}
    assert listing["ink/ink v2.safetensors"]["preview"] and "style/ink.safetensors" not in listing
    assert api("POST", "/diceforge/models/rename", {"kind": "loras", "file": "ink/ink v2.safetensors", "to": "ink v3.safetensors"})[0] == 200
    assert not os.path.exists(loras / "ink") # The folder left empty went too.


@pytest.mark.parametrize("body, status", [
    ({"file": "a.safetensors", "to": "b"}, 409), ({"file": "a.safetensors", "to": "b.ckpt"}, 400), ({"file": "a.safetensors", "to": "../b"}, 400),
    ({"file": "a.safetensors", "to": ""}, 400), ({"file": "a.safetensors", "to": None}, 400), ({"file": "a.safetensors", "to": "c:d"}, 400),
    ({"file": "nope.safetensors", "to": "c"}, 404), ({"file": "../a.safetensors", "to": "c"}, 400), ({"file": 5, "to": "c"}, 400),
    ({"file": "a.safetensors", "to": "c", "kind": "vae"}, 400)])
def test_rename_refusals(body, status, api, models):
    models("loras", "a.safetensors", b"a")
    models("loras", "b.safetensors", b"b")
    answer = api("POST", "/diceforge/models/rename", {"kind": "loras", **body})
    assert answer[0] == status and answer[1]
    assert sorted(os.listdir(models.root / "loras")) == ["a.safetensors", "b.safetensors"]


def test_rename_to_its_own_name_changes_nothing(api, models):
    models("loras", "a.safetensors", b"a")
    assert api("POST", "/diceforge/models/rename", {"kind": "loras", "file": "a.safetensors", "to": "a"})[1] == {"renamed": "a.safetensors", "to": "a.safetensors"}
    assert os.listdir(models.root / "loras") == ["a.safetensors"]


def test_a_preview_in_the_way_stops_the_rename(api, models):
    models("loras", "a.safetensors", b"a")
    models("loras", "a.preview.png", b"p")
    models("loras", "b.preview.png", b"someone else's")
    assert api("POST", "/diceforge/models/rename", {"kind": "loras", "file": "a.safetensors", "to": "b"})[0] == 409
    assert sorted(os.listdir(models.root / "loras")) == ["a.preview.png", "a.safetensors", "b.preview.png"]


def test_delete_removes_the_file_its_companions_and_info(api, models):
    path = models("loras", "old/x.safetensors", b"x")
    models("loras", "old/x.preview.jpg", b"p")
    models("loras", "old/x.metadata.json", b"{}")
    models("loras", "keep.safetensors", b"k")
    write_info("loras", "old/x.safetensors", {"user": {"notes": "n"}})
    status, body = api("DELETE", "/diceforge/models/file?kind=loras&file=old/x.safetensors")
    assert status == 200 and body == {"deleted": "old/x.safetensors", "files": ["x.safetensors", "x.preview.jpg", "x.metadata.json"]}
    assert os.listdir(models.root / "loras") == ["keep.safetensors"] and not os.path.exists(path)
    assert not os.path.exists(info_file("loras", "old/x.safetensors"))
    assert api("DELETE", "/diceforge/models/file?kind=loras&file=old/x.safetensors")[0] == 404
    for query in ("kind=loras&file=../keep.safetensors", "kind=loras", "kind=vae&file=keep.safetensors", "file=keep.safetensors"):
        assert api("DELETE", f"/diceforge/models/file?{query}")[0] in (400, 404)
    assert os.listdir(models.root / "loras") == ["keep.safetensors"]


@pytest.mark.parametrize("kind", ["checkpoints", "diffusion_models"])
def test_checkpoints_and_diffusion_models_too(kind, api, models, civitai):
    status, body = api("GET", f"/diceforge/civitai/search?kind={kind}&query=x")
    assert status == 200 and civitai.requests[-1][1]["types"] == ["Checkpoint"] # Civitai has diffusion models as Checkpoints.
    job = download_kind(api, kind, 303)
    assert job["status"] == "done" and job["file"] == "base/neon_style.safetensors"
    assert read_info(kind, "base/neon_style.safetensors")["civitai"]["model_name"] == "Base model"
    assert api("POST", "/diceforge/models/rename", {"kind": kind, "file": "base/neon_style.safetensors", "to": "studio"})[1]["to"] == "studio.safetensors"
    assert sorted(os.listdir(models.root / kind)) == ["studio.preview.png", "studio.safetensors"]
    assert api("DELETE", f"/diceforge/models/file?kind={kind}&file=studio.safetensors")[0] == 200
    assert os.listdir(models.root / kind) == []


def download_kind(api, kind, version_id):
    status, job = api("POST", "/diceforge/civitai/download", {"kind": kind, "version_id": version_id, "folder": "base"})
    assert status == 200, job
    return model_manager.JOBS[job["id"]]


def test_civitai_refusing_a_filter_is_a_400(api, models, civitai):
    status, text = api("GET", "/diceforge/civitai/search?base=Nope")
    assert status == 400 and text.startswith("Civitai refused the search:") and "baseModels" in text


def test_downloads_go_to_the_folder_named_like_the_kind(models, tmp_path, monkeypatch):
    unet = tmp_path / "unet"
    unet.mkdir()
    monkeypatch.setitem(model_manager.folder_paths.folder_names_and_paths, "diffusion_models",
                        ([str(unet), str(models.root / "diffusion_models")], model_manager.folder_paths.supported_pt_extensions))
    assert model_manager.download_root("diffusion_models") == str(models.root / "diffusion_models") # Not the older models/unet listed first.
    assert model_manager.download_root("loras") == str(models.root / "loras")


def test_model_favorites_go_with_the_file(api, models):
    models("loras", "style/ink.safetensors", b"ink")
    favorite = lambda: {entry["file"] for entry in api("GET", "/diceforge/model-browser?kind=loras")[1]["files"] if entry["favorite"]}
    assert favorite() == set()
    assert api("POST", "/diceforge/model-favorite", {"kind": "loras", "file": "style/ink.safetensors", "favorite": True})[1] == {"file": "style/ink.safetensors", "favorite": True}
    assert favorite() == {"style/ink.safetensors"}
    api("GET", "/diceforge/model-info?kind=loras&file=style/ink.safetensors") # Hashed and looked up (offline): the star stays.
    assert favorite() == {"style/ink.safetensors"}
    assert api("POST", "/diceforge/models/rename", {"kind": "loras", "file": "style/ink.safetensors", "to": "ink"})[0] == 200
    assert favorite() == {"ink.safetensors"} # Moved with its info.
    with open(models.root / "loras" / "ink.safetensors", "ab") as file:
        file.write(b" changed") # A changed file starts its Civitai data over, not your star.
    api("GET", "/diceforge/model-info?kind=loras&file=ink.safetensors")
    assert favorite() == {"ink.safetensors"}
    assert api("POST", "/diceforge/model-favorite", {"kind": "loras", "file": "ink.safetensors", "favorite": False})[0] == 200
    assert favorite() == set()
    for body, status in (({"kind": "loras", "file": "nope.safetensors", "favorite": True}, 404), ({"kind": "loras", "file": "ink.safetensors", "favorite": 1}, 400),
                         ({"kind": "nope", "file": "ink.safetensors", "favorite": True}, 404), ({"kind": "loras", "file": 5, "favorite": True}, 404)):
        assert api("POST", "/diceforge/model-favorite", body)[0] == status
