import logging
import math
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .seed_modes import MEMORY, SEED_MODES, SEED_MODE_TOOLTIP, make_picker, pick_label, pick_in_range
# Resolution groups for the nested list: fixed SDXL sizes, high-res sizes, random picks from those lists, and random chaos sizes.
STANDARD = {
    "1024 x 1024": (1024, 1024),
    "1152 x 896": (1152, 896),
    "896 x 1152": (896, 1152),
    "1216 x 832": (1216, 832),
    "832 x 1216": (832, 1216),
    "1344 x 768": (1344, 768),
    "768 x 1344": (768, 1344),
    "1536 x 640": (1536, 640),
    "640 x 1536": (640, 1536),
}
HIGH_RES = {
    "1536 x 1536": (1536, 1536),
    "1152 x 1536": (1152, 1536),
    "1536 x 1152": (1536, 1152),
    "1024 x 1536": (1024, 1536),
    "1536 x 1024": (1536, 1024),
    "1536 x 864": (1536, 864),
    "864 x 1536": (864, 1536),
}
RANDOM_LISTED = {
    "Any Listed": list(STANDARD.values()),
    "Any High-Res Listed": list(HIGH_RES.values()),
    "Vertical Listed": [size for size in STANDARD.values() if size[0] < size[1]],
    "Horizontal Listed": [size for size in STANDARD.values() if size[0] > size[1]],
    "Vertical High-Res Listed": [size for size in HIGH_RES.values() if size[0] < size[1]],
    "Horizontal High-Res Listed": [size for size in HIGH_RES.values() if size[0] > size[1]],
}
RANDOM_CHAOS = ["Any", "Portrait", "Landscape"] # Orientations for Random Chaos.
CHAOS_PIXELS = 1024 * 1024 # Pixel budget of Random Chaos before rescale: the SDXL native size.
# Rescale modes, like the HiresFix node of Easy-Use: by percentage of each side, to a width and/or height, or to a longest side.
BY_PERCENTAGE, TO_WIDTH_HEIGHT, TO_LONGEST_SIDE = "by percentage", "to Width/Height", "to longest side"
def rescaled(width, height, rescale):
    mode = (rescale or {}).get("rescale", BY_PERCENTAGE)
    if mode not in (BY_PERCENTAGE, TO_WIDTH_HEIGHT, TO_LONGEST_SIDE): # ComfyUI lets an unknown option through in an API prompt.
        raise ValueError(f"Rescale: unknown mode {mode!r}. Use one of: {BY_PERCENTAGE}, {TO_WIDTH_HEIGHT}, {TO_LONGEST_SIDE}.")
    if mode == TO_WIDTH_HEIGHT:
        target_width, target_height = rescale.get("width", 0), rescale.get("height", 0)
        if target_width and target_height:
            return float(target_width), float(target_height) # Both: that exact size.
        if target_width:
            return float(target_width), height * target_width / width # One: the other follows the aspect ratio.
        if target_height:
            return width * target_height / height, float(target_height)
        return width, height
    if mode == TO_LONGEST_SIDE:
        side = rescale.get("longer_side", 1024) # Set exactly, not as a factor: float rounding must not take it below (Random Chaos rounds down).
        return (float(side), height * side / width) if width >= height else (width * side / height, float(side))
    factor = (rescale or {}).get("percent", 100) / 100 # Each side: the pixels (megapixels) grow by its square.
    return width * factor, height * factor
# The rescale input of both resolution nodes: the mode, and the input under it. Optional inputs come after the required ones in the node, so only
# Resolution Selector (where it is the last input anyway) has it optional: there a prompt without it gets 100%.
def rescale_input(optional=False):
    return io.DynamicCombo.Input(
        "rescale",
        options=[
            io.DynamicCombo.Option(BY_PERCENTAGE, [io.Int.Input("percent", default=100, min=5, max=1000, step=5, # min on the step grid: the frontend snaps to min + k * step.
                tooltip="Each side in percent: 150 turns 1024x1024 into 1536x1536 (2.25 times the pixels), 50 into 512x512. Then rounded to multiple.")]),
            io.DynamicCombo.Option(TO_WIDTH_HEIGHT, [
                io.Int.Input("width", default=1536, min=0, max=16384, step=8, tooltip="The width. 0: follows the aspect ratio from the height."),
                io.Int.Input("height", default=0, min=0, max=16384, step=8, tooltip="The height. 0: follows the aspect ratio from the width. Both set: that exact size, whatever the size picked above."),
            ]),
            io.DynamicCombo.Option(TO_LONGEST_SIDE, [io.Int.Input("longer_side", default=1536, min=64, max=16384, step=8,
                tooltip="The longest side of the size, keeping the aspect ratio: 1536 turns 1216x832 into 1536x1048 (rounded to multiple 8).")]),
        ],
        tooltip="Rescale the picked size, like HiresFix: by percentage of each side, to a width and/or height, or to a longest side.",
        optional=optional,
    )
# Random Chaos Portrait and Landscape stay non-square after rounding (a ratio close to 1:1 can round to a square): the shorter side steps down a
# multiple, keeping the pixel budget, unless the rescale sets that side or it is already at the minimum: then the longer side steps up, unless the
# rescale sets that one (to longest side, or an exact size): what you set wins, even if that is a square.
def keep_orientation(width, height, orientation, multiple, rescale):
    if width != height or orientation not in ("portrait", "landscape"):
        return width, height
    mode = (rescale or {}).get("rescale")
    set_width = mode == TO_WIDTH_HEIGHT and bool(rescale.get("width"))
    set_height = mode == TO_WIDTH_HEIGHT and bool(rescale.get("height"))
    if orientation == "portrait": # Width is the shorter side, height the longer.
        if width > multiple and not set_width:
            return width - multiple, height
        return (width, height + multiple) if not set_height and mode != TO_LONGEST_SIDE else (width, height)
    if height > multiple and not set_height:
        return width, height - multiple
    return (width + multiple, height) if not set_width and mode != TO_LONGEST_SIDE else (width, height)
# The rescale settings a run reports with its size (the preview of random sizes compares them with the node's current ones).
def rescale_settings(rescale):
    rescale = rescale or {}
    return {"rescale": rescale.get("rescale", BY_PERCENTAGE), "percent": rescale.get("percent"), "rescale_width": rescale.get("width"),
            "rescale_height": rescale.get("height"), "longer_side": rescale.get("longer_side")}
def describe_rescale(rescale):
    mode = (rescale or {}).get("rescale", BY_PERCENTAGE)
    if mode == TO_WIDTH_HEIGHT:
        return f"{mode} {rescale.get('width', 0)}x{rescale.get('height', 0)}"
    return f"{mode} {rescale.get('longer_side') if mode == TO_LONGEST_SIDE else (rescale or {}).get('percent', 100)}"
# Node schema (V3 / Nodes 2.0): SDXL resolution selection with a nested list (pick a group, then a size of that group), outputting an empty latent of that size (like Empty Latent Image). Scale, multiple and batch are shown in the Advanced section.
class SDXLResolutionListLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        size = lambda options, tooltip, default=None: io.Combo.Input("size", options=list(options), default=default or next(iter(options)), tooltip=tooltip)
        return io.Schema(
            node_id="SDXLResolutionListLatent",
            display_name="SDXL Resolution List (Latent)",
            category="DiceForge/latent",
            description="Pick a resolution from the SDXL list (or at random from the seed) and output an empty latent of that size.",
            has_intermediate_output=True, # The size of the last run reaches the preview also when the node comes from the cache.
            inputs=[
                io.DynamicCombo.Input(
                    "resolution",
                    options=[
                        io.DynamicCombo.Option("Standard", [size(STANDARD, "Standard SDXL size, width x height.")]),
                        io.DynamicCombo.Option("High-Res", [size(HIGH_RES, "High-res size, width x height.")]),
                        io.DynamicCombo.Option("Random", [size(RANDOM_LISTED, "Picks one of the listed sizes at random from the seed: any, only vertical or only horizontal.")]),
                        io.DynamicCombo.Option("Random Chaos", [
                            size(RANDOM_CHAOS, "Orientation of the random aspect ratio: any, only portrait (taller than wide) or only landscape (wider than tall). The size stays within 1024x1024 pixels before rescale (by percentage 150: within 1536x1536 pixels)."),
                            io.Float.Input("max_aspect", default=2.0, min=1.0, max=4.0, step=0.05, tooltip="The most stretched aspect ratio allowed (2.0 = up to 2:1 or 1:2)."),
                        ]),
                    ],
                    tooltip="Resolution group: fixed sizes, or random sizes picked from the seed.",
                ),
                # The core resolution preview, fed by the frontend extension (web/resolution_preview.js) through two hidden helper widgets.
                io.ResolutionPreview.Input(
                    "preview",
                    tooltip="Live preview of the output size. Random sizes show the size of the last run, until the settings change.",
                    ratio_widget="preview_ratio",
                    megapixels_widget="preview_megapixels",
                    multiple_widget="multiple",
                ),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    tooltip="Seed for random resolution selection.",
                ),
                rescale_input(),
                io.Int.Input(
                    "multiple",
                    default=8,
                    min=8,
                    max=256,
                    step=8,
                    tooltip="Round width and height to a multiple of this value (8 for the VAE, 64 for SDXL training buckets). Random Chaos sizes round down.",
                    advanced=True,
                ),
                io.Int.Input(
                    "batch",
                    default=1,
                    min=1,
                    max=32,
                    step=1,
                    tooltip="Number of images to generate in a batch.",
                    advanced=True,
                ),
                io.Combo.Input(
                    "seed_mode",
                    options=SEED_MODES,
                    default="random",
                    tooltip=SEED_MODE_TOOLTIP,
                    advanced=True,
                ),
            ],
            # Outputs for the node: the empty latent batch, its width and height in pixels, and the seed.
            outputs=[
                io.Latent.Output(display_name="latent", tooltip="Empty latent batch, the same as Empty Latent Image makes for this size."),
                io.Int.Output(display_name="width", tooltip="Width of the latent in pixels."),
                io.Int.Output(display_name="height", tooltip="Height of the latent in pixels."),
                io.Int.Output(display_name="seed", tooltip="The seed used for this run, for example to pass on to KSampler."),
            ],
        )
    # Rounding method to make width and height multiples of `multiple` (at least `multiple` itself). Of the multiples just below and above each side,
    # the pair closest to the exact aspect ratio is taken (then the one closest in pixels), so the ratio doesn't drift. round_down: both below, so the
    # size never goes over the pixel budget (Random Chaos).
    @staticmethod
    def round_to_multiple(width, height, multiple=8, round_down=False):
        steps = lambda value: {max(multiple, math.floor(value / multiple) * multiple)} | (set() if round_down else {max(multiple, math.ceil(value / multiple) * multiple)})
        ratio, pixels = math.log(width / height), width * height
        return min(((w, h) for w in steps(width) for h in steps(height)), key=lambda size: (round(abs(math.log(size[0] / size[1]) - ratio), 9), abs(size[0] * size[1] - pixels), size))
    # Chaos-based random size: an aspect ratio picked uniformly in log scale up to max_aspect (wide and tall equally likely), in the chosen orientation, sized to the pixel budget.
    # Seed modes other than random take turns between 8 equal parts of the range (4 for one orientation).
    @staticmethod
    def chaos_size(picker, seed, orientation="Any", max_aspect=2.0, pixels=CHAOS_PIXELS):
        low = 0.0 if orientation == "Landscape" else -math.log(max_aspect)
        high = 0.0 if orientation == "Portrait" else math.log(max_aspect)
        ratio = math.exp(pick_in_range(low, high, 8 if orientation == "Any" else 4, picker, seed, f"Chaos {orientation} {max_aspect}"))
        return math.sqrt(pixels * ratio), math.sqrt(pixels / ratio)
    # Main method to get the resolution based on the selected option, applying randomization and rounding as needed, then building the empty latent with Empty Latent Image.
    @classmethod
    def execute(cls, resolution=None, seed=0, rescale=None, multiple=8, batch=1, seed_mode="random", preview=None):
        if not isinstance(resolution, dict) or "size" not in resolution: # The nested list came without a valid group (a node saved by an older version).
            raise ValueError("SDXL Resolution List (Latent): the resolution list of this node has no valid group (it was probably saved by an older version). Pick the group and size again, or add the node again.")
        picker = make_picker(seed_mode, seed) # How random picks follow the seed (random: reproducible, same picks as before seed modes existed).
        group, size = resolution["resolution"], resolution["size"] # Nested list value: the group, and the size picked in it.
        # Switching logic to determine the width and height based on the selected group, handling random picks and chaos sizes appropriately.
        if group == "Random":
            width, height = map(int, pick_label([f"{w} x {h}" for w, h in RANDOM_LISTED[size]], picker, seed).split(" x "))#Returning a random resolution from the listed sizes.
        elif group == "Random Chaos":
            width, height = cls.chaos_size(picker, seed, size, resolution.get("max_aspect", 2.0), CHAOS_PIXELS)#Returning a random aspect ratio within the 1024x1024 pixel budget for chaos sizes.
        else:
            width, height = (HIGH_RES if group == "High-Res" else STANDARD)[size]#Returning the fixed resolution for standard and high-res sizes.
        # Rescale (by percentage, to width/height or to longest side), then rounding to multiple; Chaos sizes round down, so they stay within their
        # rescaled pixel budget.
        chaos = group == "Random Chaos"
        width, height = cls.round_to_multiple(*rescaled(width, height, rescale), multiple, round_down=chaos)
        if chaos and max(resolution.get("max_aspect", 2.0), 1.0) > 1.0:
            width, height = keep_orientation(width, height, size.lower(), multiple, rescale)
        MEMORY.save()
        # Logging the final resolution, rescale, multiple, seed, and batch size for debugging and verification purposes.
        logging.info(
            f"[DiceForge] SDXL Resolution List (Latent) | {group}: {size} | Size: {width}x{height} | Rescale: {describe_rescale(rescale)} | Multiple: {multiple} | Seed: {seed} ({seed_mode}) | Batch: {batch}"
        )
        latent = nodes.EmptyLatentImage().generate(width, height, batch)[0]
        # The size of this run, with the settings it came from, for the preview of random sizes in the frontend extension.
        last_size = {"width": width, "height": height, "group": group, "size": size, "max_aspect": resolution.get("max_aspect"), "multiple": multiple,
                     **rescale_settings(rescale)}
        return io.NodeOutput(latent, width, height, seed, ui={"dice_forge_last_size": [last_size]})
# Extension entry point for ComfyUI V3 node registration.
class SDXLResolutionListLatentExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SDXLResolutionListLatent]
async def comfy_entrypoint():
    return SDXLResolutionListLatentExtension()
