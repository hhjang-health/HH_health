#!/usr/bin/env python3
"""Create Android private.tar using python-for-android's archive contract."""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import subprocess
import tarfile
from pathlib import Path


def clean(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument("--numeric-version", required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    (source / "p4a_env_vars.txt").write_text(
        "P4A_IS_WINDOWED=False\n"
        "KIVY_ORIENTATION=Portrait\n"
        f"P4A_NUMERIC_VERSION={args.numeric_version}\n"
        "P4A_MINSDK=26\n",
        encoding="utf-8",
    )

    for py in sorted(source.rglob("*.py")):
        subprocess.run([args.python, "-OO", "-m", "compileall", "-b", "-f", str(py)], check=True)
        py.unlink()

    files = sorted(
        path for path in source.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(args.output, "wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            written_dirs: set[str] = set()
            for path in files:
                name = path.relative_to(source).as_posix()
                parent = Path(name).parent
                current = Path()
                for part in parent.parts:
                    current /= part
                    directory = current.as_posix()
                    if directory in written_dirs:
                        continue
                    info = tarfile.TarInfo(directory)
                    info.type = tarfile.DIRTYPE
                    archive.addfile(clean(info))
                    written_dirs.add(directory)
                archive.add(str(path), arcname=name, filter=clean)


if __name__ == "__main__":
    main()
