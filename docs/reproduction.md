# Hogel 论文计算流程与复现边界

目标论文：Dashdavaa 等，*Efficient Hogel-Based Hologram Synthesis Method for
Holographic Stereogram Printing*，Applied Sciences 10(22), 8088 (2020)，
[DOI: 10.3390/app10228088](https://doi.org/10.3390/app10228088)。

本实现提供论文尺寸的计算流程、逐步验证和全部打印输入数据。
**不能称为与作者程序逐细节完全相同，也没有完成实体光学打印实验。**
原因不是用默认值隐藏的：论文的公式、公开信息和源代码不足以唯一确定完整实验。
`paper_audit()` 和每份结果中的 `summary.json` 均保留这些边界。

## 已核对的参数

本页所有 `test/...` 路径和实验命令均以工作区 `D:/pyworks/quanxi` 为当前目录；
`test/` 与安装包目录 `Zepholv/` 平级。可运行的中文逐阶段 Notebook 为
`test/reproduction.ipynb`，默认验证尺寸，论文尺寸需显式选择。

| 项目 | 论文数值 | API |
|---|---|---|
| 传统视角阵列 | 50 × 50 | `conventional_views` |
| 传统单视角像素 | 50 × 50 | `hogels` |
| 提出方法视角阵列 | 10 × 10 | `proposed_views` |
| 提出方法单视角像素 | 1000 × 1000 | `proposed_resolution`，由参数计算 |
| Hogel 阵列 | 50 × 50 | `hogels` |
| 提出方法 Hogel 像素 | 200 × 200 | `angular_shape`，由参数计算 |
| 每轴提取因子 | 20 | `extraction` |
| 波长 | 532 nm | `wavelength_m` |
| 距离 | 400 mm | `distance_m` |
| 场景深度间隔 | 40 mm（茶壶与球） | `depth_separation_m` / 场景几何 |
| 数值采集 FOV | 30° | `camera_fov_deg`，解释为全角 |
| 瞳孔 | 2 mm | `pupil_diameter_m` |
| 数值全息采样 | 129 μm | `hologram_sampling_m` |
| 实体打印 Hogel 间距 | 1 mm | `printed_hogel_pitch_m` |
| SLM | 1920 × 1080；6.4 μm | `slm_shape=(1080,1920)` / `slm_pixel_pitch_m` |
| 迭代检查点 | 10、30、50、100 | `iterations` |
| 重建显示灰阶 | 8 级 | `display_gray_levels`，仅用于显示 |
| 物光透镜焦距 | 85 / 25 mm | `OpticalSetup.lens_f1_m/lens_f2_m` |
| 参考光角度 | 45° | `reference_angle_deg` |
| 单次曝光 | 0.2 s | `exposure_seconds` |
| 物光/参考光能量 | 1:1 | `signal_reference_ratio` |
| 材料 | Ultimate U08M | `material` |

尺寸均采用 `(行, 列)`。API 长度统一为米，时间为秒，相位为弧度。
物理尺寸不能互相替代：`129 μm` 采样、`1 mm` 打印步长与 SLM 经
`25/85` 倍缩小后的尺寸不是一套由论文完整标定的坐标映射。

## 不能隐瞒的歧义

1. **公式 (4) 不完整。** `H[u/20,v/20](20U,20V)=P[U,V](u,v)`
   没有写取整或块内位置，直接执行会发生索引非整数及多个像素写入同一位置。
   本实现依据图 4 和像素总数守恒采用下述显式块排列；它是可逆的补全，
   不是找到了作者 MATLAB 源码。`SynthesisConfig(mapping='literal')` 会拒绝猜测。
2. **公式 (5) 与角分辨率数值不一致。** 原式含未定义的 `Δλ`；若按通常的
   `λ/ρ`，0.32 mm 与 1.28 mm 对应约 `0.0953°`、`0.0238°`，不能得到文中的
   1.66° 与 4.15°。代码分别记录原文数值与量纲一致的计算，不调整单位凑数。
3. 原始 `.blend` 场景、完整相机标定、渲染器设置、MATLAB IFTA、PSNR 参考图、
   随机种子、插值核以及 LabVIEW/硬件驱动均未找到公开源码。源码检索记录在
   `test/reference/sources.json`，这不等于证明它们在任何地方都不存在。
4. 数值部分写 30°，光学部分还写 ±30°；本实现数值采集采用全角 30°，
   不将两个表述静默混用。
5. 文中说重建图像采用八级灰度，没有明确说 SLM 相位必须八级。
   IFTA 默认连续相位，打印帧用 256 个理想相位编码，图像预览转换 sRGB 后
   量化八级。真实设备须使用测得的相位 LUT。
6. 论文没有解释完整光路中的裁切、有效 SLM 区域与 Hogel 尺寸如何标定。
   当前打印数据把 200 × 200 相位块原尺寸居中放到 SLM 帧，帧外需物理光阑。
   这不是作者未公布光学映射的替代标定。

## 源码与文献依据

- [slmsuite 源码](https://github.com/holodyne/slmsuite/tree/5ac5a19ac356fe238a54db8a0a6be7114f085cf8)，
  固定提交 `5ac5a19ac356fe238a54db8a0a6be7114f085cf8`，MIT 许可。
  基本 GS 的投影顺序和归一化迁移到独立 CPU 实现，源码与许可证快照保留在
  `test/reference/upstream/`，发行包包含许可。测试直接解析固定源文件中的
  正/逆传播方法，验证迁移后的傅里叶变换与参考一致。没有把 WGS、MRAF 等
  不同算法冒充本文 IFTA。
- [gfxdisp 光场相机插件](https://github.com/gfxdisp/Blender-addon-light-field-camera/tree/a1ae3f28f6184efcbc22ca3328003ed690b8e830)，
  固定提交 `a1ae3f28f6184efcbc22ca3328003ed690b8e830`。
  阅读了平面相机阵列与逐视角渲染流程；未发现明确许可证，因此不把其代码
  复制到发行包。离轴再中心化投影独立推导，使用 Blender 自带
  `world_to_camera_view` 检查每个视角的中心和离面标记点。
- [同作者 2019 年相关论文](https://holographypro.com/images/Publications/step-by-step.pdf)
  用于交叉核对平面相机采集及分离视差图流程。
- [Stanford 三维扫描库](https://graphics.stanford.edu/data/3Dscanrep/) 提供兔子模型。
  下载地址、原始压缩包和 PLY 的 SHA256 写入 `test/assets/bunny.source.json`。
  茶壶、球、胡萝卜和深度校验几何体由本项目创建；不是作者原场景。
- [OLAS 官方实现](https://github.com/computational-imaging/olas) 是相关研究，
  未将其中不同的全息合成方法替换为目标论文的方法。

## 第一步：Blender 再中心化采集

所有 Blender 相关实现和脚本均位于 `src/zepholv/blender/`。

```python
from zepholv.blender import Blender, CameraGrid, RenderSettings, render_lightfield

blender = Blender(r'D:\software_fileprocess\blender5.1', low_priority=True)
manifest = render_lightfield(
    blender, 'test/results/custom/capture',
    grid=CameraGrid(views=(10,10), resolution=(1000,1000)),
    scene='teapot_sphere',
    settings=RenderSettings(samples=16, threads=2),
)
```

相机在 `z=D` 平面内均匀移动，光轴保持平行，沿 `-Z` 观察；图像中心锁在
`z=0`。世界 `+Y` 朝上，PNG 的行索引从上到下。固定水平传感器适配时：

```text
W = 2 D tan(image_fov / 2)
shift_x = -camera_x / W
shift_y = -camera_y / W
```

每个视角都会用 Blender 实际投影进行检查，测试另外用解析透视公式核验离面点，
避免仅检查中心而遗漏深度视差方向错误。相机参数、矩阵、标记点和 PNG 校验值
均保存到 `capture/manifest.json`。

默认 CPU 两线程、16 samples、固定种子；原论文没有公开这些渲染参数。
导出每幅 PNG、预览、`.blend`、完整 `.glb`、实际顶点与三角形 JSON。
PNG 使用 Standard 视图变换，宿主侧解 sRGB 后转线性亮度作为强度数据。

## 第二步：Hogel 重排

```python
from zepholv.stereogram import (
    load_perspectives, rearrange_conventional, rearrange_proposed,
    restore_perspectives,
)

p = load_perspectives(manifest, 'test/results/custom/perspectives.npy')
h = rearrange_proposed(p, extraction=(20,20),
                       output='test/results/custom/hogels.npy')
```

输入 `P[V,U,y,x]`，输出 `H[i,j,a,b]`。
公式 (3) 精确实现为 `H[i,j,V,U] = P[V,U,i,j]`。
公式 (4) 的显式补全为：

```text
H[i,j,20V+a,20U+b] = P[V,U,20i+a,20j+b], 0 <= a,b < 20
```

重排阶段不插值、不丢弃像素，每个输入样本恰好出现一次。
测试对非方形整数标签数据逐元素验证，完整运行还会逐视角检查逆映射。
数组采用 NPY 内存映射，按 Hogel 行处理。

## 第三步：物光场与 IFTA

```python
from zepholv.stereogram import object_field, ifta

field = object_field(h[25,25])
solution = ifta(h[25,25], iterations=100,
                checkpoints=(10,30,50,100), seed=2020)
phase = solution.phase
intensity = solution.intensity
```

公式 (2) 的内层平面波叠加由 `ifft2c(sqrt(intensity))` 表示。
IFTA/GS 对 SLM 平面施加均匀幅度约束，对傅里叶平面施加目标幅度约束，
采用正交归一化中心 FFT。输入明确是强度，约束幅度为其平方根。
返回强度按目标总功率归一化，不对结果进行最小二乘增益拟合。

传统分支将 50 × 50 Hogel 强度双线性插值到 200 × 200 后编码；提出方法
直接编码原生 200 × 200。插值核是补充选择，论文未公开该核。
完整运行编码每一个 Hogel，保留所有相位码、量化相位的傅里叶重建强度、
逐 Hogel 指标，以及四个迭代次数的整幅逆映射视图。
全黑 Hogel 不曝光；零相位不能表示无光，因此另存 `active.npy`。

## 第四步：重建与三维可视化

三种结果明确区分：

- `reconstruct_fourier`：逐 Hogel 的相位-only 傅里叶重建，与保存的相位码一致。
- `refocus_lightfield`：所有采集视角的几何移位求和，输出多个焦平面，检验深度/视差。
- `pupil_reconstruction`：2 mm 瞳孔的非相干射线积分。它额外假设角度单元均匀采样；
  公式 (4) 未唯一给出该标定，因此仅为模型诊断。

`angular_spectrum` 是带限自由空间波传播工具，用于单 Hogel 近 SLM 诊断。
不能把几何重聚焦、单 Hogel 波传播或原始网格称为作者的整幅光学三维重建。

生成 13 张覆盖各步骤的 PNG、两个视差 GIF、包含实际完整网格的交互式三维 HTML、
交互式焦平面体和本地报告。原始 `.blend` 与 `.glb` 可直接打开。
PSNR 使用固定峰值 1 和实际参考强度，报告分开绘制实测值与论文参考值。

## 第五步：打印数据与设备边界

```python
from zepholv.stereogram import encode_hogels, export_print_job, OpticalSetup

encode_hogels(h, 'test/results/custom/encoding', iterations=100)
plan = export_print_job('test/results/custom/encoding',
                        'test/results/custom/print', setup=OpticalSetup())
```

每个 Hogel 对应一个完整 SLM PNG 和一条 X/Y/曝光记录。蛇形扫描是实现选择；
论文未公开具体扫描次序。打印计划默认只导出数据。
默认 LUT 为理想线性映射，不是实际设备校准；背景需要光阑。
数值重建还按各 Hogel 的目标总功率归一化，该功率保存在 `metrics.csv`。
这只是明确的数值约定，不代表固定曝光下各 Hogel 的实际亮度已完成标定；
仅测量相位 LUT 也不能替代整条光路的功率、衍射效率及感光响应标定。

真实设备通过 `PrinterBackend` 注入驱动，须提供移动、显示、稳定等待与快门方法。
`execute_print_job` 只接受带明确校准编号和实测 LUT 的任务，异常时关闭快门。
软件测试仅使用模拟后端，不连接任何实际打印设备。
论文的 3000 s 记录时间不能由 `2500×0.2 s` 推导出来；位移/等待开销未公布，
因此输出会分开记录已知曝光时间和未知的机械等待时间。

## 一次完整运行

在激活的 `(zepholv)` 环境、工作区 `D:/pyworks/quanxi` 中执行：

```powershell
python -m pip install -e './Zepholv[test,notebook]'

# 论文尺寸，三个场景，所有 Hogel，完整打印帧与图表。
python -u test/run_reproduction.py --blender 'D:\software_fileprocess\blender5.1' --profile paper --scene all --threads 2

# 小尺寸流程检验，不冒充论文尺寸。
python -u test/run_reproduction.py --blender 'D:\software_fileprocess\blender5.1' --profile validation --scene all --threads 2

# 全部测试，包括真实 Blender 与完整结果证据。
$env:ZEPHOLV_BLENDER = 'D:\software_fileprocess\blender5.1'
$env:ZEPHOLV_RESULTS = (Resolve-Path 'test/results/paper').Path
python -B -m unittest discover -s test -p 'test_*.py' -v

# 同一套测试，同时保存文本日志与 JSON 测试证据。
python -B test/run_tests.py --blender 'D:\software_fileprocess\blender5.1' --results 'test/results/paper'
```

也可直接在 Python 调用：

```python
from zepholv.blender import Blender
from zepholv.stereogram import SynthesisConfig, run_reproduction

run_reproduction(
    Blender(r'D:\software_fileprocess\blender5.1', low_priority=True),
    'test/results/my_experiment',
    config=SynthesisConfig(), scene='teapot_sphere',
)
```

结果主页为 `test/results/paper/index.html`。实验参数或算法源码改变时，
使用新的输出目录；已有目录只恢复相同参数及源码版本的结果，不静默覆盖不同实验。
本次论文尺寸结果由 0.3.0 的默认参数生成，对应程序快照保存在
`test/reference/zepholv-0.3.0-py3-none-any.whl`。最终 0.3.1 修正了自定义迭代检查点
在代表 Hogel 归档中的传递；论文默认检查点及其数值计算保持相同。
重新运行现有论文数据应使用该快照，或给 0.3.1 指定新的 `--output` 目录。
若一次未完成的运行仅因数值源码修正而需要重算，可显式使用
`--restart-incomplete`；它保留采集数据，重新计算未完成实验的编码。
渲染用两个 CPU 线程，FFT 用一个线程，BLAS 限制两个线程，不使用 GPU，
按行处理内存映射数组。论文尺寸数据及完整打印帧会占用数 GB 磁盘。
