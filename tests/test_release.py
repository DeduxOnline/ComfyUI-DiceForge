# The release (.github/workflows/release.yml, .github/scripts/release_notes.py): the version in pyproject.toml, DiceForge.__version__ and
# CHANGELOG.md agree, the notes come from the changelog, and the repository folder is a ComfyUI custom node as the Registry installs it.
import ast
import importlib.util
import pathlib
import tomllib
import pytest
import DiceForge

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_notes", ROOT / ".github" / "scripts" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)


def test_the_version_is_the_same_everywhere():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    assert release_notes.versions() == (version, version) == (version, DiceForge.__version__)
    assert release_notes.changelog_section(version) # The changelog has its section.
    assert release_notes.release_notes(f"v{version}").startswith(release_notes.changelog_section(version)[:40])


def test_the_registry_has_what_it_needs():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["name"] == "comfyui-diceforge" and project["project"]["dependencies"] == []
    assert (ROOT / project["project"]["license"]["file"]).is_file() and project["tool"]["comfy"]["PublisherId"]
    assert project["project"]["urls"]["Repository"].startswith("https://github.com/")


def test_a_wrong_tag_stops_the_release():
    with pytest.raises(SystemExit, match="all must say 9.9.9"):
        release_notes.release_notes("v9.9.9")


def test_the_changelog_section_ends_at_the_next_one(tmp_path):
    (tmp_path / "DiceForge").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.1.0"\n', encoding="utf-8")
    (tmp_path / "DiceForge" / "__init__.py").write_text('__version__ = "1.1.0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## [1.1.0] - 2026-11-01\n\n### Added\n- New node.\n\n## [1.0.0] - 2026-10-03\n\n- First.\n\n"
                                           "[1.1.0]: https://example\n", encoding="utf-8")
    assert release_notes.release_notes("v1.1.0", tmp_path) == "### Added\n- New node."
    assert release_notes.changelog_section("1.0.0", tmp_path) == "- First."


def test_the_repository_folder_loads_the_pack():
    tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "DiceForge" for alias in node.names}
    assert imported <= set(dir(DiceForge)) and "comfy_entrypoint" in imported
    web = next(node.value.value for node in ast.walk(tree) if isinstance(node, ast.Assign) and node.targets[0].id == "WEB_DIRECTORY")
    assert (ROOT / web).is_dir() and any((ROOT / web).glob("*.js"))
