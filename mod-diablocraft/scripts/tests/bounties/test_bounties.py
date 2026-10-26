"""diablocraft-dm9vg.1: bounties W1, the data, the board and its owners.

1. The generator: the committed migration is today's render; each of its refusals fires on a sheet broken for it.
2. The board (src/bounties/dc_bounty_board.h, compiled as it is) driven with the catalogue parsed out of the generated
   migration: the draw, the column states, completion, progress, the reroll gate and the wire records.
3. The owners (SaveLocked, LoadLocked, DropLocked cut out of src/bounties/dc_bounties.cpp) against an in-memory
   dc_bounties_board: a player draws, a party copies its leader's board, the two then move apart, a disband drops it.
4. The owned monster on a rift floor's copy (diablocraft-h3erm): OwnedMonsterAI, IsRiftTrash, StripNativeAbilities and
   the rift's OnCreatureAddWorld, cut out of src/monsters/dc_monster_ai.cpp, run in the core's order (Creature::AddToWorld:
   AIM_Initialize, then OnCreatureAddWorld); the claim's AI is still there afterwards.

Every compiled test runs again on a source mutation that removes the rule it checks, and that run must fail.
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_bounties as G
from test_class_parity import SRC, definition, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

RIFT_AI = (SRC / "monsters/dc_monster_ai.cpp").read_text(encoding="utf-8")
BOARD = (SRC / "bounties/dc_bounty_board.h").read_text(encoding="utf-8")
SERVER = (SRC / "bounties/dc_bounties.cpp").read_text(encoding="utf-8")
HEADER = (SRC / "bounties/dc_bounties.h").read_text(encoding="utf-8")
MIGRATION = G.MODULE / "data/sql/db-world/updates" / G.NAME
WIRE_ROOM = 255 - len("DCBOUNTY") - 1  # docs/contracts/window-bridge.md: prefix, tab and record in 255 bytes
SHEETS = ("rift_open_zones.csv", "rift_anchors.csv", "bounty_uniques.csv", "bounty_targets.csv")
# diablocraft-dm9vg.18: Moonglade became a Kill and no bounty of the sheet is a Click now; the Click code stays, unused. Its
# compiled tests run on this fixture catalogue: the real sheets with Moonglade's row put back as the Click row it was
# (diablocraft-dm9vg.16's spots), rendered by the same generator into a temp folder.
OLD_CLICK = {"type": "click", "title": "Moonglade objectives", "unique_entry": "", "unique_name": "", "anchors": "6;7;8;9;10;14",
             "spot": "", "objective_display": "2048", "objective_text": "Shrines activated",
             "quest_text": "Activate the shrines in Moonglade."}


def moon(rows):
    """Moonglade's row of bounties.csv (act 1, its second zone since diablocraft-hyoic.1)."""
    return next(row for row in rows if row["zone"] == "moonglade")


def zone_row(rows, key):
    return next(row for row in rows if row["zone"] == key)


def sheets(folder, edit):
    """Writes the generator's sheets into `folder` (a temp dir), bounties.csv changed by `edit`."""
    assert str(Path(folder)).startswith(tempfile.gettempdir())
    for name in SHEETS:
        shutil.copy(G.D3 / name, folder)
    rows = G.read("bounties.csv", G.D3)
    edit(rows)
    with (Path(folder) / "bounties.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, G.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# diablocraft-hyoic.5 (acts A2): the committed sheets grow with the acts (16 zones, 16 targets), but the compiled board tests
# drive the board's rules on the first set's five zones and five targets. The same generator renders them from the real sheets
# cut down to those rows, in a temp folder.
FIRST_SET_ZONES = ("ungoro", "tanaris", "thousandneedles", "azshara", "moonglade")
FIRST_SET_TARGETS = ("6581", "8208", "5937", "6649", "910048")


def first_set_render(edit=lambda rows: None):
    with tempfile.TemporaryDirectory() as folder:
        def keep(rows):
            rows[:] = [row for row in rows if row["zone"] in FIRST_SET_ZONES]
            edit(rows)
        sheets(folder, keep)
        for name, column, keys in (("rift_open_zones.csv", "key", FIRST_SET_ZONES), ("bounty_targets.csv", "entry", FIRST_SET_TARGETS)):
            rows = G.read(name, G.D3)
            with (Path(folder) / name).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, list(rows[0]))
                writer.writeheader()
                writer.writerows(row for row in rows if row[column] in keys)
        return G.render(folder)


def first_set_sql():
    if "sql" not in first_set_sql.__dict__:
        first_set_sql.sql = first_set_render()
    return first_set_sql.sql


def click_sql():
    return first_set_render(lambda rows: moon(rows).update(OLD_CLICK))


def catalogue_cpp(sql):
    """The generated rows as C++ literals: the catalogue (bounty rows, then their spots) and the named targets."""
    bounties = re.findall(r"^\((\d+), (\d), (\d+), '(\w+)', '(\w+)', '((?:[^']|'')*)', (\d+), (\d+), '((?:[^']|'')*)'\)", sql, re.M)
    spots = re.findall(r"^\((\d+), (\d+), (\d+), (-?[\d.]+), (-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\)", sql, re.M)
    named = re.findall(r"^\((\d+), '(?:[^']|'')*', '((?:[^']|'')*)'\)", sql, re.M)
    assert bounties and spots and named, "nothing parsed from the migration"
    out = []
    for bid, col, idx, kind, key, zname, mapid, zone, title in bounties:
        sp = ",".join(f"{{{a},{x}f,{y}f,{z}f,{o}f}}" for b, _, a, x, y, z, o in spots if b == bid)
        out.append(f'{{{bid},{col},{idx},"{kind}","{key}","{zname.replace(chr(39) * 2, chr(39))}","{title}",{mapid},{zone},{{{sp}}}}}')
    return ("std::vector<DC::Bounties::Bounty> catalog = {" + ",\n".join(out) + "};\n"
            "std::vector<DC::Bounties::Target> targets = {"
            + ",".join(f'{{{e},"{t.replace(chr(39) * 2, chr(39))}"}}' for e, t in named) + "};\n")


PRELUDE = r'''
#include <cassert>
#include <cstdio>
#include <map>
#include <memory>
#include <string>
#include <vector>
'''

HELPERS = r'''
using namespace DC::Bounties;
// A fixed sequence: lo, then lo+1, ... wrapped into [lo, hi]; the draw's shape, not its luck, is what is checked.
struct Seq { std::uint32_t n = 0; std::uint32_t operator()(std::uint32_t lo, std::uint32_t hi) { return lo + (n++ % (hi - lo + 1)); } };
unsigned Bits(std::uint32_t v) { unsigned n = 0; for (; v; v &= v - 1) ++n; return n; }
Cell const* At(Board const& b, unsigned col, unsigned cell) { for (auto const& c : b) if (c.column == col && c.cell == cell) return &c; return nullptr; }
Cell const* Of(Board const& b, std::uint32_t bounty) { for (auto const& c : b) if (c.bounty == bounty) return &c; return nullptr; }
'''


def compile_board(body, board=BOARD, sql=None):
    sql = sql or first_set_sql()
    return run(PRELUDE + board + catalogue_cpp(sql) + HELPERS + "int main() {\n" + body + "\n    return 0;\n}\n")


def both(test, body, old, new, sql=None):
    ok, out = compile_board(body, sql=sql)
    test.assertTrue(ok, out)
    ok, out = compile_board(body, mutate(BOARD, old, new), sql=sql)
    test.assertFalse(ok, "mutation survived: " + new)


class Generator(unittest.TestCase):
    def test_committed_migration_is_the_render(self):
        self.assertEqual(MIGRATION.read_text(encoding="utf-8"), G.render())
        self.assertEqual((G.MODULE / "data/generated" / G.NAME).read_text(encoding="utf-8"), G.render())

    def test_first_set_one_bounty_per_zone_all_kills(self):
        rows = G.catalogue()
        zones = [z["key"] for z in G.read("rift_open_zones.csv", G.D3)]
        self.assertEqual(sorted(r["zone"] for _, r, _, _ in rows), sorted(zones))
        # diablocraft-hyoic.1: the column is the zone's act (docs/research/bounty-acts.md 2.1)
        self.assertEqual([(bid, r["zone"], z["act"]) for bid, r, z, _ in rows],
                         [(101, "azshara", "1"), (102, "moonglade", "1"), (103, "darkshore", "1"), (104, "winterspring", "1"),
                          (105, "felwood", "1"), (106, "ashenvale", "1"), (107, "durotar", "1"), (108, "stonetalonmountains", "1"),
                          (201, "ungoro", "2"), (202, "tanaris", "2"), (203, "thousandneedles", "2"), (204, "silithus", "2"),
                          (205, "feralas", "2"), (206, "desolace", "2"), (207, "dustwallowmarsh", "2"), (208, "thebarrens", "2"),
                          # diablocraft-hyoic.8 (acts A5): act 3 and 4 on map 752
                          (301, "westernplaguelands", "3"), (302, "easternplaguelands", "3"), (303, "tirisfalglades", "3"),
                          (304, "silverpineforest", "3"), (305, "alteracmountains", "3"), (306, "hillsbradfoothills", "3"),
                          (307, "thehinterlands", "3"),
                          (401, "wetlands", "4"), (402, "lochmodan", "4"), (403, "dunmorogh", "4"), (404, "badlands", "4"),
                          (405, "burningsteppes", "4"), (406, "redridgemountains", "4"), (407, "elwynnforest", "4"),
                          (408, "swampofsorrows", "4"), (409, "westfall", "4"), (410, "stranglethornvale", "4"),
                          # diablocraft-hyoic.10 (acts A7): act 5 on map 753
                          (501, "hellfirepeninsula", "5"), (502, "zangarmarsh", "5"), (503, "nagrand", "5"),
                          (504, "terokkarforest", "5"), (505, "shadowmoonvalley", "5"), (506, "netherstorm", "5"),
                          (507, "bladesedgemountains", "5")])
        self.assertTrue(all(r["column"] == z["act"] for _, r, z, _ in rows))
        self.assertEqual({r["type"] for _, r, _, _ in rows}, {"kill"})  # diablocraft-dm9vg.18: the Click type is unused

    def test_moonglade_is_a_kill_of_a_made_unique_on_alexs_spot(self):
        """diablocraft-dm9vg.18: the designer's .gps, map 751 zone 493, 7941.7803 -2205.3403 491.38812 o 3.1145103; since diablocraft-hyoic.2
        it is Moonglade's bounty spot and Grimfeather is a target of the master list."""
        (bid, row, zone, (spot,)), = [b for b in G.catalogue() if b[1]["zone"] == "moonglade"]
        self.assertEqual((bid, row["type"], zone["map_id"], zone["zone_id"]), (102, "kill", "751", "493"))
        self.assertIn("(910048, 'Grimfeather the Moonmad', 'Kill Grimfeather the Moonmad')", G.render())
        self.assertEqual([spot[k] for k in "xyzo"], ["7941.7803", "-2205.3403", "491.38812", "3.1145103"])
        self.assertIn("(102, 1, 0, 7941.7803, -2205.3403, 491.38812, 3.1145103)", G.render())
        self.assertIn("(102, 1, 2, 'kill', 'moonglade', 'Moonglade', 751, 493, '')", G.render())
        self.assertNotIn("INSERT INTO `gameobject_template`", G.render_objectives())  # no Click bounty, no objective object

    def test_the_made_unique_is_a_copy_of_a_stock_creature_with_a_model(self):
        """Cross-source: the copied creature and its model row are in the core's own base data, so the copy has both; the
        copy gets its name, rank and level and no AI of its own, and only the made Uniques are written."""
        base = G.MODULE.parent / "azerothcore-wotlk/data/sql/base/db_world"
        sql = G.render()
        made = G.made_uniques()
        self.assertEqual(list(made), ["910048"])
        for entry, u in made.items():
            self.assertRegex((base / "creature_template.sql").read_text(encoding="utf-8"), rf"\({u['clone_of']},0,0,0,0,0,'")
            self.assertRegex((base / "creature_template_model.sql").read_text(encoding="utf-8"), rf"\({u['clone_of']},0,\d+,")
            self.assertIn(f"SELECT * FROM `creature_template` WHERE `entry` = {u['clone_of']};", sql)
            self.assertIn(f"SET `entry` = {entry}, `name` = 'Grimfeather the Moonmad', `subname` = NULL, `rank` = 4, `minlevel` = 58,\n"
                          f"  `maxlevel` = 58, `AIName` = '', `ScriptName` = '';", sql)
            self.assertIn(f"FROM `creature_template_model` WHERE `CreatureID` = {u['clone_of']};", sql)
        self.assertEqual(sql.count("CREATE TEMPORARY TABLE"), len(made))

    def test_spots_are_the_survey_anchors(self):
        survey = {(a["dungeon"], a["anchor"]): a for a in G.read("rift_anchors.csv", G.D3)}
        for _, row, zone, anchors in G.catalogue():
            if row["spot"]:
                continue  # a made Unique's own spot (test_moonglade_is_a_kill_of_a_made_unique_on_alexs_spot)
            for a in anchors:
                self.assertEqual(survey[(zone["name"], a["anchor"])], a)

    def broken(self, edit):
        """catalogue() on a copy of the three sheets with bounties.csv rows changed by `edit`."""
        with tempfile.TemporaryDirectory() as folder:
            sheets(folder, edit)
            with self.assertRaises(ValueError) as caught:
                G.catalogue(folder)
            return str(caught.exception)

    def test_refusals(self):
        ungoro = lambda r: zone_row(r, "ungoro")
        self.assertIn("not in", self.broken(lambda r: ungoro(r).update(anchors="99999")))
        self.assertIn("not a key", self.broken(lambda r: r[0].update(zone="duskwood")))
        # diablocraft-hyoic.1: one bounty a zone, in its act's column
        self.assertIn("a zone has one", self.broken(lambda r: zone_row(r, "tanaris").update(zone="ungoro", anchors="414")))
        self.assertIn("s act", self.broken(lambda r: ungoro(r).update(column="3")))
        self.assertIn("s act", self.broken(lambda r: zone_row(r, "azshara").update(column="2", index="9")))
        self.assertIn("twice", self.broken(lambda r: r[1].update(index="1")))
        self.assertIn("names no Unique", self.broken(lambda r: moon(r).update(OLD_CLICK, unique_entry="6581")))
        self.assertIn("title is 1 to", self.broken(lambda r: moon(r).update(OLD_CLICK, title="a|b")))
        self.assertIn("type", self.broken(lambda r: r[0].update(type="event")))
        self.assertIn("objective's display", self.broken(lambda r: moon(r).update(OLD_CLICK, objective_display="")))
        # diablocraft-dm9vg.18: a Kill on a spot of its own; diablocraft-hyoic.2: the master list names every Kill's target
        self.assertIn("not both", self.broken(lambda r: moon(r).update(anchors="6")))                    # an anchor and a spot
        self.assertIn("not both", self.broken(lambda r: ungoro(r).update(anchors="414;415")))            # two anchors
        self.assertIn("not both", self.broken(lambda r: ungoro(r).update(anchors="")))                   # neither
        self.assertIn("names no Unique", self.broken(lambda r: moon(r).update(unique_entry="910048")))
        self.assertIn("names no Unique", self.broken(lambda r: moon(r).update(unique_name="Grimfeather the Moonmad")))
        self.assertIn("no title, objective display", self.broken(lambda r: ungoro(r).update(title="Kill Ravasaur Matriarch")))
        self.assertIn("no title, objective display", self.broken(lambda r: ungoro(r).update(objective_text="Ravasaur Matriarch slain")))
        self.assertIn("four numbers", self.broken(lambda r: moon(r).update(spot="7941.7803;-2205.3403;491.38812")))
        self.assertIn("four numbers", self.broken(lambda r: moon(r).update(spot="7941.7803;-2205.3403;491.38812;nan")))
        self.assertIn("spot of its own", self.broken(lambda r: moon(r).update(OLD_CLICK, spot="1;2;3;4")))
        self.assertIn("not both", self.broken(lambda r: r[0].update(spot="1;2;3;4")))
        self.assertIn("no title, objective display", self.broken(lambda r: r[0].update(objective_display="2048")))

    def test_the_zone_sheet_refuses_an_act_outside_one_to_five(self):
        """diablocraft-hyoic.1: generate_rifts.py checks the act column the bounty generator matches columns against."""
        import generate_rifts
        rows = (G.D3 / "rift_open_zones.csv").read_text(encoding="utf-8")
        for act in ("", "0", "6", "x"):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "rift_open_zones.csv"
                path.write_text(rows.replace("open_rift_entry_tanaris,2,", f"open_rift_entry_tanaris,{act},"), encoding="utf-8")
                with self.assertRaises(SystemExit) as caught:
                    generate_rifts.read_open_zone_rows(path)
                self.assertIn("tanaris's act", str(caught.exception))
        self.assertEqual({r["key"]: r["act"] for r in generate_rifts.read_open_zone_rows()},
                         {"ungoro": "2", "tanaris": "2", "thousandneedles": "2", "azshara": "1", "moonglade": "1",
                          "darkshore": "1", "winterspring": "1", "felwood": "1", "ashenvale": "1", "durotar": "1",
                          "stonetalonmountains": "1", "silithus": "2", "feralas": "2", "desolace": "2", "dustwallowmarsh": "2",
                          "thebarrens": "2",
                          "westernplaguelands": "3", "easternplaguelands": "3", "tirisfalglades": "3", "silverpineforest": "3",
                          "alteracmountains": "3", "hillsbradfoothills": "3", "thehinterlands": "3",
                          "wetlands": "4", "lochmodan": "4", "dunmorogh": "4", "badlands": "4", "burningsteppes": "4",
                          "redridgemountains": "4", "elwynnforest": "4", "swampofsorrows": "4", "westfall": "4",
                          "stranglethornvale": "4",
                          "hellfirepeninsula": "5", "zangarmarsh": "5", "nagrand": "5", "terokkarforest": "5",
                          "shadowmoonvalley": "5", "netherstorm": "5", "bladesedgemountains": "5"})

    # diablocraft-hyoic.2: the named-target master list.
    def test_the_target_list_is_stock_creatures_and_made_uniques_with_grimfeather_and_the_matriarch(self):
        """Cross-source: each target is a creature of the core's base data or a made Unique, and the designer's two are on it."""
        base = (G.MODULE.parent / "azerothcore-wotlk/data/sql/base/db_world/creature_template.sql").read_text(encoding="utf-8")
        made = G.made_uniques()
        named = {t["entry"]: t["name"] for t in G.targets()}
        self.assertEqual(named["910048"], "Grimfeather the Moonmad")
        self.assertEqual(named["6581"], "Ravasaur Matriarch")
        for entry, name in named.items():
            if entry in made:
                self.assertEqual(made[entry]["name"], name)
            else:
                # the dump writes an apostrophe doubled or backslashed (Hed'mush the Rotting)
                quoted = re.escape(name).replace("'", r"(?:''|\\')")
                self.assertRegex(base, rf"\({entry},0,0,0,0,0,'{quoted}'")

    def broken_targets(self, text):
        with tempfile.TemporaryDirectory() as folder:
            sheets(folder, lambda rows: None)
            (Path(folder) / "bounty_targets.csv").write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                G.catalogue(folder)
            return str(caught.exception)

    def test_target_refusals(self):
        head = "entry,name,source\n"
        self.assertIn("at least one", self.broken_targets(head))
        self.assertIn("columns", self.broken_targets("entry,name\n6581,Ravasaur Matriarch\n"))
        self.assertIn("once", self.broken_targets(head + "6581,Ravasaur Matriarch,\n6581,Ravasaur Matriarch,\n"))
        self.assertIn("once", self.broken_targets(head + "0,Nobody,\n"))
        self.assertIn("no | or tab", self.broken_targets(head + "6581,Ravasaur|Matriarch,\n"))
        self.assertIn("keeps its bounty_uniques.csv name", self.broken_targets(head + "910048,Grimfeather,\n"))
        self.assertIn("over", self.broken_targets(head + "6581," + "x" * 76 + ",\n"))

    # W2 (diablocraft-dm9vg.2): the Click objective's object.
    def test_committed_objectives_migration_is_the_render(self):
        path = G.MODULE / "data/sql/db-world/updates" / G.OBJECTIVES
        self.assertEqual(path.read_text(encoding="utf-8"), G.render_objectives())
        self.assertEqual((G.MODULE / "data/generated" / G.OBJECTIVES).read_text(encoding="utf-8"), G.render_objectives())

    def test_each_click_bounty_wears_a_clickable_display_the_client_has(self):
        """Cross-source: the template is a goober (the client lets a player click type 10, not a type 5 decoration) and its
        display is a row of the GameObjectDisplayInfo.dbc the client patch ships."""
        import struct
        raw = (G.MODULE.parent / "client-patch/dbc/GameObjectDisplayInfo.dbc").read_bytes()
        _, count, _, size, _ = struct.unpack_from("<4s4I", raw)
        displays = {struct.unpack_from("<I", raw, 20 + n * size)[0] for n in range(count)}
        sql = G.render_objectives()
        templates = re.findall(r"^\((9101\d\d), (\d+), (\d+), '", sql, re.M)
        links = dict(re.findall(r"^\((\d+), (9101\d\d)\)", sql, re.M))
        clicks = [(bid, r) for bid, r, _, _ in G.catalogue() if r["type"] == "click"]
        self.assertEqual(len(templates), len(clicks))
        for (entry, kind, display), (bid, row) in zip(templates, clicks):
            self.assertEqual((kind, display, links[str(bid)]), ("10", row["objective_display"], entry))
            self.assertIn(int(display), displays)
            self.assertIn(int(entry), G.OBJECTIVE_ENTRIES)


class Board(unittest.TestCase):
    DRAW = "Seq rng; Board b = Draw(catalog, targets, Rules{0, 3, 6}, std::ref(rng));\n"

    # diablocraft-hyoic.1: a column is an act; act 1 has Azshara and Moonglade, act 2 Un'Goro, Tanaris and Thousand
    # Needles, acts 3-5 no zone yet. A short act draws what it has (ruling 2026-10-12).
    def test_draw_fills_each_act_with_its_zones_rest_locked(self):
        both(self, self.DRAW + '''
    assert(b.size() == 5);
    assert(At(b, 1, 1) && At(b, 1, 2) && !At(b, 1, 3) && At(b, 2, 1) && At(b, 2, 2) && At(b, 2, 3) && !At(b, 2, 4));
    for (std::uint32_t id : {101u, 102u, 201u, 202u, 203u}) assert(Of(b, id) && Of(b, id)->column == id / 100);
    assert(StateOf(b, 1) == ColumnState::Open && StateOf(b, 2) == ColumnState::Open);
    for (unsigned col = 3; col <= 5; ++col) assert(StateOf(b, col) == ColumnState::Locked);''',
             "pool.erase(pool.begin() + pick);", ";")

    def test_click_draws_between_min_and_max_of_its_spots(self):
        both(self, '''
    for (unsigned lo = 0; lo < 8; ++lo) for (unsigned hi = 0; hi < 8; ++hi) for (unsigned seed = 0; seed < 7; ++seed) {
        Seq rng{seed}; Board b = Draw(catalog, targets, Rules{0, lo, hi}, std::ref(rng));
        Cell const* c = Of(b, 102); assert(c);
        unsigned want_lo = std::max(1u, std::min(lo, hi)), want_hi = std::min(6u, std::max(std::max(lo, hi), 1u));
        assert(c->need >= std::min(want_lo, 6u) && c->need <= want_hi);
        assert(Bits(c->objectives) == c->need && c->objectives < (1u << 6));
    }''', "std::clamp<std::uint32_t>(rng(lo, hi), 1, have)", "rng(lo, hi)", sql=click_sql())

    # diablocraft-hyoic.2: each zone's Kill draws its own target from the master list.
    def test_a_kill_draws_its_target_from_the_list(self):
        both(self, '''
    std::vector<std::uint32_t> seen;
    for (unsigned seed = 0; seed < 25; ++seed) {
        Seq rng{seed}; Board b = Draw(catalog, targets, Rules{0, 3, 6}, std::ref(rng));
        for (Cell const& c : b) {
            assert(std::any_of(targets.begin(), targets.end(), [&](Target const& t) { return t.entry == c.target; }));
            if (std::find(seen.begin(), seen.end(), c.target) == seen.end()) seen.push_back(c.target);
        }
    }
    assert(seen.size() == targets.size());                                    // every target can come up
    Seq rng; for (Cell const& c : Draw(catalog, {}, Rules{0, 3, 6}, std::ref(rng))) assert(c.target == 0);   // no list, no target''',
             "c.target = targets[rng(0, static_cast<std::uint32_t>(targets.size() - 1))].entry;", "c.target = targets[0].entry;")

    def test_a_click_draws_no_target(self):
        both(self, self.DRAW + 'assert(Of(b, 102)->target == 0 && Of(b, 101)->target != 0);',
             "                else\n                {\n                    c.need = rules.killMonsters;",
             "                c.target = targets.front().entry;\n                if (false) {}\n                else\n                {\n                    c.need = rules.killMonsters;",
             sql=click_sql())

    def test_a_cells_title_is_its_targets(self):
        both(self, '''
    Bounty const& azshara = *Find(catalog, 101);
    assert(CellTitle(Cell{1, 1, 101, 0, 0, 0, false, 6649}, azshara, targets) == "Kill Lady Sesspira");
    assert(CellTitle(Cell{1, 1, 101, 0, 0, 0, false, 910048}, azshara, targets) == "Kill Grimfeather the Moonmad");
    assert(CellTitle(Cell{1, 1, 101, 0, 0, 0, false, 12345}, azshara, targets).empty());   // not on the list
    assert(CellTitle(Cell{1, 1, 101, 0, 0, 0, false, 0}, azshara, targets).empty());''',
             "            if (t.entry == c.target)\n", "            if (true)\n")

    def test_kill_asks_the_monster_count(self):
        both(self, 'Seq rng; Board b = Draw(catalog, targets, Rules{7, 3, 6}, std::ref(rng)); assert(At(b, 1, 1)->need == 7 && At(b, 1, 1)->objectives == 0);',
             "c.need = rules.killMonsters;", "c.need = 0;")

    def test_complete_finishes_the_column_once(self):
        both(self, self.DRAW + '''
    std::uint32_t first = At(b, 1, 1)->bounty, id = At(b, 1, 2)->bounty;
    Change ch = Complete(b, first); assert(ch.changed && !ch.columnDone && StateOf(b, 1) == ColumnState::Open);
    ch = Complete(b, id); assert(ch.changed && ch.columnDone && ch.column == 1);
    assert(StateOf(b, 1) == ColumnState::Done && StateOf(b, 2) == ColumnState::Open);
    assert(!Complete(b, id).changed);
    assert(!Complete(b, 999).changed);''', "if (c.bounty == id && !c.done)\n", "if (c.bounty == id)\n")

    def test_reroll_gate_needs_every_live_cell(self):
        both(self, self.DRAW + '''
    Board const drawn = b;
    for (Cell const& c : drawn) { assert(!Cleared(b)); Complete(b, c.bounty); }
    assert(Cleared(b)); assert(!Cleared(Board{}));''', "std::all_of(board.begin(), board.end()", "std::any_of(board.begin(), board.end()")

    def test_progress_caps_and_never_completes(self):
        both(self, 'Seq rng; Board b = Draw(catalog, targets, Rules{4, 3, 6}, std::ref(rng)); std::uint32_t id = At(b, 2, 1)->bounty;\n'
                   'assert(AddProgress(b, id, 3).changed); assert(AddProgress(b, id, 5).changed); assert(At(b, 2, 1)->progress == 4);\n'
                   'assert(!AddProgress(b, id, 1).changed); assert(!At(b, 2, 1)->done); assert(StateOf(b, 2) == ColumnState::Open);',
             "c.progress = c.need - c.progress < amount ? c.need : c.progress + amount;", "c.progress += amount;")

    def test_a_click_takes_its_spot_once_and_the_last_completes(self):
        both(self, self.DRAW + '''
    Complete(b, 101);                                                          // Azshara, act 1's other zone, done first
    Cell const* c = Of(b, 102); std::uint32_t id = c->bounty, left = c->objectives; unsigned need = c->need;
    assert(!Click(b, id, 31).changed);                                         // a spot the draw did not pick
    for (unsigned spot = 0, n = 0; spot < 32; ++spot) if (left & (1u << spot)) {
        Change ch = Click(b, id, spot); ++n;
        assert(ch.changed && Of(b, 102)->progress == n && !(Of(b, 102)->objectives & (1u << spot)));
        assert(ch.completed == (n == need) && Of(b, 102)->done == (n == need) && ch.columnDone == (n == need));
        assert(!Click(b, id, spot).changed);                                   // twice is nothing
    }
    assert(StateOf(b, 1) == ColumnState::Done && Of(b, 102)->objectives == 0);
    assert(!Click(b, 201, 0).changed);                                         // a Kill bounty has no spots''',
             "if (c.bounty == id && !c.done && (c.objectives & (1u << spot)))", "if (c.bounty == id && !c.done)",
             sql=click_sql())

    def test_complete_says_it_completed(self):
        both(self, self.DRAW + 'assert(Complete(b, At(b, 1, 1)->bounty).completed);',
             "return {true, StateOf(board, c.column) == ColumnState::Done, c.column, id, true};",
             "return {true, StateOf(board, c.column) == ColumnState::Done, c.column, id};")

    def test_locked_column_without_bounties(self):
        both(self, '''
    std::vector<Bounty> one; for (auto const& x : catalog) if (x.column != 2) one.push_back(x);
    Seq rng; Board b = Draw(one, targets, Rules{0, 3, 6}, std::ref(rng));
    assert(StateOf(b, 2) == ColumnState::Locked);
    auto r = Records(b, one, targets, true); assert(r[2] == (std::vector<std::string>{"Z", "2", "locked"}));''',
             "return any ? ColumnState::Done : ColumnState::Locked;", "return ColumnState::Done;")

    def test_records_in_order_and_under_the_wire_cap(self):
        both(self, self.DRAW + '''
    Complete(b, 101); Complete(b, 102);
    auto r = Records(b, catalog, targets, false);
    assert(r.size() == 1 + 5 + 5 + 5 + 1 && r.front()[0] == "L" && r.front()[1] == "0" && r.back() == std::vector<std::string>{"E"});
    assert(r[1] == (std::vector<std::string>{"Z", "1", "done"}) && r[2] == (std::vector<std::string>{"Z", "2", "open"}));
    assert(r[3] == (std::vector<std::string>{"Z", "3", "locked"}) && r[5][2] == "locked");
    assert(r[6] == (std::vector<std::string>{"C", "1", "1", "101", "kill", "1", "0", "0", CellTitle(*Of(b, 101), *Find(catalog, 101), targets), "azshara"}));
    assert(r[6][8].rfind("Kill ", 0) == 0 && r[7][3] == "102" && r[7][8] == CellTitle(*Of(b, 102), *Find(catalog, 102), targets) && r[7][9] == "moonglade");
    for (unsigned i = 8; i <= 10; ++i) assert(r[i][0] == "C" && r[i][1] == "2" && r[i][5] == "0" && r[i][9] == (r[i][3] == "201" ? "ungoro" : r[i][3] == "202" ? "tanaris" : "thousandneedles"));
    assert(r[11][0] == "W" && r[11][1] == "azshara" && r[13][1] == "ungoro" && r[13][2] == "Un'Goro Crater" && r[15][1] == "thousandneedles");
    assert(Records(b, catalog, targets, true).front()[1] == "1");
    for (auto const& rec : r) { std::size_t n = 0; for (auto const& f : rec) n += f.size() + 1; assert(n - 1 <= ''' + str(WIRE_ROOM) + '''); }''',
             'out.push_back({"L", leader ? "1" : "0"});', 'out.push_back({"L", "1"});')

    def test_c_names_its_zone(self):
        both(self, self.DRAW + '''
    for (auto const& rec : Records(b, catalog, targets, true)) if (rec[0] == "C") {
        Bounty const* x = Find(catalog, std::stoul(rec[3])); assert(rec.size() == 10 && rec[9] == x->zoneKey && !rec[9].empty()); }''',
             'b ? CellTitle(c, *b, targets) : "", b ? b->zoneKey : ""});', 'b ? CellTitle(c, *b, targets) : "", ""});')

    # diablocraft-dm9vg.15, moved to its own record by diablocraft-hyoic.1: a W per live zone, the zone's waypoint (the
    # entrance the marker sends the player to), world x and y to a tenth of a yard, from the lookup the server hands
    # Records; empty for a zone without one. Live: the catalogue has its bounty, drawn on this board or not.
    WAYPOINTS = """
    auto waypoint = [](std::string const& key, float& x, float& y) {
        if (key == "tanaris") return false;                      // a zone whose entrance rows are blank
        x = key == "ungoro" ? -7900.5913f : 3180.6f; y = key == "ungoro" ? -2135.8982f : -4447.6367f; return true; };"""

    def test_w_carries_every_live_zones_waypoint(self):
        both(self, self.DRAW + self.WAYPOINTS + '''
    b.erase(std::remove_if(b.begin(), b.end(), [](Cell const& c) { return c.bounty == 201; }), b.end()); // Un'Goro not drawn
    std::map<std::string, std::vector<std::string>> w;
    for (auto const& rec : Records(b, catalog, targets, true, waypoint)) if (rec[0] == "W") { assert(rec.size() == 5 && !w.count(rec[1])); w[rec[1]] = rec; }
    assert(w.size() == 5);
    assert(w["ungoro"][2] == "Un'Goro Crater" && w["ungoro"][3] == "-7900.6" && w["ungoro"][4] == "-2135.9");
    assert(w["tanaris"][2] == "Tanaris" && w["tanaris"][3].empty() && w["tanaris"][4].empty());   // no entrance: no waypoint
    assert(w["azshara"][3] == "3180.6" && w["azshara"][4] == "-4447.6");
    for (auto const& rec : Records(b, catalog, targets, true)) if (rec[0] == "W") assert(rec.size() == 5 && rec[3].empty() && rec[4].empty());''',
             "located ? Yards(x) : \"\", located ? Yards(y) : \"\"", "located ? Yards(y) : \"\", located ? Yards(x) : \"\"")
        both(self, self.DRAW + self.WAYPOINTS + '''
    b.erase(std::remove_if(b.begin(), b.end(), [](Cell const& c) { return c.bounty == 201; }), b.end());
    unsigned n = 0; for (auto const& rec : Records(b, catalog, targets, true, waypoint)) n += rec[0] == "W" && rec[1] == "ungoro";
    assert(n == 1);''', "            zones.push_back(b.zoneKey);\n",
             "            zones.push_back(b.zoneKey);\n            if (std::none_of(board.begin(), board.end(), [&](Cell const& c) { return c.bounty == b.id; }))\n                continue;\n")


# --- 3. the owners, cut out of dc_bounties.cpp, over an in-memory dc_bounties_board --------------------------------------

DOUBLES = r'''
#include <algorithm>
#include <cstdint>
#include <functional>
#include <optional>
#include <tuple>
using uint8 = std::uint8_t; using uint32 = std::uint32_t;
struct ObjectGuid { uint32 low = 0; static ObjectGuid const Empty; uint32 GetCounter() const { return low; } bool IsEmpty() const { return low == 0; } };
ObjectGuid const ObjectGuid::Empty = {};
struct Group { uint32 id, leader; ObjectGuid GetGUID() const { return {id}; } ObjectGuid GetLeaderGUID() const { return {leader}; } };
struct GroupMgr { std::map<uint32, Group> groups; Group* GetGroupByGUID(uint32 id) { auto f = groups.find(id); return f == groups.end() ? nullptr : &f->second; } };
GroupMgr groupMgr; GroupMgr* sGroupMgr = &groupMgr;
// dc_bounties_board, keyed (kind, id, col, cell) -> the other six columns (bounty_id, objectives, need, progress, done, target).
using Key = std::tuple<unsigned, unsigned, unsigned, unsigned>;
std::map<Key, std::vector<uint32>> table; int commits = 0;
struct Field { uint32 v; template<class T> T Get() const { return static_cast<T>(v); } };
struct Result { std::vector<std::vector<Field>> rows; std::size_t at = 0; Field* Fetch() { return rows[at].data(); } bool NextRow() { return ++at < rows.size(); } };
struct Trans { std::vector<std::vector<uint32>> ops; template<class... A> void Append(char const*, A... a) { ops.push_back({static_cast<uint32>(a)...}); } };
using CharacterDatabaseTransaction = std::shared_ptr<Trans>;
struct Db {
    CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Trans>(); }
    void DirectCommitTransaction(CharacterDatabaseTransaction t) {
        ++commits;
        for (auto const& op : t->ops) Apply(op);
    }
    template<class... A> void DirectExecute(char const*, A... a) { Apply({static_cast<uint32>(a)...}); }
    void Apply(std::vector<uint32> const& op) {
        if (op.size() == 2) { for (auto it = table.begin(); it != table.end();) it = std::get<0>(it->first) == op[0] && std::get<1>(it->first) == op[1] ? table.erase(it) : std::next(it); }
        else table[{op[0], op[1], op[2], op[3]}] = {op[4], op[5], op[6], op[7], op[8], op[9]};
    }
    template<class... A> std::shared_ptr<Result> Query(char const*, unsigned kind, unsigned id) {
        auto r = std::make_shared<Result>();
        for (auto const& [k, v] : table)
            if (std::get<0>(k) == kind && std::get<1>(k) == id)
                r->rows.push_back({{std::get<2>(k)}, {std::get<3>(k)}, {v[0]}, {v[1]}, {v[2]}, {v[3]}, {v[4]}, {v[5]}});
        return r->rows.empty() ? nullptr : r;
    }
} CharacterDatabase;
'''


def owners_source(server=SERVER):
    pieces = [definition(server, "struct Owner") + ";", "std::map<Owner, Board> boards;",
              definition(server, "Owner Solo("), definition(server, "Owner Party("),
              "Rules CurrentRules() { return {0, 3, 6}; }",
              "Seq seq; std::uint32_t Roll(std::uint32_t lo, std::uint32_t hi) { return seq(lo, hi); }",
              "std::uint64_t epoch = 1;",
              definition(server, "void SaveLocked("),
              definition(server, "Board& LoadLocked("), definition(server, "void DropLocked("),
              # W2: what a player in a zone copy gets put there. The player is only their board's owner here.
              definition(HEADER, "struct Open") + ";",
              "struct Player { Owner owner; }; Owner OwnerOf(Player const* p) { return p->owner; }",
              definition(server, "std::vector<Open> OpenIn(").replace("std::lock_guard<std::mutex> lock(boardMutex);", "")]
    return "\n".join(pieces)


def compile_owners(body, server=SERVER, sql=None):
    sql = sql or first_set_sql()
    code = (PRELUDE + DOUBLES + BOARD + catalogue_cpp(sql) + HELPERS + owners_source(server)
            + "\nunsigned Rows(unsigned kind, unsigned id) { unsigned n = 0; for (auto const& [k, v] : table) n += std::get<0>(k) == kind && std::get<1>(k) == id; return n; }\n"
            + "int main() {\n" + body + "\n    return 0;\n}\n")
    return run(code)


def owners_both(test, body, old, new, sql=None):
    ok, out = compile_owners(body, sql=sql)
    test.assertTrue(ok, out)
    ok, out = compile_owners(body, mutate(SERVER, old, new), sql=sql)
    test.assertFalse(ok, "mutation survived: " + new)


class Owners(unittest.TestCase):
    def test_a_player_draws_once_and_it_is_saved(self):
        owners_both(self, '''
    Board& b = LoadLocked(Solo({42}));
    assert(b.size() == 5 && Rows(0, 42) == 5);
    boards.clear();
    assert(LoadLocked(Solo({42})).size() == 5 && commits == 1);''',
                    "if (owner.kind == 0)\n                    board = Draw(", "if (false)\n                    board = Draw(")

    def test_a_party_copies_its_leader_then_they_move_apart(self):
        owners_both(self, '''
    groupMgr.groups[7] = Group{7, 42};
    Board& solo = LoadLocked(Solo({42}));
    Complete(solo, At(solo, 1, 1)->bounty); SaveLocked(Solo({42}), solo);
    Board& party = LoadLocked(Owner{1, 7});
    assert(party.size() == 5 && At(party, 1, 1)->done && Rows(1, 7) == 5);   // the leader's board, progress and all
    Complete(party, At(party, 2, 1)->bounty); SaveLocked(Owner{1, 7}, party);
    boards.clear();
    assert(!At(LoadLocked(Solo({42})), 2, 1)->done);                         // the solo board stays as it was
    assert(At(LoadLocked(Owner{1, 7}), 2, 1)->done);
    groupMgr.groups[7].leader = 43;                                           // a leader change keeps the party's board
    boards.clear();
    assert(At(LoadLocked(Owner{1, 7}), 2, 1)->done && Rows(0, 43) == 0);''',
                    "board = LoadLocked(Solo(leader)); // the leader's board, copied",
                    "board = Draw(catalog, targets, CurrentRules(), Roll);")

    def test_the_leaders_join_inside_group_create_copies_before_the_group_is_registered(self):
        # The core's order (Group.cpp Create: AddMember(leader) fires OnGroupAddMember; GroupHandler.cpp and LFGMgr.cpp
        # call sGroupMgr->AddGroup only afterwards): the first party load comes with the leader and no group in groupMgr.
        owners_both(self, '''
    Board& solo = LoadLocked(Solo({42}));
    Complete(solo, At(solo, 1, 1)->bounty); SaveLocked(Solo({42}), solo);
    Board& first = LoadLocked(Owner{1, 7}, ObjectGuid{42});                   // the leader's join; groupMgr has no 7 yet
    assert(first.size() == 5 && At(first, 1, 1)->done && Rows(1, 7) == 5);
    groupMgr.groups[7] = Group{7, 42};                                        // AddGroup, then the invitee joins
    Board& member = LoadLocked(Owner{1, 7});
    assert(member.size() == 5 && At(member, 1, 1)->done);                     // the leader's board, progress and all
    boards.clear();
    assert(At(LoadLocked(Owner{1, 7}), 1, 1)->done);''',
                    "if (leader.IsEmpty())\n                        if (Group* group",
                    "leader = ObjectGuid::Empty;\n                    if (leader.IsEmpty())\n                        if (Group* group")

    def test_the_add_member_hook_hands_the_leader_on(self):
        # Not compiled (it needs the core's Group): the hook gives LoadLocked the leader from the Group* it has.
        self.assertIn("Show(player, Party(group), group->GetLeaderGUID() == guid, group->GetLeaderGUID());",
                      definition(SERVER, "void OnAddMember("))
        self.assertIn("records = Records(LoadLocked(owner, partyLeader), catalog, targets, leader, DC::Rifts::OpenZoneWaypoint);",
                      definition(SERVER, "void Show("))

    def test_a_disband_drops_the_party_board_only(self):
        owners_both(self, '''
    groupMgr.groups[7] = Group{7, 42};
    LoadLocked(Owner{1, 7});
    DropLocked(Owner{1, 7});
    assert(Rows(1, 7) == 0 && !boards.count(Owner{1, 7}) && Rows(0, 42) == 5);''',
                    "boards.erase(owner);\n", "\n")

    def test_a_bounty_the_catalogue_dropped_leaves_its_cell(self):
        owners_both(self, '''
    table[{0, 9, 1, 1}] = {101, 0, 0, 0, 0, 6649};
    table[{0, 9, 2, 1}] = {777, 0, 0, 0, 0, 6649};
    table[{0, 9, 2, 2}] = {202, 0, 0, 0, 0, 0};       // diablocraft-hyoic.2: a Kill saved before the target column
    table[{0, 9, 2, 3}] = {203, 0, 0, 0, 0, 12345};   // a target the list no longer holds
    Board& b = LoadLocked(Solo({9}));
    assert(b.size() == 1 && b[0].bounty == 101 && b[0].target == 6649);''',
                    "if (Bounty const* b = Find(catalog, c.bounty); b && !CellTitle(c, *b, targets).empty())", "if (true)")
        owners_both(self, '''
    table[{0, 9, 2, 2}] = {202, 0, 0, 0, 0, 0};
    assert(LoadLocked(Solo({9})).size() == 5);                                  // nothing kept: a new board is drawn''',
                    "if (Bounty const* b = Find(catalog, c.bounty); b && !CellTitle(c, *b, targets).empty())",
                    "if (Bounty const* b = Find(catalog, c.bounty); b)")

    def test_saves_and_drops_move_the_epoch(self):
        owners_both(self, '''
    std::uint64_t before = epoch; LoadLocked(Solo({9})); assert(epoch > before);
    before = epoch; DropLocked(Solo({9})); assert(epoch > before);''',
                    "            CharacterDatabase.DirectCommitTransaction(trans);\n            ++epoch;", "            CharacterDatabase.DirectCommitTransaction(trans);")


class Objectives(unittest.TestCase):
    """W2 (diablocraft-dm9vg.2): what OpenIn hands the objectives for a player in a zone copy, and the guard packs."""

    PARTY = "sGroupMgr->groups[7] = Group{7, 9}; Player p{Party(&sGroupMgr->groups[7])}; Board& b = LoadLocked(p.owner, ObjectGuid{9});\n"

    def test_a_kill_bounty_is_its_unique_on_its_own_spot_until_done(self):
        owners_both(self, self.PARTY + '''
    auto open = OpenIn(&p, 751, 490);
    assert(open.size() == 1 && open[0].bounty == 201 && open[0].uniqueEntry == Of(b, 201)->target && open[0].uniqueEntry); // hyoic.2: its drawn target
    assert(open[0].spots.size() == 1 && open[0].spots[0].first == 0 && open[0].spots[0].second.anchor == 414);
    assert(OpenIn(&p, 751, 440).size() == 1 && OpenIn(&p, 751, 440)[0].bounty == 202);   // Tanaris is its own
    assert(OpenIn(&p, 1, 490).empty());                                                    // the stock map has none
    Complete(b, 201); assert(OpenIn(&p, 751, 490).empty());
    auto moon = OpenIn(&p, 751, 493);                                                      // dm9vg.18: a made Unique, its own spot
    assert(moon.size() == 1 && moon[0].bounty == 102 && moon[0].uniqueEntry == Of(b, 102)->target && moon[0].spots.size() == 1);
    assert(moon[0].spots[0].second.anchor == 0 && moon[0].spots[0].second.x == 7941.7803f && moon[0].spots[0].second.o == 3.1145103f);''',
                    "Bounty const* b = c.done ? nullptr : Find(catalog, c.bounty);", "Bounty const* b = Find(catalog, c.bounty);")
        owners_both(self, self.PARTY + 'assert(OpenIn(&p, 751, 490)[0].uniqueEntry == Of(b, 201)->target);',
                    'Open open{b->id, b->type == "kill" ? c.target : 0, b->objectiveEntry};',
                    'Open open{b->id, b->type == "kill" ? 6581u : 0, b->objectiveEntry};')

    def test_a_click_bounty_hands_out_only_the_spots_still_to_click(self):
        owners_both(self, self.PARTY + '''
    Cell const* c = Of(b, 102); std::uint32_t drawn = c->objectives;
    auto open = OpenIn(&p, 751, 493); assert(open.size() == 1 && open[0].uniqueEntry == 0 && open[0].spots.size() == c->need);
    for (auto const& [n, spot] : open[0].spots) assert(drawn & (1u << n));
    unsigned first = open[0].spots.front().first; Click(b, 102, first);
    auto after = OpenIn(&p, 751, 493); assert(after[0].spots.size() == c->need - 1);
    for (auto const& [n, spot] : after[0].spots) assert(n != first);''',
                    "if (c.objectives & (1u << spot))\n                        open.spots.push_back", "open.spots.push_back",
                    sql=click_sql())

    def test_the_zone_decides(self):
        owners_both(self, self.PARTY + 'assert(OpenIn(&p, 751, 16).size() == 1 && OpenIn(&p, 751, 16)[0].bounty == 101); assert(OpenIn(&p, 751, 1).empty());',
                    "b->mapId != mapId || b->zoneId != zoneId ||", "b->mapId != mapId ||")

    def test_every_click_spot_has_the_surveys_pack_to_guard_it(self):
        """Cross-source: the loader joins each spot to dc_rift_anchor by zone name and anchor (a pack the survey kept, so
        hostile to players); every Click spot of the generated catalogue finds a native and a pack of at least one."""
        self.assertIn("LEFT JOIN dc_rift_anchor a ON a.dungeon=b.zone_name AND a.anchor=s.anchor", SERVER)
        survey = {(a["dungeon"], int(a["anchor"])): a for a in G.read("rift_anchors.csv", G.D3)}
        with tempfile.TemporaryDirectory() as folder:  # the Click fixture: no Click bounty is in the sheet (dm9vg.18)
            sheets(folder, lambda rows: moon(rows).update(OLD_CLICK))
            clicks = [(z["name"], a) for _, r, z, anchors in G.catalogue(folder) if r["type"] == "click" for a in anchors]
        self.assertTrue(clicks)
        for zone, anchor in clicks:
            row = survey[(zone, int(anchor["anchor"]))]
            self.assertTrue(row["native_entry"].isdigit() and int(row["pack_size"]) >= 1, (zone, anchor["anchor"]))



# --- 4. the owned monster on a rift floor's copy, in the core's order -----------------------------------------------------

RIFT_DOUBLES = r"""
#include <cassert>
#include <cstdint>
#include <functional>
#include <string>
#include "dc_charm.h"
using uint32 = std::uint32_t;
enum DamageEffectType { DIRECT_DAMAGE }; enum SpellSchoolMask { SPELL_SCHOOL_MASK_NORMAL };
enum { FACTION_MONSTER = 14 }; constexpr int MAX_CREATURE_SPELLS = 8;
struct Map {};
struct Unit { int party = 0; virtual ~Unit() {} };
struct Player : Unit {};
struct CreatureAI;
struct Creature : Unit {
    CreatureAI* ai = nullptr; uint32 m_spells[MAX_CREATURE_SPELLS] = {1, 2}; uint32 entry = 6581; Map map;
    // Creature::AIM_Initialize deletes the AI it replaces.
    void AIM_Initialize(CreatureAI* next);
    CreatureAI* AI() { return ai; } Map* GetMap() { return &map; }
    uint32 GetEntry() const { return entry; } uint32 GetSpawnId() const { return 0; }   // a Map::SummonCreature summon
    std::string GetScriptName() const { return ""; }                                  // stock entry, no dc_ script
    bool IsPet() const { return false; } bool IsTotem() const { return false; } bool IsCritter() const { return false; }
    bool IsGuardian() const { return false; } bool IsControlledByPlayer() const { return false; } bool IsTrigger() const { return false; }
    bool IsCharmed() const { return false; }
    void SetRegeneratingHealth(bool) {} void SetFaction(uint32) {}
};
struct CreatureAI {
    Creature* me; explicit CreatureAI(Creature* c) : me(c) {} virtual ~CreatureAI() {}
    virtual bool CanBeSeen(Player const*) { return true; } virtual void JustDied(Unit*) {}
    virtual void DamageTaken(Unit*, uint32&, DamageEffectType, SpellSchoolMask) {}
};
void Creature::AIM_Initialize(CreatureAI* next) { delete ai; ai = next; }
namespace DC::Classes::Ancients { bool IsAncientEntry(uint32) { return false; } }
namespace DC::Rifts {
constexpr uint32 CHAMPION_BASE = 8000000;
bool riftFloor = false;
bool ScalingContext(Map const*, unsigned&, unsigned&) { return riftFloor; }
namespace Family { bool IsFamilyEntry(uint32) { return false; } }
class RiftMeleeAI : public CreatureAI { public: using CreatureAI::CreatureAI; virtual bool Owns(Unit const*) const { return true; } };
class FamilyAI : public RiftMeleeAI { public: using RiftMeleeAI::RiftMeleeAI; };
"""


def rift_source(rift=RIFT_AI):
    hook = rift[rift.index("void OnCreatureAddWorld(Creature* creature) override"):]
    # Up to the summon's return: a bounty's monster is a summon, so nothing after it runs for one.
    hook = hook[:hook.index("// a summon: minions and guardians")]
    return "\n".join([definition(rift, "Charm::Body CharmBodyOf("), definition(rift, "bool IsRiftTrash("), definition(rift, "class OwnedMonsterAI") + ";",
                      definition(rift, "CreatureAI* NewOwnedMonsterAI("), definition(rift, "void StripNativeAbilities("),
                      hook.replace(" override", "") + "\n}\n} // namespace DC::Rifts\nusing namespace DC::Rifts;\n"])


def compile_rift(body, rift=RIFT_AI):
    return run(RIFT_DOUBLES + rift_source(rift) + "int main() {\n" + body + "\n    return 0;\n}\n", extra=("-I", str(SRC / "rifts")))


class OwnedOnARiftFloor(unittest.TestCase):
    BODY = """
    riftFloor = true;                                   // a party's 751 copy that holds or held a rift floor
    Unit member, stranger; member.party = 1;
    int credited = 0;
    // The claim: GetCreatureAI hands the core the owned AI, which AIM_Initialize installs ...
    Creature unique; unique.AIM_Initialize(NewOwnedMonsterAI(&unique, [](Unit const* u) { return u->party == 1; },
                                                             [&](Unit* killer) { credited += killer == &member; }));
    // ... then Creature::AddToWorld calls the module's OnCreatureAddWorld.
    OnCreatureAddWorld(&unique);
    assert(dynamic_cast<OwnedMonsterAI*>(unique.AI()));
    Player memberSeer, strangerSeer; memberSeer.party = 1;
    assert(unique.AI()->CanBeSeen(&memberSeer) && !unique.AI()->CanBeSeen(&strangerSeer));
    uint32 damage = 10; unique.AI()->DamageTaken(&stranger, damage, DIRECT_DAMAGE, SPELL_SCHOOL_MASK_NORMAL); assert(damage == 0);
    unique.AI()->JustDied(&member); assert(credited == 1);
    assert(unique.m_spells[0] == 1);                    // left alone, abilities too
    // A stock summon of no claim is still rift trash there.
    Creature plain; plain.AIM_Initialize(new CreatureAI(&plain)); OnCreatureAddWorld(&plain);
    assert(dynamic_cast<RiftMeleeAI*>(plain.AI()) && !dynamic_cast<OwnedMonsterAI*>(plain.AI()) && plain.m_spells[0] == 0);"""

    def test_the_claims_ai_survives_the_rift_hook(self):
        ok, out = compile_rift(self.BODY)
        self.assertTrue(ok, out)
        ok, out = compile_rift(self.BODY, mutate(RIFT_AI, "if (dynamic_cast<OwnedMonsterAI*>(creature->AI()))", "if (false)"))
        self.assertFalse(ok, "mutation survived: the rift hook replaces the owned AI")


if __name__ == "__main__":
    unittest.main()
