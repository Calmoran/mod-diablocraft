"""Legendary rest, bead diablocraft-4y1jn: Gloves of Worship (gloves, list row 69, K6), and the piece it builds, N-PYLONDUR.

  "Shrine effects last for 10 minutes. (Emanates)"
  * the words are d3planner's (data.json items[7], Unique_Gloves_103_x1: custom leg_glovesofworship, args 0: no number in the text); the number is the power file's, read through
    decode_pow.py (Item_Power_Passive ItemPassive_Unique_Ring_521_x1.pow: the item's own number 1; SF_0 'Shrine Buff Duration' = 600, ten minutes). The table
    (data/legendary_powers.csv) holds ONE row for the gloves: the `player` `shrine_seconds` 600;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts `shrine_seconds` only as an
    item's one fixed number of seconds above 0, simply on;
  * the production rule (src/combat/dc_item_power_math.h: PlayerSetTo) is compiled and driven with the generated row: a shrine lasts its own seconds, or the worn gloves' 600 when
    that is more, and never fewer than its own; the gloves not worn, or another item's, change nothing; mutants of the row and the rule fail the same driver;
  * source-text guards that Pylons::Give reads the worn seconds for a shrine and never for a pylon, over the kind's own seconds, and that the reader is the rule over the
    player's rows. The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-4y1jn.md.
  * The "Emanates" half (a follower wearing the gloves) is not built: it needs a follower's item slots, and the follower lane has no item reader.
"""
import csv
import json
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
PYLONS = SRC / "combat/dc_pylons.cpp"
READERS = SRC / "combat/dc_item_powers_readers.cpp"
HARNESS = MODULE / "tests/item_power_gloves_of_worship/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Gloves_103_x1"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731
SECONDS = 600.0


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_shrine_effects_last_10_minutes(self):
        items = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"]
        item = next(i for i in items if i.get("id") == OWNER)
        self.assertEqual("Gloves of Worship", item["name"])
        self.assertEqual("Shrine effects last for 10 minutes. (Emanates)", item["required"]["custom"]["format"])
        self.assertEqual(0, item["required"]["custom"]["args"])
        self.assertIn("Shrine effects last for 10 minutes.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_number(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda *a: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), *a], capture_output=True, text=True).stdout  # noqa: E731
        self.assertRegex(run("power", "ItemPassive_Unique_Ring_521_x1"), r"'Shrine Buff Duration' = 600\b")
        self.assertIn("ItemPassive_Unique_Ring_521_x1.pow: 1", run("item", OWNER))
        self.assertEqual(10 * 60, SECONDS)

    def test_one_row_for_the_gloves(self):
        self.assertEqual([(OWNER, 0, "player", "", "shrine_seconds", SECONDS, SECONDS, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)], mine())

    def test_every_shrine_is_shorter_than_the_gloves(self):
        """The gloves lengthen: the tunable seconds of each shrine are below 600 (a longer shrine would be kept, not shortened)."""
        for r in read_csv("data/tunables/combat.csv"):
            if re.fullmatch(r"shrine_[a-z]+_seconds", r["name"]):
                self.assertLess(float(r["d3_value"]), SECONDS, r["name"])

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0067_table.sql")


class Generator(unittest.TestCase):
    ROW = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": "shrine_seconds", "value_min": "600", "value_max": "600", "cond": "", "cond_arg": "",
           "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, edits=None, drop=False):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="gloves-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            added = [] if drop else [{**self.ROW, **(edits or {})}]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + added)
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with() if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a range": dict(value_max="700"),
            "no seconds": dict(value_min="0", value_max="0"),
            "negative seconds": dict(value_min="-5", value_max="-5"),
            "a condition": dict(cond="triggered", cond_arg="5"),
            "an event": dict(fire_on="hit"),
            "a set level": dict(pieces="2"),
            "a skill": dict(kind="skill", skill="Frenzy"),
        }
        for name, edits in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edits)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        for other in ("dc_item_proc_math.h", "dc_proc_math.h"):
            files["combat/" + other] = (SRC / "combat" / other).read_text(encoding="utf-8")
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemgloves-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the power file's number, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = clear + [(T("wears", OWNER), None)]
        # worn: every shrine's own seconds (the sheet's two minutes, a minute, nothing, a long one) is lifted to 600, never lowered
        for own, want in ((120, 600), (60, 600), (1, 600), (599.99, 600), (600, 600), (600.01, 600.01), (900, 900), (3600, 3600), (0, 600)):
            out += wear + [(T("shrine", own), g(want))]
        # not worn: the shrine's own seconds, whatever they are; another owner's gloves; the gloves in the bag
        for own in (120, 0, 900):
            out += clear + [(T("shrine", own), g(own))]
            out += clear + [(T("wears", "Other Gloves"), None), (T("shrine", own), g(own))]
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
        self.assertGreater(len(want), 14)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        only = rows[0]
        row_mutants = {
            "five_minutes": [only[:5] + (300.0, 300.0) + only[7:]],
            "another_stat": [only[:4] + ("shrine_second",) + only[5:]],
            "another_kind": [only[:2] + ("skill",) + only[3:]],
            "no_row": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        start = real.index("inline double PlayerSetTo(")
        body = real[start:real.index("\n    }\n", start)]
        for name, (old, new) in {
            "the_lower_wins": ("if (value > base)", "if (value < base)"),
            "the_row_always_wins": ("if (value > base)", "if (true)"),
            "the_own_seconds_win": ("base = value;", ";"),
            "another_stat_is_read": ('"player", "", stat, situation', '"player", "", "shrine_second", situation'),
            "a_skill_stat_is_read": ('"player", "", stat, situation', '"skill", "", stat, situation'),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, body.count(old), name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1), 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def give_failures(pylons, readers):
    """What is wrong with the shrine's seconds in Pylons::Give and the reader behind it ([] when it is right)."""
    flat = re.sub(r"\s+", " ", pylons)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    start = flat.find("bool Give(Player* target, Kind kind) {")
    end = flat.find("bool GiveRandomShrine", start)
    body = flat[start:end] if start >= 0 and end > start else ""
    need("Give exists", bool(body))
    need("the kind's own seconds are the sheet's and gate the give", 'double const own = Tune(Row(kind, "seconds")); if (!target || !record || own <= 0) return false;' in body)
    need("a shrine takes the worn seconds over its own, a pylon keeps its own",
         "double const seconds = IsPylon(kind) ? own : ItemPowers::ShrineSeconds(target, own);" in body)
    need("the seconds are read after the give gate", body.find("own <= 0") < body.find("ItemPowers::ShrineSeconds(target, own)"))
    need("the aura is set to the seconds, both the longest and the left",
         "aura->SetMaxDuration(static_cast<int32>(seconds * 1000)); aura->SetDuration(static_cast<int32>(seconds * 1000));" in body)
    need("the pylon's knock-up lasts the pylon's seconds", "knockUp->SetMaxDuration(static_cast<int32>(seconds * 1000));" in body)
    need("the item powers header is included", '#include "dc_item_powers.h"' in pylons)
    reader = re.sub(r"\s+", " ", readers)
    at = reader.find("double ShrineSeconds(Player const* player, double base) {")
    reading = reader[at:reader.find("double PetSpeedFactor", at)] if at >= 0 else ""
    need("the reader exists", bool(reading))
    need("no player leaves the shrine's own seconds", "if (!player) return base;" in reading)
    need("the reader is the rule over the player's rows, under the lock, for shrine_seconds",
         'std::lock_guard<std::mutex> lock(mutex);' in reading and
         'ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), "shrine_seconds", base, SituationOf(guid, std::move(seen)))' in reading)
    return wrong


class Hooks(unittest.TestCase):
    def test_give_and_the_reader(self):
        self.assertEqual([], give_failures(PYLONS.read_text(encoding="utf-8"), READERS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        pylons = PYLONS.read_text(encoding="utf-8")
        readers = READERS.read_text(encoding="utf-8")
        mutants_pylons = {
            "a_pylon_is_lengthened": ("IsPylon(kind) ? own : ItemPowers::ShrineSeconds(target, own);", "ItemPowers::ShrineSeconds(target, own);"),
            "a_shrine_is_not": ("IsPylon(kind) ? own : ItemPowers::ShrineSeconds(target, own);", "own;"),
            "the_base_is_zero": ("ItemPowers::ShrineSeconds(target, own)", "ItemPowers::ShrineSeconds(target, 0.0)"),
            "the_gate_reads_the_worn_seconds": ("if (!target || !record || own <= 0)", "if (!target || !record)"),
            "the_aura_keeps_the_own_seconds": ("aura->SetDuration(static_cast<int32>(seconds * 1000));\n        if (kind == Kind::Empowered)", "aura->SetDuration(static_cast<int32>(own * 1000));\n        if (kind == Kind::Empowered)"),
            "no_include": ('#include "dc_item_powers.h"\n', ""),
        }
        for name, (old, new) in mutants_pylons.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, pylons.count(old), name + " does not apply")
                self.assertNotEqual([], give_failures(pylons.replace(old, new, 1), readers), name + " survived")
        mutants_readers = {
            "another_stat": ('"shrine_seconds", base', '"shrine_second", base'),
            "no_player_guard": ("            return base;\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        return ItemPower::PlayerSetTo(", "            return base;\n        ItemPower::Situation seen = Seen(player);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        return ItemPower::PlayerSetTo("),
            "a_factor_instead": ("ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), \"shrine_seconds\", base,", "ItemPower::PlayerFactor(Data().rows, CountsOf(guid), \"shrine_seconds\","),
        }
        for name, (old, new) in mutants_readers.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, readers.count(old), name + " does not apply")
                self.assertNotEqual([], give_failures(pylons, readers.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
