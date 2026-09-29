import asyncio
import hashlib
import json
import logging
import os
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
            return json.load(file)
    except (OSError, ValueError):
        return {}
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
        "images": [{**{key: image.get(key) for key in ("type", "width", "height", "nsfwLevel")}, "url": thumbnail(image.get("url") or ""), "full": image.get("url")} for image in (data.get("images") or [])[:12]],
    }
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
                return {**civitai_summary(await response.json()), "checked": time.time()}
    except Exception as error:
        logging.warning(f"[DiceForge] Model info: Civitai lookup failed: {error}")
        return {"found": False, "error": str(error), "checked": time.time()}
async def model_info(kind, name, refresh=False):
    if kind not in KINDS:
        raise web.HTTPBadRequest(text=f"Model info: unknown kind {kind}.")
    path = folder_paths.get_full_path(kind, name)
    if not path:
        raise web.HTTPNotFound(text=f"Model info: {name} is not in the {kind} folders.")
    stat = os.stat(path)
    info = read_info(kind, name)
    if info.get("size") != stat.st_size or info.get("mtime") != stat.st_mtime: # A new or changed file: its hash and Civitai data start over.
        info = {"user": info.get("user", {}), "size": stat.st_size, "mtime": stat.st_mtime}
    if not info.get("sha256"):
        started = time.time()
        info["sha256"] = await asyncio.get_running_loop().run_in_executor(None, sha256_of, path) # Off the event loop: big files take a while.
        logging.info(f"[DiceForge] Model info: sha256 of {name} in {time.time() - started:.1f}s")
    if refresh or not info.get("civitai") or info["civitai"].get("error"):
        info["civitai"] = await civitai_lookup(info["sha256"])
    write_info(kind, name, info)
    return {"kind": kind, "file": name, **info}
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
    }
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
        return web.json_response(await asyncio.get_running_loop().run_in_executor(None, model_list, kind))
    @routes.get("/diceforge/model-preview")
    async def get_model_preview(request):
        query = request.rel_url.query
        kind, name = query.get("kind", ""), query.get("file", "")
        path = folder_paths.get_full_path(kind, name) if kind in KINDS else None
        preview = path and local_preview(path, set(os.listdir(os.path.dirname(path))))
        if not preview:
            raise web.HTTPNotFound(text="Model browser: no local preview.")
        return web.FileResponse(preview, headers={"Cache-Control": "max-age=300"})
    @routes.post("/diceforge/model-info")
    async def save_model_info(request):
        body = await request.json()
        kind, name = body.get("kind", ""), body.get("file", "")
        if kind not in KINDS or not folder_paths.get_full_path(kind, name):
            raise web.HTTPNotFound(text="Model info: unknown model.")
        info = read_info(kind, name)
        info["user"] = {key: str(value)[:10000] for key, value in (body.get("user") or {}).items() if key in USER_FIELDS}
        write_info(kind, name, info)
        return web.json_response({"saved": True})
register_routes()
