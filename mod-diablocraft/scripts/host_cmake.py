"""cmake for the harness tests, on whichever host runs them.

Ten tests hardcoded C:/Program Files/CMake/bin/cmake.exe, the Visual Studio
generator and build/Release/<name>.exe, so they could only run on the old
Windows host (diablocraft-lx43). test_potion.py already did this per file; this is
the one copy for the rest. Windows still gets Visual Studio and the Release
subfolder; elsewhere cmake comes from PATH and the default generator writes the
binary straight into build/.
"""
import os
import shutil
import sys
from pathlib import Path


def cmake():
    found = shutil.which("cmake")
    if not found:
        raise SystemExit("cmake is not on PATH; this harness compiles a small C++ program")
    return found


def undebug():
    """The compile option that keeps assert() alive in a Release build."""
    return "/UNDEBUG" if os.name == "nt" else "-UNDEBUG"


def commands(source, build, name, fresh=True):
    """(configure, build, binary) for the project in `source`, built into `build`. `--fresh` by
    default: a scratch build folder left by another host holds a cache naming that host's paths."""
    tool = cmake()
    configure = [tool] + (["--fresh"] if fresh else []) + ["-S", str(source), "-B", str(build)]
    compile_ = [tool, "--build", str(build)]
    if os.name == "nt":
        configure += ["-G", "Visual Studio 17 2022", "-A", "x64"]
        compile_ += ["--config", "Release", "--", "-m:1"]
    binary = Path(build) / ("Release/%s.exe" % name if os.name == "nt" else name)
    return configure, compile_, str(binary)


def environment():
    """The environment the build runs in. Windows upper-cases every key (MSBuild
    reads Path and PATH as one); elsewhere the environment is passed through."""
    if os.name == "nt":
        return {key.upper(): value for key, value in os.environ.items()}
    return dict(os.environ)
