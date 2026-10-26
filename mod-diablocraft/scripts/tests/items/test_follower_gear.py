"""Followers' gear: what each follower may wear, the stats its gear makes, its relics and its rows.

What runs: the rules header src/items/dc_follower_gear_rule.h compiled with the real dc_common.cpp and driven with the values
parsed out of the sheets (data/d3/followers_gear.csv, followers_gear_rules.csv and the numeric rules the sheet-stat maths
asks for), each rule killed by a mutant that must turn the harness red; the generator's validation and its refusal of bad
sheets; the sheets against the sources they cite (base_items.csv usable_by, the research sheets); the migration against the
fixture mysqld's copy of the world. What does not: the equip move, the creature and the commands need a Player, a Map and
a character database, so the source guards pin that the C++ reads the tables, columns, slots and powers the sheets write.
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
import generate_follower_gear as gen  # noqa: E402
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
D3 = MODULE / "data/d3"
SRC = MODULE / "src/items"
HEADER = SRC / "dc_follower_gear_rule.h"
CPP = SRC / "dc_follower_gear.cpp"
HARNESS = MODULE / "tests/follower_gear/harness.cpp"
MIGRATION = MODULE / "data/sql/db-world/updates" / gen.MIGRATION
CHARACTER_MIGRATION = MODULE / "data/sql/db-characters/updates/followers_0002_character_gear.sql"
SCRATCH = harness_env.private_scratch(REPO / "azerothcore-wotlk/build/_agent-scratch/follower_gear_test")
CLASS_ITEM_TYPES = {"Wizard Hat", "Voodoo Mask", "Spirit Stone", "Mighty Belt", "Cloak"}


def sheet(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def research(name):
    with (REPO / "docs/research" / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def numeric_rules():
    text = (MODULE / "data/generated/numeric_rules_0001.sql").read_text(encoding="utf-8")
    return [f"{name}={value}" for name, value in re.findall(r"\('(\w+)',([\d.]+),", text)]


def build_and_run(header_dir, label):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    kinds = SCRATCH / "kinds.txt"
    kinds.write_text("".join(f"{r['follower_id']} {r['gear_slot']} {r['item_slot']} {r['item_type']}\n"
                             for r in sheet("followers_gear.csv")), encoding="utf-8")
    rules = {r["rule"]: r["value"] for r in sheet("followers_gear_rules.csv")}
    tree = SCRATCH / f"tree_{label}"
    shutil.rmtree(tree, ignore_errors=True)
    (tree / "src/items").mkdir(parents=True)
    shutil.copytree(MODULE / "src/common", tree / "src/common")
    shutil.copy(header_dir / HEADER.name, tree / "src/items" / HEADER.name)
    (tree / "tests/follower_gear").mkdir(parents=True)
    shutil.copy(HARNESS, tree / "tests/follower_gear/harness.cpp")
    binary = tree / "harness"
    built = subprocess.run([compiler, "-std=c++17", "-I", str(tree / "src"), "-o", str(binary),
                            str(tree / "tests/follower_gear/harness.cpp"), str(tree / "src/common/dc_common.cpp")],
                           capture_output=True, text=True)
    if built.returncode != 0:
        return built.returncode, built.stderr
    ran = harness_env.run([str(binary), str(kinds), rules["main_stat_multiplier"], rules["crit_damage_cap_pct"],
                           rules["player_share_pct"]] + numeric_rules(), capture_output=True, text=True)
    return ran.returncode, ran.stderr


class RulesTests(unittest.TestCase):
    def test_rules_on_the_sheets_values(self):
        code, err = build_and_run(SRC, "real")
        self.assertEqual(code, 0, err[-3000:])

    def test_each_rule_has_a_mutant_that_turns_it_red(self):
        original = HEADER.read_text(encoding="utf-8")
        mutants = {
            "a relic of another follower is taken": ("if (item.relicFollower != follower)", "if (false)"),
            "an item of a class's own is taken": ("if (item.classBound)", "if (false)"),
            "any follower wears any kind": ("kind.follower == follower && kind.itemSlot", "kind.itemSlot"),
            "a kind is matched on its slot alone": (" && kind.itemType == item.itemType", ""),
            "a two-hander ignores a full off-hand": ("if (twoHander && out.slot == Slot::MainHand && (held.filled & Bit(Slot::OffHand)))",
                                                     "if (false)"),
            "a shield beside a two-hander is taken": ("if (out.slot == Slot::OffHand && held.twoHanded)", "if (false)"),
            "the attributes count once": ("gear.value * rules.mainStatMultiplier", "gear.value"),
            "a percent bonus to an attribute counts the multiplier": (" && gear.bucket == Bucket::Flat ? gear.value", " ? gear.value"),
            "crit damage has no cap": ("crit = std::min(crit, rules.critDamageCap);", ""),
            "the player gets all of the share": ("followerValue * rules.playerSharePct / 100.0", "followerValue"),
            "the core's armor constant drops the level raise": ("level += 4.5 * (level - 59);", ""),
            "a reduction past three quarters is asked of the core": ("std::clamp(reduction, 0.0, CoreReductionCap)",
                                                                     "std::max(reduction, 0.0)"),
            "a swing leaves out the flat damage's delta": ("flatLow + sheet[Stat::WeaponFlatDamageDelta]", "flatLow"),
            "a swing leaves out the main stat": ("1.0 + sheet[mainStat] / 100.0", "1.0"),
            "the period ignores the sheet's speed": ("1000.0 / aps", "weapon.delayMs"),
            "the core's weapon damage ignores the period": ("swing * 1000.0 / attackTimeMs", "swing"),
            "a relic that keeps it from dying takes the damage": ("return cannotDie ? 0 : damage;", "return damage;"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(name):
                self.assertEqual(original.count(old), 1, f"the mutant's text is not in the header once: {old!r}")
                folder = SCRATCH / "mutant"
                shutil.rmtree(folder, ignore_errors=True)
                folder.mkdir(parents=True)
                (folder / HEADER.name).write_text(original.replace(old, new), encoding="utf-8")
                code, err = build_and_run(folder, "mutant")
                self.assertNotEqual(code, 0, f"the harness stayed green with: {name}")
                self.assertIn("FAIL", err, f"it failed, but not on a check: {err[-500:]}")
        shutil.rmtree(SCRATCH, ignore_errors=True)


class SheetTests(unittest.TestCase):
    def test_sheets_pass_the_generator(self):
        skills, relics = gen.sheet()
        self.assertEqual((len(skills), len(relics)), (24, 9))
        self.assertEqual(len(gen.gear()), 50)
        self.assertEqual([r[0] for r in gen.rules()], list(gen.RULES))
        self.assertEqual({a for a, _ in gen.stats()} & {"mf", "gf", "expmul", "expadd"}, {"mf", "gf", "expmul", "expadd"})

    def test_the_generated_files_are_the_sheets_render(self):
        text = gen.render()
        self.assertEqual(MIGRATION.read_text(encoding="utf-8"), text)
        self.assertEqual((MODULE / "data/generated" / gen.MIGRATION).read_text(encoding="utf-8"), text)

    def test_the_slots_are_the_headers(self):
        header = HEADER.read_text(encoding="utf-8")
        keys = re.findall(r'"(\w+)"', header[header.index("SlotKeys"):header.index("constexpr std::string_view KeyOf")])
        self.assertEqual(keys, list(gen.SLOTS))
        self.assertEqual(len(gen.SLOTS), 14)
        enum = re.search(r"enum class Slot : std::uint8_t\s*\{(.*?)\}", header, re.S).group(1)
        self.assertEqual([w.lower() for w in re.findall(r"\w+", enum)], list(gen.SLOTS))

    def test_the_relic_powers_are_the_headers(self):
        header = HEADER.read_text(encoding="utf-8")
        powers = re.findall(r'inline constexpr std::string_view Power\w+ = "(\w+)"', header)
        self.assertEqual(sorted(powers), sorted(gen.POWERS))

    def test_every_follower_wears_the_open_armour_and_no_class_item(self):
        base = {(r["slot"], r["type"]) for r in sheet("base_items.csv")}
        armour_types = {(s, t) for s, t in base if s in ("head", "shoulders", "torso", "hands", "wrists", "waist", "legs", "feet", "finger", "neck")}
        wearable = {(r["item_slot"], r["item_type"]) for r in sheet("followers_gear.csv") if r["gear_slot"] in gen.ARMOUR_SLOTS}
        # Everything the player wears that is not a class's own is wearable; the class ones are exactly the five of R1a section 4.
        self.assertEqual(armour_types - wearable, {k for k in armour_types if k[1] in CLASS_ITEM_TYPES})
        self.assertEqual({t for _, t in wearable} & CLASS_ITEM_TYPES, set())
        for follower in ("templar", "scoundrel", "enchantress"):
            mine = {(r["item_slot"], r["item_type"]) for r in sheet("followers_gear.csv")
                    if r["key"] == follower and r["gear_slot"] in gen.ARMOUR_SLOTS}
            self.assertEqual(mine, wearable, follower)
            rings = [r["gear_slot"] for r in sheet("followers_gear.csv") if r["key"] == follower and r["item_type"] == "Ring"]
            self.assertEqual(sorted(rings), ["ring1", "ring2"])

    def test_the_weapon_kinds_are_the_item_sheets_usable_by(self):
        """Two sources for one rule: base_items.csv names the followers a weapon is for; followers_gear.csv names the kinds."""
        listed = {}
        for row in sheet("base_items.csv"):
            if row["slot"] not in ("onehand", "twohand", "offhand"):
                continue
            for key in row["usable_by"].split(";"):
                if key in ("templar", "scoundrel", "enchantress"):
                    listed.setdefault(key, set()).add((row["slot"], row["type"]))
        wanted = {}
        for row in sheet("followers_gear.csv"):
            if row["gear_slot"] in ("mainhand", "offhand"):
                wanted.setdefault(row["key"], set()).add((row["item_slot"], row["item_type"]))
        self.assertEqual(listed, wanted)

    def test_a_two_hander_never_shares_a_follower_with_an_off_hand(self):
        for key in ("scoundrel", "enchantress"):
            self.assertFalse([r for r in sheet("followers_gear.csv") if r["key"] == key and r["gear_slot"] == "offhand"], key)
        templar = [r for r in sheet("followers_gear.csv") if r["key"] == "templar" and r["gear_slot"] in ("mainhand", "offhand")]
        self.assertFalse([r for r in templar if r["item_slot"] == "twohand"])
        self.assertEqual([r["item_type"] for r in templar if r["gear_slot"] == "offhand"], ["Shield"])

    def test_skills_and_relics_are_the_research_sheets(self):
        skills = {(r["follower"], r["skill_id"]): r for r in research("followers_skills.csv")}
        mine = {(r["key"], r["skill_id"]): r for r in sheet("followers.csv") if r["kind"] == "skill"}
        self.assertEqual(set(skills), set(mine))
        for key, row in mine.items():
            self.assertEqual((row["name"], row["text"], row["cooldown_seconds"]),
                             (skills[key]["name"], skills[key]["description"], skills[key]["cooldown_seconds"]), key)
        relics = {r["d3_id"]: r for r in research("followers_items.csv")}
        power = {"leg_followerimmortal": "cannot_die", "leg_followerallskills": "all_skills", "leg_followercooldowns": "cooldown_half"}
        mine = {r["skill_id"]: r for r in sheet("followers.csv") if r["kind"] == "relic"}
        self.assertEqual(set(relics), set(mine))
        for d3_id, row in mine.items():
            source = relics[d3_id]
            self.assertEqual((row["name"], row["text"], row["power"], row["drop_level"], row["key"]),
                             (source["name"], source["power_text"], power[source["power_id"]], source["drop_level"], source["follower"]))

    def test_the_cannot_die_relics_are_r1as(self):
        """R1a section 6: Enchanting Favor, Skeleton Key and Smoking Thurible keep the follower from dying (the brief's list had
        Hand of the Prophet, which is the Enchantress's all-skills focus)."""
        names = {r["name"] for r in sheet("followers.csv") if r["power"] == "cannot_die"}
        self.assertEqual(names, {"Enchanting Favor", "Skeleton Key", "Smoking Thurible"})

    def test_cannot_die_takes_no_damage_on_d3s_own_word(self):
        """diablocraft-q9xc1 (5): the Architect wanted death stopped, not damage, unless D3's text for Enchanting Favor says the
        follower loses no health. FI says so, so F2's build (no damage) stays; this holds the source the build rests on."""
        research = (REPO / "docs/research/followers-web-sources.md").read_text(encoding="utf-8")
        self.assertIn("FI Enchanting Favor: \"When equipped on the Templar, he does not lose health", research.replace("\n  ", " "))
        creature = (MODULE / "src/campaign/dc_follower_creature.cpp").read_text(encoding="utf-8")
        self.assertIn("damage = 0;", creature)

    def test_the_enchantress_tiers_are_r1as(self):
        levels = sorted({int(r["d3_level"]) for r in sheet("followers.csv") if r["kind"] == "skill" and r["key"] == "enchantress"})
        self.assertEqual(levels, [15, 20, 25, 30])
        levels = sorted({int(r["d3_level"]) for r in sheet("followers.csv") if r["kind"] == "skill" and r["key"] == "templar"})
        self.assertEqual(levels, [5, 10, 15, 20])

    def test_the_rules_are_d3s(self):
        self.assertEqual({n: v for n, v, _ in gen.rules()}, {"main_stat_multiplier": "2.5", "crit_damage_cap_pct": "150", "player_share_pct": "20"})

    def test_the_relic_entries_are_free_and_in_the_follower_range(self):
        _, relics = gen.sheet()
        self.assertEqual([r["entry"] for r in relics], list(range(103300, 103309)))
        shells = range(199900, 199930)
        self.assertFalse(set(r["entry"] for r in relics) & set(shells))


class RefusalTests(unittest.TestCase):
    """The generator refuses a sheet that breaks a rule of the brief."""

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
            def run(rows):
                for r in rows:
                    if predicate(r):
                        r.update(fields)
            return run

        cases = [
            ("followers.csv", edit(lambda r: r["kind"] == "relic" and r["name"] == "Skeleton Key", power="all_skills"), "one relic for each"),
            ("followers.csv", edit(lambda r: r["kind"] == "relic", power="immortal"), "power is one of"),
            ("followers.csv", edit(lambda r: r["skill_id"] == "heal", tier="2"), "disagree with R1a"),
            ("followers.csv", edit(lambda r: r["skill_id"] == "heal", scales_with="dexterity"), "own main stat"),
            ("followers.csv", drop(lambda r: r["skill_id"] == "heal"), "eight skills"),
            ("followers.csv", edit(lambda r: r["name"] == "Skeleton Key", item_entry="103399"), "not the next free"),
            ("followers.csv", edit(lambda r: r["kind"] == "relic" and r["name"] == "Enchanting Favor", item_entry="100000"), "not the next free"),
            ("followers_gear.csv", edit(lambda r: r["key"] == "scoundrel" and r["item_type"] == "Bow", gear_slot="offhand"), "only the Templar has an off-hand"),
            ("followers_gear.csv", edit(lambda r: r["item_type"] == "Helm" and r["key"] == "templar", item_type="Nonesuch"), "has no head Nonesuch"),
            ("followers_gear.csv", edit(lambda r: r["item_type"] == "Staff", gear_slot="head"), "a weapon in an armour slot"),
            ("followers_gear.csv", drop(lambda r: r["key"] == "templar" and r["gear_slot"] == "boots"), "every armour slot"),
            ("followers_gear.csv", edit(lambda r: r["item_type"] == "Helm" and r["key"] == "templar", gear_slot="relic"), "base-item slots"),
            ("followers_gear_rules.csv", edit(lambda r: r["rule"] == "main_stat_multiplier", value="0"), "a positive value"),
            ("followers_stats.csv", edit(lambda r: r["affix_id"] == "ms", treatment="own"), "treatment"),
        ]
        for name, change, message in cases:
            with self.subTest(f"{name}: {message}"):
                with self.assertRaises(ValueError) as caught:
                    self.with_sheet(name, change)
                self.assertIn(message, str(caught.exception))


class SourceGuards(unittest.TestCase):
    """The server half cannot be compiled into a test; it must read what the migrations write."""

    def source(self):
        return CPP.read_text(encoding="utf-8")

    def test_the_server_reads_the_tables_and_columns_of_the_migration(self):
        source = self.source()
        migration = MIGRATION.read_text(encoding="utf-8")
        for table in ("dc_follower_gear_kind", "dc_follower_relic", "dc_follower_stat", "dc_follower_gear_rule",
                      "dc_follower_gear_follower"):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table} ", migration)
            self.assertEqual(source.count(f"FROM {table}"), 1, table)
        for column in ("follower_id", "gear_slot", "item_slot", "item_type", "item_entry", "power", "affix_id", "treatment",
                       "rule", "value", "follower_key", "main_stat"):
            self.assertIn(column, source)
        for name in ("main_stat_multiplier", "crit_damage_cap_pct", "player_share_pct"):
            self.assertEqual(source.count(f'"{name}"'), 1, name)
        self.assertIn("dc_class_base_stats", source)

    def test_the_character_table_is_the_servers(self):
        source = self.source()
        migration = CHARACTER_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS `dc_character_follower_gear`", migration)
        for column in re.findall(r"^\s+`(\w+)` ", migration, re.M):
            self.assertIn(column, source)
        self.assertIn("DeleteCharacterSql(guid)", source)
        self.assertIn("UNIQUE KEY", migration)
        self.assertIn("PRIMARY KEY (`guid`, `follower`, `slot`)", migration)

    def test_a_worn_item_leaves_the_bags_in_the_same_transaction_it_is_parked_in(self):
        source = self.source()
        equip = source[source.index("void Equip("):source.index("void TakeOff(")]
        self.assertIn("item->DeleteFromInventoryDB(transaction);", equip)
        self.assertIn("REPLACE INTO dc_character_follower_gear", equip)
        # The inventory statement is prepared as async only: the commit is the async one, never the direct one.
        self.assertIn("AsyncCommitTransaction(transaction).m_future.get()", equip)
        self.assertNotIn("DirectCommitTransaction", source)
        # The database first, the bags after: a failed save moves nothing.
        self.assertLess(equip.index("AsyncCommitTransaction"), equip.index("MoveItemFromInventory"))

    def test_a_taken_off_item_returns_through_the_bags_and_the_inventory_save(self):
        source = self.source()
        take = source[source.index("void TakeOff("):source.index("// ---", source.index("void TakeOff("))]
        self.assertIn("CanStoreItem(NULL_BAG, NULL_SLOT, destination, item, false)", take)
        self.assertIn("SaveInventoryAndGoldToDB(transaction)", take)
        self.assertIn("DELETE FROM dc_character_follower_gear WHERE guid={} AND follower={} AND slot='{}'", take)

    def test_a_filled_slot_swaps_and_only_full_bags_refuse(self):
        """The Architect's D3 reading (decisions.md 2026-10-23 Followers F2, diablocraft-q9xc1): the new item goes on the follower and
        the old one back to the player's bags; refused only when the bags are full."""
        source = self.source()
        equip = source[source.index("void Equip("):source.index("void TakeOff(")]
        self.assertNotIn("take its item off first", source)
        self.assertIn("Worn const old = set[unsigned(placement.slot)];", equip)
        # The old item is read back and has to fit before anything moves: first in the place the new one leaves (the core's
        # own swap check), else anywhere.
        self.assertIn("LoadParked(player, old)", equip)
        self.assertIn("CanStoreItem(bag, position, destination, returned, true)", equip)
        self.assertIn("CanStoreItem(NULL_BAG, NULL_SLOT, destination, returned, false)", equip)
        self.assertIn('throw std::runtime_error("Your bags are full.");', equip)
        self.assertLess(equip.index("Your bags are full."), equip.index("BeginTransaction()"))
        # It comes back through the bags and the inventory save, in the transaction that parks the new item.
        swap = equip[equip.index("MoveItemToInventory(destination, returned, true)"):]
        self.assertIn("SaveInventoryAndGoldToDB(transaction)", swap)
        self.assertLess(equip.index("REPLACE INTO dc_character_follower_gear"), equip.index("MoveItemToInventory"))
        # The slot's row is replaced, not deleted: the follower never holds two items in one slot.
        self.assertNotIn("DELETE FROM dc_character_follower_gear", equip)

    def test_the_swap_checks_are_each_killed_by_a_mutant(self):
        source = self.source()
        for what, (old, new) in {
            "the swap check of the vacated place": ("CanStoreItem(bag, position, destination, returned, true)",
                                                   "CanStoreItem(bag, position, destination, returned, false)"),
            "the old item returned to the bags": ("player->MoveItemToInventory(destination, returned, true);", ""),
            "the full-bags refusal": ('throw std::runtime_error("Your bags are full.");', "(void)0;"),
        }.items():
            self.assertIn(old, source, what)
            with self.assertRaises(AssertionError, msg=what):
                self.assertSwapSource(source.replace(old, new, 1))

    def assertSwapSource(self, source):
        equip = source[source.index("void Equip("):source.index("void TakeOff(")]
        for text in ("CanStoreItem(bag, position, destination, returned, true)", "MoveItemToInventory(destination, returned, true)",
                     'throw std::runtime_error("Your bags are full.");'):
            self.assertIn(text, equip)

    def test_gear_changes_are_made_in_the_hub_by_a_living_player_out_of_combat(self):
        source = self.source()
        check = source[source.index("void CheckHub("):source.index("Held HeldBy(")]
        for text in ("IsAlive()", "IsInCombat()", "World::IsInHub(player)"):
            self.assertIn(text, check)
        self.assertEqual(source.count("CheckHub(player);"), 2)

    def test_gear_that_is_not_rolled_is_refused(self):
        equip = self.source()
        equip = equip[equip.index("void Equip("):equip.index("void TakeOff(")]
        self.assertIn("Identify it first.", equip)
        self.assertIn("Detail::Load(itemGuid)", equip)
        self.assertIn("designatedClass.empty()", equip)

    def test_the_sheet_is_the_gears_not_the_players(self):
        source = self.source()
        self.assertNotIn("Stats::Get(player", source.replace("Stats::Get(guid)", ""))
        self.assertIn("base.classDRPct = 0;", source)
        self.assertIn("DC::Calculate(b, c)", source)
        for text in ("affix.legendaryRank", "mapping->second.resource", 'treated->second == "ignored"', "Detail::skillAffixes"):
            self.assertIn(text, source)

    def test_the_creature_and_the_relic_are_reached_from_the_companion(self):
        creature = (MODULE / "src/campaign/dc_follower_creature.cpp").read_text(encoding="utf-8")
        self.assertIn("Items::FollowerGear::OnCompanionSummoned(player, me, unsigned(row->id));", creature)
        self.assertIn("Items::FollowerGear::CannotDie(player)", creature)
        self.assertIn("damage = 0;", creature)
        items = (SRC / "dc_items.cpp").read_text(encoding="utf-8")
        self.assertIn("FollowerGear::RegisterScripts();", items)

    def test_the_find_stats_reach_the_player_under_ids_no_item_has(self):
        source = self.source()
        self.assertIn("ShareIdBase = 1ull << 62", source)
        self.assertIn("(saved.id & ShareIdBase)", source)
        self.assertIn("Shared(total, data.rules)", source)


class FixtureDatabaseTests(unittest.TestCase):
    """The migrations against the fixture mysqld's copy of the world (never the live one)."""

    scratch = harness_env.private_name("dc_follower_gear_test")

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
        self.query("CREATE TABLE item_template LIKE acore_world.item_template", self.scratch)

    def test_the_world_migration_writes_the_tables_and_the_nine_relics(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.query("", self.scratch, feed=sql)
        self.query("", self.scratch, feed=sql)  # applied again: the same rows
        count = lambda table: self.query(f"SELECT COUNT(*) FROM {table}", self.scratch)[0]
        self.assertEqual(count("dc_follower_gear_kind"), [("50",)])
        self.assertEqual(count("dc_follower_skill"), [("24",)])
        self.assertEqual(count("dc_follower_relic"), [("9",)])
        self.assertEqual(count("dc_follower_gear_rule"), [("3",)])
        self.assertEqual(count("dc_follower_gear_follower"), [("3",)])
        rows, _ = self.query("SELECT entry, Quality, InventoryType, class, name FROM item_template ORDER BY entry", self.scratch)
        self.assertEqual([r[0] for r in rows], [str(e) for e in range(103300, 103309)])
        self.assertTrue(all(r[1] == "5" and r[2] == "0" and r[3] == "15" for r in rows))
        joined, _ = self.query("SELECT COUNT(*) FROM dc_follower_relic r JOIN item_template i ON i.entry=r.item_entry AND i.name=r.name COLLATE utf8mb4_unicode_ci",
                               self.scratch)
        self.assertEqual(joined, [("9",)])
        mains, _ = self.query("SELECT follower_key, main_stat FROM dc_follower_gear_follower ORDER BY follower_id", self.scratch)
        self.assertEqual(mains, [("templar", "strength"), ("scoundrel", "dexterity"), ("enchantress", "intelligence")])

    def test_the_character_migration_keeps_each_follower_its_own_slot_and_one_home_per_item(self):
        sql = CHARACTER_MIGRATION.read_text(encoding="utf-8")
        self.query("", self.scratch, feed=sql)
        self.query("", self.scratch, feed=sql)
        self.query("INSERT INTO dc_character_follower_gear (guid, follower, slot, item_guid) VALUES (7, 1, 'ring1', 100), (7, 2, 'ring1', 101), (7, 3, 'ring1', 102)",
                   self.scratch)
        rows, _ = self.query("SELECT follower, item_guid FROM dc_character_follower_gear WHERE guid=7 AND slot='ring1' ORDER BY follower", self.scratch)
        self.assertEqual(rows, [("1", "100"), ("2", "101"), ("3", "102")])
        # One slot of one follower holds one item, and one item is in one slot.
        _, ran = self.query("INSERT INTO dc_character_follower_gear VALUES (7, 1, 'ring1', 103)", self.scratch, check=False)
        self.assertNotEqual(ran.returncode, 0)
        _, ran = self.query("INSERT INTO dc_character_follower_gear VALUES (7, 1, 'ring2', 100)", self.scratch, check=False)
        self.assertNotEqual(ran.returncode, 0)


DELETE_HARNESS = MODULE / "tests/follower_gear/delete_sql.cpp"
CORE_STATEMENTS = REPO / "azerothcore-wotlk/src/server/database/Database/Implementation/CharacterDatabase.cpp"
GEM_RANK_MIGRATION = MODULE / "data/sql/db-characters/updates/legendary_gems_0001_rank.sql"
ROLLED = ("dc_item_instance", "dc_item_affix", "dc_enchant_offer", "dc_item_unidentified", "dc_legendary_gem_rank")


def delete_statements(header_text, character):
    """DeleteCharacterSql compiled from `header_text` (the real header, or a mutant of it) and run for `character`."""
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    tree = SCRATCH / "delete_tree"
    shutil.rmtree(tree, ignore_errors=True)
    (tree / "src/items").mkdir(parents=True)
    (tree / "tests/follower_gear").mkdir(parents=True)
    shutil.copytree(MODULE / "src/common", tree / "src/common")
    (tree / "src/items" / HEADER.name).write_text(header_text, encoding="utf-8")
    shutil.copy(DELETE_HARNESS, tree / "tests/follower_gear/delete_sql.cpp")
    binary = tree / "delete_sql"
    built = subprocess.run([compiler, "-std=c++17", "-o", str(binary), str(tree / "tests/follower_gear/delete_sql.cpp")],
                           capture_output=True, text=True)
    if built.returncode != 0:
        raise AssertionError(built.stderr)
    ran = subprocess.run([str(binary), str(character)], capture_output=True, text=True)
    return [line[4:] for line in ran.stdout.splitlines() if line.startswith("SQL ")]


class DeleteCharacterTests(unittest.TestCase):
    """Deleting a character takes its followers' parked gear with it, rolled rows and all, and nobody else's."""

    scratch = harness_env.private_name("dc_follower_gear_delete_test")
    mine, other, bagged = 7, 8, 9

    @classmethod
    def setUpClass(cls):
        try:
            import fixture_db
            cls.mysql, cls.defaults = fixture_db.mysql_and_defaults([])
        except SystemExit as stopped:
            raise unittest.SkipTest(str(stopped))

    def query(self, sql, database=None):
        ran = subprocess.run([self.mysql, "--defaults-file=" + self.defaults, "--no-login-paths", "-N",
                              "--init-command=SET SESSION sql_mode=''", database or self.scratch, "-e", sql],
                             capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        return ran.stdout.strip()

    def count(self, table, where):
        return int(self.query(f"SELECT COUNT(*) FROM {table} WHERE {where}"))

    def setUp(self):
        self.query(f"DROP DATABASE IF EXISTS {self.scratch}", "mysql")
        self.query(f"CREATE DATABASE {self.scratch}", "mysql")
        self.addCleanup(self.query, f"DROP DATABASE IF EXISTS {self.scratch}", "mysql")
        for table in ("item_instance", "dc_item_instance", "dc_item_affix", "dc_enchant_offer", "dc_item_unidentified"):
            self.query(f"CREATE TABLE {table} LIKE acore_characters.{table}")
        # The fixture predates these two tables: each is made from its own migration.
        self.query(CHARACTER_MIGRATION.read_text(encoding="utf-8"))
        self.query(re.search(r"CREATE TABLE IF NOT EXISTS `dc_legendary_gem_rank`[^;]+",
                             GEM_RANK_MIGRATION.read_text(encoding="utf-8")).group(0))
        # Character 7 has a follower item with a full set of rolled rows and a second with only the gem rank; character 8
        # has one; character 9's item is in a bag, with no gear row, and is the core's hook to clear, not this one.
        for owner, item, follower, slot in ((self.mine, 100, 1, "head"), (self.mine, 101, 3, "relic"),
                                            (self.other, 200, 1, "head"), (self.bagged, 300, 0, "")):
            self.query(f"INSERT INTO item_instance(guid,itemEntry,owner_guid,count) VALUES({item},3000,{owner},1)")
            if follower:
                self.query(f"INSERT INTO dc_character_follower_gear VALUES({owner},{follower},'{slot}',{item})")
            for table, extra in (("dc_item_instance", ""), ("dc_item_affix", ",seq"), ("dc_enchant_offer", ""),
                                 ("dc_item_unidentified", ""), ("dc_legendary_gem_rank", "")):
                self.query(f"INSERT INTO {table}(item_guid{extra}) VALUES({item}{',0' if extra else ''})")

    def run_deletion(self, header_text):
        """What the core's Player::DeleteFromDB does to the items (Player.cpp:4308), then the hook's statements."""
        core = re.search(r'PrepareStatement\(CHAR_DEL_ITEM_INSTANCE_BY_OWNER, "([^"]+)"',
                         CORE_STATEMENTS.read_text(encoding="utf-8")).group(1).replace("?", str(self.mine))
        for statement in [core] + delete_statements(header_text, self.mine):
            self.query(statement)

    def left_of(self, items):
        return {table: self.count(table, f"item_guid IN ({items})") for table in ROLLED + ("dc_character_follower_gear",)} | {
            "item_instance": self.count("item_instance", f"guid IN ({items})")}

    def test_a_deleted_character_leaves_no_follower_gear_rows(self):
        self.run_deletion(HEADER.read_text(encoding="utf-8"))
        self.assertEqual(self.left_of("100,101"), dict.fromkeys(ROLLED + ("dc_character_follower_gear", "item_instance"), 0))

    def test_another_characters_gear_and_a_bagged_item_are_left_alone(self):
        self.run_deletion(HEADER.read_text(encoding="utf-8"))
        self.assertEqual(self.left_of("200"), dict.fromkeys(ROLLED + ("dc_character_follower_gear", "item_instance"), 1))
        # A bagged item's rolled rows go with the core's per-item hook (Items::Erase), never through this one.
        self.assertEqual(self.left_of("300")["dc_item_affix"], 1)
        self.assertEqual(self.count("dc_character_follower_gear", f"guid={self.other}"), 1)

    def test_each_part_of_the_deletion_is_needed(self):
        header = HEADER.read_text(encoding="utf-8")
        func = header[header.index("inline std::vector<std::string> DeleteCharacterSql"):header.index("} // namespace DC::Items::FollowerGear")]
        gear_row = re.search(r'        out\.push_back\("DELETE FROM dc_character_follower_gear[^\n]*\n', func).group(0)
        for name, changed in (
            ("a rolled table is skipped", func.replace('"dc_item_affix", ', "", 1)),
            ("the gem rank table is skipped", re.sub(r',\s*"dc_legendary_gem_rank"', "", func, 1)),
            ("the character filter is dropped", re.sub(r'WHERE g\.guid=" \+\s+std::to_string\(character\)', 'WHERE 1=1"', func, 1)),
            ("the gear rows go first", func.replace(gear_row, "").replace(
                "std::vector<std::string> out;\n", gear_row.replace("out.push_back(", "std::vector<std::string> out{").replace(");\n", "};\n"), 1)),
        ):
            mutant = header.replace(func, changed)
            self.assertNotEqual(mutant, header, name)
            with self.subTest(name):
                self.setUp()
                self.run_deletion(mutant)
                mine = self.left_of("100,101")
                other = self.left_of("200")
                self.assertTrue(any(mine.values()) or not all(other.values()), f"the test missed: {name}")


if __name__ == "__main__":
    unittest.main()
