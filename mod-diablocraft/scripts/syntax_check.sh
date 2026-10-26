#!/usr/bin/env bash
# The compile-only check (AGENTS.md "How work moves" 3) for a changed .cpp, run from the
# checkout you are in (diablocraft-worktree-pilot-fixes, item 3).
#
#     bash mod-diablocraft/scripts/syntax_check.sh mod-diablocraft/src/combat/x.cpp [more.cpp ...]
#
# It takes the file's entry from the live build's compile_commands.json (flags, defines,
# include paths: the pinned core), drops the output and dependency options, adds
# -fsyntax-only and runs the compiler. The live build was configured in the MAIN
# checkout, so its -I paths name main's mod-diablocraft; in a linked worktree a bare
# `c++ -fsyntax-only` would read main's headers and miss a change made in the worktree
# (a #error planted in the worktree's common/dc_version.h was not seen). Here every
# `<main>/azerothcore-wotlk/modules[/mod-diablocraft]` in the command is rewritten to
# this checkout's own link (worker_worktree.sh made it), so the headers read are this
# checkout's. In the main checkout nothing is rewritten: it is the plain check.
# A file with no entry yet (new .cpp, the build has not been reconfigured) is checked with
# the flags of another file of the module, and the output says so.
# DC_COMPILE_COMMANDS overrides the compile_commands.json path (tests). Exit: the
# compiler's (1 when any file failed), 2 for a usage error or a missing database.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
main="$(dirname "$(git -C "$here" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$here/.git")")"
[ $# -ge 1 ] || { sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 2; }
db="${DC_COMPILE_COMMANDS:-$main/azerothcore-wotlk/build/compile_commands.json}"
[ -f "$db" ] || { echo "syntax_check: no compile database at $db (the live build has not been configured)" >&2; exit 2; }

HERE="$here" MAIN="$main" DB="$db" PWD_NOW="$PWD" exec python3 - "$@" <<'PY'
import json, os, shlex, subprocess, sys

here, main, db = os.environ["HERE"], os.environ["MAIN"], os.environ["DB"]
cwd0 = os.environ["PWD_NOW"]
linked = not os.path.samefile(here, main)
entries = json.load(open(db))
main_mod = main + "/azerothcore-wotlk/modules/mod-diablocraft"
here_mod = here + "/azerothcore-wotlk/modules/mod-diablocraft"
by_file = {os.path.realpath(e["file"]): e for e in entries}
module_entries = [e for e in entries if e["file"].startswith(main_mod + "/")]


def command(entry):
    return shlex.split(entry["command"]) if "command" in entry else list(entry["arguments"])


def rewrite(arg):
    if not linked:
        return arg
    if arg == "-I" + main + "/azerothcore-wotlk/modules":
        return "-I" + here + "/azerothcore-wotlk/modules"
    return arg.replace(main_mod, here_mod)


failed = 0
for given in sys.argv[1:]:
    src = given if os.path.isabs(given) else os.path.join(cwd0, given)
    src = os.path.realpath(src)
    if not os.path.isfile(src):
        print("syntax_check: no such file: %s" % given, file=sys.stderr)
        failed = 1
        continue
    rel = os.path.relpath(src, os.path.realpath(here) + "/mod-diablocraft") if src.startswith(os.path.realpath(here) + "/mod-diablocraft/") else None
    entry = by_file.get(os.path.realpath(main_mod + "/" + rel)) if rel else by_file.get(src)
    note = ""
    if entry is None:
        if not module_entries:
            print("syntax_check: no compile command for %s and none for the module" % given, file=sys.stderr)
            failed = 1
            continue
        entry = module_entries[0]
        note = " (no compile entry yet: flags of %s)" % os.path.relpath(entry["file"], main_mod)
    argv = command(entry)
    out, skip = [], False
    for arg in argv[1:]:
        if skip:
            skip = False
            continue
        if arg in ("-o", "-MF", "-MT", "-MQ"):
            skip = True
        elif arg in ("-c", "-MD", "-MMD", "-MP") or arg == entry["file"]:
            continue
        elif arg.startswith("-o") and len(arg) > 2 and not arg.startswith("-obj"):
            continue
        else:
            out.append(rewrite(arg))
    cmd = [argv[0], "-fsyntax-only"] + out + [src]
    print("syntax_check: %s%s" % (given, note), flush=True)
    code = subprocess.run(cmd, cwd=entry.get("directory") or here).returncode
    if code != 0:
        failed = 1
        print("syntax_check: FAILED (exit %d): %s" % (code, given), file=sys.stderr)
sys.exit(failed)
PY
