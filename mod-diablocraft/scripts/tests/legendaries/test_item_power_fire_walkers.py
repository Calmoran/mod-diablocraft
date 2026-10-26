"""Legendary 058, bead diablocraft-4na3e: Fire Walkers (boots, any class), which builds N-AREA (a patch of fire an item leaves on the ground) and
its first effect, `burn_trail`.

  "Burn the ground you walk on, dealing [300-400]% weapon damage each second." (d3planner item_feet.js, leg_firewalkers_p2)
  * the item's number is the damage per second, rolled once per item; the clock and the patch come from its Power file (decode_pow.py power
    ItemPassive_Unique_Boots_007_p2): SF_2 drop payload interval 0.2 is the row's icd_seconds, SF_4 proxy duration 1.5 and SF_5 damage radius 5 are
    the combat tunables fire_walkers_patch_seconds and fire_walkers_radius_yards, each its D3 value; SF_1 DoT duration and SF_3 damage pulse interval
    are not built (the burn is paid at the drop clock) and the file's ProcCoefficient is 0;
  * the table (data/legendary_powers.csv) holds ONE row: an `effect` row `burn_trail` [300-400] fired on `tick` every 0.2 seconds; the generator
    refuses the row half built;
  * the fire is dealt under the hit record 83561 'Burn the Ground' (data/legendary_power_buffs.csv `hit`, element fire, generate_spells.py), in the
    spell header, the shell manifest and the combat migration;
  * the production rules (src/combat/dc_item_power_math.h: Fire on `tick`; src/combat/dc_item_trail_math.h: Drop, Burns, Reach, PulseSeconds, PulsePct)
    are compiled and driven with the generated row: the clock fires once per 0.2 seconds while the item is worn, a patch drops only while the wearer
    moves and burns 1.5 seconds, an enemy burns within 5 yards of any live patch (once however many cover it), the pulse pays the seconds since the last
    one so the per-second number holds;
  * mutants of the rules and of the row fail the same driver; the source-text guards on the executor (outside the lock), the trail file (the
    tunables by name, the one search, ComputeHit/DealHit and never Strike so the fire cannot proc, the clear on logout) and the shell load in
    dc_combat.cpp, with their source mutants, are in test_item_power_fire_walkers_wiring.py. The C++ is compile-checked by syntax_check.sh; the
    in-game steps are in docs/test-diablocraft-4na3e.md.
"""
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402
import generate_tunables  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
TRAIL_MATH = SRC / "combat/dc_item_trail_math.h"
HARNESS = MODULE / "tests/item_power_fire_walkers/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SPELL_MIGRATION = MODULE / "data/sql/db-world/updates/combat_0089_fire_walkers_trail.sql"
OWNER = "Unique_Boots_007_p2"
STAT = "burn_trail"
EVENT = "tick"
RECORD = 83561
POWER = "ItemPassive_Unique_Boots_007_p2"
TUNABLES = {"fire_walkers_radius_yards": ("5", "yards"), "fire_walkers_patch_seconds": ("1.5", "seconds")}
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def decoded():
    """{SF label: value} of the boots' Power file, read from the client MPQs by the decoder; skips where they are not on the machine."""
    run = subprocess.run([sys.executable, "-I", str(MODULE / "scripts/decode_pow.py"), "power", POWER], capture_output=True, text=True)
    if run.returncode or "SF_" not in run.stdout:
        raise unittest.SkipTest("the decoder cannot read the client MPQs here: " + (run.stderr or run.stdout)[-200:])
    numbers = {m[1]: float(m[2]) for m in re.finditer(r"SF_\d+ '([^']+)' = ([\d.]+)", run.stdout)}
    numbers["ProcCoefficient"] = float(re.search(r"ProcCoefficient = ([\d.]+)", run.stdout)[1])
    return numbers


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not there exactly once" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


def source(name):
    """A server file's text; empty when it does not exist yet (a branch without the trail file reads red, not a crash)."""
    path = SRC / "combat" / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


class Table(unittest.TestCase):
    def test_the_words_are_the_planners_and_the_item_is_a_pool_legendary(self):
        text = (REPO / "reference/d3planner/item_feet.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n", text.index("preset", start))]
        self.assertIn('custom: {id: "leg_firewalkers_p2", name: "Burn the Ground", format: "Burn the ground you walk on, dealing %d%% weapon damage each second.", '
                      'min: 300, max: 400}', item)
        row = next(r for r in read_csv(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Burn the ground you walk on, dealing [300-400]% weapon damage each second.", "K3"), (row["power_text"], row["kind"]))
        base = next(r for r in read_csv(MODULE / "data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Fire Walkers", "feet", "legendary", "yes"), (base["d3_name"], base["slot"], base["rarity"], base["pool_version"]))

    def test_the_power_file_numbers(self):
        sf = decoded()
        self.assertEqual({"DoT duration": 1.0, "Drop payload interval": 0.2, "Damage pulse interval": 0.3, "Proxy duration": 1.5, "Damage radius": 5.0,
                          "ProcCoefficient": 0.0}, sf)

    def test_one_effect_row_fired_on_the_drop_clock_and_rolled_per_item(self):
        self.assertEqual([(OWNER, 0, "effect", "", STAT, 300.0, 400.0, "", 0.0, "", 0.0, 0, EVENT, "", 100.0, 0.2)], mine())

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv(MODULE / "data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertEqual(("", ""), (rows[0]["chance_pct"], rows[0]["fire_skills"]))
        for need in ("item_feet.js", "leg_firewalkers_p2", POWER, "diablocraft-4na3e"):
            self.assertIn(need, rows[0]["source"])
        self.assertTrue(rows[0]["note"])

    def test_the_tunables_are_the_power_files_numbers(self):
        sheet = {r["name"]: r for r in read_csv(MODULE / "data/tunables/combat.csv")}
        for name, (d3, unit) in TUNABLES.items():
            row = sheet[name]
            self.assertEqual((d3, "", unit), (row["d3_value"], row["value"], row["unit"]), name + " is D3's number, not a tuned one")
            self.assertIn(POWER, row["notes"])
            self.assertIn("diablocraft-4na3e", row["notes"])
        migration = (MODULE / "data/sql/db-world/updates" / generate_tunables.current_migration(MODULE)).read_text(encoding="utf-8")
        for name in TUNABLES:
            self.assertIn("('combat', '%s', " % name, migration)

    def test_the_hit_record(self):
        record = next(r for r in read_csv(MODULE / "data/legendary_power_buffs.csv") if r["owner"] == OWNER)
        self.assertEqual((str(RECORD), STAT, "hit", "Burn the Ground", "", "fire"),
                         (record["spell_id"], record["stat"], record["aura"], record["name"], record["text"], record["element"]))
        self.assertIn('{%d, "%s", "%s"},' % (RECORD, OWNER, STAT), (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"))
        self.assertIn("%d,Burn the Ground,fire," % RECORD, (MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8"))
        # the migration is the render that added the record, and a later record's render (immutable once applied) carries it on
        sql = SPELL_MIGRATION.read_text(encoding="utf-8")
        self.assertRegex(sql, r"\(%d,0,0,0,\d+," % RECORD)
        self.assertRegex((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), r"\(%d,0,0,0,\d+," % RECORD)
        ids = [int(r["spell_id"]) for r in read_csv(MODULE / "data/legendary_power_buffs.csv")]
        self.assertEqual(len(ids), len(set(ids)), "a record id is used twice")


class Generator(unittest.TestCase):
    BURN = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "300", "value_max": "400", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": EVENT, "fire_skills": "", "chance_pct": "",
            "icd_seconds": "0.2", "source": "s", "note": "n"}

    def render_with(self, change, record=True):
        """The generator run on a copy of the module whose sheet is the real one with the owner's row replaced (None leaves it out)."""
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="firewalkers-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            buffs = read_csv(MODULE / "data/legendary_power_buffs.csv")
            with (work / "data/legendary_power_buffs.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(buffs[0].keys()))
                writer.writeheader()
                writer.writerows(b for b in buffs if record or b["owner"] != OWNER)
            sheet = read_csv(MODULE / "data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + ([{**self.BURN, **change}] if change is not None else []))
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "on another event": ({"fire_on": "hit", "icd_seconds": ""}, STAT),
            "no event": ({"fire_on": "", "icd_seconds": ""}, "need a fire_on event"),
            "a clock with no period": ({"icd_seconds": ""}, "tick is the clock"),
            "a clock that rolls": ({"chance_pct": "50"}, "tick is the clock"),
            "a zero damage": ({"value_min": "0", "value_max": "0"}, STAT),
            "a backwards range": ({"value_min": "400", "value_max": "300"}, STAT),
            "on a set level": ({"owner": "Immortal King's Call", "pieces": "2"}, STAT),
            "naming a skill": ({"skill": "Bash"}, "a skill is named"),
            "a condition": ({"cond": "triggered", "cond_arg": "3"}, STAT),
            "an unknown effect": ({"stat": "burn_trails"}, "an effect stat is one of"),
        }
        for name, (change, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(change)

    def test_it_refuses_the_row_without_its_hit_record(self):
        with self.assertRaisesRegex(ValueError, "needs its hit record"):
            self.render_with({}, record=False)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, headers, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/" + file: text for file, text in headers.items()}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemfirewalkers-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    @staticmethod
    def headers(**changed):
        out = {"dc_item_power_math.h": MATH.read_text(encoding="utf-8"), "dc_item_trail_math.h": source("dc_item_trail_math.h")}
        out.update({k.replace("__", "."): v for k, v in changed.items()})
        return out

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and its Power file's numbers, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        period = 200   # SF_2, the drop payload interval, in milliseconds
        patch = 1500   # SF_4, the proxy duration
        radius = 5
        # the clock: not worn, or only in the bag, fires nothing; worn with no stored roll, nothing (a ranged row with no roll gives no power)
        out += [(T("clear"), None), (T("now", 5000), None), (T("fire", EVENT), "")]
        out += [(T("clear"), None), (T("bag", OWNER), None), (T("now", 5000), None), (T("fire", EVENT), "")]
        out += [(T("clear"), None), (T("wears", OWNER), None), (T("now", 5000), None), (T("fire", EVENT), "")]
        # worn: at once with the item's rolled damage, then once per drop interval, the end exact; asking in between fires nothing
        for roll in (300, 350, 400, 333.5):
            did = "%s=%s;" % (STAT, g(roll))
            out += [(T("clear"), None), (T("wears", OWNER, roll), None), (T("now", 1000), None), (T("fire", EVENT), did)]
            for k in (1, 2, 3):
                out += [(T("now", 1000 + k * period - 1), None), (T("fire", EVENT), ""), (T("now", 1000 + k * period), None), (T("fire", EVENT), did)]
        # a late ask fires once, and the next period counts from it
        out += [(T("now", 1000 + 3 * period + 900), None), (T("fire", EVENT), did), (T("now", 1000 + 3 * period + 900 + period - 1), None), (T("fire", EVENT), ""),
                (T("now", 1000 + 3 * period + 900 + period), None), (T("fire", EVENT), did)]
        # the clock is its own: no other event fires the fire
        out += [(T("clear"), None), (T("wears", OWNER, 350), None), (T("now", 1000), None)]
        out += [(T("fire", e), "") for e in ("hit", "cast", "taken", "kill", "kill_elite", "life_below", "land", "")]
        # a patch drops only while the wearer moves, and goes out after its seconds, the end exact
        out += [(T("clear"), None), (T("forget"), None), (T("now", 1000), None), (T("drop", patch, 1, 0, 0, 0, 0), "1|1"),
                (T("now", 1200), None), (T("drop", patch, 1, 0, 10, 0, 0), "1|2"),
                (T("now", 1400), None), (T("drop", patch, 0, 0, 20, 0, 0), "0|2"),            # stood still: nothing dropped, nothing out yet
                (T("now", 2499), None), (T("drop", patch, 0, 0, 20, 0, 0), "0|2"),            # the first has one millisecond left
                (T("now", 2500), None), (T("drop", patch, 0, 0, 20, 0, 0), "0|1"),            # gone at its end
                (T("now", 2700), None), (T("drop", patch, 0, 0, 20, 0, 0), "0|0"),
                (T("now", 3000), None), (T("drop", 0, 1, 0, 0, 0, 0), "0|0")]                  # a patch that lasts no time is not dropped
        # an enemy burns within the radius of a live patch on its map, in three dimensions, the end exact
        out += [(T("forget"), None), (T("now", 1000), None), (T("drop", patch, 1, 1, 100, 200, 10), "1|1")]
        for where, want in (((1, 100, 200, 10), 1), ((1, 105, 200, 10), 1), ((1, 105.01, 200, 10), 0), ((1, 103, 204, 10), 1), ((1, 103, 204.1, 10), 0),
                            ((1, 100, 200, 15), 1), ((1, 100, 200, 15.5), 0), ((1, 100, 200, 5), 1), ((1, 100, 200, 4.5), 0), ((2, 100, 200, 10), 0), ((0, 100, 200, 10), 0)):
            out.append((T("burns", *where, radius), str(want)))
        out += [(T("burns", 1, 100, 200, 10, 0), "0"), (T("burns", 1, 100, 200, 10, -1), "0")]    # no radius: nothing burns
        out += [(T("now", 2499), None), (T("burns", 1, 100, 200, 10, radius), "1"), (T("now", 2500), None), (T("burns", 1, 100, 200, 10, radius), "0")]
        # two patches: standing between them, in reach of neither alone, burns only when the radius covers the half gap
        out += [(T("forget"), None), (T("now", 1000), None), (T("drop", patch, 1, 1, 0, 0, 0), "1|1"), (T("drop", patch, 1, 1, 12, 0, 0), "1|2"),
                (T("burns", 1, 6, 0, 0, 5), "0"), (T("burns", 1, 6, 0, 0, 6), "1"), (T("burns", 1, 0, 0, 0, 5), "1"), (T("burns", 1, 12, 0, 0, 5), "1")]
        # a patch that wraps the clock's end still burns until its time and not after
        out += [(T("forget"), None), (T("now", 4294967000), None), (T("drop", patch, 1, 1, 0, 0, 0), "1|1"), (T("now", 4294967200), None), (T("burns", 1, 0, 0, 0, radius), "1"),
                (T("now", 1203), None), (T("burns", 1, 0, 0, 0, radius), "1"), (T("now", 1204), None), (T("burns", 1, 0, 0, 0, radius), "0")]
        # the reach: the farthest live patch of this map from the wearer, plus the radius
        out += [(T("forget"), None), (T("now", 1000), None), (T("drop", patch, 1, 1, 3, 0, 0), "1|1"), (T("drop", patch, 1, 1, 0, 8, 0), "1|2"),
                (T("drop", patch, 1, 2, 20, 0, 0), "1|3"), (T("reach", 1, 0, 0, 0, radius), "13"), (T("reach", 2, 0, 0, 0, radius), "25"),
                (T("reach", 3, 0, 0, 0, radius), "0"), (T("reach", 1, 0, 0, 0, 0), "0"), (T("reach", 1, 0, 0, 3, radius), g(math_hypot(8, 3) + radius)),
                (T("now", 2500), None), (T("reach", 1, 0, 0, 0, radius), "0")]
        # the pulse pays the seconds since the last one, a period at the first and past twice the period
        for last, now, want in ((0, 5000, 0.2), (1000, 1200, 0.2), (1000, 1250, 0.25), (1000, 1199, 0.199), (1000, 1400, 0.4), (1000, 1401, 0.2), (1000, 1000, 0.2),
                                (4294967200, 100, 0.196), (4294967200, 4294967295, 0.095)):
            out.append((T("pulse", last, now, 0.2), g(want)))
        out.append((T("pulse", 1000, 1200, 0), "0"))
        # the damage is the item's percent per second for those seconds: the drop interval's pulses add up to the number each second
        for per_second, seconds, want in ((350, 0.2, 70), (300, 1, 300), (400, 0.25, 100), (333.5, 0.2, 66.7), (350, 0, 0), (0, 0.2, 0), (-5, 0.2, 0), (350, -0.2, 0)):
            out.append((T("pct", per_second, seconds), g(want)))
        return out

    def drive(self, headers, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(headers, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item(self):
        want, got = self.drive(self.headers(), mine(), "real")
        self.assertGreater(len(want), 100)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "another_event": [r[:12] + ("hit",) + r[13:] for r in rows],
            "period_one": [r[:15] + (1.0,) for r in rows],
            "no_period": [r[:15] + (0.0,) for r in rows],
            "another_effect": [r[:4] + ("drain_life",) + r[5:] for r in rows],
            "no_roll": [r[:6] + (0.0, 0.0) + r[8:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(self.headers(), mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        trail = source("dc_item_trail_math.h")
        trail_mutants = {
            "a_patch_dies_one_late": ("static_cast<std::int32_t>(patch.until - now) > 0", "static_cast<std::int32_t>(patch.until - now) >= 0"),
            "the_clock_wrap_ignored": ("static_cast<std::int32_t>(patch.until - now) > 0", "patch.until > now"),
            "drops_while_still": ("if (!moving || patchMs == 0)", "if (patchMs == 0)"),
            "drops_with_no_time": ("if (!moving || patchMs == 0)", "if (!moving)"),
            "never_pruned": ("patches.erase(std::remove_if(patches.begin(), patches.end(), [now](Patch const& patch) { return !Alive(patch, now); }),\n                      patches.end());", ""),
            "a_short_patch": ("now + patchMs}", "now + patchMs / 2}"),
            "burns_on_another_map": ("patch.map == map && Alive(patch, now) && Distance", "Alive(patch, now) && Distance"),
            "burns_from_a_dead_patch": ("patch.map == map && Alive(patch, now) && Distance", "patch.map == map && Distance"),
            "radius_exclusive": ("Distance(patch, x, y, z) <= radius", "Distance(patch, x, y, z) < radius"),
            "burns_with_no_radius": ("return radius > 0 && std::any_of", "return std::any_of"),
            "ignores_height": ("double const dx = patch.x - x, dy = patch.y - y, dz = patch.z - z;", "double const dx = patch.x - x, dy = patch.y - y, dz = 0;"),
            "reach_without_the_radius": ("return farthest < 0 ? 0.0 : farthest + radius;", "return farthest < 0 ? 0.0 : farthest;"),
            "reach_to_the_nearest": ("farthest = std::max(farthest, Distance(patch, x, y, z));", "farthest = farthest < 0 ? Distance(patch, x, y, z) : std::min(farthest, Distance(patch, x, y, z));"),
            "reach_counts_a_dead_patch": ("if (patch.map == map && Alive(patch, now))\n                farthest", "if (patch.map == map)\n                farthest"),
            "reach_of_another_map": ("if (patch.map == map && Alive(patch, now))\n                farthest", "if (Alive(patch, now))\n                farthest"),
            "the_pulse_is_always_a_period": ("return gap > 0 && gap <= 2 * periodSeconds ? gap : periodSeconds;", "return periodSeconds;"),
            "the_pulse_pays_any_gap": ("return gap > 0 && gap <= 2 * periodSeconds ? gap : periodSeconds;", "return gap > 0 ? gap : periodSeconds;"),
            "the_pulse_clock_wrap_ignored": ("static_cast<std::int32_t>(now - last) / 1000.0", "(now > last ? now - last : 0) / 1000.0"),
            "damage_ignores_the_seconds": ("perSecondPct * seconds : 0.0", "perSecondPct : 0.0"),
            "a_negative_damage_pays": ("return perSecondPct > 0 && seconds > 0 ?", "return seconds > 0 ?"),
        }
        for name, (old, new) in trail_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(self.headers(dc_item_trail_math__h=mutate(trail, old, new)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        power = MATH.read_text(encoding="utf-8")
        fire = power[power.index("inline std::vector<Fired> Fire("):]
        fire = fire[:fire.index("\n    }\n")]
        fire_rules = {
            "period_is_the_number": ('row.stat == "cast_skill" ? (number > 0 ? number : situation.castCooldownSeconds) : row.icdSeconds', "number"),
            "period_end_exclusive": ("< static_cast<std::uint32_t>(icd * 1000.0)", "<= static_cast<std::uint32_t>(icd * 1000.0)"),
            "unworn_fires": ("!Owned(row, counts, situation, number)", "false"),
            "any_event_fires": ("row.fireOn != fireOn ||", "false ||"),
        }
        for name, (old, new) in fire_rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, fire.count(old), name + " does not apply once")
                want, got = self.drive(self.headers(dc_item_power_math__h=power.replace(fire, fire.replace(old, new))), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def math_hypot(*parts):
    return sum(p * p for p in parts) ** 0.5


if __name__ == "__main__":
    unittest.main()
