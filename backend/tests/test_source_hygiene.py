from pathlib import Path

import pytest

from companion.config import BACKEND_ROOT

ALLOWED_CONTROL = {"\n", "\r", "\t"}
SOURCES = sorted(
    path
    for folder in ("src", "tests", "migrations", "config")
    for path in (BACKEND_ROOT / folder).rglob("*")
    if path.suffix in {".py", ".md", ".mako"}
)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(BACKEND_ROOT)))
def test_source_files_contain_no_invisible_control_characters(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    hidden = sorted({repr(c) for c in text if ord(c) < 32 and c not in ALLOWED_CONTROL})

    assert hidden == []
