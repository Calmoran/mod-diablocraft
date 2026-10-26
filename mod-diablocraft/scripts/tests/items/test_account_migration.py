"""Execute the actual C++ migration against a private MySQL instance and legacy fixtures."""
from pathlib import Path
import csv
import os
import re
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_account_economy_sql import isolated
import host_cmake

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts/account-migration-tests"
MYSQL = Path(r"C:/Program Files/MySQL/MySQL Server 8.4")  # Windows only; elsewhere the system client library


def extract(source: str, name: str, *, declaration: bool = False) -> str:
    if declaration:
        start = source.index(name)
    else:
        found = re.search(r'\b' + re.escape(name) + r'\([^;{}]*\)\s*\{', source)
        if not found:
            raise ValueError("Missing migration function " + name)
        start = source.rfind('\n', 0, found.start()) + 1
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + (';' if declaration else '')


def prepare() -> None:
    source = (ROOT / "mod-diablocraft/src/common/dc_account_economy.cpp").read_text(encoding="utf-8")
    pieces = [extract(source, "struct " + name, declaration=True)
              for name in ["State", "PendingBalance", "Kind", "LegacyCharacter", "Contribution"]]
    header = (ROOT / "azerothcore-wotlk/src/server/game/Entities/Player/PlayerEconomy.h").read_text(encoding="utf-8")
    header = re.sub(r'^#include[^\n]*\n', '', header, flags=re.M)
    methods = '\n'.join(extract(source, name) for name in ["Load", "AppendContribution", "ClaimPending", "Migrate"])
    operation = extract(source, "class Operation final", declaration=True)
    with (ROOT / "mod-diablocraft/data/d3/account_economy.csv").open(encoding="utf-8", newline="") as stream:
        entries = list(csv.DictReader(stream))
    kinds = ','.join('{' + r['item_entry'] + ',{' + str(r['kind'] == 'material').lower() + ',' + r['copper_per_item'] + 'ULL}}' for r in entries)
    bar = next(int(r['copper_per_item']) for r in entries if r['kind'] == 'retired_gold')
    if 50000 * bar <= 2**32 - 1:
        raise ValueError('the hardcore fixture no longer passes uint32, so the mirror-saturation check tests nothing')
    schema = (ROOT / "mod-diablocraft/data/generated/account_economy_characters.sql").read_text(encoding="utf-8")
    code = r'''
#include <mysql.h>
#include <algorithm>
#include <cstdint>
#include <functional>
#include <future>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <type_traits>
#include <vector>
using uint32=std::uint32_t;using uint64=std::uint64_t;using int64=std::int64_t;
#define AC_GAME_API
#define LOG_ERROR(category,...) ((void)0)
MYSQL* connection=nullptr;uint32 mutateSource=0;
template<class T>std::string Str(T const& n){std::ostringstream s;s<<n;return s.str();}
template<class...T>std::string Format(std::string sql,T const&... values){
 std::vector<std::string> args{Str(values)...};std::size_t pos=0;
 for(auto const& a:args){pos=sql.find("{}",pos);if(pos==std::string::npos)throw std::runtime_error("SQL argument mismatch");sql.replace(pos,2,a);pos+=a.size();}return sql;
}
struct Field {std::string value;bool null=false;
 template<class T>T Get()const{if constexpr(std::is_same_v<T,std::string>)return null?"":value;else return null?T{}:T(std::stoull(value));}
};
struct Result {std::vector<std::vector<Field>> rows;std::size_t pos=0;
 Field* Fetch(){return rows.at(pos).data();}Field& operator[](std::size_t n){return rows.at(pos).at(n);}
 bool NextRow(){return ++pos<rows.size();}uint64 GetRowCount()const{return rows.size();}
};
using QueryResult=std::shared_ptr<Result>;
struct Tx {std::vector<std::string> statements;
 template<class...T>void Append(std::string const& sql,T const&... args){statements.push_back(Format(sql,args...));}
 std::size_t GetSize()const{return statements.size();}
};
using CharacterDatabaseTransaction=std::shared_ptr<Tx>;
struct Future {std::future<bool> m_future;};
struct Database {
 bool Execute(std::string const& sql){
  if(mysql_real_query(connection,sql.data(),(unsigned long)sql.size()))return false;
  int more;
  do {if(auto* r=mysql_store_result(connection))mysql_free_result(r);more=mysql_next_result(connection);}while(more==0);
  return more==-1;
 }
 template<class...T>QueryResult Query(std::string const& pattern,T const&... args){
  std::string sql=Format(pattern,args...);
  if(mysql_real_query(connection,sql.data(),(unsigned long)sql.size()))return {};
  MYSQL_RES* result=mysql_store_result(connection);if(!result)return {};
  auto out=std::make_shared<Result>();MYSQL_ROW row;unsigned count=mysql_num_fields(result);
  while((row=mysql_fetch_row(result))){std::vector<Field> fields;auto* lengths=mysql_fetch_lengths(result);
   for(unsigned i=0;i<count;++i)fields.push_back({row[i]?std::string(row[i],lengths[i]):"",row[i]==nullptr});out->rows.push_back(std::move(fields));}
  mysql_free_result(result);return out->rows.empty()?QueryResult{}:out;
 }
 void EscapeString(std::string& value){std::string out(value.size()*2+1,'\0');out.resize(mysql_real_escape_string(connection,out.data(),value.data(),(unsigned long)value.size()));value=out;}
 CharacterDatabaseTransaction BeginTransaction(){return std::make_shared<Tx>();}
 Future AsyncCommitTransaction(CharacterDatabaseTransaction const& tx){
  if(mutateSource){Execute("UPDATE characters SET money=money+1 WHERE guid="+Str(mutateSource));mutateSource=0;}
  bool ok=Execute("START TRANSACTION");for(auto const& sql:tx->statements)if(ok)ok=Execute(sql);
  if(ok)ok=Execute("COMMIT");else Execute("ROLLBACK");
  std::promise<bool> result;auto future=result.get_future();result.set_value(ok);return {std::move(future)};
 }
} CharacterDatabase;
@HEADER@
class Player {public:void SetMoneyMirror(uint32){};};
using Key=std::tuple<uint32,bool,uint32>;
@STRUCTS@
std::recursive_mutex mutex;std::map<Key,State> cache;std::map<uint32,Kind> kinds={@KINDS@};
std::set<std::pair<uint32,bool>> faultAccounts;std::set<uint32> quarantinedCharacters;
bool Actor(Player const*,uint32&,bool&){return false;}
bool Principal(uint32,uint32&,bool&){return false;}
namespace Hardcore {bool IsLocked(uint32){return false;}}
char const* Mode(bool h){return h?"hardcore":"normal";}
std::string NewId(){static uint64 id=0;return "fixture-"+Str(++id);}
std::string Escape(std::string value){CharacterDatabase.EscapeString(value);return value;}
uint64 RetiredKnownMask(){return uint64(1)<<63;} // Fixture mask, not a DBC assertion.
@COUNT@
@CUTOVER@
@LOAD@
@OPERATION@
@METHODS@
void check(bool ok,char const* name){if(!ok)throw std::runtime_error(name);std::cout<<"PASS "<<name<<'\n';}
void sql(std::string const& s){if(!CharacterDatabase.Execute(s))throw std::runtime_error(mysql_error(connection));}
uint64 number(std::string const& s){auto r=CharacterDatabase.Query(s);if(!r)throw std::runtime_error("Missing fixture result");return (*r)[0].Get<uint64>();}
bool quarantined(uint32 guid){return quarantinedCharacters.count(guid)!=0;}
bool refused(){try{return !Migrate();}catch(std::exception const&){return true;}}
int main(int argc,char** argv){
 std::cout<<std::unitbuf;if(argc!=2)return 2;connection=mysql_init(nullptr);
 if(!mysql_real_connect(connection,"127.0.0.1","root","",nullptr,(unsigned)std::stoul(argv[1]),nullptr,CLIENT_MULTI_STATEMENTS))throw std::runtime_error("Private MySQL connection failed");
 try {
 sql("CREATE DATABASE dc_migration_fixture; USE dc_migration_fixture;");
 sql(R"SQL(@SCHEMA@)SQL");
 check(!HasMigratedSources(),"pre-cutover schema may leave the provider disabled");
 sql(R"SQL(
 CREATE TABLE characters(guid INT UNSIGNED PRIMARY KEY,account INT UNSIGNED,money INT UNSIGNED,knownCurrencies BIGINT UNSIGNED DEFAULT 18446744073709551615,online TINYINT DEFAULT 0) ENGINE=InnoDB;
 CREATE TABLE dc_character_mode(guid INT UNSIGNED PRIMARY KEY,mode ENUM('normal','hardcore'),dead TINYINT DEFAULT 0) ENGINE=InnoDB;
 CREATE TABLE item_instance(guid INT UNSIGNED PRIMARY KEY,itemEntry INT UNSIGNED,owner_guid INT UNSIGNED,count INT UNSIGNED) ENGINE=InnoDB;
 CREATE TABLE character_inventory(guid INT UNSIGNED,bag INT UNSIGNED,slot INT UNSIGNED,item INT UNSIGNED UNIQUE) ENGINE=InnoDB;
 CREATE TABLE mail(id INT UNSIGNED PRIMARY KEY,receiver INT UNSIGNED,sender INT UNSIGNED,money INT UNSIGNED,has_items TINYINT) ENGINE=InnoDB;
 CREATE TABLE mail_items(mail_id INT UNSIGNED,item_guid INT UNSIGNED UNIQUE) ENGINE=InnoDB;
 CREATE TABLE dc_item_instance(item_guid INT UNSIGNED PRIMARY KEY) ENGINE=InnoDB;
 INSERT INTO characters(guid,account,money) VALUES(1,10,100),(2,10,200),(3,10,300),(4,10,400),(5,20,500);
 INSERT INTO dc_character_mode VALUES(1,'normal',0),(2,'normal',0),(3,'hardcore',1),(4,'hardcore',0);
 INSERT INTO item_instance VALUES(11,102006,1,2),(12,102000,2,7),(13,102001,3,9),(14,102006,3,50000),(15,102003,5,4),(16,102002,1,5);
 INSERT INTO character_inventory VALUES(1,0,23,11),(2,0,39,12),(3,0,81,13),(3,0,40,14),(5,0,82,15);
 INSERT INTO mail VALUES(1,2,1,777,1); INSERT INTO mail_items VALUES(1,16);
 )SQL");
 check(Migrate(),"actual C++ initial migration commits");
 check(HasMigratedSources(),"persisted cutover forbids disabling account authority");
 uint64 normal=2ULL*@BAR@+300,hardcore=50000ULL*@BAR@+700;
 check(number("SELECT balance_copper FROM dc_account_gold WHERE account_id=10 AND mode='normal'")==normal,"normal gold and bars aggregate across characters");
 check(number("SELECT balance_copper FROM dc_account_gold WHERE account_id=10 AND mode='hardcore'")==hardcore,"already-dead hardcore gold and bars contribute");
 check(number("SELECT amount FROM dc_account_currency WHERE account_id=10 AND mode='hardcore' AND item_entry=102001")==9,"dead hardcore material holdings survive in its pool");
 check(number("SELECT COUNT(*) FROM item_instance")==0&&number("SELECT COUNT(*) FROM mail_items")==0&&number("SELECT money FROM mail WHERE id=1")==777,"inventory bank currency slots and attachments are consumed, copper escrow is not");
 check(number("SELECT money FROM characters WHERE guid=3")==UINT32_MAX&&number("SELECT knownCurrencies FROM characters WHERE guid=3")==uint64(INT64_MAX),"mirrors saturate and retired known bit clears");
 check(number("SELECT COUNT(*) FROM dc_account_economy_migration")==11&&number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE mode='pending'")==2&&number("SELECT money FROM characters WHERE guid=5")==0,"every source has provenance and unchosen holdings stay pending");
 check(Migrate()&&number("SELECT balance_copper FROM dc_account_gold WHERE account_id=10 AND mode='normal'")==normal,"migration retry never credits saved mirrors");
 sql("INSERT INTO item_instance VALUES(12,102000,2,7); INSERT INTO character_inventory VALUES(2,0,39,12);");
 check(Migrate()&&number("SELECT amount FROM dc_account_currency WHERE account_id=10 AND mode='normal' AND item_entry=102000")==7&&number("SELECT COUNT(*) FROM item_instance")==0,"restored already-converted item is removed without re-credit");
 sql("INSERT INTO item_instance VALUES(12,102000,2,8); INSERT INTO character_inventory VALUES(2,0,39,12);");
 check(Migrate()&&quarantined(2)&&number("SELECT count FROM item_instance WHERE guid=12")==8,"changed restoration provenance quarantines its character and leaves the item unpaid");
 sql("DELETE FROM item_instance; DELETE FROM character_inventory; INSERT INTO item_instance VALUES(30,102000,1,1); INSERT INTO mail VALUES(2,3,1,0,1); INSERT INTO mail_items VALUES(2,30);");
 check(Migrate()&&quarantined(1)&&quarantined(3)&&number("SELECT COUNT(*) FROM item_instance")==1,"cross-mode legacy attachment is quarantined, not credited");
 sql("DELETE FROM mail_items WHERE mail_id=2; DELETE FROM mail WHERE id=2;");
 check(Migrate()&&quarantined(1)&&number("SELECT COUNT(*) FROM item_instance")==1,"orphan legacy ownership quarantines its owner and leaves the item");
 sql("DELETE FROM item_instance; INSERT INTO characters(guid,account,money) VALUES(9,21,0); INSERT INTO item_instance VALUES(30,102000,5,1); INSERT INTO mail VALUES(2,9,5,0,1); INSERT INTO mail_items VALUES(2,30);");
 check(Migrate()&&quarantined(5)&&quarantined(9)&&number("SELECT COUNT(*) FROM item_instance")==1,"two unchosen mail principals are not assumed to share a future mode");
 sql("DELETE FROM item_instance; DELETE FROM mail_items WHERE mail_id=2; DELETE FROM mail WHERE id=2; DELETE FROM characters WHERE guid=9; INSERT INTO characters(guid,account,money) VALUES(9,0,10);");
 check(Migrate()&&quarantined(9)&&number("SELECT COUNT(*) FROM dc_account_gold WHERE account_id=0")==0,"unresolved account ownership cannot create a pool for account zero");
 sql("DELETE FROM characters WHERE guid=9; INSERT INTO dc_character_mode VALUES(5,'normal',0);");
 check(Migrate()&&number("SELECT balance_copper FROM dc_account_gold WHERE account_id=20 AND mode='normal'")==500&&number("SELECT amount FROM dc_account_currency WHERE account_id=20 AND item_entry=102003")==4,"permanent mode choice claims gold and materials together");
 check(Migrate()&&number("SELECT balance_copper FROM dc_account_gold WHERE account_id=20")==500,"pending claim retry does not double-credit");
 sql("INSERT INTO characters(guid,account,money) VALUES(6,30,100); INSERT INTO dc_character_mode VALUES(6,'normal',0); INSERT INTO dc_account_gold VALUES(30,'normal',18446744073709551565,0);");
 check(Migrate()&&quarantined(6)&&number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE character_guid=6")==0,"aggregate overflow leaves all original sources unconverted");
 sql("DELETE FROM characters WHERE guid=6; DELETE FROM dc_character_mode WHERE guid=6; DELETE FROM dc_account_gold WHERE account_id=30;");
 sql("INSERT INTO characters(guid,account,money) VALUES(7,10,1); INSERT INTO dc_character_mode VALUES(7,'normal',0);");faultAccounts.insert({10,false});
 check(!Migrate()&&number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE character_guid=7")==0&&number("SELECT money FROM characters WHERE guid=7")==1,"real failed SQL transaction preserves source and provenance");
 check(Migrate()&&number("SELECT balance_copper FROM dc_account_gold WHERE account_id=10 AND mode='normal'")==normal+1,"retry after SQL failure credits exactly once");
 sql("INSERT INTO characters(guid,account,money) VALUES(8,10,2); INSERT INTO dc_character_mode VALUES(8,'normal',0);");mutateSource=8;
 check(!Migrate()&&number("SELECT COUNT(*) FROM dc_account_economy_migration WHERE character_guid=8")==0,"source changed after preflight fails its in-transaction guard");
 sql("UPDATE characters SET online=1 WHERE guid=1;");check(refused(),"online characters block cutover");
 sql("UPDATE characters SET online=0 WHERE guid=1; DELETE FROM characters WHERE guid=1; DELETE FROM dc_character_mode WHERE guid=1;");
 check(Migrate()&&number("SELECT balance_copper FROM dc_account_gold WHERE account_id=10 AND mode='normal'")==normal+4,"deleting a character cannot delete account gold");
 sql("DROP DATABASE dc_migration_fixture;");mysql_close(connection);
 }catch(...){mysql_close(connection);throw;}
}
'''
    # Load is needed before Operation; the other helpers follow its definition.
    methods = '\n'.join(extract(source, name) for name in ["Quarantine", "QuarantineItem", "AppendContribution", "ClaimPending", "Migrate"])
    for key, value in {"HEADER": header, "STRUCTS": '\n'.join(pieces), "KINDS": kinds,
                       "COUNT": extract(source, "Count"), "LOAD": extract(source, "Load"),
                       "CUTOVER": extract(source, "HasMigratedSources"),
                       "OPERATION": operation, "METHODS": methods, "SCHEMA": schema, "BAR": str(bar)}.items():
        code = code.replace('@' + key + '@', value)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "test.cpp").write_text(code, encoding="utf-8")
    (OUT / "CMakeLists.txt").write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(migration_test LANGUAGES CXX)\n'
        'add_executable(migration_test test.cpp)\ntarget_compile_features(migration_test PRIVATE cxx_std_17)\n'
        + (f'target_include_directories(migration_test PRIVATE "{MYSQL.as_posix()}/include")\n'
           f'target_link_libraries(migration_test PRIVATE "{MYSQL.as_posix()}/lib/libmysql.lib")\n'
           if os.name == "nt" else
           'target_include_directories(migration_test PRIVATE /usr/include/mysql)\n'
           'target_link_libraries(migration_test PRIVATE mysqlclient)\n'), encoding="utf-8")


def main() -> None:
    lock = ROOT / "build.lock"
    owner = f"Codex migration harness {uuid.uuid4()} {time.time()}"
    while True:
        try:
            with lock.open('x', encoding='utf-8') as stream:
                stream.write(owner)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime >= 1800:
                raise RuntimeError("Stale build.lock; inspect owner")
            print("Waiting for build.lock", flush=True)
            time.sleep(10)
    try:
        prepare()
        env = host_cmake.environment()
        if os.name == "nt":
            env['PATH'] = str(MYSQL / 'lib') + os.pathsep + str(MYSQL / 'bin') + os.pathsep + env['PATH']
        configure, build, binary = host_cmake.commands(OUT, OUT / 'build', 'migration_test')
        for command in (configure, build):
            os.utime(lock, None)
            subprocess.run(command, env=env, check=True)

        def run(port: int) -> None:
            subprocess.run([binary, str(port)], env=env, check=True)

        isolated(run)
    finally:
        if lock.read_text(encoding='utf-8') == owner:
            lock.unlink()


if __name__ == '__main__':
    main()
