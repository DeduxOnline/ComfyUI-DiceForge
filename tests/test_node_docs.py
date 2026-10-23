# Node help: DiceForge/web/docs/<node id>.md, which ComfyUI shows in its node help panel in place of a node's description. Each page is the
# node's section of the README, so the two never say different things: after a change to the README, write the pages again with
#   DICEFORGE_WRITE_NODE_DOCS=1 python -m pytest tests/test_node_docs.py
import os
import re
from test_docs import README, ROOT, SCHEMAS, TABLE_ROW, section

DOCS = ROOT / "DiceForge" / "web" / "docs"
REPOSITORY = "https://github.com/DeduxOnline/ComfyUI-DiceForge"
# Wildcard Note is a frontend node (web/wildcard_note.js), with no schema.
NODES = [(schema.node_id, schema.display_name) for schema in SCHEMAS] + [("DiceForgeWildcardNote", "Wildcard Note")]


def help_page(text):
    """A README section as a help page: its pictures next to the page (as Markdown, which the panel shows), its other links to GitHub."""
    text = re.sub(r'<img src="DiceForge/web/docs/(images/[^"]+)"[^>]*?\balt="([^"]*)"[^>]*>', r"![\2](\1)", text)
    text = text.replace("](DiceForge/web/docs/images/", "](images/")
    text = text.replace("](#", f"]({REPOSITORY}#")
    text = re.sub(r"\]\((?!https?:|mailto:|images/)([^)\s]+)\)", rf"]({REPOSITORY}/blob/main/\1)", text)
    return text.strip() + "\n"


def pages():
    return {f"{node_id}.md": help_page(section(next(slug for names, slug in TABLE_ROW.findall(README) if name in names))) for node_id, name in NODES}


def test_every_node_has_its_help_page_from_the_readme():
    expected = pages()
    if os.environ.get("DICEFORGE_WRITE_NODE_DOCS"):
        for old in DOCS.glob("*.md"):
            old.unlink()
        for name, text in expected.items():
            (DOCS / name).write_text(text, encoding="utf-8", newline="\n")
    found = {path.name: path.read_text(encoding="utf-8") for path in DOCS.glob("*.md")}
    assert sorted(found) == sorted(expected)
    assert [name for name in expected if found[name] != expected[name]] == [], \
        "the README changed: DICEFORGE_WRITE_NODE_DOCS=1 python -m pytest tests/test_node_docs.py"


def test_the_pictures_of_the_help_pages_are_there():
    shown = {picture for path in DOCS.glob("*.md") for picture in re.findall(r"\]\((images/[^)]+)\)", path.read_text(encoding="utf-8"))}
    assert shown and [picture for picture in shown if not (DOCS / picture).is_file()] == []
