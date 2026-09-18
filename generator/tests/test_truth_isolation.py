"""Spec section 5.5: no product surface and no agent may be able to name the truth.

The whole of the application (app/), the pipeline (pipeline/) and the Genie space
definition (genie/) — plus the documents that define the Genie space — must never
mention the truth table, its schema or its column."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("claim_fraud_truth", "ptm_eval", "is_fraud")
GUARDED_DIRS = ("app", "pipeline", "genie")
GUARDED_FILES = ("docs/genie-curation.md", "docs/specs/03-genie-knowledge.md")
EXCLUDED_DIR_NAMES = {"node_modules", ".venv", "dist", "build", "__pycache__", ".pytest_cache"}


def _scanned_paths() -> list[Path]:
    """Collect all regular files under guarded directories, excluding binary files and build artifacts."""
    paths = []

    # Add guarded files
    paths += [ROOT / f for f in GUARDED_FILES if (ROOT / f).exists()]

    # Add all files from guarded directories
    for directory in GUARDED_DIRS:
        dir_path = ROOT / directory
        if not dir_path.exists():
            continue
        for p in dir_path.rglob("*"):
            # Skip symlinks and paths with excluded directory names
            if p.is_symlink() or any(name in p.parts for name in EXCLUDED_DIR_NAMES):
                continue
            if not p.is_file():
                continue

            # Check if binary by reading first 8192 bytes
            try:
                with open(p, "rb") as f:
                    chunk = f.read(8192)
                    if b"\0" in chunk:
                        # Binary file, skip it
                        continue
            except (OSError, IOError):
                # Skip files we can't read
                continue

            paths.append(p)

    return paths


def _offenders():
    """Find all instances of forbidden terms in scanned paths."""
    for path in _scanned_paths():
        try:
            text = path.read_text(errors="ignore")
        except (OSError, IOError):
            # Skip files we can't read
            continue
        for term in FORBIDDEN:
            if term in text:
                yield f"{path.relative_to(ROOT)}: {term}"


def test_the_truth_is_never_named_where_the_product_or_genie_can_see_it():
    assert not list(_offenders())


def test_the_guard_actually_scans_the_product():
    """Verify the guard is not vacuous: it scans expected product files."""
    scanned = _scanned_paths()
    scanned_names = {p.relative_to(ROOT) for p in scanned}

    # Check that expected product files are scanned
    expected_files = {
        Path("app/app.yaml"),
        Path("app/requirements.txt"),
        Path("app/frontend/package.json"),
        Path("pipeline/pytest.ini"),
        Path("pipeline/transformations.py"),
        Path("genie/build_space.py"),
        Path("genie/instructions.md"),
    }
    for expected in expected_files:
        assert expected in scanned_names, f"Expected file not scanned: {expected}"

    # Check that at least one backend file is scanned
    backend_files = [p for p in scanned if "app/backend" in str(p)]
    assert backend_files, "No app/backend files scanned"

    # Verify no excluded directory names in scanned paths
    for path in scanned:
        for excluded in EXCLUDED_DIR_NAMES:
            assert excluded not in path.parts, f"Excluded dir in scanned path: {path}"
