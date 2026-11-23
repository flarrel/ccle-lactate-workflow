"""Download the exact assets listed in assets.json into a local runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def download(destination, asset):
    algorithm = asset.get("algorithm", "sha256")
    expected = asset["digest"]
    if destination.is_file():
        with destination.open("rb") as stream:
            if hashlib.file_digest(stream, algorithm).hexdigest() == expected:
                return
    partial = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.new(algorithm)
    count = 0
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "ccle-lactate-workflow/1"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > asset["max_bytes"]:
                    raise ValueError(f"{destination.name}: download exceeded its declared limit")
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"{destination.name}: {algorithm} checksum mismatch")
        partial.replace(destination)
        print(f"{destination.name}: {count:,} bytes", flush=True)
    finally:
        partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("assets", nargs="*")
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).resolve().parents[1] / "assets.json").read_text())
    args.runtime.mkdir(parents=True, exist_ok=True)
    for name in args.assets or manifest:
        download(args.runtime / name, manifest[name])


if __name__ == "__main__":
    main()
