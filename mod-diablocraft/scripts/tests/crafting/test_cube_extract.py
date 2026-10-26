"""diablocraft-wpt7l.10: Kanai's Cube, the Archive of Tal Rasha (plan docs/research/kanais-cube.md 6.2 and 7 row 11).

What this proves, and what it does not:

  * The sheet (`cube_rules.csv`) has the recipe: rule `extract`, six spend lines (5 Death's Breath and one each of the five act
    reagents, ledger entries 102008-102012), no make line; that is `cube_costs.csv`'s row for it (two sources) and its page is
    D3's text from the designer's capture. world_0053 and cube_0001 are the generator's render of both.
  * The rules (`dc_cube_rule.h`, compiled as it is): the recipe takes a Legendary item and not a Set one, consumes it, and
    `ExtractRefusal` refuses a power the framework has not built, one no slot lists, and one the account already has, in that order.
  * The handler (`dc_cube_window.h`, behind the real router, the recipe parsed out of world_0053): the list shows its six costs
    and no output, Fill gives its six cells, a transmute of the six cells reports the item removed, and a grid short one reagent
    is refused.
  * The glue, pinned as text, each pin also run on a reverted copy: TransmuteItem refuses a crafted item and runs every check
    before anything is taken, the power id is the framework's (PowerIdOf), the item is destroyed and the power is written in the
    one transaction (FinishExtract), a choice reaches the framework's Cube list, the login hands the saved slots to it, and the
    Items side puts a cubed stat power on the sheet (RefreshCubedStats).
  * NOT covered: TransmuteItem, ChooseCubePower, the login load or RefreshCubedStats against a database or the core (they need
    the live game), so a destroyed item, a lit power in the Collection panel, a power acting from its slot and Sun Keeper's elite
    damage on the sheet are the designer's Checks (docs/test-diablocraft-wpt7l.10.md).
"""
import re
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import generate_cube as G
from test_cube_items import RECIPES
from test_cube import CRAFTING, RULE, SRC, UPDATES, compile_cube, read_csv
from test_class_parity import mutate

ID = "archive_of_tal_rasha"
REAGENTS = (102008, 102009, 102010, 102011, 102012)
DEATHS_BREATH = 102000
SQL = RECIPES.read_text(encoding="utf-8")
ITEMS = items_source.source()


def cube(test, body, old=None, new=None):
    ok, out = compile_cube(body, sql=SQL)
    test.assertTrue(ok, out)
    if old is not None:
        ok, out = compile_cube(body, rule=mutate(RULE, old, new), sql=SQL)
        test.assertFalse(ok, "mutation survived: " + new)


class Generator(unittest.TestCase):
    def test_the_recipe_spends_five_breath_and_one_of_each_reagent_and_makes_no_material(self):
        recipes = {rid: (sort, rule, name, lines) for rid, sort, rule, name, lines in G.recipes()}
        sort, rule, name, lines = recipes[ID]
        self.assertEqual((rule, name, sort), ("extract", "Archive of Tal Rasha", 1))
        self.assertEqual([(kind, entry, amount) for _, kind, _, entry, amount in lines],
                         [("spend", DEATHS_BREATH, 5)] + [("spend", entry, 1) for entry in REAGENTS])

    def test_the_cost_is_both_d3_sheets_and_the_reagent_names(self):
        cost = [r for r in read_csv(G.DATA / "cube_costs.csv") if r["recipe_name"].endswith("Archive of Tal Rasha")][0]
        self.assertEqual(cost["deaths_breath"], "5")
        mine = ("khanduran_rune", "caldeum_nightshade", "arreat_war_tapestry", "corrupted_angel_flesh", "westmarch_holy_water")
        self.assertEqual([cost[k] for k in mine], ["1"] * 5)
        self.assertEqual(sum(int(cost[k]) for k in cost if k not in ("recipe_name", "other_inputs", "notes", "source_url")), 10)
        names = {int(r["item_entry"]): r["name"] for r in read_csv(G.DATA / "account_economy.csv")}
        text = [r for r in read_csv(G.DATA / "cube_recipes.csv") if "Archive of Tal Rasha" in r["recipe_name"]][0]["inputs"]
        for entry in REAGENTS:
            self.assertIn(names[entry], text)

    def test_the_recipe_and_the_page_are_d3s(self):
        # that world_0053 and the pages migration are the generator's render, with their mirrors, is test_cube_items and test_cube_grid's
        self.assertIn(f"('{ID}',1,'extract','Archive of Tal Rasha')", SQL)
        subtitle, item, note, quote, source = G.pages()[ID]
        self.assertEqual((subtitle, item, note), ("Extract Legendary Power", "Legendary Item with Special Power", ""))
        self.assertTrue(quote.startswith("...all agreed that the cube was necessary") and quote.endswith("understood the dangers."))
        self.assertEqual(source, "fragment of the Dark Exile Scrolls.")
        page_sql = (UPDATES / G.PAGES).read_text(encoding="utf-8")
        self.assertIn(f"('{ID}','Extract Legendary Power'", page_sql)

    def test_refusals(self):
        broken = __import__("test_cube").Generator("test_refusals").broken
        mine = lambda r: [x for x in r if x["recipe_id"] == ID]
        self.assertIn("makes no material", broken("cube_rules.csv", lambda r: r.append(dict(mine(r)[0], line="7", kind="make", rarity="set"))))
        self.assertIn("rule", broken("cube_rules.csv", lambda r: [x.update(rule="extraction") for x in mine(r)]))
        self.assertIn("spend the same reagents", broken("cube_rules.csv", lambda r: r.extend(
            dict(x, recipe_id="archive_two", sort="12", name="Archive Two") for x in mine(r))))


class Rules(unittest.TestCase):
    def test_it_takes_a_legendary_item_not_a_set_one_and_consumes_it(self):
        cube(self, r'''
    using namespace DC::Crafting::Cube;
    Recipe const& r = *Find(generated, "archive_of_tal_rasha");
    assert(Takes(r, "legendary") && !Takes(r, "set") && !Takes(r, "rare") && !Takes(r, "magic") && !Takes(r, "normal"));
    assert(Consumes(r) && !Makes(r, "legendary"));''',
             'recipe.rule == "extract" ? rarity == "legendary"',
             'recipe.rule == "extract" ? rarity == "legendary" || rarity == "set"')
        cube(self, r'''
    using namespace DC::Crafting::Cube;
    assert(Takes(*Find(generated, "archive_of_tal_rasha"), "legendary"));''',
             'recipe.rule == "extract" ? rarity == "legendary"',
             'recipe.rule == "extract" ? rarity == "set"')

    def test_extract_refusal_checks_built_then_listed_then_known(self):
        body = r'''
    using namespace DC::Crafting::Cube;
    assert(ExtractRefusal(true, true, false).empty());
    std::string const gone = "The Cube cannot extract that item's power yet.";
    assert(ExtractRefusal(false, true, false) == gone);                  // the framework has no row: no cost
    assert(ExtractRefusal(true, false, false) == gone);                  // no slot lists it
    assert(ExtractRefusal(false, false, true) == gone);                  // an unbuilt power is refused as unbuilt first
    assert(ExtractRefusal(true, true, true) == "You have already extracted that power.");'''
        cube(self, body, "if (!built || !listed)", "if (!built)")
        cube(self, body, "if (!built || !listed)", "if (!listed)")
        cube(self, body, "if (known)", "if (!known)")
        cube(self, body, "        if (!built || !listed)\n            return \"The Cube cannot extract that item's power yet.\";\n        if (known)\n            return \"You have already extracted that power.\";",
             "        if (known)\n            return \"You have already extracted that power.\";\n        if (!built || !listed)\n            return \"The Cube cannot extract that item's power yet.\";")


class Handler(unittest.TestCase):
    CELLS = "102000_5\t102008_1\t102009_1\t102010_1\t102011_1\t102012_1"

    def test_the_list_shows_its_six_costs_and_no_output(self):
        cube(self, r'''
    Rig rig; rig.game.funds.materials[102000] = "9"; rig.game.funds.materials[102008] = "1"; rig.cube("list");
    assert(rig.has("C|archive_of_tal_rasha|extract|Archive of Tal Rasha"));
    assert(rig.has("T|archive_of_tal_rasha|102000|5|9|1"));
    assert(rig.has("T|archive_of_tal_rasha|102008|1|1|1"));
    assert(rig.has("T|archive_of_tal_rasha|102012|1|0|0"));   // a short reagent is marked
    for (auto const& s : rig.sent) assert(s.rfind("DCCUBE\tY|archive", 0) != 0);''')

    def test_fill_gives_the_six_cells_when_the_ledger_holds_them(self):
        cube(self, r'''
    Rig rig;
    for (int e : {102000, 102008, 102009, 102010, 102011, 102012}) rig.game.funds.materials[e] = "5";
    rig.cube("fill\tarchive_of_tal_rasha");
    assert(rig.has("G|archive_of_tal_rasha|102000:5|102008:1|102009:1|102010:1|102011:1|102012:1"));
    rig.game.funds.materials[102010] = "0"; rig.cube("fill\tarchive_of_tal_rasha");
    assert(rig.refusal() == "Not enough materials for that recipe.");''')

    def test_a_transmute_of_the_six_cells_reports_the_item_removed_and_a_short_grid_is_refused(self):
        cube(self, r'''
    Rig rig;
    rig.game.effect = [&] { rig.game.bags.erase(42); for (int e : {102000, 102008, 102009, 102010, 102011, 102012}) rig.game.funds.materials[e] = "0"; };
    rig.cube("transmute\t42\t''' + self.CELLS + r'''");
    assert(rig.game.calls == std::vector<std::string>{"archive_of_tal_rasha 42"});
    assert(rig.sent.front() == "DCCUBE\tR|transmute|1" && rig.sent.back() == "DCCUBE\tE|transmute");
    Rig short_; short_.cube("transmute\t42\t102000_5\t102008_1\t102009_1\t102010_1\t102011_1");
    assert(short_.refusal() == "The Cube cannot use what is in the grid." && short_.game.calls.empty());''')


def outside_anonymous(text, marker):
    """Whether `marker` is defined at the depth of namespace DC::Items itself (braces counted over the text before it, comments and
    literals dropped), so in no anonymous namespace: a function there has internal linkage and another file cannot link to it."""
    at = text.find(marker)
    if at < 0:
        return False
    code = re.sub(r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'", "", text[:at], flags=re.S)
    return code.count("{") - code.count("}") == 1


def cut(text, start, end):
    """The text from `start` to `end`; empty when `start` is not there, so a missing piece fails its own test, not the import."""
    return text[text.index(start):text.index(end)] if start in text else ""


class Wiring(unittest.TestCase):
    BODY = cut(CRAFTING, "        void TransmuteItem(", "        void Transmute(Player* player")
    FINISH = cut(CRAFTING, "        void FinishExtract(", "        void TransmuteItem(")
    CHOOSE = cut(CRAFTING, "        void ChooseCubePower(", "        // Skill of Nilfur (set_convert)")
    SCRIPT = cut(CRAFTING, "        class CubeCharacters final", "        class Commands final")

    @staticmethod
    def branch(body):
        start = body.find('recipe.rule == "extract"')
        return body[start:body.index("            Amounts spend;")] if start >= 0 else ""

    def problems(self, body, finish, choose, script, items):
        found = []
        branch = self.branch(body)
        for pin, why in (
            ('Need(craftOnly != "yes" && !instance.crafted, "The Cube takes no crafted item for this recipe.");', "a crafted item is not refused"),
            ("power = Combat::ItemPowers::PowerIdOf((*id)[0].Get<std::string>());", "the power is not the framework's id of the item"),
            ("Cube::ExtractRefusal(Combat::ItemPowers::Built(power), listed, known)", "the refusal does not read built, listed and known"),
            ("Need(refusal.empty(), refusal.c_str());", "the refusal is not thrown before the spend"),
            ("CubePowerItems", "the slot list is not the power list's own query"),
            ("SELECT 1 FROM dc_cube_power WHERE account_id={} AND mode='{}' AND power_id='{}'", "the account's extracted set is not read"),
        ):
            if pin not in branch:
                found.append(why)
        destroy, finishing, roll = (body.find(x) for x in ("Items::DestroyWithRows(", "return FinishExtract(player, recipe, gone, *account, power, tx);", "Items::StageRoll("))
        if not 0 <= destroy < finishing < roll:
            found.append("the item is destroyed, then the power is written, and nothing is rolled")
        if not (finish.find('"INSERT IGNORE INTO dc_cube_power (account_id,mode,power_id) VALUES ({},\'{}\',\'{}\')"') >= 0
                and finish.index("INSERT IGNORE") < finish.index("Save(player, tx);")):
            found.append("the power is not written in the transaction the item and ledger are saved in")
        if not 0 <= choose.find("Need(Combat::ItemPowers::CubeSet(player, slot, power)") < choose.find("REPLACE INTO dc_cube_slot"):
            found.append("a choice reaches the framework before it is stored")
        if "Combat::ItemPowers::CubeClear(player, slot);" not in choose:
            found.append("emptying a slot does not clear the framework's Cube list")
        if choose.count("Items::RefreshCubedStats(player);") != 2:
            found.append("a choice or an empty does not refresh the cubed stats")
        for pin, why in (("PLAYERHOOK_ON_LOGIN", "the script does not hook login"),
                         ("SELECT slot,power_id FROM dc_cube_slot WHERE guid={}", "the saved slots are not read"),
                         ("Combat::ItemPowers::CubeSet(player, f[0].Get<uint32>(), f[1].Get<std::string>())", "the saved slots do not reach the framework"),
                         ("Items::RefreshCubedStats(player);", "the login does not refresh the cubed stats")):
            if pin not in script:
                found.append(why)
        refresh = cut(items, "void RefreshCubedStats(", "// --- stat sheet contribution")
        if not outside_anonymous(items, "void RefreshCubedStats("):
            found.append("RefreshCubedStats is in an anonymous namespace, so dc_cube.cpp cannot link to it")
        if "power.source != DC::Combat::ItemPower::Source::Cube" not in refresh:
            found.append("a worn power's stat rows would count twice")
        if "DC::Combat::ItemPower::CubeContributionId(ordinal, seq++)" not in refresh:
            found.append("a cubed stat is not keyed in the Cube's id range")
        if "contribution.value = row.max;" not in refresh:
            found.append("a cubed stat is not at the top of its range")
        apply = cut(items, "void Apply(Player* player, Item* item, bool equipping)", "bool UniqueEquippedAllows(")
        if "    RefreshCubedStats(player);\n}" not in apply:
            found.append("Apply does not refresh the cubed stats on every equip and unequip")
        if items.count("cubedStats.erase(player->GetGUID().GetRawValue());") != 2:
            found.append("login and logout do not forget the cubed stats")
        return found

    def args(self, **swap):
        parts = dict(body=self.BODY, finish=self.FINISH, choose=self.CHOOSE, script=self.SCRIPT, items=ITEMS)
        for key, (old, new) in swap.items():
            self.assertIn(old, parts[key], old)
            parts[key] = parts[key].replace(old, new)
        return parts

    def test_the_glue_is_right(self):
        self.assertEqual(self.problems(**self.args()), [])

    def test_each_pin_fails_on_a_reverted_copy(self):
        for swap in (
            dict(body=('Need(craftOnly != "yes" && !instance.crafted, "The Cube takes no crafted item for this recipe.");\n                auto id =', "auto id =")),
            dict(body=("power = Combat::ItemPowers::PowerIdOf((*id)[0].Get<std::string>());", "power = (*id)[0].Get<std::string>();")),
            dict(body=("Cube::ExtractRefusal(Combat::ItemPowers::Built(power), listed, known)", "Cube::ExtractRefusal(true, listed, known)")),
            dict(body=("Need(refusal.empty(), refusal.c_str());", "(void)refusal;")),
            dict(body=("return FinishExtract(player, recipe, gone, *account, power, tx);", "(void)0;")),
            dict(finish=("INSERT IGNORE INTO dc_cube_power", "INSERT IGNORE INTO dc_cube_slot")),
            dict(choose=("Need(Combat::ItemPowers::CubeSet(player, slot, power), \"That power is not available yet.\");", "(void)0;")),
            dict(choose=("Combat::ItemPowers::CubeClear(player, slot);", "(void)0;")),
            dict(choose=("Items::RefreshCubedStats(player);\n                return;", "return;")),
            dict(script=("Combat::ItemPowers::CubeSet(player, f[0].Get<uint32>(), f[1].Get<std::string>())", "true")),
            dict(script=("{PLAYERHOOK_ON_DELETE_FROM_DB, PLAYERHOOK_ON_LOGIN}", "{PLAYERHOOK_ON_DELETE_FROM_DB}")),
            dict(items=("power.source != DC::Combat::ItemPower::Source::Cube", "false")),
            dict(items=("contribution.value = row.max;", "contribution.value = row.min;")),
            dict(items=("// External linkage on purpose (declared in dc_items.h, called from dc_cube.cpp), so outside the anonymous namespaces.\n",
                        "namespace\n{\n")),
            dict(items=("    RefreshCubedStats(player);\n}\n\nbool UniqueEquippedAllows(", "}\n\nbool UniqueEquippedAllows(")),
        ):
            self.assertTrue(self.problems(**self.args(**swap)), swap)


if __name__ == "__main__":
    unittest.main()
