"""The six Greater Rift rules and the XP split (diablocraft-214r, greater-rifts brief part 7).

Compiles the production pieces against core doubles:
  - dc_gr_rules.h as it is (the lock state, the revive wait, the denied object types, the XP split);
  - the whole body of dc_gr_rules.cpp, with the core's classes replaced by small doubles: the
    PlayerScript hooks (deaths, equip, unequip, summon-teleport), the clickables hook, and the five
    exported answers are called as the core calls them, against runs held in the live map;
with the revive and XP numbers read from data/tunables/rifts.csv. Source scans cover what a double
cannot reach (where the other modules ask these answers, that the skill bar already refuses inside an
instance); the test says so below.

Cross-source: the object types equal SharedDefines.h's; the two Town Portal entries equal
dc_town_portal.cpp's; the tunables the code reads are rows of rifts.csv and its generated SQL; the 5 and 30
are greater_rifts.csv's; the step is the designer's 5 (card q-1006-03, diablocraft-tq4j); the two XP rows he sets are blank.

DC_GR_RULES_SOURCE and DC_GR_RULES_HEADER point the compile at mutated copies (mutation runs)."""
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
from split_sources import rifts_text  # noqa: E402
import harness_env
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
CPP = Path(os.environ.get('DC_GR_RULES_SOURCE', MODULE / 'src/rifts/dc_gr_rules.cpp'))
HEADER = Path(os.environ.get('DC_GR_RULES_HEADER', MODULE / 'src/rifts/dc_gr_rules.h'))
SOURCE = CPP.read_text(encoding='utf-8')


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def body(text: str, start: str, end: str) -> str:
    """The text from `start` up to (not including) the next `end` after it."""
    first = text.index(start)
    return text[first:text.index(end, first)]


# --- cross-source: the tunables the code reads exist, with the numbers greater_rifts.csv names ----
rows = {r['name']: r for r in csv.DictReader((MODULE / 'data/tunables/rifts.csv').open(encoding='utf-8', newline=''))}
read_names = set(re.findall(r'(?:Seconds|Tunables::(?:Get|Has))\(\s*(?:"rifts",\s*)?"(gr_\w+)"', SOURCE))
assert read_names == {'gr_revive_wait_first_seconds', 'gr_revive_wait_max_seconds', 'gr_revive_wait_step_seconds',
                      'gr_monster_xp_pct', 'gr_guardian_xp_multiple'}, read_names
FIRST = int(tunables_csv.value('rifts', 'gr_revive_wait_first_seconds'))
MAX = int(tunables_csv.value('rifts', 'gr_revive_wait_max_seconds'))
assert (FIRST, MAX) == (5, 30)
STEP = int(tunables_csv.value('rifts', 'gr_revive_wait_step_seconds'))
assert STEP == 5   # the designer, card q-1006-03 (docs/decisions.md 2026-10-06): 5 s first, +5 per death, 30 s cap
assert rows['gr_revive_wait_step_seconds']['d3_value'] == '' and 'q-1006-03' in rows['gr_revive_wait_step_seconds']['notes']
assert 'respawn delay grows 5s' in read('mod-diablocraft/data/d3/greater_rifts.csv')   # where the 5 and the 30 come from
for name in ('gr_monster_xp_pct', 'gr_guardian_xp_multiple'):
    # The designer's numbers: nobody published them, so the sheet leaves both cells blank (AGENTS.md "Numbers"; XP stays so, q-1006-03)
    assert rows[name]['d3_value'] == '' and rows[name]['value'] == '' and 'ALEX SETS IT' in rows[name]['notes'], name
    try:
        tunables_csv.value('rifts', name)
        raise AssertionError(name + ' must stay blank until the designer sets it')
    except tunables_csv.MissingTunable:
        pass
generated = read('mod-diablocraft/data/generated/tunables_0008.sql')
migration = read('mod-diablocraft/data/sql/db-world/updates/tunables_0008.sql')
for name, d3, tuned in (('gr_revive_wait_first_seconds', '5.0', 'NULL'), ('gr_revive_wait_max_seconds', '30.0', 'NULL'),
                         ('gr_revive_wait_step_seconds', 'NULL', '5.0'), ('gr_monster_xp_pct', 'NULL', 'NULL'),
                         ('gr_guardian_xp_multiple', 'NULL', 'NULL')):
    for sql in (generated, migration):
        assert re.search(r"\('rifts', '%s', %s, %s," % (name, re.escape(d3), tuned), sql), name

# --- cross-source: the object types and the Town Portal entries are the core's and the module's ----
defs = read('azerothcore-wotlk/src/server/shared/SharedDefines.h')
types = {n: int(v) for n, v in re.findall(r'GAMEOBJECT_TYPE_(\w+)\s*=\s*(\d+)', defs)}
header_text = HEADER.read_text(encoding='utf-8')
denied = {int(n) for n in re.findall(r'goType == (\d+)', body(header_text, 'inline bool ClickableDenied', '}'))}
assert denied == {types[n] for n in ('CHEST', 'GOOBER', 'SUMMONING_RITUAL', 'SPELLCASTER', 'MEETINGSTONE')}, denied
assert not denied & {types[n] for n in ('DOOR', 'BUTTON', 'QUESTGIVER')}   # doors and levers-as-buttons still work
portal = read('mod-diablocraft/src/rifts/dc_town_portal.cpp')
match = re.search(r'SOURCE_OBJECT = (\d+), HUB_OBJECT = (\d+)', portal)
entries = {int(n) for n in re.findall(r'entry == (\d+)', body(header_text, 'inline bool TownPortalEntry', '}'))}
assert entries == {int(match.group(1)), int(match.group(2))}, entries

# --- what the doubles cannot reach: where the other modules ask these answers --------------------
loot = read('mod-diablocraft/src/loot/dc_loot.cpp')
kill = body(loot, 'void OnPlayerCreatureKill(Player* killer, Creature* killed) override', 'auto rollFor')
assert kill.index('IsIllusion(killed)') < kill.index('GreaterRiftNoLoot(killed)') < len(kill)  # before any roll
assert 'RollLoot(' not in kill
hardcore = read('mod-diablocraft/src/hardcore/dc_hardcore.cpp')
choose = body(hardcore, 'void Choose(Player& player', 'void QueueLogout')
# diablocraft-uxps: the town refusal moved into Unavailable, which Choose asks first (and the O record asks too)
assert choose.index('Unavailable(&player, asked)') < choose.index('GreaterRiftReviveWaitLeft(&player)') \
    < choose.index('Resolve(&player, asked)')
assert 'GreaterRiftTownReviveRefused(player)' in body(hardcore, 'std::string Unavailable(Player* player, Choice choice)', 'Destination Resolve')
update = body(hardcore, 'void OnPlayerUpdate(Player* player, uint32) override', 'entry = found->second')
assert '!found->second.hardcore && DC::Rifts::GreaterRiftReviveWaitLeft(player)' in update  # the release path waits too
inventory = read('mod-diablocraft/src/items/dc_inventory.cpp')
potion = body(inventory, 'void ChangePotion(Player* player, Item* source)', 'std::uint32_t const previous')
assert 'Need(!DC::Rifts::GreaterRiftGearLocked(player)' in potion
paragon = read('mod-diablocraft/src/paragon/dc_paragon.cpp')
assert paragon.count('Rifts::GreaterRiftXp(') == 2  # the levelling award and the Paragon kill award
assert 'GreaterRiftXp(victim,amount)' in body(paragon, 'auto amount=KillXP', 'AddXP(member')
assert 'GreaterRiftXp(victim->ToCreature(), amount)' in body(paragon, 'void OnPlayerGiveXP', 'void OnPlayerSetMaxLevel')
rifts = rifts_text()
public = read('mod-diablocraft/src/rifts/dc_rifts.h')
for declaration in ('bool GreaterRiftNoLoot(Creature const* creature);', 'bool GreaterRiftGearLocked(Player const* player);',
                    'bool GreaterRiftTownReviveRefused(Player const* player);',
                    'bool GreaterRiftGuardianDead(Player const* player);',
                    'unsigned GreaterRiftReviveWaitLeft(Player const* player);',
                    'std::uint64_t GreaterRiftXp(Creature const* victim, std::uint64_t amount);'):
    assert declaration in public, declaration
DECLARATIONS = public
assert 'RegisterGreaterRiftRuleScripts();' in body(rifts, 'void RegisterScripts()', '} // namespace')
assert 'new GreaterRiftRules();' in SOURCE and 'new GreaterRiftClickables();' in SOURCE
for hook in ('PLAYERHOOK_ON_PLAYER_JUST_DIED', 'PLAYERHOOK_CAN_EQUIP_ITEM', 'PLAYERHOOK_CAN_UNEQUIP_ITEM',
             'PLAYERHOOK_ON_BEFORE_TELEPORT'):
    assert hook in SOURCE, hook
# Rule 6's skill half is the bar's own refusal inside every instance (04 section 3), which gives way in a Greater
# Rift whose Guardian is dead (card q-1006-03): both writers keep the refusal and both ask the one answer.
classes = read('mod-diablocraft/src/classes/dc_classes.cpp')
for fn in ('bool SetSlot(Player* player', 'bool SetPassive(Player* player'):
    part = body(classes, fn, '\n}\n')
    assert 'GetMap()->Instanceable() && !DC::Rifts::GreaterRiftGuardianDead(player)' in part, fn
    assert 'Not inside an instance or rift.' in part, fn
    assert part.index('IsInCombat()') < part.index('GreaterRiftGuardianDead(player)')   # combat still refuses first
assert '#include "../rifts/dc_rifts.h"' in classes
# Rule 4's only named-player teleport is the accepted summon; rule 2 and the banner half have no content to refuse.
core_player = read('azerothcore-wotlk/src/server/game/Entities/Player/Player.cpp')
assert re.search(r'TeleportTo\(m_summon_mapid[^;]*ObjectAccessor::FindPlayer\(summoner_guid\)\)', core_player)
for path in (MODULE / 'src').rglob('*'):
    if path.suffix in ('.cpp', '.h') and path.name != 'dc_gr_rules.cpp':
        assert not re.search(r'goblin|banner', path.read_text(encoding='utf-8'), re.I), path

HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t;
#include "%(header)s"
#include "%(rewards)s"
#include "%(floors)s"
#include "%(pylons)s"

// ---- doubles for the core ----
std::uint32_t now = 100000;
std::uint32_t getMSTime() { return now; }
struct Map {
    std::uint32_t id = 1, instance = 0; bool dungeon = true;
    bool IsDungeon() const { return dungeon; }
    std::uint32_t GetInstanceId() const { return instance; }
    std::uint32_t GetId() const { return id; }
};
struct WorldSession {};
std::vector<std::string> said;
struct ChatHandler {
    explicit ChatHandler(WorldSession*) {}
    void SendSysMessage(std::string const& text) { said.push_back(text); }
};
struct Guid { std::uint32_t counter; std::uint32_t GetCounter() const { return counter; } };
struct Player;
struct Unit {
    virtual ~Unit() = default;
    Player* ToPlayer();
};
struct Item {};
struct Player : Unit {
    Map* map = nullptr; std::uint32_t guid = 0; WorldSession session; bool hasSession = true;
    Map* GetMap() const { return map; }
    Guid GetGUID() const { return {guid}; }
    WorldSession* GetSession() { return hasSession ? &session : nullptr; }
};
Player* Unit::ToPlayer() { return dynamic_cast<Player*>(this); }
struct Creature { Map* map = nullptr; std::uint32_t entry = 0; Map* GetMap() const { return map; } std::uint32_t GetEntry() const { return entry; } };
struct GameObject {
    Map* map = nullptr; unsigned type = 0; std::uint32_t entry = 0;
    Map* FindMap() const { return map; }
    unsigned GetGoType() const { return type; }
    std::uint32_t GetEntry() const { return entry; }
};
enum { PLAYERHOOK_ON_PLAYER_JUST_DIED, PLAYERHOOK_CAN_EQUIP_ITEM, PLAYERHOOK_CAN_UNEQUIP_ITEM, PLAYERHOOK_ON_BEFORE_TELEPORT };
struct PlayerScript {
    PlayerScript(char const*, std::vector<int>) {}
    virtual ~PlayerScript() = default;
    virtual void OnPlayerJustDied(Player*) {}
    virtual bool OnPlayerCanEquipItem(Player*, uint8, uint16&, Item*, bool, bool) { return true; }
    virtual bool OnPlayerCanUnequipItem(Player*, uint16, bool) { return true; }
    virtual bool OnPlayerBeforeTeleport(Player*, uint32, float, float, float, float, uint32, Unit*) { return true; }
};
struct AllGameObjectScript {
    explicit AllGameObjectScript(char const*) {}
    virtual ~AllGameObjectScript() = default;
    virtual bool CanGameObjectGossipHello(Player*, GameObject*) { return false; }
};

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
    struct Rift { std::uint64_t id = 0; std::uint32_t instanceId = 0, mapId = 0, dungeonId = 0; unsigned floor = 1; std::string mode = "nr", state = "open"; unsigned grRank = 0; };
    std::mutex riftMutex;
    // The production book (dc_rift_floors.h); a test run's id is 100 + its instance, and live[instance] reads it back
    struct Book : LiveRuns<Rift> { Rift& operator[](unsigned instance) { return *Find(100 + instance); } };
    Book live;
    bool IsGuardianEntry(std::uint32_t entry) { return entry == 777; }
    // dc_gr_rewards.cpp's answer (its own test drives it): the double records the level it was asked for
    // rift floors Part F2: dc_rifts.cpp's answer for the floors' exit portal templates (test_rift_exit.py checks it against the sheet)
    bool IsExitPortal(std::uint32_t entry) { return entry >= 910070 && entry <= 918086 && entry %% 1000 >= 70 && entry %% 1000 <= 86; }
    double xpFactor = 1.0; unsigned xpAskedLevel = 999;
    double GuardianXpFactor(unsigned level) { xpAskedLevel = level; return xpFactor; }
    // dc_rifts.h's declarations, as the test scans them below
    bool GreaterRiftNoLoot(Creature const* creature);
    bool GreaterRiftGearLocked(Player const* player);
    bool GreaterRiftTownReviveRefused(Player const* player);
    bool GreaterRiftGuardianDead(Player const* player);
    unsigned GreaterRiftReviveWaitLeft(Player const* player);
    std::uint64_t GreaterRiftXp(Creature const* victim, std::uint64_t amount);
}
'''

for line in re.findall(r'^    (?:bool|unsigned|std::uint64_t) GreaterRift\w+\([^)]*\);', HARNESS, re.M):
    assert line.strip() in DECLARATIONS, line   # what the harness declares is what dc_rifts.h declares

# The module's own body, with its includes taken out (the doubles above stand in for them).
BODY = '\n'.join(line for line in SOURCE[SOURCE.index('namespace DC::Rifts'):].splitlines())

MAIN = r'''
using namespace DC::Rifts;
namespace G = DC::Rifts::Gr;

Map grMap{1, 11}, grMap2{1, 12}, nrMap{1, 21}, hubMap{0, 0, false}, closedMap{1, 31};
Player a, b, outsider;
std::uint32_t HUB_PORTAL = 910013, SOURCE_PORTAL = 910012;

void run(std::uint32_t instance, std::string mode, std::string state) {
    Rift r; r.id = 100 + instance; r.instanceId = instance; r.mapId = 1; r.mode = mode; r.state = state;
    live.Start(r);
}
// the instance id now names a floor of another map: the core reuses ids
void moveToMap(unsigned instance, std::uint32_t mapId) {
    Rift r = live[instance]; live.Remove(instance, r.mapId); r.mapId = mapId; live.Start(r);
}
void reset() {
    now = 100000; said.clear(); live.Clear(); deaths.clear();
    tunables = {{"gr_revive_wait_first_seconds", %(first)d}, {"gr_revive_wait_max_seconds", %(max)d},
                {"gr_revive_wait_step_seconds", %(step)d}, {"gr_monster_xp_pct", 50}, {"gr_guardian_xp_multiple", 3}};
    run(11, "gr", "open"); run(12, "gr", "guardian"); run(21, "nr", "open"); run(31, "gr", "closed");
    a = Player{}; a.guid = 1; a.map = &grMap; b = Player{}; b.guid = 2; b.map = &grMap;
    outsider = Player{}; outsider.guid = 3; outsider.map = &hubMap;
}
bool said_(std::string const& text) { return std::find(said.begin(), said.end(), text) != said.end(); }
std::string const NO_GEAR = "You cannot change your gear in a Greater Rift until its Guardian is dead.";

int main() {
    // ---- header: the revive wait, both edges ----
    assert(G::ReviveWaitSeconds(0, 5, 5, 30) == 0);
    assert(G::ReviveWaitSeconds(1, 5, 5, 30) == 5 && G::ReviveWaitSeconds(2, 5, 5, 30) == 10);
    assert(G::ReviveWaitSeconds(6, 5, 5, 30) == 30 && G::ReviveWaitSeconds(7, 5, 5, 30) == 30);   // capped, not past it
    assert(G::ReviveWaitSeconds(5, 5, 5, 30) == 25);
    assert(G::ReviveWaitSeconds(4, 5, 0, 30) == 5);                      // no step set: no growth
    assert(G::ReviveWaitSeconds(3, 40, 5, 30) == 40);                    // a first wait above the cap is the first wait
    assert(G::ReviveWaitSeconds(4000000000u, 5, 4000000000u, 30) == 30); // no overflow
    assert(G::WaitLeftSeconds(1000, 5, 1000) == 5 && G::WaitLeftSeconds(1000, 5, 1001) == 5);   // 4.999 s left shows 5
    assert(G::WaitLeftSeconds(1000, 5, 1999) == 5 && G::WaitLeftSeconds(1000, 5, 2000) == 4 && G::WaitLeftSeconds(1000, 5, 5999) == 1);
    assert(G::WaitLeftSeconds(1000, 5, 6000) == 0 && G::WaitLeftSeconds(1000, 5, 9000) == 0);
    assert(G::WaitLeftSeconds(0xFFFFFF00u, 5, 0xFFFFFF00u + 3000) == 2);                      // the 32-bit ms clock wraps
    assert(G::WaitLeftSeconds(0xFFFFFF00u, 5, 4000) == 1);
    assert(G::WaitLeftSeconds(1000, 0, 1000) == 0);
    // ---- header: lock state and the XP split ----
    assert(G::GuardianAlive("open") && G::GuardianAlive("guardian"));
    assert(!G::GuardianAlive("complete") && !G::GuardianAlive("closed") && !G::GuardianAlive(""));
    G::XpSplit both{true, true, 50.0, 3.0}, none;
    assert(G::SplitXp(100, false, both) == 50 && G::SplitXp(100, true, both) == 300);
    assert(G::SplitXp(101, false, both) == 50 && G::SplitXp(7, true, both) == 21);                // whole XP, rounded down
    assert(G::SplitXp(100, false, none) == 100 && G::SplitXp(100, true, none) == 100);           // unset: unchanged
    G::XpSplit monsterOnly{true, false, 25.0, 9.0}, guardianOnly{false, true, 25.0, 9.0};
    assert(G::SplitXp(100, true, monsterOnly) == 100 && G::SplitXp(100, false, monsterOnly) == 25);
    assert(G::SplitXp(100, false, guardianOnly) == 100 && G::SplitXp(100, true, guardianOnly) == 900);
    G::XpSplit negative{true, true, -50.0, -3.0};
    assert(G::SplitXp(100, false, negative) == 100 && G::SplitXp(100, true, negative) == 100);    // a broken number is no split
    G::XpSplit huge{false, true, 100.0, 1e30};
    assert(G::SplitXp(1ull << 60, true, huge) == UINT64_MAX);
    assert(G::SplitXp(0, true, both) == 0);
    for (unsigned t = 0; t < 30; ++t)
        assert(G::ClickableDenied(t) == (t == 3 || t == 10 || t == 18 || t == 22 || t == 23));
    assert(G::TownPortalEntry(910012) && G::TownPortalEntry(910013) && !G::TownPortalEntry(910011) && !G::TownPortalEntry(910014));

    // ---- rule 1: only the Guardian rolls loot ----
    reset();
    {
        Creature monster{&grMap, 100}, guardian{&grMap, 777}, nr{&nrMap, 100}, open{&hubMap, 100}, late{&closedMap, 100};
        assert(GreaterRiftNoLoot(&monster));
        assert(!GreaterRiftNoLoot(&guardian));                         // the Guardian is the one that drops
        assert(!GreaterRiftNoLoot(&nr) && !GreaterRiftNoLoot(&open));  // a Nephalem Rift and the open world are as before
        assert(GreaterRiftNoLoot(&late));                              // a run that closed still pays nothing to a straggler
        assert(!GreaterRiftNoLoot(nullptr));
        Creature stale{&grMap, 100}; moveToMap(11, 9);                     // an instance id reused on another map is not this run
        assert(!GreaterRiftNoLoot(&stale));
    }

    // ---- rule 6: gear is locked while the Guardian lives ----
    reset();
    {
        GreaterRiftRules rules;
        uint16 dest = 0; Item item;
        assert(GreaterRiftGearLocked(&a));                                         // state open
        Player guardianUp = a; guardianUp.map = &grMap2;
        assert(GreaterRiftGearLocked(&guardianUp));                                // state guardian
        assert(!GreaterRiftGearLocked(&outsider) && !GreaterRiftGearLocked(nullptr));
        Player nr = a; nr.map = &nrMap;
        assert(!GreaterRiftGearLocked(&nr));                                       // a Nephalem Rift keeps the core's rules
        Player late = a; late.map = &closedMap;
        assert(!GreaterRiftGearLocked(&late));                                     // closed: nothing to lock
        assert(!rules.OnPlayerCanEquipItem(&a, 0, dest, &item, false, true) && said_(NO_GEAR));
        said.clear();
        assert(rules.OnPlayerCanEquipItem(&a, 0, dest, &item, false, false) && said.empty());   // loading worn gear at login
        assert(rules.OnPlayerCanEquipItem(&outsider, 0, dest, &item, false, true) && said.empty());
        assert(!rules.OnPlayerCanUnequipItem(&a, 0, false) && said_(NO_GEAR));
        said.clear();
        assert(!rules.OnPlayerCanUnequipItem(&a, 0, true) && said.empty());        // a swap: the equip side speaks
        assert(rules.OnPlayerCanUnequipItem(&outsider, 0, false) && rules.OnPlayerCanUnequipItem(&nr, 0, false));
        live[11].state = "complete";                                               // the Guardian dies: gear is free
        said.clear();
        assert(!GreaterRiftGearLocked(&a));
        assert(rules.OnPlayerCanEquipItem(&a, 0, dest, &item, true, true));
        assert(rules.OnPlayerCanUnequipItem(&a, 0, false) && said.empty());
        a.hasSession = false;                                                      // no session: refuse quietly, never crash
        live[11].state = "open";
        assert(!rules.OnPlayerCanEquipItem(&a, 0, dest, &item, false, true));
    }

    // ---- rule 4: no summon to or from a Greater Rift until the Guardian is dead ----
    reset();
    {
        GreaterRiftRules rules;
        std::string const msg = "You cannot be summoned to or from a Greater Rift until its Guardian is dead.";
        assert(!rules.OnPlayerBeforeTeleport(&outsider, 1, 0, 0, 0, 0, 0, &a) && said_(msg));        // summoned INTO the rift
        said.clear();
        assert(!rules.OnPlayerBeforeTeleport(&a, 0, 0, 0, 0, 0, 0, &outsider) && said_(msg));        // summoned OUT of it
        Player outsider2 = outsider; outsider2.guid = 9;
        assert(rules.OnPlayerBeforeTeleport(&outsider, 0, 0, 0, 0, 0, 0, &outsider2));               // two players elsewhere
        assert(rules.OnPlayerBeforeTeleport(&a, 0, 0, 0, 0, 0, 0, nullptr));                         // Town Portal, a blink: no target
        Player nr = a; nr.map = &nrMap; Player nr2 = b; nr2.map = &nrMap;
        assert(rules.OnPlayerBeforeTeleport(&nr, 1, 0, 0, 0, 0, 0, &nr2));                           // Nephalem Rift: as before
        Unit unit;
        assert(rules.OnPlayerBeforeTeleport(&a, 1, 0, 0, 0, 0, 0, &unit));                           // a target that is no player
        live[11].state = "complete";
        assert(rules.OnPlayerBeforeTeleport(&outsider, 1, 0, 0, 0, 0, 0, &a));                       // Guardian dead: allowed
        live[11].state = "open"; a.hasSession = false; outsider.hasSession = false;
        assert(!rules.OnPlayerBeforeTeleport(&outsider, 1, 0, 0, 0, 0, 0, &a));                      // still refused with no session
    }

    // ---- rule 3: no chest, goober or other clickable; doors and the caster's own portal stay ----
    reset();
    {
        GreaterRiftClickables clickables;
        auto use = [&](unsigned type, std::uint32_t entry, Map* map, Player* who = &a) {
            GameObject go{map, type, entry};
            return clickables.CanGameObjectGossipHello(who, &go);
        };
        assert(use(3, 5000, &grMap) && said_("Nothing can be used in a Greater Rift."));             // a chest
        assert(use(10, 5001, &grMap) && use(10, 5001, &grMap2));                                     // a goober, Guardian alive or not
        assert(use(22, 5002, &grMap) && use(18, 5003, &grMap) && use(23, 5004, &grMap));
        assert(!use(0, 5005, &grMap) && !use(1, 5006, &grMap) && !use(2, 5007, &grMap));             // door, button, questgiver
        assert(!use(10, 910012, &grMap) && !use(10, 910013, &grMap));                                // the Town Portal pair
        assert(!use(22, 910070, &grMap) && !use(22, 910086, &grMap) && use(22, 910069, &grMap) && use(22, 910087, &grMap));   // a floor's exit portal
        assert(!use(22, 911070, &grMap) && !use(22, 918086, &grMap) && use(22, 911087, &grMap) && use(22, 919070, &grMap));   // and the ones named for later floors
        assert(!use(3, 5000, &nrMap) && !use(10, 5001, &hubMap) && !use(3, 5000, &closedMap));       // elsewhere, and a closed run
        // pylons P4: a pylon is usable (P3's entries 910120-910124); a shrine's object is not (it never stands here)
        assert(!use(22, 910120, &grMap) && !use(22, 910124, &grMap) && use(22, 910125, &grMap) && use(22, 910130, &grMap));
        live[11].state = "complete";
        assert(use(3, 5000, &grMap));                                                                // after the Guardian: still none
        assert(!use(22, 910121, &grMap));                                                            // a standing pylon still works
        GameObject go{&grMap, 3, 5000};
        assert(!clickables.CanGameObjectGossipHello(nullptr, &go) && !clickables.CanGameObjectGossipHello(&a, nullptr));
        a.hasSession = false;
        assert(use(3, 5000, &grMap));                                                                // refused even with no session
    }

    // ---- rift floors Part F1: a run's deaths are one count across its floors, and its rules hold on every floor ----
    reset();
    {
        GreaterRiftRules rules;
        Map floorTwo{1, 62};
        assert(live.AddFloor(live[11].id, 62, 1, 0) == 2);                         // run 111 now has a second floor
        rules.OnPlayerJustDied(&a);                                                // a death on floor 1 ...
        assert(GreaterRiftReviveWaitLeft(&a) == %(first)d);
        Player onTwo = a; onTwo.map = &floorTwo;                                   // ... is remembered on floor 2
        assert(GreaterRiftReviveWaitLeft(&onTwo) == %(first)d);
        rules.OnPlayerJustDied(&onTwo);                                            // the second death, on the other floor: one count
        assert(GreaterRiftReviveWaitLeft(&onTwo) == %(first)d + %(step)d && deaths.size() == 1);
        assert(GreaterRiftGearLocked(&onTwo) && GreaterRiftTownReviveRefused(&onTwo)); // rules 5 and 6 on floor 2
        Creature monster{&floorTwo, 100}, guardian{&floorTwo, 777};
        assert(GreaterRiftNoLoot(&monster) && !GreaterRiftNoLoot(&guardian));       // rule 1 on floor 2
        live.Remove(11, 1);                                                        // floor 1 unloads: the run and its count go on
        assert(GreaterRiftReviveWaitLeft(&onTwo) == %(first)d + %(step)d && GreaterRiftGearLocked(&onTwo));
        live.Remove(62, 1);                                                        // the last floor: the run is gone
        Player elsewhere = a; elsewhere.map = &grMap2;                             // a death in another live run sweeps the ended ones
        rules.OnPlayerJustDied(&elsewhere);
        assert(deaths.count({111, 1}) == 0 && deaths.count({112, 1}) == 1);
    }

    // ---- rule 5: the wait grows per death, per character, per run ----
    reset();
    {
        GreaterRiftRules rules;
        assert(GreaterRiftReviveWaitLeft(&a) == 0);                                // alive, no death yet
        rules.OnPlayerJustDied(&a);
        assert(GreaterRiftReviveWaitLeft(&a) == %(first)d);                        // the first death waits the first wait
        assert(GreaterRiftReviveWaitLeft(&b) == 0 && GreaterRiftReviveWaitLeft(&outsider) == 0);   // nobody else is held
        now += 2500; assert(GreaterRiftReviveWaitLeft(&a) == 3);                   // 2.5 s left rounds up
        now += 2500; assert(GreaterRiftReviveWaitLeft(&a) == 0);                   // over
        rules.OnPlayerJustDied(&a);
        assert(GreaterRiftReviveWaitLeft(&a) == %(first)d + %(step)d);             // the second waits the step more
        for (int i = 0; i < 20; ++i) { now += 60000; rules.OnPlayerJustDied(&a); }
        assert(GreaterRiftReviveWaitLeft(&a) == %(max)d);                          // never past the maximum
        now += 29999; assert(GreaterRiftReviveWaitLeft(&a) == 1);
        now += 1; assert(GreaterRiftReviveWaitLeft(&a) == 0);
        rules.OnPlayerJustDied(&b);                                                // another character starts at the first wait
        assert(GreaterRiftReviveWaitLeft(&b) == %(first)d);
        Player elsewhere = a; elsewhere.map = &grMap2;                             // another run: its own count
        assert(GreaterRiftReviveWaitLeft(&elsewhere) == 0);
        rules.OnPlayerJustDied(&elsewhere);
        assert(GreaterRiftReviveWaitLeft(&elsewhere) == %(first)d);
        Player nr = a; nr.map = &nrMap;                                            // a Nephalem Rift death costs no wait
        rules.OnPlayerJustDied(&nr);
        assert(GreaterRiftReviveWaitLeft(&nr) == 0);
        assert(deaths.size() == 3);
        live.Remove(12, 1);                                                        // a run that is gone is forgotten at the next death
        rules.OnPlayerJustDied(&a);
        assert(deaths.size() == 2);
        live[11].state = "closed";                                                 // a closed run holds nobody
        assert(GreaterRiftReviveWaitLeft(&a) == 0 && !GreaterRiftTownReviveRefused(&a));
        live[11].state = "complete";                                               // the wait still runs after the Guardian
        rules.OnPlayerJustDied(&a);
        assert(GreaterRiftReviveWaitLeft(&a) == %(max)d && !GreaterRiftTownReviveRefused(&a));
    }
    // ---- rules 4 and 6 lift with the Guardian, and so do the town revive and the skill bar (card q-1006-03) ----
    reset();
    {
        Player guardianUp = a; guardianUp.map = &grMap2;
        Player nr = a; nr.map = &nrMap; Player late = a; late.map = &closedMap;
        assert(GreaterRiftTownReviveRefused(&a) && GreaterRiftTownReviveRefused(&guardianUp));   // open, guardian: refused
        assert(!GreaterRiftGuardianDead(&a) && !GreaterRiftGuardianDead(&guardianUp));
        assert(!GreaterRiftGuardianDead(&nr) && !GreaterRiftGuardianDead(&outsider) && !GreaterRiftGuardianDead(nullptr));
        live[11].state = "complete";                                               // the Guardian is dead and paid
        assert(!GreaterRiftTownReviveRefused(&a) && GreaterRiftGuardianDead(&a));
        assert(GreaterRiftGearLocked(&a) == false);                                // the same moment gear unlocks
        assert(GreaterRiftTownReviveRefused(&guardianUp) && !GreaterRiftGuardianDead(&guardianUp));   // another run: its own
        assert(!GreaterRiftTownReviveRefused(&late) && GreaterRiftGuardianDead(&late));    // a closed run: nothing alive in it
        assert(!GreaterRiftTownReviveRefused(&nr) && !GreaterRiftGuardianDead(&nr));
        live[11].state = "guardian";                                               // never before the kill
        assert(GreaterRiftTownReviveRefused(&a) && !GreaterRiftGuardianDead(&a));
        live[11].mode = "nr";                                                      // a Nephalem Rift is not a Greater Rift
        live[11].state = "complete";
        assert(!GreaterRiftGuardianDead(&a) && !GreaterRiftTownReviveRefused(&a));
    }
    reset();   // the step is the designer's: unset, the wait stays the first one
    {
        GreaterRiftRules rules;
        tunables["gr_revive_wait_step_seconds"] = std::nullopt;
        rules.OnPlayerJustDied(&a); rules.OnPlayerJustDied(&a); rules.OnPlayerJustDied(&a);
        assert(GreaterRiftReviveWaitLeft(&a) == %(first)d);
        assert(GreaterRiftTownReviveRefused(&a));
        Player nr = a; nr.map = &nrMap;
        assert(!GreaterRiftTownReviveRefused(&nr) && !GreaterRiftTownReviveRefused(&outsider) && !GreaterRiftTownReviveRefused(nullptr));
    }

    // ---- the XP split ----
    reset();
    {
        Creature monster{&grMap, 100}, guardian{&grMap, 777}, nr{&nrMap, 100}, open{&hubMap, 100};
        assert(GreaterRiftXp(&monster, 1000) == 500 && GreaterRiftXp(&guardian, 1000) == 3000);
        assert(GreaterRiftXp(&nr, 1000) == 1000 && GreaterRiftXp(&open, 1000) == 1000 && GreaterRiftXp(nullptr, 1000) == 1000);
        Creature guardianInNr{&nrMap, 777};
        assert(GreaterRiftXp(&guardianInNr, 1000) == 1000);                        // a Nephalem Rift Guardian is not split
        tunables["gr_monster_xp_pct"] = std::nullopt;                              // the designer has not chosen: nothing changes
        assert(GreaterRiftXp(&monster, 1000) == 1000 && GreaterRiftXp(&guardian, 1000) == 3000);
        tunables["gr_guardian_xp_multiple"] = std::nullopt;
        assert(GreaterRiftXp(&guardian, 1000) == 1000);
        tunables["gr_monster_xp_pct"] = 100; tunables["gr_guardian_xp_multiple"] = 1;
        assert(GreaterRiftXp(&monster, 1000) == 1000 && GreaterRiftXp(&guardian, 1000) == 1000);   // the neutral values
    }

    // ---- the XP of the Guardian's level (part 8, diablocraft-yxsa): only the Guardian's, only in a Greater Rift ----
    reset();
    {
        Creature monster{&grMap, 100}, guardian{&grMap, 777}, nr{&nrMap, 777}, open{&hubMap, 777};
        live[11].grRank = 17; xpFactor = 2.5;
        assert(GreaterRiftXp(&guardian, 1000) == 7500 && xpAskedLevel == 17);      // 3 x 2.5, at the run's level
        xpAskedLevel = 999;
        assert(GreaterRiftXp(&monster, 1000) == 500 && xpAskedLevel == 999);        // a monster's XP is not the level's
        assert(GreaterRiftXp(&nr, 1000) == 1000 && GreaterRiftXp(&open, 1000) == 1000 && xpAskedLevel == 999);
        xpFactor = 1.0; assert(GreaterRiftXp(&guardian, 1000) == 3000);             // the table not set: no change
    }
    return 0;
}
''' % {'first': FIRST, 'max': MAX, 'step': STEP}

# the first and last tunable of the compile are the sheet's own numbers; the harness sets the step to 5
code = (HARNESS % {'header': HEADER.as_posix(), 'rewards': (MODULE / 'src/rifts/dc_gr_rewards.h').as_posix(),
                          'floors': (MODULE / 'src/rifts/dc_rift_floors.h').as_posix(),
                          'pylons': (MODULE / 'src/combat/dc_pylon_math.h').as_posix()}) + BODY + MAIN

compiler = shutil.which('g++') or shutil.which('c++')
if not compiler:
    raise SystemExit('g++ is not on PATH; this harness compiles a small C++ program')
with tempfile.TemporaryDirectory(prefix='dc-gr-rules-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(code, encoding='utf-8')
    subprocess.run([compiler, '-std=c++20', '-UNDEBUG', '-Wall', '-Wno-unused', '-o', str(folder / 'gr_rules'),
                    str(folder / 'test.cpp')], check=True)
    harness_env.run([str(folder / 'gr_rules')], check=True)
print('PASS: Greater Rift rules: loot, clickables, summons, revive wait and town, gear lock, XP split, wiring, tunables.')
