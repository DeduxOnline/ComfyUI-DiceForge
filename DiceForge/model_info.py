import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
import aiohttp
import folder_paths
from aiohttp import web
# Model info for the "Model info" dialog of the frontend (web/model_info.js), like rgthree's LoRA info but for every model kind: the file's sha256,
# what Civitai knows about it (looked up by that hash), and the user's own notes. Everything is kept in the ComfyUI user folder, one JSON per file,
# so model folders stay untouched; the hash is only computed again when the file's size or date changes.
KINDS = ("checkpoints", "diffusion_models", "loras", "vae", "text_encoders", "embeddings")
INFO_FOLDER = os.path.join(folder_paths.get_user_directory(), "DiceForge", "model_info")
CIVITAI_BY_HASH = os.environ.get("DICEFORGE_CIVITAI_URL", "https://civitai.com/api/v1/model-versions/by-hash/{}") # Another server for tests (e2e/server.js).
CIVITAI_MODEL = os.environ.get("DICEFORGE_CIVITAI_API", "https://civitai.com/api/v1").rstrip("/") + "/models/{}" # The model page: tags, stats, versions.
USER_FIELDS = ("name", "trigger_words", "settings", "notes")
def info_file(kind, name):
    root = os.path.abspath(os.path.join(INFO_FOLDER, kind))
    path = os.path.abspath(os.path.join(root, name.replace("\\", "/") + ".json"))
    if not path.startswith(root + os.sep):
        raise web.HTTPBadRequest(text="Model info: invalid file name.")
    return path
def read_info(kind, name):
    try:
        with open(info_file(kind, name), encoding="utf-8") as file:
            return clean_info(json.load(file))
    except (OSError, ValueError):
        return {}
# Model info as the browser, the dialog and LoRA Stack read it, whatever the file holds (edited by hand, or damaged): user fields are text, Civitai's
# trigger words a list of text and its images a list of objects. Damaged parts are left out; the rest is kept.
def clean_info(info):
    if not isinstance(info, dict):
        return {}
    info = dict(info)
    user = info.get("user")
    info["user"] = {key: str(value) for key, value in user.items() if key in USER_FIELDS and isinstance(value, (str, int, float)) and not isinstance(value, bool)} \
        if isinstance(user, dict) else {}
    civitai = info.pop("civitai", None)
    if isinstance(civitai, dict):
        civitai = dict(civitai)
        words, images = civitai.get("trigger_words"), civitai.get("images")
        civitai["trigger_words"] = [str(word) for word in words if isinstance(word, (str, int, float)) and not isinstance(word, bool)] if isinstance(words, list) else []
        civitai["images"] = [{**image, "meta": image_meta(image.get("meta"))} for image in images if isinstance(image, dict)] if isinstance(images, list) else []
        for key in ("model_name", "version_name", "type", "base_model", "url", "error"):
            if civitai.get(key) is not None and not isinstance(civitai[key], str):
                civitai[key] = str(civitai[key])
        info["civitai"] = civitai
    return info
# The JSON object a POST request sends; anything else (no JSON, a list, a number) is a 400 with a message instead of a server error.
async def json_body(request):
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="DiceForge: the request body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="DiceForge: the request body must be a JSON object.")
    return body
# A route's work with files (reading, writing, listing folders), in a thread: on ComfyUI's event loop it would hold up every other request and
# the progress of a run meanwhile (Sonar S7493). The handler reads what the request sends; the rest goes through here.
async def in_thread(function, *args):
    return await asyncio.get_running_loop().run_in_executor(None, function, *args)
def write_info(kind, name, info):
    path = info_file(kind, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(info, file, ensure_ascii=False, indent=1)
def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
# What the dialog shows from Civitai's answer for a model version: names, base model, trigger words, link and example images (with their NSFW level).
def civitai_summary(data):
    model = data.get("model") or {}
    return {
        "found": True,
        "model_id": data.get("modelId"),
        "version_id": data.get("id"),
        "model_name": model.get("name"),
        "version_name": data.get("name"),
        "type": model.get("type"),
        "base_model": data.get("baseModel"),
        "trigger_words": data.get("trainedWords") or [],
        "url": f"https://civitai.com/models/{data.get('modelId')}?modelVersionId={data.get('id')}",
        "images": [{**{key: image.get(key) for key in ("type", "width", "height", "nsfwLevel", "hasMeta")}, "url": thumbnail(image.get("url") or ""), "full": image.get("url"),
                    "page": image_page(image.get("url") or ""), "meta": image_meta(image.get("meta"))} for image in (data.get("images") or [])[:12] if isinstance(image, dict)],
    }
# What the model's page on Civitai adds (GET /models/{id}): its tags, its counts (likes, downloads, tips, comments), its creator and its versions, newest
# first, with when they came out; the versions show whether a newer one than yours is out. Bookmarks, generations and the Buzz amount of the page
# aren't in Civitai's public API.
def number(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
def listed(value):
    return value if isinstance(value, list) else []
def civitai_details(data):
    if not isinstance(data, dict):
        return {}
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    creator = data.get("creator") if isinstance(data.get("creator"), dict) else {}
    versions = [version for version in listed(data.get("modelVersions")) if isinstance(version, dict) and isinstance(version.get("id"), int)]
    def published(version):
        return str(version.get("publishedAt") or version.get("createdAt") or "")[:40]
    return {
        "tags": [str(tag).strip()[:40] for tag in listed(data.get("tags")) if isinstance(tag, (str, int)) and str(tag).strip()][:20],
        "stats": {"likes": number(stats.get("thumbsUpCount")), "downloads": number(stats.get("downloadCount")), "tips": number(stats.get("tippedAmountCount")),
                  "comments": number(stats.get("commentCount"))},
        "creator": str(creator.get("username") or "")[:60],
        "versions": [{"id": version["id"], "name": str(version.get("name") or "")[:60], "base_model": str(version.get("baseModel") or "")[:40],
                      "published": published(version), "downloads": number((version.get("stats") or {}).get("downloadCount") if isinstance(version.get("stats"), dict) else 0)}
                     for version in versions[:30]],
        "updated": max((published(version) for version in versions), default=""),
    }
async def civitai_model_details(session, model_id):
    if not isinstance(model_id, int) or isinstance(model_id, bool):
        return {}
    try:
        async with session.get(CIVITAI_MODEL.format(model_id)) as response:
            if response.status == 404: # The model's page is gone (deleted, or hidden): nothing to add, and no need to ask again.
                return {"details_checked": time.time()}
            response.raise_for_status()
            return {**civitai_details(await response.json()), "details_checked": time.time()}
    except Exception as error: # The version is known all the same; the details are asked again on the next lookup.
        logging.warning(f"[DiceForge] Model info: Civitai model details failed: {error}")
        return {}
# How an example image was made, from Civitai's meta of it (the generation data of A1111, Forge, ComfyUI or Civitai's own generator): the prompts and
# the settings the dialog shows over the image, as text and numbers only.
META_KEYS = ("prompt", "negativePrompt", "seed", "steps", "cfgScale", "sampler", "Schedule type", "scheduler", "Model", "Size", "Clip skip", "Denoising strength", "VAE")
def image_meta(meta):
    if not isinstance(meta, dict):
        return {}
    return {key: str(meta[key])[:5000] if isinstance(meta[key], str) else meta[key] for key in META_KEYS
            if isinstance(meta.get(key), (str, int, float)) and not isinstance(meta.get(key), bool) and str(meta[key]).strip()}
# The image's page on Civitai: its id is the file name of its url (.../original=true/64739376.jpeg).
def image_page(url):
    match = re.search(r"/(\d+)\.\w+$", url)
    return f"https://civitai.com/images/{match.group(1)}" if match else None
# Civitai serves resized copies: 450 px wide instead of the original (often 2 MB and more) for the dialog's previews.
def thumbnail(url):
    return url.replace("/original=true/", "/width=450/")
async def civitai_lookup(sha256):
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session: # trust_env: use the system's proxy settings.
            async with session.get(CIVITAI_BY_HASH.format(sha256)) as response:
                if response.status == 404:
                    return {"found": False, "checked": time.time()}
                response.raise_for_status()
                summary = civitai_summary(await response.json())
            return {**summary, **await civitai_model_details(session, summary["model_id"]), "checked": time.time()}
    except Exception as error:
        logging.warning(f"[DiceForge] Model info: Civitai lookup failed: {error}")
        return {"found": False, "error": str(error), "checked": time.time()}
# The model file and what is known about it; a new or changed file starts over (its hash and Civitai data), yours stays.
def stored_info(kind, name):
    if kind not in KINDS:
        raise web.HTTPBadRequest(text=f"Model info: unknown kind {kind}.")
    path = folder_paths.get_full_path(kind, name)
    if not path:
        raise web.HTTPNotFound(text=f"Model info: {name} is not in the {kind} folders.")
    stat = os.stat(path)
    info = read_info(kind, name)
    if info.get("size") != stat.st_size or info.get("mtime") != stat.st_mtime:
        info = {"user": info.get("user", {}), "favorite": info.get("favorite") is True, "size": stat.st_size, "mtime": stat.st_mtime}
    return path, info
async def model_info(kind, name, refresh=False):
    path, info = await in_thread(stored_info, kind, name)
    if not info.get("sha256"):
        started = time.time()
        info["sha256"] = await in_thread(sha256_of, path) # Big files take a while.
        logging.info(f"[DiceForge] Model info: sha256 of {name} in {time.time() - started:.1f}s")
    civitai = info.get("civitai") or {}
    if refresh or not civitai or civitai.get("error"):
        info["civitai"] = await civitai_lookup(info["sha256"])
    elif civitai.get("found") and not civitai.get("details_checked"): # The model's details (tags, stats) failed last time: only those again.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), trust_env=True) as session:
            info["civitai"] = {**civitai, **await civitai_model_details(session, civitai.get("model_id"))}
    info = await in_thread(store_lookup, kind, name, info)
    return {"kind": kind, "file": name, **info}
def local_preview_of(kind, name):
    path = folder_paths.get_full_path(kind, name) if kind in KINDS else None
    return path and local_preview(path, set(os.listdir(os.path.dirname(path))))
# The changes to an info file go one at a time (the routes run in threads, two at once can change the same file), and a lookup, which takes
# seconds, keeps what was saved meanwhile: the favorite and your fields as the file has them now.
INFO_CHANGES = threading.Lock()
def store_lookup(kind, name, info):
    with INFO_CHANGES:
        now = read_info(kind, name)
        info = {**info, "favorite": now.get("favorite") is True if now else info.get("favorite") is True, "user": now.get("user", info.get("user", {}))}
        write_info(kind, name, info)
    return info
# A model's own fields saved into its info file (the favorite flag, your notes): its name checked against the model folders first.
def update_info(kind, name, change):
    if kind not in KINDS or not isinstance(name, str) or not name or not folder_paths.get_full_path(kind, name):
        raise web.HTTPNotFound(text="Model info: unknown model.")
    with INFO_CHANGES:
        info = read_info(kind, name)
        change(info)
        write_info(kind, name, info)
# Model browser (web/model_browser.js): every file of a model kind with what is already known about it, without hashing anything; the dialog looks
# files up one by one with /diceforge/model-info. A local preview next to the file (name.preview.png, name.png... as Civitai Helper and LoRA Manager
# save them) is shown first, else the first Civitai image.
PREVIEW_ENDINGS = (".preview.png", ".preview.jpg", ".preview.jpeg", ".preview.webp", ".png", ".jpg", ".jpeg", ".webp")
def local_preview(path, folder_files):
    base = os.path.splitext(path)[0]
    return next((base + ending for ending in PREVIEW_ENDINGS if os.path.basename(base + ending) in folder_files), None)
def browser_entry(kind, name, path, folder_files):
    stat = os.stat(path)
    info = read_info(kind, name)
    fresh = info.get("size") == stat.st_size and info.get("mtime") == stat.st_mtime
    civitai = (info.get("civitai") or {}) if fresh else {}
    user = info.get("user") or {}
    images = civitai.get("images") or []
    image = next((image for image in images if image.get("type") != "video"), images[0] if images else None)
    found = bool(civitai.get("found"))
    return {
        "file": name,
        "sha256": (info.get("sha256") or "") if fresh else "", # Known once looked up: the browsers find duplicates by it.
        "favorite": info.get("favorite") is True, # ★ in the browsers: kept whatever the file's state, like your notes.
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "preview": local_preview(path, folder_files) is not None,
        "checked": bool(civitai.get("checked")) and not civitai.get("error"),
        "found": found,
        "name": user.get("name") or (" - ".join(part for part in (civitai.get("model_name"), civitai.get("version_name")) if part) if found else ""),
        "base_model": civitai.get("base_model") or "",
        "trigger_words": [word.strip() for word in (user.get("trigger_words") or "").split(",") if word.strip()] or civitai.get("trigger_words") or [],
        "settings": (user.get("settings") or "").strip(),
        "image": image and {"url": image.get("url"), "type": image.get("type"), "nsfwLevel": image.get("nsfwLevel")},
        "url": civitai.get("url") if found else None,
        "tags": civitai.get("tags") or [] if found else [],
        "stats": civitai.get("stats") if found and civitai.get("stats") else None,
        "creator": civitai.get("creator") or "" if found else "",
        "updated": civitai.get("updated") or "" if found else "",
        "newer": newer_version(civitai) if found else None,
    }
# The newest version on Civitai when it isn't yours (and came out after yours): "an update is out".
def newer_version(civitai):
    versions = civitai.get("versions") or []
    mine = next((version for version in versions if version.get("id") == civitai.get("version_id")), None)
    newest = versions[0] if versions else None
    if not mine or not newest or newest is mine or newest.get("published", "") <= mine.get("published", ""):
        return None
    return {"id": newest["id"], "name": newest.get("name", ""), "url": f"https://civitai.com/models/{civitai.get('model_id')}?modelVersionId={newest['id']}"}
def model_list(kind):
    if kind not in KINDS:
        raise web.HTTPBadRequest(text=f"Model browser: unknown kind {kind}.")
    entries, listings = [], {}
    for name in folder_paths.get_filename_list(kind):
        path = folder_paths.get_full_path(kind, name)
        if not path or not os.path.isfile(path):
            continue
        folder = os.path.dirname(path)
        if folder not in listings: # One directory listing per folder instead of a check per preview name.
            listings[folder] = set(os.listdir(folder))
        entries.append(browser_entry(kind, name, path, listings[folder]))
    return {"kind": kind, "files": entries}
def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/model-info")
    async def get_model_info(request):
        query = request.rel_url.query
        return web.json_response(await model_info(query.get("kind", ""), query.get("file", ""), query.get("refresh") == "1"))
    @routes.get("/diceforge/model-browser")
    async def get_model_list(request):
        kind = request.rel_url.query.get("kind", "")
        return web.json_response(await in_thread(model_list, kind))
    @routes.get("/diceforge/model-preview")
    async def get_model_preview(request):
        query = request.rel_url.query
        preview = await in_thread(local_preview_of, query.get("kind", ""), query.get("file", ""))
        if not preview:
            raise web.HTTPNotFound(text="Model browser: no local preview.")
        return web.FileResponse(preview, headers={"Cache-Control": "max-age=300"})
    # ★ Favorites of the model browsers: a flag in the model's info file, so it moves and goes with the file (rename, move, delete).
    @routes.post("/diceforge/model-favorite")
    async def save_model_favorite(request):
        body = await json_body(request)
        kind, name, favorite = body.get("kind", ""), body.get("file", ""), body.get("favorite")
        if not isinstance(favorite, bool):
            raise web.HTTPBadRequest(text="Model info: favorite must be true or false.")
        await in_thread(update_info, kind, name, lambda info: info.update(favorite=favorite))
        return web.json_response({"file": name, "favorite": favorite})
    @routes.post("/diceforge/model-info")
    async def save_model_info(request):
        body = await json_body(request)
        kind, name, user = body.get("kind", ""), body.get("file", ""), body.get("user") or {}
        if not isinstance(user, dict):
            raise web.HTTPBadRequest(text="Model info: user must be an object of fields.")
        fields = {key: str(value)[:10000] for key, value in user.items() if key in USER_FIELDS}
        await in_thread(update_info, kind, name, lambda info: info.update(user=fields))
        return web.json_response({"saved": True})
register_routes()
