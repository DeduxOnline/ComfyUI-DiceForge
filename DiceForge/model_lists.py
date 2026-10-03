import fnmatch
import os
import re
import folder_paths
# Model files for the random loader nodes: the folders of a model kind (loras, checkpoints, diffusion_models), and the files in one of them.
ALL_FOLDERS = "(all)"
def model_files(kind):
    return sorted(folder_paths.get_filename_list(kind), key=str.lower)
def model_folders(kind):
    folders = set()
    for name in model_files(kind):
        parts = name.replace("\\", "/").split("/")[:-1]
        folders.update("/".join(parts[:depth]) for depth in range(1, len(parts) + 1)) # "a/b/x.safetensors" is in "a" and in "a/b".
    return [ALL_FOLDERS, *sorted(folders, key=str.lower)]
# The files of a kind a name stands for, as people type them: the file name with or without folder and extension ("style/ink", "ink",
# "ink.safetensors"), or a pattern ("style/*"). Sorted; none when nothing matches.
def stem(name):
    return re.sub(r"\.[^./]+$", "", name.replace("\\", "/")).lower()
def matching_files(kind, name):
    wanted, pattern = stem(name), name.replace("\\", "/").lower()
    return sorted((file for file in folder_paths.get_filename_list(kind) if fnmatch.fnmatch(file.replace("\\", "/").lower(), pattern)
                   or stem(file) == wanted or stem(file).split("/")[-1] == wanted), key=str.lower)
def files_in_folder(kind, folder):
    if folder == ALL_FOLDERS:
        return model_files(kind)
    return [name for name in model_files(kind) if name.replace("\\", "/").startswith(folder + "/")] # Subfolders included.
def folder_input(kind, what):
    from comfy_api.latest import io
    return io.Combo.Input(
        "folder",
        options=model_folders(kind),
        default=ALL_FOLDERS,
        tooltip=f"The folder to pick the {what} from, subfolders included. (all): every {what}. Refresh the node definitions (R) after adding folders.",
    )
# What the random loaders share: the seed inputs, the pick of a file of the folder by the seed mode, and the fingerprint that runs the node again
# when the folder's files change.
def seed_inputs(things):
    from comfy_api.latest import io
    from .seed_modes import SEED_MODES, seed_mode_tooltip
    return [
        io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True,
                     tooltip="Seed for the random pick. With deck or sequential, set control after generate to increment."),
        io.Combo.Input("seed_mode", options=SEED_MODES, default="random", tooltip=seed_mode_tooltip(things), advanced=True),
    ]
def pick_model_file(kind, folder, seed, seed_mode, what, extra=()):
    from .seed_modes import MEMORY, make_picker, pick_label
    files = files_in_folder(kind, folder)
    if not files:
        raise ValueError(f"No {what} files in {folder}: add some to ComfyUI/models/{kind}, or pick another folder.")
    name = pick_label(files + list(extra), make_picker(seed_mode, seed), seed)
    MEMORY.save()
    return name
def folder_fingerprint(kind, folder, *more):
    return tuple(files_in_folder(kind, folder)), *more
# Image files for Random Image: the images under a folder (subfolders included, hidden folders and the mask editor's clipspace left out), as paths
# relative to it with "/", sorted by name.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
def image_files(root):
    found = []
    for folder, subfolders, files in os.walk(root):
        subfolders[:] = [name for name in subfolders if not name.startswith(".") and not (folder == root and name == "clipspace")]
        relative = os.path.relpath(folder, root).replace("\\", "/")
        found += [name if relative == "." else f"{relative}/{name}" for name in files if name.lower().endswith(IMAGE_EXTENSIONS)]
    return sorted(found, key=str.lower)
def image_folders(root):
    folders = set()
    for name in image_files(root):
        parts = name.split("/")[:-1]
        folders.update("/".join(parts[:depth]) for depth in range(1, len(parts) + 1))
    return [ALL_FOLDERS, *sorted(folders, key=str.lower)]
def images_in_folder(root, folder):
    files = image_files(root)
    return files if folder == ALL_FOLDERS else [name for name in files if name.startswith(folder + "/")]
