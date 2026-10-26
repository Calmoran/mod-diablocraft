"""diablocraft-wpt7l.4: Kanai's Cube, the object and the window shell with the three Iben Fahd conversions.

1. The generator (generate_cube.py): world_0042_kanais_cube.sql is the render, but for the three
   Iben Fahd sort numbers the sheet moved after dev applied it, and its mirror. The template is the Cube's own
   clickable type 22 on the display whose model is the Magtheridon cube (read from the client's DBC here), never stock 181713's
   scripted goober. The designer's placement keeps its row, and the file sorts after world_0037, which refuses a retired guid with
   another entry. The recipe rows match D3's costs (cube_costs.csv) and the material each rarity salvages into
   (salvage_rules.csv). The refusals fire.
2. The handler (src/crafting/dc_cube_window.h, with dc_crafting_window.h and dc_cube_rule.h, compiled as they are) behind
   the real router (dc_bridge.h): the recipes fed in are the ones parsed out of the generated migration, and a fake game stands
   in for dc_crafting.cpp. Covered: the list, the gate, a transmute and its records, the refusals, and the rule's pick by
   rarity.
3. The wiring of dc_crafting.cpp, pinned as text: the route, the click, the gate, the order of a transmute. The core is not
   compiled here; the in-game behaviour is the test sheet's checks.

Every compiled test runs again on a source mutation that removes its rule, and that run must fail.
"""
import csv
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import crafting_source  # noqa: E402
import generate_cube as G
from dbc_store import Store, schema
from test_class_parity import SRC, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)
from test_crafting_window import EXTRA_INCLUDES
from test_window_bridge import PRELUDE

BRIDGE = (SRC / "common/dc_bridge.h").read_text(encoding="utf-8")
GAP = (SRC / "common/dc_request_gap.h").read_text(encoding="utf-8")
WINDOW = (SRC / "crafting/dc_crafting_window.h").read_text(encoding="utf-8")
RULE = (SRC / "crafting/dc_cube_rule.h").read_text(encoding="utf-8")
CUBE = (SRC / "crafting/dc_cube_window.h").read_text(encoding="utf-8")
CRAFTING = crafting_source.source()
UPDATES = G.MODULE / "data/sql/db-world/updates"
MIGRATION = UPDATES / G.NAME
ROOT = G.MODULE.parent
BASE = ROOT / "azerothcore-wotlk/data/sql/base/db_world"


def recipes_cpp(sql):
    """The generated recipe rows as a Cube::Recipes literal."""
    heads = re.findall(r"^\('(\w+)',(\d+),'(\w+)','((?:[^']|'')*)'\)", sql, re.M)
    lines = re.findall(r"^\('(\w+)',(\d+),'(spend|make|take)','([\w ]*)',(\d+),(\d+)\)", sql, re.M)
    assert heads and lines, "no recipe rows parsed"
    out = []
    for rid, sort, rule, name in heads:
        name = name.replace("''", "'")
        body = ",".join(f'{{{n},"{k}","{r}",{e},{a}}}' for i, n, k, r, e, a in lines if i == rid)
        out.append(f'{{"{rid}","{rule}","{name}",{sort},{{{body}}}}}')
    return "DC::Crafting::Cube::Recipes generated = {" + ",".join(out) + "};\n"


RIG = r'''
using namespace DC::Crafting::Window;
using DC::Bridge::Outcome;
struct Guid { std::uint64_t id; std::uint64_t GetRawValue() const { return id; } };
struct Player { Guid guid; Guid GetGUID() const { return guid; } };
struct Fake {
    std::string gate;                       // non-empty: the gate refuses with this text
    std::vector<std::string> calls, gates;
    int failed = 0, recipesRead = 0;
    Bags bags{{42, Held{30001, 1, 255, 23}}};
    Funds funds{true, "1000", {{102000, "1"}, {102001, "150"}, {102002, "100"}, {102003, "99"}}};
    std::function<void()> effect;
    std::vector<CubeSlot> slots;                 // the Cube's power slots: a test that wants them fills this
    std::vector<CubePower> powers;               // what Powers() answers for any slot
    std::map<std::uint32_t, CubePowerText> texts;
    std::string chooseFails;
    std::vector<std::string> chose;
    int powersRead = 0;
    void Gate(Npc n) { gates.push_back(std::to_string(int(n))); if (!gate.empty()) throw std::runtime_error(gate); }
    DC::Crafting::Cube::Recipes Recipes() { ++recipesRead; return generated; }
    std::map<std::uint32_t, std::string> gemClass;  // a bag item's gem class (GemClass); absent: not a gem
    std::vector<std::string> gemCells;              // the gem cells the last Transmute got, guid:count
    std::string GemClass(std::uint32_t g) { auto at = gemClass.find(g); return at == gemClass.end() ? "" : at->second; }
    void Transmute(std::string const& id, std::uint32_t g, std::vector<DC::Crafting::Cube::Cell> const& gems) {
        calls.push_back(id + " " + std::to_string(g)); gemCells.clear();
        for (auto const& c : gems) gemCells.push_back(std::to_string(c.entry) + ":" + std::to_string(c.amount));
        if (effect) effect();
    }
    std::vector<CubeSlot> Slots() { return slots; }
    std::vector<CubePower> Powers(unsigned) { ++powersRead; return powers; }
    std::optional<CubePowerText> PowerText(std::uint32_t entry) { auto at = texts.find(entry); return at == texts.end() ? std::nullopt : std::optional<CubePowerText>(at->second); }
    void Choose(unsigned slot, std::uint32_t entry) {
        chose.push_back(std::to_string(slot) + " " + std::to_string(entry));
        if (!chooseFails.empty()) throw std::runtime_error(chooseFails);
        for (auto& s : slots) if (s.slot == slot) { s.entry = entry; s.name = entry ? "Power " + std::to_string(entry) : ""; }
    }
    Bags Carried() { return bags; }
    Funds Balance() { return funds; }
    std::optional<Rolled> Detail(std::uint64_t, bool) { return std::nullopt; }
    void Failed() { ++failed; }
};
struct Rig {
    Fake game;
    Player player{{7}};
    std::vector<std::string> sent;
    DC::Bridge::Router<Player> router{[this](Player*, std::string const& prefix, std::string const& record) { sent.push_back(prefix + "\t" + record); }};
    Rig() {
        DC::Tunables::rows["crafting/cube_burst"] = 50;
        DC::Tunables::rows["crafting/cube_per_second"] = 50;
        bool ok = router.Add("DCCUBE", {"crafting", "cube_burst", "cube_per_second"},
            [this](Player&, DC::Bridge::Request const& r, DC::Bridge::Wire<Player> const& w) { CubeRequest(game, r, w); });
        assert(ok);
    }
    Outcome cube(std::string const& payload) { sent.clear(); return router.Dispatch(&player, "DCCUBE\t" + payload, 1000); }
    bool has(std::string const& record) const { for (auto const& s : sent) if (s == "DCCUBE\t" + record) return true; return false; }
    int at(std::string const& record) const { for (std::size_t i = 0; i < sent.size(); ++i) if (sent[i] == "DCCUBE\t" + record) return int(i); return -1; }
    std::string refusal() const { return sent.size() == 1 && sent[0].rfind("DCCUBE\tX|", 0) == 0 ? sent[0].substr(9) : ""; }
};
std::string const CUBE = std::to_string(int(Npc::Cube));
'''


def strip(text, *includes):
    for include in includes:
        text = text.replace(f'#include "{include}"', "")
    return text


def compile_cube(body, window=WINDOW, rule=RULE, cube=CUBE, sql=None):
    code = (EXTRA_INCLUDES + "#include <cstdlib>\n" + PRELUDE
            + GAP.replace("#ifndef DC_REQUEST_GAP_H", "#ifndef DC_REQUEST_GAP_H_T") + "\n"
            + strip(BRIDGE, "dc_request_gap.h", "dc_tunables.h") + "\n" + strip(window, "dc_bridge.h") + "\n" + rule + "\n"
            + strip(cube, "dc_crafting_window.h", "dc_cube_rule.h") + "\n"
            + recipes_cpp(sql or MIGRATION.read_text(encoding="utf-8")) + RIG + "int main() {\n" + body + "\n    return 0;\n}\n")
    return run(code.replace("#define DC_REQUEST_GAP_H\n", "#define DC_REQUEST_GAP_H_T\n"))


def both(test, body, old, new, where="cube"):
    ok, out = compile_cube(body)
    test.assertTrue(ok, out)
    sources = {"cube": CUBE, "rule": RULE}
    ok, out = compile_cube(body, **{where: mutate(sources[where], old, new)})
    test.assertFalse(ok, "mutation survived: " + new)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


class Generator(unittest.TestCase):
    def test_the_migration_is_the_render_but_for_the_later_page_order_and_its_mirror(self):
        # world_0042 is applied on dev and frozen; the sheet has since moved the three Iben Fahd pages (world_0053 carries that)
        def unsorted(text):
            return re.sub(r"^\('(iben_\w+)',\d+,'convert',", r"('\1',N,'convert',", text, flags=re.M)
        applied = MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(unsorted(applied), unsorted(G.render()))
        self.assertEqual(re.findall(r"^\('iben_\w+',(\d+),'convert',", applied, re.M), ["1", "2", "3"])
        self.assertEqual((G.MODULE / "data/generated" / G.NAME).read_text(encoding="utf-8"), applied)

    def test_the_template_is_the_cubes_own_clickable_object_on_the_magtheridon_cube_model(self):
        sql = G.render()
        row = re.search(r"^\((\d+),(\d+),(\d+),'((?:[^']|'')*)','([^']*)','','',([\d.]+),([\d,]+),'','',12340\);$", sql, re.M)
        entry, kind, display, name, icon, size, data = row.groups()
        self.assertEqual((entry, kind, display, name, icon, size), ("910047", "22", "6896", "Kanai''s Cube", "", "1.5"))
        self.assertEqual([int(v) for v in data.split(",")], [0, 0, 0, 1] + [0] * 20)   # no spell; never dismounts
        # Cross-source: the display is the Magtheridon cube model in the DBC the client patch ships (the designer's "192766,
        # magtheradoncube", a model file id), and stock 181713 is the scripted goober the Cube must not be.
        dbc = Store((ROOT / "client-patch/dbc/GameObjectDisplayInfo.dbc").read_bytes(), schema(ROOT, "gameobjectdisplayinfo_dbc"))
        self.assertTrue(dbc.decode(6896)["ModelName"].lower().endswith("activedoodads\\cube\\magtheradoncube.mdx"))
        stock = re.search(r"^\(181713,(\d+),6896,'Manticron Cube'.*'(go_manticron_cube)'", (BASE / "gameobject_template.sql").read_text(
            encoding="utf-8"), re.M)
        self.assertEqual(stock.group(1), "10")
        # 910047 is no other object's: not stock, not in another sheet or migration.
        self.assertIsNone(re.search(r"^\(910047,", (BASE / "gameobject_template.sql").read_text(encoding="utf-8"), re.M))
        users = [p.name for p in UPDATES.glob("*.sql") if re.search(r"\b910047\b", p.read_text(encoding="utf-8"))]
        self.assertEqual(users, [G.NAME])

    def test_alexs_placement_keeps_its_row_and_comes_after_world_0037(self):
        sql = G.render()
        self.assertIn("UPDATE `gameobject` SET `id` = 910047 WHERE `guid` = 8001659 AND `id` = 181713;", sql)
        self.assertRegex(sql, r"SELECT 8001659,910047,750,4273,4273,1,1,1934.48,-18.26,328.14,0,0,0,0,1,300,0,1,'',NULL,NULL "
                              r"FROM DUAL WHERE NOT EXISTS \(SELECT 1 FROM `gameobject` WHERE `guid` = 8001659\);")
        self.assertIn("INSERT INTO dc_cube_guard VALUES ((EXISTS(SELECT 1 FROM `gameobject` WHERE `guid` = 8001659 AND `id` = 910047)));", sql)
        # world_0037 refuses to run while a retired copy guid holds another entry, and 8001659 is one of them.
        retired = read_csv(G.DATA / "world_sanctum_retired_copies.csv")
        self.assertTrue(any("8001659" in row.values() for row in retired))
        names = sorted(p.name for p in UPDATES.glob("*.sql"))
        self.assertGreater(names.index(G.NAME), names.index("world_0037_sanctum_one_copy.sql"))

    def test_the_iben_fahd_rows_are_d3s_costs_and_the_salvage_materials(self):
        recipes = {rid: (rule, name, lines) for rid, _, rule, name, lines in G.recipes() if rule == "convert"}
        self.assertEqual(list(recipes), ["iben_pleasure", "iben_regret", "iben_wrath"])   # the item recipes: test_cube_items
        costs = {r["recipe_name"].split(": ")[-1]: r for r in read_csv(G.DATA / "cube_costs.csv")}
        column = {102000: "deaths_breath", 102001: "reusable_parts", 102002: "arcane_dust", 102003: "veiled_crystals"}
        salvage = {r["rarity_id"]: int(r["material_entry"]) for r in read_csv(G.DATA / "salvage_rules.csv") if r["crafted"] == "0" and r["quality_id"] == "normal"}
        for rid, (rule, name, lines) in recipes.items():
            self.assertEqual(rule, "convert")
            spends = {e: a for _, k, _, e, a in lines if k == "spend"}
            self.assertEqual(spends, {e: int(costs[name][c]) for e, c in column.items() if int(costs[name][c])}, rid)
            makes = {r: (e, a) for _, k, r, e, a in lines if k == "make"}
            # "100 of the material matching the controlling item's rarity" (cube_recipes.csv): what that rarity salvages into
            self.assertEqual(makes, {r: (salvage[r], 100) for r in ("normal", "magic", "rare")}, rid)

    def broken(self, sheet, edit):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(folder.startswith(tempfile.gettempdir()))
            for name in ("cube_rules.csv", "cube_object.csv", "account_economy.csv", "world_objects.csv", "gems.csv"):
                shutil.copy(G.DATA / name, folder)
            path = Path(folder) / sheet
            rows = read_csv(path)
            edit(rows)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(G.CubeError) as caught:
                G.render(folder)
            return str(caught.exception)

    def test_refusals(self):
        rules = "cube_rules.csv"
        self.assertIn("recipe id", self.broken(rules, lambda r: [x.update(recipe_id="iben-wrath") for x in r[10:]]))
        self.assertIn("name", self.broken(rules, lambda r: [x.update(name="a|b") for x in r[10:]]))
        self.assertIn("rule", self.broken(rules, lambda r: [x.update(rule="reforge") for x in r[10:]]))
        self.assertIn("repeats its sort", self.broken(rules, lambda r: r[11].update(name="Other")))
        self.assertIn("rarity", self.broken(rules, lambda r: r[2].update(rarity="")))
        self.assertIn("rarity", self.broken(rules, lambda r: r[0].update(rarity="rare")))
        self.assertIn("kind", self.broken(rules, lambda r: r[0].update(kind="burn")))
        self.assertIn("ledger", self.broken(rules, lambda r: r[0].update(item_entry="30001")))
        self.assertIn("below 1", self.broken(rules, lambda r: r[0].update(amount="0")))
        self.assertIn("share a number", self.broken(rules, lambda r: r[1].update(line="1")))
        self.assertIn("one make line a rarity", self.broken(rules, lambda r: r[3].update(rarity="normal")))
        self.assertIn("makes something", self.broken(rules, lambda r: [x.update(kind="spend", rarity="", item_entry="10200" + str(i))
                                                                         for i, x in enumerate(r[:5])]))
        self.assertIn("share a sort", self.broken(rules, lambda r: [x.update(sort="1") for x in r[5:10]]))
        thing = "cube_object.csv"
        self.assertIn("taken", self.broken(thing, lambda r: r[0].update(entry="910090")))
        self.assertIn("taken", self.broken(thing, lambda r: r[0].update(entry="181713")))
        self.assertIn("size", self.broken(thing, lambda r: r[0].update(size="0")))
        self.assertIn("not a number", self.broken(thing, lambda r: r[0].update(x="here")))


class Handler(unittest.TestCase):
    def test_list_sends_each_recipe_its_costs_with_the_ledger_and_its_outputs(self):
        both(self, r'''
    Rig rig; rig.cube("list");
    assert(rig.game.gates == std::vector<std::string>{CUBE} && rig.game.calls.empty());
    assert(rig.sent.front() == "DCCUBE\tR|list|3" && rig.sent.back() == "DCCUBE\tE|list");
    assert(rig.at("C|iben_pleasure|convert|Pleasure of Iben Fahd") == 1 && rig.at("C|iben_regret|convert|Regret of Iben Fahd") == 7);
    assert(rig.has("T|iben_pleasure|102001|100|150|1") && rig.has("T|iben_pleasure|102000|1|1|1"));
    assert(rig.has("T|iben_regret|102002|100|100|1"));            // exactly enough is enough
    assert(rig.has("T|iben_wrath|102003|100|99|0"));              // one short is not
    assert(rig.has("Y|iben_wrath|normal|102001|100") && rig.has("Y|iben_wrath|magic|102002|100") && rig.has("Y|iben_wrath|rare|102003|100"));
    assert(rig.sent.size() == 1 + 3 * 6 + 1);''',
             "bool ok = std::strtoull(have.c_str(), nullptr, 10) >= line.amount;",
             "bool ok = std::strtoull(have.c_str(), nullptr, 10) > line.amount;")

    def test_a_ledger_that_cannot_be_read_shows_nothing_held(self):
        both(self, r'''
    Rig rig; rig.game.funds = Funds{}; rig.cube("list");
    assert(rig.has("T|iben_pleasure|102001|100|0|0") && rig.has("T|iben_pleasure|102000|1|0|0"));''',
             'return found == funds.materials.end() ? "0" : found->second;',
             'return found == funds.materials.end() ? "100" : found->second;')

    def test_the_gate_comes_first_and_refuses_alone(self):
        both(self, r'''
    Rig rig; rig.game.gate = "Stand next to Kanai's Cube."; rig.cube("list");
    assert(rig.refusal() == "Stand next to Kanai's Cube." && rig.game.recipesRead == 0);
    rig.cube("transmute\t42\t102003_100\t102000_1");
    assert(rig.refusal() == "Stand next to Kanai's Cube." && rig.game.calls.empty());''',
             "                game.Gate(Npc::Cube);\n                recipes = game.Recipes();\n                slots = game.Slots();",
             "                recipes = game.Recipes();\n                slots = game.Slots();")
        both(self, r'''
    Rig rig; rig.game.gate = "no"; rig.cube("transmute\t42\t102003_100\t102000_1");
    assert(rig.game.gates == std::vector<std::string>{CUBE} && rig.game.calls.empty());''',
             '"transmute", Npc::Cube, 0, false,', '"transmute", Npc::Nobody, 0, false,')

    def test_a_transmute_runs_the_recipe_reports_the_ledger_and_sends_the_recipe_again(self):
        both(self, r'''
    Rig rig;
    rig.game.effect = [&] { rig.game.funds.materials[102003] = "0"; rig.game.funds.materials[102000] = "0"; rig.game.funds.materials[102002] = "200"; };
    rig.game.funds.materials[102003] = "100";
    rig.cube("transmute\t42\t102003_100\t102000_1");
    assert(rig.game.calls == std::vector<std::string>{"iben_wrath 42"});
    assert(rig.sent.front() == "DCCUBE\tR|transmute|0" && rig.sent.back() == "DCCUBE\tE|transmute");
    assert(rig.has("M|102000:0|102002:200|102003:0"));
    int c = rig.at("C|iben_wrath|convert|Wrath of Iben Fahd");
    assert(c > rig.at("M|102000:0|102002:200|102003:0") && rig.has("T|iben_wrath|102003|100|0|0") && rig.has("Y|iben_wrath|rare|102003|100"));
    assert(!rig.has("C|iben_pleasure|convert|Pleasure of Iben Fahd"));        // the one recipe, not the list''',
             "                        SendRecipe(wire, *recipe, game.Balance());", "                        (void)recipe;")

    def test_a_refused_transmute_says_why_and_rolls_back(self):
        both(self, r'''
    Rig rig; rig.game.effect = [] { throw std::runtime_error("Not enough Veiled Crystal: you have 99 of 100."); };
    rig.cube("transmute\t42\t102003_100\t102000_1");
    assert(rig.refusal() == "Not enough Veiled Crystal: you have 99 of 100." && rig.game.failed == 1);''',
             "                    game.Transmute(chosen, guid, gems);", "                    try { game.Transmute(chosen, guid, gems); } catch (...) {}")

    def test_malformed_requests_never_reach_the_game(self):
        both(self, r'''
    Rig rig;
    for (char const* p : {"transmute\t42", "transmute\tx\t102003_100", "transmute\t42\t102003-100", "transmute\t42\t0_5",
                          "transmute\t42\t102003_0", "transmute\t42\t102003_", "transmute\t42\t_5", "transmute\t42\t102003",
                          "transmute\t42\t4294967296_1", "transmute\t42\t102003_4294967296", "transmute\t42\t1020_03_1",
                          "transmute\t42\t1_1\t2_1\t3_1\t4_1\t5_1\t6_1\t7_1\t8_1\t9_1", "transmute\t-1\t102003_100",
                          "transmute\t42\t102003_100\t", "list\t1", "fill", "fill\ta\tb", "fill\tiben-wrath",
                          "fill\taaaaaaaaaaaaaaaaaaaaaaaaa", "powers\t1", "powers\t0\t1", "powers\t1\t0", "powers\t1\t1\t1",
                          "power", "power\t0", "power\t1\t2", "choose\t1", "choose\t0\t5", "choose\t1\t-1", "choose\t1\t2\t3"}) {
        rig.cube(p); assert(rig.refusal() == "That request was not understood." && rig.game.calls.empty() && rig.game.chose.empty());
    }
    rig.cube("reforge"); assert(rig.refusal() == "Unknown Cube action.");''',
             "            Exactly(request, 2 + CubeReagentCells, 3);", "            Exactly(request, 3 + CubeReagentCells, 3);")

    def test_the_rule_picks_the_output_by_the_controlling_items_rarity(self):
        both(self, r'''
    using namespace DC::Crafting::Cube;
    Recipe const* wrath = Find(generated, "iben_wrath");
    assert(wrath && wrath->name == "Wrath of Iben Fahd" && !Find(generated, "iben"));
    assert(Makes(*wrath, "normal")->entry == 102001 && Makes(*wrath, "magic")->entry == 102002 && Makes(*wrath, "rare")->entry == 102003);
    assert(!Makes(*wrath, "legendary") && !Makes(*wrath, "set") && !Makes(*wrath, ""));''',
             'if (line.kind == "make" && line.rarity == rarity)', "if (line.rarity == rarity)", where="rule")
        both(self, r'''
    assert(DC::Crafting::Cube::Find(generated, "iben_regret")->id == "iben_regret");''',
             "            if (recipe.id == id)\n", "", where="rule")


class Wiring(unittest.TestCase):
    def test_the_route_and_its_budget(self):
        self.assertIn('"DCCUBE", {"crafting", "cube_burst", "cube_per_second"}', CRAFTING)
        self.assertIn("Window::CubeRequest(game, request, wire);", CRAFTING)
        tunables = {r["name"]: r["value"] for r in read_csv(G.MODULE / "data/tunables/crafting.csv")}
        self.assertEqual((tunables["cube_burst"], tunables["cube_per_second"]), ("10", "5"))   # q-0930-49's window values
        self.assertIn("('crafting', 'cube_burst', NULL, 10.0", (UPDATES / "tunables_0012.sql").read_text(encoding="utf-8"))

    def test_the_click_opens_the_window_for_the_cube_alone(self):
        self.assertIn("constexpr uint32 KanaisCube = 910047;", CRAFTING)
        self.assertEqual(read_csv(G.DATA / "cube_object.csv")[0]["entry"], "910047")
        self.assertIn("if (!player || !go || go->GetEntry() != KanaisCube)\n                    return false;", CRAFTING)
        self.assertIn('Window::SendCube(game, wire, "open");', CRAFTING)
        self.assertIn('return Bridge::Push(player, "DCCUBE", fields);', CRAFTING)
        self.assertIn("new KanaisCubeObject();", CRAFTING)

    def test_the_gate_is_the_cores_click_reach(self):
        self.assertIn("else if (npc == Window::Npc::Cube)\n                    CubeInReach(player_);", CRAFTING)
        self.assertIn("player->GetGameObjectIfCanInteractWith(cube->GetGUID(), GAMEOBJECT_TYPE_SPELLCASTER)", CRAFTING)
        shared = (ROOT / "azerothcore-wotlk/src/server/shared/SharedDefines.h").read_text(encoding="utf-8")
        self.assertRegex(shared, r"GAMEOBJECT_TYPE_SPELLCASTER\s*=\s*22,")   # the template's type (generate_cube.py SPELLCASTER)
        self.assertEqual(G.SPELLCASTER, 22)

    def test_a_transmute_checks_everything_before_it_spends(self):
        body = CRAFTING[CRAFTING.index("        void Transmute(Player* player"):CRAFTING.index("        // A deleted character takes its Cube slots")]
        order = ["CubeInReach(player);", "Cube::Find(recipes, id)", "Rolled(Owned(player, guid))", "Cube::Makes(*recipe, instance.rarity)",
                 "CheckMaterials(player, spend);", "SpendMaterials(player, spend);", "Grant(player, {{make->entry, make->amount}});",
                 "Save(player, tx);"]
        at = [body.index(step) for step in order]
        self.assertEqual(at, sorted(at))
        self.assertNotIn("Destroy", body)   # the controlling item stays


def table(name):
    """The core's own CREATE TABLE for `name`, from its base SQL."""
    text = (BASE / f"{name}.sql").read_text(encoding="utf-8")
    return re.search(rf"CREATE TABLE `{name}` \(.*?\) ENGINE=[^;]*;", text, re.S).group(0)


class Replay(unittest.TestCase):
    """world_0042 applied for real, twice each, on a disposable MySQL (test_account_economy_sql.isolated): dev's state (the designer's
    row on stock 181713 keeps its spot and turning), a fresh install (the row is made at the sheet's spot), and a guid held by
    something else (the guard stops the file). Each mutant must change one of the outcomes."""

    def test_the_migration_on_dev_on_a_fresh_install_and_on_a_taken_guid(self):
        from test_account_economy_sql import MYSQL, isolated
        sql = MIGRATION.read_text(encoding="utf-8")
        stub = table("gameobject_template") + "\n" + table("gameobject") + "\n" + (
            "INSERT INTO gameobject_template (entry,type,displayId,name,size,ScriptName) "
            "VALUES (181713,10,6896,'Manticron Cube',1.5,'go_manticron_cube');\n")
        dev = ("INSERT INTO gameobject (guid,id,map,zoneId,areaId,phaseMask,position_x,position_y,position_z,orientation,"
               "rotation2,rotation3) VALUES (8001659,181713,750,4273,4273,1,1934.48,-18.26,328.14,1.25,0.5857,0.8105);\n")
        taken = "INSERT INTO gameobject (guid,id,map) VALUES (8001659,999,750);\n"
        mutants = [("the dev row is kept", "UPDATE `gameobject` SET `id` = 910047 WHERE `guid` = 8001659 AND `id` = 181713;\n", ""),
                   ("a row only where none is", " WHERE NOT EXISTS (SELECT 1 FROM `gameobject` WHERE `guid` = 8001659)", ""),
                   ("the guard", "INSERT INTO dc_cube_guard VALUES", "SELECT 1 FROM dc_cube_guard WHERE 0 IN")]

        def outcomes(port, migration, tag):
            command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
                       "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

            def mysql(text, database=None):
                done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                                      capture_output=True, encoding="utf-8")
                return done.returncode, done.stdout.rstrip("\n")

            out = {}
            for case, seed in (("dev", dev), ("fresh", ""), ("taken", taken)):
                name = f"cube_{tag}_{case}"
                mysql(f"CREATE DATABASE {name} CHARACTER SET utf8mb4;")
                self.assertEqual(mysql(stub + seed, name)[0], 0)
                codes = [mysql(migration, name)[0] for _ in range(2)]
                out[case] = (codes, mysql("SELECT id, position_x, orientation, rotation3 FROM gameobject WHERE guid=8001659", name)[1],
                             mysql("SELECT type, displayId, name, size FROM gameobject_template WHERE entry=910047", name)[1],
                             mysql("SELECT COUNT(*) FROM dc_cube_recipe", name)[1] + "/" + mysql("SELECT COUNT(*) FROM dc_cube_rule", name)[1])
            return out

        def body(port):
            got = outcomes(port, sql, "real")
            self.assertEqual(got["dev"], ([0, 0], "910047\t1934.48\t1.25\t0.8105", "22\t6896\tKanai's Cube\t1.5", "3/15"))
            self.assertEqual(got["fresh"], ([0, 0], "910047\t1934.48\t0\t1", "22\t6896\tKanai's Cube\t1.5", "3/15"))
            self.assertNotEqual(got["taken"][0], [0, 0])
            self.assertEqual(got["taken"][1], "999\t0\t0\t0")
            for number, (what, old, new) in enumerate(mutants):
                self.assertEqual(sql.count(old), 1, what)
                self.assertNotEqual(outcomes(port, sql.replace(old, new), f"m{number}"), got, "mutant survived: " + what)

        isolated(body)


if __name__ == "__main__":
    unittest.main()
