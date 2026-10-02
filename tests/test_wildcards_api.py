# Server routes of the Wildcard Browser and the __ autocomplete (DiceForge/wildcards_api.py): listing, creating, reading, saving, renaming and deleting
# wildcard files.
import os
import folder_paths
import pytest
from aiohttp import web
from DiceForge.wildcards_api import checked_name


@pytest.mark.parametrize("name, expected", [("color", "color"), ("hair/long.txt", "hair/long"), ("a\\b", "a/b"), (" my list ", "my list")])
def test_checked_name_accepts(name, expected):
    assert checked_name(name) == expected


@pytest.mark.parametrize("name", ["../x", "a/../b", "", "a//b", "bad|name", "/abs", "two  spaces", "a /b"])
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


def test_create_refuses_a_taken_name(api, wildcards):
    wildcards("color.txt", "red\n")
    wildcards("pack.yaml", "outfit: [dress]\n")
    for name in ("color", "outfit"):
        status, text = api("POST", "/diceforge/wildcards/file", {"name": name, "text": "", "create": True})
        assert status == 409 and "already exists" in text
    with open(os.path.join(wildcards.folder, "color.txt"), encoding="utf-8") as file:
        assert file.read() == "red\n" # "+ New file" with a taken name doesn't empty the file.
    status, body = api("POST", "/diceforge/wildcards/file", {"name": "fresh", "text": "", "create": True})
    assert status == 200 and body["saved"] == "fresh"


def test_rename_and_move(api, wildcards):
    wildcards("color.txt", "red\nblue\n")
    status, body = api("POST", "/diceforge/wildcards/rename", {"name": "color", "to": "palette/warm"})
    assert status == 200 and body == {"renamed": "color", "to": "palette/warm", "path": os.path.join(str(wildcards.folder), "palette", "warm.txt")}
    assert not os.path.exists(os.path.join(wildcards.folder, "color.txt"))
    assert api("GET", "/diceforge/wildcards/file?name=palette/warm")[1]["text"] == "red\nblue"
    names = {entry["name"] for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert names == {"palette/warm"}
    # Moved out again: the folder left empty goes too.
    assert api("POST", "/diceforge/wildcards/rename", {"name": "palette/warm", "to": "warm"})[0] == 200
    assert os.listdir(wildcards.folder) == ["warm.txt"]


def test_rename_refusals(api, wildcards):
    wildcards("a.txt", "x\n")
    wildcards("b.txt", "y\n")
    wildcards("pack.yaml", "outfit: [dress]\n")
    assert api("POST", "/diceforge/wildcards/rename", {"name": "a", "to": "b"})[0] == 409
    assert api("POST", "/diceforge/wildcards/rename", {"name": "a", "to": "outfit"})[0] == 409 # A yaml name would be hidden by the file.
    assert api("POST", "/diceforge/wildcards/rename", {"name": "nope", "to": "c"})[0] == 404
    status, text = api("POST", "/diceforge/wildcards/rename", {"name": "outfit", "to": "c"})
    assert status == 400 and "yaml" in text
    for to in ("../escape", "", None, 5):
        assert api("POST", "/diceforge/wildcards/rename", {"name": "a", "to": to})[0] == 400
    assert api("POST", "/diceforge/wildcards/rename", {"name": "a", "to": "a"})[0] == 200 # The same name: nothing to do.
    with open(os.path.join(wildcards.folder, "a.txt"), encoding="utf-8") as file:
        assert file.read() == "x\n"
    assert sorted(os.listdir(wildcards.folder)) == ["a.txt", "b.txt", "pack.yaml"]


def test_rename_stays_in_its_wildcards_folder(api, wildcards, tmp_path, monkeypatch):
    second = tmp_path / "more"
    (second / "deep").mkdir(parents=True)
    (second / "deep" / "list.txt").write_text("z\n", encoding="utf-8")
    monkeypatch.setitem(folder_paths.folder_names_and_paths, "wildcards", ([str(wildcards.folder), str(second)], set()))
    status, body = api("POST", "/diceforge/wildcards/rename", {"name": "deep/list", "to": "other"})
    assert status == 200 and body["path"] == os.path.join(str(second), "other.txt")
    assert os.listdir(second) == ["other.txt"] and os.listdir(wildcards.folder) == []


def test_delete(api, wildcards):
    wildcards("keep.txt", "k\n")
    wildcards("hair/style/long.txt", "l\n")
    status, body = api("DELETE", "/diceforge/wildcards/file?name=hair/style/long")
    assert status == 200 and body["deleted"] == "hair/style/long"
    assert os.listdir(wildcards.folder) == ["keep.txt"] # The empty hair/style folders went with it.
    assert api("GET", "/diceforge/wildcards/file?name=hair/style/long")[0] == 404
    assert api("DELETE", "/diceforge/wildcards/file?name=hair/style/long")[0] == 404
    assert api("DELETE", "/diceforge/wildcards/file?name=../keep")[0] == 400
    assert api("DELETE", "/diceforge/wildcards/file")[0] == 400
    assert os.listdir(wildcards.folder) == ["keep.txt"]


def test_delete_keeps_yaml_and_folders_with_other_files(api, wildcards):
    wildcards("pack.yaml", "outfit: [dress]\n")
    wildcards("hair/a.txt", "a\n")
    wildcards("hair/b.txt", "b\n")
    status, text = api("DELETE", "/diceforge/wildcards/file?name=outfit")
    assert status == 400 and "yaml" in text
    assert api("DELETE", "/diceforge/wildcards/file?name=hair/a")[0] == 200
    assert os.listdir(os.path.join(wildcards.folder, "hair")) == ["b.txt"]
    assert os.path.isfile(os.path.join(wildcards.folder, "pack.yaml"))


def test_delete_shows_the_file_it_was_hiding(api, wildcards, tmp_path, monkeypatch):
    second = tmp_path / "more"
    second.mkdir()
    (second / "color.txt").write_text("from the second folder\n", encoding="utf-8")
    wildcards("color.txt", "from the first folder\n")
    monkeypatch.setitem(folder_paths.folder_names_and_paths, "wildcards", ([str(wildcards.folder), str(second)], set()))
    assert api("DELETE", "/diceforge/wildcards/file?name=color")[0] == 200
    assert api("GET", "/diceforge/wildcards/file?name=color")[1]["text"] == "from the second folder"
