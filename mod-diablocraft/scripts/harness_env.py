"""Shared environment for tests that run a compiled harness binary.

Expected crashes are normal here: the mutation harnesses abort() on purpose to
prove their assertions can fail. On this host `kernel.core_pattern` is a pipe to
apport, so the kernel pipes a core to apport even with `ulimit -c 0`; apport then
runs its Python handler for every one of them (they filled `/var/crash`).

Setting RLIMIT_CORE to exactly 1 byte makes the kernel refuse the core before it
reaches apport, so no report is filed. Use this module only for the subprocess
that runs a compiled test/harness binary -- never for worldserver, authserver,
the launch wrappers or deploy scripts.

    import harness_env
    ran = harness_env.run([str(binary)], capture_output=True, text=True)

`run()` forwards every keyword argument to `subprocess.run`. On POSIX it adds
the core limit; on Windows there is no RLIMIT_CORE and `preexec_fn` is
unsupported, so it adds nothing.

`run()` also refuses (RuntimeError) when a test script of this checkout on the call
stack is in neither RUNNERS nor COMPILE_ONLY of test_harness_core_limit.py. That
file's glob scan finds a new runner left out of RUNNERS only when that one file runs,
which a worker running just the tests near a change never does; here the same rule
rides on the new runner's own run (diablocraft-runner-check-per-test).

`build()` is the compile cache. A template that compiles one harness again for every case
or row mutant calls it instead of its own compiler line:

    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"],
                               files={"combat/dc_item_power_math.h": header_text})
    ran = harness_env.run([str(binary), str(cases_file)], capture_output=True, text=True)

Same sources, same `files` text, same flags and the same header contents give the same
binary from one compile. `files` is staged by content and put first on the include path, so
a mutant is just different text. The binary lives in the cache folder: read it, run it with
absolute paths, never write to it or delete it. Why a hit is never stale: see `_object`.
`build()` also refuses a test script that is not registered, like `run()`.
"""
import atexit
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
CORE_LIMIT_BYTES = 1


def private_scratch(shared):
    """`shared` with this process's id on the end, removed when the process ends.

    A test that writes into one fixed `_agent-scratch/<name>` folder fails at random when two panes run it at once
    (diablocraft-slwha). The folder is not made here; the test makes it where it did before."""
    path = Path(shared)
    path = path.with_name(f"{path.name}-{os.getpid()}")
    atexit.register(shutil.rmtree, path, True)
    return path


def private_name(name):
    """A database name for this process on the shared fixture mysqld: `name` and the process id (64 characters at most)."""
    return f"{name}_{os.getpid()}"


def limit_core():
    """Set RLIMIT_CORE to 1 byte in the calling process (POSIX only)."""
    if os.name == "posix":
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (CORE_LIMIT_BYTES, CORE_LIMIT_BYTES))


def _preexec():
    return limit_core if os.name == "posix" else None


def _refuse_unregistered_tests():
    """Raise when a test script of this checkout on the call stack is not registered."""
    import test_harness_core_limit as registry  # lazy: that module imports this one
    known = set(registry.RUNNERS) | set(registry.COMPILE_ONLY)
    frame = sys._getframe()
    while frame:
        path, frame = frame.f_globals.get("__file__") or "", frame.f_back
        if not os.path.basename(path).startswith("test_"):
            continue
        try:
            name = registry.rel(Path(path).resolve())
        except ValueError:  # outside this checkout (a scratch script): no entry it could be given
            continue
        if name not in known:
            raise RuntimeError(
                "%s runs a binary through harness_env.run but is not in RUNNERS: add it to RUNNERS "
                "in mod-diablocraft/scripts/tests/tooling/test_harness_core_limit.py" % name)


def run(argv, **kwargs):
    """subprocess.run with RLIMIT_CORE=1 on POSIX; refuses a test script that is not registered."""
    _refuse_unregistered_tests()
    if os.name == "posix":
        kwargs.setdefault("preexec_fn", _preexec())
    return subprocess.run(argv, **kwargs)



# ---- the compile cache -------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[2]
CACHE_ENV = "DC_HARNESS_CACHE"
KEEP_SECONDS = 3 * 24 * 3600  # an entry nobody used for this long is deleted by the next build()
compiles = []  # one (source or "link") per compiler run, so a test can count them
_compiler_ids = {}
_pruned = set()


class BuildError(AssertionError):
    """The compiler or linker failed; `.stderr` is its whole output."""

    def __init__(self, what, stderr):
        super().__init__("%s did not compile:\n%s" % (what, stderr[-3000:]))
        self.stderr = stderr


def cache_dir():
    """The cache folder: DC_HARNESS_CACHE, else the shared scratch folder (never committed)."""
    return Path(os.environ.get(CACHE_ENV) or REPO / "azerothcore-wotlk/build/_agent-scratch/harness-cache")


def _digest(*parts):
    h = hashlib.blake2b(digest_size=16)
    for part in parts:
        data = part if isinstance(part, bytes) else str(part).encode("utf-8")
        h.update(len(data).to_bytes(8, "little"))
        h.update(data)
    return h.hexdigest()


def _file_digest(path):
    return hashlib.blake2b(Path(path).read_bytes(), digest_size=16).hexdigest()


def _compiler():
    found = shutil.which("c++") or shutil.which("g++")
    if not found:
        raise unittest.SkipTest("no C++ compiler")
    if found not in _compiler_ids:
        version = subprocess.run([found, "--version"], capture_output=True, text=True).stdout
        _compiler_ids[found] = _digest(os.path.realpath(found), version)
    return found, _compiler_ids[found]


# Options whose value is a path the compiler reads relative to the working folder. A value is made
# absolute before it reaches the key or the command, so the same text from another folder is another entry.
_DIR_OPTIONS = ("-isystem", "-iquote", "-idirafter", "-I", "-L")  # a folder, found or not
_FILE_OPTIONS = ("-include", "-imacros")  # a file, left alone when it is only on the include path


def _absolute(args):
    """`args` with the path of every -I/-isystem/-iquote/-idirafter/-L/-include/-imacros made absolute."""
    out, args, i = [], list(args), 0
    while i < len(args):
        arg = args[i]
        for option in _DIR_OPTIONS + _FILE_OPTIONS:
            if arg == option and i + 1 < len(args):
                out += [option, _resolve(option, args[i + 1])]
                i += 1
                break
            if arg.startswith(option) and arg != option and option in _DIR_OPTIONS:
                out.append(option + _resolve(option, arg[len(option):]))
                break
        else:
            out.append(arg)
        i += 1
    return out


def _resolve(option, path):
    if option in _FILE_OPTIONS and not os.path.exists(path):
        return path
    return os.path.abspath(path)


def _link_inputs(link_flags):
    """The digest of every link argument that names a file (a library or object), so its path and content are in the key."""
    return [part for arg in link_flags if not arg.startswith("-") and os.path.isfile(arg)
            for part in (os.path.abspath(arg), _file_digest(arg))]


def _publish(tmp, final):
    """Move a finished folder into place; the first of two builders racing for it wins."""
    try:
        os.rename(tmp, final)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)


def _prune(root):
    """Once per process and hour: delete entries unused for KEEP_SECONDS (a hit touches its folder)."""
    marker = root / ".pruned"
    if str(root) in _pruned:
        return
    _pruned.add(str(root))
    try:
        if time.time() - marker.stat().st_mtime < 3600:
            return
    except OSError:
        pass
    marker.touch()
    cutoff = time.time() - KEEP_SECONDS
    for kind in ("obj", "bin", "stage", "text"):
        try:
            entries = list((root / kind).iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                pass


def _stage(root, files):
    """Write `files` ({relative path: text}) once per content; the folder that goes on the include path."""
    items = sorted((name, text.encode("utf-8") if isinstance(text, str) else text) for name, text in files.items())
    key = _digest(*[part for name, data in items for part in (name, data)])
    final = root / "stage" / key
    if not final.is_dir():
        (root / "stage").mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="tmp-", dir=str(root / "stage")))
        for name, data in items:
            (tmp / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp / name).write_bytes(data)
        _publish(tmp, final)
    os.utime(final)
    return final


def _dependencies(depfile, skip):
    """The files a make-style .d file lists (after the target), without the staged ones."""
    text = depfile.read_text(encoding="utf-8").replace("\\\n", " ")
    names, word, i = [], "", 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] == " ":
            word, i = word + " ", i + 2
            continue
        if ch.isspace():
            if word:
                names.append(word)
            word = ""
        else:
            word += ch
        i += 1
    if word:
        names.append(word)
    names = [os.path.abspath(n) for n in names[1:]]
    return [n for n in names if not n.startswith(str(skip))]


def _object(root, cc, cid, source, flags, includes, stage):
    """The compiled object of one source -> (object path, its digest).

    The key is the compiler, the flags, the include arguments, the staged text and the source's own
    path and bytes. What it cannot see are the headers the source pulls in from the repo: the
    entry's deps.json lists every one the compiler read, with its content digest, and a hit is
    served only after each of them is read again and still matches. A changed header therefore
    compiles again under the same key, and a hit still reads the files, which is how the runner's
    strace sees the test depend on them.
    """
    source = Path(source).resolve()
    key = _digest(cid, *flags, "--", *[str(i) for i in includes], "--", stage, source, source.read_bytes())
    final = root / "obj" / key
    try:
        meta = json.loads((final / "deps.json").read_text(encoding="utf-8"))
        if all(_file_digest(path) == digest for path, digest in meta["deps"]):
            os.utime(final)
            return final / "main.o", meta["object"]
    except (OSError, ValueError, KeyError):
        pass
    (root / "obj").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="tmp-", dir=str(root / "obj")))
    args = [cc, *flags, "-I", str(stage), *sum((["-I", str(i)] for i in includes), []),
            "-MMD", "-MF", str(tmp / "main.d"), "-c", str(source), "-o", str(tmp / "main.o")]
    compiles.append(str(source))
    built = subprocess.run(args, capture_output=True, text=True)
    if built.returncode:
        shutil.rmtree(tmp, ignore_errors=True)
        raise BuildError(source.name, built.stderr)
    deps = [[d, _file_digest(d)] for d in _dependencies(tmp / "main.d", root / "stage")]
    meta = {"deps": deps, "object": _file_digest(tmp / "main.o")}
    (tmp / "deps.json").write_text(json.dumps(meta), encoding="utf-8")
    shutil.rmtree(final, ignore_errors=True)  # a stale entry under this key: its header changed
    _publish(tmp, final)
    return final / "main.o", meta["object"]


def build(sources, flags=(), files=None, includes=(), link_flags=()):
    """Compile `sources` (.cpp paths) and link them; the same inputs give the same binary from one compile.

    flags       go to every compile and to the link (-std=c++17, -O1, -fsanitize=...)
    files       {relative path: text}, staged by content and put first on the include path
    includes    more -I folders, for headers that stay in the repo (relative ones are taken from the working folder)
    link_flags  the link only (-pthread, -l...)
    Returns the binary's path (see the module docstring for what it may be used for). Each source
    is its own cached object, so a source shared by many harnesses (dc_common.cpp) compiles once;
    a binary is keyed on the digests of its objects. Raises BuildError, never cached.
    """
    _refuse_unregistered_tests()
    cc, cid = _compiler()
    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    _prune(root)
    flags = _absolute(flags)
    link_flags = _absolute(link_flags)
    includes = [os.path.abspath(i) for i in includes]
    stage = _stage(root, files or {})
    objects = [_object(root, cc, cid, source, flags, includes, stage) for source in sources]
    key = _digest(cid, *flags, "--", *link_flags, "--", *_link_inputs(link_flags), "--", *[digest for _, digest in objects])
    final = root / "bin" / key
    if (final / "harness").is_file():
        os.utime(final)
        return final / "harness"
    (root / "bin").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="tmp-", dir=str(root / "bin")))
    compiles.append("link")
    linked = subprocess.run([cc, *flags, *[str(o) for o, _ in objects], *link_flags, "-o", str(tmp / "harness")],
                            capture_output=True, text=True)
    if linked.returncode:
        shutil.rmtree(tmp, ignore_errors=True)
        raise BuildError("link of " + " ".join(Path(s).name for s in sources), linked.stderr)
    _publish(tmp, final)
    return final / "harness"


def stage_files(files):
    """The folder holding `files` ({relative path: text or bytes}), made once per content: for a harness that includes headers by
    relative path. Read it, never write to it."""
    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    return _stage(root, files)


def build_text(code, flags=(), includes=(), extra=(), link_flags=(), files=None):
    """`build` for a harness that is a string: it is written once under the cache's text/ folder, named by its digest, so the same
    text is the same source path and the same object. `extra` are more source files (compiled to cached objects of their own);
    `files` are staged headers, as in `build`."""
    root = cache_dir()
    folder = root / "text" / _digest(code)
    source = folder / "harness.cpp"
    if not source.is_file():
        (root / "text").mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="tmp-", dir=str(root / "text")))
        (tmp / "harness.cpp").write_text(code, encoding="utf-8")
        _publish(tmp, folder)
    os.utime(folder)
    return build([source, *extra], flags=flags, files=files, includes=includes, link_flags=link_flags)


_VALUE_FLAGS = ("-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros", "-D", "-U", "-L", "-l")


def run_cpp(code, extra=(), includes=None, flags=("-std=c++17", "-O0", "-UNDEBUG")):
    """Compile (cached) and run one harness string: (exit code was 0, stdout + stderr). A compile failure raises BuildError.

    The contract of test_class_parity.run, which the crafting, items, rifts and bounties tests used: -std=c++17 -O0 -UNDEBUG, the
    module's src/common and src/paragon on the include path, `extra` source files linked in and `extra` flags (`-I`, dir) passed on."""
    if includes is None:
        includes = [REPO / "mod-diablocraft/src/common", REPO / "mod-diablocraft/src/paragon"]
    sources, flags = [], list(flags)
    for item in extra:   # test_class_parity.run put these after the source on the command line: more sources, or compiler flags
        item = str(item)
        if item.startswith("-") or (flags and flags[-1] in _VALUE_FLAGS):
            flags.append(item)
        else:
            sources.append(item)
    binary = build_text(code, flags=flags, includes=includes, extra=sources)
    ran = run([str(binary)], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout + ran.stderr
