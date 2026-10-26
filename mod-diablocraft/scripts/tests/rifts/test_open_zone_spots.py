#!/usr/bin/env python3
"""diablocraft-dm9vg.16: every open-zone anchor, bounty spot and entrance lies in its zone by the server's own lookup.

A spot outside its zone can never be reached: the zone wall (dc_open_rift.cpp, OnPlayerUpdateZone) bounces the player to
the entrance the moment the core's zone id under them is not the zone's. The designer's playtest 2026-10-12: Moonglade bounty 501
spot 1 (the Timbermaw passage) bounced him, though the survey had read it as Moonglade. The survey reads the terrain's
16 x 16 area grid only; the core asks the WMO under the point first (Map::GetAreaId), and the passage is a WMO whose area
is Timbermaw Hold, a Felwood area.

So the lookup here is the core's own code, cut out of its files and compiled: Map::GetAreaInfo, Map::GetAreaId and
Map::GetZoneId (Map.cpp), StaticVMapCollisionData::GetAreaAndLiquidData (MapCollisionData.cpp), GridTerrainData's loader,
area and heights (GridTerrainData.cpp), linked against the core's collision library (libcommon.a: StaticMapTree,
WorldModelStore). It reads the server's data (build/server/data: vmaps, maps, dbc) for map 1, whose static tree and terrain
map 751 shares as its parent (MapCollisionData.cpp:37); the Eastern Kingdoms zones read map 0 the same way under 752 and Outland's map 530 under 753. Not modelled: the dynamic tree (gameobjects; a door or a
transport with its own WMO area) and the disables table (a vmap area flag disabled for the map); neither is set for map 1
or 751 in the module's data.

    python3 mod-diablocraft/scripts/tests/rifts/test_open_zone_spots.py            the test
    python3 mod-diablocraft/scripts/tests/rifts/test_open_zone_spots.py --report   every point with the zone and area the core gives
"""
from __future__ import annotations

import csv
import re
import struct
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
AC = ROOT / "azerothcore-wotlk"
BUILD = AC / "build"
DATA = BUILD / "server/data"
SCRATCH = BUILD / "_agent-scratch/open-zone-spots"
D3 = MODULE / "data/d3"
SOURCE_MAP = 1  # rift_open_zones.csv source_map: map 751 reads map 1's vmaps and terrain

HARNESS = r'''
#include "Optional.h"
#include <array>
#include "GridTerrainData.h"
#include "Log.h"
#include "MapTree.h"
#include "ModelInstance.h"
#include "VMapMgr2.h"
#include "WorldModel.h"
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <tuple>
#include <G3D/Ray.h>
#include <G3D/g3dmath.h>

// --- what the cut code names from headers this harness does not include
float const GROUND_HEIGHT_TOLERANCE = @TOLERANCE@; // SharedDefines.h
constexpr float SIZE_OF_GRIDS = 533.3333f, CENTER_GRID_OFFSET = SIZE_OF_GRIDS / 2; // GridDefines.h
constexpr int MAX_NUMBER_OF_GRIDS = 64, CENTER_GRID_ID = MAX_NUMBER_OF_GRIDS / 2;
@GRID_DEFINES@
namespace DisableMgr { inline bool IsVMAPDisabledFor(uint32, uint8) { return false; } }
inline uint32 GetLiquidFlags(uint32) { return 0; }

// --- the DBC rows the lookup reads
struct WMOAreaTableEntry { uint32 areaId; };
struct AreaTableEntry { uint32 ID; uint32 zone; };
struct MapEntry { uint32 linked_zone; };
std::map<std::tuple<int16, int8, int32>, WMOAreaTableEntry> wmoAreas;
WMOAreaTableEntry const* GetWMOAreaTableEntryByTripple(int32 rootid, int32 adtid, int32 groupid)
{
    auto i = wmoAreas.find({int16(rootid), int8(adtid), groupid});
    return i == wmoAreas.end() ? nullptr : &i->second;
}
struct { std::map<uint32, AreaTableEntry> rows; AreaTableEntry const* LookupEntry(uint32 id) const
    { auto i = rows.find(id); return i == rows.end() ? nullptr : &i->second; } } sAreaTableStore;

// --- GridTerrainData.cpp, cut (its loader, area and heights)
@GRID@

// --- MapCollisionData.cpp's static tree read, on a stand-in holder
class StaticVMapCollisionData
{
public:
    bool GetAreaAndLiquidData(float x, float y, float z, Optional<uint8> reqLiquidType, VMAP::AreaAndLiquidData& data) const;
    std::shared_ptr<VMAP::StaticMapTree> _staticTree;
    uint32 _mapId = 0;
};
@STATIC@
struct DynamicStandIn
{
    bool GetAreaAndLiquidData(float, float, float, uint32, Optional<uint8>, VMAP::AreaAndLiquidData&) const { return false; }
};
struct CollisionStandIn
{
    StaticVMapCollisionData staticData; DynamicStandIn dynamicData;
    StaticVMapCollisionData const& GetStaticTree() const { return staticData; }
    DynamicStandIn const& GetDynamicTree() const { return dynamicData; }
};

// --- Map.cpp's lookup, on a stand-in Map
class Map
{
public:
    bool GetAreaInfo(uint32 phaseMask, float x, float y, float z, uint32& flags, int32& adtId, int32& rootId, int32& groupId) const;
    uint32 GetAreaId(uint32 phaseMask, float x, float y, float z) const;
    uint32 GetZoneId(uint32 phaseMask, float x, float y, float z) const;
    GridTerrainData* GetGridTerrainData(float x, float y);
    CollisionStandIn _mapCollisionData;
    MapEntry entry{}; MapEntry const* i_mapEntry = &entry;
    std::string mapsDir; uint32 mapId = 0;
    std::map<std::pair<int, int>, std::unique_ptr<GridTerrainData>> grids;
    std::set<std::pair<int, int>> vmapTiles;
    void LoadAround(float x, float y);
};
@MAP@

GridTerrainData* Map::GetGridTerrainData(float x, float y)
{
    int const gx = int(32 - x / SIZE_OF_GRIDS), gy = int(32 - y / SIZE_OF_GRIDS);
    auto& slot = grids[{gx, gy}];
    if (!slot)
    {
        char name[32];
        std::snprintf(name, sizeof(name), "%03u%02u%02u.map", mapId, gx, gy);
        auto grid = std::make_unique<GridTerrainData>();
        if (grid->Load(mapsDir + "/" + name) == TerrainMapDataReadResult::Success)
            slot = std::move(grid);
    }
    return slot.get();
}

// The server loads the vmap tile of every active grid; a point is checked with its grid and the eight around it.
void Map::LoadAround(float x, float y)
{
    int const gx = int(32 - x / SIZE_OF_GRIDS), gy = int(32 - y / SIZE_OF_GRIDS);
    for (int dx = -1; dx <= 1; ++dx)
        for (int dy = -1; dy <= 1; ++dy)
            if (vmapTiles.insert({gx + dx, gy + dy}).second)
                _mapCollisionData.staticData._staticTree->LoadMapTile(gx + dx, gy + dy);
}

static std::vector<std::vector<uint32>> ReadDbc(std::string const& path)
{
    std::ifstream in(path, std::ios::binary);
    char magic[4]; uint32 count, fields, size, strings;
    in.read(magic, 4); in.read((char*)&count, 4); in.read((char*)&fields, 4); in.read((char*)&size, 4); in.read((char*)&strings, 4);
    std::vector<std::vector<uint32>> rows(count, std::vector<uint32>(size / 4));
    for (auto& row : rows)
        in.read((char*)row.data(), size);
    return rows;
}

int main(int argc, char** argv)
{
    // argv: data dir, map id; stdin: "x y z" per line; stdout: "zone area wmo" per line
    std::string const data = argv[1];
    Map map; map.mapId = std::stoul(argv[2]); map.mapsDir = data + "/maps";
    for (auto const& r : ReadDbc(data + "/dbc/AreaTable.dbc")) sAreaTableStore.rows[r[0]] = {r[0], r[2]};
    for (auto const& r : ReadDbc(data + "/dbc/WMOAreaTable.dbc")) wmoAreas[{int16(r[1]), int8(r[2]), int32(r[3])}] = {r[10]};
    for (auto const& r : ReadDbc(data + "/dbc/Map.dbc")) if (r[0] == map.mapId) map.entry.linked_zone = r[22];
    auto tree = std::make_shared<VMAP::StaticMapTree>(map.mapId, data + "/vmaps/");
    if (!tree->InitMap(VMAP::VMapMgr2::getMapFileName(map.mapId))) { std::cerr << "no vmap tree\n"; return 2; }
    map._mapCollisionData.staticData._staticTree = tree;
    map._mapCollisionData.staticData._mapId = map.mapId;
    float x, y, z;
    while (std::cin >> x >> y >> z)
    {
        map.LoadAround(x, y);
        uint32 flags; int32 adt, root, group;
        bool const wmo = map.GetAreaInfo(1, x, y, z, flags, adt, root, group);
        std::cout << map.GetZoneId(1, x, y, z) << " " << map.GetAreaId(1, x, y, z) << " " << wmo << "\n";
    }
}
'''


def extract(text, signature):
    start = text.index(signature)
    opening = text.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def harness_source(map_cpp=None, grid_cpp=None, collision_cpp=None):
    game = AC / "src/server/game"
    map_cpp = map_cpp if map_cpp is not None else (game / "Maps/Map.cpp").read_text(encoding="utf-8")
    grid_cpp = grid_cpp if grid_cpp is not None else (game / "Grids/GridTerrainData.cpp").read_text(encoding="utf-8")
    collision_cpp = collision_cpp if collision_cpp is not None else (game / "Maps/MapCollisionData.cpp").read_text(encoding="utf-8")
    shared = (AC / "src/server/shared/SharedDefines.h").read_text(encoding="utf-8")
    tolerance = re.search(r"float const GROUND_HEIGHT_TOLERANCE = ([0-9.]+f);", shared).group(1)
    grid_defines = (game / "Grids/GridDefines.h").read_text(encoding="utf-8")
    defines = "\n".join(re.findall(r"^#define (?:MAP_RESOLUTION|MAP_HALFSIZE|MAP_SIZE) .*$", grid_defines, re.M))
    grid = grid_cpp[grid_cpp.index("uint16 const holetab_h"):grid_cpp.index("float GridTerrainData::getMinHeight")]
    lookup = "\n".join(extract(map_cpp, s) for s in ("bool Map::GetAreaInfo(", "uint32 Map::GetAreaId(", "uint32 Map::GetZoneId("))
    return (HARNESS.replace("@TOLERANCE@", tolerance).replace("@GRID_DEFINES@", defines).replace("@GRID@", grid)
            .replace("@STATIC@", extract(collision_cpp, "bool StaticVMapCollisionData::GetAreaAndLiquidData("))
            .replace("@MAP@", lookup))


def include_flags():
    """The core's include path and defines for its collision code, from the build's compile commands."""
    import json
    for entry in json.loads((BUILD / "compile_commands.json").read_text(encoding="utf-8")):
        if entry["file"].endswith("Collision/Maps/MapTree.cpp"):
            words = (entry.get("command") or " ".join(entry["arguments"])).split()
            flags = [w for w in words if w.startswith(("-I", "-D", "-std="))]
            break
    game = AC / "src/server/game"
    return flags + [f"-I{game / 'Grids'}", f"-I{AC / 'src/server/shared/DataStores'}", f"-I{AC / 'src/server/shared'}"]


def build(name="lookup", source=None):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cpp, binary = SCRATCH / f"{name}.cpp", SCRATCH / name
    cpp.write_text(harness_source() if source is None else source, encoding="utf-8")
    libs = [BUILD / "src/common/libcommon.a", BUILD / "deps/g3dlite/libg3dlib.a", BUILD / "deps/fmt/libfmt.a"]
    built = subprocess.run(["g++", "-O1", "-w", *include_flags(), str(cpp), "-o", str(binary), *map(str, libs),
                            "-lz", "-lpthread", "-lboost_filesystem", "-lboost_system"], capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the zone lookup did not compile:\n" + built.stderr[-5000:])
    return binary


def lookup(binary, points, source_map=SOURCE_MAP):
    """The core's (zone, area, wmo) at each (x, y, z) on the source map."""
    text = "".join(f"{x} {y} {z}\n" for x, y, z in points)
    ran = harness_env.run([str(binary), str(DATA), str(source_map)], input=text, capture_output=True, text=True, check=True)
    return [tuple(int(v) for v in line.split()) for line in ran.stdout.splitlines()]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def points():
    """Every point a player is sent to in an open zone: (zone key, zone id, label, x, y, z)."""
    zones = read(D3 / "rift_open_zones.csv")
    by_name = {z["name"]: z for z in zones}
    out = []
    anchors = {}
    for a in read(D3 / "rift_anchors.csv"):
        zone = by_name.get(a["dungeon"])
        if zone:
            anchors[(zone["key"], a["anchor"])] = a
            out.append((zone["key"], int(zone["zone_id"]), f"anchor {a['anchor']} (area {a['area']})",
                        float(a["x"]), float(a["y"]), float(a["z"])))
    for b in read(D3 / "bounties.csv"):
        zone = next(z for z in zones if z["key"] == b["zone"])
        if b["spot"]:  # diablocraft-dm9vg.18: a made Unique stands on a spot of its own, x;y;z;o
            x, y, z, _ = (float(v) for v in b["spot"].split(";"))
            out.append((b["zone"], int(zone["zone_id"]), f"bounty {b['column']}{int(b['index']):02d} own spot", x, y, z))
            continue
        for spot, anchor in enumerate(b["anchors"].split(";"), 1):
            a = anchors[(b["zone"], anchor)]
            out.append((b["zone"], int(zone["zone_id"]), f"bounty {b['column']}{int(b['index']):02d} spot {spot} (anchor {anchor})",
                        float(a["x"]), float(a["y"]), float(a["z"])))
    tunables = {r["name"]: r["value"] for r in read(MODULE / "data/tunables/rifts.csv")}
    for zone in zones:
        stem = zone["entry_tunable"]
        if all(tunables.get(f"{stem}_{c}") for c in "xyz"):
            out.append((zone["key"], int(zone["zone_id"]), "entrance",
                        *(float(tunables[f"{stem}_{c}"]) for c in "xyz")))
    return out


def lookup_found(binary, found):
    """lookup() over points() in order, each point on its own zone's source map (hyoic.8, hyoic.10: 0 for the Eastern Kingdoms zones, 1 for Kalimdor's, 530 for Outland's)."""
    source = {z["key"]: int(z["source_map"]) for z in read(D3 / "rift_open_zones.csv")}
    got = [None] * len(found)
    for map_id in sorted(set(source.values())):
        index = [n for n, p in enumerate(found) if source[p[0]] == map_id]
        for n, answer in zip(index, lookup(binary, [found[n][3:] for n in index], map_id)):
            got[n] = answer
    return got


class OpenZoneSpots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all((DATA / f"vmaps/{m:03d}.vmtree").exists() for m in (0, 1, 530)):
            raise unittest.SkipTest(f"no server data at {DATA}")
        cls.binary = build()

    def test_the_lookup_is_the_cores_own(self):
        source = harness_source()
        for piece in ("bool Map::GetAreaInfo(", "uint32 Map::GetAreaId(", "uint32 Map::GetZoneId(",
                      "bool StaticVMapCollisionData::GetAreaAndLiquidData(", "TerrainMapDataReadResult GridTerrainData::Load(",
                      "uint16 GridTerrainData::getArea("):
            self.assertIn(piece, source)

    def test_the_timbermaw_passage_is_felwood_by_its_wmo(self):
        # The designer's bounce (2026-10-12): 7262.70 -2180.89 557.20 is under the Timbermaw Hold WMO, whose area is Felwood's.
        (zone, area, wmo), = lookup(self.binary, [(7262.70, -2180.89, 557.20)])
        self.assertEqual((zone, wmo), (361, 1))

    def test_without_the_wmo_step_the_passage_reads_moonglade(self):
        # The survey's reading (terrain grid only): the core's GetAreaId with its WMO branch cut out.
        game = AC / "src/server/game"
        map_cpp = (game / "Maps/Map.cpp").read_text(encoding="utf-8")
        branch = "    if (hasVmapArea && G3D::fuzzyGe("
        self.assertEqual(map_cpp.count(branch), 1)
        grid_only = build("grid-only", harness_source(map_cpp=map_cpp.replace(branch, "    if (false && G3D::fuzzyGe(")))
        (zone, area, _), = lookup(grid_only, [(7262.70, -2180.89, 557.20)])
        self.assertEqual(zone, 493)

    def test_every_point_is_in_its_zone(self):
        found = points()
        got = lookup_found(self.binary, found)
        misses = [f"{key} {label} ({x:.1f} {y:.1f} {z:.1f}): zone {zone} area {area}, wants {want}"
                  for (key, want, label, x, y, z), (zone, area, _) in zip(found, got) if zone != want]
        self.assertEqual(misses, [])


def report():
    binary = build()
    found = points()
    for (key, want, label, x, y, z), (zone, area, wmo) in zip(found, lookup_found(binary, found)):
        if zone != want or "--all" in sys.argv:
            print(f"{'MISS' if zone != want else 'ok  '} {key} {label} {x:.2f} {y:.2f} {z:.2f} zone {zone} area {area} "
                  f"{'wmo' if wmo else 'terrain'} (wants {want})")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        unittest.main()
