import functools
import logging
import torch
import comfy.ldm.cosmos.predict2
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
# Normalized Attention Guidance (NAG, arxiv.org/abs/2505.21179) for Anima: the negative prompt also steers every cross-attention, so it works at
# CFG 1 (Turbo LoRAs, distilled models), where the negative prompt otherwise does nothing, and adds to it at a higher CFG.
# ComfyUI's own NAG node patches the self-attention output, a hook Anima's attention doesn't call. Here each block's cross-attention runs once more
# for the positive rows of the batch, with the negative prompt as the text and the same queries, as NAG does for models with a cross-attention
# (Wan). The negative is the one in the same batch for CFG, already through Anima's LLM adapter, so no second text encoding and no extra model pass:
# only one more cross-attention per block. The forwards are object patches of the model patcher, which puts the originals back after sampling.


# The NAG blend of an attention output with the positive text and with the negative one: extrapolate away from the negative, cap the growth of
# the L1 norm at tau times the positive's, then mix with the positive by alpha.
def nag(z_pos, z_neg, scale, tau, alpha):
    guided = z_pos * scale - z_neg * (scale - 1.0)
    norm_pos = torch.norm(z_pos, p=1, dim=-1, keepdim=True).clamp_min(1e-6)
    norm_guided = torch.norm(guided, p=1, dim=-1, keepdim=True).clamp_min(1e-6)
    ratio = norm_guided / norm_pos
    guided = guided * (torch.minimum(ratio, torch.full_like(ratio, tau)) / ratio)
    return guided * alpha + z_pos * (1.0 - alpha)
# A cross-attention forward with NAG on the positive rows. ComfyUI batches the conditions in the order of transformer_options["cond_or_uncond"]
# (0 positive, 1 negative), each with the same number of rows; a step that runs them in separate batches (VRAM too low) has no negative here.
def nag_cross_attention(forward, scale, tau, alpha):
    def cross_attention(x, context=None, rope_emb=None, transformer_options={}):
        out = forward(x, context, rope_emb=rope_emb, transformer_options=transformer_options)
        kinds = transformer_options.get("cond_or_uncond") or []
        if 0 not in kinds or 1 not in kinds:
            return out
        size = x.shape[0] // len(kinds)
        negative = kinds.index(1) * size
        for index, kind in enumerate(kinds):
            if kind == 0:
                rows = slice(index * size, (index + 1) * size)
                z_neg = forward(x[rows], context[negative:negative + size], rope_emb=rope_emb, transformer_options=transformer_options)
                out[rows] = nag(out[rows], z_neg, scale, tau, alpha)
        return out
    return cross_attention
# The model with NAG: a copy whose cross-attentions are patched (the model passed in stays as it is). Scale 1 or alpha 0 changes nothing.
def with_nag(model, scale, tau, alpha):
    diffusion = model.get_model_object("diffusion_model")
    if not isinstance(diffusion, comfy.ldm.cosmos.predict2.MiniTrainDIT):
        raise ValueError(f"Anima NAG works with Anima models, not with {type(diffusion).__name__}: connect the model of an Anima loader.")
    if scale == 1 or alpha == 0:
        return model
    patched = model.clone()
    for index, block in enumerate(diffusion.blocks):
        # The class's own forward: ComfyUI keeps the last model it ran loaded with its patches, so the module may still carry an earlier NAG's.
        original = functools.partial(type(block.cross_attn).forward, block.cross_attn)
        patched.add_object_patch(f"diffusion_model.blocks.{index}.cross_attn.forward", nag_cross_attention(original, scale, tau, alpha))
    patched.disable_model_cfg1_optimization() # At CFG 1 ComfyUI skips the negative prompt; NAG needs it in the batch.
    return patched


class AnimaNAG(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeAnimaNAG",
            display_name="Anima NAG",
            category="DiceForge/sampling",
            description="Normalized Attention Guidance for Anima: the negative prompt also steers every cross-attention. It makes the negative prompt work at CFG 1 (Turbo LoRAs), and strengthens it at a higher CFG. Put it between the model and KSampler.",
            search_aliases=["nag", "normalized attention guidance", "negative prompt", "negative guidance", "anima", "turbo", "cfg 1"],
            inputs=[
                io.Model.Input("model", tooltip="An Anima model (after LoRAs). Connect the output to KSampler's model."),
                io.Float.Input("nag_scale", default=5.0, min=1.0, max=50.0, step=0.1,
                               tooltip="How far from the negative prompt: 1 is off, about 3-7 a clear push, higher ones can burn the picture."),
                io.Float.Input("nag_alpha", default=0.5, min=0.0, max=1.0, step=0.01,
                               tooltip="How much of the guided attention goes in: 0 is off, 1 all of it."),
                io.Float.Input("nag_tau", default=1.5, min=1.0, max=10.0, step=0.01,
                               tooltip="The most the guidance may grow the attention's size (L1 norm), as a multiple of the positive's: keeps a high scale from burning the picture.", advanced=True),
            ],
            outputs=[
                io.Model.Output(display_name="model", tooltip="The model with NAG: connect it to KSampler. The negative prompt is KSampler's negative."),
            ],
        )

    @classmethod
    def execute(cls, model, nag_scale=5.0, nag_alpha=0.5, nag_tau=1.5):
        logging.info(f"[DiceForge] Anima NAG | scale {nag_scale:g} | alpha {nag_alpha:g} | tau {nag_tau:g}")
        return io.NodeOutput(with_nag(model, nag_scale, nag_tau, nag_alpha))


class AnimaNAGExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [AnimaNAG]
async def comfy_entrypoint():
    return AnimaNAGExtension()
