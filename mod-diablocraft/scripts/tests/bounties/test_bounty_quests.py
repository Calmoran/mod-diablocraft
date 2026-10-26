"""diablocraft-dm9vg.17: bounties as quests (brief bounty-quests-2026-10-12, ruling 2026-10-12).

1. The generator: bounties_0005_quests.sql is today's render and its mirror; a Kill bounty has one quest (its Unique, 0/1),
   a Click bounty one a count n = 1 to its spots; the words come from bounties.csv; zero rewards, not sharable,
   repeatable, filed under the zone; the map marks' area is the copy's own WorldMapArea row, read here from the DBC on
   its own; the refusals fire.
2. The rules (src/bounties/dc_bounty_board.h, compiled as it is, with the catalogue and the quest rows parsed out of the
   generated migrations): which bounty a zone shows, its count, what a player's log needs (SyncQuests) and the logout
   rule (BoardExpired). Each runs again on a mutation that breaks its rule, and that run must fail.
3. The glue (src/bounties/dc_bounty_quests.cpp): the map-mark writer, cut out and compiled against a packet double, writes
   the core's POI layout (QueryHandler.cpp HandleQuestPOIQuery); the hooks are pinned as text (when the log is synced,
   the login order, the abandon, the registration), not executed: the in-game behaviour is the designer's checks on dev.
"""
import csv
import re
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_bounties as G
from test_bounties import BOARD, HELPERS, OLD_CLICK, PRELUDE, catalogue_cpp, moon, sheets
from test_class_parity import SRC, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

QUESTS_SQL = G.MODULE / "data/sql/db-world/updates" / G.QUESTS
GLUE = (SRC / "bounties/dc_bounty_quests.cpp").read_text(encoding="utf-8")
SERVER = (SRC / "bounties/dc_bounties.cpp").read_text(encoding="utf-8")
HANDLER = (G.MODULE.parent / "azerothcore-wotlk/src/server/game/Handlers/QueryHandler.cpp").read_text(encoding="utf-8")
LINK = re.compile(r"^\((\d+), (\d+), (\d+), (\d+), (\d+)\)", re.M)  # bounty, need, target, quest, poi area


def click_fixture():
    """(catalogue sql, quests sql) of the sheets with Moonglade's old Click row put back: no bounty of the sheet is a Click
    since diablocraft-dm9vg.18, and the rules for a Click's counts stay in the code, unused, so they run on this."""
    with tempfile.TemporaryDirectory() as folder:
        sheets(folder, lambda rows: moon(rows).update(OLD_CLICK))
        return G.render(folder), G.render_quests(folder)


CLICK_SQL, CLICK_QUESTS = click_fixture()


def rows_cpp(sql=None):
    links = LINK.findall(sql or QUESTS_SQL.read_text(encoding="utf-8"))
    assert links, "no dc_bounties_quest rows parsed"
    return ("std::vector<QuestRow> rows = {" + ",".join(f"{{{b},{n},{q},{t}}}" for b, n, t, q, _ in links) + "};\n"
            "std::uint32_t Q(std::uint32_t bounty, std::uint32_t need, std::uint32_t target = 0) "
            "{ auto r = QuestOf(rows, bounty, need, target); assert(r); return r->quest; }\n")


def quest_rows(sql):
    return re.findall(r"^  \((\d+), 2, -1, 0, (\d+), 0, 0, 0, 0, (\d+), 0, 0, 0, '((?:[^']|'')*)', '((?:[^']|'')*)', "
                      r"'((?:[^']|'')*)', '', (\d+), (\d+), '((?:[^']|'')*)'\)", sql, re.M)


class Generator(unittest.TestCase):
    def test_the_migration_is_the_render_and_its_mirror(self):
        sql = G.render_quests()
        self.assertEqual(QUESTS_SQL.read_text(encoding="utf-8"), sql)
        self.assertEqual((G.MODULE / "data/generated" / G.QUESTS).read_text(encoding="utf-8"), sql)
        self.assertNotIn(G.QUESTS, (G.MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))

    def test_one_quest_a_bounty_and_a_count(self):
        sql = QUESTS_SQL.read_text(encoding="utf-8")
        templates = quest_rows(sql)
        links = LINK.findall(sql)
        sheet = {int(r["column"]) * 100 + int(r["index"]): r for r in G.read("bounties.csv", G.D3)}
        spots = {bid: len(anchors) for bid, _r, _z, anchors in G.catalogue()}
        named = {int(t["entry"]): t["name"] for t in G.targets()}
        # diablocraft-hyoic.2: a Kill has a quest per named target it can draw; a Click a quest per count (target 0)
        want = sorted((bid, n, t) for bid, r in sheet.items()
                      for n, t in ([(1, t) for t in named] if r["type"] == "kill" else [(n, 0) for n in range(1, spots[bid] + 1)]))
        self.assertEqual(sorted((int(b), int(n), int(t)) for b, n, t, _q, _a in links), want)
        self.assertEqual(len(templates), len(want))
        by_quest = {int(t[0]): t for t in templates}
        self.assertEqual(len(by_quest), len(templates), "a quest id twice")
        zones = {z["key"]: z for z in G.read("rift_open_zones.csv", G.D3)}
        for b, n, t, q, _a in links:
            quest, sort, flags, title, log, text, credit, count, objective = by_quest[int(q)]
            row = sheet[int(b)]
            self.assertIn(int(quest), G.QUEST_ENTRIES)
            self.assertEqual(int(count), int(n))
            self.assertEqual(int(sort), int(zones[row["zone"]]["zone_id"]))   # the log files it under the zone
            self.assertEqual(int(flags) & 8, 0, "QUEST_FLAGS_SHARABLE")         # not shareable
            self.assertEqual(int(credit), G.CREDIT_CREATURE)   # the bounties' own, never the rifts' 910015 (l2hsp, test_rift_credit)
            if row["type"] == "kill":   # diablocraft-hyoic.2: dm9vg.1's words, with the target and the zone
                name, zone = named[int(t)], zones[row["zone"]]["name"]
                words = (f"Kill {name}", f"Slay {name} in {zone}.", f"{name} slain")
            else:
                words = (row["title"], row["quest_text"], row["objective_text"])
            self.assertEqual((title, log, objective), tuple(w.replace("'", "''") for w in words))
        self.assertIn("'Kill Ravasaur Matriarch', 'Slay Ravasaur Matriarch in Un''Goro Crater.', 'Slay Ravasaur Matriarch in "
                      f"Un''Goro Crater.', '', {G.CREDIT_CREATURE}, 1, 'Ravasaur Matriarch slain'", sql)   # the brief's own words
        self.assertIn("'Slay Grimfeather the Moonmad in Tanaris.'", sql)   # hyoic.2: any target in any zone
        self.assertIn("Grimfeather the Moonmad slain", sql)   # dm9vg.18: Moonglade's Kill
        self.assertIn("Shrines activated", CLICK_QUESTS)     # the unused Click type still renders its words
        self.assertRegex(sql, r"INSERT INTO `quest_template_addon` \(`ID`, `SpecialFlags`\) VALUES\n(  \(\d+, 1\),?\n)+")

    def test_quests_are_numbered_by_zone_then_target(self):
        """diablocraft-hyoic.1 and .2: quests are numbered in the zone sheet's order, then the target sheet's, not the bounty
        id's (the client caches a quest by id): Un'Goro and the Matriarch keep 910200, a zone added at the sheet's end takes the
        ids after."""
        links = {(int(b), int(t)): int(q) for b, _n, t, q, _a in LINK.findall(QUESTS_SQL.read_text(encoding="utf-8"))}
        # rift_open_zones.csv: Un'Goro, Tanaris, Thousand Needles, Azshara, Moonglade, then A2's act 1 and 2 zones (hyoic.5),
        # then A5's act 3 and 4 zones (hyoic.8), then A7's act 5 zones (hyoic.10)
        order = [201, 202, 203, 101, 102, 103, 104, 105, 106, 107, 108, 204, 205, 206, 207, 208,
                 301, 302, 303, 304, 305, 306, 307, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410,
                 501, 502, 503, 504, 505, 506, 507]
        named = [int(t["entry"]) for t in G.targets()]
        self.assertEqual(links, {(b, t): 910200 + z * len(named) + i for z, b in enumerate(order) for i, t in enumerate(named)})
        self.assertEqual(links[(201, 6581)], 910200)

    def test_the_map_marks_go_on_the_copys_own_world_map_area(self):
        raw = (G.MODULE.parent / "client-patch/dbc/WorldMapArea.dbc").read_bytes()
        _, count, _, size, _ = struct.unpack_from("<4s4I", raw)
        rows = [struct.unpack_from("<3I", raw, 20 + i * size) for i in range(count)]
        for bid, _r, zone, _a in G.catalogue():
            want = [r[0] for r in rows if r[1] == int(zone["map_id"]) and r[2] == int(zone["zone_id"])]
            got = {int(a) for b, _n, _t, _q, a in LINK.findall(QUESTS_SQL.read_text(encoding="utf-8")) if int(b) == bid}
            self.assertEqual(got, set(want), bid)
        self.assertIn(3241, {int(a) for *_, a in LINK.findall(QUESTS_SQL.read_text(encoding="utf-8"))})  # Moonglade's clone

    def refuse(self, edit, message):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("bounties.csv", "rift_open_zones.csv", "rift_anchors.csv", "bounty_uniques.csv", "bounty_targets.csv"):
                shutil.copy(G.D3 / name, Path(folder) / name)
            path = Path(folder) / "bounties.csv"
            rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
            edit(rows)
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, message):
                G.render_quests(folder)

    def test_refusals(self):
        self.refuse(lambda rows: moon(rows).update(OLD_CLICK, objective_text=""), "objective_text is 1 to")
        self.refuse(lambda rows: moon(rows).update(OLD_CLICK, quest_text="a|b"), "quest_text is 1 to")
        self.refuse(lambda rows: moon(rows).update(OLD_CLICK, objective_text="x" * 81), "objective_text is 1 to")
        with tempfile.TemporaryDirectory() as folder:   # a zone with no world map row of its own
            raw = bytearray((G.MODULE.parent / "client-patch/dbc/WorldMapArea.dbc").read_bytes())
            _, count, _, size, _ = struct.unpack_from("<4s4I", raw)
            for i in range(count):
                if struct.unpack_from("<3I", raw, 20 + i * size)[1:] == (751, 493):
                    struct.pack_into("<I", raw, 20 + i * size + 8, 0)
            dbc = Path(folder) / "WorldMapArea.dbc"
            dbc.write_bytes(bytes(raw))
            with self.assertRaisesRegex(ValueError, "exactly one"):
                G.render_quests(areas_path=dbc)


def compile_rules(body, board=BOARD):
    code = (PRELUDE + "#include <algorithm>\n" + board + catalogue_cpp(CLICK_SQL) + HELPERS
            + rows_cpp(CLICK_QUESTS) + "int main() {\n" + body + "\n    return 0;\n}\n")
    return run(code)


def check(test, body, old, new):
    """The body runs on the real header, and fails on the header with `old` turned into `new` (one rule broken)."""
    ok, out = compile_rules(body)
    test.assertTrue(ok, out)
    ok, out = compile_rules(body, mutate(BOARD, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


# The board a player plays, built by hand on the Click fixture's catalogue: Un'Goro's Kill (201) and Moonglade's old Click (102),
# column then cell as diablocraft-hyoic.1 numbers them (act 2 cell 1, act 1 cell 2).
BOARD_SETUP = r'''
    Board b{Cell{2, 1, 201, 0, 0, 0, false, 6581}, Cell{1, 2, 102, 0b1111, 4, 0, false}};
    std::uint32_t const MAP = 751, UNGORO = 490, MOONGLADE = 493, TANARIS = 440;
    std::uint32_t const killQ = Q(201, 1, 6581), clickQ = Q(102, 4);
'''


class Rules(unittest.TestCase):
    def test_a_kills_quest_is_its_drawn_targets(self):
        """diablocraft-hyoic.2: Un'Goro's quest names the target its board drew."""
        check(self, BOARD_SETUP + r'''
    b[0].target = 8208;
    QuestSync s = SyncQuests(b, catalog, rows, {}, true, MAP, UNGORO);
    assert(s.quest == Q(201, 1, 8208) && s.quest != killQ && s.add == s.quest);''',
              "if (r.bounty == bounty && r.need == need && r.target == target)", "if (r.bounty == bounty && r.need == need)")

    def test_a_zone_shows_its_first_open_bounty_and_no_other(self):
        check(self, BOARD_SETUP + r'''
    assert(Showing(b, catalog, MAP, UNGORO)->bounty == 201 && Showing(b, catalog, MAP, MOONGLADE)->bounty == 102);
    assert(!Showing(b, catalog, MAP, TANARIS) && !Showing(b, catalog, 750, UNGORO));   // no bounty there; another map
    b[0].done = true;
    assert(!Showing(b, catalog, MAP, UNGORO));                                         // a done zone shows nothing''',
              "b && b->mapId == mapId && b->zoneId == zoneId", "b && b->mapId == mapId")

    def test_a_done_bounty_is_not_shown(self):
        check(self, BOARD_SETUP + r'''
    b[1].done = true;
    assert(!Showing(b, catalog, MAP, MOONGLADE));''', "            if (!c.done)\n                if (Bounty const* b = Find", "            if (true)\n                if (Bounty const* b = Find")

    def test_the_count_is_the_drawn_n_and_the_clicks(self):
        check(self, BOARD_SETUP + r'''
    Bounty const& kill = *Find(catalog, 201), &click = *Find(catalog, 102);
    assert(QuestNeed(b[0], kill) == 1 && QuestNeed(b[1], click) == 4);   // a Kill's Unique; a Click's drawn n
    assert(QuestCount(b[0], kill) == 0 && QuestCount(b[1], click) == 0);
    b[1].progress = 2; b[0].progress = 3;
    assert(QuestCount(b[1], click) == 2 && QuestCount(b[0], kill) == 0);   // clicks count; a Kill waits for its Unique
    b[0].done = true; b[1].done = true;
    assert(QuestCount(b[0], kill) == 1 && QuestCount(b[1], click) == 4);''',
              "return b.type == \"click\" ? c.need : 1;", "return b.type == \"click\" ? 6 : 1;")
        check(self, BOARD_SETUP + r'''
    Bounty const& kill = *Find(catalog, 201);
    b[0].progress = 3;
    assert(QuestCount(b[0], kill) == 0);''', "return b.type == \"click\" ? std::min(c.progress, c.need) : 0;",
              "return std::min(c.progress, c.need) + (b.type == \"click\" ? 0 : c.progress);")

    def test_entering_a_zone_adds_its_quest_with_its_count(self):
        check(self, BOARD_SETUP + r'''
    b[1].progress = 2;
    QuestSync s = SyncQuests(b, catalog, rows, {}, true, MAP, MOONGLADE);
    assert(s.add == clickQ && s.quest == clickQ && s.count == 2 && s.strip.empty() && s.finish.empty());
    s = SyncQuests(b, catalog, rows, {clickQ}, true, MAP, MOONGLADE);
    assert(s.add == 0 && s.quest == clickQ && s.count == 2);   // held: only the count is written''',
              "if (out.quest && std::find(held.begin(), held.end(), out.quest) == held.end())", "if (out.quest)")

    def test_another_zone_or_leaving_the_copy_takes_it_out(self):
        check(self, BOARD_SETUP + r'''
    QuestSync s = SyncQuests(b, catalog, rows, {clickQ}, true, MAP, UNGORO);   // walked into Un'Goro
    assert(s.strip == std::vector<std::uint32_t>{clickQ} && s.add == killQ);
    s = SyncQuests(b, catalog, rows, {killQ}, false, MAP, UNGORO);             // left the copy (or logged in)
    assert(s.strip == std::vector<std::uint32_t>{killQ} && s.add == 0 && s.quest == 0);
    s = SyncQuests(b, catalog, rows, {killQ}, true, MAP, TANARIS);             // a zone with no bounty
    assert(s.strip == std::vector<std::uint32_t>{killQ} && s.quest == 0);''',
              "if (Cell const* c = here ? Showing(board, catalog, mapId, zoneId) : nullptr)",
              "if (Cell const* c = Showing(board, catalog, mapId, zoneId))")

    def test_a_done_bounty_is_finished_then_taken_out(self):
        check(self, BOARD_SETUP + r'''
    b[0].done = true;
    QuestSync s = SyncQuests(b, catalog, rows, {killQ}, true, MAP, UNGORO);
    assert(s.finish == std::vector<std::uint32_t>{killQ} && s.strip.empty() && s.quest == 0);''',
              "            (done ? out.finish : out.strip).push_back(quest);", "            out.strip.push_back(quest);")

    def test_a_count_with_no_quest_row_shows_nothing(self):
        check(self, BOARD_SETUP + r'''
    b[1].need = 7;   // more than Moonglade's six spots: no row
    QuestSync s = SyncQuests(b, catalog, rows, {}, true, MAP, MOONGLADE);
    assert(s.quest == 0 && s.add == 0);''', "            if (QuestRow const* row = QuestOf(rows, b.id, QuestNeed(*c, b), c->target))",
              "            if (QuestRow const* row = QuestOf(rows, b.id, 4, c->target))")

    def test_a_board_is_gone_only_past_the_grace_with_nobody_online(self):
        check(self, r'''
    assert(!BoardExpired(false, 120, 120) && BoardExpired(false, 121, 120));   // a disconnect inside the grace keeps it
    assert(!BoardExpired(true, 100000, 120));                                  // a party with a member online keeps it''',
              "return !anyoneOnline && awaySeconds > graceSeconds;", "return awaySeconds > graceSeconds;")
        check(self, r'''
    assert(!BoardExpired(false, 120, 120));''', "return !anyoneOnline && awaySeconds > graceSeconds;",
              "return !anyoneOnline && awaySeconds >= graceSeconds;")


PACKET = r'''
#include <cassert>
#include <cstdint>
#include <utility>
#include <variant>
#include <vector>
using uint32 = std::uint32_t; using int32 = std::int32_t;
struct Spot { std::uint32_t anchor = 0; float x = 0, y = 0, z = 0, o = 0; std::uint32_t guardEntry = 0, guardCount = 0; };
struct WorldPacket {
    std::vector<std::variant<uint32, int32>> v;
    WorldPacket& operator<<(uint32 x) { v.emplace_back(x); return *this; }
    WorldPacket& operator<<(int32 x) { v.emplace_back(x); return *this; }
};
'''


class Glue(unittest.TestCase):
    def poi(self, glue):
        start = glue.index("        void WritePoi(")
        writer = glue[start:glue.index("        // The core's answer", start)]
        code = PACKET + writer + r'''
int main() {
    WorldPacket d;
    WritePoi(d, 910207, 751, 3241, {{0, Spot{6, 7497.61f, -3104.43f, 435.3f}}, {3, Spot{9, 7487.06f, -3087.76f, 439.6f}}});
    using V = std::variant<uint32, int32>;
    std::vector<V> want = {uint32(910207), uint32(2),
        uint32(0), int32(0), uint32(751), uint32(3241), uint32(0), uint32(0), uint32(1), uint32(1), int32(7497), int32(-3104),
        uint32(1), int32(0), uint32(751), uint32(3241), uint32(0), uint32(0), uint32(1), uint32(1), int32(7487), int32(-3087)};
    assert(d.v == want);
    return 0;
}
'''
        return run(code)

    def test_the_map_marks_are_the_cores_poi_layout(self):
        # The core's layout, in its own handler's order: quest, count; per POI index, objective, map, area, floor, the two
        # unknowns (priority, flags), the point count, then x and y each.
        layout = re.findall(r"data << (u?int32)\(itr2?->(\w+)", HANDLER[HANDLER.index("void WorldSession::HandleQuestPOIQuery"):])
        self.assertEqual([f for _, f in layout][:8], ["Id", "ObjectiveIndex", "MapId", "AreaId", "FloorId", "Unk3", "Unk4", "points"])
        ok, out = self.poi(GLUE)
        self.assertTrue(ok, out)
        broken = GLUE.replace("                data << uint32(area); // WorldMapArea row\n                data << uint32(0);    // floor\n",
                              "                data << uint32(0);    // floor\n                data << uint32(area); // WorldMapArea row\n")
        self.assertNotEqual(broken, GLUE)
        ok, _ = self.poi(broken)
        self.assertFalse(ok, "the area and floor swapped must fail")

    def test_the_hooks(self):
        update = GLUE[GLUE.index("void OnPlayerUpdate("):GLUE.index("void OnPlayerMapChanged(")]
        self.assertIn("if (!IsBountyMap(player->GetMapId()) || player->IsBeingTeleported() || !player->IsInWorld())", update)
        self.assertIn("Look const now{Epoch(), player->GetInstanceId(), player->GetZoneId(), player->GetMapId()};", update)
        self.assertIn("Sync(player, true);", update)
        moved = GLUE[GLUE.index("void OnPlayerMapChanged("):GLUE.index("void OnPlayerLogin(")]
        self.assertIn("if (!IsBountyMap(player->GetMapId()))\n                    Sync(player, false);", moved)
        login = GLUE[GLUE.index("void OnPlayerLogin("):GLUE.index("void OnPlayerLogout(")]
        self.assertLess(login.index("ExpireBoardsOnLogin(player);"), login.index("Sync(player, false);"))
        self.assertIn("LookAgain(player);", GLUE[GLUE.index("void OnPlayerQuestAbandon("):])
        self.assertIn("SERVERHOOK_CAN_PACKET_RECEIVE", GLUE)
        self.assertIn("RegisterQuestScripts();", SERVER[SERVER.index("void RegisterScripts()"):])
        expire = SERVER[SERVER.index("void ExpireBoardsOnLogin("):]
        self.assertIn("DC::Rifts::LogoutGraceSeconds()", expire)
        self.assertIn("BoardExpired(false, away(lastOut({player->GetGUID()})), grace)", expire)
        self.assertIn("BoardExpired(online, away(lastOut(members)), grace)", expire)


if __name__ == "__main__":
    unittest.main()
