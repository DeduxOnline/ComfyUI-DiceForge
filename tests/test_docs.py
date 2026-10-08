# The README follows the code (the docs agent, .claude/agents/docs.md, keeps it so): every node is in the README's node table with a link to
# its section, and that section names each of its inputs and outputs as they are called (`name`). Every link inside the README leads to a
# heading that exists, every file or picture it shows is there, and every picture in docs/images is shown.
import asyncio
import os
import pathlib
import re
import pytest
import DiceForge

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
SCHEMAS = [node.define_schema() for node in asyncio.run(asyncio.run(DiceForge.comfy_entrypoint()).get_node_list())]
TABLE_ROW = re.compile(r"^\| \[\*\*([^*]+)\*\*\]\(#([^)]+)\)", re.M)


# A heading's anchor as GitHub makes it: lower case, without punctuation, spaces as hyphens.
def anchor(heading):
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


HEADINGS = [(match.start(), len(match.group(1)), anchor(match.group(2))) for match in re.finditer(r"^(#{1,6}) (.+)$", README, re.M)]


# The text of a section: from its heading to the next heading of the same or a higher level.
def section(name):
    for index, (start, level, slug) in enumerate(HEADINGS):
        if slug == name:
            return README[start:next((other for other, other_level, _ in HEADINGS[index + 1:] if other_level <= level), len(README))]
    return ""


def node_section(schema):
    return next((slug for names, slug in TABLE_ROW.findall(README) if schema.display_name in names), None)


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda schema: schema.node_id)
def test_every_node_is_in_the_table_with_its_section(schema):
    slug = node_section(schema)
    assert slug, f"{schema.display_name} is not in the README's node table"
    assert section(slug), f"{schema.display_name}: the table links to #{slug}, which is no heading"


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda schema: schema.node_id)
def test_its_section_names_every_input_and_output(schema):
    text = section(node_section(schema) or "")
    names = [item.id for item in schema.inputs] + [item.display_name or item.id for item in schema.outputs]
    assert [name for name in names if f"`{name}`" not in text] == []


def test_links_inside_the_readme_lead_to_headings():
    slugs = {slug for _, _, slug in HEADINGS}
    assert sorted({link for link in re.findall(r"\]\(#([^)]+)\)", README) if link not in slugs}) == []


def test_the_files_and_pictures_it_shows_are_there():
    shown = [match.group(1) or match.group(2) for match in re.finditer(r"\]\((?!https?:|#|mailto:)([^)\s]+)\)|<img src=\"(?!https?:)([^\"]+)\"", README)]
    assert [path for path in shown if not (ROOT / path.split("#")[0]).exists()] == []


def test_every_picture_in_docs_images_is_shown():
    used = set(re.findall(r"docs/images/([\w.-]+)", README))
    assert sorted(set(os.listdir(ROOT / "docs" / "images")) - used) == []
