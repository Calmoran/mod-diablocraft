"""Where the fixture mysqld is (diablocraft-ze2c): the real mysqld on a data folder inside
azerothcore-wotlk/build/_agent-scratch/fixture-mysql/, started by fixture_mysql.sh.

Tests that need it call `mysql_and_defaults()`; a path given on the command line still wins.
The live server is never an answer: the client file holds the fixture socket only.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def fixture_dir() -> Path:
    if os.environ.get("DC_FIXTURE_DIR"):
        return Path(os.environ["DC_FIXTURE_DIR"])
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=Path(__file__).resolve().parent, capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent / "azerothcore-wotlk/build/_agent-scratch/fixture-mysql"


def defaults_file() -> Path:
    return Path(os.environ.get("DC_FIXTURE_DEFAULTS") or fixture_dir() / "client.cnf")


def mysql_exe() -> str:
    return shutil.which("mysql") or "/usr/bin/mysql"


def mysql_and_defaults(argv=None):
    """(mysql, defaults) from two positional arguments if given, else the fixture's."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) >= 2:
        return argv[0], argv[1]
    mysql, defaults = mysql_exe(), str(defaults_file())
    ping = subprocess.run([mysql, "--defaults-file=" + defaults, "--no-login-paths", "-e", "SELECT 1 FROM acore_world.creature_template LIMIT 1"],
                          capture_output=True, text=True)
    if ping.returncode != 0:
        raise SystemExit("the fixture mysqld is not answering with a world copy (run mod-diablocraft/scripts/fixture_mysql.sh start, seed-world): " + ping.stderr.strip())
    return mysql, defaults
