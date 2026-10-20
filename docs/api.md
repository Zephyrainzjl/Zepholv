# API 索引与数据约定

全部 Blender API 从 `zepholv.blender` 导入；全息体视图 API 从
`zepholv.stereogram` 导入。论文流程已在本机 Blender 5.1.2、Python 3.10 环境
验证；更老版本 Blender 的模型导入、材质和渲染接口可能不同。

## Blender

| API | 输入 | 返回与作用 |
|---|---|---|
| `Blender(path, timeout=None, env=None, low_priority=False)` | 软件目录或可执行文件 | 外部 Blender 调用对象，不导入宿主 `bpy` |
| `Blender.run(code, params=..., blend_file=...)` | 源码、JSON 参数、可选场景 | `BlenderResult`；代码中 `result` 进入 `.data` |
| `Blender.run_script(script, ...)` | Python 文件 | 同上，保留文件名与同目录导入 |
| `Blender.call(operator, kwargs=..., save_to=...)` | `bpy.ops` 算子名称 | 单算子调用，可保存场景 |
| `Blender.render(blend_file, output, ...)` | 场景和图片路径 | 渲染一帧；`data['output']` 为保存路径 |
| `Blender.command(args)` | 命令行参数列表 | 完整 CLI；返回日志与状态 |
| `Blender.launch(blend_file=None, args=...)` | 可选场景/启动参数 | 新 GUI 进程句柄，不连接既有窗口 |
| `CameraGrid(views=..., resolution=...)` | `(行,列)` 尺寸、米、度 | 可独立查询任意相机 `camera(row,column)` |
| `RenderSettings(samples=16, threads=2, ...)` | CPU 渲染设置 | 固定种子、采样、线程与逐帧暂停 |
| `render_lightfield(blender, output, ...)` | 网格、内置场景与资源 | `manifest.json` 路径；生成完整采集数据 |
| `download_stanford_bunny(destination)` | 明确的目标 PLY 路径 | 校验过的模型路径及旁置来源 JSON |

## Hogel 与编码

| API | 输入数据约定 | 返回 |
|---|---|---|
| `SynthesisConfig()` | 默认论文尺寸与显式补全选项 | 不可变配置；`validation()` 为小尺寸配置 |
| `paper_audit()` | 无 | 已知参数、歧义、额外选择，`exact_reproduction=False` |
| `load_perspectives(manifest, output)` | 完成的采集清单 | 内存映射 `P[V,U,y,x]`，float32 线性亮度 |
| `rearrange_conventional(P, output=...)` | 四维灰度视角数组 | `H[y,x,V,U]`，公式 (3) |
| `rearrange_proposed(P, extraction=(20,20), output=...)` | 高分辨率视角数组 | 可逆块排列的 Hogel 数组，不插值 |
| `restore_perspectives(H, extraction=..., output=...)` | Hogel 数组 | 原生视角数组，逐像素逆映射 |
| `perspective_from_hogels(H,row,column,extraction=...)` | 一组 Hogel 及源相机坐标 | 一幅原生分辨率视角图 |
| `object_field(intensity)` | 单 Hogel 角强度 | 公式 (2) 对应的复物光场 |
| `fft2c(field)` / `ifft2c(field)` | 二维复场 | 正交归一化中心傅里叶正/逆变换 |
| `ifta(intensity, iterations=100, ...)` | 单 Hogel 强度，不是幅度 | `IFTAResult.phase/intensity/snapshots/mse_history` |
| `encode_hogels(H, output, ...)` | 所有 Hogel，按行流式读取 | 编码清单路径；保存每个相位码和对应重建强度 |
| `quantize_phase(phase,levels=256)` | 弧度相位 | uint8 相位级编号，周期取模 |
| `decode_phase(codes,levels=256)` | 相位级编号 | float32 弧度相位 |
| `reconstruct_fourier(phase,total_power=...)` | 相位与总功率 | 均匀照明下的傅里叶重建强度 |
| `psnr(reference,reconstructed,peak=1)` | 同形强度参考与重建 | 不做增益拟合的固定峰值 PSNR，单位 dB |

`SynthesisConfig.phase_levels=None` 表示默认连续相位优化、256 级打印编码；
指定整数可改变完整流水线的最终相位编码级数。单独调用
`ifta(..., phase_levels=8)` 则会在迭代内施加八级相位约束。
`depth_separation_m` 记录论文的 40 mm 设定；提供的内置茶壶与球场景固定使用
该间隔。自定义场景需通过 Blender 脚本建立并使用各步骤 API 处理。

## 重建与打印

| API | 作用与边界 |
|---|---|
| `refocus_lightfield(P, grid, depth_m=..., output_shape=...)` | 已标定采集坐标中的几何重聚焦，非光学实验 |
| `pupil_reconstruction(H, eye_m=..., ...)` | 明确均匀角采样假设下的非相干瞳孔积分 |
| `angular_spectrum(field, wavelength_m=..., pixel_pitch_m=..., distance_m=...)` | 单复场带限自由空间传播，非完整光路模拟 |
| `OpticalSetup(...)` | 论文光学参数及未给出标定量的显式记录 |
| `diffraction_limit(wavelength_m,aperture_m)` | 返回 `λ/ρ` 的弧度与角度，未篡改为原文错误数值 |
| `slm_frame(codes, shape=..., lut=...)` | 原尺寸相位块居中显示，外部区域需物理光阑 |
| `export_print_job(encoding,output,...)` | 导出每一帧 PNG 和完整 X/Y/曝光计划，不操作硬件 |
| `PrinterBackend` | 自备 SLM、位移台和快门的设备协议 |
| `execute_print_job(manifest, backend)` | 仅在给出实测 LUT 与校准编号后调用自备驱动 |

## 流水线与图表

```python
from zepholv.stereogram import run_reproduction, visualize_reproduction, index_reproductions
```

`run_reproduction` 执行所有步骤；`visualize_reproduction(output)` 可从已完成数据
重新生成图表和 HTML，避免重新渲染或编码；`index_reproductions(root)` 链接多个场景。
`low_impact(threads=2)` 可用于包裹自定义数值流程，限制 BLAS 线程并临时降低
Windows 进程优先级，退出时恢复。

大型数组默认采用 float32；相位码为 uint8，激活标记为 bool。所有 `.npy` 均可
通过 `numpy.load(path,mmap_mode='r')` 按需读取，避免一次加载完整实验。
