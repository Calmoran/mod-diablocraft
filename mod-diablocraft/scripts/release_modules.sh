#!/usr/bin/env bash
# Sourced by build.sh and release_gate.sh (diablocraft-qzdu): which third-party modules a
# release carries. The list is release_modules.txt of the cut being built.
#
#     link_release_modules <core>/modules <worktree-core>/modules <release_modules.txt>
#
# Links the core's own non-directory entries (CMakeLists.txt, the loader files) and exactly
# the modules the list names. The core builds EVERY directory in modules/ as a module
# (ConfigureModules.cmake, IS_DIRECTORY, no name check), so no directory is linked unlisted,
# whatever its name. The worktree is persistent, so it first drops every link an earlier
# build left, mod-diablocraft included (the caller links the cut's own).
# Returns 1, saying why on stderr, when the list is missing or names a module the core
# does not have: a release that silently lacks a module is worse than a stopped build.
link_release_modules() {
    local core_mods="$1" wt_mods="$2" list="$3" entry name want
    local -a listed
    [ -f "$list" ] || { echo "release modules: no list at $list; a release links only the modules it names." >&2; return 1; }
    mapfile -t listed < <(sed 's/#.*//; s/[[:space:]]//g; /^$/d' "$list")
    for entry in "$wt_mods"/* "$wt_mods"/.[!.]*; do
        [ -L "$entry" ] && rm -f "$entry"
    done
    for entry in "$core_mods"/* "$core_mods"/.[!.]*; do
        [ -e "$entry" ] && [ ! -d "$entry" ] && ln -sfn "$entry" "$wt_mods/$(basename "$entry")"
    done
    for want in "${listed[@]}"; do
        [ "$want" = mod-diablocraft ] && continue
        [ -e "$core_mods/$want" ] || { echo "release modules: $list names $want, which $core_mods does not have." >&2; return 1; }
        ln -sfn "$core_mods/$want" "$wt_mods/$want"
    done
}
