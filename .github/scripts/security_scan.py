# Security checks of all of DiceForge's code. The unit tests run them (tests/test_security_scan.py), so CI fails on a break; the security agent
# (.claude/agents/security.md) starts from them. Only the Python standard library.
#   python .github/scripts/security_scan.py                what is never allowed (exits with 1 when found)
#   python .github/scripts/security_scan.py --inventory    and what to go through by hand: every HTTP route, every place that writes, moves or
#                                                          deletes files, every request to another site
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "DiceForge"

# Places that look like a break and are not, each with the reason (path, a piece of the line, why).
ALLOWED = [
    ("DiceForge/web/prompt_highlight.js", "layer.innerHTML = highlightPrompt(",
     "highlightPrompt builds the HTML from escapeHTML(text) pieces and its own class names (marksHTML)"),
    ("DiceForge/web/wildcards.js", "highlight.innerHTML = highlightWildcardFile(",
     "highlightWildcardFile builds the HTML with marksHTML, which escapes every piece of text"),
]

JS_RULES = [
    (re.compile(r"\.(innerHTML|outerHTML)\s*=(?!=)|insertAdjacentHTML\(|document\.write\("), "HTML from text: build elements with element() (dom.js)"),
    (re.compile(r"(?<![\w.])eval\(|new Function\("), "code from text"),
    (re.compile(r"window\.open\((?![^;]*noopener)"), "window.open without noopener: the opened page could reach this one"),
    (re.compile(r"""target:\s*["']_blank["'](?![^}]*rel:\s*["'][^"']*noopener)"""), "a link to a new tab without rel: noopener"),
]
FORBIDDEN_CALLS = {
    "eval": "eval of data", "exec": "exec of data", "pickle.load": "pickle runs code from the data", "pickle.loads": "pickle runs code from the data",
    "marshal.loads": "marshal of data", "os.system": "a shell command", "os.popen": "a shell command",
    "subprocess.run": "a process started", "subprocess.Popen": "a process started", "subprocess.call": "a process started",
    "subprocess.check_output": "a process started", "subprocess.check_call": "a process started",
    "ssl._create_unverified_context": "TLS without checking the certificate",
}
WRITES = {"os.remove", "os.unlink", "os.rename", "os.replace", "os.rmdir", "os.makedirs", "os.mkdir", "os.utime", "shutil.move", "shutil.rmtree",
          "shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree", "shutil.copyfileobj"}
WRITE_METHODS = {"write_text", "write_bytes", "unlink", "rmdir", "touch", "mkdir", "rename", "replace", "writestr"}
NETWORK = {"urllib.request.urlopen", "urlopen", "urllib.request.Request", "http_read.read", "read_up_to", "aiohttp.ClientSession"}


def finding(path, line, message):
    return {"path": path, "line": line, "message": message}


def allowed(path, text):
    return any(path == where and piece in text for where, piece, _ in ALLOWED)


def js_findings(path, text):
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("//") or allowed(path, line):
            continue
        found += [finding(path, number, message) for pattern, message in JS_RULES if pattern.search(line)]
    return found


# A call's name as written: "os.remove", "open", "self.path.unlink" (only names and attributes; anything else is "").
def call_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


# The yaml loaders that build only plain data: SafeLoader and the classes of the sources made from it.
def safe_loaders(trees):
    names = {"SafeLoader", "CSafeLoader", "yaml.SafeLoader", "yaml.CSafeLoader"}
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(call_name(base) in names for base in node.bases):
                names.add(node.name)
    return names


def python_findings(path, tree, loaders):
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        if name in FORBIDDEN_CALLS:
            found.append(finding(path, node.lineno, f"{name}: {FORBIDDEN_CALLS[name]}"))
        if name in ("yaml.load", "yaml.load_all") and call_name(keywords.get("Loader", ast.Constant(None))) not in loaders:
            found.append(finding(path, node.lineno, f"{name} without a safe Loader runs code from the file: yaml.safe_load"))
        if name.endswith(".extractall"):
            found.append(finding(path, node.lineno, "extractall writes where the archive's names say (../ included): check each name"))
        if isinstance(keywords.get("shell"), ast.Constant) and keywords["shell"].value is True:
            found.append(finding(path, node.lineno, "shell=True: a shell command"))
        if isinstance(keywords.get("verify"), ast.Constant) and keywords["verify"].value is False:
            found.append(finding(path, node.lineno, "verify=False: TLS without checking the certificate"))
    return found


# The function each line is in, for the inventory: {line: name}.
def enclosing(tree):
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                names[line] = node.name  # Inner functions come later in the walk and win.
    return names


def write_mode(node):
    mode = node.args[1] if len(node.args) > 1 else next((keyword.value for keyword in node.keywords if keyword.arg == "mode"), None)
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(flag in mode.value for flag in "wax+")


def inventory(path, text, tree):
    where = enclosing(tree)
    routes, writes, network = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and call_name(decorator.func) in ("routes.get", "routes.post", "routes.delete") and decorator.args:
                    route = decorator.args[0].value if isinstance(decorator.args[0], ast.Constant) else "?"
                    routes.append((path, node.lineno, call_name(decorator.func).split(".")[1].upper(), route, node.name))
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        code = (ast.get_source_segment(text, node) or name).replace("\n", " ")[:110]
        method = name.rsplit(".", 1)[-1]
        path_method = method in WRITE_METHODS and "." in name and not (method == "replace" and len(node.args) != 1)  # Not str.replace(a, b).
        if name in WRITES or path_method or (name == "open" and write_mode(node)) or (name.endswith("ZipFile") and write_mode(node)):
            writes.append((path, node.lineno, where.get(node.lineno, "(module)"), code))
        if name in NETWORK or method in ("urlopen", "read_up_to"):
            network.append((path, node.lineno, where.get(node.lineno, "(module)"), code))
    return routes, writes, network


def scan():
    sources = {f"DiceForge/{path.relative_to(SOURCE).as_posix()}": path.read_text(encoding="utf-8") for path in sorted(SOURCE.rglob("*.py")) if "__pycache__" not in path.parts}
    trees = {path: ast.parse(text, filename=path) for path, text in sources.items()}
    loaders = safe_loaders(trees.values())
    found = [item for path, tree in trees.items() for item in python_findings(path, tree, loaders)]
    for path in sorted((SOURCE / "web").glob("*.js")):
        relative = f"DiceForge/{path.relative_to(SOURCE).as_posix()}"
        found += js_findings(relative, path.read_text(encoding="utf-8"))
    routes, writes, network = [], [], []
    for path, tree in trees.items():
        found_routes, found_writes, found_network = inventory(path, sources[path], tree)
        routes += found_routes
        writes += found_writes
        network += found_network
    return found, {"routes": routes, "writes": sorted(writes), "network": sorted(network)}


def print_inventory(lists):
    print(f"\n## Routes ({len(lists['routes'])})")
    for path, line, method, route, handler in sorted(lists["routes"], key=lambda item: item[3]):
        print(f"- {method} {route}  ->  {handler}  ({path}:{line})")
    print(f"\n## Writing, moving or deleting files ({len(lists['writes'])})")
    for path, line, function, code in lists["writes"]:
        print(f"- {path}:{line} in {function}: {code}")
    print(f"\n## Requests to other sites, and reads with a size limit ({len(lists['network'])})")
    for path, line, function, code in lists["network"]:
        print(f"- {path}:{line} in {function}: {code}")
    print(f"\n## Allowed exceptions ({len(ALLOWED)})")
    for path, piece, why in ALLOWED:
        print(f"- {path}: {piece} -- {why}")


def main():
    found, lists = scan()
    for item in found:
        print(f"ERROR  {item['path']}:{item['line']}  {item['message']}")
    print(f"{len(found)} security problems.")
    if "--inventory" in sys.argv:
        print_inventory(lists)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
