# Anima NAG (DiceForge/anima_nag.py): the NAG blend, the cross-attention that guides the positive rows of a batch away from the negative, and the
# node's model patches. The attention modules are Anima's own (comfy.ldm.cosmos.predict2.Attention), with small random weights.
import functools
import torch
import comfy.ldm.cosmos.predict2 as predict2
import comfy.model_patcher
import comfy.ops
import comfy.utils
import pytest
from DiceForge.anima_nag import AnimaNAG, nag, nag_cross_attention, with_nag


def attention(seed=0):
    torch.manual_seed(seed)
    module = predict2.Attention(32, 16, n_heads=4, head_dim=8, operations=comfy.ops.disable_weight_init)
    for parameter in module.parameters():
        torch.nn.init.normal_(parameter, std=0.2)
    return module.eval()


def batch(rows=2, seed=1):
    generator = torch.Generator().manual_seed(seed)
    return torch.randn(rows, 10, 32, generator=generator), torch.randn(rows, 6, 16, generator=generator)


def test_the_blend_is_off_at_scale_1_or_alpha_0_and_caps_the_norm():
    z_pos, z_neg = torch.randn(2, 5, 8), torch.randn(2, 5, 8)
    assert torch.allclose(nag(z_pos, z_neg, 1.0, 1.5, 0.5), z_pos)
    assert torch.allclose(nag(z_pos, z_neg, 5.0, 1.5, 0.0), z_pos)
    guided = nag(z_pos, z_neg, 20.0, 1.5, 1.0) # All of the guided attention: its L1 norm at most tau times the positive's.
    ratio = guided.abs().sum(-1) / z_pos.abs().sum(-1)
    assert (ratio <= 1.5 + 1e-4).all()
    toward = nag(z_pos, z_neg, 3.0, 10.0, 1.0) # No cap reached: a plain step away from the negative.
    assert torch.allclose(toward, z_pos * 3.0 - z_neg * 2.0, atol=1e-5)


def test_the_positive_rows_are_guided_with_the_negative_text_and_the_rest_stays():
    module = attention()
    forward = functools.partial(predict2.Attention.forward, module)
    patched = nag_cross_attention(forward, 5.0, 1.5, 0.5)
    x, context = batch()
    plain = forward(x, context)
    for kinds in ([1, 0], [0, 1]): # ComfyUI puts the negative first or second.
        out = patched(x.clone(), context, transformer_options={"cond_or_uncond": kinds})
        pos, neg = kinds.index(0), kinds.index(1)
        z_neg = forward(x[pos:pos + 1], context[neg:neg + 1]) # The positive's queries with the negative's text.
        assert torch.allclose(out[pos], nag(plain[pos:pos + 1], z_neg, 5.0, 1.5, 0.5)[0], atol=1e-5)
        assert torch.equal(out[neg], plain[neg])
        assert not torch.allclose(out[pos], plain[pos])
    for options in ({}, {"cond_or_uncond": [0, 0]}, {"cond_or_uncond": [1]}): # No negative in this batch: nothing to guide.
        assert torch.equal(patched(x, context, transformer_options=options), plain)


def test_every_positive_part_of_the_batch_is_guided():
    module = attention()
    forward = functools.partial(predict2.Attention.forward, module)
    x, context = batch(rows=6) # Three conditions of two rows each: positive, negative, positive (an area prompt, for one).
    out = nag_cross_attention(forward, 4.0, 2.0, 1.0)(x.clone(), context, transformer_options={"cond_or_uncond": [0, 1, 0]})
    plain = forward(x, context)
    for rows in (slice(0, 2), slice(4, 6)):
        assert torch.allclose(out[rows], nag(plain[rows], forward(x[rows], context[2:4]), 4.0, 2.0, 1.0), atol=1e-5)
    assert torch.equal(out[2:4], plain[2:4])


class Holder(torch.nn.Module):
    def __init__(self, diffusion_model):
        super().__init__()
        self.diffusion_model = diffusion_model


def anima(blocks=3):
    # An Anima DiT (Anima subclasses MiniTrainDIT) cut down to what the node reads: its blocks' cross-attentions.
    diffusion = predict2.MiniTrainDIT.__new__(predict2.MiniTrainDIT)
    torch.nn.Module.__init__(diffusion)
    diffusion.blocks = torch.nn.ModuleList()
    for index in range(blocks):
        block = torch.nn.Module()
        block.cross_attn = attention(index)
        diffusion.blocks.append(block)
    return comfy.model_patcher.ModelPatcher(Holder(diffusion), load_device=torch.device("cpu"), offload_device=torch.device("cpu"))


def test_the_node_patches_every_cross_attention_of_a_copy():
    original = anima()
    patched = AnimaNAG.execute(original, nag_scale=5.0, nag_alpha=0.5, nag_tau=1.5).result[0]
    assert patched is not original and not original.object_patches and "disable_cfg1_optimization" not in original.model_options
    assert sorted(patched.object_patches) == [f"diffusion_model.blocks.{index}.cross_attn.forward" for index in range(3)]
    assert patched.model_options["disable_cfg1_optimization"] # At CFG 1 the negative must still be in the batch.
    assert with_nag(original, 1.0, 1.5, 0.5) is original and with_nag(original, 5.0, 1.5, 0.0) is original


def test_the_patch_wraps_the_class_forward_not_one_left_on_the_module():
    model = anima(blocks=1)
    module = model.model.diffusion_model.blocks[0].cross_attn
    x, context = batch()
    plain = predict2.Attention.forward(module, x, context)
    module.forward = lambda *args, **kwargs: pytest.fail("an earlier patch's forward was called") # As ComfyUI leaves the last model it ran.
    patched = with_nag(model, 5.0, 1.5, 0.5)
    name = "diffusion_model.blocks.0.cross_attn.forward"
    backup = comfy.utils.set_attr(patched.model, name, patched.object_patches[name]) # What the model patcher does when it loads the copy.
    try:
        out = module(x.clone(), context, transformer_options={"cond_or_uncond": [1, 0]})
    finally:
        comfy.utils.set_attr(patched.model, name, backup)
    assert torch.equal(out[0], plain[0]) and not torch.allclose(out[1], plain[1])


def test_a_model_other_than_anima_is_a_clear_error():
    sdxl_like = comfy.model_patcher.ModelPatcher(Holder(torch.nn.Linear(2, 2)), load_device=torch.device("cpu"), offload_device=torch.device("cpu"))
    with pytest.raises(ValueError, match="Anima NAG works with Anima models, not with Linear"):
        AnimaNAG.execute(sdxl_like)
