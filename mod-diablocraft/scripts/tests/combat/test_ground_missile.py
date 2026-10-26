"""Ground-point missiles resolve where they land (diablocraft-w8xlw): a ground-point ability record with a projectile Speed used to deal nothing.

The bug, traced from the code and the generated records rather than from a cast (no agent can cast on dev):
  * `dc_ability_targets` (src/combat/dc_combat_resolve.cpp) resolves a cast in `Finish` when the record has no Speed (ResolveCast), and for a record with
    a Speed (and not channelled) leaves it to `Impact`, the script's AfterHit, which hits one unit a time.
  * The core calls AfterHit only from Spell::DoAllEffectOnTarget, for a unit (or object) its effects aimed at (Spell.cpp:3116, :3480, :3498); a record whose one
    effect is a dummy at a ground point (TARGET_DEST_DEST) has no unit target, and `_handle_immediate_phase` runs only the effect handlers, never AfterHit.
    So such a record never resolved: no damage, no resource, no ground effect. Which records, read from the generated spell_shells.sql, the
    core's own target table (SpellInfo.cpp) and the targeting sheet: fourteen when the bead was found (listed below), and the Demon Hunter's later records of the same two shapes (a ground point, or the caster alone).
What this proves, and how:
  * **The trace.** For every record the engine's script is attached to, the old rule (a Speed means the impact resolves it) and the new rule
    (GroundMissile::PathOf) give the same path except for exactly those fourteen records, which were "never" and are now "arrival"; a record with no Speed
    resolves at the cast and a missile aimed at a unit resolves on impact, both as before.
  * **The rule.** tests/ground_missile/harness.cpp compiles the real dc_ground_missile_math.h and is driven with every record's own Speed, channelling and aim; the
    flight time is distance over Speed. Mutations of the header must each make it fail.
  * **The engine.** The text of Finish: it asks PathOf with the record's Speed, channelling and whether any effect aims at a unit other than the caster; the
    arrival schedules the same ResolveCast with the launch's shell, point and origin on the caster's own queue after the flight, unless the caster died or left the
    map, instance or phase; the impact path is untouched. Each rule is mutated in a copy of the text and the guard must fail.
What it does not prove: a cast on a running server, and that the client draws the missile (the records keep their Speed).

    python mod-diablocraft/scripts/tests/combat/test_ground_missile.py
"""

import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
HEADER = MODULE / "src/combat/dc_ground_missile_math.h"
HARNESS = MODULE / "tests/ground_missile/harness.cpp"
RESOLVE = MODULE / "src/combat/dc_combat_resolve.cpp"
CORE_TARGETS = REPO / "azerothcore-wotlk/src/server/game/Spells/SpellInfo.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
TARGET_UNIT_CASTER = 1
SPELL_ATTR1_CHANNELED = 0x4 | 0x40   # SPELL_ATTR1_CHANNELED_1 | SPELL_ATTR1_CHANNELED_2

# The records that never resolved, by what each one is: a missile (a Speed) with one dummy effect that aims at no unit but the caster. Two kinds:
# aimed at a ground point (TARGET_DEST_DEST, 87), and centred on the caster (TARGET_UNIT_CASTER, 1: the unit it would hit is the caster, which the
# impact refuses). The bead names the first fourteen; the Demon Hunter's records merged later in the same shapes. Strafe left the list when it became a real channel (combat_0103), which resolves at the cast.
TARGET_DEST_DEST = 87
NEVER = {
    "Bone Spikes": 85100, "Bone Spikes - Sudden Impact": 85121, "Bone Spikes - Path of Bones": 85122, "Bone Spikes - Blood Spikes": 85125,
    "Arcane Orb - Spark": 83152, "Arcane Orb - Scorch": 83154, "Arcane Orb - Frozen Orb": 83155,
    "Meteor - Thunder Crash": 83205,
    "Wave of Light - Wall of Light": 83702, "Wave of Light - Pillar of the Ancients": 83704, "Wave of Light - Shattering Light": 83706,
    "Fist of the Heavens": 85408, "Fist of the Heavens - Reverberation": 85465, "Fist of the Heavens - Fissure": 85466,
}
DEMON_HUNTER_GROUND = {
    "Cluster Arrow": 85722, "Cluster Arrow - Loaded for Bear": 85834, "Cluster Arrow - Shooting Stars": 85835, "Cluster Arrow - Cluster Bombs": 85836,
    "Rain of Vengeance": 85723, "Rain of Vengeance - Dark Cloud": 85840, "Spike Trap - Impaling Spines": 85809,
}
DEMON_HUNTER_SELF = {
    "Fan of Knives": 85716, "Fan of Knives - Assassin's Knives": 85805,
    "Chakram - Shuriken Cloud": 85763,   # cast on the Demon Hunter, not thrown (vawmy.14)
}
GROUND = {**NEVER, **DEMON_HUNTER_GROUND}   # aimed at a ground point
EVERY_NEVER = {**GROUND, **DEMON_HUNTER_SELF}   # every record that never resolved

def split_values(text):
    """The comma-separated values of one SQL row, a quoted string (with '' inside) as one value."""
    values, current, quoted, i = [], "", False, 0
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == "'" and text[i + 1:i + 2] == "'":
                current += "''"
                i += 1
            elif ch == "'":
                quoted = False
                current += ch
            else:
                current += ch
        elif ch == "'":
            quoted = True
            current += ch
        elif ch == ",":
            values.append(current)
            current = ""
        else:
            current += ch
        i += 1
    values.append(current)
    return values


def records():
    """{spell id: {column: value}} of every spell_dbc record of the generated render."""
    sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
    columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql, re.S)[1].split(",")]
    found = {}
    for m in re.finditer(r"^\((\d+),(.*)\)[,;]$", sql[sql.index("INSERT INTO `spell_dbc`"):], re.M):
        values = split_values(m[1] + "," + m[2])
        if len(values) == len(columns):
            found[int(m[1])] = dict(zip(columns, values))
    return found, sql


def unit_targets():
    """The target numbers the core says are units, from its own table (SpellInfo.cpp), by line number."""
    kinds = {}
    for number, line in enumerate(l for l in CORE_TARGETS.read_text(encoding="utf-8").splitlines() if re.match(r"\s*\{TARGET_OBJECT_TYPE_\w+,.*\},\s*//", l)):
        kinds[number] = re.match(r"\s*\{(TARGET_OBJECT_TYPE_\w+),", line)[1]
    return {number for number, kind in kinds.items() if kind == "TARGET_OBJECT_TYPE_UNIT"}


def aims_at_a_unit(record, units):
    for i in (1, 2, 3):
        if int(record["Effect_%d" % i]):
            for side in ("A", "B"):
                target = int(record["ImplicitTarget%s_%d" % (side, i)])
                if target in units and target != TARGET_UNIT_CASTER:
                    return True
    return False


def engine_ids(sql):
    """The spell ids the engine's script resolves (dc_ability_targets)."""
    line = re.search(r"INSERT INTO spell_script_names \(spell_id,ScriptName\) VALUES ((?:\(\d+,'dc_ability_targets'\),?)+);", sql)[1]
    return [int(x) for x in re.findall(r"\((\d+),'dc_ability_targets'\)", line)]


def old_path(speed, channeled, aims):
    """The rule before the fix: a Speed hands the cast to the impact, which only a unit-aimed record ever gets."""
    if speed <= 0 or channeled:
        return "cast"
    return "impact" if aims else "never"


class Trace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CORE_TARGETS.is_file():
            raise unittest.SkipTest("no core source")
        cls.records, sql = records()
        cls.ids = engine_ids(sql)
        cls.units = unit_targets()
        cls.names = {int(r["spell_id"]): r["name"] for r in csv.DictReader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())}

    def facts(self, spell_id):
        record = self.records[spell_id]
        return float(record["Speed"]), bool(int(record["AttributesEx"]) & SPELL_ATTR1_CHANNELED), aims_at_a_unit(record, self.units)

    def test_the_core_table_reads_a_ground_point_as_no_unit(self):
        self.assertNotIn(87, self.units)        # TARGET_DEST_DEST
        self.assertIn(TARGET_UNIT_CASTER, self.units)
        self.assertIn(6, self.units)            # TARGET_UNIT_TARGET_ENEMY

    def test_exactly_these_records_never_resolved(self):
        never = {self.names[i]: i for i in self.ids if i in self.records and old_path(*self.facts(i)) == "never"}
        self.assertEqual(EVERY_NEVER, never)
        self.assertEqual((14, 7, 3), (len(NEVER), len(DEMON_HUNTER_GROUND), len(DEMON_HUNTER_SELF)))

    def test_every_one_of_them_is_one_of_the_two_shapes_and_nothing_else_is(self):
        """A missile whose one dummy effect aims at a ground point or at the caster; no record of another shape never resolved."""
        for name, spell_id in EVERY_NEVER.items():
            record = self.records[spell_id]
            self.assertGreater(float(record["Speed"]), 0, name)
            self.assertEqual(("3", "0", "0"), (record["Effect_1"], record["Effect_2"], record["Effect_3"]), name)
            self.assertEqual(str(TARGET_DEST_DEST if name in GROUND else TARGET_UNIT_CASTER), record["ImplicitTargetA_1"], name)
            self.assertEqual("0", record["ImplicitTargetB_1"], name)
        for spell_id in self.ids:
            if spell_id in self.records and self.names[spell_id] not in EVERY_NEVER:
                speed, channeled, aims = self.facts(spell_id)
                self.assertNotEqual("never", old_path(speed, channeled, aims), self.names[spell_id])

    def test_those_now_resolve_on_arrival_and_nothing_else_moved(self):
        for spell_id in self.ids:
            if spell_id not in self.records:
                continue
            speed, channeled, aims = self.facts(spell_id)
            old = old_path(speed, channeled, aims)
            new = {"cast": "cast", "impact": "impact", "arrival": "arrival"}["cast" if speed <= 0 or channeled else ("impact" if aims else "arrival")]
            if self.names[spell_id] in EVERY_NEVER:
                self.assertEqual(("never", "arrival"), (old, new), self.names[spell_id])
            else:
                self.assertEqual(old, new, self.names[spell_id])

    def test_every_ground_point_one_has_a_speed_a_dummy_effect_and_a_point(self):
        for name, spell_id in GROUND.items():
            record = self.records[spell_id]
            self.assertGreater(float(record["Speed"]), 0, name)
            self.assertEqual("3", record["Effect_1"], name)          # SPELL_EFFECT_DUMMY
            self.assertEqual("87", record["ImplicitTargetA_1"], name)  # TARGET_DEST_DEST
            self.assertEqual(["0", "0"], [record["Effect_2"], record["Effect_3"]], name)

    def test_the_other_ground_point_records_have_no_speed_and_resolved_at_the_cast(self):
        targeting = {r["skill"]: r["target_type"] for r in csv.DictReader((MODULE / "data/d3/skill_targeting.csv").read_text(encoding="utf-8").splitlines())}
        for spell_id in self.ids:
            if spell_id in self.records and targeting.get(self.names[spell_id].split(" - ")[0]) == "ground_area" and self.names[spell_id] not in EVERY_NEVER:
                self.assertLessEqual(self.facts(spell_id)[0], 0.0, self.names[spell_id])


class Rule(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_ground_missile_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="groundmissile-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self):
        out = []
        for speed, channeled, aims, want in ((0, 0, 0, "cast"), (0, 0, 1, "cast"), (30, 0, 0, "arrival"), (30, 0, 1, "impact"), (30, 1, 0, "cast"),
                                             (30, 1, 1, "cast"), (-5, 0, 0, "cast"), (0.5, 0, 0, "arrival")):
            out.append(("path\t%s\t%d\t%d" % (speed, channeled, aims), want))
        for distance, speed, want in ((30, 30, 1000), (15, 30, 500), (0, 30, 0), (-4, 30, 0), (30, 0, 0), (10, 20, 500), (1, 3, 333), (2, 3, 667)):
            out.append(("arrival\t%s\t%s" % (distance, speed), str(want)))
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [want for _, want in cases], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rule_agrees_with_the_cases(self):
        want, got = self.drive(HEADER.read_text(encoding="utf-8"), "real")
        self.assertEqual(want, got)

    def test_a_planted_difference_is_caught(self):
        real = HEADER.read_text(encoding="utf-8")
        mutants = {
            "a speed alone is a missile at units": ("return aimsAtAUnit ? Path::OnImpact : Path::OnArrival;", "return Path::OnImpact;"),
            "a ground point resolves on impact": ("return aimsAtAUnit ? Path::OnImpact : Path::OnArrival;", "return aimsAtAUnit ? Path::OnArrival : Path::OnImpact;"),
            "a channel is a missile": ("if (speed <= 0 || channeled)", "if (speed <= 0)"),
            "no speed is a missile": ("if (speed <= 0 || channeled)", "if (channeled)"),
            "no flight": ("std::lround(distance / speed * 1000.0)", "0"),
            "the flight is in seconds": ("std::lround(distance / speed * 1000.0)", "std::lround(distance / speed)"),
            "the flight truncates": ("std::lround(distance / speed * 1000.0)", "static_cast<long>(distance / speed * 1000.0)"),
            "a negative distance flies": ("if (distance <= 0 || speed <= 0)", "if (speed <= 0)"),
        }
        want, _ = self.drive(real, "want")
        for label, (old, new) in mutants.items():
            with self.subTest(label):
                self.assertEqual(1, real.count(old), label + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), label.replace(" ", "-"))
                self.assertNotEqual(want, got, label + " survived")


def finish_problems(text):
    """What is off in Finish's use of the ground-missile rule in `text`; empty when it is right."""
    flat = re.sub(r"\s+", " ", text)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the header is included", '#include "dc_ground_missile_math.h"' in text)
    need("Finish asks the rule with the record's Speed, channelling and aim",
         "switch (GroundMissile::PathOf(GetSpellInfo()->Speed, GetSpellInfo()->IsChanneled(), AimsAtAUnit()))" in flat)
    need("the cast path resolves at the cast", "case GroundMissile::Path::AtCast: ResolveCast(player, shell, center, native, GetExplTargetUnit(), &origin); break;" in flat)
    need("the arrival path lands at the point", "case GroundMissile::Path::OnArrival: LandAtPoint(player); break;" in flat)
    need("the impact path leaves the cast to Impact", "case GroundMissile::Path::OnImpact: break;" in flat)
    need("only a unit that is not the caster counts as an aim",
         "aim.GetObjectType() == TARGET_OBJECT_TYPE_UNIT && aim.GetTarget() != TARGET_UNIT_CASTER" in flat and "if (effect.IsEffect())" in flat)
    land = flat[flat.index("void LandAtPoint(Player* player)"):] if "void LandAtPoint(Player* player)" in flat else ""
    land = land[:land.index("void Struck(") if "void Struck(" in land else 2000]
    need("it waits the flight over the record's Speed, from the caster to the point",
         "GroundMissile::ArrivalMs(player->GetExactDist(center), GetSpellInfo()->Speed)" in land)
    need("it runs on the caster's own queue", "player->m_Events.AddEventAtOffset(" in land)
    need("it keeps the launch's shell, point and origin", "shell = shell, center = center, origin = origin" in land)
    need("it gives up when the caster died or left",
         all(x in land for x in ("!player->IsAlive()", "!player->IsInWorld()", "player->GetMapId() != map", "player->GetInstanceId() != instance",
                                 "player->GetPhaseMask() != phase")))
    need("it resolves the same cast", "ResolveCast(player, shell, center, {}, aimed ? ObjectAccessor::GetUnit(*player, aimed) : nullptr, &origin);" in land)
    return wrong


class Engine(unittest.TestCase):
    def test_finish_uses_the_rule_and_lands_the_missile(self):
        self.assertEqual([], finish_problems(RESOLVE.read_text(encoding="utf-8")))

    def test_the_impact_path_is_as_it_was(self):
        text = re.sub(r"\s+", " ", RESOLVE.read_text(encoding="utf-8"))
        self.assertIn("void Impact() { Shaman::FreeHits free(freeCast); Player* player = GetCaster()->ToPlayer(); Unit* target = GetHitUnit(); if (!paid || !Projectile() ||", text)
        self.assertIn("AfterHit += SpellHitFn(dc_ability_targets::Impact);", text)
        self.assertEqual(1, text.count("bool Projectile() { return GetSpellInfo()->Speed > 0 && !GetSpellInfo()->IsChanneled(); }"))

    def test_a_planted_difference_is_caught(self):
        real = RESOLVE.read_text(encoding="utf-8")
        mutants = {
            "no include": ('#include "dc_ground_missile_math.h"\n', ""),
            "the impact resolves too": ("case GroundMissile::Path::OnImpact:\n                        break;", "case GroundMissile::Path::OnImpact:\n                        LandAtPoint(player);\n                        break;"),
            "the arrival does nothing": ("case GroundMissile::Path::OnArrival:\n                        LandAtPoint(player);\n                        break;", "case GroundMissile::Path::OnArrival:\n                        break;"),
            "the caster counts as an aim": ("aim.GetTarget() != TARGET_UNIT_CASTER", "aim.GetTarget() != TARGET_UNIT_TARGET_ENEMY"),
            "an empty effect counts": ("if (effect.IsEffect())\n                        for", "if (true)\n                        for"),
            "no flight": ("GroundMissile::ArrivalMs(player->GetExactDist(center), GetSpellInfo()->Speed)", "0"),
            "the flight is from the origin": ("player->GetExactDist(center)", "player->GetExactDist(origin)"),
            "a dead caster still casts": ("if (!player->IsAlive() || !player->IsInWorld() ||", "if (!player->IsInWorld() ||"),
            "another map still casts": ("player->GetMapId() != map ||", ""),
            "the point is lost": ("ResolveCast(player, shell, center, {}, aimed", "ResolveCast(player, shell, origin, {}, aimed"),
        }
        for label, (old, new) in mutants.items():
            with self.subTest(label):
                self.assertEqual(1, real.count(old), label + " does not apply")
                self.assertNotEqual([], finish_problems(real.replace(old, new, 1)), label + " survived")


if __name__ == "__main__":
    unittest.main()
