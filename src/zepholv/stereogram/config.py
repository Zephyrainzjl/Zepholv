"""Published parameters and explicit boundaries of the reconstruction."""

from dataclasses import asdict, dataclass
import math


class PaperAmbiguityError(ValueError):
    """A literal, fully specified reproduction cannot be inferred from the paper."""


@dataclass(frozen=True)
class SynthesisConfig:
    """Paper dimensions by default. Axis order is always (rows, columns).

    block_permutation is a documented bijective completion of Eq. (4), not
    author-verified source code. Set mapping='literal' to refuse this assumption.
    """

    hogels: tuple[int, int] = (50, 50)
    conventional_views: tuple[int, int] = (50, 50)
    proposed_views: tuple[int, int] = (10, 10)
    extraction: tuple[int, int] = (20, 20)
    mapping: str = "block_permutation"
    wavelength_m: float = 532e-9
    distance_m: float = .4
    depth_separation_m: float = .04
    camera_fov_deg: float = 30
    pupil_diameter_m: float = .002
    hologram_sampling_m: float = 129e-6
    printed_hogel_pitch_m: float = .001
    slm_pixel_pitch_m: float = 6.4e-6
    slm_shape: tuple[int, int] = (1080, 1920)
    iterations: tuple[int, ...] = (10, 30, 50, 100)
    phase_levels: int | None = None
    display_gray_levels: int = 8
    seed: int = 2020

    def __post_init__(self):
        for shape in (self.hogels, self.conventional_views, self.proposed_views, self.extraction, self.slm_shape):
            if len(shape) != 2 or any(not isinstance(v, int) or v < 1 for v in shape):
                raise ValueError("All shapes must contain two positive integers")
        if self.mapping not in {"block_permutation", "literal"}:
            raise ValueError("mapping must be 'block_permutation' or 'literal'")
        if self.mapping == "literal":
            raise PaperAmbiguityError(
                "Eq. (4) omits within-block indices and rounding; exact author mapping is unavailable. "
                "Use mapping='block_permutation' only with the documented assumption."
            )
        if not self.iterations or any(v < 1 or not isinstance(v, int) for v in self.iterations):
            raise ValueError("iterations must contain positive integers")
        if tuple(sorted(set(self.iterations))) != self.iterations:
            raise ValueError("iterations must be increasing without duplicates")
        if self.phase_levels is not None and not 2 <= self.phase_levels <= 256:
            raise ValueError("phase_levels must be None or between 2 and 256")
        for value in (self.wavelength_m, self.distance_m, self.pupil_diameter_m,
                      self.hologram_sampling_m, self.printed_hogel_pitch_m, self.slm_pixel_pitch_m):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Physical lengths must be finite and positive")

    @property
    def proposed_resolution(self):
        return tuple(a * b for a, b in zip(self.hogels, self.extraction))

    @property
    def angular_shape(self):
        return tuple(a * b for a, b in zip(self.proposed_views, self.extraction))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def validation(cls):
        """Small end-to-end numerical validation; explicitly not paper dimensions."""
        return cls(hogels=(12, 12), conventional_views=(12, 12),
                   proposed_views=(3, 3), extraction=(8, 8))


def paper_audit():
    """Machine-readable reproducibility findings; never assert equivalence."""
    return {
        "doi": "10.3390/app10228088",
        "exact_reproduction": False,
        "author_source_found": False,
        "known": {"conventional": "50x50 views at 50x50", "proposed": "10x10 views at 1000x1000",
                  "hogels": "50x50", "proposed_hogel": "200x200", "extraction": 20,
                  "wavelength_nm": 532, "distance_mm": 400, "pupil_mm": 2},
        "unresolved": [
            "Eq. (4) omits integer rounding and within-block indices; a bijective block permutation is an explicit completion.",
            "Eq. (5) uses delta-lambda without defining it; lambda/rho yields 0.0953 and 0.0238 degrees, unlike the printed values.",
            "Original Blender scenes, camera calibration, renderer settings, MATLAB IFTA and LabVIEW source were not found publicly.",
            "IFTA seed, amplitude normalization, interpolation kernel, PSNR reference and phase quantization are not specified.",
            "Eight-level grayscale is stated for reconstructed images, not explicitly for SLM phase: phase defaults to continuous.",
            "Numerical FOV is 30 degrees while the optical text also states +/-30 degrees; total 30 is used for numerical acquisition.",
            "The printed 1 mm hogel, 129 um numerical sampling and 25/85 relay magnification do not define one unique calibrated geometry.",
            "Optical recording and optical photographs require unavailable printer hardware and cannot be synthesized as experimental evidence.",
        ],
        "implemented_choices": {
            "mapping": "bijective camera-major block permutation, zero-based indices",
            "camera": "parallel-axis off-axis lens shifts, planar uniformly spaced camera array",
            "ifta": "CPU GS adapted from MIT-licensed slmsuite basic GS, fixed seed and unitary centered FFT",
            "interpolation": "bilinear intensity resizing, conventional method only",
            "intensity": "linear luminance decoded from sRGB PNG",
            "psnr": "measured against the exact target intensity; no fitting to published numbers",
            "view_refocus": "geometric light-field shift-and-sum, explicitly separate from optical reconstruction",
        },
    }
