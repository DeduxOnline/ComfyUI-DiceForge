import asyncio
import json
import os
import comfy.samplers
import folder_paths
from aiohttp import web
from .model_info import json_body
# KSampler presets (web/sampler_presets.js, node menu of KSampler and KSampler Advanced): steps, CFG, sampler and scheduler for a model family, from
# the models' own recommendations, and your own presets, saved in the ComfyUI user folder. "Auto" in the menu picks the built-in one by the base
# model of the connected checkpoint (Civitai's base model names in BASES).
BUILTIN = [
    {"name": "Anima", "steps": 30, "cfg": 4.5, "sampler_name": "er_sde", "scheduler": "simple",
     "note": "Anima base / aesthetic (CircleStone Labs): 30-50 steps, CFG 4-6 (the aesthetic version also at 3); er_sde is its maker's default, euler_ancestral is softer."},
    {"name": "Anima Turbo", "steps": 10, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
     "note": "Anima Turbo, the distilled version: CFG 1 and 8-12 steps."},
    {"name": "Illustrious", "steps": 28, "cfg": 6.0, "sampler_name": "euler_ancestral", "scheduler": "normal",
     "note": "Illustrious XL and its merges: Euler a, 20-30 steps, CFG 5-7."},
    {"name": "NoobAI (eps)", "steps": 28, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "normal",
     "note": "NoobAI-XL epsilon versions: Euler a, 28 steps, CFG 4-6."},
    {"name": "NoobAI (v-pred)", "steps": 30, "cfg": 4.5, "sampler_name": "euler", "scheduler": "normal",
     "note": "NoobAI-XL v-prediction: Euler only (other samplers and Karras don't work properly), 28-35 steps, CFG 4-5. A checkpoint not marked as v-pred needs ModelSamplingDiscrete (v_prediction) in front."},
]
BUILTIN_NAMES = {preset["name"].lower() for preset in BUILTIN}
PRESETS_FILE = os.path.join(folder_paths.get_user_directory(), "DiceForge", "sampler_presets.json")
FIELDS = ("steps", "cfg", "sampler_name", "scheduler")


# A preset as given (a request, or a line of the file): its name and the four settings, checked; None for one that isn't usable.
def checked(preset):
    if not isinstance(preset, dict):
        return None
    name, steps, cfg = preset.get("name"), preset.get("steps"), preset.get("cfg")
    sampler, scheduler = preset.get("sampler_name"), preset.get("scheduler")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
        return None
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 10000:
        return None
    if isinstance(cfg, bool) or not isinstance(cfg, (int, float)) or not 0.0 <= cfg <= 100.0:
        return None
    if sampler not in comfy.samplers.KSampler.SAMPLERS or scheduler not in comfy.samplers.KSampler.SCHEDULERS:
        return None
    return {"name": name.strip(), "steps": steps, "cfg": round(float(cfg), 2), "sampler_name": sampler, "scheduler": scheduler}
def read_presets():
    try:
        with open(PRESETS_FILE, encoding="utf-8") as file:
            presets = json.load(file)
    except (OSError, ValueError): # None yet, or damaged: none (saving one writes a good file).
        return []
    return [preset for preset in map(checked, presets if isinstance(presets, list) else []) if preset]
def write_presets(presets):
    os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)
    with open(PRESETS_FILE, "w", encoding="utf-8") as file:
        json.dump(presets, file, ensure_ascii=False, indent=1)
def save_preset(body):
    preset = checked(body)
    if preset is None:
        raise web.HTTPBadRequest(text="Sampler presets: a preset needs a name (up to 60 characters), steps (1-10000), cfg (0-100) and a sampler and "
                                      "scheduler of this ComfyUI.")
    if preset["name"].lower() in BUILTIN_NAMES:
        raise web.HTTPConflict(text=f"Sampler presets: {preset['name']} is a built-in preset; save yours under another name.")
    presets = [item for item in read_presets() if item["name"].lower() != preset["name"].lower()] + [preset] # The same name: replaced.
    write_presets(sorted(presets, key=lambda item: item["name"].lower()))
    return preset
def delete_preset(name):
    presets = read_presets()
    kept = [item for item in presets if item["name"].lower() != str(name or "").strip().lower()]
    if len(kept) == len(presets):
        raise web.HTTPNotFound(text=f"Sampler presets: no preset of yours named {name!r}.")
    write_presets(kept)


def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/sampler-presets")
    async def list_presets(request):
        presets = await asyncio.get_running_loop().run_in_executor(None, read_presets)
        return web.json_response({"builtin": BUILTIN, "user": presets})
    @routes.post("/diceforge/sampler-presets")
    async def post_preset(request):
        body = await json_body(request)
        try:
            return web.json_response(await asyncio.get_running_loop().run_in_executor(None, save_preset, body))
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Sampler presets: can't save: {error.strerror or error}.") from None
    @routes.delete("/diceforge/sampler-presets")
    async def remove_preset(request):
        name = request.rel_url.query.get("name", "")
        try:
            await asyncio.get_running_loop().run_in_executor(None, delete_preset, name)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Sampler presets: can't delete: {error.strerror or error}.") from None
        return web.json_response({"deleted": name})
register_routes()
