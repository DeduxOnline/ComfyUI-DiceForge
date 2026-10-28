import math
import re
import folder_paths
import nodes
from aiohttp import web
from comfy_api.latest import io
from .routes import in_thread, json_body
from .model_lists import matching_files
from .random_sampler import SAMPLERS, SCHEDULERS, options_output, parse_names
from .variation_seed import with_variation
# XY Plot: one node gives KSampler the settings of one cell of an X/Y comparison (seed, steps, CFG, sampler, scheduler, LoRA, LoRA strength,
# denoise, variation seed or variation strength on each axis) and Dice Grid its labels. index counts up after each run (control after generate:
# increment), so ComfyUI's Run with a batch count of the number of cells (Set Run to N cells, in the node's menu: web/xy_plot.js) makes every
# cell, from index 0, and Dice Grid lays the images out with the values as column and row headers.
AXES = ("none", "seed", "steps", "cfg", "sampler", "scheduler", "lora", "lora strength", "denoise", "variation seed", "variation strength")
MAX_VALUES, MAX_CELLS = 64, 256 # Per axis, and in all: a typo like 1-100000 doesn't queue a night of images.
NUMBER = r"-?\d+(?:\.\d+)?"
RANGE = re.compile(rf"^({NUMBER})\s*(?:\.\.|-)\s*({NUMBER})(?:\s*:\s*({NUMBER}))?$") # 1-5, 3.5-7:0.5, -1..1:0.5
NUMBER_AXES = {"seed": (int, 0, 0xFFFFFFFFFFFFFFFF), "steps": (int, 1, 10000), "cfg": (float, 0.0, 100.0), "lora strength": (float, -100.0, 100.0),
               "denoise": (float, 0.0, 1.0), "variation seed": (int, 0, 0xFFFFFFFFFFFFFFFF), "variation strength": (float, 0.0, 1.0)}


def short(value):
    return f"{value:g}" if isinstance(value, float) else str(value)
def number(text): # Whole numbers stay exact (seeds go past what a float holds).
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    value = float(text)
    if not math.isfinite(value): # 1e999 is inf; nan is no number either.
        raise ValueError(f"XY Plot: {text} is not a usable number.")
    return value
# Numbers typed in a field: separated by commas or new lines, each a number or a range (start-end, with :step; the step is 1 unless given).
def parse_numbers(text, axis):
    kind, low, high = NUMBER_AXES[axis]
    values = []
    for item in (item.strip() for item in re.split(r"[,\n]", text or "")):
        if not item:
            continue
        match = RANGE.match(item)
        if match:
            start, end = number(match.group(1)), number(match.group(2))
            step = abs(number(match.group(3))) if match.group(3) else 1
            if step == 0:
                raise ValueError(f"XY Plot: the step of {item} is 0.")
            try:
                count = math.floor(abs(end - start) / step + 1e-9) + 1
            except OverflowError: # A range past what a float holds.
                count = None
            if count is None or count > MAX_VALUES:
                raise ValueError(f"XY Plot: {item} has {count or 'too many'} values, more than {MAX_VALUES}.")
            direction = 1 if end >= start else -1
            exact = all(isinstance(part, int) for part in (start, end, step))
            values += [start + index * step * direction if exact else round(start + index * step * direction, 6) for index in range(count)]
        else:
            try:
                values.append(number(item))
            except ValueError:
                raise ValueError(f"XY Plot: {item!r} is not a number or a range (like 4-8 or 3.5-7:0.5) for {axis}.") from None
    if kind is int:
        if any(value != int(value) for value in values):
            raise ValueError(f"XY Plot: {axis} takes whole numbers.")
        values = [int(value) for value in values]
    else:
        values = [float(value) for value in values] # CFG 4 is the float 4.0 KSampler takes.
    outside = [short(value) for value in values if not low <= value <= high]
    if outside:
        raise ValueError(f"XY Plot: {', '.join(outside)} out of range for {axis} ({short(kind(low))} to {short(kind(high))}).")
    return list(dict.fromkeys(values))
# LoRA files typed in a field: names (with or without folder and extension) or patterns like style/* ; None for the image without a LoRA.
def parse_loras(text):
    names = []
    for item in (item.strip() for item in re.split(r"[,\n]", text or "")):
        if not item:
            continue
        if item.lower() == "none":
            names.append("None")
            continue
        found = matching_files("loras", item)
        if not found:
            raise ValueError(f"XY Plot: no LoRA matches {item!r}.")
        names += found
    return list(dict.fromkeys(names))
def axis_values(axis, text):
    if axis not in AXES:
        raise ValueError(f"XY Plot: unknown axis {axis!r}.")
    if axis == "none":
        return [None]
    if axis in NUMBER_AXES:
        values = parse_numbers(text, axis)
    elif axis == "sampler":
        values = parse_names(text or "", SAMPLERS, "sampler", "XY Plot")
    elif axis == "scheduler":
        values = parse_names(text or "", SCHEDULERS, "scheduler", "XY Plot")
    else:
        values = parse_loras(text)
    if not values:
        raise ValueError(f"XY Plot: no values for {axis}.")
    if len(values) > MAX_VALUES:
        raise ValueError(f"XY Plot: {len(values)} values for {axis}, more than {MAX_VALUES}.")
    return values
def label(axis, value):
    if axis == "none":
        return ""
    if axis == "seed":
        return f"seed {value}"
    if axis == "steps":
        return f"{value} steps"
    if axis == "cfg":
        return f"CFG {short(value)}"
    if axis in ("lora strength", "denoise"):
        return f"{'strength' if axis == 'lora strength' else 'denoise'} {short(value)}"
    if axis.startswith("variation"):
        return f"variation {short(value)}"
    return "no LoRA" if axis == "lora" and value == "None" else str(value) # A LoRA file: Dice Grid shows it without folder and extension.
# Both axes, checked: their values and labels, and the number of cells. Y alone is taken as X (one row of images).
def plan(x_type, x_values, y_type, y_values):
    if y_type != "none" and x_type == "none":
        x_type, x_values, y_type, y_values = y_type, y_values, "none", ""
    if x_type != "none" and x_type == y_type:
        raise ValueError(f"XY Plot: X and Y are both {x_type}; pick two different axes.")
    xs, ys = axis_values(x_type, x_values), axis_values(y_type, y_values)
    if len(xs) * len(ys) > MAX_CELLS:
        raise ValueError(f"XY Plot: {len(xs)} x {len(ys)} = {len(xs) * len(ys)} images, more than {MAX_CELLS}.")
    return {"x_type": x_type, "y_type": y_type, "xs": xs, "ys": ys, "count": len(xs) * len(ys)}
FIELDS = {"seed": "seed", "steps": "steps", "cfg": "cfg", "sampler": "sampler_name", "scheduler": "scheduler", "lora": "lora_name", "lora strength": "lora_strength",
          "denoise": "denoise", "variation seed": "variation_seed", "variation strength": "variation_strength"}


class XYPlot(io.ComfyNode):
    loader = nodes.LoraLoader() # The core loader, which keeps the last LoRA file in memory.

    @classmethod
    def define_schema(cls):
        axis_tip = ("Values, separated by commas or new lines. Numbers: 4, 5.5, 7 or ranges 4-8 (step 1) and 3.5-7:0.5. Sampler, scheduler: names, * for all. "
                    "LoRA: file names, with or without folder and extension, patterns like style/*, None for no LoRA.")
        return io.Schema(
            node_id="DiceForgeXYPlot",
            display_name="XY Plot",
            category="DiceForge/sampling",
            description="Settings for an X/Y comparison grid: each run gives KSampler the values of one cell and Dice Grid its labels, and goes on to the next cell; "
                        "Set Run to N cells in the node's menu makes the whole plot with ComfyUI's Run.",
            search_aliases=["xy plot", "xy grid", "x/y plot", "comparison", "grid", "sampler comparison", "cfg comparison", "lora comparison"],
            inputs=[
                io.Combo.Input("x_type", options=list(AXES), default="cfg", tooltip="What changes from column to column."),
                io.String.Input("x_values", multiline=True, default="4, 5.5, 7", tooltip=axis_tip),
                io.Combo.Input("y_type", options=list(AXES), default="sampler", tooltip="What changes from row to row (none: one row)."),
                io.String.Input("y_values", multiline=True, default="euler, euler_ancestral, dpmpp_2m", tooltip=axis_tip),
                # Counts up after each run, so Run goes cell by cell; past the last cell it starts again at the first (a new grid), so its maximum
                # is far past MAX_CELLS: increment stops at the maximum.
                io.Int.Input("index", default=0, min=0, max=0xFFFFFFFF, control_after_generate=io.ControlAfterGenerate.increment,
                             tooltip="The cell of this run, row by row; past the last one it starts again at the first. Counts up after each run, so Run makes the cells one by one."),
                # No control after generate: the runs of a plot go cell by cell, and the frontend's (randomize by default for an input named seed)
                # would give each cell another seed.
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=False,
                             tooltip="Seed of every cell, unless an axis is seed. It stays the same from cell to cell."),
                io.Int.Input("steps", default=28, min=1, max=10000, tooltip="Steps of every cell, unless an axis is steps."),
                io.Float.Input("cfg", default=6.0, min=0.0, max=100.0, step=0.1, round=0.01, tooltip="CFG of every cell, unless an axis is cfg."),
                io.Combo.Input("sampler_name", options=list(SAMPLERS), default="euler_ancestral" if "euler_ancestral" in SAMPLERS else SAMPLERS[0],
                               tooltip="Sampler of every cell, unless an axis is sampler."),
                io.Combo.Input("scheduler", options=list(SCHEDULERS), default="normal" if "normal" in SCHEDULERS else SCHEDULERS[0],
                               tooltip="Scheduler of every cell, unless an axis is scheduler."),
                io.Float.Input("denoise", default=1.0, min=0.0, max=1.0, step=0.01, tooltip="Denoise of every cell, unless an axis is denoise.", advanced=True),
                io.Combo.Input("lora_name", options=["None", *folder_paths.get_filename_list("loras")], default="None",
                               tooltip="LoRA of every cell (for a lora strength axis), unless an axis is lora. Applied to model and clip.", advanced=True),
                io.Float.Input("lora_strength", default=1.0, min=-100.0, max=100.0, step=0.05, tooltip="LoRA strength, unless an axis is lora strength.", advanced=True),
                io.Int.Input("variation_seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, tooltip="Variation seed of every cell (as Variation Seed), unless an axis is variation seed.", advanced=True, optional=True),
                io.Float.Input("variation_strength", default=0.0, min=0.0, max=1.0, step=0.01,
                               tooltip="Variation strength of every cell (0: none). A variation seed axis with strength 0.1: variations of one picture.", advanced=True, optional=True),
                io.Model.Input("model", optional=True, tooltip="The model, for a LoRA (lora_name, or a lora axis). Passed through otherwise."),
                io.Clip.Input("clip", optional=True, tooltip="The CLIP, for a LoRA. Passed through otherwise."),
            ],
            outputs=[
                io.Model.Output(display_name="model", tooltip="The model, with this cell's LoRA."),
                io.Clip.Output(display_name="clip", tooltip="The CLIP, with this cell's LoRA."),
                io.Int.Output(display_name="seed", tooltip="For KSampler's seed."),
                io.Int.Output(display_name="steps", tooltip="For KSampler's steps."),
                io.Float.Output(display_name="cfg", tooltip="For KSampler's cfg."),
                options_output("sampler_name", SAMPLERS, "For KSampler's sampler_name."),
                options_output("scheduler", SCHEDULERS, "For KSampler's scheduler."),
                io.Float.Output(display_name="denoise", tooltip="For KSampler's denoise."),
                io.String.Output(display_name="x_label", tooltip="For Dice Grid's label: the column."),
                io.String.Output(display_name="y_label", tooltip="For Dice Grid's row_label: the row."),
                io.Int.Output(display_name="count", tooltip="Images in the grid, for Dice Grid's count."),
                io.Int.Output(display_name="columns", tooltip="Values on X, for Dice Grid's columns (one row per Y value)."),
                io.Boolean.Output(display_name="new_grid", tooltip="True for the first cell, for Dice Grid's new_grid: each plot starts a fresh grid."),
            ],
        )

    @classmethod
    def validate_inputs(cls, x_type="none", x_values="", y_type="none", y_values="", **kwargs):
        try:
            plan(x_type, x_values, y_type, y_values)
        except ValueError as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, x_type, x_values, y_type, y_values, index=0, seed=0, steps=28, cfg=6.0, sampler_name="euler", scheduler="normal", denoise=1.0,
                lora_name="None", lora_strength=1.0, model=None, clip=None, variation_seed=0, variation_strength=0.0):
        layout = plan(x_type, x_values, y_type, y_values)
        cell = index % layout["count"]
        x, y = layout["xs"][cell % len(layout["xs"])], layout["ys"][cell // len(layout["xs"])]
        values = {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler_name, "scheduler": scheduler, "denoise": denoise, "lora_name": lora_name,
                  "lora_strength": lora_strength, "variation_seed": variation_seed, "variation_strength": variation_strength}
        for axis, value in ((layout["x_type"], x), (layout["y_type"], y)):
            if axis != "none":
                values[FIELDS[axis]] = value
        if values["lora_name"] != "None":
            if model is None:
                raise ValueError("XY Plot: a LoRA needs the model input connected (and clip, for its text part).")
            strength = values["lora_strength"]
            model, lora_clip = cls.loader.load_lora(model, clip, values["lora_name"], strength, strength if clip is not None else 0)
            clip = lora_clip if clip is not None else None
        if values["variation_strength"] > 0:
            if model is None:
                raise ValueError("XY Plot: a variation needs the model input connected (its output goes to KSampler).")
            model = with_variation(model, values["variation_seed"], values["variation_strength"])
        return io.NodeOutput(model, clip, values["seed"], values["steps"], values["cfg"], values["sampler_name"], values["scheduler"], values["denoise"],
                             label(layout["x_type"], x), label(layout["y_type"], y), layout["count"], len(layout["xs"]), cell == 0)


# The node's preview (web/xy_plot.js): the labels of both axes and the count, or what is wrong with the values.
def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.post("/diceforge/xy-plot")
    async def xy_preview(request):
        body = await json_body(request)
        x_type, x_values, y_type, y_values = (body.get(key) if isinstance(body.get(key), str) else "" for key in ("x_type", "x_values", "y_type", "y_values"))
        try:
            layout = await in_thread(plan, x_type or "none", x_values, y_type or "none", y_values) # A lora axis lists the LoRA files.
        except ValueError as error:
            raise web.HTTPBadRequest(text=str(error)) from None
        return web.json_response({"x_type": layout["x_type"], "y_type": layout["y_type"], "count": layout["count"],
                                  "x": [label(layout["x_type"], value) for value in layout["xs"]], "y": [label(layout["y_type"], value) for value in layout["ys"]]})
register_routes()
