"""SLM frame export, calibrated driver boundary and dry-run recording plans."""

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time
from typing import Protocol

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class OpticalSetup:
    wavelength_m: float = 532e-9
    slm_shape: tuple[int, int] = (1080, 1920)
    slm_pixel_pitch_m: float = 6.4e-6
    lens_f1_m: float = .085
    lens_f2_m: float = .025
    reference_angle_deg: float = 45
    exposure_seconds: float = .2
    signal_reference_ratio: float = 1
    material: str = "Ultimate U08M silver halide"
    hogel_pitch_m: float = .001
    settling_seconds: float | None = None

    def __post_init__(self):
        if len(self.slm_shape) != 2 or min(self.slm_shape) < 1:
            raise ValueError("Invalid SLM shape")
        if min(self.wavelength_m, self.slm_pixel_pitch_m, self.lens_f1_m, self.lens_f2_m,
               self.exposure_seconds, self.hogel_pitch_m, self.signal_reference_ratio) <= 0:
            raise ValueError("Optical lengths, exposure, ratio and pitch must be positive")

    @property
    def relay_magnification(self):
        return self.lens_f2_m / self.lens_f1_m


def diffraction_limit(wavelength_m=532e-9, aperture_m=.00128):
    """Rayleigh-order lambda/rho, radians and degrees; distinct from printed Eq. (5)."""
    if wavelength_m <= 0 or aperture_m <= 0:
        raise ValueError("Wavelength and aperture must be positive")
    radians = wavelength_m / aperture_m
    return {"radians": radians, "degrees": math.degrees(radians)}


def slm_frame(phase_codes, *, phase_levels=256, shape=(1080, 1920), lut=None):
    """Center native hogel codes without resizing; return an 8-bit display frame.

    A supplied LUT maps integer phase bins to calibrated grayscale. Default is
    ideal linear 0..2pi; this is NOT an actual device calibration. The background
    must be physically apertured: zero phase outside is not zero light.
    """
    phase = np.asarray(phase_codes)
    if phase.ndim != 2 or any(a > b for a, b in zip(phase.shape, shape)):
        raise ValueError("Phase map must be 2D and fit inside the SLM frame")
    if not 2 <= phase_levels <= 256 or np.any(phase < 0) or np.any(phase >= phase_levels):
        raise ValueError("Invalid phase codes or levels")
    if lut is None:
        lookup = np.rint(np.arange(phase_levels) * 256 / phase_levels).astype(np.uint8)
    else:
        lookup = np.asarray(lut)
        if lookup.shape != (phase_levels,) or np.any(lookup < 0) or np.any(lookup > 255):
            raise ValueError("LUT must contain one 8-bit value per phase bin")
        lookup = lookup.astype(np.uint8)
    frame = np.zeros(shape, dtype=np.uint8)
    y, x = ((a - b) // 2 for a, b in zip(shape, phase.shape))
    frame[y:y + phase.shape[0], x:x + phase.shape[1]] = lookup[phase.astype(int)]
    return frame


def export_print_job(encoding, output, *, setup=OpticalSetup(), scan="serpentine", lut=None,
                     calibration_id=None):
    """Export all SLM frames and X/Y/shutter instructions without controlling hardware."""
    if scan not in {"serpentine", "raster"}:
        raise ValueError("scan must be serpentine or raster")
    root = Path(encoding)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    if not summary.get("complete"):
        raise ValueError("Encoding is incomplete")
    phase = np.load(root / summary["phase_codes"], mmap_mode="r")
    active = np.load(root / "active.npy")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frames = output / "frames"
    frames.mkdir(exist_ok=True)
    rows, cols = phase.shape[:2]
    records = []
    for row in range(rows):
        columns = range(cols - 1, -1, -1) if scan == "serpentine" and row % 2 else range(cols)
        for column in columns:
            filename = f"frames/h{row:03d}_{column:03d}.png"
            frame = slm_frame(phase[row, column], phase_levels=summary["phase_levels"], shape=setup.slm_shape, lut=lut)
            Image.fromarray(frame).save(output / filename)
            records.append({"sequence": len(records), "row": row, "column": column,
                            "x_m": column * setup.hogel_pitch_m, "y_m": row * setup.hogel_pitch_m,
                            "frame": filename, "expose": bool(active[row, column]),
                            "exposure_seconds": setup.exposure_seconds if active[row, column] else 0})
    manifest = {"mode": "data_export_only", "optical_experiment_performed": False,
                "calibration_id": calibration_id, "lut": "supplied" if lut is not None else "uncalibrated ideal linear",
                "setup": asdict(setup), "scan": scan, "scan_source": "implementation choice; not specified by 2020 paper",
                "active_shape": phase.shape[-2:], "physical_aperture_required": True,
                "recording_time_from_paper_seconds": 3000,
                "known_exposure_time_seconds": sum(item["exposure_seconds"] for item in records),
                "settling_time": "not specified in paper; must be calibrated", "records": records}
    path = output / "print_job.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


class PrinterBackend(Protocol):
    """Implement this protocol for actual calibrated SLM/stage/shutter hardware."""

    def move_to(self, x_m: float, y_m: float) -> None: ...
    def show_frame(self, path: Path) -> None: ...
    def wait_until_settled(self) -> None: ...
    def open_shutter(self) -> None: ...
    def close_shutter(self) -> None: ...


def execute_print_job(manifest, backend: PrinterBackend, *, sleep=time.sleep):
    """Run a supplied hardware driver only after a calibration ID is recorded.

    No vendor driver or paper LabVIEW implementation was published/found. No
    hardware is connected automatically and software tests use a fake backend.
    """
    path = Path(manifest)
    job = json.loads(path.read_text(encoding="utf-8"))
    if not job.get("calibration_id") or job["lut"] != "supplied":
        raise ValueError("Actual recording requires an explicitly calibrated device LUT and calibration_id")
    backend.close_shutter()
    try:
        for record in job["records"]:
            backend.move_to(record["x_m"], record["y_m"])
            backend.show_frame(path.parent / record["frame"])
            backend.wait_until_settled()
            if record["expose"]:
                try:
                    backend.open_shutter()
                    sleep(record["exposure_seconds"])
                finally:
                    backend.close_shutter()
    finally:
        backend.close_shutter()
    return {"records_processed": len(job["records"])}
