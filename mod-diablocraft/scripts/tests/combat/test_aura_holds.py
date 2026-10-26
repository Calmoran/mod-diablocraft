"""Nightmarish fear, the hazard freeze and the Jailer's root are real auras (diablocraft-aura-fixes, row 7).

    python3 mod-diablocraft/scripts/tests/combat/test_aura_holds.py

They were Unit::SetControlled calls with no aura (the Jailer's root also added a stock aura beside it): invisible,
unrefused by immunity (Unit::SetControlled checks none; Unit::AddAura refuses an immune target), and unseen by
Juggernaut. Ruling q-1003-11: stock WoW records for now. Each hold is now ApplyHold: a stock donor aura cast by the
elite, the tuned length written on its duration, nothing to time out, SetControlled gone.

The module's own function is cut out of the elite affix files and compiled against doubles:
  real      ApplyHold;
  data      the three donor records, read out of the client's Spell.dbc: each is one instant APPLY_AURA effect of the
            expected type (fear 7, stun 12, root 26) with no aura-interrupt flag, so damage taken does not end it;
  double    AddAura's answer (an immune target is refused, by aura type as the core's immunity list holds it, which is
            what Ignore Pain and Nerves of Steel carry once their records do, row 5; a target immune to the spell id,
            Ice Climbers' freeze, gets an aura back that was never applied to it, as the core's AddAura does:
            diablocraft-c062z), the player's auras.
Juggernaut shortens a control by reading the new aura's effect types; the donors' effect types are checked against
the types dc_barbarian_passives.cpp maps. MutationsAreCaught puts one defect back at a time.
What this does not run: the real AddAura and immunity list, the client's debuff tray, the Juggernaut update.
"""
import atexit
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
from test_skill_swing_recovery import definition
from split_sources import affixes_text

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
PASSIVES = MODULE / "src/classes/barbarian/dc_barbarian_passives.cpp"
CLIENT_SPELL = ROOT / "client-patch/dbc/Spell.dbc"
# Its own folder per run: parallel jobs, and other worktrees (they share _agent-scratch), never share a binary path.
SCRATCH_PARENT = ROOT / "azerothcore-wotlk/build/_agent-scratch/aura-fixes"
SCRATCH_PARENT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(tempfile.mkdtemp(prefix="aura-holds-", dir=SCRATCH_PARENT))
atexit.register(shutil.rmtree, SCRATCH, ignore_errors=True)

# donor id -> (aura type, what the hold is)
DONORS = {"FEAR_HOLD": (7, "fear"), "FREEZE_HOLD": (12, "stun"), "JAILER_DEBUFF": (26, "root")}


def constants(source):
    return {name: int(number) for name, number in
            re.findall(r"constexpr std::uint32_t (FEAR_HOLD|FREEZE_HOLD|JAILER_DEBUFF) = (\d+);", source)}


def dbc_record(spell):
    data = CLIENT_SPELL.read_bytes()
    _, count, fields, size, _ = struct.unpack_from("<4sIIII", data)
    for index in range(count):
        record = struct.unpack_from("<%dI" % fields, data, 20 + index * size)
        if record[0] == spell:
            return record
    raise AssertionError("spell %d is not in %s" % (spell, CLIENT_SPELL))


HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>
#include <string>
using uint32 = std::uint32_t; using uint64 = std::uint64_t; using int32 = std::int32_t;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); std::exit(3); } } while (0)
namespace Std { namespace Rifts {} }
struct ObjectGuid { uint64 raw = 0; bool operator<(ObjectGuid o) const { return raw < o.raw; } };
struct Aura {
    int32 maxDuration = 20000, duration = 20000;               // the donor record's own length, as the core gives it
    bool applied = true;                                       // the target map refused it (an IMMUNITY_ID immunity)
    void SetMaxDuration(int32 d) { maxDuration = d; } void SetDuration(int32 d) { duration = d; }
    Aura const* GetApplicationOfTarget(ObjectGuid) const { return applied ? this : nullptr; }
};
static std::map<uint32, uint32> auraTypeOf = {{@FEAR@, 7}, {@FREEZE@, 12}, {@JAILER@, 26}};   // from the client's Spell.dbc
struct Player;
struct Unit {
    ObjectGuid guid; ObjectGuid GetGUID() const { return guid; }
    std::map<std::pair<uint32, uint64>, Aura> auras;           // (spell, caster) -> aura
    std::set<uint32> immuneToAuraTypes;                        // m_spellImmune[IMMUNITY_STATE], what 147/96 puts there
    std::set<uint32> immuneToIds;                              // m_spellImmune[IMMUNITY_ID], Ice Climbers' freeze
    int controlledCalls = 0;                                   // SetControlled: the call the old code made
    // Unit::AddAura(spellId, target): refused if the target is immune; the aura is cast by this unit.
    Aura* AddAura(uint32 spell, Unit* target) {
        if (target->immuneToAuraTypes.count(auraTypeOf.at(spell))) return nullptr;
        Aura& aura = target->auras[{spell, guid.raw}];          // owned by the target
        aura.applied = !target->immuneToIds.count(spell);       // AddAura's effect check skips IMMUNITY_ID; the target map's does not
        return &aura;
    }
    void RemoveOwnedAura(Aura* aura) {
        for (auto it = auras.begin(); it != auras.end(); ++it) if (&it->second == aura) { auras.erase(it); return; }
        CHECK(false);                                           // the core aborts on an aura it does not own
    }
    void RemoveAurasDueToSpell(uint32 spell, ObjectGuid caster) {
        auras.erase({spell, caster.raw}); }
    void RemoveAurasDueToSpell(uint32 spell) {
        for (auto it = auras.begin(); it != auras.end();) it = it->first.first == spell ? auras.erase(it) : std::next(it); }
};
struct Player : Unit {};

@FUNCTION@

int main(int argc, char** argv) {
    std::string name = argc > 1 ? argv[1] : "";
    Unit elite; elite.guid.raw = 5; Player p; p.guid.raw = 9;
    uint32 const donors[] = {@FEAR@, @FREEZE@, @JAILER@};
    if (name == "each_hold_is_an_aura_with_the_tuned_length") {
        unsigned ms = 1500;
        for (uint32 donor : donors) {
            Player q; q.guid.raw = 9;
            CHECK(ApplyHold(&elite, &q, donor, ms));
            auto it = q.auras.find({donor, elite.guid.raw});
            CHECK(it != q.auras.end());                                    // on the player, cast by the elite
            CHECK(it->second.duration == 1500 && it->second.maxDuration == 1500);
        }
    } else if (name == "an_immune_player_is_not_held") {
        // Ignore Pain / Nerves of Steel: the control immunity by aura type (stun, root, fear, confuse, decrease speed).
        p.immuneToAuraTypes = {12, 26, 7, 5, 33};
        for (uint32 donor : donors) {
            CHECK(!ApplyHold(&elite, &p, donor, 1500));
            CHECK(p.auras.empty());
        }
    } else if (name == "a_player_immune_to_one_control_is_held_by_the_others") {
        p.immuneToAuraTypes = {7};                                         // fear only
        CHECK(!ApplyHold(&elite, &p, @FEAR@, 1500));
        CHECK(ApplyHold(&elite, &p, @FREEZE@, 1500) && ApplyHold(&elite, &p, @JAILER@, 1500));
    } else if (name == "a_hold_refused_by_id_is_not_held_and_not_left_behind") {
        // c062z: Ice Climbers refuses the freeze by id; the core's AddAura still returns the unapplied aura.
        p.immuneToIds = {@FREEZE@};
        CHECK(!ApplyHold(&elite, &p, @FREEZE@, 1500));                     // so the crystal does not interrupt
        CHECK(p.auras.empty());                                            // nothing left to land on a later update
        CHECK(ApplyHold(&elite, &p, @FEAR@, 1500) && ApplyHold(&elite, &p, @JAILER@, 1500));
        CHECK(p.auras.size() == 2);
    } else if (name == "a_second_hold_from_the_same_caster_runs_the_new_length_from_now") {
        CHECK(ApplyHold(&elite, &p, @FEAR@, 4000));
        p.auras[{@FEAR@, elite.guid.raw}].duration = 700;                  // most of it has run
        CHECK(ApplyHold(&elite, &p, @FEAR@, 2500));
        auto const& a = p.auras.at({@FEAR@, elite.guid.raw});
        CHECK(p.auras.size() == 1 && a.duration == 2500 && a.maxDuration == 2500);
    } else if (name == "two_elites_hold_separately") {
        Unit other; other.guid.raw = 6;
        CHECK(ApplyHold(&elite, &p, @FEAR@, 2000) && ApplyHold(&other, &p, @FEAR@, 3000));
        CHECK(p.auras.size() == 2);
    } else if (name == "no_source_player_donor_or_length_holds_nothing") {
        CHECK(!ApplyHold(nullptr, &p, @FEAR@, 1000) && !ApplyHold(&elite, nullptr, @FEAR@, 1000));
        CHECK(!ApplyHold(&elite, &p, 0, 1000) && !ApplyHold(&elite, &p, @FEAR@, 0));
        CHECK(p.auras.empty());
    } else {
        std::fprintf(stderr, "no case %s\n", name.c_str()); return 4;
    }
    std::puts("ok");
    return 0;
}
'''

CASES = ["each_hold_is_an_aura_with_the_tuned_length", "an_immune_player_is_not_held",
         "a_player_immune_to_one_control_is_held_by_the_others", "a_hold_refused_by_id_is_not_held_and_not_left_behind",
         "a_second_hold_from_the_same_caster_runs_the_new_length_from_now", "two_elites_hold_separately",
         "no_source_player_donor_or_length_holds_nothing"]

SIGNATURE = "bool ApplyHold(Unit* source, Player* player, std::uint32_t donor, std::uint32_t ms)"


def build(source, label):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler on this host")
    ids = constants(source)
    function = definition(SIGNATURE, source).replace("std::uint32_t", "uint32").replace("std::int32_t", "int32")
    text = (HARNESS.replace("@FUNCTION@", function).replace("@FEAR@", str(ids["FEAR_HOLD"]))
            .replace("@FREEZE@", str(ids["FREEZE_HOLD"])).replace("@JAILER@", str(ids["JAILER_DEBUFF"])))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cpp = SCRATCH / (label + ".cpp")
    cpp.write_text(text, encoding="utf-8")
    binary = SCRATCH / label
    binary = harness_env.build([cpp], flags=["-std=c++17", "-O0"])
    return binary


def failing(source, label):
    binary = build(source, label)
    return [case for case in CASES if harness_env.run([str(binary), case], capture_output=True, text=True).returncode]


class Holds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = affixes_text()
        cls.binary = build(cls.source, "production")


def make_case(case):
    def check(self):
        done = harness_env.run([str(self.binary), case], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, case + ": " + done.stderr.strip())
    return check


for _case in CASES:
    setattr(Holds, "test_" + _case, make_case(_case))


class Donors(unittest.TestCase):
    """The stock records the holds borrow, read from the client's own Spell.dbc."""

    @classmethod
    def setUpClass(cls):
        cls.source = affixes_text()
        cls.ids = constants(cls.source)

    def test_the_three_donors_are_named(self):
        self.assertEqual(set(self.ids), set(DONORS))

    def test_each_donor_is_one_instant_aura_of_the_right_type_that_damage_does_not_break(self):
        for name, (aura, what) in DONORS.items():
            with self.subTest(name):
                record = dbc_record(self.ids[name])
                effects = [record[71 + slot] for slot in range(3)]
                auras = [record[95 + slot] for slot in range(3)]
                self.assertEqual(effects, [6, 0, 0], "%s is not one APPLY_AURA effect" % what)   # SPELL_EFFECT_APPLY_AURA
                self.assertEqual(auras[0], aura, "%s donor %d" % (what, self.ids[name]))
                self.assertEqual(record[32] & 0x2, 0, "the %s breaks on damage taken (AuraInterruptFlags)" % what)

    def test_the_spell_mechanic_is_what_the_hold_is(self):
        self.assertEqual(dbc_record(self.ids["FEAR_HOLD"])[3], 5)      # MECHANIC_FEAR
        self.assertEqual(dbc_record(self.ids["FREEZE_HOLD"])[3], 12)   # MECHANIC_STUN

    def test_juggernaut_maps_each_donors_aura_type_to_a_control(self):
        passives = PASSIVES.read_text(encoding="utf-8")
        for aura_type, name in ((7, "SPELL_AURA_MOD_FEAR"), (12, "SPELL_AURA_MOD_STUN"), (26, "SPELL_AURA_MOD_ROOT")):
            self.assertRegex(passives, r"case %s:\s*mask \|= 1u << MECHANIC_" % name)


class Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = affixes_text()

    def test_no_hold_is_a_state_without_an_aura_any_more(self):
        self.assertNotIn("SetControlled", self.source)
        for name in ("QueueControl", "ReleaseHold", "DrainTimed"):
            self.assertNotIn(name, self.source)
        internal = (MODULE / "src/rifts/dc_rifts_internal.h").read_text(encoding="utf-8")
        self.assertNotIn("struct Timed", internal)

    def test_the_three_call_sites_apply_a_hold(self):
        self.assertIn("ApplyHold(elite, victim, JAILER_DEBUFF, n.jailerRootMs);", self.source)
        self.assertIn("ApplyHold(elite, player, FEAR_HOLD, n.nightmarishMs);", self.source)
        self.assertIn("if (ApplyHold(source, player, FREEZE_HOLD, h.freezeMs))", self.source)

    def test_a_map_change_takes_the_holds_off(self):
        body = definition("void ReleasePlayerControls(Player* player)", self.source)
        self.assertIn("for (std::uint32_t hold : {FEAR_HOLD, FREEZE_HOLD, JAILER_DEBUFF})", body)
        self.assertIn("player->RemoveAurasDueToSpell(hold);", body)


MUTATIONS = [
    ("the hold does not carry the tuned length",
     "    hold->SetMaxDuration(static_cast<std::int32_t>(ms));\n    hold->SetDuration(static_cast<std::int32_t>(ms));\n",
     "",
     ["each_hold_is_an_aura_with_the_tuned_length", "a_second_hold_from_the_same_caster_runs_the_new_length_from_now"]),
    ("the hold ignores a refusal and reports it landed",
     "    if (!hold)\n        return false;",
     "    if (!hold)\n        return true;",
     ["an_immune_player_is_not_held", "a_player_immune_to_one_control_is_held_by_the_others"]),
    ("a hold refused by id reports it landed (c062z)",
     "    if (!hold->GetApplicationOfTarget(player->GetGUID()))\n",
     "    if (false)\n",
     ["a_hold_refused_by_id_is_not_held_and_not_left_behind"]),
    ("a hold refused by id is left on the player (c062z)",
     "        player->RemoveOwnedAura(hold);\n",
     "",
     ["a_hold_refused_by_id_is_not_held_and_not_left_behind"]),
    ("a refresh stacks beside the old hold instead of replacing it",
     "    player->RemoveAurasDueToSpell(donor, source->GetGUID());\n",
     "",
     []),   # the core replaces an aura of the same caster itself; the harness's map does too (same key)
]


class MutationsAreCaught(unittest.TestCase):
    def test_each_defect_fails_the_cases_that_name_it(self):
        source = affixes_text()
        for index, (label, old, new, expected) in enumerate(MUTATIONS):
            if not expected:
                continue
            with self.subTest(label):
                self.assertEqual(source.count(old), 1, "mutation %r does not match once" % label)
                caught = failing(source.replace(old, new), "mutant%d" % index)
                self.assertTrue(set(expected) <= set(caught), "%s: expected %s to fail, failed %s" % (label, expected, caught))


class Today(unittest.TestCase):
    """Against the code before the rule there is no ApplyHold: the holds were SetControlled and a timer."""

    def test_the_old_code_had_no_aura_hold(self):
        old = subprocess.run(["git", "show", "9cf87dc5:mod-diablocraft/src/rifts/dc_rift_elites.cpp"], cwd=ROOT,
                             capture_output=True, text=True)
        if old.returncode:
            raise unittest.SkipTest("the parent commit is not in this clone")
        self.assertNotIn("ApplyHold", old.stdout)
        self.assertIn("player->SetControlled(true, UNIT_STATE_FLEEING, elite, true);", old.stdout)
        self.assertIn("player->SetControlled(true, UNIT_STATE_STUNNED);", old.stdout)
        self.assertIn("victim->SetControlled(true, UNIT_STATE_ROOT);", old.stdout)


if __name__ == "__main__":
    unittest.main()
