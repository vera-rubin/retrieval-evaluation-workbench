"""Standard-library-only dependency bootstrap shared by entry point and CLI."""
from pathlib import Path
import sys


def artifact_root(value=None, default=None) -> Path:
    selected = value if value is not None else default
    if selected is None:
        raise ValueError("An artifact root or default is required")
    return Path(selected).expanduser().resolve()


def artifact_site(value=None, default=None) -> Path:
    return artifact_root(value, default) / "site"


def select_artifact_root(argv, default) -> Path:
    """Mirror exact argparse options before importing the dependency-using CLI."""
    selected = Path(default)
    values = list(argv)
    for index, value in enumerate(values):
        if value == "--":
            break
        if value == "--artifacts" and index + 1 < len(values):
            selected = Path(values[index + 1])
        elif value.startswith("--artifacts="):
            selected = Path(value.split("=", 1)[1])
    return selected.expanduser().resolve()


def bootstrap_artifact_site(value=None, default=None) -> Path:
    """Add only the selected staged site, without processing .pth files."""
    selected = artifact_site(value, default)
    if selected.is_dir():
        rendered = str(selected)
        if all(Path(entry).resolve() != selected for entry in sys.path if entry):
            sys.path.insert(1 if sys.path else 0, rendered)
    return selected
