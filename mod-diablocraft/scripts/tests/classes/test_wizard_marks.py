"""The Wizard's frozen and chilled marks follow the aura (diablocraft-aura-fixes, aura review row 8).

    python3 mod-diablocraft/scripts/tests/classes/test_wizard_marks.py

The Wizard keeps "frozen", "chilled" and Bone Chill as per-caster timestamps (Marks) beside the stock "Wizard -
Frozen" and "Wizard - Slowed" auras. A Juggernaut elite is immune to freeze and snare, so Unit::AddAura refuses
both auras - yet Chill wrote the chilled mark before it tried the slow, and Frost Nova - Bone Chill wrote its mark
whether or not the freeze landed, so Cold Blooded, Bone Chill and the chill procs added their damage-taken bonus to
a target that was neither frozen nor chilled. The rule now: no aura, no mark, and a status is read from the unit as
well as the mark.

The module's own functions are cut out of the Wizard's files (src/classes/wizard/) and compiled against doubles:
  real      Freeze, Slow, Chill, FrozenMark, Frozen, Chilled, and Chill's default argument as dc_wizard_internal.h
            declares it;
  double    the target (the auras on it, and what it is immune to, as AddAura answers), the clock, the Wizard's
            state (the marks map), Apply (AddAura's answer: refused for an immune target, else the aura is put on).
The Bone Chill write and the two damage reads are in functions too large to compile on their own, so they are
pinned as text. MutationsAreCaught puts one old behaviour back at a time.
What this does not run: the real AddAura, the immunity a Juggernaut elite really has, the damage bonus itself.
"""
import atexit
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env
from test_skill_swing_recovery import definition

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
WIZARD_CPP = wizard_source.CPP
INTERNAL_H = wizard_source.FOLDER / "dc_wizard_internal.h"
# Chill's default argument: on the declaration in dc_wizard_internal.h now, on the definition in the one-file code before.
CHILL_DECLARED = "void Chill(Player* player, Unit* target, double seconds, double pct = -1);"
# Its own folder per run: parallel jobs, and other worktrees (they share _agent-scratch), never share a binary path.
SCRATCH_PARENT = ROOT / "azerothcore-wotlk/build/_agent-scratch/aura-fixes"
SCRATCH_PARENT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(tempfile.mkdtemp(prefix="wizard-marks-", dir=SCRATCH_PARENT))
atexit.register(shutil.rmtree, SCRATCH, ignore_errors=True)

# (name, signature tail). The return type is bool now and was void for Freeze and Slow; both are accepted so the
# same harness can show the old code red. Chill's tail stops before its default argument, which the definition had in
# the one-file code and the declaration has now.
FUNCTIONS = [("Freeze", "Freeze(Player* player, Unit* target, double seconds)"),
             ("Slow", "Slow(Player* player, Unit* target, double pct, double seconds)"),
             ("Chill", "Chill(Player* player, Unit* target, double seconds, double pct"),
             ("FrozenMark", "bool FrozenMark(Player* player, Unit* target)"),
             ("Frozen", "bool Frozen(Player* player, Unit* target)"),
             ("Chilled", "bool Chilled(Player* player, Unit* target)")]


def cut(source, signature, optional=False):
    pattern = re.compile(r"(?:bool|void) " + re.escape(signature) if not signature.startswith("bool ") else re.escape(signature))
    found = pattern.search(source)
    if not found:
        if optional:
            return None
        raise AssertionError("no %s" % signature)
    return definition(found.group(0), source)


HARNESS = r'''
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <unordered_map>
#include <utility>
using uint32 = std::uint32_t; using uint64 = std::uint64_t; using int32 = std::int32_t;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); std::exit(3); } } while (0)

static uint64 now = 100000;
uint64 Now() { return now; }
enum { EFFECT_0 = 0 };
struct ObjectGuid { uint64 raw = 0; uint64 GetRawValue() const { return raw; } bool operator==(ObjectGuid o) const { return raw == o.raw; } };
struct AuraEffect { int32 amount = 0; void ChangeAmount(int32 a) { amount = a; } };
struct Aura { AuraEffect effect; AuraEffect* GetEffect(int) { return &effect; } };
struct Unit {
    ObjectGuid guid;
    std::set<std::pair<uint32, uint64>> auras;                                  // (spell, caster guid)
    std::set<std::string> immune;                                                // helpers AddAura refuses (a Juggernaut elite)
    ObjectGuid GetGUID() const { return guid; }
    bool HasAura(uint32 id, ObjectGuid caster) const { return auras.count({id, caster.raw}) != 0; }
    bool HasAura(uint32 id) const { for (auto const& a : auras) if (a.first == id) return true; return false; }   // any caster
};
struct Player : Unit {};
namespace Shells { uint32 HelperFor(char const* name) {
    std::string n = name; return n == "Wizard - Frozen" ? 1 : n == "Wizard - Slowed" ? 2 : 0; } }
double Tune(char const*) { return 60.0; }                                       // wizard_chill_slow_pct, sourced
namespace GemPowers { double ChillBonus(Player const*) { return 0.0; } }       // Iceblink is not worn here

// Apply: the stock path - AddAura refuses an immune target, otherwise the aura is on it.
static Aura applied;
Aura* Apply(Player* player, Unit* target, char const* helper, double, Unit* = nullptr) {
    if (target->immune.count(helper)) return nullptr;
    target->auras.insert({Shells::HelperFor(helper), player->guid.raw});
    return &applied;
}

struct Marks { uint64 frozen = 0, chilled = 0, boneChill = 0; };
struct State { std::unordered_map<uint64, Marks> marks; };
std::recursive_mutex mutex;
static std::map<Player*, State> states;
State& StateOf(Player* p) { return states[p]; }

@FUNCTIONS@

static void Setup(Player& w, Unit& t) { states.clear(); now = 100000; w.guid.raw = 1; t.guid.raw = 77; applied = Aura{}; }
static Marks const* MarkOf(Player& w, Unit& t) { auto f = StateOf(&w).marks.find(t.guid.raw); return f == StateOf(&w).marks.end() ? nullptr : &f->second; }

int main(int argc, char** argv) {
    std::string name = argc > 1 ? argv[1] : "";
    Player w; Unit t; Setup(w, t);
    if (name == "a_freeze_that_lands_marks_the_target_frozen") {
        Freeze(&w, &t, 2.0);
        CHECK(Frozen(&w, &t) && FrozenMark(&w, &t) && t.HasAura(1, w.guid));
    } else if (name == "a_frozen_immune_target_gets_no_mark") {
        t.immune.insert("Wizard - Frozen");                                    // a Juggernaut elite
        Freeze(&w, &t, 2.0);
        CHECK(!Frozen(&w, &t) && !FrozenMark(&w, &t) && MarkOf(w, t) == nullptr);
    } else if (name == "a_chill_that_lands_marks_the_target_chilled") {
        Chill(&w, &t, 3.0);
        CHECK(Chilled(&w, &t) && t.HasAura(2, w.guid) && applied.effect.amount == -60);
    } else if (name == "a_snare_immune_target_is_not_chilled") {
        t.immune.insert("Wizard - Slowed");
        Chill(&w, &t, 3.0);
        CHECK(!Chilled(&w, &t) && MarkOf(w, t) == nullptr);                   // the mark used to be written first
    } else if (name == "a_chill_with_its_own_slow_follows_the_slow_aura_too") {
        t.immune.insert("Wizard - Slowed");
        Chill(&w, &t, 3.0, 40.0);
        CHECK(!Chilled(&w, &t) && MarkOf(w, t) == nullptr);
    } else if (name == "a_status_is_read_from_the_unit_as_well_as_the_mark") {
        Freeze(&w, &t, 2.0); Chill(&w, &t, 2.0);
        CHECK(Frozen(&w, &t) && Chilled(&w, &t));
        t.auras.clear();                                                       // dispelled, or removed some other way
        CHECK(!Frozen(&w, &t) && !Chilled(&w, &t));
        CHECK(FrozenMark(&w, &t));                                             // it did die frozen: the kill hook asks the mark
    } else if (name == "another_casters_aura_is_not_this_wizards_status") {
        Freeze(&w, &t, 2.0);
        t.auras.clear(); t.auras.insert({1, 999});                             // somebody else's freeze
        CHECK(!Frozen(&w, &t));
    } else if (name == "a_mark_runs_out") {
        Freeze(&w, &t, 2.0); Chill(&w, &t, 2.0);
        now += 2001;
        CHECK(!Frozen(&w, &t) && !Chilled(&w, &t) && !FrozenMark(&w, &t));
    } else {
        std::fprintf(stderr, "no case %s\n", name.c_str()); return 4;
    }
    std::puts("ok");
    return 0;
}
'''

CASES = [
    "a_freeze_that_lands_marks_the_target_frozen",
    "a_frozen_immune_target_gets_no_mark",
    "a_chill_that_lands_marks_the_target_chilled",
    "a_snare_immune_target_is_not_chilled",
    "a_chill_with_its_own_slow_follows_the_slow_aura_too",
    "a_status_is_read_from_the_unit_as_well_as_the_mark",
    "another_casters_aura_is_not_this_wizards_status",
    "a_mark_runs_out",
]


def build(source, label):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler on this host")
    body = "\n\n".join(cut(source, signature, optional=name == "FrozenMark") or
                       "bool FrozenMark(Player* player, Unit* target)\n{\n    std::lock_guard<std::recursive_mutex> guard(mutex);\n"
                       "    auto found = StateOf(player).marks.find(target->GetGUID().GetRawValue());\n"
                       "    return found != StateOf(player).marks.end() && found->second.frozen > Now();\n}"
                       for name, signature in FUNCTIONS)
    if "double pct = -1)" not in body:
        header = INTERNAL_H.read_text(encoding="utf-8")
        assert header.count(CHILL_DECLARED) == 1, "dc_wizard_internal.h does not declare Chill's default once"
        body = CHILL_DECLARED + "\n\n" + body
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cpp = SCRATCH / (label + ".cpp")
    cpp.write_text(HARNESS.replace("@FUNCTIONS@", body), encoding="utf-8")
    binary = SCRATCH / label
    binary = harness_env.build([cpp], flags=["-std=c++17", "-O0"])
    return binary


def failing(source, label):
    binary = build(source, label)
    return [case for case in CASES if harness_env.run([str(binary), case], capture_output=True, text=True).returncode]


class Rule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WIZARD_CPP.read_text(encoding="utf-8")
        cls.binary = build(cls.source, "production")


def make_case(case):
    def check(self):
        done = harness_env.run([str(self.binary), case], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, case + ": " + done.stderr.strip())
    return check


for _case in CASES:
    setattr(Rule, "test_" + _case, make_case(_case))


class Wiring(unittest.TestCase):
    """The reads and the Bone Chill write live in functions too large to compile alone: pinned as text."""

    @classmethod
    def setUpClass(cls):
        cls.source = WIZARD_CPP.read_text(encoding="utf-8")

    def test_bone_chill_is_marked_only_when_the_freeze_landed(self):
        self.assertIn('if (Freeze(player, target, seconds) && IsRune(id, "Bone Chill"))', self.source)

    def test_the_damage_reads_ask_the_unit(self):
        self.assertIn("if (marks.boneChill > now && Frozen(player, target))", self.source)
        self.assertIn('Has(player, "Cold Blooded") && (Frozen(player, target) || Chilled(player, target)))', self.source)

    def test_the_kill_hook_still_asks_the_mark_alone(self):
        self.assertIn("frozen = FrozenMark(player, killed);", self.source)


MUTATIONS = [
    ("Freeze writes its mark before it knows the freeze landed",
     'if (!Apply(player, target, "Wizard - Frozen", seconds))\n            return false;\n        std::lock_guard<std::recursive_mutex> guard(mutex);',
     'Apply(player, target, "Wizard - Frozen", seconds);\n        std::lock_guard<std::recursive_mutex> guard(mutex);',
     ["a_frozen_immune_target_gets_no_mark"]),
    ("Chill writes the chilled mark before it tries the slow, as it did",
     "if (!Slow(player, target, slow > 0 ? slow + GemPowers::ChillBonus(player) : slow, seconds))\n            return;\n        std::lock_guard<std::recursive_mutex> guard(mutex);",
     "Slow(player, target, slow > 0 ? slow + GemPowers::ChillBonus(player) : slow, seconds);\n        std::lock_guard<std::recursive_mutex> guard(mutex);",
     ["a_snare_immune_target_is_not_chilled", "a_chill_with_its_own_slow_follows_the_slow_aura_too"]),
    ("Slow says it landed when it did not",
     "if (!aura)\n            return false;",
     "if (!aura)\n            return true;",
     ["a_snare_immune_target_is_not_chilled"]),
    ("Frozen reads the mark and not the unit",
     'return FrozenMark(player, target) && target->HasAura(Shells::HelperFor("Wizard - Frozen"), player->GetGUID());',
     "return FrozenMark(player, target);",
     ["a_status_is_read_from_the_unit_as_well_as_the_mark"]),
    ("Chilled reads the mark and not the unit",
     'found->second.chilled > Now() &&\n               target->HasAura(Shells::HelperFor("Wizard - Slowed"), player->GetGUID());',
     "found->second.chilled > Now();",
     ["a_status_is_read_from_the_unit_as_well_as_the_mark"]),
    ("Frozen takes anyone's aura",
     'target->HasAura(Shells::HelperFor("Wizard - Frozen"), player->GetGUID())',
     'target->HasAura(Shells::HelperFor("Wizard - Frozen"))',
     ["another_casters_aura_is_not_this_wizards_status"]),
]


class MutationsAreCaught(unittest.TestCase):
    def test_each_defect_fails_the_cases_that_name_it(self):
        source = WIZARD_CPP.read_text(encoding="utf-8")
        for index, (label, old, new, expected) in enumerate(MUTATIONS):
            with self.subTest(label):
                self.assertEqual(source.count(old), 1, "mutation %r does not match once" % label)
                caught = failing(source.replace(old, new), "mutant%d" % index)
                self.assertTrue(set(expected) <= set(caught), "%s: expected %s to fail, failed %s" % (label, expected, caught))


class Today(unittest.TestCase):
    """The same cases against the code before the rule (the parent commit's dc_wizard.cpp) fail."""

    def test_the_old_marks_fail_the_cases(self):
        old = subprocess.run(["git", "show", "9cf87dc5:mod-diablocraft/src/classes/wizard/dc_wizard.cpp"], cwd=ROOT,
                             capture_output=True, text=True)
        if old.returncode:
            raise unittest.SkipTest("the parent commit is not in this clone")
        caught = failing(old.stdout, "today")
        # Freeze already refused to mark on a failed freeze; the bugs were Chill's order, the Bone Chill write (pinned
        # as text) and the reads.
        for case in ("a_snare_immune_target_is_not_chilled", "a_status_is_read_from_the_unit_as_well_as_the_mark"):
            self.assertIn(case, caught)


if __name__ == "__main__":
    unittest.main()
