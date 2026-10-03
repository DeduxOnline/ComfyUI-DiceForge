import asyncio
import csv
import io
import os
import folder_paths
from aiohttp import web
from .model_info import json_body
# Prompt styles (web/prompt_styles.js, node menu of CLIP Dual Text Encode): named pieces of positive and negative prompt, put into the prompts with
# one click, as A1111's styles. Built in: the quality tags each model family is made for; yours: a styles.csv in A1111's format (name, prompt,
# negative_prompt) in the ComfyUI user folder, so an A1111 styles.csv can simply be copied there. {prompt} in a style's text is where the prompt
# goes; without it the style is added after the prompt.
BUILTIN = [
    {"name": "Illustrious quality", "prompt": "masterpiece, best quality, amazing quality, very aesthetic, absurdres, {prompt}",
     "negative_prompt": "{prompt}, lowres, worst quality, bad quality, bad anatomy, bad hands, jpeg artifacts, signature, watermark, text",
     "note": "Illustrious XL and its merges: quality tags first, the usual negative."},
    {"name": "NoobAI quality", "prompt": "masterpiece, best quality, newest, absurdres, highres, {prompt}",
     "negative_prompt": "{prompt}, worst quality, low quality, old, early, lowres, bad anatomy, bad hands, mutated hands, signature, username, logo, watermark",
     "note": "NoobAI-XL (eps and v-pred): its makers' quality and date tags."},
    {"name": "NoobAI v-pred quality", "prompt": "masterpiece, best quality, newest, absurdres, highres, very awa, {prompt}",
     "negative_prompt": "{prompt}, worst quality, low quality, old, early, lowres, bad anatomy, bad hands, mutated hands, signature, username, logo, watermark",
     "note": "NoobAI-XL v-pred: as NoobAI, with its very awa aesthetic tag."},
    {"name": "Anima quality", "prompt": "masterpiece, best quality, score_8, newest, {prompt}",
     "negative_prompt": "{prompt}, worst quality, low quality, score_1, score_2, score_3, blurry, jpeg artifacts, sepia",
     "note": "Anima: quality and score tags first; check the model page for the version you use."},
]
BUILTIN_NAMES = {style["name"].lower() for style in BUILTIN}
STYLES_FILE = os.path.join(folder_paths.get_user_directory(), "DiceForge", "styles.csv")
FIELDS = ("name", "prompt", "negative_prompt")


# A style as given (a request, or a row of the file): name, prompt and negative prompt, checked; None for one that isn't usable.
def checked(style):
    if not isinstance(style, dict):
        return None
    name, prompt, negative = style.get("name"), style.get("prompt") or "", style.get("negative_prompt") or ""
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80 or not isinstance(prompt, str) or not isinstance(negative, str):
        return None
    if not prompt.strip() and not negative.strip():
        return None
    if len(prompt) > 20000 or len(negative) > 20000:
        return None
    return {"name": name.strip(), "prompt": prompt, "negative_prompt": negative}
def parse_styles(text):
    styles, seen = [], set()
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        style = checked({key: row.get(key) for key in FIELDS})
        if style and style["name"].lower() not in seen:
            seen.add(style["name"].lower())
            styles.append(style)
    return styles
def read_styles():
    try:
        with open(STYLES_FILE, encoding="utf-8", newline="") as file:
            return parse_styles(file.read())
    except (OSError, UnicodeDecodeError, csv.Error): # None yet, or not a CSV: none (saving one writes a good file).
        return []
def write_styles(styles):
    os.makedirs(os.path.dirname(STYLES_FILE), exist_ok=True)
    with open(STYLES_FILE, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(styles)
def save_style(body):
    style = checked(body)
    if style is None:
        raise web.HTTPBadRequest(text="Prompt styles: a style needs a name (up to 80 characters) and a prompt or a negative prompt.")
    if style["name"].lower() in BUILTIN_NAMES:
        raise web.HTTPConflict(text=f"Prompt styles: {style['name']} is a built-in style; save yours under another name.")
    styles = [item for item in read_styles() if item["name"].lower() != style["name"].lower()] + [style] # The same name: replaced.
    write_styles(sorted(styles, key=lambda item: item["name"].lower()))
    return style
def delete_style(name):
    styles = read_styles()
    kept = [item for item in styles if item["name"].lower() != str(name or "").strip().lower()]
    if len(kept) == len(styles):
        raise web.HTTPNotFound(text=f"Prompt styles: no style of yours named {name!r}.")
    write_styles(kept)


def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/styles")
    async def list_styles(request):
        styles = await asyncio.get_running_loop().run_in_executor(None, read_styles)
        return web.json_response({"builtin": BUILTIN, "user": styles})
    @routes.post("/diceforge/styles")
    async def post_style(request):
        body = await json_body(request)
        try:
            return web.json_response(await asyncio.get_running_loop().run_in_executor(None, save_style, body))
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Prompt styles: can't save: {error.strerror or error}.") from None
    @routes.delete("/diceforge/styles")
    async def remove_style(request):
        name = request.rel_url.query.get("name", "")
        try:
            await asyncio.get_running_loop().run_in_executor(None, delete_style, name)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Prompt styles: can't delete: {error.strerror or error}.") from None
        return web.json_response({"deleted": name})
register_routes()
