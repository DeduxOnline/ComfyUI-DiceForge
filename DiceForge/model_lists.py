import os
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
