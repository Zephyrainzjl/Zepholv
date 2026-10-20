# Blender 调用接口

Zepholv 使用独立进程调用 Blender 自带的 Python，不要求宿主 Python 安装
`bpy`，也不要求两侧的 Python 版本一致。仅使用 Python 标准库。

## 初始化

```python
from zepholv.blender import Blender

blender = Blender(r"D:\software_fileprocess\blender5.1", timeout=120)
print(blender.version())
```

可传 Blender 安装目录或完整可执行文件路径；支持 Windows 的
`blender.exe`、Linux 的 `blender` 和 macOS 的 `Blender.app`。
换电脑时更改路径即可；目标电脑仍需安装 Blender 及任务依赖的插件、
素材或额外 Python 模块。插件、算子和引擎名称取决于目标 Blender 版本。

## 任意 Blender Python API

`run` 中可以调用 `bpy.data`、`bpy.ops`、`bpy.context`、`bpy.types`、
`mathutils` 等 Blender 自带 Python 接口。`bpy` 已自动导入。
传入参数通过 `params` 读取，将返回值赋给 `result`：

```python
from pathlib import Path
from zepholv.blender import Blender

blender = Blender(r"D:\software_fileprocess\blender5.1")
scene_path = str(Path("example.blend").resolve())
job = blender.run('''
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

bpy.ops.mesh.primitive_cube_add(size=params['size'])
cube = bpy.context.object
cube.name = 'ExampleCube'
cube.rotation_euler = (0.2, 0.3, 0.4)

material = bpy.data.materials.new('Blue')
material.diffuse_color = (0.05, 0.2, 0.8, 1.0)
cube.data.materials.append(material)

cube.keyframe_insert(data_path='rotation_euler', frame=1)
cube.rotation_euler.z += 1.0
cube.keyframe_insert(data_path='rotation_euler', frame=24)
bpy.context.scene.frame_set(1)

bpy.ops.object.camera_add(location=(5, -5, 4))
camera = bpy.context.object
direction = cube.location - camera.location
camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type='AREA', location=(2, -2, 5))
bpy.context.object.data.energy = 500
bpy.context.object.data.size = 4

bpy.ops.wm.save_as_mainfile(filepath=params['scene'])
result = {'objects': list(bpy.data.objects.keys()), 'scene': params['scene']}
''', params={'size': 2.0, 'scene': scene_path})

print(job.data)
print(job.stdout)
```

同样可在脚本中执行导入导出、几何节点、修改器、动画、仿真、烘焙、
多相机渲染等 Blender 支持的任务，无需等待 Zepholv 为每个功能增加包装。
模型导入导出直接调用目标版本提供的算子，例如
`bpy.ops.wm.obj_import(filepath=params['model'])`。

参数与结果必须能转换为 JSON；向量使用 `list(vector)`，对象传名称或其他
普通数据，路径使用 `str(path)`。无法直接把 Blender 内存对象传回宿主。
源代码通过临时文件协议执行，不经过 shell 拼接；临时文件在任务后清理。
只运行可信脚本，脚本可访问当前用户权限下的文件和系统资源。

## 执行脚本文件

```python
job = blender.run_script(
    'my_scene.py',
    params={'size': 2},
    script_args=['--custom-option', 'value'],
    cwd='.',
)
```

脚本中可直接使用 `bpy`、`params`，并赋值 `result`。
`__file__` 为原脚本路径，同目录模块可以导入；`sys.argv` 为
`[脚本路径, *script_args]`。相对数据文件路径由 `cwd` 决定，默认继承
调用进程目录；Blender 的 `//` 路径则依照 `.blend` 文件解析。

## 现成场景与常用操作

```python
# 每次调用都会启动独立的 Blender，使用 blend_file 载入已有场景。
job = blender.run(
    'result = list(bpy.data.objects.keys())',
    blend_file='example.blend',
)

# 默认后台上下文中的单个 bpy.ops 算子，可保存操作后的场景。
job = blender.call(
    'mesh.primitive_cube_add',
    kwargs={'size': 1, 'location': [0, 0, 2]},
    blend_file='example.blend',
    save_to='edited.blend',
)

# 使用场景已有相机渲染静帧；输出目录自动创建。
job = blender.render(
    'example.blend', 'renders/frame.png',
    frame=1, engine='CYCLES', resolution=(512, 512),
)
print(job.data['output'])

# 完整命令行入口；参数必须使用列表，每个元素对应一个参数。
print(blender.command(['--help']).stdout)

# 打开新界面窗口，返回 subprocess.Popen；不连接现有窗口。
process = blender.launch('example.blend')
```

## 执行模型与限制

每个 `run`、`run_script`、`call`、`render` 都是独立的后台进程，完成后退出。
连续操作需放到同一脚本，或保存场景并在下次调用中载入。不会远程代理
Python 对象，也不会修改已经打开的 Blender 窗口。

默认使用 `--factory-startup` 取得稳定初始环境。需要用户启动配置或插件时，
为 `run` / `run_script` 设置 `factory_startup=False`，或在脚本中启用插件。
`extra_args` 可传高级 Blender 启动参数，但不能破坏脚本执行所需的
`--python`、`--python-exit-code` 与 `--` 参数协议。

脚本入口可以使用完整 `bpy` API，但后台模式没有交互窗口；依赖编辑器、
选择状态或界面事件的算子仍受 Blender 自身上下文约束，可使用
`bpy.context.temp_override` 或数据 API。需要真实 UI 的任务可用
`launch(args=['--python', '绝对脚本路径'])` 在新界面中执行，此方式不提供
上述 JSON 参数与结果协议，且界面生命周期由调用方管理。

`BlenderResult` 包含 `data`、`stdout`、`stderr`、`returncode`、`command`
及 `elapsed`（秒）。失败抛出 `BlenderError`，错误信息包含 Blender 侧
Python traceback，异常的 `.result` 提供进程日志。非 JSON 返回值也会报错。

```python
from zepholv.blender import BlenderError, BlenderTimeoutError

try:
    job = blender.run('result = bpy.app.version_string', timeout=30)
except BlenderTimeoutError as exc:
    print('超时，Blender 子进程已结束', exc.result.stdout)
except BlenderError as exc:
    print(str(exc))
    if exc.result:
        print(exc.result.stderr)
```

默认不限制运行时间；构造时的 `timeout` 为默认秒数，单次调用可覆盖。
超时结束 Blender 进程，但不会自动管理用户脚本自行启动的其他进程。
用户脚本主动退出 Blender 或破坏结果协议时，可能无法取得结构化结果。

后台进程会移除宿主环境的 `PYTHONHOME` 与 `PYTHONPATH`，避免虚拟环境干扰
Blender 自带解释器；如需额外环境变量，可通过构造参数 `env={...}` 传入。

## 验证

普通测试无需 Blender。真实集成测试在 `Zepholv/` 目录的 PowerShell 中执行：

```powershell
$env:ZEPHOLV_BLENDER = 'D:\software_fileprocess\blender5.1'
python -m unittest discover -s ../test -v
```

测试会在临时目录内创建场景并渲染小尺寸 PNG，退出后清理。

底层参数说明见 [Blender 官方命令行文档](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html)。
