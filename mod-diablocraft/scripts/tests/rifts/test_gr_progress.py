"""Rift progress and the Greater Rift timer (diablocraft-del2, greater-rifts brief part 4; monster spawning S3, diablocraft-43j0).

Compiles the production pieces against core doubles:
  - dc_gr_progress.h as it is (the hundredths, the pack's one drop, the orb counts, the pickup and expiry rules);
  - the whole body of dc_gr_progress.cpp, with the core's classes replaced by small doubles: the points of a
    creature (the table read from the generated spawn_sheets_0002_progress.sql), the orbs a dead pack leaves in
    each mode, a run member walking into one, the clock running out and the Guardian's result, each driven the
    way the rift hooks drive them, against runs held in the live map;
  - BaseEntry cut out of dc_family_ai.cpp (a champion or rare clone counts as the monster it clones);
with every number read from data/tunables/rifts.csv, the sheet the code reads at run time. Source scans
cover what a double cannot reach (the hooks that call these, the quest veto, the turn-in, the quest loader,
the migrations); the test says so below.

Cross-source: warpath's table is in points of a 650-point bar; both rift quests count 30,000 hundredths (300 points; ruling 2026-10-16,
diablocraft-owe7u); the orb rows of the sheet equal warpath's counts, and both kinds' orb is 6.5 points, 1% of D3's 650, 2.17% of ours; the two orb entries in C++ are the ones the generator writes;
the Greater orb's display is the tunable's and the Nephalem orb's is its own row (the designer's pick, 9701, small and lifted);
the outcome words the header writes are values of the dc_rift.outcome ENUM; `isElite` is gone from the kill path.

DC_GR_PROGRESS_SOURCE and DC_GR_PROGRESS_HEADER point the compile at mutated copies (mutation runs)."""
from pathlib import Path
import csv
import os
import re
import shutil
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import affixes_text, rifts_text  # noqa: E402
import harness_env
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
CPP = Path(os.environ.get('DC_GR_PROGRESS_SOURCE', MODULE / 'src/rifts/dc_gr_progress.cpp'))
HEADER = Path(os.environ.get('DC_GR_PROGRESS_HEADER', MODULE / 'src/rifts/dc_gr_progress.h'))
SOURCE = CPP.read_text(encoding='utf-8')
HEADER_TEXT = HEADER.read_text(encoding='utf-8')


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def body(text: str, start: str, end: str) -> str:
    """The text from `start` up to (not including) the next `end` after it."""
    first = text.index(start)
    return text[first:text.index(end, first)]


def value(name: str) -> float:
    return tunables_csv.value('rifts', name)


# --- cross-source: the tunables the code reads exist, and the numbers are warpath's -------------------------------
rows = {r['name']: r for r in csv.DictReader((MODULE / 'data/tunables/rifts.csv').open(encoding='utf-8', newline=''))}
literal_names = set(re.findall(r'Number\(\s*"(\w+)"', SOURCE))
assert literal_names == {'monster_progress_default_points', 'gr_orb_pickup_radius_yards', 'nr_orb_lift_yards'}, literal_names
suffixes = set(re.findall(r'\+ "(_orb_\w+)"', SOURCE))
assert suffixes == {'_orb_champion_count', '_orb_rare_count', '_orb_points'}, suffixes   # built per mode: "gr" or "nr"
assert 'greater ? "gr" : "nr"' in SOURCE
orb_rows = {m + s: rows[m + s] for m in ('gr', 'nr') for s in suffixes}
read_names = literal_names | set(orb_rows)
for name in read_names | {'gr_orb_display_id', 'nr_orb_display_id'}:
    assert name in rows, name
for retired in ('progress_units_per_kill', 'gr_progress_weight_elite', 'gr_progress_weight_pack_member', 'gr_orb_count',
                'gr_orb_progress_pct'):
    assert retired not in rows and retired not in SOURCE and retired not in HEADER_TEXT, retired   # S3 retired them
    assert ('"rifts", "%s"' % retired) in read('mod-diablocraft/scripts/generate/tunables/generate_tunables.py'), retired   # and the migration drops them
assert 'Multiple(' not in SOURCE and 'KindOf' not in SOURCE and 'isElite' not in SOURCE   # an elite is no longer a weight

# warpath's table is points of D3's 650-point bar; ours is 300 points, 30,000 hundredths, the same in every dungeon (ruling 2026-10-16, diablocraft-owe7u)
readme = read('mod-diablocraft/data/d3/README.md')
assert '`progress_pct` = `progress_points / 650 \xd7 100`' in readme
BAR_POINTS = 650                                          # D3's bar, the denominator of warpath's progress_pct
RIFT_BAR_POINTS = 300                                     # ours: 300 points fill it
warpath = list(csv.DictReader((MODULE / 'data/d3/gr_monster_progress.csv').open(encoding='utf-8', newline='')))
assert len(warpath) == 197
for row in warpath:
    assert abs(float(row['progress_pct']) - round(float(row['progress_points']) / BAR_POINTS * 100, 4)) < 1e-9, row['name']
    assert abs(float(row['progress_points']) * 100 - round(float(row['progress_points']) * 100)) < 1e-9, row['name']   # whole hundredths
quest_rows = [r for r in csv.DictReader((MODULE / 'data/d3/rift_quests.csv').open(encoding='utf-8', newline='')) if r['kind'] == 'quest']
assert [(r['mode'], r['bar_hundredths']) for r in quest_rows] == [('nr', str(RIFT_BAR_POINTS * 100)), ('gr', str(RIFT_BAR_POINTS * 100))]
BAR = RIFT_BAR_POINTS * 100
assert BAR <= 65535                                       # the core's 16-bit quest counter (QuestDef.h CreatureOrGOCount)
assert re.search(r'uint16\s+CreatureOrGOCount\[QUEST_OBJECTIVES_COUNT\]|CreatureOrGOCount\[', read('azerothcore-wotlk/src/server/game/Quests/QuestDef.h'))
# the orb rows: warpath's split and points for Greater Rifts, the designer's seeds for Nephalem Rifts
assert [value('gr_orb_champion_count'), value('gr_orb_rare_count'), value('gr_orb_points')] == [3, 4, 6.5]
assert [value('nr_orb_champion_count'), value('nr_orb_rare_count'), value('nr_orb_points')] == [3, 4, 6.5]
for name in ('gr_orb_champion_count', 'gr_orb_rare_count'):
    assert rows[name]['d3_value'] and not rows[name]['value'], name
# both kinds' orb is 6.5 points, the designer's value (q-1008-11, decisions.md 2026-10-09: 1% of D3's 650; of our 300-point bar it is 2.17%); the Greater row keeps warpath's 7.5 as d3_value
assert rows['gr_orb_points']['d3_value'] == '7.5' and rows['gr_orb_points']['value'] == '6.5'
for name in ('nr_orb_champion_count', 'nr_orb_rare_count', 'nr_orb_points', 'gr_orb_points'):
    assert 'SEED' not in rows[name]['notes'] and 'ruling 2026-10-09 q-1008-11' in rows[name]['notes'], name
for name in ('nr_orb_champion_count', 'nr_orb_rare_count', 'nr_orb_points'):
    assert not rows[name]['d3_value'] and rows[name]['value'], name
# The designer's pick from the orb row on dev (2026-10-16, diablocraft-ivtf5): 9701, the Flame Sphere
assert rows['nr_orb_display_id']['value'] == '9701' and rows['nr_orb_display_id']['d3_value'] == '' and 'Flame Sphere' in rows['nr_orb_display_id']['notes']
assert value('nr_orb_points') / BAR_POINTS == 0.01 == value('gr_orb_points') / BAR_POINTS   # 1% of D3's bar, both kinds
assert rows['monster_progress_default_points']['d3_value'] == '1' and not rows['monster_progress_default_points']['value']
assert value('gr_orb_pickup_radius_yards') == 5.5 and 'INTERACTION_DISTANCE' in rows['gr_orb_pickup_radius_yards']['notes']
# the pickup reach is the core's own interaction distance (the sheet says so)
assert re.search(r'#define INTERACTION_DISTANCE\s+5\.5f', read('azerothcore-wotlk/src/server/game/Entities/Object/ObjectDefines.h'))
generated = read('mod-diablocraft/data/generated/tunables_0014.sql')
migration = read('mod-diablocraft/data/sql/db-world/updates/tunables_0014.sql')
assert generated == migration
for name in read_names | {'gr_orb_display_id', 'nr_orb_display_id'}:
    assert re.search(r"\('rifts', '%s', " % name, migration), name
for retired in ('progress_units_per_kill', 'gr_progress_weight_elite', 'gr_progress_weight_pack_member', 'gr_orb_count', 'gr_orb_progress_pct'):
    assert "DELETE FROM `dc_tunables` WHERE `category` = 'rifts' AND `name` = '%s';" % retired in migration, retired
    assert not re.search(r"\('rifts', '%s', " % retired, migration), retired

# --- cross-source: the orb templates, the outcome words, the core's rank test -------------------------------------
entry = int(re.search(r'constexpr std::uint32_t ORB_ENTRY = (\d+), NR_ORB_ENTRY = (\d+);', SOURCE).group(1))
nr_entry = int(re.search(r'constexpr std::uint32_t ORB_ENTRY = (\d+), NR_ORB_ENTRY = (\d+);', SOURCE).group(2))
generator = read('mod-diablocraft/scripts/generate/rifts/generate_rifts.py')
assert int(re.search(r'^ORB_ENTRY = (\d+)', generator, re.M).group(1)) == entry
assert int(re.search(r'^NR_ORB_ENTRY = (\d+)', generator, re.M).group(1)) == nr_entry
assert entry != nr_entry
orb_sql = read('mod-diablocraft/data/sql/db-world/updates/rifts_0016_gr_orb.sql')
assert orb_sql == read('mod-diablocraft/data/generated/rift_orb.sql')
template = re.search(r'\((\d+), (\d+), (\d+), \'Progress Orb\'', orb_sql)
assert int(template.group(1)) == entry
assert int(template.group(2)) == 5                                 # GAMEOBJECT_TYPE_GENERIC: nothing to click or loot
assert re.search(r'GAMEOBJECT_TYPE_GENERIC\s*=\s*5', read('azerothcore-wotlk/src/server/shared/SharedDefines.h'))
assert int(template.group(3)) == int(value('gr_orb_display_id')) == 363
# rifts_0020 (the purple stand-in) is applied and frozen; the picked look ships whole as rifts_0031
assert int(re.search(r"\(%d, 5, (\d+), 'Nephalem Progress Orb'" % nr_entry, read('mod-diablocraft/data/sql/db-world/updates/rifts_0020_nr_orb.sql')).group(1)) == 363
nr_sql = read('mod-diablocraft/data/sql/db-world/updates/rifts_0031_nr_orb_look.sql')
assert nr_sql == read('mod-diablocraft/data/generated/rift_nr_orb.sql')
nr_template = re.search(r'\((\d+), (\d+), (\d+), \'Nephalem Progress Orb\'', nr_sql)
assert int(nr_template.group(1)) == nr_entry and int(nr_template.group(2)) == 5
assert int(nr_template.group(3)) == int(value('nr_orb_display_id')) == 9701   # the orange look the designer picked; gr_orb_display_id stays the floor aura 363
taken = set()
for path in (MODULE / 'data/sql/db-world/updates').glob('*.sql'):
    for mine, own in ((entry, 'rifts_0016_gr_orb.sql'), (nr_entry, 'rifts_0031_nr_orb_look.sql')):
        if path.name not in (own, 'rifts_0020_nr_orb.sql') and re.search(r'gameobject_template[^;]*\(%d,' % mine, path.read_text(encoding='utf-8')):
            taken.add((path.name, mine))
assert not taken, taken                                            # the entries are nobody else's

enum = re.search(r"`outcome` ENUM\(([^)]*)\)", read('mod-diablocraft/data/sql/db-characters/updates/rifts_0005_rift_quests.sql')).group(1)
values = set(re.findall(r"'(\w+)'", enum))
names = set(re.findall(r'return beaten \? "(\w+)" : "(\w+)"', HEADER_TEXT)[0])
assert names == {'success', 'expired'} and names <= values, (names, values)
time_left = read('mod-diablocraft/data/sql/db-characters/updates/rifts_0008_gr_time_left.sql')
assert re.search(r'ADD COLUMN `time_left` INT UNSIGNED NULL', time_left) and 'DEFAULT' not in time_left
assert 'time_left={}' in SOURCE

# --- what the doubles cannot reach: where the rift hooks call these ------------------------------------
quests = read('mod-diablocraft/src/rifts/dc_rift_quests.cpp')
kill = body(quests, 'static void CreditRiftKill(Player* killer, Creature* killed)', '\nclass RiftPlayer')
assert 'AddProgress(killer, rift.id, KillUnits(killed, rift), 1);' in kill
assert kill.index('rift.state != "open"') < kill.index('AddProgress(')
assert 'rift.progress' not in kill                                 # one writer of progress: AddProgress
add = body(quests, 'void AddProgress(Player* source', '\nclass RiftPlayer')
assert 'stored->state != "open"' in add and 'SpawnGuardian(source, rift)' in add
assert 'deadline' not in add and 'outcome' not in add              # the Guardian spawns at 100% whatever the clock says
assert 'ProjectProgress(rift)' in add and 'Persist(rift)' in add
assert 'stored->progress = Gr::Filled(stored->progress, units, stored->requiredUnits);' in add   # capped at the bar, no wrap on a big sum
ai = read('mod-diablocraft/src/monsters/dc_monster_ai.cpp')
spawn = body(ai, 'void SpawnGuardian(Player* killer, Rift& rift)', '\n}\n')
assert 'deadline' not in spawn and 'outcome' not in spawn and 'timeLeft' not in spawn
complete = body(ai, 'bool CompleteGuardianKill(Creature* dead, Unit* killer)', '\n}\n')
assert complete.index('RecordGuardianResult(rift)') < complete.index('RewardGuardian(credit, dead, rift)') \
    < complete.index('CompleteRunQuests(rift.id)')           # result at the death, before any reward settles
veto = body(quests, 'bool OnPlayerBeforeQuestComplete(Player* player, uint32 questId) override', '    // 7.9.7')
assert veto.index('rift.mode == "gr" && rift.outcome != "success"') < veto.index('rift.state == "complete"')
turn = body(quests, 'void HandleTurnIn(Player* player, std::uint32_t questId)', 'Guardian death (7.4)')
assert 'rift.mode == "gr" ? "" : ", outcome=\'success\'"' in turn  # a turn-in never writes a Greater Rift's outcome
drain = body(quests, 'case QuestWork::Complete:', 'case QuestWork::Remove:')
late = body(drain, 'if (work.rift.mode == "gr" && work.rift.outcome != "success")', 'SetQuestProgress')
assert 'FailQuest(work.rift.questId)' in late and 'CompleteQuest' not in late and 'break;' in late
assert drain.index('RemoveTimedQuest(work.rift.questId)') < drain.index('player->CompleteQuest(work.rift.questId)')
assert 'SetQuestSlotTimer(slot, 0)' in drain
elites = affixes_text()
died = body(elites, 'void OnUnitDeath(Unit* unit, Unit* killer) override', 'Avenge(elite);')
# diablocraft-8720: the head count is one PackLife the leader and every member share, and the death
# asks the dying monster's own, never the leader (whose corpse may be gone from the map). S3: every pack death
# goes to DropGreaterOrbs, which counts it (Gr::OrbsFall) whether or not a run is there.
assert 'DropGreaterOrbs(elite);' in died and 'life->Died()' not in died
assert 'livingOthers' not in died and 'orbsDropped' not in elites
drop = body(read('mod-diablocraft/src/rifts/dc_gr_progress.cpp'), 'void DropGreaterOrbs(Creature* dead)', 'void GreaterTick(Map* map)')
assert 'Gr::OrbsFall(*pack->life)' in drop and 'pack->rare, !pack->member' not in drop     # no Nephalem-rare exception (xgms)
assert 'mine->life = state->life;' in elites and 'mine->life->Joined();' in elites
assert 'std::make_shared<Gr::PackLife>()' in read('mod-diablocraft/src/rifts/dc_rifts_internal.h')
rifts = rifts_text()
update = body(rifts, 'void OnMapUpdate(Map* map, uint32 diff) override', 'private:')
assert update.index('DrainClosures(map);') < update.index('GreaterTick(map);') < update.index('else')
assert 'ForgetGreaterOrbs(map->GetInstanceId());' in body(rifts, 'void OnDestroyMap(Map* map) override', 'Rift closing;')
status = body(rifts, 'static bool HandleStatus(ChatHandler* handler)', '// A 3.3.5a client')                  # .dc rift status
# the bar is progress/requiredUnits in both modes; the kill count and `required` (0 since S3) are not printed (review cr1e)
assert 'players {}, progress {}/{}, state {}"' in status and 'rift.progress,\n                                     rift.requiredUnits, rift.state' in status
assert 'kills, state' not in status and 'rift.required,' not in status and 'rift.kills' not in status
assert 'Greater Rift {}: outcome {}' in status and 'progress {}/{}, outcome' not in status
internal = read('mod-diablocraft/src/rifts/dc_rifts_internal.h')
for declaration in ('unsigned KillUnits(Creature* killed, Rift const& rift);', 'bool LoadMonsterProgress(std::string& error);', 'void DropGreaterOrbs(Creature* dead);',
                    'void GreaterTick(Map* map);', 'void RecordGuardianResult(Rift& rift);', 'void GrantGreaterUnlocks(Rift const& rift);',
                    'void ForgetGreaterOrbs(std::uint32_t instanceId);'):
    assert declaration in internal, declaration
assert 'void AddProgress(Player* source, std::uint64_t runId, unsigned units, unsigned kills);' in read(
    'mod-diablocraft/src/rifts/dc_rift_quests.h')
assert 'std::string outcome = "pending";' in read('mod-diablocraft/src/rifts/dc_rifts.h')
contract = read('docs/contracts/greater-rift-tracker.md')
for column in ('gr_rank', 'deadline', 'outcome', 'time_left', 'progress', 'required_units', 'state'):
    assert '`%s`' % column in contract, column

# --- the bar is the quest's own count, one quest per mode (S3): nothing reads a kill baseline any more ------------------------
for path in (MODULE / 'src/rifts').glob('*.cpp'):
    text = path.read_text(encoding='utf-8')
    for gone in ('killsRequired', 'UnitsPerKill', 'nephalemQuests', 'greaterQuests', 'kills_required'):
        assert gone not in text, (path.name, gone)
loader = body(rifts, 'auto const loadBar = [&](bool timed, char const* what)', 'BarQuest const loadedQuest')
assert 'TimeAllowed{} ORDER BY ID' in loader and 'timed ? ">0" : "=0"' in loader
assert 'rows->GetRowCount() != 1 || !bar.units || bar.units > 65535' in loader                  # exactly one quest per mode, inside the 16-bit counter
assert 'rift.requiredUnits = (greater ? greaterQuest : nephalemQuest).units;' in rifts          # the run's bar is the quest's count
assert 'if (!LoadMonsterProgress(progressError))' in rifts
assert 'questId = nephalemQuest.id;' in quests                                                    # the obelisk offers the one Nephalem quest

HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>
using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t; using uint64 = std::uint64_t;
#include "%(header)s"
#include "%(floors)s"
#include "%(complete)s"
namespace DC::Rifts { inline constexpr std::uint32_t CHAMPION_BASE = %(champion_base)d, RARE_BASE = %(rare_base)d; }

#define INVALID_HEIGHT -100000.0f
#define LOG_ERROR(...) (void)0
#define LOG_INFO(...) (void)0

// ---- doubles for the core ----
struct ObjectGuid {
    std::uint64_t value = 0;
    std::uint32_t GetCounter() const { return static_cast<std::uint32_t>(value); }
    bool operator<(ObjectGuid const& other) const { return value < other.value; }
    bool operator==(ObjectGuid const& other) const { return value == other.value; }
};
struct GameObject {
    ObjectGuid guid; std::uint32_t entry = 0; float x = 0, y = 0, z = 0; bool deleted = false;
    ObjectGuid GetGUID() const { return guid; }
    void Delete() { deleted = true; }
};
struct WorldSession {};
std::vector<std::string> chat;
struct ChatHandler { explicit ChatHandler(WorldSession*) {} void SendSysMessage(std::string const& text) { chat.push_back(text); } };
struct Player {
    bool alive = true; float x = 0, y = 0, z = 0; WorldSession session; bool hasSession = true;
    char const* GetName() const { return "the designer"; }
    WorldSession* GetSession() { return hasSession ? &session : nullptr; }
    bool IsAlive() const { return alive; }
    double GetExactDist(float a, float b, float c) const { return std::sqrt((x - a) * (x - a) + (y - b) * (y - b) + (z - c) * (z - c)); }
};
struct Map {
    std::uint32_t id = 1, instance = 0; bool dungeon = true;
    std::vector<std::unique_ptr<GameObject>> made;
    std::vector<Player*> players;
    bool hasGround = true;
    bool IsDungeon() const { return dungeon; }
    std::uint32_t GetInstanceId() const { return instance; }
    std::uint32_t GetId() const { return id; }
    GameObject* GetGameObject(ObjectGuid guid) const {
        for (auto const& object : made) if (object->guid == guid && !object->deleted) return object.get();
        return nullptr;
    }
    float GetHeight(std::uint32_t, float, float, float z, bool = true, float = 0) const { return hasGround ? 28.5f : INVALID_HEIGHT - 1; }
    GameObject* SummonGameObject(std::uint32_t entry, float x, float y, float z, float, float, float, float, float, std::uint32_t) {
        made.push_back(std::make_unique<GameObject>());
        GameObject* object = made.back().get();
        object->guid.value = 1000 + made.size(); object->entry = entry; object->x = x; object->y = y; object->z = z;
        return object;
    }
    template <class F> void DoForAllPlayers(F f) { for (Player* p : players) f(p); }
    unsigned alive() const { unsigned n = 0; for (auto const& o : made) n += !o->deleted; return n; }
};
std::vector<std::pair<std::string, std::vector<std::string>>> centre;   // what the bridge was asked to push: prefix and fields (the centre-screen line)
namespace DC::Bridge { bool Push(Player* player, std::string const& prefix, std::vector<std::string> const& fields) {
    if (!player || !player->GetSession()) return false;
    centre.emplace_back(prefix, fields); return true;
} }
namespace DC::Rifts { struct EliteState { std::shared_ptr<Gr::PackLife> life = std::make_shared<Gr::PackLife>(); bool rare = false, member = false; }; }
std::map<std::uint64_t, Player*> online;
namespace ObjectAccessor { Player* FindPlayer(ObjectGuid guid) { auto found = online.find(guid.value); return found == online.end() ? nullptr : found->second; } }
struct Creature {
    Map* map = nullptr; float x = 10, y = 20, z = 30, o = 0; std::uint32_t entry = 0;
    DC::Rifts::EliteState* state = nullptr;
    struct { DC::Rifts::EliteState** s; template <class T> T* Get(char const*) { return *s; } } CustomData{&state};
    Map* GetMap() const { return map; }
    float GetPositionX() const { return x; } float GetPositionY() const { return y; } float GetPositionZ() const { return z; }
    float GetOrientation() const { return o; }
    std::uint32_t GetPhaseMask() const { return 1; }
    std::uint32_t GetEntry() const { return entry; }
};
namespace GameTime { struct Seconds { long long v; long long count() const { return v; } }; long long clock = 0; Seconds GetGameTime() { return {clock}; } }

// The world database: dc_monster_progress, the rows of the generated migration (entry, hundredths)
struct Field { std::uint32_t v = 0; template <class T> T Get() const { return static_cast<T>(v); } };
struct ResultSet {
    std::vector<std::pair<std::uint32_t, std::uint32_t>> rows; std::size_t at = 0; Field cols[2];
    Field* Fetch() { cols[0].v = rows[at].first; cols[1].v = rows[at].second; return cols; }
    bool NextRow() { return ++at < rows.size(); }
};
using QueryResult = std::shared_ptr<ResultSet>;
std::vector<std::pair<std::uint32_t, std::uint32_t>> progressTable; bool progressTableMissing = false;
struct { QueryResult Query(std::string const& sql) {
    assert(sql == "SELECT entry, hundredths FROM dc_monster_progress");
    if (progressTableMissing) return nullptr;
    auto result = std::make_shared<ResultSet>(); result->rows = progressTable; return result;
} } WorldDatabase;

std::vector<std::string> sql;
struct { template <class... A> void DirectExecute(std::string const& fmt, A const&... args) {
    std::vector<std::string> parts; ((parts.push_back((std::ostringstream() << args).str())), ...);
    std::string out; std::size_t next = 0;
    for (std::size_t i = 0; i < fmt.size(); ++i) {
        if (fmt[i] == '{' && i + 1 < fmt.size() && fmt[i + 1] == '}') { out += parts.at(next++); ++i; } else out += fmt[i];
    }
    sql.push_back(out);
} } CharacterDatabase;

std::map<std::string, std::optional<double>> tunables;
namespace DC::Tunables {
    double Get(std::string const& category, std::string const& name) {
        assert(category == "rifts");
        auto found = tunables.find(name);
        assert(found != tunables.end());
        return found->second.value_or(0.0);
    }
    bool Has(std::string const& category, std::string const& name) {
        assert(category == "rifts");
        auto found = tunables.find(name);
        return found != tunables.end() && found->second.has_value();
    }
}
namespace DC::Rifts {
    struct Rift {
        std::uint64_t id = 0; std::uint32_t instanceId = 0, mapId = 0, dungeonId = 0, guardianInstance = 0; unsigned floor = 1, progress = 0, requiredUnits = 0, grRank = 0, timeLeft = 0, players = 1;
        std::string mode = "nr", state = "open", outcome = "pending"; std::int64_t deadline = 0;
    };
    struct AffixNumbers { float minionSpread = 5; };
    std::mutex riftMutex;
    // The production book (dc_rift_floors.h); a test run's id is 100 + its instance, and live[instance] reads it back
    struct Book : LiveRuns<Rift> { Rift& operator[](unsigned instance) { return *Find(100 + instance); } };
    Book live;
    std::vector<std::string> said;
    void Announce(Rift const&, std::string const& text) { said.push_back(text); }
    unsigned UnitsPerKill() { return 20; }
    std::shared_ptr<AffixNumbers const> Numbers() { return std::make_shared<AffixNumbers const>(); }
    std::vector<std::tuple<std::uint64_t, unsigned, unsigned, Player*>> added;
    void AddProgress(Player* source, std::uint64_t runId, unsigned units, unsigned kills) { added.emplace_back(runId, units, kills, source); }
    std::vector<std::string> cleared;   // the state of each run the tick swept (dc_rift_ai.cpp's ClearGreaterRift)
    bool ClearGreaterRift(Map*, Rift const& rift, Player const*) { cleared.push_back(rift.state); return rift.mode == "gr"; }
    std::vector<ObjectGuid> enrolled;
    std::vector<ObjectGuid> EnrolledGuids(std::uint64_t) { return enrolled; }
    struct GrLevels { unsigned unlocked = 1, beaten = 0; };
    struct GrUnlock { GrLevels before, after; };
    std::vector<std::tuple<std::uint32_t, unsigned, unsigned, bool>> beats;
    std::map<std::uint32_t, GrUnlock> beatResult;
    GrUnlock RecordGreaterRiftBeaten(std::uint32_t guid, unsigned level, unsigned secondsLeft, bool solo) {
        beats.emplace_back(guid, level, secondsLeft, solo); return beatResult[guid];
    }
    // dc_rifts_internal.h's declarations, as the test scans them above
    unsigned KillUnits(Creature* killed, Rift const& rift);
    bool LoadMonsterProgress(std::string& error);
    void DropGreaterOrbs(Creature* dead);
    void GreaterTick(Map* map);
    void RecordGuardianResult(Rift& rift);
    void ForgetGreaterOrbs(std::uint32_t instanceId);
    void GrantGreaterUnlocks(Rift const& rift);
    // Part 11 (Urshi): GreaterTick hands the map to her; her own test is test_urshi.py
    unsigned urshiTicks = 0;
    void UrshiTick(Map* map) { ++urshiTicks; }
}
'''

for line in re.findall(r'^    (?:unsigned|void|bool) (?:KillUnits|LoadMonsterProgress|DropGreaterOrbs|GreaterTick|RecordGuardianResult|ForgetGreaterOrbs|GrantGreaterUnlocks)\([^)]*\);', HARNESS, re.M):
    assert line.strip().replace('std::uint32_t', 'std::uint32_t') in internal, line   # what the harness declares is what the header declares

# BaseEntry, cut out of the family AI as it stands: a champion or rare clone counts as the monster it clones
family_ai = read('mod-diablocraft/src/monsters/dc_family_ai.cpp')
base_entry = body(family_ai, 'std::uint32_t BaseEntry(std::uint32_t entry)', '    bool IsFamilyEntry')
internal_text = read('mod-diablocraft/src/rifts/dc_rifts_internal.h')
bases = re.search(r'inline constexpr std::uint32_t CHAMPION_BASE = (\d+), RARE_BASE = (\d+);', internal_text)
CHAMPION_BASE, RARE_BASE = int(bases.group(1)), int(bases.group(2))
BODY = 'namespace DC::Rifts::Family {\n' + base_entry.rstrip() + '\n}\n' + SOURCE[SOURCE.index('namespace DC::Rifts'):]

# --- the generated table, and the sequence of kills the bar is filled with ------------------------------------------------
import random
progress_sql = read('mod-diablocraft/data/generated/spawn_sheets_0002_progress.sql')
assert progress_sql == read('mod-diablocraft/data/sql/db-world/updates/spawn_sheets_0002_progress.sql')
table = [(int(e), int(h)) for _, e, h in re.findall(r"\('([^']*)', (\d+), (\d+)\)", progress_sql)]
# the same table made another way: the roster's warpath_name -> warpath's points x 100, at the roster's creature entries
import generate_monster_models as models
roster_rows = list(csv.DictReader((MODULE / 'data/d3/monster_roster.csv').open(encoding='utf-8', newline='')))
points = {r['name']: r['progress_points'] for r in warpath}
ids = models.entries()
expected = [(ids[r['name']], round(float(points[r['warpath_name']]) * 100)) for r in roster_rows
            if r['name'] not in models.HELD_BACK and r['warpath_name'] in points]
assert table == expected and len(table) == 59, (len(table), len(expected))
assert len([r for r in roster_rows if r['name'] not in models.HELD_BACK and r['warpath_name'] not in points]) == 5   # these (and the held-back Decaying Cryptstalker, which has no creature) count the default
rng = random.Random(7)
kills, cumulative, full_at, total = [], 0, 0, 0
default_hundredths = round(float(rows['monster_progress_default_points']['d3_value']) * 100)
while not full_at or len(kills) < full_at + 12:
    roll = rng.random()
    if roll < 0.12:
        entry_, hundredths_ = 424242, default_hundredths                            # no row: the default
    else:
        entry_, hundredths_ = rng.choice(table)
        entry_ += rng.choice((0, 0, CHAMPION_BASE, RARE_BASE))                      # a clone counts as the monster it clones
    kills.append((entry_, rng.randrange(3)))
    total += hundredths_
    if not full_at and total >= BAR:
        full_at = len(kills)
sample_entry, sample = table[3]
MAIN_VALUES = {'units': BAR, 'default': float(rows['monster_progress_default_points']['d3_value']),
               'radius': value('gr_orb_pickup_radius_yards'), 'lift': value('nr_orb_lift_yards'), 'entry': entry, 'nr_entry': nr_entry,
               'grc': int(value('gr_orb_champion_count')), 'grr': int(value('gr_orb_rare_count')), 'grp': value('gr_orb_points'),
               'nrc': int(value('nr_orb_champion_count')), 'nrr': int(value('nr_orb_rare_count')), 'nrp': value('nr_orb_points'),
               'grunits': round(value('gr_orb_points') * 100), 'grpct': '%.3g' % (100 * round(value('gr_orb_points') * 100) / BAR), 'nrpct': '%.3g' % (100 * round(value('nr_orb_points') * 100) / BAR),
               'table': ', '.join('{%d, %d}' % row for row in table), 'rows': len(table), 'sample_entry': sample_entry, 'sample': sample,
               'other_entry': table[4][0], 'champion_base': CHAMPION_BASE, 'rare_base': RARE_BASE,
               'kills': ', '.join('{%d, %d}' % k for k in kills), 'expected_sum': total, 'expected_full': full_at}
assert table[4][0] != sample_entry and sample != 100                                  # the sample is not the default by luck
assert MAIN_VALUES['grpct'] == '2.17' and MAIN_VALUES['nrpct'] == '2.17'   # 650 of 30,000

MAIN = r'''
using namespace DC::Rifts;
namespace G = DC::Rifts::Gr;

Map grMap{1, 11}, nrMap{1, 21}, hubMap{0, 0, false}, closedMap{1, 31}, guardianMap{1, 41}, fullMap{1, 51};
Player a, b;
EliteState packState;
Rift& run(Map& map, std::string mode, std::string state) {
    Rift r; r.instanceId = map.instance; r.mapId = 1; r.mode = mode; r.state = state; r.id = 100 + map.instance;
    r.requiredUnits = %(units)d; r.progress = 0; r.deadline = 5000; r.grRank = 17;
    r.guardianInstance = state == "guardian" || state == "complete" ? map.instance : 0;
    live.Start(r); return live[map.instance];
}
// the instance id now names a floor of another map: the core reuses ids
void moveToMap(unsigned instance, std::uint32_t mapId) {
    Rift r = live[instance]; live.Remove(instance, r.mapId); r.mapId = mapId; live.Start(r);
}
std::vector<std::unique_ptr<Creature>> made;
std::vector<std::unique_ptr<EliteState>> states;
void reset() {
    GameTime::clock = 4000; urshiTicks = 0; sql.clear(); said.clear(); added.clear(); cleared.clear(); live.Clear(); packState = EliteState{}; chat.clear(); centre.clear(); beats.clear(); beatResult.clear(); enrolled.clear(); online.clear();
    tunables = {{"monster_progress_default_points", %(default).10g}, {"gr_orb_pickup_radius_yards", %(radius).10g}, {"nr_orb_lift_yards", %(lift).10g},
                {"gr_orb_champion_count", %(grc)d}, {"gr_orb_rare_count", %(grr)d}, {"gr_orb_points", %(grp).10g},
                {"nr_orb_champion_count", %(nrc)d}, {"nr_orb_rare_count", %(nrr)d}, {"nr_orb_points", %(nrp).10g}};
    progressTable = {%(table)s}; progressTableMissing = false; made.clear(); states.clear();
    { std::string error; assert(LoadMonsterProgress(error)); }
    for (Map* m : {&grMap, &nrMap, &closedMap, &guardianMap, &fullMap}) { m->made.clear(); m->players.clear(); m->hasGround = true; }
    run(grMap, "gr", "open"); run(nrMap, "nr", "open"); run(closedMap, "gr", "closed"); run(guardianMap, "gr", "guardian");
    run(fullMap, "gr", "open").progress = %(units)d;
    a = Player{}; b = Player{};
}
bool said_(std::string const& text) { return std::find(said.begin(), said.end(), text) != said.end(); }
// Creatures and packs of the test. A pack is its members sharing one PackLife; member 0 is the leader.
Creature* monster(Map& map, std::uint32_t entry) { made.push_back(std::make_unique<Creature>()); made.back()->map = &map; made.back()->entry = entry; return made.back().get(); }
std::vector<Creature*> pack(Map& map, unsigned members, bool rare) {
    std::vector<Creature*> out; std::shared_ptr<G::PackLife> life = std::make_shared<G::PackLife>();
    for (unsigned i = 0; i < members; ++i) {
        if (i) life->Joined();
        Creature* c = monster(map, 0);
        states.push_back(std::make_unique<EliteState>()); EliteState* st = states.back().get();
        st->life = life; st->rare = rare; st->member = i != 0; c->state = st; out.push_back(c);
    }
    return out;
}
unsigned lying(Map& map, std::uint32_t entry) { unsigned n = 0; for (auto const& o : map.made) n += !o->deleted && o->entry == entry; return n; }

int main() {
    // ---- header: hundredths of a point ----
    assert(G::Hundredths(1.0) == 100 && G::Hundredths(0.56) == 56 && G::Hundredths(7.5) == 750 && G::Hundredths(6.5) == 650);
    assert(G::Hundredths(650) == 65000 && G::Hundredths(0.04) == 4 && G::Hundredths(1.75) == 175);   // exact: warpath's two decimals
    assert(G::Hundredths(0.005) == 1 && G::Hundredths(0.004) == 0);                    // half a hundredth rounds up
    assert(G::Hundredths(0) == 0 && G::Hundredths(-3) == 0 && G::Hundredths(std::nan("")) == 0);   // a loss of progress is no weight
    assert(G::Hundredths(INFINITY) == 0 && G::Hundredths(1e30) == 4000000000u);        // and nothing wraps
    assert(G::KillHundredths(true, 56, 100) == 56 && G::KillHundredths(false, 56, 100) == 100);
    assert(G::KillHundredths(true, 0, 100) == 0);                                      // a row of 0 points is 0, not the default
    assert(G::Filled(0, 100, 65000) == 100 && G::Filled(64950, 100, 65000) == 65000 && G::Filled(65000, 100, 65000) == 65000);
    assert(G::Filled(4000000000u, 4000000000u, 65000) == 65000);                       // no wrap on a big sum
    // ---- header: the orbs a kind of pack drops ----
    {
        G::Orbs c = G::OrbsFor(false, 3, 4, 7.5), r = G::OrbsFor(true, 3, 4, 7.5);
        assert(c.count == 3 && r.count == 4 && c.hundredths == 750 && r.hundredths == 750);
        G::Orbs n = G::OrbsFor(true, 3, 4, 6.5);
        assert(n.count == 4 && n.hundredths == 650);                                   // a Nephalem orb is 650 of the bar
        assert(G::OrbsFor(false, 3.4, 4, 7.5).count == 3 && G::OrbsFor(false, 3.5, 4, 7.5).count == 4);
        assert(G::OrbsFor(false, -1, 4, 7.5).count == 0 && G::OrbsFor(true, 3, std::nan(""), 7.5).count == 0);
        assert(G::OrbsFor(false, 3, 4, -7.5).hundredths == 0 && G::OrbsFor(false, 3, 4, std::nan("")).hundredths == 0);
        assert(G::OrbsFor(false, 1e30, 4, 7.5).count == 4000000000u);
    }
    // ---- header: a pack drops its orbs once, in whatever order its members die (diablocraft-8720) ----
    // A leader and three members share one PackLife; the leader dying first and despawning (it is no
    // longer anywhere to ask) must not make each later member count itself the last. Every order of
    // the four deaths drops exactly once, on the fourth.
    {
        std::vector<int> order{0, 1, 2, 3};
        unsigned orders = 0;
        do {
            G::PackLife life;                                        // the leader's
            for (int i = 0; i < 3; ++i) life.Joined();               // three members share it
            unsigned drops = 0;
            for (int k = 0; k < 4; ++k) {
                bool const dropped = life.Died();
                drops += dropped;
                assert(dropped == (k == 3));                         // only the death that empties the pack
            }
            assert(drops == 1);
            assert(!life.Died());                                    // a stray fifth death drops nothing
            ++orders;
        } while (std::next_permutation(order.begin(), order.end()));
        assert(orders == 24);
        G::PackLife lone; assert(lone.Died() && !lone.Died());       // a lone monster is a pack of one
        G::PackLife two; two.Joined(); assert(!two.Died() && two.Died());
        G::PackLife taken; assert(taken.Drop() && !taken.Drop() && !taken.Died());   // the one drop, taken once, by whoever
    }
    // ---- header: which death drops the orbs (Gr::OrbsFall) ----
    // Every pack, in either rift kind (a Nephalem rare included, diablocraft-xgms), drops exactly once, on its last
    // death, whoever that is: in every order of the four deaths, the leader's own death early or late drops nothing.
    {
        std::vector<int> order{0, 1, 2, 3};
        do {
            G::PackLife life; for (int i = 0; i < 3; ++i) life.Joined();
            unsigned drops = 0; int at = -1;
            for (int k = 0; k < 4; ++k) {
                if (G::OrbsFall(life)) { ++drops; at = k; }
            }
            assert(drops == 1 && at == 3);                           // the last of the pack, whoever it was
        } while (std::next_permutation(order.begin(), order.end()));
        G::PackLife alone; assert(G::OrbsFall(alone) && !G::OrbsFall(alone));   // a rare with no minions
        G::PackLife minion; minion.Joined();
        assert(!G::OrbsFall(minion) && G::OrbsFall(minion) && !G::OrbsFall(minion));   // two members: the second death drops, once
    }
    assert(G::OrbsWanted(true, 0, 65000) && !G::OrbsWanted(false, 0, 65000));
    assert(!G::OrbsWanted(true, 65000, 65000) && G::OrbsWanted(true, 64999, 65000));
    G::Spot s0 = G::OrbSpot(0, 4, 10, 20, 5), s1 = G::OrbSpot(1, 4, 10, 20, 5), s2 = G::OrbSpot(2, 4, 10, 20, 5);
    assert(std::fabs(s0.x - 15) < 1e-4 && std::fabs(s0.y - 20) < 1e-4);
    assert(std::fabs(s1.x - 10) < 1e-4 && std::fabs(s1.y - 25) < 1e-4 && std::fabs(s2.x - 5) < 1e-4);
    G::Spot lone = G::OrbSpot(0, 0, 10, 20, 5); assert(lone.x == 15 && lone.y == 20);   // no count: no division by zero
    assert(G::WithinPickup(5.5, 5.5) && G::WithinPickup(0, 5.5) && !G::WithinPickup(5.51, 5.5));
    assert(!G::WithinPickup(0, 0) && !G::WithinPickup(0, -1) && !G::WithinPickup(0, std::nan("")));
    // ---- header: the clock ----
    assert(G::InTime(4999, 5000) && !G::InTime(5000, 5000) && !G::InTime(5001, 5000));   // 0:00 itself is late
    assert(G::TimeLeft(4700, 5000) == 300 && G::TimeLeft(4999, 5000) == 1 && G::TimeLeft(5000, 5000) == 0 && G::TimeLeft(6000, 5000) == 0);
    assert(std::string(G::OutcomeName(true)) == "success" && std::string(G::OutcomeName(false)) == "expired");
    assert(G::ExpiryDue(true, 5000, 5000) && G::ExpiryDue(true, 9000, 5000) && !G::ExpiryDue(true, 4999, 5000));
    assert(!G::ExpiryDue(false, 9000, 5000) && !G::ExpiryDue(true, 9000, 0) && !G::ExpiryDue(true, 9000, -5));

    // ---- what a kill is worth: the monster's own points, in both modes ----
    reset();
    {
        Rift const& gr = live[11]; Rift const& nr = live[21];
        // every row of the generated table: its exact hundredths, in either mode, as the monster, its champion clone and its rare clone
        for (auto const& [monsterEntry, hundredths] : progressTable) {
            for (std::uint32_t offset : {0u, %(champion_base)du, %(rare_base)du}) {
                Creature* c = monster(grMap, monsterEntry + offset);
                assert(KillUnits(c, gr) == hundredths && KillUnits(c, nr) == hundredths);
            }
        }
        assert(progressTable.size() == %(rows)d);
        // a monster with no row counts the default: 1.0 point = 100
        Creature* none = monster(grMap, 424242);
        assert(KillUnits(none, gr) == 100 && KillUnits(none, nr) == 100);
        assert(KillUnits(monster(grMap, %(champion_base)d + 424242), nr) == 100);
        assert(KillUnits(nullptr, gr) == 100);
        // a pack member and an elite give their own monster's points, not a multiple
        Creature* lead = pack(grMap, 3, false)[0]; lead->entry = %(champion_base)d + %(sample_entry)d;
        assert(KillUnits(lead, gr) == %(sample)d);
        // The designer sets the default: the monsters with no row follow it
        tunables["monster_progress_default_points"] = 2.5;
        assert(KillUnits(none, gr) == 250 && KillUnits(monster(grMap, %(sample_entry)d), gr) == %(sample)d);
        tunables["monster_progress_default_points"] = std::nullopt;
        assert(KillUnits(none, gr) == 0);                                                  // a blank row is nothing yet, never a crash
        // the table reloaded: a row changes at once; a missing table keeps the old one
        progressTable = {{%(sample_entry)d, 7}}; { std::string e; assert(LoadMonsterProgress(e)); }
        assert(KillUnits(monster(grMap, %(sample_entry)d), gr) == 7 && KillUnits(monster(grMap, %(other_entry)d), gr) == 0);
        progressTable = {}; progressTableMissing = true;
        { std::string e; assert(!LoadMonsterProgress(e) && e.find("spawn_sheets_0002_progress.sql") != std::string::npos); }
        assert(KillUnits(monster(grMap, %(sample_entry)d), gr) == 7);
    }

    // ---- the bar fills at %(units)d, from kills on several floors ----
    reset();
    {
        // The kills of one run in the order they fall, on three floors (three maps, three instance ids, one run id): the
        // sample sequence from the sheet. Each is added the way AddProgress adds it (Gr::Filled), and the bar is full on
        // exactly the kill the sheet's own sum says.
        struct Kill { std::uint32_t entry; int floorMap; };
        std::vector<Kill> kills = {%(kills)s};
        unsigned progress = 0, sum = 0, fullAt = 0, kill = 0;
        for (Kill const& k : kills) {
            Map* floors[3] = {&grMap, &nrMap, &fullMap};
            Creature* c = monster(*floors[k.floorMap], k.entry);
            unsigned const units = KillUnits(c, live[11]);
            sum += units; ++kill;
            progress = G::Filled(progress, units, %(units)d);
            assert(progress <= %(units)d && progress == std::min<unsigned>(sum, %(units)d));
            if (progress >= %(units)d && !fullAt) fullAt = kill;
        }
        assert(sum == %(expected_sum)d);                                                   // the sheet's sum, computed beside the C++
        assert(fullAt == %(expected_full)d && progress == %(units)d);                      // full on the kill that crosses the bar, no later and no more
    }

    // ---- a promoted pack's orbs: how many, how much, where, in each mode ----
    reset();
    {
        std::uint32_t const purple = %(entry)d, orange = %(nr_entry)d;
        // Greater Rift: champions 3, a rare 4, each worth 6.5 points, when the last member dies
        auto champions = pack(grMap, 3, false);
        DropGreaterOrbs(champions[0]); DropGreaterOrbs(champions[1]);
        assert(grMap.alive() == 0);                                                        // two of three: nothing yet
        DropGreaterOrbs(champions[2]);
        assert(lying(grMap, purple) == %(grc)d && grMap.alive() == %(grc)d);
        assert(live[11].progress == 0 && added.empty());                                   // the orbs are not progress until taken
        for (unsigned i = 0; i < %(grc)d; ++i) {
            G::Spot spot = G::OrbSpot(i, %(grc)d, 10, 20, 5);
            assert(std::fabs(grMap.made[i]->x - spot.x) < 1e-3 && std::fabs(grMap.made[i]->y - spot.y) < 1e-3);
            assert(std::fabs(grMap.made[i]->z - 28.5f) < 1e-3);                            // on the ground under the body
        }
        grMap.made.clear();
        auto rare = pack(grMap, 4, true);
        for (int i = 0; i < 3; ++i) DropGreaterOrbs(rare[i]);
        assert(grMap.alive() == 0);                                                        // a Greater Rift rare drops with its last minion
        DropGreaterOrbs(rare[3]);
        assert(lying(grMap, purple) == %(grr)d && grMap.alive() == %(grr)d);
        // Nephalem Rift: the same counts, orange, each worth 6.5 points; a champion pack on its last death
        auto nrChampions = pack(nrMap, 3, false);
        DropGreaterOrbs(nrChampions[1]); DropGreaterOrbs(nrChampions[0]);
        assert(nrMap.alive() == 0);
        DropGreaterOrbs(nrChampions[2]);
        assert(lying(nrMap, orange) == %(nrc)d && nrMap.alive() == %(nrc)d);
        for (auto const& o : nrMap.made) assert(std::fabs(o->z - (28.5f + %(lift).10g)) < 1e-3);   // the bare Nephalem sphere floats above the ground; the purple floor aura (above) sits on it
        // a Nephalem rare pack: like every pack, its orbs fall when the whole pack is dead, once only, whichever
        // member falls last (diablocraft-xgms; D3's rare-on-its-own-death is not followed)
        nrMap.made.clear();
        auto nrRare = pack(nrMap, 4, true);
        DropGreaterOrbs(nrRare[2]); DropGreaterOrbs(nrRare[3]);
        assert(nrMap.alive() == 0);                                                        // minions dying drop nothing
        DropGreaterOrbs(nrRare[0]);                                                        // the rare falls with a minion standing
        assert(nrMap.alive() == 0);                                                        // ...and still nothing
        DropGreaterOrbs(nrRare[1]);                                                        // the last minion: the pack drops
        assert(lying(nrMap, orange) == %(nrr)d && nrMap.alive() == %(nrr)d);
        DropGreaterOrbs(nrRare[1]);                                                        // a stray extra death drops nothing more
        assert(nrMap.alive() == %(nrr)d);
        // and the rare dying last drops on that death
        nrMap.made.clear();
        auto lastRare = pack(nrMap, 3, true);
        DropGreaterOrbs(lastRare[1]); DropGreaterOrbs(lastRare[2]);
        assert(nrMap.alive() == 0);
        DropGreaterOrbs(lastRare[0]);
        assert(nrMap.alive() == %(nrr)d);
        // a rare with no minions
        nrMap.made.clear(); auto alone = pack(nrMap, 1, true); DropGreaterOrbs(alone[0]);
        assert(nrMap.alive() == %(nrr)d);
        // no ground found: where the body lay
        grMap.made.clear(); grMap.hasGround = false;
        auto lone = pack(grMap, 1, false); DropGreaterOrbs(lone[0]);
        for (auto const& o : grMap.made) assert(o->z == 30);
        grMap.hasGround = true;
        // not in a live open run, or no pack at all: nothing lies, but a pack's deaths are still counted
        reset();
        Creature* plain = monster(grMap, 0);
        DropGreaterOrbs(plain); DropGreaterOrbs(nullptr);
        for (Map* m : {&hubMap, &closedMap, &guardianMap, &fullMap}) { auto p = pack(*m, 1, false); DropGreaterOrbs(p[0]); }
        assert(grMap.alive() == 0 && hubMap.alive() == 0 && closedMap.alive() == 0 && guardianMap.alive() == 0 && fullMap.alive() == 0);
        {   // the death in a closed map was counted all the same: the pack of one has dropped, so a second call drops nothing
            auto p = pack(closedMap, 1, false); DropGreaterOrbs(p[0]); live[31].state = "open"; DropGreaterOrbs(p[0]);
            assert(closedMap.alive() == 0);
        }
        tunables["gr_orb_champion_count"] = 0;
        auto none = pack(grMap, 1, false); DropGreaterOrbs(none[0]);
        assert(grMap.alive() == 0);                                                        // a count of 0 summons nothing
        tunables["gr_orb_champion_count"] = %(grc)d; moveToMap(11, 9);                     // an instance id reused on another map
        auto moved = pack(grMap, 1, false); DropGreaterOrbs(moved[0]);
        assert(grMap.alive() == 0);
    }

    // ---- a run member walks into an orb, either mode ----
    reset();
    {
        auto champions = pack(grMap, 1, false);
        DropGreaterOrbs(champions[0]);
        grMap.players = {&a, &b};
        a.x = 10 + 60; b.x = 10 + 60;
        GreaterTick(&grMap);
        assert(added.empty() && grMap.alive() == %(grc)d);                                 // nobody near: nothing moves
        a.x = 10; a.y = 20; a.z = 28.5f;                                                   // at the corpse: every orb is within reach
        a.alive = false;
        GreaterTick(&grMap);
        assert(added.empty() && grMap.alive() == %(grc)d);                                 // a dead player takes nothing
        a.alive = true;
        GreaterTick(&grMap);
        assert(added.size() == %(grc)d && grMap.alive() == 0);                             // every orb taken, once each
        assert(chat.size() == %(grc)d && chat[0] == "Progress orb: +%(grpct)s%% of the Greater Rift.");   // each pickup says so (diablocraft-kfsu)
        for (auto const& call : added)
            assert(std::get<0>(call) == live[11].id && std::get<1>(call) == %(grunits)d && std::get<2>(call) == 0 && std::get<3>(call) == &a);
        GreaterTick(&grMap);
        assert(added.size() == %(grc)d);                                                   // taken orbs are gone: no second pickup
    }
    reset();   // a Nephalem Rift's orb adds 650 hundredths = 6.5 points = %(nrpct)s%% of the bar, and says so
    {
        auto rare = pack(nrMap, 2, true);
        DropGreaterOrbs(rare[1]); DropGreaterOrbs(rare[0]);                                // the pack's last death
        nrMap.players = {&a}; a.x = 10; a.y = 20; a.z = 28.5f;
        GreaterTick(&nrMap);
        assert(added.size() == %(nrr)d && nrMap.alive() == 0);
        for (auto const& call : added)
            assert(std::get<0>(call) == live[21].id && std::get<1>(call) == 650 && std::get<2>(call) == 0 && std::get<3>(call) == &a);
        assert(chat.size() == %(nrr)d && chat[0] == "Progress orb: +%(nrpct)s%% of the Nephalem Rift.");
        assert(live[21].outcome == "pending" && live[21].timeLeft == 0 && sql.empty() && cleared.empty() && urshiTicks == 0);   // the clock and Urshi are Greater only
        GameTime::clock = 99999; GreaterTick(&nrMap);
        assert(sql.empty() && live[21].outcome == "pending");                              // a Nephalem Rift has no clock, whatever its deadline
        live[21].deadline = 5000; GreaterTick(&nrMap);
        assert(sql.empty() && live[21].outcome == "pending");
    }
    reset();
    {
        auto champions = pack(grMap, 1, false);
        DropGreaterOrbs(champions[0]);
        grMap.players = {&a, &b};
        float const reach = %(radius).10g;
        G::Spot spot = G::OrbSpot(0, %(grc)d, 10, 20, 5);
        a.x = spot.x + reach + 0.01f; a.y = spot.y; a.z = 28.5f;
        b.x = 500;
        GreaterTick(&grMap);
        unsigned const before = added.size();
        assert(grMap.alive() >= 1 && !(grMap.made[0]->deleted));                           // just out of reach of the first orb
        a.x = spot.x + reach - 0.01f;
        GreaterTick(&grMap);
        assert(grMap.made[0]->deleted && added.size() > before);                           // just in reach of it
        // two members at the same orb: one pickup
        reset(); auto again = pack(grMap, 1, false); DropGreaterOrbs(again[0]);
        grMap.players = {&a, &b};
        a.x = 10; a.y = 20; a.z = 28.5f; b = a;
        GreaterTick(&grMap);
        assert(added.size() == %(grc)d);
        assert(std::get<3>(added[0]) == &a);                                               // the first in the map's list takes it
    }
    reset();   // diablocraft-aejc: the tick sweeps the map while the Guardian is up or just dead, never before
    {
        grMap.players = {&a};
        GreaterTick(&grMap);
        assert(cleared.empty());                                                           // open: nothing to sweep
        live[11].state = "guardian"; live[11].guardianInstance = 11; GreaterTick(&grMap);
        live[11].state = "complete"; GreaterTick(&grMap);
        assert((cleared == std::vector<std::string>{"guardian", "complete"}));
        // rift floors 6.9: another floor of the same run keeps its monsters; the sweep is the Guardian floor's alone
        Map secondFloor{1, 61}; secondFloor.players = {&a}; secondFloor.hasGround = true;
        assert(live.AddFloor(live[11].id, 61, 1, 0) == 2);
        GreaterTick(&secondFloor);
        assert(cleared.size() == 2);
        live[11].state = "closed"; GreaterTick(&grMap);
        assert(cleared.size() == 2);                                                       // closed: the run is over
        cleared.clear(); grMap.players.clear(); live[11].state = "guardian"; GreaterTick(&grMap);
        assert(cleared.empty());                                                           // no player on the map: no one to load anything
        live[21].state = "guardian"; live[21].guardianInstance = 21; nrMap.players = {&a}; GreaterTick(&nrMap);
        assert(cleared.empty());                                                           // a Nephalem Guardian floor is not swept here
    }
    reset();   // the bar fills, or the Guardian is up: the orbs left lying are cleared, not taken
    {
        auto p1 = pack(grMap, 1, false);
        DropGreaterOrbs(p1[0]);
        grMap.players = {&a}; a.x = 10; a.y = 20; a.z = 28.5f;
        live[11].state = "guardian"; live[11].guardianInstance = 11;
        GreaterTick(&grMap);
        assert(added.empty() && grMap.alive() == 0);
        grMap.made.clear(); live[11].state = "open"; auto p2 = pack(grMap, 1, false); DropGreaterOrbs(p2[0]);
        live[11].progress = live[11].requiredUnits;
        GreaterTick(&grMap);
        assert(added.empty() && grMap.alive() == 0);
        grMap.made.clear(); live[11].progress = 0; auto p3 = pack(grMap, 1, false); DropGreaterOrbs(p3[0]);
        for (auto const& o : grMap.made) o->deleted = true;                                // the map removed them itself
        GreaterTick(&grMap);
        assert(added.empty());
        ForgetGreaterOrbs(11);                                                             // and the list was dropped with the map
        auto p4 = pack(grMap, 1, false); DropGreaterOrbs(p4[0]);
        ForgetGreaterOrbs(11);
        GreaterTick(&grMap);
        assert(added.empty() && grMap.alive() == %(grc)d);                                 // nobody near: the orbs wait, lists are fresh
        GreaterTick(&grMap);
        assert(grMap.alive() == %(grc)d);                                                  // the forgotten list's orbs are not tracked again
        // a full Nephalem bar clears its orange orbs the same way
        auto p5 = pack(nrMap, 1, false); DropGreaterOrbs(p5[0]);
        nrMap.players = {&a}; live[21].progress = live[21].requiredUnits;
        GreaterTick(&nrMap);
        assert(added.empty() && nrMap.alive() == 0);
    }

    // ---- the clock runs out ----
    reset();
    {
        GreaterTick(&grMap);
        assert(sql.empty() && live[11].outcome == "pending" && said.empty());                // 4000 < 5000: time left
        GameTime::clock = 4999; GreaterTick(&grMap);
        assert(sql.empty() && live[11].outcome == "pending");                                 // the last second is still in time
        GameTime::clock = 5000; GreaterTick(&grMap);                                          // 0:00
        assert(live[11].outcome == "expired" && live[11].timeLeft == 0);
        assert(sql.size() == 1 && sql[0] == "UPDATE dc_rift SET outcome='expired', time_left=0 WHERE id=111 AND outcome='pending'");
        assert(said.size() == 1 && said_("The Greater Rift timer has run out. Its Guardian can still be killed, "
                                         "but this Greater Rift can no longer be beaten."));
        GameTime::clock = 7000; GreaterTick(&grMap);
        assert(sql.size() == 1 && said.size() == 1);                                          // once
        assert(live[11].state == "open" && live[11].progress == 0);                           // nothing else about the run changes
        live[41].outcome = "success"; GreaterTick(&guardianMap);
        assert(live[41].outcome == "success" && sql.size() == 1);                             // a result is kept
        GreaterTick(&nrMap); GreaterTick(&hubMap); GreaterTick(&closedMap); GreaterTick(nullptr);
        assert(live[21].outcome == "pending" && live[31].outcome == "pending" && sql.size() == 1);
        live[51].deadline = 0; GreaterTick(&fullMap);
        assert(live[51].outcome == "pending");                                                // no deadline, no expiry
    }

    // ---- the Guardian dies: beaten or failed, and the time left ----
    reset();
    {
        GameTime::clock = 4700;                                                               // 5:00 left
        Rift rift = live[41];
        RecordGuardianResult(rift);
        assert(rift.outcome == "success" && rift.timeLeft == 300);
        assert(live[41].outcome == "success" && live[41].timeLeft == 300);
        assert(sql.size() == 1 && sql[0] == "UPDATE dc_rift SET outcome='success', time_left=300 WHERE id=141 AND outcome='pending'");
        assert(said_("Greater Rift 17 beaten with 5:00 left on the clock."));
        RecordGuardianResult(rift);
        assert(sql.size() == 1 && rift.timeLeft == 300);                                      // once
    }
    reset();
    {
        GameTime::clock = 4999; Rift rift = live[41]; RecordGuardianResult(rift);
        assert(rift.outcome == "success" && rift.timeLeft == 1 && said_("Greater Rift 17 beaten with 0:01 left on the clock."));
    }
    reset();
    {
        GameTime::clock = 5000; Rift rift = live[41]; RecordGuardianResult(rift);             // the second the clock hits 0:00
        assert(rift.outcome == "expired" && rift.timeLeft == 0 && live[41].outcome == "expired");
        assert(sql[0] == "UPDATE dc_rift SET outcome='expired', time_left=0 WHERE id=141 AND outcome='pending'");
        assert(said_("The Guardian fell after the clock ran out. Greater Rift 17 is not beaten."));
    }
    reset();
    {
        GameTime::clock = 6000;                                                               // the tick got there first
        GreaterTick(&grMap); live[41].outcome = "expired"; live[41].timeLeft = 0;
        sql.clear(); said.clear();
        Rift rift = live[41]; RecordGuardianResult(rift);
        assert(rift.outcome == "expired" && sql.empty());                                     // no second write
        assert(said_("The Guardian fell after the clock ran out. Greater Rift 17 is not beaten."));
    }
    reset();
    {
        Rift nr = live[21]; GameTime::clock = 4700; RecordGuardianResult(nr);
        assert(nr.outcome == "pending" && sql.empty() && said.empty());                       // a Nephalem Rift keeps its own rules
        live[41].deadline = 0; Rift none = live[41]; RecordGuardianResult(none);
        assert(none.outcome == "expired");                                                    // no deadline is never a beaten run
        assert(beats.empty());
    }

    // ---- an in-time kill unlocks on every enrolled member's own character ----
    reset();
    {
        Player online1, online2; online[7] = &online1; online[8] = &online2;                  // 9 is offline
        enrolled = {ObjectGuid{7}, ObjectGuid{8}, ObjectGuid{9}};
        beatResult[7] = GrUnlock{{1, 0}, {19, 17}};                                           // moves up: told
        beatResult[8] = GrUnlock{{30, 20}, {30, 20}};                                         // already higher: not told
        beatResult[9] = GrUnlock{{1, 0}, {19, 17}};                                           // offline: written, nobody to tell
        live[41].players = 3;
        GameTime::clock = 4700; Rift rift = live[41]; RecordGuardianResult(rift);
        assert(beats.size() == 3);
        for (auto const& beat : beats) assert(std::get<1>(beat) == 17 && std::get<2>(beat) == 300 && std::get<3>(beat) == false);   // level, seconds left, not solo
        assert(std::get<0>(beats[0]) == 7 && std::get<0>(beats[1]) == 8 && std::get<0>(beats[2]) == 9);
        assert(chat.size() == 1 && chat[0] == "You can now open Greater Rift 19.");
        // the in-time kill pushes D3's line (the centre-screen channel) to each enrolled member who is online (9 is not), once
        std::vector<std::string> const want = {"C", "gr_complete", "b2b2b2", "Greater Rift Complete! You finished with ", "00ff00", "5 minutes", "b2b2b2", " remaining."};
        assert(centre.size() == 2 && centre[0].first == "DCRIFTTEXT" && centre[0].second == want && centre[1] == centre[0]);
        assert(want == DC::Rifts::Text::Fields(DC::Rifts::Text::GreaterRiftComplete, DC::Rifts::Gr::CompleteParts(300)));
        RecordGuardianResult(rift);
        assert(beats.size() == 3 && chat.size() == 1 && centre.size() == 2);                  // once
    }
    reset();
    {
        enrolled = {ObjectGuid{7}}; live[41].players = 1;                                     // a solo run
        GameTime::clock = 4700; Rift rift = live[41]; RecordGuardianResult(rift);
        assert(beats.size() == 1 && std::get<3>(beats[0]) == true);
        assert(centre.empty());                                                           // a solo run: the member is not online at the kill
        Player gone; gone.hasSession = false; online[7] = &gone; beatResult[7] = GrUnlock{{1, 0}, {19, 17}};
        beats.clear(); rift.outcome = "success";
        GrantGreaterUnlocks(rift);                                                            // no session: written, no message, no crash
        assert(beats.size() == 1 && chat.empty());
        rift.outcome = "expired"; beats.clear(); GrantGreaterUnlocks(rift);
        assert(beats.empty());                                                                // a failed run unlocks nothing
        Rift nr = live[21]; nr.outcome = "success"; GrantGreaterUnlocks(nr);
        assert(beats.empty());                                                                // nor does a Nephalem Rift
    }
    reset();   // late, or the clock already out: nobody is raised
    {
        enrolled = {ObjectGuid{7}};
        GameTime::clock = 5000; Rift late = live[41]; RecordGuardianResult(late);
        assert(beats.empty() && centre.empty());                                              // a late kill has no completed line
        GameTime::clock = 6000; GreaterTick(&grMap); live[41].outcome = "expired"; Rift out = live[41]; RecordGuardianResult(out);
        assert(beats.empty());
    }
    return 0;
}
''' % MAIN_VALUES

code = (HARNESS % {'header': HEADER.as_posix(), 'floors': (MODULE / 'src/rifts/dc_rift_floors.h').as_posix(), 'complete': (MODULE / 'src/rifts/dc_gr_complete.h').as_posix(),
                   'champion_base': CHAMPION_BASE, 'rare_base': RARE_BASE}) + BODY + MAIN

compiler = shutil.which('g++') or shutil.which('c++')
if not compiler:
    raise SystemExit('g++ is not on PATH; this harness compiles a small C++ program')
with tempfile.TemporaryDirectory(prefix='dc-gr-progress-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(code, encoding='utf-8')
    subprocess.run([compiler, '-std=c++20', '-UNDEBUG', '-Wall', '-Wno-unused', '-o', str(folder / 'gr_progress'),
                    str(folder / 'test.cpp')], check=True)
    harness_env.run([str(folder / 'gr_progress')], check=True)
print('PASS: Greater Rift progress: kill weights, orbs, pickup, the clock, the Guardian result, wiring, tunables.')
