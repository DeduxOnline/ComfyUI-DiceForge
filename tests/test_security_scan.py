# The security checks of DiceForge's code (.github/scripts/security_scan.py, the start of the security agent): what is never allowed in the
# frontend and the Python, the exceptions with their reasons, and the inventory of routes, file changes and requests. DiceForge itself must pass.
import ast
import importlib.util
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("security_scan", ROOT / ".github" / "scripts" / "security_scan.py")
security_scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security_scan)


@pytest.mark.parametrize("line", [
    "panel.innerHTML = text;", "panel.outerHTML = text;", "panel.insertAdjacentHTML('beforeend', text);", "document.write(text);",
    "const value = eval(text);", "const run = new Function(text);", 'window.open(url, "_blank");',
    'element("a", { href: url, target: "_blank" }, "link")', 'element("a", { href: url, target: "_blank", rel: "nofollow" }, "link")',
])
def test_frontend_lines_that_are_never_allowed(line):
    assert len(security_scan.js_findings("DiceForge/web/x.js", line)) == 1


@pytest.mark.parametrize("line", [
    "panel.textContent = text;", "if (panel.innerHTML === '') return;", 'window.open(url, "_blank", "noopener");',
    'element("a", { href: url, target: "_blank", rel: "noopener" }, "link")', "// panel.innerHTML = text; an old way",
    "const values = retrieval(text);",
])
def test_frontend_lines_that_are_fine(line):
    assert security_scan.js_findings("DiceForge/web/x.js", line) == []


def test_an_exception_holds_only_where_it_was_given():
    path, piece, _ = security_scan.ALLOWED[0]
    line = f"  {piece}text, names);"
    assert security_scan.js_findings(path, line) == []
    assert len(security_scan.js_findings("DiceForge/web/other.js", line)) == 1


def test_every_exception_still_names_a_real_line():
    for path, piece, why in security_scan.ALLOWED:
        assert piece in (ROOT / path).read_text(encoding="utf-8"), f"a stale exception: {path} ({why})"


def python_problems(code):
    tree = ast.parse(code)
    return [item["message"].split(":")[0] for item in security_scan.python_findings("x.py", tree, security_scan.safe_loaders([tree]))]


def test_python_calls_that_are_never_allowed():
    code = """
value = eval(text)
data = pickle.loads(blob)
os.system(command)
subprocess.run(["ls"])
other(command, shell=True)
fetch(url, verify=False)
data = yaml.load(file)
archive.extractall(folder)
"""
    assert python_problems(code) == ["eval", "pickle.loads", "os.system", "subprocess.run", "shell=True", "verify=False",
                                     "yaml.load without a safe Loader runs code from the file", "extractall writes where the archive's names say (../ included)"]


def test_safe_yaml_loaders_are_fine_also_made_from_safeloader():
    code = """
class TextLoader(yaml.SafeLoader):
    pass
a = yaml.load(file, Loader=yaml.SafeLoader)
b = yaml.load(file, Loader=TextLoader)
c = yaml.safe_load(file)
d = yaml.load(file, Loader=yaml.FullLoader)
"""
    assert python_problems(code) == ["yaml.load without a safe Loader runs code from the file"]


def test_the_inventory_lists_routes_file_changes_and_requests():
    code = '''
@routes.post("/diceforge/thing")
async def save_thing(request):
    os.remove(path)
    target.replace(other)
    name = name.replace("a", "b")
    with open(path, "w") as file:
        pass
    with open(path) as file:
        pass
    async with aiohttp.ClientSession() as session:
        pass
'''
    routes, writes, network = security_scan.inventory("x.py", code, ast.parse(code))
    assert [(method, route, handler) for _, _, method, route, handler in routes] == [("POST", "/diceforge/thing", "save_thing")]
    assert [code for _, _, function, code in writes if function == "save_thing"] == ['os.remove(path)', 'target.replace(other)', 'open(path, "w")']
    assert [code for *_, code in network] == ["aiohttp.ClientSession()"]


def test_diceforge_passes():
    found, lists = security_scan.scan()
    assert found == []
    assert len(lists["routes"]) > 30 and lists["writes"] and lists["network"]
