"""Explicitly requested, attributed research assets; never downloaded on import."""

import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import urllib.request


def download_stanford_bunny(destination: str | Path) -> Path:
    """Download Stanford's bunny and extract only the named reconstruction.

    Source and use conditions: https://graphics.stanford.edu/data/3Dscanrep/
    The archive checksum and download URL are recorded next to the extracted PLY.
    No archive paths are used as filesystem destinations.
    """
    target = Path(destination).expanduser().resolve()
    sidecar = target.with_suffix(".source.json")
    if target.is_file() and sidecar.is_file():
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        if hashlib.sha256(target.read_bytes()).hexdigest() != metadata["mesh_sha256"]:
            raise ValueError("Cached bunny checksum mismatch")
        return target
    if target.exists():
        raise FileExistsError(f"Unverified asset already exists: {target}")
    url = "https://graphics.stanford.edu/pub/3Dscanrep/bunny.tar.gz"
    with tempfile.TemporaryDirectory(prefix="zepholv-bunny-") as temporary:
        archive = Path(temporary) / "bunny.tar.gz"
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
        with tarfile.open(archive, "r:gz") as bundle:
            member = bundle.getmember("bunny/reconstruction/bun_zipper.ply")
            if not member.isfile() or member.size > 50_000_000:
                raise ValueError("Unexpected Stanford archive member")
            data = bundle.extractfile(member).read()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        sidecar.write_text(json.dumps({
            "source": url,
            "attribution": "Stanford University Computer Graphics Laboratory, Stanford Bunny",
            "conditions": "https://graphics.stanford.edu/data/3Dscanrep/",
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "mesh_sha256": hashlib.sha256(data).hexdigest(),
        }, indent=2), encoding="utf-8")
    return target
