from __future__ import annotations

import pathlib
import tomllib


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PACKAGE_ROOT / "pyproject.toml"


def load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as handle:
        return tomllib.load(handle)


def test_release_metadata_is_pypi_ready() -> None:
    payload = load_pyproject()
    build_system = payload["build-system"]
    project = payload["project"]

    assert any(requirement.startswith("setuptools>=77") for requirement in build_system["requires"])
    assert project["name"] == "parse-mcp"
    assert project["readme"] == "README.md"
    assert project["requires-python"] == ">=3.10"
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert project["urls"] == {
        "Homepage": "https://github.com/ArdeleanLucas/PARSE",
        "Repository": "https://github.com/ArdeleanLucas/PARSE",
        "Issues": "https://github.com/ArdeleanLucas/PARSE/issues",
        "Documentation": "https://github.com/ArdeleanLucas/PARSE/tree/main/docs",
    }


def test_core_dependencies_stay_minimal() -> None:
    project = load_pyproject()["project"]
    dependencies = set(project["dependencies"])

    assert dependencies == {"pydantic>=2.7,<3"}
    assert "langchain-core>=0.2" not in dependencies
    assert "llama-index-core>=0.10" not in dependencies
    assert "crewai>=0.30" not in dependencies
