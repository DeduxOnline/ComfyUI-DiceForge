# Random Int, Random Float, Random Sampler, the random model loaders, Random Image and Load Diffusion Model + CLIP. The core loaders are replaced by
# stand-ins that record what they were asked to load: the tests check what DiceForge picks and passes on, not ComfyUI's model loading.
import os
import nodes
import numpy as np
import pytest
from PIL import Image
from DiceForge import model_lists
from DiceForge.load_diffusion_model_clip import LoadDiffusionModelCLIP, clip_types
from DiceForge.random_checkpoint import RandomCheckpointLoader
from DiceForge.random_diffusion_model import RandomDiffusionModelLoader
from DiceForge.random_float import RandomFloatSeedModes as RandomFloat
from DiceForge.random_image import RandomImageLoader
from DiceForge.random_int import RandomIntSeedModes as RandomInt
from DiceForge.random_lora import NO_LORA, RandomLoraLoader
from DiceForge.random_sampler import SAMPLERS, SCHEDULERS, RandomSampler, parse_names
from DiceForge.random_vae import RandomVAELoader


def value(node, **inputs):
    return node.execute(**inputs).result[0]


def test_random_int_range_step_and_reversed_range():
    assert all(value(RandomInt, min=3, max=9, step=3, seed=seed) in (3, 6, 9) for seed in range(40))
    assert all(3 <= value(RandomInt, min=9, max=3, seed=seed) <= 9 for seed in range(40))


def test_random_int_deck_and_sequential_go_through_every_value():
    assert sorted(value(RandomInt, min=0, max=10, seed=seed, seed_mode="deck") for seed in range(11)) == list(range(11))
    assert [value(RandomInt, min=5, max=7, seed=seed, seed_mode="sequential") for seed in range(4)] == [5, 6, 7, 5]


def test_random_int_shuffle_remembers_between_runs():
    assert sorted(value(RandomInt, min=1, max=6, seed=0, seed_mode="shuffle") for _ in range(6)) == [1, 2, 3, 4, 5, 6]


def test_random_float_with_a_step_hits_the_grid_including_max():
    got = {value(RandomFloat, min=0.5, max=0.9, step=0.1, seed=seed, seed_mode="deck") for seed in range(5)}
    assert got == {0.5, 0.6, 0.7, 0.8, 0.9}


def test_random_float_without_a_step_spreads_over_the_parts():
    got = [value(RandomFloat, min=0.0, max=1.0, seed=seed, seed_mode="deck", parts=4) for seed in range(4)]
    assert sorted(int(v * 4) for v in got) == [0, 1, 2, 3]
    assert all(2.0 <= value(RandomFloat, min=5.0, max=2.0, seed=seed) <= 5.0 for seed in range(30))


def test_parse_names():
    assert parse_names("euler, euler\n dpmpp_2m", SAMPLERS, "sampler") == ["euler", "dpmpp_2m"]
    assert parse_names("*", SCHEDULERS, "scheduler") == list(SCHEDULERS)
    with pytest.raises(ValueError, match="unknown sampler nope"):
        parse_names("euler, nope", SAMPLERS, "sampler")
    with pytest.raises(ValueError, match="no samplers listed"):
        parse_names(" , ", SAMPLERS, "sampler")


def test_random_sampler_deals_every_pair():
    pairs = [RandomSampler.execute("euler, dpmpp_2m", "normal, karras", seed=seed, seed_mode="deck").result[2] for seed in range(4)]
    assert sorted(pairs) == ["dpmpp_2m / karras", "dpmpp_2m / normal", "euler / karras", "euler / normal"]
    sampler, scheduler, label, *_ = RandomSampler.execute("euler", "karras").result
    assert (sampler, scheduler, label) == ("euler", "karras", "euler / karras")


def test_model_folders_and_files_in_a_folder(models):
    for name in ("root.safetensors", "anime/a1.safetensors", "anime/styles/s1.safetensors", "real/r1.safetensors"):
        models("loras", name)
    assert model_lists.model_folders("loras") == ["(all)", "anime", "anime/styles", "real"]
    assert [os.path.basename(name) for name in model_lists.files_in_folder("loras", "anime")] == ["a1.safetensors", "s1.safetensors"]
    assert len(model_lists.files_in_folder("loras", "(all)")) == 4


@pytest.fixture
def loaded(monkeypatch):
    """Stand-ins for the core loaders: each call is recorded as (loader, file)."""
    calls = []
    monkeypatch.setattr(RandomLoraLoader.loader, "load_lora", lambda model, clip, name, sm, sc: (calls.append(("lora", name, sm, sc)) or (f"{model}+{name}", clip and f"{clip}+{name}")))
    monkeypatch.setattr(nodes.CheckpointLoaderSimple, "load_checkpoint", lambda self, name: (calls.append(("checkpoint", name)) or ("model", "clip", "vae")))
    monkeypatch.setattr(nodes.UNETLoader, "load_unet", lambda self, name, dtype: (calls.append(("unet", name, dtype)) or ("unet",)))
    monkeypatch.setattr(nodes.VAELoader, "load_vae", lambda self, name: (calls.append(("vae", name)) or ("vae",)))
    monkeypatch.setattr(nodes.CLIPLoader, "load_clip", lambda self, name, type, device: (calls.append(("clip", name, type)) or ("clip",)))
    monkeypatch.setattr(nodes.DualCLIPLoader, "load_clip", lambda self, a, b, type, device: (calls.append(("dualclip", a, b, type)) or ("clip2",)))
    return calls


def test_random_lora_picks_from_the_folder_and_applies_it(models, loaded):
    for name in ("style/a.safetensors", "style/b.safetensors", "other/c.safetensors"):
        models("loras", name)
    picked = {RandomLoraLoader.execute("model", folder="style", seed=seed, seed_mode="deck", clip="clip").result[2] for seed in range(2)}
    assert {os.path.basename(name) for name in picked} == {"a.safetensors", "b.safetensors"}
    model, clip, name = RandomLoraLoader.execute("model", folder="style", seed=0, seed_mode="deck", clip="clip").result
    assert model == f"model+{name}" and clip == f"clip+{name}" and loaded[-1][2] == 1.0


def test_random_lora_without_clip_and_with_the_no_lora_option(models, loaded):
    models("loras", "only.safetensors")
    model, clip, name = RandomLoraLoader.execute("model", seed=0, clip=None).result
    assert clip is None and loaded[-1][3] == 0
    results = {RandomLoraLoader.execute("model", seed=seed, seed_mode="deck", include_none=True).result for seed in range(2)}
    assert ("model", None, "") in results


def test_random_loaders_explain_an_empty_folder(models, loaded):
    for node, what in ((RandomLoraLoader, "LoRA"), (RandomCheckpointLoader, "checkpoint"), (RandomDiffusionModelLoader, "diffusion model"), (RandomVAELoader, "VAE")):
        inputs = {"model": "m"} if node is RandomLoraLoader else {}
        with pytest.raises(ValueError, match=f"No {what} files"):
            node.execute(**inputs)


def test_random_checkpoint_diffusion_model_and_vae_deal_every_file(models, loaded):
    for kind in ("checkpoints", "diffusion_models", "vae"):
        for index in range(3):
            models(kind, f"f{index}.safetensors")
    assert sorted(RandomCheckpointLoader.execute(seed=seed, seed_mode="deck").result[3] for seed in range(3)) == ["f0.safetensors", "f1.safetensors", "f2.safetensors"]
    assert RandomDiffusionModelLoader.execute(seed=1, seed_mode="sequential", weight_dtype="fp8_e4m3fn").result == ("unet", "f1.safetensors")
    assert loaded[-1] == ("unet", "f1.safetensors", "fp8_e4m3fn")
    assert RandomVAELoader.execute(seed=2, seed_mode="sequential").result == ("vae", "f2.safetensors")


def test_load_diffusion_model_clip_checks_the_type_before_loading(loaded):
    single, dual = clip_types()
    one_file, two_files = single[0], next(t for t in dual if t not in single)
    with pytest.raises(ValueError, match="needs two text encoders"):
        LoadDiffusionModelCLIP.execute("m.safetensors", "a.safetensors", "None", two_files)
    with pytest.raises(ValueError, match="takes one text encoder"):
        LoadDiffusionModelCLIP.execute("m.safetensors", "a.safetensors", "b.safetensors", next(t for t in single if t not in dual))
    assert loaded == [] # Nothing loaded before the error.
    assert LoadDiffusionModelCLIP.execute("m.safetensors", "a.safetensors", "None", one_file).result == ("unet", "clip")
    assert LoadDiffusionModelCLIP.execute("m.safetensors", "a.safetensors", "b.safetensors", two_files).result == ("unet", "clip2")
    assert loaded[-1] == ("dualclip", "a.safetensors", "b.safetensors", two_files)


@pytest.fixture
def images(tmp_path):
    folder = tmp_path / "pictures"
    (folder / "sub").mkdir(parents=True)
    (folder / "clipspace").mkdir()
    (folder / ".hidden").mkdir()
    Image.new("RGB", (32, 16), (255, 0, 0)).save(folder / "red.png")
    rgba = Image.new("RGBA", (8, 8), (0, 0, 255, 255))
    rgba.putpixel((0, 0), (0, 0, 255, 0))
    rgba.save(folder / "sub" / "blue.png")
    Image.new("RGB", (4, 4)).save(folder / ".hidden" / "no.png")
    (folder / "notes.txt").write_text("not an image")
    return folder


def test_image_files_skip_hidden_folders_and_clipspace(images):
    assert model_lists.image_files(str(images)) == ["red.png", "sub/blue.png"]
    assert model_lists.image_folders(str(images)) == ["(all)", "sub"]


def test_random_image_loads_like_load_image(images):
    image, mask, name = RandomImageLoader.execute(seed=1, seed_mode="sequential", path=str(images)).result
    assert name == "sub/blue.png"
    assert tuple(image.shape) == (1, 8, 8, 3) and float(image[0, 0, 0, 2]) > 0.99
    assert tuple(mask.shape) == (1, 8, 8) and float(mask[0, 0, 0]) == 1.0 and float(mask[0, 1, 1]) == 0.0
    image, _, name = RandomImageLoader.execute(seed=0, seed_mode="sequential", path=str(images)).result
    assert name == "red.png" and tuple(image.shape) == (1, 16, 32, 3)
    assert np.allclose(image[0, 0, 0].cpu().numpy(), [1.0, 0.0, 0.0])


def test_random_image_sends_its_pick_to_the_node_preview(images, monkeypatch):
    output = RandomImageLoader.execute(seed=1, seed_mode="sequential", path=str(images)) # Another folder: a temporary copy to show.
    shown = output.ui["dice_forge_image"][0]
    assert {key: shown[key] for key in ("file", "folder", "width", "height", "frames", "seed", "seed_mode")} == \
        {"file": "sub/blue.png", "folder": os.path.abspath(str(images)), "width": 8, "height": 8, "frames": 1, "seed": 1, "seed_mode": "sequential"}
    assert shown["view"]["type"] == "temp" and shown["view"]["filename"].endswith(".png")
    assert set(output.ui) == {"dice_forge_image"} # Only this preview: not also ComfyUI's image preview.
    monkeypatch.setattr(model_lists.folder_paths, "get_input_directory", lambda: str(images)) # The input folder: shown from there.
    shown = RandomImageLoader.execute(folder="sub", seed=0, seed_mode="sequential").ui["dice_forge_image"][0]
    assert shown["file"] == "sub/blue.png" and shown["folder"] == "input/sub" and shown["view"] == {"filename": "blue.png", "subfolder": "sub", "type": "input"}
    shown = RandomImageLoader.execute(seed=0, seed_mode="sequential").ui["dice_forge_image"][0]
    assert shown["folder"] == "input" and shown["view"] == {"filename": "red.png", "subfolder": "", "type": "input"}


def test_random_image_errors(tmp_path, images):
    with pytest.raises(ValueError, match="is not a folder"):
        RandomImageLoader.execute(path=str(tmp_path / "missing"))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no images"):
        RandomImageLoader.execute(path=str(empty))
