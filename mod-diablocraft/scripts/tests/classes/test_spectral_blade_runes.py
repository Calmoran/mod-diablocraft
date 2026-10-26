"""Spectral Blade - Barrier Blades gives its shield with every cast (diablocraft-04na, the designer's card diablocraft-cqdo).

    python3 mod-diablocraft/scripts/tests/classes/test_spectral_blade_runes.py

The designer: "this spell does not show any sort of shield applying to the player when they cast this spell with the barrier
blades rune". D3: "With each cast, gain a protective shield for 3 seconds that absorbs 4% of your Life in damage."

Why it never showed: the module gave the shield in Wizard::Cast, which dc_ability_targets::Finish calls only for a
cast that is not a projectile (the 2026-09-15 rule: a projectile's hits land at impact, in Impact). Barrier Blades'
record keeps the Speed of its visual donor Arcane Barrage (24 in the generated spell_dbc row, the client's Spell.dbc
and the committed patch-4.MPQ), so every cast of it is a projectile and Cast never ran. The shield record itself was
always right: a named, iconed, non-passive SCHOOL_ABSORB on the caster. The shield is now given from Wizard::Begin,
the OnCast hook every committed cast passes through, projectile or not.

The module's own functions are cut out of the Wizard's files (src/classes/wizard/) and compiled against doubles:
  real      Begin (the dispatch) and Spectral Blade's Begin, Shield, Apply, Num, RowOf, IsSkill, IsRune, StateOf, and
            the declarations that carry their default arguments (dc_wizard_internal.h); the other mechanics' Begin
            are their own files' business and do nothing here;
            the generated shell catalogue (dc_spell_shells.h) and the real number reader (dc_spell_numbers.cpp);
  data      every record in the generated spell_shells.sql (the 4% is the rune's second base point, the 3 seconds its
            duration row in the stock SpellDuration.dbc), so no number is typed;
  double    the Wizard and her auras: AddAura answers the way the pinned core does for an aura with no stacks
            (Unit::_TryStackingOrRefreshingExistingAura, then Aura::ModStackAmount: a recast puts the duration back
            to the record's own, which for the shield is permanent, and the amount back to the record's own, zero),
            an aura loses its time and goes at zero (Aura::Update); the spell mods (none apply to a helper record).
What this does not run: the real AddAura, the client drawing the buff, the dispatch in dc_combat.cpp (its three
facts are pinned as text below), and Cast itself (too large to compile alone: pinned as text that it no longer
carries the shield). MutationsAreCaught puts one defect back at a time; Today runs the same cases on the code
before the fix, which was one file (dc_wizard.cpp), with the harness laid out as that file was.
"""
import re
import shutil
import struct
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env
from test_skill_swing_recovery import SHELLS_SQL, definition, sql_rows

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
WIZARD_CPP = wizard_source.CPP
INTERNAL_H = wizard_source.FOLDER / "dc_wizard_internal.h"
COMBAT_CPP = MODULE / "src/combat/dc_combat.cpp"
SHELLS_H = MODULE / "src/combat/dc_spell_shells.h"
NUMBERS_CPP = MODULE / "src/combat/dc_spell_numbers.cpp"
STUBS = MODULE / "tests/spell_numbers/stubs"
DBC = ROOT / "azerothcore-wotlk/build/server/data/dbc"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/spectral-blade-runes"
BEFORE_THE_FIX = "362f4743"  # nightly when diablocraft-04na branched

RUNE = "Spectral Blade - Barrier Blades"
SHIELD = "Spectral Blade - Barrier Blades - shield"

# The functions the cases run, cut out of the Wizard's files in the order they must compile; the declarations with
# default arguments come first, out of dc_wizard_internal.h.
DECLARED = ["double Num(uint32 id, std::string_view token, std::string_view qualifier = {});",
            "Aura* Apply(Player* player, Unit* target, char const* helper, double seconds, Unit* caster = nullptr);"]
HELPERS = ["double Num(uint32 id, std::string_view token, std::string_view qualifier)",
           "Row const* RowOf(uint32 id)",
           "bool IsSkill(uint32 id, std::string_view skill)",
           "bool IsRune(uint32 id, std::string_view rune)",
           "State& StateOf(Player* player)",
           "Aura* Apply(Player* player, Unit* target, char const* helper, double seconds, Unit* caster)",
           "void Shield(Player* player, char const* helper, double lifePct, double seconds)"]
MECHANIC = "void Begin(Player* player, std::uint32_t spellId)"
# The same, as the code before the fix had them: one file, the helpers in an unnamed namespace, Begin doing every mechanic.
ONE_FILE_HELPERS = ["Row const* RowOf(uint32 id)",
           "bool IsSkill(uint32 id, std::string_view skill)",
           "bool IsRune(uint32 id, std::string_view rune)",
           "uint32 PassiveId(std::string_view name)",
           "bool Has(Player* player, char const* passive)",
           "uint32 BuffOf(Unit* unit, std::string_view skill)",
           "bool Signature(uint32 id)",
           "State& StateOf(Player* player)",
           "void After(Player* player, double seconds, std::function<void(Player*)> run)",
           "Aura* Apply(Player* player, Unit* target, char const* helper, double seconds, Unit* caster = nullptr)",
           "void Shield(Player* player, char const* helper, double lifePct, double seconds)"]
BEGIN = "void Begin(Player* player, std::uint32_t spellId, Unit* explicitTarget)"
CAST = "void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Position const& center,"

HARNESS = r'''
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
#include "DatabaseEnv.h"
#include "SpellMgr.h"
#include "dc_spell_numbers.h"
#include "@SHELLS@"

using uint64 = std::uint64_t;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); std::exit(3); } } while (0)

static uint64 now = 100000;                                          // the game clock, ms
static double shieldPotency = 1.0;                                   // what ItemPowers::ShieldFactor answers

struct ObjectGuid { uint64 raw = 0; uint64 GetRawValue() const { return raw; } };
struct Position {};
struct AuraEffect { int32 amount = 0; void ChangeAmount(int32 a) { amount = a; } };
struct Aura {
    AuraEffect effect; int32 maxDuration = -1, duration = -1;          // -1 is permanent
    AuraEffect* GetEffect(int) { return &effect; }
    void SetMaxDuration(int32 d) { maxDuration = d; }
    void SetDuration(int32 d) { duration = d; }
};
enum { EFFECT_0 = 0 };

// One caster in these cases (the Wizard), so the core's per-caster lookup of an aura is its spell id.
struct Unit {
    ObjectGuid guid; bool alive = true; uint32 maxHealth = 50000;
    std::map<uint32, Aura> auras;
    ObjectGuid GetGUID() const { return guid; }
    bool IsAlive() const { return alive; }
    uint32 GetMaxHealth() const { return maxHealth; }
    bool HasAura(uint32 id) const { return auras.count(id) != 0; }
    Position GetPosition() const { return {}; }
    // Unit::AddAura -> Aura::TryRefreshStackOrCreate for a record with no stacks. A new aura takes the record's own
    // duration and amount. A second cast finds the first (Unit::_TryStackingOrRefreshingExistingAura,
    // Unit.cpp:4386) and ModStackAmount(1) (SpellAuras.cpp:1056) refreshes it: RefreshTimers puts the duration back to
    // the record's, SetStackAmount recalculates the amount from the record's base points. Either way the aura is back
    // to what the record says; the caller then sets what it means.
    Aura* AddAura(uint32 id, Unit* target) {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(id);
        if (!info || !target->alive) return nullptr;
        Aura& aura = target->auras[id];
        aura.maxDuration = aura.duration = info->GetDuration();
        aura.effect.amount = info->Effects[0].BasePoints + (info->Effects[0].DieSides == 1 ? 1 : 0);
        return &aura;
    }
};
struct Player : Unit { bool IsValidAttackTarget(Unit*) const { return true; } Unit* GetSelectedUnit() { return nullptr; } };
struct Creature : Unit {};

// Aura::Update: the time runs down and the aura goes at zero.
static void Advance(Unit& unit, int32 ms) {
    now += ms;
    for (auto it = unit.auras.begin(); it != unit.auras.end();) {
        Aura& aura = it->second;
        if (aura.duration > 0) {
            aura.duration -= ms;
            if (aura.duration <= 0) { it = unit.auras.erase(it); continue; }
        }
        ++it;
    }
}

namespace DC::Combat {
    // No spell mod touches a helper record (no class mask), so the duration is what was asked.
    double ModifiedDurationSeconds(Player*, std::uint32_t, double seconds) { return seconds; }
    double AttacksPerSecond(Player*, std::uint32_t = 0) { return 1.0; }
    bool Strike(Player*, Unit*, std::uint32_t, std::optional<double> = std::nullopt, bool = false) { return false; }
    std::vector<Unit*> StrikeArea(Player*, std::uint32_t, Position const&, double, std::optional<double> = std::nullopt,
                                  bool = false) { return {}; }
    namespace Passives { bool Has(Player*, char const*) { return false; } }   // this Wizard has no passive
    // Ashnagarr's Blood Bracer (diablocraft-46s0p): the one reader every shield's amount is multiplied by; 1 with no item worn.
    namespace ItemPowers { double ShieldFactor(Player const*) { return shieldPotency; } }
}
namespace DC::Classes { std::string CategoryOf(std::uint32_t) { return "Primary"; } }

@LAYOUT@
using namespace DC::Combat;

// The dc_spell_values rows: the exact numbers no record field holds (Deflection's absorb time among them).
static void LoadExact(char const* path) {
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::vector<std::string> cells;
        std::string cell;
        std::istringstream pieces(line);
        while (std::getline(pieces, cell, '\t')) cells.push_back(cell);
        WorldDatabase.Rows.push_back({Field{cells[0]}, Field{cells[1]}, Field{cells[2]}, Field{cells[3]}});
    }
}

static void LoadRecords(char const* path) {
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::istringstream cells(line);
        long v[8];
        for (long& x : v) cells >> x;
        SpellInfo& info = sSpellMgr->Add(uint32(v[0]));
        info.Duration = int32(v[1]);
        for (int slot = 0; slot < 3; ++slot) {
            info.Effects[slot].BasePoints = int32(v[2 + 2 * slot]);
            info.Effects[slot].DieSides = int32(v[3 + 2 * slot]);
        }
    }
}

static uint32 RuneId(char const* skill, char const* rune) {
    for (auto const& row : Shells::Abilities)
        if (!std::strcmp(row.skill, skill) && !std::strcmp(row.rune, rune)) return row.id;
    return 0;
}

int main(int argc, char** argv) {
    if (argc != 4) { std::fprintf(stderr, "usage: harness records.tsv exact.tsv case\n"); return 2; }
    LoadRecords(argv[1]);
    LoadExact(argv[2]);
    std::string name = argv[3];
    Player w; w.guid.raw = 1;
    Unit enemy; enemy.guid.raw = 77;
    uint32 const rune = RuneId("Spectral Blade", "Barrier Blades");
    uint32 const shield = Shells::HelperFor("@SHIELD@");
    CHECK(rune && shield);
    if (name == "a_barrier_blades_cast_puts_the_shield_on_the_caster") {
        Wizard::Begin(&w, rune, nullptr);
        CHECK(w.HasAura(shield));
        CHECK(w.auras[shield].effect.amount == 2000);                    // 4% of 50000: the rune's second base point
        CHECK(w.auras[shield].duration == 3000 && w.auras[shield].maxDuration == 3000);  // the rune's duration row
    } else if (name == "the_shield_is_four_percent_of_the_casters_maximum_life") {
        w.maxHealth = 123457;
        Wizard::Begin(&w, rune, nullptr);
        CHECK(w.auras[shield].effect.amount == 4938);                    // 123457 x 4 / 100, rounded down
    } else if (name == "the_shield_is_scaled_by_the_wearers_shield_potency") {
        shieldPotency = 1.75;                                            // Ashnagarr's Blood Bracer rolled 75
        Wizard::Begin(&w, rune, nullptr);
        CHECK(w.auras[shield].effect.amount == 3500);                    // 4% of 50000 x 1.75
        CHECK(w.auras[shield].duration == 3000);                         // the time is not scaled
    } else if (name == "a_cast_at_a_target_gives_the_same_shield") {
        Wizard::Begin(&w, rune, &enemy);
        CHECK(w.auras[shield].effect.amount == 2000 && w.auras[shield].duration == 3000);
    } else if (name == "a_second_cast_replaces_the_running_shield_it_does_not_stack") {
        Wizard::Begin(&w, rune, nullptr);
        w.auras[shield].effect.amount -= 700;                            // hit for 700 meanwhile
        Advance(w, 1000);
        CHECK(w.auras[shield].duration == 2000);
        Wizard::Begin(&w, rune, nullptr);
        CHECK(w.auras.size() == 1);
        CHECK(w.auras[shield].effect.amount == 2000);                    // full again, not 1300 + 2000
        CHECK(w.auras[shield].duration == 3000 && w.auras[shield].maxDuration == 3000);
    } else if (name == "the_shield_runs_out_after_three_seconds") {
        Wizard::Begin(&w, rune, nullptr);
        Advance(w, 2999);
        CHECK(w.HasAura(shield));
        Advance(w, 1);
        CHECK(!w.HasAura(shield));
    } else if (name == "a_recast_starts_the_three_seconds_again") {
        Wizard::Begin(&w, rune, nullptr);
        Advance(w, 2000);
        Wizard::Begin(&w, rune, nullptr);
        Advance(w, 2999);
        CHECK(w.HasAura(shield));
        Advance(w, 1);
        CHECK(!w.HasAura(shield));
    } else if (name == "no_other_skill_gives_this_shield") {
        // Every other skill and rune in the catalogue, Spectral Blade's other five among them. Several of them state an
        // absorb size of their own (Diamond Skin's runes, Deflection): none of them may give this shield.
        int checked = 0;
        for (auto const& row : Shells::Abilities)
            if (row.id != rune) { Wizard::Begin(&w, row.id, nullptr); ++checked; }
        CHECK(checked > 100 && !w.HasAura(shield));
    } else if (name == "the_other_shields_are_left_alone") {
        uint32 const deflection = Shells::HelperFor("Magic Weapon - Deflection - shield");
        uint32 const diamond = RuneId("Diamond Skin", "");
        CHECK(deflection && diamond);
        w.auras[deflection] = Aura{{1234}, 2500, 2500};
        w.auras[diamond] = Aura{{9000}, 4000, 4000};
        Wizard::Begin(&w, rune, nullptr);
        CHECK(w.auras.size() == 3 && w.HasAura(shield));                 // all three beside each other
        CHECK(w.auras[deflection].effect.amount == 1234 && w.auras[deflection].duration == 2500);
        CHECK(w.auras[diamond].effect.amount == 9000 && w.auras[diamond].duration == 4000);
    } else {
        std::fprintf(stderr, "no case %s\n", name.c_str());
        return 4;
    }
    std::puts("ok");
    return 0;
}
'''

CASES = [
    "a_barrier_blades_cast_puts_the_shield_on_the_caster",
    "the_shield_is_four_percent_of_the_casters_maximum_life",
    "the_shield_is_scaled_by_the_wearers_shield_potency",
    "a_cast_at_a_target_gives_the_same_shield",
    "a_second_cast_replaces_the_running_shield_it_does_not_stack",
    "the_shield_runs_out_after_three_seconds",
    "a_recast_starts_the_three_seconds_again",
    "no_other_skill_gives_this_shield",
    "the_other_shields_are_left_alone",
]
# The cases the shield being absent (the code before the fix) must fail: all but the one that wants none given.
FAILS_BEFORE = [case for case in CASES if case != "no_other_skill_gives_this_shield"]

SPLIT = r'''namespace DC::Combat::Wizard::Shared {
using Row = Shells::Ability;
std::recursive_mutex mutex;
uint64 Now() { return now; }
struct Timer { uint64 at = 0; std::function<void(Player*)> run; };
struct State {
    std::vector<Timer> timers;
    uint64 flameWard = 0;
};
std::unordered_map<uint64, State> states;

@DECLARED@

@HELPERS@
}  // namespace DC::Combat::Wizard::Shared

// The other mechanics' Begin: their own files' business.
namespace DC::Combat::Wizard::Teleport { void Begin(Player*, Shared::State&, uint32) {} }
namespace DC::Combat::Wizard::Passive {
void Prodigy(Player*, std::uint32_t) {}
void ArcaneDynamo(Player*, Shared::State&, std::uint32_t) {}
void IllusionistBegin(Player*, Shared::State&, std::uint32_t) {}
}
namespace DC::Combat::Wizard::EnergyTwister { void Begin(Player*, Shared::State&, std::uint32_t, Unit*) {} }
namespace DC::Combat::Wizard::Familiar { void Begin(Player*, Shared::State&, std::uint32_t, Unit*) {} }

namespace DC::Combat::Wizard::SpectralBlade {
using namespace Shared;
@MECHANIC@
}  // namespace DC::Combat::Wizard::SpectralBlade

namespace DC::Combat::Wizard {
using namespace Shared;
@BEGIN@
}  // namespace DC::Combat::Wizard

'''

ONE_FILE = r'''namespace DC::Combat::Wizard {
namespace {
using Row = Shells::Ability;
std::recursive_mutex mutex;
double Num(uint32 id, std::string_view token, std::string_view qualifier = {}) { return Numbers::Num(id, token, qualifier); }
uint64 Now() { return now; }
struct Timer { uint64 at = 0; std::function<void(Player*)> run; };
struct State {
    std::vector<Timer> timers;
    unsigned flashes = 0, stormCharges = 0;
    uint32 empowered = 0;
    uint64 familiarReady = 0, illusionistSpeed = 0, flameWard = 0;
};
std::unordered_map<uint64, State> states;

@HELPERS@

Unit* Find(Player*, ObjectGuid) { return nullptr; }
Creature* FamiliarOf(Player*) { return nullptr; }               // no Familiar is out
void ReversalBegin(Player*, State&, uint32) {}                  // Teleport's own business
void TeleportBegin(Player*, State&, uint32) {}
}  // namespace

@BEGIN@
}  // namespace DC::Combat::Wizard

'''


def durations():
    """SpellDuration.dbc: row id -> milliseconds (-1 is permanent)."""
    data = (DBC / "SpellDuration.dbc").read_bytes()
    _magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    return {struct.unpack_from("<I", data, 20 + i * size)[0]: struct.unpack_from("<i", data, 24 + i * size)[0]
            for i in range(count)}


def generated_rows():
    return {int(row["ID"]): row for row in sql_rows(SHELLS_SQL.read_text(encoding="utf-8"))}


def helper_id(identity):
    found = re.search(r'\{(\d+), "%s", \d+\}' % re.escape(identity), SHELLS_H.read_text(encoding="utf-8"))
    assert found, "no helper named %s" % identity
    return int(found.group(1))


def rune_id(skill, rune):
    found = re.search(r'\{(\d+), "%s", "%s", [\d.]+\}' % (re.escape(skill), re.escape(rune)),
                      SHELLS_H.read_text(encoding="utf-8"))
    assert found, "no %s - %s" % (skill, rune)
    return int(found.group(1))


def records_file():
    """Every generated record, as the harness's spell store takes them: id, duration ms, then three
    (base points, die sides) pairs - every field out of the generated row, so a number another skill states (Diamond
    Skin's 40%) reads as it does in the server and not as absent."""
    rows, lengths = generated_rows(), durations()
    lines = []
    for ident, row in sorted(rows.items()):
        cells = [ident, lengths.get(int(row["DurationIndex"]), 0)]
        for slot in (1, 2, 3):
            cells += [row["EffectBasePoints_%d" % slot], row["EffectDieSides_%d" % slot]]
        lines.append(" ".join(str(cell) for cell in cells))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    records = SCRATCH / "records.tsv"
    records.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # The exact-value table, as test_spell_numbers reads it out of the same generated file.
    exact = SCRATCH / "exact.tsv"
    exact.write_text("\n".join("\t".join(row) for row in re.findall(
        r"\((\d+),'([a-z_]+)','([a-z_]*)',([0-9.]+)\)", SHELLS_SQL.read_text(encoding="utf-8"))) + "\n",
        encoding="utf-8")
    return records, exact


def toolchain():
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler on this host")
    if not DBC.is_dir():
        raise unittest.SkipTest("client DBCs are not extracted")
    return compiler


def declared(header):
    for line in DECLARED:
        assert header.count(line) == 1, "%r is not declared once in dc_wizard_internal.h" % line
    return "\n".join(DECLARED)


def build(source, label, one_file=False):
    """`source` is the Wizard's files joined (wizard_source.CPP); with `one_file`, the single dc_wizard.cpp of the code
    before the split."""
    compiler = toolchain()
    if one_file:
        layout = ONE_FILE.replace("@HELPERS@", "\n\n".join(definition(marker, source) for marker in ONE_FILE_HELPERS))
    else:
        layout = (SPLIT.replace("@DECLARED@", declared(INTERNAL_H.read_text(encoding="utf-8")))
                  .replace("@HELPERS@", "\n\n".join(definition(marker, source) for marker in HELPERS))
                  .replace("@MECHANIC@", definition(MECHANIC, source)))
    program = (HARNESS.replace("@LAYOUT@", layout).replace("@BEGIN@", definition(BEGIN, source))
               .replace("@SHELLS@", SHELLS_H.as_posix()).replace("@SHIELD@", SHIELD))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cpp = SCRATCH / (label + ".cpp")
    cpp.write_text(program, encoding="utf-8")
    binary = SCRATCH / label
    binary = harness_env.build([cpp, NUMBERS_CPP], flags=["-std=c++17", "-O0"], includes=[STUBS, MODULE / "src/combat"])
    return binary


def failing(source, label, one_file=False):
    binary, (records, exact) = build(source, label, one_file), records_file()
    return [case for case in CASES
            if harness_env.run([str(binary), str(records), str(exact), case],
                               capture_output=True, text=True).returncode]


class Rule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WIZARD_CPP.read_text(encoding="utf-8")
        cls.binary = build(cls.source, "production")
        cls.records, cls.exact = records_file()


def make_case(case):
    def check(self):
        done = harness_env.run([str(self.binary), str(self.records), str(self.exact), case],
                               capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, case + ": " + done.stderr.strip())
    return check


for _case in CASES:
    setattr(Rule, "test_" + _case, make_case(_case))


class Visible(unittest.TestCase):
    """The record the shield rides on is a buff the client draws, from the generated row."""

    def test_the_shield_record_is_a_visible_absorb_on_the_caster(self):
        row = generated_rows()[helper_id(SHIELD)]
        self.assertEqual(int(row["Attributes"]) & 0x40, 0, "a passive aura is never sent to the client")
        self.assertEqual(int(row["Attributes"]) & 0x80, 0, "do-not-display keeps it off the aura bar")
        self.assertEqual(row["Name_Lang_enUS"], SHIELD)
        self.assertNotEqual(int(row["SpellIconID"]), 0, "a buff with no icon shows as a question mark")
        self.assertEqual((int(row["Effect_1"]), int(row["EffectAura_1"]), int(row["ImplicitTargetA_1"])), (6, 69, 1),
                         "APPLY_AURA, SCHOOL_ABSORB, on the caster")
        self.assertEqual(int(row["EffectMiscValue_1"]), 127, "every school")
        self.assertEqual(int(row["AuraInterruptFlags"]), 0, "nothing the Wizard does cancels it")


class Wiring(unittest.TestCase):
    """Cast and the dispatch are too large to compile alone: their facts are pinned as text."""

    @classmethod
    def setUpClass(cls):
        cls.wizard = WIZARD_CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT_CPP.parent / "dc_combat_internal.h", *sorted(COMBAT_CPP.parent.glob("dc_combat*.cpp"))])

    def test_cast_no_longer_gives_the_shield(self):
        self.assertNotIn(SHIELD, definition(CAST, self.wizard),
                         "Cast is skipped for a projectile record, and Barrier Blades is one")
        given = re.findall(r'Shield\(player, "%s"' % re.escape(SHIELD), self.wizard)
        self.assertEqual(1, len(given), "the shield is given in one place")
        self.assertIn('Shield(player, "%s"' % SHIELD, definition(MECHANIC, self.wizard), "and that place is Spectral Blade's Begin")
        self.assertIn("SpectralBlade::Begin(player, spellId);", definition(BEGIN, self.wizard))

    def test_the_number_reader_is_the_real_one(self):
        """The harness compiles the Wizard's Num; this pins that it is still the one-line forward to Numbers::Num."""
        self.assertRegex(self.wizard, r"double Num\(uint32 id, std::string_view token, std::string_view qualifier\)"
                                      r"\s*\{\s*return Numbers::Num\(id, token, qualifier\);\s*\}")

    def test_a_projectile_cast_skips_cast_but_not_begin(self):
        finish = definition("void Finish()", self.combat)
        self.assertRegex(finish, r"if \(!paid \|\| !player\)\s+return;")
        self.assertRegex(finish, r"case GroundMissile::Path::AtCast:\s+ResolveCast\(")
        begin = definition("void Begin()", self.combat)
        between = begin[begin.index("paid = true;"):begin.index("Wizard::Begin(player, shell.spellId")]
        self.assertNotIn("return", between, "a paid cast must reach Wizard::Begin")


MUTATIONS = [
    ("Begin gives no Barrier Blades shield",
     'if (IsRune(spellId, "Barrier Blades"))\n            Shield(player, "Spectral Blade - Barrier Blades - shield", Num(spellId, "absorb_capacity_life_pct"),\n                   Num(spellId, "absorb_duration_seconds"));',
     "",
     ["a_barrier_blades_cast_puts_the_shield_on_the_caster", "a_second_cast_replaces_the_running_shield_it_does_not_stack",
      "a_recast_starts_the_three_seconds_again", "the_other_shields_are_left_alone"]),
    ("the size and the time swapped",
     'Num(spellId, "absorb_capacity_life_pct"),\n                   Num(spellId, "absorb_duration_seconds"));',
     'Num(spellId, "absorb_duration_seconds"),\n                   Num(spellId, "absorb_capacity_life_pct"));',
     ["a_barrier_blades_cast_puts_the_shield_on_the_caster", "the_shield_is_four_percent_of_the_casters_maximum_life"]),
    ("the shield never runs out (no duration given)",
     'Num(spellId, "absorb_duration_seconds"));',
     "-1);",
     ["the_shield_runs_out_after_three_seconds", "a_recast_starts_the_three_seconds_again"]),
    ("anything that states an absorb size gives it, not Barrier Blades alone",
     'if (IsRune(spellId, "Barrier Blades"))',
     'if (Num(spellId, "absorb_capacity_life_pct") > 0)',
     ["no_other_skill_gives_this_shield"]),
    ("another rune's cast gives it, not Barrier Blades'",
     'if (IsRune(spellId, "Barrier Blades"))',
     'if (IsRune(spellId, "Siphoning Blade"))',
     ["a_barrier_blades_cast_puts_the_shield_on_the_caster"]),
    ("only a cast with a target gives it",
     "        SpectralBlade::Begin(player, spellId);",
     "        if (explicitTarget)\n            SpectralBlade::Begin(player, spellId);",
     ["a_barrier_blades_cast_puts_the_shield_on_the_caster"]),
    ("the shield skips the wearer's shield potency (Ashnagarr's Blood Bracer, diablocraft-46s0p)",
     "lifePct / 100 * ItemPowers::ShieldFactor(player)",
     "lifePct / 100",
     ["the_shield_is_scaled_by_the_wearers_shield_potency"]),
    ("the shield's clock is never set, so a recast leaves it permanent",
     "aura->SetDuration(int32(seconds * 1000));",
     "",
     ["the_shield_runs_out_after_three_seconds", "a_recast_starts_the_three_seconds_again"]),
]


class MutationsAreCaught(unittest.TestCase):
    def test_each_defect_fails_the_cases_that_name_it(self):
        source = WIZARD_CPP.read_text(encoding="utf-8")
        for index, (label, old, new, expected) in enumerate(MUTATIONS):
            with self.subTest(label):
                self.assertEqual(source.count(old), 1, "mutation %r does not match once" % label)
                caught = failing(source.replace(old, new), "mutant%d" % index)
                self.assertTrue(set(expected) <= set(caught),
                                "%s: expected %s to fail, failed %s" % (label, expected, caught))

    def test_the_old_place_is_refused(self):
        """The shield put back into Cast is caught by the pin, whatever Begin does."""
        source = WIZARD_CPP.read_text(encoding="utf-8")
        anchor = "        if (IsSkill(id, \"Mirror Image\"))\n            MirrorImage::SummonImages(player, id);"
        self.assertEqual(source.count(anchor), 1)
        mutated = source.replace(anchor, anchor + '\n        if (IsRune(id, "Barrier Blades"))\n            Shield(player, "' + SHIELD + '", 4, 3);')
        self.assertIn(SHIELD, definition(CAST, mutated))


class Today(unittest.TestCase):
    """The same cases on the code before the fix: the shield is not given."""

    def test_the_code_before_the_fix_fails_the_shield_cases(self):
        old = subprocess.run(["git", "show", BEFORE_THE_FIX + ":mod-diablocraft/src/classes/wizard/dc_wizard.cpp"],
                             cwd=ROOT, capture_output=True, text=True)
        if old.returncode:
            raise unittest.SkipTest("the parent commit is not in this clone")
        self.assertEqual(sorted(failing(old.stdout, "today", one_file=True)), sorted(FAILS_BEFORE))


if __name__ == "__main__":
    unittest.main()
