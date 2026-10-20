cmake_minimum_required(VERSION 3.18)
project(zepholv_native LANGUAGES CXX)

set(PYBIND11_FINDPYTHON ON)
find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_native MODULE bindings.cpp)
target_compile_features(_native PRIVATE cxx_std_17)

# Install into a staging directory containing the zepholv package.
install(TARGETS _native
    LIBRARY DESTINATION zepholv
    RUNTIME DESTINATION zepholv
)
