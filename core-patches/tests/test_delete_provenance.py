"""Exercise #82 against the production migration and delete-hook bodies.

The existing migration fixture supplies the core/SQL doubles. This test compiles
only that small extracted fixture and runs it against a private loopback MySQL
instance under /tmp; it never reads the configured server database.
"""
from pathlib import Path
import importlib.util
import shlex
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "mod-diablocraft/scripts"
sys.path.insert(0, str(SCRIPTS))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402


def source_fixture(path: Path) -> Path:
    spec = importlib.util.spec_from_file_location("account_migration_fixture", SCRIPTS / "tests/items/test_account_migration.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = path
    module.prepare()
    source = (ROOT / "mod-diablocraft/src/common/dc_account_economy.cpp").read_text()
    fixture = path / "test.cpp"
    code = fixture.read_text()
    # The harness now carries Quarantine, QuarantineItem and quarantinedCharacters itself; this test
    # only swaps its no-op LOG_ERROR for one that records what the production code logs.
    silent = "#define LOG_ERROR(category,...) ((void)0)"
    assert silent in code
    code = code.replace(silent, "std::vector<std::string> errorLogs;"
                        "\n#define LOG_ERROR(channel, pattern, ...) errorLogs.push_back(Format(pattern, __VA_ARGS__))")
    delete_source = source.replace("OnPlayerDeleteFromDB(CharacterDatabaseTransaction transaction, uint32 guid) override",
                                   "OnPlayerDeleteFromDB(CharacterDatabaseTransaction transaction, uint32 guid)")
    delete = module.extract(delete_source, "OnPlayerDeleteFromDB")
    code = code.replace("int main(int argc", delete + "\nint main(int argc", 1)
    marker = ' sql("DROP DATABASE dc_migration_fixture;");'
    assert marker in code
    regression = r'''
 sql(R"SQL(
 CREATE TABLE characters(guid INT UNSIGNED PRIMARY KEY,account INT UNSIGNED,money INT UNSIGNED,
   knownCurrencies BIGINT UNSIGNED DEFAULT 18446744073709551615,online TINYINT DEFAULT 0) ENGINE=InnoDB;
 CREATE TABLE dc_character_mode(guid INT UNSIGNED PRIMARY KEY,mode VARCHAR(20),dead TINYINT DEFAULT 0) ENGINE=InnoDB;
 CREATE TABLE item_instance(guid INT UNSIGNED PRIMARY KEY,itemEntry INT UNSIGNED,owner_guid INT UNSIGNED,count INT UNSIGNED) ENGINE=InnoDB;
 CREATE TABLE character_inventory(guid INT UNSIGNED,bag INT UNSIGNED,slot INT UNSIGNED,item INT UNSIGNED UNIQUE) ENGINE=InnoDB;
 CREATE TABLE mail(id INT UNSIGNED PRIMARY KEY,receiver INT UNSIGNED,sender INT UNSIGNED,money INT UNSIGNED,has_items TINYINT) ENGINE=InnoDB;
 CREATE TABLE mail_items(mail_id INT UNSIGNED,item_guid INT UNSIGNED UNIQUE) ENGINE=InnoDB;
 CREATE TABLE dc_item_instance(item_guid INT UNSIGNED PRIMARY KEY) ENGINE=InnoDB;
 )SQL");
 // Reproduce #82's reused GUID: the old code threw on guid 39 and stopped startup.
 sql("INSERT INTO characters(guid,account,money) VALUES(39,79,0),(40,79,2);"
     "INSERT INTO dc_character_mode VALUES(39,'normal',0),(40,'normal',0);"
     "INSERT INTO dc_account_economy_migration(source_kind,source_guid,character_guid,account_id,mode,item_entry,original_amount,pool_amount,location)"
     " VALUES('character',39,39,78,'normal',0,0,0,'new character seed');");
 check(Migrate()&&quarantinedCharacters.count(39)&&!quarantinedCharacters.count(40)&&
       number("SELECT balance_copper FROM dc_account_gold WHERE account_id=79 AND mode='normal'")==2,
       "reused GUID stale seed quarantines one character; another migrates");
 // GUID 41 models a character seed and both unsettled and settled item history.
 sql("INSERT INTO characters(guid,account,money) VALUES(41,80,0); INSERT INTO dc_character_mode VALUES(41,'normal',0);");
 sql("INSERT INTO dc_account_economy_migration(source_kind,source_guid,character_guid,account_id,mode,item_entry,original_amount,pool_amount,location) VALUES"
     "('character',41,41,80,'normal',0,0,0,'new character seed'),"
     "('item',141,41,80,'normal',102000,17,17,'inventory:0:1'),"
     "('item',142,41,80,'pending',102000,19,19,'inventory:0:2');");
 {auto tx=CharacterDatabase.BeginTransaction();tx->Append("DELETE FROM characters WHERE guid=41");
  tx->Append("DELETE FROM dc_character_mode WHERE guid=41");OnPlayerDeleteFromDB(tx,41);
  check(CharacterDatabase.AsyncCommitTransaction(tx).m_future.get(),"delete hook shares character transaction");}
 check(number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid=41")==0&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='item' AND source_guid=142")==0&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='item' AND source_guid=141")==1,
       "delete removes seed and pending item but retains settled item audit");
 sql("INSERT INTO characters(guid,account,money) VALUES(41,80,0); INSERT INTO dc_character_mode VALUES(41,'normal',0);");
 check(Migrate()&&number("SELECT account_id FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid=41")==80&&
       !quarantinedCharacters.count(41),"same-account GUID reuse receives a fresh seed");
 {auto tx=CharacterDatabase.BeginTransaction();tx->Append("DELETE FROM characters WHERE guid=41");
  tx->Append("DELETE FROM dc_character_mode WHERE guid=41");OnPlayerDeleteFromDB(tx,41);
  check(CharacterDatabase.AsyncCommitTransaction(tx).m_future.get(),"second delete transaction commits");}
 sql("INSERT INTO characters(guid,account,money) VALUES(41,81,0); INSERT INTO dc_character_mode VALUES(41,'normal',0);");
 check(Migrate()&&number("SELECT account_id FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid=41")==81&&
       !quarantinedCharacters.count(41)&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='item' AND source_guid=141")==1,
       "cross-account GUID reuse ignores kept settled item audit");
 sql("INSERT INTO item_instance VALUES(141,102000,41,17); INSERT INTO character_inventory VALUES(41,0,1,141);");
 check(Migrate()&&!quarantinedCharacters.count(41)&&
       number("SELECT COUNT(*) FROM item_instance WHERE guid=141")==0&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='item' AND source_guid=141")==1&&
       number("SELECT COUNT(*) FROM dc_account_currency WHERE account_id=81 AND item_entry=102000")==0,
       "settled item restoration ignores historical principal and cannot credit twice");
 sql("INSERT INTO characters(guid,account,money) VALUES(42,90,5),(43,92,3);"
     "INSERT INTO dc_character_mode VALUES(42,'normal',0),(43,'normal',0);"
     "INSERT INTO dc_account_economy_migration(source_kind,source_guid,character_guid,account_id,mode,item_entry,original_amount,pool_amount,location)"
     " VALUES('item',143,42,91,'pending',102000,7,7,'inventory:0:3');");
 check(Migrate()&&quarantinedCharacters.count(42)&&!quarantinedCharacters.count(43)&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid=42")==0&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid=43")==1&&
       number("SELECT balance_copper FROM dc_account_gold WHERE account_id=92 AND mode='normal'")==3,
       "malformed pending item quarantines its character while another migrates");
 check(number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='item' AND character_guid=42 AND mode='pending' AND account_id<>90")==1&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='item' AND character_guid=41 AND mode='pending' AND account_id<>81")==0,
       "login guard detects malformed pending item and ignores settled item audit");
 sql("INSERT INTO characters(guid,account,money) VALUES(44,0,2),(45,95,4),(46,96,1);"
     "INSERT INTO dc_character_mode VALUES(44,'normal',0),(45,'normal',0),(46,'invalid',0);");
 check(Migrate()&&quarantinedCharacters.count(44)&&quarantinedCharacters.count(46)&&
       !quarantinedCharacters.count(45)&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid IN (44,46)")==0&&
       number("SELECT balance_copper FROM dc_account_gold WHERE account_id=95 AND mode='normal'")==4,
       "account-zero and invalid-mode characters quarantine without stopping healthy migration");
 sql("INSERT INTO characters(guid,account,money) VALUES(47,97,1),(48,98,4);"
     "INSERT INTO dc_character_mode VALUES(47,'normal',0),(48,'normal',0);"
     "INSERT INTO item_instance VALUES(147,102000,47,0);"
     "INSERT INTO character_inventory VALUES(47,0,1,147);");
 check(Migrate()&&quarantinedCharacters.count(47)&&!quarantinedCharacters.count(48)&&
       number("SELECT COUNT(*) FROM item_instance WHERE guid=147")==1&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid=47")==0&&
       number("SELECT balance_copper FROM dc_account_gold WHERE account_id=98 AND mode='normal'")==4,
       "zero-count item quarantines its owner, leaves source untouched, and migrates another character");
 sql("INSERT INTO characters(guid,account,money) VALUES(53,102,1),(54,103,1),(55,104,3);"
     "INSERT INTO dc_character_mode VALUES(53,'normal',0),(54,'hardcore',0),(55,'normal',0);"
     "INSERT INTO item_instance VALUES(153,102000,53,2);"
     "INSERT INTO mail VALUES(153,54,53,0,1); INSERT INTO mail_items VALUES(153,153);");
 check(Migrate()&&quarantinedCharacters.count(53)&&quarantinedCharacters.count(54)&&
       !quarantinedCharacters.count(55)&&
       number("SELECT COUNT(*) FROM item_instance WHERE guid=153")==1&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid IN (53,54)")==0&&
       number("SELECT balance_copper FROM dc_account_gold WHERE account_id=104 AND mode='normal'")==3,
       "cross-mode mail quarantines both principals and leaves a healthy character migrating");
 sql("INSERT INTO characters(guid,account,money) VALUES(49,99,5);"
     "INSERT INTO dc_character_mode VALUES(49,'normal',0);"
     "INSERT INTO item_instance VALUES(148,102000,0,2),(149,102000,0,3);");
 errorLogs.clear();
 check(Migrate()&&number("SELECT COUNT(*) FROM item_instance WHERE guid=148")==1&&
       number("SELECT COUNT(*) FROM item_instance WHERE guid=149")==1&&
       number("SELECT balance_copper FROM dc_account_gold WHERE account_id=99 AND mode='normal'")==5,
       "multiple unowned orphan items remain unpaid while healthy migration continues");
 auto orphanLogs = []() {return std::count_if(errorLogs.begin(),errorLogs.end(),
   [](std::string const& line){return line.find("Unowned legacy items")!=std::string::npos;});};
 auto orphanLine = std::find_if(errorLogs.begin(),errorLogs.end(),
   [](std::string const& line){return line.find("Unowned legacy items")!=std::string::npos;});
 check(orphanLogs()==1&&orphanLine!=errorLogs.end()&&orphanLine->find("count=2")!=std::string::npos&&
       orphanLine->find("item_guids=148,149")!=std::string::npos,
       "two orphan GUIDs produce one startup summary line with count and GUIDs");
 errorLogs.clear();
 check(Migrate()&&orphanLogs()==1&&
       std::any_of(errorLogs.begin(),errorLogs.end(),[](std::string const& line){
         return line.find("count=2 item_guids=148,149")!=std::string::npos;}),
       "repeat startup emits one orphan summary line again");
 sql("INSERT INTO dc_account_gold(account_id,mode,balance_copper,revision)"
     " VALUES(100,'normal',18446744073709551614,0);"
     "INSERT INTO characters(guid,account,money) VALUES(50,100,1),(51,100,1),(52,101,6);"
     "INSERT INTO dc_character_mode VALUES(50,'normal',0),(51,'normal',0),(52,'normal',0);");
 errorLogs.clear();
 check(Migrate()&&quarantinedCharacters.count(50)&&quarantinedCharacters.count(51)&&
       !quarantinedCharacters.count(52)&&
       number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE source_kind='character' AND source_guid IN (50,51)")==0&&
       number("SELECT balance_copper FROM dc_account_gold WHERE account_id=100 AND mode='normal'")==18446744073709551614ULL&&
       number("SELECT balance_copper FROM dc_account_gold WHERE account_id=101 AND mode='normal'")==6,
       "shared-account overflow quarantines every contributor without paying either one");
 check(std::count_if(errorLogs.begin(),errorLogs.end(),[](std::string const& line){
         return line.find("account=100 mode=normal asset=0")!=std::string::npos;})==2&&
       std::any_of(errorLogs.begin(),errorLogs.end(),[](std::string const& line){
         return line.find("Character guid=50")!=std::string::npos&&
                line.find("account=100 mode=normal asset=0")!=std::string::npos;})&&
       std::any_of(errorLogs.begin(),errorLogs.end(),[](std::string const& line){
         return line.find("Character guid=51")!=std::string::npos&&
                line.find("account=100 mode=normal asset=0")!=std::string::npos;}),
       "each overflow repair line names its character, account, mode, and asset");
'''
    start = code.index(' check(!HasMigratedSources(),')
    end = code.index(marker)
    code = code[:start] + regression + code[end:]
    fixture.write_text(code)
    return fixture


def main() -> None:
    # The installed mysqld AppArmor profile permits private datadirs in /tmp,
    # but denies their initialization under the repository build directory.
    with tempfile.TemporaryDirectory(prefix="delete-provenance-", dir="/tmp") as name:
        path = Path(name)
        fixture = source_fixture(path)
        flags = shlex.split(subprocess.check_output(["mysql_config", "--cflags", "--libs"], text=True))
        subprocess.run(["g++", "-std=c++17", "-pthread", str(fixture), "-o", str(path / "fixture"), *flags], check=True)
        data = path / "data"
        base = ["mysqld", "--no-defaults", "--user=mysql", "--basedir=/usr", "--datadir=" + str(data),
                "--log-error=" + str(path / "mysql.log")]
        subprocess.run(base + ["--initialize-insecure"], check=True, stdout=subprocess.DEVNULL)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        process = subprocess.Popen(base + ["--bind-address=127.0.0.1", "--port=" + str(port),
                                   "--socket=" + str(path / "mysql.sock"), "--mysqlx=0", "--skip-log-bin",
                                   "--pid-file=" + str(path / "mysql.pid")], stdout=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError((path / "mysql.log").read_text())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("private MySQL did not start")
            harness_env.run([str(path / "fixture"), str(port)], check=True)
        finally:
            if process.poll() is None:
                subprocess.run(["mysqladmin", "--no-defaults", "--protocol=tcp", "--host=127.0.0.1",
                                "--port=" + str(port), "--user=root", "shutdown"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                process.wait(timeout=30)
        print("PASS private MySQL fixture removed; no live database used")


if __name__ == "__main__":
    main()
