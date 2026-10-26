"""Exercise generated account schema in a disposable, uniquely named MySQL database.

Starts a separate loopback-only MySQL process with its own scratch data directory.
Never connects to the configured server. Tests schema/transaction semantics, not the
C++ legacy-source classifier; live migration acceptance remains a separate gate.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable
import hashlib
import os
import re
import shutil
import socket
import subprocess
import time
import uuid

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
ROOT = Path(__file__).resolve().parents[4]
# The disposable server runs on whichever host this is (diablocraft-lx43): the
# Windows install where it was written, otherwise mysql/mysqld/mysqladmin from the
# host's own packages. Either way it is a separate process on its own data
# directory and port; the configured server is never contacted.
WINDOWS = os.name == "nt"
if WINDOWS:
    MYSQL = Path(r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe")
    MYSQLD, MYSQLADMIN = MYSQL.with_name("mysqld.exe"), MYSQL.with_name("mysqladmin.exe")
    BASEDIR = MYSQL.parent.parent
else:
    MYSQL = Path(shutil.which("mysql") or "/usr/bin/mysql")
    MYSQLD = Path(shutil.which("mysqld") or "/usr/sbin/mysqld")
    MYSQLADMIN = Path(shutil.which("mysqladmin") or "/usr/bin/mysqladmin")
    BASEDIR = Path("/usr")
NO_WINDOW = subprocess.CREATE_NO_WINDOW if WINDOWS else 0


def run_tests(port: int) -> None:
    database = "dc_account_test_" + uuid.uuid4().hex
    assert re.fullmatch(r'dc_account_test_[0-9a-f]{32}', database)
    env = {key.upper(): value for key, value in os.environ.items()} if WINDOWS else dict(os.environ)
    env.pop("MYSQL_PWD", None)
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", "--port=" + str(port),
               "--user=root", "--batch", "--raw", "--skip-column-names"]

    def sql(text: str, *, selected: bool = True, expected_failure: bool = False) -> str:
        result = subprocess.run(command + (["--database=" + database] if selected else []),
                                input=text, text=True, encoding="utf-8", env=env,
                                capture_output=True, check=False)
        if (result.returncode != 0) != expected_failure:
            raise RuntimeError("Unexpected isolated SQL result: " + result.stderr.strip())
        return result.stdout.strip()

    def check(ok: bool, name: str) -> None:
        if not ok:
            raise AssertionError(name)
        print("PASS " + name, flush=True)

    sql(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4;", selected=False)
    try:
        schema = (ROOT / "mod-diablocraft/data/generated/account_economy_characters.sql").read_text(encoding="utf-8")
        sql(schema)
        sql(schema)
        check(sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND engine='InnoDB'") == "5",
              "generated schema is replayable and entirely transactional")
        sql("INSERT INTO dc_account_gold VALUES(1,'normal',18446744073709551615,0),(1,'hardcore',7,0);")
        check(sql("SELECT balance_copper FROM dc_account_gold WHERE account_id=1 AND mode='normal'") == str(2**64-1),
              "uint64 maximum survives SQL round trip")
        sql("UPDATE dc_account_gold SET balance_copper=balance_copper+1 WHERE account_id=1 AND mode='normal';", expected_failure=True)
        check(sql("SELECT balance_copper FROM dc_account_gold WHERE account_id=1 AND mode='hardcore'") == "7",
              "overflow refusal leaves the other mode untouched")
        sql("CREATE TABLE fixture_item(guid INT PRIMARY KEY,owner INT NOT NULL) ENGINE=InnoDB; INSERT INTO fixture_item VALUES(5,1);")
        sql("START TRANSACTION; UPDATE dc_account_gold SET balance_copper=20,revision=revision+1 WHERE account_id=1 AND mode='normal' AND revision=99; INSERT INTO dc_account_economy_check VALUES('stale',0,IF(ROW_COUNT()=1,1,0)); DELETE FROM fixture_item WHERE guid=5; COMMIT;", expected_failure=True)
        check(sql("SELECT COUNT(*) FROM fixture_item WHERE guid=5") == "1" and
              sql("SELECT balance_copper FROM dc_account_gold WHERE account_id=1 AND mode='normal'") == str(2**64-1),
              "zero-row CAS CHECK aborts the entire operation")
        sql("START TRANSACTION; DELETE FROM fixture_item WHERE guid=5; UPDATE dc_account_gold SET balance_copper=20,revision=revision+1 WHERE account_id=1 AND mode='normal' AND revision=0; INSERT INTO dc_account_economy_check VALUES('paid',0,IF(ROW_COUNT()=1,1,0)); COMMIT;")
        check(sql("SELECT COUNT(*) FROM fixture_item") == "0" and
              sql("SELECT balance_copper FROM dc_account_gold WHERE account_id=1 AND mode='normal'") == "20",
              "goods and account change commit together")
        sql("INSERT INTO dc_account_currency VALUES(1,'normal',102000,18446744073709551615,0);")
        check(sql("SELECT amount FROM dc_account_currency") == str(2**64-1), "materials retain full uint64 counts")
        provenance = "INSERT INTO dc_account_economy_migration(source_kind,source_guid,character_guid,account_id,mode,item_entry,original_amount,pool_amount,location) VALUES('item',90,5,1,'hardcore',102000,9,9,'inventory:0:1');"
        sql(provenance)
        sql("START TRANSACTION; UPDATE dc_account_gold SET balance_copper=99 WHERE account_id=1 AND mode='hardcore';" + provenance + "COMMIT;", expected_failure=True)
        check(sql("SELECT balance_copper FROM dc_account_gold WHERE account_id=1 AND mode='hardcore'") == "7",
              "duplicate source provenance rolls back a retry credit")
        sql("INSERT INTO dc_account_economy_migration(source_kind,source_guid,character_guid,account_id,mode,item_entry,original_amount,pool_amount,location) VALUES('character',91,91,2,'pending',0,100,100,'characters.money');")
        check(sql("SELECT COUNT(*) FROM dc_account_gold WHERE account_id=2") == "0", "pending source is not defaulted to normal mode")
        sql("INSERT INTO dc_account_gold VALUES(2,'hardcore',0,0); START TRANSACTION; UPDATE dc_account_economy_migration SET mode='hardcore' WHERE source_kind='character' AND source_guid=91 AND mode='pending'; INSERT INTO dc_account_economy_check VALUES('claim',0,IF(ROW_COUNT()=1,1,0)); UPDATE dc_account_gold SET balance_copper=100,revision=1 WHERE account_id=2 AND mode='hardcore'; COMMIT;")
        sql("START TRANSACTION; UPDATE dc_account_economy_migration SET mode='hardcore' WHERE source_kind='character' AND source_guid=91 AND mode='pending'; INSERT INTO dc_account_economy_check VALUES('retry',0,IF(ROW_COUNT()=1,1,0)); UPDATE dc_account_gold SET balance_copper=200 WHERE account_id=2; COMMIT;", expected_failure=True)
        check(sql("SELECT balance_copper FROM dc_account_gold WHERE account_id=2") == "100", "pending claim cannot be applied twice")
        sql("INSERT INTO dc_account_gold VALUES(3,'normal',100,0);")

        def competitor(identifier: str) -> bool:
            result = subprocess.run(command + ["--database=" + database], env=env,
                input="START TRANSACTION; UPDATE dc_account_gold SET balance_copper=90,revision=1 WHERE account_id=3 AND mode='normal' AND revision=0; "
                      f"INSERT INTO dc_account_economy_check VALUES('{identifier}',0,IF(ROW_COUNT()=1,1,0)); COMMIT;",
                text=True, capture_output=True, check=False)
            return result.returncode == 0

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(competitor, ["competitor-a", "competitor-b"]))
        check(sum(results) == 1 and sql("SELECT balance_copper,revision FROM dc_account_gold WHERE account_id=3") == "90\t1",
              "competing database writers cannot both spend the same revision")
        print("PASS isolated MySQL tests; no live database selected", flush=True)
    finally:
        sql(f"DROP DATABASE `{database}`;", selected=False)
        print("Removed disposable test database " + database, flush=True)


def initialized_data(scratch: Path) -> Path:
    """A data directory `mysqld --initialize-insecure` made, kept per mysqld version next to the disposable servers: starting from a copy
    (0.3 s) instead of initializing each time (4.3 s) is most of what a disposable server costs. Made in a folder of its own and
    renamed into place, so two runs starting together cannot see it half made."""
    version = subprocess.run([str(MYSQLD), "--version"], capture_output=True, text=True).stdout
    template = scratch / ("template-data-" + hashlib.sha1(version.encode()).hexdigest()[:12])
    if not (template / "mysql.ibd").is_file():
        building = scratch / ("template-building-" + uuid.uuid4().hex)
        (building / "data").mkdir(parents=True)
        try:
            subprocess.run([str(MYSQLD), "--no-defaults", "--basedir=" + str(BASEDIR), "--datadir=" + str(building / "data"),
                            "--log-error=" + str(building / "init.log"), "--initialize-insecure"], check=True)
            try:
                os.rename(building / "data", template)
            except OSError:
                pass  # another run made it first
        finally:
            shutil.rmtree(building, ignore_errors=True)
    return template


def isolated(test_runner: Callable[[int], None] = run_tests) -> None:
    # On Linux the host's AppArmor profile lets mysqld write only inside the fixture folder
    # (ops/apparmor/, diablocraft-ze2c), so the disposable server's folder goes there.
    if WINDOWS:
        scratch = (ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts").resolve()
    else:
        import fixture_db
        scratch = (fixture_db.fixture_dir() / "disposable").resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    directory = scratch / ("account-economy-mysql-" + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    data = directory / "data"
    data.mkdir()
    log = directory / "mysql.log"
    base = [str(MYSQLD), "--no-defaults", "--basedir=" + str(BASEDIR),
            "--datadir=" + str(data), "--log-error=" + str(log)]
    if not WINDOWS:
        # The default socket and pid file are the live server's. A unix socket path holds at
        # most 107 bytes, so the socket sits at the fixture folder's top, not in the long folder.
        base += ["--socket=" + str(scratch.parent / ("d-" + directory.name[-12:] + ".sock")),
                 "--pid-file=" + str(directory / "mysqld.pid")]
    process = None
    try:
        if WINDOWS:
            subprocess.run(base + ["--initialize-insecure"], check=True, creationflags=NO_WINDOW)
        else:
            shutil.copytree(initialized_data(scratch), data, symlinks=True, dirs_exist_ok=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        process = subprocess.Popen(base + ["--bind-address=127.0.0.1", "--port=" + str(port),
            "--mysqlx=0", "--innodb-buffer-pool-size=32M", "--max-connections=8", "--skip-log-bin"],
            creationflags=NO_WINDOW)
        ready = False
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Isolated MySQL exited; inspect " + str(log))
            # An open port is not a server that answers yet: ping it.
            ping = subprocess.run([str(MYSQLADMIN), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1",
                "--port=" + str(port), "--user=root", "ping"], capture_output=True, creationflags=NO_WINDOW)
            if ping.returncode == 0:
                ready = True
                break
            time.sleep(0.1)
        if not ready:
            raise RuntimeError("Isolated MySQL startup timed out")
        test_runner(port)
    finally:
        if process is not None and process.poll() is None:
            subprocess.run([str(MYSQLADMIN), "--no-defaults", "--protocol=tcp",
                "--host=127.0.0.1", "--port=" + str(port), "--user=root", "shutdown"],
                check=False, capture_output=True)
            process.wait(timeout=30)
        # Only this process's validated scratch directory is eligible for cleanup.
        if directory.resolve().parent != scratch or not re.fullmatch(r'account-economy-mysql-[0-9a-f]{32}', directory.name):
            raise RuntimeError("Unsafe test cleanup target")
        shutil.rmtree(directory)
        print("Removed isolated MySQL data directory; no live database changed", flush=True)


if __name__ == "__main__":
    isolated()
