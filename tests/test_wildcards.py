# Wildcard files of CLIP Dual Text Encode: __name__ from .txt and .yaml files, subfolders, globs, line weights, variables in names, multi-picks from a
# file, errors, and the index that follows file changes.
import os
import random
import time
from collections import Counter
import pytest
from DiceForge import clip_text_encode_pos_neg as prompts
from DiceForge.clip_text_encode_pos_neg import CLIPTextEncodePositiveNegative as Node
from DiceForge.seed_modes import RandomPicker


def resolve(positive, negative="", seed=0):
    return prompts.resolve_prompts((positive, negative), RandomPicker(random.Random(seed)))


def results(text, seeds=80):
    return {resolve(text, seed=seed)[0] for seed in range(seeds)}


def test_wildcard_picks_a_line_skipping_comments_and_empty_lines(wildcards):
    wildcards("color.txt", "# colors\nred\n\n  blue  \ngreen\n")
    assert results("__color__ hair") == {"red hair", "blue hair", "green hair"}


def test_wildcard_in_a_subfolder(wildcards):
    wildcards("styles/photo.txt", "35mm\nportrait lens\n")
    assert results("__styles/photo__") == {"35mm", "portrait lens"}


def test_lines_can_hold_choices_and_other_wildcards(wildcards):
    wildcards("color.txt", "red\nblue\n")
    wildcards("outfit.txt", "{long|short} __color__ dress\n")
    assert results("__outfit__") == {f"{length} {color} dress" for length in ("long", "short") for color in ("red", "blue")}


def test_missing_and_empty_wildcards_are_clear_errors(wildcards):
    wildcards("empty.txt", "# nothing here\n\n")
    with pytest.raises(ValueError, match="__nope__ not found"):
        resolve("__nope__")
    with pytest.raises(ValueError, match="__empty__ is empty"):
        resolve("__empty__")


def test_wildcards_that_include_each_other_stop_with_an_error(wildcards):
    wildcards("loop_a.txt", "__loop_b__\n")
    wildcards("loop_b.txt", "__loop_a__\n")
    with pytest.raises(ValueError, match="nested too deep"):
        resolve("__loop_a__")


def test_globs_join_the_lines_of_every_matching_file(wildcards):
    wildcards("hair/color.txt", "blonde hair\nred hair\n")
    wildcards("hair/style.txt", "bob cut\n")
    wildcards("eyes/color.txt", "green eyes\n")
    wildcards("hair/empty.txt", "")
    assert results("__hair/*__") == {"blonde hair", "red hair", "bob cut"}
    assert results("__*/color__") == {"blonde hair", "red hair", "green eyes"}
    with pytest.raises(ValueError, match="matches no wildcard files"):
        resolve("__nothing/*__")


def test_a_glob_is_not_mistaken_for_a_comment(wildcards):
    wildcards("hair/style.txt", "bob cut\n")
    assert resolve("__hair/*__ /* note */ ok")[0] == "bob cut ok"


def test_line_weights(wildcards):
    wildcards("weighted.txt", "8::common\n1::rare\n0::never\n")
    counts = Counter(resolve("__weighted__", seed=seed)[0] for seed in range(900))
    assert counts["never"] == 0 and 0.8 < counts["common"] / 900 < 0.97
    wildcards("off.txt", "0::a\n0::b\n")
    with pytest.raises(ValueError, match="weight 0"):
        resolve("__off__")


def test_yaml_wildcards(wildcards):
    wildcards("pack.yaml", "characters:\n  alice:\n    outfit: [blue dress, white apron]\n    hair: blonde hair\n  bob:\n    outfit:\n      - jeans\n")
    wildcards("styles/pk.yml", "photo:\n  - 35mm\n  - \"{analog|digital} film\"\n")
    assert results("__characters/alice/outfit__") == {"blue dress", "white apron"}
    assert results("__characters/alice/hair__") == {"blonde hair"}
    assert results("__characters/*/outfit__") == {"blue dress", "white apron", "jeans"}
    assert results("__styles/photo__") == {"35mm", "analog film", "digital film"}


def test_a_txt_file_hides_a_yaml_key_of_the_same_name_and_bad_yaml_is_skipped(wildcards):
    wildcards("color.txt", "red\n")
    wildcards("pack.yaml", "color: [from yaml]\nother: [x]\n")
    wildcards("broken.yaml", "bad: [unclosed\n")
    assert results("__color__") == {"red"}
    assert results("__other__") == {"x"}


def test_variable_in_a_wildcard_name(wildcards):
    wildcards("outfit/male.txt", "suit\ntuxedo\n")
    wildcards("outfit/female.txt", "dress\nskirt\n")
    for seed in range(40):
        positive, negative = resolve("${g={male|female}}${g}: __outfit/${g}__", "not __outfit/${g}__", seed)
        gender, outfit = positive.split(": ")
        assert outfit in {"male": {"suit", "tuxedo"}, "female": {"dress", "skirt"}}[gender]
        assert negative.split(" ")[1] in {"male": {"suit", "tuxedo"}, "female": {"dress", "skirt"}}[gender]
    assert resolve("__outfit/${g}__ ${g=male}")[0] in {"suit", "tuxedo"} # Set later in the same prompt.
    with pytest.raises(ValueError, match=r"\$\{zz\}"):
        resolve("__outfit/${zz}__")


def test_combinations_mode_refuses_a_variable_wildcard_name(wildcards):
    wildcards("outfit/male.txt", "suit\n")
    with pytest.raises(ValueError, match="combinations cannot count"):
        Node.execute("${g=male}__outfit/${g}__", "", clip=None, seed=0, seed_mode="combinations")


def test_multi_pick_from_a_wildcard(wildcards):
    wildcards("color.txt", "red\nblue\ngreen\nwhite\n")
    wildcards("outfit/female.txt", "dress\nskirt\n")
    for seed in range(50):
        chosen = resolve("{2$$__color__}", seed=seed)[0].split(", ")
        assert len(chosen) == len(set(chosen)) == 2 and set(chosen) <= {"red", "blue", "green", "white"}
    assert " and " in resolve("{2$$ and $$__color__}", seed=3)[0]
    assert set(resolve("${g=female}{2$$__outfit/${g}__}")[0].split(", ")) == {"dress", "skirt"}


def test_counting_combinations_with_wildcards(wildcards):
    wildcards("color.txt", "red\nblue\ngreen\n")
    wildcards("weighted.txt", "2::a\n0::off\nb\n")
    wildcards("hair/a.txt", "x\ny\n")
    wildcards("hair/b.txt", "z\n")
    assert prompts.count_combinations("__color__ {a|b}", {}) == 6
    assert prompts.count_combinations("__weighted__", {}) == 2
    assert prompts.count_combinations("__hair/*__", {}) == 3
    assert prompts.count_combinations("{2$$__color__}", {}) == 3


def test_combinations_mode_goes_through_every_wildcard_line(wildcards):
    wildcards("color.txt", "red\nblue\ngreen\n")
    got = [Node.execute("__color__ {cat|dog}", "", clip=None, seed=seed, seed_mode="combinations").result[2] for seed in range(6)]
    assert len(set(got)) == 6


def test_deck_mode_deals_every_wildcard_line(wildcards):
    wildcards("color.txt", "red\nblue\ngreen\nwhite\n")
    got = [Node.execute("__color__", "", clip=None, seed=seed, seed_mode="deck").result[2] for seed in range(4)]
    assert sorted(got) == ["blue", "green", "red", "white"]


def test_a_new_file_is_found_without_restarting(wildcards):
    wildcards("color.txt", "red\n")
    path = os.path.join(wildcards.folder, "late.txt")
    with open(path, "w", encoding="utf-8") as file:
        file.write("later\n")
    assert resolve("__late__")[0] == "later"


def test_the_node_runs_again_when_a_wildcard_file_changes(wildcards):
    path = wildcards("color.txt", "red\n")
    before = Node.fingerprint_inputs()
    stamp = time.time() + 10
    os.utime(path, (stamp, stamp))
    assert Node.fingerprint_inputs() != before


def test_wildcard_names_and_index(wildcards):
    wildcards("b.txt", "x\n")
    wildcards("A/c.txt", "x\n")
    wildcards("pack.yaml", "k: [x]\n")
    assert prompts.wildcard_names(refresh=True) == ["A/c", "b", "k"]
    assert prompts.find_wildcard("A/c").endswith(os.path.join("A", "c.txt"))
    assert prompts.find_wildcard("../outside") is None
