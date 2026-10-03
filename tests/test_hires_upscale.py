# HiresFix (Load VAE) (DiceForge/hires_upscale.py): the upscale model, the rescale after it, the VAE from the list, and what is shown or saved.
import nodes
import pytest
import torch
from DiceForge import hires_upscale, load_vae_decode_save
from DiceForge.hires_upscale import HiresUpscale


@pytest.fixture
def stand_ins(monkeypatch):
    """A 4x upscale model, a VAE that records what it encodes, and the VAE list's loader."""
    calls = []
    monkeypatch.setattr(hires_upscale, "load_upscale_model", lambda name: (calls.append(("model", name)) or "4x"))
    monkeypatch.setattr(hires_upscale, "upscale_with_model", lambda model, images: torch.zeros(images.shape[0], images.shape[1] * 4, images.shape[2] * 4, 3))
    monkeypatch.setattr(load_vae_decode_save.LoadVAEDecodeSave, "load_vae", staticmethod(lambda name: (calls.append(("vae", name)) or "vae")))
    monkeypatch.setattr(nodes.VAEEncode, "encode", lambda self, vae, images: (calls.append(("encode", tuple(images.shape))) or {"samples": torch.zeros(1, 4, images.shape[1] // 8, images.shape[2] // 8)},))
    return calls


def image(width=512, height=384):
    return torch.rand(1, height, width, 3)


def run(**inputs):
    values = {"image": image(), "model_name": "4x-AnimeSharp.pth", "rescale": {"rescale": "by percentage", "percent": 50}, "vae_name": "sdxl_vae.safetensors",
              "image_output": "Hide", **inputs}
    return HiresUpscale.execute(**values)


def test_model_then_half_the_size_then_encoded(stand_ins):
    images, latent, vae = run().result
    assert images.shape == (1, 768, 1024, 3) and latent["samples"].shape == (1, 4, 96, 128) and vae == "vae" # 4x, then 50%: twice the size.
    assert stand_ins == [("model", "4x-AnimeSharp.pth"), ("vae", "sdxl_vae.safetensors"), ("encode", (1, 768, 1024, 3))]


@pytest.mark.parametrize("inputs, size", [
    ({"rescale": {"rescale": "to Width/Height", "width": 1536, "height": 0}}, (1152, 1536)), ({"rescale": {"rescale": "to longest side", "longer_side": 1000}}, (752, 1000)),
    ({"rescale_after_model": False}, (1536, 2048)), ({"model_name": "None", "rescale": {"rescale": "by percentage", "percent": 150}}, (576, 768)),
    ({"model_name": "None", "rescale_after_model": False, "rescale": {"rescale": "by percentage", "percent": 200}}, (768, 1024)), # Without a model: rescaled anyway.
])
def test_sizes(stand_ins, inputs, size):
    assert tuple(run(**inputs).result[0].shape[1:3]) == size


def test_shown_or_saved_and_bad_values(stand_ins, monkeypatch):
    shown = []
    monkeypatch.setattr(hires_upscale, "show_or_save", lambda cls, images, prefix, mode: (shown.append((prefix, mode)) or None))
    run(image_output="Save", filename_prefix="x/hires")
    assert shown == [("x/hires", "Save")]
    with pytest.raises(ValueError, match="unknown image_output"):
        run(image_output="Nope")
    with pytest.raises(ValueError, match="unknown rescale_method"):
        run(rescale_method="nope")
    assert ("model", "4x-AnimeSharp.pth") in stand_ins and hires_upscale.upscale_models()[0] == "None"
