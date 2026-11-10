"""Smoke test so CI is green from the scaffold commit onward."""
from pathlib import Path


def test_repo_layout():
    root = Path(__file__).resolve().parent.parent
    assert (root / "src" / "verba").is_dir()
    assert (root / "README.md").exists()
