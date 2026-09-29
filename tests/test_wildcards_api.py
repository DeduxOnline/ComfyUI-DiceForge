# Server routes of the Wildcard Browser and the __ autocomplete (DiceForge/wildcards_api.py): listing, reading, saving and creating wildcard files.
import os
import pytest
from aiohttp import web
from DiceForge.wildcards_api import checked_name


@pytest.mark.parametrize("name, expected", [("color", "color"), ("hair/long.txt", "hair/long"), ("a\\b", "a/b"), (" my list ", "my list")])
def test_checked_name_accepts(name, expected):
    assert checked_name(name) == expected


@pytest.mark.parametrize("name", ["../x", "a/../b", "", "a//b", "bad|name", "/abs"])
def test_checked_name_refuses(name):
    with pytest.raises(web.HTTPBadRequest):
        checked_name(name)


def test_list_read_and_save(api, wildcards):
    wildcards("color.txt", "# comment\nred\nblue\n\ngreen\nwhite\n")
    wildcards("hair/style.txt", "bob\n")
    wildcards("pack.yaml", "outfit: [dress, suit]\n")
    status, body = api("GET", "/diceforge/wildcards")
    files = {entry["name"]: entry for entry in body["files"]}
    assert status == 200 and set(files) == {"color", "hair/style", "outfit"}
    assert files["color"]["lines"] == 4 and files["color"]["preview"] == ["red", "blue", "green"]
    assert files["outfit"]["yaml"] == "pack.yaml" and "yaml" not in files["color"]
    status, body = api("GET", "/diceforge/wildcards/file?name=color")
    assert status == 200 and body["text"] == "# comment\nred\nblue\n\ngreen\nwhite"
    assert api("POST", "/diceforge/wildcards/file", {"name": "color", "text": "black\r\nwhite\n\n"})[0] == 200
    with open(os.path.join(wildcards.folder, "color.txt"), encoding="utf-8") as file:
        assert file.read() == "black\nwhite\n"


def test_new_files_and_folders(api, wildcards):
    status, body = api("POST", "/diceforge/wildcards/file", {"name": "new/deep/list", "text": "a\nb"})
    assert status == 200 and body["saved"] == "new/deep/list"
    assert os.path.isfile(os.path.join(wildcards.folder, "new", "deep", "list.txt"))
    assert api("POST", "/diceforge/wildcards/file", {"name": "../escape", "text": "x"})[0] == 400
    assert api("GET", "/diceforge/wildcards/file?name=nope")[0] == 404


def test_yaml_wildcards_are_read_only(api, wildcards):
    wildcards("pack.yaml", "outfit: [dress, suit]\n")
    status, body = api("GET", "/diceforge/wildcards/file?name=outfit")
    assert status == 200 and body["readonly"] is True and body["text"] == "dress\nsuit"
    status, text = api("POST", "/diceforge/wildcards/file", {"name": "outfit", "text": "x"})
    assert status == 400 and "yaml" in text
