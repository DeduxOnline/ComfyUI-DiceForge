import logging
import math
import nodes
from comfy_api.latest import io
from .seed_modes import MEMORY, SEED_MODES, SEED_MODE_TOOLTIP, make_picker, pick_label
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
# Node schema (V3 / Nodes 2.0): aspect ratio and megapixel target like the core Resolution Selector, plus random aspect ratios, outputting an empty latent of that size (like Empty Latent Image). Multiple and batch are shown in the Advanced section.
class ResolutionSelectorRandomLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeResolutionSelector",
            display_name="Resolution Selector (Random)",
            category="DiceForge/latent",
            description="Calculate a size from an aspect ratio and a megapixel target (or a random aspect ratio from the seed) and output an empty latent of that size.",
            has_intermediate_output=True, # The size of the last run reaches the preview also when the node comes from the cache.
            inputs=[
                io.Combo.Input(
                    "aspect_ratio",
                    options=list(ASPECT_RATIOS) + list(RANDOM_LISTED),
                    default="1:1 (Square)",
                    tooltip="Aspect ratio for the output dimensions. Random options pick one from the seed.",
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
                    tooltip="Live preview of the calculated output resolution. Random options show the size of the last run, until the settings change.",
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
                    max=256,
                    step=8,
                    tooltip="Round width and height to a multiple of this value (8 for the VAE, 64 for SDXL training buckets).",
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
    # Megapixel sizing, the same math as the core Resolution Selector, before each side is rounded to multiple.
    @staticmethod
    def size_for_ratio(w_ratio, h_ratio, megapixels, multiple=8, round_down=False):
        scale = math.sqrt(megapixels * 1024 * 1024 / (w_ratio * h_ratio))
        width, height = w_ratio * scale, h_ratio * scale
        snap = math.floor if round_down else round
        return (
            max(multiple, snap(width / multiple) * multiple),
            max(multiple, snap(height / multiple) * multiple),
        )
    # Main method to get the resolution based on the selected option, applying randomization as needed, then building the empty latent with Empty Latent Image.
    @classmethod
    def execute(cls, aspect_ratio, megapixels=1.0, seed=0, multiple=8, batch=1, seed_mode="random", preview=None):
        picker = make_picker(seed_mode, seed) # How random picks follow the seed (random: reproducible, same picks as before seed modes existed).
        # Switching logic to determine the aspect ratio based on the selected option, handling listed random and chaos options appropriately.
        if aspect_ratio in RANDOM_LISTED:
            w_ratio, h_ratio = ASPECT_RATIOS[pick_label([name for name, ratio in ASPECT_RATIOS.items() if ratio in RANDOM_LISTED[aspect_ratio]], picker, seed)]#Returning a random aspect ratio from the list.
        else:
            w_ratio, h_ratio = ASPECT_RATIOS[aspect_ratio]#Returning the fixed aspect ratio for standard options.
        width, height = cls.size_for_ratio(w_ratio, h_ratio, megapixels, multiple)
        MEMORY.save()
        logging.info(
            f"[DiceForge] Resolution Selector (Random, Latent) | Size: {width}x{height} ({width * height / (1024 * 1024):.2f} MP) | Aspect: {aspect_ratio} | Multiple: {multiple} | Seed: {seed} ({seed_mode}) | Batch: {batch}"
        )
        latent = nodes.EmptyLatentImage().generate(width, height, batch)[0]
        # The size of this run, with the settings it came from, for the preview of random options in the frontend extension.
        last_size = {"width": width, "height": height, "aspect_ratio": aspect_ratio, "megapixels": megapixels, "multiple": multiple,
                     }
        return io.NodeOutput(latent, width, height, seed, ui={"dice_forge_last_size": [last_size]})
