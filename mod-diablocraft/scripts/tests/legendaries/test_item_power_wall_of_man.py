"""Legendary rest, bead diablocraft-44hz9: Wall of Man (an off-hand shield, list row 67, K3), and the piece it builds, N-ABSGRANT; rebuilt by diablocraft-upwsv.

  "[20-30]% chance to be protected by a shield of bones when you are hit."
  * the words and the range are d3planner's (item_offhand.js, Unique_Shield_011_x1: custom leg_wallofman, min 20 max 30: the power file holds no chance); the numbers are the file's,
    read through decode_pow.py (itemPassive_Unique_Shield_011: SF_0 'Shield Duration' = 8, SF_1 'Shield Absorb Percentage' = 0.25, SF_2 'Cooldown Duration' = 20, SF_6 '' = 0.1).
    The table (data/legendary_powers.csv) holds FOUR rows: the `effect` `bone_shield` [20-30] on `taken` (the chance, rolled once per item), the fixed `player` rows
    `bone_shield_seconds` 8 and `bone_shield_cooldown_seconds` 20, and the fixed `buff` `damage_reduction_pct` 25. The protection's aura is the item's `damage_reduction_pct`
    record in legendary_power_buffs.csv (83563, a dummy aura that states the 25 as $s1);
  * **the designer's reading (card q-1021-91 (a)).** Not a Life shield: while the protection lasts every hit taken is 25% smaller. The file's 'Shield Absorb Percentage' 0.25 is that 25%;
    the blank tunable wall_of_man_shield_pct_of_max_life is retired (the tunables render deletes it);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts `bone_shield` only as an item's
    chance on `taken` with both companion rows and its absorb record, and the companion rows only beside it;
  * the production rules (src/combat/dc_item_power_math.h: Fire, CooldownOver, StackedFactor; dc_proc_math.h: Rolls) are compiled and driven with the generated rows: a monster's
    hit fires the effect with the wearer's roll, nothing else does; the wait is 20 seconds, the end inclusive and right across the clock's wrap; every hit taken is multiplied by
    0.75 while the aura stands and by 1 when it does not (or the shield is not worn); the chance is the roll scaled by the hit's proc coefficient; mutants of the rows and the rules
    fail the same driver;
  * source-text guards that the executor rolls only when a protection could be put, starts the wait only for a protection, and puts the record's aura for the seconds. The C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-44hz9.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
EFFECTS = SRC / "combat/dc_item_powers_effects.cpp"
HARNESS = MODULE / "tests/item_power_wall_of_man/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Shield_011_x1"
STAT = "bone_shield"
SECONDS, COOLDOWN = 8.0, 20.0
TUNABLE = "wall_of_man_shield_pct_of_max_life"          # retired
REDUCTION = 25.0
RECORD = 83563
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_twenty_to_thirty_percent_to_be_protected_by_a_shield_of_bones(self):
        text = (REPO / "reference/d3planner/item_offhand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('format: "%d%% chance to be protected by a shield of bones when you are hit.", min: 20, max: 30', item)
        self.assertIn("[20-30]% chance to be protected by a shield of bones when you are hit.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_numbers_and_no_base(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        power = harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", "itemPassive_Unique_Shield_011"], capture_output=True, text=True).stdout
        for label, number in (("Shield Duration", "8"), ("Shield Absorb Percentage", "0.25"), ("Cooldown Duration", "20")):
            self.assertRegex(power, r"'%s' = %s\b" % (label, number.replace(".", r"\.")))

    def test_four_rows_for_the_protection(self):
        self.assertEqual([
            (OWNER, 0, "effect", "", STAT, 20.0, 30.0, "", 0.0, "", 0.0, 0, "taken", "", 100.0, 0.0),
            (OWNER, 0, "buff", "", "damage_reduction_pct", REDUCTION, REDUCTION, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (OWNER, 0, "player", "", "bone_shield_cooldown_seconds", COOLDOWN, COOLDOWN, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (OWNER, 0, "player", "", "bone_shield_seconds", SECONDS, SECONDS, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
        ], sorted(mine(), key=lambda r: (r[2] != "effect", r[2], r[4])))

    def test_the_25_is_the_power_files_and_alexs_reading(self):
        for row in (r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == "damage_reduction_pct"):
            self.assertIn("SF_1 'Shield Absorb Percentage' = 0.25", row["source"])
            self.assertIn("q-1021-91", row["source"])

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0067_table.sql")


class Record(unittest.TestCase):
    def test_the_reduction_record_is_in_the_sheet_the_render_the_header_and_the_migration(self):
        buffs = [r for r in read_csv("data/legendary_power_buffs.csv") if r["owner"] == OWNER]
        self.assertEqual([(str(RECORD), "damage_reduction_pct", "dummy", "Wall of Man")], [(r["spell_id"], r["stat"], r["aura"], r["name"]) for r in buffs])
        self.assertEqual("Damage taken reduced by $s1%.", buffs[0]["text"])
        shells = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        columns = re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\)", shells)[1].replace("`", "").split(", ")
        line = next(l for l in shells.splitlines() if l.startswith("(%d," % RECORD))
        cells = line.rstrip(",;")[1:-1].split(",")
        at = lambda name: cells[columns.index(name)]   # noqa: E731
        self.assertEqual(("6", "4"), (at("Effect_1"), at("EffectAura_1")))                        # APPLY_AURA, DUMMY: no absorb any more
        self.assertEqual(str(int(REDUCTION) - 1), at("EffectBasePoints_1"))                        # $s1 = base + die = 25
        self.assertIn("{%d, \"%s\", \"damage_reduction_pct\"}" % (RECORD, OWNER), (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"))
        self.assertNotIn('"bone_shield"}', (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"))
        self.assertTrue(list((MODULE / "data/sql/db-world/updates").glob("combat_01*_wall_of_man_damage_reduction_record.sql")))
        self.assertNotIn("absorb", (MODULE / "scripts/generate/classes/generate_spells.py").read_text(encoding="utf-8").split("def power_buff_stacks")[1].split("def pylon_tunable")[0])

    def test_the_blank_shield_tunable_is_retired(self):
        self.assertEqual([], [r for r in read_csv("data/tunables/combat.csv") if r["name"] == TUNABLE])
        import generate_tunables as tunables
        self.assertIn(("combat", TUNABLE), tunables.RETIRED)
        rendered = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        sql = (MODULE / "data/sql/db-world/updates" / rendered).read_text(encoding="utf-8")
        self.assertIn("DELETE FROM `dc_tunables` WHERE `category` = 'combat' AND `name` = '%s';" % TUNABLE, sql)
        self.assertNotIn("('combat', '%s'," % TUNABLE, sql)
        for path in (SRC / "combat").glob("*.cpp"):
            self.assertNotIn(TUNABLE, path.read_text(encoding="utf-8"), path.name)


class Generator(unittest.TestCase):
    EFFECT = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "20", "value_max": "30", "cond": "", "cond_arg": "",
              "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "taken", "fire_skills": "", "chance_pct": "", "icd_seconds": "",
              "source": "s", "note": "n"}
    COMPANIONS = {"bone_shield_seconds": "8", "bone_shield_cooldown_seconds": "20"}
    BUFF = {**EFFECT, "kind": "buff", "stat": "damage_reduction_pct", "value_min": "25", "value_max": "25", "fire_on": ""}

    def render_with(self, effect=None, companions=None, drop=(), record=True, buff=True, buff_edits=None):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="wall-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            buffs = read_csv("data/legendary_power_buffs.csv")
            with (work / "data/legendary_power_buffs.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(buffs[0].keys()))
                writer.writeheader()
                writer.writerows(b for b in buffs if record or b["owner"] != OWNER)
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            added = [{**self.EFFECT, **(effect or {})}]
            if buff:
                added.append({**self.BUFF, **(buff_edits or {})})
            for stat, number in self.COMPANIONS.items():
                if stat not in drop:
                    added.append({**self.EFFECT, "kind": "player", "stat": stat, "value_min": number, "value_max": number, "fire_on": "", **((companions or {}).get(stat, {}))})
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + added)
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(4, len([r for r in self.render_with() if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "on a hit": dict(effect={"fire_on": "hit"}),
            "on a kill": dict(effect={"fire_on": "kill"}),
            "named skills": dict(effect={"fire_skills": "Frenzy"}),
            "a chance column": dict(effect={"chance_pct": "25"}),
            "a cooldown column": dict(effect={"icd_seconds": "20"}),
            "a condition": dict(effect={"cond": "triggered", "cond_arg": "5"}),
            "a set level": dict(effect={"pieces": "2"}),
            "no chance": dict(effect={"value_min": "0", "value_max": "0"}),
            "a chance over 100": dict(effect={"value_min": "50", "value_max": "150"}),
            "no seconds row": dict(drop=("bone_shield_seconds",)),
            "no cooldown row": dict(drop=("bone_shield_cooldown_seconds",)),
            "a seconds range": dict(companions={"bone_shield_seconds": {"value_max": "10"}}),
            "a cooldown on an event": dict(companions={"bone_shield_cooldown_seconds": {"fire_on": "taken"}}),
            "no reduction record": dict(record=False),
            "no reduction row": dict(buff=False),
            "a reduction range": dict(buff_edits={"value_max": "30"}),
            "a reduction over the whole hit": dict(buff_edits={"value_min": "100", "value_max": "100"}),
        }
        for name, edits in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(**edits)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        for other in ("dc_item_proc_math.h", "dc_proc_math.h"):
            files["combat/" + other] = (SRC / "combat" / other).read_text(encoding="utf-8")
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemwall-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the power file's numbers, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        cool = int(COOLDOWN * 1000)
        # a monster's hit fires the effect with the wearer's roll, whatever the skill name says
        for roll in (20, 25.5, 30):
            wear = clear + [(T("wears", OWNER), None), (T("rolled", OWNER, "", STAT, roll), None), (T("now", 5000), None)]
            out += wear + [(T("fire", "taken", "", 1, 0), "%s:%g" % (STAT, roll))]
            for event in ("hit", "kill", "block", "tick", "chest", "taken_element", "takens", ""):
                out += wear + [(T("fire", event, "", 1, 0), "none")]
        out += clear + [(T("wears", OWNER), None), (T("fire", "taken", "", 1, 0), "none")]
        out += clear + [(T("rolled", OWNER, "", STAT, 25), None), (T("fire", "taken", "", 1, 0), "none")]
        out += clear + [(T("wears", "Other Shield"), None), (T("rolled", "Other Shield", "", STAT, 25), None), (T("fire", "taken", "", 1, 0), "none")]
        # the wait: none before the first shield; 20 seconds after one, the end inclusive; right across the clock's wrap
        for now, started, last, want in ((100000, 0, 0, 1), (100000, 0, 100000, 1), (100000, 1, 100000, 0), (100001, 1, 100000, 0), (100000 + cool - 1, 1, 100000, 0),
                                         (100000 + cool, 1, 100000, 1), (500, 1, 4294967000, 0), (19703, 1, 4294967000, 0), (19704, 1, 4294967000, 1), (1000 + 2592000000, 1, 1000, 1)):
            out.append((T("cooldown", now, started, last, COOLDOWN), str(want)))
        out += [(T("cooldown", 100000, 1, 100000, 0), "1"), (T("cooldown", 100000, 1, 100000, -5), "1")]
        # what the protection takes off: every hit taken x 0.75 while the aura stands (one stack), x 1 when it does not or when the shield is not worn
        keep = 1 - REDUCTION / 100
        out += clear + [(T("wears", OWNER), None), (T("incoming", 1, OWNER), "%.10g" % keep), (T("incoming", 0, OWNER), "1"), (T("incoming", 1, "Other Shield"), "1"),
                        (T("incoming", 2, OWNER), "%.10g" % (1 - 2 * REDUCTION / 100))]
        out += clear + [(T("incoming", 1, OWNER), "1")]                                        # the aura without the shield worn: no cut
        out += clear + [(T("wears", "Other Shield"), None), (T("incoming", 1, OWNER), "1")]
        # the chance: the roll scaled by the hit's proc coefficient (a monster's hit is 1), falling on a draw below it
        for chance, coefficient, draw, want in ((20, "1", 19.99, 1), (20, "1", 20, 0), (30, "1", 29.99, 1), (30, "1", 30, 0), (25, "0.5", 12.49, 1), (25, "0.5", 12.5, 0),
                                                (25, "-", 0, 0), (25, "0", 0, 0), (0, "1", 0, 0)):
            out.append((T("chance", chance, coefficient, draw), str(want)))
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
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(4, len(rows))
        want, _ = self.drive(real, rows, "want")
        effect = [r for r in rows if r[2] == "effect"][0]
        buff = [r for r in rows if r[2] == "buff"][0]
        others = [r for r in rows if r[2] != "effect"]
        row_mutants = {
            "another_event": [effect[:12] + ("hit",) + effect[13:]] + others,
            "a_fixed_chance": [effect[:5] + (25.0, 25.0) + effect[7:]] + others,
            "the_cut_halved": [effect] + [r if r is not buff else buff[:5] + (12.5, 12.5) + buff[7:] for r in others],
            "no_cut": [effect] + [r for r in others if r is not buff],
            "another_stat": [effect] + [r if r is not buff else buff[:4] + ("armor_pct",) + buff[5:] for r in others],
            "no_row": others,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        for name, (old, new) in {
            "the_wait_end_is_exclusive": ("return !started || (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);", "return !started || (now - last) > static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);"),
            "the_wait_is_in_seconds": ("return !started || (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);", "return !started || (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds));"),
            "the_wrap_blocks_the_shield": ("return !started || (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);", "return !started || (now >= last && (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0));"),
            "the_first_shield_waits": ("return !started || (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);", "return (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);"),
            "no_wait": ("return !started || (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);", "return true;"),
            "the_cut_is_added": ("factor *= std::max(0.0, 1.0 + sign * held->second * number / 100.0);", "factor *= std::max(0.0, 1.0 - sign * held->second * number / 100.0);"),
            "the_cut_ignores_the_stacks": ("factor *= std::max(0.0, 1.0 + sign * held->second * number / 100.0);", "factor *= std::max(0.0, 1.0 + sign * number / 100.0);"),
            "the_cut_without_the_aura": ("auto held = stacks.find(row.owner);\n            double number = 0;\n            if (held != stacks.end() &&", "auto held = stacks.find(row.owner);\n            double number = 0;\n            if (true &&"),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def shield_failures(effects):
    """What is wrong with the shield executor in `effects` ([] when it is right)."""
    flat = re.sub(r"\s+", " ", effects)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    start = flat.find("void BoneShield(Player* player, ItemPower::Row const& row, double chancePct, double coefficient) {")
    need("the executor exists", start >= 0)
    end = flat.find("// N-FEAR", start)
    body = flat[start:end] if start >= 0 and end > start else ""
    for stat in ("bone_shield_seconds", "bone_shield_cooldown_seconds"):
        need("the %s row is the item's" % stat, 'ItemPower::OwnerNumber(Data().rows, row.owner, "player", "%s")' % stat in body)
    need("the record is the item's damage_reduction_pct aura", 'Shells::PowerBuffFor(row.owner.c_str(), "damage_reduction_pct")' in body)
    need("no record, no seconds or a dead wearer put nothing and roll nothing", "if (!player->IsAlive() || !record || seconds <= 0) return;" in body)
    need("no Life shield is left: no tunable, no amount, no absorb", not any(word in body for word in ("Tunables", "amount", "ChangeAmount", "ShieldFactor", "BoneShieldAmount")))
    need("the wait has its own key", 'std::string const key = row.owner + "|shield";' in body)
    need("the wait is judged first, then the chance, under the lock",
         "std::lock_guard<std::mutex> lock(mutex);" in body and
         "if (!ItemPower::CooldownOver(now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) || "
         "!Proc::Rolls(coefficient, chancePct, [](float pct) { return roll_chance_f(pct); })) return;" in body)
    need("the wait starts only for a shield", "return; fired[key] = now; }" in body)
    need("the protection is the record's aura for the seconds",
         "player->AddAura(record, player)" in body and "aura->SetMaxDuration(static_cast<std::int32_t>(seconds * 1000.0));" in body and
         "aura->SetDuration(static_cast<std::int32_t>(seconds * 1000.0));" in body)
    need("the branch is the bone_shield stat with its row at the hit's coefficient", 'else if (one.stat == "bone_shield" && one.row) BoneShield(player, *one.row, one.value, scale);' in flat)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_shield_executor(self):
        self.assertEqual([], shield_failures(EFFECTS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        real = EFFECTS.read_text(encoding="utf-8")
        mutants = {
            "no_seconds_row": ('"player", "bone_shield_seconds")', '"player", "bone_shield_secs")'),
            "no_cooldown_row": ('"player", "bone_shield_cooldown_seconds")', '"player", "bone_shield_cooldown")'),
            "another_record": ('Shells::PowerBuffFor(row.owner.c_str(), "damage_reduction_pct")', 'Shells::PowerBuffFor(row.owner.c_str(), "bone_shield")'),
            "no_seconds_still_rolls": ("|| !record || seconds <= 0)", "|| !record)"),
            "the_shield_is_back": ("SetDuration(static_cast<std::int32_t>(seconds * 1000.0));\n            }\n        }\n\n        // N-FEAR", "SetDuration(static_cast<std::int32_t>(seconds * 1000.0));\n                aura->GetEffect(EFFECT_0)->ChangeAmount(1000);\n            }\n        }\n\n        // N-FEAR"),
            "the_events_key": ('row.owner + "|shield"', "ItemPower::FireKey(row)"),
            "no_wait_check": ("!ItemPower::CooldownOver(now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) ||", ""),
            "the_chance_ignores_the_coefficient": ("CooldownOver(now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) ||\n                    !Proc::Rolls(coefficient, chancePct,", "CooldownOver(now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) ||\n                    !Proc::Rolls(1.0, chancePct,"),
            "a_failed_roll_starts_the_wait": ("                    return;\n                fired[key] = now;\n            }\n            if (Aura* aura = player->AddAura(record, player))", "                    fired[key] = now;\n                fired[key] = now;\n            }\n            if (Aura* aura = player->AddAura(record, player))"),
            "no_duration": ("player->AddAura(record, player))\n            {\n                aura->SetMaxDuration(static_cast<std::int32_t>(seconds * 1000.0));", "player->AddAura(record, player))\n            {"),
            "not_dispatched": ('one.stat == "bone_shield" && one.row', 'one.stat == "bone_shields" && one.row'),
            "ignores_the_hit_coefficient": ("BoneShield(player, *one.row, one.value, scale);", "BoneShield(player, *one.row, one.value, 1.0);"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], shield_failures(real.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
