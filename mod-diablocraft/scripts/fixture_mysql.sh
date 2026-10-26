#!/usr/bin/env bash
# The one fixture mysqld (diablocraft-ze2c): the real /usr/sbin/mysqld on a data folder
# inside azerothcore-wotlk/build/_agent-scratch/fixture-mysql/, the only folder the
# AppArmor local override (ops/apparmor/) lets it use. Socket only, never the live 3306.
#
#     fixture_mysql.sh start|stop|status|seed-world|seed-characters-schema [dump.sql.gz]
#
# seed-world loads acore_world from a dump (default: the newest
# /home/user/backups/torment-db-*.sql.gz) into the fixture; it never reads the live server.
# A dump predates any migration that has not shipped, so seed-world then applies the legendary-gem
# ones (dc_tooltip.lua's startup query joins their tables), the item power table's, and the per-item preset ranges and
# affix metadata dc_tooltip.lua names a line from (ytzea); each replays safely over a shipped copy.
# seed-characters-schema adds the tables acore_characters lacks, structure only (no player rows).
# Tests find the server through DC_FIXTURE_SOCKET (default: fixture-mysql/sock) and
# DC_FIXTURE_DIR, see scripts/fixture_db.py.
set -eu
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
common="$(dirname "$(git -C "$here" rev-parse --path-format=absolute --git-common-dir)")"
dir="${DC_FIXTURE_DIR:-$common/azerothcore-wotlk/build/_agent-scratch/fixture-mysql}"
sock="$dir/sock"
run_mysqld=(/usr/sbin/mysqld --no-defaults --basedir=/usr --datadir="$dir/data"
    --skip-networking --socket="$sock" --mysqlx=OFF --pid-file="$dir/mysqld.pid"
    --log-error="$dir/run.err" --tmpdir="$dir/tmp" --skip-log-bin
    --default-time-zone=+00:00
    --sql-mode=ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION)
up() { mysqladmin --no-defaults -uroot -S "$sock" ping >/dev/null 2>&1; }

case "${1:-status}" in
  start)
    up && { echo "fixture mysqld already up: $sock"; exit 0; }
    mkdir -p "$dir/tmp" "$dir/data"
    [ -d "$dir/data/mysql" ] || "${run_mysqld[@]}" --initialize-insecure
    nohup "${run_mysqld[@]}" >/dev/null 2>&1 &
    for _ in $(seq 100); do up && { echo "fixture mysqld up: $sock"; exit 0; }; sleep 0.3; done
    echo "fixture mysqld did not start; see $dir/run.err" >&2; exit 1 ;;
  stop)
    up && mysqladmin --no-defaults -uroot -S "$sock" shutdown; echo "fixture mysqld stopped" ;;
  status)
    if up; then echo "up: $sock"; else echo "down: $sock"; exit 1; fi ;;
  seed-world)
    up || { echo "start the fixture first" >&2; exit 1; }
    dump="${2:-$(ls -1 /home/user/backups/torment-db-2*.sql.gz | sort | tail -1)}"
    echo "seeding acore_world from $dump"
    # only the acore_world statements: USE `acore_world` up to the next USE
    zcat "$dump" | awk 'BEGIN{on=1} /^USE `/{on=($0=="USE `acore_world`;")} /^CREATE DATABASE/{on=($0 ~ /`acore_world`/)} on' \
        | mysql --no-defaults -uroot -S "$sock"
    # The website's leaderboard tests insert into acore_world.dc_tunables without `notes`
    # (their fixture table has it nullable); the real column is NOT NULL with no default,
    # which strict mode refuses. One fixture database name serves both, so the copy gets a
    # default. Nothing else about the table differs from the dump.
    mysql --no-defaults -uroot -S "$sock" acore_world -e "ALTER TABLE dc_tunables MODIFY notes LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT ('') COMMENT 'The audit row or decision this number came from'"
    for sql in legendary_gems_0001 legendary_gems_0007_table legendary_gems_0002_items legendary_powers_0001_table legendary_powers_0002_table legendary_powers_0004_table legendary_powers_0005_table legendary_powers_0006_table legendary_powers_0007_table legendary_powers_0008_table legendary_powers_0009_table legendary_powers_0010_table legendary_powers_0011_table legendary_powers_0012_table legendary_powers_0013_table legendary_powers_0014_table legendary_powers_0015_table legendary_powers_0016_table legendary_powers_0017_table legendary_powers_0018_table legendary_powers_0019_table legendary_powers_0020_table legendary_powers_0021_table legendary_powers_0022_table legendary_powers_0023_table legendary_powers_0024_table legendary_powers_0025_table legendary_powers_0026_table legendary_powers_0027_table legendary_powers_0028_table legendary_powers_0029_table legendary_powers_0030_table legendary_powers_0031_table legendary_powers_0032_table legendary_powers_0033_table legendary_powers_0036_table legendary_powers_0037_table legendary_powers_0038_table legendary_powers_0039_table legendary_powers_0040_table legendary_powers_0041_table legendary_powers_0042_table legendary_powers_0043_table legendary_powers_0044_table legendary_powers_0045_table legendary_powers_0046_table legendary_powers_0047_table legendary_powers_0048_table legendary_powers_0049_table legendary_powers_0050_table legendary_powers_0051_table legendary_powers_0053_table legendary_powers_0054_table legendary_powers_0055_table legendary_powers_0056_table legendary_powers_0057_table legendary_powers_0058_table legendary_powers_0059_table legendary_powers_0067_table legendary_powers_0068_table legendary_powers_0069_table legendary_powers_0070_table legendary_powers_0071_table legendary_powers_0072_table legendary_powers_0073_table legendary_powers_0074_table legendary_powers_0075_table items_0024_item_preset_ranges items_0033_item_preset_ranges_sweep items_0034_affix_metadata_sweep; do
        mysql --no-defaults -uroot -S "$sock" acore_world < "$here/../data/sql/db-world/updates/$sql.sql"
    done ;;
  seed-characters-schema)
    up || { echo "start the fixture first" >&2; exit 1; }
    dump="${2:-$(ls -1 /home/user/backups/torment-db-2*.sql.gz | sort | tail -1)}"
    echo "adding missing acore_characters tables (structure only) from $dump"
    (echo 'SET FOREIGN_KEY_CHECKS=0;'; zcat "$dump" | awk 'BEGIN{on=0} /^USE `/{on=($0=="USE `acore_characters`;"); if(on)print} on && /^(DROP TABLE|INSERT|LOCK TABLES|UNLOCK TABLES|\/\*!40000 ALTER)/{next} on{sub(/^CREATE TABLE `/,"CREATE TABLE IF NOT EXISTS `"); print}') \
        | mysql --no-defaults -uroot -S "$sock" ;;
  *) sed -n '2,/^set -eu/p' "${BASH_SOURCE[0]}" | sed '$d;s/^# \{0,1\}//'; exit 2 ;;
esac
