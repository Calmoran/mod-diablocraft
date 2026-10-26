"""diablocraft-xw2m - the Mystic rebuilt the D3 way (server rules), executed where it can be.

What this suite proves, and what it does not:

  * The **rules** are the production header `src/items/dc_enchant_rule.h` (who may be enchanted, what a roll
    costs, what a line may become, which lines are listed), compiled into `scripts/tests/crafting/enchant_rule_tests.cpp`
    and driven with what the generators emit: every row of the generated `dc_affix_pool`, the generated
    `dc_mystic_scalar`, and an oracle written here from D3Planner's exclusive groups and from the exact-fraction
    price rule. Every rule has a **mutation** that must turn the harness red.
  * The **materials** table is the generated `dc_mystic_rule`, replayed in SQLite through the very query
    dc_crafting.cpp runs, for every rarity and slot, against the brief's table.
  * The **migration** (items_crafting_0002) runs on the fixture mysqld (skipped when it is down): an offer row
    stored by the old code keeps reading back, with the new columns at 0.
  * The **wiring** of Roll (it pays before anything is stored, a waiting roll blocks the next) is checked by reading
    dc_crafting.cpp and the dc_items*.cpp files with comments removed. It is not executed: that needs a Player and is the GM
    script in docs/test-diablocraft-xw2m.md. Pick and the pending screen (choice 1/2/3, the bind flag, the stored
    choices, the damage-line rule) are executed in test_mystic_crafting.py; the substring checks on them below are
    kept only as a cheap second line.
"""
import concurrent.futures
import csv
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unittest
import uuid
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import crafting_source  # noqa: E402
import harness_env

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import fixture_db  # noqa: E402
from test_fresh_characters_db import core_base  # noqa: E402
from test_crafting_queries import cpp_queries  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
SRC = MODULE / "src"
HEADER = SRC / "items" / "dc_enchant_rule.h"
HARNESS = MODULE / "scripts" / "tests/crafting" / "enchant_rule_tests.cpp"
GENERATED = MODULE / "data" / "generated"
D3 = MODULE / "data" / "d3"
PLANNER = ROOT / "reference" / "d3planner" / "data_stats.js"
CHARACTERS = MODULE / "data" / "sql" / "db-characters" / "updates"
SCRATCH = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "mystic_enchant"

# The groups an item holds one of (D3Planner's statExclusiveGroups) that this code has to name itself.
# The main attribute and the skill bonuses are groups by the pool id the caller passes, so they need no table row.
TABLE_GROUPS = ("weapon", "elemental", "resistany", "onhit", "lifeper")


def code(path):
    """Source with comments removed, so prose cannot satisfy a wiring check."""
    return without_comments(path.read_text(encoding="utf-8"))


def without_comments(text):
    lines = []
    for line in text.splitlines():
        if line.strip().startswith(("//", "*", "/*")):
            continue
        lines.append(line.split("//")[0])
    return "\n".join(lines)


def pool_rows():
    text = (GENERATED / "affix_pools.sql").read_text(encoding="utf-8")
    rows = re.findall(r"^\('([^']*)', '([^']*)', '[^']*', '([^']*)', (\S+), (\S+), (\S+), '([^']*)', \S+, "
                      r"'[^']*', (\S+), (\S+), (\S+), '([^']*)'\)", text, re.M)

    def cell(value):
        value = value.rstrip(",")
        return "" if value == "NULL" else value
    return [(slot, bracket, affix, kind, cell(lo), cell(hi), cell(lo2), cell(hi2), cell(step), weapon, cell(order))
            for slot, affix, kind, lo, hi, step, bracket, order, lo2, hi2, weapon in rows]


def planner_groups():
    """{affix id: group} for the exclusive groups the code names, from D3Planner's own data_stats.js."""
    text = PLANNER.read_text(encoding="utf-8")
    block = text[text.index("DiabloCalc.statGroups = {"):text.index("DiabloCalc.statExclusiveGroups")]
    named = {name: re.findall(r'"(\w+)"', members)
             for name, members in re.findall(r'"(\w+)": \[(.*?)\]', block, re.S)}
    exclusive = re.findall(r'"(\w+)"', re.search(r"statExclusiveGroups = \[(.*?)\]", text, re.S).group(1))
    assert set(TABLE_GROUPS) <= set(exclusive), exclusive
    groups = {}

    def members(name, seen=()):
        for member in named.get(name, []):
            yield member
            if member in named and member not in seen:   # "resistany" holds "resist", itself a group of six
                yield from members(member, seen + (member,))
    for group in TABLE_GROUPS:
        for member in members(group):
            groups[member] = group
    return groups


def scalar_breakpoints():
    with (D3 / "mystic_cost_scalars.csv").open(encoding="utf-8", newline="") as handle:
        return [(int(r["use_count"]), int(r["scalar_tenths"])) for r in csv.DictReader(handle)]


def scalar(roll, points):
    """D3's table with a straight line between breakpoints, as an exact fraction."""
    for (a, ta), (b, tb) in zip(points, points[1:]):
        if a <= roll <= b:
            return Fraction(ta, 10) + Fraction(tb - ta, 10) * Fraction(roll - a, b - a)
    return None


def generated_scalars():
    text = (GENERATED / "mystic_rules.sql").read_text(encoding="utf-8")
    return [(int(a), int(b)) for a, b in re.findall(r"INSERT INTO `dc_mystic_scalar` VALUES \((\d+),(\d+)\);", text)]


def write_inputs():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "pool.tsv").write_text("".join("\t".join(r) + "\n" for r in pool_rows()), encoding="utf-8")
    (SCRATCH / "groups.tsv").write_text("".join("%s\t%s\n" % kv for kv in sorted(planner_groups().items())),
                                        encoding="utf-8")
    (SCRATCH / "scalars.tsv").write_text("".join("%d\t%d\n" % p for p in generated_scalars()), encoding="utf-8")
    points = scalar_breakpoints()
    lines = []
    for base in (1, 7, 333, 1000, 25000, 4321987):
        for roll in range(1, points[-1][0] + 1):
            lines.append("%d\t%d\t%d\n" % (base, roll, int(base * scalar(roll, points))))   # floor
    (SCRATCH / "prices.tsv").write_text("".join(lines), encoding="utf-8")


def build(include_dir, name, strict=True):
    compiler = shutil.which("c++") or shutil.which("g++")
    binary = SCRATCH / name
    flags = ["-Wall", "-Wextra", "-Werror"] if strict else []
    built = subprocess.run([compiler, "-std=c++17", "-O1", *flags, "-I", str(include_dir), str(HARNESS), "-o",
                            str(binary)], capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
    return binary


def run(binary):
    return harness_env.run([str(binary)] + [str(SCRATCH / n) for n in ("pool.tsv", "groups.tsv", "scalars.tsv",
                                                                         "prices.tsv")],
                           capture_output=True, text=True)


# One mutation per rule; each must make the harness fail.
MUTATIONS = [
    ("who: magic items can be enchanted",
     'rarity == "rare" || rarity == "legendary" || rarity == "set"',
     'rarity == "rare" || rarity == "legendary" || rarity == "set" || rarity == "magic"'),
    ("who: set items cannot be",
     'rarity == "rare" || rarity == "legendary" || rarity == "set"', 'rarity == "rare" || rarity == "legendary"'),
    ("price: rounds up", "std::floor(base *", "std::ceil(base *"),
    ("price: the last breakpoint is refused", "roll > table.back().count", "roll >= table.back().count"),
    ("price: roll 0 has a price", "roll < table.front().count ||", "roll + 1 < table.front().count ||"),
    ("price: a step, not a straight line between breakpoints",
     "(static_cast<long long>(b.tenths) - a.tenths) * (roll - a.count)",
     "(static_cast<long long>(b.tenths) - a.tenths) * 0"),
    ("price: a falling table is priced", "b.count <= a.count || b.tenths < a.tenths", "b.count <= a.count"),
    ("price: a negative base is priced", "base < 0 ||", ""),
    ("groups: Resistance to All does not exclude", '{"resall", "resistany"}', '{"resall", "resall"}'),
    ("groups: a single resistance is its own group", '{"resfir", "resistany"}', '{"resfir", "resfir"}'),
    ("groups: weapon damage rows are separate", '{"wpnfir", "weapon"}', '{"wpnfir", "wpnfir"}'),
    ("groups: elemental damage rows are separate", '{"dmgcol", "elemental"}', '{"dmgcol", "dmgcol"}'),
    ("groups: on-hit effects are separate", '{"hitstun", "onhit"}', '{"hitstun", "hitstun"}'),
    ("groups: life per hit and per kill are separate", '{"laek", "lifeper"}', '{"laek", "laek"}'),
    ("replace: a line becomes anything of another pool", "c.kind != own->kind ||", "false ||"),
    ("replace: any line can become a damage row", "c.weaponClass.empty() == damage ||", "false ||"),
    ("replace: a damage line can become another weapon's damage", "(damage && c.weaponClass != weaponClass)", "false"),
    ("replace: held groups are ignored", "if (used.count(Exclusion(c.id)) || ctx.Expand(c).empty())",
     "if (ctx.Expand(c).empty())"),
    ("replace: what the item cannot carry is offered", "|| ctx.Expand(c).empty())", ")"),
    ("replace: a line cannot become itself", "row.seq == target.seq || row.kind", "row.kind"),
    ("replace: the sockets exclude themselves", '(target.kind == "socket" && row.kind == "socket")', "false"),
    ("choices: one new choice, not two", "out.size() == 2", "out.size() == 1"),
    ("choices: three new choices", "out.size() == 2", "out.size() == 3"),
    ("choices: never shuffled", "ctx.Shuffle(eligible);", ""),
    ("choices: a socket choice keeps the pool's kind", 'pick.kind = rolled.id == "sockets" ? "socket" : rolled.kind;',
     "pick.kind = rolled.kind;"),
    ("choices: the second part is not rolled", "pick.value2 = value2;", "pick.value2 = 0;"),
    ("choices: the second bracket is not carried", "pick.min2 = rolled.min2;", "pick.min2 = 0;"),
    ("choices: a choice is for no line", "pick.seq = target.seq;\n            pick.id = rolled.id;",
     "pick.seq = 0;\n            pick.id = rolled.id;"),
    ("preview: the second range is dropped", "pick.max2 = e.max2;", "pick.max2 = 0;"),
    ("waiting: the current line is not first", "std::vector<Pick> out{*current};", "std::vector<Pick> out;"),
    ("waiting: the sockets line is not found by any socket row", "(socket && p.kind == \"socket\")", "false"),
    ("lines: an enchant-locked item lists every line", "if (locked && !enchanted)", "if (false && !enchanted)"),
    ("lines: one socket row marks the sockets enchanted", "(other.kind == \"socket\" && other.rerolled)", "false"),
    ("lines: every socket is a line", 'row.kind == "gem" || (row.kind == "socket" && socketsListed)',
     'row.kind == "gem"'),
    ("lines: gems in the sockets do not grey them", "if (sockets && gems)", "if (false)"),
    ("lines: a line with one choice is open", "Replacements(pool, row, rows, ctx).size() < 2",
     "Replacements(pool, row, rows, ctx).size() < 1"),
    ("lines: the sockets line carries one row's value", "line.pick.value = static_cast<double>(", "(void)static_cast<double>("),
    ("lines: the tooltip order is by name", "a.order < b.order", "a.order > b.order"),
]


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which("c++") or shutil.which("g++")):
            raise unittest.SkipTest("no C++ compiler")
        write_inputs()
        cls.binary = build(HEADER.parent, "enchant_rule_tests")

    def test_the_production_header_passes_on_the_generated_data(self):
        result = run(self.binary)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        print("\n" + result.stdout.strip())

    def test_the_price_table_is_d3s_and_the_brief_spot_values_hold(self):
        """1.2, 1.4, 1.6, 1.8, 2.0 for N=1..5, 6.0 at N=10, x3 per doubling after it (the brief)."""
        points = scalar_breakpoints()
        self.assertEqual(generated_scalars(), points)
        self.assertEqual([scalar(n, points) for n in (1, 2, 3, 4, 5)],
                         [Fraction(12, 10), Fraction(14, 10), Fraction(16, 10), Fraction(18, 10), Fraction(2)])
        self.assertEqual(scalar(10, points), 6)
        for n in (10, 20, 40, 80, 160, 320):
            self.assertEqual(scalar(2 * n, points), 3 * scalar(n, points))
        self.assertEqual([int(1000 * scalar(n, points)) for n in range(1, 13)],
                         [1200, 1400, 1600, 1800, 2000, 2800, 3600, 4400, 5200, 6000, 7200, 8400])

    def test_every_mutation_fails(self):
        source = HEADER.read_text(encoding="utf-8")

        def attempt(index):
            label, old, new = MUTATIONS[index]
            if source.count(old) != 1:
                return label, "mutation target moved or is ambiguous: " + old, None
            folder = SCRATCH / ("mutant_%d" % index)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / HEADER.name).write_text(source.replace(old, new), encoding="utf-8")
            try:
                binary = build(folder, "bin_%d" % index, strict=False)
            except AssertionError:
                return label, "the mutant did not compile; fix the mutation, a compile error is not a catch", None
            return label, None, run(binary)

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
            results = list(pool.map(attempt, range(len(MUTATIONS))))
        for label, problem, result in results:
            with self.subTest(mutation=label):
                self.assertIsNone(problem, label)
                self.assertNotEqual(result.returncode, 0, label + " was not caught:\n" + result.stdout)


class Materials(unittest.TestCase):
    """The generated dc_mystic_rule through the very query Roll and MysticState run."""

    @classmethod
    def setUpClass(cls):
        text = (GENERATED / "mystic_rules.sql").read_text(encoding="utf-8")
        cls.db = sqlite3.connect(":memory:")
        cls.db.execute("CREATE TABLE dc_mystic_rule(rarity,slot,payment_kind,material_1_entry,material_2_entry,"
                       "material_count,gem_tier,gem_count_rule)")
        for values in re.findall(r"INSERT INTO `dc_mystic_rule` VALUES \((.*)\);", text):
            cls.db.execute("INSERT INTO dc_mystic_rule VALUES (%s)" % values)
        queries = [q for q in cpp_queries(crafting_source.source())
                   if "FROM dc_mystic_rule" in q]
        assert len(queries) == 1, queries
        cls.query = queries[0]
        with (D3 / "account_economy.csv").open(encoding="utf-8", newline="") as handle:
            cls.entry = {r["name"]: int(r["item_entry"]) for r in csv.DictReader(handle)}
        slots = {row[0] for row in pool_rows()} - {"follower"}
        cls.slots = sorted(slots)

    def rule(self, rarity, slot):
        sql = self.query.replace("{}", "?", 3)
        return self.db.execute(sql.replace("'?'", "?"), (rarity, slot)).fetchone()

    def test_armor_and_weapons_pay_three_and_three_on_every_rarity(self):
        for rarity in ("rare", "legendary", "set"):
            for slot in set(self.slots) - {"neck", "finger"}:
                kind, m1, m2, count, tier, rule = self.rule(rarity, slot)
                self.assertEqual((kind, m1, m2, count, tier, rule),
                                 ("gold", self.entry["Arcane Dust"], self.entry["Veiled Crystal"], 3, "", ""),
                                 (rarity, slot))

    def test_a_rare_ring_or_amulet_pays_two_and_two(self):
        for slot in ("neck", "finger"):
            kind, m1, m2, count, *_ = self.rule("rare", slot)
            self.assertEqual((kind, m1, m2, count),
                             ("gold", self.entry["Arcane Dust"], self.entry["Veiled Crystal"], 2), slot)

    def test_a_legendary_or_set_ring_or_amulet_pays_one_imperial_gem_and_nothing_else(self):
        for rarity in ("legendary", "set"):
            for slot in ("neck", "finger"):
                kind, m1, m2, count, tier, rule = self.rule(rarity, slot)
                self.assertEqual((kind, m1, m2, count, tier), ("gem", 0, 0, 0, "Imperial"), (rarity, slot))
                self.assertEqual(rule, "mystic_jewelry_gem_count")

    def test_no_death_breath_or_forgotten_soul_and_no_row_for_other_rarities(self):
        used = {m for row in self.db.execute("SELECT material_1_entry,material_2_entry FROM dc_mystic_rule") for m in row}
        self.assertEqual(used - {0}, {self.entry["Arcane Dust"], self.entry["Veiled Crystal"]})
        for rarity in ("normal", "magic", "ethereal"):
            self.assertIsNone(self.rule(rarity, "head"), rarity)

    def test_one_imperial_gem_and_two_new_choices_are_sourced_counts(self):
        """The count rules are generated from mystic.csv (dc_numeric_rule), never a number written in code."""
        import generate_numeric_data
        rules = dict(re.findall(r"\('(\w+)',([0-9.]+),", generate_numeric_data.render()))
        self.assertEqual(float(rules["mystic_jewelry_gem_count"]), 1)
        self.assertEqual(float(rules["mystic_offer_count"]), 2)
        window = (SRC / "crafting" / "dc_crafting_window.h").read_text(encoding="utf-8")
        self.assertIn("EnchantChoices = 3;", window)       # the current line plus the offer count
        self.assertIn("SourcedCount(countRule.c_str())", without_comments(crafting_source.source()))


class Migration(unittest.TestCase):
    """items_crafting_0002 on the fixture mysqld: an offer stored by the old code still reads back."""

    def mysql(self, *args, stdin=None):
        return subprocess.run([fixture_db.mysql_exe(), "--defaults-file=" + str(fixture_db.defaults_file()),
                               "--no-login-paths", *args], input=stdin, capture_output=True, text=True)

    def test_an_old_offer_row_reads_back_with_the_new_columns_at_zero_and_the_alter_is_idempotent(self):
        if self.mysql("-e", "SELECT 1").returncode != 0:
            self.skipTest("the fixture mysqld is down (fixture_mysql.sh start)")
        second = (CHARACTERS / "items_crafting_0002_enchant_offer_pair.sql").read_text(encoding="utf-8")
        # What a first start builds: the core's base schema, then our updates in the updater's order up to this one.
        upto = sorted(CHARACTERS.glob("*.sql"), key=lambda p: p.name)
        upto = upto[:[p.name for p in upto].index("items_crafting_0002_enchant_offer_pair.sql")]
        db = "mystic_offer_" + uuid.uuid4().hex[:10]
        self.assertEqual(self.mysql("-e", "CREATE DATABASE " + db).returncode, 0)
        try:
            for path in core_base() + upto:
                done = self.mysql(db, stdin=path.read_text(encoding="utf-8"))
                self.assertEqual(done.returncode, 0, path.name + ": " + done.stderr)
            self.assertEqual(self.mysql(db, "-N", "-e", "SELECT COUNT(*) FROM information_schema.columns WHERE "
                                        "table_schema=DATABASE() AND table_name='dc_enchant_offer' AND "
                                        "column_name IN ('value2','range_min2','range_max2')").stdout.strip(), "0")
            done = self.mysql(db, stdin=second)
            self.assertEqual(done.returncode, 0, done.stderr)
            # The row the OLD code wrote: no value2 / range_min2 / range_max2 in its column list.
            old = self.mysql(db, "-e", "INSERT INTO dc_enchant_offer(item_guid,choice_id,target_seq,affix_id,value,"
                             "range_min,range_max,kind) VALUES(77,1,2,'vit',10,5,15,'primary'),"
                             "(77,2,2,'chd',20,10,30,'primary')")
            self.assertEqual(old.returncode, 0, old.stderr)
            # The new code's rows carry them.
            new = self.mysql(db, "-e", "INSERT INTO dc_enchant_offer(item_guid,choice_id,target_seq,affix_id,value,"
                             "range_min,range_max,kind,value2,range_min2,range_max2) "
                             "VALUES(78,1,0,'wpnlit',100,90,110,'primary',130,120,140)")
            self.assertEqual(new.returncode, 0, new.stderr)
            # Re-running the migration changes nothing (it is applied once per database, but a replay must be safe).
            again = self.mysql(db, stdin=second)
            self.assertEqual(again.returncode, 0, again.stderr)
            read = self.mysql(db, "-N", "-e", "SELECT item_guid,choice_id,affix_id,value,value2,range_min2,range_max2 "
                              "FROM dc_enchant_offer ORDER BY item_guid,choice_id")
            self.assertEqual(read.returncode, 0, read.stderr)
            rows = [line.split("\t") for line in read.stdout.strip().splitlines()]
            self.assertEqual(rows, [["77", "1", "vit", "10", "0", "0", "0"], ["77", "2", "chd", "20", "0", "0", "0"],
                                    ["78", "1", "wpnlit", "100", "130", "120", "140"]])
            # The statement StoredOffers runs.
            stored = [q for q in cpp_queries(crafting_source.source(),
                                             "CharacterDatabase.Query") if q.startswith("SELECT target_seq,affix_id,value,")]
            self.assertEqual(len(stored), 1, stored)
            read = self.mysql(db, "-N", "-e", stored[0].replace("{}", "77"))
            self.assertEqual(read.returncode, 0, read.stderr)
            self.assertEqual(len(read.stdout.strip().splitlines()), 2)
        finally:
            self.mysql("-e", "DROP DATABASE IF EXISTS " + db)


class Wiring(unittest.TestCase):
    """The production paths call the tested rules; comments removed first."""

    crafting = without_comments(crafting_source.source())
    items = without_comments(items_source.source())

    @staticmethod
    def body(text, signature):
        start = text.index(signature)
        end = text.index("\n        }\n", start)
        return text[start:end]

    def test_the_rules_come_from_the_tested_header(self):
        self.assertIn('#include "../items/dc_enchant_rule.h"', self.crafting)
        self.assertIn('#include "dc_enchant_rule.h"', self.items)
        for call in ("Enchant::Price(", "Enchant::Eligible(", "Enchant::Waiting("):
            self.assertIn(call, self.crafting)
        for call in ("Enchant::Lines(", "Enchant::NewChoices(", "Enchant::Preview("):
            self.assertIn(call, self.items)

    def test_the_price_is_the_tunable_times_the_table_for_the_next_paid_roll_and_is_not_invented(self):
        cost = self.body(self.crafting, "EnchantCost CostOf(")
        self.assertIn("SELECT mystic_base_gold FROM dc_loot_tuning", cost)
        self.assertIn("SELECT use_count,scalar_tenths FROM dc_mystic_scalar", cost)
        self.assertIn("instance.enchantAttempts + 1", cost)
        self.assertIn("instance.enchantAttempts + 1 <= scalars.back().count", cost)   # nothing priced past the table
        self.assertNotIn("mystic_cost_multiplier", self.crafting)
        self.assertNotRegex(cost, r"\b(pow|std::pow)\(")

    def test_roll_pays_the_gold_and_the_materials_and_stores_the_three_choices_in_one_transaction(self):
        roll = self.body(self.crafting, "void Roll(Player* player")
        order = [roll.index(token) for token in ("CostOf(", "CheckMaterials(", "CanAfford(", "BeginTransaction()",
                                                 "Economy::Charge(", "SpendMaterials(", "INSERT INTO dc_enchant_offer",
                                                 "Save(player, tx)")]
        self.assertEqual(order, sorted(order), "Roll must check, then charge and store together, then save")
        self.assertIn("StoredOffers(guid).empty()", roll)          # a waiting roll blocks the next one
        self.assertIn("NeedReplaceable(line)", roll)
        self.assertIn("SourcedCount(\"mystic_offer_count\")", roll)

    def test_the_item_is_locked_bound_and_the_roll_counted_when_the_roll_is_paid(self):
        roll = self.body(self.crafting, "void Roll(Player* player")
        self.assertIn("enchant_locked=1,enchant_attempts=enchant_attempts+1,bound_account=", roll)
        self.assertIn("item->SetBinding(true)", roll)
        self.assertIn("rerolled=1", roll)        # the line the roll was paid on is the enchanted one

    def test_pick_is_free_and_choice_one_keeps_the_line(self):
        pick = self.body(self.crafting, "void Pick(Player* player")
        for charge in ("Economy::Charge", "SpendMaterials", "CostOf(", "CheckMaterials"):
            self.assertNotIn(charge, pick)
        self.assertIn("if (choice > 1)", pick)           # 1 changes nothing on the item
        self.assertIn("offers[choice - 2].affix", pick)  # 2 and 3 are the stored rolls
        self.assertIn("DELETE FROM dc_enchant_offer", pick)

    def test_the_stored_choices_survive_a_relog_because_they_live_in_the_characters_database(self):
        self.assertIn("INSERT INTO dc_enchant_offer", self.crafting)
        self.assertIn("FROM dc_enchant_offer WHERE item_guid", self.crafting)
        self.assertNotRegex(self.crafting, r"static\s+(std::)?(map|unordered_map)<[^>]*Offer")

    def test_the_window_state_carries_the_bind_warning_and_the_enchant_state_of_the_item(self):
        state = self.body(self.crafting, "Window::EnchantState MysticState(")
        self.assertIn("state.bind = instance.boundAccount == 0;", state)     # the first enchant only: it binds
        self.assertIn("state.enchanted = instance.enchantLocked;", state)

    def test_the_soulbound_gate_and_the_economy_are_the_old_ones(self):
        self.assertIn("CanApplySoulboundFlag", items_source.source()
                      + "".join(p.read_text(encoding="utf-8") for p in (SRC).rglob("*.cpp")))
        self.assertIn("PlayerEconomy::BeginTransaction()", self.crafting)

    def test_weapon_damage_choices_roll_both_parts_and_a_damage_line_stays_a_damage_line(self):
        self.assertIn("RollWeaponDelta", self.items)
        self.assertIn("WeaponClass()", self.items)


if __name__ == "__main__":
    unittest.main()
