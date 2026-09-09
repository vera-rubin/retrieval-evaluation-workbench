"""Generate the reviewable Zenodo description from authoritative CITATION.cff.

Original release tooling; SPDX-License-Identifier: Apache-2.0.
No account access, network calls, deposit, or publication is performed.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--cff", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = args.cff.resolve().parent
    artifacts = (args.artifacts or root / ".artifacts").resolve()
    site = artifacts / "site"
    if site.is_dir():
        sys.path.insert(0, str(site))
    try:
        import yaml
    except ImportError:
        print("METADATA_DEPENDENCY_MISSING: acquire the pinned PyYAML dependency first", file=sys.stderr)
        return 2
    try:
        if (root / ".zenodo.json").exists():
            raise ValueError(".zenodo.json would override the authoritative CITATION.cff")
        class UniqueKeysSafeLoader(yaml.SafeLoader):
            def construct_mapping(self, node, deep=False):
                mapping = {}
                for key_node, value_node in node.value:
                    key = self.construct_object(key_node, deep=deep)
                    if key in mapping:
                        raise ValueError("Duplicate YAML key: " + str(key))
                    mapping[key] = self.construct_object(value_node, deep=deep)
                return mapping
        citation = yaml.load(args.cff.read_text(encoding="utf-8-sig"), Loader=UniqueKeysSafeLoader)
        if not isinstance(citation, dict):
            raise ValueError("CITATION.cff must be a YAML mapping")
        description = citation.get("abstract")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("CITATION.cff must provide a nonempty abstract")
        content = "# Zenodo description\n\n" + description.strip() + "\n"
        if args.check:
            if not args.out.is_file() or args.out.read_bytes() != content.encode("utf-8"):
                print("METADATA_DESCRIPTION_MISMATCH", file=sys.stderr)
                return 1
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(content, encoding="utf-8", newline="\n")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print("METADATA_GENERATION_FAILED: " + str(exc), file=sys.stderr)
        return 2
    print("METADATA_DESCRIPTION_MATCHES" if args.check else "METADATA_DESCRIPTION_GENERATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
