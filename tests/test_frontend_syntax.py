# Every JavaScript file of the frontend and the end-to-end tests parses: one typo stops the whole extension (or a whole spec) from loading,
# and the end-to-end tests would find it only after ten minutes. node --check reads a file without running it.
import glob
import os
import shutil
import subprocess
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = sorted(glob.glob(os.path.join(ROOT, "DiceForge", "web", "*.js")) + glob.glob(os.path.join(ROOT, "e2e", "*.js"))
               + glob.glob(os.path.join(ROOT, "e2e", "qa", "*.js")))


# Skipped only on a computer without node: on GitHub Actions (CI set) a missing node fails, so the check can't pass by doing nothing.
@pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("CI"), reason="node.js is not installed")
@pytest.mark.parametrize("path", FILES, ids=lambda path: os.path.relpath(path, ROOT).replace(os.sep, "/"))
def test_a_javascript_file_parses(path, tmp_path):
    # The frontend's files are ES modules, the end-to-end tests' CommonJS: the extension tells node which.
    module = os.path.join(ROOT, "DiceForge", "web") == os.path.dirname(path)
    copy = tmp_path / (os.path.basename(path) + (".mjs" if module else ".cjs"))
    shutil.copyfile(path, copy)
    result = subprocess.run(["node", "--check", str(copy)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_the_files_are_found():
    assert len([path for path in FILES if "web" in path]) > 20 and any(path.endswith(".spec.js") for path in FILES)
