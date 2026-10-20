"""Phase-only IFTA with explicit conventions and bounded CPU/memory use.

The basic GS projection order and normalization are adapted from slmsuite,
commit 5ac5a19ac356fe238a54db8a0a6be7114f085cf8 (MIT). Its advanced weighted,
feedback, GPU and MRAF features are intentionally not this paper's IFTA.
The license is included in third_party/slmsuite_LICENSE.txt.
"""

from dataclasses import dataclass
from pathlib import Path
import csv
import json
import time

import numpy as np
from PIL import Image
from scipy import fft


def fft2c(field):
    """Unitary centered DFT; odd and even sizes use the same invertible convention."""
    return fft.fftshift(fft.fft2(fft.ifftshift(field), norm="ortho", workers=1))


def ifft2c(field):
    return fft.fftshift(fft.ifft2(fft.ifftshift(field), norm="ortho", workers=1))


def psnr(reference, reconstructed, *, peak=1.0):
    """Fixed-peak intensity PSNR, with no data-dependent gain fitting or clipping."""
    a, b = np.asarray(reference, dtype=np.float64), np.asarray(reconstructed, dtype=np.float64)
    if a.shape != b.shape or not a.size or peak <= 0:
        raise ValueError("PSNR requires equal nonempty shapes and a positive peak")
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("PSNR inputs must be finite")
    error = np.mean((a - b) ** 2)
    return float("inf") if error == 0 else float(10 * np.log10(peak * peak / error))


def quantize_phase(phase, levels=256):
    if not isinstance(levels, int) or not 2 <= levels <= 256:
        raise ValueError("levels must be an integer between 2 and 256")
    phase = np.asarray(phase)
    if not np.all(np.isfinite(phase)):
        raise ValueError("phase must be finite")
    return np.mod(np.rint(np.mod(phase, 2 * np.pi) * levels / (2 * np.pi)), levels).astype(np.uint8)


def decode_phase(codes, levels=256):
    codes = np.asarray(codes)
    if not 2 <= levels <= 256 or np.any(codes < 0) or np.any(codes >= levels):
        raise ValueError("Invalid phase codes or levels")
    return codes.astype(np.float32) * np.float32(2 * np.pi / levels)


def reconstruct_fourier(phase, *, total_power=1.0):
    """Intensity from uniform-amplitude SLM phase, normalized by Parseval's theorem."""
    phase = np.asarray(phase, dtype=np.float32)
    if phase.ndim != 2 or not phase.size or total_power < 0 or not np.isfinite(total_power):
        raise ValueError("Expected a nonempty 2D phase and finite nonnegative power")
    field = np.exp(np.complex64(1j) * phase) / np.float32(np.sqrt(phase.size))
    return (np.abs(fft2c(field)) ** 2 * total_power).astype(np.float32)


def object_field(intensity, *, phase=None):
    """Eq. (2) inner sum via centered inverse DFT of sqrt(angular intensity)."""
    intensity = np.asarray(intensity, dtype=np.float32)
    if intensity.ndim != 2 or not np.all(np.isfinite(intensity)) or np.any(intensity < 0):
        raise ValueError("Expected finite nonnegative 2D angular intensity")
    angular = np.sqrt(intensity).astype(np.complex64)
    if phase is not None:
        if np.shape(phase) != intensity.shape:
            raise ValueError("Angular phase shape mismatch")
        angular *= np.exp(np.complex64(1j) * np.asarray(phase, dtype=np.float32))
    return ifft2c(angular)


@dataclass
class IFTAFrame:
    phase: np.ndarray
    intensity: np.ndarray
    psnr_db: float


@dataclass
class IFTAResult:
    phase: np.ndarray
    intensity: np.ndarray
    snapshots: dict[int, IFTAFrame]
    mse_history: list[float]


def ifta(intensity, *, iterations=100, checkpoints=(10, 30, 50, 100), seed=2020,
         initial_phase=None, phase_levels=None, track_history=True):
    """Basic GS under unit-amplitude nearfield and target farfield constraints.

    intensity is target power, not amplitude. Both transforms are unitary.
    Final intensity is energy-matched to the target sum (never least-squares fit).
    A zero target means an unexposed hogel: zero intensity and placeholder phase.
    phase_levels=None optimizes continuous phase; finite levels are optional.
    """
    target = np.asarray(intensity, dtype=np.float32)
    if target.ndim != 2 or not target.size or np.any(target < 0) or not np.all(np.isfinite(target)):
        raise ValueError("Target must be a finite nonnegative 2D intensity")
    if not isinstance(iterations, int) or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    if phase_levels is not None and (not isinstance(phase_levels, int) or not 2 <= phase_levels <= 256):
        raise ValueError("phase_levels must be None or an integer in [2,256]")
    checkpoints = set(checkpoints)
    if initial_phase is not None:
        phase = np.asarray(initial_phase, dtype=np.float32).copy()
        if phase.shape != target.shape or not np.all(np.isfinite(phase)):
            raise ValueError("Initial phase shape/values are invalid")
    else:
        phase = np.random.default_rng(seed).uniform(-np.pi, np.pi, target.shape).astype(np.float32)
    power = float(np.sum(target, dtype=np.float64))
    if power == 0:
        frame = IFTAFrame(np.zeros_like(target), np.zeros_like(target), float("inf"))
        return IFTAResult(frame.phase, frame.intensity, {n: frame for n in checkpoints if n <= iterations},
                          [0.] * iterations if track_history else [])
    amplitude = np.sqrt(target / power)
    source_amp = np.float32(1 / np.sqrt(target.size))
    snapshots = {}
    history = []
    # Project complex unit phasors directly. This is mathematically identical to
    # exp(1j*angle(...)), but avoids two costly angle/exponential pairs per step.
    field = source_amp * np.exp(np.complex64(1j) * phase)
    for iteration in range(1, iterations + 1):
        farfield = fft2c(field)
        magnitude = np.abs(farfield)
        unit = np.ones_like(farfield)
        np.divide(farfield, magnitude, out=unit, where=magnitude > 0)
        nearfield = ifft2c(amplitude * unit)
        magnitude = np.abs(nearfield)
        field = np.ones_like(nearfield)
        np.divide(nearfield, magnitude, out=field, where=magnitude > 0)
        field *= source_amp
        if phase_levels is not None:
            phase = np.angle(field)
            phase = decode_phase(quantize_phase(phase, phase_levels), phase_levels)
            field = source_amp * np.exp(np.complex64(1j) * phase)
        if track_history or iteration in checkpoints or iteration == iterations:
            reconstructed = (np.abs(fft2c(field)) ** 2 * power).astype(np.float32)
            if track_history:
                history.append(float(np.mean((reconstructed - target) ** 2, dtype=np.float64)))
            if iteration in checkpoints:
                snapshots[iteration] = IFTAFrame(np.angle(field), reconstructed, psnr(target, reconstructed))
    phase = np.angle(field)
    return IFTAResult(phase, reconstructed, snapshots, history)


def resize_intensity(image, shape):
    """Bilinear intensity interpolation for the conventional branch only."""
    image = np.asarray(image, dtype=np.float32)
    if image.ndim != 2 or len(shape) != 2 or any(v < 1 for v in shape):
        raise ValueError("Expected 2D intensity and positive output shape")
    return np.asarray(Image.fromarray(image).resize((shape[1], shape[0]), Image.Resampling.BILINEAR)).copy()


def encode_hogels(hogels, output, *, angular_shape=None, iterations=100, phase_levels=256,
                  seed=2020, pause_seconds=.001, progress=None, representative=None,
                  checkpoints=(10, 30, 50, 100), view_extraction=(1, 1)):
    """Encode every hogel sequentially, store actual printable phase and its reconstruction.

    Codes are integer phase bins. Optical amplitude is zero for inactive hogels;
    their zero phase placeholder must not be illuminated during printing.
    When angular_shape differs, only the conventional input is interpolated.
    """
    h = np.asanyarray(hogels)
    if h.ndim != 4:
        raise ValueError("Expected H[y,x,v,u]")
    shape = tuple(angular_shape or h.shape[-2:])
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    codes = np.lib.format.open_memmap(root / "phase_codes.npy", mode="w+", dtype=np.uint8,
                                     shape=(*h.shape[:2], *shape))
    recon = np.lib.format.open_memmap(root / "reconstruction.npy", mode="w+", dtype=np.float32, shape=codes.shape)
    active = np.zeros(h.shape[:2], dtype=bool)
    metrics = []
    bv, bu = view_extraction
    if shape[0] % bv or shape[1] % bu:
        raise ValueError("View extraction must divide encoded angular dimensions")
    checkpoints = tuple(n for n in checkpoints if 0 < n <= iterations)
    checkpoint_views = {n: np.zeros((h.shape[0] * bv, h.shape[1] * bu), np.float32) for n in checkpoints}
    origin_v, origin_u = (shape[0] // (2 * bv)) * bv, (shape[1] // (2 * bu)) * bu
    started = time.monotonic()
    for row in range(h.shape[0]):
        for column in range(h.shape[1]):
            target = np.asarray(h[row, column], dtype=np.float32)
            if target.shape != shape:
                target = resize_intensity(target, shape)
            active[row, column] = bool(np.any(target > 0))
            result = ifta(target, iterations=iterations, checkpoints=checkpoints, seed=seed + row * h.shape[1] + column,
                          track_history=False)
            bins = quantize_phase(result.phase, phase_levels)
            codes[row, column] = bins
            reconstructed = reconstruct_fourier(decode_phase(bins, phase_levels), total_power=float(target.sum(dtype=np.float64)))
            recon[row, column] = reconstructed
            score = psnr(target, reconstructed)
            metrics.append([row, column, int(active[row, column]), float(target.sum(dtype=np.float64)), score])
            for n, view in checkpoint_views.items():
                view[row * bv:(row + 1) * bv, column * bu:(column + 1) * bu] = result.snapshots[n].intensity[
                    origin_v:origin_v + bv, origin_u:origin_u + bu]
            if representative == (row, column):
                representative_result = ifta(target, iterations=iterations, checkpoints=checkpoints,
                                             seed=seed + row * h.shape[1] + column)
                frames = {f"phase_{n}": frame.phase for n, frame in representative_result.snapshots.items()}
                frames.update({f"intensity_{n}": frame.intensity for n, frame in representative_result.snapshots.items()})
                np.savez_compressed(root / "representative.npz", target=target, phase=representative_result.phase,
                                    history=representative_result.mse_history, **frames)
            if pause_seconds:
                time.sleep(pause_seconds)
        codes.flush()
        recon.flush()
        if progress:
            progress(row + 1, h.shape[0])
    np.save(root / "active.npy", active)
    for n, view in checkpoint_views.items():
        np.save(root / f"checkpoint_{n:04d}.npy", view)
    with (root / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row", "column", "active", "target_power", "psnr_db_fixed_peak_1"])
        writer.writerows(metrics)
    summary = {"complete": True, "shape": codes.shape, "input_shape": h.shape, "iterations": iterations,
               "phase_levels": phase_levels, "seed": seed, "active_hogels": int(active.sum()),
               "total_hogels": active.size, "elapsed_seconds": time.monotonic() - started,
               "reconstruction": "unitary Fourier propagation of saved quantized phase, target-power normalization",
               "interpolation": "none" if tuple(h.shape[-2:]) == shape else "bilinear intensity",
               "phase_codes": "phase_codes.npy", "intensity": "reconstruction.npy",
               "checkpoints": checkpoints, "view_extraction": view_extraction,
               "checkpoint_views": "inverse-mapped continuous-phase intensity at the central camera/block"}
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return root / "summary.json"
