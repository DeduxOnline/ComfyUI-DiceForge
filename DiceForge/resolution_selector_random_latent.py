import logging
import math
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .seed_modes import MEMORY, SEED_MODES, SEED_MODE_TOOLTIP, make_picker, pick_label, pick_in_range
from .sdxl_resolution_list_latent import describe_rescale, keep_orientation, rescale_input, rescale_settings, rescaled
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
# Node schema (V3 / Nodes 2.0): aspect ratio and megapixel target like the core Resolution Selector, plus random aspect ratios, outputting an empty latent of that size (like Empty Latent Image). Multiple, batch and max_aspect are shown in the Advanced section.
class ResolutionSelectorRandomLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ResolutionSelectorRandomLatent",
            display_name="Resolution Selector (Random, Latent)",
            category="DiceForge/latent",
            description="Calculate a size from an aspect ratio and a megapixel target (or a random aspect ratio from the seed) and output an empty latent of that size.",
            has_intermediate_output=True, # The size of the last run reaches the preview also when the node comes from the cache.
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
                io.Float.Input(
                    "max_aspect",
                    default=2.0,
                    min=1.0,
                    max=4.0,
                    step=0.05,
                    tooltip="Random Chaos options only: the most stretched aspect ratio allowed (2.0 = up to 2:1 or 1:2).",
                    advanced=True,
                ),
                io.Combo.Input(
                    "seed_mode",
                    options=SEED_MODES,
                    default="random",
                    tooltip=SEED_MODE_TOOLTIP,
                    advanced=True,
                ),
                rescale_input(optional=True), # Last, so workflows and prompts made before it keep working (it starts at by percentage 100).
            ],
            # Outputs for the node: the empty latent batch, its width and height in pixels, and the seed.
            outputs=[
                io.Latent.Output(display_name="latent", tooltip="Empty latent batch, the same as Empty Latent Image makes for this size."),
                io.Int.Output(display_name="width", tooltip="Width of the latent in pixels."),
                io.Int.Output(display_name="height", tooltip="Height of the latent in pixels."),
                io.Int.Output(display_name="seed", tooltip="The seed used for this run, for example to pass on to KSampler."),
            ],
        )
    # Megapixel sizing, the same math as the core Resolution Selector (so 100% gives the same size), with the rescale applied to the exact size
    # before each side is rounded to multiple.
    @staticmethod
    def size_for_ratio(w_ratio, h_ratio, megapixels, multiple=8, round_down=False, rescale=None):
        scale = math.sqrt(megapixels * 1024 * 1024 / (w_ratio * h_ratio))
        width, height = rescaled(w_ratio * scale, h_ratio * scale, rescale)
        snap = math.floor if round_down else round # Random Chaos rounds down from the exact size, so it never exceeds its (rescaled) megapixels.
        return (
            max(multiple, snap(width / multiple) * multiple),
            max(multiple, snap(height / multiple) * multiple),
        )
    # Chaos-based random aspect ratio, uniform in log scale so wide and tall ratios are equally likely. Seed modes other than random take turns between
    # 8 equal parts of the range (4 for one orientation).
    @staticmethod
    def chaos_ratio(picker, seed, max_aspect=2.0, orientation="any"):
        low = 0.0 if orientation == "landscape" else -math.log(max_aspect)
        high = 0.0 if orientation == "portrait" else math.log(max_aspect)
        return math.exp(pick_in_range(low, high, 8 if orientation == "any" else 4, picker, seed, f"Chaos {orientation} {max_aspect}")), 1.0
    # Main method to get the resolution based on the selected option, applying randomization as needed, then building the empty latent with Empty Latent Image.
    @classmethod
    def execute(cls, aspect_ratio, megapixels=1.0, seed=0, multiple=8, batch=1, max_aspect=2.0, seed_mode="random", preview=None, rescale=None):
        picker = make_picker(seed_mode, seed) # How random picks follow the seed (random: reproducible, same picks as before seed modes existed).
        # Switching logic to determine the aspect ratio based on the selected option, handling listed random and chaos options appropriately.
        if aspect_ratio in RANDOM_LISTED:
            w_ratio, h_ratio = ASPECT_RATIOS[pick_label([name for name, ratio in ASPECT_RATIOS.items() if ratio in RANDOM_LISTED[aspect_ratio]], picker, seed)]#Returning a random aspect ratio from the list.
        elif aspect_ratio in RANDOM_CHAOS:
            w_ratio, h_ratio = cls.chaos_ratio(picker, seed, max_aspect, RANDOM_CHAOS[aspect_ratio])#Returning any aspect ratio up to max_aspect for chaos options.
        else:
            w_ratio, h_ratio = ASPECT_RATIOS[aspect_ratio]#Returning the fixed aspect ratio for standard options.
        chaos = aspect_ratio in RANDOM_CHAOS
        width, height = cls.size_for_ratio(w_ratio, h_ratio, megapixels, multiple, round_down=chaos, rescale=rescale)
        if chaos and max_aspect > 1.0:
            width, height = keep_orientation(width, height, RANDOM_CHAOS[aspect_ratio], multiple, rescale) # Portrait and Landscape stay non-square.
        MEMORY.save()
        # Logging the final resolution, megapixels, rescale, seed, and batch size for debugging and verification purposes.
        logging.info(
            f"[DiceForge] Resolution Selector (Random, Latent) | Size: {width}x{height} ({width * height / (1024 * 1024):.2f} MP) | Aspect: {aspect_ratio} | Rescale: {describe_rescale(rescale)} | Multiple: {multiple} | Seed: {seed} ({seed_mode}) | Batch: {batch}"
        )
        latent = nodes.EmptyLatentImage().generate(width, height, batch)[0]
        # The size of this run, with the settings it came from, for the preview of random options in the frontend extension.
        last_size = {"width": width, "height": height, "aspect_ratio": aspect_ratio, "megapixels": megapixels, "multiple": multiple, "max_aspect": max_aspect,
                     **rescale_settings(rescale)}
        return io.NodeOutput(latent, width, height, seed, ui={"dice_forge_last_size": [last_size]})
# Extension entry point for ComfyUI V3 node registration.
class ResolutionSelectorRandomLatentExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [ResolutionSelectorRandomLatent]
async def comfy_entrypoint():
    return ResolutionSelectorRandomLatentExtension()
