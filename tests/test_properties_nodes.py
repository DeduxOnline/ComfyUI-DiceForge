# Invariants of the other DiceForge nodes on generated inputs: resolution sizes (both nodes, every group, rescale mode, multiple and seed mode),
# Random Int / Float / Sampler, the random loaders, LoRA Stack (junk stack data, strengths, groups, trigger words), Dice Grid layouts, and the
# file names that must never leave their folder (model info, presets, wildcards).
import itertools
import json
import math
import os
import random
from collections import Counter
import nodes
import numpy as np
import pytest
from aiohttp import web
from hypothesis import assume, example, given, settings, strategies as st
from DiceForge import dice_grid, lora_stack, model_info, wildcards_api
from DiceForge.lora_stack import LoraStack, group_pick, parse_stack, preset_path, row_strength
from DiceForge.random_float import RandomFloatSeedModes as RandomFloat
from DiceForge.random_int import RandomIntSeedModes as RandomInt
from DiceForge.random_lora import RandomLoraLoader
from DiceForge.random_sampler import SAMPLERS, SCHEDULERS, RandomSampler
from DiceForge.resolution_selector_random_latent import ASPECT_RATIOS
from DiceForge.resolution_selector_random_latent import RANDOM_CHAOS as SELECTOR_CHAOS
from DiceForge.resolution_selector_random_latent import RANDOM_LISTED as SELECTOR_LISTED
from DiceForge.resolution_selector_random_latent import ResolutionSelectorRandomLatent as Selector
from DiceForge.sdxl_resolution_list_latent import (BY_PERCENTAGE, CHAOS_PIXELS, HIGH_RES, RANDOM_CHAOS, RANDOM_LISTED, STANDARD, TO_LONGEST_SIDE,
                                                   TO_WIDTH_HEIGHT, SDXLResolutionListLatent as SDXL)
from DiceForge.seed_modes import DeckPicker
scaled = lambda count: max(1, count * settings.default.max_examples // 200) # Explicit budgets follow the profile (thorough: 15 times).

SEED_MODES = ["random", "deck", "shuffle", "balanced", "sequential"]
REPRODUCIBLE = ["random", "deck", "sequential"]
seeds = st.integers(0, 2 ** 64 - 1)
multiples = st.integers(1, 32).map(lambda k: k * 8)
percents = st.integers(1, 200).map(lambda k: k * 5)
sides = st.integers(0, 2048).map(lambda k: k * 8)
rescales = st.one_of(
    st.none(),
    st.builds(lambda percent: {"rescale": BY_PERCENTAGE, "percent": percent}, percents),
    st.builds(lambda width, height: {"rescale": TO_WIDTH_HEIGHT, "width": width, "height": height}, sides, sides),
    st.builds(lambda side: {"rescale": TO_LONGEST_SIDE, "longer_side": side}, st.integers(8, 2048).map(lambda k: k * 8)),
)
max_aspects = st.integers(20, 80).map(lambda k: round(k * 0.05, 2))


@pytest.fixture
def latents(monkeypatch):
    """Empty Latent Image without the tensor (sizes up to 16384 would take gigabytes): records the sizes asked for."""
    made = []

    def generate(self, width, height, batch_size=1):
        made.append((width, height, batch_size))
        return ({"samples": None},)
    monkeypatch.setattr(nodes.EmptyLatentImage, "generate", generate)
    return made


@st.composite
def sdxl_resolutions(draw):
    group = draw(st.sampled_from(["Standard", "High-Res", "Random", "Random Chaos"]))
    sizes = {"Standard": list(STANDARD), "High-Res": list(HIGH_RES), "Random": list(RANDOM_LISTED), "Random Chaos": RANDOM_CHAOS}[group]
    resolution = {"resolution": group, "size": draw(st.sampled_from(sizes))}
    if group == "Random Chaos":
        resolution["max_aspect"] = draw(max_aspects)
    return resolution


def sdxl(resolution, rescale, multiple=8, seed=0, mode="random", batch=1):
    output = SDXL.execute(resolution, seed, rescale, multiple, batch, mode)
    return output.result[1], output.result[2], output


def selector(aspect, megapixels=1.0, rescale=None, multiple=8, seed=0, mode="random", max_aspect=2.0, batch=1):
    output = Selector.execute(aspect, megapixels, seed, multiple, batch, max_aspect, mode, None, rescale)
    return output.result[1], output.result[2], output


def orientation(resolution):
    return {"Portrait": "portrait", "Landscape": "landscape"}.get(resolution["size"]) if resolution["resolution"] == "Random Chaos" else None


def exact_size(rescale):
    return rescale is not None and rescale["rescale"] == TO_WIDTH_HEIGHT and rescale["width"] and rescale["height"]


# Every size: positive multiples of multiple, the latent of that size and batch, the same size in the preview message, the seed passed through,
# and the same size again for the same seed in the reproducible modes.
@settings(max_examples=scaled(300))
@given(resolution=sdxl_resolutions(), rescale=rescales, multiple=multiples, batch=st.integers(1, 4), seed=seeds, mode=st.sampled_from(SEED_MODES))
def test_sdxl_sizes_are_multiples_and_reported_consistently(resolution, rescale, multiple, batch, seed, mode, latents):
    width, height, output = sdxl(resolution, rescale, multiple, seed, mode, batch)
    assert isinstance(width, int) and isinstance(height, int)
    assert width % multiple == 0 and height % multiple == 0 and width >= multiple and height >= multiple
    assert latents[-1] == (width, height, batch) and output.result[3] == seed
    last = output.ui["dice_forge_last_size"][0]
    assert (last["width"], last["height"], last["multiple"]) == (width, height, multiple)
    json.dumps(output.ui) # The preview message goes to the browser as JSON.
    if mode in REPRODUCIBLE:
        assert sdxl(resolution, rescale, multiple, seed, mode, batch)[:2] == (width, height)


@settings(max_examples=scaled(300))
@given(aspect=st.sampled_from([*ASPECT_RATIOS, *SELECTOR_LISTED, *SELECTOR_CHAOS]), megapixels=st.integers(1, 160).map(lambda k: round(k * 0.1, 1)),
       rescale=rescales, multiple=multiples, batch=st.integers(1, 4), seed=seeds, mode=st.sampled_from(SEED_MODES), max_aspect=max_aspects)
def test_selector_sizes_are_multiples_and_reported_consistently(aspect, megapixels, rescale, multiple, batch, seed, mode, max_aspect, latents):
    width, height, output = selector(aspect, megapixels, rescale, multiple, seed, mode, max_aspect, batch)
    assert isinstance(width, int) and isinstance(height, int)
    assert width % multiple == 0 and height % multiple == 0 and width >= multiple and height >= multiple
    assert latents[-1] == (width, height, batch) and output.result[3] == seed
    last = output.ui["dice_forge_last_size"][0]
    assert (last["width"], last["height"]) == (width, height)
    json.dumps(output.ui)
    if mode in REPRODUCIBLE:
        assert selector(aspect, megapixels, rescale, multiple, seed, mode, max_aspect, batch)[:2] == (width, height)


# The rescale promises, in every group (Random Chaos included): to Width/Height with both sides gives exactly that size; with one side, that side;
# to longest side, that longest side (the 1520-instead-of-1536 bug); Portrait and Landscape keep their orientation.
@settings(max_examples=scaled(300))
@given(resolution=sdxl_resolutions(), rescale=rescales, multiple=multiples, seed=seeds, mode=st.sampled_from(SEED_MODES))
def test_sdxl_rescale_promises_hold_in_every_group(resolution, rescale, multiple, seed, mode, latents):
    width, height, _ = sdxl(resolution, rescale, multiple, seed, mode)
    check_rescale_promises(width, height, rescale, multiple, orientation(resolution), resolution.get("max_aspect", 2.0))


@settings(max_examples=scaled(300))
@given(aspect=st.sampled_from([*ASPECT_RATIOS, *SELECTOR_LISTED, *SELECTOR_CHAOS]), rescale=rescales, multiple=multiples, seed=seeds,
       mode=st.sampled_from(SEED_MODES), max_aspect=max_aspects)
def test_selector_rescale_promises_hold_for_every_aspect(aspect, rescale, multiple, seed, mode, max_aspect, latents):
    width, height, _ = selector(aspect, 1.0, rescale, multiple, seed, mode, max_aspect)
    wanted = SELECTOR_CHAOS.get(aspect)
    check_rescale_promises(width, height, rescale, multiple, wanted if wanted != "any" else None, max_aspect)


def check_rescale_promises(width, height, rescale, multiple, wanted, max_aspect):
    on_grid = lambda side: side and side % multiple == 0
    if exact_size(rescale):
        if on_grid(rescale["width"]) and on_grid(rescale["height"]):
            assert (width, height) == (rescale["width"], rescale["height"])
        return # The exact size wins over the orientation.
    if rescale and rescale["rescale"] == TO_WIDTH_HEIGHT and on_grid(rescale["width"]):
        assert width == rescale["width"]
    if rescale and rescale["rescale"] == TO_WIDTH_HEIGHT and on_grid(rescale["height"]):
        assert height == rescale["height"]
    if rescale and rescale["rescale"] == TO_LONGEST_SIDE and on_grid(rescale["longer_side"]):
        assert max(width, height) == rescale["longer_side"]
    if wanted and max_aspect > 1.0 and width == height:
        # A square only when no side may move: the shorter is at the minimum or set, and the longer is set (or is the longest side).
        mode = rescale and rescale["rescale"]
        set_width = mode == TO_WIDTH_HEIGHT and bool(rescale["width"])
        set_height = mode == TO_WIDTH_HEIGHT and bool(rescale["height"])
        shorter_set, longer_set = (set_width, set_height) if wanted == "portrait" else (set_height, set_width)
        assert (width == multiple or shorter_set) and (longer_set or mode == TO_LONGEST_SIDE), (width, height)
    elif wanted and max_aspect > 1.0:
        assert (width < height) if wanted == "portrait" else (width > height), (width, height)


# Random Chaos: within the pixel budget (rounded down), the aspect ratio within max_aspect (give or take the rounding), every orientation obeyed.
@settings(max_examples=scaled(300))
@given(size=st.sampled_from(RANDOM_CHAOS), max_aspect=max_aspects, percent=percents, multiple=multiples, seed=seeds, mode=st.sampled_from(SEED_MODES))
def test_chaos_stays_within_budget_and_aspect(size, max_aspect, percent, multiple, seed, mode, latents):
    resolution = {"resolution": "Random Chaos", "size": size, "max_aspect": max_aspect}
    width, height, _ = sdxl(resolution, {"rescale": BY_PERCENTAGE, "percent": percent}, multiple, seed, mode)
    budget = CHAOS_PIXELS * (percent / 100) ** 2
    if min(width, height) == multiple:
        return # The smallest size there is: it can't stay within a smaller budget (and Portrait/Landscape step the longer side up from it).
    assert width * height <= budget * 1.000001
    exact_long = math.sqrt(budget * max_aspect) # The longest a side can be at max_aspect.
    assert max(width, height) <= exact_long + 1e-6
    slack = math.log((min(width, height) + 2 * multiple) / min(width, height))
    assert abs(math.log(width / height)) <= math.log(max_aspect) + slack


@settings(max_examples=scaled(200))
@given(width=st.floats(1, 20000), height=st.floats(1, 20000), multiple=multiples, round_down=st.booleans())
@example(width=1020.0, height=1020.0, multiple=8, round_down=False)
@example(width=1536.0, height=1047.9999999999, multiple=8, round_down=True)
def test_round_to_multiple_is_the_closest_ratio_on_the_grid(width, height, multiple, round_down):
    w, h = SDXL.round_to_multiple(width, height, multiple, round_down)
    assert w % multiple == 0 and h % multiple == 0 and w >= multiple and h >= multiple
    for side, value in ((w, width), (h, height)):
        below = max(multiple, math.floor(value / multiple) * multiple)
        above = max(multiple, math.ceil(value / multiple) * multiple)
        assert side in ((below,) if round_down else (below, above))
    candidates = lambda value: {max(multiple, math.floor(value / multiple) * multiple)} | (set() if round_down else {max(multiple, math.ceil(value / multiple) * multiple)})
    best = min(round(abs(math.log(a / b) - math.log(width / height)), 9) for a in candidates(width) for b in candidates(height))
    assert round(abs(math.log(w / h) - math.log(width / height)), 9) == best # No pair on the grid keeps the ratio better.
    assert SDXL.round_to_multiple(height, width, multiple, round_down) == (h, w) # Turning the size turns the result.


@settings(max_examples=scaled(200))
@given(ratio=st.sampled_from(list(ASPECT_RATIOS.values())), megapixels=st.integers(1, 160).map(lambda k: round(k * 0.1, 1)), multiple=multiples, percent=percents)
def test_selector_sizes_follow_megapixels_and_ratio(ratio, megapixels, multiple, percent):
    width, height = Selector.size_for_ratio(*ratio, megapixels, multiple, rescale={"rescale": BY_PERCENTAGE, "percent": percent})
    scale = math.sqrt(megapixels * 1024 * 1024 / (ratio[0] * ratio[1])) * percent / 100
    for side, exact in ((width, ratio[0] * scale), (height, ratio[1] * scale)):
        assert abs(side - exact) <= multiple / 2 + 1e-9 or side == multiple # Each side rounded to the nearest multiple.
    down = Selector.size_for_ratio(*ratio, megapixels, multiple, round_down=True, rescale={"rescale": BY_PERCENTAGE, "percent": percent})
    assert down[0] <= max(multiple, width) and down[1] <= max(multiple, height)


@given(group=st.sampled_from(list(RANDOM_LISTED)), seed=seeds, mode=st.sampled_from(SEED_MODES))
def test_random_listed_sizes_come_from_their_list(group, seed, mode, latents):
    width, height, _ = sdxl({"resolution": "Random", "size": group}, None, 8, seed, mode)
    assert (width, height) in RANDOM_LISTED[group]


@given(group=st.sampled_from(list(RANDOM_LISTED)), first=st.integers(0, 10 ** 9))
def test_deck_and_sequential_go_through_the_whole_list(group, first, latents):
    sizes = RANDOM_LISTED[group]
    for mode in ("deck", "sequential"):
        start = first * len(sizes)
        dealt = [sdxl({"resolution": "Random", "size": group}, None, 8, seed, mode)[:2] for seed in range(start, start + len(sizes))]
        assert sorted(dealt) == sorted(sizes)


# Random Int / Float / Sampler.
@settings(max_examples=scaled(300))
@given(low=st.integers(-2 ** 64, 2 ** 64), high=st.integers(-2 ** 64, 2 ** 64), step=st.one_of(st.integers(1, 10), st.integers(1, 2 ** 64)), seed=seeds,
       mode=st.sampled_from(SEED_MODES))
def test_random_int_is_in_range_and_on_the_step(low, high, step, seed, mode):
    value = RandomInt.execute(low, high, step, seed, mode).result[0]
    bottom, top = sorted((low, high))
    assert isinstance(value, int) and bottom <= value <= top and (value - bottom) % step == 0


@given(low=st.integers(-50, 50), span=st.integers(0, 30), step=st.integers(1, 4), first=st.integers(0, 10 ** 6))
def test_random_int_deck_and_sequential_cover_every_value(low, span, step, first):
    values = list(range(low, low + span + 1, step))
    for mode in ("deck", "sequential"):
        start = first * len(values)
        assert sorted(RandomInt.execute(low, low + span, step, seed, mode).result[0] for seed in range(start, start + len(values))) == values


@settings(max_examples=scaled(300))
@given(low=st.floats(-1e9, 1e9), high=st.floats(-1e9, 1e9), step=st.one_of(st.just(0.0), st.floats(1e-6, 1e9)), parts=st.integers(2, 1000), seed=seeds,
       mode=st.sampled_from(SEED_MODES))
@example(low=0.0, high=1.0, step=0.1, parts=10, seed=10, mode="sequential")
@example(low=0.1, high=0.7, step=0.2, parts=10, seed=3, mode="sequential")
def test_random_float_is_in_range_and_on_the_step(low, high, step, parts, seed, mode):
    value = RandomFloat.execute(low, high, step, seed, mode, parts).result[0]
    bottom, top = sorted((low, high))
    tolerance = 1e-9 * max(1.0, abs(bottom), abs(top))
    assert isinstance(value, float) and math.isfinite(value)
    assert bottom - tolerance <= value <= top + tolerance, (value, bottom, top)
    if step > 0:
        nearest = bottom + round((value - bottom) / step) * step
        assert abs(value - nearest) <= 1e-10 + tolerance # On the step grid, give or take the rounding to 10 decimals.


@given(samplers=st.lists(st.sampled_from(SAMPLERS), min_size=1, max_size=6), schedulers=st.lists(st.sampled_from(SCHEDULERS), min_size=1, max_size=4),
       joins=st.sampled_from([", ", ",", "\n", " ,\n "]), seed=seeds, mode=st.sampled_from(SEED_MODES))
def test_random_sampler_picks_a_listed_pair(samplers, schedulers, joins, seed, mode):
    sampler, scheduler, label, *_ = RandomSampler.execute(joins.join(samplers), joins.join(schedulers), seed, mode).result
    assert sampler in samplers and scheduler in schedulers and label == f"{sampler} / {scheduler}"


@given(text=st.text(max_size=40), seed=seeds)
def test_random_sampler_with_any_text_picks_a_real_sampler_or_says_why(text, seed):
    try:
        sampler, scheduler, *_ = RandomSampler.execute(text, "*", seed, "random").result
    except ValueError as error:
        assert "Random Sampler" in str(error)
        return
    assert sampler in SAMPLERS and scheduler in SCHEDULERS


def test_random_sampler_deck_goes_through_every_pair():
    pairs = {RandomSampler.execute("euler, dpmpp_2m, ddim", "normal, karras", seed, "deck").result[2] for seed in range(6)}
    assert len(pairs) == 6


@settings(max_examples=scaled(60))
@given(names=st.lists(st.text(alphabet="abcxyz", min_size=1, max_size=5), min_size=1, max_size=6, unique=True),
       folders=st.lists(st.sampled_from(["", "a/", "a/b/", "c/"]), min_size=6, max_size=6), seed=seeds, mode=st.sampled_from(SEED_MODES), include_none=st.booleans())
def test_random_lora_picks_a_file_of_the_folder(names, folders, seed, mode, include_none, models, monkeypatch):
    monkeypatch.setattr(RandomLoraLoader.loader, "load_lora", lambda model, clip, name, sm, sc: (model, clip))
    for existing in list((models.root / "loras").rglob("*.safetensors")):
        existing.unlink() # The model folder lives for the whole test: start each example empty.
    files = [folders[index] + name + ".safetensors" for index, name in enumerate(names)]
    for name in files:
        models("loras", name)
    for folder in ("(all)", "a", "a/b", "c"):
        inside = [name for name in files if folder == "(all)" or name.startswith(folder + "/")]
        if not inside:
            with pytest.raises(ValueError, match="No LoRA files"):
                RandomLoraLoader.execute("model", folder, 1.0, 1.0, seed, mode, include_none, None)
            continue
        name = RandomLoraLoader.execute("model", folder, 1.0, 1.0, seed, mode, include_none, None).result[2]
        assert name in inside or (include_none and name == "")


# LoRA Stack: any stack data is parsed or refused with a clear error, strengths stay in their range on the 0.05 grid, groups use min to max rows.
junk = st.recursive(st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False), st.text(max_size=8)),
                    lambda children: st.one_of(st.lists(children, max_size=4), st.dictionaries(st.text(max_size=8), children, max_size=4)), max_leaves=12)
row_junk = st.fixed_dictionaries({}, optional={"lora": st.one_of(st.text(max_size=6), st.integers(), st.none()), "on": junk, "strength": junk, "clip": junk,
                                               "random": junk, "min": junk, "max": junk, "group": st.one_of(st.sampled_from(["", "A", "B", "Z"]), junk),
                                               "triggers": st.one_of(st.sampled_from(["all", "none", "custom"]), junk), "trigger_words": junk})
stack_junk = st.one_of(junk, st.fixed_dictionaries({}, optional={"rows": st.one_of(junk, st.lists(st.one_of(row_junk, junk), max_size=5)),
                                                                 "groups": st.one_of(junk, st.dictionaries(st.sampled_from(["A", "B", "Z"]), junk)),
                                                                 "separate_clip": junk}))


@settings(max_examples=scaled(400))
@given(data=stack_junk, seed=seeds, mode=st.sampled_from(SEED_MODES))
def test_any_stack_data_runs_or_fails_with_a_clear_error(data, seed, mode, models, monkeypatch):
    models("loras", "a.safetensors")
    monkeypatch.setattr(lora_stack.comfy.sd, "load_lora_for_models", lambda model, clip, lora, sm, sc, lora_metadata=None: (model, clip))
    monkeypatch.setattr(LoraStack, "load", classmethod(lambda cls, path: ({}, {})))
    text = json.dumps(data)
    try:
        model, clip, triggers, info = LoraStack.execute([], text, seed, mode, []).result
    except ValueError as error:
        assert str(error).startswith("LoRA Stack")
        return
    assert isinstance(triggers, str) and isinstance(info, str)


@given(text=st.text(max_size=30))
def test_any_text_as_stack_data_is_parsed_or_refused_clearly(text):
    try:
        rows, groups, separate = parse_stack(text)
    except ValueError as error:
        assert str(error).startswith("LoRA Stack")
        return
    assert isinstance(rows, list) and isinstance(groups, dict) and isinstance(separate, bool)
    assert all(isinstance(row, dict) and isinstance(row["lora"], str) and row["lora"] for row in rows)


strengths = st.integers(-400, 400).map(lambda k: round(k * 0.05, 2))


@given(low=strengths, high=strengths, seed=seeds, mode=st.sampled_from(SEED_MODES))
def test_random_strength_stays_in_range_on_the_grid(low, high, seed, mode):
    from DiceForge.seed_modes import make_picker
    value = row_strength({"lora": "x", "random": True, "min": low, "max": high}, make_picker(mode, seed), seed)
    bottom, top = sorted((low, high))
    assert bottom - 1e-9 <= value <= top + 1e-9
    assert abs((value - bottom) / 0.05 - round((value - bottom) / 0.05)) < 1e-6


@given(low=strengths, span=st.integers(0, 59), reverse=st.booleans(), first=st.integers(0, 10 ** 6))
def test_random_strength_deck_deals_every_value(low, span, reverse, first):
    bottom, top = low, round(low + span * 0.05, 2)
    low, high = (top, bottom) if reverse else (bottom, top) # min above max still works.
    count = span + 1
    start = first * count
    dealt = sorted(row_strength({"lora": "x", "random": True, "min": low, "max": high}, DeckPicker(random.Random(seed), seed, {}), seed) for seed in range(start, start + count))
    assert dealt == [round(bottom + index * 0.05, 4) for index in range(count)]


@given(size=st.integers(0, 8), low=st.one_of(st.integers(-3, 10), st.none(), st.text(max_size=2)), high=st.one_of(st.integers(-3, 10), st.none(), st.text(max_size=2)),
       seed=seeds, mode=st.sampled_from(SEED_MODES))
def test_group_uses_min_to_max_different_rows(size, low, high, seed, mode):
    from DiceForge.seed_modes import make_picker
    rows = [{"lora": f"r{index}"} for index in range(size)]
    chosen = group_pick("A", rows, {"min": low, "max": high}, make_picker(mode, seed), seed)
    assert len({row["lora"] for row in chosen}) == len(chosen) and all(row in rows for row in chosen)
    floor = max(0, int(lora_stack.number(low, 1))) # Numbers in text count ("2"), anything else is the default.
    ceiling = max(floor, int(lora_stack.number(high, floor)))
    assert min(floor, size) <= len(chosen) <= min(ceiling, size)
    assert [rows.index(row) for row in chosen] == sorted(rows.index(row) for row in chosen) # Stack order kept.


def test_a_huge_group_is_refused_quickly():
    import time
    rows = [{"lora": f"r{index}"} for index in range(40)]
    started = time.perf_counter()
    with pytest.raises(ValueError, match="too many combinations"):
        group_pick("A", rows, {"min": 0, "max": 40}, None, 0)
    assert time.perf_counter() - started < 2 # Counted, not listed: 2^40 combinations would never finish.


# Dice Grid: any labels (long words, emoji, other scripts, line breaks), any count of cells and columns: an image with every cell inside it.
labels = st.text(max_size=60)


@settings(max_examples=scaled(60))
@given(cells=st.lists(st.tuples(labels, st.one_of(st.just(""), st.text(max_size=12)), st.integers(16, 96)), min_size=1, max_size=9), columns=st.integers(0, 5),
       cell_width=st.integers(32, 160), legend=st.text(max_size=80), position=st.sampled_from(dice_grid.LEGEND_POSITIONS), numbered=st.booleans())
def test_grid_renders_any_labels(cells, columns, cell_width, legend, position, numbered):
    from PIL import Image
    items = [{"label": label, "row": row, "image": Image.new("RGB", (cell_width, height), (200, 10, 10))} for label, row, height in cells]
    grid = dice_grid.render(items, columns, cell_width, legend, position, numbered)
    assert grid.mode == "RGB" and grid.width >= cell_width and grid.height >= max(height for _, _, height in cells)
    red = int(np.all(np.asarray(grid) == (200, 10, 10), axis=-1).sum())
    distinct = {(row, label) for label, row, _ in cells} if any(row for _, row, _ in cells) else None
    if distinct is None:
        assert red >= sum(cell_width * height for _, _, height in cells) * 0.95 # Every cell is in the grid (text may cover a few pixels).


@given(label=st.text(max_size=80))
def test_clean_label_never_fails(label):
    cleaned = dice_grid.clean_label(label)
    assert isinstance(cleaned, str) and "/" not in cleaned.rsplit("/", 1)[-1] and len(cleaned) <= len(label)


# Names from the browser or a preset never reach outside their folder.
@given(name=st.text(max_size=40))
@example(name="../../x")
@example(name="..")
@example(name="/etc/passwd")
@example(name="a/../../b")
@example(name="C:\\x")
def test_model_info_files_stay_in_their_folder(name):
    for kind in model_info.KINDS:
        root = os.path.abspath(os.path.join(model_info.INFO_FOLDER, kind))
        try:
            path = model_info.info_file(kind, name)
        except web.HTTPBadRequest:
            continue
        except ValueError:
            assert "\x00" in name # Only a NUL byte, which no file name has.
            continue
        assert path.startswith(root + os.sep)


@given(name=st.text(max_size=40))
@example(name="../evil")
@example(name=".hidden")
@example(name="a\\..\\b")
def test_preset_files_stay_in_their_folder(name):
    try:
        clean, path = preset_path(name)
    except web.HTTPBadRequest:
        return
    assert os.path.dirname(path) == lora_stack.PRESET_FOLDER and not clean.startswith(".") and "/" not in clean and "\\" not in clean


@given(name=st.text(max_size=40))
@example(name="../x")
@example(name="a/../../x")
@example(name="a//b")
def test_wildcard_names_stay_in_their_folder(name):
    try:
        clean = wildcards_api.checked_name(name)
    except web.HTTPBadRequest:
        return
    assert ".." not in clean.split("/") and not clean.startswith("/") and "\\" not in clean
    root = os.path.abspath("/wildcards")
    assert os.path.abspath(os.path.join(root, *clean.split("/")) + ".txt").startswith(root + os.sep)
