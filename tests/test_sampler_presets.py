import json
import comfy.samplers
import pytest
from DiceForge import sampler_presets


def preset(**changes):
    return {"name": "Mine", "steps": 24, "cfg": 5.5, "sampler_name": "euler", "scheduler": "karras", **changes}


def test_builtin_presets_use_samplers_and_schedulers_of_comfyui():
    names = [item["name"] for item in sampler_presets.BUILTIN]
    assert names == ["Anima", "Anima Turbo", "Illustrious", "NoobAI (eps)", "NoobAI (v-pred)"]
    for item in sampler_presets.BUILTIN:
        assert sampler_presets.checked(item) == {key: item[key] for key in ("name", *sampler_presets.FIELDS)}
        assert item["note"]
    vpred = next(item for item in sampler_presets.BUILTIN if item["name"] == "NoobAI (v-pred)")
    assert vpred["sampler_name"] == "euler" and "karras" not in vpred["scheduler"]


@pytest.mark.parametrize("change", [{"name": ""}, {"name": "   "}, {"name": "x" * 61}, {"name": 5}, {"steps": 0}, {"steps": 10001}, {"steps": True},
                                    {"steps": 2.5}, {"cfg": -1}, {"cfg": 101}, {"cfg": "5"}, {"cfg": False}, {"sampler_name": "nope"},
                                    {"scheduler": "nope"}, {"scheduler": None}])
def test_bad_presets_are_refused(change):
    assert sampler_presets.checked(preset(**change)) is None


def test_checked_trims_the_name_and_rounds_cfg():
    assert sampler_presets.checked(preset(name="  Mine  ", cfg=5.556, extra=1)) == preset(cfg=5.56)
    assert sampler_presets.checked("text") is None


def test_list_save_replace_and_delete(api):
    status, answer = api("GET", "/diceforge/sampler-presets")
    assert status == 200 and answer["user"] == [] and [item["name"] for item in answer["builtin"]][0] == "Anima"
    assert api("POST", "/diceforge/sampler-presets", json=preset(name="b"))[0] == 200
    assert api("POST", "/diceforge/sampler-presets", json=preset(name="A", steps=30))[0] == 200
    assert api("POST", "/diceforge/sampler-presets", json=preset(name="a", steps=12))[1]["steps"] == 12 # The same name, other case: replaced.
    assert [(item["name"], item["steps"]) for item in api("GET", "/diceforge/sampler-presets")[1]["user"]] == [("a", 12), ("b", 24)]
    assert api("DELETE", "/diceforge/sampler-presets?name=A")[0] == 200
    assert [item["name"] for item in api("GET", "/diceforge/sampler-presets")[1]["user"]] == ["b"]
    status, text = api("DELETE", "/diceforge/sampler-presets?name=A")
    assert status == 404 and "no preset" in text


def test_builtin_names_cant_be_taken(api):
    status, text = api("POST", "/diceforge/sampler-presets", json=preset(name="illustrious"))
    assert status == 409 and "built-in" in text
    assert api("POST", "/diceforge/sampler-presets", json=preset(sampler_name="nope"))[0] == 400


def test_a_damaged_file_reads_as_no_presets_and_bad_lines_are_skipped():
    with open(sampler_presets.PRESETS_FILE, "w", encoding="utf-8") as file:
        file.write("{not json")
    assert sampler_presets.read_presets() == []
    with open(sampler_presets.PRESETS_FILE, "w", encoding="utf-8") as file:
        json.dump([preset(), preset(name="bad", steps=0), "x", None], file)
    assert sampler_presets.read_presets() == [preset()]
    with open(sampler_presets.PRESETS_FILE, "w", encoding="utf-8") as file:
        json.dump({"name": "x"}, file)
    assert sampler_presets.read_presets() == []


def test_every_comfyui_sampler_and_scheduler_can_be_saved():
    for sampler in comfy.samplers.KSampler.SAMPLERS:
        assert sampler_presets.checked(preset(sampler_name=sampler))
    for scheduler in comfy.samplers.KSampler.SCHEDULERS:
        assert sampler_presets.checked(preset(scheduler=scheduler))
