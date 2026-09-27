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
