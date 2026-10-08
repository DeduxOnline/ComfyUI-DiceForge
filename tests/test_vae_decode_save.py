# VAE Decode + Save and Load VAE + Decode + Save (DiceForge/load_vae_decode_save.py): decoding, saving PNG files with the workflow, passing the images
# on, and keeping the loaded VAE between runs. A stand-in VAE turns each latent into a gray image 8 times its size.
import os
import types
import folder_paths
import nodes
import pytest
import torch
from PIL import Image
from DiceForge.load_vae_decode_save import LoadVAEDecodeSave, VAEDecodeSave, _vae_cache


class FakeVAE:
    def __init__(self, video=False):
        self.video, self.decoded = video, []

    def decode(self, latent):
        self.decoded.append(tuple(latent.shape))
        batch, _, height, width = latent.shape
        images = torch.full((batch, height * 8, width * 8, 3), 0.5)
        return images.reshape(1, batch, height * 8, width * 8, 3) if self.video else images


def latent(batch=1, height=6, width=8):
    return {"samples": torch.zeros((batch, 4, height, width))}


def saved_files(ui):
    return [os.path.join(folder_paths.get_output_directory(), image["subfolder"], image["filename"]) for image in ui.as_dict()["images"]]


@pytest.fixture
def with_workflow(monkeypatch):
    """The prompt and workflow that ComfyUI gives a node while it runs (saved in the PNG)."""
    hidden = types.SimpleNamespace(prompt={"1": {"class_type": "DiceForgeVAEDecodeSave"}}, extra_pnginfo={"workflow": {"nodes": []}}, unique_id="1")
    monkeypatch.setattr(VAEDecodeSave, "hidden", hidden, raising=False)
    monkeypatch.setattr(LoadVAEDecodeSave, "hidden", hidden, raising=False)


def test_decodes_saves_and_passes_the_images_on(with_workflow):
    vae = FakeVAE()
    out = VAEDecodeSave.execute(latent(batch=2), vae, "DiceForge/test_vds_%width%x%height%")
    images = out.result[0]
    assert tuple(images.shape) == (2, 48, 64, 3) and vae.decoded == [(2, 4, 6, 8)]
    files = saved_files(out.ui)
    assert len(files) == 2 and all(os.path.basename(path).startswith("test_vds_64x48_") for path in files)
    with Image.open(files[0]) as image:
        assert image.size == (64, 48) and image.getpixel((0, 0))[0] in (127, 128)
        assert "prompt" in image.info and "workflow" in image.info


def test_video_style_output_becomes_a_batch_of_frames(with_workflow):
    out = VAEDecodeSave.execute(latent(batch=3), FakeVAE(video=True), "DiceForge/test_video")
    assert tuple(out.result[0].shape) == (3, 48, 64, 3) and len(saved_files(out.ui)) == 3


@pytest.mark.filterwarnings("ignore:The PyTorch API of nested tensors is in prototype stage")
def test_a_nested_latent_uses_its_first_tensor(with_workflow):
    vae = FakeVAE()
    nested = torch.nested.nested_tensor([torch.zeros((1, 4, 2, 2)), torch.zeros((1, 4, 3, 3))])
    VAEDecodeSave.execute({"samples": nested}, vae, "DiceForge/test_nested")
    assert vae.decoded == [(1, 4, 2, 2)]


def test_load_vae_version_keeps_the_vae_while_the_name_stays(monkeypatch, with_workflow):
    loads = []
    monkeypatch.setattr(nodes.VAELoader, "load_vae", lambda self, name: (loads.append(name) or (FakeVAE(),)))
    _vae_cache.update(name=None, vae=None)
    for name in ("a.safetensors", "a.safetensors", "b.safetensors", "b.safetensors"):
        LoadVAEDecodeSave.execute(latent(), name, "DiceForge/test_load_vds")
    assert loads == ["a.safetensors", "b.safetensors"]


def test_a_failed_load_is_tried_again_next_run(monkeypatch):
    def broken(self, name):
        raise RuntimeError("disk error")
    monkeypatch.setattr(nodes.VAELoader, "load_vae", broken)
    _vae_cache.update(name=None, vae=None)
    with pytest.raises(RuntimeError):
        LoadVAEDecodeSave.load_vae("c.safetensors")
    assert _vae_cache["name"] is None


def output_files(prefix):
    folder = os.path.join(folder_paths.get_output_directory(), "DiceForge")
    return sorted(name for name in os.listdir(folder) if name.startswith(prefix)) if os.path.isdir(folder) else []


def test_image_output_hide_preview_save_hide_and_save(with_workflow):
    for node, args in ((VAEDecodeSave, (FakeVAE(),)), (LoadVAEDecodeSave, ())):
        if node is LoadVAEDecodeSave:
            _vae_cache.update(name="fake.safetensors", vae=FakeVAE()) # Already loaded: no file needed.
            args = ("fake.safetensors",)
        tag = node.__name__
        hidden = node.execute(latent(batch=2), *args, f"DiceForge/io_hide_{tag}", image_output="Hide")
        assert tuple(hidden.result[0].shape) == (2, 48, 64, 3) and hidden.ui is None and output_files(f"io_hide_{tag}") == []
        assert hidden.result[1] is (args[0] if node is VAEDecodeSave else _vae_cache["vae"]) # The VAE used, passed on.
        preview = node.execute(latent(), *args, f"DiceForge/io_preview_{tag}", image_output="Preview")
        shown = preview.ui.as_dict()["images"]
        assert len(shown) == 1 and shown[0]["type"] == "temp" and output_files(f"io_preview_{tag}") == [] # Shown, not saved.
        saved = node.execute(latent(), *args, f"DiceForge/io_save_{tag}", image_output="Save")
        assert saved.ui.as_dict()["images"][0]["type"] == "output" and len(output_files(f"io_save_{tag}")) == 1
        quiet = node.execute(latent(batch=2), *args, f"DiceForge/io_quiet_{tag}", image_output="Hide&Save")
        assert quiet.ui is None and len(output_files(f"io_quiet_{tag}")) == 2 # Saved, not shown.
        default = node.execute(latent(), *args, f"DiceForge/io_default_{tag}") # Workflows made before image_output: Save.
        assert len(output_files(f"io_default_{tag}")) == 1
    vae = FakeVAE()
    with pytest.raises(ValueError, match="unknown image_output"):
        VAEDecodeSave.execute(latent(), vae, "DiceForge/io_bad", image_output="Sideways")
    assert vae.decoded == [] # Refused before decoding.
    _vae_cache.update(name=None, vae=None)
