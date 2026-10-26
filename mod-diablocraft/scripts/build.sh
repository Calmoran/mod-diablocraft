#!/usr/bin/env bash
# Build one target under build.lock (build-release.lock for --release). Linux port of build.ps1.
#
#     mod-diablocraft/scripts/build.sh [--configure] [--target worldserver] [--jobs 1]
#     mod-diablocraft/scripts/build.sh --release <sha> [--target worldserver] [--jobs 1]
#
# Takes build.lock (build-release.lock with --release, so a dev build, which takes
# build-dev.lock in dev_realm.sh, never waits on a release build or a gate) in the main
# checkout (owner + pid + time), waits while another build holds it, refuses a lock older
# than 30 minutes, and touches the lock every 10 seconds while cmake runs. Eight jobs by
# default on the designer's upgraded server (2026-09-25); DC_BUILD_JOBS or --jobs overrides this
# per host.
#
# --release <sha> builds a commit nightly contains (DC_REVIEWED_REF overrides the ref, for tests;
# dev_lane.sh's dev branch is refused) and never the working tree (batch-updates plan
# section 4, W2; docs/test-diablocraft-release-build.md). The cut is checked out
# detached in one persistent worktree under
# azerothcore-wotlk/build/release-worktree, whose own build folder stays put, so the
# build of a later cut is incremental. The core is not in git: it is linked into the
# worktree entry by entry, the way release_gate.sh links it, and the module is the
# worktree's own mod-diablocraft, so the compiled code is the cut's. Of the core's
# modules/ only the ones the cut's mod-diablocraft/scripts/release_modules.txt names are
# linked (release_modules.sh), so a module added there for dev never reaches a release.
# CMAKE_INSTALL_PREFIX is the live server tree (`live_server` below) because
# AzerothCore compiles _CONF_DIR from it (src/cmake/platform/unix/settings.cmake);
# the release cache and the generated _CONF_DIR compile flags are checked against the
# live build before anything compiles, and a mismatch stops the build. The compile
# runs under nice (DC_RELEASE_NICE, default 10) so the live server is not starved.
#
# Building is not deploying: this writes azerothcore-wotlk/build/... — or, with
# --release, the worktree's own build folder — and never installs into the live tree.
# Deploy with mod-diablocraft/scripts/deploy_worldserver.sh afterwards.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The main checkout, even when this script runs from a linked worktree: release_gate.sh
# runs the cut's build.sh from the temporary worktree it makes for the cut.
main_root="$(dirname "$(git -C "$repo" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$repo/.git")")"

# The live server tree: the install prefix every build uses, and the tree its binary
# looks in for configs (<prefix>/etc, which is `configs/` there, so the module confs
# load as files). Since the H1 switch it is the game tree torment-game reads; the
# old in-repo build/server sat under /home, which that account cannot read
# (diablocraft-tg4n). A mismatch against the live build's cache stops a release
# build instead of shipping a binary that cannot find the live configs.
live_server="/srv/torment-game/server"

target=worldserver
configure=0
jobs="${DC_BUILD_JOBS:-8}"
release=""
nice_level="${DC_RELEASE_NICE:-10}"
while [ $# -gt 0 ]; do
    case "$1" in
        --configure) configure=1 ;;
        --target) target="$2"; shift ;;
        --jobs) jobs="$2"; shift ;;
        --release) release="${2:?--release needs a commit}"; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

# A build without --release writes the build folder of the checkout it runs from,
# and a linked worker worktree links the main checkout's live build folder into
# itself (worker_worktree.sh): it would rebuild the live build with that worktree's
# sources. Builds are the PM's, in the main checkout (diablocraft-twbu).
if [ -z "$release" ] && [ ! "$repo" -ef "$main_root" ]; then
    echo "build.sh: RED this is a linked worktree ($repo); a build without --release would write the live build folder." >&2
    echo "build.sh: build in the main checkout ($main_root), or use --release <sha> for a cut." >&2
    exit 4
fi

lock="$main_root/build${release:+-release}.lock"
owner="$(hostname)-$$-$(date +%s)"
acquired=0
cleanup() {
    if [ "$acquired" -eq 1 ] && [ -e "$lock" ] && grep -q "owner=$owner" "$lock" 2>/dev/null; then
        rm -f "$lock"
    fi
}
trap cleanup EXIT

while [ "$acquired" -eq 0 ]; do
    if ( set -o noclobber; printf 'owner=%s\npid=%s\ncreated=%s\n' "$owner" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$lock" ) 2>/dev/null; then
        acquired=1
    else
        [ -e "$lock" ] || continue
        age=$(( ( $(date +%s) - $(stat -c %Y "$lock") ) / 60 ))
        if [ "$age" -ge 30 ]; then
            echo "$(basename "$lock") is over 30 minutes old. Inspect its owner before removing a stale lock." >&2
            exit 3
        fi
        echo "Another build owns $(basename "$lock"); waiting 10 seconds."
        sleep 10
    fi
done

logdir="$main_root/azerothcore-wotlk/build/_agent-scratch/logs"
mkdir -p "$logdir"
log="$logdir/build-${release:+release-}${target}${release:+-${release:0:8}}-$(date +%Y%m%d-%H%M%S).log"

declare -a nice_cmd=()
run_cmake() {
    # Touch the lock while cmake runs so a long link never reads as stale. The
    # subshell's output goes to /dev/null so it never holds the caller's pipe open.
    ( while sleep 10; do touch "$lock" 2>/dev/null || exit 0; done ) >/dev/null 2>&1 &
    local toucher=$!
    set +e
    "${nice_cmd[@]}" cmake "$@" 2>&1 | tee -a "$log"
    local code=${PIPESTATUS[0]}
    set -e
    kill "$toucher" 2>/dev/null || true
    if [ "$code" -ne 0 ]; then
        echo "CMake failed ($code); inspect $log." >&2
        exit "$code"
    fi
}

cache_value() { # cache_value <CMakeCache.txt> <KEY>
    sed -n "s/^$2:[^=]*=//p" "$1" | head -n 1
}

cache_has() { # cache_has <CMakeCache.txt> <KEY>; CMAKE_CXX_FLAGS is legitimately empty
    grep -q "^$2:" "$1"
}

# The cut's tree: the worktree's own path for every entry of the core except build
# (the worktree gets its own) and modules (see below), then the modules: only those the
# cut's release_modules.txt names, and the cut's own mod-diablocraft.
. "$repo/mod-diablocraft/scripts/release_modules.sh"
link_core() { # link_core <core> <worktree-core>
    local core="$1" wt_core="$2" entry name
    for entry in "$core"/* "$core"/.[!.]*; do
        name="$(basename "$entry")"
        case "$name" in build|modules) continue ;; esac
        [ -e "$entry" ] && ln -sfn "$entry" "$wt_core/$name"
    done
    link_release_modules "$core/modules" "$wt_core/modules" "$worktree/mod-diablocraft/scripts/release_modules.txt" || exit 2
    ln -sfn "$worktree/mod-diablocraft" "$wt_core/modules/mod-diablocraft"
}

# The cache keys a release build must share with the live build: they decide what the
# binary is and where it looks for its configs. Each one is copied from the live cache
# into the release configure and read back from the release cache afterwards.
mirror_keys=(CMAKE_INSTALL_PREFIX CMAKE_BUILD_TYPE CMAKE_CXX_COMPILER CMAKE_CXX_COMPILER_LAUNCHER CMAKE_CXX_FLAGS)

if [ -n "$release" ]; then
    # ---- the cut, in a persistent worktree -------------------------------------
    cut="$(git -C "$main_root" rev-parse --verify --quiet "$release^{commit}")" \
        || { echo "build.sh: no such commit in $main_root: $release" >&2; exit 2; }
    # A release is cut from reviewed work only: dev (dev_lane.sh) holds branches nightly does not.
    reviewed="${DC_REVIEWED_REF:-nightly}"
    git -C "$main_root" merge-base --is-ancestor "$cut" "$reviewed" 2>/dev/null \
        || { echo "build.sh: RED $cut is not in $reviewed (or $reviewed does not exist): a release is cut only from nightly, never from dev." >&2; exit 3; }
    live_build="$main_root/azerothcore-wotlk/build"
    live_cache="$live_build/CMakeCache.txt"
    [ -f "$live_cache" ] || { echo "build.sh: no live build cache at $live_cache; configure the live build first." >&2; exit 1; }
    live_prefix="$(cache_value "$live_cache" CMAKE_INSTALL_PREFIX)"
    if [ "$live_prefix" != "$live_server" ]; then
        echo "build.sh: the live build's CMAKE_INSTALL_PREFIX is $live_prefix but this script's live_server is $live_server." >&2
        echo "build.sh: the live tree moved (the H1 switch?) or the live build was reconfigured; fix the live_server line near the top of build.sh." >&2
        exit 1
    fi

    worktree="$live_build/release-worktree"
    wt_core="$worktree/azerothcore-wotlk"
    wt_build="$wt_core/build"
    if [ -e "$worktree/.git" ]; then
        top="$(git -C "$worktree" rev-parse --show-toplevel 2>/dev/null)"
        [ -n "$top" ] && [ "$(realpath "$top")" = "$(realpath "$worktree")" ] \
            || { echo "build.sh: $worktree holds a git checkout of somewhere else (${top:-nothing}); move it away and rerun." >&2; exit 2; }
        dirty="$(git -C "$worktree" status --porcelain --untracked-files=no)"
        [ -z "$dirty" ] || { echo "build.sh: the release worktree has tracked changes; not touching it: $dirty" >&2; exit 2; }
        git -C "$worktree" checkout --detach --quiet "$cut" \
            || { echo "build.sh: could not check out $cut in $worktree" >&2; exit 2; }
    else
        [ -e "$worktree" ] && { echo "build.sh: $worktree exists and is not a git worktree; move it away and rerun." >&2; exit 2; }
        git -C "$main_root" worktree prune
        git -C "$main_root" worktree add --detach --quiet "$worktree" "$cut" \
            || { echo "build.sh: could not make the release worktree $worktree at $cut" >&2; exit 2; }
        echo "release build: made the worktree $worktree at $cut"
    fi
    mkdir -p "$wt_core/modules" "$wt_build"
    link_core "$main_root/azerothcore-wotlk" "$wt_core"

    nice_cmd=(nice -n "$nice_level")
    echo "release build: cut $cut, worktree $worktree, build $wt_build, prefix $live_server"
    echo "release build: nice -n $nice_level, $jobs jobs"

    declare -a mirror_args=()
    for key in "${mirror_keys[@]}"; do
        cache_has "$live_cache" "$key" \
            || { echo "build.sh: the live cache $live_cache has no $key; cannot mirror the live build." >&2; exit 1; }
        mirror_args+=("-D$key=$(cache_value "$live_cache" "$key")")
    done
    run_cmake -S "$wt_core" -B "$wt_build" "${mirror_args[@]}"

    # The check the 2026-09-22 Mage/B3 binary failed: a worktree-local prefix compiled
    # the wrong _CONF_DIR and the startup guard stopped the server on missing configs.
    for key in "${mirror_keys[@]}"; do
        got="$(cache_value "$wt_build/CMakeCache.txt" "$key")"
        want="$(cache_value "$live_cache" "$key")"
        if cache_has "$wt_build/CMakeCache.txt" "$key" && [ "$got" = "$want" ]; then
            continue
        fi
        if [ "$key" = CMAKE_INSTALL_PREFIX ]; then
            echo "build.sh: RED the release build's CMAKE_INSTALL_PREFIX is '$got' but the live build's is '$want'." >&2
            echo "build.sh: AzerothCore compiles _CONF_DIR from that prefix, so this binary would look for the live module configs in $got/etc." >&2
            echo "build.sh: remove $wt_build and rebuild; if the live tree moved (the H1 switch), fix the live_server line near the top of this script." >&2
        else
            echo "build.sh: RED the release build's $key is '$got' but the live build's is '$want'; remove $wt_build and rebuild." >&2
        fi
        exit 1
    done

    # The compile-time proof, not just the cache: _CONF_DIR reaches every object as
    # -D_CONF_DIR from src/cmake/showoptions.cmake, so the generated flags.make files
    # must carry the live tree and nothing else. (The linked binary is no use for
    # this: gcc merges the literal into its neighbours, so the plain path is not a
    # substring of it.) Some targets escape the quotes twice, hence the backslashes.
    want_conf='-D_CONF_DIR="'"$live_prefix"'/etc"'
    got_conf="$(grep -rho --include=flags.make -- "-D_CONF_DIR=[^ ]*" "$wt_build" 2>/dev/null | tr -d '\\' | sort -u)"
    if [ "$got_conf" != "$want_conf" ]; then
        echo "build.sh: RED the release build compiles _CONF_DIR as ${got_conf:-nothing}, not $want_conf." >&2
        echo "build.sh: a binary built that way would look for the live module configs elsewhere; remove $wt_build and rebuild." >&2
        exit 1
    fi
    echo "release build: _CONF_DIR is the live tree ($live_prefix/etc) in every target"

    build="$wt_build"
else
    cd "$repo"
    build="azerothcore-wotlk/build"
    if [ "$configure" -eq 1 ]; then
        # The prefix is stated, not left to the cache: a fresh build folder would
        # otherwise compile _CONF_DIR from cmake's default and miss the game tree.
        run_cmake -S azerothcore-wotlk -B azerothcore-wotlk/build -DCMAKE_INSTALL_PREFIX="$live_server"
    fi
fi

# With the Makefile generator, "--target worldserver" alone does not know how to
# produce modules/libmodules.a (MSBuild resolved it implicitly on Windows), so
# the modules library is built first when the target links it.
if [ "$target" = worldserver ]; then
    run_cmake --build "$build" --target modules --parallel "$jobs"
fi
run_cmake --build "$build" --target "$target" --parallel "$jobs"
built="$(find "$build/src/server/apps" -maxdepth 1 -type f -name "$target" 2>/dev/null | head -1)"
echo "built ${built:-target $target} (log: $log)"
if [ -z "$built" ]; then
    echo "build.sh: cmake returned 0 but produced no $target under $build/src/server/apps" >&2
    exit 1
fi
ls -la "$built"

if [ -n "$release" ]; then
    echo "release build: cut $cut built; not installed and not deployed, the live tree is untouched."
fi
