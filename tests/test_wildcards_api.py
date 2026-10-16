# Server routes of the Wildcard Browser and the __ autocomplete (DiceForge/wildcards_api.py): listing, creating, reading, saving, renaming and deleting
# wildcard files.
import io
import os
import re
import zipfile
import folder_paths
import pytest
import yaml
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


def test_card_pictures_of_a_yaml_card_pack(api, wildcards):
    # A card pack: POSES.yaml with name: prompt pairs, and POSES/<name>.jpeg next to it; or a folder named like the file.
    wildcards("POSES.yaml", "  POSES:\n    sitting: sitting,\n    bent over:  bent over,\n    no-picture: standing,\n    ../../evil: x\n")
    os.makedirs(os.path.join(wildcards.folder, "POSES"))
    for name in ("sitting.jpeg", "bent over.png"):
        with open(os.path.join(wildcards.folder, "POSES", name), "wb") as file:
            file.write(b"picture " + name.encode())
    wildcards("styles/pack.yml", "ink: inked lines\n")
    os.makedirs(os.path.join(wildcards.folder, "styles", "pack"))
    with open(os.path.join(wildcards.folder, "styles", "pack", "ink.webp"), "wb") as file:
        file.write(b"ink picture")
    with open(os.path.join(os.path.dirname(wildcards.folder), "evil.png"), "wb") as file: # What ../../evil reaches from POSES: outside, never served.
        file.write(b"no")
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert [name for name, entry in sorted(files.items()) if entry.get("picture")] == ["POSES/bent over", "POSES/sitting", "styles/ink"]
    assert files["POSES/sitting"]["preview"] == ["sitting,"]
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/sitting") == (200, "picture sitting.jpeg")
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/bent%20over") == (200, "picture bent over.png")
    assert api("GET", "/diceforge/wildcards/picture?name=styles/ink") == (200, "ink picture")
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/no-picture")[0] == 404
    assert api("GET", "/diceforge/wildcards/picture?name=../x")[0] == 400


def test_new_files_and_folders(api, wildcards):
    status, body = api("POST", "/diceforge/wildcards/file", {"name": "new/deep/list", "text": "a\nb"})
    assert status == 200 and body["saved"] == "new/deep/list"
    assert os.path.isfile(os.path.join(wildcards.folder, "new", "deep", "list.txt"))
    assert api("POST", "/diceforge/wildcards/file", {"name": "../escape", "text": "x"})[0] == 400
    assert api("GET", "/diceforge/wildcards/file?name=nope")[0] == 404


def read_pack(wildcards, name="pack.yaml"):
    with open(os.path.join(wildcards.folder, *name.split("/")), encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_a_yaml_key_is_saved_in_its_yaml_file(api, wildcards):
    wildcards("pack.yaml", "# my pack\noutfit: [dress, suit]\nhair:\n  color: red\n  style: [bob, '0123', 'yes']\nnote: {deep: [x]}\n")
    status, body = api("GET", "/diceforge/wildcards/file?name=outfit")
    assert status == 200 and body["yaml"] == "pack.yaml" and body["text"] == "dress\nsuit" and "readonly" not in body
    status, body = api("POST", "/diceforge/wildcards/file", {"name": "hair/color", "text": "red\r\n  dark brown  \n\n# a comment\n"})
    assert status == 200 and body["yaml"] == "pack.yaml" and body["path"] == os.path.join(str(wildcards.folder), "pack.yaml")
    # The key's lines in place (a single text becomes a list), the other keys as they were, in their order, "0123" and "yes" still texts.
    assert read_pack(wildcards) == {"outfit": ["dress", "suit"], "hair": {"color": ["red", "dark brown", "# a comment"], "style": ["bob", "0123", "yes"]}, "note": {"deep": ["x"]}}
    assert list(read_pack(wildcards)) == ["outfit", "hair", "note"]
    assert api("GET", "/diceforge/wildcards/file?name=hair/color")[1]["text"] == "red\ndark brown\n# a comment"
    assert not any(name.endswith(".txt") for name in os.listdir(wildcards.folder)) # No txt file to hide the key.


def test_a_yaml_file_whole_read_saved_as_written_and_deleted(api, wildcards):
    text = "# my poses\nPOSES:\n  sitting: [sitting, on a chair]\n  standing: standing,\n"
    wildcards("packs/poses.yaml", text)
    wildcards("color.txt", "red\n")
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert files["packs/POSES/sitting"]["yaml_file"] == "packs/poses.yaml" and "yaml_file" not in files["color"]
    status, body = api("GET", "/diceforge/wildcards/yaml?file=packs/poses.yaml")
    assert status == 200 and body["text"] == text.rstrip("\n") and body["path"] == os.path.join(str(wildcards.folder), "packs", "poses.yaml")
    edited = text + "  # new\n  kneeling: kneeling,\n"
    assert api("POST", "/diceforge/wildcards/yaml", {"file": "packs/poses.yaml", "text": edited.replace("\n", "\r\n")})[0] == 200
    with open(os.path.join(wildcards.folder, "packs", "poses.yaml"), encoding="utf-8") as file:
        assert file.read() == edited # As written: its comments too.
    assert api("GET", "/diceforge/wildcards/file?name=packs/POSES/kneeling")[1]["text"] == "kneeling,"
    for junk in ("POSES:\n  broken: [x", "- a list\n- of lines\n"): # Not yaml, or not keys: nothing saved.
        status, message = api("POST", "/diceforge/wildcards/yaml", {"file": "packs/poses.yaml", "text": junk})
        assert status == 400 and "nothing was saved" in message
    with open(os.path.join(wildcards.folder, "packs", "poses.yaml"), encoding="utf-8") as file:
        assert file.read() == edited
    assert api("GET", "/diceforge/wildcards/yaml?file=color.txt")[0] == 404 # Only the yaml files of wildcards.
    assert api("GET", "/diceforge/wildcards/yaml?file=../x.yaml")[0] == 400
    status, body = api("DELETE", "/diceforge/wildcards/yaml?file=packs/poses.yaml")
    assert status == 200 and not os.path.exists(os.path.join(wildcards.folder, "packs"))
    assert api("POST", "/diceforge/wildcards/restore", {"id": body["undo"]})[1]["restored"] == "packs/poses.yaml"
    with open(os.path.join(wildcards.folder, "packs", "poses.yaml"), encoding="utf-8") as file:
        assert file.read() == edited


def test_a_keys_change_keeps_the_yaml_files_comments_and_layout(api, wildcards):
    wildcards("POSES.yaml", "# pack\n  POSES:\n    # standing poses\n    standing: standing,\n    sitting: sitting,   # comfy\n    lying: lying,\n# the end\n")
    path = os.path.join(wildcards.folder, "POSES.yaml")
    def text():
        with open(path, encoding="utf-8") as file:
            return file.read()
    assert api("POST", "/diceforge/wildcards/file", {"name": "POSES/standing", "text": "standing, arms crossed"})[0] == 200
    assert text() == "# pack\n  POSES:\n    # standing poses\n    standing: standing, arms crossed\n    sitting: sitting,   # comfy\n    lying: lying,\n# the end\n"
    assert api("POST", "/diceforge/wildcards/file", {"name": "POSES/kneeling", "text": "kneeling,", "create": True, "next_to": "POSES/lying"})[0] == 200
    assert api("POST", "/diceforge/wildcards/rename", {"name": "POSES/lying", "to": "POSES/reclining"})[0] == 200
    assert text() == "# pack\n  POSES:\n    # standing poses\n    standing: standing, arms crossed\n    sitting: sitting,   # comfy\n    reclining: lying,\n    kneeling: kneeling,\n# the end\n"
    undo = api("DELETE", "/diceforge/wildcards/file?name=POSES/sitting")[1]["undo"]
    assert text() == "# pack\n  POSES:\n    # standing poses\n    standing: standing, arms crossed\n    reclining: lying,\n    kneeling: kneeling,\n# the end\n"
    assert api("POST", "/diceforge/wildcards/restore", {"id": undo})[0] == 200 # Back in its place.
    assert text() == "# pack\n  POSES:\n    # standing poses\n    standing: standing, arms crossed\n    sitting: sitting,\n    reclining: lying,\n    kneeling: kneeling,\n# the end\n"
    assert api("POST", "/diceforge/wildcards/file", {"name": "POSES/sitting", "text": "sitting,\non a chair"})[0] == 200
    assert text() == "# pack\n  POSES:\n    # standing poses\n    standing: standing, arms crossed\n    sitting:\n    - sitting,\n    - on a chair\n    reclining: lying,\n    kneeling: kneeling,\n# the end\n"


def test_a_new_key_goes_into_the_yaml_file_of_the_wildcard_it_is_next_to(api, wildcards):
    wildcards("POSES.yaml", "POSES:\n  sitting: sitting,\n")
    wildcards("styles/pack.yml", "ink: inked lines\n")
    status, body = api("POST", "/diceforge/wildcards/file", {"name": "POSES/kneeling", "text": "kneeling,", "create": True, "next_to": "POSES/sitting"})
    assert status == 200 and body["yaml"] == "POSES.yaml"
    assert read_pack(wildcards, "POSES.yaml") == {"POSES": {"sitting": "sitting,", "kneeling": "kneeling,"}} # One line: key: text, as card packs write it.
    assert api("POST", "/diceforge/wildcards/file", {"name": "POSES/group/two", "text": "a", "create": True, "next_to": "POSES/sitting"})[0] == 200
    assert read_pack(wildcards, "POSES.yaml")["POSES"]["group"] == {"two": "a"}
    # styles/pack.yml's wildcards are named styles/...: another name can't be one of its keys.
    status, text = api("POST", "/diceforge/wildcards/file", {"name": "other/thing", "text": "a", "create": True, "next_to": "styles/ink"})
    assert status == 400 and "styles/" in text
    assert api("POST", "/diceforge/wildcards/file", {"name": "styles/wash", "text": "watercolor", "create": True, "next_to": "styles/ink"})[0] == 200
    assert read_pack(wildcards, "styles/pack.yml") == {"ink": "inked lines", "wash": "watercolor"}
    # Inside a wildcard, as if it were a folder; a name taken; next to something that is not a yaml wildcard.
    assert api("POST", "/diceforge/wildcards/file", {"name": "POSES/sitting/low", "text": "a", "create": True, "next_to": "POSES/sitting"})[0] == 409
    assert api("POST", "/diceforge/wildcards/file", {"name": "POSES/kneeling", "text": "a", "create": True, "next_to": "POSES/sitting"})[0] == 409
    wildcards("color.txt", "red\n")
    for next_to in ("color", "nope", "../x", 5):
        assert api("POST", "/diceforge/wildcards/file", {"name": "POSES/new", "text": "a", "create": True, "next_to": next_to})[0] == 400
    assert "new" not in read_pack(wildcards, "POSES.yaml")["POSES"]


def test_a_yaml_key_is_renamed_and_moved_among_its_files_keys_with_its_picture(api, wildcards):
    wildcards("POSES.yaml", "POSES:\n  sitting: sitting,\n  standing: standing,\n  lying: lying,\n")
    wildcards("styles/pack.yml", "ink: inked lines\n")
    wildcards("color.txt", "red\n")
    assert api("POST", "/diceforge/wildcards/picture?name=POSES/standing", data=PNG)[0] == 200
    assert api("POST", "/diceforge/wildcards/favorite", {"name": "POSES/standing", "favorite": True})[0] == 200
    status, body = api("POST", "/diceforge/wildcards/rename", {"name": "POSES/standing", "to": "POSES/upright"})
    assert status == 200 and body["to"] == "POSES/upright"
    assert list(read_pack(wildcards, "POSES.yaml")["POSES"]) == ["sitting", "upright", "lying"] # In its place.
    assert os.listdir(os.path.join(wildcards.folder, "POSES")) == ["upright.png"] # The card's picture went along,
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert files["POSES/upright"]["picture"] is True and files["POSES/upright"]["favorite"] is True # and its star.
    assert api("POST", "/diceforge/wildcards/rename", {"name": "POSES/upright", "to": "POSES/still/upright"})[0] == 200 # Into a "folder" of keys.
    assert read_pack(wildcards, "POSES.yaml") == {"POSES": {"sitting": "sitting,", "lying": "lying,", "still": {"upright": "standing,"}}}
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/still/upright") == (200, PNG)
    assert not os.path.exists(os.path.join(wildcards.folder, "POSES", "upright.png"))
    # Out of the yaml file's names (styles/pack.yml's are styles/...), to a name taken, onto itself.
    status, text = api("POST", "/diceforge/wildcards/rename", {"name": "styles/ink", "to": "ink"})
    assert status == 400 and "→ txt" in text
    assert api("POST", "/diceforge/wildcards/rename", {"name": "POSES/sitting", "to": "POSES/lying"})[0] == 409
    assert api("POST", "/diceforge/wildcards/rename", {"name": "POSES/sitting", "to": "color"})[0] == 409
    assert api("POST", "/diceforge/wildcards/rename", {"name": "POSES/sitting", "to": "POSES/sitting"})[0] == 200
    assert read_pack(wildcards, "POSES.yaml") == {"POSES": {"sitting": "sitting,", "lying": "lying,", "still": {"upright": "standing,"}}}


def test_a_deleted_yaml_key_comes_back_with_its_picture_and_star(api, wildcards):
    wildcards("POSES.yaml", "POSES:\n  sitting: sitting,\n  group:\n    two: [a, b]\n")
    assert api("POST", "/diceforge/wildcards/picture?name=POSES/group/two", data=PNG)[0] == 200
    assert api("POST", "/diceforge/wildcards/favorite", {"name": "POSES/group/two", "favorite": True})[0] == 200
    status, body = api("DELETE", "/diceforge/wildcards/file?name=POSES/group/two")
    assert status == 200 and body["undo"]
    assert read_pack(wildcards, "POSES.yaml") == {"POSES": {"sitting": "sitting,"}} # The key, and the "folder" it left empty.
    assert not os.path.exists(os.path.join(wildcards.folder, "POSES", "group")) # Its picture is in the trash.
    status, body = api("POST", "/diceforge/wildcards/restore", {"id": body["undo"]})
    assert status == 200 and body["restored"] == "POSES/group/two"
    assert read_pack(wildcards, "POSES.yaml") == {"POSES": {"sitting": "sitting,", "group": {"two": ["a", "b"]}}}
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert files["POSES/group/two"]["picture"] is True and files["POSES/group/two"]["favorite"] is True
    # The last key: the yaml file goes, and comes back with it.
    first = api("DELETE", "/diceforge/wildcards/file?name=POSES/sitting")[1]["undo"]
    second = api("DELETE", "/diceforge/wildcards/file?name=POSES/group/two")[1]["undo"]
    assert not os.path.exists(os.path.join(wildcards.folder, "POSES.yaml"))
    assert api("POST", "/diceforge/wildcards/restore", {"id": second})[0] == 200
    assert read_pack(wildcards, "POSES.yaml") == {"POSES": {"group": {"two": ["a", "b"]}}}
    api("POST", "/diceforge/wildcards/file", {"name": "POSES/sitting", "text": "a new one", "create": True, "next_to": "POSES/group/two"})
    assert api("POST", "/diceforge/wildcards/restore", {"id": first})[0] == 409 # The name is taken again: not overwritten.
    assert read_pack(wildcards, "POSES.yaml")["POSES"]["sitting"] == ["a new one"]


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
    assert api("POST", "/diceforge/wildcards/rename", {"name": "outfit", "to": "b"})[0] == 409 # A yaml key can't take a txt file's name.
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
    wildcards("pack.yaml", "outfit: [dress]\nshoes: [boots]\n")
    wildcards("hair/a.txt", "a\n")
    wildcards("hair/b.txt", "b\n")
    assert api("DELETE", "/diceforge/wildcards/file?name=outfit")[0] == 200
    assert read_pack(wildcards) == {"shoes": ["boots"]} # Only that key goes from the yaml file.
    assert api("DELETE", "/diceforge/wildcards/file?name=hair/a")[0] == 200
    assert os.listdir(os.path.join(wildcards.folder, "hair")) == ["b.txt"]


def test_delete_shows_the_file_it_was_hiding(api, wildcards, tmp_path, monkeypatch):
    second = tmp_path / "more"
    second.mkdir()
    (second / "color.txt").write_text("from the second folder\n", encoding="utf-8")
    wildcards("color.txt", "from the first folder\n")
    monkeypatch.setitem(folder_paths.folder_names_and_paths, "wildcards", ([str(wildcards.folder), str(second)], set()))
    assert api("DELETE", "/diceforge/wildcards/file?name=color")[0] == 200
    assert api("GET", "/diceforge/wildcards/file?name=color")[1]["text"] == "from the second folder"


def test_favorites_follow_renames_and_deletes(api, wildcards):
    wildcards("color.txt", "red\n")
    wildcards("hair/style.txt", "bob\n")
    wildcards("pack.yaml", "outfit: [dress]\n")
    favorite = lambda: {entry["name"] for entry in api("GET", "/diceforge/wildcards")[1]["files"] if entry["favorite"]}
    assert favorite() == set()
    for name in ("color", "outfit"): # A yaml wildcard can be a favorite too.
        assert api("POST", "/diceforge/wildcards/favorite", {"name": name, "favorite": True})[1] == {"name": name, "favorite": True}
    assert favorite() == {"color", "outfit"}
    assert api("POST", "/diceforge/wildcards/rename", {"name": "color", "to": "palette/color"})[0] == 200
    assert favorite() == {"palette/color", "outfit"} # The star moved with it.
    assert api("DELETE", "/diceforge/wildcards/file?name=palette/color")[0] == 200
    assert favorite() == {"outfit"}
    assert api("POST", "/diceforge/wildcards/favorite", {"name": "outfit", "favorite": False})[0] == 200
    assert favorite() == set()


@pytest.mark.parametrize("body, status", [({"name": "nope", "favorite": True}, 404), ({"name": "color", "favorite": "yes"}, 400), ({"name": "../x", "favorite": True}, 400),
                                          ({"name": 5, "favorite": True}, 400), ({"favorite": True}, 400)])
def test_favorite_refusals(body, status, api, wildcards):
    wildcards("color.txt", "red\n")
    assert api("POST", "/diceforge/wildcards/favorite", body)[0] == status
    assert api("POST", "/diceforge/wildcards/favorite", {"name": "gone", "favorite": False})[0] == 200 # Unstarring a missing name is harmless.


def test_a_damaged_favorites_file_means_none(api, wildcards):
    from DiceForge import wildcards_api
    wildcards("color.txt", "red\n")
    for junk in ("not json", "{}", "[1, null, \"color\"]"):
        with open(wildcards_api.FAVORITES_FILE, "w", encoding="utf-8") as file:
            file.write(junk)
        status, body = api("GET", "/diceforge/wildcards")
        assert status == 200 and body["files"][0]["favorite"] == (junk.endswith("]"))


def test_a_folder_of_txt_files_to_yaml_and_back(api, wildcards):
    wildcards("POSES/sitting.txt", "# a comment\nsitting\n\nsitting, legs crossed\n")
    wildcards("POSES/standing.txt", "standing\n")
    wildcards("POSES/deep/kneel.txt", "kneeling\n")
    with open(os.path.join(wildcards.folder, "POSES", "sitting.png"), "wb") as file:
        file.write(b"\x89PNG\r\n\x1a\nsitting")
    status, body = api("POST", "/diceforge/wildcards/convert", {"name": "POSES", "to": "yaml"})
    assert status == 200 and body["names"] == ["POSES/deep/kneel", "POSES/sitting", "POSES/standing"]
    with open(os.path.join(wildcards.folder, "POSES.yaml"), encoding="utf-8") as file:
        assert yaml.safe_load(file) == {"POSES": {"deep": {"kneel": ["kneeling"]}, "sitting": ["# a comment", "sitting", "sitting, legs crossed"],
                                                  "standing": ["standing"]}}
    assert not os.path.exists(os.path.join(wildcards.folder, "POSES", "sitting.txt")) # Moved into the yaml file, not copied: a txt would hide its key.
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert set(files) == {"POSES/deep/kneel", "POSES/sitting", "POSES/standing"} and files["POSES/sitting"]["yaml"] == "POSES.yaml"
    assert files["POSES/sitting"]["lines"] == 2 and files["POSES/sitting"]["picture"] is True # The same names; the picture is now its card's.
    status, body = api("POST", "/diceforge/wildcards/convert", {"name": "POSES/sitting", "to": "txt"}) # Any of its names: the whole yaml file.
    assert status == 200 and body["names"] == ["POSES/deep/kneel", "POSES/sitting", "POSES/standing"]
    assert not os.path.exists(os.path.join(wildcards.folder, "POSES.yaml"))
    with open(os.path.join(wildcards.folder, "POSES", "sitting.txt"), encoding="utf-8") as file:
        assert file.read() == "# a comment\nsitting\nsitting, legs crossed\n"
    assert os.path.isfile(os.path.join(wildcards.folder, "POSES", "deep", "kneel.txt")) and os.path.isfile(os.path.join(wildcards.folder, "POSES", "sitting.png"))


def test_one_txt_file_to_yaml_and_what_is_refused(api, wildcards):
    wildcards("styles/color.txt", "red\nyes\n{blue|green}\n")
    status, body = api("POST", "/diceforge/wildcards/convert", {"name": "styles/color", "to": "yaml"})
    assert status == 200 and body["path"].endswith(os.path.join("styles", "color.yaml"))
    assert api("GET", "/diceforge/wildcards/file?name=styles/color")[1]["text"] == "red\nyes\n{blue|green}" # Read back as written.
    wildcards("styles/color2.txt", "x\n")
    wildcards("styles/color2.yml", "color2: [y]\n")
    assert api("POST", "/diceforge/wildcards/convert", {"name": "styles/color2", "to": "yaml"})[0] == 409 # A yaml file of that name is there.
    wildcards("a.txt", "x\n")
    wildcards("a/b.txt", "y\n")
    status, text = api("POST", "/diceforge/wildcards/convert", {"name": "a", "to": "yaml"})
    assert status == 409 and "both a file and a folder" in text and os.path.isfile(os.path.join(wildcards.folder, "a.txt"))
    wildcards("pack.yaml", "hair: {color: [red], style: [bob]}\n")
    wildcards("hair/color.txt", "black\n") # Hides the yaml key hair/color, and is in the way of its txt file.
    status, text = api("POST", "/diceforge/wildcards/convert", {"name": "hair", "to": "txt"})
    assert status == 409 and "hair/color.txt already exists" in text
    assert os.path.isfile(os.path.join(wildcards.folder, "pack.yaml")) and not os.path.exists(os.path.join(wildcards.folder, "hair", "style.txt")) # Nothing changed.
    assert api("POST", "/diceforge/wildcards/convert", {"name": "hair", "to": "json"})[0] == 400
    assert api("POST", "/diceforge/wildcards/convert", {"name": "nope", "to": "yaml"})[0] == 404
    assert api("POST", "/diceforge/wildcards/convert", {"name": "nope", "to": "txt"})[0] == 404
    assert api("POST", "/diceforge/wildcards/convert", {"name": "../x", "to": "txt"})[0] == 400


PNG = b"\x89PNG\r\n\x1a\n" + b"png"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg"


def test_a_yaml_card_gets_a_picture_replaced_and_removed(api, wildcards):
    wildcards("POSES.yaml", "POSES:\n  sitting: sitting,\n")
    wildcards("color.txt", "red\n")
    status, body = api("POST", "/diceforge/wildcards/picture?name=POSES/sitting", data=PNG)
    assert status == 200 and body["picture"].endswith(os.path.join("POSES", "sitting.png"))
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/sitting") == (200, PNG)
    assert api("POST", "/diceforge/wildcards/picture?name=POSES/sitting", data=JPEG)[0] == 200 # Another picture: in place of the first.
    assert sorted(os.listdir(os.path.join(wildcards.folder, "POSES"))) == ["sitting.jpg"]
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/sitting") == (200, JPEG)
    status, text = api("POST", "/diceforge/wildcards/picture?name=POSES/sitting", data=b"<html>not a picture")
    assert status == 400 and "PNG, JPEG, WebP or GIF" in text
    assert api("POST", "/diceforge/wildcards/picture?name=color", data=PNG)[0] == 400 # A txt wildcard: no card picture.
    assert api("POST", "/diceforge/wildcards/picture?name=../x", data=PNG)[0] == 400
    assert api("DELETE", "/diceforge/wildcards/picture?name=POSES/sitting")[0] == 200
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/sitting")[0] == 404
    assert api("DELETE", "/diceforge/wildcards/picture?name=POSES/sitting")[0] == 404


def test_card_pictures_in_a_cards_folder_as_wildcard_gallery_packs_keep_them(api, wildcards):
    # The A1111 Wildcard Gallery keeps a card's picture at cards/<the key's path>: at the top of the wildcards folder, or next to the yaml file.
    wildcards("POSES.yaml", "POSES:\n  sitting: sitting,\n  standing: [standing, hands on hips]\n")
    wildcards("styles/pack.yml", "ink: inked lines\n")
    for path, content in (("cards/POSES/sitting.jpeg", b"top"), ("styles/cards/ink.png", b"next to it"), ("cards/POSES/standing/[1].jpeg", b"a line")):
        os.makedirs(os.path.dirname(os.path.join(wildcards.folder, *path.split("/"))), exist_ok=True)
        with open(os.path.join(wildcards.folder, *path.split("/")), "wb") as file:
            file.write(content)
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert files["POSES/sitting"]["picture"] is True and files["styles/ink"]["picture"] is True and "picture" not in files["POSES/standing"]
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/sitting") == (200, b"top")
    assert api("GET", "/diceforge/wildcards/picture?name=styles/ink") == (200, b"next to it")
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/standing&line=1") == (200, b"a line")
    assert "cards/POSES/sitting" not in files # Pictures, not wildcards.


def test_each_line_of_a_card_can_have_its_own_picture(api, wildcards):
    wildcards("POSES.yaml", "POSES:\n  standing: ['# poses', standing, hands on hips, arms crossed]\n  sitting: sitting,\n")
    wildcards("color.txt", "red\nblue\n")
    status, body = api("POST", "/diceforge/wildcards/picture?name=POSES/standing&line=2", data=PNG)
    assert status == 200 and body["picture"].endswith(os.path.join("POSES", "standing", "[2].png")) # Next to the yaml file, as the card's own.
    assert api("POST", "/diceforge/wildcards/picture?name=POSES/standing&line=1", data=JPEG)[0] == 200
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/standing&line=2") == (200, PNG)
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/standing&line=3")[0] == 404
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/standing")[0] == 404 # The card's own picture is another one.
    status, body = api("GET", "/diceforge/wildcards/cards?folder=POSES")
    assert status == 200 and body["cards"] == [
        {"name": "POSES/sitting", "lines": [{"index": 0, "text": "sitting,"}], "pictures": []},
        {"name": "POSES/standing", "lines": [{"index": 1, "text": "standing"}, {"index": 2, "text": "hands on hips"}, {"index": 3, "text": "arms crossed"}], "pictures": [1, 2]}]
    assert [card["name"] for card in api("GET", "/diceforge/wildcards/cards")[1]["cards"]] == ["POSES/sitting", "POSES/standing"] # Only yaml cards.
    assert api("DELETE", "/diceforge/wildcards/picture?name=POSES/standing&line=1")[0] == 200
    assert api("GET", "/diceforge/wildcards/cards?folder=POSES")[1]["cards"][1]["pictures"] == [2]
    for query in ("line=4", "line=x", "line=-1", "line=100000"): # Past the last line; not a line number.
        assert api("POST", f"/diceforge/wildcards/picture?name=POSES/standing&{query}", data=PNG)[0] == 400
    assert api("POST", "/diceforge/wildcards/picture?name=color&line=0", data=PNG)[0] == 400 # A txt wildcard: no card pictures.
    assert api("GET", "/diceforge/wildcards/cards?folder=../x")[0] == 400


def test_line_pictures_go_with_their_lines_and_their_key(api, wildcards):
    wildcards("POSES.yaml", "POSES:\n  sitting: sitting,\n  standing: [standing, hands on hips, arms crossed, leaning]\n  lying: lying,\n")
    for line, picture in ((0, b"\x89PNG\r\n\x1a\nstanding"), (1, b"\x89PNG\r\n\x1a\nhips"), (3, b"\x89PNG\r\n\x1a\nleaning")):
        assert api("POST", f"/diceforge/wildcards/picture?name=POSES/standing&line={line}", data=picture)[0] == 200
    # Saved lines: a picture follows its line's text; a changed line keeps the picture at its place; a removed line's picture goes.
    assert api("POST", "/diceforge/wildcards/file", {"name": "POSES/standing", "text": "hands on hips\nstanding\narms folded"})[0] == 200
    line = lambda index: api("GET", f"/diceforge/wildcards/picture?name=POSES/standing&line={index}")
    assert line(0) == (200, b"\x89PNG\r\n\x1a\nhips") and line(1) == (200, b"\x89PNG\r\n\x1a\nstanding") and line(2)[0] == 404 and line(3)[0] == 404
    assert sorted(os.listdir(os.path.join(wildcards.folder, "POSES", "standing"))) == ["[0].png", "[1].png"]
    # Renamed: the pictures go along; deleted and brought back: in its place in the file, with them.
    assert api("POST", "/diceforge/wildcards/rename", {"name": "POSES/standing", "to": "POSES/upright"})[0] == 200
    assert sorted(os.listdir(os.path.join(wildcards.folder, "POSES", "upright"))) == ["[0].png", "[1].png"]
    assert not os.path.exists(os.path.join(wildcards.folder, "POSES", "standing"))
    undo = api("DELETE", "/diceforge/wildcards/file?name=POSES/upright")[1]["undo"]
    assert not os.path.exists(os.path.join(wildcards.folder, "POSES"))
    assert api("POST", "/diceforge/wildcards/restore", {"id": undo})[0] == 200
    assert list(read_pack(wildcards, "POSES.yaml")["POSES"]) == ["sitting", "upright", "lying"]
    assert api("GET", "/diceforge/wildcards/picture?name=POSES/upright&line=1") == (200, b"\x89PNG\r\n\x1a\nstanding")


def zip_of(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return data.getvalue()


def test_a_zip_card_pack_is_imported_with_its_paths(api, wildcards):
    wildcards("color.txt", "red\n")
    data = zip_of({"POSES.yaml": "POSES:\n  sitting: sitting,\n", "POSES/sitting.png": PNG, "POSES/notes.pdf": b"%PDF", "../evil.txt": "x",
                   "__MACOSX/POSES/._sitting.png": b"x", ".hidden/a.txt": "x", "color.txt": "black\n", "more\\style.txt": "bob\n"})
    status, body = api("POST", "/diceforge/wildcards/import", data=data)
    assert status == 200 and sorted(body["imported"]) == ["POSES.yaml", "POSES/sitting.png", "more/style.txt"]
    assert body["skipped"] == ["color.txt"] and len(body["left_out"]) == 4 # A pdf, a path out, a Mac's leftovers, a hidden folder.
    with open(os.path.join(wildcards.folder, "color.txt"), encoding="utf-8") as file:
        assert file.read() == "red\n" # Kept as it was.
    assert not os.path.exists(os.path.join(os.path.dirname(wildcards.folder), "evil.txt"))
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert files["POSES/sitting"]["picture"] is True and "more/style" in files
    status, body = api("POST", "/diceforge/wildcards/import?folder=packs/new", data=zip_of({"hair.txt": "long\n"}))
    assert status == 200 and body["imported"] == ["hair.txt"] and os.path.isfile(os.path.join(wildcards.folder, "packs", "new", "hair.txt"))
    assert api("POST", "/diceforge/wildcards/import", data=b"not a zip")[0] == 400
    assert api("POST", "/diceforge/wildcards/import?folder=../x", data=data)[0] == 400


def test_search_finds_wildcards_by_their_lines(api, wildcards):
    wildcards("color.txt", "# red in a comment\ncrimson red\nblue\n")
    wildcards("pack.yaml", "outfit: [Red dress, suit]\n")
    wildcards("hair.txt", "bob\n")
    status, body = api("GET", "/diceforge/wildcards/search?q=RED")
    assert status == 200 and body["found"] == [{"name": "color", "line": "crimson red"}, {"name": "outfit", "line": "Red dress"}] # Not in comments.
    assert api("GET", "/diceforge/wildcards/search?q=zzz")[1]["found"] == []
    assert api("GET", "/diceforge/wildcards/search?q=r")[0] == 400


def zip_bytes(body):
    return body if isinstance(body, bytes) else body.encode("utf-8") # A zip that happens to read as text comes back as text.


def test_a_folder_or_all_wildcards_export_as_a_zip_that_imports_back(api, wildcards):
    wildcards("color.txt", "red\n")
    wildcards("anima/style.txt", "flat\n")
    wildcards("anima/POSES.yaml", "POSES:\n  sitting: sitting,\n")
    os.makedirs(os.path.join(wildcards.folder, "anima", "POSES"))
    with open(os.path.join(wildcards.folder, "anima", "POSES", "sitting.png"), "wb") as file:
        file.write(PNG)
    wildcards("anima/notes.pdf", "not a wildcard")
    wildcards("anima/.hidden/x.txt", "x\n")
    status, body = api("GET", "/diceforge/wildcards/export?folder=anima")
    assert status == 200
    names = sorted(zipfile.ZipFile(io.BytesIO(zip_bytes(body))).namelist())
    assert names == ["anima/POSES.yaml", "anima/POSES/sitting.png", "anima/style.txt"] # With the folder's name; no pdf, no hidden folder.
    status, body = api("GET", "/diceforge/wildcards/export?folder=anima/POSES")
    assert sorted(zipfile.ZipFile(io.BytesIO(zip_bytes(body))).namelist()) == ["anima/POSES.yaml", "anima/POSES/sitting.png"] # The pack's yaml too.
    status, body = api("GET", "/diceforge/wildcards/export")
    assert status == 200 and "color.txt" in zipfile.ZipFile(io.BytesIO(zip_bytes(body))).namelist()
    assert api("GET", "/diceforge/wildcards/export?folder=nope")[0] == 404
    assert api("GET", "/diceforge/wildcards/export?folder=../x")[0] == 400
    exported = zip_bytes(api("GET", "/diceforge/wildcards/export?folder=anima")[1])
    status, body = api("POST", "/diceforge/wildcards/import?folder=copy", data=exported)
    assert status == 200 and sorted(body["imported"]) == ["anima/POSES.yaml", "anima/POSES/sitting.png", "anima/style.txt"]
    assert os.path.isfile(os.path.join(wildcards.folder, "copy", "anima", "POSES", "sitting.png"))


def test_a_delete_is_undone_with_its_star(api, wildcards):
    wildcards("hair/style/long.txt", "l\n")
    assert api("POST", "/diceforge/wildcards/favorite", {"name": "hair/style/long", "favorite": True})[0] == 200
    status, body = api("DELETE", "/diceforge/wildcards/file?name=hair/style/long")
    assert status == 200 and body["undo"] and os.listdir(wildcards.folder) == [] # In the trash, its folders gone.
    status, body = api("POST", "/diceforge/wildcards/restore", {"id": body["undo"]})
    assert status == 200 and body["restored"] == "hair/style/long"
    with open(os.path.join(wildcards.folder, "hair", "style", "long.txt"), encoding="utf-8") as file:
        assert file.read() == "l\n"
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert files["hair/style/long"]["favorite"] is True
    undo = api("DELETE", "/diceforge/wildcards/file?name=hair/style/long")[1]["undo"]
    wildcards("hair/style/long.txt", "a new one\n")
    assert api("POST", "/diceforge/wildcards/restore", {"id": undo})[0] == 409 # The name is taken again: not overwritten.
    assert api("POST", "/diceforge/wildcards/restore", {"id": "1234567890123456789-deadbeef"})[0] == 404
    for junk in ("../x", 5, None, "1234567890123456789-deadbeef/../x"):
        assert api("POST", "/diceforge/wildcards/restore", {"id": junk})[0] == 400


def test_the_trash_keeps_the_last_deletes(api, wildcards, monkeypatch):
    from DiceForge import wildcards_api
    monkeypatch.setattr(wildcards_api, "TRASH_KEPT", 2)
    undo = []
    for name in ("a", "b", "c"):
        wildcards(f"{name}.txt", f"{name}\n")
        undo.append(api("DELETE", f"/diceforge/wildcards/file?name={name}")[1]["undo"])
    assert len(os.listdir(wildcards_api.TRASH_FOLDER)) == 2
    assert api("POST", "/diceforge/wildcards/restore", {"id": undo[0]})[0] == 404 # The oldest is gone.
    assert api("POST", "/diceforge/wildcards/restore", {"id": undo[2]})[0] == 200


def test_preview_picks_fill_a_wildcard_or_a_folder_in_as_runs_would(api, wildcards):
    wildcards("hair/color.txt", "red\nblue\n0::never\n")
    wildcards("hair/style.txt", "{long|short} __hair/color__ hair\n")
    status, body = api("GET", "/diceforge/wildcards/preview?name=hair/color&count=20")
    assert status == 200 and body["token"] == "hair/color" and len(body["picks"]) == 20 and set(body["picks"]) <= {"red", "blue"} # Weight 0: never.
    picks = api("GET", "/diceforge/wildcards/preview?name=hair/style")[1]["picks"]
    assert len(picks) == 5 and all(re.fullmatch(r"(long|short) (red|blue) hair", pick) for pick in picks) # Choices and nested wildcards.
    status, body = api("GET", "/diceforge/wildcards/preview?name=hair&folder=1&count=10")
    assert status == 200 and body["token"] == "hair/*" and all(pick in ("red", "blue") or pick.endswith(" hair") for pick in body["picks"])
    assert api("GET", "/diceforge/wildcards/preview?name=nope")[0] == 404
    assert api("GET", "/diceforge/wildcards/preview?name=hair")[0] == 404 # A folder, not a wildcard.
    for query in ("name=../x", "name=hair/color&count=0", "name=hair/color&count=21", "name=hair/color&count=x", ""):
        assert api("GET", f"/diceforge/wildcards/preview?{query}")[0] == 400



def test_the_list_marks_wildcards_a_file_uses_that_do_not_exist(api, wildcards):
    wildcards("hair/color.txt", "red\n")
    wildcards("look.txt", "__hair/color__ and __hair/colour__\n{__Hair/Color__|__eyes__}\n__hair/*__, __nope/*__, __outfit/${gender}__\n")
    wildcards("pack.yaml", "outfit: [__missing__ dress]\n")
    files = {entry["name"]: entry for entry in api("GET", "/diceforge/wildcards")[1]["files"]}
    assert files["look"]["broken"] == ["eyes", "hair/colour", "nope/*"] # Case doesn't matter; a glob that matches is fine; variables are left out.
    assert files["outfit"]["broken"] == ["missing"] and "broken" not in files["hair/color"]


def test_find_and_replace_in_every_wildcard(api, wildcards):
    wildcards("a.txt", "__hair/colour__, smile\nred __hair/colour__\n")
    wildcards("b.txt", "nothing here\n")
    wildcards("pack.yaml", "outfit: [__hair/colour__ dress, suit]\nlook:\n  one: __hair/colour__\n  keep: '0123'\n")
    body = {"find": "__hair/colour__", "replace": "__hair/color__"}
    status, preview = api("POST", "/diceforge/wildcards/replace", body)
    assert status == 200 and preview["applied"] is False and "in_yaml" not in preview
    assert preview["files"] == [{"name": "a", "count": 2, "line": "__hair/colour__, smile", "after": "__hair/color__, smile"},
                                {"name": "look/one", "count": 1, "line": "__hair/colour__", "after": "__hair/color__"},
                                {"name": "outfit", "count": 1, "line": "__hair/colour__ dress", "after": "__hair/color__ dress"}]
    with open(os.path.join(wildcards.folder, "a.txt"), encoding="utf-8") as file:
        assert "colour" in file.read() # A preview changes nothing.
    status, done = api("POST", "/diceforge/wildcards/replace", {**body, "apply": True})
    assert status == 200 and done["applied"] is True and [entry["name"] for entry in done["files"]] == ["a", "look/one", "outfit"]
    with open(os.path.join(wildcards.folder, "a.txt"), encoding="utf-8") as file:
        assert file.read() == "__hair/color__, smile\nred __hair/color__\n"
    assert read_pack(wildcards) == {"outfit": ["__hair/color__ dress", "suit"], "look": {"one": "__hair/color__", "keep": "0123"}}
    for junk in ({"find": ""}, {"find": "a\nb"}, {"find": "x", "replace": "y\n"}, {"find": "x" * 501}, {"find": 5}, {"find": "x", "apply": "yes"}, {"find": "x", "replace": 3}):
        assert api("POST", "/diceforge/wildcards/replace", junk)[0] == 400
