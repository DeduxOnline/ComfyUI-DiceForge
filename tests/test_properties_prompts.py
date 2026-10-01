# Invariants of the prompt syntax of CLIP Dual Text Encode, checked on generated prompts: any text either resolves or fails with a clear ValueError
# (never another error, never a hang, never a leftover placeholder); every output is one the prompt can make; combinations lists every possible
# prompt exactly once; locks, variables, escapes, comments and the clean-up keep their promises in every seed mode.
import itertools
import random
import re
import time
from collections import Counter
from hypothesis import assume, example, given, settings, strategies as st
from DiceForge import clip_text_encode_pos_neg as prompts
from DiceForge.clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative as Node
from DiceForge.seed_modes import RandomPicker
scaled = lambda count: max(1, count * settings.default.max_examples // 200) # Explicit budgets follow the profile (thorough: 15 times).

MODES = ["random", "deck", "shuffle", "balanced", "combinations", "mutate"]
REPRODUCIBLE = ["random", "deck", "combinations"]
seeds = st.integers(0, 2 ** 64 - 1)
words = st.text(alphabet="abcdefgh", min_size=1, max_size=5)


def run(positive, negative="", seed=0, mode="random", trim=True):
    return Node.execute(positive, negative, clip=None, seed=seed, seed_mode=mode, trim=trim).result[2:]


def resolve(text, seed=0):
    return prompts.resolve_prompts((text, ""), RandomPicker(random.Random(seed)))[0]


# Prompts made of literal text, {a|b} choices and {low-high$$sep$$a|b} multi-picks, nested; render() writes one as prompt text and outputs() lists
# every prompt it can make (ordered=True: multi-picks in option order, as combinations lists them; False: in any order, as the other modes pick).
literal = st.text(alphabet="abcxyz", max_size=3)


def tree(children):
    sequence = st.lists(children, max_size=3)
    choice = st.tuples(st.just("choice"), st.lists(sequence, min_size=1, max_size=4))
    # Multi-pick options written differently: the same text twice ({2$$a|a}) is one card in deck and shuffle but two options in random.
    multi = st.tuples(st.just("multi"), st.lists(sequence, min_size=1, max_size=4, unique_by=lambda option: render(option)), st.integers(0, 4), st.integers(0, 4),
                      st.sampled_from([None, "+", " and ", ""]))
    return st.one_of(choice, multi)


nodes = st.recursive(literal, tree, max_leaves=8)
prompt_trees = st.lists(nodes, min_size=1, max_size=4)


def render(sequence):
    text = ""
    for node in sequence:
        if isinstance(node, str):
            text += node
        elif node[0] == "choice":
            text += "{" + "|".join(render(option) for option in node[1]) + "}"
        else:
            _, options, low, high, separator = node
            head = f"{low}-{high}$$" + (f"{separator}$$" if separator is not None else "")
            text += "{" + head + "|".join(render(option) for option in options) + "}"
    return text


def outputs(sequence, ordered):
    results = [""]
    for node in sequence:
        if isinstance(node, str):
            made = [node]
        elif node[0] == "choice":
            made = [text for option in node[1] for text in outputs(option, ordered)]
        else:
            _, options, low, high, separator = node
            separator = ", " if separator is None else separator
            count = len(options)
            high = min(max(low, high), count)
            low = min(low, high)
            made = []
            for size in range(low, high + 1):
                for subset in (itertools.combinations if ordered else itertools.permutations)(range(count), size):
                    for parts in itertools.product(*(outputs(options[index], ordered) for index in subset)):
                        made.append(separator.join(parts))
        results = [before + after for before in results for after in made]
    return results


def possible_count(sequence):
    total = 1
    for node in sequence:
        if isinstance(node, str):
            continue
        if node[0] == "choice":
            total *= sum(possible_count(option) for option in node[1])
        else:
            _, options, low, high, _ = node
            high = min(max(low, high), len(options))
            low = min(low, high)
            total *= sum(math_prod(possible_count(options[index]) for index in subset) for size in range(low, high + 1)
                         for subset in itertools.permutations(range(len(options)), size))
    return total


def math_prod(values):
    result = 1
    for value in values:
        result *= value
    return result


# Fuzzing: any text built from the syntax characters resolves to plain text or fails with a ValueError, in every seed mode, quickly.
syntax_text = st.text(alphabet="ab {}|$=!:_\\/*,2-#\n", max_size=60)


@settings(max_examples=scaled(400))
@given(text=syntax_text, negative=syntax_text, seed=seeds, mode=st.sampled_from(MODES), trim=st.booleans())
@example(text="{" * 80 + "a" + "}" * 80, negative="", seed=0, mode="random", trim=True)
@example(text="${a=${b}}${b=${a}}${a}", negative="", seed=0, mode="random", trim=True)
@example(text="{99999999999999999999$$a|b}", negative="", seed=0, mode="combinations", trim=True)
@example(text="{2-1$$a|b|c}{-$$a}{$$a}{0$$a|b}", negative="", seed=0, mode="deck", trim=True)
def test_any_text_resolves_or_fails_with_a_clear_error(text, negative, seed, mode, trim, wildcards):
    started = time.perf_counter()
    try:
        positive_text, negative_text = run(text, negative, seed, mode, trim)
    except ValueError as error:
        assert str(error) # A message for the node's error, never an empty one.
        return
    finally:
        assert time.perf_counter() - started < 5
    for output in (positive_text, negative_text):
        assert isinstance(output, str)
        assert "\x00" not in output and "\x01" not in output # No placeholder of a variable or a counted choice leaks out.


@settings(max_examples=scaled(300))
@given(text=st.text(max_size=80), seed=seeds, mode=st.sampled_from(MODES))
def test_any_unicode_text_resolves_or_fails_with_a_clear_error(text, seed, mode, wildcards):
    assume("\x00" not in text and "\x01" not in text)
    try:
        positive_text, negative_text = run(text, text, seed, mode)
    except ValueError as error:
        assert str(error)
        return
    assert "\x00" not in positive_text + negative_text


@given(count=st.integers(1, 300))
def test_deep_nesting_is_an_error_not_a_crash(count, wildcards):
    for text in ("{" * count + "a" + "}" * count, "${v=" * count + "a" + "}" * count + "${v}", "{1$$" * count + "a" + "}" * count):
        try:
            run(text)
        except ValueError as error:
            assert "deep" in str(error) or "never set" in str(error)


def test_long_adversarial_prompts_stay_fast(wildcards):
    for text in ("_" * 3000 + "!", "__a " * 800 + "!", "{" * 2000, "|" * 3000, "$${" * 1000, ", ," * 1500, "\\" * 3000, "/*" * 1500, "__" + "a " * 1500):
        started = time.perf_counter()
        try:
            run(text, text, mode="combinations")
            run(text, text, mode="random")
        except ValueError:
            pass
        assert time.perf_counter() - started < 3, text[:20]


# Text without choice syntax comes out as written.
@given(tokens=st.lists(st.text(alphabet="abcXYZ0().:'é", min_size=1, max_size=8), min_size=1, max_size=10), joins=st.lists(st.sampled_from([" ", ", ", "\n"]), min_size=10, max_size=10), seed=seeds, mode=st.sampled_from(MODES))
def test_plain_text_comes_out_as_written(tokens, joins, seed, mode):
    text = "".join(token + join for token, join in zip(tokens, joins))[:-1]
    text = text.strip(" ,\n")
    assume(text and not re.search(r"\n *\n *\n", text))
    assert run(text, seed=seed, mode=mode, trim=False)[0] == text


# Every pick is a prompt the text can make, in every mode, and the reproducible modes give the same prompt for the same seed.
@settings(max_examples=scaled(150))
@given(sequence=prompt_trees, seed=seeds, mode=st.sampled_from(MODES))
def test_every_output_is_a_prompt_the_text_can_make(sequence, seed, mode):
    assume(possible_count(sequence) <= 3000)
    text = render(sequence)
    possible = {prompts.tidy_commas(output) for output in outputs(sequence, ordered=mode == "combinations")}
    output = run(text, seed=seed, mode=mode, trim=False)[0]
    assert output in possible, (text, output)
    if mode in REPRODUCIBLE:
        assert run(text, seed=seed, mode=mode, trim=False)[0] == output


# combinations: seeds 0, 1, 2... list every prompt the text can make exactly once, then start over.
@settings(max_examples=scaled(150))
@given(sequence=prompt_trees, start=st.integers(0, 10 ** 6))
def test_combinations_list_every_prompt_exactly_once(sequence, start):
    text = render(sequence)
    expected = Counter(prompts.tidy_commas(output) for output in outputs(sequence, ordered=True))
    total = sum(expected.values())
    assume(total <= 400)
    assert prompts.count_combinations(prompts.strip_comments(text), {}) == total
    first = start * total # Any whole cycle lists the same prompts.
    listed = Counter(run(text, seed=seed, mode="combinations", trim=False)[0] for seed in range(first, first + total))
    assert listed == expected, text
    assert run(text, seed=first + total + 3, mode="combinations", trim=False) == run(text, seed=3, mode="combinations", trim=False)


@settings(max_examples=scaled(60))
@given(choices=st.lists(st.integers(1, 5), min_size=1, max_size=4), negative=st.integers(1, 4))
def test_combinations_of_both_prompts_multiply(choices, negative):
    positive_text = " ".join("{" + "|".join(f"p{index}o{option}" for option in range(count)) + "}" for index, count in enumerate(choices))
    negative_text = "{" + "|".join(f"n{option}" for option in range(negative)) + "}"
    total = math_prod(choices) * negative
    listed = {run(positive_text, negative_text, seed=seed, mode="combinations") for seed in range(total)}
    assert len(listed) == total # Every pair once: positive and negative are counted together.


# Multi-picks give exactly the asked number of different options, joined by the separator, in every mode.
@given(options=st.lists(words, min_size=1, max_size=8, unique=True), low=st.integers(0, 10), span=st.integers(0, 10), separator=st.sampled_from([" + ", " and ", "|", "/"]),
       seed=seeds, mode=st.sampled_from(MODES))
def test_multi_pick_gives_different_options_within_the_count(options, low, span, separator, seed, mode):
    assume(separator != "|") # | separates options: \| is the separator then.
    text = "{" + f"{low}-{low + span}$${separator}$$" + "|".join(options) + "}"
    output = run(text, seed=seed, mode=mode, trim=False)[0]
    picked = output.split(separator.strip()) if output else []
    picked = [item.strip() for item in picked]
    high = min(low + span, len(options))
    assert min(low, high) <= len(picked) <= high
    assert len(picked) == len(set(picked)) and set(picked) <= set(options)


@given(options=st.lists(words, min_size=2, max_size=6, unique=True), zero=st.integers(0, 5), seed=seeds, mode=st.sampled_from(MODES))
def test_options_of_weight_zero_never_come(options, zero, seed, mode):
    zero %= len(options)
    text = "{" + "|".join(("0::" if index == zero else "") + option for index, option in enumerate(options)) + "}"
    assert run(text, seed=seed, mode=mode)[0] != options[zero]
    text = "{2$$" + "|".join(("0::" if index == zero else "2::") + option for index, option in enumerate(options)) + "}"
    assert options[zero] not in run(text, seed=seed, mode=mode)[0].split(", ")


@given(options=st.lists(words, min_size=2, max_size=6, unique=True), locked=st.sets(st.integers(0, 5), min_size=1, max_size=3), seed=seeds, mode=st.sampled_from(MODES))
def test_locked_options_always_come_in_every_mode(options, locked, seed, mode):
    locked = sorted({index % len(options) for index in locked})
    text = "{" + "|".join(("!" if index in locked else "") + option for index, option in enumerate(options)) + "} end"
    assert run(text, seed=seed, mode=mode)[0] == ", ".join(options[index] for index in locked) + " end"


# Variables: one value for every use, in both prompts, whether used before or after it's set.
@given(options=st.lists(words, min_size=1, max_size=5, unique=True), uses=st.integers(1, 4), before=st.booleans(), seed=seeds, mode=st.sampled_from(MODES))
def test_a_variable_has_one_value_everywhere(options, uses, before, seed, mode):
    setting = "${pick={" + "|".join(options) + "}}"
    body = " ".join(["${pick}"] * uses)
    positive = f"{body} {setting}" if before else f"{setting} {body}"
    positive_text, negative_text = run(positive, "${pick}", seed=seed, mode=mode)
    values = positive_text.split(" ")
    assert len(values) == uses and len(set(values)) == 1 and values[0] in options
    assert negative_text == values[0]


@given(value=st.text(alphabet="abc {}|", max_size=12), seed=seeds)
def test_variable_values_follow_the_choice_syntax(value, seed):
    depths = list(itertools.accumulate({"{": 1, "}": -1}.get(char, 0) for char in value))
    assume(not depths or (min(depths) >= 0 and depths[-1] == 0)) # Properly nested: a stray } would end ${v=...} early, as documented.
    try:
        direct = run(value, seed=seed, mode="combinations")[0]
        through = run("${v=" + value + "}${v}", seed=seed, mode="combinations")[0]
    except ValueError:
        return
    assert through == direct # The value is filled in once, like the same text in the prompt.


# Escapes: \{ \} \| \! give the character itself, never a choice.
@given(text=st.text(alphabet="ab{}|!$: ", max_size=30), seed=seeds, mode=st.sampled_from(MODES))
def test_escaped_syntax_comes_out_as_written(text, seed, mode):
    escaped = re.sub(r"([{}|!])", r"\\\1", text)
    assert run(escaped, seed=seed, mode=mode, trim=False)[0] == prompts.tidy_commas(text)


# Comments are removed, the rest stays.
@given(before=words, after=words, comment=st.text(alphabet="ab {}|_ *", max_size=15))
def test_comments_are_removed(before, after, comment):
    assume("*/" not in comment)
    assert run(f"{before} /*{comment}*/ {after}")[0] == f"{before} {after}"
    assert run(f"{before} //{comment}\n{after}")[0] == f"{before}\n{after}"


# Clean-up: comma tidying and the trim input are idempotent and only change spaces and commas.
cleanup_text = st.text(alphabet="ab ,\t\n().!?:;", max_size=60)


@given(text=cleanup_text)
def test_tidy_commas_is_idempotent_and_keeps_the_words(text):
    once = prompts.tidy_commas(text)
    assert prompts.tidy_commas(once) == once
    assert re.sub(r"[\s,]", "", once) == re.sub(r"[\s,]", "", text)
    assert once == once.strip(" \t\n,")
    assert not re.search(r",[ \t]*,", once) and "  " not in once


@given(text=st.text(alphabet="ab ,\t\n\r().!?:; 　", max_size=60))
def test_trim_spaces_is_idempotent_and_keeps_every_other_character(text):
    once = prompts.trim_spaces(text)
    assert prompts.trim_spaces(once) == once
    assert re.sub(r"\s", "", once) == re.sub(r"\s", "", text)
    assert once == once.strip() and "  " not in once and "\n\n\n" not in once
    for line in once.split("\n"):
        assert line == line.strip(" \t")
    assert not re.search(r" [,.;:!?)]|\( ", once)


# mutate: after the first run, each run changes exactly one choice of the last prompt.
@settings(max_examples=scaled(30))
@given(sizes=st.lists(st.integers(2, 4), min_size=1, max_size=5))
def test_mutate_changes_exactly_one_choice_per_run(sizes):
    text = " ".join("{" + "|".join(f"c{index}o{option}" for option in range(size)) + "}" for index, size in enumerate(sizes))
    last = run(text, mode="mutate")[0].split(" ")
    for _ in range(8):
        now = run(text, mode="mutate")[0].split(" ")
        assert sum(a != b for a, b in zip(last, now)) == 1, (last, now)
        last = now


# Wildcards: lines as written (comments, empty lines, indentation, Windows line ends and a UTF-8 BOM don't matter), every line dealt once per deck
# round, counted once by combinations, multi-picks of different lines, and names with spaces, subfolders and non-Latin letters.
line_text = st.text(alphabet="abcdefg xyzéä", min_size=1, max_size=10).map(str.strip).filter(bool)


@settings(max_examples=scaled(80))
@given(lines=st.lists(line_text, min_size=1, max_size=10, unique=True), crlf=st.booleans(), bom=st.booleans(), indent=st.sampled_from(["", "  ", "\t"]))
def test_wildcard_lines_are_read_as_written(lines, crlf, bom, indent, wildcards):
    newline = "\r\n" if crlf else "\n"
    text = ("﻿" if bom else "") + newline.join(["# comment", ""] + [indent + line for line in lines] + ["", "#tail"]) + newline
    with open(wildcards.folder / "w.txt", "w", encoding="utf-8", newline="") as file:
        file.write(text)
    prompts.wildcard_index(refresh=True)
    assert prompts.read_wildcard("w") == lines


@settings(max_examples=scaled(80))
@given(lines=st.lists(line_text, min_size=1, max_size=10, unique=True), bom=st.booleans())
def test_first_line_of_a_wildcard_with_bom_is_the_line(lines, bom, wildcards):
    with open(wildcards.folder / "w.txt", "w", encoding="utf-8-sig" if bom else "utf-8") as file:
        file.write("\n".join(lines))
    prompts.wildcard_index(refresh=True)
    assert {run("__w__", seed=seed, mode="deck")[0] for seed in range(len(lines))} == {prompts.trim_spaces(line) for line in lines}


@settings(max_examples=scaled(60))
@given(lines=st.lists(st.text(alphabet="abcdefgh", min_size=1, max_size=6), min_size=1, max_size=12, unique=True), round_number=st.integers(0, 10 ** 9))
def test_wildcard_deck_deals_every_line_once_per_round(lines, round_number, wildcards):
    wildcards("w.txt", "\n".join(lines))
    first = round_number * len(lines)
    assert sorted(run("__w__", seed=seed, mode="deck")[0] for seed in range(first, first + len(lines))) == sorted(lines)
    assert sorted(run("__w__", seed=seed, mode="combinations")[0] for seed in range(len(lines))) == sorted(lines)


@settings(max_examples=scaled(60))
@given(lines=st.lists(st.text(alphabet="abcdefgh", min_size=1, max_size=6), min_size=1, max_size=10, unique=True), count=st.integers(1, 12), seed=seeds,
       mode=st.sampled_from(MODES))
def test_multi_pick_from_a_wildcard_gives_different_lines(lines, count, seed, mode, wildcards):
    wildcards("w.txt", "\n".join(lines))
    picked = run("{" + f"{count}$$__w__" + "}", seed=seed, mode=mode)[0].split(", ")
    assert len(picked) == len(set(picked)) == min(count, len(lines)) and set(picked) <= set(lines)


name_part = st.text(alphabet="abcxyzабвгдеёжзиклмнопрстуфхцчшщъыьэюя0123456789-_.", min_size=1, max_size=6).filter(lambda part: part.strip("_") == part and part not in (".", ".."))


@settings(max_examples=scaled(80))
@given(parts=st.lists(st.lists(name_part, min_size=1, max_size=2).map(" ".join), min_size=1, max_size=3), line=words)
def test_wildcard_names_with_spaces_folders_and_any_letters(parts, line, wildcards):
    name = "/".join(parts)
    assume(not name.endswith("_") and "__" not in name)
    wildcards(name + ".txt", line + "\n")
    assert run(f"x __{name}__ y")[0] == f"x {line} y"
    assert name in prompts.wildcard_names()


@given(weights=st.lists(st.integers(0, 4), min_size=2, max_size=6))
def test_wildcard_line_weights_like_choice_weights(weights, wildcards):
    assume(any(weights))
    wildcards("w.txt", "\n".join(f"{weight}::line{index}" for index, weight in enumerate(weights)))
    dealt = Counter(run("__w__", seed=seed, mode="deck")[0] for seed in range(sum(weights)))
    assert dealt == {f"line{index}": weight for index, weight in enumerate(weights) if weight} # A deck round deals each line as often as its weight.


# Huge or odd weights: no crash and no hang.
@given(digits=st.integers(1, 400), mode=st.sampled_from(MODES), seed=seeds)
@example(digits=400, mode="deck", seed=0)
@example(digits=12, mode="shuffle", seed=0)
def test_huge_weights_neither_crash_nor_hang(digits, mode, seed, wildcards):
    weight = "9" * digits
    started = time.perf_counter()
    for text in (f"{{{weight}::a|b}}", f"{{2$${weight}::a|{weight}.5::b|c}}", f"{{{weight}::a|0::b}}"):
        output = run(text, seed=seed, mode=mode)[0]
        assert set(output.split(", ")) <= {"a", "b", "c"}
    assert time.perf_counter() - started < 3


def test_huge_weights_still_favour_the_heavy_option():
    counts = Counter(resolve("{1000000::a|b}", seed) for seed in range(200))
    assert counts["a"] >= 195
    counts = Counter(run("{1000000::a|b}", seed=seed, mode="deck")[0] for seed in range(200))
    assert counts["a"] >= 195
