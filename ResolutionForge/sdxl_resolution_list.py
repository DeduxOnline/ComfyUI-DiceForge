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
RANDOM_CHAOS = {
    "Small": 512 * 512,
    "Medium": 1024 * 1024,
    "Large": 1536 * 1536,
}
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
                            size(RANDOM_CHAOS, "Pixel budget: Small up to 512x512, Medium up to 1024x1024, Large up to 1536x1536 pixels.", default="Medium"),
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
                    "multiply",
                    default=1.0,
                    min=0.1,
                    max=10.0,
                    step=0.05,
                    tooltip="Multiply the width and height by this value (Use vae_alignment for VAE compatibility of resolutions).",
                    advanced=True,
                ),
                io.Int.Input(
                    "vae_alignment",
                    default=64,
                    min=8,
                    max=256,
                    step=8,
                    tooltip="Round dimensions to nearest multiple of this value (VAE requirement). Random Chaos sizes round down.",
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
    # Vae alignment rounding method to ensure width and height are multiples of the specified alignment value, with a minimum of the alignment value itself.
    @staticmethod
    def round_for_vae(width, height, vae_alignment=64, round_down=False):
        snap = (lambda v: v // vae_alignment) if round_down else (lambda v: round(v / vae_alignment))
        return (
            max(vae_alignment, snap(width) * vae_alignment),
            max(vae_alignment, snap(height) * vae_alignment),
        )
    # Chaos-based random size: an aspect ratio picked uniformly in log scale up to max_aspect (wide and tall equally likely), sized to the pixel budget.
    @staticmethod
    def chaos_size(rng, pixels, max_aspect=2.0):
        ratio = math.exp(rng.uniform(-math.log(max_aspect), math.log(max_aspect)))
        return math.sqrt(pixels * ratio), math.sqrt(pixels / ratio)
    # Main method to get the resolution based on the selected option, applying randomization and VAE alignment as needed, and returning the final width, height, and batch size.
    @classmethod
    def execute(cls, resolution, seed=0, multiply=1.0, vae_alignment=64, batch=1):
        rng = random.Random(seed) #Seed behavior for reproducibility of random selections.
        group, size = resolution["resolution"], resolution["size"] # Nested list value: the group, and the size picked in it.
        # Switching logic to determine the width and height based on the selected group, handling random picks and chaos sizes appropriately.
        if group == "Random":
            width, height = rng.choice(RANDOM_LISTED[size])#Returning a random resolution from the listed sizes.
        elif group == "Random Chaos":
            width, height = cls.chaos_size(rng, RANDOM_CHAOS[size], resolution.get("max_aspect", 2.0))#Returning a random aspect ratio within the pixel budget for chaos sizes.
        else:
            width, height = (HIGH_RES if group == "High-Res" else STANDARD)[size]#Returning the fixed resolution for standard and high-res sizes.
        # Applying the multiply factor to the width and height, followed by rounding for VAE alignment to ensure compatibility with the model's requirements.
        width, height = cls.round_for_vae(
            round(width * multiply),
            round(height * multiply),
            vae_alignment,
            round_down=group == "Random Chaos", # Round chaos sizes down so they stay within the "up to" pixel limit.
        )
        # Logging the final resolution, VAE alignment, seed, and batch size for debugging and verification purposes.
        print(
            f"[ResolutionForge] SDXL Resolution List (Latent) | {group}: {size} | Size: {width}x{height} | VAE Alignment: {vae_alignment} | Seed: {seed} | Batch: {batch}"
        )
        return io.NodeOutput(width, height, batch, seed)
