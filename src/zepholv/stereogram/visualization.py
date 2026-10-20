"""Export publication-style diagnostic figures and standalone interactive 3D files.

No figure is labelled as an optical experiment. Raw arrays and calibrated poses
remain alongside all visualizations. Plotting never changes the synthesis data.
"""

import html
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .ifta import object_field, psnr, resize_intensity
from .lightfield import linear_to_srgb, perspective_from_hogels


def _display(array):
    return np.uint8(np.rint(linear_to_srgb(array) * 255))


def _mosaic(hogels, tile=12):
    rows, cols = hogels.shape[:2]
    image = np.empty((rows * tile, cols * tile), np.float32)
    for row in range(rows):
        for column in range(cols):
            image[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile] = resize_intensity(hogels[row, column], (tile, tile))
    return image


def visualize_reproduction(output):
    """Generate all stage plots, animated parallax and rotatable actual geometry."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import plotly.graph_objects as go

    root = Path(output)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    config = summary["request"]["config"]
    figures = root / "figures"
    figures.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "figure.facecolor": "white"})
    gallery = []

    def finish(fig, filename, caption):
        fig.tight_layout()
        fig.savefig(figures / filename, dpi=160, bbox_inches="tight")
        plt.close(fig)
        gallery.append((filename, caption))

    captures = {}
    for method in ("conventional", "proposed"):
        captures[method] = json.loads((root / method / "capture" / "manifest.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(2, 3, figsize=(11, 7))
    for row, method in enumerate(captures):
        data = captures[method]
        records = data["images"]
        indices = [0, len(records) // 2, len(records) - 1]
        for column, index in enumerate(indices):
            item = records[index]
            with Image.open(root / method / "capture" / item["file"]) as image:
                axes[row, column].imshow(image, interpolation="nearest")
            axes[row, column].set_title(f"{method}: camera ({item['row']}, {item['column']})\n{data['request']['grid']['resolution']} pixels")
            axes[row, column].axis("off")
    finish(fig, "01_acquisition.png", "Actual Blender perspective images at the two native acquisition resolutions.")

    geometry = json.loads((root / "proposed" / "capture" / "geometry.json").read_text(encoding="utf-8"))
    poses = captures["proposed"]["request"]["cameras"]
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    colors = plt.cm.Set2(np.linspace(0, 1, len(geometry)))
    mesh_figure = go.Figure()
    for mesh, color in zip(geometry, colors):
        vertices, triangles = np.asarray(mesh["vertices"]), np.asarray(mesh["triangles"])
        stride = max(1, len(triangles) // 2200)
        collection = Poly3DCollection(vertices[triangles[::stride]], facecolor=color, edgecolor="none", alpha=.9)
        ax.add_collection3d(collection)
        mesh_figure.add_trace(go.Mesh3d(x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
                                       i=triangles[:, 0], j=triangles[:, 1], k=triangles[:, 2],
                                       name=mesh["name"], opacity=1, flatshading=False,
                                       color=f"rgb({int(color[0]*255)},{int(color[1]*255)},{int(color[2]*255)})"))
    locations = np.array([pose["location"] for pose in poses])
    ax.scatter(*locations.T, s=5, color="#315b9b", label="actual camera array")
    for location in locations[::max(1, len(locations) // 12)]:
        ax.plot([location[0], 0], [location[1], 0], [location[2], 0], color="#315b9b", alpha=.15)
    all_vertices = np.concatenate([np.array(mesh["vertices"]) for mesh in geometry])
    ax.auto_scale_xyz([-.13, .13], [-.13, .13], [-.1, config["distance_m"]])
    ax.set(xlabel="X [m]", ylabel="Y [m]", zlabel="Z [m]", title="Actual scene meshes and calibrated planar cameras")
    ax.view_init(18, -62)
    finish(fig, "02_geometry_3d.png", "3D acquisition geometry. Static mesh display is subsampled; GLB and interactive mesh retain all triangles.")
    mesh_figure.add_trace(go.Scatter3d(x=locations[:, 0], y=locations[:, 1], z=locations[:, 2],
                                      mode="markers", marker={"size": 2, "color": "#315b9b"}, name="Camera array"))
    mesh_figure.update_layout(title=f"{summary['scene']}: actual meshes and cameras (metres)",
                              scene={"aspectmode": "data", "xaxis_title": "X [m]", "yaxis_title": "Y [m]", "zaxis_title": "Z [m]"})
    mesh_figure.write_html(figures / "scene_3d.html", include_plotlyjs=True)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, method in zip(axes, captures):
        hogels = np.load(root / method / "hogels.npy", mmap_mode="r")
        ax.imshow(_display(_mosaic(hogels)), cmap="gray", vmin=0, vmax=255)
        ax.set_title(f"{method}: {hogels.shape[:2]} hogels\nNative angular size {hogels.shape[-2:]}")
        ax.axis("off")
        del hogels
    finish(fig, "03_hogel_mosaic.png", "All hogels, with tiles reduced only for this overview; synthesis arrays retain their native resolution.")

    representative = summary["methods"]["proposed"]["representative_hogel"]
    hy, hx = config["hogels"]
    selections = [tuple(representative), (hy // 2, hx // 2), (hy // 3, hx // 3)]
    fig, axes = plt.subplots(2, 3, figsize=(10, 7))
    for row, method in enumerate(captures):
        hogels = np.load(root / method / "hogels.npy", mmap_mode="r")
        for column, selection in enumerate(selections):
            axes[row, column].imshow(_display(hogels[selection]), cmap="gray", interpolation="nearest", vmin=0, vmax=255)
            axes[row, column].set_title(f"{method} H{selection}\n{hogels.shape[-2:]}")
        del hogels
    finish(fig, "04_hogel_details.png", "Native angular intensity distributions, with explicit hogel coordinates.")

    checkpoints = config["iterations"]
    fig, axes = plt.subplots(len(checkpoints), 3, figsize=(10, 3 * len(checkpoints)), squeeze=False)
    representative_data = {}
    for method in captures:
        representative_data[method] = np.load(root / method / "encoding" / "representative.npz")
    for row, n in enumerate(checkpoints):
        data = representative_data["proposed"]
        axes[row, 0].imshow(data[f"phase_{n}"], cmap="twilight", vmin=-np.pi, vmax=np.pi)
        axes[row, 0].set_title(f"Proposed H{tuple(representative)} phase [rad]\nIFTA N={n}")
        for column, method in enumerate(captures, 1):
            view = np.load(root / method / "encoding" / f"checkpoint_{n:04d}.npy")
            display = np.round(linear_to_srgb(view) * (config["display_gray_levels"] - 1)) / (config["display_gray_levels"] - 1)
            axes[row, column].imshow(display, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
            axes[row, column].set_title(f"{method}, N={n}\n8-level display, native shape {view.shape}")
        for ax in axes[row]:
            ax.axis("off")
    finish(fig, "05_ifta_iterations.png", "All hogels encoded at 10/30/50/100 iterations. Views inverse-map the numerical angular intensities; they are not optical photographs.")

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for method, data in representative_data.items():
        measured = [psnr(data["target"], data[f"intensity_{n}"]) for n in checkpoints]
        axes[0].plot(checkpoints, measured, "o-", label=method)
    axes[0].set(title="Measured representative hogel", xlabel="IFTA iterations", ylabel="PSNR [dB], fixed peak 1")
    axes[0].legend()
    methods = list(captures)
    scores = [summary["methods"][m]["common_highres_view_psnr_db"] for m in methods]
    axes[1].bar(methods, scores, color=["#7593af", "#479e8a"])
    axes[1].set(title="Measured final common high-res view", ylabel="PSNR [dB]; same camera and reference")
    for method in methods:
        published = summary["published_psnr_db_not_measured"][method]
        axes[2].plot([10, 30, 50, 100], published, "o--", label=method)
    axes[2].set(title="Published values ONLY - not reproduced", xlabel="IFTA iterations", ylabel="Reported PSNR [dB]")
    axes[2].legend()
    finish(fig, "06_psnr.png", "Measured values and published values are separated. Unknown author references prevent claims of matching the paper's PSNR.")

    fig, axes = plt.subplots(3, 3, figsize=(10, 10))
    recon = np.load(root / "proposed" / "encoding" / "reconstruction.npy", mmap_mode="r")
    views = config["proposed_views"]
    for row, v in enumerate([0, views[0] // 2, views[0] - 1]):
        for column, u in enumerate([0, views[1] // 2, views[1] - 1]):
            image = perspective_from_hogels(recon, v, u, extraction=config["extraction"])
            axes[row, column].imshow(_display(image), cmap="gray", vmin=0, vmax=255)
            axes[row, column].set_title(f"Decoded view ({v}, {u})")
            axes[row, column].axis("off")
    finish(fig, "07_decoded_parallax.png", "Full horizontal and vertical parallax decoded from the saved quantized phase reconstructions.")
    for direction in ("horizontal", "vertical"):
        frames = []
        for index in range(views[1] if direction == "horizontal" else views[0]):
            v, u = (views[0] // 2, index) if direction == "horizontal" else (index, views[1] // 2)
            image = perspective_from_hogels(recon, v, u, extraction=config["extraction"])
            frames.append(Image.fromarray(_display(resize_intensity(image, (384, 384)))))
        frames[0].save(figures / f"parallax_{direction}.gif", save_all=True, append_images=frames[1:], duration=140, loop=0)
    del recon

    fig, axes = plt.subplots(2, 7, figsize=(17, 5))
    for row, method in enumerate(captures):
        data = np.load(root / method / "refocus.npz")
        for column, (depth, intensity) in enumerate(zip(data["depths_m"], data["intensity"])):
            axes[row, column].imshow(_display(intensity), cmap="gray", vmin=0, vmax=255)
            axes[row, column].set_title(f"{method}\nz={depth * 1000:.0f} mm")
            axes[row, column].axis("off")
    finish(fig, "08_refocus_stack.png", "Geometric shift-and-sum of the captured light field, using every camera. This is a capture diagnostic, not IFTA or an optical reconstruction.")
    focus = np.load(root / "proposed" / "refocus.npz")
    volume = go.Figure()
    sample_size = 80
    xx, yy = np.meshgrid(np.linspace(-1, 1, sample_size), np.linspace(1, -1, sample_size))
    for depth, intensity in zip(focus["depths_m"], focus["intensity"]):
        small = resize_intensity(intensity, (sample_size, sample_size))
        volume.add_trace(go.Surface(x=xx, y=yy, z=np.full_like(xx, depth * 1000), surfacecolor=small,
                                   colorscale="Gray", cmin=0, cmax=1, opacity=.65, showscale=False,
                                   name=f"z={depth*1000:.0f} mm"))
    volume.update_layout(title="Calibrated light-field refocus stack (geometric diagnostic)",
                          scene={"xaxis_title": "Normalized image X", "yaxis_title": "Normalized image Y", "zaxis_title": "Focus plane Z [mm]"})
    volume.write_html(figures / "refocus_volume_3d.html", include_plotlyjs=True)

    fig, axes = plt.subplots(2, 3, figsize=(10, 7))
    for row, method in enumerate(captures):
        pupils = np.load(root / method / "pupil_views.npy")
        for column, index in enumerate([3, 4, 5]):
            axes[row, column].imshow(_display(pupils[index]), cmap="gray", vmin=0, vmax=255, interpolation="nearest")
            axes[row, column].set_title(f"{method}, eye x={[-25,0,25][column]} mm\n2 mm pupil, 400 mm distance")
            axes[row, column].axis("off")
    finish(fig, "09_pupil_model.png", "Incoherent pupil ray integral under an explicitly assumed uniform angular-bin calibration. Original optical calibration is unavailable.")

    data = np.load(root / "proposed" / "single_hogel_wave.npz")
    fig, axes = plt.subplots(3, 3, figsize=(10, 9))
    for ax, distance, intensity in zip(axes.ravel(), data["distances_m"], data["intensity"]):
        ax.imshow(np.log1p(intensity), cmap="magma")
        ax.set_title(f"Single hogel, free space z={distance*1000:.1f} mm")
        ax.axis("off")
    finish(fig, "10_wave_propagation.png", "Band-limited angular-spectrum propagation around one SLM hogel. These are near-SLM wave diagnostics, not the full 3D scene.")

    print_path = root / "proposed" / "print" / "print_job.json"
    if print_path.is_file():
        job = json.loads(print_path.read_text(encoding="utf-8"))
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        selected = next(r for r in job["records"] if [r["row"], r["column"]] == representative)
        with Image.open(print_path.parent / selected["frame"]) as image:
            axes[0].imshow(image, cmap="gray", vmin=0, vmax=255)
        axes[0].set_title("Actual 1920 x 1080 SLM export\nNative phase patch centered; aperture required")
        coordinates = np.array([[r["x_m"], r["y_m"]] for r in job["records"]]) * 1000
        axes[1].plot(*coordinates.T, lw=.5, color="#2d7f7d")
        axes[1].set(title=f"Dry-run {job['scan']} path: {len(coordinates)} hogels", xlabel="Stage X [mm]", ylabel="Stage Y [mm]")
        axes[1].set_aspect("equal")
        finish(fig, "11_print_data.png", "Every hogel has an exported display frame and stage instruction. No hardware exposure was performed; the default grayscale LUT is uncalibrated.")

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.set_xlim(0, 12)
    ax.set_ylim(-2, 2)
    for x, y, label in [(1, 0, "532 nm laser"), (3, 0, "Beam splitter"), (5, 1, "Phase-only SLM"),
                        (7, 1, "L1: 85 mm"), (8.5, 1, "L2: 25 mm"), (10.5, 0, "Apertures + plate\nX/Y stage"),
                        (5.5, -1, "Reference arm\nL3 / L4: focal lengths not reported")]:
        ax.text(x, y, label, ha="center", va="center", bbox={"facecolor": "#edf3f4", "edgecolor": "#527b86", "boxstyle": "round,pad=0.4"})
    for start, end in [((1.7,0),(2.3,0)),((3.3,.3),(4.4,.8)),((5.8,1),(6.5,1)),((7.4,1),(8,1)),((9,1),(10.2,.2)),((3.3,-.3),(4.4,-.9)),((7,-1),(10.2,-.2))]:
        ax.annotate("", end, start, arrowprops={"arrowstyle": "->", "color": "#558359"})
    ax.text(9, -1.3, "Reference incidence: 45 deg\nExposure: 0.2 s; signal/reference 1:1\nUltimate U08M silver halide", ha="center")
    ax.set_title("Reported optical elements - schematic, not to scale, hardware NOT reproduced")
    ax.axis("off")
    finish(fig, "12_optical_setup.png", "The paper's reported optical parameters are recorded; unspecified geometry and vendor drivers are not invented.")

    target = representative_data["proposed"]["target"]
    wave = object_field(target)
    fig, axes = plt.subplots(1, 3, figsize=(11, 4))
    for ax, image, title, cmap in zip(axes, [target, abs(wave), np.angle(wave)],
                                    ["Angular intensity", "Eq. (2) object-field amplitude", "Eq. (2) object-field phase"],
                                    ["gray", "gray", "twilight"]):
        ax.imshow(image, cmap=cmap)
        ax.set_title(title)
        ax.axis("off")
    finish(fig, "13_object_field.png", "Direct inverse Fourier superposition of sqrt(intensity), distinct from the phase-only IFTA projection.")
    for archive in representative_data.values():
        archive.close()

    rows = "".join(f"<tr><td>{method}</td><td>{info['dimensions']['views']}</td><td>{info['dimensions']['perspective']}</td>"
                   f"<td>{info['dimensions']['native_angular']}</td><td>{info['roundtrip_max_error']}</td>"
                   f"<td>{info['common_highres_view_psnr_db']:.3f}</td></tr>" for method, info in summary["methods"].items())
    audit = "".join(f"<li>{html.escape(item)}</li>" for item in summary["audit"]["unresolved"])
    images = "".join(f'<figure><a href="figures/{name}"><img src="figures/{name}" loading="lazy"></a><figcaption>{html.escape(caption)}</figcaption></figure>'
                     for name, caption in gallery)
    report = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Zepholv: {html.escape(summary['scene'])}</title>
<style>body{{max-width:1150px;margin:35px auto;font:16px/1.6 system-ui;color:#20313b;padding:0 20px}}img{{width:100%;height:auto}}figure{{margin:32px 0}}figcaption{{color:#526470}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border:1px solid #cbd5dd}}.notice{{padding:18px;background:#fff3d8;border-left:5px solid #c78c25}}a{{color:#146b83}}</style>
<h1>{html.escape(summary['scene'])}: Hogel synthesis evidence</h1>
<p class="notice"><b>This is an audited computational implementation, not an exact author-code reproduction or physical optical experiment.</b> The source paper is DOI <a href="https://doi.org/10.3390/app10228088">10.3390/app10228088</a>. Every deviation and unresolved parameter is listed below. Published numerical scores are not claimed as our measurements.</p>
<p><a href="summary.json">Machine-readable summary</a> | <a href="figures/scene_3d.html">Rotate complete scene meshes and cameras</a> | <a href="proposed/capture/scene.glb">Original full GLB geometry</a> | <a href="proposed/capture/scene.blend">Blender scene</a> | <a href="figures/refocus_volume_3d.html">Interactive refocus volume</a></p>
<p><a href="figures/parallax_horizontal.gif">Horizontal parallax animation</a> | <a href="figures/parallax_vertical.gif">Vertical parallax animation</a></p>
<table><tr><th>Method</th><th>Camera array</th><th>Perspective pixels</th><th>Native hogel angular pixels</th><th>Inverse-map error</th><th>Measured common-view PSNR [dB]</th></tr>{rows}</table>
<h2>Unresolved details and assumptions</h2><ul>{audit}</ul>
<h2>Every numerical stage</h2>{images}
<h2>Data products</h2><p>Each method directory contains all captured PNG views, per-camera matrices and fiducial checks, linear perspectives.npy, native hogels.npy, every quantized phase in encoding/phase_codes.npy, its Fourier intensity in encoding/reconstruction.npy, per-hogel metrics.csv, 10/30/50/100 iteration views, pupil samples and wave diagnostics. print/ contains every SLM frame and the full stage/shutter plan. These files are data and simulations; no optical recording was performed.</p>
</html>'''
    (root / "report.html").write_text(report, encoding="utf-8")
    return root / "report.html"


def index_reproductions(output):
    """Link completed public-API runs in a standalone local HTML index."""
    root = Path(output)
    items = []
    for path in sorted(root.glob("*/summary.json")):
        info = json.loads(path.read_text(encoding="utf-8"))
        folder = path.parent.name
        items.append(f'<article><h2><a href="{folder}/report.html">{html.escape(info["scene"])}</a></h2>'
                     f'<a href="{folder}/report.html"><img width="360" src="{folder}/proposed/capture/preview.png"></a>'
                     f'<p>Exact author reproduction: false. Hardware experiment: not performed.</p></article>')
    (root / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Zepholv reproduction results</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:40px auto}article{display:inline-block;vertical-align:top;margin:15px;width:45%}img{max-width:100%}</style>'
        '<h1>Zepholv: computational reproduction evidence</h1><p>All scene reports, raw data and interactive 3D results.</p>'
        + ''.join(items), encoding="utf-8")
    return root / "index.html"
