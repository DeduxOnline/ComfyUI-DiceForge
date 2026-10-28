# The frontend's pure functions, which need no page and no ComfyUI: what they give for known inputs, run in Node.js in a moment, where the
# end-to-end tests only reach them through a browser and a server.
import json
import os
import re
import shutil
import subprocess
import pytest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DiceForge", "web")


def js_source(file, *names):
    """Module-level definitions of a web/ file, as written and in the order given: a function or a constant, from its first line to the line
    that closes it at the start of a line (or its one line)."""
    with open(os.path.join(WEB, file), encoding="utf-8") as source:
        lines = source.read().replace("\r\n", "\n").split("\n")
    pieces = []
    for name in names:
        start = next(index for index, line in enumerate(lines) if re.match(rf"(?:export )?(?:function|const) {name}\b", line))
        end = start
        if re.search(r"[{\[(]\s*(?://.*)?$", lines[start]):
            end = next(index for index in range(start + 1, len(lines)) if lines[index][:1] in ("}", "]", ")"))
        pieces.append("\n".join(lines[start:end + 1]).removeprefix("export "))
    return "\n".join(pieces)


def run(source, function, cases):
    script = source + f"\nconst cases = {json.dumps(cases)};\nconsole.log(JSON.stringify(cases.map((args) => {function}(...args))));"
    return json.loads(subprocess.run(["node", "-"], input=script, capture_output=True, text=True, check=True, encoding="utf-8").stdout)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node.js is not installed")


@needs_node
def test_a_sampler_name_from_a_picture_becomes_comfyuis():
    cases = {
        ("DPM++ 2M Karras", None): {"sampler_name": "dpmpp_2m", "scheduler": "karras"}, # The schedule in the sampler's name (A1111).
        ("DPM++ 2M SDE Karras", "Exponential"): {"sampler_name": "dpmpp_2m_sde", "scheduler": "exponential"}, # The schedule type wins.
        ("Euler a", "Automatic"): {"sampler_name": "euler_ancestral", "scheduler": None}, # The sampler's own default.
        ("Euler", "Uniform"): {"sampler_name": "euler", "scheduler": "normal"},
        ("dpmpp_2m", "sgm_uniform"): {"sampler_name": "dpmpp_2m", "scheduler": "sgm_uniform"}, # ComfyUI's names pass as they are.
        ("UniPC", "Some New"): {"sampler_name": "uni_pc", "scheduler": "some_new"},
        ("", None): {"sampler_name": None, "scheduler": None},
    }
    source = js_source("apply_settings.js", "SAMPLERS", "SCHEDULERS", "plain", "comfySampler")
    assert run(source, "comfySampler", [list(args) for args in cases]) == list(cases.values())


@needs_node
def test_a_style_is_split_around_the_prompt():
    cases = {
        "": {"before": "", "after": ""},
        "   ": {"before": "", "after": ""},
        "masterpiece, best quality": {"before": "", "after": "masterpiece, best quality"}, # No {prompt}: after it.
        "photo of {prompt}, 35mm, ": {"before": "photo of", "after": "35mm"},
        ", , {prompt}": {"before": "", "after": ""},
        "{prompt} a {prompt} b": {"before": "", "after": "a   b"}, # Only the first {prompt} splits.
    }
    source = js_source("prompt_styles.js", "JOINING", "trimJoin", "stylePieces")
    assert run(source, "stylePieces", [[style] for style in cases]) == list(cases.values())


@needs_node
def test_a_model_gets_the_preset_of_its_family():
    cases = {
        ("anima/anima-preview.safetensors", None): "Anima",
        ("x/Anima_turbo_v1.safetensors", None): "Anima Turbo",
        ("anima_turbo.safetensors", "Anima"): "Anima Turbo", # The base names the family, the file the turbo.
        ("C:\\models\\anima.safetensors", None): "Anima",
        ("noobaiXL_vPred10.safetensors", None): "NoobAI (v-pred)",
        ("NoobAI-XL-eps.safetensors", None): "NoobAI (eps)",
        ("waiIllustriousSDXL_v150.safetensors", None): "Illustrious",
        ("ilxl_mix.safetensors", None): "Illustrious",
        ("model_ilxl.safetensors", None): "Illustrious",
        ("bilxl.safetensors", None): None, # ilxl inside a word is not Illustrious.
        ("sdxl_base.safetensors", None): None,
        ("my_merge.safetensors", "Illustrious"): "Illustrious", # From Civitai's base model.
        ("noob_vpred.safetensors", "SDXL 1.0"): "NoobAI (v-pred)", # A base that names no family: the file's name.
    }
    source = js_source("sampler_presets.js", "presetNameFor")
    assert run(source, "presetNameFor", [list(args) for args in cases]) == list(cases.values())


@needs_node
def test_a_tag_is_written_as_a_prompt_wants_it():
    cases = {"long_hair": "long hair", "ab_c": "ab c", "^_^": "^_^", ">_<": ">_<", "o_o": "o_o", "a_b": "a_b", "xd": "xd",
             "hatsune_miku_(cosplay)": "hatsune miku \\(cosplay\\)", ":)": ":\\)"}
    assert run(js_source("tag_autocomplete.js", "tagText"), "tagText", [[tag] for tag in cases]) == list(cases.values())


@needs_node
def test_clean_up_keeps_the_head_and_one_of_each_line():
    cases = [
        (["# head\n\nred\nblue\nred\n  \ngreen  \n", False], {"text": "# head\nred\nblue\ngreen", "duplicates": 1, "empty": 3}),
        (["  red\nred\n", False], {"text": "  red", "duplicates": 1, "empty": 1}), # The same line once spaces are trimmed.
        (["2::b\nA\n1.5::c\na\n10\n9", True], {"text": "9\n10\nA\na\n2::b\n1.5::c", "duplicates": 0, "empty": 0}), # Weights don't sort.
    ]
    assert run(js_source("wildcards.js", "cleanLines"), "cleanLines", [args for args, _ in cases]) == [result for _, result in cases]


@needs_node
def test_the_prompt_highlight_marks():
    cases = [
        (["{a|b}", None], [[0, 1, "b0"], [2, 3, "b0"], [4, 5, "b0"]]),
        (["{2$$a|3::b}", None], [[0, 1, "b0"], [1, 4, "count"], [5, 6, "b0"], [6, 9, "weight"], [10, 11, "b0"]]),
        (["{!a|b}", None], [[0, 1, "b0"], [1, 2, "lock"], [3, 4, "b0"], [5, 6, "b0"]]),
        (["{a|{b|c}}", None], [[0, 1, "b0"], [2, 3, "b0"], [3, 4, "b1"], [5, 6, "b1"], [7, 8, "b1"], [8, 9, "b0"]]),
        (["{a", None], [[0, 1, "bad"]]), # Never closed.
        (["a}", None], [[1, 2, "bad"]]), # Closes nothing.
        (["__color__ __nope__", ["Color"]], [[0, 9, "wc"], [10, 18, "wc-missing"]]),
        (["__col*__", ["color"]], [[0, 8, "wc"]]),
        (["__x__", None], [[0, 5, "wc"]]), # The list isn't there yet: nothing is called missing.
        (["<lora:x:0.5> ${s=a} ${s} // note", None], [[0, 12, "lora"], [13, 17, "var"], [18, 19, "var"], [20, 24, "var"], [25, 32, "comment"]]),
        (["\\{a\\}", None], [[0, 2, "esc"], [3, 5, "esc"]]),
        (["(red:1.2) embedding:foo", None], [[4, 8, "attn"], [10, 23, "embed"]]),
    ]
    source = js_source("prompt_highlight.js", "NAME_CHAR", "TOKENS", "COUNT", "WEIGHT_START", "globTest", "promptMarks")
    assert run(source, "promptMarks", [args for args, _ in cases]) == [marks for _, marks in cases]


@needs_node
def test_the_workflow_a_run_sends_has_no_run_data():
    kept = {"dice_forge_history": [{"positive": "an earlier prompt"}], "dice_forge_danbooru": {"text": "a prompt"},
            "dice_forge_image": {"file_name": "cat.png"}, "dice_forge_height": 120}
    workflow = {"nodes": [{"id": 1, "properties": kept}, {"id": 2}],
                "definitions": {"subgraphs": [{"id": "a", "nodes": [{"id": 3, "properties": dict(kept)}]}]}, "extra": {"ds": 1}}
    clean = {"nodes": [{"id": 1, "properties": {"dice_forge_height": 120}}, {"id": 2}],
             "definitions": {"subgraphs": [{"id": "a", "nodes": [{"id": 3, "properties": {"dice_forge_height": 120}}]}]}, "extra": {"ds": 1}}
    cases = [[workflow], [{"nodes": [{"id": 1}]}], [None]]
    source = js_source("prompt_preview.js", "RUN_DATA", "withoutRunData")
    assert run(source, "withoutRunData", cases) == [clean, {"nodes": [{"id": 1}]}, None]

@needs_node
def test_danbooru_tag_enhancers_row_sums_up_the_last_run():
    one = {"posts": [{"id": 101, "rating": "g"}], "added": "smile, twintails, blue sky", "mode": "random"}
    cases = [[one], [{**one, "site": "e621", "posts": [{"id": 201, "rating_name": "safe"}], "added": "solo"}],
             [{"posts": [{"id": 1}, {"id": 2}, {"id": 3}], "added": "", "mode": "fixed", "site": "danbooru"}]]
    source = js_source("danbooru_preview.js", "RATINGS", "ratingName", "SITES", "postsName", "summary")
    assert run(source, "summary", cases) == ["Last run: post #101 (general), +3 tags", "Last run: e621 post #201 (safe), +1 tag",
                                             "Last run: 3 posts, no tags added · fixed"]


@needs_node
def test_lora_stacks_random_strength_reads_as_a_range():
    cases = [[{"min": 0.6, "max": 1}], [{"strength": 0.75}], [{}], [{"min": 0.333, "max": 0.9}]]
    source = js_source("lora_stack.js", "round", "rangeText")
    assert run(source, "rangeText", cases) == ["🎲 0.60–1.00", "🎲 0.75–0.75", "🎲 1.00–1.00", "🎲 0.33–0.90"]


@needs_node
def test_lora_stack_keeps_a_groups_rows_together():
    rows = [{"lora": "a1", "group": "A"}, {"lora": "x", "group": ""}, {"lora": "b1", "group": "B"}, {"lora": "a2", "group": "A"},
            {"lora": "y", "group": ""}, {"lora": "b2", "group": "B"}]
    source = js_source("lora_stack.js", "together")
    order = [[row["lora"] for row in result] for result in run(source, "together", [[rows], [rows[:1] + rows[3:4] + rows[1:2]], [[]]])]
    assert order == [["a1", "a2", "x", "b1", "b2", "y"], ["a1", "a2", "x"], []]


@needs_node
def test_xy_plots_row_names_the_cell_the_next_run_makes():
    plan = {"x_type": "steps", "y_type": "cfg", "count": 6, "x": ["20 steps", "25 steps", "30 steps"], "y": ["CFG 5", "CFG 7"]}
    row = {"x_type": "cfg", "y_type": "none", "count": 3, "x": ["CFG 4", "CFG 5", "CFG 6"], "y": [""]}
    cases = [[plan, 0], [plan, 4], [plan, 6], [row, 1], [{"x_type": "none", "y_type": "none", "count": 1, "x": [""], "y": [""]}, 0]]
    source = js_source("xy_plot.js", "nextCell", "summaryText")
    assert run(source, "summaryText", [[plan, 4, True]]) == ["3 × 2 = 6 cells · set Widget control mode to after to see the next cell"]
    assert run(source, "summaryText", cases) == ["3 × 2 = 6 cells · next: 20 steps, CFG 5", "3 × 2 = 6 cells · next: 25 steps, CFG 7",
                                                 "3 × 2 = 6 cells · next: 20 steps, CFG 5", "3 cells · next: CFG 5",
                                                 "Pick what changes on X (and Y) to make a plot."]
