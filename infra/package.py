#!/usr/bin/env python3
"""Build a small Lambda archive without demos, browser files, or local state."""
from pathlib import Path
import zipfile


def package():
    root = Path(__file__).resolve().parents[1]
    output = root / "infra" / "collector.zip"
    files = sorted((root / "giftcard_tool").glob("*.py"))
    files.append(root / "config" / "retailers-live.json")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            entry = zipfile.ZipInfo(path.relative_to(root).as_posix(), (2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, path.read_bytes())
    print(f"Created {output.name}: {len(files)} files, {output.stat().st_size} bytes")


if __name__ == "__main__":
    package()
