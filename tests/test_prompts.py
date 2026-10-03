# Prompt syntax of CLIP Dual Text Encode without wildcard files: {a|b} choices, weights, multi-picks, variables, locks, escapes, comments, clean-up,
# and the seed modes of the node (combinations, mutate, deck, shuffle).
import random
from collections import Counter
import pytest
from DiceForge import clip_text_encode_pos_neg as prompts
from DiceForge.clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative as Node
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
    positive, negative, positive_text, negative_text = run("{a|b}", "bad", seed=1)
    assert positive is None and negative is None
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
    assert sorted(run("{a|b|c|d|e}", mode="shuffle")[2] for _ in range(5)) == list("abcde")


def test_mutate_changes_exactly_one_choice_per_run():
    text = "{a1|a2|a3|a4} {b1|b2|b3|b4} {c1|c2|c3|c4}"
    previous = run(text, mode="mutate")[2].split(" ")
    for _ in range(10):
        current = run(text, mode="mutate")[2].split(" ")
        assert sum(a != b for a, b in zip(previous, current)) == 1, (previous, current)
        previous = current


def test_remembering_modes_never_use_the_cache():
    assert Node.fingerprint_inputs(seed_mode="random")[1] is None
    first, second = Node.fingerprint_inputs(seed_mode="shuffle")[1], Node.fingerprint_inputs(seed_mode="shuffle")[1]
    assert first != second


def test_the_node_sends_its_prompts_to_the_page_preview(wildcards):
    from DiceForge.clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative
    wildcards("color.txt", "red\n")
    output = CLIPTextEncodePositiveNegative.execute("a __color__ car", "{lowres|lowres}", seed=7, seed_mode="deck")
    assert output.ui == {"dice_forge_prompts": [{"positive": "a red car", "negative": "lowres", "seed": 7, "seed_mode": "deck", "note": ""}]}
    combinations = CLIPTextEncodePositiveNegative.execute("{a|b}", "", seed=1, seed_mode="combinations").ui["dice_forge_prompts"][0]
    assert combinations["positive"] == "b" and combinations["note"] == "combination 2 of 2"
