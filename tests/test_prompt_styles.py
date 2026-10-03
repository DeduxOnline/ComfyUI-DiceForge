# Prompt styles (DiceForge/prompt_styles.py): the built-in family styles, your styles in an A1111 styles.csv, and the routes.
import pytest
from DiceForge import prompt_styles


def test_builtin_styles_put_the_quality_tags_first():
    assert [style["name"] for style in prompt_styles.BUILTIN] == ["Illustrious quality", "NoobAI quality", "NoobAI v-pred quality", "Anima quality"]
    for style in prompt_styles.BUILTIN:
        assert style["prompt"].endswith("{prompt}") and style["negative_prompt"].startswith("{prompt}") and style["note"]
        assert prompt_styles.checked(style)


def test_an_a1111_styles_csv_is_read_as_it_is():
    text = '﻿name,prompt,negative_prompt\nCinematic,"{prompt}, film grain, 35mm","cartoon, 3d"\n,no name,\nEmpty,,\ncinematic,dup,\nOnly negative,,"blurry"\n'
    assert prompt_styles.parse_styles(text) == [
        {"name": "Cinematic", "prompt": "{prompt}, film grain, 35mm", "negative_prompt": "cartoon, 3d"},
        {"name": "Only negative", "prompt": "", "negative_prompt": "blurry"}]


def test_list_save_replace_and_delete(api):
    status, body = api("GET", "/diceforge/styles")
    assert status == 200 and body["user"] == [] and body["builtin"][0]["name"] == "Illustrious quality"
    assert api("POST", "/diceforge/styles", json={"name": "b", "prompt": "x, {prompt}"})[0] == 200
    assert api("POST", "/diceforge/styles", json={"name": "A", "prompt": "y", "negative_prompt": "z"})[0] == 200
    assert api("POST", "/diceforge/styles", json={"name": "a", "prompt": "w"})[1]["prompt"] == "w" # Same name: replaced.
    assert [(style["name"], style["prompt"]) for style in api("GET", "/diceforge/styles")[1]["user"]] == [("a", "w"), ("b", "x, {prompt}")]
    with open(prompt_styles.STYLES_FILE, encoding="utf-8") as file:
        assert file.readline().strip() == "name,prompt,negative_prompt" # A1111's columns.
    assert api("DELETE", "/diceforge/styles?name=A")[0] == 200
    assert api("DELETE", "/diceforge/styles?name=A")[0] == 404


@pytest.mark.parametrize("body, status", [({"name": "Illustrious Quality", "prompt": "x"}, 409), ({"name": "", "prompt": "x"}, 400), ({"name": "x"}, 400),
                                          ({"name": "x" * 81, "prompt": "x"}, 400), ({"name": "x", "prompt": 5}, 400), ({"name": "x", "prompt": "x" * 20001}, 400)])
def test_bad_styles_are_refused(body, status, api):
    assert api("POST", "/diceforge/styles", json=body)[0] == status


def test_a_damaged_file_reads_as_no_styles():
    with open(prompt_styles.STYLES_FILE, "wb") as file:
        file.write(b"\xff\xfe\x00junk")
    assert prompt_styles.read_styles() == []
