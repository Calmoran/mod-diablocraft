"""diablocraft-wpt7l.7 and .9: Kanai's Cube, Skill of Nilfur, Hope of Cain and Law of Kulle (plan docs/research/kanais-cube.md 7 row 6; the designer's
answers to q-1011-01, decisions 2026-10-12: equal chance on random picks, the defaults of question 6).

1. The generator: world_0053 is the render of every recipe and its mirror (generate_cube.py --migration), and sorts after
   world_0044 and world_0042, which are applied on dev (applied_migrations_dev.csv) and keep the bytes they were applied with:
   world_0042 the three Iben Fahd conversions, world_0044 every recipe in the first page order. The two rows are cube_costs.csv's costs; an item recipe makes no material;
   the set size floor is a tunable with D3's 3. Cross-source: every Rare's item type has a legendary or set item in the drop
   pool, and the sets under the floor are D3's 2-piece sets.
2. The rules (dc_cube_rule.h, compiled as it is): what each recipe takes, and Nilfur's pick of the set's other pieces.
3. The handler (dc_cube_window.h, behind the real router, the recipes parsed out of world_0053): the list shows the two with
   their costs and no outputs; a transmute that consumes the item reports it removed.
4. The glue (dc_crafting.cpp), pinned as text: every check before anything is spent, the item destroyed before the new one
   is staged, Nilfur at normal quality, Hope through the drop's own pick with the Rare's item type.
5. Replay: world_0042, world_0044 then world_0053, each twice, on a disposable MySQL.
Each rule test runs again on a mutation that breaks the rule, and that run must fail.
"""
import re
import subprocess
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import applied_migrations as am
import generate_cube as G
from test_class_parity import mutate
from test_cube import CRAFTING, RULE, UPDATES, compile_cube, read_csv, table

APPLIED = UPDATES / G.RECIPES
# The newest full rewrite of the sheet's recipes (generate_cube.py --migration): the one a fresh database ends on.
RECIPES = UPDATES / "world_0053_cube_recipe_order.sql"
SQL = RECIPES.read_text(encoding="utf-8") if RECIPES.exists() else ""
COLUMN = {102000: "deaths_breath", 102001: "reusable_parts", 102002: "arcane_dust", 102003: "veiled_crystals",
          102004: "forgotten_souls", 102008: "khanduran_rune", 102009: "caldeum_nightshade", 102010: "arreat_war_tapestry",
          102011: "corrupted_angel_flesh", 102012: "westmarch_holy_water"}


def cube(test, body, old=None, new=None):
    """The body runs on the real headers with world_0053's recipes, and fails on dc_cube_rule.h with `old` made `new`."""
    ok, out = compile_cube(body, sql=SQL)
    test.assertTrue(ok, out)
    if old is not None:
        ok, out = compile_cube(body, rule=mutate(RULE, old, new), sql=SQL)
        test.assertFalse(ok, "mutation survived: " + new)


class Generator(unittest.TestCase):
    def test_the_migration_is_the_render_and_its_mirror_after_world_0042(self):
        sql = G.render_recipes()
        self.assertEqual(SQL, sql)
        self.assertEqual((G.MODULE / "data/generated" / RECIPES.name).read_text(encoding="utf-8"), sql)
        self.assertNotIn(RECIPES, [UPDATES / key.split("/", 1)[1] for key in am.load_manifest(G.MODULE)])
        names = sorted(p.name for p in UPDATES.glob("*.sql"))
        self.assertGreater(names.index(RECIPES.name), names.index(G.RECIPES))
        self.assertGreater(names.index(G.RECIPES), names.index(G.NAME))
        # world_0042 keeps the three it was applied with; world_0044 carries every recipe
        self.assertEqual(re.findall(r"^\('(\w+)',\d+,'(?:convert|set_convert|rare_upgrade|reforge|primal_upgrade|augment|extract)','", G.render(), re.M), ["iben_pleasure", "iben_regret", "iben_wrath"])
        self.assertEqual(re.findall(r"^\('(\w+)',\d+,'(?:convert|set_convert|rare_upgrade|reforge|primal_upgrade|augment|extract)','", sql, re.M),
                         ["archive_of_tal_rasha", "law_of_kulle", "hope_of_cain", "skill_of_nilfur", "iben_pleasure", "iben_regret", "iben_wrath", "caldesanns_despair", "curiosity_of_lorath_nahr"])

    def test_the_pages_run_in_alexs_order_with_five_and_six_left_for_cathan_and_radament(self):
        # decisions.md 2026-10-15: the Cube's page order; 5 Work of Cathan and 6 Darkness of Radament are not built yet
        self.assertEqual([(rid, sort) for rid, sort, *_ in G.recipes()],
                         [("archive_of_tal_rasha", 1), ("law_of_kulle", 2), ("hope_of_cain", 3), ("skill_of_nilfur", 4), ("iben_pleasure", 7),
                          ("iben_regret", 8), ("iben_wrath", 9), ("caldesanns_despair", 10), ("curiosity_of_lorath_nahr", 11)])

    def test_the_two_rows_are_d3s_costs_and_make_no_material(self):
        recipes = {rid: (rule, name, lines) for rid, _, rule, name, lines in G.recipes()}
        costs = {r["recipe_name"].split(": ")[-1]: r for r in read_csv(G.DATA / "cube_costs.csv")}
        for rid, rule, name in (("skill_of_nilfur", "set_convert", "Skill of Nilfur"), ("hope_of_cain", "rare_upgrade", "Hope of Cain"),
                                ("law_of_kulle", "reforge", "Law of Kulle")):
            got_rule, got_name, lines = recipes[rid]
            self.assertEqual((got_rule, got_name), (rule, name))
            self.assertEqual({e: a for _, k, _, e, a in lines if k == "spend"},
                             {e: int(costs[name][c]) for e, c in COLUMN.items() if int(costs[name][c])}, rid)
            self.assertFalse([line for line in lines if line[1] != "spend"], rid)
            # nothing of the cost is outside the ledger: no reagent, gold or Ashes column is set for either
            self.assertEqual(sum(int(v) for k, v in costs[name].items() if k not in COLUMN.values()
                                 and k not in ("recipe_name", "other_inputs", "notes", "source_url")), 0)
        self.assertIn("never rolls Ancient", costs["Skill of Nilfur"]["notes"])
        # Law of Kulle's five reagents are the bounty caches' ledger materials (W3), by name
        ledger = {int(r["item_entry"]): r["name"] for r in read_csv(G.DATA / "account_economy.csv") if r["kind"] == "material"}
        self.assertEqual([ledger[e] for e in range(102008, 102013)], ["Khanduran Rune", "Caldeum Nightshade", "Arreat War Tapestry",
                                                                      "Corrupted Angel Flesh", "Westmarch Holy Water"])
        self.assertIn("Smart Loot always active", costs["Law of Kulle"]["notes"])
        self.assertIn("at least 3 items", costs["Skill of Nilfur"]["other_inputs"])

    def test_the_set_floor_is_a_tunable_with_d3s_three(self):
        rows = {r["name"]: r for r in read_csv(G.MODULE / "data/tunables/crafting.csv")}
        self.assertEqual((rows["cube_set_min_pieces"]["d3_value"], rows["cube_set_min_pieces"]["value"]), ("3", ""))
        self.assertIn("('crafting', 'cube_set_min_pieces', 3.0, NULL", (UPDATES / "tunables_0012.sql").read_text(encoding="utf-8"))
        self.assertIn('Tunables::Get("crafting", "cube_set_min_pieces")', CRAFTING)

    def test_every_rare_type_has_a_legendary_and_the_floor_stops_d3s_two_piece_sets(self):
        rows = read_csv(G.MODULE / "data/d3/base_items.csv")
        pool = [r for r in rows if r["rarity"] in ("legendary", "set") and r["pool_version"] == "yes" and r["craft_only"] != "yes"]
        generic = {r["type"] for r in rows if r["rarity"] == ""}
        # 44 are D3's; the Shaman's Ritual Mace and Totem (source torment_shaman, diablocraft-xnrvn.3) are the two beyond them.
        self.assertEqual(len(generic), 44 + 2)
        self.assertEqual({r["type"] for r in rows if r["rarity"] == "" and r["source_file"] == "torment_shaman"},
                         {"Ritual Mace", "Totem"})
        # The Totem has no legendary yet (the Shaman's legendaries are step 3 of her build, paused): the one type without.
        self.assertEqual(sorted(t for t in generic if not any(p["type"] == t for p in pool)), ["Totem"])
        sizes = {}
        for r in pool:
            if r["rarity"] == "set":
                sizes[r["set_name"]] = sizes.get(r["set_name"], 0) + 1
        small = sorted(s for s, n in sizes.items() if n < 3)
        self.assertEqual(len(small), 12)
        self.assertIn("Legacy of Nightmares", small)    # D3's two rings, which Nilfur does not take
        self.assertTrue(all(n == 2 for s, n in sizes.items() if s in small))

    def test_refusals(self):
        broken = __import__("test_cube").Generator("test_refusals").broken
        nilfur = lambda r: [x for x in r if x["recipe_id"] == "skill_of_nilfur"]
        self.assertIn("makes no material", broken("cube_rules.csv", lambda r: nilfur(r)[1].update(kind="make", rarity="set")))
        self.assertIn("spends or takes something", broken("cube_rules.csv", lambda r: [x.update(kind="make", rarity=rarity)
                                                                             for x, rarity in zip(nilfur(r), ("set", "rare"))]))
        self.assertIn("rule", broken("cube_rules.csv", lambda r: [x.update(rule="unknown_rule") for x in nilfur(r)]))

    def test_world_0042_and_0044_keep_the_bytes_dev_applied_and_a_run_leaves_them(self):
        manifest = am.load_manifest(G.MODULE)
        for name, render in ((G.NAME, G.render()), (G.RECIPES, G.render_recipes())):
            with self.subTest(name=name):
                path = UPDATES / name
                self.assertEqual(am.sha1(path.read_bytes()), manifest["db-world/updates/" + name])
                self.assertEqual((G.MODULE / "data/generated" / name).read_bytes(), path.read_bytes())
                # the sheet moved on, so the render differs and the guard keeps the file
                self.assertEqual(am.migration_state(G.MODULE, path, render), am.MIGRATION_FROZEN)
                self.assertFalse(am.write_migration(G.MODULE, path, render))

    def test_a_new_recipe_migration_must_be_one_the_updater_reads(self):
        for wrong in (G.MODULE / "data/generated/world_0099_cube.sql", UPDATES / "world_0099_cube.txt"):
            with self.subTest(path=wrong.name):
                with self.assertRaises(am.CompanionMigrationError):
                    G.generate(wrong)
                self.assertFalse(wrong.exists())


class Rules(unittest.TestCase):
    def test_each_recipe_takes_its_rarity(self):
        cube(self, r'''
    using namespace DC::Crafting::Cube;
    Recipe const& nilfur = *Find(generated, "skill_of_nilfur");
    assert(Takes(nilfur, "set") && !Takes(nilfur, "legendary") && !Takes(nilfur, "rare"));
    assert(Takes(*Find(generated, "hope_of_cain"), "rare") && !Takes(*Find(generated, "hope_of_cain"), "set"));
    assert(!Takes(*Find(generated, "iben_wrath"), "rare") && !Consumes(*Find(generated, "iben_wrath")));
    assert(Consumes(nilfur) && Consumes(*Find(generated, "law_of_kulle")));''',
             'recipe.rule == "set_convert" ? rarity == "set"', 'recipe.rule == "set_convert" ? rarity == "legendary"')
        cube(self, r'''
    assert(DC::Crafting::Cube::Takes(*DC::Crafting::Cube::Find(generated, "hope_of_cain"), "rare"));''',
             ': recipe.rule == "rare_upgrade" ? rarity == "rare"', ': recipe.rule == "rare_upgrade" ? rarity == "magic"')
        kulle = r'''
    using namespace DC::Crafting::Cube;
    Recipe const& kulle = *Find(generated, "law_of_kulle");
    assert(Takes(kulle, "legendary") && Takes(kulle, "set") && !Takes(kulle, "rare") && !Takes(kulle, "magic"));'''
        cube(self, kulle, 'recipe.rule == "reforge" ? rarity == "legendary" || rarity == "set"',
             'recipe.rule == "reforge" ? rarity == "legendary"')
        cube(self, kulle, 'recipe.rule == "reforge" ? rarity == "legendary" || rarity == "set"',
             'recipe.rule == "reforge" ? rarity != "rare"')
        cube(self, r'''
    assert(!DC::Crafting::Cube::Consumes(*DC::Crafting::Cube::Find(generated, "iben_wrath")));''',
             'return recipe.rule != "convert" && recipe.rule != "augment";', "return true;")

    def test_nilfur_picks_another_piece_of_a_set_big_enough(self):
        body = r'''
    using DC::Crafting::Cube::OtherPieces;
    std::vector<std::uint32_t> set{11, 12, 13, 14};
    assert((OtherPieces(set, 12, 3) == std::vector<std::uint32_t>{11, 13, 14}));     // never the piece you put in
    assert((OtherPieces({11, 12, 13}, 13, 3) == std::vector<std::uint32_t>{11, 12})); // exactly the floor is enough
    assert(OtherPieces({11, 12}, 11, 3).empty());                                   // a 2-piece set is not taken
    assert((OtherPieces(set, 99, 3) == set));                                         // an older version of a piece: all of today's'''
        cube(self, body, "if (pieces.size() < least)", "if (pieces.size() < least - 1)")
        cube(self, body, "if (piece != own)", "if (true)")


class Handler(unittest.TestCase):
    def test_the_list_shows_the_two_with_their_costs_and_no_outputs(self):
        cube(self, r'''
    Rig rig; rig.game.funds.materials[102004] = "10"; rig.game.funds.materials[102000] = "25"; rig.cube("list");
    assert(rig.sent.front() == "DCCUBE\tR|list|9" && rig.sent.back() == "DCCUBE\tE|list");
    assert(rig.has("C|law_of_kulle|reforge|Law of Kulle") && rig.has("T|law_of_kulle|102004|50|10|0") && rig.has("T|law_of_kulle|102012|5|0|0"));
    assert(rig.at("C|skill_of_nilfur|set_convert|Skill of Nilfur") < rig.at("C|iben_wrath|convert|Wrath of Iben Fahd"));
    assert(rig.has("T|skill_of_nilfur|102004|10|10|1") && rig.has("T|skill_of_nilfur|102000|10|25|1"));
    assert(rig.has("C|hope_of_cain|rare_upgrade|Hope of Cain") && rig.has("T|hope_of_cain|102000|25|25|1"));
    assert(rig.has("T|hope_of_cain|102001|50|150|1") && rig.has("T|hope_of_cain|102003|50|99|1"));
    for (auto const& s : rig.sent) assert(s.rfind("DCCUBE\tY|skill", 0) != 0 && s.rfind("DCCUBE\tY|hope", 0) != 0);
    assert(rig.sent.size() == 1 + 3 * 6 + 3 + 5 + 7 + 2 + 3 + 7 + 1);''')

    def test_a_transmute_that_consumes_the_item_reports_it_removed_and_the_new_one(self):
        cube(self, r'''
    Rig rig;
    rig.game.effect = [&] { rig.game.bags.erase(42); rig.game.bags[43] = Held{30002, 1, 255, 23}; rig.game.funds.materials[102004] = "0"; };
    rig.cube("transmute\t42\t102004_10\t102000_10");
    assert(rig.game.calls == std::vector<std::string>{"skill_of_nilfur 42"});
    assert(rig.sent.front() == "DCCUBE\tR|transmute|1" && rig.sent.back() == "DCCUBE\tE|transmute");
    assert(rig.at("C|skill_of_nilfur|set_convert|Skill of Nilfur") > 0 && !rig.has("C|hope_of_cain|rare_upgrade|Hope of Cain"));''')


class Wiring(unittest.TestCase):
    BODY = CRAFTING[CRAFTING.index("        void TransmuteItem("):CRAFTING.index("        void Transmute(Player* player")]

    def test_the_transmute_sends_an_item_recipe_to_its_own_path(self):
        self.assertIn('if (recipe->rule != "convert")\n                return TransmuteItem(player, *recipe, guid);', CRAFTING)
        self.assertIn('Need(recipe && (recipe->rule == "convert" || recipe->rule == "augment" || Cube::Consumes(*recipe)), "Choose a recipe.");', CRAFTING)
        self.assertIn('Need(Cube::Takes(recipe, instance.rarity), "The Cube takes no item of that rarity for this recipe.");', self.BODY)

    def test_every_check_comes_before_anything_is_spent_and_the_item_goes_before_the_new_one_is_staged(self):
        body = self.BODY
        order = ["auto* item = Owned(player, guid);", "Rolled(item)", "Cube::Takes(recipe, instance.rarity)",
                 "SalvageEligible(item->IsEquipped(), item->IsInTrade())", "CheckMaterials(player, spend);",
                 "CheckRoom(player, room);", "SpendMaterials(player, spend);", "Grant(player, gems);",
                 "GrantGem(player, gem, tx);", "Items::DestroyWithRows(player, item, tx);",
                 "Items::StageRoll(player, pick, player->GetLevel(), \"\", tx, rollClass, quality);", "Save(player, tx);",
                 "staged->Publish();"]
        at = [body.index(step) for step in order]
        self.assertEqual(at, sorted(at))

    def test_nilfur_rolls_another_drop_pool_piece_of_the_set_at_normal_quality(self):
        body = self.BODY
        self.assertIn('Need(!instance.crafted && craftOnly != "yes", "The Cube takes no crafted item for this recipe.");', body)
        self.assertIn("RollClass::InDropPool(", body)
        self.assertIn("Cube::OtherPieces(pieces, instance.baseItem, least)", body)
        self.assertIn("rollClass = SlotVendor::RollClassFor(designation[pick], setClass, playerClass);", body)
        self.assertIn('quality = "normal";', body)

    def test_hope_picks_through_the_drops_own_pool_by_the_rares_item_type(self):
        body = self.BODY
        self.assertIn('rollClass = SlotVendor::RollClassFor(designated, "", playerClass);', body)
        self.assertIn("Kadala::SlotFilter const filter{slot, {type}};", body)
        self.assertIn("pick = Loot::PickBaseItem(Loot::Rarity::Legendary, player->GetLevel(), rollClass, 0, &filter);", body)

    def test_kulle_rolls_the_same_item_again_as_a_drop_for_your_class(self):
        body = self.BODY
        kulle = body[body.index('if (recipe.rule == "reforge")'):body.index('else if (recipe.rule == "primal_upgrade")')]
        self.assertIn('Need(!instance.crafted && craftOnly != "yes", "The Cube takes no crafted item for this recipe.");', kulle)
        self.assertIn("pick = instance.baseItem;", kulle)
        # D3: Smart Loot always (never another class's primary stat): the player's class, a class-only item's own
        self.assertIn('rollClass = SlotVendor::RollClassFor(designated, "", playerClass);', kulle)
        self.assertNotIn("quality =", kulle)   # "": decided as a drop (Ancient and Primal at the normal rates)
        loot = (G.MODULE / "src/loot/dc_loot.cpp").read_text(encoding="utf-8")
        self.assertIn("std::vector<BaseItem> const& pool = rarity == Rarity::Legendary ? uniques : generics;", loot)
        self.assertIn("if (filter && !filter->Admits(item.slot, item.type))", loot)


class Replay(unittest.TestCase):
    def test_world_0044_and_0053_after_world_0042_twice(self):
        from test_account_economy_sql import MYSQL, isolated
        stub = table("gameobject_template") + "\n" + table("gameobject") + "\n"

        def body(port):
            command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
                       "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

            def mysql(text, database=None):
                done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                                      capture_output=True, encoding="utf-8")
                return done.returncode, done.stdout.rstrip("\n"), done.stderr

            mysql("CREATE DATABASE cube_items CHARACTER SET utf8mb4;")
            code, _out, err = mysql(stub, "cube_items")
            self.assertEqual(code, 0, err)
            for path in (UPDATES / G.NAME, APPLIED, RECIPES, UPDATES / G.NAME, APPLIED, RECIPES, RECIPES):
                code, _out, err = mysql(path.read_text(encoding="utf-8"), "cube_items")
                self.assertEqual(code, 0, f"{path.name}: {err}")
            self.assertEqual(mysql("SELECT GROUP_CONCAT(recipe_id ORDER BY sort) FROM dc_cube_recipe", "cube_items")[1],
                             "archive_of_tal_rasha,law_of_kulle,hope_of_cain,skill_of_nilfur,iben_pleasure,iben_regret,iben_wrath,caldesanns_despair,curiosity_of_lorath_nahr")
            self.assertEqual(mysql("SELECT COUNT(*) FROM dc_cube_rule WHERE recipe_id IN ('skill_of_nilfur','hope_of_cain','law_of_kulle')",
                                   "cube_items")[1], "12")

        isolated(body)


if __name__ == "__main__":
    unittest.main()
