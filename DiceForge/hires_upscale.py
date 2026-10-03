import logging
import comfy.utils
import folder_paths
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .load_vae_decode_save import FILENAME_PREFIX_TOOLTIP, LoadVAEDecodeSave, check_image_output, show_or_save, vae_output
from .sdxl_resolution_list_latent import BY_PERCENTAGE, TO_LONGEST_SIDE, TO_WIDTH_HEIGHT, rescaled
# HiresFix (Load VAE), like Easy-Use's HiresFix but with the VAE picked from a list instead of a vae input: the image made bigger with an upscale
# model (ESRGAN, 4x-UltraSharp, AnimeSharp...), then rescaled (by percentage of the upscaled image, to a width and/or height, or to a longest side),
# shown or saved, and encoded with the VAE into the latent for a second KSampler pass (denoise 0.3-0.5).
NO_MODEL = "None"
RESCALE_METHODS = ["nearest-exact", "bilinear", "area", "bicubic", "lanczos"]
_model_cache = {"name": None, "model": None} # The last upscale model, kept between runs like the VAE.


def upscale_models():
    return [NO_MODEL, *folder_paths.get_filename_list("upscale_models")]
def load_upscale_model(name):
    if _model_cache["name"] != name:
        from comfy_extras.nodes_upscale_model import UpscaleModelLoader
        _model_cache.update(name=None, model=None) # Release the previous one first; a failed load then retries on the next run.
        _model_cache.update(name=name, model=UpscaleModelLoader.execute(name).result[0])
    return _model_cache["model"]
def upscale_with_model(model, images):
    from comfy_extras.nodes_upscale_model import ImageUpscaleWithModel
    return ImageUpscaleWithModel.execute(model, images).result[0]
def round_to(value, multiple=8):
    return max(multiple, int(round(value / multiple)) * multiple)
# The rescale of the upscaled image: the same modes as the resolution nodes, here with 50% by default (a 4x model at 50%: twice the size).
def rescale_input():
    return io.DynamicCombo.Input(
        "rescale",
        options=[
            io.DynamicCombo.Option(BY_PERCENTAGE, [io.Int.Input("percent", default=50, min=5, max=1000, step=5,
                tooltip="Each side in percent of the image after the upscale model (of the image as it came without one): a 4x model at 50% gives twice the size.")]),
            io.DynamicCombo.Option(TO_WIDTH_HEIGHT, [
                io.Int.Input("width", default=1536, min=0, max=16384, step=8, tooltip="The width. 0: follows the aspect ratio from the height."),
                io.Int.Input("height", default=0, min=0, max=16384, step=8, tooltip="The height. 0: follows the aspect ratio from the width. Both set: that exact size (crop decides what happens to a different aspect ratio)."),
            ]),
            io.DynamicCombo.Option(TO_LONGEST_SIDE, [io.Int.Input("longer_side", default=2048, min=64, max=16384, step=8,
                tooltip="The longest side, keeping the aspect ratio.")]),
        ],
        tooltip="The size after the upscale model: by percentage, to a width and/or height, or to a longest side. Rounded to multiples of 8 for the latent.",
    )


class HiresUpscale(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        models = upscale_models()
        return io.Schema(
            node_id="DiceForgeHiresUpscale",
            display_name="HiresFix (Load VAE)",
            category="DiceForge/image",
            description="As Easy-Use's HiresFix, with the VAE from a list: the image made bigger with an upscale model, rescaled, shown or saved, and encoded into a latent for a second KSampler pass.",
            search_aliases=["hiresfix", "hires fix", "upscale", "upscale model", "esrgan", "image upscale", "load vae", "vae encode"],
            is_output_node=True,
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            inputs=[
                io.Image.Input("image", tooltip="The image of the first pass (VAE Decode, or VAE Decode + Save's images)."),
                io.Combo.Input("model_name", options=models, default=models[1] if len(models) > 1 else NO_MODEL,
                               tooltip="The upscale model (models/upscale_models: ESRGAN, 4x-UltraSharp, AnimeSharp...). None: only rescaled."),
                io.Boolean.Input("rescale_after_model", default=True, tooltip="Rescale the upscaled image (below). Off: keep the upscale model's size (4x for a 4x model)."),
                io.Combo.Input("rescale_method", options=RESCALE_METHODS, default="lanczos", tooltip="How the image is resized after the model."),
                rescale_input(),
                io.Combo.Input("crop", options=["disabled", "center"], default="disabled", tooltip="With an exact width and height of another aspect ratio: disabled stretches, center crops."),
                io.Combo.Input("vae_name", options=nodes.VAELoader.vae_list(nodes.VAELoader), tooltip="The VAE that encodes the image into the latent. Same list as Load VAE."),
                io.Combo.Input("image_output", options=["Hide", "Preview", "Save", "Hide&Save"], default="Preview",
                               tooltip="Hide: only pass the image on. Preview: show it on the node. Save: save and show it, like Save Image. Hide&Save: save without showing."),
                io.String.Input("filename_prefix", default="DiceForge/hires", tooltip=FILENAME_PREFIX_TOOLTIP, advanced=True),
            ],
            outputs=[
                io.Image.Output(display_name="image", tooltip="The upscaled and rescaled image."),
                io.Latent.Output(display_name="latent", tooltip="The image encoded with the VAE: for a second KSampler pass (denoise 0.3-0.5)."),
                vae_output(),
            ],
        )

    @classmethod
    def execute(cls, image, model_name=NO_MODEL, rescale_after_model=True, rescale_method="lanczos", rescale=None, crop="disabled", vae_name=None,
                image_output="Preview", filename_prefix="DiceForge/hires"):
        check_image_output(image_output, "HiresFix (Load VAE)") # Before any work: a wrong value costs nothing.
        if rescale_method not in RESCALE_METHODS:
            raise ValueError(f"HiresFix (Load VAE): unknown rescale_method {rescale_method!r} (one of {', '.join(RESCALE_METHODS)}).")
        height, width = image.shape[1], image.shape[2]
        images = image[..., :3]
        if model_name != NO_MODEL:
            images = upscale_with_model(load_upscale_model(model_name), images)
        model_height, model_width = images.shape[1], images.shape[2]
        if rescale_after_model or model_name == NO_MODEL:
            new_width, new_height = (round_to(side) for side in rescaled(model_width, model_height, rescale or {"rescale": BY_PERCENTAGE, "percent": 50}))
        else:
            new_width, new_height = round_to(model_width), round_to(model_height) # The model's size, on the latent's grid.
        if (new_width, new_height) != (model_width, model_height):
            images = comfy.utils.common_upscale(images.movedim(-1, 1), new_width, new_height, rescale_method, crop).movedim(1, -1)
        vae = LoadVAEDecodeSave.load_vae(vae_name)
        latent = nodes.VAEEncode().encode(vae, images)[0]
        logging.info(f"[DiceForge] HiresFix (Load VAE) | {width}x{height} -> {model_name} {model_width}x{model_height} -> {new_width}x{new_height} ({rescale_method}) | VAE: {vae_name}")
        return io.NodeOutput(images, latent, vae, ui=show_or_save(cls, images, filename_prefix, image_output))


class HiresUpscaleExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [HiresUpscale]
async def comfy_entrypoint():
    return HiresUpscaleExtension()
