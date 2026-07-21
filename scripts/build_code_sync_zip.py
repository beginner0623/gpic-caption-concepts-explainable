from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
import zipfile


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a code-sync zip with repository-relative archive paths.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("paths", nargs="+", type=Path)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo = Path.cwd()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in args.paths:
            source = repo / path
            if not source.is_file():
                raise SystemExit(f"missing file: {path}")
            arcname = path.as_posix()
            archive.write(source, arcname)
            entries.append(arcname)
    print(args.output)
    print("entries:")
    for entry in entries:
        print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
