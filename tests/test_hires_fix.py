# Hires Fix (DiceForge/hires_fix.py): the size of the second pass, the latent upscale, the upscale model path and the second sampler pass.
import nodes
import pytest
import torch
from DiceForge import hires_fix
from DiceForge.hires_fix import HiresFix, target_size


@pytest.mark.parametrize("given, expected", [
    ((1024, 1024, 1.5), (1536, 1536)), ((832, 1216, 1.5), (1248, 1824)), ((1024, 1024, 1.5, 2048, 0), (2048, 2048)), ((832, 1216, 2.0, 0, 1824), (1248, 1824)),
    ((1024, 768, 1.0, 1920, 1080), (1920, 1080)), ((1000, 1000, 1.33), (1328, 1328)), ((8000, 8000, 4.0), (16384, 16384)),
])
def test_target_size(given, expected):
    assert target_size(*given) == expected


@pytest.fixture
def stand_ins(monkeypatch):
    """Stand-ins for the core nodes: what they were asked, and plain results."""
    calls = []
    def upscale(self, samples, method, width, height, crop):
        calls.append(("latent", method, width, height))
        return ({"samples": torch.zeros(1, 4, height // 8, width // 8)},)
    def sample(model, seed, steps, cfg, sampler, scheduler, positive, negative, latent, denoise=1.0):
        calls.append(("sample", seed, steps, cfg, sampler, scheduler, tuple(latent["samples"].shape), denoise))
        return ({"samples": latent["samples"] + 1},)
    monkeypatch.setattr(nodes.LatentUpscale, "upscale", upscale)
    monkeypatch.setattr(nodes, "common_ksampler", sample)
    monkeypatch.setattr(nodes.VAEDecode, "decode", lambda self, vae, samples: (calls.append(("decode",)) or torch.zeros(1, samples["samples"].shape[-2] * 8, samples["samples"].shape[-1] * 8, 3),))
    monkeypatch.setattr(nodes.VAEEncode, "encode", lambda self, vae, image: (calls.append(("encode", tuple(image.shape))) or {"samples": torch.zeros(1, 4, image.shape[1] // 8, image.shape[2] // 8)},))
    return calls


def latent(width=1024, height=768):
    return {"samples": torch.zeros(1, 4, height // 8, width // 8)}


def test_latent_upscale_then_a_second_pass(stand_ins):
    result, image, width, height = HiresFix.execute("model", "pos", "neg", latent(), upscale_by=1.5, seed=7, steps=12, cfg=5.0, sampler_name="euler",
                                                     scheduler="karras", denoise=0.5).result
    assert (width, height, image) == (1536, 1152, None) # No vae: no image.
    assert stand_ins == [("latent", "bislerp", 1536, 1152), ("sample", 7, 12, 5.0, "euler", "karras", (1, 4, 144, 192), 0.5)]
    assert result["samples"].shape == (1, 4, 144, 192)


def test_exact_size_and_decoded_image(stand_ins):
    result, image, width, height = HiresFix.execute("model", "pos", "neg", latent(832, 1216), width=1248, height=1824, vae="vae").result
    assert (width, height) == (1248, 1824) and image.shape == (1, 1824, 1248, 3)


def test_upscale_model_works_in_pixels(stand_ins, monkeypatch):
    from comfy_extras import nodes_upscale_model
    class Upscaled:
        def __init__(self, image):
            self.result = (torch.zeros(image.shape[0], image.shape[1] * 4, image.shape[2] * 4, 3),)
    monkeypatch.setattr(nodes_upscale_model.ImageUpscaleWithModel, "execute", classmethod(lambda cls, model, image: Upscaled(image)))
    HiresFix.execute("model", "pos", "neg", latent(512, 512), upscale_by=2.0, vae="vae", upscale_model="4x")
    assert stand_ins[:2] == [("decode",), ("encode", (1, 1024, 1024, 3))] # 512 -> 2048 by the model -> resized to 1024.
    with pytest.raises(ValueError, match="connect the vae too"):
        HiresFix.execute("model", "pos", "neg", latent(), upscale_model="4x")
    assert hires_fix.round_to(1001) == 1000
