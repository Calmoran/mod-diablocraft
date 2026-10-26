"""Creation-only Paragon and economy paths, compiled from production functions.

I/O doubles inject failed reads/commits; no game server or live database is used.
The existing class-parity harness exercises Start's creation and resume paths.
"""
import tempfile
import unittest
from pathlib import Path
from test_class_parity import SRC, definition, run

SOCKET_LIMIT = 107   # mysqld refuses a Unix socket path longer than this


def short_socket_dir():
    """A temp folder whose mysql.sock fits the socket limit, whatever the checkout's depth or TMPDIR is."""
    base = tempfile.gettempdir()
    if len(base) + len('/sock-xxxxxxxx/mysql.sock') > SOCKET_LIMIT - 20:
        base = '/tmp'
    return tempfile.TemporaryDirectory(prefix='sock-', dir=base)


class CreationParagon(unittest.TestCase):
    def test_floor_modes_xp_allocations_peers_and_failures(self):
        source = (SRC / 'paragon/dc_paragon.cpp').read_text()
        code = r'''
#include <algorithm>
#include <cassert>
#include <map>
#include <mutex>
#include <string>
#include <vector>
#include "dc_paragon_math.h"
using uint32 = std::uint32_t;
struct Session { uint32 account = 7; uint32 GetAccountId() { return account; } };
struct Player { Session session; int mode = 1; Session* GetSession() { return &session; } };
namespace DC::Hardcore {
    enum class Mode { Unchosen, Normal, Hardcore };
    Mode ModeOf(Player* p) { return Mode(p->mode); }
}
namespace DC::Paragon {
enum class Pool { Normal, Hardcore };
using AccountKey = std::pair<uint32, Pool>;
char const* PoolName(Pool p) { return p == Pool::Normal ? "normal" : "hardcore"; }
std::mutex mutex;
bool ready = true, writeWorks = true, readWorks = true;
unsigned writes = 0;
std::vector<XP> xpTable(800, 100);
std::map<AccountKey, Progress> accounts, durable;
struct Save { bool dirty = false, urgent = false, orphan = false; };   // the part of production's Save the floor touches
std::map<AccountKey, Save> saves;
struct Character { AccountKey account; unsigned points = 13; bool dirty = false, progressDirty = false; };
std::map<uint32, Character> characters;
void Check(Player*) { Need(ready, "unavailable"); }
Progress ReadAccount(AccountKey const& key) { Need(readWorks, "read failed"); return durable[key]; }
Progress& Account(AccountKey const& key) {
    if (!accounts.count(key)) accounts[key] = durable[key];
    return accounts.at(key);
}
struct DB {
    void DirectExecute(char const*, uint32 level, XP xp, uint32 account, char const* pool) {
        ++writes;
        if (writeWorks) durable[{account, std::string(pool) == "normal" ? Pool::Normal : Pool::Hardcore}] = {level, xp};
    }
} CharacterDatabase;
// The write itself is production's FlushNow (test_paragon_save.py runs it); here it is the double that fails on demand.
bool FlushNow(AccountKey const& key) {
    if (!saves.count(key)) return true;   // nothing owed, nothing written (production's first line)
    ++writes;
    if (!writeWorks) return false;
    durable[key] = accounts.at(key);
    saves.at(key).dirty = false;
    return true;
}
''' + definition(source, 'void ApplyProgress(') + '\n' + definition(source, 'bool EnsureStartingLevel(') + r'''
}
int main() {
    using namespace DC::Paragon;
    Player p; std::string error;
    AccountKey normal{7, Pool::Normal}, hardcore{7, Pool::Hardcore};
    durable[normal] = {10, 25}; durable[hardcore] = {99, 17};
    characters[1] = Character{normal}; characters[2] = Character{hardcore};
    assert(EnsureStartingLevel(&p, 200, error));
    assert(durable[normal].level == 200 && durable[normal].xp == 0 && writes == 1);
    assert(characters.size() == 2 && characters[1].points == 13 && characters[1].dirty && characters[1].progressDirty);
    assert(characters[2].points == 13 && !characters[2].dirty && durable[hardcore].xp == 17);
    assert(EnsureStartingLevel(&p, 200, error) && writes == 1);
    durable[normal] = {300, 77}; accounts.clear();
    assert(EnsureStartingLevel(&p, 200, error) && writes == 1 && durable[normal].xp == 77);
    p.mode = 2;
    assert(EnsureStartingLevel(&p, 200, error));
    assert(durable[hardcore].level == 200 && durable[hardcore].xp == 0 && writes == 2);
    assert(durable[normal].level == 300 && characters[2].dirty && characters[2].points == 13);
    p.session.account = 8; characters.clear();
    assert(EnsureStartingLevel(&p, 0, error) && writes == 2);
    assert(accounts.count({8, Pool::Hardcore}) == 0);
    assert(!EnsureStartingLevel(&p, 801, error));
    p.mode = 0; assert(!EnsureStartingLevel(&p, 200, error));
    p.mode = 1; writeWorks = false;
    assert(!EnsureStartingLevel(&p, 200, error) && durable[AccountKey(8, Pool::Normal)].level == 0);
    assert(saves.count({8, Pool::Normal}) && saves.at({8, Pool::Normal}).orphan); // owed to the tick, not dropped
    assert(accounts.at({8, Pool::Normal}).level == 200);
}
'''
        ok, out = run(code, ('-I' + str(SRC / 'paragon'),))
        self.assertTrue(ok, out)


class CreationEconomy(unittest.TestCase):
    def test_shared_provenance_checks_without_session_enlistment(self):
        source = (SRC / 'common/dc_account_economy.cpp').read_text()
        code = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
using uint32=std::uint32_t; using uint64=std::uint64_t;
#define LOG_ERROR(...) ((void)0)
constexpr unsigned AT_LOGIN_FIRST=0x20;
struct Player;
struct Session { Player* player=nullptr; uint32 GetAccountId() { return 7; } Player* GetPlayer() { return player; } };
struct Player {
    Session session; bool online=false, first=true; uint32 mirror=0;
    struct Guid { uint32 GetCounter() { return 42; } };
    Guid GetGUID() { return {}; } Session* GetSession() { return &session; }
    bool IsInWorld() { return online; } bool HasAtLoginFlag(unsigned) { return first; }
    void SetMoneyMirror(uint32 v) { mirror=v; }
};
struct Field {
    std::string text;
    template<class T> T Get() const {
        if constexpr(std::is_same_v<T,std::string>) return text;
        else return T(std::stoull(text));
    }
};
struct Row { std::vector<Field> fields; Field operator[](unsigned n) const { return fields.at(n); } };
using QueryResult=std::shared_ptr<Row>;
QueryResult row(std::initializer_list<std::string> values) {
    auto r=std::make_shared<Row>(); for(auto v:values) r->fields.push_back({v}); return r;
}
std::string recordedMode="missing"; unsigned recordedAccount=0, mismatch=0;
bool queryWorks=true, commitWorks=true;
struct DB {
    template<class... A> QueryResult Query(char const* sql, A...) {
        if(!queryWorks) return {};
        std::string s=sql;
        if(s.find("COALESCE")!=std::string::npos) return row({std::to_string(recordedAccount),recordedMode});
        if(s.find("COUNT")!=std::string::npos) return row({std::to_string(mismatch)});
        return row({"25"});
    }
} CharacterDatabase;
struct Key { unsigned account; bool hardcore; unsigned entry; };
struct Balance { uint64 amount=0; } balance;
struct Operation { bool failed=false, seeded=false; Balance& Row(Key) { return balance; } } operation;
unsigned seeds=0, finalizes=0, flushes=0;
Player* enlisted=nullptr;
namespace PlayerEconomy {
    struct Scope { explicit Scope(Player* p) { enlisted=p; operation={}; } };
    bool FinalizeLoad(Player*) { ++finalizes; return true; }
    void Fail() { operation.failed=true; }
    bool Flush() {
        ++flushes;
        if(operation.failed || !commitWorks || (enlisted && enlisted->GetSession()->GetPlayer()!=enlisted)) return false;
        if(operation.seeded) { ++seeds; recordedMode="normal"; recordedAccount=7; balance.amount+=25; }
        return true;
    }
}
namespace DC {
namespace Hardcore { enum class Mode { Unchosen, Normal, Hardcore }; Mode ModeOf(Player*) { return Mode::Normal; } }
namespace AccountEconomy {
bool enabled=true;
std::set<uint32> quarantinedCharacters;
char const* Mode(bool hardcore) { return hardcore?"hardcore":"normal"; }
Operation* Current() { return &operation; }
struct Contribution {
    std::string kind,mode,location; uint64 guid,original,pool; uint32 character,account,entry,mail; bool recorded;
};
void AppendContribution(Operation& op, Contribution const&) { op.seeded=true; }
bool ClaimPending(Operation&,uint32,uint32,std::string const&) { return true; }
''' + '\n'.join(definition(source, marker) for marker in (
            'static bool ResolveStart(', 'bool ResolvePending(', 'bool ResolveCreation(')) + r'''
} }
int main() {
    using namespace DC::AccountEconomy;
    Player p;
    assert(ResolveCreation(&p) && enlisted==nullptr && finalizes==0 && seeds==1);
    assert(ResolveCreation(&p) && seeds==1); // repeated creation does not seed twice
    p.session.player=&p;
    assert(ResolvePending(&p) && enlisted==&p && finalizes==1 && seeds==1);
    assert(!ResolveCreation(&p)); p.session.player=nullptr;
    p.online=true; assert(!ResolveCreation(&p)); p.online=false;
    p.first=false; assert(!ResolveCreation(&p)); p.first=true;
    for(bool creation:{false,true}) {
        p.session.player=creation?nullptr:&p;
        auto resolve=[&] { return creation?ResolveCreation(&p):ResolvePending(&p); };
        recordedAccount=8; assert(!resolve()); recordedAccount=7;
        recordedMode="hardcore"; assert(!resolve()); recordedMode="normal";
        mismatch=1; assert(!resolve()); mismatch=0;
        quarantinedCharacters.insert(42); assert(!resolve()); quarantinedCharacters.clear();
        queryWorks=false; assert(!resolve()); queryWorks=true;
        commitWorks=false; assert(!resolve()); commitWorks=true;
        assert(seeds==1);
    }
}
'''
        ok, out = run(code)
        self.assertTrue(ok, out)


class CreationMigration(unittest.TestCase):
    def test_socket_path_fits_whatever_the_checkout_depth_or_tmpdir(self):
        """The mysqld socket stays under the limit when the scratch folder or TMPDIR is deep (the nightly's tree)."""
        import os
        deep = Path(tempfile.gettempdir()) / ('d' * 60) / ('e' * 60)
        deep.mkdir(parents=True)
        old = os.environ.get('TMPDIR')
        os.environ['TMPDIR'] = str(deep)
        tempfile.tempdir = None
        try:
            with short_socket_dir() as directory:
                self.assertLessEqual(len(str(Path(directory) / 'mysql.sock')), SOCKET_LIMIT)
        finally:
            if old is None:
                del os.environ['TMPDIR']
            else:
                os.environ['TMPDIR'] = old
            tempfile.tempdir = None
            deep.rmdir(); deep.parent.rmdir()

    def test_mysql_upgrade_preserves_profiles_and_adds_filters_and_floor(self):
        import shutil
        import subprocess
        import time
        from test_class_parity import ROOT, SCRATCH
        mysqld, mysql, admin = (shutil.which(name) for name in ('mysqld', 'mysql', 'mysqladmin'))
        if not all((mysqld, mysql, admin)):
            self.skipTest('isolated MySQL tools are unavailable')
        with tempfile.TemporaryDirectory(prefix='start-sql-', dir=SCRATCH) as directory, short_socket_dir() as sockets:
            folder = Path(directory)
            data, socket = folder / 'data', Path(sockets) / 'mysql.sock'
            base = [mysqld, '--no-defaults', '--datadir=' + str(data),
                    '--log-error=' + str(folder / 'mysql.log')]
            initialized = subprocess.run(base + ['--initialize-insecure'], capture_output=True, text=True, timeout=60)
            if initialized.returncode:
                if 'Permission denied' in initialized.stderr:
                    self.skipTest('Host denies mysqld access to the isolated scratch datadir; no SQL executed')
                log = folder / 'mysql.log'
                self.fail(initialized.stderr + (log.read_text() if log.exists() else ''))
            server = subprocess.Popen(base + ['--skip-networking', '--mysqlx=0', '--socket=' + str(socket),
                                       '--pid-file=' + str(folder / 'mysql.pid'),
                                       '--innodb-buffer-pool-size=32M'], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            client = [mysql, '--no-defaults', '--no-login-paths', '--protocol=socket',
                      '--socket=' + str(socket), '--user=root', '--batch', '--skip-column-names']
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        self.fail((folder / 'mysql.log').read_text())
                    if subprocess.run(client + ['-e', 'SELECT 1'], capture_output=True).returncode == 0:
                        break
                    time.sleep(0.1)
                else:
                    self.fail('isolated MySQL did not start')
                updates = ROOT / 'mod-diablocraft/data/sql/db-world/updates'
                sql = 'CREATE DATABASE creation_test; USE creation_test;\n'
                sql += (updates / 'world_0016_class_starts.sql').read_text()
                sql += (updates / 'world_0021_class_starts.sql').read_text()
                sql += (updates / 'world_0040_class_starts.sql').read_text()
                sql += "SELECT COUNT(*) FROM dc_class_start; SELECT SUM(count) FROM dc_class_starter_kit;\n"
                sql += "SELECT base_type,base_slot,designated_class FROM dc_class_starter_kit WHERE class_id=1 AND slot='offhand';\n"
                sql += "SELECT tuned_value FROM dc_tunables WHERE category='paragon' AND name='starting_paragon_level';\n"
                result = subprocess.run(client, input=sql, text=True, capture_output=True, check=True, timeout=30)
                self.assertEqual(result.stdout.splitlines(), ['2', '26', 'Shield\toffhand\t', '200'])
            finally:
                if server.poll() is None:
                    subprocess.run([admin, '--no-defaults', '--socket=' + str(socket), '--user=root', 'shutdown'],
                                   capture_output=True, timeout=15)
                    server.wait(timeout=15)


if __name__ == '__main__':
    unittest.main()
