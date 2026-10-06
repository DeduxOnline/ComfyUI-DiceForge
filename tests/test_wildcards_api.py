# Server routes of the Wildcard Browser and the __ autocomplete (DiceForge/wildcards_api.py): listing, creating, reading, saving, renaming and deleting
# wildcard files.
import io
import os
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
