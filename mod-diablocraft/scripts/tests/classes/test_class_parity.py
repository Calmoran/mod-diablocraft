"""diablocraft-class-parity: the class gates, compiled from production source.

Each harness pulls the real functions out of the module's .cpp files and
compiles them against small doubles, so what is tested is what ships. Every
test then runs again on a source mutation that puts the old Barbarian-only rule
back, and requires that run to fail: a test that cannot fail proves nothing.

Classes in the doubles follow class_map.csv: Warrior (1) is the Barbarian,
Mage (8) the Wizard; Monk (12) has no row and stands for "a class with no data".
"""
import os
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
SRC = MODULE / "src"
MAIN = MODULE / "tests/class_parity/main.cpp"
# Scratch lives under build/_agent-scratch/, never /tmp (CLAUDE.md).
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch"


def definition(source, marker):
    """The full brace-balanced definition that starts at `marker`."""
    start = source.index(marker)
    opening = source.index("{", start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end].replace(" override", "")


def mutate(source, old, new):
    assert source.count(old) == 1, f"mutation anchor not unique: {old!r}"
    return source.replace(old, new)


FLAGS_WITH_A_VALUE = ("-I", "-isystem", "-iquote", "-include", "-D", "-U")


def split_extra(extra):
    """(flags, sources) of the extra compiler arguments: what starts with '-' is a flag ('-I' and the like take the next argument
    along), the rest is a source file."""
    flags, sources, items = [], [], [str(e) for e in extra]
    while items:
        item = items.pop(0)
        if item.startswith("-"):
            flags.append(item)
            if item in FLAGS_WITH_A_VALUE and items:
                flags.append(items.pop(0))
        else:
            sources.append(item)
    return flags, sources


def run(code, extra=()):
    """Compile and run one harness; returns (ok, output). `extra` are compiler arguments: flags go to the compiler as flags, files are
    compiled in with the harness."""
    flags, sources = split_extra(extra)
    binary = harness_env.build([MAIN, *sources], flags=["-std=c++17", "-O0", "-UNDEBUG", *flags], files={"program.h": code},
                               includes=[SRC / "common", SRC / "paragon"])
    ran = harness_env.run([str(binary)], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout + ran.stderr


# --- item 1: rifts and the town portal --------------------------------------

def portal_harness(rifts, quests):
    return r'''
#include <cassert>
#include <cstdint>
#include <mutex>
#include <set>
unsigned warns = 0;
#define LOG_WARN(...) (++warns)
constexpr std::uint32_t TOWN_PORTAL_SHELL = 81167;
struct Player {
    unsigned cls; std::set<std::uint32_t> spells;
    unsigned getClass() const { return cls; }
    bool HasSpell(std::uint32_t id) const { return spells.count(id) != 0; }
    void learnSpell(std::uint32_t id) { spells.insert(id); }
};
namespace DC::Classes { bool Playable(Player const* p) { return p && (p->cls == 1 || p->cls == 8); } }
struct SpellInfo {};
struct SpellMgr { SpellInfo const* GetSpellInfo(std::uint32_t) { static SpellInfo info; return &info; } } spellMgr;
SpellMgr* sSpellMgr = &spellMgr;
void SweepOnLogin(Player*) {}
''' + definition(rifts, "bool PlayableClass(") + r'''
struct Hooks {
''' + definition(quests, "void OnPlayerLogin(Player* player) override") + r'''
};
int main() {
    Hooks hooks;
    Player barbarian{1}, wizard{8}, monk{12};
    hooks.OnPlayerLogin(&barbarian); hooks.OnPlayerLogin(&wizard);
    hooks.OnPlayerLogin(&monk); hooks.OnPlayerLogin(&monk);
    assert(barbarian.HasSpell(TOWN_PORTAL_SHELL));
    assert(wizard.HasSpell(TOWN_PORTAL_SHELL));
    assert(!monk.HasSpell(TOWN_PORTAL_SHELL));
    assert(warns == 1); // named once, refused every login
}
'''


class RiftsAndPortal(unittest.TestCase):
    rifts = (SRC / "rifts/dc_rifts.cpp").read_text(encoding="utf-8")
    quests = (SRC / "rifts/dc_rift_quests.cpp").read_text(encoding="utf-8")
    BARBARIAN_ONLY = ("        if (DC::Classes::Playable(player))\n            return true;",
                      "        if (player->getClass() == 1)\n            return true;")

    def test_every_mapped_class_learns_the_portal(self):
        ok, out = run(portal_harness(self.rifts, self.quests))
        self.assertTrue(ok, out)

    def test_portal_mutation_to_barbarian_only_fails(self):
        ok, _ = run(portal_harness(mutate(self.rifts, *self.BARBARIAN_ONLY), self.quests))
        self.assertFalse(ok)

    def test_rift_keeper_harness_open_gate(self):
        # test_rift_keeper.py compiles the real OpenRun with the real gate.
        script = MODULE / "scripts/tests/rifts/test_rift_keeper.py"
        ok = subprocess.run(["python3", str(script)], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout[-2000:] + ok.stderr[-2000:])
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="class-parity-rift-", dir=SCRATCH) as folder:
            mutated = Path(folder) / "dc_rifts.cpp"
            mutated.write_text(mutate(self.rifts, *self.BARBARIAN_ONLY), encoding="utf-8")
            bad = subprocess.run(["python3", str(script)], capture_output=True, text=True,
                                 env=dict(os.environ, DC_RIFT_KEEPER_SOURCE=str(mutated)))
            self.assertNotEqual(bad.returncode, 0, "the Barbarian-only OpenRun gate passed the harness")


# --- item 2: paragon --------------------------------------------------------

def paragon_harness(paragon):
    return r'''
#include "dc_common.h"
#include "dc_paragon_math.h"
#include <cassert>
#include <cmath>
#include <cstdint>
#include <mutex>
#include <optional>
#include <set>
#include <string>
unsigned warns = 0;
#define LOG_WARN(...) (++warns)
struct Player { unsigned cls; unsigned getClass() const { return cls; } };
namespace DC::Classes {
bool Playable(Player const* p) { return p && (p->cls == 1 || p->cls == 8); }
std::string PrimaryStatOf(Player const* p) { return p->cls == 1 ? "Strength" : p->cls == 8 ? "Intelligence" : ""; }
std::uint32_t ClassIdOf(Player const* p) { return p->cls == 1 ? 1 : p->cls == 8 ? 2 : 0; }
}
// diablocraft-resource-rollout-a item 5: the registry rows Paid reads, as
// generated (Fury 1, Arcane Power 0.5 per point) and dc_resources.h's payment.
namespace DC::Resources {
struct Resource { std::uint32_t classId; double paragonPerPoint; };
inline Resource const Rows[] = {{1, 1.0}, {2, 0.5}};
inline Resource const* Of(std::uint32_t id) { for (auto const& r : Rows) if (r.classId == id) return &r; return nullptr; }
inline double ParagonMaximum(Resource const& r, std::uint32_t points)
{ return static_cast<double>(points * static_cast<std::uint64_t>(std::llround(r.paragonPerPoint * 2)) / 2); }
}
namespace DC::Paragon { namespace {
''' + definition(paragon, "struct Rule") + r''';
using Points = std::array<unsigned, 16>;
std::array<Rule, 16> rules;
bool ready = true;
''' + "\n".join(definition(paragon, m) for m in (
        "bool ParagonClass(", "std::optional<Stat> PrimaryStat(", "void Check(",
        "Resources::Resource const& ClassResource(",
        "double Paid(Player const* player, Rule const& rule, unsigned count)\n{",
        "std::vector<Contribution> Contributions(")) + r'''
} }
using namespace DC; using namespace DC::Paragon;
int main() {
    for (unsigned i = 0; i < 16; ++i) { rules[i].id = i + 1; rules[i].value = 5; rules[i].stat = Stat::Vitality; }
    // What the loader sets for id 1 / "primary" (dc_paragon.cpp OnStartup).
    rules[0].key = "primary"; rules[0].stat = Stat::Strength; rules[0].classPrimary = true;
    Player barbarian{1}, wizard{8}, monk{12};
    Points points{}; points[0] = 10;
    auto wiz = Contributions(&wizard, points);
    assert(wiz.size() == 1 && wiz[0].stat == Stat::Intelligence && wiz[0].value == 50);
    auto barb = Contributions(&barbarian, points);
    assert(barb.size() == 1 && barb[0].stat == Stat::Strength && barb[0].value == 50);
    // Maximum Resource is the player's own resource's, paid in whole points.
    rules[3].key = "resource"; rules[3].stat = Stat::MaxFury; rules[3].classResource = true; rules[3].value = 1;
    Points resource{}; resource[3] = 5;
    assert(Contributions(&wizard, resource)[0].value == 2 && Contributions(&barbarian, resource)[0].value == 5);
    Check(&barbarian); Check(&wizard);
    bool refused = false;
    try { Check(&monk); } catch (std::runtime_error const&) { refused = true; }
    assert(refused && !ParagonClass(&monk) && warns == 1);
}
'''


class Paragon(unittest.TestCase):
    source = (SRC / "paragon/dc_paragon.cpp").read_text(encoding="utf-8")

    def test_wizard_gets_intelligence_and_passes_the_gate(self):
        ok, out = run(paragon_harness(self.source))
        self.assertTrue(ok, out)

    def test_fixed_strength_mutation_fails(self):
        mutated = mutate(self.source, "            if (rule.classPrimary)\n", "            if (false)\n")
        self.assertFalse(run(paragon_harness(mutated))[0])

    def test_warrior_gate_mutation_fails(self):
        mutated = mutate(self.source, "    if (Classes::Playable(player))\n        return true;",
                         "    if (player->getClass() == 1)\n        return true;")
        self.assertFalse(run(paragon_harness(mutated))[0])

    def test_login_and_kill_use_the_one_gate(self):
        self.assertTrue(self.gates_hold(self.source))
        mutated = mutate(self.source, "if (!ParagonClass(member) || member->GetLevel()!=NumericData::MaximumLevel())",
                         "if (member->getClass()!=CLASS_WARRIOR || member->GetLevel()!=NumericData::MaximumLevel())")
        self.assertFalse(self.gates_hold(mutated))

    @staticmethod
    def gates_hold(source):
        login = definition(source, "void OnPlayerLogin(Player* player) override")
        kill = definition(source, "static void Kill(Creature* victim)")
        return ("CLASS_WARRIOR" not in source and "if (!ParagonClass(player)) return;" in login
                and "!ParagonClass(member)" in kill)


# --- items 3 and 4: first login for every class, visible fallbacks ----------

def world_harness(world):
    return r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std::chrono_literals;
using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t;
unsigned warns = 0, errors = 0;
#define LOG_WARN(...) (++warns)
#define LOG_ERROR(...) (++errors)
#define LOG_INFO(...) ((void)0)
constexpr uint8 INVENTORY_SLOT_BAG_0 = 255, EQUIPMENT_SLOT_START = 0, INVENTORY_SLOT_ITEM_END = 39,
                EQUIPMENT_SLOT_MAINHAND = 15, EQUIPMENT_SLOT_OFFHAND = 16;
constexpr unsigned INVTYPE_2HWEAPON = 17, EQUIP_ERR_OK = 0, AT_LOGIN_FIRST = 0x20, CLASS_MAGE = 8, CLASS_WARRIOR = 1;
struct Guid { uint32 value; uint32 GetCounter() const { return value; } };
struct ItemTemplate { unsigned InventoryType = 13; };
struct Item {
    uint32 id; ItemTemplate proto;
    ItemTemplate const* GetTemplate() const { return &proto; }
    uint8 GetBagSlot() const { return 0; } uint8 GetSlot() const { return 0; }
    Guid GetGUID() const { return {id}; }
};
struct Session { bool aborted = false; bool EconomyAborted() const { return aborted; } };
struct WorldLocation { unsigned GetMapId() const { return 530; } };
struct Map {};
struct MapMgr { Map* CreateMap(unsigned, void*) { static Map map; return &map; } } mapMgr;
auto* sMapMgr = &mapMgr;
namespace DataMap { struct Base {}; }
constexpr int ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL = 5;
// Player::m_Events: the login hook queues the reach-level re-check; the double keeps the callbacks so a test can run them.
struct EventMap {
    std::vector<std::function<void()>> queued;
    void AddEventAtOffset(std::function<void()> f, std::chrono::seconds) { queued.push_back(std::move(f)); }
};
struct CustomStore { template<class T> T* GetDefault(char const*) { static T value; return &value; } };
struct Player {
    uint32 guid; unsigned cls; Session session; std::set<uint32> spells, skills; unsigned equipped = 0;
    bool far = false, relocated = false; unsigned level = 1, teleports = 0;
    CustomStore CustomData;
    EventMap m_Events;
    unsigned criteriaUpdates = 0, criteriaLevel = 0;
    void UpdateAchievementCriteria(int type) { if (type == ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL) { ++criteriaUpdates; criteriaLevel = level; } }
    bool IsBeingTeleportedFar() const { return far; }
    void SetLevel(unsigned v) { level = v; }
    void InitStatsForLevel() {} void InitTalentForLevel() {} void InitTaxiNodesForLevel() {}
    void InitGlyphsForLevel() {} void UpdateAllStats() {}
    Map* FindMap() { return nullptr; } void ResetMap() {} void SetMap(Map*) {}
    void Relocate(WorldLocation const&) { relocated = true; } void setCinematic(unsigned) {}
    unsigned getClass() const { return cls; }
    Guid GetGUID() const { return {guid}; }
    Session* GetSession() { return &session; }
    char const* GetName() const { return "test"; }
    void learnSpell(uint32 id) { spells.insert(id); }
    void LearnDefaultSkill(uint32 id, int) { skills.insert(id); }
    Item* GetItemByPos(uint8, uint8) { return nullptr; }
    void DestroyItem(uint8, uint8, bool) {}
    template <class T> void SaveToDB(T&, bool, bool) {}
    void GiveLevel(uint32 v) { level = v; }
    unsigned GetLevel() const { return level; }
    void SetHomebind(WorldLocation const&, uint32) {}
    bool TeleportTo(WorldLocation const&) { ++teleports; return true; }
    template <class T> unsigned CanEquipItem(uint8, uint16&, Item*, bool) { return EQUIP_ERR_OK; }
    unsigned CanEquipItem(uint8, uint16&, Item*, bool) { return EQUIP_ERR_OK; }
    void RemoveItem(uint8, uint8, bool) {}
    void EquipItem(uint16, Item*, bool) { ++equipped; }
    uint32 GetMaxHealth() const { return 1; }
    bool firstLogin = false;
    bool HasAtLoginFlag(unsigned) const { return firstLogin; }
    void SetHealth(uint32) {}
};
struct ChatHandler {
    explicit ChatHandler(Session*) {}
    void SendSysMessage(char const*) {}
    template <class... T> void PSendSysMessage(char const*, T...) {}
};
// The character database, reduced to the two records Start reads and writes.
struct Db {
    std::map<uint32, unsigned> start;                 // dc_character_start.complete
    std::set<std::pair<uint32, unsigned>> items;      // dc_character_starter_item
} db;
struct Row { unsigned v; struct F { unsigned v; template <class T> T Get() const { return T(v); } };
             F operator[](int) const { return {v}; } };
using QueryResult = std::shared_ptr<Row>;
struct Transaction {
    std::vector<std::pair<std::string, std::vector<uint32>>> writes;
    template <class... A> void Append(char const* sql, A... a) { writes.push_back({sql, {uint32(a)...}}); }
};
using CharacterDatabaseTransaction = std::shared_ptr<Transaction>;
struct CharacterDb {
    template <class... A> QueryResult Query(char const* sql, uint32 guid, A... more) {
        std::string const s = sql; std::vector<unsigned> rest{unsigned(more)...};
        if (s.find("dc_character_starter_item") != std::string::npos)
            return db.items.count({guid, rest.at(0)}) ? std::make_shared<Row>(Row{1}) : nullptr;
        if (s.find("dc_character_tier") != std::string::npos) return std::make_shared<Row>(Row{1});
        auto found = db.start.find(guid);
        return found == db.start.end() ? nullptr : std::make_shared<Row>(Row{found->second});
    }
    CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Transaction>(); }
} CharacterDatabase;
unsigned failSlot = 255;
void SaveStart(Player*, CharacterDatabaseTransaction const& t) { t->Append("native-save"); }
void CommitCharacterSave(CharacterDatabaseTransaction const& t) {
    for (auto const& [sql, args] : t->writes)
        if (sql.rfind("INSERT INTO dc_character_starter_item", 0) == 0) {
            assert(t->writes.front().first == "staged-affixes");
            assert(t->writes.size() == 3 && t->writes[1].first == "native-save");
            if (args[1] == failSlot) throw std::runtime_error("injected slot commit failure");
        }
    for (auto const& [sql, args] : t->writes) {
        std::string const s = sql;
        if (s.rfind("INSERT INTO dc_character_start(", 0) == 0) db.start[args[0]] = 0;
        else if (s.rfind("UPDATE dc_character_start", 0) == 0) db.start[args[0]] = 1;
        else if (s.rfind("INSERT INTO dc_character_starter_item", 0) == 0) db.items.insert({args[0], args[1]});
    }
}
unsigned ensureCalls = 0, resolveCalls = 0, rolls = 0;
bool ensureWorks = true;
std::map<uint32, int> modes;  // guid -> 0 unchosen, 1 normal
namespace DC {
namespace Hardcore { enum class Mode { Unchosen, Normal, Hardcore };
    Mode ModeOf(Player const* p) { return modes[p->guid] ? Mode::Normal : Mode::Unchosen; }
    bool EnsureMode(Player* p) { ++ensureCalls; if (ensureWorks) modes[p->guid] = 1; return ensureWorks; } }
namespace AccountEconomy {
    bool resolves = true;
    bool ResolvePending(Player*) { ++resolveCalls; return resolves; }
    bool ResolveCreation(Player* p) { return ResolvePending(p); }
}
namespace Paragon { bool EnsureStartingLevel(Player*, uint32, std::string&) { return true; } }
namespace NumericData { unsigned MaximumLevel() { return 70; } }
namespace Difficulty { bool SelectTier(Player*, unsigned, std::string&) { return true; } }
namespace Classes {
    // class_map.csv: Warrior (1) and Mage (8) have skills; the Monk (12) has none yet and is not Playable.
    bool Playable(Player const* p) { return p && (p->cls == 1 || p->cls == 8); }
    bool barWorks = true;
    unsigned ActiveSlots() { return 6; }
    std::vector<unsigned> Bar(Player*) { return std::vector<unsigned>(barWorks ? ActiveSlots() : 0); }
    bool InitializeStarterBar(Player*, std::string&) { return true; }
}
namespace Items {
    struct StagedRoll { Item item{900}; Item* GetItem() { return &item; } void Publish() {} };
    auto StageRoll(Player*, uint32, uint32, std::string const&, CharacterDatabaseTransaction const& tx) {
        ++rolls; tx->Append("staged-affixes"); return std::make_unique<StagedRoll>();
    }
    void RefreshContributions(Player*, Item*) {}
}
namespace Stats { bool Recompute(Player*) { return true; } }
namespace World { namespace {
''' + definition(world, "struct KitSlot") + ";\n" + definition(world, "struct ClassStart") + r''';
std::map<uint8, ClassStart> classStarts;
std::set<uint8> creatableClasses{1, 8}; // the classes with a start profile (dc_class_start): Barbarian and Wizard
WorldLocation hub; uint32 hubArea = 0; bool ready = true;
uint32 StarterNumber(char const*, char const*, uint32, uint32) { return 70; }
unsigned sweeps = 0;
void MoveToHubSpawn(Player*, char const*) {}
bool AtHubSpawn(Player* p) { return p->relocated; }
void SweepBags(Player*) { ++sweeps; }
uint32 SatchelsPerCharacter() { return 2; }
void RemoveTravel(Player*) {}
std::set<uint32> bagGrants;
void GrantStarterBags(Player*, uint32 guid) { bagGrants.insert(guid); }
struct StartResume : DataMap::Base { bool waitingForMap = false; };
''' + "\n".join(definition(world, m) for m in (
        "ClassStart const* ProfileFor(", "void GrantEquipmentSkills(", "bool Setup(", "bool StartOwed(",
        "void Start(")) + r'''
struct Gate {
''' + definition(world, "    bool CanAccountCreateCharacter(") + r'''
};
struct Hub {
''' + definition(world, "    void OnPlayerLogin(Player* player) override") + r'''
};
} } }
using namespace DC::World;
int main() {
    // The Barbarian's profile: one kit slot and one proficiency are enough here.
    classStarts[1] = ClassStart{"barbarian", "Barbarian", {KitSlot{EQUIPMENT_SLOT_MAINHAND, "legendary", {100}}}, {{196, 44}}};

    // #69: a class with no profile still gets its mode and account resolved.
    Player wizard{10, 8};
    Start(&wizard);
    assert(modes[10] == 1 && ensureCalls == 1 && resolveCalls == 1);
    assert(!db.start.count(10) && rolls == 0 && warns == 1);
    Start(&wizard); // every later login: nothing to redo, nothing logged again
    assert(ensureCalls == 1 && resolveCalls == 1 && warns == 1);

    // Item 4: no profile, no proficiency repair - and it was already named once.
    GrantEquipmentSkills(&wizard);
    assert(wizard.spells.empty() && warns == 1);

    // The Barbarian: mode, account, kit once, never twice.
    Player barbarian{20, 1};
    Start(&barbarian);
    assert(modes[20] == 1 && db.start.at(20) == 1 && rolls == 1 && barbarian.equipped == 1);
    Start(&barbarian);
    assert(rolls == 1 && barbarian.equipped == 1);
    GrantEquipmentSkills(&barbarian);
    assert(barbarian.spells.count(196) && barbarian.skills.count(44));

    // A mode that could not be written defers everything, as before.
    ensureWorks = false;
    Player failed{30, 1};
    Start(&failed);
    assert(!db.start.count(30) && resolveCalls == 2 && rolls == 1);
    ensureWorks = true;

    // A mode that exists but whose account failed this login defers the kit.
    Player aborted{40, 1}; modes[40] = 1; aborted.session.aborted = true;
    Start(&aborted);
    assert(!db.start.count(40) && rolls == 1);

    // Q2 option a (ruling 2026-09-23): Wiztest - a Mage made before the Wizard
    // had a profile, now that it has one. The legacy migration records its
    // start as complete; login sets up mode and account and gives nothing.
    classStarts[8] = ClassStart{"wizard", "Wizard", {KitSlot{EQUIPMENT_SLOT_MAINHAND, "legendary", {200}}}, {{196, 44}}};
    Player wiztest{50, 8}; db.start[50] = 1;
    auto resolves = resolveCalls, before = rolls;
    Hub{}.OnPlayerLogin(&wiztest);
    assert(modes[50] == 1 && resolveCalls == resolves + 1);
    assert(rolls == before && wiztest.equipped == 0 && !bagGrants.count(50)); // no Satchels (ruling 6)
    // diablocraft-egn4j: every login queues the reach-level re-check, and it asks the criteria once when it runs.
    assert(wiztest.m_Events.queued.size() == 1 && wiztest.criteriaUpdates == 0);
    wiztest.m_Events.queued[0]();
    assert(wiztest.criteriaUpdates == 1);
    Hub{}.OnPlayerLogin(&wiztest);                        // and never later
    assert(rolls == before && wiztest.equipped == 0 && resolveCalls == resolves + 1);
    // A new Mage made after the profile: the kit once, never twice.
    Player fresh{60, 8}; fresh.firstLogin = true;
    Hub{}.OnPlayerLogin(&fresh); Start(&fresh);           // then OnPlayerFirstLogin
    assert(db.start.at(60) == 1 && rolls == before + 1 && fresh.equipped == 1 && bagGrants.count(60));
    fresh.firstLogin = false;
    Hub{}.OnPlayerLogin(&fresh);
    assert(rolls == before + 1 && fresh.equipped == 1);

    // Creation completes off-world without a teleport or login state.
    Player created{70, 1}; created.firstLogin = true;
    Start(&created, true);
    assert(db.start.at(70) == 1 && created.level == 70 && created.relocated && created.teleports == 0);
    // diablocraft-egn4j: the reach-level criteria are updated after SetLevel, so a level-70 start earns them.
    assert(created.criteriaUpdates == 1 && created.criteriaLevel == 70);
    auto count = rolls;
    Hub{}.OnPlayerLogin(&created); Start(&created);
    assert(rolls == count);

    // A failed middle-slot commit keeps the prior slot and resumes exactly once.
    classStarts[1].kit.push_back(KitSlot{EQUIPMENT_SLOT_OFFHAND, "rare", {300}});
    Player interrupted{80, 1}; interrupted.firstLogin = true;
    failSlot = EQUIPMENT_SLOT_OFFHAND;
    Start(&interrupted, true);
    assert(db.start.at(80) == 0 && db.items.count({80, EQUIPMENT_SLOT_MAINHAND}) == 1);
    assert(!db.items.count({80, EQUIPMENT_SLOT_OFFHAND}));
    failSlot = 255; count = rolls;
    Hub{}.OnPlayerLogin(&interrupted); Start(&interrupted);
    assert(db.start.at(80) == 1 && rolls == count + 1 && db.items.count({80, EQUIPMENT_SLOT_OFFHAND}) == 1);
    count = rolls; Start(&interrupted); assert(rolls == count);

    // Account failure before any start row is recoverable on first login.
    Player unresolved{90, 1}; unresolved.firstLogin = true;
    DC::AccountEconomy::resolves = false;
    Start(&unresolved, true); assert(!db.start.count(90));
    DC::AccountEconomy::resolves = true;
    Start(&unresolved); assert(db.start.at(90) == 1);

    Player badbar{95, 1};
    DC::Classes::barWorks = false; count = rolls;
    Start(&badbar, true); assert(db.start.at(95) == 0 && rolls == count);
    DC::Classes::barWorks = true;
    Start(&badbar); assert(db.start.at(95) == 1);

    Player transferring{100, 1}; transferring.far = true;
    Start(&transferring);
    assert(!db.start.count(100));
    assert(transferring.CustomData.GetDefault<StartResume>("DCStartResume")->waitingForMap);
    ready = false;
    assert(Gate{}.CanAccountCreateCharacter(1, 1, CLASS_MAGE));
    assert(Gate{}.CanAccountCreateCharacter(1, 1, CLASS_WARRIOR));
    assert(!Gate{}.CanAccountCreateCharacter(1, 1, 2));
    Player nodata{110, 1}; Start(&nodata, true); assert(!db.start.count(110));
    ready = true; Start(&nodata); assert(db.start.at(110) == 1);
}
'''


class FirstLogin(unittest.TestCase):
    source = (SRC / "common/dc_world.cpp").read_text(encoding="utf-8")

    def test_every_class_gets_mode_and_account(self):
        ok, out = run(world_harness(self.source))
        self.assertTrue(ok, out)

    def test_profile_before_setup_mutation_fails(self):
        # The pre-fix order: the profile lookup returns before the mode is written.
        mutated = mutate(self.source,
                         "    if (!Setup(player, creation))\n        return;",
                         "    if (!ProfileFor(player)) return;\n    if (!Setup(player, creation))\n        return;")
        self.assertFalse(run(world_harness(mutated))[0])

    def test_login_without_setup_mutation_fails(self):
        # Setup only inside Start: Wiztest, whose start is recorded, never gets it.
        mutated = mutate(self.source, "        Setup(player);\n        auto row=", "        auto row=")
        self.assertFalse(run(world_harness(mutated))[0])

    def test_silent_profile_miss_mutation_fails(self):
        mutated = mutate(self.source, "    if (named.insert(wowClass).second)\n        LOG_WARN(\"server\", \"[DC world]",
                         "    if (false)\n        LOG_WARN(\"server\", \"[DC world]")
        self.assertFalse(run(world_harness(mutated))[0])

    def test_no_reach_level_update_at_creation_mutation_fails(self):
        mutated = mutate(self.source, "            player->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_REACH_LEVEL);\n", "")
        self.assertFalse(run(world_harness(mutated))[0])

    def test_no_reach_level_recheck_at_login_mutation_fails(self):
        mutated = mutate(self.source, "        player->m_Events.AddEventAtOffset(", "        (void)(")
        self.assertFalse(run(world_harness(mutated))[0])


CALCULATE_HARNESS = r'''
#include "dc_common.h"
#include "dc_numeric_data.h"
#include <cassert>
#include <map>
#include <string>
namespace DC::NumericData {
std::map<std::string, double> rules{{"crit_chance_pct", 5}, {"crit_damage_pct", 50}, {"attack_speed_cap", 5},
    {"movement_cap_pct", 25}, {"magic_find_cap_pct", 300}, {"gold_find_cap_pct", 300}, {"xp_penalty_level", 70},
    {"xp_divisor", 10}, {"all_res_per_int", 0.1}, {"class_dr_pct", 30}, {"armor_level_coefficient", 50},
    {"resistance_level_coefficient", 5}};
double Rule(char const* name) { return rules.at(name); }
unsigned MaximumLevel() { return 70; }
double BaseFury(unsigned) { return 100; }
BlockTuning Block() { return {75, 100, 1}; }
}
std::map<std::string, int> notices;
int main() {
    using namespace DC;
    BaseStats base; base.strength = 10; base.dexterity = 8; base.intelligence = 8; base.vitality = 9;
    base.baseArmor = 18; base.baseLife = 40; base.lifePerVitality = 10; base.maxFury = 100;
    Calculate(base, {});                       // no notice installed: silent, as the math tests expect
    SetClassRuleFallbackNotice([](char const* rule) { ++notices[rule]; });
    BaseStats named = base; named.classDRPct = 30; named.allResPerInt = 0.1;
    Calculate(named, {});
    assert(notices.empty());                   // a base that names its class is not a fallback
    Calculate(base, {}); Calculate(base, {});
    assert(notices["class_dr_pct"] == 1 && notices["all_res_per_int"] == 1 && notices.size() == 2);
}
'''


class ClassRuleFallback(unittest.TestCase):
    common = SRC / "common/dc_common.cpp"

    def build(self, source_text):
        text = (source_text.replace('#include "dc_common.h"', f'#include "{SRC / "common/dc_common.h"}"')
                .replace('#include "dc_numeric_data.h"', f'#include "{SRC / "common/dc_numeric_data.h"}"'))
        folder = SCRATCH / "class-parity-common"      # one file a text, named by it, so the same text is the same path for the cache
        folder.mkdir(parents=True, exist_ok=True)
        copy = folder / ("dc_common-%s.cpp" % hashlib.sha1(text.encode("utf-8")).hexdigest()[:16])
        copy.write_text(text, encoding="utf-8")
        return run(CALCULATE_HARNESS, extra=[copy])

    def test_fallback_is_reported_once_per_rule(self):
        ok, out = self.build(self.common.read_text(encoding="utf-8"))
        self.assertTrue(ok, out)

    def test_silent_fallback_mutation_fails(self):
        mutated = mutate(self.common.read_text(encoding="utf-8"),
                         '    if (std::isnan(base.classDRPct)) NoteFallback(drFallbackNamed, "class_dr_pct");\n', "")
        self.assertFalse(self.build(mutated)[0])


# --- item 5 and the Q1/Q2 rulings: data ---------------------------------------

import struct as _struct
import sys as _sys

_sys.path.insert(0, str(MODULE / "scripts"))
import generate_class_proficiencies as proficiencies  # noqa: E402
import generate_sql  # noqa: E402

D3 = MODULE / "data/d3"
CLIENT_DBC = ROOT / "client-patch/dbc"


def dbc(name):
    raw = (CLIENT_DBC / f"{name}.dbc").read_bytes()
    _, count, fields, size, _ = _struct.unpack_from("<4s4I", raw)
    return [_struct.unpack_from(f"<{fields}I", raw, 20 + n * size) for n in range(count)]


def proficiency_spell(skill):
    """The one SkillLineAbility spell of `skill` whose Spell.dbc effect is
    SPELL_EFFECT_PROFICIENCY (60): the spell that grants the proficiency."""
    spells = {row[0]: row for row in dbc("Spell")}
    found = {row[2] for row in dbc("SkillLineAbility")
             if row[1] == skill and row[2] in spells and 60 in spells[row[2]][71:74]}
    assert len(found) == 1, (skill, found)
    return found.pop()


def wizard_equipment_skills(classify=generate_sql.classify):
    """(spell, skill) for every Wizard-usable base that needs a skill at all:
    the start kit's own eligibility rule, the generator's classification and the
    core's ItemTemplate::GetSkill (armor table: Cloth 415, Plate 293, Shield 433)."""
    armor = {1: 415, 2: 414, 3: 413, 4: 293, 6: 433}
    needed = set()
    for line, base in enumerate(proficiencies.read_csv(D3 / "base_items.csv"), 2):
        if base["pool_version"] != "yes" or not proficiencies.usable(base, "wizard"):
            continue
        item_class, subclass, _ = classify(base, None, line, [])
        skill = (proficiencies.WEAPON_SKILLS[subclass] if item_class == 2 else armor.get(subclass, 0))
        if skill:
            needed.add(skill)
    return {(proficiency_spell(skill), skill) for skill in needed}


class WizardProfile(unittest.TestCase):
    profiles = generate_sql.class_start_rows(D3 / "class_starts.csv")

    def test_kit_mirrors_the_barbarian(self):
        self.assertEqual(self.profiles[8]["class_key"], "wizard")
        projection = lambda profile: [(r['slot'], r['rarity'], r['count']) for r in profile['kit']]
        self.assertEqual(projection(self.profiles[8]), projection(self.profiles[1]))

    def test_skills_are_exactly_the_derived_set(self):
        shipped = {(r["spell_id"], r["skill_id"]) for r in self.profiles[8]["skills"]}
        self.assertEqual(shipped, wizard_equipment_skills())

    def test_plate_armor_mutation_is_not_covered(self):
        # Q1 option B is what makes the armor wearable: with Plate back, the
        # derivation asks for Plate and Shield, which the profile does not grant.
        def plate(fields, path, line, row):
            item_class, subclass, inventory = generate_sql.classify(fields, path, line, row)
            if item_class == 4 and fields["slot"] not in ("neck", "finger") and fields["type"] != "Source":
                subclass = 6 if fields["type"] == "Shield" else 4
            return item_class, subclass, inventory
        shipped = {(r["spell_id"], r["skill_id"]) for r in self.profiles[8]["skills"]}
        self.assertNotEqual(shipped, wizard_equipment_skills(plate))

    def test_every_kit_candidate_is_wearable(self):
        # Offline half of "can equip every piece": each candidate the loader
        # would roll needs no skill, or one the profile grants and the class may
        # learn (native, or a generated SkillRaceClassInfo row).
        granted = {r["skill_id"] for r in self.profiles[8]["skills"]}
        mage = 1 << 7
        allowed = {row[1] for row in dbc("SkillRaceClassInfo") if not row[3] or row[3] & mage}
        rows = proficiencies.read_csv(D3 / "base_items.csv")
        for kit in self.profiles[8]["kit"]:
            slot, rarity = kit["slot"], kit["rarity"]
            pool = generate_sql.starter_candidates(self.profiles[8], kit, rows)
            self.assertTrue(pool, slot)
            for base in pool:
                # items_0011 lets the Mage wear it: the same usable/designation rule.
                self.assertTrue(not base["usable_by"] or "wizard" in base["usable_by"].split(";"), base["d3_id"])
                self.assertIn(base["designated_class"], ("", "wizard"), base["d3_id"])
                item_class, subclass, _ = generate_sql.classify(base, None, 0, [])
                skill = proficiencies.WEAPON_SKILLS[subclass] if item_class == 2 else 0
                if item_class == 4:
                    self.assertEqual(subclass, 0, base["d3_id"])          # Miscellaneous armor
                if skill:
                    self.assertIn(skill, granted, base["d3_id"])
                    self.assertIn(skill, allowed, base["d3_id"])


class Proficiencies(unittest.TestCase):
    def test_client_dbc_carries_exactly_the_generated_rows(self):
        rows = {row[0]: row for row in dbc("SkillRaceClassInfo")}
        ids = proficiencies.identities(MODULE)
        self.assertEqual({k for k in rows if k in proficiencies.RESERVED}, set(ids.values()))
        for (key, skill), identity in ids.items():
            self.assertEqual(rows[identity][1:4], (skill, 0, 1 << (proficiencies.classes(MODULE)[key] - 1)))
        self.assertNotIn(1000, rows)                                      # the trade skill pilot's rows are gone
        self.assertNotIn(1001, rows)

    def test_migration_matches_the_ids(self):
        sql = (MODULE / "data/sql/db-world/updates" / proficiencies.MIGRATION).read_text(encoding="utf-8")
        for (key, skill), identity in proficiencies.identities(MODULE).items():
            self.assertIn(f"({identity},{skill},0,", sql)

    def test_an_identity_outside_the_reservation_is_refused(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="class-parity-ids-", dir=SCRATCH) as folder:
            data = Path(folder) / "data"
            data.mkdir()
            (data / "class_proficiency_ids.csv").write_text(
                "class_key,skill_id,race_class_id\nwizard,44,1001\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                proficiencies.identities(Path(folder))


class MiscArmorMigrations(unittest.TestCase):
    """items_0009/items_0010 change subclass and items_0011 AllowableClass, and
    nothing else (PM review return: a full DELETE + INSERT reset crafting_0003's
    Flags|134217728, ItemLevel 70 and MaxDurability)."""
    UPDATES = MODULE / "data/sql/db-world/updates"
    MIRRORS = MODULE / "data" / "generated"
    COLUMNS = ("entry", "class", "subclass", "name", "displayid", "Quality", "InventoryType", "ItemLevel",
               "RequiredLevel", "dmg_min1", "dmg_max1", "dmg_type1", "delay", "maxcount", "stackable",
               "bonding", "spellid_1", "spelltrigger_1", "description", "Flags", "MaxDurability", "SellPrice",
               "AllowableClass")

    @staticmethod
    def statements(text):
        import re
        body = "\n".join(line for line in text.splitlines()
                         if not line.startswith("--") and not line.upper().startswith("SET NAMES"))
        return [s for s in re.split(r";\s*\n", body) if s.strip()]

    def database(self, template_sql, shell_sql, allowable_sql=None):
        import sqlite3
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE item_template (" + ", ".join(
            f"`{c}` {'TEXT' if c in ('name', 'description') else 'INTEGER'} DEFAULT "
            f"{chr(39) * 2 if c in ('name', 'description') else (-1 if c == 'AllowableClass' else 0)}"
            for c in self.COLUMNS) + ", PRIMARY KEY(entry))")
        # The applied history: 0002 and items_0007 as they shipped ...
        for text in ((self.UPDATES / generate_sql.TEMPLATE_APPLIED).read_text(encoding="utf-8"),
                     (self.UPDATES / generate_sql.SHELL_APPLIED).read_text(encoding="utf-8")):
            for statement in self.statements(text):
                db.execute(statement)
        # ... then what later migrations wrote into other columns: crafting_0003's
        # Flags|134217728, ItemLevel 70 and native durability, plus a sell price,
        # all distinct per row so a reset cannot hide behind a common default.
        db.execute("UPDATE item_template SET Flags=(Flags|134217728)+entry%7, ItemLevel=70, "
                   "MaxDurability=40+entry%61, SellPrice=entry*3")
        before = {row[0]: row for row in db.execute("SELECT * FROM item_template ORDER BY entry")}
        if allowable_sql is None:
            allowable_sql = (self.UPDATES / generate_sql.ALLOWABLE_MIGRATION).read_text(encoding="utf-8")
        for text in (template_sql, shell_sql, allowable_sql):
            for statement in self.statements(text):
                db.execute(statement)
        after = {row[0]: row for row in db.execute("SELECT * FROM item_template ORDER BY entry")}
        return before, after

    def check(self, before, after):
        subclass, allowable = self.COLUMNS.index("subclass"), self.COLUMNS.index("AllowableClass")
        kept = [i for i in range(len(self.COLUMNS)) if i not in (subclass, allowable)]
        self.assertEqual(before.keys(), after.keys())
        moved = 0
        for entry, old in before.items():
            new = after[entry]
            self.assertEqual([old[i] for i in kept], [new[i] for i in kept], entry)
            if new[1] == 4:
                self.assertEqual(new[subclass], 0, entry)       # every armor row Miscellaneous
            moved += old[subclass] != new[subclass]
        self.assertEqual(moved, 576)                            # 558 bases + 18 shells

    def test_only_subclass_changes_and_later_columns_survive(self):
        self.check(*self.database((self.UPDATES / generate_sql.TEMPLATE_MIGRATION).read_text(encoding="utf-8"),
                                  (self.UPDATES / generate_sql.SHELL_MIGRATION).read_text(encoding="utf-8")))

    def test_full_render_replay_mutation_fails(self):
        # The returned version: replaying the full DELETE + INSERT render.
        before, after = self.database((self.MIRRORS / "item_template.sql").read_text(encoding="utf-8"),
                                      (self.MIRRORS / "unidentified_shells.sql").read_text(encoding="utf-8"))
        with self.assertRaises(AssertionError):
            self.check(before, after)

    def allowable_by_type(self, allowable_sql=None):
        """type -> set of AllowableClass values after the migrations."""
        _, after = self.database((self.UPDATES / generate_sql.TEMPLATE_MIGRATION).read_text(encoding="utf-8"),
                                 (self.UPDATES / generate_sql.SHELL_MIGRATION).read_text(encoding="utf-8"),
                                 allowable_sql)
        column = self.COLUMNS.index("AllowableClass")
        entries = {row["d3_id"]: int(row["item_entry"]) for row in proficiencies.read_csv(D3 / "base_item_ids.csv")}
        found = {}
        for base in proficiencies.read_csv(D3 / "base_items.csv"):
            if entries[base["d3_id"]] not in after:
                continue                   # a base added since 0002 is inserted by its own migration (test_shaman_class_items.py)
            key = base["type"] + ("/" + base["designated_class"] if base["designated_class"] else "")
            found.setdefault(key, set()).add(after[entries[base["d3_id"]]][column])
        return found

    # Sources: D3Planner data.json itemTypes. shield.classes lists wizard and
    # barbarian (with monk, crusader, ...); wizardhat/source/wand .class = wizard;
    # mightybelt.class = barbarian; crusadershield.class = crusader; fistweapon
    # is monk-only; amulet names no class. WoW bits: Warrior 1, Mage 128.
    EXPECTED = {"Shield": {129}, "Wizard Hat/wizard": {128}, "Source/wizard": {128},
                "Mighty Belt/barbarian": {1}, "Crusader Shield/crusader": {0}, "Amulet": {-1},
                "Wand/wizard": {128}, "Fist Weapon/monk": {0}}

    def test_allowable_class_follows_the_sourced_class_lists(self):
        found = self.allowable_by_type()
        for key, want in self.EXPECTED.items():
            self.assertEqual(found[key], want, key)

    def test_universal_armor_mutation_fails(self):
        # Rulings (1)/(2): wear eligibility is per class, never universal.
        found = self.allowable_by_type(allowable_sql="")
        self.assertNotEqual({k: found[k] for k in self.EXPECTED}, self.EXPECTED)

    def test_delta_refuses_anything_but_subclass(self):
        applied = self.UPDATES / generate_sql.TEMPLATE_APPLIED
        current = (self.MIRRORS / "item_template.sql").read_text(encoding="utf-8")
        renamed = current.replace("'Mighty Belt'", "'Mightier Belt'", 1)
        with self.assertRaises(generate_sql.DataError):
            generate_sql.render_subclass_delta(applied, renamed, "fixture")

    def test_rerun_is_a_no_op(self):
        template = (self.UPDATES / generate_sql.TEMPLATE_MIGRATION).read_text(encoding="utf-8")
        shells = (self.UPDATES / generate_sql.SHELL_MIGRATION).read_text(encoding="utf-8")
        _, once = self.database(template, shells)
        _, twice = self.database(template + template, shells + shells)
        self.assertEqual(once, twice)


class ClientItems(unittest.TestCase):
    def test_client_item_dbc_agrees_with_the_misc_armor_render(self):
        # The client reads an item's class/subclass from its own Item.dbc; it
        # must say Miscellaneous wherever the server now does. The full rows
        # are in the generator's mirrors; the migrations only move subclass.
        import re
        rows = {row[0]: row for row in dbc("Item")}
        mirrors = MODULE / "data" / "generated"
        pattern = re.compile(r"^\((\d+), (\d+), (\d+), '(?:[^']|'')*', (\d+), \d+, (\d+)", re.M)
        seen = 0
        for name in ("item_template.sql", "unidentified_shells.sql"):
            for entry, item_class, subclass, display, inventory in pattern.findall(
                    (mirrors / name).read_text(encoding="utf-8")):
                row = rows[int(entry)]
                self.assertEqual((row[1], row[2], row[5], row[6]),
                                 (int(item_class), int(subclass), int(display), int(inventory)), entry)
                if int(item_class) == 4:
                    self.assertEqual(int(subclass), 0, entry)
                seen += 1
        self.assertEqual(seen, 1142 + 3)           # 1114 bases and 28 shells, plus the Shaman's three (xnrvn.3)


class LegacyCharacters(unittest.TestCase):
    def test_only_newly_profiled_classes_are_marked(self):
        sql, added = generate_sql.render_class_start_legacy(MODULE, self.classes())
        self.assertEqual(added, [7])
        self.assertIn("SELECT guid,1 FROM characters WHERE class IN (7);", sql)
        self.assertIn("SELECT guid,0 FROM characters WHERE class IN (7);", sql)
        self.assertNotIn("DELETE", sql.upper())
        shipped = (MODULE / "data/sql/db-characters/updates" / generate_sql.CLASS_START_LEGACY_MIGRATION)
        self.assertEqual(shipped.read_text(encoding="utf-8"), sql)

    def test_a_class_already_profiled_is_never_marked(self):
        # Mutation: treat the Barbarian as new, which would mark every existing
        # Barbarian - including ones mid-start - as having had its kit.
        original = generate_sql.CLASS_START_APPLIED
        try:
            generate_sql.CLASS_START_APPLIED = ()
            # With no applied profile to compare against, the guard falls back
            # to "every class is new" - the exact render the first test refuses.
            self.assertEqual(generate_sql.render_class_start_legacy(MODULE, self.classes())[1], [1, 2, 3, 7, 8, 12, 13, 14])
        finally:
            generate_sql.CLASS_START_APPLIED = original

    @staticmethod
    def classes():
        return generate_sql.class_start_rows(D3 / "class_starts.csv")


class ExtraArguments(unittest.TestCase):
    """run()'s `extra`: an -I or -D reaches the compiler as a flag (test_start_at_creation and bounties/test_bounties pass one), a file is compiled in."""

    PROGRAM = '#include "probe.h"\n#ifndef PROBE_FLAG\n#error the -D did not arrive\n#endif\nint main() { return PROBE_VALUE + Twice(2) - 6; }\n'

    def folder(self):
        temp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "probe.h").write_text("#define PROBE_VALUE 2\nint Twice(int);\n", encoding="utf-8")
        (root / "twice.cpp").write_text('#include "probe.h"\nint Twice(int v) { return 2 * v; }\n', encoding="utf-8")
        return root

    def test_split_extra_keeps_flags_flags_and_files_files(self):
        self.assertEqual((["-I", "a", "-DX=1", "-Ib", "-isystem", "c"], ["f.cpp", "g.cpp"]),
                         split_extra(["-I", "a", "f.cpp", "-DX=1", Path("g.cpp"), "-Ib", "-isystem", "c"]))

    def test_an_include_flag_a_define_and_a_source_reach_the_compiler(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        root = self.folder()
        for extra in (("-I", str(root), "-DPROBE_FLAG=1", root / "twice.cpp"), ("-I" + str(root), "-DPROBE_FLAG", str(root / "twice.cpp"))):
            with self.subTest(extra=[str(e) for e in extra]):
                ok, out = run(self.PROGRAM, extra=extra)
                self.assertTrue(ok, out)

    def test_without_the_flags_the_program_does_not_build(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        root = self.folder()
        with self.assertRaises(AssertionError):
            run(self.PROGRAM, extra=(root / "twice.cpp",))
        with self.assertRaises(AssertionError):
            run(self.PROGRAM, extra=("-I", str(root), root / "twice.cpp"))   # the -D is missing


if __name__ == "__main__":
    unittest.main()
