"""diablocraft-3gjoe - the follower relics' affix rolls and drop sources.

What runs: the two production headers (src/items/dc_relic_rule.h, src/loot/dc_pick_rule.h) compiled into
scripts/tests/items/relic_tests.cpp and driven with the values of the sheets, each rule killed by a mutant that must turn the
harness red; the sheets against D3 (reference/d3planner: the relics' drop level and weight, the pool of each relic kind) and
against the loot tunables (Torment I); the generator and its refusal of broken sheets; the migration against the fixture
mysqld. What does not: the roll and the drop themselves need a Player and a database, so the source guards pin that the C++
reads the tables and columns the sheets write and routes every roll and every pick through the headers; the receipt is
docs/test-diablocraft-3gjoe.md.
"""
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_follower_relics as gen  # noqa: E402
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
D3 = MODULE / "data/d3"
SRC = MODULE / "src"
RELIC_HEADER = SRC / "items/dc_relic_rule.h"
PICK_HEADER = SRC / "loot/dc_pick_rule.h"
HARNESS = MODULE / "scripts/tests/items/relic_tests.cpp"
MIGRATION = MODULE / "data/sql/db-world/updates" / gen.MIGRATION
PLANNER = REPO / "reference/d3planner"
SCRATCH = harness_env.private_scratch(REPO / "azerothcore-wotlk/build/_agent-scratch/follower_relics_test")


def sheet(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def tunable(name):
    """The effective value of a loot tunable in the generated migration: tuned, else D3's."""
    text = (MODULE / "data/generated/tunables_0012.sql").read_text(encoding="utf-8")
    match = re.search(r"\('loot', '%s', ([0-9.]+|NULL), ([0-9.]+|NULL)," % name, text)
    assert match, name + " is not in the generated tunables"
    d3_value, tuned = match.groups()
    return float(tuned if tuned != "NULL" else d3_value)


def loot_row(name):
    """A row of the loot tunables sheet: (d3_value, value, unit) as the CSV says them."""
    with (MODULE / "data/tunables/loot.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream, strict=True) if r["name"] == name]
    assert len(rows) == 1, name + " is not one row of data/tunables/loot.csv"
    return rows[0]["d3_value"], rows[0]["value"], rows[0]["unit"]


def ordinary_weight():
    """The ordinary base's drop weight the way DC::Tunables::Get reads it: tuned, else D3's."""
    d3_value, value, _ = loot_row("ordinary_drop_weight")
    return int(float(value or d3_value))


def build(include_dirs, name):
    compiler = shutil.which("c++") or shutil.which("g++")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = SCRATCH / name
    flags = ["-Wall", "-Wextra", "-Werror"] if name == "relic_tests" else []
    command = [compiler, "-std=c++17", "-O1", *flags]
    for folder in include_dirs:
        command += ["-I", str(folder)]
    built = subprocess.run(command + [str(HARNESS), "-o", str(binary)], capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
    return binary


def run(binary):
    rolls = sheet("followers_relic_rolls.csv")[0]
    return harness_env.run([str(binary), rolls["primary_affixes"], rolls["secondary_affixes"], rolls["drop_weight"],
                            rolls["min_tier"], str(int(tunable("full_roll_primary_affixes"))),
                            str(int(tunable("full_roll_secondary_affixes"))), str(ordinary_weight())],
                           capture_output=True, text=True)


# One mutation per rule: (header, what it breaks, old text, new text). Each must make the harness fail.
MUTATIONS = [
    (RELIC_HEADER, "a relic rolls its rarity's counts", "return IsRelic(relic) ? relic : rarity;", "return rarity;"),
    (RELIC_HEADER, "every base rolls the relic's counts", "return IsRelic(relic) ? relic : rarity;", "return relic;"),
    (RELIC_HEADER, "a base with no counts is a relic", "return roll.primary + roll.secondary > 0;", "return true;"),
    (RELIC_HEADER, "the switch lets a relic be Ancient when off", "return !IsRelic(relic) || ancientPrimal;", "return true;"),
    (RELIC_HEADER, "the switch never lets a relic be Ancient", "return !IsRelic(relic) || ancientPrimal;", "return !IsRelic(relic);"),
    (RELIC_HEADER, "the switch strips every base of its quality", "return !IsRelic(relic) || ancientPrimal;", "return ancientPrimal;"),
    (RELIC_HEADER, "the quality asked is ignored", "return MayBeAncient(relic, ancientPrimal) ? asked : \"normal\";",
     "return \"normal\";"),
    (RELIC_HEADER, "a relic rolls no block", "return shield || IsRelic(relic);", "return shield;"),
    (RELIC_HEADER, "every base rolls block", "return shield || IsRelic(relic);", "return true;"),
    (PICK_HEADER, "the tier gate is gone", "return tier >= candidate.minTier;", "return true;"),
    (PICK_HEADER, "the tier gate is off by one", "return tier >= candidate.minTier;", "return tier > candidate.minTier;"),
    (PICK_HEADER, "the weights are ignored", "total += candidate.weight;", "total += 1;"),
    (PICK_HEADER, "the span of a weight is cut short", "below += candidate.weight;", "below += candidate.weight / 2;"),
    (PICK_HEADER, "an empty pick returns a candidate", "if (total == 0)\n            return 0;", "if (total == 0)\n            return 1;"),
]


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which("c++") or shutil.which("g++")):
            raise unittest.SkipTest("no C++ compiler")
        cls.binary = build([RELIC_HEADER.parent, PICK_HEADER.parent], "relic_tests")

    def test_the_production_headers_pass_on_the_sheet_values(self):
        result = run(self.binary)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("relic rules OK", result.stdout)
        self.assertIn("relic counts 4+1 rarity counts 4+2", result.stdout)

    def test_a_relic_drops_a_third_as_often_as_an_ordinary_base(self):
        out = run(self.binary).stdout
        self.assertIn("relic share 9.9099% ordinary share 30.03%", out)

    def test_every_mutation_fails(self):
        for index, (header, label, old, new) in enumerate(MUTATIONS):
            with self.subTest(mutation=label):
                source = header.read_text(encoding="utf-8")
                self.assertEqual(source.count(old), 1, "mutation target moved: " + old)
                folder = SCRATCH / ("mutant_%d" % index)
                shutil.rmtree(folder, ignore_errors=True)
                folder.mkdir(parents=True)
                other = PICK_HEADER if header == RELIC_HEADER else RELIC_HEADER
                (folder / header.name).write_text(source.replace(old, new), encoding="utf-8")
                (folder / other.name).write_text(other.read_text(encoding="utf-8"), encoding="utf-8")
                result = run(build([folder], "mutant"))
                self.assertNotEqual(result.returncode, 0, label + " was not caught:\n" + result.stdout)


def planner():
    data = json.loads((PLANNER / "data.json").read_text(encoding="utf-8"))
    js = (PLANNER / "slots.js").read_text(encoding="utf-8")
    return data, js


def item_type_affixes(js, key):
    """{affix key: limit name} of d3planner's itemTypes.<key>."""
    start = js.index("DiabloCalc.itemTypes")
    block = js[js.index("\n  %s: {" % key, start):]
    block = block[:block.index("\n    },")]
    return dict(re.findall(r'(\w+): "(\w+)"', block[block.index("affixes: {"):]))


def limits(js):
    """{limit name: {bracket: (min, max)}} for the brackets the relics use (primal is ancient, ancient inherits legendary)."""
    start = js.index("DiabloCalc.statLimits")

    def block(name):
        header = "\n  %s: {" % name
        i = js.index(header, start) + len(header)
        return js[i:js.index("\n  },", i)]

    def parse(text):
        out = {}
        for m in re.finditer(r"(\w+): \{([^}]*)\}", text):
            vals = dict(re.findall(r"(\w+): ([-\d.]+)", m.group(2)))
            if "min" in vals:
                out[m.group(1)] = (float(vals["min"]), float(vals["max"]))
        return out

    legendary, ancient = parse(block("legendary")), parse(block("ancient"))
    return {"legendary": legendary, "ancient": {**legendary, **ancient}, "primal": {**legendary, **ancient}}


class Sheets(unittest.TestCase):
    def test_the_sheets_pass_the_generator(self):
        gen.render()

    def test_the_generated_files_are_the_sheets_render(self):
        text = gen.render()
        self.assertEqual(MIGRATION.read_text(encoding="utf-8"), text)
        self.assertEqual((MODULE / "data/generated" / gen.MIGRATION).read_text(encoding="utf-8"), text)

    def test_each_relic_rolls_d3s_five_properties_four_primary_and_one_secondary(self):
        rows = sheet("followers_relic_rolls.csv")
        self.assertEqual(len(rows), 9)
        for row in rows:
            self.assertEqual((row["primary_affixes"], row["secondary_affixes"]), ("4", "1"), row["d3_id"])

    def test_the_drop_weight_and_level_are_d3planners(self):
        data, _ = planner()
        drops = data["dropData"]
        ordinary = max(set(v["weight"] for v in drops.values()), key=[v["weight"] for v in drops.values()].count)
        self.assertEqual(ordinary, 100)
        self.assertEqual(loot_row("ordinary_drop_weight"), (str(ordinary), "", "count"))
        self.assertEqual(ordinary_weight(), ordinary)
        for row in sheet("followers_relic_rolls.csv"):
            drop = drops[row["d3_id"]]
            self.assertEqual(int(row["drop_weight"]), drop["weight"], row["d3_id"])
        for row in sheet("followers.csv"):
            if row["kind"] == "relic":
                self.assertEqual(int(row["drop_level"]), drops[row["skill_id"]]["level"], row["name"])

    def test_the_tier_is_torment_one_as_the_ancient_gate_has_it(self):
        sql = (MODULE / "data/sql/db-world/updates/difficulty_0001_tier_phase.sql").read_text(encoding="utf-8")
        rows = dict((name, int(tier)) for tier, _phase, name in re.findall(r"\((\d+),(\d+),'([^']+)'\)", sql))
        for row in sheet("followers_relic_rolls.csv"):
            self.assertEqual(int(row["min_tier"]), rows["Torment I"], row["d3_id"])
        self.assertEqual(int(tunable("ancient_min_tier")), rows["Torment I"])

    def test_the_item_level_of_a_relic_is_the_drop_level(self):
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"'followers\.csv','yes','','no'\)", text)), 9)
        self.assertEqual(len(re.findall(r"'legendary','',61,61,", text)), 9)

    def test_the_ancient_switch_is_on_in_the_sheet_and_this_migration_shipped_it_off(self):
        rows = [r for r in sheet("followers_relic_rules.csv") if r["rule"] == "relic_ancient_primal"]
        self.assertEqual([(r["value"], r["unit"]) for r in rows], [("1", "flag")])
        # followers_0006 is merged with the switch at 0; the designer's answer (q-1021-138 b) is written by followers_0007_rare_relics.sql.
        self.assertIn("('relic_ancient_primal',0,'flag')", MIGRATION.read_text(encoding="utf-8"))
        later = (MODULE / "data/sql/db-world/updates/followers_0007_rare_relics.sql").read_text(encoding="utf-8")
        self.assertIn("('relic_ancient_primal',1,'flag')", later)

    def test_the_pools_are_d3planners_affixes_and_ranges(self):
        data, js = planner()
        by_limit = limits(js)
        slots = js[js.index("DiabloCalc.itemSlots"):]
        follower = slots[slots.index("  follower: {"):slots.index("  head: {")]
        shared = dict(re.findall(r'(\w+): "(\w+)"', follower[follower.index("affixes: {"):]))
        rows = sheet("followers_relic_pools.csv")
        for slot, kind in (("templarrelic", "Templar Relic"), ("scoundreltoken", "Scoundrel Token"),
                           ("enchantressfocus", "Enchantress Focus")):
            own = item_type_affixes(js, slot)
            self.assertEqual(data["itemTypes"][slot]["name"], kind)
            wanted = {**own, **shared}
            mine = {r["affix_id"] for r in rows if r["slot"] == slot}
            self.assertEqual(mine, set(wanted), slot)
            for row in (r for r in rows if r["slot"] == slot):
                low, high = by_limit[row["item_level_bracket"]][wanted[row["affix_id"]]]
                self.assertEqual((float(row["value_min"]), float(row["value_max"])), (low, high),
                                 "%s %s %s" % (slot, row["affix_id"], row["item_level_bracket"]))

    def test_the_kinds_split_four_primary_to_one_secondary_where_the_pool_allows(self):
        rows = sheet("followers_relic_pools.csv")
        for slot in ("templarrelic", "scoundreltoken", "enchantressfocus"):
            kinds = {}
            for r in rows:
                if r["slot"] == slot and r["item_level_bracket"] == "legendary":
                    kinds.setdefault(r["kind"], []).append(r["affix_id"])
            self.assertGreaterEqual(len(kinds["primary"]), 4, slot)
            self.assertGreaterEqual(len(kinds["secondary"]), 1, slot)
        # The Scoundrel and the Enchantress have one secondary, so their fifth property is always Bonus Experience.
        for slot in ("scoundreltoken", "enchantressfocus"):
            secondary = [r["affix_id"] for r in rows if r["slot"] == slot and r["kind"] == "secondary"
                         and r["item_level_bracket"] == "legendary"]
            self.assertEqual(secondary, ["expadd"])
        templar = {r["affix_id"] for r in rows if r["slot"] == "templarrelic" and r["kind"] == "secondary"}
        self.assertEqual(templar, {"block", "laek", "expadd"})

    def test_the_main_stat_is_the_followers_own(self):
        rows = sheet("followers_relic_pools.csv")
        for slot, stat in (("templarrelic", "str"), ("scoundreltoken", "dex"), ("enchantressfocus", "int")):
            mains = {r["affix_id"] for r in rows if r["slot"] == slot} & {"str", "dex", "int"}
            self.assertEqual(mains, {stat}, slot)

    def test_the_primal_rows_are_the_ancient_rows(self):
        rows = sheet("followers_relic_pools.csv")
        key = lambda r: (r["slot"], r["affix_id"])
        ancient = {key(r): (r["value_min"], r["value_max"]) for r in rows if r["item_level_bracket"] == "ancient"}
        primal = {key(r): (r["value_min"], r["value_max"]) for r in rows if r["item_level_bracket"] == "primal"}
        self.assertEqual(ancient, primal)


class RefusalTests(unittest.TestCase):
    """The generator refuses a sheet that breaks a rule."""

    def with_sheet(self, name, change):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            shutil.copytree(D3, module / "data/d3")
            shutil.copy(MODULE / "data/gem_items.csv", module / "data/gem_items.csv")
            path = module / "data/d3" / name
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            fields = list(rows[0].keys())
            rows = change(rows) or rows
            with path.open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            return gen.render(module)

    def test_each_refusal(self):
        def drop(predicate):
            return lambda rows: [r for r in rows if not predicate(r)]

        def edit(predicate, **fields):
            def apply(rows):
                for r in rows:
                    if predicate(r):
                        r.update(fields)
            return apply

        first = lambda r: r.get("d3_id") == "x1_FollowerItem_Templar_Legendary_01"
        cases = [
            ("followers_relic_rolls.csv", drop(first), "one row for each of the nine"),
            ("followers_relic_rolls.csv", lambda rows: rows + [dict(rows[0])], "not a relic of followers.csv, or repeated"),
            ("followers_relic_rolls.csv", edit(first, d3_id="nonesuch"), "not a relic of followers.csv"),
            ("followers_relic_rolls.csv", edit(first, drop_weight="0"), "is not a number of at least 1"),
            ("followers_relic_rolls.csv", edit(first, primary_affixes="0", secondary_affixes="0"), "at least one affix"),
            ("followers_relic_rolls.csv", edit(first, min_tier="x"), "is not a number"),
            ("followers_relic_rolls.csv", edit(first, source=""), "source is required"),
            ("followers_relic_rules.csv", edit(lambda r: True, value="2"), "0 or 1"),
            ("followers_relic_rules.csv", edit(lambda r: True, unit="count"), "a flag"),
            ("followers_relic_rules.csv", edit(lambda r: True, rule="other"), "the rules are"),
            ("followers_relic_pools.csv", edit(lambda r: r["affix_id"] == "str" and r["item_level_bracket"] == "primal",
                                               item_level_bracket="rare"), "the bracket"),
            ("followers_relic_pools.csv", edit(lambda r: r["affix_id"] == "vit", slot="head"), "a relic slot"),
            ("followers_relic_pools.csv", edit(lambda r: r["affix_id"] == "chd", kind="tertiary"), "primary or secondary"),
            ("followers_relic_pools.csv", edit(lambda r: r["affix_id"] == "armor", value_max="1"), "value_max below value_min"),
            ("followers_relic_pools.csv", drop(lambda r: r["affix_id"] == "armor" and r["item_level_bracket"] == "ancient"),
             "holds other affixes"),
            ("followers_relic_pools.csv", lambda rows: rows + [dict(rows[0])], "repeated"),
        ]
        for name, change, message in cases:
            with self.subTest(f"{name}: {message}"):
                with self.assertRaises(ValueError) as caught:
                    self.with_sheet(name, change)
                self.assertIn(message, str(caught.exception))


def code(path):
    """Source with comments removed, so prose cannot satisfy a wiring check."""
    lines = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(("//", "*", "/*")):
            continue
        lines.append(line.split("//")[0])
    return "\n".join(lines)


class SourceGuards(unittest.TestCase):
    def test_the_server_reads_the_tables_and_columns_of_the_migration(self):
        items = code(SRC / "items/dc_items.cpp")
        for text in ("dc_follower_relic_roll", "primary_affixes", "secondary_affixes", "dc_follower_relic_rule",
                     "relic_ancient_primal", "relic->second.relicPrimary = ", "relic->second.relicSecondary = "):
            self.assertIn(text, items)
        loot = code(SRC / "loot/dc_loot.cpp")
        for text in ("SELECT item_entry, drop_weight, min_tier FROM dc_follower_relic_roll", "item.weight = fields[1]",
                     "item.minTier = fields[2]"):
            self.assertIn(text, loot)
        migration = MIGRATION.read_text(encoding="utf-8")
        for text in ("primary_affixes", "secondary_affixes", "drop_weight", "min_tier", "item_entry"):
            self.assertIn(text, migration)

    def test_an_ordinary_bases_weight_is_the_tunable_and_no_compiled_literal(self):
        header = code(PICK_HEADER)
        self.assertNotIn("OrdinaryWeight", header)
        self.assertNotRegex(header, r"\b100\b")
        self.assertIn("unsigned weight = 0;", header)
        loot = code(SRC / "loot/dc_loot.cpp")
        self.assertNotIn("OrdinaryWeight", loot)
        self.assertIn('DC::Tunables::Get("loot", "ordinary_drop_weight")', loot)
        self.assertIn("Pick::Candidate const candidate{item.entry, item.weight ? item.weight : ordinaryWeight, item.minTier};", loot)
        self.assertIn("unsigned weight = 0, minTier = 0;", loot)
        self.assertNotIn("OrdinaryWeight", (HARNESS).read_text(encoding="utf-8"))

    def test_the_ordinary_weight_row_reaches_the_tunables_migration(self):
        name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        sql = (MODULE / "data/generated" / name).read_text(encoding="utf-8")
        self.assertRegex(sql, r"\('loot', 'ordinary_drop_weight', 100(\.0)?, NULL, ")

    def test_every_roll_takes_its_counts_its_quality_and_its_block_from_the_relic_rule(self):
        roll = code(SRC / "items/dc_items_roll.cpp")
        self.assertIn("DC::Relic::Counts({base.relicPrimary, base.relicSecondary}, {rarityCounts.primary, rarityCounts.secondary})", roll)
        self.assertIn("planning.counts = {counts.primary, counts.secondary};", roll)
        self.assertIn("DC::Relic::Quality({base.relicPrimary, base.relicSecondary}, relicAncientPrimal, qualityTier)", roll)
        self.assertIn("!DC::Relic::MayBeAncient({found->second.relicPrimary, found->second.relicSecondary}, relicAncientPrimal)", roll)
        self.assertIn("DC::Relic::RollsBlock(Shield(base), {base.relicPrimary, base.relicSecondary})", roll)
        self.assertIn("DC::Relic::RollsBlock(Shield(*base), {base->relicPrimary, base->relicSecondary})", code(SRC / "items/dc_items_enchant.cpp"))

    def test_every_drop_that_has_a_tier_passes_it_and_the_gamble_and_the_cube_pass_none(self):
        loot = code(SRC / "loot/dc_loot.cpp")
        self.assertEqual(loot.count("PickBaseItem(rarity, monsterLevel, rollClass, tier)"), 2)
        self.assertIn("PickBaseItem(Rarity::Legendary, monsterLevel, rollClass, bossTier)",
                      code(SRC / "loot/dc_loot_delivery.cpp"))
        self.assertIn("PickBaseItem(Rarity::Legendary, level, rollClass, 0, &filter)", loot)
        self.assertIn("PickBaseItem(Rarity::Rare, level, rollClass, 0, &filter)", loot)
        self.assertIn("PickBaseItem(Loot::Rarity::Legendary, player->GetLevel(), rollClass, 0, &filter)",
                      code(SRC / "crafting/dc_cube.cpp"))
        self.assertIn("Pick::Choose(eligible,", loot)
        self.assertIn("Pick::Open(candidate, tier)", loot)

    def test_a_relic_is_worn_rolled_and_its_affixes_count(self):
        gear = code(SRC / "items/dc_follower_gear.cpp")
        equip = gear[gear.index("void Equip("):gear.index("void TakeOff(")]
        self.assertLess(equip.index("Detail::Load(itemGuid)"), equip.index("data.relics.find(item->GetEntry())"))
        self.assertLess(equip.index("Identify it first."), equip.index("data.relics.find(item->GetEntry())"))
        compute = gear[gear.index("Computed Compute("):]
        self.assertNotIn("data.relics.count(worn.entry)", compute[:compute.index("out.weapon.present")])


class FixtureDatabaseTests(unittest.TestCase):
    """The migration against the fixture mysqld's copy of the world (never the live one)."""

    scratch = harness_env.private_name("dc_follower_relics_test")

    @classmethod
    def setUpClass(cls):
        try:
            import fixture_db
            cls.mysql, cls.defaults = fixture_db.mysql_and_defaults([])
        except SystemExit as stopped:
            raise unittest.SkipTest(str(stopped))

    def query(self, sql, database="mysql", feed=None, check=True):
        ran = subprocess.run([self.mysql, "--defaults-file=" + self.defaults, "--no-login-paths", "-N", database] +
                             ([] if feed else ["-e", sql]), input=feed, capture_output=True, text=True)
        if check:
            self.assertEqual(ran.returncode, 0, ran.stderr)
        return [tuple(line.split("\t")) for line in ran.stdout.splitlines()], ran

    def setUp(self):
        self.query(f"DROP DATABASE IF EXISTS {self.scratch}")
        self.query(f"CREATE DATABASE {self.scratch}")
        self.addCleanup(self.query, f"DROP DATABASE IF EXISTS {self.scratch}")
        # The two tables as the migrations that create them write them (the fixture world's copies may be older).
        updates = MODULE / "data/sql/db-world/updates"
        for name, table in (("0002_dc_base_item.sql", "dc_base_item"), ("items_0040_quiver_attack_speed.sql", "dc_affix_pool")):
            text = (updates / name).read_text(encoding="utf-8")
            create = re.search(r"CREATE TABLE `%s` \(.*?\) ENGINE=[^;]*;" % table, text, re.S)
            self.assertTrue(create, name)
            self.query("", self.scratch, feed=create.group(0))

    def test_the_migration_writes_the_relics_as_base_items_with_their_pools_and_is_repeatable(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.query("INSERT INTO dc_base_item (entry, d3_id, d3_name, slot, type, rarity, usable_by, item_level, level_req, "
                   "weapon_min, weapon_max, weapon_aps, preset_affixes, set_name, source_file, pool_version, designated_class, "
                   "craft_only) VALUES (100000,'Amulet16','Amulet','neck','Amulet','','',NULL,NULL,NULL,NULL,NULL,'','','data.json',"
                   "'yes','','no')", self.scratch)
        self.query("", self.scratch, feed=sql)
        self.query("", self.scratch, feed=sql)  # applied again: the same rows
        count = lambda table: self.query(f"SELECT COUNT(*) FROM {table}", self.scratch)[0]
        self.assertEqual(count("dc_follower_relic_roll"), [("9",)])
        self.assertEqual(count("dc_follower_relic_rule"), [("1",)])
        self.assertEqual(count("dc_base_item"), [("10",)])       # the amulet it did not touch, and the nine
        self.assertEqual(count("dc_affix_pool"), [("60",)])
        rows, _ = self.query("SELECT b.entry, b.slot, b.rarity, b.pool_version, b.item_level, r.primary_affixes, r.secondary_affixes, "
                             "r.drop_weight, r.min_tier FROM dc_base_item b JOIN dc_follower_relic_roll r ON r.item_entry=b.entry "
                             "ORDER BY b.entry", self.scratch)
        self.assertEqual([r[0] for r in rows], [str(e) for e in range(103300, 103309)])
        self.assertTrue(all(r[2:] == ("legendary", "yes", "61", "4", "1", "33", "5") for r in rows), rows)
        slots, _ = self.query("SELECT DISTINCT slot FROM dc_base_item WHERE entry >= 103300 ORDER BY slot", self.scratch)
        self.assertEqual(slots, [("enchantressfocus",), ("scoundreltoken",), ("templarrelic",)])
        pools, _ = self.query("SELECT slot, item_level_bracket, COUNT(*) FROM dc_affix_pool GROUP BY slot, item_level_bracket "
                              "ORDER BY slot, item_level_bracket", self.scratch)
        self.assertEqual(pools, [("enchantressfocus", "ancient", "6"), ("enchantressfocus", "legendary", "6"),
                                 ("enchantressfocus", "primal", "6"), ("scoundreltoken", "ancient", "6"),
                                 ("scoundreltoken", "legendary", "6"), ("scoundreltoken", "primal", "6"),
                                 ("templarrelic", "ancient", "8"), ("templarrelic", "legendary", "8"),
                                 ("templarrelic", "primal", "8")])


if __name__ == "__main__":
    unittest.main()
