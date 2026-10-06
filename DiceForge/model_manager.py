import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import time
import uuid
from urllib.parse import urlsplit
import aiohttp
import folder_paths
from aiohttp import web
from .http_read import read_up_to
from .model_info import PREVIEW_ENDINGS, civitai_details, civitai_summary, info_file, json_body, local_preview, read_info, thumbnail, write_info
# Managing the model files of the LoRA, Checkpoint and Diffusion Model Browsers (web/model_browser.js, web/civitai.js): Create is finding a model on
# Civitai and downloading it (with its Civitai data and a preview, so the browser shows it at once), Read is the browser and Model info, Update is
# renaming or moving a file (its preview and info go with it) and Delete is removing it. MANAGED_KINDS lists the kinds the routes accept.
MANAGED_KINDS = ("loras", "checkpoints", "diffusion_models", "vae", "text_encoders")
# Civitai's model types that load as each kind. Civitai has no type of its own for diffusion models (Flux, Qwen... without their text encoders and
# VAE): they are Checkpoints there, and the browser says to pick a version whose file is the diffusion model alone. Nor has it one for text
# encoders: they are renamed, moved and deleted here, not searched for.
CIVITAI_TYPES = {"loras": ("LORA", "LoCon", "DoRA"), "checkpoints": ("Checkpoint",), "diffusion_models": ("Checkpoint",), "vae": ("VAE",), "text_encoders": ()}
def civitai_types(kind):
    types = CIVITAI_TYPES[managed_kind(kind)]
    if not types:
        raise web.HTTPBadRequest(text=f"Civitai has no model type for {kind}: they can't be searched or downloaded there.")
    return types
CIVITAI_API = os.environ.get("DICEFORGE_CIVITAI_API", "https://civitai.com/api/v1") # Another server for tests (e2e/server.js).
KEY_FILE = os.path.join(folder_paths.get_user_directory(), "DiceForge", "civitai.json")
SORTS = ("Highest Rated", "Most Downloaded", "Newest")
COMPANIONS = PREVIEW_ENDINGS + (".civitai.info", ".metadata.json", ".json") # Files next to a model that belong to it (as other managers save them).
FORBIDDEN = re.compile(r'[<>:"|?*\x00-\x1f]') # Not allowed in file names on Windows (and control characters anywhere).
MAX_DOWNLOADS = 3 # Downloads running at the same time.
PREVIEW_BYTES = 20 * 1024 * 1024 # A Civitai preview image at most.
JOBS, TASKS = {}, {} # Downloads of this session by id: what the browser shows, and the task doing it.


class DownloadError(Exception):
    pass


def managed_kind(kind):
    if kind not in MANAGED_KINDS:
        raise web.HTTPBadRequest(text=f"Models: {kind!r} can't be managed here (only {', '.join(MANAGED_KINDS)}).")
    return MANAGED_KINDS[MANAGED_KINDS.index(kind)] # The list's own string, not the one sent: paths are made only of known names.
# A relative file or folder name inside a model folder: / for subfolders, no .. and nothing Windows can't name a file.
def checked_relative(name, what="name"):
    name = (name if isinstance(name, str) else "").strip().replace("\\", "/")
    parts = name.split("/")
    if not name or len(name) > 1000 or FORBIDDEN.search(name) or any(part in ("", ".", "..") or part != part.strip() or part.endswith(".") for part in parts):
        raise web.HTTPBadRequest(text=f"Models: {name!r} is not a usable {what} (no .., no empty folder names, none of < > : \" | ? *).")
    return name
def extensions():
    return {extension.lower() for extension in folder_paths.supported_pt_extensions}
def drop_list_cache(kind):
    folder_paths.filename_list_cache.pop(kind, None) # The loaders' lists and the browser see the change at once.
def root_of(kind, path):
    path = os.path.abspath(path)
    return next(root for root in map(os.path.abspath, folder_paths.get_folder_paths(kind)) if path.startswith(root + os.sep))
def inside(root, *parts):
    path = os.path.abspath(os.path.join(root, *parts))
    if not path.startswith(root + os.sep):
        raise web.HTTPBadRequest(text="Models: the file would be outside the model folder.")
    return path
def relative_name(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")
# The model file of a name from the browser, with the model folder it is in.
def existing(kind, name):
    name = checked_relative(name, "file name") # Before ComfyUI's lookup, which would read "../x" as "x": another file than the one named.
    path = folder_paths.get_full_path(managed_kind(kind), name)
    if not path or not os.path.isfile(path):
        raise web.HTTPNotFound(text=f"Models: no {kind} file {name!r}.")
    return path, root_of(kind, path)
# The files that go with a model file: its previews and other managers' info files (name.preview.png, name.civitai.info...).
def companions(path):
    base, folder = os.path.splitext(path)[0], os.path.dirname(path)
    present = set(os.listdir(folder))
    return [(ending, base + ending) for ending in COMPANIONS if os.path.basename(base + ending) in present]
def remove_empty_folders(folder, root):
    while folder != root and folder.startswith(root + os.sep):
        try:
            os.rmdir(folder)
        except OSError: # Not empty: it stays, and so do the folders above it.
            return
        folder = os.path.dirname(folder)


# Update: a new name (the extension stays; "a/b" moves it to the folder a), in the same model folder. The previews, the other info files and the
# Model info entry (notes, Civitai data, hash) go with it.
def rename_model(kind, name, to):
    path, root = existing(kind, name)
    to = checked_relative(to, "new name")
    extension = os.path.splitext(path)[1]
    given = os.path.splitext(to)[1]
    if given.lower() not in extensions():
        to += extension # "style/ink v2" keeps .safetensors; so does a name with dots of its own, like "ink.v2".
    elif given.lower() != extension.lower():
        raise web.HTTPBadRequest(text=f"Models: a {extension} file keeps its extension (not {given}).")
    target = inside(root, *to.split("/"))
    new_name = relative_name(root, target)
    same = os.path.normcase(target) == os.path.normcase(path)
    if same and target == path:
        return {"renamed": name, "to": new_name}
    moves = [(path, target)] + [(companion, os.path.splitext(target)[0] + ending) for ending, companion in companions(path)]
    for source, destination in moves:
        if os.path.exists(destination) and os.path.normcase(destination) != os.path.normcase(source):
            raise web.HTTPConflict(text=f"Models: {relative_name(root, destination)} already exists.")
    shadow = folder_paths.get_full_path(kind, new_name)
    if shadow and os.path.normcase(os.path.abspath(shadow)) != os.path.normcase(path): # The same name in another model folder.
        raise web.HTTPConflict(text=f"Models: {new_name} already exists ({shadow}).")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    for source, destination in moves:
        os.replace(source, destination)
    old_info, new_info = info_file(kind, name), info_file(kind, new_name)
    if os.path.isfile(old_info) and old_info != new_info:
        os.makedirs(os.path.dirname(new_info), exist_ok=True)
        os.replace(old_info, new_info)
    remove_empty_folders(os.path.dirname(path), root)
    drop_list_cache(kind)
    return {"renamed": name, "to": new_name}
# Deleted models wait in a trash folder next to their model folder (models/.diceforge_trash for models/loras: on the same drive, so moving a
# model there takes no time and no space), so a delete can be undone. The last TRASH_KEPT are kept, and none after ComfyUI restarts: a delete
# frees the space by then. A model folder whose parent can't take the trash (another drive, read-only) deletes at once, without undo.
TRASH_NAME = ".diceforge_trash"
TRASH_KEPT = 10
TRASH_ID = re.compile(r"\d{19}-[0-9a-f]{8}")
last_trashed = [0] # Ids in the order of the deletes, also two within a clock tick: the oldest go first.
def trash_folder(root):
    return os.path.join(os.path.dirname(os.path.abspath(root)), TRASH_NAME)
def new_trash(root):
    trash = trash_folder(root)
    try:
        os.makedirs(trash, exist_ok=True)
        if os.stat(trash).st_dev != os.stat(root).st_dev: # Another drive: moving a model there would copy gigabytes.
            return None
        last_trashed[0] = max(time.time_ns(), last_trashed[0] + 1)
        folder = os.path.join(trash, f"{last_trashed[0]:019d}-{uuid.uuid4().hex[:8]}")
        os.makedirs(folder)
        return folder
    except OSError:
        return None
# A kept delete's folder in a trash folder, found among its entries (a path made only of names the trash holds, never of the id as sent).
def kept_delete(trash, trash_id):
    try:
        return next((os.path.join(trash, name) for name in os.listdir(trash) if TRASH_ID.fullmatch(name) and name == trash_id), None)
    except OSError:
        return None
def empty_trash(trash, kept=0):
    try:
        entries = sorted(name for name in os.listdir(trash) if TRASH_ID.fullmatch(name))
    except OSError:
        return
    for name in entries[:len(entries) - kept] if kept else entries:
        shutil.rmtree(os.path.join(trash, name), ignore_errors=True)
# When ComfyUI starts: the deletes of the last session are final.
def empty_all_trash():
    for kind in MANAGED_KINDS:
        try:
            roots = folder_paths.get_folder_paths(kind)
        except Exception: # A kind this ComfyUI doesn't have.
            continue
        for root in roots:
            empty_trash(trash_folder(root))
# Delete: the model file, its previews and info files, and its Model info entry, into the trash (see above); folders left empty go too.
def delete_model(kind, name):
    path, root = existing(kind, name)
    removed = [path] + [companion for _ending, companion in companions(path)]
    info = info_file(kind, name)
    folder = new_trash(root)
    if folder is None:
        for file in removed:
            os.remove(file)
        try:
            os.remove(info)
        except OSError:
            pass
    else:
        with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as file:
            json.dump({"kind": kind, "name": name, "files": [os.path.basename(file) for file in removed], "info": os.path.isfile(info)}, file)
        for file in removed:
            os.replace(file, os.path.join(folder, os.path.basename(file))) # The same drive: only a new name.
        if os.path.isfile(info):
            shutil.move(info, os.path.join(folder, "model_info.json"))
        empty_trash(os.path.dirname(folder), TRASH_KEPT)
    remove_empty_folders(os.path.dirname(path), root)
    drop_list_cache(kind)
    return {"deleted": name, "files": [os.path.basename(file) for file in removed], **({"undo": os.path.basename(folder)} if folder else {})}
# Undo a delete: the model and its files back where they were, from the trash of one of the kind's model folders.
def restore_model(kind, trash_id):
    kind = managed_kind(kind)
    if not isinstance(trash_id, str) or not TRASH_ID.fullmatch(trash_id):
        raise web.HTTPBadRequest(text="Models: that is not a deleted model's id.")
    root, folder = next(((os.path.abspath(root), kept) for root in folder_paths.get_folder_paths(kind)
                         for kept in [kept_delete(trash_folder(root), trash_id)] if kept), (None, None))
    try:
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as file:
            meta = json.load(file)
        name, files = checked_relative(meta["name"], "file name"), [str(file) for file in meta["files"]]
    except (TypeError, OSError, ValueError, KeyError):
        raise web.HTTPNotFound(text="Models: nothing to undo: the deleted model is no longer kept (a restart of ComfyUI empties the trash).") from None
    if meta.get("kind") != kind or any(os.path.basename(file) != file or file in ("", ".", "..") for file in files):
        raise web.HTTPBadRequest(text="Models: that deleted model can't be brought back here.")
    target = inside(root, *name.split("/"))
    if os.path.exists(target) or folder_paths.get_full_path(kind, name):
        raise web.HTTPConflict(text=f"Models: there is a {name} again: rename it to bring the deleted one back.")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    for file in files:
        os.replace(os.path.join(folder, file), os.path.join(os.path.dirname(target), file))
    if meta.get("info") and os.path.isfile(os.path.join(folder, "model_info.json")):
        os.makedirs(os.path.dirname(info_file(kind, name)), exist_ok=True)
        shutil.move(os.path.join(folder, "model_info.json"), info_file(kind, name))
    shutil.rmtree(folder, ignore_errors=True)
    drop_list_cache(kind)
    return {"restored": name}


# The Civitai API key: CIVITAI_API_KEY (or DICEFORGE_CIVITAI_KEY) from the environment, else the one saved from the browser in the ComfyUI user folder.
# It is only ever sent to Civitai (the API's own host), and never back to the browser.
def api_key():
    for variable in ("CIVITAI_API_KEY", "DICEFORGE_CIVITAI_KEY"):
        if os.environ.get(variable, "").strip():
            return os.environ[variable].strip(), "environment"
    try:
        with open(KEY_FILE, encoding="utf-8") as file:
            key = json.load(file).get("api_key")
        return (key, "settings") if isinstance(key, str) and key else ("", None)
    except (OSError, ValueError, AttributeError):
        return "", None
def save_key(key):
    if key:
        os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
        with open(KEY_FILE, "w", encoding="utf-8") as file:
            json.dump({"api_key": key}, file)
    elif os.path.exists(KEY_FILE):
        os.remove(KEY_FILE)
def auth_headers(url):
    key, _source = api_key()
    same_host = urlsplit(url)[:2] == urlsplit(CIVITAI_API)[:2]
    return {"Authorization": f"Bearer {key}"} if key and same_host else {}
def session(**timeouts):
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(**(timeouts or {"total": 30})), trust_env=True) # trust_env: the system's proxy settings.
async def civitai_json(path, params=()):
    url = CIVITAI_API.rstrip("/") + path
    try:
        async with session() as client, client.get(url, params=list(params), headers=auth_headers(url)) as response:
            if response.status == 404:
                raise web.HTTPNotFound(text="Civitai: not found.")
            if response.status in (401, 403):
                raise web.HTTPForbidden(text="Civitai refused the request: check the API key (🔑).")
            if response.status == 400: # A filter Civitai doesn't know (a base model name...): its message says which.
                raise web.HTTPBadRequest(text=f"Civitai refused the search: {(await response.text())[:300]}")
            response.raise_for_status()
            data = await response.json(content_type=None)
    except web.HTTPException:
        raise
    except Exception as error: # Offline, a timeout, Civitai down or answering something else than JSON.
        raise web.HTTPBadGateway(text=f"Civitai could not be reached: {error}") from None
    if not isinstance(data, dict):
        raise web.HTTPBadGateway(text="Civitai answered something unexpected.")
    return data


# Create, part 1: search. What the cards need from Civitai's model list, and which versions are already here (same sha256, or the same file name).
def local_index(kind):
    names, hashes = {}, {}
    for name in folder_paths.get_filename_list(kind):
        names.setdefault(os.path.basename(name.replace("\\", "/")).lower(), name)
        sha256 = read_info(kind, name).get("sha256")
        if isinstance(sha256, str):
            hashes.setdefault(sha256.lower(), name)
    return names, hashes
def model_file(version):
    files = [file for file in version.get("files") or [] if isinstance(file, dict) and os.path.splitext(str(file.get("name") or ""))[1].lower() in extensions()]
    return next((file for file in files if file.get("primary")), files[0] if files else None)
def images_of(version, count):
    return [{"url": thumbnail(str(image.get("url") or "")), "type": image.get("type"), "nsfwLevel": image.get("nsfwLevel")}
            for image in (version.get("images") or []) if isinstance(image, dict) and image.get("url")][:count]
def text_list(value):
    return [str(item) for item in value if isinstance(item, (str, int, float))] if isinstance(value, list) else []
def search_item(item, index):
    names, hashes = index
    versions = []
    for version in (item.get("modelVersions") or [])[:12]:
        if not isinstance(version, dict):
            continue
        file = model_file(version)
        sha256 = str(((file or {}).get("hashes") or {}).get("SHA256") or "").lower()
        installed = (hashes.get(sha256) if sha256 else None) or (names.get(str(file["name"]).lower()) if file else None)
        versions.append({"id": version.get("id"), "name": str(version.get("name") or ""), "base_model": str(version.get("baseModel") or ""),
                         "trigger_words": text_list(version.get("trainedWords")), "early_access": version.get("availability") == "EarlyAccess",
                         "file": file and {"name": str(file.get("name")), "size": round(float(file.get("sizeKB") or 0) * 1024)}, "installed": installed,
                         "images": images_of(version, 4)})
    stats, creator = item.get("stats") if isinstance(item.get("stats"), dict) else {}, item.get("creator") if isinstance(item.get("creator"), dict) else {}
    return {"id": item.get("id"), "name": str(item.get("name") or ""), "type": str(item.get("type") or ""), "creator": str(creator.get("username") or ""),
            "nsfw": bool(item.get("nsfw")), "downloads": stats.get("downloadCount") or 0, "likes": stats.get("thumbsUpCount") or 0,
            "url": f"https://civitai.com/models/{item.get('id')}", "versions": versions}
async def search(kind, query="", base="", sort="", nsfw=False, cursor=""):
    params = [("limit", "24"), ("sort", sort if sort in SORTS else SORTS[0]), ("nsfw", "true" if nsfw else "false")]
    params += [("types", civitai_type) for civitai_type in civitai_types(kind)]
    params += [(key, value[:200]) for key, value in (("query", query.strip()), ("baseModels", base.strip()), ("cursor", cursor)) if value]
    data = await civitai_json("/models", params)
    index = await asyncio.get_running_loop().run_in_executor(None, local_index, kind)
    items = [search_item(item, index) for item in data.get("items") or [] if isinstance(item, dict)]
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return {"items": items, "next": metadata.get("nextCursor")}


# Create, part 2: download a version into a model folder. The file is written as name.part and checked against Civitai's sha256 before it gets its
# name, so a stopped or damaged download never shows up as a model. Its Civitai data and hash are saved for Model info, and the first image as preview.
def public(job):
    return {key: value for key, value in job.items() if key != "path"}
def safe_file_name(name):
    name = FORBIDDEN.sub("_", os.path.basename(str(name).replace("\\", "/"))).strip().strip(".") or "model.safetensors"
    return name
# Where downloads go: the model folder named like the kind (models/diffusion_models, not the older models/unet ComfyUI lists first), else the first.
def download_root(kind):
    roots = [os.path.abspath(root) for root in folder_paths.get_folder_paths(kind)]
    return next((root for root in roots if os.path.basename(root) == kind), roots[0])
def open_for_writing(path):
    return open(path, "wb") # noqa: SIM115  (closed by run_download, which writes it chunk by chunk)
def write_bytes(path, data):
    with open(path, "wb") as out:
        out.write(data)
async def start_download(kind, version_id, folder=""):
    civitai_types(kind) # A kind Civitai has, before anything is asked.
    if isinstance(version_id, bool) or not isinstance(version_id, int) or version_id <= 0:
        raise web.HTTPBadRequest(text="Civitai: version_id must be a model version number.")
    folder = checked_relative(folder, "folder") if isinstance(folder, str) and folder.strip() else ""
    if sum(job["status"] == "downloading" for job in JOBS.values()) >= MAX_DOWNLOADS:
        raise web.HTTPTooManyRequests(text=f"Civitai: {MAX_DOWNLOADS} downloads are running; start this one when one is done.")
    version = await civitai_json(f"/model-versions/{version_id}")
    model = version.get("model") if isinstance(version.get("model"), dict) else {}
    if model.get("type") and model["type"] not in CIVITAI_TYPES[kind]:
        raise web.HTTPBadRequest(text=f"Civitai: {model.get('name')} is a {model['type']}, not one of {', '.join(CIVITAI_TYPES[kind])}.")
    file = model_file(version)
    url = file and (file.get("downloadUrl") or version.get("downloadUrl"))
    if not file or not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https"):
        raise web.HTTPBadRequest(text="Civitai: this version has no file in a format ComfyUI loads.")
    root = download_root(kind)
    path = inside(root, *([*folder.split("/")] if folder else []), safe_file_name(file["name"]))
    name = relative_name(root, path)
    if os.path.splitext(path)[1].lower() not in extensions():
        raise web.HTTPBadRequest(text=f"Civitai: {name} is not a model file ComfyUI loads.")
    if os.path.exists(path) or folder_paths.get_full_path(kind, name):
        raise web.HTTPConflict(text=f"Civitai: {name} is already there.")
    if any(job["path"] == path and job["status"] == "downloading" for job in JOBS.values()):
        raise web.HTTPConflict(text=f"Civitai: {name} is already downloading.")
    job = {"id": uuid.uuid4().hex[:12], "kind": kind, "version_id": version_id, "model": str(model.get("name") or ""), "version": str(version.get("name") or ""),
           "file": name, "path": path, "total": round(float(file.get("sizeKB") or 0) * 1024), "done": 0, "status": "downloading", "error": None,
           "started": time.time()}
    JOBS[job["id"]] = job
    TASKS[job["id"]] = asyncio.create_task(run_download(job, version, file, url))
    return public(job)
async def run_download(job, version, file, url):
    path, part = job["path"], job["path"] + ".part"
    loop = asyncio.get_running_loop()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        digest = hashlib.sha256()
        async with session(total=None, sock_connect=30, sock_read=120) as client, client.get(url, headers=auth_headers(url)) as response:
            if response.status in (401, 403):
                raise DownloadError("Civitai wants an API key for this download: add yours with 🔑 API key (Civitai → Account settings → API keys).")
            response.raise_for_status()
            if response.content_type.startswith("text/html"):
                raise DownloadError("Civitai answered with a web page instead of the file: the download may need an API key or early access.")
            job["total"] = response.content_length or job["total"]
            out = await loop.run_in_executor(None, open_for_writing, part) # The file is opened, written and closed off the event loop:
            try:                                                               # a slow disk doesn't stall ComfyUI.
                async for chunk in response.content.iter_any(): # As it arrives, so the progress moves on a slow line too.
                    await loop.run_in_executor(None, out.write, chunk)
                    digest.update(chunk)
                    job["done"] += len(chunk)
            finally:
                await loop.run_in_executor(None, out.close)
        sha256 = digest.hexdigest()
        expected = str((file.get("hashes") or {}).get("SHA256") or "").lower()
        if expected and expected != sha256:
            raise DownloadError("The download is damaged (its sha256 is not Civitai's): try again.")
        if os.path.exists(path):
            raise DownloadError(f"{job['file']} appeared meanwhile: the download was not saved over it.")
        os.replace(part, path)
        stat = os.stat(path)
        write_info(job["kind"], job["file"], {"user": {}, "size": stat.st_size, "mtime": stat.st_mtime, "sha256": sha256,
                                              "civitai": {**civitai_summary(version), **await model_details(version.get("modelId")), "checked": time.time()}})
        await save_preview(version, path)
        drop_list_cache(job["kind"])
        job.update(status="done", done=stat.st_size, total=stat.st_size)
    except asyncio.CancelledError:
        job["status"] = "cancelled"
        raise # Stopped: the cleanup below runs, and the task ends as cancelled.
    except Exception as error:
        logging.warning(f"[DiceForge] Civitai download of {job['file']} failed: {error}")
        job.update(status="error", error=str(error) if isinstance(error, DownloadError) else f"Download failed: {error}")
    finally:
        if job["status"] != "done" and os.path.exists(part):
            os.remove(part)
        TASKS.pop(job["id"], None)
# The first image of the version (not a video), resized by Civitai, as name.preview.<png|jpg|webp> when the model has no preview yet.
# The tags, stats and versions of the downloaded model's page (Model info asks again later when this fails).
async def model_details(model_id):
    if not isinstance(model_id, int) or isinstance(model_id, bool):
        return {}
    try:
        return {**civitai_details(await civitai_json(f"/models/{model_id}")), "details_checked": time.time()}
    except web.HTTPException as error:
        logging.warning(f"[DiceForge] Civitai: no model details for {model_id}: {error.text}")
        return {}
async def save_preview(version, path):
    image = next((image for image in images_of(version, 12) if image["type"] != "video"), None)
    if not image or local_preview(path, set(os.listdir(os.path.dirname(path)))):
        return
    try:
        async with session() as client, client.get(image["url"]) as response:
            response.raise_for_status()
            extension = {"image/png": ".png", "image/webp": ".webp"}.get(response.content_type, ".jpg")
            data = await read_up_to(response, PREVIEW_BYTES)
        if len(data) > PREVIEW_BYTES:
            raise ValueError(f"the image is over {PREVIEW_BYTES // (1024 * 1024)} MB")
        await asyncio.get_running_loop().run_in_executor(None, write_bytes, os.path.splitext(path)[0] + ".preview" + extension, data)
    except Exception as error: # The model is there; only its preview is missing (the browser shows Civitai's image instead).
        logging.warning(f"[DiceForge] Civitai preview of {os.path.basename(path)} not saved: {error}")
def cancel_download(job_id):
    job = JOBS.get(job_id)
    if job is None:
        raise web.HTTPNotFound(text="Civitai: no such download.")
    task = TASKS.get(job_id)
    if task:
        task.cancel()
        job["status"] = "cancelled"
    else:
        JOBS.pop(job_id) # A finished one: cleared from the list.
    return public(job)


def query_flag(query, key):
    return query.get(key, "").lower() in ("1", "true", "yes")
def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/civitai/search")
    async def civitai_search(request):
        query = request.rel_url.query
        return web.json_response(await search(query.get("kind", "loras"), query.get("query", ""), query.get("base", ""), query.get("sort", ""),
                                              query_flag(query, "nsfw"), query.get("cursor", "")))
    @routes.post("/diceforge/civitai/download")
    async def civitai_download(request):
        body = await json_body(request)
        return web.json_response(await start_download(body.get("kind", "loras"), body.get("version_id"), body.get("folder", "")))
    @routes.get("/diceforge/civitai/downloads")
    async def civitai_downloads(request):
        return web.json_response({"jobs": [public(job) for job in sorted(JOBS.values(), key=lambda job: -job["started"])]})
    @routes.delete("/diceforge/civitai/downloads")
    async def civitai_cancel(request):
        return web.json_response(cancel_download(request.rel_url.query.get("id", "")))
    @routes.get("/diceforge/civitai/key")
    async def civitai_key(request):
        _key, source = api_key()
        return web.json_response({"set": source is not None, "source": source})
    @routes.post("/diceforge/civitai/key")
    async def civitai_save_key(request):
        key = (await json_body(request)).get("key", "")
        if not isinstance(key, str) or (key.strip() and not re.fullmatch(r"[\w-]{8,200}", key.strip())):
            raise web.HTTPBadRequest(text="Civitai: that is not an API key (letters and digits, from Civitai → Account settings → API keys).")
        try:
            await asyncio.get_running_loop().run_in_executor(None, save_key, key.strip())
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Civitai: the key could not be saved: {error.strerror or error}.") from None
        _key, source = api_key()
        return web.json_response({"set": source is not None, "source": source})
    @routes.post("/diceforge/models/rename")
    async def models_rename(request):
        body = await json_body(request)
        try:
            return web.json_response(await asyncio.get_running_loop().run_in_executor(None, rename_model, body.get("kind", ""), body.get("file"), body.get("to")))
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Models: can't rename: {error.strerror or error}.") from None
    @routes.delete("/diceforge/models/file")
    async def models_delete(request):
        query = request.rel_url.query
        try:
            return web.json_response(await asyncio.get_running_loop().run_in_executor(None, delete_model, query.get("kind", ""), query.get("file")))
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Models: can't delete: {error.strerror or error}.") from None
    @routes.post("/diceforge/models/restore")
    async def models_restore(request):
        body = await json_body(request)
        try:
            return web.json_response(await asyncio.get_running_loop().run_in_executor(None, restore_model, body.get("kind", ""), body.get("id")))
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Models: can't bring the model back: {error.strerror or error}.") from None
register_routes()
empty_all_trash()
