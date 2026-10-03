import logging
import comfy.samplers
import comfy.utils
import nodes
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
# Hires Fix in one node: the latent of the first pass made bigger, then sampled again at low denoise, so the bigger image gets new detail instead of
# blur. Bigger by a factor, or to an exact size (connect width and height of a second SDXL Resolution List or Resolution Selector with rescale);
# in the latent (fast), or in pixels with an upscale model (ESRGAN and the like: sharper) when a VAE and an upscale model are connected.
UPSCALE_METHODS = ["nearest-exact", "bilinear", "area", "bicubic", "bislerp"]
MAX_SIDE = 16384


def round_to(value, multiple=8):
    return max(multiple, int(round(value / multiple)) * multiple)
# The size of the second pass, in pixels: width and height as given (one of them: the other follows the aspect ratio), else the first pass's size
# times upscale_by. Rounded to multiples of 8, as latents need.
def target_size(width, height, upscale_by, target_width=0, target_height=0):
    if target_width and target_height:
        size = (target_width, target_height)
    elif target_width:
        size = (target_width, height * target_width / width)
    elif target_height:
        size = (width * target_height / height, target_height)
    else:
        size = (width * upscale_by, height * upscale_by)
    return tuple(min(round_to(side), MAX_SIDE) for side in size)


class HiresFix(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        samplers, schedulers = comfy.samplers.KSampler.SAMPLERS, comfy.samplers.KSampler.SCHEDULERS
        return io.Schema(
            node_id="DiceForgeHiresFix",
            display_name="Hires Fix",
            category="DiceForge/sampling",
            description="Makes the first pass's latent bigger (by a factor or to a size; in the latent, or in pixels with an upscale model) and samples it again at low denoise, for a bigger image with new detail.",
            search_aliases=["hires fix", "highres fix", "hires", "upscale", "second pass", "latent upscale", "img2img upscale"],
            inputs=[
                io.Model.Input("model", tooltip="The model, as for the first KSampler."),
                io.Conditioning.Input("positive", tooltip="The positive conditioning, as for the first KSampler."),
                io.Conditioning.Input("negative", tooltip="The negative conditioning, as for the first KSampler."),
                io.Latent.Input("samples", tooltip="The latent from the first KSampler."),
                io.Float.Input("upscale_by", default=1.5, min=1.0, max=4.0, step=0.05, tooltip="How much bigger, each side (1.5: 1024x1024 becomes 1536x1536). Not used when width or height is set."),
                io.Int.Input("width", default=0, min=0, max=MAX_SIDE, step=8, tooltip="The size of the second pass instead of upscale_by (0: not set). Connect width of an SDXL Resolution List with rescale. Only one of the two: the other follows the aspect ratio."),
                io.Int.Input("height", default=0, min=0, max=MAX_SIDE, step=8, tooltip="The height of the second pass (0: not set)."),
                io.Combo.Input("upscale_method", options=UPSCALE_METHODS, default="bislerp", tooltip="How the latent is made bigger (or the pixels resized after an upscale model)."),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True, tooltip="Seed of the second pass (connect the first one's for the same noise)."),
                io.Int.Input("steps", default=15, min=1, max=10000, tooltip="Steps of the second pass."),
                io.Float.Input("cfg", default=6.0, min=0.0, max=100.0, step=0.1, round=0.01, tooltip="CFG of the second pass."),
                io.Combo.Input("sampler_name", options=list(samplers), default="euler_ancestral" if "euler_ancestral" in samplers else samplers[0], tooltip="Sampler of the second pass."),
                io.Combo.Input("scheduler", options=list(schedulers), default="normal" if "normal" in schedulers else schedulers[0], tooltip="Scheduler of the second pass."),
                io.Float.Input("denoise", default=0.45, min=0.0, max=1.0, step=0.01, tooltip="How much the second pass changes: 0.3-0.5 adds detail and keeps the picture; higher changes more. Latent upscales need about 0.5 or more (less leaves them blurry)."),
                io.Vae.Input("vae", optional=True, tooltip="With upscale_model: the VAE to go to pixels and back. Alone: only for the image output."),
                io.UpscaleModel.Input("upscale_model", optional=True, tooltip="An upscale model (Load Upscale Model: ESRGAN, 4x-UltraSharp...): the image is made bigger in pixels with it, then resized to the size of the second pass. Needs vae."),
            ],
            outputs=[
                io.Latent.Output(display_name="latent", tooltip="The latent of the second pass, for VAE Decode (+ Save)."),
                io.Image.Output(display_name="image", tooltip="The second pass decoded, when vae is connected (else nothing: use VAE Decode)."),
                io.Int.Output(display_name="width", tooltip="The width of the second pass in pixels."),
                io.Int.Output(display_name="height", tooltip="The height of the second pass in pixels."),
            ],
        )

    @classmethod
    def execute(cls, model, positive, negative, samples, upscale_by=1.5, width=0, height=0, upscale_method="bislerp", seed=0, steps=15, cfg=6.0,
                sampler_name="euler_ancestral", scheduler="normal", denoise=0.45, vae=None, upscale_model=None):
        if upscale_model is not None and vae is None:
            raise ValueError("Hires Fix: an upscale model works in pixels: connect the vae too (or leave upscale_model empty for a latent upscale).")
        ratio = samples.get("downscale_ratio_spacial") or 8
        first_width, first_height = samples["samples"].shape[-1] * ratio, samples["samples"].shape[-2] * ratio
        new_width, new_height = target_size(first_width, first_height, upscale_by, width, height)
        if upscale_model is not None:
            from comfy_extras.nodes_upscale_model import ImageUpscaleWithModel
            image = nodes.VAEDecode().decode(vae, samples)[0]
            image = image.reshape(-1, *image.shape[-3:]) # A video VAE gives frames: one batch of images.
            image = ImageUpscaleWithModel.execute(upscale_model, image).result[0]
            image = comfy.utils.common_upscale(image.movedim(-1, 1), new_width, new_height, upscale_method if upscale_method != "bislerp" else "bicubic", "disabled").movedim(1, -1)
            bigger = nodes.VAEEncode().encode(vae, image[..., :3])[0]
            how = f"upscale model, then {new_width}x{new_height}"
        else:
            bigger = nodes.LatentUpscale().upscale(samples, upscale_method, new_width, new_height, "disabled")[0]
            how = f"latent {upscale_method}"
        logging.info(f"[DiceForge] Hires Fix | {first_width}x{first_height} -> {new_width}x{new_height} ({how}) | {steps} steps, CFG {cfg}, {sampler_name} / {scheduler}, denoise {denoise} | Seed: {seed}")
        result = nodes.common_ksampler(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, bigger, denoise=denoise)[0]
        image = nodes.VAEDecode().decode(vae, result)[0] if vae is not None else None
        return io.NodeOutput(result, image, new_width, new_height)


class HiresFixExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [HiresFix]
async def comfy_entrypoint():
    return HiresFixExtension()
