#!/usr/bin/env bash
# Build the server half of the pinned Rochet2/AIO checkout for the live
# lua_scripts tree (security G2/G1, core-patches/0020-aio-server-security.patch).
#
# The AIO engine is third-party: it is pinned in modules-commit.txt and changed
# only by patch files, never forked (docs/design/00-architecture.md 8). This
# script exports AIO_Server from the AIO checkout at that pin, applies every
# core-patches/*-aio-*.patch in numeric order, and writes the result to a target
# directory. It never writes to the AIO checkout.
#
# Usage:
#   build_live_aio.sh <target-dir>
#       Export the pinned AIO_Server, apply the AIO patches, copy it to
#       <target-dir> (the live .../lua_scripts/AIO/AIO_Server folder).
#   build_live_aio.sh --compare <live-dir>
#       Export the pinned AIO_Server WITHOUT the patches and diff it against
#       <live-dir> with line endings ignored. Exit non-zero on any other
#       difference, listing it. Run this before the first live build so the
#       security deploy changes only what the patch changes.
#   build_live_aio.sh --install <live-AIO-dir>
#       The PM's deploy. Back up <live-AIO-dir> (the live lua_scripts/AIO
#       folder), then make the patched AIO_Server the one ALE loads: replace its
#       AIO_Server and remove the stray AIO_Client copy. ALE is loaded by file
#       name and refuses the second AIO.lua, so with AIO_Client present the
#       shipped, unpAtched AIO_Client/AIO.lua is the engine and the patched
#       AIO_Server/AIO.lua never runs. The client half still reaches players via
#       the client-patch manifest (Interface/AddOns/AIO_Client). Prints the
#       backup path and the exact restore command, then the PM restarts.
#
# Environment (defaults are the real paths):
#   AIO_CHECKOUT   git checkout of the AIO repo (default: ~/torment-aio)
#   AIO_PATCH_DIR  directory holding *-aio-*.patch (default: <repo>/core-patches)
#   AIO_BUILD_TMP  scratch root for the export (default: the core build's
#                  _agent-scratch; never /tmp)
#   AIO_BACKUP     backup path for --install (default: a timestamped folder under
#                  the scratch root; it must not already exist)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="build_live_aio.sh"

die() { echo "$script: $*" >&2; exit 2; }

usage() {
    echo "usage: $script <target-dir>" >&2
    echo "       $script --compare <live-dir>" >&2
    echo "       $script --install <live-AIO-dir>" >&2
    exit 2
}

[ $# -ge 1 ] || usage

mode="build"
case "$1" in
    --compare) [ $# -eq 2 ] || usage; mode="compare"; arg="$2" ;;
    --install) [ $# -eq 2 ] || usage; mode="install"; arg="$2" ;;
    --*) usage ;;
    *) [ $# -eq 1 ] || usage; arg="$1" ;;
esac

aio_root="${AIO_CHECKOUT:-$HOME/torment-aio}"
patch_dir="${AIO_PATCH_DIR:-$root/core-patches}"

[ -f "$root/modules-commit.txt" ] || die "no modules-commit.txt under $root"
commit="$(awk '$1 == "AIO" { print $2; exit }' "$root/modules-commit.txt")"
[ -n "$commit" ] || die "modules-commit.txt has no AIO pin"

[ -d "$aio_root/.git" ] || die "no AIO git checkout at $aio_root"
git -C "$aio_root" rev-parse --verify --quiet "${commit}^{commit}" >/dev/null \
    || die "pin $commit is not present in $aio_root"

[ -d "$patch_dir" ] || die "no patch directory $patch_dir"
patch_dir="$(cd "$patch_dir" && pwd)"

tmp_root="${AIO_BUILD_TMP:-$root/azerothcore-wotlk/build/_agent-scratch}"
mkdir -p "$tmp_root"
tmp="$(mktemp -d "$tmp_root/aio-build.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# Read-only export of the committed tree at the pin; the checkout is untouched.
git -C "$aio_root" archive "$commit" AIO_Server | tar -x -C "$tmp"

if [ "$mode" = "compare" ]; then
    live="$arg"
    [ -d "$live" ] || die "no live directory $live"
    set +e
    diff -r --strip-trailing-cr "$tmp/AIO_Server" "$live"
    rc=$?
    set -e
    if [ "$rc" -ne 0 ]; then
        echo "$script: $live differs from the AIO pin (line endings ignored)" >&2
        exit 1
    fi
    echo "$script: $live matches the AIO pin apart from line endings"
    exit 0
fi

if [ "$mode" = "build" ]; then
    target="$arg"
    [ -n "$target" ] || die "empty target directory"
    [ "$target" != "/" ] || die "refusing to write to /"
fi

patches=()
while IFS= read -r p; do patches+=("$p"); done \
    < <(compgen -G "$patch_dir/*-aio-*.patch" 2>/dev/null | sort || true)

if [ "${#patches[@]}" -gt 0 ]; then
    (
        cd "$tmp"
        for p in "${patches[@]}"; do
            git apply --check "$p" || die "patch does not apply at the pin: $p"
            git apply "$p"
            echo "$script: applied $(basename "$p")"
        done
    )
fi

if [ "$mode" = "install" ]; then
    live="$arg"
    [ -d "$live" ] || die "no live AIO directory $live"
    [ -f "$live/AIO_Server/AIO.lua" ] || die "$live is not the live lua_scripts/AIO (no AIO_Server/AIO.lua)"
    [ "$live" != "/" ] || die "refusing to write to /"

    backup="${AIO_BACKUP:-$tmp_root/aio-backup-$(date -u +%Y%m%dT%H%M%SZ)}"
    [ -n "$backup" ] || die "empty backup path"
    [ ! -e "$backup" ] || die "backup path already exists: $backup"
    mkdir -p "$(dirname "$backup")"
    cp -a "$live" "$backup"

    # ALE loads by file name and refuses the second AIO.lua, so the stray
    # AIO_Client copy shadows the engine. Drop it (its files still reach
    # players through the client-patch manifest) and put the patched
    # AIO_Server where ALE will load it.
    rm -rf "$live/AIO_Client" "$live/AIO_Server"
    mkdir -p "$live/AIO_Server"
    cp -a "$tmp/AIO_Server/." "$live/AIO_Server/"

    echo "$script: installed patched AIO_Server into $live/AIO_Server (pin ${commit:0:12}, ${#patches[@]} patch(es))"
    echo "$script: removed the stray $live/AIO_Client (client half ships via the client-patch manifest)"
    echo "$script: backup of the pre-deploy AIO folder: $backup"
    echo "$script: rollback: rm -rf '$live' && cp -a '$backup' '$live'"
    echo "$script: then restart worldserver; the log must load bin/lua_scripts/AIO/AIO_Server/AIO.lua with no 'same name already loaded' error, and a non-GM '.aio debug' must reply 'no such command'"
    exit 0
fi

mkdir -p "$target"
cp -a "$tmp/AIO_Server/." "$target/"
echo "$script: wrote patched AIO_Server to $target (pin ${commit:0:12}, ${#patches[@]} patch(es))"
