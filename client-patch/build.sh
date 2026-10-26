#!/usr/bin/env bash
# Build patch-4.MPQ from client-patch/dbc and client-patch/art on Linux.
# Port of build.ps1. Packaging uses smpq (StormLib's command-line tool,
# `apt install smpq`) instead of Ladik's MPQ Editor, which is Windows-only.
#
# The 3.3.5a client only reads DBCs and art out of its MPQ chain, so anything we
# change client-side has to be packaged. patch.MPQ, patch-2.MPQ and patch-3.MPQ
# are Blizzard's, which makes 4 the next free slot; the client loads
# higher-numbered patches last, so ours wins.
#
# Regenerate the DBCs before running this:
#     python3 mod-diablocraft/scripts/generate/classes/generate_spells.py     # Spell.dbc
#     python3 client-patch/dbc/build_currencytypes.py        # CurrencyTypes.dbc
#     python3 client-patch/dbc/build_item.py --mysql ... --defaults-file ...   # Item.dbc
#     python3 client-patch/dbc/build_itemextendedcost.py     # ItemExtendedCost.dbc (Kadala's prices)
#
#     client-patch/build.sh [--output client-patch/patch-4.MPQ] [--install <WoW Data dir>]
#                           [--client-rebuild <unpacked client-rebuild CI artefact>]
#
# --client-rebuild defaults to the pinned glue-unlock artefact (client-patch/glue_unlock_run names its CI run), fetched
# once with `gh run download` into the shared scratch folder when a signed interface file needs it; DC_CLIENT_EXT_ROOT moves that folder.
#
# There is no client on the Linux server, so --install is only for a mounted
# client folder. Normally: build here, copy patch-4.MPQ to the Windows PC's
# "WoW Client/Data/" with the game closed. Bump client_patch in VERSION
# whenever this archive changes (00 section 7).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
output="$here/patch-4.MPQ"
install_dir=""
client_ext=""
while [ $# -gt 0 ]; do
    case "$1" in
        --output) output="$2"; shift ;;
        --install) install_dir="$2"; shift ;;
        --client-rebuild) client_ext="$2"; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done
command -v smpq >/dev/null 2>&1 || { echo 'smpq not found: sudo apt install smpq' >&2; exit 1; }

# Stamp the addon TOCs with VERSION client_patch so the AIO handshake reports
# the patch this archive is built at (docs/contracts/version-enforcement.md).
bash "$here/stamp_client_patch.sh"

# Stage the archive layout: DBFilesClient\<name>.dbc for DBCs, art paths as-is.
# smpq stores each file under the path given on its command line, and StormLib
# treats / and \ alike inside the archive.
stage="$(mktemp -d "${TMPDIR:-/tmp}/mpqbuild_XXXXXXXX")"
trap 'rm -rf "$stage"' EXIT
count=0
mkdir -p "$stage/DBFilesClient"
for dbc in "$here"/dbc/*.dbc; do
    [ -f "$dbc" ] || continue
    cp "$dbc" "$stage/DBFilesClient/"; count=$((count + 1))
done
# The 3.3.5 client signature-checks Interface\GlueXML and Interface\FrameXML and refuses to start with an
# edited file ("Your login interface files are corrupt", Nightly 52). Such a file is packed only with --client-rebuild
# naming a build whose pin in launcher/engine/src/allow.rs PINNED carries the glue-unlock flag, the rebuilt WowClient64.exe,
# built with the check off: manifest.py's rule (ships_glue_unlock), asked here, not restated.
# The default --client-rebuild: the artefact of the client-rebuild CI run glue_unlock_run names, the run whose WowClient64.exe
# the pin in allow.rs flags. It sits in the shared scratch folder (one copy for every worktree, the folder a release copies it
# from), fetched with `gh run download` when missing; the flag is still asked of manifest.py, so a run without it still refuses.
default_client_rebuild() {
    local run root dest tmp
    [ -s "$here/glue_unlock_run" ] || { echo "build.sh: client-patch/glue_unlock_run is missing or empty (it names the CI run of the pinned glue-unlock artefact)" >&2; return 1; }
    run="$(tr -d '[:space:]' < "$here/glue_unlock_run")"
    root="${DC_CLIENT_EXT_ROOT:-$here/../azerothcore-wotlk/build/_agent-scratch}"
    dest="$root/client-rebuild-run$run"
    if [ ! -d "$dest" ]; then
        command -v gh >/dev/null 2>&1 || { echo "build.sh: the pinned client-rebuild artefact (CI run $run) is not at $dest and gh is not installed" >&2; return 1; }
        mkdir -p "$root" && tmp="$(mktemp -d "$root/.fetch-XXXXXXXX")" || return 1
        if ! (cd "$here" && gh run download "$run" -n client-rebuild -D "$tmp") >&2; then
            rm -rf "$tmp"
            echo "build.sh: gh run download of the client-rebuild artefact of CI run $run failed (is gh logged in?)" >&2
            return 1
        fi
        mv "$tmp" "$dest" || { rm -rf "$tmp"; echo "build.sh: could not move the fetched artefact to $dest" >&2; return 1; }
    fi
    printf '%s\n' "$dest"
}
if [ -d "$here/art/Interface" ]; then
    bad="$(find "$here/art/Interface" -ipath '*/gluexml/*' -o -ipath '*/framexml/*' | head -3)"
    if [ -n "$bad" ] && [ -z "$client_ext" ]; then
        client_ext="$(default_client_rebuild)" || client_ext=""
    fi
    if [ -n "$bad" ] && ! { [ -n "$client_ext" ] && python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import manifest; sys.exit(0 if manifest.ships_glue_unlock(manifest.Path(sys.argv[2]), manifest.Path(sys.argv[1]).parent) else 1)' "$here" "$client_ext"; }; then
        echo "refusing to pack a signed interface file: $bad: the 3.3.5 client signature-checks Interface/GlueXML and Interface/FrameXML and refuses to start with an edited file. Such a file ships only with --client-rebuild and a build whose pin in launcher/engine/src/allow.rs PINNED carries the glue-unlock flag; otherwise remove it from client-patch/art (client-patch/parked/README.md)" >&2
        exit 1
    fi
fi
if [ -d "$here/art" ]; then
    while IFS= read -r -d '' art; do
        rel="${art#"$here/art/"}"
        # The art's drawing scripts, notes and manifests sit beside it; the client never reads them (3e4v)
        case "$(basename "$rel")" in .*|*.py|*.pyc|*.md|*manifest.json) continue ;; esac
        # source/ holds what the art is drawn from (fonts, raw sheets), never shipped (build_ui_art.py SKIP_DIRS);
        # __pycache__/ is what running a drawing script leaves behind (diablocraft-5wdni)
        case "/$rel" in */source/*|*/__pycache__/*) continue ;; esac
        mkdir -p "$stage/$(dirname "$rel")"; cp "$art" "$stage/$rel"; count=$((count + 1))
    done < <(find "$here/art" -type f -print0)
fi
# Edited map tiles (Noggit, docs/guide-map-editing.md). client-patch/maps/World holds the
# ADTs that client-patch/mapedit/mapedit.py staged. The gate refuses to pack an ADT whose
# server map/vmap/mmap data was not regenerated for exactly that file, so players never
# see a wall the server does not know about.
if [ -d "$here/maps/World" ]; then
    python3 "$here/mapedit/mapedit.py" verify-packed --stage "$here/maps" || { echo "map tiles are not packable: run mapedit.py first." >&2; exit 1; }
    while IFS= read -r -d '' adt; do
        rel="${adt#"$here/maps/"}"
        mkdir -p "$stage/$(dirname "$rel")"; cp "$adt" "$stage/$rel"; count=$((count + 1))
    done < <(find "$here/maps/World" -type f -iname '*.adt' -print0)
fi
[ "$count" -gt 0 ] || { echo "Nothing to package: no .dbc in $here/dbc and no files in $here/art." >&2; exit 1; }

# Rebuild from scratch every time; an MPQ that still holds a stale DBC is worse
# than no patch at all, because the client silently prefers it.
rm -f "$output"
# Hash table size: power of two with room to spare, as the PowerShell build did.
cap=16
while [ "$cap" -lt $((count + 8)) ]; do cap=$((cap * 2)); done
(
    cd "$stage"
    find . -type f | sed 's|^\./||' | sort > "$stage.list"
    while IFS= read -r f; do printf '  + %-40s %10s bytes\n' "$f" "$(stat -c %s "$f")"; done < "$stage.list"
    # MPQ version 2, as Blizzard's 3.3.5 patches are: world editors refuse version 4
    # (smpq's default), so they never saw our Map.dbc rows (diablocraft-t4f3).
    # shellcheck disable=SC2046
    smpq --create --mpq-version 2 --max-file-count "$cap" "$output" $(cat "$stage.list") >/dev/null
)
[ -f "$output" ] || { echo "smpq did not create $output" >&2; exit 1; }

# Verify by listing the archive back; a silent run is not evidence that
# anything was stored.
# smpq 1.6 lists "<size> <date> <time> <name>", not bare names, so the three
# leading columns come off before anything is compared. A build whose check
# cannot match is a build with no evidence behind it: before this, every file
# in the archive was reported missing and the script exited 1 with a complete
# archive on disk. Lines that are already bare names are left alone, so an
# smpq that prints them that way still verifies.
listing="$(smpq --list "$output" \
    | awk '{ if ($1 ~ /^[0-9]+$/ && NF >= 4) sub(/^[[:space:]]*[0-9]+[[:space:]]+[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+/, ""); print }' \
    | tr '\\' '/' )"
missing=0
# A here-string, not printf | grep -q: grep -q leaves at the first match, the printf took SIGPIPE and pipefail made a present
# file "missing" at random (diablocraft-9jft9).
while IFS= read -r f; do
    if ! grep -Fqx -- "$f" <<< "$listing"; then echo "$f is missing from the built archive." >&2; missing=1; fi
done < "$stage.list"
rm -f "$stage.list"
[ "$missing" -eq 0 ] || exit 1
printf 'built %s (%.1f MB, %d file(s))\n' "$(basename "$output")" "$(awk "BEGIN{print $(stat -c %s "$output")/1048576}")" "$count"

if [ -n "$install_dir" ]; then
    [ -d "$install_dir" ] || { echo "Client Data folder not found at '$install_dir'." >&2; exit 1; }
    cp -f "$output" "$install_dir/$(basename "$output")"
    echo "installed to $install_dir"
    echo 'Bump client_patch in VERSION whenever this archive changes (00 section 7).'
fi
