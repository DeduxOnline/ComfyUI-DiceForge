import fnmatch
import functools
import io
import json
import os
import re
import secrets
import shutil
import threading
import time
import zipfile
import zlib
from urllib.parse import quote
import folder_paths
import yaml
from aiohttp import web
from .clip_text_encode_pos_neg import WILDCARD_PATTERN, TextLoader, entry_lines, fill_in, find_wildcard, read_text_lines, wildcard_index, yaml_wildcards
from .http_read import read_up_to
from .model_info import in_thread, json_body
# Server side of the Wildcard Browser and the __ autocomplete (web/wildcards.js): the list of wildcards, and creating, reading, saving, renaming and
# deleting a wildcard (a txt file, or a key of a yaml file, changed in that file), converting txt files to a yaml file and back, and the cards'
# pictures. A deleted wildcard goes to a trash folder first, so the Wildcard Browser can undo the delete; a folder (or all of them) can be
# exported as a zip.
PART = r"[\w\-.]+(?: [\w\-.]+)*" # Single spaces inside a name, as __hair color__ reads them (clip_text_encode_pos_neg.WILDCARD_PATTERN).
NAME = re.compile(rf"{PART}(/{PART})*")
def checked_name(name):
    name = (name if isinstance(name, str) else "").strip().replace("\\", "/").removesuffix(".txt")
    if not NAME.fullmatch(name) or ".." in name.split("/"):
        raise web.HTTPBadRequest(text=f"Wildcards: {name!r} is not a usable name (letters, digits, - _ ., single spaces inside, and / for folders).")
    return name
# Where a new wildcard file goes: in the given wildcards folder (by default the first one), never outside it.
def new_path(name, root=None):
    root = os.path.abspath(root or folder_paths.get_folder_paths("wildcards")[0])
    path = os.path.abspath(os.path.join(root, *name.split("/")) + ".txt")
    if not path.startswith(root + os.sep):
        raise web.HTTPBadRequest(text="Wildcards: the file would be outside the wildcards folder.")
    return path
# The wildcards folder a file is in.
def root_of(path):
    path = os.path.abspath(path)
    return next(root for root in map(os.path.abspath, folder_paths.get_folder_paths("wildcards")) if path.startswith(root + os.sep))
# The index entry of an existing wildcard, for renaming or deleting it: {"path"} for a txt file, {"path", "lines", "inner"} for a yaml key.
def existing_entry(name):
    entry = wildcard_index(refresh=True).get(name)
    if entry is None:
        raise web.HTTPNotFound(text=f"Wildcards: no wildcard {name}.")
    return entry
# Folders left empty by a delete or a rename go too, up to (not including) the wildcards folder.
def remove_empty_folders(folder, root):
    while folder != root and folder.startswith(root + os.sep):
        try:
            os.rmdir(folder)
        except OSError: # Not empty (or not removable): it stays, and so do the folders above it.
            return
        folder = os.path.dirname(folder)
def delete_file(path):
    os.remove(path)
    remove_empty_folders(os.path.dirname(path), root_of(path))
def move_file(path, target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.replace(path, target) # The target was checked to be free (or the same file, in another case).
    remove_empty_folders(os.path.dirname(path), root_of(path))
# ★ Favorite wildcards (txt or yaml), by name, in the ComfyUI user folder; a rename or move takes the star along, a delete drops it.
FAVORITES_FILE = os.path.join(folder_paths.get_user_directory(), "DiceForge", "wildcard_favorites.json")
def read_favorites():
    try:
        with open(FAVORITES_FILE, encoding="utf-8") as file:
            names = json.load(file)
        return {name for name in names if isinstance(name, str)} if isinstance(names, list) else set()
    except (OSError, ValueError): # None yet, or damaged: no favorites (the next star writes a good file).
        return set()
def write_favorites(names):
    os.makedirs(os.path.dirname(FAVORITES_FILE), exist_ok=True)
    with open(FAVORITES_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(names, key=str.lower), file, ensure_ascii=False, indent=1)
def rename_favorite(name, to):
    names = read_favorites()
    if name in names:
        write_favorites((names - {name}) | ({to} if to else set()))
# Card pictures (the Wildcard Browser's cards mode) of a yaml key, at the key's path in its file (POSES/sitting for POSES: {sitting: ...}): next to its
# yaml file (POSES.yaml and POSES/sitting.jpeg, as card packs come), in a folder named like the file (poses.yaml and poses/POSES/sitting.png), or in
# a cards folder next to the yaml file or at the top of its wildcards folder (cards/POSES/sitting.jpeg, where the card packs of the A1111 Wildcard
# Gallery keep them). A key of several lines can have a picture for each line too, as those packs do: POSES/sitting/[0].jpeg for its first line.
# Only a picture inside the wildcards folder counts.
PICTURE_ENDINGS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
LINE_PICTURE = re.compile(r"\[(\d{1,5})\](\.\w+)")
def picture_bases(entry):
    folder = os.path.realpath(os.path.dirname(entry["path"]))
    root = os.path.realpath(root_of(entry["path"]))
    stem = os.path.splitext(os.path.basename(entry["path"]))[0]
    parts = entry["inner"].split("/")
    return root, [os.path.join(folder, *parts), os.path.join(folder, stem, *parts), os.path.join(folder, "cards", *parts), os.path.join(root, "cards", *parts)]
def card_picture(entry, line=None):
    if not entry or "inner" not in entry:
        return None
    root, bases = picture_bases(entry)
    for base in bases:
        base = base if line is None else os.path.join(base, f"[{line}]")
        for ending in PICTURE_ENDINGS:
            path = os.path.realpath(base + ending)
            if path.startswith(root + os.sep) and os.path.isfile(path):
                return path
    return None
# The pictures of a key's lines: {line index: path}, the first found for each line.
def line_pictures(entry):
    if not entry or "inner" not in entry:
        return {}
    root, bases = picture_bases(entry)
    found = {}
    for base in bases:
        base = os.path.realpath(base)
        if not base.startswith(root + os.sep) or not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            match = LINE_PICTURE.fullmatch(name)
            if match and match.group(2).lower() in PICTURE_ENDINGS:
                found.setdefault(int(match.group(1)), os.path.join(base, name))
    return found
# A card's picture, sent from the browser: PNG, JPEG, WebP or GIF (by its first bytes, not its name), saved where card_picture finds it first
# (POSES/sitting.png next to POSES.yaml, POSES/sitting/[0].png for a line), in place of the picture it had. Only a yaml wildcard has card pictures.
PICTURE_BYTES = 20 * 1024 * 1024
def picture_ending(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else None
def picture_base(entry, line=None):
    if not entry or "inner" not in entry:
        return None
    folder = os.path.realpath(os.path.dirname(entry["path"]))
    base = os.path.realpath(os.path.join(folder, *entry["inner"].split("/"), *([f"[{line}]"] if line is not None else [])))
    return base if base.startswith(folder + os.sep) else None
def save_picture(base, data, ending):
    for other in PICTURE_ENDINGS:
        if os.path.isfile(base + other):
            os.remove(base + other)
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with open(base + ending, "wb") as file:
        file.write(data)
    return base + ending
# A picture moved to where card_picture finds it first for a key (or a line) of that yaml file: a renamed or restored card keeps its pictures. The
# folders it leaves go when they are empty.
def move_picture(path, yaml_path, inner, line=None):
    base = picture_base({"path": yaml_path, "inner": inner}, line)
    if path is None or base is None:
        return
    for other in PICTURE_ENDINGS:
        if os.path.isfile(base + other) and os.path.normcase(base + other) != os.path.normcase(path):
            os.remove(base + other)
    os.makedirs(os.path.dirname(base), exist_ok=True)
    shutil.move(path, base + os.path.splitext(path)[1].lower())
    remove_empty_folders(os.path.dirname(os.path.abspath(path)), root_of(yaml_path))
def move_pictures(entry, inner):
    pictures, lines = card_picture(entry), line_pictures(entry)
    move_picture(pictures, entry["path"], inner)
    for line, path in lines.items():
        move_picture(path, entry["path"], inner, line)
# Saved lines keep their pictures: a picture goes with its line's text when the lines move, stays at its place when that line's text changed, and
# goes when its line is gone.
def follow_line_pictures(entry, new_lines):
    pictures = line_pictures(entry)
    if not pictures:
        return
    old, taken, plan = entry["lines"], set(), {}
    for index, path in sorted(pictures.items()):
        text = old[index] if index < len(old) else None
        to = next((place for place, line in enumerate(new_lines) if line == text and place not in taken), None)
        if to is not None:
            taken.add(to)
            plan[index] = to
    for index in pictures:
        if index not in plan and index < len(new_lines) and index not in taken:
            taken.add(index)
            plan[index] = index
    staged = []
    for index, path in pictures.items():
        if index in plan:
            staging = path + ".moving"
            os.replace(path, staging)
            staged.append((staging, plan[index], os.path.splitext(path)[1]))
        else:
            os.remove(path)
    for staging, to, ending in staged:
        base = picture_base(entry, to)
        os.makedirs(os.path.dirname(base), exist_ok=True)
        os.replace(staging, base + ending.lower())
    for path in pictures.values():
        remove_empty_folders(os.path.dirname(path), root_of(entry["path"]))
# Yaml wildcards are changed in their yaml file: a key's lines saved, the key renamed or moved among the file's keys, deleted, or a new key added
# next to the others; the rest of the file stays as it was, comments and all (write_keys).
def read_yaml(path):
    try:
        with open(path, encoding="utf-8-sig") as file:
            data = yaml.load(file, Loader=TextLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't read {path}: {error}") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text=f"Wildcards: {path} is not a yaml file of keys.")
    return data
def write_text(path, text):
    temporary = path + ".tmp" # Written whole first: a failed write leaves the file as it was.
    with open(temporary, "w", encoding="utf-8", newline="\n") as file:
        file.write(text.rstrip("\n") + "\n")
    os.replace(temporary, path)
def write_yaml(path, data):
    write_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=4096))
# The same change made in the file's text, so that its comments and layout stay: only the changed key's text is touched (its value written again,
# the key renamed, taken out, or put in at the end of its mapping or at its old place). The edited text is kept when it reads as exactly the keys
# meant, in their order; else (keys written as {flow}, anchors...) the file is written anew from the keys.
class NoTextEdit(ValueError):
    pass
def dumped(key, value, indent):
    text = yaml.safe_dump({key: value}, allow_unicode=True, sort_keys=False, default_flow_style=False, width=4096).rstrip("\n")
    return text.replace("\n", "\n" + " " * indent)
# The block mapping at a key path (the file's own at []), or None when the path isn't there.
def mapping_at(root, parts):
    node = root
    for part in parts:
        if not isinstance(node, yaml.MappingNode) or node.flow_style:
            raise NoTextEdit()
        node = next((value for key, value in node.value if isinstance(key, yaml.ScalarNode) and key.value == part), None)
        if node is None:
            return None
    if not isinstance(node, yaml.MappingNode) or node.flow_style or not node.value:
        raise NoTextEdit()
    return node
def pair_at(root, parts):
    mapping = mapping_at(root, parts[:-1])
    pair = next(((key, value) for key, value in mapping.value if isinstance(key, yaml.ScalarNode) and key.value == parts[-1]), None) if mapping else None
    if pair is None:
        raise NoTextEdit()
    return pair
# Where a value's text ends: a block value's end is where the next key starts, so its line's indent and the blank and comment lines before it
# (they go with what comes next) are left out.
def value_end(text, node):
    end = node.end_mark.index
    if isinstance(node, yaml.ScalarNode) or node.flow_style:
        return end
    lines = text[node.start_mark.index:end].split("\n")
    while len(lines) > 1 and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
        lines.pop()
    return node.start_mark.index + len("\n".join(lines))
def line_end(text, at):
    end = text.find("\n", at)
    return len(text) if end == -1 else end
def compose(text):
    root = yaml.compose(text, Loader=TextLoader)
    if not isinstance(root, yaml.MappingNode) or root.flow_style or not root.value:
        raise NoTextEdit()
    return root
def edit_value(text, parts, value):
    key, node = pair_at(compose(text), parts)
    return text[:key.start_mark.index] + dumped(key.value, value, key.start_mark.column) + text[value_end(text, node):]
def edit_rename(text, parts, name):
    key, _ = pair_at(compose(text), parts)
    return text[:key.start_mark.index] + dumped(name, 0, 0)[:-len(": 0")] + text[key.end_mark.index:]
# Takes a key's lines out, or those of the key above it that it leaves empty.
def edit_remove(text, parts):
    root = compose(text)
    while len(parts) > 1 and len(mapping_at(root, parts[:-1]).value) == 1:
        parts = parts[:-1]
    if len(parts) == 1 and len(root.value) == 1:
        raise NoTextEdit() # The file's last key: the file goes.
    key, node = pair_at(root, parts)
    return text[:key.start_mark.index - key.start_mark.column] + text[line_end(text, value_end(text, node)) + 1:]
# Puts a key in, with the keys above it that aren't there yet: at the end of the deepest mapping of its path there is, or (position) at its place.
def edit_add(text, parts, value, position=None):
    root = compose(text)
    depth = len(parts) - 1
    while depth and mapping_at(root, parts[:depth]) is None:
        depth -= 1
    mapping = mapping_at(root, parts[:depth])
    for part in reversed(parts[depth + 1:]):
        value = {part: value}
    indent = mapping.value[0][0].start_mark.column
    if position is not None and depth == len(parts) - 1 and position < len(mapping.value):
        before = mapping.value[position][0]
        at = before.start_mark.index - before.start_mark.column
        return text[:at] + " " * indent + dumped(parts[depth], value, indent) + "\n" + text[at:]
    at = line_end(text, value_end(text, mapping.value[-1][1]))
    return text[:at] + "\n" + " " * indent + dumped(parts[depth], value, indent) + text[at:]
def write_keys(path, data, *edits):
    try:
        with open(path, encoding="utf-8-sig") as file:
            text = file.read()
        for edit in edits:
            text = edit(text)
        if json.dumps(yaml.load(text, Loader=TextLoader)) == json.dumps(data):
            write_text(path, text)
            return
    except (NoTextEdit, yaml.YAMLError, TypeError):
        pass
    write_yaml(path, data)
def yaml_lines(text):
    return [line.strip() for line in str(text).replace("\r\n", "\n").split("\n") if line.strip()]
# A key's new lines: one line stays a single text (key: text, as card packs write them), unless the key was a list of lines.
def key_value(lines, old=None):
    return lines[0] if len(lines) == 1 and not (isinstance(old, list) and old) else lines
# The key path of a wildcard in its yaml file (POSES/sitting in a file of the top folder), and the names its file's keys can have (POSES/... ;
# for styles/pack.yaml, styles/...): the start of the name that is the yaml file's folder.
def key_parts(entry):
    return entry["inner"].split("/")
def yaml_prefix(name, entry):
    return name[:len(name) - len(entry["inner"])]
# A key put in (at its place among its neighbours, when given: a restored key goes back where it was).
def put_key(data, parts, value, name, position=None):
    level = data
    for index, part in enumerate(parts[:-1]):
        level = level.setdefault(part, {})
        if not isinstance(level, dict):
            raise web.HTTPConflict(text=f"Wildcards: {'/'.join(parts[:index + 1])} is a wildcard in that yaml file, not a folder: {name} can't go in it.")
    if parts[-1] in level:
        raise web.HTTPConflict(text=f"Wildcards: {name} already exists in that yaml file.")
    items = list(level.items())
    items.insert(len(items) if position is None else position, (parts[-1], value))
    level.clear()
    level.update(items)
# Takes a key out (with the keys above it that it leaves empty) and gives its value.
def pop_key(data, parts):
    levels = [data]
    try:
        for part in parts[:-1]:
            levels.append(levels[-1][part])
        value = levels[-1].pop(parts[-1])
    except (KeyError, TypeError, AttributeError):
        raise web.HTTPConflict(text="Wildcards: the yaml file changed: open the browser again.") from None
    for level, part in zip(reversed(levels[:-1]), reversed(parts[:-1])):
        if level[part]:
            break
        del level[part]
    return value
def save_yaml_key(entry, text):
    data = read_yaml(entry["path"])
    parts = key_parts(entry)
    level = data
    for part in parts[:-1]:
        level = level.get(part) if isinstance(level, dict) else None
    if not isinstance(level, dict) or parts[-1] not in level:
        raise web.HTTPConflict(text="Wildcards: the yaml file changed: open the browser again.")
    lines = yaml_lines(text)
    value = level[parts[-1]] = key_value(lines, level[parts[-1]])
    write_keys(entry["path"], data, lambda source: edit_value(source, parts, value))
    follow_line_pictures(entry, lines)
# A new key in the yaml file of another wildcard (next_to), when its name can be one of that file's keys.
def add_yaml_key(name, next_to, text):
    sibling = wildcard_index(refresh=True).get(next_to)
    if sibling is None or "lines" not in sibling:
        raise web.HTTPBadRequest(text=f"Wildcards: {next_to} is not a yaml wildcard to add {name} next to.")
    prefix = yaml_prefix(next_to, sibling)
    if not name.startswith(prefix):
        raise web.HTTPBadRequest(text=f"Wildcards: the wildcards of {os.path.basename(sibling['path'])} are named {prefix}…: {name} can't be one of them.")
    data, parts, value = read_yaml(sibling["path"]), name[len(prefix):].split("/"), key_value(yaml_lines(text))
    put_key(data, parts, value, name)
    write_keys(sibling["path"], data, lambda source: edit_add(source, parts, value))
    return sibling["path"]
# Rename or move a key among its yaml file's keys (in its place when only its last part changes); its card picture goes along.
def rename_yaml_key(name, to, entry):
    prefix = yaml_prefix(name, entry)
    if not to.startswith(prefix):
        raise web.HTTPBadRequest(text=f"Wildcards: {name} is a key of {os.path.basename(entry['path'])}, whose wildcards are named {prefix}…; "
                                      "to move it elsewhere, turn the yaml file into txt files first (→ txt).")
    parts, target = key_parts(entry), to[len(prefix):].split("/")
    data = read_yaml(entry["path"])
    level = data
    for part in parts[:-1]:
        level = level.get(part) if isinstance(level, dict) else None
    if parts[:-1] == target[:-1] and isinstance(level, dict) and parts[-1] in level:
        if target[-1] in level and target[-1] != parts[-1]:
            raise web.HTTPConflict(text=f"Wildcards: {to} already exists in that yaml file.")
        renamed = {target[-1] if key == parts[-1] else key: value for key, value in level.items()}
        level.clear()
        level.update(renamed)
        write_keys(entry["path"], data, lambda source: edit_rename(source, parts, target[-1]))
    else:
        value = pop_key(data, parts)
        put_key(data, target, value, to)
        write_keys(entry["path"], data, lambda source: edit_remove(source, parts), lambda source: edit_add(source, target, value))
    move_pictures(entry, "/".join(target))
# A folder or file of txt wildcards to one yaml file and back, with the same wildcard names: hair/ (hair/color.txt, hair/style.txt) becomes
# hair.yaml ({hair: {color: [...], style: [...]}}) next to the folder, and a yaml file becomes one txt file per key. Card pictures stay where they
# are (hair/color.png serves both). Nothing is overwritten: a name or file already taken stops the conversion before anything changes.
def yaml_target(name, root):
    parts = name.split("/")
    for ending in (".yaml", ".yml"):
        if os.path.exists(os.path.join(root, *parts[:-1], parts[-1] + ending)):
            raise web.HTTPConflict(text=f"Wildcards: {name}{ending} already exists.")
    return os.path.join(root, *parts[:-1], parts[-1] + ".yaml")
def to_yaml(name):
    index = wildcard_index(refresh=True)
    files = {key: entry["path"] for key, entry in index.items() if "lines" not in entry and (key == name or key.startswith(name + "/"))}
    if not files:
        raise web.HTTPNotFound(text=f"Wildcards: no txt wildcard {name} (or in the folder {name}).")
    root = root_of(files[min(files)])
    files = {key: path for key, path in files.items() if root_of(path) == root} # One wildcards folder: the yaml file goes there.
    target, depth, data = yaml_target(name, root), name.count("/"), {}
    for key, path in sorted(files.items()):
        level, parts = data, key.split("/")[depth:]
        for part in parts[:-1]:
            level = level.setdefault(part, {})
            if not isinstance(level, dict):
                raise web.HTTPConflict(text=f"Wildcards: {'/'.join(key.split('/')[:depth] + parts[:parts.index(part) + 1])} is both a file and a folder.")
        if isinstance(level.get(parts[-1]), dict):
            raise web.HTTPConflict(text=f"Wildcards: {key} is both a file and a folder.")
        try:
            level[parts[-1]] = [line.strip() for line in read_text_lines(path) if line.strip()]
        except ValueError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: {error}") from None
    write_yaml(target, data)
    for path in files.values():
        delete_file(path)
    return target, sorted(files)
def to_txt(name):
    index = wildcard_index(refresh=True)
    paths = sorted({entry["path"] for key, entry in index.items() if "lines" in entry and (key == name or key.startswith(name + "/"))})
    if not paths:
        raise web.HTTPNotFound(text=f"Wildcards: no yaml wildcard {name} (or in the folder {name}).")
    plan = []
    for path in paths:
        root = root_of(path)
        prefix = os.path.relpath(os.path.dirname(path), root).replace(os.sep, "/")
        for key, lines in yaml_wildcards(read_yaml(path), "" if prefix == "." else prefix):
            target = new_path(checked_name(key), root)
            if os.path.exists(target) or find_wildcard(key):
                raise web.HTTPConflict(text=f"Wildcards: {key}.txt already exists: rename it first.")
            plan.append((key, target, lines))
    if len({target for _, target, _ in plan}) < len(plan):
        raise web.HTTPConflict(text="Wildcards: two yaml keys would make the same txt file.")
    for _, target, lines in plan:
        write_lines(target, "\n".join(lines))
    for path in paths:
        os.remove(path)
    return paths, [key for key, _, _ in plan]
# Import a zip of wildcards (a card pack: POSES.yaml and POSES/sitting.png...): its txt, yaml and picture files go into the first wildcards
# folder (or a folder in it), with their paths. Files already there are skipped, never overwritten; other files and paths that would leave
# the folder are left out. Limits keep a zip bomb out.
ZIP_BYTES, ZIP_FILES, ZIP_UNPACKED = 512 * 1024 * 1024, 5000, 1024 * 1024 * 1024
IMPORTED = (".txt", ".yaml", ".yml") + PICTURE_ENDINGS
def import_zip(data, folder=""):
    root = os.path.abspath(folder_paths.get_folder_paths("wildcards")[0])
    base = os.path.abspath(os.path.join(root, *folder.split("/"))) if folder else root
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        members = [member for member in archive.infolist() if not member.is_dir()]
    except (zipfile.BadZipFile, ValueError, OSError):
        raise web.HTTPBadRequest(text="Wildcards: that is not a zip file.") from None
    if len(members) > ZIP_FILES or sum(member.file_size for member in members) > ZIP_UNPACKED:
        raise web.HTTPBadRequest(text=f"Wildcards: the zip is too big (at most {ZIP_FILES} files and 1 GB unpacked).")
    imported, skipped, left_out = [], [], []
    for member in members:
        parts = [part for part in member.filename.replace("\\", "/").split("/") if part not in ("", ".")]
        # Windows drops spaces and dots at the end of a name: "a /b.txt" would land in another folder than the zip says, or fail half-way.
        if (not parts or ".." in parts or parts[0] == "__MACOSX" or any(part.startswith(".") or part != part.rstrip(" .") for part in parts)
                or not parts[-1].lower().endswith(IMPORTED)):
            left_out.append(member.filename)
            continue
        target = os.path.abspath(os.path.join(base, *parts))
        if not target.startswith(root + os.sep):
            left_out.append(member.filename)
        elif os.path.exists(target):
            skipped.append("/".join(parts))
        else:
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with archive.open(member) as source, open(target, "wb") as file:
                    file.write(source.read(ZIP_UNPACKED))
            except (zipfile.BadZipFile, zlib.error, EOFError, OSError): # A damaged member (a wrong CRC, a size that lies) or a name the disk refuses.
                if os.path.isfile(target):
                    os.remove(target) # Not a half-written file: it was not there before.
                left_out.append(member.filename)
                continue
            imported.append("/".join(parts))
    return imported, skipped, left_out
# Export a folder of wildcards (all of them without one) as a zip that Import zip takes back: its txt, yaml and picture files, with their paths
# from the wildcards folder (the folder's own name included), and a yaml card pack's yaml file next to the folder (POSES.yaml with POSES/). A file
# in two wildcards folders goes once, from the first, as wildcards are read.
def export_zip(folder=""):
    buffer, added, total, found = io.BytesIO(), set(), 0, False
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(path, root):
            nonlocal total
            entry = os.path.relpath(path, root).replace(os.sep, "/")
            name = os.path.basename(path)
            if name.startswith(".") or not name.lower().endswith(IMPORTED) or entry in added or not os.path.isfile(path):
                return
            total += os.path.getsize(path)
            if total > ZIP_UNPACKED or len(added) >= ZIP_FILES:
                raise web.HTTPBadRequest(text=f"Wildcards: too much to export at once (at most {ZIP_FILES} files and 1 GB): export a smaller folder.")
            archive.write(path, entry)
            added.add(entry)
        for root in map(os.path.abspath, folder_paths.get_folder_paths("wildcards")):
            base = os.path.join(root, *folder.split("/")) if folder else root
            packs = [base + ending for ending in (".yaml", ".yml") if folder and os.path.isfile(base + ending)]
            found = found or bool(packs) or os.path.isdir(base)
            for pack in packs:
                add(pack, root)
            for current, folders, files in os.walk(base): # Symbolic links to folders are not followed; a Windows junction (made by the user) is.
                folders[:] = sorted(name for name in folders if not name.startswith("."))
                for name in sorted(files):
                    add(os.path.join(current, name), root)
    if folder and not found:
        raise web.HTTPNotFound(text=f"Wildcards: no folder {folder}.")
    return buffer.getvalue()
# Deleted wildcards wait in a trash folder (the last 50), so a delete can be undone: a txt file goes back where it was, a yaml key back into its
# yaml file (with its card picture), each with its star.
TRASH_FOLDER = os.path.join(folder_paths.get_user_directory(), "DiceForge", "wildcards_trash")
TRASH_KEPT = 50
TRASH_ID = re.compile(r"\d{19}-[0-9a-f]{8}")
last_trashed = [0] # Ids in the order of the deletes, also two within a clock tick: the oldest go first.
def trash_folder(meta):
    last_trashed[0] = max(time.time_ns(), last_trashed[0] + 1)
    trash_id = f"{last_trashed[0]:019d}-{secrets.token_hex(4)}"
    folder = os.path.join(TRASH_FOLDER, trash_id)
    os.makedirs(folder)
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as file:
        json.dump(meta, file, ensure_ascii=False)
    for old in sorted(os.listdir(TRASH_FOLDER))[:-TRASH_KEPT]:
        if old != trash_id:
            shutil.rmtree(os.path.join(TRASH_FOLDER, old), ignore_errors=True)
    return trash_id, folder
def trash_file(path, name, favorite):
    trash_id, folder = trash_folder({"name": name, "path": os.path.abspath(path), "favorite": favorite})
    root = root_of(path)
    shutil.move(path, os.path.join(folder, "file.txt")) # Moved, not copied: on another drive too.
    remove_empty_folders(os.path.dirname(os.path.abspath(path)), root)
    return trash_id
# A yaml key: its value as it was in the file, and its pictures (the card's, as "card", and its lines', by line); a yaml file left without keys
# goes too.
def trash_yaml_key(entry, name, favorite):
    data, parts = read_yaml(entry["path"]), key_parts(entry)
    parent = data
    for part in parts[:-1]:
        parent = parent.get(part) if isinstance(parent, dict) else None
    position = list(parent).index(parts[-1]) if isinstance(parent, dict) and parts[-1] in parent else None
    value = pop_key(data, parts)
    pictures = {str(line): path for line, path in line_pictures(entry).items()}
    if card_picture(entry):
        pictures["card"] = card_picture(entry)
    meta = {"name": name, "path": os.path.abspath(entry["path"]), "inner": entry["inner"], "value": value, "favorite": favorite, "position": position,
            "pictures": {key: os.path.splitext(path)[1].lower() for key, path in pictures.items()}}
    trash_id, folder = trash_folder(meta)
    for key, path in pictures.items():
        shutil.move(path, os.path.join(folder, f"picture-{key}{meta['pictures'][key]}"))
        remove_empty_folders(os.path.dirname(path), root_of(entry["path"]))
    if data:
        write_keys(entry["path"], data, lambda source: edit_remove(source, parts))
    else:
        os.remove(entry["path"])
    return trash_id
def restore_yaml_key(folder, meta, name, path):
    inner = checked_name(meta.get("inner"))
    if not path.lower().endswith((".yaml", ".yml")) or not name.endswith(inner):
        raise web.HTTPBadRequest(text="Wildcards: the deleted wildcard's record is damaged.")
    data, parts, value, position = read_yaml(path) if os.path.exists(path) else {}, inner.split("/"), meta.get("value"), meta.get("position")
    position = position if isinstance(position, int) and position >= 0 else None
    put_key(data, parts, value, name, position)
    if os.path.exists(path):
        write_keys(path, data, lambda source: edit_add(source, parts, value, position))
    else:
        write_yaml(path, data)
    pictures = meta.get("pictures")
    for key, ending in (pictures.items() if isinstance(pictures, dict) else []):
        line = None if key == "card" else int(key) if str(key).isdigit() else False
        if line is not False and ending in PICTURE_ENDINGS and os.path.isfile(os.path.join(folder, f"picture-{key}{ending}")):
            move_picture(os.path.join(folder, f"picture-{key}{ending}"), path, inner, line)
def restore_file(trash_id):
    if not isinstance(trash_id, str) or not TRASH_ID.fullmatch(trash_id):
        raise web.HTTPBadRequest(text="Wildcards: that is not a deleted file's id.")
    try: # The delete's folder, found among the trash's own entries (not a path made of the id as sent).
        folder = next(os.path.join(TRASH_FOLDER, name) for name in os.listdir(TRASH_FOLDER) if TRASH_ID.fullmatch(name) and name == trash_id)
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as file:
            meta = json.load(file)
        name, path = checked_name(meta.get("name")), os.path.abspath(str(meta.get("path", "")))
    except (OSError, ValueError, AttributeError, StopIteration):
        raise web.HTTPNotFound(text="Wildcards: nothing to undo: the deleted file is no longer kept.") from None
    if not any(path.startswith(root + os.sep) for root in map(os.path.abspath, folder_paths.get_folder_paths("wildcards"))):
        raise web.HTTPBadRequest(text="Wildcards: the deleted file was in a folder that is no longer a wildcards folder.")
    if wildcard_index(refresh=True).get(name) is not None or ("inner" not in meta and os.path.exists(path)):
        raise web.HTTPConflict(text=f"Wildcards: there is a wildcard {name} again: rename it to bring the deleted one back.")
    if "inner" in meta:
        restore_yaml_key(folder, meta, name, path)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.move(os.path.join(folder, "file.txt"), path)
    shutil.rmtree(folder, ignore_errors=True)
    return name, path, meta.get("favorite") is True
# The wildcards a file's lines use that no wildcard file answers (__haircolour__ for __hair/color__): the Wildcard Browser marks them. A name
# with a variable is left out (known only in a run); * and ? count when they match at least one name. lowered: the names in lower case.
def broken_references(options, names, lowered):
    broken = set()
    for line in options:
        for match in WILDCARD_PATTERN.finditer(line):
            name = match.group(1)
            if "${" in name or "\x00" in name:
                continue
            if "*" in name or "?" in name:
                if not any(fnmatch.fnmatchcase(item, name) for item in names):
                    broken.add(name)
            elif name.lower() not in lowered:
                broken.add(name)
    return sorted(broken)
# Find and replace in every wildcard, txt files and yaml keys (the text as written, case and all): what would change, or (apply) the change
# itself. Lines stay lines: neither text may hold a line break.
REPLACE_LONGEST = 500
def replace_in_yaml(path, keys, find, replacement):
    data, edits = read_yaml(path), []
    for parts in keys:
        level = data
        for part in parts[:-1]:
            level = level[part]
        value = level[parts[-1]]
        value = level[parts[-1]] = [item.replace(find, replacement) if isinstance(item, str) else item for item in value] if isinstance(value, list) else value.replace(find, replacement)
        edits.append(lambda source, parts=parts, value=value: edit_value(source, parts, value))
    write_keys(path, data, *edits)
def replace_in_wildcards(find, replacement, apply):
    changed, yaml_keys = [], {}
    for name, entry in sorted(wildcard_index(refresh=True).items(), key=lambda item: item[0].lower()):
        if "lines" in entry:
            count = sum(line.count(find) for line in entry["lines"])
            if count:
                line = next(line for line in entry["lines"] if find in line)
                changed.append({"name": name, "count": count, "line": line[:200], "after": line.replace(find, replacement)[:200]})
                yaml_keys.setdefault(entry["path"], []).append(key_parts(entry))
            continue
        try:
            with open(entry["path"], encoding="utf-8", newline="") as file:
                text = file.read()
        except (OSError, UnicodeDecodeError): # An unreadable file is not changed.
            continue
        count = text.count(find)
        if not count:
            continue
        line = next(line for line in text.splitlines() if find in line).strip()
        changed.append({"name": name, "count": count, "line": line[:200], "after": line.replace(find, replacement)[:200]})
        if apply:
            with open(entry["path"], "w", encoding="utf-8", newline="") as file:
                file.write(text.replace(find, replacement))
    if apply:
        for path, keys in yaml_keys.items():
            replace_in_yaml(path, keys, find, replacement)
        wildcard_index(refresh=True)
    return {"files": changed, "applied": apply}
# 🎲 Preview picks: what runs would put in for a wildcard (or a folder's __folder/*__), as many times, each with a new random seed: the same filling
# in as the prompt nodes (weights, choices, nested wildcards).
PREVIEW_MOST = 20
def preview_picks(name, folder, count):
    index = wildcard_index(refresh=True)
    if not (any(key.startswith(f"{name}/") for key in index) if folder else name in index):
        raise web.HTTPNotFound(text=f"Wildcards: no {'folder' if folder else 'wildcard'} {name}.")
    token = f"{name}/*" if folder else name
    picks = []
    for _ in range(count):
        try:
            (text,), _note = fill_in((f"__{token}__",), secrets.randbelow(0x100000000), "random")
        except (ValueError, RecursionError) as error: # A file that can't be read, a wildcard that uses itself...
            raise web.HTTPBadRequest(text=f"Wildcards: {error}") from None
        picks.append(text)
    return {"token": token, "picks": picks}
# Search the wildcards' lines (not only their names): each wildcard with a line that has the text, and its first such line.
def search_lines(text, limit=200):
    found = []
    for name, entry in sorted(wildcard_index(refresh=True).items(), key=lambda item: item[0].lower()):
        try:
            line = next((line for line in entry_lines(entry) if text in line.lower()), None)
        except ValueError: # An unreadable file: not found in it.
            continue
        if line is not None:
            found.append({"name": name, "line": line})
            if len(found) >= limit:
                break
    return found
# A yaml file in the lines mode, whole, as written (its comments too): by its path in its wildcards folder (styles/pack.yml), found among the
# yaml files that have wildcards. Saved as written once it reads as yaml keys.
def yaml_name(path):
    return os.path.relpath(path, root_of(path)).replace(os.sep, "/")
def yaml_file(name):
    name = checked_name(name)
    path = next((entry["path"] for entry in wildcard_index(refresh=True).values() if "lines" in entry and yaml_name(entry["path"]) == name), None)
    if path is None:
        raise web.HTTPNotFound(text=f"Wildcards: no yaml file {name} with wildcards.")
    return name, path
def read_whole(path):
    with open(path, encoding="utf-8-sig") as file:
        return file.read()
def save_yaml_text(path, text):
    text = text.replace("\r\n", "\n").rstrip("\n") + "\n"
    try:
        data = yaml.load(text, Loader=TextLoader)
    except yaml.YAMLError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: that is not valid yaml, nothing was saved: {error}") from None
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Wildcards: a yaml wildcards file is keys (name: lines), nothing was saved.")
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as file:
        file.write(text)
    os.replace(temporary, path)
# A picture's line=N, when there is one.
def picture_line(query):
    line = query.get("line")
    if line is None:
        return None
    if not line.isdigit() or int(line) > 99999:
        raise web.HTTPBadRequest(text="Wildcards: line is a line's number, counted from 0.")
    return int(line)
def folder_cards(folder):
    cards = []
    for name, entry in sorted(wildcard_index(refresh=True).items(), key=lambda item: item[0].lower()):
        if "inner" in entry and (not folder or name.startswith(f"{folder}/")):
            lines = [{"index": index, "text": line} for index, line in enumerate(entry["lines"]) if line and not line.startswith("#")]
            cards.append({"name": name, "lines": lines, "pictures": sorted(line_pictures(entry))})
    return cards
def write_lines(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(text.replace("\r\n", "\n").rstrip("\n") + "\n")
# A route runs in a thread (in_thread), so two requests can change the same file at once: a favorites file or a yaml file that both read,
# change and write would keep only one of the changes (a star clicked on two files in a row). The changes to the wildcard files go one at a time.
CHANGES = threading.Lock()
def one_at_a_time(function):
    @functools.wraps(function)
    def run(*args):
        with CHANGES:
            return function(*args)
    return run
# What the routes below do with the wildcard files, run in a thread (in_thread): indexing reads and stats every wildcard file, which on ComfyUI's
# event loop would hold up every other request meanwhile.
def wildcard_listing():
    files, favorites, index = [], read_favorites(), wildcard_index(refresh=True)
    names = list(index)
    lowered = {name.lower() for name in names}
    for name, entry in sorted(index.items(), key=lambda item: item[0].lower()):
        try:
            options, error = entry_lines(entry), {}
        except ValueError as problem: # One unreadable file doesn't hide the others: it is listed with its error.
            options, error = [], {"error": str(problem)}
        broken = broken_references(options, names, lowered)
        files.append({"name": name, "lines": len(options), "preview": options[:3], "favorite": name in favorites, **({"broken": broken} if broken else {}),
                      **({"yaml": os.path.basename(entry["path"]), "yaml_file": yaml_name(entry["path"])} if "lines" in entry else {}), **({"picture": True} if card_picture(entry) else {}), **error})
    return {"folders": folder_paths.get_folder_paths("wildcards"), "files": files}
def no_picture(name, line):
    return web.HTTPNotFound(text=f"Wildcards: no picture for {name}{'' if line is None else f' line {line}'}.")
def picture_of(name, line):
    path = card_picture(wildcard_index().get(name) or wildcard_index(refresh=True).get(name), line)
    if path is None:
        raise no_picture(name, line)
    return path
# Where a card's (or a line's) new picture goes, checked before the picture is read.
def picture_place(name, line):
    entry = wildcard_index(refresh=True).get(name)
    base = picture_base(entry, line)
    if base is None:
        raise web.HTTPBadRequest(text=f"Wildcards: {name} is not a yaml card: pictures are for the wildcards of a yaml file.")
    if line is not None and line >= len(entry["lines"]):
        raise web.HTTPBadRequest(text=f"Wildcards: {name} has no line {line} (its lines are counted from 0).")
    return base
@one_at_a_time
def remove_picture(name, line):
    path = card_picture(wildcard_index(refresh=True).get(name), line)
    if path is None:
        raise no_picture(name, line)
    try:
        os.remove(path)
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't remove the picture: {error.strerror or error}.") from None
    return {"name": name, "removed": path}
def yaml_text(file):
    name, path = yaml_file(file)
    try:
        text = read_whole(path)
    except (OSError, UnicodeDecodeError) as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't read {path}: {error}") from None
    return {"file": name, "path": path, "text": text.rstrip("\n")}
@one_at_a_time
def save_yaml(file, text):
    name, path = yaml_file(file)
    try:
        save_yaml_text(path, text)
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't save {name}: {error.strerror or error}.") from None
    wildcard_index(refresh=True)
    return {"saved": name, "path": path}
# A whole yaml file to the trash (↶ Undo with /diceforge/wildcards/restore), its wildcards' stars dropped.
@one_at_a_time
def delete_yaml(file):
    name, path = yaml_file(file)
    keys = [key for key, entry in wildcard_index().items() if entry.get("path") == path]
    try:
        trash_id = trash_file(path, name, False)
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't delete {name}: {error.strerror or error}.") from None
    wildcard_index(refresh=True)
    for key in keys:
        rename_favorite(key, None)
    return {"deleted": name, "path": path, "undo": trash_id}
@one_at_a_time
def convert(name, to):
    try:
        if to == "yaml":
            path, names = to_yaml(name)
            result = {"converted": name, "to": "yaml", "path": path, "names": names}
        else:
            paths, names = to_txt(name)
            result = {"converted": name, "to": "txt", "removed": paths, "names": names}
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't convert {name}: {error.strerror or error}.") from None
    wildcard_index(refresh=True)
    return result
def wildcard_text(name):
    entry = wildcard_index(refresh=True).get(name)
    if entry is None:
        raise web.HTTPNotFound(text=f"Wildcards: no wildcard {name}.")
    if "lines" in entry:
        return {"name": name, "path": entry["path"], "text": "\n".join(entry["lines"]), "yaml": os.path.basename(entry["path"])}
    try:
        lines = read_text_lines(entry["path"])
    except ValueError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: {error}") from None
    return {"name": name, "path": entry["path"], "text": "\n".join(lines)}
# Create (refused when the name is taken) or save: an existing wildcard is saved in place (a yaml key in its yaml file), a new one goes to the
# first wildcards folder as a txt file, or next to a yaml wildcard (next_to), into that wildcard's yaml file.
@one_at_a_time
def save_wildcard(name, text, next_to, create):
    entry = wildcard_index(refresh=True).get(name)
    if create and entry is not None:
        raise web.HTTPConflict(text=f"Wildcards: {name} already exists ({entry['path']}).")
    # On Windows (and macOS) Color.txt is color.txt: a new Color would write over color's lines.
    existing = create and entry is None and next_to is None and find_wildcard(name)
    if existing:
        raise web.HTTPConflict(text=f"Wildcards: {name} already exists as {existing} (file names don't tell upper and lower case apart here).")
    try:
        if entry is not None and "lines" in entry:
            save_yaml_key(entry, text)
            path = entry["path"]
        elif entry is None and next_to is not None:
            path = add_yaml_key(name, checked_name(next_to), text)
        else:
            path = find_wildcard(name) or new_path(name)
            write_lines(path, text)
    except OSError as error: # A name too long for the file system, a read-only folder...: a message, not a server error.
        raise web.HTTPBadRequest(text=f"Wildcards: can't save {name}: {error.strerror or error}.") from None
    wildcard_index(refresh=True)
    return {"saved": name, "path": path, **({"yaml": os.path.basename(path)} if path.lower().endswith((".yaml", ".yml")) else {})}
# Rename or move (a / in the new name puts it in a folder): a file stays in its wildcards folder, a yaml key among its yaml file's keys, and a
# name already taken is refused.
@one_at_a_time
def rename_wildcard(name, to):
    entry = existing_entry(name)
    path = entry["path"]
    taken = wildcard_index().get(to)
    if "lines" in entry:
        if to == name:
            return {"renamed": name, "to": to, "path": path}
        if taken is not None:
            raise web.HTTPConflict(text=f"Wildcards: {to} already exists ({taken['path']}).")
        move, target = (rename_yaml_key, name, to, entry), path
    else:
        target = new_path(to, root_of(path))
        if taken is not None and os.path.normcase(os.path.abspath(taken["path"])) != os.path.normcase(os.path.abspath(path)): # Only a change of case is the same file.
            raise web.HTTPConflict(text=f"Wildcards: {to} already exists ({taken['path']}).")
        if os.path.exists(target) and os.path.normcase(target) != os.path.normcase(os.path.abspath(path)):
            raise web.HTTPConflict(text=f"Wildcards: {target} already exists.")
        move = (move_file, path, target)
    try:
        move[0](*move[1:])
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't rename {name} to {to}: {error.strerror or error}.") from None
    wildcard_index(refresh=True)
    rename_favorite(name, to)
    return {"renamed": name, "to": to, "path": target}
@one_at_a_time
def delete_wildcard(name):
    entry = existing_entry(name)
    path = entry["path"]
    trash = (trash_yaml_key, entry) if "lines" in entry else (trash_file, path)
    try:
        trash_id = trash[0](*trash[1:], name, name in read_favorites())
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't delete {name}: {error.strerror or error}.") from None
    wildcard_index(refresh=True)
    rename_favorite(name, None)
    return {"deleted": name, "path": path, "undo": trash_id}
# Undo a delete: the id is the delete's "undo".
@one_at_a_time
def restore_wildcard(trash_id):
    try:
        name, path, favorite = restore_file(trash_id)
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't bring the file back: {error.strerror or error}.") from None
    wildcard_index(refresh=True)
    if favorite:
        try:
            write_favorites(read_favorites() | {name})
        except OSError: # Back without its star.
            pass
    return {"restored": name, "path": path}
@one_at_a_time
def import_into(data, folder):
    try:
        imported, skipped, left_out = import_zip(data, folder)
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: can't import the zip: {error.strerror or error}.") from None
    wildcard_index(refresh=True)
    return {"imported": imported, "skipped": skipped, "left_out": left_out}
@one_at_a_time
def set_favorite(name, favorite):
    if favorite and name not in wildcard_index(refresh=True):
        raise web.HTTPNotFound(text=f"Wildcards: no wildcard {name}.")
    names = read_favorites()
    try:
        write_favorites(names | {name} if favorite else names - {name})
    except OSError as error:
        raise web.HTTPBadRequest(text=f"Wildcards: the favorites could not be saved: {error.strerror or error}.") from None
    return {"name": name, "favorite": favorite}
def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/wildcards")
    async def list_wildcards(request):
        return web.json_response(await in_thread(wildcard_listing))
    # A card's picture, or with line=N the picture of its line N (counted from 0, as in the yaml list).
    @routes.get("/diceforge/wildcards/picture")
    async def wildcard_picture(request):
        name, line = checked_name(request.rel_url.query.get("name")), picture_line(request.rel_url.query)
        return web.FileResponse(await in_thread(picture_of, name, line), headers={"Cache-Control": "max-age=300"})
    @routes.post("/diceforge/wildcards/picture")
    async def set_wildcard_picture(request):
        name, line = checked_name(request.rel_url.query.get("name")), picture_line(request.rel_url.query)
        base = await in_thread(picture_place, name, line)
        data = await read_up_to(request, PICTURE_BYTES) # The whole body (content.read(n) gives only what has come so far).
        if len(data) > PICTURE_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=PICTURE_BYTES, actual_size=len(data), text="Wildcards: the picture is over 20 MB.")
        ending = picture_ending(data)
        if ending is None:
            raise web.HTTPBadRequest(text="Wildcards: send a PNG, JPEG, WebP or GIF picture.")
        try:
            path = await in_thread(one_at_a_time(save_picture), base, data, ending)
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't save the picture: {error.strerror or error}.") from None
        return web.json_response({"name": name, "picture": path})
    @routes.delete("/diceforge/wildcards/picture")
    async def remove_wildcard_picture(request):
        name, line = checked_name(request.rel_url.query.get("name")), picture_line(request.rel_url.query)
        return web.json_response(await in_thread(remove_picture, name, line))
    @routes.get("/diceforge/wildcards/yaml")
    async def read_yaml_file(request):
        return web.json_response(await in_thread(yaml_text, request.rel_url.query.get("file")))
    @routes.post("/diceforge/wildcards/yaml")
    async def save_yaml_file(request):
        body = await json_body(request)
        return web.json_response(await in_thread(save_yaml, body.get("file"), str(body.get("text", ""))))
    @routes.delete("/diceforge/wildcards/yaml")
    async def delete_yaml_file(request):
        return web.json_response(await in_thread(delete_yaml, request.rel_url.query.get("file")))
    # The yaml cards of a folder (all of them without one) with their lines, for the cards mode's card per line: each line's index in its key's
    # list, and the lines that have a picture.
    @routes.get("/diceforge/wildcards/cards")
    async def wildcard_cards(request):
        folder = request.rel_url.query.get("folder", "").strip()
        folder = checked_name(folder) if folder else ""
        return web.json_response({"cards": await in_thread(folder_cards, folder)})
    # Convert a txt wildcard or folder to one yaml file ("to": "yaml"), or the yaml file(s) of a wildcard or folder to txt files ("to": "txt").
    @routes.post("/diceforge/wildcards/convert")
    async def convert_wildcards(request):
        body = await json_body(request)
        name, to = checked_name(body.get("name")), body.get("to")
        if to not in ("yaml", "txt"):
            raise web.HTTPBadRequest(text='Wildcards: "to" must be "yaml" or "txt".')
        return web.json_response(await in_thread(convert, name, to))
    @routes.get("/diceforge/wildcards/file")
    async def read_wildcard_file(request):
        return web.json_response(await in_thread(wildcard_text, checked_name(request.rel_url.query.get("name"))))
    @routes.post("/diceforge/wildcards/file")
    async def save_wildcard_file(request):
        body = await json_body(request)
        return web.json_response(await in_thread(save_wildcard, checked_name(body.get("name")), str(body.get("text", "")), body.get("next_to"), body.get("create") is True))
    @routes.post("/diceforge/wildcards/rename")
    async def rename_wildcard_file(request):
        body = await json_body(request)
        return web.json_response(await in_thread(rename_wildcard, checked_name(body.get("name")), checked_name(body.get("to"))))
    @routes.delete("/diceforge/wildcards/file")
    async def delete_wildcard_file(request):
        return web.json_response(await in_thread(delete_wildcard, checked_name(request.rel_url.query.get("name"))))
    @routes.post("/diceforge/wildcards/restore")
    async def restore_wildcard_file(request):
        return web.json_response(await in_thread(restore_wildcard, (await json_body(request)).get("id")))
    @routes.get("/diceforge/wildcards/preview")
    async def preview_wildcard(request):
        query = request.rel_url.query
        name = checked_name(query.get("name"))
        try:
            count = int(query.get("count", "5"))
        except ValueError:
            raise web.HTTPBadRequest(text="Wildcards: count must be a number.") from None
        if not 1 <= count <= PREVIEW_MOST:
            raise web.HTTPBadRequest(text=f"Wildcards: count must be 1 to {PREVIEW_MOST}.")
        folder = query.get("folder") in ("1", "true")
        return web.json_response(await in_thread(preview_picks, name, folder, count))
    @routes.post("/diceforge/wildcards/replace")
    async def replace_wildcards(request):
        body = await json_body(request)
        find, replacement, apply = body.get("find"), body.get("replace", ""), body.get("apply", False)
        if not isinstance(find, str) or not find or len(find) > REPLACE_LONGEST or not isinstance(replacement, str) or len(replacement) > REPLACE_LONGEST:
            raise web.HTTPBadRequest(text=f"Wildcards: find (1 to {REPLACE_LONGEST} characters) and replace (up to {REPLACE_LONGEST}) are texts.")
        if any(mark in find + replacement for mark in "\r\n") or not isinstance(apply, bool):
            raise web.HTTPBadRequest(text="Wildcards: find and replace work within a line (no line breaks); apply is true or false.")
        try:
            return web.json_response(await in_thread(one_at_a_time(replace_in_wildcards), find, replacement, apply))
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Wildcards: can't replace: {error.strerror or error}.") from None
    @routes.get("/diceforge/wildcards/export")
    async def export_wildcards(request):
        folder = request.rel_url.query.get("folder", "").strip()
        folder = checked_name(folder) if folder else ""
        data = await in_thread(export_zip, folder)
        filename = f"wildcards-{folder.replace('/', '-')}.zip" if folder else "wildcards.zip"
        return web.Response(body=data, content_type="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})
    @routes.post("/diceforge/wildcards/import")
    async def import_wildcards(request):
        folder = request.rel_url.query.get("folder", "").strip()
        folder = checked_name(folder) if folder else ""
        data = await read_up_to(request, ZIP_BYTES)
        if len(data) > ZIP_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=ZIP_BYTES, actual_size=len(data), text="Wildcards: the zip is over 512 MB.")
        return web.json_response(await in_thread(import_into, data, folder))
    @routes.get("/diceforge/wildcards/search")
    async def search_wildcard_lines(request):
        text = request.rel_url.query.get("q", "").strip().lower()
        if len(text) < 2:
            raise web.HTTPBadRequest(text="Wildcards: search for at least 2 characters.")
        return web.json_response({"found": await in_thread(search_lines, text)})
    @routes.post("/diceforge/wildcards/favorite")
    async def favorite_wildcard(request):
        body = await json_body(request)
        name, favorite = checked_name(body.get("name")), body.get("favorite")
        if not isinstance(favorite, bool):
            raise web.HTTPBadRequest(text="Wildcards: favorite must be true or false.")
        return web.json_response(await in_thread(set_favorite, name, favorite))
register_routes()
