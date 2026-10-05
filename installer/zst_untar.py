#!/usr/bin/env python3
"""zst_untar.py ARCHIVE DEST — unpack a .tar.zst into a prefix using the ``zstandard`` package.

Only ever run through ``uv run --no-project --with zstandard`` by ollama_setup (python <
3.14 has no zstd in the stdlib and a minimal host has no zstd binary).
"""
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import userspace  # noqa: E402
import zstandard  # noqa: E402

if __name__ == "__main__":
    archive, dest = sys.argv[1], Path(sys.argv[2])
    with open(archive, "rb") as fh:
        with zstandard.ZstdDecompressor().stream_reader(fh) as reader, \
                tarfile.open(fileobj=reader, mode="r|") as tf:
            userspace.extract_prefix(tf, dest, strip=0, skip_top_files=False)
