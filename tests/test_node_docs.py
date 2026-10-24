# Node help: DiceForge/web/docs/<node id>.md, which ComfyUI shows in its node help panel in place of a node's description. A page is short,
# for a side panel: the node's description, its picture from the README, its inputs and outputs with their tooltips (each node its own, also
# where the README describes several nodes in one section) and a link to its README section for the rest. Written from the code and the
# README, so they never say different things: after a change to either, write the pages again with
#   DICEFORGE_WRITE_NODE_DOCS=1 python -m pytest tests/test_node_docs.py
import os
import re
import pytest
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


# A table of inputs or outputs, a row each: its name (optional inputs marked), type and tooltip. A tooltip's | would end its cell.
def table(heading, items):
    def row(item):
        name = f"`{item.display_name or item.id}`" if heading == "Output" else f"`{item.id}`" + (" (optional)" if item.optional else "")
        return f"| {name} | {item.io_type} | {plain(item.tooltip).replace(chr(10), ' ').replace('|', chr(92) + '|')} |"
    return "\n".join([f"| {heading} | Type | Description |", "|---|---|---|"] + [row(item) for item in items])


def schema_page(schema):
    slug = slug_of(schema.display_name)
    picture = PICTURE.search(section(slug))
    shown = [item for item in schema.inputs if not item.advanced]
    advanced = [item for item in schema.inputs if item.advanced]
    parts = [plain(schema.description), f"![{picture.group(2)}]({picture.group(1)})" if picture else None,
             "## Inputs\n\n" + table("Input", shown) if shown else None,
             "## Advanced inputs\n\nUnder **Show advanced inputs** on the node.\n\n" + table("Input", advanced) if advanced else None,
             "## Outputs\n\n" + table("Output", schema.outputs),
             f"More in the [DiceForge guide]({REPOSITORY}#{slug}): examples, tips, and how it works with the other nodes."]
    return "\n\n".join(part for part in parts if part) + "\n"


def pages():
    found = {f"{schema.node_id}.md": schema_page(schema) for schema in SCHEMAS}
    found["DiceForgeWildcardNote.md"] = help_page(section(slug_of("Wildcard Note"))) # A frontend node (web/wildcard_note.js), with no schema.
    return found


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda schema: schema.node_id)
def test_every_node_has_a_description_and_tooltips(schema):
    assert schema.description
    assert [item.id for item in schema.inputs if not item.tooltip] == []
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
