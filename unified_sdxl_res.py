import math
import random
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
# Aspect ratios for the canvas, in the "W:H (Name)" form the frontend resolution preview reads.
ASPECT_RATIOS = {
    "1:1 (Square)": (1, 1),
    "2:3 (Portrait Photo)": (2, 3),
    "3:2 (Photo)": (3, 2),
    "3:4 (Portrait Standard)": (3, 4),
    "4:3 (Standard)": (4, 3),
    "7:9 (Portrait)": (7, 9),
    "9:7 (Landscape)": (9, 7),
    "9:16 (Portrait Widescreen)": (9, 16),
    "16:9 (Widescreen)": (16, 9),
    "9:21 (Portrait Ultrawide)": (9, 21),
    "21:9 (Ultrawide)": (21, 9),
}
# Random options picking one of the listed aspect ratios.
RANDOM_LISTED = {
    "Random Any": list(ASPECT_RATIOS.values()),
    "Random Portrait": [ratio for ratio in ASPECT_RATIOS.values() if ratio[0] < ratio[1]],
    "Random Landscape": [ratio for ratio in ASPECT_RATIOS.values() if ratio[0] > ratio[1]],
}
# Random chaos options picking any aspect ratio up to max_aspect, with the allowed orientation.
RANDOM_CHAOS = {
    "Random Chaos Any": "any",
    "Random Chaos Portrait": "portrait",
    "Random Chaos Landscape": "landscape",
}
# Node schema (V3 / Nodes 2.0): aspect ratio and megapixel target like the core Resolution Selector, plus random aspect ratios. Multiple, batch and max_aspect are shown in the Advanced section.
class UnifiedSDXLResolution(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="UnifiedSDXLResolution",
            display_name="Resolution Selector (Random)",
            category="utils",
            description="Calculate width and height from an aspect ratio and a megapixel target, or pick a random aspect ratio from the seed.",
            inputs=[
                io.Combo.Input(
                    "aspect_ratio",
                    options=list(ASPECT_RATIOS) + list(RANDOM_LISTED) + list(RANDOM_CHAOS),
                    default="1:1 (Square)",
                    tooltip="Aspect ratio for the output dimensions. Random options pick one from the seed: listed ratios, or any ratio up to max_aspect for Chaos.",
                ),
                io.Float.Input(
                    "megapixels",
                    default=1.0,
                    min=0.1,
                    max=16.0,
                    step=0.1,
                    tooltip="Target total megapixels. 1.0 MP = 1024x1024 for square.",
                ),
                io.ResolutionPreview.Input(
                    "preview",
                    tooltip="Live preview of the calculated output resolution (not shown for random options).",
                ),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for random aspect ratio selection. Ignored for fixed aspect ratios.",
                ),
                io.Int.Input(
                    "multiple",
                    default=8,
                    min=8,
                    max=128,
                    step=4,
                    tooltip="Round width and height to the nearest multiple of this value (8 for the VAE, 64 for SDXL training buckets).",
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
                io.Float.Input(
                    "max_aspect",
                    default=2.0,
                    min=1.0,
                    max=4.0,
                    step=0.05,
                    tooltip="Random Chaos options only: the most stretched aspect ratio allowed (2.0 = up to 2:1 or 1:2).",
                    advanced=True,
                ),
            ],
            # Outputs for the node: width, height, and batch size.
            outputs=[
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
                io.Int.Output(display_name="batch"),
            ],
        )
    # Megapixel sizing method, same math as the core Resolution Selector so the frontend preview matches the output.
    @staticmethod
    def size_for_ratio(w_ratio, h_ratio, megapixels, multiple=8):
        scale = math.sqrt(megapixels * 1024 * 1024 / (w_ratio * h_ratio))
        return (
            max(multiple, round(w_ratio * scale / multiple) * multiple),
            max(multiple, round(h_ratio * scale / multiple) * multiple),
        )
    # Chaos-based random aspect ratio, uniform in log scale so wide and tall ratios are equally likely.
    @staticmethod
    def chaos_ratio(rng, max_aspect=2.0, orientation="any"):
        low = 0.0 if orientation == "landscape" else -math.log(max_aspect)
        high = 0.0 if orientation == "portrait" else math.log(max_aspect)
        return math.exp(rng.uniform(low, high)), 1.0
    # Main method to get the resolution based on the selected option, applying randomization as needed, and returning the final width, height, and batch size.
    @classmethod
    def execute(cls, aspect_ratio, megapixels=1.0, seed=0, multiple=8, batch=1, max_aspect=2.0, preview=None):
        rng = random.Random(seed) #Seed behavior for reproducibility of random selections.
        # Switching logic to determine the aspect ratio based on the selected option, handling listed random and chaos options appropriately.
        if aspect_ratio in RANDOM_LISTED:
            w_ratio, h_ratio = rng.choice(RANDOM_LISTED[aspect_ratio])#Returning a random aspect ratio from the list.
        elif aspect_ratio in RANDOM_CHAOS:
            w_ratio, h_ratio = cls.chaos_ratio(rng, max_aspect, RANDOM_CHAOS[aspect_ratio])#Returning any aspect ratio up to max_aspect for chaos options.
        else:
            w_ratio, h_ratio = ASPECT_RATIOS[aspect_ratio]#Returning the fixed aspect ratio for standard options.
        width, height = cls.size_for_ratio(w_ratio, h_ratio, megapixels, multiple)
        # Logging the final resolution, megapixels, seed, and batch size for debugging and verification purposes.
        print(
            f"[SDXL Resolution] Size: {width}x{height} ({width * height / (1024 * 1024):.2f} MP) | Aspect: {aspect_ratio} | Multiple: {multiple} | Seed: {seed} | Batch: {batch}"
        )
        return io.NodeOutput(width, height, batch)
# Extension entry point for ComfyUI V3 node registration.
class UnifiedSDXLResolutionExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [UnifiedSDXLResolution]
async def comfy_entrypoint():
    return UnifiedSDXLResolutionExtension()
