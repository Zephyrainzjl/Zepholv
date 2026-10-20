"""Standalone Blender-side acquisition implementation. All bpy usage stays here.

Original implementation; grid acquisition workflow informed by gfxdisp's
Blender-addon-light-field-camera. See docs/reproduction.md for provenance.
"""

import hashlib
import json
import math
from pathlib import Path
import time

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 0.65
    return mat


def finish(obj, name, mat):
    obj.name = name
    obj.data.materials.append(mat)
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    return obj


def lathe(name, profile, center, mat, segments=96):
    vertices = []
    for radius, y in profile:
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            vertices.append((center[0] + radius * math.cos(angle), center[1] + y,
                             center[2] + radius * math.sin(angle)))
    faces = []
    for j in range(len(profile) - 1):
        for i in range(segments):
            k = j * segments + i
            nxt = j * segments + (i + 1) % segments
            faces.append((k, nxt, nxt + segments, k + segments))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, mat)


def tube(name, points, radii, mat, segments=20):
    vertices = []
    for j, point in enumerate(points):
        tangent = Vector(points[min(j + 1, len(points) - 1)]) - Vector(points[max(j - 1, 0)])
        tangent.normalize()
        normal = tangent.cross(Vector((0, 0, 1))).normalized()
        second = tangent.cross(normal).normalized()
        for i in range(segments):
            angle = i * 2 * math.pi / segments
            p = Vector(point) + radii[j] * (math.cos(angle) * normal + math.sin(angle) * second)
            vertices.append(tuple(p))
    faces = []
    for j in range(len(points) - 1):
        for i in range(segments):
            a = j * segments + i
            b = j * segments + (i + 1) % segments
            faces.append((a, b, b + segments, a + segments))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, mat)


def create_scene(kind, bunny_mesh):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    white = material("Diffuse_white", (0.65, 0.65, 0.65))
    if kind == "teapot_sphere":
        center = (-0.018, -0.005, 0)
        lathe("Teapot_body", [(0, -0.044), (.025, -.044), (.036, -.032), (.043, -.008),
              (.04, .009), (.03, .023), (.024, .026)], center, white)
        lathe("Teapot_lid", [(.025, .025), (.029, .028), (.021, .032), (.01, .034), (0, .035)], center, white)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=.005,
                                           location=(center[0], center[1] + .038, 0))
        finish(bpy.context.object, "Lid_knob", white)
        points = [(-.05 - .043 * t, -.013 + .048 * t * t, 0) for t in [i / 30 for i in range(31)]]
        tube("Spout", points, [.011 * (1 - i / 30) + .0035 for i in range(31)], white)
        points = [(.022 + .03 * math.cos(t), -.006 + .035 * math.sin(t), -.003)
                  for t in [-math.pi / 2 + i * math.pi / 48 for i in range(49)]]
        tube("Handle", points, [.004] * len(points), white)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=.024,
                                           location=(.06, .062, -.04))
        finish(bpy.context.object, "Sphere_depth_offset_40mm", white)
    elif kind == "bunny_carrot":
        bpy.ops.wm.ply_import(filepath=bunny_mesh)
        bunny = bpy.context.object
        coords = [vertex.co.copy() for vertex in bunny.data.vertices]
        mins = Vector(tuple(min(v[i] for v in coords) for i in range(3)))
        maxs = Vector(tuple(max(v[i] for v in coords) for i in range(3)))
        midpoint = (mins + maxs) / 2
        scale = .145 / (maxs.y - mins.y)
        for vertex in bunny.data.vertices:
            vertex.co = (vertex.co - midpoint) * scale
        bunny.location = (-.015, -.005, 0)
        bunny.rotation_euler.y = -.25
        finish(bunny, "Stanford_bunny", white)
        points = [(.055 + .027 * t, .038 + .028 * t, .025) for t in [i / 20 for i in range(21)]]
        tube("Carrot", points, [.001 + .009 * i / 20 for i in range(21)], white)
        for k in range(5):
            points = [(.082 + .025 * t, .066 + (.02 + k * .003) * math.sin(t * 1.5), .025 + (k - 2) * .002)
                      for t in [i / 12 for i in range(13)]]
            tube("Carrot_leaf", points, [.0008] * len(points), white, 8)
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=20, radius=.028, location=(-.055, .035, -.04))
        finish(bpy.context.object, "Far_sphere", white)
        bpy.ops.mesh.primitive_cube_add(size=.042, location=(.045, .03, 0), rotation=(.3, .4, .2))
        finish(bpy.context.object, "Middle_cube", white)
        bpy.ops.mesh.primitive_torus_add(major_radius=.027, minor_radius=.009, location=(0, -.045, .04))
        finish(bpy.context.object, "Near_torus", white)


def export_geometry(output):
    geometry = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        geometry.append({
            "name": obj.name,
            "vertices": [list(obj.matrix_world @ v.co) for v in mesh.vertices],
            "triangles": [list(face.vertices) for face in mesh.loop_triangles],
        })
        evaluated.to_mesh_clear()
    (output / "geometry.json").write_text(json.dumps(geometry), encoding="utf-8")
    bpy.ops.export_scene.gltf(filepath=str(output / "scene.glb"), export_format="GLB",
                              export_cameras=False, export_lights=False)


def acquire(request):
    output = Path(request["output"])
    output.mkdir(parents=True, exist_ok=True)
    views = output / "views"
    views.mkdir(exist_ok=True)
    create_scene(request["scene"], request["bunny_mesh"])
    scene = bpy.context.scene
    grid = request["grid"]
    settings = request["settings"]
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = settings["samples"]
    scene.cycles.use_denoising = False
    scene.cycles.seed = settings["seed"]
    scene.cycles.max_bounces = 3
    scene.cycles.diffuse_bounces = 2
    scene.render.threads_mode = "FIXED"
    scene.render.threads = settings["threads"]
    scene.render.use_persistent_data = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.world.color = (0, 0, 0)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0
    for name, location, power, size in [
        ("Key", (-.16, .16, .22), .22, .18), ("Fill", (.18, .08, .15), .06, .14),
    ]:
        bpy.ops.object.light_add(type="AREA", location=location)
        lamp = bpy.context.object
        lamp.name = name
        lamp.rotation_euler = (-lamp.location).to_track_quat("-Z", "Y").to_euler()
        lamp.data.energy = power
        lamp.data.shape = "DISK"
        lamp.data.size = size
    bpy.ops.object.camera_add(location=(0, 0, grid["distance_m"]))
    camera = bpy.context.object
    scene.camera = camera
    camera.data.type = "PERSP"
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.sensor_width = 36
    camera.data.lens = 18 / math.tan(math.radians(grid["image_fov_deg"]) / 2)
    camera.data.clip_start = .001
    camera.data.clip_end = 10
    scene.render.resolution_x = settings["preview_size"]
    scene.render.resolution_y = settings["preview_size"]
    scene.render.filepath = str(output / "preview.png")
    if not (output / "preview.png").is_file():
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "scene.blend"), check_existing=False)
    export_geometry(output)
    height, width = grid["resolution"]
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    records = []
    started = time.monotonic()
    manifest_path = output / "manifest.json"

    def checkpoint(complete=False):
        payload = {"request": request, "complete": complete, "images": records,
                   "blender_version": bpy.app.version_string,
                   "elapsed_seconds": time.monotonic() - started,
                   "intensity": "PNG sRGB, decode to linear luminance on host",
                   "coordinate_convention": "world +Y up; camera looks -Z; PNG top-left"}
        temporary = manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(manifest_path)

    checkpoint()
    for index, pose in enumerate(request["cameras"]):
        camera.location = pose["location"]
        camera.data.shift_x = pose["shift_x"]
        camera.data.shift_y = pose["shift_y"]
        bpy.context.view_layer.update()
        center = world_to_camera_view(scene, camera, Vector((0, 0, 0)))
        if max(abs(center.x - .5), abs(center.y - .5)) > 2e-5:
            raise RuntimeError(f"Re-centering calibration failed: {tuple(center)}")
        filename = f"views/v{pose['row']:03d}_u{pose['column']:03d}.png"
        image_path = output / filename
        if not image_path.is_file():
            scene.render.filepath = str(image_path)
            bpy.ops.render.render(write_still=True)
        # Projection checks include off-plane fiducials, not just the center.
        fiducials = [[-.03, -.02, -.04], [.02, .03, .04], [0, 0, 0]]
        records.append({**pose, "file": filename,
            "world_to_camera": [list(row) for row in camera.matrix_world.inverted()],
            "fiducials_world": fiducials,
            "fiducials_ndc": [list(world_to_camera_view(scene, camera, Vector(point))) for point in fiducials],
            "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest()})
        if index % 10 == 0:
            checkpoint()
            print(f"ZEPHOLV_ACQUISITION {index + 1}/{len(request['cameras'])}", flush=True)
        if settings["pause_seconds"]:
            time.sleep(settings["pause_seconds"])
    checkpoint(complete=True)
    return {"manifest": str(manifest_path), "views": len(records)}


if __name__ == "__main__":
    result = acquire(params)
