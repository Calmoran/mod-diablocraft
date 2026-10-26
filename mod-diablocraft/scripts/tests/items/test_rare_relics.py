"""diablocraft-vucek - the Blacksmith-crafted rare follower relics.

What runs: the two production headers (src/items/dc_relic_rule.h, src/items/dc_roll_class.h) compiled into
scripts/tests/items/rare_relic_tests.cpp and driven with the values of the sheets and of the migration, each rule killed by a
mutant that must turn the harness red; the sheets against the game's own Blacksmith recipes
(docs/research/blacksmith-recipe-coverage.csv), against d3planner (the Rare bracket of each relic kind) and against the loot
tunables (a Rare's full budget); the generator and its refusal of broken sheets; the switch flipped in a copy of the sheets; the
migration against the fixture mysqld. What does not: the craft and the roll themselves need a Player and a database, so the source
guards pin that the C++ reads the tables and columns the sheets write; the receipt is docs/test-diablocraft-vucek.md.
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
import generate_rare_relics as gen  # noqa: E402
import generate_follower_relics as legendary_gen  # noqa: E402
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
D3 = MODULE / "data/d3"
SRC = MODULE / "src"
RELIC_HEADER = SRC / "items/dc_relic_rule.h"
ROLL_CLASS_HEADER = SRC / "items/dc_roll_class.h"
HARNESS = MODULE / "scripts/tests/items/rare_relic_tests.cpp"
MIGRATION = MODULE / "data/sql/db-world/updates" / gen.MIGRATION
PLANNER = REPO / "reference/d3planner"
COVERAGE = REPO / "docs/research/blacksmith-recipe-coverage.csv"
SCRATCH = harness_env.private_scratch(REPO / "azerothcore-wotlk/build/_agent-scratch/rare_relics_test")
KINDS = {"templar": "Templar", "scoundrel": "Scoundrel", "enchantress": "Enchantress"}


def sheet(name, folder=D3):
    with (folder / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def tunable(name):
    """The effective value of a loot tunable in the generated migration: tuned, else D3's."""
    text = (MODULE / "data/generated/tunables_0012.sql").read_text(encoding="utf-8")
    match = re.search(r"\('loot', '%s', ([0-9.]+|NULL), ([0-9.]+|NULL)," % name, text)
    assert match, name + " is not in the generated tunables"
    d3_value, tuned = match.groups()
    return float(tuned if tuned != "NULL" else d3_value)


def build(include_dirs, name):
    compiler = shutil.which("c++") or shutil.which("g++")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = SCRATCH / name
    flags = ["-Wall", "-Wextra", "-Werror"] if name == "rare_relic_tests" else []
    command = [compiler, "-std=c++17", "-O1", *flags]
    for folder in include_dirs:
        command += ["-I", str(folder)]
    built = subprocess.run(command + [str(HARNESS), "-o", str(binary)], capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
    return binary


def switch():
    return [r["value"] for r in sheet("followers_relic_rules.csv") if r["rule"] == gen.SWITCH][0]


def migration_craft_only():
    return sorted(set(re.findall(r"'followers_rare_relics\.csv','yes','',('(?:yes|no)')\)", MIGRATION.read_text(encoding="utf-8"))))


def run(binary, craft_only=None, drops=None):
    own = sheet("followers_rare_relics.csv")[0]
    only = craft_only or migration_craft_only()[0].strip("'")
    return harness_env.run([str(binary), own["primary_affixes"], own["secondary_affixes"],
                            str(int(tunable("full_roll_primary_affixes"))), str(int(tunable("full_roll_secondary_affixes"))),
                            only, str(drops if drops is not None else switch())], capture_output=True, text=True)


# One mutation per rule: (header, what it breaks, old text, new text). Each must make the harness fail.
MUTATIONS = [
    (RELIC_HEADER, "a rare relic rolls the rarity's counts", "return IsRelic(relic) ? relic : rarity;", "return rarity;"),
    (RELIC_HEADER, "every base rolls the relic's counts", "return IsRelic(relic) ? relic : rarity;", "return relic;"),
    (RELIC_HEADER, "a base with no counts is a relic", "return roll.primary + roll.secondary > 0;", "return true;"),
    (RELIC_HEADER, "a relic rolls no block", "return shield || IsRelic(relic);", "return shield;"),
    (RELIC_HEADER, "every base rolls block", "return shield || IsRelic(relic);", "return true;"),
    (ROLL_CLASS_HEADER, "a craft_only base drops", 'return poolVersion == "yes" && craftOnly != "yes" && rarity != "ethereal";',
     'return poolVersion == "yes" && rarity != "ethereal";'),
    (ROLL_CLASS_HEADER, "nothing drops once the switch is on", 'return poolVersion == "yes" && craftOnly != "yes" && rarity != "ethereal";',
     'return false;'),
]


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which("c++") or shutil.which("g++")):
            raise unittest.SkipTest("no C++ compiler")
        cls.binary = build([RELIC_HEADER.parent], "rare_relic_tests")

    def test_the_production_headers_pass_on_the_sheet_values(self):
        result = run(self.binary)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rare relic rules OK", result.stdout)
        self.assertIn("rare relic counts 4+2", result.stdout)
        self.assertIn("rare relic in drop pool yes", result.stdout)

    def test_the_switch_puts_the_rare_relic_in_the_drop_pool_or_keeps_it_out_both_ways(self):
        on = run(self.binary, craft_only="no", drops=1)
        self.assertEqual(on.returncode, 0, on.stdout + on.stderr)
        self.assertIn("rare relic in drop pool yes", on.stdout)
        off = run(self.binary, craft_only="yes", drops=0)
        self.assertEqual(off.returncode, 0, off.stdout + off.stderr)
        self.assertIn("rare relic in drop pool no", off.stdout)
        self.assertNotEqual(run(self.binary, craft_only="yes", drops=1).returncode, 0, "the migration must follow the switch")
        self.assertNotEqual(run(self.binary, craft_only="no", drops=0).returncode, 0, "the migration must follow the switch")

    def test_every_mutation_fails(self):
        for index, (header, label, old, new) in enumerate(MUTATIONS):
            with self.subTest(mutation=label):
                source = header.read_text(encoding="utf-8")
                self.assertEqual(source.count(old), 1, "mutation target moved: " + old)
                folder = SCRATCH / ("mutant_%d" % index)
                shutil.rmtree(folder, ignore_errors=True)
                folder.mkdir(parents=True)
                for other in (RELIC_HEADER, ROLL_CLASS_HEADER):
                    (folder / other.name).write_text(source.replace(old, new) if other == header
                                                     else other.read_text(encoding="utf-8"), encoding="utf-8")
                result = run(build([folder], "mutant"))
                self.assertNotEqual(result.returncode, 0, label + " was not caught:\n" + result.stdout)


def coverage_row(recipe):
    with COVERAGE.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["recipe"] == recipe]
    assert len(rows) == 1, recipe
    return rows[0]


def planner():
    data = json.loads((PLANNER / "data.json").read_text(encoding="utf-8"))
    js = (PLANNER / "slots.js").read_text(encoding="utf-8")
    return data, js


class Sheets(unittest.TestCase):
    def test_the_sheets_pass_the_generator(self):
        gen.render()

    def test_the_generated_files_are_the_sheets_render(self):
        text = gen.render()
        self.assertEqual(MIGRATION.read_text(encoding="utf-8"), text)
        self.assertEqual((MODULE / "data/generated" / gen.MIGRATION).read_text(encoding="utf-8"), text)

    def test_the_legendary_relics_migration_is_unchanged_by_the_new_switch_row(self):
        text = legendary_gen.render()
        self.assertEqual((MODULE / "data/sql/db-world/updates" / legendary_gen.MIGRATION).read_text(encoding="utf-8"), text)
        self.assertNotIn(gen.SWITCH, text)

    def test_each_recipe_is_the_game_files_level_12_recipe_of_its_follower(self):
        rows = sheet("followers_rare_relics.csv")
        self.assertEqual([r["key"] for r in rows], list(KINDS))
        for row in rows:
            game = coverage_row("T12_Armor_%sSpecial" % KINDS[row["key"]])
            where = row["key"]
            self.assertEqual(row["recipe_sno"], game["recipe_sno"], where)
            self.assertEqual(row["d3_id"], game["output_d3_id"], where)
            self.assertEqual((game["artisan_level"], game["gold"]), ("12", row["gold"]), where)
            self.assertEqual((row["item_level"], row["required_level"]), (game["item_level"], game["required_level"]), where)
            self.assertEqual(game["additional_affixes"], "6", where)
            costs = {i["d3_id"]: i["amount"] for i in json.loads(game["ingredients"])}
            self.assertEqual(costs, {"Crafting_AssortedParts_01": int(row["reusable_parts"]),
                                     "Crafting_Magic_01": int(row["arcane_dust"]),
                                     "Crafting_Rare_01": int(row["veiled_crystals"])}, where)

    def test_the_cost_is_the_launch_sovereign_cost(self):
        sovereign = [r for r in sheet("blacksmith_recipes.csv") if r["row_type"] == "recipe" and r["slot"] == "head"][0]
        for row in sheet("followers_rare_relics.csv"):
            self.assertEqual((row["reusable_parts"], row["arcane_dust"], row["veiled_crystals"], row["gold"]),
                             (sovereign["reusable_parts"], sovereign["arcane_dust"], sovereign["veiled_crystals"],
                              sovereign["gold"]), row["key"])
            self.assertEqual(sovereign["deaths_breath"], "0")
            self.assertEqual(sovereign["level"], row["required_level"])

    def test_a_rare_relic_rolls_a_rares_full_budget_and_the_tier_sheet_says_so(self):
        tiers = [r for r in sheet("rarity_tiers.csv") if r["rarity"].startswith("Rare")]
        self.assertEqual(len(tiers), 1)
        text = " ".join(tiers[0].values())
        self.assertIn("max 4 primary + 2 secondary", text)
        for row in sheet("followers_rare_relics.csv"):
            self.assertEqual((int(row["primary_affixes"]), int(row["secondary_affixes"])),
                             (int(tunable("full_roll_primary_affixes")), int(tunable("full_roll_secondary_affixes"))))

    def test_the_materials_are_the_catalogues_own_entries(self):
        materials = {r["d3_id"]: r["item_entry"] for r in sheet("blacksmith_catalog_materials.csv")}
        text = MIGRATION.read_text(encoding="utf-8")
        for d3_id in ("Crafting_AssortedParts_01", "Crafting_Magic_01", "Crafting_Rare_01"):
            self.assertEqual(len(re.findall(r"\(36237[789],'%s',%s,15\)" % (d3_id, materials[d3_id]), text)), 3, d3_id)

    def test_each_recipe_is_a_new_one_and_each_item_the_next_free_entry(self):
        old = {r["recipe_sno"] for r in sheet("blacksmith_catalog.csv")}
        rows = sheet("followers_rare_relics.csv")
        self.assertFalse(old & {r["recipe_sno"] for r in rows})
        self.assertEqual([int(r["item_entry"]) for r in rows], [103309, 103310, 103311])

    def test_the_rare_pools_are_d3planners_rare_bracket(self):
        data, js = planner()
        start = js.index("DiabloCalc.statLimits")
        header = "\n  rare: {"
        block = js[js.index(header, start) + len(header):]
        block = block[:block.index("\n  },")]
        limits = {m.group(1): (float(re.search(r"min: ([-\d.]+)", m.group(2)).group(1)),
                               float(re.search(r"max: ([-\d.]+)", m.group(2)).group(1)))
                  for m in re.finditer(r"(\w+): \{([^}]*)\}", block) if "min" in m.group(2)}
        slots = js[js.index("DiabloCalc.itemSlots"):]
        follower = slots[slots.index("  follower: {"):slots.index("  head: {")]
        shared = dict(re.findall(r'(\w+): "(\w+)"', follower[follower.index("affixes: {"):]))
        rows = sheet("followers_rare_relic_pools.csv")
        for slot, kind in (("templarrelic", "templarrelic"), ("scoundreltoken", "scoundreltoken"),
                           ("enchantressfocus", "enchantressfocus")):
            start_type = js.index("DiabloCalc.itemTypes")
            body = js[js.index("\n  %s: {" % kind, start_type):]
            body = body[:body.index("\n    },")]
            own = dict(re.findall(r'(\w+): "(\w+)"', body[body.index("affixes: {"):]))
            wanted = {**own, **shared}
            mine = {r["affix_id"] for r in rows if r["slot"] == slot}
            self.assertEqual(mine, set(wanted), slot)
            for row in (r for r in rows if r["slot"] == slot):
                low, high = limits[wanted[row["affix_id"]]]
                self.assertEqual((float(row["value_min"]), float(row["value_max"])), (low, high), "%s %s" % (slot, row["affix_id"]))
        self.assertEqual(data["itemTypes"]["templarrelic"]["name"], "Templar Relic")

    def test_the_four_shared_affixes_are_the_follower_slots_rare_rows(self):
        shared = {(r["affix_id"], r["value_min"], r["value_max"]) for r in sheet("affix_pools.csv")
                  if r["slot"] == "follower" and r["item_level_bracket"] == "rare"}
        self.assertEqual(len(shared), 4)
        for slot in ("templarrelic", "scoundreltoken", "enchantressfocus"):
            mine = {(r["affix_id"], r["value_min"], r["value_max"]) for r in sheet("followers_rare_relic_pools.csv")
                    if r["slot"] == slot}
            self.assertTrue(shared <= mine, slot)

    def test_the_scoundrel_and_the_enchantress_have_one_secondary_so_they_roll_four_and_one(self):
        rows = sheet("followers_rare_relic_pools.csv")
        for slot in ("scoundreltoken", "enchantressfocus"):
            self.assertEqual([r["affix_id"] for r in rows if r["slot"] == slot and r["kind"] == "secondary"], ["expadd"])
            self.assertGreaterEqual(len([r for r in rows if r["slot"] == slot and r["kind"] == "primary"]), 4)
        templar = {r["affix_id"] for r in rows if r["slot"] == "templarrelic" and r["kind"] == "secondary"}
        self.assertEqual(templar, {"block", "laek", "expadd"})

    def test_both_switches_are_on_as_alex_answered(self):
        rules = {r["rule"]: (r["value"], r["unit"]) for r in sheet("followers_relic_rules.csv")}
        # q-1021-138 (b): the relics may roll Ancient and Primal; q-1021-140 (b): the rare relics also drop.
        self.assertEqual(rules, {"relic_ancient_primal": ("1", "flag"), gen.SWITCH: ("1", "flag")})
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(migration_craft_only(), ["'no'"])
        self.assertEqual(len(re.findall(r"'followers_rare_relics\.csv','yes','','no'\)", text)), 3)
        self.assertIn("('relic_ancient_primal',1,'flag'),\n('rare_relic_drops',1,'flag')", text)

    def test_both_switches_off_write_the_rare_relics_craft_only_and_the_relics_legendary_only(self):
        text = self.render_with(ancient="0", drops="0")
        self.assertEqual(len(re.findall(r"'followers_rare_relics\.csv','yes','','yes'\)", text)), 3)
        self.assertIn("('relic_ancient_primal',0,'flag'),\n('rare_relic_drops',0,'flag')", text)
        self.assertNotIn("'yes','','no')", text)

    def test_each_switch_alone_moves_only_its_own_row(self):
        only_ancient = self.render_with(ancient="1", drops="0")
        self.assertIn("('relic_ancient_primal',1,'flag'),\n('rare_relic_drops',0,'flag')", only_ancient)
        self.assertEqual(len(re.findall(r"'yes','','yes'\)", only_ancient)), 3)
        only_drops = self.render_with(ancient="0", drops="1")
        self.assertIn("('relic_ancient_primal',0,'flag'),\n('rare_relic_drops',1,'flag')", only_drops)
        self.assertEqual(len(re.findall(r"'yes','','no'\)", only_drops)), 3)

    def render_with(self, ancient, drops):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            shutil.copytree(D3, module / "data/d3")
            shutil.copy(MODULE / "data/gem_items.csv", module / "data/gem_items.csv")
            path = module / "data/d3/followers_relic_rules.csv"
            rows = list(csv.reader(path.open(encoding="utf-8", newline="")))
            for row in rows[1:]:
                row[1] = ancient if row[0] == "relic_ancient_primal" else drops
            with path.open("w", encoding="utf-8", newline="") as out:
                csv.writer(out, lineterminator="\n").writerows(rows)
            return gen.render(module)

    def test_the_legendary_generator_still_renders_what_it_shipped_whatever_the_sheet_says(self):
        self.assertIn("('relic_ancient_primal',0,'flag')", legendary_gen.render())


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

        first = lambda r: r.get("key") == "templar"
        cases = [
            ("followers_rare_relics.csv", drop(first), "one row for each of"),
            ("followers_rare_relics.csv", edit(first, item_entry="103400"), "is not the next free one"),
            ("followers_rare_relics.csv", edit(first, item_entry="100004"), "is not the next free one"),
            ("followers_rare_relics.csv", edit(first, recipe_sno="362322"), "already a Blacksmith recipe"),
            ("followers_rare_relics.csv", edit(first, item_level="71"), "1 to 70"),
            ("followers_rare_relics.csv", edit(first, primary_affixes="0", secondary_affixes="0"), "at least one affix"),
            ("followers_rare_relics.csv", edit(first, arcane_dust="0"), "is not a number of at least 1"),
            ("followers_rare_relics.csv", edit(first, source=""), "source are required"),
            ("followers_rare_relics.csv", edit(first, displayid="0"), "displayid"),
            ("followers_relic_rules.csv", edit(lambda r: r["rule"] == gen.SWITCH, value="2"), "0 or 1"),
            ("followers_relic_rules.csv", edit(lambda r: r["rule"] == gen.SWITCH, unit="count"), "a flag"),
            ("followers_relic_rules.csv", drop(lambda r: r["rule"] == gen.SWITCH), "one rare_relic_drops row"),
            ("followers_rare_relic_pools.csv", edit(lambda r: r["affix_id"] == "vit", slot="head"), "a relic slot"),
            ("followers_rare_relic_pools.csv", edit(lambda r: r["affix_id"] == "vit", item_level_bracket="legendary"), "the bracket rare"),
            ("followers_rare_relic_pools.csv", edit(lambda r: r["affix_id"] == "armor", value_max="1"), "value_max below value_min"),
            ("followers_rare_relic_pools.csv", drop(lambda r: r["affix_id"] == "armor"), "other affixes than the legendary"),
            ("followers_rare_relic_pools.csv", lambda rows: rows + [dict(rows[0])], "repeated"),
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
    def test_the_craft_reads_the_catalogue_and_the_base_the_migration_writes(self):
        craft = code(SRC / "crafting/dc_crafting_shared.cpp")
        for text in ("FROM dc_blacksmith_catalog WHERE id={}", "FROM dc_blacksmith_catalog_material WHERE recipe_id={}",
                     "SELECT entry FROM dc_base_item WHERE entry={} AND pool_version='yes'", "StageRoll(player, entry, level, rarity,"):
            self.assertIn(text, craft)
        migration = MIGRATION.read_text(encoding="utf-8")
        for text in ("dc_blacksmith_catalog (id,output_entry,name,slot,category,page,rarity,item_level,required_level,gold_d3,enabled,"
                     "unavailable_reason)", "dc_blacksmith_catalog_material (recipe_id,d3_id,item_entry,amount)"):
            self.assertIn(text, migration)

    def test_the_catalogue_columns_are_the_ones_crafting_0006_creates(self):
        create = (MODULE / "data/sql/db-world/updates/crafting_0006_blacksmith_catalog.sql").read_text(encoding="utf-8")
        for column in ("id INT UNSIGNED", "output_entry", "gold_d3", "unavailable_reason", "recipe_id", "item_entry", "amount"):
            self.assertIn(column, create)

    def test_the_drop_pool_reads_craft_only_and_the_roll_reads_the_relic_counts(self):
        loot = code(SRC / "loot/dc_loot.cpp")
        self.assertIn("b.craft_only", loot)
        self.assertIn("DC::RollClass::InDropPool(rarity, fields[7].Get<std::string>(), fields[8].Get<std::string>(),", loot)
        items = code(SRC / "items/dc_items.cpp")
        self.assertIn("SELECT item_entry, primary_affixes, secondary_affixes FROM dc_follower_relic_roll", items)
        roll = code(SRC / "items/dc_items_roll.cpp")
        self.assertIn("DC::Relic::Counts({base.relicPrimary, base.relicSecondary}, {rarityCounts.primary, rarityCounts.secondary})", roll)
        self.assertIn("DC::Relic::RollsBlock(Shield(base), {base.relicPrimary, base.relicSecondary})", roll)

    def test_a_rare_relic_is_worn_through_the_same_relic_table(self):
        gear = code(SRC / "items/dc_follower_gear.cpp")
        self.assertIn("SELECT item_entry, follower_id, power FROM dc_follower_relic", gear)
        self.assertIn("data.relics.find(item->GetEntry())", gear)


class FixtureDatabaseTests(unittest.TestCase):
    """The migration against the fixture mysqld's copy of the world (never the live one)."""

    scratch = harness_env.private_name("dc_rare_relics_test")

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
        updates = MODULE / "data/sql/db-world/updates"
        # The tables as the migrations that create them write them (the fixture world's copies may be older).
        for name, table in (("0002_dc_base_item.sql", "dc_base_item"), ("items_0040_quiver_attack_speed.sql", "dc_affix_pool")):
            text = (updates / name).read_text(encoding="utf-8")
            create = re.search(r"CREATE TABLE `%s` \(.*?\) ENGINE=[^;]*;" % table, text, re.S)
            self.assertTrue(create, name)
            self.query("", self.scratch, feed=create.group(0))
        catalogue = (updates / "crafting_0006_blacksmith_catalog.sql").read_text(encoding="utf-8")
        for create in re.findall(r"CREATE TABLE IF NOT EXISTS dc_blacksmith_catalog[^;]*;", catalogue):
            self.query("", self.scratch, feed=create)
        self.query("CREATE TABLE item_template (entry INT UNSIGNED NOT NULL PRIMARY KEY, class TINYINT UNSIGNED NOT NULL, "
                   "subclass TINYINT UNSIGNED NOT NULL, name VARCHAR(255) NOT NULL, displayid INT UNSIGNED NOT NULL, "
                   "Quality TINYINT UNSIGNED NOT NULL, Flags INT UNSIGNED NOT NULL, BuyCount TINYINT UNSIGNED NOT NULL, "
                   "BuyPrice BIGINT NOT NULL, SellPrice INT UNSIGNED NOT NULL, InventoryType TINYINT UNSIGNED NOT NULL, "
                   "maxcount INT NOT NULL, stackable INT NOT NULL, BagFamily INT UNSIGNED NOT NULL, bonding TINYINT UNSIGNED "
                   "NOT NULL, ItemLevel SMALLINT UNSIGNED NOT NULL, description VARCHAR(255) NOT NULL)", self.scratch)
        # The relic tables the earlier migrations create: followers_0005 (dc_follower_relic) and followers_0006.
        for name in ("followers_0005_gear.sql", "followers_0006_relic_rolls.sql"):
            text = (updates / name).read_text(encoding="utf-8")
            for create in re.findall(r"CREATE TABLE IF NOT EXISTS dc_follower_relic[^;]*;", text):
                self.query("", self.scratch, feed=create)

    def test_the_migration_writes_the_rare_relics_and_is_repeatable(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        # followers_0006 has written the Ancient switch at 0 by now; this migration moves it to the sheet's 1.
        self.query("INSERT INTO dc_follower_relic_rule VALUES ('relic_ancient_primal',0,'flag')", self.scratch)
        self.query("", self.scratch, feed=sql)
        self.query("", self.scratch, feed=sql)  # applied again: the same rows
        count = lambda table: self.query(f"SELECT COUNT(*) FROM {table}", self.scratch)[0]
        self.assertEqual(count("dc_base_item"), [("3",)])
        self.assertEqual(count("dc_follower_relic"), [("3",)])
        self.assertEqual(count("dc_follower_relic_roll"), [("3",)])
        self.assertEqual(self.query("SELECT rule, value, unit FROM dc_follower_relic_rule ORDER BY rule", self.scratch)[0],
                         [("rare_relic_drops", "1", "flag"), ("relic_ancient_primal", "1", "flag")])
        self.assertEqual(count("dc_affix_pool"), [("20",)])
        self.assertEqual(count("dc_blacksmith_catalog"), [("3",)])
        self.assertEqual(count("dc_blacksmith_catalog_material"), [("9",)])
        self.assertEqual(count("item_template"), [("3",)])
        rows, _ = self.query("SELECT b.entry, b.slot, b.rarity, b.pool_version, b.craft_only, b.item_level, r.primary_affixes, "
                             "r.secondary_affixes, f.power, c.id, c.rarity, c.gold_d3, c.enabled FROM dc_base_item b "
                             "JOIN dc_follower_relic_roll r ON r.item_entry=b.entry JOIN dc_follower_relic f ON f.item_entry=b.entry "
                             "JOIN dc_blacksmith_catalog c ON c.output_entry=b.entry ORDER BY b.entry", self.scratch)
        self.assertEqual([r[0] for r in rows], ["103309", "103310", "103311"])
        self.assertEqual([r[9] for r in rows], ["362377", "362378", "362379"])
        for r in rows:
            self.assertEqual((r[2], r[3], r[4], r[5], r[6], r[7], r[8]), ("", "yes", "no", "70", "4", "2", ""), r)
            self.assertEqual((r[10], r[11], r[12]), ("rare", "1000", "1"), r)
        materials, _ = self.query("SELECT recipe_id, d3_id, item_entry, amount FROM dc_blacksmith_catalog_material "
                                  "ORDER BY recipe_id, d3_id", self.scratch)
        self.assertEqual({(r[1], r[3]) for r in materials}, {("Crafting_AssortedParts_01", "15"), ("Crafting_Magic_01", "15"),
                                                              ("Crafting_Rare_01", "15")})
        pools, _ = self.query("SELECT slot, item_level_bracket, COUNT(*) FROM dc_affix_pool GROUP BY slot, item_level_bracket "
                              "ORDER BY slot", self.scratch)
        self.assertEqual(pools, [("enchantressfocus", "rare", "6"), ("scoundreltoken", "rare", "6"), ("templarrelic", "rare", "8")])

    def test_it_leaves_the_legendary_relics_and_the_other_blacksmith_recipes_alone(self):
        updates = MODULE / "data/sql/db-world/updates"
        self.query("INSERT INTO dc_blacksmith_catalog VALUES (362322,100010,'Cloak','torso','Cloak','armor','rare',70,70,1000,1,'')",
                   self.scratch)
        self.query("INSERT INTO dc_affix_pool (slot, affix_id, affix_name, kind, value_min, value_max, item_level_bracket, is_percent, "
                   "source_file, display_order, weapon_class) VALUES ('templarrelic','str','Strength','primary',626,750,'legendary',0,'slots.js',1,'')",
                   self.scratch)
        self.query("", self.scratch, feed=MIGRATION.read_text(encoding="utf-8"))
        self.assertEqual(self.query("SELECT COUNT(*) FROM dc_blacksmith_catalog WHERE id=362322", self.scratch)[0], [("1",)])
        self.assertEqual(self.query("SELECT COUNT(*) FROM dc_affix_pool WHERE item_level_bracket='legendary'", self.scratch)[0],
                         [("1",)])
        self.assertTrue((updates / legendary_gen.MIGRATION).is_file())


if __name__ == "__main__":
    unittest.main()
