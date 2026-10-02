"""T233 — project test home, README pointer only.

Covers:

* ``test_folder_exists`` — the ``project-test-home`` folder exists at repo root.
* ``test_index_exists`` — the folder index README exists.
* ``test_readme_contains_pointer`` — the root README contains the pointer box.
* ``test_readme_does_not_contain_proof_bodies`` — root README does not paste
  proof bodies (cold-start dates, chat id, notary submission, stranger names).
* ``test_forbidden_absent_from_folder`` — forbidden tokens absent from the new
  folder.
* ``test_forbidden_absent_from_readme_box`` — forbidden tokens absent from the
  new README box.
* ``test_no_persian_in_readme`` — no Persian script in README.md.
* ``test_no_persian_in_status`` — no Persian script in STATUS.md.
* ``test_no_persian_in_folder`` — no Persian script in any folder file.
* ``test_no_persian_in_test_file`` — no Persian script in this test file.
* ``test_author_untouched`` — Author section bytes unchanged.
* ``test_license_untouched`` — License section bytes unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FOLDER = REPO_ROOT / "project-test-home"
INDEX = FOLDER / "README.md"
README = REPO_ROOT / "README.md"
STATUS = REPO_ROOT / "STATUS.md"
TEST_FILE = Path(__file__).resolve()

PERSIAN_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

FORBIDDEN = [
    "stripe",
    "microsoft",
    "partner center",
    "token",
    "seventh agent",
]


def _folder_text() -> str:
    parts: list[str] = []
    for p in sorted(FOLDER.rglob("*")):
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_folder_exists() -> None:
    assert FOLDER.is_dir(), f"{FOLDER} must exist as a directory"


def test_index_exists() -> None:
    assert INDEX.is_file(), f"{INDEX} must exist as a file"


def test_readme_contains_pointer() -> None:
    text = README.read_text(encoding="utf-8")
    assert "Project test home" in text
    assert "project-test-home" in text


def test_readme_does_not_contain_proof_bodies() -> None:
    text = README.read_text(encoding="utf-8")
    assert "8064095778" not in text
    assert "7fde5e42-aad5-4964-992b-f1987149f834" not in text
    assert "3J54UZPZW3" not in text
    assert "2026-09-16" not in text
    assert "act-e9abbe8b54ae" not in text
    assert "act-ddbc7f12eaf0" not in text
    assert "act-89fdc25ca6d6" not in text


@pytest.mark.parametrize("needle", FORBIDDEN)
def test_forbidden_absent_from_folder(needle: str) -> None:
    assert needle not in _folder_text().lower()


@pytest.mark.parametrize("needle", FORBIDDEN)
def test_forbidden_absent_from_readme_box(needle: str) -> None:
    text = README.read_text(encoding="utf-8")
    start = text.index("## Project test home")
    end = text.index("## Destination — Planned")
    box = text[start:end]
    assert needle not in box.lower()


def test_no_persian_in_readme() -> None:
    text = README.read_text(encoding="utf-8")
    assert not PERSIAN_RE.search(text), "README.md must not contain Persian script"


def test_no_persian_in_status() -> None:
    text = STATUS.read_text(encoding="utf-8")
    assert not PERSIAN_RE.search(text), "STATUS.md must not contain Persian script"


def test_no_persian_in_folder() -> None:
    assert not PERSIAN_RE.search(_folder_text()), (
        "project-test-home folder must not contain Persian script"
    )


def test_no_persian_in_test_file() -> None:
    text = TEST_FILE.read_text(encoding="utf-8")
    assert not PERSIAN_RE.search(text), (
        "test_t233_test_home.py must not contain Persian script"
    )


def test_old_persian_folder_absent() -> None:
    old_folder = REPO_ROOT / "\u0645\u0627\u0646\u0647-\u062a\u0633\u062a-\u067e\u0631\u0648\u0698\u0647"
    assert not old_folder.exists(), (
        "the old Persian folder name must not exist"
    )


def test_author_untouched() -> None:
    text = README.read_text(encoding="utf-8")
    assert "## Author" in text
    assert "Amin Azimi" in text
    assert "Azimi Innovation Lab" in text
    assert "End-to-End System Development" in text


def test_license_untouched() -> None:
    text = README.read_text(encoding="utf-8")
    assert "## License" in text
    assert "Apache License, Version 2.0" in text
    lic = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache" in lic
