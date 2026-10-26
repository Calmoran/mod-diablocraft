"""diablocraft-t3t8 - Ancient and Primal Ancient items, executed where it can be.

What this suite proves, and what it does not:

  * The **decision** (chances, tier / item-level / Primal-unlock gates, the bracket an item reads, who may be
    Ancient) is the production header `src/items/dc_quality_rule.h`, compiled into
    `scripts/tests/loot/quality_tests.cpp` and driven with the tunables the generator emitted. Every rule has a
    mutation that must turn the harness red.
  * The **data**: affix_pools.csv's ancient rows equal D3Planner's `statLimits.ancient` for every stat the slot
    maps to a limit (reference/d3planner/slots.js), and primal rows equal ancient rows.
  * The **wiring** - that every legendary / set source decides the quality, the quality rides the shell, the
    buffer rows and the ground carrier, and identify rolls in it - is read from the code with comments removed.
    It is not executed: that needs a Player and a database and is the GM script in
    docs/test-diablocraft-t3t8.md. A Primal's "top of the bracket" lines are text-checked the same way.
  * The **migration** (loot_0011) uses information_schema and PREPARE, so it is checked as text only.
"""
import csv
import pathlib
import re
import shutil
import subprocess
import sys
import unittest

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import crafting_source  # noqa: E402
import applied_migrations
import harness_env

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

MODULE = pathlib.Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
SRC = MODULE / "src"
HEADER = SRC / "items" / "dc_quality_rule.h"
HARNESS = MODULE / "scripts" / "tests/loot" / "quality_tests.cpp"
D3 = MODULE / "data" / "d3"
SCRATCH = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "ancient_primal_t3t8"
SLOTS_JS = ROOT / "reference" / "d3planner" / "slots.js"


def code(path):
    """Source with comments removed, so prose cannot satisfy a wiring check."""
    return without_comments(pathlib.Path(path).read_text(encoding="utf-8"))


def without_comments(text):
    lines = []
    for line in text.splitlines():
        if line.strip().startswith(("//", "*", "/*")):
            continue
        lines.append(line.split("//")[0])
    return "\n".join(lines)


def tunable(name):
    """The effective value of a loot tunable in the generated migration: tuned, else D3's."""
    text = (MODULE / "data" / "generated" / "tunables_0012.sql").read_text(encoding="utf-8")
    match = re.search(r"\('loot', '%s', ([0-9.]+|NULL), ([0-9.]+|NULL)," % name, text)
    assert match, name + " is not in the generated tunables"
    d3_value, tuned = match.groups()
    return float(tuned if tuned != "NULL" else d3_value)


def build(include_dir, name, strict=True):
    compiler = shutil.which("c++") or shutil.which("g++")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = SCRATCH / name
    flags = ["-Wall", "-Wextra", "-Werror"] if strict else []
    built = subprocess.run([compiler, "-std=c++17", "-O1", *flags, "-I", str(include_dir), str(HARNESS), "-o", str(binary)],
                           capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
    return binary


def run(binary):
    return harness_env.run([str(binary), *(str(tunable(n)) for n in (
        "ancient_chance_pct", "primal_chance_pct", "ancient_min_tier", "ancient_min_item_level",
        "ancient_min_tier_gamble"))],
        capture_output=True, text=True)


# One mutation per rule; each must make the harness fail.
MUTATIONS = [
    ("the tier gate is gone", "tier < minTier ||", ""),
    ("a gamble keeps the monster drop's tier gate", "gambled ? rule.gambleMinTier : rule.minTier", "rule.minTier"),
    ("a monster drop takes the gamble's open gate", "gambled ? rule.gambleMinTier : rule.minTier", "rule.gambleMinTier"),
    ("the item-level gate is gone", "|| itemLevel < rule.minItemLevel", ""),
    ("Primal needs no unlock", "primalUnlocked ? std::clamp(rule.primalPct, 0.0, 100.0) : 0.0",
     "std::clamp(rule.primalPct, 0.0, 100.0)"),
    ("a Rare can be Ancient", 'return rarity == "legendary" || rarity == "set";', "return true;"),
    ("Ancient ignores its chance", "pct < primal + ancient ? \"ancient\"", "pct < primal + ancient * 2 ? \"ancient\""),
    ("Primal takes Ancient's slice", "pct < primal + ancient", "pct < ancient"),
    ("Primal reads the ancient bracket's name wrong", "(quality == \"ancient\" || quality == \"primal\")",
     "(quality == \"ancient\")"),
    ("an Ancient reads the legendary bracket", "return quality;\n        return (rarity", "return \"legendary\";\n        return (rarity"),
    ("every quality rolls at the top", 'return quality == "primal";', "return quality != \"normal\";"),
    ("an unknown tier is trusted", 'return quality == "ancient" || quality == "primal" ? quality : "normal";',
     "return quality;"),
]


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which("c++") or shutil.which("g++")):
            raise unittest.SkipTest("no C++ compiler")
        cls.binary = build(HEADER.parent, "quality_tests")

    def test_the_production_header_passes_on_the_sheet_values(self):
        result = run(self.binary)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("quality rules OK", result.stdout)

    def test_the_chances_are_alexs_ten_and_a_quarter_percent(self):
        self.assertEqual(tunable("ancient_chance_pct"), 10.0)
        self.assertEqual(tunable("primal_chance_pct"), 0.25)
        self.assertEqual(tunable("ancient_min_tier"), 5.0)          # Torment I (dc_tier_phase)
        self.assertEqual(tunable("ancient_min_item_level"), 70.0)
        self.assertEqual(tunable("ancient_min_tier_gamble"), 0.0)   # D3: a gamble or craft needs level 70 on any difficulty
        self.assertEqual(tunable("primal_unlock_solo_gr"), 70.0)
        out = run(self.binary).stdout
        self.assertIn("legendary unlocked ancient=10% primal=0.25%", out)
        self.assertIn("set locked ancient=10% primal=0%", out)

    def test_torment_one_is_tier_five(self):
        sql = (MODULE / "data" / "sql" / "db-world" / "updates" / "difficulty_0001_tier_phase.sql").read_text(encoding="utf-8")
        rows = dict((name, int(tier)) for tier, _phase, name in re.findall(r"\((\d+),(\d+),'([^']+)'\)", sql))
        self.assertEqual(rows["Torment I"], int(tunable("ancient_min_tier")))

    def test_every_mutation_fails(self):
        for index, (label, old, new) in enumerate(MUTATIONS):
            with self.subTest(mutation=label):
                source = HEADER.read_text(encoding="utf-8")
                self.assertEqual(source.count(old), 1, "mutation target moved: " + old)
                folder = SCRATCH / ("mutant_%d" % index)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "dc_quality_rule.h").write_text(source.replace(old, new), encoding="utf-8")
                result = run(build(folder, "mutant", strict=False))
                self.assertNotEqual(result.returncode, 0, label + " was not caught:\n" + result.stdout)


def planner_limits():
    """{limit name: (min, max, min2, max2)} for legendary and ancient, and {slot: {affix: limit name}}."""
    js = SLOTS_JS.read_text(encoding="utf-8")
    start = js.index("DiabloCalc.statLimits")

    def block(name):
        i = js.index("\n  %s: {" % name, start)
        return js[i:js.index("\n  },", i)]

    def parse(text):
        out = {}
        for m in re.finditer(r"(\w+): \{([^}]*)\}", text):
            vals = dict(re.findall(r"(\w+): ([-\d.]+)", m.group(2)))
            out[m.group(1)] = tuple(float(vals[k]) if k in vals else None for k in ("min", "max", "min2", "max2"))
        return out

    legendary, ancient = parse(block("legendary")), parse(block("ancient"))
    ancient = {**legendary, **ancient}                      # slots.js:262-269: what ancient does not redefine inherits
    slots = {}
    body = js[js.index("DiabloCalc.itemSlots"):]
    for m in re.finditer(r"\n  (\w+): \{\n    name:.*?affixes: \{(.*?)\n    \},", body, re.S):
        slots.setdefault(m.group(1), dict(re.findall(r'(\w+): "(\w+)"', m.group(2))))
    return legendary, ancient, slots


class Data(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (D3 / "affix_pools.csv").open(encoding="utf-8", newline="") as stream:
            cls.rows = list(csv.DictReader(stream))
        cls.legendary, cls.ancient, cls.slots = planner_limits()

    @staticmethod
    def pair(row):
        f = lambda x: float(x) if x else None
        return (f(row["value_min"]), f(row["value_max"]), f(row["value_min2"]), f(row["value_max2"]))

    def test_the_ancient_rows_are_d3planners_ancient_limits(self):
        checked = 0
        for row in self.rows:
            if row["item_level_bracket"] != "ancient" or row["weapon_class"]:
                continue
            limit = self.slots.get(row["slot"], {}).get(row["affix_id"])
            if limit not in self.ancient:
                continue
            checked += 1
            got, want = self.pair(row), self.ancient[limit]
            # Jewelry damage and Bleed carry one value in our pool; their second range is not rolled
            # (the pool has never held it, for legendary either), so the first range is the check.
            self.assertEqual(got[:2], want[:2], "%s %s (%s)" % (row["slot"], row["affix_id"], limit))
            if row["affix_id"] not in ("wpnphy", "bleed"):
                self.assertEqual(got, want, "%s %s (%s)" % (row["slot"], row["affix_id"], limit))
        self.assertGreater(checked, 200)

    def test_the_weapon_damage_rows_are_the_ancient_damage_limits(self):
        classes = {"damage1HNormal": "damage1HNormal", "damage1HFast": "damage1HFast", "damage2H": "damage2H"}
        seen = set()
        for row in self.rows:
            if row["item_level_bracket"] != "ancient" or not row["weapon_class"]:
                continue
            self.assertEqual(self.pair(row), self.ancient[classes[row["weapon_class"]]], row["slot"] + row["affix_id"])
            seen.add(row["weapon_class"])
        self.assertEqual(seen, set(classes))

    def test_the_ancient_bracket_really_redefines_the_main_stats(self):
        by = {(r["slot"], r["affix_id"], r["item_level_bracket"], r["weapon_class"]): self.pair(r) for r in self.rows}
        self.assertEqual(by[("head", "mainstat", "legendary", "")][:2], (626.0, 750.0))
        self.assertEqual(by[("head", "mainstat", "ancient", "")][:2], (825.0, 1000.0))
        self.assertGreater(sum(1 for (s, a, b, w), v in by.items() if b == "ancient" and v != by[(s, a, "legendary", w)]), 100)

    def test_primal_is_the_ancient_bracket_row_for_row(self):
        by = {}
        for r in self.rows:
            by.setdefault((r["slot"], r["affix_id"], r["weapon_class"]), {})[r["item_level_bracket"]] = self.pair(r)
        for key, brackets in by.items():
            self.assertEqual(brackets["primal"], brackets["ancient"], str(key))
        self.assertEqual({r["item_level_bracket"] for r in self.rows}, {"rare", "legendary", "ancient", "primal"})

    def test_the_primal_look_is_its_own_row(self):
        with (D3 / "ground_loot_visuals.csv").open(encoding="utf-8", newline="") as stream:
            visuals = {r["rarity"]: r for r in csv.DictReader(stream)}
        self.assertEqual(visuals["primal"]["plate_level"], "6")
        self.assertGreater(int(visuals["primal"]["beam_spell"]), 0)
        self.assertNotEqual(visuals["primal"]["beam_spell"], visuals["legendary"]["beam_spell"])
        self.assertEqual(sorted(int(v["plate_level"]) for v in visuals.values()), [1, 2, 3, 4, 5, 6])

    def test_the_primal_ground_label_is_red_from_the_one_palette(self):
        # diablocraft-ipc7: the label's triple names the plate level's rarity (RarityForLevel: "primal"), and the
        # plate colours its name out of the tooltip's DCRARITY by that word; so the one palette row makes it red.
        tooltip = (MODULE / "lua" / "aio" / "dc_tooltip.lua").read_text(encoding="utf-8")
        self.assertIn("set={0,1,0},primal={1,.1,.1}}", tooltip)
        plates = (MODULE / "lua" / "aio" / "dc_ground_plates.lua").read_text(encoding="utf-8")
        self.assertIn("local colour = palette and palette[rarity]", plates)
        ground = code(SRC / "loot" / "dc_ground_loot.cpp")
        self.assertIn("RarityForLevel(carrier->GetLevel())", ground)


class Wiring(unittest.TestCase):
    """The production paths call the tested functions; comments removed first."""

    @classmethod
    def setUpClass(cls):
        cls.items = without_comments(items_source.source())
        cls.loot = code(SRC / "loot" / "dc_loot.cpp") + "\n" + code(SRC / "loot" / "dc_loot_delivery.cpp")   # R4: split
        cls.ground = code(SRC / "loot" / "dc_ground_loot.cpp")
        cls.corpse = code(SRC / "loot" / "dc_corpse_loot.cpp")
        cls.identify = code(SRC / "items" / "dc_identify.cpp")

    def test_the_decision_is_made_by_the_tested_header_from_the_tunables(self):
        self.assertIn("DC::Quality::Decide(rarity, QualityRule()", self.items)
        for name in ("ancient_chance_pct", "primal_chance_pct", "ancient_min_tier", "ancient_min_item_level",
                     "ancient_min_tier_gamble", "primal_unlock_solo_gr"):
            self.assertIn('"loot", "%s"' % name, self.items)

    def test_every_drop_source_decides_the_quality_once_at_the_drop(self):
        # The loot roll and the first-kill legendary decide before delivery, with the monster drop's tier gate; the set
        # and bounty caches pass no quality to StageRoll, so it decides there with that same gate; identify passes the
        # shell's.
        self.assertEqual(self.loot.count("DC::Items::RollQuality("), 2)
        self.assertIn("std::string qualityTier = quality.empty() ? RollQuality(player, baseItemId, itemLevel)", self.items)
        for path in ("items/dc_set_cache.cpp", "bounties/dc_bounty_cache.cpp"):
            text = code(SRC / path)
            call = text[text.index("StageRoll("):]
            self.assertNotIn("Quality", call[:call.index(");")], path)
        self.assertIn("rollClass,\n                                          row->qualityTier)", self.identify)

    def test_a_gamble_or_craft_decides_with_the_level_gate_only(self):
        # Kadala, the slot vendors, the Cube and the artisans pass the quality they
        # decided with `gambled`; a monster drop and the caches keep ancient_min_tier.
        self.assertRegex(code(SRC / "items" / "dc_items.h"), r"unsigned tier = 0,\s+bool gambled = false\);")
        self.assertIn("PrimalUnlocked(player), distribution(Engine()), gambled);", self.items)
        self.assertIn('rule.gambleMinTier = static_cast<unsigned>(DC::Tunables::Get("loot", "ancient_min_tier_gamble"));', self.items)
        sites = {
            "loot/dc_kadala.cpp": "DC::Items::RollQuality(player, base, level, 0, true)",
            "items/dc_slot_vendor.cpp": "RollQuality(player, entry, player->GetLevel(), 0, true)",
            "crafting/dc_cube.cpp": "Items::RollQuality(player, pick, player->GetLevel(), 0, true)",
        }
        for path, call in sites.items():
            self.assertEqual(code(SRC / path).count(call), 1, path)
        crafting = without_comments(crafting_source.source())
        self.assertIn("Items::RollQuality(player, entry, level, 0, true)", crafting)          # the artisan craft
        self.assertRegex(crafting, r"if \(quality\.empty\(\)\)\s+quality = Items::RollQuality\(player, pick, player->GetLevel\(\), 0, true\);")
        # Nilfur and Curiosity decided theirs first, so the Cube's fallback never reaches them.
        fallback = crafting.index("if (quality.empty())")
        self.assertLess(crafting.index('quality = "normal";'), fallback)
        self.assertLess(crafting.index('quality = "primal";'), fallback)
        # Nothing else passes `gambled`: the drops and both caches keep the Torment I gate.
        for path in ("loot/dc_loot.cpp", "loot/dc_loot_delivery.cpp", "loot/dc_ground_loot.cpp", "loot/dc_corpse_loot.cpp", "items/dc_set_cache.cpp",
                     "bounties/dc_bounty_cache.cpp", "common/dc_world.cpp"):
            self.assertNotRegex(code(SRC / path), r"RollQuality\([^;]*, true\)", path)

    def test_the_quality_rides_every_hop_between_the_drop_and_identify(self):
        self.assertEqual(self.loot.count(",quality)") + self.loot.count(", quality)"), 15)
        self.assertIn("quality_tier) \"\n            \"VALUES ({},{},{},'{}','{}',{},{},'{}','{}')", self.loot)
        self.assertIn("rollClass, quality_tier) \"\n        \"VALUES ({}, {}, {}, '{}', '{}', {}, {}, '{}', '{}')", self.loot.replace("roll_class,", "rollClass,"))
        self.assertIn("roll_class, quality_tier) \"", self.loot)
        self.assertIn("roll_class,quality_tier \"", self.loot)
        self.assertIn("DC::Quality::Clean(f[13].Get<std::string>())", self.loot)
        self.assertIn("expires_at,roll_class,quality_tier)", self.ground)
        self.assertIn("expires_at,roll_class,quality_tier)", self.corpse)
        self.assertIn("DC::Quality::Clean(quality)", self.corpse)
        self.assertIn("shell.qualityTier = DC::Quality::Clean(", self.items)

    def test_the_instance_row_stores_the_decided_quality_not_normal(self):
        self.assertIn("VALUES ({}, {}, '{}', '{}')\",\n        itemGuid, baseItemId, qualityTier,", self.items)
        self.assertNotIn("quality_tier, rarity) VALUES ({}, {}, 'normal'", self.items)

    def test_the_roll_reads_the_quality_bracket_and_the_mystic_keeps_it(self):
        self.assertIn("BracketFor(base.rarity, qualityTier)", self.items)
        self.assertIn("BracketFor(instance.rarity, instance.qualityTier)", self.items)
        # a Bottomless potion is Legendary but never Ancient (diablocraft-1z5ye)
        self.assertIn("if (!DC::Quality::Eligible(base.rarity) || base.slot == \"potion\")\n            qualityTier = \"normal\";", self.items)

    def test_a_primal_rolls_every_value_at_the_top(self):
        self.assertIn("bool const atTop = DC::Quality::AtTop(qualityTier);", self.items)
        self.assertIn("auto valueOf = [&](PoolEntry const& entry) { return atTop ? entry.max : RollValue(entry); };", self.items)
        self.assertIn("affix.value2 = atTop ? entry.max2 : affix.value + RollWeaponDelta(entry);", self.items)
        stage = self.items[self.items.index("auto valueOf"):self.items.index("RollPlanInput planning;")]
        self.assertEqual(stage.count("valueOf(entry)"), 6)       # sockets, weapon element, armor element (hcwjv), single resist (fjutd), skill group, ordinary affix
        self.assertEqual(stage.count("RollValue(entry)"), 1)      # only inside valueOf itself

    def test_the_mystic_draws_a_primals_top_in_one_place_and_an_ancient_inside_its_own_bracket(self):
        # diablocraft-ipc7. The one place: MysticCtx::Value; the roll and the choice list both draw through it.
        self.assertEqual(code(SRC / "items" / "dc_enchant_rule.h").count("ctx.Value("), 1)
        self.assertIn("in.ctx.atTop = DC::Quality::AtTop(instance.qualityTier);", self.items)
        value = self.items[self.items.index("std::pair<double, double> Value(Enchant::Cand const& c) const"):]
        value = value[:value.index("std::string WeaponClass()")]
        self.assertIn("if (atTop)\n            return {c.max, c.max2 > 0 ? c.max2 : 0.0};", value)
        self.assertLess(value.index("if (atTop)"), value.index("RollValue(entry)"))   # a Primal never draws
        # `?` shows a Primal's single value: the preview picks collapse to their max
        self.assertIn("if (in.ctx.atTop)\n        {\n            pick.min = pick.max;\n            pick.min2 = pick.max2;", self.items)
        # An Ancient reroll reads the ancient bracket's rows (not the legendary ones), and the two differ.
        # (head mainstat: legendary 626-750, ancient 825-1000, pinned above; Bracket("legendary","ancient") ==
        # "ancient" is executed by quality_tests.cpp). The Mystic's pool is that bracket's rows, so its draw
        # stays inside them.
        self.assertIn("PoolFor(base->second, BracketFor(instance.rarity, instance.qualityTier))", self.items)
        self.assertIn("for (PoolEntry const& p : bracket)\n        in.pool.push_back(", self.items)

    def test_a_primal_ground_drop_wears_the_primal_look(self):
        self.assertIn('quality == "primal" ? visuals.find("primal") : visuals.end()', self.ground)
        self.assertIn("if (look == visuals.end()) look = visuals.find(rarity);", self.ground)

    def test_a_gm_can_force_and_read_the_quality(self):
        self.assertIn('{"quality", HandleQuality, SEC_ADMINISTRATOR, Console::No}', self.items)
        self.assertIn("forcedQuality[key] = choice;", self.items)
        self.assertIn("auto shell = GetUnidentified(itemGuid)", self.items)

    def test_the_account_unlock_reads_the_account_best_in_the_characters_mode(self):
        level = code(SRC / "rifts" / "dc_gr_level.cpp")
        self.assertIn("FROM dc_account_gr_solo s JOIN characters c ON c.account=s.account_id", level)
        self.assertIn("s.mode='{}'),0)\",\n                guid, ModeKey(guid)", level)

    def test_startup_refuses_a_database_without_the_columns(self):
        self.assertIn("SELECT COUNT(quality_tier) FROM dc_item_unidentified", self.items)
        self.assertIn("SELECT COUNT(quality_tier) FROM dc_loot_buffer", self.loot)


class Migration(unittest.TestCase):
    def test_both_tables_gain_quality_tier_idempotently(self):
        sql = (MODULE / "data/sql/db-characters/updates/loot_0011_quality_tier.sql").read_text(encoding="utf-8")
        for table in ("dc_item_unidentified", "dc_loot_buffer"):
            self.assertIn("table_name='%s' AND column_name='quality_tier'" % table, sql)
            self.assertIn("ALTER TABLE %s ADD COLUMN `quality_tier` ENUM(''normal'',''ancient'',''primal'')" % table, sql)
        self.assertEqual(sql.count("IF(@dc_exists=0"), 2)
        self.assertNotRegex(sql, r"(?i)\bINSERT\b|\bUPDATE\b|\bDELETE\b")

    def test_the_new_files_sort_after_the_tables_they_alter(self):
        updates = MODULE / "data/sql/db-characters/updates"
        names = sorted(p.name for p in updates.glob("*.sql"))
        new = "loot_0011_quality_tier.sql"
        for table_file in ("items_0003_unidentified.sql", "loot_0001_loot_buffer.sql", "loot_0009_corpse_rows.sql"):
            self.assertLess(names.index(table_file), names.index(new))

    def test_the_primal_look_migration_shipped_as_committed_beside_the_applied_one(self):
        """loot_0008 is applied and carries no primal row; loot_0011 adds it and is applied too, unchanged.

        This used to assert that loot_0011 was NOT in the manifest, which was true while it was unreleased.
        update 9 shipped it (the file is in the cut 1841e9cd) and that update's record, eadfb5e4
        (2026-10-11, 'applied_migrations +46 from live'), refreshed data/sql/applied_migrations.csv from the
        live updates table - so the assertion became false on the data, not in the data. What the manifest is
        the authority for still holds and is what the check is now: the file applied is the file in the tree.
        """
        manifest = applied_migrations.load_manifest(MODULE)
        visuals = MODULE / "data/sql/db-world/updates/loot_0008_ground_visuals.sql"
        primal = MODULE / "data/sql/db-world/updates/loot_0011_ground_visual_primal.sql"
        self.assertTrue(applied_migrations.is_applied(MODULE, visuals))
        self.assertNotIn("primal", visuals.read_text(encoding="utf-8"))
        self.assertTrue(applied_migrations.is_applied(MODULE, primal), "update 9 shipped it")
        self.assertEqual(manifest.get(applied_migrations.manifest_key(MODULE, primal)),
                         applied_migrations.sha1(primal.read_bytes()),
                         "loot_0011 is applied and the file has changed since: an applied migration is immutable")
        self.assertIn("('primal',6,", primal.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
