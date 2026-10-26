"""Legendary rest, bead diablocraft-w7wes: Monkey King's Garb (Monk set, list rows 230, 231, 232), all three levels as one set.

  2 pieces: "Your damage taken is reduced by 50% while Sweeping Wind is active."
  4 pieces: "Every second Sweeping Wind spawns a decoy next to the last enemy you hit that taunts nearby enemies and then explodes for 1000% weapon
            damage for each stack of Sweeping Wind you have."
  6 pieces: "Lashing Tail Kick, Tempest Rush, and Wave of Light have their damage increased by 1500% for each stack of Sweeping Wind you have."
  * the numbers are read from d3planner (data_itemsets.js, sunwuko) and the catalogue; the table (data/legendary_powers.csv) holds THREE rows for the
    set, one a level: `player` damage_taken_pct -50 under skills_active Sweeping Wind; `skill` Sweeping Wind decoy_damage_pct_per_stack 1000;
    `skill` Lashing Tail Kick;Tempest Rush;Wave of Light damage_by_wind_stacks_pct 1500;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses a
    bad row of the two new stats;
  * the production rules are compiled and driven with the generated rows: the set counter and the levels (Owned), PlayerFactor under skills_active, the
    decoy's number (SkillSetTo) and its explosion (TauntDecoy::BlastPct), the clock (Wind::CompletesSecond), the decoy's build and reach rules, and
    PerStackFactor by the vortex's stacks; mutants of the rows, the rules and the headers fail the same driver;
  * the numbers the set text does not give (the taunt radius, the delay and the explosion radius) are blank placeholder tunables, and a blank one builds no
    decoy; source-text guards for the seams (Monk::SkillActive, Monk::WindStacks, ComputeHit's call, the vortex's tick and last hit, the decoy's place and
    explosion, the decoy creature of the summons sheet). The C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-w7wes.md.
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
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
DECOY_H = SRC / "combat/dc_taunt_decoy_math.h"
WIND_H = SRC / "classes/monk/dc_monk_sweeping_wind.h"
WIND_CPP = SRC / "classes/monk/dc_monk_sweeping_wind.cpp"
DECOY_CPP = SRC / "combat/dc_taunt_decoy.cpp"
HARNESS = MODULE / "tests/item_power_monkey_kings_garb/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SET = "Monkey King's Garb"
KICKS = "Lashing Tail Kick;Tempest Rush;Wave of Light"
ROW = re.compile(r"\('((?:[^']|'')*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1].replace("''", "'"), int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return sorted((r for r in (all_rows() if rows is None else rows) if r[0] == SET), key=lambda r: r[1])


def words():
    """{level: (the number, the text)} from d3planner's set."""
    text = (REPO / "reference/d3planner/data_itemsets.js").read_text(encoding="utf-8")
    start = text.index("sunwuko: {")
    block = text[start:text.index("\n  },\n", start)]
    found = dict(re.findall(r'"(\d)": \[\s*\{format: "(.*?)"\}', block, re.S))
    assert sorted(found) == ["2", "4", "6"], found
    two = re.fullmatch(r"Your damage taken is reduced by (\d+)%% while Sweeping Wind is active\.", found["2"])
    four = re.fullmatch(r"Every second Sweeping Wind spawns a decoy next to the last enemy you hit that taunts nearby enemies and then explodes for "
                        r"(\d+)%% weapon damage for each stack of Sweeping Wind you have\.", found["4"])
    six = re.fullmatch(r"Lashing Tail Kick, Tempest Rush, and Wave of Light have their damage increased by (\d+)%% for each stack of Sweeping Wind you have\.",
                       found["6"])
    assert two and four and six, found
    return {2: float(two[1]), 4: float(four[1]), 6: float(six[1])}


class Table(unittest.TestCase):
    def test_the_sources_say_50_1000_and_1500(self):
        self.assertEqual({2: 50.0, 4: 1000.0, 6: 1500.0}, words())
        text = (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8")
        for level, number in words().items():
            self.assertIn("%d%%" % number if level != 2 else "50%", text)
        for skill in ("Sweeping Wind", "Lashing Tail Kick", "Tempest Rush", "Wave of Light"):
            self.assertIn(skill, [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv")])

    def test_three_rows_one_a_level(self):
        number = words()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual([(SET, 2, "player", "", "damage_taken_pct", -number[2], -number[2], "skills_active", 0.0, "Sweeping Wind", 0.0, 0, "", "", 100.0, 0.0),
                          (SET, 4, "skill", "Sweeping Wind", "decoy_damage_pct_per_stack", number[4], number[4], *blank),
                          (SET, 6, "skill", KICKS, "damage_by_wind_stacks_pct", number[6], number[6], *blank)], mine())

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0064_table.sql")

    def test_the_decoys_numbers_are_the_power_files(self):
        rows = {r["name"]: r for r in read_csv("data/tunables/monk.csv")}
        for name, d3, unit in (("monkey_kings_garb_decoy_taunt_radius_yards", "15", "yards"), ("monkey_kings_garb_decoy_explode_delay_seconds", "0.5", "seconds"),
                               ("monkey_kings_garb_decoy_explode_radius_yards", "15", "yards"), ("monkey_kings_garb_decoy_empty_offset_yards", "5", "yards")):
            self.assertEqual((d3, "", unit), (rows[name]["d3_value"], rows[name]["value"], rows[name]["unit"]), name)
            self.assertIn("P4_ItemPassive_Unique_Ring_043_SpawnDecoy.pow", rows[name]["notes"], name)
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)

    def test_those_numbers_are_what_the_power_file_says(self):
        """Cross-source: the set's 4-piece record grants Ring_043, whose SpawnDecoy power holds the labels; read from the client archives."""
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        text = harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", "P4_ItemPassive_Unique_Ring_043_SpawnDecoy"],
                               capture_output=True, text=True).stdout
        for label, number in (("Taunt Radius", "15"), ("Delay Before Explosion", "0.5"), ("Explosion Radius", "15"), ("Offset From Player If No Enemies", "5")):
            self.assertRegex(text, r"'%s' = %s\b" % (label, re.escape(number)))


class Generator(unittest.TestCase):
    BASE_4 = {"owner": SET, "pieces": "4", "kind": "skill", "skill": "Sweeping Wind", "stat": "decoy_damage_pct_per_stack", "value_min": "1000",
              "value_max": "1000", "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "",
              "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}
    BASE_6 = {**BASE_4, "pieces": "6", "skill": KICKS, "stat": "damage_by_wind_stacks_pct", "value_min": "1500", "value_max": "1500"}

    def render_with(self, stat, *edits):
        work = Path(tempfile.mkdtemp(prefix="monkeyking-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if not (r["owner"] == SET and r["stat"] == stat)]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + list(edits))
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.assertEqual(3, len([r for r in self.render_with("none") if r[0] == SET]))

    def test_it_refuses_what_it_cannot_carry(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        decoy = {
            "a range": ({"value_min": "900"}, "decoy_damage_pct_per_stack is one number"),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min|decoy_damage_pct_per_stack is one number"),
            "another skill": ({"skill": "Lashing Tail Kick"}, "decoy_damage_pct_per_stack is one number"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Sweeping Wind"}, "decoy_damage_pct_per_stack is one number"),
            "an event": ({"fire_on": "cast", "fire_skills": "Sweeping Wind"}, "an event fires|decoy_damage_pct_per_stack is one number"),
        }
        for name, (edit, why) in decoy.items():
            with self.subTest(case="decoy " + name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with("decoy_damage_pct_per_stack", {**self.BASE_4, **edit})
        stacks = {
            "a range": ({"value_min": "1400"}, "damage_by_wind_stacks_pct is one number"),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min|damage_by_wind_stacks_pct is one number"),
            "another skill": ({"skill": "Fists of Thunder"}, "damage_by_wind_stacks_pct is one number"),
            "one good skill and a bad one": ({"skill": "Tempest Rush;Fists of Thunder"}, "damage_by_wind_stacks_pct is one number"),
            "a condition": ({"cond": "skills_active", "cond_skills": "Sweeping Wind"}, "damage_by_wind_stacks_pct is one number"),
            "not a skill": ({"skill": "Tempest Rushes"}, "is not a skill"),
        }
        for name, (edit, why) in stacks.items():
            with self.subTest(case="stacks " + name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with("damage_by_wind_stacks_pct", {**self.BASE_6, **edit})


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, decoy_text, wind_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text, "combat/dc_taunt_decoy_math.h": decoy_text, "classes/monk/dc_monk_sweeping_wind.h": wind_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemmonkeyking-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the set's words, not from the code."""
        n = words()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # 2 pieces: damage taken x(1 - 50/100) while the vortex is up, and only then
        out += clear + [(T("taken"), "1")]
        out += clear + [(T("pieces", SET, 1), None), (T("active", "Sweeping Wind"), None), (T("taken"), "1")]
        out += clear + [(T("pieces", SET, 2), None), (T("taken"), "1"), (T("active", "Sweeping Wind"), None), (T("taken"), g(1 - n[2] / 100))]
        out += clear + [(T("pieces", SET, 6), None), (T("active", "Sweeping Wind"), None), (T("taken"), g(1 - n[2] / 100))]
        out += clear + [(T("pieces", SET, 2), None), (T("active", "Lashing Tail Kick"), None), (T("taken"), "1")]
        out += clear + [(T("pieces", "Other Set", 6), None), (T("active", "Sweeping Wind"), None), (T("taken"), "1")]
        # 4 pieces: the decoy number 1000 only with 4, and the explosion is 1000% for each stack the vortex holds then
        for stacks in (0, 1, 3, 10):
            out += clear + [(T("pieces", SET, 4), None), (T("decoy", stacks), "%s %s" % (g(n[4]), g(n[4] * stacks)))]
        out += clear + [(T("pieces", SET, 3), None), (T("decoy", 5), "0 0")]
        out += clear + [(T("pieces", SET, 6), None), (T("decoy", 2), "%s %s" % (g(n[4]), g(n[4] * 2)))]
        # the decoy is built only with all three numbers set; the reach is inclusive
        for a, b, c, want in ((5, 2, 8, 1), (0, 2, 8, 0), (5, 0, 8, 0), (5, 2, 0, 0), (0, 0, 0, 0), (-1, 2, 8, 0)):
            out += [(T("built", a, b, c), str(want))]
        for d, r, want in ((0, 5, 1), (5, 5, 1), (5.01, 5, 0), (4.9, 5, 1), (1, 0, 0), (0, 0, 0), (-1, 5, 0)):
            out += [(T("within", d, r), str(want))]
        # the clock: a decoy each whole second of the vortex's 0.25 s ticks, the 4th and the 8th
        for index in range(0, 13):
            out += [(T("second", index, 0.25), "1" if index in (4, 8, 12) else "0")]
        for index in range(0, 7):
            out += [(T("second", index, 0.5), "1" if index in (2, 4, 6) else "0")]
        for seconds, want in ((0, 0), (-1, 0), (2, 2000), (1.5, 1500), (0.0004, 0), (0.0006, 1)):
            out += [(T("millis", seconds), str(want))]
        # 6 pieces: 1 + 1500/100 x the stacks, for the three skills only
        for skill in KICKS.split(";"):
            for stacks in (0, 1, 3, 10):
                out += clear + [(T("pieces", SET, 6), None), (T("perstack", skill, stacks), g(1 + n[6] / 100 * stacks))]
        for other in ("Fists of Thunder", "Sweeping Wind", "Lashing Tail", "tempest rush", ""):
            out += clear + [(T("pieces", SET, 6), None), (T("perstack", other, 3), "1")]
        out += clear + [(T("pieces", SET, 5), None), (T("perstack", "Tempest Rush", 3), "1")]
        out += clear + [(T("pieces", SET, 4), None), (T("perstack", "Tempest Rush", 3), "1")]
        out += clear + [(T("pieces", SET, 6), None), (T("perstack", "Tempest Rush", -2), "1")]
        return out

    def drive(self, math_text, decoy_text, wind_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(math_text, decoy_text, wind_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def texts(self):
        return MATH.read_text(encoding="utf-8"), DECOY_H.read_text(encoding="utf-8"), WIND_H.read_text(encoding="utf-8")

    def test_every_rule_agrees_with_the_set_text(self):
        want, got = self.drive(*self.texts(), mine(), "real")
        self.assertGreater(len(want), 60)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real, decoy, wind = self.texts()
        rows = mine()
        self.assertEqual(3, len(rows))
        want, _ = self.drive(real, decoy, wind, rows, "want")
        row_mutants = {
            "two_not_fifty": [rows[0][:5] + (-25.0, -25.0) + rows[0][7:]] + rows[1:],
            "two_without_the_condition": [rows[0][:7] + ("", 0.0, "") + rows[0][10:]] + rows[1:],
            "two_on_another_skill": [rows[0][:9] + ("Whirlwind",) + rows[0][10:]] + rows[1:],
            "four_a_tenth": [rows[0], rows[1][:5] + (100.0, 100.0) + rows[1][7:], rows[2]],
            "four_on_another_level": [rows[0], rows[1][:1] + (6,) + rows[1][2:], rows[2]],
            "six_a_tenth": rows[:2] + [rows[2][:5] + (150.0, 150.0) + rows[2][7:]],
            "six_loses_the_kick": rows[:2] + [rows[2][:3] + ("Tempest Rush;Wave of Light",) + rows[2][4:]],
            "six_adds_the_wind": rows[:2] + [rows[2][:3] + (KICKS + ";Sweeping Wind",) + rows[2][4:]],
            "six_on_four_pieces": rows[:2] + [rows[2][:1] + (4,) + rows[2][2:]],
            "no_set": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, decoy, wind, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double PerStackFactor("):]
        body = body[:body.index("\n    }\n") + 7]
        math_mutants = {
            "the_factor_loses_its_one": (body, body.replace("factor *= 1.0 + pct / 100.0 * count;", "factor *= pct / 100.0 * count;", 1)),
            "the_count_adds": (body, body.replace("factor *= 1.0 + pct / 100.0 * count;", "factor *= 1.0 + pct / 100.0 + count;", 1)),
            "a_negative_count_counts": (body, body.replace("std::max(0.0, stacks)", "stacks", 1)),
        }
        for name, (old, new) in math_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(old, new, name + " does not apply")
                _, got = self.drive(real.replace(old, new), decoy, wind, rows, name)
                self.assertNotEqual(want, got, name + " survived")
        owned = real[real.index("inline bool Owned("):]
        owned = owned[:owned.index("\n    }\n") + 7]
        with self.subTest(mutant="a_level_one_short"):
            mutated = owned.replace("worn->second < row.pieces", "worn->second + 1 < row.pieces", 1)
            self.assertNotEqual(owned, mutated)
            _, got = self.drive(real.replace(owned, mutated), decoy, wind, rows, "short")
            self.assertNotEqual(want, got, "a_level_one_short survived")
        decoy_mutants = {
            "built_with_any_number": ("return tauntRadius > 0 && delaySeconds > 0 && blastRadius > 0;", "return tauntRadius > 0 || delaySeconds > 0 || blastRadius > 0;"),
            "built_without_the_delay": ("return tauntRadius > 0 && delaySeconds > 0 && blastRadius > 0;", "return tauntRadius > 0 && blastRadius > 0;"),
            "the_edge_is_out": ("distance >= 0 && distance <= radius", "distance >= 0 && distance < radius"),
            "no_radius_is_everywhere": ("return radius > 0 && distance >= 0 && distance <= radius;", "return distance >= 0 && distance <= radius;"),
            "the_blast_ignores_the_stacks": ("std::max(0.0, perStackPct) * stacks", "std::max(0.0, perStackPct)"),
            "the_blast_adds_the_stacks": ("std::max(0.0, perStackPct) * stacks", "std::max(0.0, perStackPct) + stacks"),
            "seconds_truncate": ("seconds * 1000.0 + 0.5", "seconds * 1000.0"),
        }
        for name, (old, new) in decoy_mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, decoy.count(old), name + " does not apply")
                _, got = self.drive(real, decoy.replace(old, new, 1), wind, rows, name)
                self.assertNotEqual(want, got, name + " survived")
        second = wind[wind.index("inline bool CompletesSecond("):]
        second = second[:second.index("\n    }\n") + 7]
        with self.subTest(mutant="every_tick_completes_a_second"):
            mutated = second.replace("return PaysSpirit(index, tickSeconds);", "return index > 0;", 1)
            self.assertNotEqual(second, mutated)
            _, got = self.drive(real, decoy, wind.replace(second, mutated), rows, "tick")
            self.assertNotEqual(want, got, "every_tick_completes_a_second survived")


def tick_failures(text):
    """What is wrong with the vortex's reading of the 4-piece in `text` ([] when it is right)."""
    wrong = []
    flat = re.sub(r"\s+", " ", text)

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the number is the item's decoy_damage_pct_per_stack on the skill, base 0, asked before the lock",
         'double const decoyPct = ItemPowers::SkillSetTo(player, std::string(Skill), "decoy_damage_pct_per_stack", 0);' in text
         and text.index("decoy_damage_pct_per_stack") < text.index("std::lock_guard<std::mutex> guard(mutex);", text.index("decoy_damage_pct_per_stack")))
    need("the last enemy hit is a vortex tick's struck enemy", "if (!struck.empty()) vortex.lastHit = struck.back()->GetGUID().GetRawValue();" in flat)
    need("a decoy each whole second, outside the lock", "if (decoyPct > 0 && CompletesSecond(index, tick)) Decoy(player, spellId, lastHit, decoyPct);" in flat)
    need("the entry is the summons sheet's decoy", "spec.entry = Rifts::Ally::DecoyEntry;" in text)
    need("the three numbers are the monk tunables, a blank one 0",
         all(name in text for name in ("monkey_kings_garb_decoy_taunt_radius_yards", "monkey_kings_garb_decoy_explode_delay_seconds",
                                       "monkey_kings_garb_decoy_explode_radius_yards"))
         and "return DC::Tunables::Has(\"monk\", name) ? DC::Tunables::Get(\"monk\", name) : 0.0;" in flat)
    need("the explosion follows the stacks when it goes off", "return Combat::TauntDecoy::BlastPct(perStackPct, StacksNow(player));" in flat)
    need("the decoy goes beside the last enemy hit while it lives, else a little in front of the Monk",
         "near && near->IsAlive() && player->IsValidAttackTarget(near) ? near->GetNearPosition(DecoyBesideYards, near->GetAbsoluteAngle(player)) : player->GetNearPosition(float(OpenNumber(\"monkey_kings_garb_decoy_empty_offset_yards\")), player->GetOrientation());" in flat)
    need("it is placed at that spot", "Combat::TauntDecoy::Place(player, where, spec);" in flat)
    need("a hit landed records the last enemy", "found->second.lastHit = target->GetGUID().GetRawValue();" in flat)
    need("Active and Stacks answer for a vortex that has not run out", flat.count("found->second.until > now") >= 2)
    return wrong


def place_failures(text):
    """What is wrong with the shared decoy's placing and exploding in `text` ([] when it is right)."""
    wrong = []
    flat = re.sub(r"\s+", " ", text)

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the decoy stands at the spot it is given", "bool Place(Player* owner, Position const& where, Spec const& spec)" in flat)
    need("nothing is placed without the whole spec", "!Built(spec.tauntRadius, spec.delaySeconds, spec.blastRadius)" in flat)
    need("the taunt is the core's, cast from the decoy", "decoy->AddAura(Taunt, enemy)" in flat and "constexpr std::uint32_t Taunt = 355;" in flat)
    need("the taunted are engaged with the decoy and in its threat list", "enemy->EngageWithTarget(decoy);" in flat and "enemy->GetThreatMgr().AddThreat(decoy, 1.0f);" in flat)
    need("the taunt lasts the delay", "taunt->SetMaxDuration(int32(ms)); taunt->SetDuration(int32(ms));" in flat)
    need("only enemies within the taunt radius", "Within(decoy->GetExactDist(enemy), spec.tauntRadius)" in flat)
    need("the explosion is the owner's hit, off the owner's queue, at the spot",
         "owner->m_Events.AddEventAtOffset([owner, guid = decoy->GetGUID(), where, spec]" in flat
         and "Combat::Strike(owner, enemy, spec.spellId, pct, true);" in flat)
    need("only enemies within the blast radius", "Within(where.GetExactDist(enemy), spec.blastRadius)" in flat)
    need("the decoy goes after", "gone->DespawnOrUnsummon();" in flat)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_vortex_reads_the_4_piece(self):
        self.assertEqual([], tick_failures(WIND_CPP.read_text(encoding="utf-8")))

    def test_the_decoy_places_and_explodes(self):
        self.assertEqual([], place_failures(DECOY_CPP.read_text(encoding="utf-8")))

    def test_the_seams_to_the_engine(self):
        combat = (SRC / "combat/dc_combat.cpp").read_text(encoding="utf-8")
        self.assertIn('ItemPowers::PerStackFactor(player, petName, "damage_by_wind_stacks_pct", Monk::WindStacks(player))', combat)
        self.assertLess(combat.index('ItemPowers::PerStackFactor(player, petName, "damage_by_wind_stacks_pct"'), combat.index("hit.total = Total("))
        powers = (SRC / "combat/dc_item_powers.cpp").read_text(encoding="utf-8")
        self.assertIn("if (SkillIsActive(player, skill))", powers)
        self.assertIn("return Abilities::SkillActive(player, skill) || Monk::SkillActive(player, skill);", combat)
        monk = (SRC / "classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.assertIn('return skill == "Sweeping Wind" && Wind::Active(player);', monk)
        self.assertIn("return Wind::Stacks(player);", monk)
        self.assertIn("Wind::Landed(player);\n        Wind::Struck(player, target);", monk)

    def test_the_shared_folders_name_no_skill_and_no_class(self):
        for path in (DECOY_CPP, SRC / "combat/dc_taunt_decoy.h", DECOY_H):
            text = path.read_text(encoding="utf-8")
            for name in ("Monk", "Sweeping Wind", "Monkey King", "Barbarian", "Crusader", "Wizard"):
                self.assertNotIn(name, text, f"{path.name} names {name}")
        for path in (SRC / "combat").rglob("*"):
            if path.suffix in (".cpp", ".h") and path.name != "dc_spell_shells.h":
                self.assertNotIn("decoy_damage_pct_per_stack", path.read_text(encoding="utf-8", errors="replace"), path)

    def test_the_decoy_creature_is_a_pawn_of_the_summons_sheet(self):
        rows = [r for r in read_csv("data/legendary_summons.csv") if r["entry"] == "900128"]
        self.assertEqual(1, len(rows))
        self.assertEqual(("dc_legendary_pawn", SET), (rows[0]["script"], rows[0]["item"]))
        self.assertIn("IsAllyEntry", (SRC / "rifts/dc_ally.h").read_text(encoding="utf-8"))
        self.assertIn("Count = 9", (SRC / "rifts/dc_ally.h").read_text(encoding="utf-8"))
        self.assertIn("DecoyEntry = 900128;", (SRC / "rifts/dc_ally.h").read_text(encoding="utf-8"))

    def test_the_source_guards_fail_their_mutants(self):
        wind, place = WIND_CPP.read_text(encoding="utf-8"), DECOY_CPP.read_text(encoding="utf-8")
        wind_mutants = {
            "no_decoy_number": ('"decoy_damage_pct_per_stack", 0)', '"decoy_damage_pct_per_stack", 7)'),
            "every_tick": ("CompletesSecond(index, tick)", "true"),
            "the_wrong_entry": ("spec.entry = Rifts::Ally::DecoyEntry;", "spec.entry = Rifts::Ally::FirstEntry;"),
            "the_blast_ignores_the_stacks": ("BlastPct(perStackPct, StacksNow(player))", "BlastPct(perStackPct, 1)"),
            "a_blank_tunable_reads_one": (": 0.0;\n        }\n\n        unsigned StacksNow", ": 1.0;\n        }\n\n        unsigned StacksNow"),
            "no_last_hit": ("vortex.lastHit = struck.back()->GetGUID().GetRawValue();", "vortex.lastHit = 0;"),
            "no_empty_offset": ("player->GetNearPosition(float(OpenNumber(\"monkey_kings_garb_decoy_empty_offset_yards\")), player->GetOrientation())", "player->GetPosition()"),
            "a_dead_enemy_still_hosts_it": ("near && near->IsAlive() && player->IsValidAttackTarget(near)", "near"),
        }
        for name, (old, new) in wind_mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, wind.count(old), name + " does not apply")
                self.assertNotEqual([], tick_failures(wind.replace(old, new, 1)), name + " survived")
        place_mutants = {
            "no_spec_check": ("!Built(spec.tauntRadius, spec.delaySeconds, spec.blastRadius)", "false"),
            "no_taunt": ("decoy->AddAura(Taunt, enemy)", "nullptr"),
            "the_taunt_is_the_owners": ("decoy->AddAura(Taunt, enemy)", "owner->AddAura(Taunt, enemy)"),
            "no_threat": ("enemy->GetThreatMgr().AddThreat(decoy, 1.0f);", ""),
            "the_blast_is_a_dot_less_hit_on_everyone": ("Within(where.GetExactDist(enemy), spec.blastRadius)", "true"),
            "the_decoy_stays": ("gone->DespawnOrUnsummon();", ""),
        }
        for name, (old, new) in place_mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, place.count(old), name + " does not apply")
                self.assertNotEqual([], place_failures(place.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
