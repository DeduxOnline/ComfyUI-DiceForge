# Robustness: what the nodes and routes do with damaged or unusual files and requests. A damaged memory, grid, model info or preset file starts
# over or is skipped (never a crash on every run); wildcard files in other encodings or deleted after indexing are clear errors; junk requests are
# 4xx answers, never server errors; many threads at once don't break anything; picks are the same in every Python process; and the frontend's
# wildcard autocomplete knows the same name characters as the server.
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import pytest
import torch
from hypothesis import given, settings, strategies as st
from DiceForge import clip_text_encode_pos_neg as prompts
from DiceForge import dice_grid, lora_stack, model_info, seed_modes
from DiceForge.clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative as Node
from DiceForge.dice_grid import DiceGrid, GridStore
from DiceForge.lora_stack import LoraStack, known_triggers, row_triggers
from DiceForge.seed_modes import BalancedPicker, ShufflePicker, deck_cards
scaled = lambda count: max(1, count * settings.default.max_examples // 200) # Explicit budgets follow the profile (thorough: 15 times).

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(positive, negative="", seed=0, mode="random"):
    return Node.execute(positive, negative, clip=None, seed=seed, seed_mode=mode).result[2:4]


# Seed memory: a file that isn't a database, values that aren't JSON, and states of the wrong shape.
def test_a_damaged_memory_file_starts_over():
    memory = seed_modes.MEMORY
    os.makedirs(os.path.dirname(memory.path), exist_ok=True)
    with open(memory.path, "wb") as file:
        file.write(b"this is not a database" * 100)
    for mode in ("shuffle", "balanced", "mutate"):
        assert run("{a|b|c}", mode=mode)[0] in ("a", "b", "c")
    with sqlite3.connect(memory.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM memory").fetchone()[0] >= 3 # A working memory file again.
    assert any(name.startswith(os.path.basename(memory.path) + ".broken") for name in os.listdir(os.path.dirname(memory.path))) # Kept aside.


class Damaged:
    """A connection whose database turns out malformed while in use (as SQLite says when pages inside the file are damaged)."""
    def __init__(self, error):
        self.error = error

    def execute(self, *args):
        raise self.error

    def close(self):
        pass


def test_a_memory_damaged_while_in_use_starts_over():
    memory = seed_modes.MEMORY
    memory.set("shuffle", "k", {"position": 1})
    memory.save()
    memory.connection.close()
    memory.connection = Damaged(sqlite3.DatabaseError("database disk image is malformed"))
    assert memory.get("shuffle", "k") is None # Set aside: a new, empty memory.
    memory.set("shuffle", "k", {"position": 2})
    memory.save()
    assert memory.get("shuffle", "k") == {"position": 2}


def test_a_locked_memory_is_not_mistaken_for_damage():
    memory = seed_modes.MEMORY
    memory.set("shuffle", "k", {"position": 1})
    memory.save()
    real = memory.connection
    memory.connection = Damaged(sqlite3.OperationalError("database is locked"))
    try:
        with pytest.raises(sqlite3.OperationalError):
            memory.get("shuffle", "k")
        assert os.path.exists(memory.path) # Nothing set aside.
    finally:
        memory.connection = real
    assert memory.get("shuffle", "k") == {"position": 1}


JUNK_STATES = ["junk", 5, None, [], [1, 2], {}, {"position": "x"}, {"order": 5}, {"order": None, "position": 99, "last": None, "previous": None, "pending": "ab"},
               {"order": 1, "position": -3, "last": "zz", "previous": None, "pending": ["zz", 7]}, {"position": 1.5, "pending": [], "order": "x"}]


@pytest.mark.parametrize("state", JUNK_STATES)
def test_shuffle_with_a_damaged_state_starts_a_new_round(state):
    weighted = [(1.0, name) for name in "abcd"]
    seed_modes.MEMORY.set("shuffle", seed_modes.MEMORY.key(deck_cards(weighted)), state)
    dealt = [ShufflePicker().pick(weighted, 1, True)[0][0] for _ in range(8)]
    assert set(dealt) <= set("abcd") and len(dealt) == 8
    assert sorted(dealt[4:]) == list("abcd") # Back to whole rounds.


@pytest.mark.parametrize("credits", ["junk", 5, None, [], [1], [0, 0, 0, 0, 0], ["a", 0, 0, 0], [1e308, -1e308, 0, 0], [float("nan"), 0, 0, 0], [float("inf"), 0, 0, 0]])
def test_balanced_with_damaged_credits_starts_over(credits):
    weighted = [(1.0, name) for name in "abcd"]
    seed_modes.MEMORY.set("balanced", seed_modes.MEMORY.key(weighted), credits)
    dealt = [BalancedPicker().pick(weighted, 1, False)[0][0] for _ in range(40)]
    assert set(dealt) == set("abcd")


@pytest.mark.parametrize("last", ["junk", 5, [1, 2], [[1]], [["x", ["a"], 2]], [[[0], "a", 2]], [[[0], ["zzz"], 2]], [[[0], ["a"], "x"]]])
def test_mutate_with_a_damaged_memory_picks_afresh(last):
    text = "{a|b|c} {x|y}"
    seed_modes.MEMORY.set("mutate", seed_modes.MEMORY.key(text, ""), last)
    first = run(text, mode="mutate")[0].split(" ")
    assert first[0] in "abc" and first[1] in "xy"
    second = run(text, seed=1, mode="mutate")[0].split(" ")
    assert sum(a != b for a, b in zip(first, second)) == 1 # And mutating works again from there.


def test_memory_values_that_are_not_json_are_ignored():
    memory = seed_modes.MEMORY
    memory.set("shuffle", "k", {"position": 1})
    with memory.lock:
        memory.database().execute("UPDATE memory SET value = ? WHERE key = ?", ("{not json", "k"))
    assert memory.get("shuffle", "k") is None


# Dice Grid: a damaged manifest or missing cell images don't block the grid forever.
@pytest.mark.parametrize("manifest", ["{oops", "[]", "5", "null", '{"cells": "x"}', '{"cells": [{"file": "missing.png", "label": "a", "row": ""}], "done": false, "next": 1}',
                                      '{"cells": [5, null, {"label": "b"}], "next": "x"}', '{"done": true}'])
def test_a_damaged_grid_manifest_starts_over_or_skips_the_damage(manifest):
    store = GridStore("damaged-")
    os.makedirs(store.folder, exist_ok=True)
    with open(store.manifest, "w", encoding="utf-8") as file:
        file.write(manifest)
    grid, cells = DiceGrid.execute(torch.full((1, 16, 16, 3), 0.5), name="damaged", cell_width=32, save=False, label="new").result
    assert cells >= 1 and grid.shape[-1] == 3
    grid, cells2 = DiceGrid.execute(torch.full((1, 16, 16, 3), 0.5), name="damaged", cell_width=32, save=False, label="next").result
    assert cells2 == cells + 1


def test_a_damaged_cell_image_is_skipped():
    DiceGrid.execute(torch.full((1, 16, 16, 3), 0.5), name="cellbroken", cell_width=32, save=False, label="a")
    DiceGrid.execute(torch.full((1, 16, 16, 3), 0.5), name="cellbroken", cell_width=32, save=False, label="b")
    store = GridStore("cellbroken-")
    with open(os.path.join(store.folder, store.state["cells"][0]["file"]), "wb") as file:
        file.write(b"not a png")
    grid, cells = DiceGrid.execute(torch.full((1, 16, 16, 3), 0.5), name="cellbroken", cell_width=32, save=False, label="c").result
    assert grid.shape[-1] == 3 and cells >= 2


# Model info files written by hand or damaged: the browser, the trigger words and LoRA Stack keep working.
JUNK_INFO = [[], "x", 5, {"user": "x", "civitai": [1]}, {"user": {"trigger_words": ["a"]}, "civitai": {"trigger_words": "abc", "images": [None, 5, "x"]}},
             {"civitai": {"found": True, "images": "x", "model_name": 5}}, {"size": "big", "mtime": None, "user": None, "civitai": None}]


@pytest.mark.parametrize("info", JUNK_INFO)
def test_damaged_model_info_is_ignored_where_it_is_wrong(info, models, monkeypatch):
    path = models("loras", "x.safetensors")
    stat = os.stat(path)
    if isinstance(info, dict) and "size" not in info:
        info = {**info, "size": stat.st_size, "mtime": stat.st_mtime} # Fresh, so the damaged parts are read.
    target = model_info.info_file("loras", "x.safetensors")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as file:
        json.dump(info, file)
    entry = model_info.model_list("loras")["files"][0]
    assert entry["file"] == "x.safetensors" and all(isinstance(word, str) for word in entry["trigger_words"])
    json.dumps(entry)
    user, civitai = known_triggers("x.safetensors")
    assert all(isinstance(word, str) for word in user + civitai)
    monkeypatch.setattr(lora_stack.comfy.sd, "load_lora_for_models", lambda model, clip, lora, sm, sc, lora_metadata=None: (model, clip))
    monkeypatch.setattr(LoraStack, "load", classmethod(lambda cls, path: ({}, {})))
    triggers = LoraStack.execute([], json.dumps({"rows": [{"lora": "x.safetensors"}]}), 0, "random", []).result[2]
    assert isinstance(triggers, str)


@pytest.mark.parametrize("words, expected", [(["a", " b ", ""], ["a", "b"]), ("a, b", ["a", "b"]), (None, []), (5, []), ([1, None, "c"], ["1", "c"])])
def test_custom_trigger_words_of_any_shape(words, expected):
    assert row_triggers({"lora": "x", "triggers": "custom", "trigger_words": words}) == expected


def test_a_damaged_preset_is_skipped_in_the_list_and_refused_when_opened(api):
    os.makedirs(lora_stack.PRESET_FOLDER, exist_ok=True)
    for name, text in (("broken", "{oops"), ("notstack", "[1, 2]"), ("good", json.dumps({"stack": {"rows": [{"lora": "a"}]}}))):
        with open(os.path.join(lora_stack.PRESET_FOLDER, name + ".json"), "w", encoding="utf-8") as file:
            file.write(text)
    try:
        status, body = api("GET", "/diceforge/lora-presets")
        assert status == 200 and [preset["name"] for preset in body["presets"]] == ["good"]
        for name in ("broken", "notstack"):
            status, body = api("GET", f"/diceforge/lora-presets/file?name={name}")
            assert status == 400, (name, status, body)
    finally:
        shutil.rmtree(lora_stack.PRESET_FOLDER, ignore_errors=True)


# Junk requests: every route answers 4xx (with a message) or 2xx, never a server error.
ROUTES = [("POST", "/diceforge/wildcards/file"), ("POST", "/diceforge/lora-presets"), ("POST", "/diceforge/lora-triggers"), ("POST", "/diceforge/model-bases"),
          ("POST", "/diceforge/model-info"), ("GET", "/diceforge/model-info?kind=loras&file=nope"), ("GET", "/diceforge/model-info?kind=x&file=y"),
          ("GET", "/diceforge/model-browser?kind=nope"), ("GET", "/diceforge/model-preview?kind=loras&file=../../x"), ("GET", "/diceforge/wildcards/file?name=../x"),
          ("GET", "/diceforge/lora-presets/file?name=../x"), ("DELETE", "/diceforge/lora-presets?name=../x"), ("GET", "/diceforge/wildcards/file"),
          ("POST", "/diceforge/wildcards/rename"), ("DELETE", "/diceforge/wildcards/file?name=../x"), ("DELETE", "/diceforge/wildcards/file"),
          ("DELETE", "/diceforge/wildcards/file?name=nope"), ("POST", "/diceforge/models/rename"), ("DELETE", "/diceforge/models/file?kind=loras&file=../x"),
          ("DELETE", "/diceforge/models/file"), ("POST", "/diceforge/civitai/download"), ("POST", "/diceforge/civitai/key"), ("GET", "/diceforge/civitai/key"),
          ("GET", "/diceforge/civitai/downloads"), ("DELETE", "/diceforge/civitai/downloads?id=x"),
          ("POST", "/diceforge/model-favorite"), ("POST", "/diceforge/wildcards/favorite"), ("POST", "/diceforge/sampler-presets"),
          ("GET", "/diceforge/sampler-presets"), ("DELETE", "/diceforge/sampler-presets?name=nope"), ("DELETE", "/diceforge/sampler-presets"),
          ("POST", "/diceforge/xy-plot"), ("POST", "/diceforge/styles"), ("GET", "/diceforge/styles"), ("DELETE", "/diceforge/styles?name=nope"),
          ("GET", "/diceforge/tags?q=hair"), ("GET", "/diceforge/tags?limit=x"), ("GET", "/diceforge/tags/lists"), ("POST", "/diceforge/tags/download"),
          ("GET", "/diceforge/grid?node=1"), ("GET", "/diceforge/grid/image?node=1&file=00000.png"), ("POST", "/diceforge/grid/keep"), ("POST", "/diceforge/grid/save")]
JUNK_BODIES = ["not json", "", "[]", "5", "null", '"text"', '{"loras": 5}', '{"loras": [1, null, {"a": 1}, "x.safetensors"]}', '{"items": 5}',
               '{"items": [1, null, "x", {"kind": 5, "file": []}, {"kind": "loras", "file": "../../x"}]}', '{"kind": "loras", "file": "x", "user": [1]}',
               '{"kind": "loras", "file": "x", "user": {"name": {"a": 1}}}', '{"name": 5}', '{"name": "ok", "stack": 5}', '{"name": "ok", "stack": {"rows": "x"}}',
               '{"name": "../../evil", "text": "x"}', '{"name": "ok", "text": 5}', '{"name": ["a"]}', '{"name": "ok", "to": 5}',
               '{"name": "ok", "to": "../../evil"}', '{"name": "ok", "text": "x", "create": "yes"}', '{"kind": "loras", "file": "x.safetensors", "to": 5}',
               '{"kind": "loras", "file": "x.safetensors", "to": "../../evil"}', '{"kind": "loras", "file": "../x.safetensors", "to": "y"}', '{"key": 5}',
               '{"key": "x\\u0000y"}', '{"version_id": "1"}', '{"version_id": 1.5}', '{"version_id": -3}', '{"version_id": 1, "folder": "../../x"}',
               '{"name": "x", "steps": "5", "cfg": 5, "sampler_name": "euler", "scheduler": "normal"}', '{"name": "x", "steps": 5, "cfg": 1e308}']


@pytest.mark.parametrize("method, path", ROUTES)
def test_junk_requests_never_cause_a_server_error(method, path, api, wildcards, models):
    models("loras", "x.safetensors")
    for body in JUNK_BODIES:
        status, answer = api(method, path, data=body.encode())
        assert status < 500, (method, path, body, status, answer)
        if status >= 400:
            assert answer, (method, path, body) # A message saying what's wrong.
    shutil.rmtree(lora_stack.PRESET_FOLDER, ignore_errors=True)


KEYS = ["name", "stack", "rows", "text", "loras", "items", "kind", "file", "user", "overwrite", "lora", "groups", "to", "create", "favorite", "steps", "cfg", "sampler_name", "scheduler", "x_type", "x_values", "y_type", "y_values", "prompt", "negative_prompt", "list", "node", "file", "files", "kept"]


def json_children(children):
    return st.one_of(st.lists(children, max_size=4), st.dictionaries(st.sampled_from(KEYS), children, max_size=4))


json_values = st.recursive(st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=10)),
                           json_children, max_leaves=10)


@settings(max_examples=scaled(40))
@given(body=json_values, route=st.sampled_from([route for route in ROUTES if route[0] == "POST"]))
def test_generated_json_bodies_never_cause_a_server_error(body, route, api, wildcards, models):
    models("loras", "x.safetensors")
    status, answer = api(route[0], route[1], data=json.dumps(body).encode())
    assert status < 500, (route, body, status, answer)
    shutil.rmtree(lora_stack.PRESET_FOLDER, ignore_errors=True)



PAGE_KEYS = ["tags", "stats", "creator", "modelVersions", "id", "name", "publishedAt", "downloadCount", "thumbsUpCount", "username", "baseModel"]
civitai_pages = st.recursive(st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=8)),
                             lambda children: st.one_of(st.lists(children, max_size=4), st.dictionaries(st.sampled_from(PAGE_KEYS), children, max_size=5)), max_leaves=14)


@settings(max_examples=scaled(200))
@given(page=civitai_pages, version_id=st.one_of(st.none(), st.integers()))
def test_any_civitai_page_gives_clean_details(page, version_id):
    """Whatever Civitai's model page holds, the details are plain: tags as short strings, counts as numbers >= 0, versions with an id, and the newer
    version check never fails."""
    details = model_info.civitai_details(page)
    json.dumps(details)
    if details:
        assert all(isinstance(tag, str) and 0 < len(tag) <= 40 for tag in details["tags"])
        assert all(isinstance(count, int) and count >= 0 for count in details["stats"].values())
        assert all(isinstance(version["id"], int) for version in details["versions"])
        model_info.newer_version({**details, "version_id": version_id, "model_id": 1})

# Wildcard files in other encodings, invalid YAML, YAML scalars, files deleted after indexing.
def test_a_wildcard_file_in_another_encoding_is_a_clear_error(wildcards, api):
    wildcards("good.txt", "red\n")
    with open(wildcards.folder / "cyrillic.txt", "wb") as file:
        file.write("красный\nсиний\n".encode("cp1251"))
    prompts.wildcard_index(refresh=True)
    with pytest.raises(ValueError, match=r"cyrillic\.txt is not UTF-8"):
        run("__cyrillic__")
    assert run("__good__")[0] == "red" # The other files still work.
    status, body = api("GET", "/diceforge/wildcards")
    assert status == 200
    listed = {file["name"]: file for file in body["files"]}
    assert listed["good"]["lines"] == 1 and "not UTF-8" in listed["cyrillic"]["error"]
    status, body = api("GET", "/diceforge/wildcards/file?name=cyrillic")
    assert status == 400 and "not UTF-8" in body


def test_broken_yaml_files_are_skipped(wildcards):
    wildcards("good.yaml", "colors: [red]\n")
    wildcards("bad.yaml", "colors: [unclosed\n  - : :\n")
    with open(wildcards.folder / "latin.yaml", "wb") as file:
        file.write("hats: [bérêt]\n".encode("latin-1"))
    prompts.wildcard_index(refresh=True)
    assert run("__colors__")[0] == "red"
    with pytest.raises(ValueError, match="not found"):
        run("__hats__")


def test_yaml_lines_are_text_as_written(wildcards):
    wildcards("answers.yaml", "answers:\n  - yes\n  - no\n  - on\n  - 12:30\n  - 0123\n  - 1.50\n  - ~\n  - null\n  -\n  - 'quoted'\n  - 2024-01-31\n")
    assert prompts.read_wildcard("answers") == ["yes", "no", "on", "12:30", "0123", "1.50", "quoted", "2024-01-31"]
    wildcards("keys.yaml", "yes:\n  1: [a]\n")
    assert prompts.read_wildcard("yes/1") == ["a"]


def test_a_wildcard_file_deleted_after_indexing_is_a_clear_error(wildcards):
    path = wildcards("gone.txt", "a\n")
    prompts.wildcard_index(refresh=True)
    os.remove(path)
    with pytest.raises(ValueError, match="gone"):
        prompts.read_wildcard("gone")


def test_a_big_wildcard_file_stays_fast(wildcards):
    wildcards("big.txt", "\n".join(f"line {index}" for index in range(100000)))
    started = time.perf_counter()
    for mode in ("random", "deck", "shuffle", "balanced", "combinations", "mutate"):
        assert run("__big__", seed=12345, mode=mode)[0].startswith("line ")
    assert time.perf_counter() - started < 15


# Threads: nodes and memory used from several threads at once (the server answers routes in threads while a prompt runs).
def test_nodes_survive_many_threads(wildcards):
    wildcards("color.txt", "red\nblue\ngreen\n")
    errors = []

    def work(index):
        try:
            for step in range(15):
                mode = ("random", "deck", "shuffle", "balanced", "combinations", "mutate")[(index + step) % 6]
                positive, _ = run("{a|b|c} __color__ {2$$x|y|z}", seed=step, mode=mode)
                if not positive:
                    errors.append(f"empty prompt in {mode}")
                if step % 5 == 0:
                    wildcards(f"extra{index}.txt", f"v{step}\n") # Files change while others read the index.
        except Exception as error: # noqa: BLE001
            errors.append(repr(error))
    threads = [threading.Thread(target=work, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


# Determinism: the reproducible modes give the same picks in every Python process (no hash() or set order in the picks).
PROBE = r'''
import json, os, sys
sys.argv = ["probe"]
sys.path[:0] = [os.environ["DICEFORGE_TESTS"]]
import conftest
from DiceForge.clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative as Node
from DiceForge.lora_stack import group_pick, row_strength
from DiceForge.random_float import RandomFloatSeedModes
from DiceForge.random_int import RandomIntSeedModes
from DiceForge.random_sampler import RandomSampler
from DiceForge.resolution_selector_random_latent import ResolutionSelectorRandomLatent as Selector
from DiceForge.sdxl_resolution_list_latent import SDXLResolutionListLatent as SDXL
from DiceForge.seed_modes import make_picker
import nodes
nodes.EmptyLatentImage.generate = lambda self, w, h, batch_size=1: ({"samples": None},)
results = []
for seed in (0, 1, 7, 123456789, 2 ** 63):
    for mode in ("random", "deck", "combinations"):
        results.append(Node.execute("{a|b|{c|d}} {2$$e|f|g|h} ${v={i|j}}${v} {3::k|l}", "{m|n}", clip=None, seed=seed, seed_mode=mode).result[2:4])
    for mode in ("random", "deck", "sequential"):
        results.append(SDXL.execute({"resolution": "Random Chaos", "size": "Any", "max_aspect": 2.5}, seed, None, 8, 1, mode).result[1:3])
        results.append(SDXL.execute({"resolution": "Random", "size": "Any Listed"}, seed, None, 8, 1, mode).result[1:3])
        results.append(Selector.execute("Random Any", 1.3, seed, 16, 1, 2.0, mode).result[1:3])
        results.append(RandomIntSeedModes.execute(-1000, 10 ** 12, 3, seed, mode).result[0])
        results.append(RandomFloatSeedModes.execute(-5.0, 5.0, 0.0, seed, mode, 10).result[0])
        results.append(RandomSampler.execute("*", "*", seed, mode).result[2])
        results.append(row_strength({"lora": "x", "random": True, "min": 0.2, "max": 1.4}, make_picker(mode, seed), seed))
        results.append([row["lora"] for row in group_pick("A", [{"lora": f"r{i}"} for i in range(6)], {"min": 1, "max": 3}, make_picker(mode, seed), seed)])
print(json.dumps(results))
'''


def test_picks_are_the_same_in_every_python_process(tmp_path):
    outputs = []
    for hash_seed in ("0", "12345", "random"):
        environment = {**os.environ, "PYTHONHASHSEED": hash_seed, "DICEFORGE_TESTS": os.path.join(REPO, "tests")}
        result = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, env=environment, cwd=str(tmp_path), timeout=300)
        assert result.returncode == 0, result.stderr[-2000:]
        outputs.append(result.stdout.strip().splitlines()[-1])
    assert outputs[0] == outputs[1] == outputs[2]


# Frontend: the wildcard autocomplete (web/wildcards.js) knows the same name characters as the server's wildcard pattern, in every script.
@pytest.mark.skipif(shutil.which("node") is None, reason="node.js is not installed")
def test_autocomplete_knows_every_letter_the_server_does():
    import re
    import unicodedata
    source = open(os.path.join(REPO, "DiceForge", "web", "wildcards.js"), encoding="utf-8").read()
    pattern = re.search(r"!(/\^\[.*?\]\*\$/u)\.test\(typedText\)", source).group(1) # The characters a typed name may have.
    script = f"const pattern = {pattern};\nconst found = [];\nfor (let code = 0x20; code < 0x30000; code++) {{ if (code >= 0xD800 && code < 0xE000) continue;" \
             "\n  if (pattern.test('a' + String.fromCodePoint(code))) found.push(code); }\nconsole.log(JSON.stringify(found));"
    javascript = set(json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout))
    name_char = re.compile(prompts.NAME_PART)
    python = {code for code in range(0x20, 0x30000) if not 0xD800 <= code < 0xE000 and name_char.fullmatch(chr(code))}
    python.add(ord(" ")) # Single spaces inside a name, as the server reads them.
    assigned = {code for code in python | javascript if unicodedata.category(chr(code)) != "Cn"} # Letters both Unicode versions know.
    assert sorted(python & assigned) == sorted(javascript & assigned)


# Random Image: a damaged image file in the folder is an error that names it.
@pytest.mark.parametrize("content", [b"not an image", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40])
def test_a_damaged_image_is_named_in_the_error(tmp_path, content):
    from DiceForge.random_image import RandomImageLoader
    (tmp_path / "broken.png").write_bytes(content)
    with pytest.raises(ValueError, match=r"Random Image: broken\.png can't be read"):
        RandomImageLoader.execute(seed=0, seed_mode="sequential", path=str(tmp_path))


# The memory file replaced while ComfyUI runs (deleted and a new file put there): the memory opens what is there now, instead of writing to the
# deleted file ("attempt to write a readonly database" on every run until a restart).
def test_a_memory_file_replaced_while_open_is_reopened():
    memory = seed_modes.MEMORY
    memory.set("shuffle", "k", {"position": 1})
    memory.save()
    os.remove(memory.path)
    with open(memory.path, "wb") as file:
        file.write(b"\x5a" * 8192) # Another file at the same place.
    memory.set("shuffle", "k", {"position": 2})
    memory.save()
    assert memory.get("shuffle", "k") == {"position": 2}
    with sqlite3.connect(memory.path) as connection: # What was written is in the file that is there now.
        assert connection.execute("SELECT COUNT(*) FROM memory").fetchone()[0] == 1


@pytest.mark.parametrize("route, body", [("/diceforge/wildcards/file", {"name": "x" * 5000, "text": "y"}),
                                         ("/diceforge/lora-presets", {"name": "x" * 5000, "stack": {"rows": []}})])
def test_a_name_too_long_for_the_file_system_is_a_400(route, body, api, wildcards):
    status, answer = api("POST", route, json=body)
    assert status == 400 and "can't save" in answer
    shutil.rmtree(lora_stack.PRESET_FOLDER, ignore_errors=True)


def test_an_unknown_rescale_mode_is_a_clear_error():
    from DiceForge.sdxl_resolution_list_latent import rescaled
    with pytest.raises(ValueError, match="Rescale: unknown mode 'sideways'"):
        rescaled(1024, 1024, {"rescale": "sideways"})
    assert rescaled(1024, 768, None) == (1024, 768) # No rescale at all (Resolution Selector's optional input): 100%.


# mutate keeps its last picks only while they fit: a wildcard file that grows gives a multi-pick its full count again.
def test_mutate_multi_pick_follows_a_wildcard_file_that_grows(wildcards):
    wildcards("grow.txt", "only\n")
    assert run("{3$$__grow__}", mode="mutate")[0] == "only"
    wildcards("grow.txt", "only\nb\nc\nd\ne\n")
    picked = run("{3$$__grow__}", seed=1, mode="mutate")[0].split(", ")
    assert len(picked) == len(set(picked)) == 3
