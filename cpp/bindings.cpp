#include <pybind11/pybind11.h>

// Reserve the import path zepholv._native. Add bindings with module.def(...).
PYBIND11_MODULE(_native, module) {
    module.doc() = "Reserved C++ extension for Zepholv; no bindings yet.";
}
