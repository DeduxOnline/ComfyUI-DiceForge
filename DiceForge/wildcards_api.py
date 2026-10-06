import asyncio
import io
import json
import os
import re
import secrets
import shutil
import time
import zipfile
from urllib.parse import quote
import folder_paths
import yaml
from aiohttp import web
from .clip_text_encode_pos_neg import TextLoader, entry_lines, find_wildcard, read_text_lines, wildcard_index, yaml_wildcards
from .http_read import read_up_to
from .model_info import json_body
# Server side of the Wildcard Browser and the __ autocomplete (web/wildcards.js): the list of wildcards, and creating, reading, saving, renaming and
# deleting a wildcard file, converting txt files to a yaml file and back, and the cards' pictures. Wildcards from yaml files are listed and
# shown too, but read-only: they are edited in their yaml file (or converted to txt files). A deleted file goes to a trash folder first, so the
# Wildcard Browser can undo the delete; a folder (or all of them) can be exported as a zip.
PART = r"[\w\-.]+(?: [\w\-.]+)*" # Single spaces inside a name, as __hair color__ reads them (clip_text_encode_pos_neg.WILDCARD_PATTERN).
NAME = re.compile(rf"{PART}(/{PART})*")
def checked_name(name):
    name = (name if isinstance(name, str) else "").strip().replace("\\", "/").removesuffix(".txt")
    if not NAME.fullmatch(name) or ".." in name.split("/"):
        raise web.HTTPBadRequest(text=f"Wildcards: {name!r} is not a usable name (letters, digits, - _ ., single spaces inside, and / for folders).")
    return name
# Where a new wildcard file goes: in the given wildcards folder (by default the first one), never outside it.
def new_path(name, root=None):
    root = os.path.abspath(root or folder_paths.get_folder_paths("wildcards")[0])
    path = os.path.abspath(os.path.join(root, *name.split("/")) + ".txt")
    if not path.startswith(root + os.sep):
        raise web.HTTPBadRequest(text="Wildcards: the file would be outside the wildcards folder.")
    return path
# The wildcards folder a file is in.
def root_of(path):
    path = os.path.abspath(path)
    return next(root for root in map(os.path.abspath, folder_paths.get_folder_paths("wildcards")) if path.startswith(root + os.sep))
# The .txt file of an existing wildcard, for renaming or deleting it: a yaml wildcard or a missing one is a clear error.
def existing_file(name):
    path = find_wildcard(name)
    if path is None:
        entry = wildcard_index(refresh=True).get(name)
        if entry is not None:
            raise web.HTTPBadRequest(text=f"Wildcards: {name} comes from {entry['path']}: edit it in that yaml file.")
        raise web.HTTPNotFound(text=f"Wildcards: no wildcard {name}.")
    return path
# Folders left empty by a delete or a rename go too, up to (not including) the wildcards folder.
def remove_empty_folders(folder, root):
    while folder != root and folder.startswith(root + os.sep):
        try:
            os.rmdir(folder)
        except OSError: # Not empty (or not removable): it stays, and so do the folders above it.
            return
        folder = os.path.dirname(folder)
def delete_file(path):
    os.remove(path)
    remove_empty_folders(os.path.dirname(path), root_of(path))
def move_file(path, target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.replace(path, target) # The target was checked to be free (or the same file, in another case).
    remove_empty_folders(os.path.dirname(path), root_of(path))
# ★ Favorite wildcards (txt or yaml), by name, in the ComfyUI user folder; a rename or move takes the star along, a delete drops it.
FAVORITES_FILE = os.path.join(folder_paths.get_user_directory(), "DiceForge", "wildcard_favorites.json")
def read_favorites():
    try:
        with open(FAVORITES_FILE, encoding="utf-8") as file:
            names = json.load(file)
        return {name for name in names if isinstance(name, str)} if isinstance(names, list) else set()
    except (OSError, ValueError): # None yet, or damaged: no favorites (the next star writes a good file).
        return set()
def write_favorites(names):
    os.makedirs(os.path.dirname(FAVORITES_FILE), exist_ok=True)
    with open(FAVORITES_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(names, key=str.lower), file, ensure_ascii=False, indent=1)
def rename_favorite(name, to):
    names = read_favorites()
    if name in names:
        write_favorites((names - {name}) | ({to} if to else set()))
# Card pictures (the Wildcard Browser's cards mode): a yaml key's picture is next to its yaml file, at the key's path (POSES.yaml with
# POSES: {sitting: ...} and POSES/sitting.jpeg, as card packs come), or in a folder named like the file (poses.yaml and poses/POSES/sitting.png).
# Only a picture inside the yaml file's folder counts.
PICTURE_ENDINGS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
def card_picture(entry):
    if not entry or "inner" not in entry:
        return None
    folder = os.path.realpath(os.path.dirname(entry["path"]))
    stem = os.path.splitext(os.path.basename(entry["path"]))[0]
    parts = entry["inner"].split("/")
    for base in (os.path.join(folder, *parts), os.path.join(folder, stem, *parts)):
        for ending in PICTURE_ENDINGS:
            path = os.path.realpath(base + ending)
            if path.startswith(folder + os.sep) and os.path.isfile(path):
                return path
    return None
# A card's picture, sent from the browser: PNG, JPEG, WebP or GIF (by its first bytes, not its name), saved where card_picture finds it first
# (POSES/sitting.png next to POSES.yaml), in place of the picture it had. Only a yaml wildcard has a card picture.
PICTURE_BYTES = 20 * 1024 * 1024
def picture_ending(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else None
def picture_base(entry):
    if not entry or "inner" not in entry:
        return None
    folder = os.path.realpath(os.path.dirname(entry["path"]))
    base = os.path.realpath(os.path.join(folder, *entry["inner"].split("/")))
    return base if base.startswith(folder + os.sep) else None
def save_picture(base, data, ending):
    for other in PICTURE_ENDINGS:
        if os.path.isfile(base + other):
            os.remove(base + other)
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with open(base + ending, "wb") as file:
        file.write(data)
    return base + ending
# A folder or file of txt wildcards to one yaml file and back, with the same wildcard names: hair/ (hair/color.txt, hair/style.txt) becomes
# hair.yaml ({hair: {color: [...], style: [...]}}) next to the folder, and a yaml file becomes one txt file per key. Card pictures stay where they
# are (hair/color.png serves both). Nothing is overwritten: a name or file already taken stops the conversion before anything changes.
def yaml_target(name, root):
    parts = name.split("/")
    for ending in (".yaml", ".yml"):
        if os.path.exists(os.path.join(root, *parts[:-1], parts[-1] + ending)):
            raise web.HTTPConflict(text=f"Wildcards: {name}{ending} already exists.")
    return os.path.join(root, *parts[:-1], parts[-1] + ".yaml")
def to_yaml(name):
    index = wildcard_index(refresh=True)
    files = {key: entry["path"] for key, entry in index.items() if "lines" not in entry and (key == name or key.startswith(name + "/"))}
    if not files:
        raise web.HTTPNotFound(text=f"Wildcards: no txt wildcard {name} (or in the folder {name}).")
    root = root_of(files[min(files)])
    files = {key: path for key, path in files.items() if root_of(path) == root} # One wildcards folder: the yaml file goes there.
    target, depth, data = yaml_target(name, root), name.count("/"), {}
    for key, path in sorted(files.items()):
        level, parts = data, key.split("/")[depth:]
        for part in parts[:-1]:
            level = level.setdefault(part, {})
            if not isinstance(level, dict):
                raise web.HTTPConflict(text=f"Wildcards: {'/'.join(key.split('/')[:depth] + parts[:parts.index(part) + 1])} is both a file and a folder.")
        if isinstance(level.get(parts[-1]), dict):
            raise web.HTTPConflict(text=f"Wildcards: {key} is both a file and a folder.")
        try:
            level[parts[-1]] = [line.strip() for line in read_text_lines(path) if line.strip()]
        except ValueError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: {error}") from None
    with open(target, "w", encoding="utf-8", newline="\n") as file:
        yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False, default_flow_style=False, width=4096)
    for path in files.values():
        delete_file(path)
    return target, sorted(files)
def to_txt(name):
    index = wildcard_index(refresh=True)
    paths = sorted({entry["path"] for key, entry in index.items() if "lines" in entry and (key == name or key.startswith(name + "/"))})
    if not paths:
        raise web.HTTPNotFound(text=f"Wildcards: no yaml wildcard {name} (or in the folder {name}).")
    plan = []
    for path in paths:
        root = root_of(path)
        prefix = os.path.relpath(os.path.dirname(path), root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8-sig") as file:
                data = yaml.load(file, Loader=TextLoader)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't read {path}: {error}") from None
        for key, lines in yaml_wildcards(data, "" if prefix == "." else prefix):
            target = new_path(checked_name(key), root)
            if os.path.exists(target) or find_wildcard(key):
                raise web.HTTPConflict(text=f"Wildcards: {key}.txt already exists: rename it first.")
            plan.append((key, target, lines))
    if len({target for _, target, _ in plan}) < len(plan):
        raise web.HTTPConflict(text="Wildcards: two yaml keys would make the same txt file.")
    for _, target, lines in plan:
        write_lines(target, "\n".join(lines))
    for path in paths:
        os.remove(path)
    return paths, [key for key, _, _ in plan]
# Import a zip of wildcards (a card pack: POSES.yaml and POSES/sitting.png...): its txt, yaml and picture files go into the first wildcards
# folder (or a folder in it), with their paths. Files already there are skipped, never overwritten; other files and paths that would leave
# the folder are left out. Limits keep a zip bomb out.
ZIP_BYTES, ZIP_FILES, ZIP_UNPACKED = 512 * 1024 * 1024, 5000, 1024 * 1024 * 1024
IMPORTED = (".txt", ".yaml", ".yml") + PICTURE_ENDINGS
def import_zip(data, folder=""):
    root = os.path.abspath(folder_paths.get_folder_paths("wildcards")[0])
    base = os.path.abspath(os.path.join(root, *folder.split("/"))) if folder else root
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        members = [member for member in archive.infolist() if not member.is_dir()]
    except (zipfile.BadZipFile, ValueError, OSError):
        raise web.HTTPBadRequest(text="Wildcards: that is not a zip file.") from None
    if len(members) > ZIP_FILES or sum(member.file_size for member in members) > ZIP_UNPACKED:
        raise web.HTTPBadRequest(text=f"Wildcards: the zip is too big (at most {ZIP_FILES} files and 1 GB unpacked).")
    imported, skipped, left_out = [], [], []
    for member in members:
        parts = [part for part in member.filename.replace("\\", "/").split("/") if part not in ("", ".")]
        if not parts or ".." in parts or parts[0] == "__MACOSX" or any(part.startswith(".") for part in parts) or not parts[-1].lower().endswith(IMPORTED):
            left_out.append(member.filename)
            continue
        target = os.path.abspath(os.path.join(base, *parts))
        if not target.startswith(root + os.sep):
            left_out.append(member.filename)
        elif os.path.exists(target):
            skipped.append("/".join(parts))
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as file:
                file.write(source.read(ZIP_UNPACKED))
            imported.append("/".join(parts))
    return imported, skipped, left_out
# Export a folder of wildcards (all of them without one) as a zip that Import zip takes back: its txt, yaml and picture files, with their paths
# from the wildcards folder (the folder's own name included), and a yaml card pack's yaml file next to the folder (POSES.yaml with POSES/). A file
# in two wildcards folders goes once, from the first, as wildcards are read.
def export_zip(folder=""):
    buffer, added, total, found = io.BytesIO(), set(), 0, False
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(path, root):
            nonlocal total
            entry = os.path.relpath(path, root).replace(os.sep, "/")
            name = os.path.basename(path)
            if name.startswith(".") or not name.lower().endswith(IMPORTED) or entry in added or not os.path.isfile(path):
                return
            total += os.path.getsize(path)
            if total > ZIP_UNPACKED or len(added) >= ZIP_FILES:
                raise web.HTTPBadRequest(text=f"Wildcards: too much to export at once (at most {ZIP_FILES} files and 1 GB): export a smaller folder.")
            archive.write(path, entry)
            added.add(entry)
        for root in map(os.path.abspath, folder_paths.get_folder_paths("wildcards")):
            base = os.path.join(root, *folder.split("/")) if folder else root
            packs = [base + ending for ending in (".yaml", ".yml") if folder and os.path.isfile(base + ending)]
            found = found or bool(packs) or os.path.isdir(base)
            for pack in packs:
                add(pack, root)
            for current, folders, files in os.walk(base): # Links to folders are not followed: nothing outside the wildcards folder.
                folders[:] = sorted(name for name in folders if not name.startswith("."))
                for name in sorted(files):
                    add(os.path.join(current, name), root)
    if folder and not found:
        raise web.HTTPNotFound(text=f"Wildcards: no folder {folder}.")
    return buffer.getvalue()
# Deleted files wait in a trash folder (the last 50), so a delete can be undone: the file goes back where it was, with its star.
TRASH_FOLDER = os.path.join(folder_paths.get_user_directory(), "DiceForge", "wildcards_trash")
TRASH_KEPT = 50
TRASH_ID = re.compile(r"\d{19}-[0-9a-f]{8}")
last_trashed = [0] # Ids in the order of the deletes, also two within a clock tick: the oldest go first.
def trash_file(path, name, favorite):
    last_trashed[0] = max(time.time_ns(), last_trashed[0] + 1)
    trash_id = f"{last_trashed[0]:019d}-{secrets.token_hex(4)}"
    folder = os.path.join(TRASH_FOLDER, trash_id)
    os.makedirs(folder)
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as file:
        json.dump({"name": name, "path": os.path.abspath(path), "favorite": favorite}, file)
    root = root_of(path)
    shutil.move(path, os.path.join(folder, "file.txt")) # Moved, not copied: on another drive too.
    remove_empty_folders(os.path.dirname(os.path.abspath(path)), root)
    for old in sorted(os.listdir(TRASH_FOLDER))[:-TRASH_KEPT]:
        shutil.rmtree(os.path.join(TRASH_FOLDER, old), ignore_errors=True)
    return trash_id
def restore_file(trash_id):
    if not isinstance(trash_id, str) or not TRASH_ID.fullmatch(trash_id):
        raise web.HTTPBadRequest(text="Wildcards: that is not a deleted file's id.")
    folder = os.path.join(TRASH_FOLDER, trash_id)
    try:
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as file:
            meta = json.load(file)
        name, path = checked_name(meta.get("name")), os.path.abspath(str(meta.get("path", "")))
    except (OSError, ValueError, AttributeError):
        raise web.HTTPNotFound(text="Wildcards: nothing to undo: the deleted file is no longer kept.") from None
    if not any(path.startswith(root + os.sep) for root in map(os.path.abspath, folder_paths.get_folder_paths("wildcards"))):
        raise web.HTTPBadRequest(text="Wildcards: the deleted file was in a folder that is no longer a wildcards folder.")
    if wildcard_index(refresh=True).get(name) is not None or os.path.exists(path):
        raise web.HTTPConflict(text=f"Wildcards: there is a wildcard {name} again: rename it to bring the deleted one back.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.move(os.path.join(folder, "file.txt"), path)
    shutil.rmtree(folder, ignore_errors=True)
    return name, path, meta.get("favorite") is True
# Search the wildcards' lines (not only their names): each wildcard with a line that has the text, and its first such line.
def search_lines(text, limit=200):
    found = []
    for name, entry in sorted(wildcard_index(refresh=True).items(), key=lambda item: item[0].lower()):
        try:
            line = next((line for line in entry_lines(entry) if text in line.lower()), None)
        except ValueError: # An unreadable file: not found in it.
            continue
        if line is not None:
            found.append({"name": name, "line": line})
            if len(found) >= limit:
                break
    return found
def write_lines(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(text.replace("\r\n", "\n").rstrip("\n") + "\n")
def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/wildcards")
    async def list_wildcards(request):
        files, favorites = [], read_favorites()
        for name, entry in sorted(wildcard_index(refresh=True).items(), key=lambda item: item[0].lower()):
            try:
                options, error = entry_lines(entry), {}
            except ValueError as problem: # One unreadable file doesn't hide the others: it is listed with its error.
                options, error = [], {"error": str(problem)}
            files.append({"name": name, "lines": len(options), "preview": options[:3], "favorite": name in favorites,
                          **({"yaml": os.path.basename(entry["path"])} if "lines" in entry else {}), **({"picture": True} if card_picture(entry) else {}), **error})
        return web.json_response({"folders": folder_paths.get_folder_paths("wildcards"), "files": files})
    @routes.get("/diceforge/wildcards/picture")
    async def wildcard_picture(request):
        name = checked_name(request.rel_url.query.get("name"))
        path = card_picture(wildcard_index().get(name) or wildcard_index(refresh=True).get(name))
        if path is None:
            raise web.HTTPNotFound(text=f"Wildcards: no picture for {name}.")
        return web.FileResponse(path, headers={"Cache-Control": "max-age=300"})
    @routes.post("/diceforge/wildcards/picture")
    async def set_wildcard_picture(request):
        name = checked_name(request.rel_url.query.get("name"))
        base = picture_base(wildcard_index(refresh=True).get(name))
        if base is None:
            raise web.HTTPBadRequest(text=f"Wildcards: {name} is not a yaml card: pictures are for the wildcards of a yaml file.")
        data = await read_up_to(request, PICTURE_BYTES) # The whole body (content.read(n) gives only what has come so far).
        if len(data) > PICTURE_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=PICTURE_BYTES, actual_size=len(data), text="Wildcards: the picture is over 20 MB.")
        ending = picture_ending(data)
        if ending is None:
            raise web.HTTPBadRequest(text="Wildcards: send a PNG, JPEG, WebP or GIF picture.")
        try:
            path = await asyncio.get_running_loop().run_in_executor(None, save_picture, base, data, ending)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't save the picture: {error.strerror or error}.") from None
        return web.json_response({"name": name, "picture": path})
    @routes.delete("/diceforge/wildcards/picture")
    async def remove_wildcard_picture(request):
        name = checked_name(request.rel_url.query.get("name"))
        path = card_picture(wildcard_index(refresh=True).get(name))
        if path is None:
            raise web.HTTPNotFound(text=f"Wildcards: no picture for {name}.")
        try:
            os.remove(path)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't remove the picture: {error.strerror or error}.") from None
        return web.json_response({"name": name, "removed": path})
    # Convert a txt wildcard or folder to one yaml file ("to": "yaml"), or the yaml file(s) of a wildcard or folder to txt files ("to": "txt").
    @routes.post("/diceforge/wildcards/convert")
    async def convert_wildcards(request):
        body = await json_body(request)
        name, to = checked_name(body.get("name")), body.get("to")
        if to not in ("yaml", "txt"):
            raise web.HTTPBadRequest(text='Wildcards: "to" must be "yaml" or "txt".')
        try:
            if to == "yaml":
                path, names = await asyncio.get_running_loop().run_in_executor(None, to_yaml, name)
                result = {"converted": name, "to": "yaml", "path": path, "names": names}
            else:
                paths, names = await asyncio.get_running_loop().run_in_executor(None, to_txt, name)
                result = {"converted": name, "to": "txt", "removed": paths, "names": names}
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't convert {name}: {error.strerror or error}.") from None
        wildcard_index(refresh=True)
        return web.json_response(result)
    @routes.get("/diceforge/wildcards/file")
    async def read_wildcard_file(request):
        name = checked_name(request.rel_url.query.get("name"))
        entry = wildcard_index(refresh=True).get(name)
        if entry is None:
            raise web.HTTPNotFound(text=f"Wildcards: no wildcard {name}.")
        if "lines" in entry:
            return web.json_response({"name": name, "path": entry["path"], "text": "\n".join(entry["lines"]), "readonly": True})
        try:
            lines = read_text_lines(entry["path"])
        except ValueError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: {error}") from None
        return web.json_response({"name": name, "path": entry["path"], "text": "\n".join(lines)})
    # Create ("create": true, refused when the name is taken) or save: an existing file is saved in place, a new one goes to the first wildcards folder.
    @routes.post("/diceforge/wildcards/file")
    async def save_wildcard_file(request):
        body = await json_body(request)
        name = checked_name(body.get("name"))
        path = find_wildcard(name)
        entry = wildcard_index(refresh=True).get(name)
        if body.get("create") is True and entry is not None:
            raise web.HTTPConflict(text=f"Wildcards: {name} already exists ({entry['path']}).")
        if path is None and entry is not None:
            raise web.HTTPBadRequest(text=f"Wildcards: {name} comes from {entry['path']}: edit it in that yaml file.")
        path = path or new_path(name)
        try:
            await asyncio.get_running_loop().run_in_executor(None, write_lines, path, str(body.get("text", ""))) # Off the event loop.
        except OSError as error: # A name too long for the file system, a read-only folder...: a message, not a server error.
            raise web.HTTPBadRequest(text=f"Wildcards: can't save {name}: {error.strerror or error}.") from None
        return web.json_response({"saved": name, "path": path})
    # Rename or move (a / in the new name puts it in a folder): the file stays in its wildcards folder, and a name already taken is refused.
    @routes.post("/diceforge/wildcards/rename")
    async def rename_wildcard_file(request):
        body = await json_body(request)
        name, to = checked_name(body.get("name")), checked_name(body.get("to"))
        path = existing_file(name)
        target = new_path(to, root_of(path))
        taken = wildcard_index(refresh=True).get(to)
        if taken is not None and os.path.normcase(os.path.abspath(taken["path"])) != os.path.normcase(os.path.abspath(path)): # Only a change of case is the same file.
            raise web.HTTPConflict(text=f"Wildcards: {to} already exists ({taken['path']}).")
        if os.path.exists(target) and os.path.normcase(target) != os.path.normcase(os.path.abspath(path)):
            raise web.HTTPConflict(text=f"Wildcards: {target} already exists.")
        try:
            await asyncio.get_running_loop().run_in_executor(None, move_file, path, target)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't rename {name} to {to}: {error.strerror or error}.") from None
        wildcard_index(refresh=True)
        rename_favorite(name, to)
        return web.json_response({"renamed": name, "to": to, "path": target})
    @routes.delete("/diceforge/wildcards/file")
    async def delete_wildcard_file(request):
        name = checked_name(request.rel_url.query.get("name"))
        path = existing_file(name)
        try:
            trash_id = await asyncio.get_running_loop().run_in_executor(None, trash_file, path, name, name in read_favorites())
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't delete {name}: {error.strerror or error}.") from None
        wildcard_index(refresh=True)
        rename_favorite(name, None)
        return web.json_response({"deleted": name, "path": path, "undo": trash_id})
    # Undo a delete: {"id": the delete's "undo"}.
    @routes.post("/diceforge/wildcards/restore")
    async def restore_wildcard_file(request):
        body = await json_body(request)
        try:
            name, path, favorite = await asyncio.get_running_loop().run_in_executor(None, restore_file, body.get("id"))
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't bring the file back: {error.strerror or error}.") from None
        wildcard_index(refresh=True)
        if favorite:
            try:
                write_favorites(read_favorites() | {name})
            except OSError: # Back without its star.
                pass
        return web.json_response({"restored": name, "path": path})
    @routes.get("/diceforge/wildcards/export")
    async def export_wildcards(request):
        folder = request.rel_url.query.get("folder", "").strip()
        folder = checked_name(folder) if folder else ""
        data = await asyncio.get_running_loop().run_in_executor(None, export_zip, folder)
        filename = f"wildcards-{folder.replace('/', '-')}.zip" if folder else "wildcards.zip"
        return web.Response(body=data, content_type="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})
    @routes.post("/diceforge/wildcards/import")
    async def import_wildcards(request):
        folder = request.rel_url.query.get("folder", "").strip()
        folder = checked_name(folder) if folder else ""
        data = await read_up_to(request, ZIP_BYTES)
        if len(data) > ZIP_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=ZIP_BYTES, actual_size=len(data), text="Wildcards: the zip is over 512 MB.")
        try:
            imported, skipped, left_out = await asyncio.get_running_loop().run_in_executor(None, import_zip, data, folder)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't import the zip: {error.strerror or error}.") from None
        wildcard_index(refresh=True)
        return web.json_response({"imported": imported, "skipped": skipped, "left_out": left_out})
    @routes.get("/diceforge/wildcards/search")
    async def search_wildcard_lines(request):
        text = request.rel_url.query.get("q", "").strip().lower()
        if len(text) < 2:
            raise web.HTTPBadRequest(text="Wildcards: search for at least 2 characters.")
        return web.json_response({"found": await asyncio.get_running_loop().run_in_executor(None, search_lines, text)})
    @routes.post("/diceforge/wildcards/favorite")
    async def favorite_wildcard(request):
        body = await json_body(request)
        name, favorite = checked_name(body.get("name")), body.get("favorite")
        if not isinstance(favorite, bool):
            raise web.HTTPBadRequest(text="Wildcards: favorite must be true or false.")
        if favorite and name not in wildcard_index(refresh=True):
            raise web.HTTPNotFound(text=f"Wildcards: no wildcard {name}.")
        names = read_favorites()
        try:
            write_favorites(names | {name} if favorite else names - {name})
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: the favorites could not be saved: {error.strerror or error}.") from None
        return web.json_response({"name": name, "favorite": favorite})
register_routes()
