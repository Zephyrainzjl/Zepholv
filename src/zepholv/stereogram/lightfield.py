"""Streaming perspective loading and lossless, explicitly indexed permutations."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def srgb_to_linear(image):
    image = np.asarray(image, dtype=np.float32)
    if not np.all(np.isfinite(image)) or np.any((image < 0) | (image > 1)):
        raise ValueError("sRGB values must be finite and within [0,1]")
    return np.where(image <= .04045, image / 12.92, ((image + .055) / 1.055) ** 2.4)


def linear_to_srgb(image):
    image = np.clip(np.asarray(image), 0, 1)
    return np.where(image <= .0031308, 12.92 * image, 1.055 * image ** (1 / 2.4) - .055)


def load_perspectives(manifest: str | Path, output: str | Path, *, verify_hashes=True):
    """Write float32 linear grayscale P[v,u,y,x] to a memory-mapped NPY file."""
    manifest = Path(manifest)
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if not metadata.get("complete"):
        raise ValueError("Acquisition is incomplete")
    grid = metadata["request"]["grid"]
    shape = (*grid["views"], *grid["resolution"])
    if len(metadata["images"]) != shape[0] * shape[1]:
        raise ValueError("Incorrect number of captured views")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    array = np.lib.format.open_memmap(output, mode="w+", dtype=np.float32, shape=shape)
    seen = set()
    for item in metadata["images"]:
        index = item["row"], item["column"]
        if index in seen or not (0 <= index[0] < shape[0] and 0 <= index[1] < shape[1]):
            raise ValueError("Duplicate or out-of-bounds camera index")
        seen.add(index)
        path = manifest.parent / item["file"]
        if verify_hashes and hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Captured image checksum mismatch: {path}")
        with Image.open(path) as image:
            if image.size != (shape[3], shape[2]):
                raise ValueError(f"Captured image resolution mismatch: {path}")
            rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255
        array[index] = srgb_to_linear(rgb) @ np.array([.2126, .7152, .0722], np.float32)
    array.flush()
    return array


def _destination(shape, dtype, output):
    if output is None:
        return np.empty(shape, dtype=dtype)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    return np.lib.format.open_memmap(path, mode="w+", dtype=dtype, shape=shape)


def rearrange_conventional(perspectives, *, output=None):
    """Eq. (3), exactly: H[y,x,v,u] = P[v,u,y,x]. No interpolation."""
    p = np.asanyarray(perspectives)
    if p.ndim != 4:
        raise ValueError("Expected P[v,u,y,x] grayscale array")
    v, u, y, x = p.shape
    h = _destination((y, x, v, u), p.dtype, output)
    for row in range(y):
        h[row] = p[:, :, row, :].transpose(2, 0, 1)
    if hasattr(h, "flush"):
        h.flush()
    return h


def rearrange_proposed(perspectives, extraction=(20, 20), *, output=None):
    """Explicit bijective completion of Eq. (4), with no pixel interpolation.

    H[i,j,bv*V+a,bu*U+b] = P[V,U,bv*i+a,bu*j+b].
    Every input sample occurs exactly once. This completion is not author code.
    """
    p = np.asanyarray(perspectives)
    if p.ndim != 4 or len(extraction) != 2:
        raise ValueError("Expected P[v,u,y,x] and a two-dimensional extraction factor")
    bv, bu = extraction
    if any(not isinstance(value, int) or value < 1 for value in extraction):
        raise ValueError("Extraction factors must be positive integers")
    v, u, y, x = p.shape
    if y % bv or x % bu:
        raise ValueError("Perspective dimensions must be divisible by extraction")
    hy, hx = y // bv, x // bu
    h = _destination((hy, hx, v * bv, u * bu), p.dtype, output)
    for row in range(hy):
        block = p[:, :, row * bv:(row + 1) * bv, :]
        h[row] = block.reshape(v, u, bv, hx, bu).transpose(3, 0, 2, 1, 4).reshape(hx, v * bv, u * bu)
    if hasattr(h, "flush"):
        h.flush()
    return h


def perspective_from_hogels(hogels, row: int, column: int, *, extraction=(1, 1)):
    """Inverse-map one original perspective, without materializing the whole LF."""
    h = np.asanyarray(hogels)
    if h.ndim != 4:
        raise ValueError("Expected H[y,x,v,u]")
    bv, bu = extraction
    hy, hx, av, au = h.shape
    if bv < 1 or bu < 1 or av % bv or au % bu:
        raise ValueError("Hogel angular dimensions must be divisible by extraction")
    if not (0 <= row < av // bv and 0 <= column < au // bu):
        raise IndexError((row, column))
    block = h[:, :, row * bv:(row + 1) * bv, column * bu:(column + 1) * bu]
    return block.transpose(0, 2, 1, 3).reshape(hy * bv, hx * bu)


def restore_perspectives(hogels, extraction=(1, 1), *, output=None):
    h = np.asanyarray(hogels)
    bv, bu = extraction
    if h.ndim != 4 or bv < 1 or bu < 1 or h.shape[2] % bv or h.shape[3] % bu:
        raise ValueError("Invalid hogel shape or extraction factor")
    hy, hx, av, au = h.shape
    p = _destination((av // bv, au // bu, hy * bv, hx * bu), h.dtype, output)
    for v in range(p.shape[0]):
        for u in range(p.shape[1]):
            p[v, u] = perspective_from_hogels(h, v, u, extraction=extraction)
    if hasattr(p, "flush"):
        p.flush()
    return p
