#!/usr/bin/env python3
"""Fail unless AIO would serve only our own Lua (diablocraft-xbba).

    python3 mod-diablocraft/scripts/check_aio_served.py <server-dir> [--dev-forgeui LIST]

<server-dir> is the folder that holds bin/lua_scripts (the game tree's `server`).
AIO sends every file that calls AIO.AddAddon to every player at every login, and
ALE loads every .lua/.ext under lua_scripts recursively, through symlinks too.
A copied dev tree once carried ForgeUI (252 files, ~7.8 MB) that way. It fails unless:

  1. the top level of bin/lua_scripts is exactly AIO, dc_aio, extensions;
  2. AIO holds only AIO_Server (plus LICENSE and README files);
  3. no file ALE would load outside dc_aio mentions AddAddon (AddAddon and
     AddAddonCode both register served code), except AIO's own AIO.lua;
  4. no client-bound file (a dc_aio file that calls AddAddon, so AIO ships it to
     every player) names a Discord token, webhook, channel or role id, a GitHub
     token, or the repository detail the poster files with (bug-report-messages.md,
     "Nothing secret reaches a player").

With --dev-forgeui LIST (the dev realm's deploy passes it; the live deploy and the release gate never
do) a fifth top-level folder, ForgeUI, is allowed, and its files may call AddAddon, but only the files
named in LIST (one path relative to ForgeUI/ per line, forgeui_files.txt): any other file under it fails.
Without the flag ForgeUI is a stray top-level folder, as before.

On success it prints the AIO-served file count and bytes. Exit 0 pass, 1 fail,
2 usage. Read-only.
"""
import os
import re
import sys

TOP = {"AIO", "dc_aio", "extensions"}
AIO_OWN = os.path.join("AIO", "AIO_Server", "AIO.lua")
FORGEUI = "ForgeUI"   # the dev realm's layout tool, allowed only with --dev-forgeui
LOADED = (".lua", ".ext", ".moon")  # what ALE's script scan picks up
MARK = b"AddAddon"

# What must never reach a client. Each entry is the name the report prints and a
# byte pattern; only files AIO serves are scanned, so the bot's own config - which
# legitimately holds these - is not this check's business.
SECRETS = (
    ("a Discord token",
     re.compile(rb"[MN][A-Za-z\d_-]{22,24}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}")),
    ("a Discord webhook",
     re.compile(rb"discord(?:app)?\.com/api/webhooks/")),
    ("a GitHub token",
     re.compile(rb"(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}")),
    ("a channel or role id",
     re.compile(rb"(?i)\b(?:channel|role|guild|webhook)_?id\b\s*[=:]")),
    ("a GitHub repository detail",
     re.compile(rb"github\.com/[\w.-]+/[\w.-]+")),
)


def walk(base):
    """Yield (path relative to base, real path) for every file ALE would reach, following symlinks once each."""
    seen = set()
    stack = [""]
    while stack:
        rel = stack.pop()
        here = os.path.join(base, rel)
        real = os.path.realpath(here)
        if real in seen:
            continue
        seen.add(real)
        try:
            names = sorted(os.listdir(here))
        except OSError:
            continue
        for name in names:
            child = os.path.join(rel, name)
            full = os.path.join(base, child)
            if os.path.isdir(full):
                stack.append(child)
            elif os.path.isfile(full):
                yield child, full


def read_list(path):
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def forgeui_files(server_dir):
    base = os.path.join(server_dir.rstrip("/") or "/", "bin", "lua_scripts", FORGEUI)
    return {rel.replace(os.sep, "/") for rel, _ in walk(base)} if os.path.isdir(base) else set()


def check(server_dir, forgeui_list=None):
    """Return (problems, served_files, served_bytes). forgeui_list: the set of paths under ForgeUI/ the dev realm may hold."""
    scripts = os.path.join(server_dir, "bin", "lua_scripts")
    problems = []
    if not os.path.isdir(scripts):
        return [f"{scripts} does not exist"], 0, 0

    top = set(os.listdir(scripts))
    allowed_top = TOP | ({FORGEUI} if forgeui_list is not None else set())
    for extra in sorted(top - allowed_top):
        problems.append(f"lua_scripts/{extra}: not allowed at the top level (only AIO, dc_aio, extensions)")
    for missing in sorted(TOP - top):
        problems.append(f"lua_scripts/{missing}: missing (the top level must be exactly AIO, dc_aio, extensions)")

    aio = os.path.join(scripts, "AIO")
    if os.path.isdir(aio):
        for name in sorted(os.listdir(aio)):
            if name != "AIO_Server" and not name.upper().startswith(("LICENSE", "README")):
                problems.append(f"lua_scripts/AIO/{name}: AIO holds only AIO_Server (plus LICENSE and README)")

    served, served_bytes = 0, 0
    for rel, full in walk(scripts):
        if not rel.lower().endswith(LOADED):
            continue
        try:
            data = open(full, "rb").read()
        except OSError as e:
            problems.append(f"lua_scripts/{rel}: unreadable ({e})")
            continue
        if MARK not in data:
            continue
        if forgeui_list is not None and rel.split(os.sep)[0] == FORGEUI:
            continue   # held to its file list below
        if rel.split(os.sep)[0] == "dc_aio":
            if b"AddAddon(" in data:
                served += 1
                served_bytes += len(data)
                for name, pattern in SECRETS:
                    if pattern.search(data):
                        problems.append(f"lua_scripts/{rel}: client-bound code names {name}")
        elif rel != AIO_OWN:
            problems.append(f"lua_scripts/{rel}: calls AddAddon outside dc_aio, so AIO would serve it to every player")
    if forgeui_list is not None and os.path.isdir(os.path.join(scripts, FORGEUI)):
        for rel, _ in walk(os.path.join(scripts, FORGEUI)):
            if rel.replace(os.sep, "/") not in forgeui_list:
                problems.append(f"lua_scripts/{FORGEUI}/{rel}: not on the ForgeUI file list, so the dev realm may not hold it")
    return problems, served, served_bytes


def main(argv):
    args = argv[1:]
    forgeui_list = None
    if len(args) == 3 and args[1] == "--dev-forgeui":
        try:
            forgeui_list = read_list(args[2])
        except OSError as e:
            print(f"aio-served: RED cannot read the ForgeUI file list {args[2]} ({e})")
            return 1
        if not forgeui_list:
            print(f"aio-served: RED the ForgeUI file list {args[2]} is empty")
            return 1
        args = args[:1]
    if len(args) != 1:
        print(__doc__.split("\n\n")[0] + "\nusage: check_aio_served.py <server-dir> [--dev-forgeui LIST]", file=sys.stderr)
        return 2
    problems, served, served_bytes = check(args[0].rstrip("/") or "/", forgeui_list)
    if problems:
        for p in problems:
            print("aio-served: RED " + p)
        return 1
    held = ""
    if forgeui_list is not None:
        held = f"; ForgeUI (dev only) holds {len(forgeui_list & forgeui_files(args[0]))} listed files"
    print(f"aio-served: green, AIO serves {served} files, {served_bytes} bytes (all from dc_aio){held}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
