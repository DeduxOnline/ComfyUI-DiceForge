# Prompt syntax of CLIP Dual Text Encode without wildcard files: {a|b} choices, weights, multi-picks, variables, locks, escapes, comments, clean-up,
# and the seed modes of the node (combinations, mutate, deck, shuffle).
import random
from collections import Counter
import pytest
from DiceForge import clip_text_encode_pos_neg as prompts
from DiceForge.clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative as Node, WildcardsToText
from DiceForge.seed_modes import DeckPicker, RandomPicker


def resolve(positive, negative="", seed=0):
    return prompts.resolve_prompts((positive, negative), RandomPicker(random.Random(seed)))


def one(text, seed=0):
    return resolve(text, seed=seed)[0]


def run(positive, negative="", seed=0, mode="random", trim=True):
    return Node.execute(positive, negative, clip=None, seed=seed, seed_mode=mode, trim=trim).result


def test_text_without_syntax_stays_as_it_is():
    assert one("a photo of a cat, (masterpiece:1.2)") == "a photo of a cat, (masterpiece:1.2)"


def test_choice_picks_one_option_reproducibly():
    results = {one("{red|green|blue} car", seed) for seed in range(50)}
    assert results == {"red car", "green car", "blue car"}
    first, again = one("{red|green|blue}", 7), one("{red|green|blue}", 7)
    assert first == again


def test_nested_choices_and_empty_options():
    assert {one("{a|{b|c}}", seed) for seed in range(60)} == {"a", "b", "c"}
    assert {one("x, {|y}, z", seed) for seed in range(40)} == {"x, z", "x, y, z"}


def test_weights_change_the_odds_and_zero_never_comes():
    counts = Counter(one("{3::cat|dog}", seed) for seed in range(2000))
    assert 0.70 < counts["cat"] / 2000 < 0.80
    assert all(one("{0::never|a|b}", seed) != "never" for seed in range(200))


@pytest.mark.parametrize("text, sizes", [
    ("{2$$a|b|c}", {2}),
    ("{1-3$$a|b|c}", {1, 2, 3}),
    ("{-2$$a|b|c}", {0, 1, 2}),
    ("{2-$$a|b|c}", {2, 3}),
])
def test_multi_pick_counts_without_repeats(text, sizes):
    seen = set()
    for seed in range(200):
        parts = [part for part in one(text, seed).split(", ") if part]
        assert len(parts) == len(set(parts))
        seen.add(len(parts))
    assert seen == sizes


def test_multi_pick_separator():
    assert " and " in one("{2$$ and $$a|b|c}", 3)


def test_variable_is_filled_once_and_shared_by_both_prompts():
    for seed in range(30):
        positive, negative = resolve("${hair={red|blue|green}}${hair} hair, ${hair} ribbon", "no ${hair} shoes", seed)
        color = positive.split(" ")[0]
        assert positive == f"{color} hair, {color} ribbon" and negative == f"no {color} shoes"


def test_variable_can_be_used_before_it_is_set_and_bang_form_works():
    assert one("${x} cat ${x=big}") == "big cat"
    assert one("${x=!tiny}${x} dog") == "tiny dog"


def test_unset_variable_is_a_clear_error():
    with pytest.raises(ValueError, match=r"\$\{nope\}"):
        one("a ${nope} b")


def test_locked_option_always_comes_in_every_mode():
    for mode in ("random", "deck", "shuffle", "balanced", "combinations", "mutate"):
        assert {run("{sky|!sea|forest}", seed=seed, mode=mode)[2] for seed in range(6)} == {"sea"}, mode


def test_escaped_braces_and_bars_stay_literal():
    assert one(r"\{not a choice\} a \| b") == "{not a choice} a | b"


def test_comments_are_removed():
    assert run("cat /* hidden */, dog // the rest\nbird")[2] == "cat, dog\nbird"


@pytest.mark.parametrize("text, expected", [
    ("a, , b", "a, b"),
    ("a,, ,b", "a,b"),
    (", a, b,", "a, b"),
    ("a  ,  b", "a, b"),
])
def test_tidy_commas(text, expected):
    assert prompts.tidy_commas(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("  a   b  ", "a b"),
    ("a , b ; c !", "a, b; c!"),
    ("( a )", "(a)"),
    ("a\n\n\n\nb", "a\n\nb"),
    ("line one  \n  line two", "line one\nline two"),
])
def test_trim_spaces(text, expected):
    assert prompts.trim_spaces(text) == expected


def test_node_trim_input():
    assert run("( a ) , b", trim=True)[2] == "(a), b"
    assert run("( a ) , b", trim=False)[2] == "( a ), b"


def test_node_without_clip_outputs_only_text():
    positive, negative, positive_text, negative_text, model = run("{a|b}", "bad", seed=1)
    assert positive is None and negative is None and model is None
    assert positive_text in ("a", "b") and negative_text == "bad"


@pytest.mark.parametrize("text, total", [
    ("{a|b}, {c|d|e}", 6),
    ("{2$$a|b|c}", 3),
    ("{1-2$$a|b|c}", 6),
    ("{0::a|b|c}", 2),
    ("{a|{b|c}}", 3),
    ("{a|!b|c}", 1),
    ("${x={a|b}}${x} {c|d}", 4),
    ("plain", 1),
])
def test_count_combinations(text, total):
    assert prompts.count_combinations(text, {}) == total


def test_combinations_mode_goes_through_every_combination_then_starts_over():
    text = "{a|b} {c|d|e}"
    results = [run(text, seed=seed, mode="combinations")[2] for seed in range(12)]
    assert len(set(results[:6])) == 6
    assert results[6:] == results[:6]


def test_combinations_cover_multi_picks():
    results = {run("{2$$a|b|c|d}", seed=seed, mode="combinations")[2] for seed in range(6)}
    assert len(results) == 6 and all(len(result.split(", ")) == 2 for result in results)


def test_deck_mode_deals_every_option_before_repeating():
    assert sorted(run("{a|b|c|d}", seed=seed, mode="deck")[2] for seed in range(4)) == ["a", "b", "c", "d"]


def test_deck_same_list_twice_in_a_prompt_gives_different_options():
    for seed in range(10):
        first, second = prompts.resolve_prompts(("{a|b|c} {a|b|c}",), DeckPicker(random.Random(seed), seed, {}))[0].split(" ")
        assert first != second


def test_shuffle_mode_goes_through_every_option():
    assert sorted(run("{a|b|c|d|e}", seed=seed, mode="shuffle")[2] for seed in range(5)) == list("abcde")


def test_mutate_changes_exactly_one_choice_per_run():
    text = "{a1|a2|a3|a4} {b1|b2|b3|b4} {c1|c2|c3|c4}"
    previous = run(text, mode="mutate")[2].split(" ")
    for seed in range(1, 11):
        current = run(text, seed=seed, mode="mutate")[2].split(" ")
        assert sum(a != b for a, b in zip(previous, current)) == 1, (previous, current)
        previous = current


@pytest.mark.parametrize("mode", ["shuffle", "balanced", "mutate"])
def test_remembering_modes_give_a_seed_its_prompt_again(mode):
    text = "{a|b|c|d|e} {x|y|z}"
    first = [run(text, seed=seed, mode=mode)[2] for seed in range(5)]
    assert [run(text, seed=seed, mode=mode)[2] for seed in (3, 0, 4)] == [first[3], first[0], first[4]] # Older seeds again: their prompts.
    fifth = run(text, seed=5, mode=mode)[2]
    assert run(text, seed=5, mode=mode)[2] == fifth
    if mode == "shuffle": # Replaying didn't move the shuffle on: the next new seeds still finish the round.
        assert sorted(prompt.split(" ")[0] for prompt in first) == list("abcde")


def test_the_cache_is_only_skipped_when_wildcard_files_change():
    assert Node.fingerprint_inputs(seed_mode="shuffle") == Node.fingerprint_inputs(seed_mode="random") # Same seed, same prompts: the cache is right.


def test_the_node_sends_its_prompts_to_the_page_preview(wildcards):
    from DiceForge.clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative
    wildcards("color.txt", "red\n")
    output = CLIPTextEncodePositiveNegative.execute("a __color__ car", "{lowres|lowres}", seed=7, seed_mode="deck")
    assert output.ui == {"dice_forge_prompts": [{"positive": "a red car", "negative": "lowres", "seed": 7, "seed_mode": "deck", "note": ""}]}
    combinations = CLIPTextEncodePositiveNegative.execute("{a|b}", "", seed=1, seed_mode="combinations").ui["dice_forge_prompts"][0]
    assert combinations["positive"] == "b" and combinations["note"] == "combination 2 of 2"


@pytest.fixture
def lora_calls(monkeypatch):
    """A stand-in for the core LoRA loader: each call is recorded as (file, strength model, strength clip)."""
    calls = []
    monkeypatch.setattr(Node.loader, "load_lora", lambda model, clip, name, sm, sc: (calls.append((name, sm, sc)) or (model and f"{model}+{name}", clip and f"{clip}+{name}")))
    return calls


def test_lora_tags_go_on_the_model_and_leave_the_text(models, lora_calls):
    for name in ("style/ink.safetensors", "detail.safetensors"):
        models("loras", name)
    result = Node.execute("1girl, <lora:ink:0.8>, smile <LORA:detail.safetensors>", "lowres, <lyco:style/ink:0.5:0.25>", seed=0, model="model").result
    assert result[2] == "1girl, smile" and result[3] == "lowres"
    assert lora_calls == [("style/ink.safetensors", 0.8, 0), ("detail.safetensors", 1.0, 0), ("style/ink.safetensors", 0.5, 0)] # No CLIP: the model only.
    assert result[4] == "model+style/ink.safetensors+detail.safetensors+style/ink.safetensors"


def test_a_choice_can_pick_the_lora_and_a_missing_one_says_so(models, lora_calls):
    for name in ("a.safetensors", "b.safetensors"):
        models("loras", name)
    picked = {Node.execute("cat {<lora:a:1>|<lora:b:1>}", "", seed=seed, model="m").result[4] for seed in range(20)}
    assert picked == {"m+a.safetensors", "m+b.safetensors"}
    assert Node.execute("no tags", "", seed=0, model="m").result[4] == "m" and len(lora_calls) == 20 # Passed through.
    with pytest.raises(ValueError, match="no LoRA file for <lora:nope>"):
        Node.execute("<lora:nope:1>", "", seed=0, model="m")


def test_both_prompt_nodes_share_what_a_list_remembers():
    """A list's shuffle round is kept by its options, not by the node: the same list in CLIP Dual Text Encode and Wildcards to Text (or two nodes of
    either) deals from one round between them, and a seed that came before, in either node, gives its pick again."""
    text = "{a|b|c|d}"
    picks = []
    for seed in (11, 12):
        picks.append(run(text, seed=seed, mode="shuffle")[2])
        picks.append(WildcardsToText.execute(text, seed=seed + 100, seed_mode="shuffle").result[0])
    assert sorted(picks) == ["a", "b", "c", "d"] # One round between the two nodes.
    assert WildcardsToText.execute(text, seed=11, seed_mode="shuffle").result[0] == picks[0] # Seed 11 came before, in the CLIP node.
    assert run("{a|b|c|d|e}", seed=11, mode="shuffle")[2] in "abcde" # Another list: its own round.


def test_wildcards_to_text_fills_in_like_the_clip_node():
    text = "a {red|green|blue|white} car, {2$$hat|scarf|bow}, ${c={big|small}}${c} dog // gone"
    for mode in ("random", "deck", "combinations"):
        for seed in range(4):
            filled = WildcardsToText.execute(text, seed=seed, seed_mode=mode)
            assert filled.result[0] == run(text, seed=seed, mode=mode)[2] # The same seed: the same text as CLIP Dual Text Encode.
            assert filled.ui == {"text": [filled.result[0]]}
    assert WildcardsToText.execute("  a  {x}  ,  b ", trim=True).result[0] == "a x, b"
    assert WildcardsToText.execute("<lora:style:0.8> a {cat|cat}").result[0] == "<lora:style:0.8> a cat" # LoRA tags stay in the text.
