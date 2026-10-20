"""Executed by Blender's bundled Python, not the host interpreter.

Keep this file standalone: Zepholv need not be installed inside Blender.
"""

import json
from pathlib import Path
import sys
import tokenize
import traceback


def main():
    separator = sys.argv.index("--")
    request_path, response_path = sys.argv[separator + 1:separator + 3]
    try:
        request = json.loads(Path(request_path).read_text(encoding="utf-8"))
        import bpy

        source_path = request["script"]
        if source_path:
            with tokenize.open(source_path) as stream:
                code = stream.read()
            sys.path.insert(0, str(Path(source_path).parent))
        else:
            code = request["code"]
            source_path = "<zepholv-blender>"
            sys.path.insert(0, str(Path.cwd()))
        sys.argv = [source_path, *request["argv"]]
        namespace = {
            "__name__": "__main__", "__file__": source_path,
            "bpy": bpy, "params": request["params"], "result": None,
        }
        exec(compile(code, source_path, "exec"), namespace)
        response = {"ok": True, "result": namespace["result"]}
        # Serialize here so a non-JSON result becomes a useful remote exception.
        serialized = json.dumps(response, ensure_ascii=False, allow_nan=False)
    except BaseException:
        error = traceback.format_exc()
        Path(response_path).write_text(
            json.dumps({"ok": False, "traceback": error}, ensure_ascii=False),
            encoding="utf-8",
        )
        raise
    Path(response_path).write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
