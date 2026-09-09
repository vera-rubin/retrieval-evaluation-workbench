"""CLI entry point; use the standalone isolated Python environment."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
# Only the explicitly staged dependency directory is added. Do not process
# .pth files, modify PATH, or change any shared interpreter installation.
from hippo_eval.bootstrap import bootstrap_artifact_site, select_artifact_root
artifact_root = select_artifact_root(sys.argv[1:], root / ".artifacts")
bootstrap_artifact_site(artifact_root)
from hippo_eval.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
