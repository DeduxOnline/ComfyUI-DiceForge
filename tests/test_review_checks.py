# The checks of a change before it is pushed (.github/scripts/review_checks.py, run by the reviewer agent): line endings, Sonar's nested
# template literals, the lines that are always wrong or worth a look, routes left out of the robustness tests, and what a change of the code
# usually comes with.
import importlib.util
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_checks", ROOT / ".github" / "scripts" / "review_checks.py")
review_checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review_checks)


def levels(found):
    return [(item["level"], item["path"], item["line"]) for item in found]


@pytest.mark.parametrize("text, style", [("a\r\nb\r\n", "crlf"), ("a\nb\n", "lf"), ("a\r\nb\n", "mixed"), ("one line", ""), ("", "")])
def test_line_style(text, style):
    assert review_checks.line_style(text) == style


def test_line_endings_must_stay_the_files_own():
    assert levels(review_checks.line_endings("a.js", "x\r\ny\n", "")) == [("ERROR", "a.js", 0)]  # Mixed.
    assert "CRLF to LF" in review_checks.line_endings("a.js", "x\ny\n", "x\r\ny\r\n")[0]["message"]
    assert review_checks.line_endings("a.js", "x\r\nz\r\n", "x\r\ny\r\n") == []
    assert review_checks.line_endings("new.js", "x\ny\n", "") == []  # A new file has no style to keep yet.


@pytest.mark.parametrize("line", [
    "const a = `x ${b ? `y` : z}`;",
    "f(`${`inner`}`)",
    "const a = `x ${list.map((item) => `<${item}>`).join('')}`;",
    "const a = `x ${ { key: `y` }.key }`;",
])
def test_nested_template_literals_are_found(line):
    assert review_checks.nested_template(line)


@pytest.mark.parametrize("line", [
    "const a = `x ${b}` + `y ${c}`;",
    "const a = `x ${f(\"`\")}`;",  # A backtick in a string inside ${...}.
    "const a = '`' + `x`;",
    "// `x ${`y`}` in a comment",
    "const a = `x \\${`;",  # Not a ${...}: escaped.
    "const a = `x ${ {key: 1}.key }`;",
    "const css = `.a{color:red}`;",
])
def test_other_template_literals_are_not(line):
    assert not review_checks.nested_template(line)


def test_lines_that_are_errors_or_worth_a_look():
    python = review_checks.added_line_findings("DiceForge/x.py", [
        (1, "data = yaml.load(text)"), (2, "data = yaml.load(text, Loader=yaml.SafeLoader)"), (3, "value = eval(text)"),
        (4, "subprocess.run(command, shell=True)"), (5, "except:"), (6, "# TODO: later"), (7, "import random"), (8, "pattern = r'TODO'"),
    ])
    assert levels(python) == [("ERROR", "DiceForge/x.py", 1), ("ERROR", "DiceForge/x.py", 3), ("ERROR", "DiceForge/x.py", 4),
                              ("WARN", "DiceForge/x.py", 5), ("WARN", "DiceForge/x.py", 6), ("WARN", "DiceForge/x.py", 7)]
    script = review_checks.added_line_findings("DiceForge/web/x.js", [
        (1, "panel.innerHTML = text;"), (2, "console.log(value);"), (3, 'window.open(url, "_blank");'), (4, 'window.open(url, "_blank", "noopener");'),
        (5, "panel.textContent = text;"),
    ])
    assert levels(script) == [("ERROR", "DiceForge/web/x.js", 1), ("WARN", "DiceForge/web/x.js", 2), ("WARN", "DiceForge/web/x.js", 3)]
    assert review_checks.added_line_findings("e2e/qa/x.js", [(1, "console.log(report);")]) == []  # A tool prints.
    assert review_checks.added_line_findings("tests/test_x.py", [(1, 'code = "value = eval(text)"')]) == []  # A test holds them as data.
    assert levels(review_checks.added_line_findings("e2e/x.spec.js", [(1, "const a = `x ${`y`}`;")])) == [("WARN", "e2e/x.spec.js", 1)]


def test_random_is_fine_where_sonar_lets_it_be():
    allowed = review_checks.random_allowed()
    assert "DiceForge/seed_modes.py" in allowed
    assert review_checks.added_line_findings("DiceForge/seed_modes.py", [(1, "import random")], allowed) == []
    assert levels(review_checks.added_line_findings("DiceForge/other.py", [(1, "random.choice(items)")], allowed)) == [("WARN", "DiceForge/other.py", 1)]


def test_a_route_left_out_of_the_robustness_tests_is_an_error():
    sources = {"a.py": '@routes.get("/diceforge/one")\n@routes.post("/diceforge/two")\n'}
    listed = 'ROUTES = [("GET", "/diceforge/one?x=1")]'
    found = review_checks.unlisted_routes(sources, listed)
    assert [item["message"] for item in found] == ["POST /diceforge/two (a.py) is not in ROUTES"]
    assert review_checks.unlisted_routes(sources, listed + ' + [("POST", "/diceforge/two")]') == []


def test_every_route_of_diceforge_is_listed_now():
    sources = {path.name: path.read_text(encoding="utf-8") for path in (ROOT / "DiceForge").glob("*.py")}
    assert review_checks.unlisted_routes(sources, (ROOT / "tests" / "test_robustness.py").read_text(encoding="utf-8")) == []


def test_what_a_change_of_the_code_comes_with():
    alone = [item["path"] for item in review_checks.companions(["DiceForge/x.py", "DiceForge/web/y.js"])]
    assert alone == ["CHANGELOG.md", "README.md", "tests/", "e2e/"]
    complete = ["DiceForge/x.py", "DiceForge/web/y.js", "CHANGELOG.md", "README.md", "tests/test_x.py", "e2e/ui-nodes.spec.js"]
    assert review_checks.companions(complete) == []
    assert review_checks.companions(["README.md", "tests/test_x.py"]) == []  # No code changed.


def test_the_checks_run_on_this_repository():
    changed, found = review_checks.run("HEAD")
    assert isinstance(changed, list) and all(item["level"] in ("ERROR", "WARN") for item in found)
