"""Create and inspect a source-only archive using an explicit file allowlist.

A passing artifact audit means the archive lacks matching secret patterns and
unexpected files. It does NOT prove that no secret exists in Git history.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
INCLUDE_DIRS = ("app", "tests", "docs", "scripts", "evals", ".github", "examples")
INCLUDE_FILES = (
    "README.md", "SECURITY.md", "CHANGELOG.md",
    "Makefile", "requirements.txt", "pytest.ini", ".env.example", ".gitignore",
)
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "reports"}
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".txt", ".yml", ".yaml", ".sh", ".ini", ".example", ""}
SECRET_PATTERNS = (
    re.compile(rb"sk-proj-[A-Za-z0-9_-]{24,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{40,}"),
    re.compile(rb"ghp_[A-Za-z0-9]{30,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def select_files(root: Path) -> list[Path]:
    paths = [root / name for name in INCLUDE_FILES if (root / name).is_file()]
    for dirname in INCLUDE_DIRS:
        base = root / dirname
        if base.is_dir():
            paths.extend(p for p in base.rglob("*") if p.is_file())
    selected = []
    for path in sorted(set(paths)):
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS or part.startswith(".env") and part != ".env.example"
               for part in relative.parts):
            continue
        if path.is_symlink() or path.suffix not in ALLOWED_SUFFIXES:
            continue
        selected.append(relative)
    return selected


def check_content(name: str, content: bytes) -> None:
    if any(pattern.search(content) for pattern in SECRET_PATTERNS):
        raise ValueError(f"Possible credential found in {name}; aborting packaging")


def validate_names(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise ValueError("Duplicate archive entries")
    for name in names:
        parts = Path(name).parts
        if not name or name.startswith("/") or ".." in parts or any(p in SKIP_PARTS for p in parts):
            raise ValueError(f"Unsafe archive path: {name}")
        if any(part.startswith(".env") and part != ".env.example" for part in parts):
            raise ValueError("Private .env file included")
    required = {"README.md", "app/main.py", "requirements.txt", "scripts/package_release.sh"}
    if not required.issubset(names):
        raise ValueError(f"Missing release files: {sorted(required - set(names))}")
    examples = [name for name in names if name.startswith("examples/") and name.endswith(".json")]
    if len(examples) < 3:
        raise ValueError("Provide at least three real JSON examples before packaging")


def build_archive(root: Path, output: Path) -> None:
    selected = select_files(root)
    validate_names([str(p) for p in selected])
    contents = [(str(p), (root / p).read_bytes()) for p in selected]
    for name, data in contents:
        check_content(name, data)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=8) as archive:
        for name, data in contents:
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o644 << 16)
            archive.writestr(info, data)
    inspect_archive(output)


def inspect_archive(path: Path) -> dict[str, int]:
    with ZipFile(path) as archive:
        names = archive.namelist()
        validate_names(names)
        for name in names:
            check_content(name, archive.read(name))
        report = {
            "files": len(names),
            "example_json": sum(n.startswith("examples/") and n.endswith(".json") for n in names),
        }
        print(f"PASS {path}: {report['files']} files, {report['example_json']} JSON examples, no detected credential patterns")
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or inspect a source-only release ZIP")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--build", type=Path, metavar="OUTPUT_ZIP")
    action.add_argument("--inspect", type=Path, metavar="EXISTING_ZIP")
    args = parser.parse_args()
    if args.build:
        build_archive(ROOT, args.build)
    else:
        inspect_archive(args.inspect)


if __name__ == "__main__":
    main()
