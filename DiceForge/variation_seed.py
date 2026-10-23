import logging
import torch
import comfy.patcher_extension
import comfy.sample
from comfy_api.latest import io
# Variation seeds, as in A1111 (subseed and variation strength): the same picture with small differences. The noise KSampler starts from (made from
# its seed) is blended with the noise of a second seed, the variation seed: at strength 0 the picture is the seed's own, at 0.1 the same composition
# with other details (folds, strands of hair, the background), at 1 the variation seed's own picture. The blend is spherical (slerp), so the noise
# keeps the size the model expects.
# It goes on the model, as a wrapper of the sampling: KSampler (or any sampler) then starts from the blended noise. On the model, not the latent,
# because flow models (Flux, Anima, Qwen...) don't read the latent at full denoise; this way it works for every model with the plain KSampler.
WRAPPER_KEY = "diceforge_variation"


def slerp(a, b, t):
    t = min(max(float(t), 0.0), 1.0)
    if t in (0.0, 1.0): # The ends exactly, without rounding.
        return b if t else a
    flat_a, flat_b = a.reshape(a.shape[0], -1).float(), b.reshape(b.shape[0], -1).float()
    unit_a = flat_a / flat_a.norm(dim=1, keepdim=True).clamp_min(1e-8)
    unit_b = flat_b / flat_b.norm(dim=1, keepdim=True).clamp_min(1e-8)
    omega = torch.acos((unit_a * unit_b).sum(dim=1).clamp(-1.0, 1.0))
    sin_omega = torch.sin(omega)
    linear = sin_omega.abs() < 1e-6 # (Nearly) the same direction: a straight blend.
    weight_a = torch.where(linear, torch.full_like(omega, 1 - t), torch.sin((1 - t) * omega) / sin_omega.clamp_min(1e-6))
    weight_b = torch.where(linear, torch.full_like(omega, t), torch.sin(t * omega) / sin_omega.clamp_min(1e-6))
    blended = weight_a[:, None] * flat_a + weight_b[:, None] * flat_b
    return blended.reshape(a.shape).to(a.dtype)
# The sampler's noise blended with the variation seed's noise of the same shape. No noise (add_noise disabled: all zeros) stays as it is.
def blend_noise(noise, variation_seed, strength):
    if strength <= 0 or not torch.is_tensor(noise) or getattr(noise, "is_nested", False) or not noise.any():
        return noise
    variation = comfy.sample.prepare_noise(noise, variation_seed).to(device=noise.device, dtype=noise.dtype)
    return slerp(noise, variation, strength)
# The model with the variation: a copy whose sampling starts from the blended noise (the model passed in stays as it is).
def with_variation(model, variation_seed, strength):
    if strength <= 0:
        return model
    def sample(executor, noise, *args, **kwargs):
        return executor(blend_noise(noise, variation_seed, strength), *args, **kwargs)
    patched = model.clone()
    patched.remove_wrappers_with_key(comfy.patcher_extension.WrappersMP.OUTER_SAMPLE, WRAPPER_KEY) # One variation at a time: the last node's.
    patched.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.OUTER_SAMPLE, WRAPPER_KEY, sample)
    return patched


class VariationSeed(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeVariationSeed",
            display_name="Variation Seed",
            category="DiceForge/sampling",
            description="Variations of a picture, as A1111's variation seed: the noise of KSampler's seed is blended with the noise of the variation seed. A low strength keeps the composition and changes details. Put it between the model and KSampler.",
            search_aliases=["variation seed", "subseed", "variation strength", "variations", "seed variation", "noise blend"],
            inputs=[
                io.Model.Input("model", tooltip="The model (after LoRAs). Connect the output to KSampler's model."),
                io.Int.Input("variation_seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True,
                             tooltip="The second seed. With control after generate on increment, every run is another variation of the same picture (KSampler's seed fixed)."),
                io.Float.Input("variation_strength", default=0.1, min=0.0, max=1.0, step=0.01,
                               tooltip="How much of the variation seed's noise: 0 is KSampler's seed's own picture, 0.05-0.15 the same composition with other details, 0.3 visibly different, 1 the variation seed's own picture."),
            ],
            outputs=[
                io.Model.Output(display_name="model", tooltip="The model whose sampling starts from the blended noise: connect it to KSampler."),
                io.String.Output(display_name="label", tooltip="For Dice Grid's label: the variation seed and strength."),
            ],
        )

    @classmethod
    def execute(cls, model, variation_seed=0, variation_strength=0.1):
        logging.info(f"[DiceForge] Variation Seed | variation seed {variation_seed} | strength {variation_strength:g}")
        return io.NodeOutput(with_variation(model, variation_seed, variation_strength), f"variation {variation_seed} @ {variation_strength:g}")
