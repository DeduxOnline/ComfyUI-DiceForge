# XY Plot (DiceForge/xy_plot.py): the axis values typed in its fields, the cell of each run, the labels for Dice Grid, the LoRA and the preview route.
import pytest
from DiceForge import xy_plot
from DiceForge.random_sampler import SAMPLERS, SCHEDULERS
from DiceForge.xy_plot import XYPlot, parse_numbers, plan


@pytest.fixture
def lora_calls(monkeypatch):
    """A stand-in for the core LoRA loader: each call is recorded as (file, strength model, strength clip)."""
    calls = []
    monkeypatch.setattr(XYPlot.loader, "load_lora", lambda model, clip, name, sm, sc: (calls.append((name, sm, sc)) or (f"{model}+{name}", clip and f"{clip}+{name}")))
    return calls


def run(index, **inputs):
    values = {"x_type": "cfg", "x_values": "4, 5.5, 7", "y_type": "sampler", "y_values": "euler, dpmpp_2m", "seed": 7, "steps": 20, "cfg": 6.0,
              "sampler_name": "euler", "scheduler": "normal", **inputs}
    return dict(zip(["model", "clip", "seed", "steps", "cfg", "sampler_name", "scheduler", "denoise", "x_label", "y_label", "count", "columns", "new_grid"],
                    XYPlot.execute(index=index, **values).result))


def test_numbers_lists_and_ranges():
    assert parse_numbers("4, 5.5\n7", "cfg") == [4, 5.5, 7]
    assert parse_numbers("3.5-5:0.5", "cfg") == [3.5, 4.0, 4.5, 5.0]
    assert parse_numbers("8-6", "steps") == [8, 7, 6] # Downwards too.
    assert parse_numbers("-1..1:0.5", "lora strength") == [-1.0, -0.5, 0.0, 0.5, 1.0]
    assert parse_numbers("18446744073709551615, 1-3, 2", "seed") == [18446744073709551615, 1, 2, 3] # Exact, duplicates dropped.
    assert parse_numbers("0.1-0.3:0.1", "denoise") == [0.1, 0.2, 0.3] # No 0.30000000000000004.


@pytest.mark.parametrize("text, axis, message", [("4.5", "steps", "whole numbers"), ("0", "steps", "out of range"), ("1.5", "denoise", "out of range"),
                                                  ("abc", "cfg", "not a number"), ("1-5:0", "cfg", "step of"), ("1-1000", "seed", "more than 64"),
                                                  ("1e999", "cfg", "not a number"), ("nan", "cfg", "not a number"), ("0-1e999", "cfg", "not a number"),
                                                  ("0-" + "9" * 400 + ".5", "cfg", "not a usable number"), ("0-" + "9" * 400, "seed", "too many values")])
def test_bad_numbers_say_what_is_wrong(text, axis, message):
    with pytest.raises(ValueError, match=message):
        parse_numbers(text, axis)


def test_names_and_loras(models):
    for name in ("style/ink.safetensors", "style/glow.safetensors", "detail.safetensors"):
        models("loras", name)
    assert xy_plot.axis_values("sampler", "*") == list(SAMPLERS)
    assert xy_plot.axis_values("scheduler", "karras, normal") == ["karras", "normal"]
    assert xy_plot.axis_values("lora", "style/*, None, detail") == ["style/glow.safetensors", "style/ink.safetensors", "None", "detail.safetensors"]
    assert xy_plot.axis_values("lora", "ink.safetensors") == ["style/ink.safetensors"] # By file name alone.
    with pytest.raises(ValueError, match="no LoRA matches 'nope'"):
        xy_plot.axis_values("lora", "nope")
    with pytest.raises(ValueError, match="XY Plot: unknown sampler"):
        xy_plot.axis_values("sampler", "euler, nope")


def test_plan_counts_and_refuses_bad_axes():
    assert plan("cfg", "4, 5", "steps", "20, 30, 40")["count"] == 6
    assert plan("none", "", "cfg", "4, 5") == {"x_type": "cfg", "y_type": "none", "xs": [4, 5], "ys": [None], "count": 2} # Y alone: one row.
    assert plan("none", "", "none", "")["count"] == 1
    with pytest.raises(ValueError, match="both cfg"):
        plan("cfg", "4", "cfg", "5")
    with pytest.raises(ValueError, match="more than 256"):
        plan("seed", "1-64", "steps", "1-5")


def test_each_run_is_one_cell_row_by_row():
    cells = [run(index) for index in range(6)]
    assert [(cell["cfg"], cell["sampler_name"]) for cell in cells] == [(4, "euler"), (5.5, "euler"), (7, "euler"), (4, "dpmpp_2m"), (5.5, "dpmpp_2m"), (7, "dpmpp_2m")]
    assert [(cell["x_label"], cell["y_label"]) for cell in cells[:2]] == [("CFG 4", "euler"), ("CFG 5.5", "euler")]
    assert all(cell["count"] == 6 and cell["columns"] == 3 for cell in cells)
    assert [cell["new_grid"] for cell in cells] == [True, False, False, False, False, False]
    assert all(cell["seed"] == 7 and cell["steps"] == 20 and cell["scheduler"] == "normal" for cell in cells) # The rest stays.
    assert run(6) == cells[0] # Past the end: round again.


def test_seed_has_no_control_after_generate():
    # ▶ Queue queues the cells one by one: a control after generate (the frontend's default for an input named seed) would give each cell
    # another seed.
    seed = next(item for item in XYPlot.define_schema().inputs if item.id == "seed")
    assert seed.as_dict()["control_after_generate"] is False


def test_labels_of_each_axis():
    assert run(1, x_type="seed", x_values="10, 11", y_type="none")["x_label"] == "seed 11"
    assert run(0, x_type="steps", x_values="30", y_type="denoise", y_values="0.5")["x_label"] == "30 steps"
    assert run(0, x_type="steps", x_values="30", y_type="denoise", y_values="0.5")["y_label"] == "denoise 0.5"
    assert run(0, x_type="scheduler", x_values=SCHEDULERS[0], y_type="none")["y_label"] == ""


def test_loras_on_an_axis_and_their_strength(models, lora_calls):
    for name in ("style/ink.safetensors", "style/glow.safetensors"):
        models("loras", name)
    cell = run(1, x_type="lora", x_values="None, style/ink", y_type="lora strength", y_values="0.5, 1", model="model", clip="clip")
    assert cell["model"] == "model+style/ink.safetensors" and cell["clip"] == "clip+style/ink.safetensors" and cell["x_label"] == "style/ink.safetensors"
    assert lora_calls == [("style/ink.safetensors", 0.5, 0.5)]
    empty = run(0, x_type="lora", x_values="None, style/ink", y_type="none", model="model", clip="clip")
    assert empty["model"] == "model" and empty["x_label"] == "no LoRA" and len(lora_calls) == 1 # No LoRA: nothing loaded.
    strength = run(1, x_type="lora strength", x_values="0, 0.8", y_type="none", lora_name="style/glow.safetensors", model="model")
    assert strength["clip"] is None and lora_calls[-1] == ("style/glow.safetensors", 0.8, 0) # No clip: the model only.
    with pytest.raises(ValueError, match="needs the model input"):
        run(1, x_type="lora", x_values="None, style/ink", y_type="none")


def test_validation_and_preview_route(api, models):
    assert XYPlot.validate_inputs("cfg", "4, 5", "none", "") is True
    assert "not a number" in XYPlot.validate_inputs("cfg", "4, x", "none", "")
    assert XYPlot.validate_inputs() is True # Linked fields aren't known yet: nothing to check.
    status, body = api("POST", "/diceforge/xy-plot", json={"x_type": "cfg", "x_values": "4-5:0.5", "y_type": "sampler", "y_values": "euler"})
    assert status == 200 and body == {"x_type": "cfg", "y_type": "sampler", "count": 3, "x": ["CFG 4", "CFG 4.5", "CFG 5"], "y": ["euler"]}
    status, text = api("POST", "/diceforge/xy-plot", json={"x_type": "steps", "x_values": "4.5"})
    assert status == 400 and "whole numbers" in text
    for junk in ([], 5, {"x_type": 5}, {"x_type": "nope"}):
        assert api("POST", "/diceforge/xy-plot", json=junk)[0] in (200, 400)
