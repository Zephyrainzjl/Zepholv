"""Audited, resumable public workflow from Blender capture to printing data."""

from dataclasses import asdict
import gc
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from zepholv.blender import Blender, CameraGrid, RenderSettings, render_lightfield
from .config import SynthesisConfig, paper_audit
from .ifta import encode_hogels, psnr, resize_intensity
from .lightfield import load_perspectives, perspective_from_hogels, rearrange_conventional, rearrange_proposed
from .printing import OpticalSetup, diffraction_limit, export_print_job
from .reconstruction import angular_spectrum, pupil_reconstruction, refocus_lightfield
from .resources import low_impact


def _json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def _fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_reproduction(
    blender: Blender, output: str | Path, *, scene="teapot_sphere",
    config=SynthesisConfig(), settings=RenderSettings(), bunny_mesh=None,
    export_frames=True, visualize=True, progress=print, restart_incomplete=False,
) -> Path:
    """Run all numerical stages, save evidence and optionally all print frames.

    Returns summary.json. Never records a physical hologram. The audit is part
    of every output, and exact_reproduction remains False. Outputs are resumed
    only for identical configuration and numerical source fingerprint.
    """
    root = Path(output).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(b"".join(
        p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py"))
    )).hexdigest()
    request = json.loads(json.dumps({"scene": scene, "config": asdict(config),
                                    "settings": asdict(settings), "numerical_source_sha256": source_hash}))
    state_path = root / "run.json"
    if state_path.exists():
        previous = json.loads(state_path.read_text(encoding="utf-8"))
        if previous["request"] != request:
            old = {k: v for k, v in previous["request"].items() if k != "numerical_source_sha256"}
            new = {k: v for k, v in request.items() if k != "numerical_source_sha256"}
            if not (restart_incomplete and not previous.get("complete") and old == new):
                raise ValueError("Existing numerical run has different configuration/source; choose another output")
            # Explicit restart of an unfinished run: recompute all encodings.
            for method in ("proposed", "conventional"):
                marker = root / method / "encoding" / "summary.json"
                if marker.exists():
                    marker.unlink()
    _json(state_path, {"request": request, "complete": False, "audit": paper_audit()})
    started = time.monotonic()
    representative = None
    summaries = {}
    with low_impact(settings.threads):
        for method in ("proposed", "conventional"):
            branch = root / method
            branch.mkdir(exist_ok=True)
            grid = CameraGrid(
                views=config.proposed_views if method == "proposed" else config.conventional_views,
                resolution=config.proposed_resolution if method == "proposed" else config.hogels,
                distance_m=config.distance_m, fov_deg=config.camera_fov_deg,
            )
            progress(f"[{scene}/{method}] 1/6 Blender acquisition {grid.views} x {grid.resolution}")
            manifest = render_lightfield(blender, branch / "capture", grid=grid, scene=scene,
                                        bunny_mesh=bunny_mesh, settings=settings)
            progress(f"[{scene}/{method}] 2/6 Decode sRGB -> linear intensity")
            p = load_perspectives(manifest, branch / "perspectives.npy")
            progress(f"[{scene}/{method}] 3/6 Hogel permutation")
            if method == "proposed":
                h = rearrange_proposed(p, config.extraction, output=branch / "hogels.npy")
                # Pick the hogel with greatest angular variance, not a blank one.
                best = -1
                for row in range(h.shape[0]):
                    variances = np.var(h[row], axis=(-2, -1))
                    column = int(np.argmax(variances))
                    if variances[column] > best:
                        best, representative = float(variances[column]), (row, column)
            else:
                h = rearrange_conventional(p, output=branch / "hogels.npy")
            extraction = config.extraction if method == "proposed" else (1, 1)
            # Check every original camera against its inverse-mapped perspective.
            maximum_roundtrip_error = 0.
            for v in range(p.shape[0]):
                for u in range(p.shape[1]):
                    restored = perspective_from_hogels(h, v, u, extraction=extraction)
                    maximum_roundtrip_error = max(maximum_roundtrip_error, float(np.max(abs(restored - p[v, u]))))
            if maximum_roundtrip_error:
                raise AssertionError("Permutation is not lossless")
            target_view = np.array(p[0, 0])
            depths = [-.06, -.04, -.02, 0, .02, .04, .06]
            focus = np.stack([refocus_lightfield(p, grid, depth_m=z) for z in depths])
            np.savez_compressed(branch / "refocus.npz", intensity=focus, depths_m=depths)
            del p
            gc.collect()
            progress(f"[{scene}/{method}] 4/6 IFTA for every hogel, {max(config.iterations)} iterations")
            encoding = branch / "encoding"
            summary_file = encoding / "summary.json"
            if not summary_file.exists():
                summary_file = encode_hogels(
                    h, encoding, angular_shape=config.angular_shape,
                    iterations=max(config.iterations), phase_levels=config.phase_levels or 256,
                    seed=config.seed, representative=representative, checkpoints=config.iterations,
                    view_extraction=extraction,
                    progress=lambda done, total: progress(f"[{scene}/{method}] encoded hogel row {done}/{total}"),
                )
            encoded = json.loads(summary_file.read_text(encoding="utf-8"))
            reconstructed = np.load(encoding / "reconstruction.npy", mmap_mode="r")
            if method == "proposed":
                view = perspective_from_hogels(reconstructed, 0, 0, extraction=config.extraction)
            else:
                view = np.array(reconstructed[:, :, 0, 0])
            np.save(branch / "decoded_view.npy", view)
            native_score = psnr(target_view, view)
            progress(f"[{scene}/{method}] 5/6 Pupil and wave-propagation diagnostics")
            pupils = np.stack([pupil_reconstruction(
                reconstructed, eye_m=(x, y, config.distance_m),
                pupil_diameter_m=config.pupil_diameter_m, hogel_pitch_m=config.hologram_sampling_m,
                fov_deg=config.camera_fov_deg,
            ) for y in (.025, 0, -.025) for x in (-.025, 0, .025)])
            np.save(branch / "pupil_views.npy", pupils)
            codes = np.load(encoding / "phase_codes.npy", mmap_mode="r")
            phase = np.asarray(codes[representative], dtype=np.float32) * (2 * np.pi / encoded["phase_levels"])
            wave = np.exp(1j * phase)
            propagation_z = np.linspace(-.002, .002, 9)
            wave_stack = np.stack([abs(angular_spectrum(wave, wavelength_m=config.wavelength_m,
                                                       pixel_pitch_m=config.slm_pixel_pitch_m,
                                                       distance_m=float(z))) ** 2 for z in propagation_z])
            np.savez_compressed(branch / "single_hogel_wave.npz", intensity=wave_stack,
                                distances_m=propagation_z, label="near-SLM diagnostic; not a 3D scene reconstruction")
            del codes, reconstructed, h
            gc.collect()
            if export_frames:
                progress(f"[{scene}/{method}] 6/6 Export complete SLM frame sequence and dry-run plan")
                export_print_job(encoding, branch / "print", setup=OpticalSetup(
                    slm_shape=config.slm_shape, slm_pixel_pitch_m=config.slm_pixel_pitch_m,
                    wavelength_m=config.wavelength_m, hogel_pitch_m=config.printed_hogel_pitch_m,
                ))
            summaries[method] = {
                "capture": str(manifest.relative_to(root)), "encoding": str(summary_file.relative_to(root)),
                "roundtrip_max_error": maximum_roundtrip_error,
                "native_input_view_psnr_db": native_score if np.isfinite(native_score) else None,
                "representative_hogel": representative,
                "dimensions": {"views": grid.views, "perspective": grid.resolution,
                               "hogels": config.hogels, "native_angular": config.angular_shape if method == "proposed" else config.conventional_views},
                "encoding_seconds": encoded["elapsed_seconds"], "active_hogels": encoded["active_hogels"],
            }
        # Same camera position and same high-resolution reference in both branches.
        reference = np.load(root / "proposed" / "perspectives.npy", mmap_mode="r")
        common_target = np.array(reference[0, 0])
        for method in summaries:
            view = np.load(root / method / "decoded_view.npy")
            if view.shape != common_target.shape:
                view = resize_intensity(view, common_target.shape)
            score = psnr(common_target, view)
            summaries[method]["common_highres_view_psnr_db"] = score if np.isfinite(score) else None
        del reference
        from importlib.metadata import version
        versions = {name: version(name) for name in ("Zepholv", "numpy", "scipy", "pillow", "matplotlib", "plotly")}
        summary = {
            "complete": True, "scene": scene, "request": request, "audit": paper_audit(),
            "methods": summaries, "elapsed_seconds_this_invocation": time.monotonic() - started,
            "published_psnr_db_not_measured": {"conventional": [11.21, 23.95, 27.21, 31.43],
                                                "proposed": [12.67, 24.70, 28.71, 33.17]},
            "diffraction_check": {"conventional_0.32mm": diffraction_limit(config.wavelength_m, .00032),
                                  "proposed_1.28mm": diffraction_limit(config.wavelength_m, .00128)},
            "environment": {"python": platform.python_version(), "platform": platform.platform(), "packages": versions},
            "artifacts": {str(path.relative_to(root)): {"bytes": path.stat().st_size}
                          for path in root.rglob("*.npy")},
        }
        _json(root / "summary.json", summary)
        if visualize:
            from .visualization import visualize_reproduction
            progress(f"[{scene}] Generate all figures and interactive 3D report")
            visualize_reproduction(root)
        _json(state_path, {"request": request, "complete": True, "audit": paper_audit()})
    return root / "summary.json"
