"""Explicitly separated Fourier, free-space and geometric LF reconstructions."""

import math

import numpy as np
from scipy import fft, ndimage

from .ifta import resize_intensity


def angular_spectrum(field, *, wavelength_m=532e-9, pixel_pitch_m=6.4e-6,
                     distance_m=.4, padding=2, bandlimit=True):
    """Band-limited angular-spectrum free-space propagation of one complex field.

    This is a diagnostic wave propagator, not a replacement for the paper's
    uncalibrated relay, recording material, or full incoherent stereogram.
    """
    field = np.asarray(field, dtype=np.complex64)
    if field.ndim != 2 or not np.all(np.isfinite(field)):
        raise ValueError("field must be a finite 2D complex array")
    if wavelength_m <= 0 or pixel_pitch_m <= 0 or not np.isfinite(distance_m):
        raise ValueError("Invalid propagation parameters")
    if not isinstance(padding, int) or padding < 1:
        raise ValueError("padding must be a positive integer")
    height, width = field.shape
    shape = height * padding, width * padding
    y0, x0 = (shape[0] - height) // 2, (shape[1] - width) // 2
    padded = np.zeros(shape, dtype=np.complex64)
    padded[y0:y0 + height, x0:x0 + width] = field
    fy = fft.fftfreq(shape[0], pixel_pitch_m)[:, None]
    fx = fft.fftfreq(shape[1], pixel_pitch_m)[None, :]
    square = 1 / wavelength_m ** 2 - fx ** 2 - fy ** 2
    allowed = square >= 0
    if bandlimit:
        limit_x = 1 / (wavelength_m * math.sqrt(1 + (2 * distance_m / (shape[1] * pixel_pitch_m)) ** 2))
        limit_y = 1 / (wavelength_m * math.sqrt(1 + (2 * distance_m / (shape[0] * pixel_pitch_m)) ** 2))
        allowed &= (abs(fx) <= limit_x) & (abs(fy) <= limit_y)
    transfer = np.exp(2j * np.pi * distance_m * np.sqrt(np.maximum(square, 0))) * allowed
    propagated = fft.ifft2(fft.fft2(padded, workers=1) * transfer, workers=1)
    return propagated[y0:y0 + height, x0:x0 + width].astype(np.complex64)


def refocus_lightfield(perspectives, grid, *, depth_m=0, output_shape=(256, 256)):
    """Geometric shift-and-sum around z=0 in the calibrated capture frame.

    Positive depth points toward the camera. This is a light-field diagnostic,
    not a physically recorded hologram. All captured views are used.
    """
    p = np.asanyarray(perspectives)
    if p.ndim != 4 or tuple(p.shape[:2]) != tuple(grid.views):
        raise ValueError("Perspective array does not match the camera grid")
    if depth_m >= grid.distance_m:
        raise ValueError("Focus plane must lie in front of the camera plane")
    height, width = output_shape
    if height < 1 or width < 1:
        raise ValueError("Invalid output_shape")
    focal_px = width / (2 * math.tan(math.radians(grid.image_fov_deg) / 2))
    summed = np.zeros(output_shape, dtype=np.float64)
    weights = np.zeros(output_shape, dtype=np.float64)
    mask = np.ones(output_shape, dtype=np.float32)
    factor = focal_px * depth_m / (grid.distance_m * (grid.distance_m - depth_m))
    for row in range(p.shape[0]):
        for column in range(p.shape[1]):
            x, y, _ = grid.camera(row, column)["location"]
            shift = -factor * y, factor * x
            view = resize_intensity(p[row, column], output_shape)
            summed += ndimage.shift(view, shift, order=1, mode="constant", cval=0, prefilter=False)
            weights += ndimage.shift(mask, shift, order=1, mode="constant", cval=0, prefilter=False)
    return np.divide(summed, weights, out=np.zeros_like(summed), where=weights > 0).astype(np.float32)


def pupil_reconstruction(hogels, *, eye_m=(0, 0, .4), pupil_diameter_m=.002,
                         hogel_pitch_m=129e-6, fov_deg=30, samples=9):
    """Incoherent ray-intensity integral over a circular observer pupil.

    Assumes uniformly spaced angular bins on tan(theta). Eq. (4) does NOT
    uniquely establish this calibration, so this result is a model diagnostic,
    not an author-equivalent optical reconstruction. Returns native hogel grid.
    """
    h = np.asanyarray(hogels)
    if h.ndim != 4 or eye_m[2] <= 0 or pupil_diameter_m <= 0 or hogel_pitch_m <= 0:
        raise ValueError("Invalid hogel array, pupil, eye distance or pitch")
    if not isinstance(samples, int) or samples < 1 or not 0 < fov_deg < 120:
        raise ValueError("Invalid pupil sampling or FOV")
    hy, hx, av, au = h.shape
    x = (np.arange(hx) - (hx - 1) / 2) * hogel_pitch_m
    y = ((hy - 1) / 2 - np.arange(hy)) * hogel_pitch_m
    yy, xx = np.meshgrid(np.arange(hy), np.arange(hx), indexing="ij")
    bound = math.tan(math.radians(fov_deg) / 2)
    offsets = [(0., 0.)]
    if samples > 1:
        offsets += [(math.sqrt((i - .5) / (samples - 1)) * pupil_diameter_m / 2 * math.cos(i * 2.399963),
                     math.sqrt((i - .5) / (samples - 1)) * pupil_diameter_m / 2 * math.sin(i * 2.399963))
                    for i in range(1, samples)]
    result = np.zeros((hy, hx), dtype=np.float64)
    for dx, dy in offsets:
        # Camera index grows left-to-right and top-to-bottom, respectively.
        u = ((eye_m[0] + dx - x[None, :]) / eye_m[2] / bound + 1) / 2 * (au - 1)
        v = (1 - (eye_m[1] + dy - y[:, None]) / eye_m[2] / bound) / 2 * (av - 1)
        valid = (u >= 0) & (u <= au - 1) & (v >= 0) & (v <= av - 1)
        u = np.clip(np.broadcast_to(u, (hy, hx)), 0, au - 1)
        v = np.clip(np.broadcast_to(v, (hy, hx)), 0, av - 1)
        u0, v0 = u.astype(int), v.astype(int)
        u1, v1 = np.minimum(u0 + 1, au - 1), np.minimum(v0 + 1, av - 1)
        fu, fv = u - u0, v - v0
        sampled = ((1 - fv) * ((1 - fu) * h[yy, xx, v0, u0] + fu * h[yy, xx, v0, u1])
                   + fv * ((1 - fu) * h[yy, xx, v1, u0] + fu * h[yy, xx, v1, u1]))
        result += sampled * valid
    return (result / len(offsets)).astype(np.float32)
