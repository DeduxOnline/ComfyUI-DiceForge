import asyncio
import bisect
import csv
import heapq
import io
import json
import logging
import os
import re
import threading
import aiohttp
import folder_paths
from aiohttp import web
from .model_info import json_body
# Tag autocomplete for the prompt fields (web/tag_autocomplete.js): Danbooru and e621 tags, the way anime models (Illustrious, NoobAI, Anima) were
# trained on them, with how often each is used and its aliases. The lists are CSV files in the format of a1111-sd-webui-tagcomplete
# (tag,type,count,"alias,alias"), kept in the ComfyUI user folder: downloaded from that project with one click, or put there by hand. Every list
# there is used; a tag in two lists counts once, with its higher count.
TAGS_FOLDER = os.path.join(folder_paths.get_user_directory(), "DiceForge", "tags")
TAGS_URL = os.environ.get("DICEFORGE_TAGS_URL", "https://raw.githubusercontent.com/DominikDoom/a1111-sd-webui-tagcomplete/main/tags/{name}.csv")
LISTS = {"danbooru": "Danbooru (anime: Illustrious, NoobAI, Anima, Pony)", "e621": "e621 (furry: NoobAI, Pony)"}
MAX_BYTES = 64 * 1024 * 1024 # A tag list is a few MB; anything far bigger is not one.
TYPES = {0: "general", 1: "artist", 3: "copyright", 4: "character", 5: "meta"}
TYPE_NUMBERS = {name: number for number, name in TYPES.items()}
FAVORITES_FILE = os.path.join(folder_paths.get_user_directory(), "DiceForge", "tag_favorites.json")
SORTS = ("count", "name")


def tag_key(text):
    return re.sub(r"\s+", "_", text.strip().lower())
# The tags of a CSV text: (tag, type, count, aliases), rows that aren't tags left out.
def parse_tags(text):
    tags = []
    for row in csv.reader(io.StringIO(text.lstrip("﻿"))):
        if len(row) < 2 or not row[0].strip() or len(row[0]) > 200: # At least the tag and its type, as in every tagcomplete list.
            continue
        try:
            kind = int(row[1]) if row[1].strip() else 0
            count = int(float(row[2])) if len(row) > 2 and row[2].strip() else 0
        except ValueError:
            continue # A header line, or not a tag list.
        aliases = [alias.strip() for alias in (row[3] if len(row) > 3 else "").split(",") if alias.strip() and len(alias) <= 200]
        tags.append((row[0].strip(), kind, max(count, 0), aliases))
    return tags


# The tags of every list in the folder, read again when a file changes: names and aliases sorted, for prefix search by bisection.
class TagIndex:
    def __init__(self):
        self.lock, self.signature, self.tags, self.names, self.aliases, self.by_count = threading.Lock(), None, [], [], [], []

    def files(self):
        try:
            return sorted(name for name in os.listdir(TAGS_FOLDER) if name.lower().endswith(".csv"))
        except OSError:
            return []

    def load(self):
        files = self.files()
        signature = tuple((name, os.path.getmtime(os.path.join(TAGS_FOLDER, name)), os.path.getsize(os.path.join(TAGS_FOLDER, name))) for name in files)
        with self.lock:
            if signature == self.signature:
                return self
            merged = {}
            for name in files:
                try:
                    with open(os.path.join(TAGS_FOLDER, name), encoding="utf-8", errors="replace") as file:
                        tags = parse_tags(file.read())
                except OSError as error:
                    logging.warning(f"[DiceForge] Tag autocomplete: can't read {name}: {error}")
                    continue
                for tag, kind, count, aliases in tags:
                    known = merged.get(tag_key(tag))
                    if known is None or count > known[2]:
                        merged[tag_key(tag)] = (tag, kind, count, sorted(set(aliases) | set(known[3] if known else [])))
            self.tags = list(merged.values())
            self.names = sorted((tag_key(tag[0]), index) for index, tag in enumerate(self.tags))
            self.aliases = sorted((tag_key(alias), index, alias) for index, tag in enumerate(self.tags) for alias in tag[3])
            self.by_count = sorted(range(len(self.tags)), key=lambda index: (-self.tags[index][2], self.tags[index][0].lower()))
            self.signature = signature
        return self

    # The most used tags whose name or an alias starts with what is typed (spaces as underscores), then those that contain it.
    def search(self, typed, limit=12):
        key = tag_key(typed)
        if not key:
            return []
        found = {}
        for sorted_list in (self.names, self.aliases):
            start = bisect.bisect_left(sorted_list, (key,))
            for entry in sorted_list[start:]:
                if not entry[0].startswith(key):
                    break
                index = entry[1]
                if index not in found:
                    found[index] = entry[2] if len(entry) > 2 else None # The alias that matched, to show it.
        best = heapq.nlargest(limit, found, key=lambda index: self.tags[index][2])
        if len(best) < limit and len(key) >= 3: # Few start with it: the most used that contain it.
            more = (index for index, tag in enumerate(self.tags) if index not in found and key in tag_key(tag[0]))
            best += heapq.nlargest(limit - len(best), more, key=lambda index: self.tags[index][2])
        return [{"tag": self.tags[index][0], "type": TYPES.get(self.tags[index][1], "general"), "count": self.tags[index][2], "alias": found.get(index)}
                for index in best]
    def entry(self, index, favorites=frozenset()):
        tag, kind, count, aliases = self.tags[index]
        return {"tag": tag, "type": TYPES.get(kind, "general"), "count": count, "aliases": aliases[:8], "favorite": tag in favorites}

    # The Tag Browser's page of tags: those whose name or an alias contains what is typed (all without), of one type or the favorites, most used
    # first or by name; offset and limit page through them.
    def browse(self, typed="", kind="", sort="count", offset=0, limit=100, favorites=frozenset()):
        key = tag_key(typed)
        number = TYPE_NUMBERS.get(kind)
        def fits(index):
            tag, tag_kind, _count, aliases = self.tags[index]
            if kind == "favorites" and tag not in favorites:
                return False
            if number is not None and tag_kind != number:
                return False
            return not key or key in tag_key(tag) or any(key in tag_key(alias) for alias in aliases)
        found = [index for index in self.by_count if fits(index)]
        if sort == "name":
            found.sort(key=lambda index: self.tags[index][0].lower())
        elif key: # Most used first, but the tags that start with what is typed before the ones that only contain it.
            found.sort(key=lambda index: not tag_key(self.tags[index][0]).startswith(key))
        return {"tags": [self.entry(index, favorites) for index in found[offset:offset + limit]], "total": len(found)}
INDEX = TagIndex()


def read_favorites():
    try:
        with open(FAVORITES_FILE, encoding="utf-8") as file:
            names = json.load(file)
    except (OSError, ValueError):
        return [] # None yet, or damaged: none.
    return [name for name in names if isinstance(name, str) and name.strip()][:10000] if isinstance(names, list) else []
def set_favorite(tag, favorite):
    names = [name for name in read_favorites() if name != tag] + ([tag] if favorite else [])
    os.makedirs(os.path.dirname(FAVORITES_FILE), exist_ok=True)
    with open(FAVORITES_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(names, key=str.lower), file, ensure_ascii=False, indent=1)
    return names
def number_query(query, name, default, low, high):
    try:
        return max(low, min(int(query.get(name, default)), high))
    except ValueError:
        return default


async def download(name):
    if name not in LISTS:
        raise web.HTTPBadRequest(text=f"Tag autocomplete: no list {name!r} (there are {', '.join(LISTS)}).")
    url = TAGS_URL.format(name=name)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300), trust_env=True) as session, session.get(url) as response:
            response.raise_for_status()
            data = await response.content.read(MAX_BYTES + 1)
    except aiohttp.ClientError as error:
        raise web.HTTPBadGateway(text=f"Tag autocomplete: can't download the {name} list: {error}.") from None
    except asyncio.TimeoutError:
        raise web.HTTPBadGateway(text=f"Tag autocomplete: downloading the {name} list took too long.") from None
    text = data.decode("utf-8", errors="replace")
    tags = parse_tags(text)
    if len(data) > MAX_BYTES or not tags:
        raise web.HTTPBadGateway(text=f"Tag autocomplete: what came for the {name} list is not a tag list.")
    def save():
        os.makedirs(TAGS_FOLDER, exist_ok=True)
        path = os.path.join(TAGS_FOLDER, f"{name}.csv")
        with open(path + ".part", "wb") as file:
            file.write(data)
        os.replace(path + ".part", path)
    await asyncio.get_running_loop().run_in_executor(None, save)
    return {"list": name, "tags": len(tags)}


def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/tags")
    async def search_tags(request):
        query = request.rel_url.query
        limit = number_query(query, "limit", 12, 1, 50)
        index = await asyncio.get_running_loop().run_in_executor(None, INDEX.load)
        return web.json_response({"tags": index.search(query.get("q", "")[:100], limit), "ready": bool(index.tags)})
    @routes.get("/diceforge/tags/browse")
    async def browse_tags(request):
        query = request.rel_url.query
        kind, sort = query.get("type", ""), query.get("sort", "count")
        if kind and kind not in TYPE_NUMBERS and kind != "favorites":
            raise web.HTTPBadRequest(text=f"Tag Browser: no tag type {kind!r} (there are {', '.join(TYPE_NUMBERS)} and favorites).")
        if sort not in SORTS:
            raise web.HTTPBadRequest(text=f"Tag Browser: sort by {' or '.join(SORTS)}.")
        loop = asyncio.get_running_loop()
        index = await loop.run_in_executor(None, INDEX.load)
        favorites = frozenset(await loop.run_in_executor(None, read_favorites))
        page = await loop.run_in_executor(None, lambda: index.browse(query.get("q", "")[:100], kind, sort, number_query(query, "offset", 0, 0, 10 ** 7),
                                                                     number_query(query, "limit", 100, 1, 500), favorites))
        return web.json_response({**page, "ready": bool(index.tags)})
    @routes.post("/diceforge/tags/favorite")
    async def favorite_tag(request):
        body = await json_body(request)
        tag, favorite = body.get("tag"), body.get("favorite")
        if not isinstance(tag, str) or not tag.strip() or len(tag) > 200 or not isinstance(favorite, bool):
            raise web.HTTPBadRequest(text="Tag Browser: a favorite needs the tag and favorite true or false.")
        try:
            names = await asyncio.get_running_loop().run_in_executor(None, set_favorite, tag.strip(), favorite)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Tag Browser: can't save the favorites: {error.strerror or error}.") from None
        return web.json_response({"favorites": len(names)})
    @routes.get("/diceforge/tags/lists")
    async def tag_lists(request):
        files = await asyncio.get_running_loop().run_in_executor(None, INDEX.files)
        return web.json_response({"files": files, "lists": [{"name": name, "title": title, "here": f"{name}.csv" in files} for name, title in LISTS.items()]})
    @routes.post("/diceforge/tags/download")
    async def download_tags(request):
        name = (await json_body(request)).get("list")
        return web.json_response(await download(name if isinstance(name, str) else ""))
register_routes()
