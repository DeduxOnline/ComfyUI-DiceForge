# Node help: DiceForge/web/docs/<node id>.md, which ComfyUI shows in its node help panel in place of a node's description. A page is short,
# for a side panel: the node's description, its picture from the README, what it has besides its inputs (NOTES), its inputs with their
# defaults and tooltips, its outputs (each node its own, also where the README describes several nodes in one section) and a link to its
# README section for the rest. Written from the code and the
# README, so they never say different things: after a change to either, write the pages again with
#   DICEFORGE_WRITE_NODE_DOCS=1 python -m pytest tests/test_node_docs.py
import os
import re
import pytest
from comfy_api.latest import io
from test_docs import README, ROOT, SCHEMAS, TABLE_ROW, section

DOCS = ROOT / "DiceForge" / "web" / "docs"
REPOSITORY = "https://github.com/DeduxOnline/ComfyUI-DiceForge"
PICTURE = re.compile(r'<img src="DiceForge/web/docs/(images/[^"]+)"[^>]*?\balt="([^"]*)"[^>]*>')


def help_page(text):
    """A README section as a help page: its pictures next to the page (as Markdown, which the panel shows), its other links to GitHub."""
    text = PICTURE.sub(r"![\2](\1)", text)
    text = text.replace("](DiceForge/web/docs/images/", "](images/")
    text = text.replace("](#", f"]({REPOSITORY}#")
    text = re.sub(r"\]\((?!https?:|mailto:|images/)([^)\s]+)\)", rf"]({REPOSITORY}/blob/main/\1)", text)
    return text.strip() + "\n"


def slug_of(name):
    return next(slug for names, slug in TABLE_ROW.findall(README) if name in names)


# Descriptions and tooltips are plain text, which Markdown would change: __name__ would turn bold, and <lora:name:weight> is dropped as HTML.
def plain(text):
    return re.sub(r"([_*\\])", r"\\\1", text).replace("<", "&lt;")


def cell(text):
    return text.replace("\n", " ").replace("|", "\\|")


# Inputs a node's own frontend hides and replaces: LoRA Stack's rows are kept in loras (web/lora_stack.js), and NOTES says what is shown instead.
HIDDEN = {("DiceForgeLoraStack", "loras")}
# What a node has besides its inputs: buttons, panels and menu tools of its frontend, and the warnings a short page must not lose.
NOTES = {
    "DiceForgeCLIPDualTextEncode": "Its right-click menu has the prompt tools: **📖 Syntax guide**, **🕘 Prompt history**, **🎲 Wildcard Browser**, "
        "**✂ Selection → new wildcard…**, **🎴 LoRA Browser** (to insert trigger words), **🏷 Tag autocomplete** (download tag lists), "
        "**🏷 Tag Browser** and **🎨 Prompt styles**.",
    "DiceForgeLoraStack": "The LoRAs are rows on the node: **⋮⋮** (drag to reorder), on/off, the LoRA (click its name to pick another one), "
        "**ℹ** (Model info), **🏷** (trigger words), a **group**, **🎲** (random strength), the strength and **✕** (remove). "
        "**＋ Add LoRA** opens the LoRA Browser; *Separate CLIP strength* and the groups' settings are under the rows.",
    "DiceForgeGrid": "Under the node, the cells of the grid: click one to star it (**★**); **💾 Save N kept** saves the starred ones at full size, "
        "with the workflow of their own run; **↺** on a cell opens the workflow of its run.",
    "DiceForgeXYPlot": "The node shows the headers and the number of images; **▶ Queue N images** queues a run for every cell (click again to stop). "
        "Connect `seed` to KSampler, or set KSampler's *control after generate* to *fixed*: otherwise every cell gets another seed.",
    "DiceForgeAnimaNAG": "At CFG 1 ComfyUI skips the negative prompt, so the node turns it back on: 10 Turbo steps take 13–14 s instead of 5 s. "
        "It needs the positive and negative prompts in one batch: when low VRAM makes ComfyUI run them apart, that step has no NAG. "
        "With several Anima NAG nodes in a row, the last one counts; on a model other than Anima it stops with an error.",
    "DiceForgeDanbooruEnhancer": "Under its inputs the node shows the posts' pictures (click one to open the post; pictures that aren't general are "
        "blurred until clicked), the added tags (click to copy) and what it searched.",
}


# A list type is a combo with every option (Random Sampler's sampler_name), and a DynamicCombo a combo that adds inputs: both are COMBO.
def type_of(item):
    return "COMBO" if not isinstance(item.io_type, str) or isinstance(item, io.DynamicCombo.Input) else item.io_type


def default_of(item):
    """A widget's default as the node starts with it. Not a file name: those come from this computer's models folder (HiresFix's model_name)."""
    value = getattr(item, "default", None)
    if not isinstance(item, io.WidgetInput) or item.force_input or value is None or value == "" or isinstance(item, io.DynamicCombo.Input):
        return ""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        value = f"{value:g}"
    value = str(value)
    if isinstance(item, io.Combo.Input) and re.search(r"\.\w+$", value):
        return ""
    return "`" + cell(value if len(value) <= 24 else value[:23] + "…").replace("`", "'") + "`"


# The rows of an input table: each input (sockets marked optional; a widget always has a value), and after a DynamicCombo the inputs its
# options add, once each, with the options that have them.
def input_rows(schema, items):
    for item in items:
        if (schema.node_id, item.id) in HIDDEN:
            continue
        socket = not isinstance(item, io.WidgetInput) or item.force_input
        yield f"`{item.id}`" + (" (optional)" if item.optional and socket else ""), item
        if isinstance(item, io.DynamicCombo.Input):
            added = {}
            for option in item.options:
                for nested in option.inputs:
                    added.setdefault(nested.id, (nested, []))[1].append(option.key)
            for nested, keys in added.values():
                yield f"`{nested.id}` (`{item.id}`: {', '.join(keys)})", nested


def input_table(schema, items):
    rows = [f"| {name} | {type_of(item)} | {default_of(item)} | {cell(plain(item.tooltip))} |" for name, item in input_rows(schema, items)]
    return "\n".join(["| Input | Type | Default | Description |", "|---|---|---|---|"] + rows)


def output_table(items):
    rows = [f"| `{item.display_name or item.id}` | {type_of(item)} | {cell(plain(item.tooltip))} |" for item in items]
    return "\n".join(["| Output | Type | Description |", "|---|---|---|"] + rows)


# The node's picture: the first of its README section, else one that names it (Random Sampler and Dice Grid share another node's picture).
def picture_of(schema, slug):
    return PICTURE.search(section(slug)) or next((found for found in PICTURE.finditer(README) if schema.display_name in found.group(2)), None)


def schema_page(schema):
    slug = slug_of(schema.display_name)
    picture = picture_of(schema, slug)
    shown = [item for item in schema.inputs if not item.advanced]
    advanced = [item for item in schema.inputs if item.advanced]
    parts = [plain(schema.description), f"![{picture.group(2)}]({picture.group(1)})" if picture else None,
             NOTES.get(schema.node_id),
             "## Inputs\n\n" + input_table(schema, shown) if shown else None,
             "## Advanced inputs\n\nUnder **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic "
             "design).\n\n" + input_table(schema, advanced) if advanced else None,
             "## Outputs\n\n" + output_table(schema.outputs),
             f"More in the [DiceForge guide]({REPOSITORY}#{slug}): examples, tips, and how it works with the other nodes."]
    return "\n\n".join(part for part in parts if part) + "\n"


def pages():
    found = {f"{schema.node_id}.md": schema_page(schema) for schema in SCHEMAS}
    found["DiceForgeWildcardNote.md"] = help_page(section(slug_of("Wildcard Note"))) # A frontend node (web/wildcard_note.js), with no schema.
    return found


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda schema: schema.node_id)
def test_every_node_has_a_description_and_tooltips(schema):
    assert schema.description
    assert [item.id for item in schema.inputs for item in item.get_all() if not item.tooltip] == [] # With the inputs a DynamicCombo adds.
    assert [item.display_name or item.id for item in schema.outputs if not item.tooltip] == []


def test_every_node_has_its_help_page():
    expected = pages()
    if os.environ.get("DICEFORGE_WRITE_NODE_DOCS"):
        for old in DOCS.glob("*.md"):
            old.unlink()
        for name, text in expected.items():
            (DOCS / name).write_text(text, encoding="utf-8", newline="\n")
    found = {path.name: path.read_text(encoding="utf-8") for path in DOCS.glob("*.md")}
    assert sorted(found) == sorted(expected)
    assert [name for name in expected if found[name] != expected[name]] == [], \
        "the README or a node changed: DICEFORGE_WRITE_NODE_DOCS=1 python -m pytest tests/test_node_docs.py"


def test_the_pictures_of_the_help_pages_are_there():
    shown = {picture for path in DOCS.glob("*.md") for picture in re.findall(r"\]\((images/[^)]+)\)", path.read_text(encoding="utf-8"))}
    assert shown and [picture for picture in shown if not (DOCS / picture).is_file()] == []
