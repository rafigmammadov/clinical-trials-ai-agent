"""Verify that the release archiver fails closed and excludes secrets."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.audit_archive import build_archive, inspect_archive


def make_minimal(root: Path):
    for name in ["app/main.py", "scripts/package_release.sh", "README.md", "requirements.txt",
                 "examples/a.json", "examples/b.json", "examples/c.json"]:
        path = root / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text("test data\n")


def test_packager_ignores_untracked_environment_and_git_history(tmp_path):
    make_minimal(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=secret-value")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "secret").write_text("SECRET")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "key").write_text("SECRET")
    archive = tmp_path / "dist" / "release.zip"
    build_archive(tmp_path, archive)
    with ZipFile(archive) as zipped:
        names = zipped.namelist()
    assert ".env" not in names
    assert not any(".git/" in name or ".venv/" in name for name in names)
    assert inspect_archive(archive)["example_json"] == 3


def test_packager_refuses_credential_in_readme(tmp_path):
    make_minimal(tmp_path)
    (tmp_path / "README.md").write_text("sk-proj-" + "A" * 50)
    with pytest.raises(ValueError, match="credential"):
        build_archive(tmp_path, tmp_path / "release.zip")


def test_packager_refuses_missing_examples(tmp_path):
    make_minimal(tmp_path)
    (tmp_path / "examples/c.json").unlink()
    with pytest.raises(ValueError, match="three real JSON"):
        build_archive(tmp_path, tmp_path / "release.zip")


def test_archive_audit_rejects_hidden_env_variant(tmp_path):
    from zipfile import ZIP_DEFLATED
    make_minimal(tmp_path)
    archive = tmp_path / "release.zip"
    build_archive(tmp_path, archive)
    with ZipFile(archive, "a", compression=ZIP_DEFLATED) as zipped:
        zipped.writestr("app/.env.production", "OPENAI_API_KEY=PRIVATE")
    with pytest.raises(ValueError, match="Private .env"):
        inspect_archive(archive)
