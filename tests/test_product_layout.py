"""Release documentation must describe files which really exist."""
from pathlib import Path
import re
from app.version import __version__
from scripts.audit_archive import INCLUDE_FILES

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_independent_of_api_prefix():
    assert __version__ == "1.0.0"
    assert "/api/v1/analyze" in (ROOT / "docs/api.md").read_text()


def test_local_readme_document_links_exist():
    content = (ROOT / "README.md").read_text()
    for path in re.findall(r"\]\(([^)]+)\)", content):
        if path.startswith(("http:", "https:", "#")):
            continue
        if path.startswith("examples/"):
            # Actual clinical examples are generated on the user's machine.
            assert path.endswith(".json")
        else:
            assert (ROOT / path).is_file(), path


def test_release_does_not_include_redundant_tutorial_or_interview_files():
    assert "START_HERE.md" not in INCLUDE_FILES
    assert not (ROOT / "docs/INTERVIEW_DEFENSE.md").exists()
    assert not (ROOT / "docs/engineering_report.md").exists()
    docs = {x.name for x in (ROOT / "docs").glob("*.md")}
    assert docs == {"architecture.md", "api.md", "verification.md"}


def test_source_only_archive_maintains_test_corpus():
    required = {"cases.json", "identity_cases.json", "grounding_cases.json", "recall_cases.json"}
    actual = {f.name for f in (ROOT / "evals").glob("*.json")}
    assert actual == required
