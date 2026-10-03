"""The notes of a release: checks that the tag, pyproject.toml, DiceForge.__version__ and CHANGELOG.md agree on the version, and prints that
version's section of the changelog (the release's notes on GitHub). Used by .github/workflows/release.yml: python release_notes.py v1.2.0"""
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def versions(root=ROOT):
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    package = re.search(r'^__version__ = "([^"]+)"', (root / "DiceForge" / "__init__.py").read_text(encoding="utf-8"), re.MULTILINE)
    return project, package.group(1) if package else None


def changelog_section(version, root=ROOT):
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else None


def release_notes(tag, root=ROOT):
    version = tag.removeprefix("v")
    project, package = versions(root)
    problems = []
    if project != version:
        problems.append(f"pyproject.toml has {project}")
    if package != version:
        problems.append(f"DiceForge.__version__ is {package}")
    notes = changelog_section(version, root)
    if notes is None:
        problems.append(f"CHANGELOG.md has no section ## [{version}]")
    if problems:
        raise SystemExit(f"Release {tag}: " + "; ".join(problems) + f" (all must say {version}).")
    return notes


if __name__ == "__main__":
    print(release_notes(sys.argv[1]))
