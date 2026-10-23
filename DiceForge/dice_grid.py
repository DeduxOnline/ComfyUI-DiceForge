import json
import logging
import math
import os
import re
import shutil
import numpy as np
import torch
import folder_paths
from aiohttp import web
from comfy.cli_args import args
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo
from comfy_api.latest import io, ui
from .routes import in_thread, json_body
# Dice Grid collects one image per run (the runs of a DiceForge series) and lays them out in a labeled grid. The cells are kept as small PNG files
# in the ComfyUI user folder between runs, not in RAM, so a grid survives a restart. Finished grids are saved to the output folder.
GRID_FOLDER = os.path.join(folder_paths.get_user_directory(), "DiceForge", "grids")
MAX_CELLS = 1000 # A grid without count and labels starts over after this many cells.
BACKGROUND, TEXT, HEADER = (24, 24, 24), (235, 235, 235), (40, 40, 40)
LABEL_EXTENSIONS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
# Label text: a model or image file name is shown without its folder and extension ("anime/styles/ink.safetensors" -> "ink").
def clean_label(label):
    label = (label or "").strip()
    if label.lower().endswith(LABEL_EXTENSIONS):
        label = os.path.splitext(label.replace("\\", "/").rsplit("/", 1)[-1])[0]
    return label
def font_for(cell_width):
    try:
        return ImageFont.load_default(size=max(12, cell_width // 18)) # NOSONAR: size exists since Pillow 10.1; older Pillow raises TypeError, handled below.
    except TypeError:
        return ImageFont.load_default() # Pillow before 10.1: the small bitmap font.
# Text split into lines that fit a width (long words are cut), for captions and headers.
def wrap(draw, text, font, width):
    lines = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip()
            if draw.textlength(candidate, font=font) <= width or not line:
                line = candidate
                while draw.textlength(line, font=font) > width and len(line) > 1:
                    cut = max(1, len(line) - 1)
                    while cut > 1 and draw.textlength(line[:cut], font=font) > width:
                        cut -= 1
                    lines.append(line[:cut])
                    line = line[cut:]
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines
def text_height(lines, font):
    return len(lines) * round(font.size * 1.3) if lines and any(lines) else 0
def draw_lines(draw, lines, font, x, y, width):
    for index, line in enumerate(lines):
        draw.text((x + (width - draw.textlength(line, font=font)) / 2, y + index * round(font.size * 1.3)), line, font=font, fill=TEXT)
# Grid rendering. XY grid (some cells have a row label): rows by row label and columns by label, in order of first appearance, with headers.
# Plain grid: `columns` per row (0: about square), each image with its label under it.
def render_cells(cells, columns, cell_width, pad=8):
    font = font_for(cell_width)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if any(cell["row"] for cell in cells):
        rows = list(dict.fromkeys(cell["row"] for cell in cells))
        cols = list(dict.fromkeys(cell["label"] for cell in cells))
        place = {(cell["row"], cell["label"]): cell for cell in cells}
        row_width = min(cell_width, int(max(probe.textlength(line, font=font) for row in rows for line in wrap(probe, row, font, cell_width))) + 2 * pad) # Row header column.
        header = max(text_height(wrap(probe, col, font, cell_width), font) for col in cols) + 2 * pad
        heights = [max((place[(row, col)]["image"].height for col in cols if (row, col) in place), default=0) for row in rows]
        grid = Image.new("RGB", (row_width + len(cols) * (cell_width + pad) + pad, header + sum(heights) + pad * (len(rows) + 1)), BACKGROUND)
        draw = ImageDraw.Draw(grid)
        for index, col in enumerate(cols):
            x = row_width + pad + index * (cell_width + pad)
            draw_lines(draw, wrap(draw, col, font, cell_width), font, x, pad, cell_width)
        y = header
        for row, height in zip(rows, heights):
            lines = wrap(draw, row, font, row_width - 2 * pad)
            draw_lines(draw, lines, font, pad, y + (height - text_height(lines, font)) / 2, row_width - 2 * pad)
            for index, col in enumerate(cols):
                if (row, col) in place:
                    image = place[(row, col)]["image"]
                    grid.paste(image, (row_width + pad + index * (cell_width + pad), y + (height - image.height) // 2))
            y += height + pad
        return grid
    columns = columns or math.ceil(math.sqrt(len(cells)))
    rows = [cells[start:start + columns] for start in range(0, len(cells), columns)]
    captions = [[wrap(probe, cell["label"], font, cell_width) if cell["label"] else [] for cell in row] for row in rows]
    heights = [max(cell["image"].height for cell in row) for row in rows]
    caption_heights = [max(text_height(lines, font) for lines in row) for row in captions]
    grid = Image.new("RGB", (pad + min(columns, len(cells)) * (cell_width + pad), pad + sum(h + c + (pad if c else 0) + pad for h, c in zip(heights, caption_heights))), BACKGROUND)
    draw = ImageDraw.Draw(grid)
    y = pad
    for row, lines_row, height, caption in zip(rows, captions, heights, caption_heights):
        for index, (cell, lines) in enumerate(zip(row, lines_row)):
            x = pad + index * (cell_width + pad)
            grid.paste(cell["image"], (x + (cell_width - cell["image"].width) // 2, y + (height - cell["image"].height) // 2))
            draw_lines(draw, lines, font, x, y + height + pad, cell_width)
        y += height + caption + (pad if caption else 0) + pad
    return grid
LEGEND_POSITIONS = ["top", "bottom"]
# The grid with its legend: a text block above or below it (the legend input), and with numbered cells, the numbers under the images and the full
# labels listed in the legend ("1. anime/ink"), for labels too long to fit under an image. XY grids keep their headers and aren't numbered.
def render(cells, columns, cell_width, legend="", position="top", numbered=False, pad=8):
    entries = []
    if numbered and not any(cell["row"] for cell in cells):
        entries = [f"{index + 1}. {cell['label']}" for index, cell in enumerate(cells) if cell["label"]]
        cells = [{**cell, "label": str(index + 1)} for index, cell in enumerate(cells)]
    grid = render_cells(cells, columns, cell_width, pad)
    text = "\n".join(part for part in (legend.strip(), "\n".join(entries)) if part)
    if not text:
        return grid
    font = font_for(cell_width)
    lines = wrap(ImageDraw.Draw(grid), text, font, grid.width - 4 * pad)
    height = text_height(lines, font) + 2 * pad
    framed = Image.new("RGB", (grid.width, grid.height + height), BACKGROUND)
    top = position != "bottom"
    framed.paste(grid, (0, height if top else 0))
    draw = ImageDraw.Draw(framed)
    y = 0 if top else grid.height
    draw.rectangle((0, y, grid.width, y + height - 1), fill=HEADER)
    for index, line in enumerate(lines):
        draw.text((2 * pad, y + pad + index * round(font.size * 1.3)), line, font=font, fill=TEXT)
    return framed
def to_tensor(image):
    return torch.from_numpy(np.array(image).astype(np.float32) / 255.0)[None,]
def full_pil(tensor):
    return Image.fromarray(np.clip(255.0 * tensor.cpu().float().numpy(), 0, 255).astype(np.uint8)).convert("RGB")
def to_pil(tensor, cell_width):
    image = full_pil(tensor)
    return image.resize((cell_width, max(1, round(image.height * cell_width / image.width))), Image.LANCZOS)
# One grid's cells on disk: grids/<name>-<node id>/, with manifest.json listing the cells (file, label, row, kept) in order. Next to each cell, its
# image at full size with the run's workflow in it (00001.full.png), for the best ones kept from the grid (the cells panel, web/dice_grid.js).
CELL_FILE = re.compile(r"\d+\.png")
def grid_key(name, node_id):
    return f"{name}-{node_id}"
class GridStore:
    def __init__(self, key):
        self.folder = os.path.join(GRID_FOLDER, re.sub(r"[^\w.-]+", "_", key))
        self.manifest = os.path.join(self.folder, "manifest.json")
        try:
            with open(self.manifest, encoding="utf-8") as file:
                self.state = self.checked(json.load(file))
        except (OSError, ValueError):
            self.state = {"cells": [], "done": False, "next": 0}
    # A manifest as written by save(); a damaged one keeps the cells it still describes properly, and never names a file outside the grid folder.
    @staticmethod
    def checked(state):
        if not isinstance(state, dict):
            raise ValueError("not a grid manifest")
        cells = [{"file": cell["file"], "label": cell.get("label") if isinstance(cell.get("label"), str) else "", "row": cell.get("row") if isinstance(cell.get("row"), str) else "",
                  "kept": cell.get("kept") is True}
                 for cell in state.get("cells") if isinstance(cell, dict) and isinstance(cell.get("file"), str) and CELL_FILE.fullmatch(cell["file"])] \
            if isinstance(state.get("cells"), list) else []
        used = max((int(cell["file"][:-4]) + 1 for cell in cells), default=0)
        following = state.get("next") if isinstance(state.get("next"), int) and not isinstance(state.get("next"), bool) else 0
        return {"cells": cells, "done": state.get("done") is True, "next": max(following, used)} # New cells never overwrite a kept one.
    def clear(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        self.state = {"cells": [], "done": False, "next": 0}
    def add(self, image, label, row, full=None, metadata=None):
        os.makedirs(self.folder, exist_ok=True)
        name = f"{self.state['next']:05}.png"
        self.state["next"] += 1
        image.save(os.path.join(self.folder, name), compress_level=1)
        if full is not None:
            full.save(os.path.join(self.folder, full_name(name)), pnginfo=metadata, compress_level=4)
        self.state["cells"].append({"file": name, "label": label, "row": row, "kept": False})
    def cell(self, file):
        return next((cell for cell in self.state["cells"] if cell["file"] == file), None)
    def has(self, label, row):
        return any(cell["label"] == label and cell["row"] == row for cell in self.state["cells"])
    def cells(self, cell_width):
        loaded, kept = [], []
        for cell in self.state["cells"]:
            try:
                with Image.open(os.path.join(self.folder, cell["file"])) as image:
                    image = image.convert("RGB")
            except OSError as error: # A cell image deleted or damaged: left out of the grid instead of failing every run.
                logging.warning(f"[DiceForge] Dice Grid | Leaving out {cell['file']}: {error}")
                continue
            kept.append(cell)
            if image.width != cell_width: # cell_width changed during the grid.
                image = image.resize((cell_width, max(1, round(image.height * cell_width / image.width))), Image.LANCZOS)
            loaded.append({**cell, "image": image})
        self.state["cells"] = kept
        return loaded
    def save(self):
        os.makedirs(self.folder, exist_ok=True)
        with open(self.manifest, "w", encoding="utf-8") as file:
            json.dump(self.state, file)
# The run's prompt and workflow, for a kept image (as Save Image writes them), unless ComfyUI runs with --disable-metadata.
def run_metadata(hidden):
    if hidden is None or args.disable_metadata:
        return None
    metadata = PngInfo()
    if hidden.prompt is not None:
        metadata.add_text("prompt", json.dumps(hidden.prompt))
    for key, value in (hidden.extra_pnginfo or {}).items():
        metadata.add_text(key, json.dumps(value))
    return metadata
def full_name(file):
    return file[:-4] + ".full.png"
# Node schema (V3 / Nodes 2.0): collects the image of each run into a grid with labels (for example the LoRA or checkpoint name from the random
# loaders), and saves the grid when it is finished: after `count` images, or, with count 0, when a label comes again (a deck round is over).
class DiceGrid(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeGrid",
            display_name="Dice Grid",
            category="DiceForge/image",
            description="Collects the image of each run into a labeled grid (a comparison of LoRAs, checkpoints, samplers...) and saves it when it is finished.",
            search_aliases=["grid", "xy plot", "xy grid", "comparison", "contact sheet", "image grid", "dice grid"],
            is_output_node=True,
            hidden=[io.Hidden.unique_id, io.Hidden.prompt, io.Hidden.extra_pnginfo],
            inputs=[
                io.Image.Input("image", tooltip="The image of this run. Each run adds it to the grid (every image of a batch)."),
                io.String.Input("label", optional=True, force_input=True, tooltip="Caption of the image, for example lora_name or ckpt_name from a random loader. File names are shown without folder and extension. In an XY grid: the column."),
                io.String.Input("row_label", optional=True, force_input=True, tooltip="Connect to make an XY grid: rows by this label, columns by label (for example checkpoint x LoRA with seed mode combinations)."),
                io.Int.Input("count", default=0, min=0, max=MAX_CELLS, tooltip="Images in a finished grid. 0: the grid is finished when a label comes again, which is the end of a round with deck or shuffle."),
                io.Int.Input("columns", default=0, min=0, max=100, tooltip="Images per row (0: about square). XY grids take their columns from the labels."),
                io.Int.Input("cell_width", default=384, min=64, max=2048, step=8, tooltip="Width of each image in the grid; heights follow the aspect ratio, so images of different sizes fit.", advanced=True),
                io.Boolean.Input("save", default=True, tooltip="Save each finished grid to the output folder."),
                io.String.Input("filename_prefix", default="DiceForge/grid", tooltip="File name prefix of saved grids, in the output folder.", advanced=True),
                io.String.Input("name", default="grid", tooltip="Grids are kept per node and name: another name starts a separate grid (the old one stays until you come back to its name).", advanced=True),
                io.Boolean.Input("new_grid", default=False, tooltip="Start a new grid with this image (the unfinished one is dropped). Turn it off again for the next runs.", advanced=True),
                io.String.Input("legend", multiline=True, default="", tooltip="Text shown in a block above or below the grid: a title, the settings that stay the same, or the prompt (connect positive_text of CLIP Dual Text Encode)."),
                io.Combo.Input("legend_position", options=LEGEND_POSITIONS, default="top", tooltip="Where the legend goes: above or below the grid.", advanced=True),
                io.Boolean.Input("numbered", default=False, tooltip="Number the images and list their full labels in the legend (1. anime/ink ...), for labels too long to fit under an image. Not for XY grids, which have headers."),
            ],
            outputs=[
                io.Image.Output(display_name="grid", tooltip="The grid so far, this run's image included."),
                io.Int.Output(display_name="cells", tooltip="Images in the grid so far."),
            ],
        )
    # Method to run the node on every run, even when the image comes from the cache: each run adds a cell.
    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return os.urandom(8).hex()
    # Saves a finished grid to the output folder, with the workflow in the PNG like Save Image.
    @classmethod
    def save_grid(cls, grid, prefix):
        results = ui.ImageSaveHelper.save_images(to_tensor(grid), filename_prefix=prefix, folder_type=io.FolderType.output, cls=cls)
        logging.info(f"[DiceForge] Dice Grid | Saved {results[0].filename} ({grid.width}x{grid.height})")
        return results
    # Main method: adds this run's images, finishes the grid when it is full or a label repeats, and shows the grid on the node.
    @classmethod
    def execute(cls, image, count=0, columns=0, cell_width=384, save=True, filename_prefix="DiceForge/grid", name="grid", new_grid=False, legend="", legend_position="top", numbered=False, label=None, row_label=None):
        layout = (legend or "", legend_position, numbered) # Legend settings for every render of this run.
        store = GridStore(grid_key(name, cls.hidden.unique_id if cls.hidden else ""))
        if store.state["done"] or new_grid:
            store.clear()
        label, row = clean_label(label), clean_label(row_label)
        saved = None
        for index in range(image.shape[0]):
            cell_label = f"{label} #{index + 1}" if label and image.shape[0] > 1 else label
            repeat = count == 0 and (cell_label or row) and store.has(cell_label, row)
            if repeat or len(store.state["cells"]) >= (count or MAX_CELLS):
                if save and store.state["cells"]:
                    saved = cls.save_grid(render(store.cells(cell_width), columns, cell_width, *layout), filename_prefix) # A round is over: the grid is finished.
                store.clear()
            store.add(to_pil(image[index], cell_width), cell_label, row, full_pil(image[index]), run_metadata(cls.hidden))
        grid = render(store.cells(cell_width), columns, cell_width, *layout)
        if count and len(store.state["cells"]) >= count:
            store.state["done"] = True # Full: saved now, and the next run starts a new grid.
            if save:
                saved = cls.save_grid(grid, filename_prefix)
        store.save()
        cells = len(store.state["cells"])
        logging.info(f"[DiceForge] Dice Grid | {cells} cell(s){' of ' + str(count) if count else ''} | {row + ' / ' if row else ''}{label}")
        shown = ui.SavedImages(saved) if saved and store.state["done"] else ui.PreviewImage(to_tensor(grid), cls=cls)
        return io.NodeOutput(to_tensor(grid), cells, ui=shown)
# The cells panel under the node (web/dice_grid.js): the cells of the node's grid, their images, ★ to keep the best ones, and saving those at full
# size (with the run's workflow in them, like Save Image) to the output folder.
KEPT_PREFIX = "DiceForge/kept/kept"
def store_of(query):
    node, name = query.get("node"), query.get("name") or "grid"
    if not isinstance(node, str) or not node or not isinstance(name, str):
        raise web.HTTPBadRequest(text="Dice Grid: which node's grid (node and name).")
    return GridStore(grid_key(name, node))
def save_kept(store):
    saved = []
    for cell in store.state["cells"]:
        source = os.path.join(store.folder, full_name(cell["file"]))
        if not cell["kept"] or not os.path.isfile(source):
            continue
        folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(KEPT_PREFIX, folder_paths.get_output_directory())
        label = re.sub(r"[^\w.-]+", "_", " ".join(part for part in (cell["row"], cell["label"]) if part)).strip("_")[:60]
        file = f"{filename}_{counter:05}_{label}.png" if label else f"{filename}_{counter:05}_.png"
        os.makedirs(folder, exist_ok=True)
        shutil.copyfile(source, os.path.join(folder, file)) # The PNG as made: its workflow and prompt stay in it.
        saved.append(f"{subfolder}/{file}" if subfolder else file)
    return saved
# What the routes below do with a grid's files, in a thread (in_thread).
def grid_listing(query):
    store = store_of(query)
    cells = [{**cell, "full": os.path.isfile(os.path.join(store.folder, full_name(cell["file"])))} for cell in store.state["cells"]]
    return {"cells": cells, "done": store.state["done"]}
def cell_image(query):
    store, file = store_of(query), query.get("file", "")
    if not CELL_FILE.fullmatch(file) or store.cell(file) is None:
        raise web.HTTPNotFound(text="Dice Grid: no such cell.")
    path = os.path.join(store.folder, full_name(file) if query.get("full") == "1" else file)
    if not os.path.isfile(path):
        raise web.HTTPNotFound(text="Dice Grid: that image is gone.")
    return path
def keep_cells(body):
    store, kept = store_of(body), body.get("kept")
    files = body.get("files") if isinstance(body.get("files"), list) else [body.get("file")]
    if not isinstance(kept, bool) or not files or not all(isinstance(file, str) and store.cell(file) for file in files):
        raise web.HTTPBadRequest(text="Dice Grid: keep needs the cells (file or files) and kept true or false.")
    for file in files:
        store.cell(file)["kept"] = kept
    store.save()
    return {"kept": [cell["file"] for cell in store.state["cells"] if cell["kept"]]}
def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/grid")
    async def grid_cells(request):
        return web.json_response(await in_thread(grid_listing, dict(request.rel_url.query)))
    @routes.get("/diceforge/grid/image")
    async def grid_image(request):
        return web.FileResponse(await in_thread(cell_image, dict(request.rel_url.query)), headers={"Cache-Control": "no-cache"})
    @routes.post("/diceforge/grid/keep")
    async def grid_keep(request):
        return web.json_response(await in_thread(keep_cells, await json_body(request)))
    @routes.post("/diceforge/grid/save")
    async def grid_save(request):
        body = await json_body(request)
        try:
            saved = await in_thread(lambda: save_kept(store_of(body)))
        except OSError as error:
            raise web.HTTPBadRequest(text=f"Dice Grid: can't save the kept images: {error.strerror or error}.") from None
        if not saved:
            raise web.HTTPBadRequest(text="Dice Grid: no kept cells to save (★ a cell first).")
        return web.json_response({"saved": saved})
register_routes()
