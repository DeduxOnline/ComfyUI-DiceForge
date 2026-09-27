# Base of SDXL Resolution List (Latent): the resolution list and size logic. It is not registered as a node of its own.
import math
import random
from comfy_api.latest import io
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
CHAOS_PIXELS = 1024 * 1024 # Pixel budget of Random Chaos: the SDXL native size (use scale for larger or smaller sizes).
# Node schema (V3 / Nodes 2.0) for SDXL resolution selection with a nested list: pick a group, then a size of that group. Multiply, VAE alignment and batch are shown in the Advanced section.
class SDXLResolutionList(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        size = lambda options, tooltip, default=None: io.Combo.Input("size", options=list(options), default=default or next(iter(options)), tooltip=tooltip)
        return io.Schema(
            node_id="UnifiedSDXLResolution",
            display_name="SDXL Resolution List",
            category="utils",
            inputs=[
                io.DynamicCombo.Input(
                    "resolution",
                    options=[
                        io.DynamicCombo.Option("Standard", [size(STANDARD, "Standard SDXL size, width x height.")]),
                        io.DynamicCombo.Option("High-Res", [size(HIGH_RES, "High-res size, width x height.")]),
                        io.DynamicCombo.Option("Random", [size(RANDOM_LISTED, "Picks one of the listed sizes at random from the seed: any, only vertical or only horizontal.")]),
                        io.DynamicCombo.Option("Random Chaos", [
                            size(RANDOM_CHAOS, "Orientation of the random aspect ratio: any, only portrait (taller than wide) or only landscape (wider than tall). The size stays within 1024x1024 pixels before scale."),
                            io.Float.Input("max_aspect", default=2.0, min=1.0, max=4.0, step=0.05, tooltip="The most stretched aspect ratio allowed (2.0 = up to 2:1 or 1:2)."),
                        ]),
                    ],
                    tooltip="Resolution group: fixed sizes, or random sizes picked from the seed.",
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
                    default=1.0,
                    min=0.1,
                    max=10.0,
                    step=0.05,
                    tooltip="Scale the width and height by this factor (2.0 gives 4x the pixels), before rounding to multiple.",
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
            ],
            # Outputs for the node: width, height, batch size, and the seed.
            outputs=[
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
                io.Int.Output(display_name="batch"),
                io.Int.Output(display_name="seed", tooltip="The seed used for this run, for example to pass on to KSampler."),
            ],
        )
    # Rounding method to make width and height multiples of `multiple`, with a minimum of `multiple` itself.
    @staticmethod
    def round_to_multiple(width, height, multiple=8, round_down=False):
        snap = (lambda v: v // multiple) if round_down else (lambda v: round(v / multiple))
        return (
            max(multiple, snap(width) * multiple),
            max(multiple, snap(height) * multiple),
        )
    # Chaos-based random size: an aspect ratio picked uniformly in log scale up to max_aspect (wide and tall equally likely), in the chosen orientation, sized to the pixel budget.
    @staticmethod
    def chaos_size(rng, orientation="Any", max_aspect=2.0, pixels=CHAOS_PIXELS):
        low = 0.0 if orientation == "Landscape" else -math.log(max_aspect)
        high = 0.0 if orientation == "Portrait" else math.log(max_aspect)
        ratio = math.exp(rng.uniform(low, high))
        return math.sqrt(pixels * ratio), math.sqrt(pixels / ratio)
    # Main method to get the resolution based on the selected option, applying randomization and VAE alignment as needed, and returning the final width, height, and batch size.
    @classmethod
    def execute(cls, resolution, seed=0, scale=1.0, multiple=8, batch=1):
        rng = random.Random(seed) #Seed behavior for reproducibility of random selections.
        group, size = resolution["resolution"], resolution["size"] # Nested list value: the group, and the size picked in it.
        # Switching logic to determine the width and height based on the selected group, handling random picks and chaos sizes appropriately.
        if group == "Random":
            width, height = rng.choice(RANDOM_LISTED[size])#Returning a random resolution from the listed sizes.
        elif group == "Random Chaos":
            width, height = cls.chaos_size(rng, size, resolution.get("max_aspect", 2.0))#Returning a random aspect ratio within the pixel budget for chaos sizes.
        else:
            width, height = (HIGH_RES if group == "High-Res" else STANDARD)[size]#Returning the fixed resolution for standard and high-res sizes.
        # Applying the scale factor to the width and height, followed by rounding to multiple to ensure compatibility with the model's requirements.
        chaos = group == "Random Chaos"
        to_pixels = math.floor if chaos else round # Chaos sizes round down all the way, so they stay within the pixel budget.
        width, height = cls.round_to_multiple(
            to_pixels(width * scale),
            to_pixels(height * scale),
            multiple,
            round_down=chaos,
        )
        # Portrait and Landscape stay non-square after rounding (a ratio close to 1:1 can round to a square): the shorter side steps down, keeping the budget.
        if chaos and size != "Any" and width == height and max(resolution.get("max_aspect", 2.0), 1.0) > 1.0 and width > multiple:
            if size == "Portrait":
                width -= multiple
            else:
                height -= multiple
        # Logging the final resolution, VAE alignment, seed, and batch size for debugging and verification purposes.
        print(
            f"[ResolutionForge] SDXL Resolution List (Latent) | {group}: {size} | Size: {width}x{height} | Scale: {scale} | Multiple: {multiple} | Seed: {seed} | Batch: {batch}"
        )
        return io.NodeOutput(width, height, batch, seed)
