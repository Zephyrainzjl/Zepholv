"""Re-centered off-axis light-field acquisition using installed Blender.

Grid traversal was studied against gfxdisp/Blender-addon-light-field-camera
(a1ae3f28). Camera shifts are an independent two-plane derivation, verified
inside Blender with bpy_extras.object_utils.world_to_camera_view.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import math

from .client import Blender

@dataclass(frozen=True)
class CameraGrid:
    """All array dimensions are (rows, columns), all world lengths are metres.

    Cameras lie in z=distance_m, look along -Z, and use lens shift to lock the
    image plane z=0. Images use top-left origins; world +Y points upward.
    fov_deg specifies total camera-array coverage, not a half-angle.
    """

    views: tuple[int, int] = (10, 10)
    resolution: tuple[int, int] = (1000, 1000)
    distance_m: float = 0.4
    fov_deg: float = 30.0
    image_fov_deg: float = 30.0

    def __post_init__(self):
        for shape in (self.views, self.resolution):
            if len(shape) != 2 or any(not isinstance(v, int) or v < 1 for v in shape):
                raise ValueError("views and resolution must contain two positive integers")
        if not math.isfinite(self.distance_m) or self.distance_m <= 0:
            raise ValueError("distance_m must be finite and positive")
        if not all(0 < angle < 120 for angle in (self.fov_deg, self.image_fov_deg)):
            raise ValueError("FOVs must be between 0 and 120 degrees")

    @property
    def plane_width_m(self):
        return 2 * self.distance_m * math.tan(math.radians(self.image_fov_deg) / 2)

    @property
    def plane_height_m(self):
        return self.plane_width_m * self.resolution[0] / self.resolution[1]

    def camera(self, row: int, column: int):
        """Return a single camera pose and lens shift, without launching Blender."""
        rows, cols = self.views
        if not (0 <= row < rows and 0 <= column < cols):
            raise IndexError((row, column))
        half = self.distance_m * math.tan(math.radians(self.fov_deg) / 2)
        x = half * (2 * column / (cols - 1) - 1) if cols > 1 else 0.0
        y = half * (1 - 2 * row / (rows - 1)) if rows > 1 else 0.0
        return {
            "row": row, "column": column,
            "location": [x, y, self.distance_m],
            "shift_x": -x / self.plane_width_m,
            # Horizontal sensor fit: both shifts are measured in frame widths.
            "shift_y": -y / self.plane_width_m,
        }


@dataclass(frozen=True)
class RenderSettings:
    """CPU rendering policy, explicitly distinct from the unspecified paper setup."""

    samples: int = 16
    threads: int = 2
    pause_seconds: float = 0.005
    seed: int = 2020
    preview_size: int = 512

    def __post_init__(self):
        if min(self.samples, self.threads, self.preview_size) < 1 or self.pause_seconds < 0:
            raise ValueError("samples/threads/preview_size must be positive; pause must be nonnegative")


def render_lightfield(
    blender: Blender,
    output: str | Path,
    *,
    grid: CameraGrid = CameraGrid(),
    scene: str = "teapot_sphere",
    bunny_mesh: str | Path | None = None,
    settings: RenderSettings = RenderSettings(),
    resume: bool = True,
) -> Path:
    """Render a complete array, preview, .blend, GLB and actual mesh geometry.

    Built-in scenes: teapot_sphere, bunny_carrot, depth_shapes. Original author
    scene files were not available; these are documented replacement scenes.
    Existing output can only be resumed when the complete request matches.
    Returns the completed manifest path. Blender runs once for the entire grid.
    """
    if scene not in {"teapot_sphere", "bunny_carrot", "depth_shapes"}:
        raise ValueError(f"Unknown scene: {scene}")
    destination = Path(output).expanduser().resolve()
    mesh = Path(bunny_mesh).expanduser().resolve() if bunny_mesh else None
    if scene == "bunny_carrot" and (mesh is None or not mesh.is_file()):
        raise FileNotFoundError("bunny_carrot requires bunny_mesh; use download_stanford_bunny()")
    script = Path(__file__).with_name("_lightfield_scene.py")
    request = {
        "grid": asdict(grid), "settings": asdict(settings), "scene": scene,
        "bunny_mesh": str(mesh) if mesh else None,
        "mesh_sha256": hashlib.sha256(mesh.read_bytes()).hexdigest() if mesh else None,
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "cameras": [grid.camera(r, c) for r in range(grid.views[0]) for c in range(grid.views[1])],
        "output": str(destination),
    }
    manifest = destination / "manifest.json"
    if manifest.exists():
        previous = json.loads(manifest.read_text(encoding="utf-8"))
        expected = json.loads(json.dumps(request))
        recorded = dict(previous["request"])
        # A bunny asset supplied for a multi-scene run does not affect other scenes.
        if scene != "bunny_carrot":
            for name in ("bunny_mesh", "mesh_sha256"):
                expected.pop(name, None)
                recorded.pop(name, None)
        if recorded != expected:
            raise ValueError("Existing acquisition uses a different request; choose a new output directory")
        if not resume:
            raise FileExistsError(destination)
        if previous.get("complete") and all((destination / item["file"]).is_file() for item in previous["images"]):
            return manifest
    elif destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Refusing to reuse a nonempty directory without manifest: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    job = blender.run_script(
        script, params=request, extra_args=["--threads", str(settings.threads)],
    )
    (destination / "blender.log").write_text(job.stdout + "\n" + job.stderr, encoding="utf-8")
    return manifest
