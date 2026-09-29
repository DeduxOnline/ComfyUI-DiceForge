# Resolution nodes: SDXL Resolution List (Latent) and Resolution Selector (Random, Latent): listed and random sizes, scale by area, rounding, Random
# Chaos budgets and orientations, and the frontend preview's rounding (web/resolution_preview.js) against the node's.
import itertools
import json
import math
import os
import shutil
import subprocess
import pytest
from DiceForge.resolution_selector_random_latent import ASPECT_RATIOS, ResolutionSelectorRandomLatent as Selector
from DiceForge.sdxl_resolution_list_latent import CHAOS_PIXELS, HIGH_RES, RANDOM_LISTED, STANDARD, SDXLResolutionListLatent as SDXL

round_to_multiple = SDXL.round_to_multiple


def sdxl(group, size, seed=0, scale=1.0, multiple=8, batch=1, mode="random", max_aspect=2.0):
    latent, width, height, out_seed = SDXL.execute({"resolution": group, "size": size, "max_aspect": max_aspect}, seed, scale, multiple, batch, mode).result
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


def test_scale_sides_by_multiplies_each_side():
    assert sdxl("Standard", "1024 x 1024", scale=1.5, multiple=16)[1:3] == (1536, 1536)
    assert sdxl("Standard", "1024 x 1024", scale=2.0)[1:3] == (2048, 2048) # Four times the pixels.
    assert sdxl("Standard", "1216 x 832", scale=0.5)[1:3] == (608, 416)
    _, width, height, _ = sdxl("Standard", "768 x 1344", scale=1.3, multiple=16)
    assert width % 16 == 0 and height % 16 == 0 and abs(width * height / (768 * 1344) - 1.69) < 0.05 # The pixels grow by the square.
    assert abs(width / height - 768 / 1344) < 0.01


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


@pytest.mark.parametrize("orientation, scale, multiple, max_aspect", [("Any", 1.0, 8, 2.0), ("Portrait", 1.5, 64, 3.0), ("Landscape", 0.75, 16, 1.5)])
def test_random_chaos_stays_in_budget_orientation_and_aspect(orientation, scale, multiple, max_aspect):
    for seed in range(60):
        _, width, height, _ = sdxl("Random Chaos", orientation, seed=seed, scale=scale, multiple=multiple, max_aspect=max_aspect)
        assert width % multiple == 0 and height % multiple == 0
        assert width * height <= CHAOS_PIXELS * scale ** 2
        assert max(width, height) / min(width, height) <= max_aspect * 1.15 # Rounding down can stretch a little.
        if orientation == "Portrait":
            assert height > width
        if orientation == "Landscape":
            assert width > height


def test_an_old_node_without_a_group_is_a_clear_error():
    with pytest.raises(ValueError, match="no valid group"):
        SDXL.execute(None, 0, 1.0, 8, 1, "random")


def test_the_run_reports_its_size_for_the_preview():
    out = SDXL.execute({"resolution": "Random", "size": "Any Listed"}, 3, 1.0, 8, 1, "random")
    last = out.ui["dice_forge_last_size"][0]
    assert (last["width"], last["height"], last["group"], last["size"]) == (out.result[1], out.result[2], "Random", "Any Listed")


def test_listed_random_fingerprint_only_changes_for_remembering_modes():
    assert SDXL.fingerprint_inputs({"resolution": "Standard"}, "shuffle") is None
    assert SDXL.fingerprint_inputs({"resolution": "Random"}, "deck") is None
    assert SDXL.fingerprint_inputs({"resolution": "Random"}, "shuffle") is not None


def test_selector_fixed_ratio_and_megapixels():
    _, width, height, _ = Selector.execute("16:9 (Widescreen)", megapixels=1.0, multiple=8).result
    assert abs(width / height - 16 / 9) < 0.02 and abs(width * height / 1024 ** 2 - 1.0) < 0.03


def test_selector_random_listed_picks_the_right_orientation():
    for seed in range(40):
        _, width, height, _ = Selector.execute("Random Portrait", seed=seed).result
        assert width < height
        ratio = width / height
        assert any(abs(ratio - w / h) < 0.03 for w, h in ASPECT_RATIOS.values())


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
def test_the_preview_rounds_exactly_like_the_node():
    cases = [(w * s, h * s, m) for (w, h) in list(STANDARD.values()) + list(HIGH_RES.values()) for s in (0.5, 0.9, 1.0, 1.3, math.sqrt(1.69), 2.1) for m in (8, 16, 32, 64)]
    script = js_function("roundToMultiple") + f"\nconsole.log(JSON.stringify({json.dumps(cases)}.map(([w, h, m]) => roundToMultiple(w, h, m))));"
    output = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert [tuple(size) for size in json.loads(output)] == [round_to_multiple(w, h, m) for w, h, m in cases]
