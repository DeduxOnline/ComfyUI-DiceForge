# Resolution nodes: SDXL Resolution List (Latent) and Resolution Selector (Random, Latent): listed and random sizes, rescale modes, rounding, Random
# Chaos budgets and orientations, and the frontend preview's rounding (web/resolution_preview.js) against the node's.
import itertools
import json
import math
import os
import shutil
import subprocess
import pytest
from DiceForge.resolution_selector_random_latent import ASPECT_RATIOS, ResolutionSelectorRandomLatent as Selector
from DiceForge.sdxl_resolution_list_latent import CHAOS_PIXELS, HIGH_RES, RANDOM_LISTED, STANDARD, SDXLResolutionListLatent as SDXL, rescaled

round_to_multiple = SDXL.round_to_multiple


def by_percentage(percent):
    return {"rescale": "by percentage", "percent": percent}


def sdxl(group, size, seed=0, rescale=None, multiple=8, batch=1, mode="random", max_aspect=2.0):
    latent, width, height, out_seed = SDXL.execute({"resolution": group, "size": size, "max_aspect": max_aspect}, seed, rescale or by_percentage(100), multiple, batch, mode).result
    return latent, width, height, out_seed


def test_round_to_multiple_gives_multiples_close_to_the_ratio():
    for width, height, multiple in itertools.product([500, 777.7, 1000, 1448.2], [300, 640.4, 1211], [8, 16, 64]):
        w, h = round_to_multiple(width, height, multiple)
        assert w % multiple == 0 and h % multiple == 0
        assert abs(w - width) < multiple and abs(h - height) < multiple
        best = min(abs(math.log((a / b) / (width / height))) for a in {math.floor(width / multiple) * multiple, math.ceil(width / multiple) * multiple}
                   for b in {math.floor(height / multiple) * multiple, math.ceil(height / multiple) * multiple})
        assert abs(abs(math.log((w / h) / (width / height))) - best) < 1e-9


def test_round_down_never_goes_over_and_never_below_one_multiple():
    for width, height in [(1000.9, 999.1), (15, 3), (1449, 725)]:
        w, h = round_to_multiple(width, height, 64, round_down=True)
        assert w <= max(width, 64) and h <= max(height, 64) and w >= 64 and h >= 64


def test_standard_size_makes_the_latent():
    latent, width, height, seed = sdxl("Standard", "1216 x 832", seed=5, batch=2)
    assert (width, height, seed) == (1216, 832, 5)
    assert tuple(latent["samples"].shape) == (2, 4, 104, 152)


def test_rescale_by_percentage_multiplies_each_side():
    assert sdxl("Standard", "1024 x 1024", rescale=by_percentage(150), multiple=16)[1:3] == (1536, 1536)
    assert sdxl("Standard", "1024 x 1024", rescale=by_percentage(200))[1:3] == (2048, 2048) # Four times the pixels.
    assert sdxl("Standard", "1216 x 832", rescale=by_percentage(50))[1:3] == (608, 416)
    _, width, height, _ = sdxl("Standard", "768 x 1344", rescale=by_percentage(130), multiple=16)
    assert width % 16 == 0 and height % 16 == 0 and abs(width * height / (768 * 1344) - 1.69) < 0.05 # The pixels grow by the square.
    assert abs(width / height - 768 / 1344) < 0.01


def test_rescale_to_width_and_height():
    to = lambda width=0, height=0: {"rescale": "to Width/Height", "width": width, "height": height}
    assert sdxl("Standard", "1216 x 832", rescale=to(1920, 1080))[1:3] == (1920, 1080) # Both: that exact size.
    width, height = sdxl("Standard", "1216 x 832", rescale=to(width=1536))[1:3]
    assert width == 1536 and abs(width / height - 1216 / 832) < 0.01 and height % 8 == 0
    width, height = sdxl("Standard", "832 x 1216", rescale=to(height=1600))[1:3]
    assert height == 1600 and abs(width / height - 832 / 1216) < 0.01
    assert sdxl("Standard", "1216 x 832", rescale=to())[1:3] == (1216, 832) # Neither: unchanged.


def test_rescale_to_longest_side():
    longest = lambda side: {"rescale": "to longest side", "longer_side": side}
    assert sdxl("Standard", "1024 x 1024", rescale=longest(1536))[1:3] == (1536, 1536)
    assert sdxl("Standard", "1216 x 832", rescale=longest(1536))[1:3] == (1536, 1048)
    width, height = sdxl("Standard", "832 x 1216", rescale=longest(2048), multiple=64)[1:3]
    assert height == 2048 and width % 64 == 0


def test_rescale_without_an_input_is_by_100_percent():
    assert rescaled(1216, 832, None) == (1216, 832)
    assert SDXL.execute({"resolution": "Standard", "size": "1216 x 832"}).result[1:3] == (1216, 832)


def test_high_res_sizes():
    for name, size in HIGH_RES.items():
        assert sdxl("High-Res", name)[1:3] == size


@pytest.mark.parametrize("group", list(RANDOM_LISTED))
def test_random_listed_only_picks_listed_sizes_and_deck_deals_all_of_them(group):
    listed = RANDOM_LISTED[group]
    dealt = [sdxl("Random", group, seed=seed, mode="deck")[1:3] for seed in range(len(listed))]
    assert sorted(dealt) == sorted(listed)
    assert all(sdxl("Random", group, seed=seed)[1:3] in listed for seed in range(30))


def test_random_sequential_goes_in_order():
    listed = RANDOM_LISTED["Any Listed"]
    assert [sdxl("Random", "Any Listed", seed=seed, mode="sequential")[1:3] for seed in range(len(listed))] == listed


@pytest.mark.parametrize("orientation, percent, multiple, max_aspect", [("Any", 100, 8, 2.0), ("Portrait", 150, 64, 3.0), ("Landscape", 75, 16, 1.5)])
def test_random_chaos_stays_in_budget_orientation_and_aspect(orientation, percent, multiple, max_aspect):
    for seed in range(60):
        _, width, height, _ = sdxl("Random Chaos", orientation, seed=seed, rescale=by_percentage(percent), multiple=multiple, max_aspect=max_aspect)
        assert width % multiple == 0 and height % multiple == 0
        assert width * height <= CHAOS_PIXELS * (percent / 100) ** 2
        assert max(width, height) / min(width, height) <= max_aspect * 1.15 # Rounding down can stretch a little.
        if orientation == "Portrait":
            assert height > width
        if orientation == "Landscape":
            assert width > height


def test_random_chaos_to_longest_side_keeps_the_longest_side():
    for seed in range(40):
        _, width, height, _ = sdxl("Random Chaos", "Any", seed=seed, rescale={"rescale": "to longest side", "longer_side": 1536}, multiple=16)
        assert 1536 - 16 < max(width, height) <= 1536


def test_an_old_node_without_a_group_is_a_clear_error():
    with pytest.raises(ValueError, match="no valid group"):
        SDXL.execute(None, 0, by_percentage(100), 8, 1, "random")


def test_the_run_reports_its_size_for_the_preview():
    out = SDXL.execute({"resolution": "Random", "size": "Any Listed"}, 3, by_percentage(150), 8, 1, "random")
    last = out.ui["dice_forge_last_size"][0]
    assert (last["width"], last["height"], last["group"], last["size"]) == (out.result[1], out.result[2], "Random", "Any Listed")
    assert (last["rescale"], last["percent"], last["rescale_width"], last["longer_side"]) == ("by percentage", 150, None, None)


@pytest.mark.parametrize("mode", ["shuffle", "balanced"])
def test_remembering_modes_give_a_seed_its_size_again(mode):
    sizes = {seed: Selector.execute("Random Any", seed=seed, seed_mode=mode).result[1:3] for seed in range(8)}
    assert {seed: Selector.execute("Random Any", seed=seed, seed_mode=mode).result[1:3] for seed in (7, 2, 0)} == {seed: sizes[seed] for seed in (7, 2, 0)}


def test_selector_fixed_ratio_and_megapixels():
    _, width, height, _ = Selector.execute("16:9 (Widescreen)", megapixels=1.0, multiple=8).result
    assert abs(width / height - 16 / 9) < 0.02 and abs(width * height / 1024 ** 2 - 1.0) < 0.03


def test_selector_random_listed_picks_the_right_orientation():
    for seed in range(40):
        _, width, height, _ = Selector.execute("Random Portrait", seed=seed).result
        assert width < height
        ratio = width / height
        assert any(abs(ratio - w / h) < 0.03 for w, h in ASPECT_RATIOS.values())


def old_selector_size(w_ratio, h_ratio, megapixels, multiple=8, round_down=False):
    """The size before rescale existed (the same math as the core Resolution Selector)."""
    scale = math.sqrt(megapixels * 1024 * 1024 / (w_ratio * h_ratio))
    snap = math.floor if round_down else round
    return max(multiple, snap(w_ratio * scale / multiple) * multiple), max(multiple, snap(h_ratio * scale / multiple) * multiple)


def test_selector_at_100_percent_keeps_the_old_sizes():
    for (w_ratio, h_ratio), megapixels, multiple in itertools.product(ASPECT_RATIOS.values(), (0.5, 1.0, 1.3, 2.25), (8, 16, 64)):
        assert Selector.size_for_ratio(w_ratio, h_ratio, megapixels, multiple) == old_selector_size(w_ratio, h_ratio, megapixels, multiple)
        assert Selector.size_for_ratio(w_ratio, h_ratio, megapixels, multiple, rescale=by_percentage(100)) == old_selector_size(w_ratio, h_ratio, megapixels, multiple)


def test_selector_rescale_modes():
    run = lambda ratio, rescale, **inputs: Selector.execute(ratio, rescale=rescale, **inputs).result[1:3]
    assert run("1:1 (Square)", by_percentage(150)) == (1536, 1536)
    assert run("16:9 (Widescreen)", {"rescale": "to longest side", "longer_side": 2048}) == (2048, 1152)
    assert run("9:16 (Portrait Widescreen)", {"rescale": "to longest side", "longer_side": 1920}) == (1080, 1920)
    assert run("4:3 (Standard)", {"rescale": "to Width/Height", "width": 1600, "height": 0}) == (1600, 1200)
    assert run("4:3 (Standard)", {"rescale": "to Width/Height", "width": 1920, "height": 1080}) == (1920, 1080)
    width, height = run("3:2 (Photo)", by_percentage(50), megapixels=2.0)
    assert abs(width * height / 1024 ** 2 - 0.5) < 0.02 # Half each side of 2 MP: a quarter of the pixels.


def test_selector_reports_rescale_for_the_preview():
    last = Selector.execute("Random Any", seed=4, rescale=by_percentage(120)).ui["dice_forge_last_size"][0]
    assert (last["rescale"], last["percent"], last["longer_side"]) == ("by percentage", 120, None)


def test_selector_chaos_with_rescale_stays_within_the_rescaled_megapixels():
    for seed in range(40):
        _, width, height, _ = Selector.execute("Random Chaos Any", megapixels=1.0, seed=seed, multiple=16, rescale=by_percentage(150)).result
        assert width * height <= 1.5 ** 2 * 1024 ** 2 and width % 16 == 0
        _, width, height, _ = Selector.execute("Random Chaos Portrait", seed=seed, rescale={"rescale": "to longest side", "longer_side": 1536}).result
        assert height == 1536 and width < height


def test_selector_chaos_stays_within_the_megapixels():
    for seed in range(40):
        _, width, height, _ = Selector.execute("Random Chaos Landscape", megapixels=1.5, seed=seed, multiple=64, max_aspect=2.5).result
        assert width > height and width * height <= 1.5 * 1024 ** 2 and width % 64 == 0


JS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DiceForge", "web", "resolution_preview.js")


def js_function(name):
    source = open(JS_FILE, encoding="utf-8").read()
    start = source.index(f"function {name}(")
    depth, index = 0, source.index("{", start)
    for index in range(index, len(source)):
        depth += {"{": 1, "}": -1}.get(source[index], 0)
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError(f"{name} not closed")


@pytest.mark.skipif(shutil.which("node") is None, reason="node.js is not installed")
def test_the_preview_rescales_exactly_like_the_node():
    rescales = [{"rescale": "by percentage", "percent": percent} for percent in (50, 100, 137, 150)] + \
        [{"rescale": "to Width/Height", "width": w, "height": h} for w, h in ((1536, 0), (0, 1600), (1920, 1080), (0, 0))] + \
        [{"rescale": "to longest side", "longer_side": side} for side in (1024, 1536, 2000)]
    cases = [(w, h, r) for (w, h) in list(STANDARD.values())[:5] for r in rescales]
    preview = [{"rescale": r["rescale"], "percent": r.get("percent"), "rescale_width": r.get("width"), "rescale_height": r.get("height"), "longer_side": r.get("longer_side")} for _, _, r in cases]
    script = js_function("rescaled") + f"\nconst cases = {json.dumps([[w, h] for w, h, _ in cases])}, settings = {json.dumps(preview)};" + \
        "\nconsole.log(JSON.stringify(cases.map(([w, h], index) => rescaled(w, h, settings[index]))));"
    output = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    for got, (w, h, r) in zip(json.loads(output), cases):
        assert got == pytest.approx(list(rescaled(w, h, r))), (w, h, r)


@pytest.mark.skipif(shutil.which("node") is None, reason="node.js is not installed")
def test_the_selector_preview_sizes_exactly_like_the_node():
    rescales = [None, by_percentage(150), by_percentage(55), {"rescale": "to longest side", "longer_side": 1600}, {"rescale": "to Width/Height", "width": 1000, "height": 0}]
    cases = [(w, h, megapixels, multiple, r) for (w, h) in ASPECT_RATIOS.values() for megapixels in (0.5, 1.0, 1.21, 2.0) for multiple in (8, 64) for r in rescales]
    cases += [(1, 1, (13 * 8) ** 2 / 1024 ** 2, 16, None), (1, 1, (21 * 8) ** 2 / 1024 ** 2, 16, None)] # 104 / 16 = 6.5, 168 / 16 = 10.5: Python rounds halves to even.
    settings = [{"megapixels": mp, "multiple": m, "rescale": (r or {}).get("rescale", "by percentage"), "percent": (r or {}).get("percent"),
                 "rescale_width": (r or {}).get("width"), "rescale_height": (r or {}).get("height"), "longer_side": (r or {}).get("longer_side")} for _, _, mp, m, r in cases]
    script = "\n".join(js_function(name) for name in ("roundHalfEven", "rescaled", "selectorSize")) + \
        f"\nconst cases = {json.dumps([[w, h] for w, h, *_ in cases])}, settings = {json.dumps(settings)};" + \
        "\nconsole.log(JSON.stringify(cases.map(([w, h], index) => selectorSize(w, h, settings[index]))));"
    output = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert [tuple(size) for size in json.loads(output)] == [Selector.size_for_ratio(w, h, mp, m, rescale=r) for w, h, mp, m, r in cases]


@pytest.mark.skipif(shutil.which("node") is None, reason="node.js is not installed")
def test_the_preview_rounds_exactly_like_the_node():
    cases = [(w * s, h * s, m) for (w, h) in list(STANDARD.values()) + list(HIGH_RES.values()) for s in (0.5, 0.9, 1.0, 1.3, math.sqrt(1.69), 2.1) for m in (8, 16, 32, 64)]
    script = js_function("roundToMultiple") + f"\nconsole.log(JSON.stringify({json.dumps(cases)}.map(([w, h, m]) => roundToMultiple(w, h, m))));"
    output = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert [tuple(size) for size in json.loads(output)] == [round_to_multiple(w, h, m) for w, h, m in cases]
