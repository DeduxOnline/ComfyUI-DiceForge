# The text helpers of the Wildcard Browser and ✂ Selection → new wildcard (web/wildcards.js) replaced regular expressions that could backtrack
# on a long text (Sonar S8786). They must give what those expressions gave: every text made of the characters that matter here, up to a few
# characters long, and longer texts like real ones, through both the old expression and the new helper.
import itertools
import json
import shutil
import subprocess
import pytest
from test_frontend_functions import js_source

# The expressions the helpers replaced, as they were.
OLD = r"""
const old = {
  oneLine: (text) => text.replace(/\s*\n\s*/g, " ").trim(),
  withoutTrailingNewlines: (text) => text.replace(/\n+$/, ""),
  yamlOption: (line) => {
    const value = (/^\s*-\s+(.+)$/.exec(line) ?? /^\s*[^#:\s][^:]*:\s+(\S.*)$/.exec(line))?.[1].trim() ?? "";
    if (/^[[{]/.test(value)) return "";
    return /^(["']).*\1$/.test(value) ? value.slice(1, -1) : value;
  },
  suggestedName: (line) => line.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_+|_+$/g, "").split("_").slice(0, 3).join("_") || "new",
};
"""


# Every text of up to four of these characters (line breaks, spaces and tabs, the yaml marks, quotes, letters of two scripts), and texts like
# a prompt, a wildcard file and a yaml file.
ALPHABET = ["\n", " ", "\t", "-", ":", "#", "\"", "[", "_", "a", "é", "Я", "1"]
TEXTS = ["".join(chars) for size in range(5) for chars in itertools.product(ALPHABET, repeat=size)] + [
    "1girl, red dress,\n  smile \n\n", "  key: \"quoted: value\"  ", "- 2::hands on hips", "pose:\n  sitting: [a, b]\n", "Красное платье\n\tулыбка",
    "a" * 3000 + " " * 3000 + "\n" * 3000 + "b", "\n" * 5000, " \n" * 3000 + "x"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node.js is not installed")
@pytest.mark.parametrize("name", ["oneLine", "withoutTrailingNewlines", "yamlOption", "suggestedName"])
def test_the_helper_gives_what_the_old_expression_gave(name):
    texts = [text for text in TEXTS if "\n" not in text] if name == "yamlOption" else TEXTS # yamlOption gets one line of a file.
    script = js_source("wildcards.js", name) + OLD + f"\nconst texts = {json.dumps(texts)};" + \
        f"\nconsole.log(JSON.stringify(texts.map((text) => [text, {name}(text), old.{name}(text)]).filter(([, now, before]) => now !== before).slice(0, 10)));"
    # The script on standard input: as an argument, a list this long is over the size the system allows one.
    output = subprocess.run(["node", "-"], input=script, capture_output=True, text=True, check=True, encoding="utf-8").stdout
    assert json.loads(output) == []
