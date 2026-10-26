"""diablocraft-kw18: the C++ half of the open-world rift proof of concept, pinned as text (it cannot run here).

dc_open_rift.cpp takes each zone's copy map from its row (bounty acts A4, diablocraft-hyoic.7): every zone's map_id must be
the Map row of a clone sheet (data/d3/world_open_rift_dbc.csv 751, world_open_rift_ek_dbc.csv 752), and no map id is left
in the file. The zones are rift_open_zones.csv through dc_rift_open_zone
(diablocraft-hmnei): the table's migration is the sheet, every zone id is a top-level zone of map 1 in AreaTable.dbc with the
sheet's name, and ZoneOf() (the copy's zone: the rift floor's, else the one the player asked for, else the first) is cut out
and driven against doubles. The entrance is its own sheet row (rifts.csv open_rift_entry_x,
_y, _z, _o: the designer's .gps of 2026-10-09, diablocraft-2yb2): EntryPoint() is cut out of the file and compiled against a
tunables double fed with those rows, and the Map.dbc corpse fields are required to stay the graveyard's. Also pins the rules of the shell: the command
is GM only, the boundary reads the player's zone on that map only and puts the player back at the entrance, a new
party member joins through the core's own TeleportTo, and the scripts are registered.

Not covered: that it compiles into the server (syntax_check.sh is run on it), the teleport into a real copy, the walk
out of the crater (docs/test-diablocraft-kw18.md is the GM check on dev).
"""
import csv
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import rifts_text  # noqa: E402
import generate_open_rift_map as gen  # noqa: E402
import harness_env  # noqa: E402

SRC = HERE.parent / "src" / "rifts"
CPP = SRC / "dc_open_rift.cpp"
RIFTS_CSV = HERE.parent / "data" / "tunables" / "rifts.csv"
ZONES_CSV = HERE.parent / "data" / "d3" / "rift_open_zones.csv"
AREA_DBC = HERE.parents[1] / "azerothcore-wotlk" / "build" / "server" / "data" / "dbc" / "AreaTable.dbc"
GPS = {"x": -7900.5913, "y": -2135.8982, "z": -249.10184, "o": 0.6463665}   # the designer's .gps on map 751, 2026-10-09


def entry_rows():
    with RIFTS_CSV.open(encoding="utf-8", newline="") as handle:
        return {r["name"]: r for r in csv.DictReader(handle)}


def problems(text, rifts):
    """What is wrong with the shell `text`; empty when every rule holds."""
    out = []
    if "MAP_ID" in text or re.search(r"\b75[0-9]\b", text[text.index("namespace DC::Rifts::OpenRift"):]):
        out.append("a map id is still in the code (A4: the zone's row carries it)")
    if "ENTRY_X" in text or "ENTRY_Y" in text or "constexpr float ENTRY" in text:
        out.append("the entrance is still a constant in the file")
    for axis in ("x", "y", "z", "o"):
        if f'zone.entryTunable + "_{axis}"' not in text:
            out.append(f"the entrance does not read <entry_tunable>_{axis}")
    if "490" in text or "UNGORO" in text:
        out.append("a zone is still hardcoded")
    loader = text[text.index("class ZoneLoader"):text.index("} // namespace")]
    if ("SELECT `key`, `name`, `zone_id`, `entry_tunable`, `act`, `map_id` FROM `dc_rift_open_zone` ORDER BY `seq`" not in loader
            or "fields[0].Get<std::string>(), fields[1].Get<std::string>(), fields[3].Get<std::string>(),\n                                     fields[2].Get<uint32>(), fields[4].Get<uint32>(), fields[5].Get<uint32>()" not in loader):
        out.append("the zones are not loaded from dc_rift_open_zone in sheet order")
    if '{"openrift", HandleOpenRift, SEC_GAMEMASTER, Console::No}' not in text:
        out.append("the command is not GM only")
    zone_hook = text[text.index("void OnPlayerUpdateZone"):text.index("void OnPlayerUpdate(")]
    if "!IsOpenZoneMap(player->GetMapId()) || player->IsBeingTeleported()" not in zone_hook:
        out.append("the boundary does not read the map")
    if "if (OpenZone const* zone = ZoneOf(player); zone && !Holds(player, newZone))" not in zone_hook:
        out.append("the boundary does not ask the player's wall")
    if "Bounce(player, *zone);" not in zone_hook:
        out.append("the zone edge does not bounce")
    bounce = text[text.index("void Bounce(Player* player, OpenZone const& zone)"):text.index("class Boundary")]
    if "Entry const entry = EntryPoint(zone);" not in bounce:
        out.append("the bounce does not use the zone's entrance")
    if "if (player->TeleportTo(zone.mapId, entry.x, entry.y, entry.z, entry.o))" not in bounce or "if (!entry.set)" not in bounce:
        out.append("the bounce does not put the player back at the entrance")
    wall_hook = text[text.index("void OnPlayerUpdate("):text.index("void OnPlayerLogout")]
    if "!IsOpenZoneMap(player->GetMapId()) || player->IsBeingTeleported()" not in wall_hook:
        out.append("the wall check does not read the map")
    if "InWallSpot(player->GetMapId(), player->GetPositionX(), player->GetPositionY(), player->GetPositionZ())" not in wall_hook or "Bounce(player, *zone);" not in wall_hook:
        out.append("a wall spot does not bounce")
    if "PLAYERHOOK_ON_UPDATE," not in text:
        out.append("the wall check is not hooked to the player update")
    command = text[text.index("static bool HandleOpenRift"):text.index("private:")]
    # bounties R0 (diablocraft-dm9vg.7): the command is routed like a trip, then goes to the entrance
    if ("SendTo(player, *zone, error)" not in command or "Arrive(player, copy, *zone, entry.x, entry.y, entry.z, entry.o)" not in command
            or "if (!entry.set)" not in command):
        out.append("the command does not go to the entrance, or goes with none set")
    if "if (candidate.key == word)" not in command or "Entry const entry = EntryPoint(*zone);" not in command:
        out.append("the command does not go to the zone it was asked for")
    if "asked[player->GetGUID().GetRawValue()] = zone->key;" not in command:
        out.append("the command does not remember the zone asked for")
    logout = text[text.index("void OnPlayerLogout"):text.index("class OpenRiftCommand")]
    if "before.erase(player->GetGUID().GetRawValue());" not in logout:
        out.append("the return point is kept after logout")
    if "asked.erase" in logout:  # bounties W5 (diablocraft-dm9vg.5): a player who logs out in a zone logs back in sealed to it
        out.append("the zone asked for is dropped at logout")
    if ("OpenRift::RegisterScripts();" not in rifts or "new Boundary();" not in text or "new OpenRiftCommand();" not in text
            or "new ZoneLoader();" not in text):
        out.append("a script is not registered")
    # zone fog (diablocraft-qm4ll): the masks are the sheet's zones over AreaTable, every arrival on the map (rift floors too)
    # lights them all (the client's engine fog does the covering), and on the map the explore hook stops the core's XP and
    # achievement credit
    if '#include "dc_zone_fog.h"' not in text:
        out.append("the fog rules are not included")
    if ("for (AreaTableEntry const* area : sAreaTableStore)" not in loader or "areas.push_back({area->ID, area->zone, area->exploreFlag});" not in loader
            or "ids.push_back(zone.zoneId);" not in loader or "fogMasks = ZoneFog::Masks(areas, ids, PLAYER_EXPLORED_ZONES_SIZE);" not in loader):
        out.append("the fog masks are not the loaded zones over AreaTable")
    enter = text[text.index("void OnPlayerEnterAll("):text.index("void OnPlayerLeaveAll(")]
    if "Light(player);" not in enter or enter.index("Light(") > enter.index("IsLiveInstance("):
        out.append("an arrival on the map does not light the zones, or a rift floor skips it")
    if "PLAYERHOOK_ON_MAP_CHANGED, PLAYERHOOK_CAN_AREA_EXPLORE_AND_OUTDOOR}" not in text:
        out.append("the explore hook is not registered")
    explore = text[text.index("bool OnPlayerCanAreaExploreAndOutdoor(Player* player) override"):text.index("class CopyCounts")]
    if "if (!IsOpenZoneMap(player->GetMapId()))\n                    return true;\n                return false;" not in explore:
        out.append("the explore hook does not stop the core on the map alone")
    if "Explore(" in text or "Darken(" in text or "RemoveFlag(PLAYER_EXPLORED_ZONES_1" in text:
        out.append("the copy still clears or lights single areas")
    return out


HARNESS_HEAD = (
    "#include <cassert>\n#include <map>\n#include <mutex>\n#include <string>\n#include <unordered_map>\n#include <unordered_set>\n#include <vector>\n")


def runner(test, directory):
    """Compile and run one harness in `directory`; the exit code."""
    compiler = shutil.which("g++") or shutil.which("c++")
    test.assertTrue(compiler, "g++ is not on PATH")
    source, binary = Path(directory) / "t.cpp", Path(directory) / "t"

    def run(src):
        source.write_text(src, encoding="utf-8")
        built = subprocess.run([compiler, "-std=c++20", "-UNDEBUG", "-D_GLIBCXX_ASSERTIONS", "-o", str(binary), str(source)],
                               capture_output=True, text=True)   # front() of no zones aborts, not UB
        test.assertEqual(built.returncode, 0, built.stderr[-2000:])
        return harness_env.run([str(binary)]).returncode
    return run


class OpenRiftScript(unittest.TestCase):
    def test_the_shell_holds_every_rule(self):
        self.assertEqual(problems(CPP.read_text(encoding="utf-8"), rifts_text()), [])

    def test_each_rule_fails_when_broken(self):
        text, rifts = CPP.read_text(encoding="utf-8"), rifts_text()
        mutations = (
            ("            if (zone.mapId == mapId)\n                return true;", "            if (mapId == 751)\n                return true;"), ('zone.entryTunable + "_z"', 'zone.entryTunable + "_x"'), ('{"openrift", HandleOpenRift, SEC_GAMEMASTER', '{"openrift", HandleOpenRift, SEC_PLAYER'),
            ("zone && !Holds(player, newZone)", "zone && newZone != 490"),
            ("                if (!IsOpenZoneMap(player->GetMapId()) || player->IsBeingTeleported())\n                    return;\n                if (OpenZone",
             "                if (player->IsBeingTeleported())\n                    return;\n                if (OpenZone"),
            ("                if (!IsOpenZoneMap(player->GetMapId()) || player->IsBeingTeleported())\n                    return;\n                bool first;",
             "                if (player->IsBeingTeleported())\n                    return;\n                bool first;"),
            ("if (player->TeleportTo(zone.mapId, entry.x, entry.y, entry.z, entry.o))", "if (player->TeleportTo(zone.mapId, entry.x, entry.y, entry.z, 0.0f))"),
            ("if (player->TeleportTo(zone.mapId, entry.x, entry.y, entry.z, entry.o))", "if (player->TeleportTo(751, entry.x, entry.y, entry.z, entry.o))"),
            ("`act`, `map_id` FROM", "`act`, 751 FROM"),
            ("zone && !Holds(player, newZone))\n                    Bounce(player, *zone);", "zone && !Holds(player, newZone))\n                    (void) 0;"),
            ("                    if (OpenZone const* zone = ZoneOf(player))\n                        Bounce(player, *zone);",
             "                    if (OpenZone const* zone = ZoneOf(player))\n                        (void) 0;"),
            ("PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT,", "PLAYERHOOK_ON_LOGOUT,"),
            ("Arrive(player, copy, *zone, entry.x, entry.y, entry.z, entry.o)", "Arrive(player, copy, *zone, entry.x, entry.y, entry.z, 0.0f)"),
            ("                before.erase(player->GetGUID().GetRawValue());\n                arrived", "                (void) 0;\n                arrived"),
            ("                before.erase(player->GetGUID().GetRawValue());\n                arrived",
             "                before.erase(player->GetGUID().GetRawValue());\n                asked.erase(player->GetGUID().GetRawValue());\n                arrived"),
            ("                    asked[player->GetGUID().GetRawValue()] = zone->key;\n", ""),
            ("if (candidate.key == word)", "if (candidate.key != word)"),
            ("Entry const entry = EntryPoint(*zone);", "Entry const entry = EntryPoint(zones.front());"),
            ("ORDER BY `seq`", "ORDER BY `key`"),
            ("new Boundary();", "(void) 0;"), ("new ZoneLoader();", "(void) 0;"),
            ('#include "dc_zone_fog.h"', ""), ("ids.push_back(zone.zoneId);", "ids.push_back(0);"),
            ("fogMasks = ZoneFog::Masks(areas, ids, PLAYER_EXPLORED_ZONES_SIZE);", "(void) 0;"),
            ("                Light(player); // every copy, a rift floor's too\n", ""),
            (", PLAYERHOOK_CAN_AREA_EXPLORE_AND_OUTDOOR}", "}"),
            ("                    return true;\n                return false;", "                    return true;\n                return true;"),
            ("        void Light(Player* player)", "        void Darken(Player* player)"))
        for old, new in mutations:
            with self.subTest(mutation=old):
                self.assertEqual(text.count(old), 1, f"{old!r} is not unique")
                self.assertNotEqual(problems(text.replace(old, new), rifts), [], f"the check passed with {old!r} replaced")
        self.assertNotEqual(problems(text, rifts.replace("OpenRift::RegisterScripts();", "")), [])

    def test_the_entrance_comes_from_the_rows_and_the_dbc_keeps_the_graveyard(self):
        rows = entry_rows()
        for axis, value in GPS.items():
            row = rows[f"open_rift_entry_{axis}"]
            self.assertEqual(float(row["value"]), value, f"open_rift_entry_{axis} is not the designer's .gps")
        self.assertEqual(rows["open_rift_entry_o"]["unit"], "radians")
        _, _, fields = gen.map_row()
        self.assertEqual((float(fields["CorpseX"]), float(fields["CorpseY"])), (-6160.06, -1142.43))   # client side unchanged
        # the production EntryPoint(), compiled against a tunables double fed with the rows, gives the .gps back
        text = CPP.read_text(encoding="utf-8")
        start = text.index("struct OpenZone")
        end = text.index("// The wall spots")
        code = (
            "#include <cassert>\n#include <cmath>\n#include <map>\n#include <string>\n#include <vector>\nusing uint32 = unsigned;\n"
            "std::map<std::string, double> sheet;\n"
            "namespace DC::Tunables { bool Has(std::string const& c, std::string const& n) { assert(c == \"rifts\"); return sheet.count(n); }\n"
            "  double Get(std::string const& c, std::string const& n) { assert(c == \"rifts\"); return sheet.at(n); } }\n"
            "namespace {\n" + text[start:end] + "}\n"
            "int main() {\n  OpenZone ungoro{\"ungoro\", \"Un'Goro Crater\", \"open_rift_entry\", 490}, tanaris{\"tanaris\", \"Tanaris\", \"open_rift_entry_tanaris\", 440};\n"
            "  assert(!EntryPoint(ungoro).set);\n"
            + "".join(f'  sheet["open_rift_entry_{a}"] = {float(rows[f"open_rift_entry_{a}"]["value"])!r};\n' for a in GPS) +
            "  Entry e = EntryPoint(ungoro); assert(e.set);\n"
            + "".join(f"  assert(std::fabs(e.{a} - {v!r}f) < 1e-3);\n" for a, v in GPS.items()) +
            "  assert(!EntryPoint(tanaris).set);   // another zone's rows, blank: no entrance, not Un'Goro's\n"
            '  sheet.erase("open_rift_entry_o"); assert(!EntryPoint(ungoro).set);   // a blank row is no entrance\n  return 0;\n}\n')
        compiler = shutil.which("g++") or shutil.which("c++")
        self.assertTrue(compiler, "g++ is not on PATH")
        with tempfile.TemporaryDirectory(prefix="dc-open-rift-") as directory:
            source = Path(directory) / "t.cpp"
            source.write_text(code, encoding="utf-8")
            subprocess.run([compiler, "-std=c++20", "-UNDEBUG", "-o", str(Path(directory) / "t"), str(source)], check=True)
            harness_env.run([str(Path(directory) / "t")], check=True)
            # a wrong row is red: the mutated file's EntryPoint reads another row for y
            bad = code.replace('names[1]', 'names[0]') if 'names[1]' in code else None
            self.assertIsNotNone(bad)
            source.write_text(bad, encoding="utf-8")
            subprocess.run([compiler, "-std=c++20", "-UNDEBUG", "-o", str(Path(directory) / "t2"), str(source)], check=True)
            self.assertNotEqual(harness_env.run([str(Path(directory) / "t2")]).returncode, 0, "y read from the x row passed")

    def wall_rows(self):
        rows = entry_rows()
        spots, n = [], 1
        while f"open_rift_wall_{n:02d}_x" in rows:
            spots.append({a: rows[f"open_rift_wall_{n:02d}_{a}"] for a in ("x", "y", "z", "r", "map")})
            n += 1
        return spots

    def test_the_wall_sheet_is_whole_and_leaves_the_entrance_alone(self):
        rows = entry_rows()
        spots = self.wall_rows()
        self.assertGreaterEqual(len(spots), 1)
        # no row past the end of the list (the list stops at the first spot with a gap), every spot has all four numbers
        self.assertEqual(len([n for n in rows if n.startswith("open_rift_wall_")]), 5 * len(spots))
        map_id, _, _ = gen.map_row()
        for n, spot in enumerate(spots, 1):
            for axis, row in spot.items():
                self.assertNotEqual(row["value"].strip(), "", f"open_rift_wall_{n:02d}_{axis} is blank")
                self.assertEqual(row["unit"], "map" if axis == "map" else "yards")
            # every spot so far is the designer's Kalimdor one (diablocraft-hyoic.7: a spot names its map)
            self.assertEqual(int(spot["map"]["value"]), map_id, f"spot {n} is not on the Kalimdor copy")
            self.assertGreater(float(spot["r"]["value"]), 0, f"spot {n} is switched off in the sheet")
            self.assertGreater(len(spot["x"]["notes"]), 0)
            # the entrance is not inside a spot: the bounce would send the player back into it, every tick
            distance = ((float(spot["x"]["value"]) - GPS["x"]) ** 2 + (float(spot["y"]["value"]) - GPS["y"]) ** 2
                        + (float(spot["z"]["value"]) - GPS["z"]) ** 2) ** 0.5
            self.assertGreater(distance, float(spot["r"]["value"]), f"spot {n} holds the entrance")

    def test_a_wall_spot_is_a_sphere_read_from_the_rows(self):
        text = CPP.read_text(encoding="utf-8")
        start, end = text.index("bool InWallSpot"), text.index("// Where each GM stood before")
        spots = self.wall_rows()
        first = {a: float(spots[0][a]["value"]) for a in "xyzr"}

        def build(body, sheet_lines):
            return (
                "#include <cassert>\n#include <cstdio>\n#include <map>\n#include <string>\nusing uint32 = unsigned;\n"
                "std::map<std::string, double> sheet;\n"
                "namespace DC::Tunables { bool Has(std::string const& c, std::string const& n) { assert(c == \"rifts\"); return sheet.count(n); }\n"
                "  double Get(std::string const& c, std::string const& n) { assert(c == \"rifts\"); return sheet.at(n); } }\n"
                "namespace {\n" + body + "}\n"
                "void spot(int n, double x, double y, double z, double r, double map = 751) { char b[40];\n"
                "  std::snprintf(b, 40, \"open_rift_wall_%02d_x\", n); sheet[b] = x; std::snprintf(b, 40, \"open_rift_wall_%02d_y\", n); sheet[b] = y;\n"
                "  std::snprintf(b, 40, \"open_rift_wall_%02d_z\", n); sheet[b] = z; std::snprintf(b, 40, \"open_rift_wall_%02d_r\", n); sheet[b] = r;\n"
                "  std::snprintf(b, 40, \"open_rift_wall_%02d_map\", n); sheet[b] = map; }\n"
                "int main() {\n" + sheet_lines + "  return 0;\n}\n")

        x, y, z, r = first["x"], first["y"], first["z"], first["r"]
        checks = (
            "  assert(!InWallSpot(751, 0, 0, 0));   // no rows, no spot\n"
            f"  spot(1, {x!r}, {y!r}, {z!r}, {r!r});\n"
            f"  assert(InWallSpot(751, {x!r}, {y!r}, {z!r}));\n"
            f"  assert(InWallSpot(751, {x + r - 1!r}, {y!r}, {z!r}));          // inside the radius\n"
            f"  assert(!InWallSpot(751, {x + r + 1!r}, {y!r}, {z!r}));         // outside it\n"
            f"  assert(!InWallSpot(751, {x!r}, {y!r}, {z + r + 1!r}));         // a sphere: too high is outside\n"
            f"  assert(!InWallSpot(751, {x + r * 0.8!r}, {y + r * 0.8!r}, {z!r}));   // the corner of a box is outside a sphere\n"
            f"  assert(!InWallSpot(752, {x!r}, {y!r}, {z!r}));   // the same spot on another map's copy is nothing (diablocraft-hyoic.7)\n"
            "  spot(2, 100, 100, 100, 10);\n"
            "  assert(InWallSpot(751, 105, 100, 100));   // the second spot\n"
            f"  spot(1, {x!r}, {y!r}, {z!r}, {r!r}, 752);\n"
            f"  assert(InWallSpot(752, {x!r}, {y!r}, {z!r}) && !InWallSpot(751, {x!r}, {y!r}, {z!r}));   // a spot on 752 holds on 752 only\n"
            "  assert(InWallSpot(751, 105, 100, 100));   // and the list goes on past it\n"
            f"  spot(1, {x!r}, {y!r}, {z!r}, {r!r});\n"
            "  spot(2, 100, 100, 100, 0);\n"
            "  assert(!InWallSpot(751, 105, 100, 100) && !InWallSpot(751, 100, 100, 100));  // radius 0 switches a spot off, even on its centre\n"
            "  spot(3, 500, 500, 500, 10);\n"
            "  sheet.erase(\"open_rift_wall_02_map\");\n"
            "  assert(!InWallSpot(751, 500, 500, 500));  // the list ends at the first gap\n"
            f"  assert(InWallSpot(751, {x!r}, {y!r}, {z!r}));   // and what is before the gap stays\n")
        compiler = shutil.which("g++") or shutil.which("c++")
        self.assertTrue(compiler, "g++ is not on PATH")
        with tempfile.TemporaryDirectory(prefix="dc-open-rift-wall-") as directory:
            source, binary = Path(directory) / "t.cpp", Path(directory) / "t"

            def run(body):
                source.write_text(build(body, checks), encoding="utf-8")
                subprocess.run([compiler, "-std=c++20", "-UNDEBUG", "-o", str(binary), str(source)], check=True)
                return harness_env.run([str(binary)]).returncode

            self.assertEqual(run(text[start:end]), 0)
            body = text[start:end]
            for old, new in (("<= radius * radius", "< 0"), ("radius > 0 && ", ""), ("dz * dz", "0"), ("dx * dx", "0"), ("n < 100", "n < 2"),
                             ("if (!set)\n                    return false;", "if (!set)\n                    continue;"),
                             ('"open_rift_wall_%02u_%s"', '"open_rift_wall_%02u_%s "'),
                             ("for (int i = 0; i < 5; ++i)", "for (int i = 0; i < 4; ++i)"),
                             (" != mapId)\n                    continue;", " != mapId && false)\n                    continue;"),
                             (" != mapId)\n                    continue;", " != mapId)\n                    return false;")):
                with self.subTest(mutation=old):
                    self.assertEqual(body.count(old), 1, f"{old!r} is not unique")
                    self.assertNotEqual(run(body.replace(old, new)), 0, f"the wall check passed with {old!r} replaced")

    def test_a_gm_with_gm_mode_on_is_not_bounced(self):
        """diablocraft-452w: the production Bounce(), compiled against a stub Player: .gm on walks free, .gm off and a player bounce."""
        text = CPP.read_text(encoding="utf-8")
        body = (text[text.index("struct OpenZone"):text.index("// The wall spots")]
                + text[text.index("void Bounce(Player* player, OpenZone const& zone)"):text.index("// The arrival check")])
        code = (
            "#include <cassert>\n#include <map>\n#include <string>\n#include <vector>\nusing uint32 = unsigned;\n"
            "std::map<std::string, double> sheet;\n"
            "namespace DC::Tunables { bool Has(std::string const&, std::string const& n) { return sheet.count(n); }\n"
            "  double Get(std::string const&, std::string const& n) { return sheet.at(n); } }\n"
            "struct WorldSession {};\n"
            "struct ChatHandler { int& said; ChatHandler(WorldSession*, int& s) : said(s) {} void SendSysMessage(char const*) { ++said; } };\n"
            "int sent = 0, teleports = 0;\n"
            "struct Player { bool gm; bool IsGameMaster() const { return gm; } WorldSession s;\n"
            "  bool TeleportTo(uint32, float, float, float, float) { ++teleports; return true; } WorldSession* GetSession() { return &s; } };\n"
            "#define ChatHandler(session) ChatHandler(session, sent)\n"
            "namespace {\n" + body + "}\n"
            "int main() {\n"
            '  for (char const* n : {"open_rift_entry_x", "open_rift_entry_y", "open_rift_entry_z", "open_rift_entry_o"}) sheet[n] = 1;\n'
            "  Player gmOn{true}, gmOff{false};\n  OpenZone ungoro{\"ungoro\", \"Un'Goro Crater\", \"open_rift_entry\", 490, 2, 751};\n"
            "  Bounce(&gmOn, ungoro);  assert(teleports == 0 && sent == 0);   // .gm on: not bounced\n"
            "  Bounce(&gmOff, ungoro); assert(teleports == 1 && sent == 1);   // a GM account with .gm off: bounced like a player\n"
            "  return 0;\n}\n")
        compiler = shutil.which("g++") or shutil.which("c++")
        self.assertTrue(compiler, "g++ is not on PATH")
        with tempfile.TemporaryDirectory(prefix="dc-open-rift-gm-") as directory:
            source, binary = Path(directory) / "t.cpp", Path(directory) / "t"

            def run(src):
                source.write_text(src, encoding="utf-8")
                subprocess.run([compiler, "-std=c++20", "-UNDEBUG", "-o", str(binary), str(source)], check=True)
                return harness_env.run([str(binary)]).returncode

            self.assertEqual(run(code), 0)
            for old, new in (("if (player->IsGameMaster())", "if (false)"), ("if (player->IsGameMaster())", "if (!player->IsGameMaster())"),
                             ("if (player->IsGameMaster())", "if (player->GetSession())")):
                with self.subTest(mutation=new):
                    self.assertEqual(code.count(old), 1)
                    self.assertNotEqual(run(code.replace(old, new)), 0, f"the GM check passed with {new!r}")

    def test_the_zones_are_the_sheet_and_areatable(self):
        """rifts_0026 is the sheet's render, every zone is a top-level zone of map 1 under the sheet's name, all on the copy."""
        import generate_rifts as R
        with ZONES_CSV.open(encoding="utf-8-sig", newline="") as handle:
            zones = list(csv.DictReader(handle))
        self.assertEqual([z["key"] for z in zones], ["ungoro", "tanaris", "thousandneedles", "azshara", "moonglade",
                                                       # diablocraft-hyoic.5 (acts A2): act 1 and 2, the stock .tele spots as entrances
                                                       "darkshore", "winterspring", "felwood", "ashenvale", "durotar", "stonetalonmountains",
                                                       "silithus", "feralas", "desolace", "dustwallowmarsh", "thebarrens",
                                                       # diablocraft-hyoic.8 (acts A5): act 3 and 4 on the Eastern Kingdoms copy 752
                                                       "westernplaguelands", "easternplaguelands", "tirisfalglades", "silverpineforest",
                                                       "alteracmountains", "hillsbradfoothills", "thehinterlands", "wetlands", "lochmodan",
                                                       "dunmorogh", "badlands", "burningsteppes", "redridgemountains", "elwynnforest",
                                                       "swampofsorrows", "westfall", "stranglethornvale",
                                                       # diablocraft-hyoic.10 (acts A7): act 5 on the Outland copy 753
                                                       "hellfirepeninsula", "zangarmarsh", "nagrand", "terokkarforest",
                                                       "shadowmoonvalley", "netherstorm", "bladesedgemountains"])
        migration = HERE.parent / "data/sql/db-world/updates" / R.OPEN_ZONE_TABLE_MIGRATION
        self.assertEqual(migration.read_text(encoding="utf-8"), R.open_zone_table_sql(R.read_open_zone_rows()))
        copy_of = {source_id: map_id for map_id, source_id, _ in (gen.map_row(layer[0]) for layer in gen.LAYERS)}   # hyoic.8: a copy a continent
        raw = AREA_DBC.read_bytes()
        count, fields, size, strings = struct.unpack_from("<4I", raw, 4)
        block = 20 + count * size
        area = {}
        for n in range(count):
            record = struct.unpack_from(f"<{fields}I", raw, 20 + n * size)
            name = raw[block + record[11]:raw.index(b"\0", block + record[11])].decode()
            area[record[0]] = (record[1], record[2], name)
        for zone in zones:
            self.assertEqual(int(zone["map_id"]), copy_of[int(zone["source_map"])])
            self.assertEqual(area[int(zone["zone_id"])], (int(zone["source_map"]), 0, zone["name"]), zone["key"])
        # The designer's .gps of 2026-10-11 gave the other four their entrances: every zone is on, with all four rows set
        rows = entry_rows()
        for zone in zones:
            self.assertTrue(all(rows[f"{zone['entry_tunable']}_{a}"]["value"].strip() for a in "xyzo"), zone["key"])
        self.assertEqual([z["name"] for z in R.read_open_zones()], [z["name"] for z in zones])
        # diablocraft-hyoic.4: the table the loader reads the act from carries it (the loader: problems())
        self.assertIn("`act` TINYINT UNSIGNED NOT NULL", migration.read_text(encoding="utf-8"))

    def test_the_copy_zone_is_the_floor_then_the_command_then_the_first(self):
        """ZoneOf(), cut out and driven: a rift floor's zone wins over what the player asked for; then the command's; then the first."""
        text = CPP.read_text(encoding="utf-8")
        body = (text[text.index("struct OpenZone"):text.index("        // The entrance:")]
                + text[text.index("        std::mutex mutex;"):text.index("        // The one bounce")])
        code = (
            HARNESS_HEAD
            + "using uint32 = unsigned; using uint64 = unsigned long long;\nstruct WorldLocation {};\n"
            "struct Rift { uint32 dungeonId = 0; };\nstruct Dungeon { std::string name; };\n"
            "std::mutex riftMutex;\nstd::map<uint32, uint32> floors;   // instance -> dungeon id\n"
            "std::map<uint32, std::string> pool;\n"
            "struct Live { bool View(uint32 instance, uint32 map, Rift& out) { if (map != 751) return false; auto f = floors.find(instance);"
            " if (f == floors.end()) return false; out.dungeonId = f->second; return true; } } live;\n"
            "bool ArrivalOf(uint32 id, Dungeon& out) { auto f = pool.find(id); if (f == pool.end()) return false; out.name = f->second; return true; }\n"
            "struct Guid { uint64 raw; uint64 GetRawValue() const { return raw; } };\n"
            "struct Player { uint32 instance; Guid guid; uint32 map = 751; uint32 GetInstanceId() const { return instance; } Guid GetGUID() const { return guid; }\n"
            "  uint32 GetMapId() const { return map; } };\n"
            "namespace {\n" + body + "}\n"
            "int main() {\n"
            "  Player p{7, {1}};\n  assert(!ZoneOf(&p));   // no zones loaded: none\n"
            "  zones = {{\"hinterlands\", \"The Hinterlands\", \"open_rift_entry_hinterlands\", 47, 3, 752},"
            " {\"ungoro\", \"Un'Goro Crater\", \"open_rift_entry\", 490, 2, 751}, {\"tanaris\", \"Tanaris\", \"open_rift_entry_tanaris\", 440, 2, 751},"
            " {\"azshara\", \"Azshara\", \"open_rift_entry_azshara\", 16, 1, 751}};\n"
            "  assert(ZoneOf(&p)->key == \"ungoro\");   // nothing known: the sheet's first\n"
            "  asked[1] = \"azshara\"; assert(ZoneOf(&p)->key == \"azshara\");   // the command's zone\n"
            "  pool[1002] = \"Tanaris\"; floors[7] = 1002; assert(ZoneOf(&p)->key == \"tanaris\");   // a floor's zone beats the command's\n"
            "  pool[1002] = \"Ragefire Chasm\"; assert(ZoneOf(&p)->key == \"ungoro\");   // a floor of no open zone: the first, not the command's\n"
            "  floors.clear(); Player q{7, {2}}; assert(ZoneOf(&q)->key == \"ungoro\");   // another player's ask is not this one's\n"
            "  Player east{7, {1}, 752}; assert(ZoneOf(&east)->key == \"hinterlands\");   // on 752: that map's zones only, the ask on 751 is not there\n"
            "  Player outland{7, {1}, 530}; assert(!ZoneOf(&outland));   // a map with no zone: none\n"
            "  return 0;\n}\n")
        with tempfile.TemporaryDirectory(prefix="dc-open-rift-zone-") as directory:
            run = runner(self, directory)
            self.assertEqual(run(code), 0)
            for old, new in (("if (inRift && ArrivalOf(rift.dungeonId, dungeon))", "if (false)"),
                             ("name.empty() ? zone.key == key : zone.name == name", "zone.key == key"),
                             ("name.empty() ? zone.key == key : zone.name == name", "name.empty() ? false : zone.name == name"),
                             ("            return first;\n        }", "            return nullptr;\n        }"),
                             ("                if (zone.mapId == mapId)\n                {\n                    first", "                if (true)\n                {\n                    first"),
                             ("if (zone.mapId == mapId && (name.empty()", "if (true && (name.empty()")):
                with self.subTest(mutation=old):
                    self.assertEqual(code.count(old), 1, f"{old!r} is not unique")
                    self.assertNotEqual(run(code.replace(old, new)), 0, f"ZoneOf passed with {old!r} replaced")

    def test_the_fog_masks_are_the_open_zones_areas(self):
        """dc_zone_fog.h compiled as it is: Masks() over every AreaTable row and the sheet's zones is the explore bits of
        exactly the areas in those zones."""
        with ZONES_CSV.open(encoding="utf-8-sig", newline="") as handle:
            zone_rows = list(csv.DictReader(handle))
        zone_ids = [int(z["zone_id"]) for z in zone_rows]
        source = {int(z["zone_id"]): int(z["source_map"]) for z in zone_rows}   # hyoic.8: Kalimdor (1) or the Eastern Kingdoms (0)
        raw = AREA_DBC.read_bytes()
        count, fields, size, _ = struct.unpack_from("<4I", raw, 4)
        areas = [struct.unpack_from("<4I", raw, 20 + n * size) for n in range(count)]   # ID, map, zone, exploreFlag
        expected = {}
        inside = [a for a in areas if a[0] in zone_ids or a[2] in zone_ids]
        for area in inside:
            expected[area[3] // 32] = expected.get(area[3] // 32, 0) | 1 << (area[3] % 32)
        self.assertGreater(len(inside), 5 * 3, "the zones' sub-areas are missing")
        self.assertTrue(all(a[1] == source[a[0] if a[0] in source else a[2]] for a in inside),
                        "an area of the open zones is not on its zone's source continent")
        hyjal = [a for a in areas if 616 in (a[0], a[2])]   # a zone off the sheet (Hyjal, cut 2026-10-13): its bits stay
        self.assertTrue(hyjal and all(not expected.get(a[3] // 32, 0) & 1 << (a[3] % 32) for a in hyjal))
        rows = ",".join("{%d,%d,%d}" % (a[0], a[2], a[3]) for a in areas)
        code = (
            "#include \"dc_zone_fog.h\"\n#include <cassert>\n#include <cstdio>\nusing namespace DC::Rifts::ZoneFog;\n"
            "int main() {\n"
            "  std::vector<Area> areas = {" + rows + "};\n"
            "  for (auto const& [word, bits] : Masks(areas, {" + ",".join(map(str, zone_ids)) + "}, 128))\n"
            "    std::printf(\"%u %u\\n\", word, bits);\n"
            "  assert(Masks({{1, 0, 4096}, {2, 1, 31}}, {1}, 128) == (std::map<std::uint32_t, std::uint32_t>{{0, 1u << 31}}));   // past the last word: dropped\n"
            "  return 0;\n}\n")
        header = (SRC / "dc_zone_fog.h").read_text(encoding="utf-8")
        compiler = shutil.which("g++") or shutil.which("c++")
        self.assertTrue(compiler, "g++ is not on PATH")
        with tempfile.TemporaryDirectory(prefix="dc-zone-fog-") as directory:
            source, binary, copy = Path(directory) / "t.cpp", Path(directory) / "t", Path(directory) / "dc_zone_fog.h"
            source.write_text(code, encoding="utf-8")

            def run(text):
                copy.write_text(text, encoding="utf-8")
                built = subprocess.run([compiler, "-std=c++20", "-UNDEBUG", "-I", directory, "-o", str(binary), str(source)],
                                       capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stderr[-2000:])
                ran = harness_env.run([str(binary)], capture_output=True, text=True)
                return ran.returncode == 0 and {int(w): int(b) for w, b in (l.split() for l in ran.stdout.split("\n") if l)} == expected

            self.assertTrue(run(header))
            for old, new in (("area.id == zone || area.zone == zone", "area.zone == zone"),
                             ("area.id == zone || area.zone == zone", "area.id == zone"),
                             ("&& area.exploreFlag / 32 < words", ""),
                             ("1u << (area.exploreFlag % 32)", "1u << (area.exploreFlag % 31)")):
                with self.subTest(mutation=old):
                    self.assertEqual(header.count(old), 1, f"{old!r} is not unique")
                    self.assertFalse(run(header.replace(old, new)), f"the fog rules passed with {old!r} replaced")

    def test_light_driven(self):
        """Light(), cut out of dc_open_rift.cpp and driven against a player double: an arrival sets every bit of the open
        zones' areas, keeps the bits of other zones, and sets the same bits again on a return or another copy."""
        text = CPP.read_text(encoding="utf-8")
        body = text[text.index("        std::map<uint32, uint32> fogMasks;"):text.index("        class Boundary")]
        code = (
            "#include <cassert>\n#include <map>\n#include \"dc_zone_fog.h\"\n"
            "using uint16 = unsigned short; using uint32 = unsigned;\n"
            "enum { PLAYER_EXPLORED_ZONES_1 = 1000 };\nconstexpr uint32 PLAYER_EXPLORED_ZONES_SIZE = 128;\n"
            "struct Player { std::map<uint16, uint32> f; void SetFlag(uint16 i, uint32 v) { f[i] |= v; }"
            " void RemoveFlag(uint16 i, uint32 v) { f[i] &= ~v; } uint32 W(uint32 w) { return f[PLAYER_EXPLORED_ZONES_1 + w]; } };\n"
            "namespace DC::Rifts::OpenRift {\nnamespace {\n" + body + "}\n}\nusing namespace DC::Rifts::OpenRift;\n"
            "int main() {\n"
            "  fogMasks = DC::Rifts::ZoneFog::Masks({{10, 0, 3}, {11, 10, 40}, {20, 0, 5}}, {10}, PLAYER_EXPLORED_ZONES_SIZE);\n"
            "  Player p;\n  p.SetFlag(PLAYER_EXPLORED_ZONES_1, 1u << 5);\n"
            "  Light(&p); assert(p.W(0) == (1u << 3 | 1u << 5) && p.W(1) == 1u << 8);   // the zone's bits come on, another zone's stays\n"
            "  auto lit = p.f; Light(&p); assert(p.f == lit);                           // a return, or another copy: the same\n"
            "  Player q; Light(&q); assert(q.W(0) == 1u << 3 && q.W(1) == 1u << 8);      // a fresh character gets them all\n"
            "  return 0;\n}\n")
        compiler = shutil.which("g++") or shutil.which("c++")
        self.assertTrue(compiler, "g++ is not on PATH")
        with tempfile.TemporaryDirectory(prefix="dc-zone-fog-glue-") as directory:
            source, binary = Path(directory) / "t.cpp", Path(directory) / "t"

            def run(src):
                source.write_text(src, encoding="utf-8")
                built = subprocess.run([compiler, "-std=c++20", "-UNDEBUG", "-I", str(SRC), "-o", str(binary), str(source)],
                                       capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stderr[-2000:])
                return harness_env.run([str(binary)]).returncode

            self.assertEqual(run(code), 0)
            for old, new in (("player->SetFlag(PLAYER_EXPLORED_ZONES_1 + word, bits);", "player->RemoveFlag(PLAYER_EXPLORED_ZONES_1 + word, bits);"),
                             ("player->SetFlag(PLAYER_EXPLORED_ZONES_1 + word, bits);", "player->SetFlag(PLAYER_EXPLORED_ZONES_1 + word, bits & 1u);"),
                             ("for (auto const& [word, bits] : fogMasks)", "for (auto const& [word, bits] : std::map<uint32, uint32>{})")):
                with self.subTest(mutation=old):
                    self.assertEqual(code.count(old), 1, f"{old!r} is not unique")
                    self.assertNotEqual(run(code.replace(old, new)), 0, f"the fog glue passed with {old!r} replaced")

    def test_a_bounty_traveller_walks_the_open_zones_and_a_rift_floor_keeps_its_one(self):
        """Holds(), cut out with ZoneOf and driven (diablocraft-dm9vg.11): a traveller (the zone asked for is known) crosses
        between the open zones of the asked zone's act (diablocraft-hyoic.4, the act edge) and bounces at another act's and at
        an unsurveyed one; a rift floor's player bounces at any other zone; a player in the copy with no zone asked for keeps
        the one zone."""
        text = CPP.read_text(encoding="utf-8")
        start = text.index("        // The zone edge: true when")
        self.assertLess(text.index("        std::mutex mutex;"), start)
        self.assertLess(start, text.index("        // The one bounce"))
        body = (text[text.index("struct OpenZone"):text.index("        // The entrance:")]
                + text[text.index("        std::mutex mutex;"):text.index("        // The one bounce")])
        code = (
            HARNESS_HEAD
            + "using uint32 = unsigned; using uint64 = unsigned long long;\nstruct WorldLocation {};\n"
            "struct Rift { uint32 dungeonId = 0; };\nstruct Dungeon { std::string name; };\n"
            "std::mutex riftMutex;\nstd::map<uint32, uint32> floors;\nstd::map<uint32, std::string> pool;\n"
            "struct Live { bool View(uint32 instance, uint32 map, Rift& out) { if (map != 751) return false; auto f = floors.find(instance);"
            " if (f == floors.end()) return false; out.dungeonId = f->second; return true; } } live;\n"
            "bool ArrivalOf(uint32 id, Dungeon& out) { auto f = pool.find(id); if (f == pool.end()) return false; out.name = f->second; return true; }\n"
            "struct Guid { uint64 raw; uint64 GetRawValue() const { return raw; } };\n"
            "struct Player { uint32 instance; Guid guid; uint32 map = 751; uint32 GetInstanceId() const { return instance; } Guid GetGUID() const { return guid; }\n"
            "  uint32 GetMapId() const { return map; } };\n"
            "namespace {\n" + body + "}\n"
            "int main() {\n"
            "  Player none{7, {9}}; assert(Holds(&none, 1234));   // no zones loaded: no wall to hold\n"
            "  zones = {{\"ungoro\", \"Un'Goro Crater\", \"open_rift_entry\", 490, 2, 751}, {\"tanaris\", \"Tanaris\", \"open_rift_entry_tanaris\", 440, 2, 751},"
            " {\"azshara\", \"Azshara\", \"open_rift_entry_azshara\", 16, 1, 751}, {\"moonglade\", \"Moonglade\", \"open_rift_entry_moonglade\", 493, 1, 751},"
            " {\"hinterlands\", \"The Hinterlands\", \"open_rift_entry_hinterlands\", 47, 3, 752}};\n"
            "  const uint32 feralas = 357;   // a Kalimdor zone the sheet does not hold: unsurveyed\n"
            "  Player trav{8, {1}}; asked[1] = \"ungoro\";\n"
            "  assert(Holds(&trav, 490) && Holds(&trav, 440));   // a traveller walks between the open zones of the act (act 2)\n"
            "  assert(!Holds(&trav, 16) && !Holds(&trav, 493));   // and bounces at the act edge (Azshara, Moonglade: act 1)\n"
            "  assert(!Holds(&trav, feralas));   // and at an unsurveyed one\n"
            "  Player north{8, {4}}; asked[4] = \"azshara\";\n"
            "  assert(Holds(&north, 16) && Holds(&north, 493) && !Holds(&north, 490) && !Holds(&north, 440));   // act 1's own\n"
            "  Player rift{7, {2}}; asked[2] = \"tanaris\"; pool[1002] = \"Tanaris\"; floors[7] = 1002;\n"
            "  assert(Holds(&rift, 440) && !Holds(&rift, 490) && !Holds(&rift, 16) && !Holds(&rift, feralas));   // a rift floor: its one zone\n"
            "  Player plain{8, {3}};\n"
            "  assert(Holds(&plain, 490) && !Holds(&plain, 440));   // no zone asked for: the one zone (the sheet's first)\n"
            "  Player east{8, {5}, 752}; asked[5] = \"ungoro\";\n"
            "  assert(Holds(&east, 47) && !Holds(&east, 490));   // on 752 the act is 752's zone's, not the asked 751 zone's\n"
            "  return 0;\n}\n")
        with tempfile.TemporaryDirectory(prefix="dc-open-rift-wall-") as directory:
            run = runner(self, directory)
            self.assertEqual(run(code), 0)
            for old, new in (("if (inRift || !travelled)", "if (!travelled)"),
                             ("if (inRift || !travelled)", "if (inRift)"),
                             ("                if (zone.zoneId == newZone && zone.act == own->act)\n                    return true;\n            return false;",
                              "                return true;\n            return false;"),
                             ("                if (zone.zoneId == newZone && zone.act == own->act)\n                    return true;\n            return false;",
                              "                if (zone.zoneId == newZone && zone.act == own->act)\n                    return true;\n            return true;"),
                             ("if (zone.zoneId == newZone && zone.act == own->act)", "if (zone.zoneId == newZone)"),
                             ("return newZone == own->zoneId;", "return true;"),
                             ("travelled = asked.count(player->GetGUID().GetRawValue()) != 0;", "travelled = !asked.empty();")):
                with self.subTest(mutation=old):
                    self.assertEqual(code.count(old), 1, f"{old!r} is not unique")
                    self.assertNotEqual(run(code.replace(old, new)), 0, f"Holds passed with {old!r} replaced")

    def test_the_header_and_the_include_exist(self):
        self.assertTrue((SRC / "dc_open_rift.h").is_file())
        self.assertIn('#include "dc_open_rift.h"', (SRC / "dc_rifts.cpp").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
