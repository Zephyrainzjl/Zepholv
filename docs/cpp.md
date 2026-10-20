# C++ 扩展预留

扩展模块名为 `zepholv._native`，绑定位置为 `cpp/bindings.cpp`。
当前只有可编译的空模块，没有业务函数，Python 包入口不主动导入它。
普通 Python 安装无需 C++ 编译器。

## 本地构建

需要支持 C++17 的编译器；Windows 可使用 Visual Studio Build Tools 的
“使用 C++ 的桌面开发”工作负载。在项目根目录执行：

```console
python -m pip install -e ".[cpp]"
python -m pybind11 --cmakedir
```

将上条命令输出的路径填入下面的 `<pybind11-cmake-directory>`，
将 `python -c "import sys; print(sys.executable)"` 的输出填入
`<python-executable>`，以确保扩展使用当前环境：

```console
cmake -S cpp -B build/cpp -Dpybind11_DIR="<pybind11-cmake-directory>" -DPython_EXECUTABLE="<python-executable>"
cmake --build build/cpp --config Release
cmake --install build/cpp --config Release --prefix src
python -c "import zepholv._native; print(zepholv._native.__doc__)"
```

安装步骤会把 `.pyd`（Windows）或 `.so`（Linux/macOS）放到
`src/zepholv/`，用于上述可编辑安装环境的本地开发。

## 后续接入

在 `cpp/` 下添加 C++ 实现文件，将它们加入 `pybind11_add_module`，
并在 `bindings.cpp` 中注册函数或类。此时 C++ 构建独立于 Python 打包；
若需要把原生扩展随 wheel 分发，再将构建后端接入 CMake
（例如采用 scikit-build-core），并配置各平台构建。
当前纯 Python wheel 不包含手工编译的扩展。
