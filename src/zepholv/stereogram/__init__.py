"""Hogel synthesis APIs for DOI 10.3390/app10228088, with an explicit audit."""

from .config import PaperAmbiguityError, SynthesisConfig, paper_audit
from .lightfield import (
    load_perspectives, rearrange_conventional, rearrange_proposed,
    restore_perspectives, perspective_from_hogels,
)
from .ifta import (ifta, IFTAResult, fft2c, ifft2c, psnr, object_field, encode_hogels,
                   quantize_phase, decode_phase, reconstruct_fourier)
from .printing import (OpticalSetup, PrinterBackend, diffraction_limit, slm_frame,
                       export_print_job, execute_print_job)
from .reconstruction import angular_spectrum, pupil_reconstruction, refocus_lightfield
from .pipeline import run_reproduction
from .resources import low_impact
from .visualization import visualize_reproduction, index_reproductions

__all__ = ["PaperAmbiguityError", "SynthesisConfig", "paper_audit", "load_perspectives",
           "rearrange_conventional", "rearrange_proposed", "restore_perspectives",
           "perspective_from_hogels", "ifta", "IFTAResult", "fft2c", "ifft2c", "psnr",
           "object_field", "encode_hogels", "quantize_phase", "decode_phase", "reconstruct_fourier",
           "OpticalSetup", "PrinterBackend", "diffraction_limit", "slm_frame", "export_print_job",
           "execute_print_job", "angular_spectrum", "pupil_reconstruction", "refocus_lightfield",
           "run_reproduction", "low_impact", "visualize_reproduction", "index_reproductions"]
