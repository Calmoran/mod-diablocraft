#!/usr/bin/env bash
# Keep the stock restart delay and crash-loop guard; patch 0017 fixes GDB status.
#
# Two trees are supported (service-accounts plan step 3, 2026-09-30):
#
#   * the in-repo tree, today's layout: <repo>/azerothcore-wotlk/build/server
#     holds the binaries and configs/, the stock restarter comes from
#     <repo>/azerothcore-wotlk/apps/startup-scripts/src, crash dumps go to
#     /home/user/torment-crashes/<name>;
#   * a game service tree: <tree>/server holds the binaries, simple-restarter
#     and configs/, and crash dumps go to <tree>/crashes/<name> (plan step 4
#     copies the restarter next to the binary). The tree is the directory this
#     copy of the script lives in, or DC_GAME_TREE when set, so the pane
#     command of the plan needs no environment:
#
#       sudo -u torment-game /srv/torment-game/run_server.sh worldserver
#
# DC_CRASH_DIR overrides the crash directory in either layout. The restarter,
# GDB, core limit and console behaviour are unchanged.
set -e
if [ "$#" -ne 1 ] || [[ "$1" != worldserver && "$1" != authserver ]]; then
    echo "Usage: $0 worldserver|authserver" >&2
    exit 2
fi
name="$1"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
if [ -n "${DC_GAME_TREE:-}" ]; then
    tree="${DC_GAME_TREE%/}"
elif [ -d "$here/server" ]; then
    tree="$here"
else
    tree=""
fi
if [ -n "$tree" ]; then
    server="$tree/server"
    restarter="$server/simple-restarter"
    crashes="${DC_CRASH_DIR:-$tree/crashes/$name}"
else
    server="$root/azerothcore-wotlk/build/server"
    restarter="$root/azerothcore-wotlk/apps/startup-scripts/src/simple-restarter"
    crashes="${DC_CRASH_DIR:-/home/user/torment-crashes/$name}"
fi
gdb_enabled=0
if [ "$name" = worldserver ]; then
    command -v gdb >/dev/null || { echo 'gdb is required for worldserver' >&2; exit 1; }
    gdb_enabled=1
fi
cd "$server"
[ -x "$restarter" ] || { echo "Missing restarter at $restarter" >&2; exit 1; }
[ -x "./$name" ] && [ -r "configs/$name.conf" ] || {
    echo "Missing executable or configs/$name.conf in $server" >&2
    exit 1
}
mkdir -p "$crashes" || { echo "Cannot create crash directory $crashes" >&2; exit 1; }
ulimit -c unlimited
# `sudo -u torment-game` sets SHELL to that account's login shell (nologin), and
# GDB starts the inferior through $SHELL ("This account is currently not
# available", diablocraft-d9t6). Hand the restarter a real shell.
SHELL="$(command -v bash)"; export SHELL
export WITH_CONSOLE=1
exec "$restarter" "$server" "$name" '' "configs/$name.conf" '' '' "$gdb_enabled" "$crashes"
