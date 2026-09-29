import os
import re
import folder_paths
from aiohttp import web
from .clip_text_encode_pos_neg import find_wildcard, wildcard_names
# Server side of the Wildcard Browser and the __ autocomplete (web/wildcards.js): the list of wildcard files, reading one, and saving one.
NAME = re.compile(r"[\w\-. ]+(/[\w\-. ]+)*")
def checked_name(name):
    name = (name or "").strip().replace("\\", "/").removesuffix(".txt")
    if not NAME.fullmatch(name) or ".." in name.split("/"):
        raise web.HTTPBadRequest(text=f"Wildcards: {name!r} is not a usable name (letters, digits, - _ . space, and / for folders).")
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
        for name in wildcard_names():
            lines = [line.strip() for line in read_lines(find_wildcard(name))]
            options = [line for line in lines if line and not line.startswith("#")]
            files.append({"name": name, "lines": len(options), "preview": options[:3]})
        return web.json_response({"folders": folder_paths.get_folder_paths("wildcards"), "files": files})
    @routes.get("/diceforge/wildcards/file")
    async def read_wildcard_file(request):
        name = checked_name(request.rel_url.query.get("name"))
        path = find_wildcard(name)
        if path is None:
            raise web.HTTPNotFound(text=f"Wildcards: no file {name}.txt.")
        return web.json_response({"name": name, "path": path, "text": "\n".join(read_lines(path))})
    @routes.post("/diceforge/wildcards/file")
    async def save_wildcard_file(request):
        body = await request.json()
        name = checked_name(body.get("name"))
        path = find_wildcard(name) # An existing file is saved in place; a new one goes to the first wildcards folder.
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
