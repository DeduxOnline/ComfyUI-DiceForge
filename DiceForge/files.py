# Folders of the model and wildcard files: the folder a file is in, and the empty folders a delete or a move leaves behind.
import os


# The one of the roots (the ComfyUI folders of a kind, or the wildcards folder) that holds path.
def root_in(roots, path):
    path = os.path.abspath(path)
    return next(root for root in map(os.path.abspath, roots) if path.startswith(root + os.sep))


# Folders left empty by a delete or a move go too, up to (not including) the root.
def remove_empty_folders(folder, root):
    while folder != root and folder.startswith(root + os.sep):
        try:
            os.rmdir(folder)
        except OSError: # Not empty (or not removable): it stays, and so do the folders above it.
            return
        folder = os.path.dirname(folder)
