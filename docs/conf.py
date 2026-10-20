"""Minimal Sphinx configuration."""

from importlib.metadata import version as package_version

project = "Zepholv"
release = package_version("Zepholv")
version = release
extensions = ["myst_parser"]
source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = ["_build"]
language = "zh_CN"
html_theme = "alabaster"
