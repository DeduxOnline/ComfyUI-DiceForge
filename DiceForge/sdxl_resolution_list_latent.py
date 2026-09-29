import logging
import math
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .seed_modes import MEMORY, SEED_MODES, SEED_MODE_TOOLTIP, make_picker, pick_label, pick_in_range, fingerprint
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
CHAOS_PIXELS = 1024 * 1024 # Pixel budget of Random Chaos: the SDXL native size, times the square of scale sides by.
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
            inputs=[
                io.DynamicCombo.Input(
                    "resolution",
                    options=[
                        io.DynamicCombo.Option("Standard", [size(STANDARD, "Standard SDXL size, width x height.")]),
                        io.DynamicCombo.Option("High-Res", [size(HIGH_RES, "High-res size, width x height.")]),
                        io.DynamicCombo.Option("Random", [size(RANDOM_LISTED, "Picks one of the listed sizes at random from the seed: any, only vertical or only horizontal.")]),
                        io.DynamicCombo.Option("Random Chaos", [
                            size(RANDOM_CHAOS, "Orientation of the random aspect ratio: any, only portrait (taller than wide) or only landscape (wider than tall). The size stays within 1024x1024 pixels with each side times scale sides by (1.5: up to 1536x1536 pixels)."),
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
                io.Float.Input(
                    "scale",
                    display_name="scale sides by",
                    default=1.0,
                    min=0.1,
                    max=10.0,
                    step=0.05,
                    tooltip="Multiply the width and the height by this factor, keeping the aspect ratio: 1.5 turns 1024x1024 into 1536x1536, 0.5 into 512x512. The number of pixels grows by its square (1.5: 2.25 times the pixels, 2.0: 4 times). Then rounded to multiple.",
                    advanced=True,
                ),
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
    # Method to run the node every time for random sizes in the modes that remember earlier runs, instead of using ComfyUI's cache.
    @classmethod
    def fingerprint_inputs(cls, resolution=None, seed_mode="random", **kwargs):
        group = resolution.get("resolution") if isinstance(resolution, dict) else None
        return fingerprint(seed_mode) if group in ("Random", "Random Chaos") else None
    # Main method to get the resolution based on the selected option, applying randomization and rounding as needed, then building the empty latent with Empty Latent Image.
    @classmethod
    def execute(cls, resolution=None, seed=0, scale=1.0, multiple=8, batch=1, seed_mode="random", preview=None):
        if not isinstance(resolution, dict) or "size" not in resolution: # The nested list came without a valid group (a node saved by an older version).
            raise ValueError("SDXL Resolution List (Latent): the resolution list of this node has no valid group (it was probably saved by an older version). Pick the group and size again, or add the node again.")
        picker = make_picker(seed_mode, seed) # How random picks follow the seed (random: reproducible, same picks as before seed modes existed).
        group, size = resolution["resolution"], resolution["size"] # Nested list value: the group, and the size picked in it.
        # Switching logic to determine the width and height based on the selected group, handling random picks and chaos sizes appropriately.
        if group == "Random":
            width, height = map(int, pick_label([f"{w} x {h}" for w, h in RANDOM_LISTED[size]], picker, seed).split(" x "))#Returning a random resolution from the listed sizes.
        elif group == "Random Chaos":
            width, height = cls.chaos_size(picker, seed, size, resolution.get("max_aspect", 2.0), CHAOS_PIXELS * scale ** 2)#Returning a random aspect ratio within the pixel budget (each side times scale) for chaos sizes.
        else:
            width, height = (HIGH_RES if group == "High-Res" else STANDARD)[size]#Returning the fixed resolution for standard and high-res sizes.
        # Scale sides by: each side times scale, so the pixels (megapixels) times its square (Random Chaos has it in its pixel budget already). Then
        # rounding to multiple; Chaos sizes round down, so they stay within the pixel budget.
        chaos = group == "Random Chaos"
        side = 1.0 if chaos else scale
        width, height = cls.round_to_multiple(width * side, height * side, multiple, round_down=chaos)
        # Portrait and Landscape stay non-square after rounding (a ratio close to 1:1 can round to a square): the shorter side steps down, keeping the budget.
        if chaos and size != "Any" and width == height and max(resolution.get("max_aspect", 2.0), 1.0) > 1.0 and width > multiple:
            if size == "Portrait":
                width -= multiple
            else:
                height -= multiple
        MEMORY.save()
        # Logging the final resolution, scale, multiple, seed, and batch size for debugging and verification purposes.
        logging.info(
            f"[DiceForge] SDXL Resolution List (Latent) | {group}: {size} | Size: {width}x{height} | Scale sides by: {scale} | Multiple: {multiple} | Seed: {seed} ({seed_mode}) | Batch: {batch}"
        )
        latent = nodes.EmptyLatentImage().generate(width, height, batch)[0]
        # The size of this run, with the settings it came from, for the preview of random sizes in the frontend extension.
        last_size = {"width": width, "height": height, "group": group, "size": size, "max_aspect": resolution.get("max_aspect"), "scale": scale, "multiple": multiple}
        return io.NodeOutput(latent, width, height, seed, ui={"dice_forge_last_size": [last_size]})
# Extension entry point for ComfyUI V3 node registration.
class SDXLResolutionListLatentExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [SDXLResolutionListLatent]
async def comfy_entrypoint():
    return SDXLResolutionListLatentExtension()
