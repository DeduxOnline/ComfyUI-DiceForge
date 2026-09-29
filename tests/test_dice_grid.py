# Dice Grid (DiceForge/dice_grid.py): labels, the rendered grid and legend, and collecting runs into grids that finish after `count` images or when a
# label comes again, kept on disk between runs.
import os
import folder_paths
import pytest
import torch
from PIL import Image
from DiceForge import dice_grid
from DiceForge.dice_grid import DiceGrid, GridStore, clean_label, render


def image(value=0.5, batch=1, height=32, width=48):
    return torch.full((batch, height, width, 3), value)


def run(name, img=None, **inputs):
    grid, cells = DiceGrid.execute(img if img is not None else image(), name=name, cell_width=64, filename_prefix=f"DiceForge/test_{name}", **inputs).result
    return grid, cells


def saved(name):
    folder = os.path.join(folder_paths.get_output_directory(), "DiceForge")
    return sorted(file for file in os.listdir(folder) if file.startswith(f"test_{name}_")) if os.path.isdir(folder) else []


@pytest.mark.parametrize("label, expected", [
    ("anime/styles/ink.safetensors", "ink"), ("C:\\models\\x.ckpt", "x"), ("photo.PNG", "photo"), ("euler / karras", "euler / karras"), (None, ""),
])
def test_clean_label(label, expected):
    assert clean_label(label) == expected


def cells(count, label="x", row=""):
    return [{"image": Image.new("RGB", (64, 40), (index * 40, 0, 0)), "label": f"{label}{index}", "row": row} for index in range(count)]


def test_render_lays_out_columns_and_adds_a_legend():
    two_columns, four_columns = render(cells(4), 2, 64), render(cells(4), 4, 64)
    assert four_columns.width > two_columns.width and two_columns.height > four_columns.height
    with_legend = render(cells(4), 2, 64, legend="a title")
    assert with_legend.width == two_columns.width and with_legend.height > two_columns.height
    top, bottom = render(cells(2), 2, 64, legend="t", position="top"), render(cells(2), 2, 64, legend="t", position="bottom")
    assert top.size == bottom.size and top.getpixel((5, 5)) != bottom.getpixel((5, 5))


def test_numbered_cells_list_their_labels_in_the_legend():
    plain, numbered = render(cells(3, label="a very long label "), 3, 64), render(cells(3, label="a very long label "), 3, 64, numbered=True)
    assert numbered.height > plain.height


def test_a_grid_finishes_after_count_images_and_is_saved():
    assert [run("count", count=3)[1] for _ in range(3)] == [1, 2, 3]
    assert len(saved("count")) == 1
    assert run("count", count=3)[1] == 1 # A new grid after a finished one.


def test_without_count_a_repeated_label_ends_the_round():
    for label in ("a", "b", "c"):
        run("round", label=label)
    assert saved("round") == []
    _, cells_now = run("round", label="a")
    assert cells_now == 1 and len(saved("round")) == 1


def test_batch_images_get_numbered_labels_and_new_grid_starts_over():
    _, count = run("batch", img=image(batch=3), label="lora.safetensors")
    store = GridStore("batch-")
    assert count == 3 and [cell["label"] for cell in store.state["cells"]] == ["lora #1", "lora #2", "lora #3"]
    assert run("batch", new_grid=True)[1] == 1


def test_xy_grid_uses_row_labels():
    for row in ("ckpt1", "ckpt2"):
        for column in ("a", "b"):
            grid, _ = run("xy", label=column, row_label=f"{row}.safetensors")
    store = GridStore("xy-")
    assert [(cell["row"], cell["label"]) for cell in store.state["cells"]] == [("ckpt1", "a"), ("ckpt1", "b"), ("ckpt2", "a"), ("ckpt2", "b")]
    assert grid.shape[0] == 1 and grid.shape[-1] == 3


def test_cells_survive_on_disk_between_runs():
    run("disk", label="one")
    store = GridStore("disk-")
    assert len(store.state["cells"]) == 1
    assert os.path.isfile(os.path.join(store.folder, store.state["cells"][0]["file"]))
    assert store.folder.startswith(dice_grid.GRID_FOLDER)


def test_the_node_runs_every_time():
    assert DiceGrid.fingerprint_inputs() != DiceGrid.fingerprint_inputs()
