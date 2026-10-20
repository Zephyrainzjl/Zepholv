# Zepholv

Zepholv 的 Python 安装包骨架，采用 `src/` 布局，预留 C++ 扩展接口。
提供 Blender 外部调用、光场采集、Hogel 重排、相位编码、数值重建与打印数据导出。
论文计算流程的参数、来源及未公开细节见 [复现说明](docs/reproduction.md)。

## 目录

```text
Zepholv/
├── README.md
├── pyproject.toml          # 包信息、依赖与构建配置
├── MANIFEST.in            # 源码分发包含的额外文件
├── src/
│   └── zepholv/
│       ├── __init__.py    # 包入口与版本
│       ├── zepholv.py     # Python 功能实现位置
│       ├── blender/      # Blender 调用、再中心化采集、场景与独立进程桥接
│       └── stereogram/  # Hogel、IFTA、数值重建、打印数据及可视化 API
├── cpp/
│   ├── CMakeLists.txt     # 独立的 C++ 扩展构建入口
│   └── bindings.cpp      # pybind11 绑定占位
└── docs/
    ├── conf.py
    ├── index.md
    ├── usage.md
    ├── blender.md
    ├── reproduction.md
    ├── api.md
    ├── cpp.md
    ├── requirements.txt
    ├── Makefile
    └── make.bat
```

测试目录与 `Zepholv/` 平级，位于 `D:/pyworks/quanxi/test/`，不在安装包内部：

```text
quanxi/
├── Zepholv/                         # 上面的安装包目录
└── test/
    ├── reproduction.ipynb           # 可运行的中文分阶段流程、结果图与交互三维图
    ├── test_*.py                    # 通过公开 API 测试
    ├── run_reproduction.py
    ├── run_tests.py
    ├── acquire.py
    ├── reference/                   # 来源与参考源码快照
    ├── assets/                      # 模型
    └── results/                     # 全部输出；paper/index.html 为论文尺寸结果入口
```

## 安装与使用

需要 Python 3.10 或更高版本。在项目根目录执行：

```console
python -m pip install -e .
python -c "import zepholv; print(zepholv.__version__)"
```

发布名为 `Zepholv`，Python 导入名统一使用小写 `zepholv`。
数值与可视化依赖由 `pyproject.toml` 自动安装；Blender 使用单独安装的软件，
不在宿主环境中安装 `bpy`。

## Blender 调用

只需传入 Blender 安装目录或可执行文件路径，无需额外安装 `bpy`：

```python
from zepholv.blender import Blender

blender = Blender(r"D:\software_fileprocess\blender5.1")
job = blender.run('''
bpy.ops.mesh.primitive_cube_add(size=params['size'])
result = {'name': bpy.context.object.name, 'version': bpy.app.version_string}
''', params={'size': 2})
print(job.data)
```

通过 `run` 可执行完整 Blender Python API；另有 `run_script`、`call`、
`render`、`command` 和 `launch`。每次后台调用均为独立进程；连续操作放在
同一脚本，或通过 `.blend` 文件传递场景。依赖界面的功能仍受 Blender
上下文限制。完整示例和错误处理见 [Blender 文档](docs/blender.md)。

## Hogel 合成与完整实验

```python
from zepholv.blender import Blender
from zepholv.stereogram import SynthesisConfig, run_reproduction

summary = run_reproduction(
    Blender(r"D:\software_fileprocess\blender5.1", low_priority=True),
    "../test/results/my_experiment",  # 当前工作目录为 Zepholv/
    scene="teapot_sphere", config=SynthesisConfig(),
)
```

默认配置使用论文尺寸，编码全部 2500 个 Hogel、保存四个迭代检查点，
并导出所有 SLM 帧、数值诊断和三维图表。CPU 渲染限制两个线程。
结果是有来源记录的计算实现；原文公式与未公开细节的歧义、替代场景和额外
建模假设均显式记录，不能声称完成了完全相同的作者实验或实体光学打印。

完整三场景运行及逐步 API 见 [复现说明](docs/reproduction.md)。

## 测试与打包

安装后运行测试，无需额外测试框架：

```console
python -m unittest discover -s ../test -v
```

构建 wheel 和源码包：

```console
python -m pip install build
python -m build
```

生成文件位于 `dist/`，可通过 `python -m pip install dist/<生成的文件名>.whl`
安装。源码包包含文档和 C++ 占位源码；外部测试、Notebook、参考快照、模型和实验输出独立保存在同级 `test/`，不进入安装包。

### 中文 Notebook

在 `D:/pyworks/quanxi`（`Zepholv` 和 `test` 的上级目录）执行：

```powershell
python -m pip install -e './Zepholv[notebook,test]'
python -m ipykernel install --user --name zepholv --display-name 'Python (zepholv)'
python -m jupyterlab test/reproduction.ipynb
```

选择 `Python (zepholv)` 内核后从上往下运行。默认是三场景小尺寸完整计算，所有阶段即时显示图像，
并另行展示已有论文尺寸结果。修改配置单元中的 `PROFILE` 可计算论文尺寸；不会覆盖已有 `paper/` 数据。

## 文档与 C++

```console
python -m pip install -e ".[docs]"
python -m sphinx -M html docs docs/_build
```

文档首页为 `docs/_build/html/index.html`。
C++ 构建步骤见 [docs/cpp.md](docs/cpp.md)。当前 `pip install .` 只构建
Python 包，C++ 为独立的可选构建入口，尚未接入 wheel 自动构建。

暂不添加 Git/GitHub、在线文档发布或社区治理配置。
许可证尚未指定；对外发布前请补充许可证及作者信息。
