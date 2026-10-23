# Checks of a change before it is pushed: what has made CI red or a review ask again in this project. The reviewer agent
# (.claude/agents/reviewer.md) runs it first; anyone can. Only the Python standard library.
#   python .github/scripts/review_checks.py [<base>]
# <base>: the commit to compare with (default HEAD: the uncommitted changes, new files included; origin/main for everything not pushed yet).
# Prints the findings, ERROR (CI would fail, or a rule of the project is broken) and WARN (worth a look); exits with 1 when there is an ERROR.
import ast
import configparser
import importlib.util
import pathlib
import re
import shutil
import subprocess
import sys

# The security scan's allowed exceptions, from its file (the portable build's Python doesn't import from the script's folder).
_spec = importlib.util.spec_from_file_location("security_scan", pathlib.Path(__file__).with_name("security_scan.py"))
security_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(security_scan)

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEXT = {".py", ".js", ".md", ".yml", ".yaml", ".toml", ".json", ".sh", ".txt", ".css", ".html", ".properties"}
ROUTE = re.compile(r'@routes\.(get|post|delete)\("([^"]+)"\)')
LISTED_ROUTE = re.compile(r'\("(GET|POST|DELETE)",\s*"([^"]+)"\)')

# Lines that are an ERROR or a WARN wherever they are added: (pattern, level, message) per file type.
PYTHON_RULES = [
    (re.compile(r"\byaml\.load\((?![^)]*Loader=(yaml\.)?(C?SafeLoader|TextLoader)\b)"), "ERROR",
     "yaml.load without a safe Loader runs code from the file: yaml.safe_load (security_scan.py knows the loaders made from SafeLoader)"),
    (re.compile(r"(?<![\w.])(eval|exec)\("), "ERROR", "eval / exec of data"),
    (re.compile(r"\bpickle\.loads?\("), "ERROR", "pickle runs code from the data"),
    (re.compile(r"shell\s*=\s*True|\bos\.system\("), "ERROR", "a shell command: subprocess with a list of arguments"),
    (re.compile(r"^\s*except\s*:"), "WARN", "a bare except also catches KeyboardInterrupt: name the exceptions"),
    (re.compile(r"#\s*(TODO|FIXME|XXX)\b"), "WARN", "a TODO left in"),
]
JS_RULES = [
    (re.compile(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML\(|document\.write\("), "ERROR",
     "HTML from text: build elements with element() (dom.js), text goes in as text"),
    (re.compile(r"//\s*(TODO|FIXME|XXX)\b"), "WARN", "a TODO left in"),
    (re.compile(r"""["']_blank["'](?![^)]*noopener)"""), "WARN", "a new tab without noopener: the opened page could reach this one"),
]
CONSOLE_LOG = re.compile(r"\bconsole\.log\(")
RANDOM = re.compile(r"\bimport random\b|\bfrom random import\b|\brandom\.(random|randint|randrange|choice|choices|shuffle|sample|uniform)\(")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout


# A file as it was at a commit, its bytes as they are (CRLF too), or None when it wasn't there.
def at_commit(base, path):
    result = subprocess.run(["git", "show", f"{base}:{path}"], cwd=ROOT, capture_output=True, check=False)
    return result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else None


def finding(level, path, line, message):
    return {"level": level, "path": path, "line": line, "message": message}


# The changed files (added, modified or renamed, new ones not in git yet included), relative to the repository.
def changed_files(base):
    names = set(git("diff", "--name-only", "--diff-filter=AMR", base).split()) | set(git("ls-files", "--others", "--exclude-standard").split())
    return sorted(name for name in names if (ROOT / name).is_file())


# A text's line endings: "crlf", "lf", "mixed", or "" without any.
def line_style(text):
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    if crlf and lf:
        return "mixed"
    return "crlf" if crlf else ("lf" if lf else "")


def line_endings(path, text, before):
    style = line_style(text)
    if style == "mixed":
        return [finding("ERROR", path, 0, "mixed line endings (CRLF and LF): keep the file's own")]
    old = line_style(before) if before else ""
    if old and style and old != style:
        return [finding("ERROR", path, 0, f"line endings changed from {old.upper()} to {style.upper()}: the whole file shows as changed")]
    return []


# A template literal inside another one's ${...} (Sonar S4624): what a line holds, read as code, strings and templates.
def nested_template(line):
    stack = []  # "`": in a template's text; "{": in its ${...} (with its own count of braces); a quote: in a string.
    depth = []
    index = 0
    while index < len(line):
        character = line[index]
        top = stack[-1] if stack else None
        if top in ("'", '"'):
            if character == "\\":
                index += 1
            elif character == top:
                stack.pop()
        elif top == "`":
            if character == "\\":
                index += 1
            elif character == "`":
                stack.pop()
            elif line.startswith("${", index):
                stack.append("{")
                depth.append(0)
                index += 1
        elif character == "`":
            if "{" in stack:
                return True
            stack.append("`")
        elif character in ("'", '"'):
            stack.append(character)
        elif top == "{" and character == "{":
            depth[-1] += 1
        elif top == "{" and character == "}":
            if depth[-1]:
                depth[-1] -= 1
            else:
                stack.pop()
                depth.pop()
        elif character == "/" and line.startswith("//", index):
            break
        index += 1
    return False


# The files where Sonar lets random stay (sonar-project.properties: the S2245 exceptions).
def random_allowed():
    properties = configparser.ConfigParser()
    text = (ROOT / "sonar-project.properties").read_text(encoding="utf-8") if (ROOT / "sonar-project.properties").is_file() else ""
    properties.read_string("[sonar]\n" + text)
    values = properties["sonar"]
    return {values.get(key.replace("rulekey", "resourcekey")) for key in values if key.endswith("rulekey") and values[key] == "python:S2245"}


# The rules of a file: DiceForge's own Python and frontend (tests and tools hold these patterns as data, and may run things).
def rules_of(path):
    if path.startswith("DiceForge/") and path.endswith(".py"):
        return PYTHON_RULES
    return JS_RULES if path.startswith("DiceForge/web/") and path.endswith(".js") else []


def added_line_findings(path, lines, allowed=frozenset()):
    rules = rules_of(path)
    found = []
    for number, line in lines:
        if security_scan.allowed(path, line): # An exception the security scan lists with its reason (a line moved to another file, say).
            continue
        found += [finding(level, path, number, message) for pattern, level, message in rules if pattern.search(line)]
        if path.startswith("DiceForge/web/") and CONSOLE_LOG.search(line):
            found.append(finding("WARN", path, number, "console.log left in the frontend (console.error / console.warn for what users should see)"))
        if path.endswith(".js") and nested_template(line):
            found.append(finding("WARN", path, number, "a template literal inside another one's ${...} (Sonar S4624): build the inner text first"))
        if path.endswith(".py") and path.startswith("DiceForge/") and path not in allowed and RANDOM.search(line):
            found.append(finding("WARN", path, number, "random here is flagged by Sonar (S2245): secrets, or an exception in sonar-project.properties"))
    return found


# The lines a change adds to a file: [(line number, text)]; every line of a file that is new.
def added_lines(base, path):
    if at_commit(base, path) is None:
        return list(enumerate((ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines(), 1))
    lines, number = [], 0
    for line in git("diff", "-U0", base, "--", path).splitlines():
        hunk = re.match(r"@@ -\S+ \+(\d+)", line)
        if hunk:
            number = int(hunk.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append((number, line[1:]))
            number += 1
    return lines


def syntax(path):
    file = ROOT / path
    if path.endswith(".py"):
        try:
            ast.parse(file.read_text(encoding="utf-8"), filename=path)
        except SyntaxError as error:
            return [finding("ERROR", path, error.lineno or 0, f"Python syntax: {error.msg}")]
        return []
    tools = {".js": ["node", "--check"], ".sh": ["bash", "-n"]}
    command = tools.get(file.suffix)
    if not command or not shutil.which(command[0]):
        return []
    result = subprocess.run([*command, str(file)], capture_output=True, text=True, check=False)
    message = (result.stderr or result.stdout).strip().splitlines()
    return [finding("ERROR", path, 0, f"syntax: {message[-1] if message else 'does not parse'}")] if result.returncode else []


# Every route the sources register is tried with junk by the robustness tests (tests/test_robustness.py ROUTES): one left out fails the tests.
def unlisted_routes(sources, robustness):
    listed = {(method, path.split("?")[0]) for method, path in LISTED_ROUTE.findall(robustness)}
    return [finding("ERROR", "tests/test_robustness.py", 0, f"{method.upper()} {path} ({name}) is not in ROUTES")
            for name, text in sorted(sources.items()) for method, path in ROUTE.findall(text) if (method.upper(), path) not in listed]


# What a change of the code usually comes with here: a CHANGELOG entry, the README, tests (unit for the Python, end to end for the frontend).
def companions(changed):
    code = [name for name in changed if name.startswith("DiceForge/")]
    if not code:
        return []
    found = []
    if "CHANGELOG.md" not in changed:
        found.append(finding("WARN", "CHANGELOG.md", 0, "the code changed, the CHANGELOG didn't (an entry under [Unreleased])"))
    if "README.md" not in changed:
        found.append(finding("WARN", "README.md", 0, "the code changed, the README didn't: does a node or window work differently now?"))
    if any(name.endswith(".py") for name in code) and not any(name.startswith("tests/") for name in changed):
        found.append(finding("WARN", "tests/", 0, "Python code changed without a unit test"))
    if any(name.startswith("DiceForge/web/") for name in code) and not any(re.match(r"e2e/.*\.spec\.js$", name) for name in changed):
        found.append(finding("WARN", "e2e/", 0, "frontend code changed without an end-to-end test (both designs)"))
    return found


def run(base="HEAD"):
    changed = changed_files(base)
    allowed = random_allowed()
    found = []
    for path in changed:
        if pathlib.PurePath(path).suffix not in TEXT:
            continue
        text = (ROOT / path).read_bytes().decode("utf-8", errors="replace")
        found += line_endings(path, text, at_commit(base, path) or "")
        found += syntax(path)
        found += added_line_findings(path, added_lines(base, path), allowed)
    sources = {path.name: path.read_text(encoding="utf-8") for path in (ROOT / "DiceForge").glob("*.py")}
    robustness = ROOT / "tests" / "test_robustness.py"
    if robustness.is_file():
        found += unlisted_routes(sources, robustness.read_text(encoding="utf-8"))
    return changed, found + companions(changed)


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    changed, found = run(base)
    print(f"{len(changed)} changed files against {base}.")
    for item in sorted(found, key=lambda item: (item["level"] != "ERROR", item["path"], item["line"])):
        where = f"{item['path']}:{item['line']}" if item["line"] else item["path"]
        print(f"{item['level']:5}  {where}  {item['message']}")
    errors = sum(item["level"] == "ERROR" for item in found)
    print(f"{errors} errors, {len(found) - errors} warnings.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
