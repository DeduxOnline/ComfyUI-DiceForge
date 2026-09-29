import os
import re
import folder_paths
from aiohttp import web
from .clip_text_encode_pos_neg import entry_lines, find_wildcard, wildcard_index
# Server side of the Wildcard Browser and the __ autocomplete (web/wildcards.js): the list of wildcards, reading one, and saving one. Wildcards from
# yaml files are listed and shown too, but read-only: they are edited in their yaml file.
PART = r"[\w\-.]+(?: [\w\-.]+)*" # Single spaces inside a name, as __hair color__ reads them (clip_text_encode_pos_neg.WILDCARD_PATTERN).
NAME = re.compile(rf"{PART}(/{PART})*")
def checked_name(name):
    name = (name or "").strip().replace("\\", "/").removesuffix(".txt")
    if not NAME.fullmatch(name) or ".." in name.split("/"):
        raise web.HTTPBadRequest(text=f"Wildcards: {name!r} is not a usable name (letters, digits, - _ ., single spaces inside, and / for folders).")
    return name
def read_lines(path):
    with open(path, encoding="utf-8") as file:
        return [line.rstrip("\r\n") for line in file]
def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/wildcards")
    async def list_wildcards(request):
        files = []
        for name, entry in sorted(wildcard_index(refresh=True).items(), key=lambda item: item[0].lower()):
            options = entry_lines(entry)
            files.append({"name": name, "lines": len(options), "preview": options[:3], **({"yaml": os.path.basename(entry["path"])} if "lines" in entry else {})})
        return web.json_response({"folders": folder_paths.get_folder_paths("wildcards"), "files": files})
    @routes.get("/diceforge/wildcards/file")
    async def read_wildcard_file(request):
        name = checked_name(request.rel_url.query.get("name"))
        entry = wildcard_index(refresh=True).get(name)
        if entry is None:
            raise web.HTTPNotFound(text=f"Wildcards: no wildcard {name}.")
        if "lines" in entry:
            return web.json_response({"name": name, "path": entry["path"], "text": "\n".join(entry["lines"]), "readonly": True})
        return web.json_response({"name": name, "path": entry["path"], "text": "\n".join(read_lines(entry["path"]))})
    @routes.post("/diceforge/wildcards/file")
    async def save_wildcard_file(request):
        body = await request.json()
        name = checked_name(body.get("name"))
        path = find_wildcard(name) # An existing file is saved in place; a new one goes to the first wildcards folder.
        entry = wildcard_index(refresh=True).get(name)
        if path is None and entry is not None:
            raise web.HTTPBadRequest(text=f"Wildcards: {name} comes from {entry['path']}: edit it in that yaml file.")
        if path is None:
            root = os.path.abspath(folder_paths.get_folder_paths("wildcards")[0])
            path = os.path.abspath(os.path.join(root, *name.split("/")) + ".txt")
            if not path.startswith(root + os.sep):
                raise web.HTTPBadRequest(text="Wildcards: the file would be outside the wildcards folder.")
            os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as file:
            file.write(str(body.get("text", "")).replace("\r\n", "\n").rstrip("\n") + "\n")
        return web.json_response({"saved": name, "path": path})
register_routes()
