# 安装与开发

在项目根目录安装，要求 Python 3.10 或更高版本：

```console
python -m pip install -e .
```

检查包入口：

```python
import zepholv

print(zepholv.__version__)
```

在 `src/zepholv/zepholv.py` 添加 Python 功能，随后按需在
`src/zepholv/__init__.py` 显式导出公共接口。版本号由 `pyproject.toml`
统一维护，更新版本后需要重新安装以刷新安装元数据。

测试放在安装包外、与 `Zepholv/` 平级的 `../test/` 下，以 `test_` 开头命名。
以下命令在 `Zepholv/` 内执行：

```console
python -m unittest discover -s ../test -v
```

文档依赖通过 `python -m pip install -e ".[docs]"` 安装，随后执行
`python -m sphinx -M html docs docs/_build`。也可在 `docs/` 中运行
`make html`（Linux/macOS）或 `make.bat html`（Windows）。
