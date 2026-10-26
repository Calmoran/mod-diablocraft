"""Spectral Blade - Flame Blades deals its damage, and its stacks are a buff the Wizard wears (diablocraft-o2be,
Part 2 of docs/briefs/spectral-blade-runes-brief.md, the designer's card diablocraft-tnek).

    python3 mod-diablocraft/scripts/tests/classes/test_flame_blades.py

The designer: the rune "deals no damage at all". D3: "Each enemy hit increases the damage of your Fire spells by 1%, up to a
maximum of 30%, for 5 seconds."

Why it dealt none: the loader in dc_combat.cpp gives a shell its damage_pct only when its record states no
duration_seconds (a duration is read as the damage waiting on something: a summon, an armour, a fuse). Flame Blades'
record states duration_seconds, because that is the name its 5 seconds had in the values sheet, so it loaded with
damage 0, ComputeHit made 0, ResolveHit skipped Wizard::Landed (it runs for a hit above 0 only) and the rune hit for
nothing and gave no bonus either. The 5 seconds are the length of a stack, not a wait: the token is now
bonus_duration_seconds, which the loader does not read as a wait.

The bonus is a buff now: the helper record "Flame Blades", a stacking aura on the Wizard, one stack for each enemy
hit, each on its own clock (d3planner's simulator, wizard.js:98: refresh false, maxstacks 30). ElementalBonus reads
the stacks back, so the buff shows the number the damage uses.

Two harnesses compile the module's own functions against doubles of the core:
  loader    DamageWaits, cut out of dc_combat.cpp, over every shell in the generated catalogue and the real number
            reader (dc_spell_numbers.cpp), so the answer for each record is the shipped record's;
  stacks    FlameBlade, SyncFlameBlades, FlameBladesBonus, Apply, Num and ElementalBonus, cut out of the Wizard's
            files (src/classes/wizard/), the default arguments from dc_wizard_internal.h, with the Wizard, her
            auras (AddAura answers as the pinned core does for an aura that stacks: one more stack, the time back
            to the record's) and the clock as doubles.
What this does not run: ResolveHit, ComputeHit and the core's cone selection (the record is checked: Speed 0, Fire,
a 15-yard cone, 168), the client drawing the buff (the live check in docs/test-spectral-blade-runes.md (Part 2)), and Landed and
OnPlayerUpdate (too large to compile alone: pinned as text). MutationsAreCaught puts one defect back at a time;
Today runs the loader on the code before the fix.
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
from test_skill_swing_recovery import definition
from test_spectral_blade_runes import (COMBAT_CPP, DBC, INTERNAL_H, MODULE, NUMBERS_CPP, ROOT, SHELLS_H, SHELLS_SQL,
                                       STUBS, WIZARD_CPP, declared, durations, generated_rows, helper_id, rune_id,
                                       toolchain)

SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/flame-blades"
BEFORE_THE_FIX = "174b7b59"  # nightly when diablocraft-o2be branched

BUFF = "Flame Blades"
WAITS = "bool DamageWaits(std::uint32_t id)"
LANDED = "void Landed(Player* player, Unit* target, std::uint32_t spellId, Hit const& hit, bool periodic)"
UPDATE = "void OnPlayerUpdate(Player* player, uint32 diff) override"

# The functions the stacks cases run, cut out of the Wizard's files in the order they must compile: the shared helpers
# (their default arguments are declared in dc_wizard_internal.h, test_spectral_blade_runes.DECLARED), then Spectral
# Blade's own.
HELPERS = ["double Num(uint32 id, std::string_view token, std::string_view qualifier)",
           "Row const* RowOf(uint32 id)",
           "bool IsSkill(uint32 id, std::string_view skill)",
           "bool IsRune(uint32 id, std::string_view rune)",
           "State& StateOf(Player* player)",
           "Aura* Apply(Player* player, Unit* target, char const* helper, double seconds, Unit* caster)"]
MECHANIC = ["void FlameBlade(Player* player, uint32 id)",
            "void SyncFlameBlades(Player* player)",
            "void FlameBladesBonus(Player* player, double& bonus)"]
ELEMENTAL = "double ElementalBonus(Player* player, unsigned school)"

COMMON = r'''
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

// Every generated record, as the spell store takes it: id, duration ms, stack limit, then three (base points, die
// sides) pairs, each out of the generated row.
static void LoadRecords(char const* path) {
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::istringstream cells(line);
        long v[9];
        for (long& x : v) cells >> x;
        SpellInfo& info = sSpellMgr->Add(uint32(v[0]));
        info.Duration = int32(v[1]);
        info.StackAmount = uint32(v[2]);
        for (int slot = 0; slot < 3; ++slot) {
            info.Effects[slot].BasePoints = int32(v[3 + 2 * slot]);
            info.Effects[slot].DieSides = int32(v[4 + 2 * slot]);
        }
    }
}

static uint32 RuneId(char const* skill, char const* rune) {
    for (auto const& row : DC::Combat::Shells::Abilities)
        if (!std::strcmp(row.skill, skill) && !std::strcmp(row.rune, rune)) return row.id;
    return 0;
}
'''

LOADER = COMMON + r'''
namespace DC::Combat {
@WAITS@
}
using namespace DC::Combat;

int main(int argc, char** argv) {
    if (argc != 2) { std::fprintf(stderr, "usage: loader records.tsv\n"); return 2; }
    LoadRecords(argv[1]);
    for (auto const& row : Shells::Abilities) std::printf("waits %u %d\n", row.id, DamageWaits(row.id) ? 1 : 0);
    // What the loader gives a shell that does not wait: the record's damage_pct.
    uint32 const flame = RuneId("Spectral Blade", "Flame Blades"), base = RuneId("Spectral Blade", "");
    std::printf("damage %u %g\n", flame, Numbers::Num(flame, "damage_pct"));
    std::printf("damage %u %g\n", base, Numbers::Num(base, "damage_pct"));
    return 0;
}
'''

STACKS = COMMON + r'''
static uint64 now = 100000;                                          // the game clock, ms
constexpr unsigned SPELL_SCHOOL_MASK_FIRE = 4, SPELL_SCHOOL_MASK_FROST = 16;

struct ObjectGuid { uint64 raw = 0; uint64 GetRawValue() const { return raw; } };
struct Position {};
struct Aura {
    int32 maxDuration = -1, duration = -1; uint8 stacks = 1;           // -1 is permanent
    void SetMaxDuration(int32 d) { maxDuration = d; }
    void SetDuration(int32 d) { duration = d; }
    void SetStackAmount(uint8 s) { stacks = s; }
    uint8 GetStackAmount() const { return stacks; }
};

struct Unit {
    ObjectGuid guid; bool alive = true;
    std::map<uint32, Aura> auras;
    ObjectGuid GetGUID() const { return guid; }
    bool IsAlive() const { return alive; }
    bool HasAura(uint32 id) const { return auras.count(id) != 0; }
    Aura* GetAura(uint32 id) { auto f = auras.find(id); return f == auras.end() ? nullptr : &f->second; }
    void RemoveAurasDueToSpell(uint32 id) { auras.erase(id); }
    // Unit::AddAura -> Aura::TryRefreshStackOrCreate. A new aura is one stack at the record's duration. One that is
    // there is found (Unit::_TryStackingOrRefreshingExistingAura) and ModStackAmount(1) adds a stack up to the
    // record's limit and puts the time back to the record's.
    Aura* AddAura(uint32 id, Unit* target) {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(id);
        if (!info || !target->alive) return nullptr;
        auto found = target->auras.find(id);
        if (found != target->auras.end()) {
            Aura& aura = found->second;
            if (info->StackAmount && aura.stacks < info->StackAmount) ++aura.stacks;
            aura.maxDuration = aura.duration = info->GetDuration();
            return &aura;
        }
        Aura& aura = target->auras[id];
        aura = Aura{};
        aura.maxDuration = aura.duration = info->GetDuration();
        return &aura;
    }
};
struct Player : Unit {};

namespace DC::Combat {
    // No spell mod touches a helper record (no class mask), so the duration is what was asked.
    double ModifiedDurationSeconds(Player*, std::uint32_t, double seconds) { return seconds; }
}

namespace DC::Combat::Wizard::Shared {
using Row = Shells::Ability;
std::recursive_mutex mutex;
uint64 Now() { return now; }
struct Expiring { uint64 until = 0; double value = 0; };
struct State {
    std::vector<Expiring> absoluteZero;
    std::vector<uint64> flameBlades;
};
std::unordered_map<uint64, State> states;

@DECLARED@

@HELPERS@
}  // namespace DC::Combat::Wizard::Shared

namespace DC::Combat::Wizard::SpectralBlade {
using namespace Shared;
@MECHANIC@
}  // namespace DC::Combat::Wizard::SpectralBlade

namespace DC::Combat::Wizard {
using namespace Shared;
@ELEMENTAL@
}  // namespace DC::Combat::Wizard

using namespace DC::Combat;
using namespace DC::Combat::Wizard;
using namespace DC::Combat::Wizard::SpectralBlade;

// The clock runs, the aura goes at zero (Aura::Update), then the module's update hook syncs the stacks.
static void Advance(Player& unit, int32 ms) {
    now += ms;
    for (auto it = unit.auras.begin(); it != unit.auras.end();) {
        Aura& aura = it->second;
        if (aura.duration > 0) {
            aura.duration -= ms;
            if (aura.duration <= 0) { it = unit.auras.erase(it); continue; }
        }
        ++it;
    }
    SyncFlameBlades(&unit);
}

int main(int argc, char** argv) {
    if (argc != 3) { std::fprintf(stderr, "usage: stacks records.tsv case\n"); return 2; }
    LoadRecords(argv[1]);
    std::string name = argv[2];
    Player w; w.guid.raw = 1;
    uint32 const rune = RuneId("Spectral Blade", "Flame Blades");
    uint32 const buff = Shells::HelperFor("@BUFF@");
    CHECK(rune && buff);
    auto hit = [&](int n) { for (int i = 0; i < n; ++i) FlameBlade(&w, rune); };
    auto fire = [&]() { return ElementalBonus(&w, SPELL_SCHOOL_MASK_FIRE); };
    if (name == "each_enemy_hit_is_one_stack") {
        CHECK(fire() == 0 && !w.HasAura(buff));
        hit(5);
        CHECK(w.HasAura(buff) && w.auras[buff].stacks == 5);
        CHECK(fire() == 5);                                              // 1% a hit, from the rune's record
        CHECK(w.auras[buff].duration == 5000 && w.auras[buff].maxDuration == 5000);
    } else if (name == "the_stacks_stop_at_thirty") {
        hit(40);
        CHECK(w.auras[buff].stacks == 30);
        CHECK(fire() == 30);
    } else if (name == "the_buff_shows_the_number_the_damage_uses") {
        for (int n = 1; n <= 35; ++n) {
            hit(1);
            int const expect = n < 30 ? n : 30;
            CHECK(w.auras[buff].stacks == expect);
            CHECK(fire() == expect);
        }
    } else if (name == "only_fire_damage_gets_it") {
        hit(10);
        CHECK(fire() == 10);
        for (unsigned school : {1u, 2u, 8u, 16u, 32u, 64u}) CHECK(ElementalBonus(&w, school) == 0);
    } else if (name == "each_hit_runs_out_on_its_own_clock") {
        hit(3);                                                          // t = 0
        Advance(w, 2000);
        hit(2);                                                          // t = 2 s
        CHECK(w.auras[buff].stacks == 5 && fire() == 5);
        Advance(w, 2999);                                                // t = 4.999 s: the first three still count
        CHECK(w.auras[buff].stacks == 5 && fire() == 5);
        Advance(w, 1);                                                   // t = 5 s: they are gone, the other two stay
        CHECK(w.HasAura(buff) && w.auras[buff].stacks == 2 && fire() == 2);
        CHECK(w.auras[buff].duration == 2000);                           // the buff's time is the newest stack's
        Advance(w, 1999);
        CHECK(w.auras[buff].stacks == 2 && fire() == 2);
        Advance(w, 1);                                                   // t = 7 s: the last two
        CHECK(!w.HasAura(buff) && fire() == 0);
    } else if (name == "a_hit_puts_the_buffs_time_back_to_five_seconds") {
        hit(1);
        Advance(w, 4000);
        CHECK(w.auras[buff].duration == 1000);
        hit(1);
        CHECK(w.auras[buff].stacks == 2);
        CHECK(w.auras[buff].duration == 5000 && w.auras[buff].maxDuration == 5000);
    } else if (name == "the_oldest_stack_goes_first_when_they_are_full") {
        hit(30);                                                         // t = 0
        Advance(w, 4000);
        hit(1);                                                          // the 31st: one of the first thirty goes
        CHECK(w.auras[buff].stacks == 30 && fire() == 30);
        Advance(w, 1000);                                                // t = 5 s: the 29 left of the first are gone
        CHECK(w.HasAura(buff) && w.auras[buff].stacks == 1 && fire() == 1);
    } else if (name == "a_cancelled_buff_starts_again_from_the_next_hit") {
        hit(5);
        w.RemoveAurasDueToSpell(buff);                                   // the player cancels it
        CHECK(fire() == 0);                                              // the bonus went with it
        hit(1);                                                          // a hit before the next update
        CHECK(w.HasAura(buff) && w.auras[buff].stacks == 1 && fire() == 1);  // not six
        w.RemoveAurasDueToSpell(buff);
        Advance(w, 50);                                                  // the update forgets the hits it counted
        CHECK(fire() == 0);
        hit(1);
        CHECK(w.HasAura(buff) && w.auras[buff].stacks == 1 && fire() == 1);
    } else if (name == "another_wizards_hits_are_not_shared") {
        Player other; other.guid.raw = 2;
        hit(5);
        CHECK(ElementalBonus(&other, SPELL_SCHOOL_MASK_FIRE) == 0 && !other.HasAura(buff));
    } else {
        std::fprintf(stderr, "no case %s\n", name.c_str());
        return 4;
    }
    std::puts("ok");
    return 0;
}
'''

CASES = [
    "each_enemy_hit_is_one_stack",
    "the_stacks_stop_at_thirty",
    "the_buff_shows_the_number_the_damage_uses",
    "only_fire_damage_gets_it",
    "each_hit_runs_out_on_its_own_clock",
    "a_hit_puts_the_buffs_time_back_to_five_seconds",
    "the_oldest_stack_goes_first_when_they_are_full",
    "a_cancelled_buff_starts_again_from_the_next_hit",
    "another_wizards_hits_are_not_shared",
]


def records_file():
    """Every generated record for the harness's spell store: id, duration ms, stack limit, three (base points, die
    sides) pairs - every field out of the generated row, so a number reads as it does in the server."""
    rows, lengths = generated_rows(), durations()
    lines = []
    for ident, row in sorted(rows.items()):
        cells = [ident, lengths.get(int(row["DurationIndex"]), 0), row["CumulativeAura"]]
        for slot in (1, 2, 3):
            cells += [row["EffectBasePoints_%d" % slot], row["EffectDieSides_%d" % slot]]
        lines.append(" ".join(str(cell) for cell in cells))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    records = SCRATCH / "records.tsv"
    records.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return records


def compile_program(program, label, src=MODULE / "src"):
    """`src` is a module src tree: this checkout's, or the commit before the fix (the data it was generated from is
    in it: dc_spell_values.h and dc_spell_shells.h)."""
    compiler = toolchain()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cpp = SCRATCH / (label + ".cpp")
    cpp.write_text(program, encoding="utf-8")
    binary = SCRATCH / label
    binary = harness_env.build([cpp, src / "combat/dc_spell_numbers.cpp"], flags=["-std=c++20", "-O0"], includes=[STUBS, src / "combat"])
    return binary


def build_stacks(source, label):
    helpers = "\n\n".join(definition(marker, source) for marker in HELPERS)
    mechanic = "\n\n".join(definition(marker, source) for marker in MECHANIC)
    program = (STACKS.replace("@DECLARED@", declared(INTERNAL_H.read_text(encoding="utf-8"))).replace("@HELPERS@", helpers)
               .replace("@MECHANIC@", mechanic).replace("@ELEMENTAL@", definition(ELEMENTAL, source))
               .replace("@SHELLS@", SHELLS_H.as_posix()).replace("@BUFF@", BUFF))
    return compile_program(program, label)


def failing(source, label):
    binary, records = build_stacks(source, label), records_file()
    return [case for case in CASES
            if harness_env.run([str(binary), str(records), case], capture_output=True, text=True).returncode]


def waits_function(source):
    """DamageWaits as the file has it; for the code before the fix, where the test was inline in the loader, the
    same expression wrapped in a function."""
    if WAITS in source:
        return definition(WAITS, source)
    found = re.search(r"bool const delayed = (.*?);\n\s+if \(!delayed", source, re.S)
    assert found, "the loader's delayed test is not where it was"
    return "bool DamageWaits(std::uint32_t id)\n{\n    struct { std::uint32_t id; } ability{id};\n    return %s;\n}" % found[1]


def tree_before_the_fix():
    """The module's src as it was before the fix (None when the commit is not in this clone)."""
    target = SCRATCH / "before"
    if not (target / "mod-diablocraft/src").is_dir():
        target.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "archive", BEFORE_THE_FIX, "mod-diablocraft/src"], cwd=ROOT, capture_output=True)
        if archive.returncode:
            return None
        subprocess.run(["tar", "-x", "-C", str(target)], input=archive.stdout, check=True)
    return target / "mod-diablocraft/src"


def loader_report(source, label, src=MODULE / "src"):
    program = LOADER.replace("@WAITS@", waits_function(source)).replace("@SHELLS@", (src / "combat/dc_spell_shells.h").as_posix())
    binary, records = compile_program(program, label, src), records_file()
    done = harness_env.run([str(binary), str(records)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    waits = {int(m[1]) for m in re.finditer(r"^waits (\d+) 1$", done.stdout, re.M)}
    damage = {int(m[1]): float(m[2]) for m in re.finditer(r"^damage (\d+) (\S+)$", done.stdout, re.M)}
    return waits, damage


class Stacks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = build_stacks(WIZARD_CPP.read_text(encoding="utf-8"), "production")
        cls.records = records_file()


def make_case(case):
    def check(self):
        done = harness_env.run([str(self.binary), str(self.records), case], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, case + ": " + done.stderr.strip())
    return check


for _case in CASES:
    setattr(Stacks, "test_" + _case, make_case(_case))


class Damage(unittest.TestCase):
    """The rune deals Spectral Blade's damage as Fire to every enemy in the cone."""

    @classmethod
    def setUpClass(cls):
        cls.source = "".join(p.read_text(encoding="utf-8") for p in [COMBAT_CPP.parent / "dc_combat_internal.h", *sorted(COMBAT_CPP.parent.glob("dc_combat*.cpp"))])
        cls.flame = rune_id("Spectral Blade", "Flame Blades")
        cls.base = rune_id("Spectral Blade", "")

    def test_the_loader_gives_flame_blades_the_skills_damage(self):
        waits, damage = loader_report(self.source, "loader")
        self.assertNotIn(self.flame, waits, "the loader reads Flame Blades' damage as waiting, so it deals none")
        self.assertEqual(damage[self.flame], 168)
        self.assertEqual(damage[self.flame], damage[self.base], "the rune deals Spectral Blade's own damage")

    def test_only_flame_blades_changed_what_the_loader_does(self):
        tree = tree_before_the_fix()
        if tree is None:
            raise unittest.SkipTest("the parent commit is not in this clone")
        before, _ = loader_report((tree / "combat/dc_combat.cpp").read_text(encoding="utf-8"), "loader_before", tree)
        after, _ = loader_report(self.source, "loader")
        # The records that existed when the loader was last changed: the Monk's block (diablocraft-3mk78, 83650 up) is newer than
        # the parent commit's loader, whose rules were never meant for it.
        before, after = {i for i in before if i < 83650}, {i for i in after if i < 83650}
        self.assertIn(self.flame, before)
        self.assertEqual(before - after, {self.flame}, "the records that wait, before and after")
        self.assertEqual(after - before, set())
        self.assertGreater(len(after), 80, "the summons, armours, fuses and grounds still wait")

    def test_the_record_is_an_instant_fire_cone(self):
        row = generated_rows()[self.flame]
        self.assertEqual(int(row["SchoolMask"]), 4, "Fire")
        self.assertEqual(float(row["Speed"]), 0, "a projectile record skips the cast's own resolve")
        self.assertEqual(int(row["Effect_1"]), 3, "DUMMY: the module deals the damage")
        self.assertEqual(int(row["EffectBasePoints_1"]) + int(row["EffectDieSides_1"]), 168)
        self.assertRegex(SHELLS_SQL.read_text(encoding="utf-8"),
                         r"dc_spell_targeting VALUES \(%d,'cone_enemies','NUMERIC',15\.0," % self.flame)

    def test_the_rune_states_its_five_seconds_as_the_stacks_length(self):
        waits_by_name = re.findall(r'\{%d, "([a-z_]+)"' % self.flame,
                                   (MODULE / "src/combat/dc_spell_values.h").read_text(encoding="utf-8"))
        self.assertIn("bonus_duration_seconds", waits_by_name)
        self.assertNotIn("duration_seconds", waits_by_name)


class Visible(unittest.TestCase):
    """The record the stacks ride on is a buff the client draws, from the generated row."""

    def test_the_buff_record_is_a_visible_stacking_aura_on_the_caster(self):
        rows = generated_rows()
        row, rune = rows[helper_id(BUFF)], rows[rune_id("Spectral Blade", "Flame Blades")]
        self.assertEqual(int(row["Attributes"]) & 0x40, 0, "a passive aura is never sent to the client")
        self.assertEqual(int(row["Attributes"]) & 0x80, 0, "do-not-display keeps it off the aura bar")
        self.assertEqual(row["Name_Lang_enUS"], BUFF)
        self.assertEqual(row["SpellIconID"], rune["SpellIconID"], "the rune's icon")
        self.assertNotEqual(int(row["SpellIconID"]), 0, "a buff with no icon shows as a question mark")
        self.assertEqual((int(row["Effect_1"]), int(row["EffectAura_1"]), int(row["ImplicitTargetA_1"])), (6, 4, 1),
                         "APPLY_AURA, DUMMY, on the caster")
        self.assertEqual(int(row["CumulativeAura"]), 30, "30 stacks: max_bonus_pct over damage_bonus_pct")
        self.assertEqual(durations()[int(row["DurationIndex"])], 5000, "the five seconds of a hit")
        self.assertEqual(int(row["EffectBasePoints_1"]) + int(row["EffectDieSides_1"]), 1, "1% a stack")
        self.assertIn("$s1%", row["AuraDescription_Lang_enUS"], "the sentence states one stack's worth")
        self.assertEqual(int(row["SpellVisualID_1"]), 0, "wearing it plays no spell effect")
        self.assertEqual(int(row["AuraInterruptFlags"]), 0, "nothing the Wizard does cancels it")


class Wiring(unittest.TestCase):
    """Landed, the update hook and the loader are too large to compile alone: their facts are pinned as text."""

    @classmethod
    def setUpClass(cls):
        cls.wizard = WIZARD_CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT_CPP.parent / "dc_combat_internal.h", *sorted(COMBAT_CPP.parent.glob("dc_combat*.cpp"))])

    def test_a_flame_blades_hit_adds_a_stack_and_nothing_else_does(self):
        landed = definition(LANDED, self.wizard)
        self.assertEqual(landed.count("FlameBlade("), 1)
        self.assertRegex(landed, r'if \(periodic\)\s+return;[^{}]*if \(IsRune\(id, "Flame Blades"\)\)\s+SpectralBlade::FlameBlade\(player, id\);',
                         "an enemy hit, not a damage tick")

    def test_a_hit_is_landed_only_when_it_deals_damage(self):
        """So a rune that deals none never reached Landed: the stacks and the damage fail together."""
        self.assertRegex(self.combat, r"if \(hit\.total > 0\)\s*\{\s*GainPerEnemyHit\(player, shell\.spellId\);\s*"
                                      r"Wizard::Landed\(player, target, shell\.spellId, hit, false\);")

    def test_the_stacks_are_synced_every_update(self):
        self.assertIn("SyncFlameBlades(player);", definition(UPDATE, self.wizard))

    def test_the_hits_are_clocks_not_a_sum(self):
        self.assertRegex(INTERNAL_H.read_text(encoding="utf-8"), r"std::vector<uint64> flameBlades;")

    def test_the_loader_asks_the_function(self):
        self.assertRegex(self.combat, r"if \(!DamageWaits\(ability\.id\) && Numbers::Has\(ability\.id, \"damage_pct\"\)\)")

    def test_the_number_reader_is_the_real_one(self):
        """The harness compiles the Wizard's Num; this pins that it is still the one-line forward to Numbers::Num."""
        self.assertRegex(self.wizard, r"double Num\(uint32 id, std::string_view token, std::string_view qualifier\)"
                                      r"\s*\{\s*return Numbers::Num\(id, token, qualifier\);\s*\}")


MUTATIONS = [
    ("the stacks are not capped",
     "if (stacks.size() > most)\n                stacks.erase(stacks.begin());",
     "",
     ["the_stacks_stop_at_thirty", "the_buff_shows_the_number_the_damage_uses"]),
    ("the newest goes when they are full, not the oldest",
     "stacks.erase(stacks.begin());",
     "stacks.pop_back();",
     ["the_oldest_stack_goes_first_when_they_are_full"]),
    ("all the stacks share the newest clock",
     "stacks.push_back(now + uint64(seconds * 1000));",
     "stacks.push_back(now + uint64(seconds * 1000));\n            for (uint64& until : stacks)\n                until = stacks.back();",
     ["each_hit_runs_out_on_its_own_clock", "the_oldest_stack_goes_first_when_they_are_full"]),
    ("the update never drops a stack that ran out",
     "std::erase_if(stacks, [now](uint64 until) { return until <= now; });\n        uint32 const buff",
     "uint32 const buff",
     ["each_hit_runs_out_on_its_own_clock", "the_oldest_stack_goes_first_when_they_are_full"]),
    ("a stack lives to the last millisecond of its second",
     "std::erase_if(stacks, [now](uint64 until) { return until <= now; });\n        uint32 const buff",
     "std::erase_if(stacks, [now](uint64 until) { return until < now; });\n        uint32 const buff",
     ["each_hit_runs_out_on_its_own_clock"]),
    ("a stack lasts a tenth of the time",
     "stacks.push_back(now + uint64(seconds * 1000));",
     "stacks.push_back(now + uint64(seconds * 100));",
     ["each_hit_runs_out_on_its_own_clock", "a_hit_puts_the_buffs_time_back_to_five_seconds",
      "the_oldest_stack_goes_first_when_they_are_full"]),
    ("a cancelled buff keeps its hits",
     "if (!player->HasAura(buff))\n                stacks.clear();",
     "",
     ["a_cancelled_buff_starts_again_from_the_next_hit"]),
    ("the update never tells the aura the stacks left",
     "aura->SetStackAmount(uint8(stacks.size()));",
     "(void) aura;",
     ["each_hit_runs_out_on_its_own_clock", "the_oldest_stack_goes_first_when_they_are_full"]),
    ("every school gets it, not Fire alone",
     "if (school == SPELL_SCHOOL_MASK_FIRE)\n            SpectralBlade::FlameBladesBonus(player, bonus);",
     "if (true)\n            SpectralBlade::FlameBladesBonus(player, bonus);",
     ["only_fire_damage_gets_it"]),
    ("a stack is worth a number typed in the code",
     "aura->GetStackAmount() * Num(row.id, \"damage_bonus_pct\")",
     "aura->GetStackAmount() * 2.0",
     ["each_enemy_hit_is_one_stack", "the_buff_shows_the_number_the_damage_uses"]),
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

    def test_the_loader_reading_the_old_name_is_caught(self):
        """Put the sheet's old token back: the shell loads with no damage again."""
        source = "".join(p.read_text(encoding="utf-8") for p in [COMBAT_CPP.parent / "dc_combat_internal.h", *sorted(COMBAT_CPP.parent.glob("dc_combat*.cpp"))])
        old = 'Numbers::Has(id, "dot_duration_seconds") || Numbers::Has(id, "duration_seconds") ||'
        self.assertEqual(source.count(old), 1)
        mutated = source.replace(old, 'Numbers::Has(id, "dot_duration_seconds") || Numbers::Has(id, "duration_seconds") ||\n'
                                      '                   Numbers::Has(id, "bonus_duration_seconds") ||')
        waits, _ = loader_report(mutated, "loader_mutant")
        self.assertIn(rune_id("Spectral Blade", "Flame Blades"), waits)


class Today(unittest.TestCase):
    """The loader on the code before the fix: Flame Blades waits, so it deals nothing."""

    def test_the_code_before_the_fix_loads_flame_blades_with_no_damage(self):
        tree = tree_before_the_fix()
        if tree is None:
            raise unittest.SkipTest("the parent commit is not in this clone")
        waits, _ = loader_report((tree / "combat/dc_combat.cpp").read_text(encoding="utf-8"), "loader_before", tree)
        self.assertIn(rune_id("Spectral Blade", "Flame Blades"), waits)
        self.assertNotIn(rune_id("Spectral Blade", ""), waits, "the skill itself deals its damage")
        self.assertNotIn(rune_id("Spectral Blade", "Ice Blades"), waits, "so do the runes that state no duration")


if __name__ == "__main__":
    unittest.main()
