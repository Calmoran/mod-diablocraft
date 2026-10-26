"""Legendary rest, bead diablocraft-n8m1a: Hellrack (crossbow, any class), which builds N-STUN (a control an item puts on an enemy, and the event a
control put on an enemy is).

  "Chance to root enemies to the ground when you hit them."
  * the numbers are the item's power file's (docs/research/legendary-pow-data.csv row Hellrack: the item's own 0.2 read as the chance, decisions.md
    2026-10-10 (a); SF_0 Jailer Duration 2, SF_1 Cooldown Duration 0.1) and the text the catalogue's and the tooltip's, read apart from the table; the
    table holds ONE row for the pool item Unique_XBow_002_x1: an `effect` `root_seconds` 2 fired on a `hit` of any skill (no fire_skills), chance 20,
    internal cooldown 0.1 s;
  * the generated SQL and the committed migration are what the generator renders, the migration the newest full table; the generator accepts the control
    effect's hit with no skill named (every skill) and the control effect only as an item's one fixed number on a hit, and refuses it on a control event (an
    effect that fires its own event would loop); any other effect's hit or cast still names its skills;
  * the production rules (src/combat/dc_item_power_math.h: Fire with the chance x the hit's proc coefficient and the internal cooldown, ControlSpell,
    ControlEvent) are compiled and driven with the generated row: every skill's hit can root, the chance asked is 20 x the coefficient (a hit with
    none cannot), once per 0.1 s at most (the end exact), only while worn; the stock aura is 64695 and the control events name stun, freeze, blind
    and root as Torment's holds carry them;
  * mutants of the rules and of the row fail the same driver;
  * source-text guards: the effect puts the stock hold on the enemy the hit struck for the row's seconds (the player's own hold taken off first), and
    the aura hook fires `control_<kind>` for an aura a player put on a monster, and only when a row listens; the stock record is a root-only aura with
    the Root mechanic in the client's Spell.dbc. The C++ is compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-n8m1a.md.
"""
import csv
import re
import shutil
import struct
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
HARNESS = MODULE / "tests/item_power_hellrack/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_XBow_002_x1"
STAT = "root_seconds"
EARTHGRAB = 64695
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine():
    return [r for r in all_rows() if r[0] == OWNER]


def numbers():
    """(chance percent, root seconds, internal cooldown seconds) from the item's power file, as the research decoded it."""
    row = next(r for r in read_csv(REPO / "docs/research/legendary-pow-data.csv") if r["item_or_set"] == "Hellrack")
    assert row["linked_by"] == "item " + OWNER, row
    jailer = re.search(r"SF_0 Jailer Duration = ([\d.]+)", row["script_formulas"])
    cooldown = re.search(r"SF_1 Cooldown Duration = ([\d.]+)", row["script_formulas"])
    assert jailer and cooldown, row
    return float(row["item_number"]) * 100, float(jailer[1]), float(cooldown[1])


class Table(unittest.TestCase):
    def test_the_sources_give_the_text_and_the_numbers(self):
        self.assertEqual((20.0, 2.0, 0.1), numbers())
        catalogue = [r for r in read_csv(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertIn("root enemies to the ground when you hit them", catalogue[0]["power_text"])

    def test_one_row_roots_on_any_hit(self):
        chance, seconds, icd = numbers()
        self.assertEqual([(OWNER, 0, "effect", "", STAT, seconds, seconds, "", 0.0, "", 0.0, 0, "hit", "", chance, icd)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("root enemies to the ground", m[1])


class Generator(unittest.TestCase):
    ROOT = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "2", "value_max": "2", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit", "fire_skills": "", "chance_pct": "20",
            "icd_seconds": "0.1", "source": "s", "note": "n"}

    def render_with(self, *changes):
        """The generator run on a copy of the module whose sheet is the real one with the owner's rows replaced by these."""
        work = Path(tempfile.mkdtemp(prefix="hellrack-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv(MODULE / "data/legendary_powers.csv")
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows([r for r in sheet if r["owner"] != OWNER] + [{**self.ROOT, **c} for c in changes])
            return [r for r in generator.rows(work) if r[0] == OWNER]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_events_and_the_effect_are_in_the_vocabulary(self):
        self.assertIn(STAT, generator.EFFECT_STATS)
        self.assertEqual(("control_stun", "control_freeze", "control_blind", "control_root"), generator.CONTROL_EVENTS)
        self.assertTrue(set(generator.CONTROL_EVENTS) <= set(generator.EVENTS))

    def test_the_real_row_passes_and_a_hit_may_name_skills_or_none(self):
        self.assertEqual(1, len(self.render_with({})))
        self.assertEqual("Rend", self.render_with({"fire_skills": "Rend"})[0][13])

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a range": {"value_min": "1", "value_max": "2"},
            "no seconds": {"value_min": "0", "value_max": "0"},
            "a set bonus": {"owner": "Immortal King's Call", "pieces": "2"},
            "a condition": {"cond": "enemies_hit_at_most", "cond_arg": "3", "fire_on": "hit_spender"},
            "a skill named": {"skill": "Rend"},
            "on a cast": {"fire_on": "cast", "fire_skills": "Rend"},
            "on being hit": {"fire_on": "taken"},
            "on its own event": {"fire_on": "control_root"},
            "on another control event": {"fire_on": "control_stun"},
            "a hit of no skill": {"fire_skills": "Not A Skill"},
        }
        for name, change in refused.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                self.render_with(change)

    def test_a_control_event_names_no_skill_and_another_cast_or_hit_still_needs_one(self):
        with self.assertRaisesRegex(ValueError, "names skills"):
            self.render_with({"stat": "cooldown_cut_seconds", "value_min": "1", "value_max": "1", "fire_on": "control_stun", "fire_skills": "Rend"})
        self.assertEqual("control_stun", self.render_with({"stat": "cooldown_cut_seconds", "value_min": "1", "value_max": "1", "fire_on": "control_stun"})[0][12])
        for event in ("cast", "hit"):
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, "a cast, a hit or a landing needs fire_skills"):
                self.render_with({"stat": "cooldown_cut_seconds", "value_min": "1", "value_max": "1", "fire_on": event})


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemhellrack-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        chance, seconds, icd = numbers()
        rooted = "%s=%g;" % (STAT, seconds)
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = clear + [(T("wears", OWNER), None)]
        # not worn: nothing, and no roll asked
        out += clear + [(T("fire", "hit", "Rend", 1), "|")]
        # worn: a hit of any skill asks 20% x the hit's proc coefficient; the roll falls or it does not
        for skill in ("Rend", "Magic Missile", "Fists of Thunder", ""):
            for coefficient in (1, 0.5, 0.125):
                asked = "%g;" % (chance * coefficient)
                out += wear + [(T("now", 5000), None), (T("fire", "hit", skill, coefficient), rooted + "|" + asked)]
                out += wear + [(T("now", 5000), None), (T("dice", chance * coefficient + 0.01), None),
                               (T("fire", "hit", skill, coefficient), "|" + asked)]
        # a hit that states no proc coefficient cannot root (no roll asked)
        out += wear + [(T("now", 5000), None), (T("fire", "hit", "Rend", 0), "|")]
        # other events do not root
        for event in ("cast", "taken", "kill", "hit_spender", "control_root", "control_stun"):
            out += wear + [(T("now", 5000), None), (T("fire", event, "Rend", 1), "|")]
        # at most once per internal cooldown (the end exact); a failed roll does not start it
        ms = int(round(icd * 1000))
        out += wear + [(T("now", 5000), None), (T("fire", "hit", "Rend", 1), rooted + "|%g;" % chance),
                       (T("now", 5000 + ms - 1), None), (T("fire", "hit", "Rend", 1), "|"),
                       (T("now", 5000 + ms), None), (T("fire", "hit", "Rend", 1), rooted + "|%g;" % chance),
                       (T("dice", 100), None), (T("now", 5000 + 2 * ms), None), (T("fire", "hit", "Rend", 1), "|%g;" % chance),
                       (T("dice", 0), None), (T("now", 5000 + 2 * ms + 1), None), (T("fire", "hit", "Rend", 1), rooted + "|%g;" % chance)]
        # the control effect's aura: the stock root; nothing else is a control effect
        out += [(T("spell", STAT), str(EARTHGRAB)), (T("spell", "stun_seconds"), "853"), (T("spell", "stun"), "0"), (T("spell", "cooldown_cut_seconds"), "0")]
        # the event a control aura put on an enemy is: the Stun aura is a stun, a freeze when it carries the Freeze mechanic or is Torment's freeze hold
        # (stock 15878 "Ice Blast", mechanic Stun: the Monk's and the rift elites' freeze); a confuse is Torment's blind (stock 9992 "Dizzy", Blinding
        # Flash); a root a root; anything else (a slow, a dummy) no event
        for args, want in (((56, 1, 0, 0, 0), "control_stun"), ((83000, 1, 1, 0, 0), "control_freeze"), ((15878, 1, 0, 0, 0), "control_freeze"),
                           ((9992, 0, 0, 1, 0), "control_blind"), ((EARTHGRAB, 0, 0, 0, 1), "control_root"), ((12345, 0, 0, 0, 0), ""),
                           ((12345, 0, 1, 0, 0), ""), ((12345, 1, 0, 0, 1), "control_stun"), ((12345, 0, 0, 1, 1), "control_blind")):
            out.append((T("event", *args), want))
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        set_at = lambda i, v: [r[:i] + (v,) + r[i + 1:] for r in rows]  # noqa: E731
        row_mutants = {
            "the_chance_halved": set_at(14, rows[0][14] / 2),
            "the_chance_certain": set_at(14, 100.0),
            "no_cooldown": set_at(15, 0.0),
            "the_cooldown_a_second": set_at(15, 1.0),
            "one_skill_only": set_at(13, "Rend"),
            "the_wrong_event": set_at(12, "hit_spender"),
            "the_seconds_doubled": [r[:5] + (r[5] * 2, r[6] * 2) + r[7:] for r in rows],
            "another_effect": set_at(4, "stun_seconds"),
            "no_row": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("// N-STUN (Hellrack). A control effect"):]
        body = body[:body.index("// What one fired `effect` row does")]
        rules = {
            "another_root": ("RootHold = 64695", "RootHold = 23694"),
            "the_stat_misnamed": ('stat == "root_seconds"', 'stat == "root"'),
            "freeze_is_a_stun": ("freeze || spellId == FreezeHold ? \"control_freeze\"", "spellId == FreezeHold ? \"control_freeze\""),
            "the_hold_is_a_stun": ("freeze || spellId == FreezeHold ?", "freeze ?"),
            "blind_unread": ("if (confuse)", "if (false)"),
            "root_first": ("if (stun)", "if (stun && !root)"),
            "root_unread": ("if (root)", "if (false)"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        fire = real[real.index("inline std::vector<Fired> Fire("):]
        fire = fire[:fire.index("\n    }\n")]
        fire_rules = {
            "every_skill_refused": ("!row.fireSkills.empty() && std::find", "true || std::find"),
            "the_chance_unscaled": ("roll(row.chancePct * scale)", "roll(row.chancePct)"),
            "no_coefficient_still_rolls": ("row.chancePct * scale > 0 && ", ""),
            "cooldown_end_exclusive": ("< static_cast<std::uint32_t>(icd * 1000.0)", "<= static_cast<std::uint32_t>(icd * 1000.0)"),
        }
        for name, (old, new) in fire_rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, fire, name + " does not apply")
                want, got = self.drive(real.replace(fire, fire.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


class StockRecord(unittest.TestCase):
    """Stock 64695 "Earthgrab" in the client's Spell.dbc: one apply-aura effect, MOD_ROOT, with the Root mechanic and no other effect."""

    def test_earthgrab_is_a_plain_root(self):
        dbc = REPO / "azerothcore-wotlk/build/server/data/dbc/Spell.dbc"
        schema = REPO / "azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql"
        if not dbc.is_file() or not schema.is_file():
            raise unittest.SkipTest("no client Spell.dbc")
        columns, inside = [], False
        for line in schema.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("CREATE TABLE `spell_dbc`"):
                inside = True
            elif inside and line.startswith(")"):
                break
            elif inside and line.strip().startswith("`"):
                columns.append(line.strip().split("`")[1])
        data = dbc.read_bytes()
        _magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
        self.assertEqual(len(columns), fields)
        records = {struct.unpack_from("<I", data, 20 + i * size)[0]: struct.unpack_from("<%dI" % fields, data, 20 + i * size) for i in range(count)}
        record = dict(zip(columns, records[EARTHGRAB]))
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))   # SPELL_EFFECT_APPLY_AURA only
        self.assertEqual(26, record["EffectAura_1"])                                                # SPELL_AURA_MOD_ROOT
        self.assertEqual(7, record["Mechanic"])                                                     # MECHANIC_ROOT


if __name__ == "__main__":
    unittest.main()
