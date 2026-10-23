# LoRA Stack (DiceForge/lora_stack.py): rows, random strengths, groups, trigger words, what gets applied, presets, and its server routes. The core
# LoRA patching is replaced by a stand-in that records each call, so the tests need no real model.
import json
import os
import random
import pytest
from aiohttp import web
from DiceForge import lora_stack, model_info
from DiceForge.lora_stack import LoraStack, group_pick, parse_stack, preset_path, preset_stack, row_strength, row_triggers
from DiceForge.seed_modes import DeckPicker, RandomPicker


@pytest.fixture
def applied(monkeypatch):
    calls = []

    def fake_apply(model, clip, lora, strength_model, strength_clip, lora_metadata=None):
        calls.append((lora["name"], strength_model, strength_clip))
        return model + [lora["name"]], (clip + [lora["name"]] if clip is not None else None)
    monkeypatch.setattr(lora_stack.comfy.sd, "load_lora_for_models", fake_apply)
    monkeypatch.setattr(LoraStack, "load", classmethod(lambda cls, path: ({"name": os.path.basename(path)}, {})))
    return calls


@pytest.fixture
def loras(models):
    for name in ("detail.safetensors", "style/a.safetensors", "style/b.safetensors", "style/c.safetensors"):
        models("loras", name)
    return models


def stack(*rows, groups=None, separate_clip=False):
    return json.dumps({"rows": list(rows), "groups": groups or {}, "separate_clip": separate_clip})


def run(text, seed=0, mode="random", clip=True):
    return LoraStack.execute([], text, seed, mode, [] if clip else None).result


def test_parse_stack_keeps_rows_with_a_lora():
    rows, groups, separate = parse_stack(stack({"lora": "a"}, {"strength": 1}, "junk", groups={"A": {"min": 1}}, separate_clip=True))
    assert rows == [{"lora": "a"}] and groups == {"A": {"min": 1}} and separate is True
    assert parse_stack("") == ([], {}, False)
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_stack("{oops")


def test_fixed_and_random_strengths():
    assert row_strength({"lora": "x", "strength": 0.7}, None, 0) == 0.7
    row = {"lora": "x", "random": True, "min": 0.9, "max": 0.5}
    dealt = sorted(row_strength(row, DeckPicker(random.Random(seed), seed, {}), seed) for seed in range(9))
    assert dealt == [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
    assert [row_strength(row, None, seed) for seed in range(3)] == [0.5, 0.55, 0.6]
    assert row_strength({"lora": "x", "random": True, "min": 0.6, "max": 0.6}, None, 5) == 0.6


def test_group_pick_deals_every_combination():
    rows = [{"lora": name} for name in "abc"]
    dealt = {tuple(row["lora"] for row in group_pick("A", rows, {"min": 1, "max": 2}, DeckPicker(random.Random(seed), seed, {}), seed)) for seed in range(6)}
    assert dealt == {("a",), ("b",), ("c",), ("a", "b"), ("a", "c"), ("b", "c")}
    assert group_pick("A", rows, {"min": 0, "max": 0}, None, 0) == []
    assert len(group_pick("A", rows, {"min": 5, "max": 9}, None, 0)) == 3 # Clamped to the rows there are.


def test_a_group_too_big_to_list_is_an_error(monkeypatch):
    monkeypatch.setattr(lora_stack, "SUBSET_LIMIT", 10)
    with pytest.raises(ValueError, match="too many combinations"):
        group_pick("B", [{"lora": str(index)} for index in range(8)], {"min": 1, "max": 3}, RandomPicker(random.Random(0)), 0)


def test_rows_apply_in_order_and_report_what_was_applied(loras, applied):
    model, clip, triggers, info = run(stack({"lora": "detail.safetensors", "strength": 0.8}, {"lora": "style/a.safetensors", "strength": 1}))
    assert model == ["detail.safetensors", "a.safetensors"] and clip == model
    assert applied == [("detail.safetensors", 0.8, 0.8), ("a.safetensors", 1.0, 1.0)]
    assert info == "detail 0.8, a 1"


def test_off_rows_zero_strength_and_separate_clip(loras, applied):
    text = stack({"lora": "detail.safetensors", "on": False}, {"lora": "style/a.safetensors", "strength": 0, "clip": 0}, {"lora": "style/b.safetensors", "strength": 0.9, "clip": 0.4},
                 {"lora": "style/c.safetensors", "strength": 0, "clip": 0.5}, separate_clip=True)
    _, _, _, info = run(text)
    assert applied == [("b.safetensors", 0.9, 0.4), ("c.safetensors", 0.0, 0.5)] # Model strength 0 with a CLIP strength: the CLIP only.
    assert info == "a 0, b 0.9/0.4, c 0/0.5"


def test_without_clip_only_the_model_changes(loras, applied):
    _, clip, _, _ = run(stack({"lora": "detail.safetensors", "strength": 0.5}), clip=False)
    assert clip is None and applied == [("detail.safetensors", 0.5, 0)]


def test_groups_take_turns_with_deck(loras, applied):
    rows = [{"lora": "detail.safetensors"}] + [{"lora": f"style/{name}.safetensors", "group": "A"} for name in "abc"]
    infos = [run(stack(*rows, groups={"A": {"min": 1, "max": 1}}), seed=seed, mode="deck")[3] for seed in range(3)]
    assert sorted(info.split(", ")[1] for info in infos) == ["a 1", "b 1", "c 1"]
    assert all(info.startswith("detail 1") for info in infos)


def test_a_missing_lora_file_is_a_clear_error(loras, applied):
    with pytest.raises(ValueError, match="gone.safetensors is not in the loras folders"):
        run(stack({"lora": "gone.safetensors"}))


def test_trigger_words_per_row(loras, applied):
    model_info.write_info("loras", "style/a.safetensors", {"civitai": {"trigger_words": ["pony style", "score_9", "masterpiece"]}})
    model_info.write_info("loras", "style/b.safetensors", {"user": {"trigger_words": "bstyle, ink"}, "civitai": {"trigger_words": ["b_civitai"]}})
    a, b = {"lora": "style/a.safetensors"}, {"lora": "style/b.safetensors"}
    assert row_triggers(a) == ["pony style", "score_9", "masterpiece"]
    assert row_triggers(b) == ["bstyle", "ink"] # Your own words come before Civitai's.
    assert row_triggers({**a, "triggers": "none"}) == []
    assert row_triggers({**a, "triggers": "custom", "trigger_words": ["score_9", " glossy ", ""]}) == ["score_9", "glossy"]
    _, _, triggers, _ = run(stack({**a, "triggers": "custom", "trigger_words": ["ink", "glossy"]}, b))
    assert triggers == "ink, glossy, bstyle" # Each word once.


def test_the_node_runs_again_when_model_info_changes(loras):
    text = stack({"lora": "style/a.safetensors"})
    before = LoraStack.fingerprint_inputs(text)
    model_info.write_info("loras", "style/a.safetensors", {"user": {"trigger_words": "new"}})
    path = model_info.info_file("loras", "style/a.safetensors")
    os.utime(path, (os.path.getmtime(path) + 10,) * 2)
    assert LoraStack.fingerprint_inputs(text) != before


def test_loras_no_longer_used_leave_memory(loras, monkeypatch):
    LoraStack.cache.clear()
    # The real load, with its cache: the files here are not real LoRAs, so reading them is replaced one level lower.
    monkeypatch.setattr(lora_stack.comfy.utils, "load_torch_file", lambda path, safe_load=True, return_metadata=False: ({"name": os.path.basename(path)}, {}))
    monkeypatch.setattr(lora_stack.comfy.sd, "load_lora_for_models", lambda model, clip, lora, sm, sc, lora_metadata=None: (model, clip))
    run(stack({"lora": "detail.safetensors"}, {"lora": "style/a.safetensors"}))
    assert len(LoraStack.cache) == 2
    run(stack({"lora": "detail.safetensors"}))
    assert [os.path.basename(path) for path in LoraStack.cache] == ["detail.safetensors"]


def test_preset_names_and_contents():
    assert preset_path("my set (v2)")[0] == "my set (v2)"
    assert preset_path("styles.json")[0] == "styles"
    for bad in ("../evil", "a/b", ".hidden", ""):
        with pytest.raises(web.HTTPBadRequest) as error:
            preset_path(bad)
        assert "not a usable preset name" in error.value.text
    rows = [{"lora": "a"}, {"nope": 1}]
    assert preset_stack({"stack": {"rows": rows}})["rows"] == [{"lora": "a"}]
    assert preset_stack({"rows": rows, "separate_clip": 1})["separate_clip"] is True
    with pytest.raises(web.HTTPBadRequest) as error:
        preset_stack({"hello": 1})
    assert "not a LoRA Stack preset" in error.value.text


def test_preset_routes(api):
    body = {"name": "my set", "stack": {"rows": [{"lora": "style/a.safetensors", "strength": 0.7}], "groups": {"A": {"min": 1, "max": 1}}}}
    assert api("POST", "/diceforge/lora-presets", body)[0] == 200
    status, listing = api("GET", "/diceforge/lora-presets")
    assert status == 200 and [p["name"] for p in listing["presets"]] == ["my set"] and listing["presets"][0]["loras"] == ["style/a.safetensors"]
    status, preset = api("GET", "/diceforge/lora-presets/file?name=my%20set")
    assert preset["stack"]["rows"][0]["strength"] == 0.7
    assert api("POST", "/diceforge/lora-presets", body)[0] == 409 # Exists: asks first.
    assert api("POST", "/diceforge/lora-presets", {**body, "overwrite": True})[0] == 200
    assert api("POST", "/diceforge/lora-presets", {"name": "broken", "stack": {"hello": 1}})[0] == 400
    for device in ("con", "NUL", "com1.backup"): # Windows device names: the "file" would be the device, so nothing is saved.
        assert api("POST", "/diceforge/lora-presets", {"name": device, "stack": body["stack"]})[0] == 400
    assert not os.path.exists(preset_path("broken")[1]) # Nothing written for a refused preset.
    assert api("POST", "/diceforge/lora-presets", {"name": "../evil", "stack": {"rows": []}})[0] == 400
    assert api("DELETE", "/diceforge/lora-presets?name=my%20set")[0] == 200
    assert api("GET", "/diceforge/lora-presets/file?name=my%20set")[0] == 404


def test_base_models_and_trigger_word_routes(api, loras):
    path = os.path.join(loras.root, "loras", "style", "a.safetensors")
    stat = os.stat(path)
    model_info.write_info("loras", "style/a.safetensors", {"size": stat.st_size, "mtime": stat.st_mtime, "civitai": {"base_model": "Pony", "trigger_words": ["p"]}, "user": {"trigger_words": "mine"}})
    model_info.write_info("loras", "style/b.safetensors", {"size": 1, "mtime": 1, "civitai": {"base_model": "Illustrious"}}) # Stale: the file changed since.
    status, body = api("POST", "/diceforge/model-bases", {"items": [{"kind": "loras", "file": "style/a.safetensors"}, {"kind": "loras", "file": "style/b.safetensors"}, {"kind": "nope", "file": "x"}]})
    assert status == 200 and body["bases"] == ["Pony", None, None]
    status, body = api("POST", "/diceforge/lora-triggers", {"loras": ["style/a.safetensors", "detail.safetensors"]})
    assert body["triggers"] == [{"user": ["mine"], "civitai": ["p"]}, {"user": [], "civitai": []}]
