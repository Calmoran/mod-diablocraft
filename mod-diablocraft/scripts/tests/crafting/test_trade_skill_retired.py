#!/usr/bin/env python3
"""The trade skill pilot is retired whole (diablocraft-professions-fixes, decisions.md 2026-10-03 R4).

Four things, each with a mutation that must fail:
  * no pilot piece is left in the code, data, scripts or addon, and nothing calls one;
  * the retirement migrations and the client DBCs remove every row the pilot added;
  * the Jeweler's gem-removal price has one source (the charged `jeweler_unsocket_gold`): the
    unused `economy.jeweler_remove_gold` tunable and the `removeGold` the window never showed are gone;
  * the combine refusal names gold, not the retired Gold Bars.
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
MODULE = HERE.parent
ROOT = MODULE.parent

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import crafting_source  # noqa: E402
import generate_trade_skill_retirement as retirement
from dbc_store import Store, schema

# Pieces of the pilot that no live file may still carry. The retirement generator and this test name
# them on purpose; world_0013 is the frozen history of the rows it added, and the applied-migrations
# manifest lists it.
PILOT_WORDS = re.compile(r"tradeskill_pilot|TradeSkillPilot|PilotReagents|PilotData|PilotRecipe|GrantPilotSkills|"
                         r"dc_tradeskill_reagents|DiablocraftTradeSkillPilot")
HISTORY = {"mod-diablocraft/scripts/generate/crafting/generate_trade_skill_retirement.py",
           "mod-diablocraft/scripts/tests/crafting/test_trade_skill_retired.py",
           "mod-diablocraft/data/sql/db-world/updates/world_0013_tradeskill_pilot.sql",
           "mod-diablocraft/data/sql/applied_migrations.csv",
           "mod-diablocraft/data/sql/db-world/updates/world_0029_trade_skill_retired.sql"}
LIVE_DIRS = ("mod-diablocraft/src", "mod-diablocraft/lua", "mod-diablocraft/scripts", "mod-diablocraft/data",
             "client-patch/addons", "client-patch/dbc")
TEXT = {".cpp", ".h", ".lua", ".py", ".csv", ".sql", ".toc", ".xml", ".sh"}


def live_files(root=ROOT):
    for folder in LIVE_DIRS:
        for path in sorted((root / folder).rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and path.suffix in TEXT and rel not in HISTORY and "__pycache__" not in rel:
                yield rel, path


def leftovers(files):
    return [rel for rel, path in files if PILOT_WORDS.search(path.read_text(encoding="utf-8", errors="replace"))]


def removal_price_problems(cpp, lua, sheet):
    problems = []
    if "removeGold" in lua or "jeweler_remove_gold" in lua:
        problems.append("the Jeweler sends a removal price the server never charges")
    if "jeweler_remove_gold" in sheet:
        problems.append("the unused gem-removal tunable is back")
    # Both removal paths (remove, and the swap's removal) charge the one sourced price.
    if len(re.findall(r'SourcedCount\("jeweler_unsocket_gold"\)', cpp)) != 2 or "Economy::GoldCost(unsocketGold)" not in cpp:
        problems.append("the charged removal price is not the sourced one in both paths")
    return problems


class TradeSkillRetired(unittest.TestCase):
    def test_no_pilot_piece_remains(self):
        self.assertEqual(leftovers(live_files()), [])
        for gone in ("mod-diablocraft/lua/aio/dc_tradeskill_pilot.lua", "client-patch/addons/Torment/TradeSkillPilot.lua",
                     "mod-diablocraft/src/crafting/dc_tradeskill_pilot_data.h", "mod-diablocraft/data/tradeskill_pilot.csv",
                     "mod-diablocraft/data/generated/tradeskill_pilot.sql",
                     "mod-diablocraft/scripts/generate_tradeskill_pilot.py"):
            self.assertFalse((ROOT / gone).exists(), gone)

    def test_a_pilot_piece_is_found(self):
        scratch = ROOT / "azerothcore-wotlk/build/_agent-scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        probe = scratch / "pilot-leftover-probe.cpp"
        try:
            probe.write_text("void GrantPilotSkills(Player*);\n")
            self.assertEqual(leftovers([("probe", probe)]), ["probe"])
        finally:
            probe.unlink(missing_ok=True)

    def test_dbcs_and_migrations_remove_every_pilot_row(self):
        for name, (table, values) in retirement.STORES.items():
            store = Store((ROOT / "client-patch/dbc" / f"{name}.dbc").read_bytes(), schema(ROOT, table))
            self.assertEqual([v for v in values if v in store.rows], [], name)
        world = (MODULE / "data/sql/db-world/updates" / retirement.WORLD_MIGRATION).read_text(encoding="utf-8")
        for table, values in retirement.STORES.values():
            self.assertIn(f"DELETE FROM `{table}` WHERE ID IN ({','.join(map(str, values))});", world)
        self.assertIn("DELETE FROM spell_script_names WHERE spell_id IN (85002,85003)", world)
        characters = (MODULE / "data/sql/db-characters/updates" / retirement.CHARACTER_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("DELETE FROM character_spell WHERE spell IN (85000,85001,85002,85003);", characters)
        self.assertIn("DELETE FROM character_skills WHERE skill IN (1000,1001);", characters)

    def test_the_retired_rules_are_not_the_class_proficiency_ids(self):
        # The class proficiency rules start at 1002; the pilot's two were 1000 and 1001.
        self.assertTrue(set(retirement.RACE_CLASS_RULES).isdisjoint(range(1002, 2000)))

    def test_gem_removal_price_has_one_source(self):
        cpp = crafting_source.source()
        lua = (MODULE / "lua/aio/dc_jeweler.lua").read_text(encoding="utf-8")
        sheet = (MODULE / "data/tunables/economy.csv").read_text(encoding="utf-8")
        self.assertEqual(removal_price_problems(cpp, lua, sheet), [])
        self.assertIn("jeweler_remove_gold", (MODULE / "data/sql/db-world/updates" / retirement.WORLD_MIGRATION).read_text())
        self.assertNotEqual(removal_price_problems(cpp.replace("jeweler_unsocket_gold", "jeweler_remove_gold", 1), lua, sheet), [])
        self.assertNotEqual(removal_price_problems(cpp, lua + "\nlocal x = {removeGold = 0}", sheet), [])
        self.assertNotEqual(removal_price_problems(cpp, lua, sheet + "jeweler_remove_gold,,0,gold,x\n"), [])

    def test_combine_refusal_names_gold_not_gold_bars(self):
        cpp = crafting_source.source()
        combine = re.search(r"void Combine\(.*?\n        \}\n", cpp, re.S).group(0)
        self.assertIn('Need(Economy::CanAfford(player, price), "Not enough account gold.");', combine)
        self.assertNotIn("Gold Bars", cpp)
        self.assertIn("Gold Bars", cpp.replace("Not enough account gold.", "Not enough gold and Gold Bars.", 1))


if __name__ == "__main__":
    unittest.main()
