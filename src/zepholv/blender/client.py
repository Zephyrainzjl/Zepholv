"""Portable subprocess interface to Blender's own Python interpreter."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class BlenderResult:
    """A completed Blender job. ``data`` is the script's JSON-compatible result."""

    data: Any
    stdout: str
    stderr: str
    returncode: int
    command: tuple[str, ...]
    elapsed: float


class BlenderError(RuntimeError):
    """Blender failed, returned an invalid response, or raised a script exception."""

    def __init__(self, message: str, result: BlenderResult | None = None):
        super().__init__(message)
        self.result = result


class BlenderTimeoutError(BlenderError):
    """The time limit expired; the Blender subprocess was killed and reaped."""


class Blender:
    """Run Blender using an installation directory or executable path.

    Background jobs are independent processes. Use one script for operations
    sharing scene state, or save a .blend file and supply it to the next job.
    Only execute trusted scripts: they have the permissions of the current user.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        low_priority: bool = False,
    ):
        self.executable = self._resolve_executable(path)
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive or None")
        self.timeout = timeout
        self.env = dict(env or {})
        self.low_priority = low_priority

    @staticmethod
    def _resolve_executable(path: str | os.PathLike[str]) -> Path:
        supplied = Path(path).expanduser().resolve()
        if supplied.is_dir():
            names = ("blender.exe", "blender") if os.name == "nt" else ("blender", "blender.exe")
            candidates = [supplied / name for name in names]
            candidates += [
                supplied / "Contents" / "MacOS" / "Blender",
                supplied / "Blender.app" / "Contents" / "MacOS" / "Blender",
            ]
        else:
            candidates = [supplied]
        for candidate in candidates:
            if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
                return candidate
        raise FileNotFoundError(f"No Blender executable found at {supplied}")

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        # Host virtual environments must not replace Blender's bundled Python.
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        environment.update(self.env)
        return environment

    @staticmethod
    def _file(path: str | os.PathLike[str]) -> Path:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        return resolved

    def command(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
        cwd: str | os.PathLike[str] | None = None,
        check: bool = True,
    ) -> BlenderResult:
        """Run arbitrary Blender CLI arguments synchronously without a shell.

        ``timeout=None`` uses the instance default. Output is captured as UTF-8.
        Use ``launch`` for an interactive window instead of this blocking method.
        """
        if isinstance(args, (str, bytes)):
            raise TypeError("args must be a sequence of arguments, not a command string")
        limit = self.timeout if timeout is None else timeout
        if limit is not None and limit <= 0:
            raise ValueError("timeout must be positive or None")
        command = (str(self.executable), *(str(arg) for arg in args))
        started = time.monotonic()
        try:
            process = subprocess.run(
                command,
                cwd=cwd,
                env=self._environment(),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=limit,
                creationflags=(subprocess.CREATE_NO_WINDOW | (
                    subprocess.BELOW_NORMAL_PRIORITY_CLASS if self.low_priority else 0
                )) if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            def decode(value: str | bytes | None) -> str:
                return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""

            result = BlenderResult(
                None, decode(exc.stdout), decode(exc.stderr), -1,
                command, time.monotonic() - started,
            )
            raise BlenderTimeoutError(f"Blender exceeded timeout of {limit} seconds", result) from exc
        except OSError as exc:
            raise BlenderError(f"Unable to start Blender: {exc}") from exc
        result = BlenderResult(
            None, process.stdout, process.stderr, process.returncode,
            command, time.monotonic() - started,
        )
        if check and result.returncode:
            raise BlenderError(f"Blender exited with code {result.returncode}\n{result.stderr or result.stdout}", result)
        return result

    def version(self) -> str:
        """Return Blender's first version line."""
        return self.command(["--version"]).stdout.splitlines()[0]

    def run(
        self,
        code: str,
        *,
        params: Mapping[str, Any] | None = None,
        blend_file: str | os.PathLike[str] | None = None,
        timeout: float | None = None,
        cwd: str | os.PathLike[str] | None = None,
        factory_startup: bool = True,
        extra_args: Sequence[str] = (),
        script_args: Sequence[str] = (),
    ) -> BlenderResult:
        """Execute Python with full bpy access in a fresh background Blender.

        The script receives ``bpy`` and ``params``. Assign JSON-compatible output
        to ``result`` to receive it as ``BlenderResult.data``. Blender objects,
        vectors and arrays must first be converted to JSON-compatible values.
        """
        if not isinstance(code, str):
            raise TypeError("code must be a Python source string")
        return self._execute(
            code=code, script=None, params=params, blend_file=blend_file,
            timeout=timeout, cwd=cwd, factory_startup=factory_startup,
            extra_args=extra_args, script_args=script_args,
        )

    def run_script(
        self,
        script: str | os.PathLike[str],
        *,
        params: Mapping[str, Any] | None = None,
        blend_file: str | os.PathLike[str] | None = None,
        timeout: float | None = None,
        cwd: str | os.PathLike[str] | None = None,
        factory_startup: bool = True,
        extra_args: Sequence[str] = (),
        script_args: Sequence[str] = (),
    ) -> BlenderResult:
        """Execute a .py file, preserving __file__ and sibling imports.

        Inside the script, sys.argv is [script_path, *script_args]. Source file
        encoding declarations are honored by Blender's Python interpreter.
        """
        return self._execute(
            code=None, script=str(self._file(script)), params=params,
            blend_file=blend_file, timeout=timeout, cwd=cwd,
            factory_startup=factory_startup, extra_args=extra_args,
            script_args=script_args,
        )

    def _execute(
        self, *, code, script, params, blend_file, timeout, cwd,
        factory_startup, extra_args, script_args,
    ) -> BlenderResult:
        if isinstance(extra_args, (str, bytes)) or isinstance(script_args, (str, bytes)):
            raise TypeError("extra_args and script_args must be sequences, not strings")
        blend = self._file(blend_file) if blend_file is not None else None
        payload = {
            "code": code, "script": script, "params": dict(params or {}),
            "argv": [str(arg) for arg in script_args],
        }
        # Validate before launching Blender, and never put source code in a shell.
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        with tempfile.TemporaryDirectory(prefix="zepholv-blender-") as temporary:
            directory = Path(temporary)
            request = directory / "request.json"
            response = directory / "response.json"
            request.write_text(serialized, encoding="utf-8")
            args = ["--background"]
            if factory_startup:
                args.append("--factory-startup")
            args.extend(str(arg) for arg in extra_args)
            if blend is not None:
                args.append(str(blend))
            args.extend([
                "--python-exit-code", "1", "--python",
                str(Path(__file__).with_name("_runner.py")),
                "--", str(request), str(response),
            ])
            process = self.command(args, timeout=timeout, cwd=cwd, check=False)
            try:
                reply = json.loads(response.read_text(encoding="utf-8"))
                if not isinstance(reply, dict) or not isinstance(reply.get("ok"), bool):
                    raise ValueError("invalid response envelope")
            except (OSError, ValueError) as exc:
                raise BlenderError(
                    f"Blender did not return a valid response (exit {process.returncode}).\n"
                    f"{process.stderr}\n{process.stdout}", process,
                ) from exc
            result = BlenderResult(
                reply.get("result"), process.stdout, process.stderr,
                process.returncode, process.command, process.elapsed,
            )
            if not reply["ok"] or process.returncode:
                raise BlenderError(
                    reply.get("traceback") or f"Blender exited with code {process.returncode}", result,
                )
            return result

    def call(
        self, operator: str, *, kwargs: Mapping[str, Any] | None = None,
        blend_file: str | os.PathLike[str] | None = None,
        save_to: str | os.PathLike[str] | None = None,
        timeout: float | None = None,
    ) -> BlenderResult:
        """Call an operator such as 'mesh.primitive_cube_add' with keyword args.

        The operator runs in the default background context. For selection,
        overrides, execution context or multiple operations, use ``run``.
        """
        name = operator.removeprefix("bpy.ops.")
        if len(name.split(".")) != 2 or not all(part.isidentifier() for part in name.split(".")):
            raise ValueError("operator must have the form 'category.operator'")
        return self.run(
            "category, name = params['operator'].split('.')\n"
            "status = getattr(getattr(bpy.ops, category), name)(**params['kwargs'])\n"
            "if 'FINISHED' not in status:\n"
            "    raise RuntimeError('Operator did not finish: ' + repr(status))\n"
            "if params['save_to']:\n"
            "    bpy.ops.wm.save_as_mainfile(filepath=params['save_to'])\n"
            "result = sorted(status)\n",
            params={
                "operator": name, "kwargs": dict(kwargs or {}),
                "save_to": str(Path(save_to).expanduser().resolve()) if save_to is not None else None,
            },
            blend_file=blend_file, timeout=timeout,
        )

    def render(
        self, blend_file: str | os.PathLike[str], output: str | os.PathLike[str],
        *, frame: int = 1, engine: str | None = None,
        resolution: tuple[int, int] | None = None, image_format: str = "PNG",
        timeout: float | None = None,
    ) -> BlenderResult:
        """Render one frame of an existing scene with its configured camera.

        ``engine`` is a Blender engine identifier, e.g. 'CYCLES' or
        'BLENDER_EEVEE'. More advanced rendering is available through ``run``.
        """
        if resolution is not None and (len(resolution) != 2 or any(value <= 0 for value in resolution)):
            raise ValueError("resolution must contain two positive dimensions")
        destination = Path(output).expanduser().resolve()
        return self.run(
            "from pathlib import Path\n"
            "scene = bpy.context.scene\n"
            "scene.frame_set(params['frame'])\n"
            "if params['engine']:\n"
            "    scene.render.engine = params['engine']\n"
            "if params['resolution']:\n"
            "    scene.render.resolution_x, scene.render.resolution_y = params['resolution']\n"
            "    scene.render.resolution_percentage = 100\n"
            "Path(params['output']).parent.mkdir(parents=True, exist_ok=True)\n"
            "scene.render.filepath = params['output']\n"
            "scene.render.image_settings.file_format = params['format']\n"
            "bpy.ops.render.render(write_still=True)\n"
            "output = scene.render.filepath\n"
            "if scene.render.use_file_extension:\n"
            "    output = bpy.path.ensure_ext(output, scene.render.file_extension)\n"
            "result = {'output': output, 'frame': scene.frame_current}\n",
            params={"frame": frame, "engine": engine, "resolution": resolution,
                    "format": image_format, "output": str(destination)},
            blend_file=blend_file, timeout=timeout,
        )

    def launch(
        self, blend_file: str | os.PathLike[str] | None = None, *,
        args: Sequence[str] = (), cwd: str | os.PathLike[str] | None = None,
    ) -> subprocess.Popen:
        """Open Blender's GUI and return immediately with the process handle.

        This launches a new instance; it does not attach to an already open UI.
        """
        if isinstance(args, (str, bytes)):
            raise TypeError("args must be a sequence of arguments")
        command = [str(self.executable)]
        if blend_file is not None:
            command.append(str(self._file(blend_file)))
        command.extend(str(arg) for arg in args)
        try:
            return subprocess.Popen(command, cwd=cwd, env=self._environment())
        except OSError as exc:
            raise BlenderError(f"Unable to open Blender: {exc}") from exc
