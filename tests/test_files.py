# root_in and remove_empty_folders (DiceForge/files.py): the folder a file is in, and the empty folders a delete or a move leaves behind.
import os

from DiceForge.files import remove_empty_folders, root_in


def test_root_in_is_the_root_that_holds_the_path(tmp_path):
    loras, other = str(tmp_path / "loras"), str(tmp_path / "other")
    assert root_in([other, loras], os.path.join(loras, "a", "b.safetensors")) == os.path.abspath(loras)


def test_folders_left_empty_go_up_to_the_root(tmp_path):
    root = str(tmp_path / "loras")
    os.makedirs(os.path.join(root, "a", "b"))
    remove_empty_folders(os.path.join(root, "a", "b"), root)
    assert os.path.isdir(root)
    assert not os.path.exists(os.path.join(root, "a"))


def test_a_folder_with_files_stays(tmp_path):
    root = str(tmp_path / "loras")
    os.makedirs(os.path.join(root, "c", "d"))
    open(os.path.join(root, "c", "keep.txt"), "w").close()
    remove_empty_folders(os.path.join(root, "c", "d"), root)
    assert not os.path.exists(os.path.join(root, "c", "d"))
    assert os.path.isfile(os.path.join(root, "c", "keep.txt"))
