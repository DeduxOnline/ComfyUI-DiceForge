import asyncio
import json
import os
import re
import folder_paths
from aiohttp import web
from .clip_text_encode_pos_neg import entry_lines, find_wildcard, read_text_lines, wildcard_index
from .model_info import json_body
# Server side of the Wildcard Browser and the __ autocomplete (web/wildcards.js): the list of wildcards, and creating, reading, saving, renaming and
# deleting a wildcard file. Wildcards from yaml files are listed and shown too, but read-only: they are edited in their yaml file.
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
                          **({"yaml": os.path.basename(entry["path"])} if "lines" in entry else {}), **error})
        return web.json_response({"folders": folder_paths.get_folder_paths("wildcards"), "files": files})
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
            await asyncio.get_running_loop().run_in_executor(None, delete_file, path)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't delete {name}: {error.strerror or error}.") from None
        wildcard_index(refresh=True)
        rename_favorite(name, None)
        return web.json_response({"deleted": name, "path": path})
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
