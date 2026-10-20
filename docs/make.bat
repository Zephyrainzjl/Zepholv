@echo off
setlocal
pushd "%~dp0"
if "%~1"=="" (
    python -m sphinx -M help . _build
) else (
    python -m sphinx -M %* . _build
)
set "SPHINX_RESULT=%ERRORLEVEL%"
popd
exit /b %SPHINX_RESULT%
