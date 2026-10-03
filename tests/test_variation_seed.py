# Variation Seed (DiceForge/variation_seed.py): the spherical blend of two noises, the wrapper that puts it into the sampling, and XY Plot's
# variation axes.
import torch
import comfy.model_patcher
import comfy.patcher_extension
import comfy.sample
import pytest
from DiceForge import variation_seed, xy_plot
from DiceForge.variation_seed import VariationSeed, blend_noise, slerp, with_variation


def noise(seed, shape=(2, 4, 16, 16)):
    return comfy.sample.prepare_noise(torch.zeros(shape), seed)


def cosine(a, b):
    return torch.nn.functional.cosine_similarity(a.reshape(a.shape[0], -1), b.reshape(b.shape[0], -1)).min().item()


def test_slerp_ends_and_keeps_the_size_of_the_noise():
    a, b = noise(1), noise(2)
    assert torch.equal(slerp(a, b, 0), a) and torch.equal(slerp(a, b, 1), b)
    middle = slerp(a, b, 0.5)
    assert abs(middle.norm().item() / a.norm().item() - 1) < 0.02 # A plain average would shrink it by about 30%.
    assert torch.allclose(slerp(a, a, 0.3), a, atol=1e-5) # The same direction: no division by zero.


def test_a_low_strength_stays_close_and_is_reproducible():
    base = noise(10)
    small, again, other = blend_noise(base, 99, 0.1), blend_noise(base, 99, 0.1), blend_noise(base, 100, 0.1)
    assert torch.equal(small, again) and not torch.equal(small, other) # The same three numbers: the same noise.
    assert cosine(small, base) > 0.98 and cosine(blend_noise(base, 99, 0.5), base) < 0.9
    assert torch.equal(blend_noise(base, 99, 0), base)
    zeros = torch.zeros(1, 4, 8, 8)
    assert torch.equal(blend_noise(zeros, 99, 0.5), zeros) # add_noise disabled: nothing to blend.


def model():
    return comfy.model_patcher.ModelPatcher(torch.nn.Linear(1, 1), load_device=torch.device("cpu"), offload_device=torch.device("cpu"))


def test_the_wrapper_gives_the_sampler_the_blended_noise():
    original = model()
    patched, label = VariationSeed.execute(original, variation_seed=5, variation_strength=0.2).result
    assert label == "variation 5 @ 0.2" and patched is not original
    assert not original.wrappers.get(comfy.patcher_extension.WrappersMP.OUTER_SAMPLE) # The model passed in stays as it is.
    wrappers = patched.wrappers[comfy.patcher_extension.WrappersMP.OUTER_SAMPLE][variation_seed.WRAPPER_KEY]
    seen = []
    base = noise(3)
    wrappers[0](lambda given, *args, **kwargs: seen.append((given, args, kwargs)), base, "latent", "sampler", seed=3)
    assert torch.equal(seen[0][0], blend_noise(base, 5, 0.2)) and seen[0][1] == ("latent", "sampler") and seen[0][2] == {"seed": 3}
    again = with_variation(patched, 6, 0.3) # Another Variation Seed after it: only the last one counts.
    assert len(again.wrappers[comfy.patcher_extension.WrappersMP.OUTER_SAMPLE][variation_seed.WRAPPER_KEY]) == 1
    assert with_variation(original, 5, 0) is original


def test_xy_plot_variation_axes(monkeypatch):
    calls = []
    monkeypatch.setattr(xy_plot, "with_variation", lambda model, seed, strength: (calls.append((seed, strength)) or f"{model}~{seed}"))
    inputs = {"x_type": "variation seed", "x_values": "1-3", "y_type": "none", "y_values": "", "variation_strength": 0.1, "model": "m"}
    cells = [xy_plot.XYPlot.execute(index=index, **inputs).result for index in range(3)]
    assert [cell[0] for cell in cells] == ["m~1", "m~2", "m~3"] and [cell[8] for cell in cells] == ["variation 1", "variation 2", "variation 3"]
    assert calls == [(1, 0.1), (2, 0.1), (3, 0.1)]
    strengths = xy_plot.XYPlot.execute(index=1, x_type="variation strength", x_values="0, 0.1", y_type="none", y_values="", variation_seed=7, model="m").result
    assert strengths[0] == "m~7" and calls[-1] == (7, 0.1)
    assert xy_plot.XYPlot.execute(index=0, x_type="variation strength", x_values="0, 0.1", y_type="none", y_values="", model="m").result[0] == "m" # 0: none.
    with pytest.raises(ValueError, match="variation needs the model"):
        xy_plot.XYPlot.execute(index=0, x_type="variation seed", x_values="1", y_type="none", y_values="", variation_strength=0.1)
