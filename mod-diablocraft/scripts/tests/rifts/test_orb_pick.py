"""diablocraft-xwwg9: the stock orb pick round (`.dc orbrow`).

The harness compiles the real dc_orb_pick.h and checks the row: in front of the GM, the first candidate on the GM's
left, evenly spaced, whichever way the GM faces; each rule is mutated and the mutant must fail. The candidate list is
checked against its sources: tier 1 against the stock GameObjectDisplayInfo.dbc the server reads, tier 2 against
world_object_displays.csv (the Torment rows the Nightly patch carries); the template against world_objects.csv. The
command's glue is pinned by text (each copy wears its display and scale before it is added to the map, goes after 10
minutes, a second command removes the row). The client has no handler for a gameobject's display changing after the
create packet (reference/wowdecomp CGGameObject_C registers state, flags, art kit, path progress and dynamic flags,
not the display), so a copy given its display after AddToMap draws the template's look; the order is the test.
"""
import csv
import re
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_class_parity import MODULE, ROOT, SRC, mutate  # noqa: E402
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

HEADER = (SRC / "rifts/dc_orb_pick.h").read_text(encoding="utf-8")
GLUE = (SRC / "rifts/dc_orb_pick.cpp").read_text(encoding="utf-8")
LOADER = (SRC / "mod_diablocraft_loader.cpp").read_text(encoding="utf-8")
STOCK_DISPLAYS = ROOT / "azerothcore-wotlk/build/server/data/dbc/GameObjectDisplayInfo.dbc"


def sheet(name):
    with (MODULE / "data/d3" / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def candidates():
    return [(int(d), float(s), float(lift), label, flag == "true") for d, s, lift, label, flag in
            re.findall(r'\{(\d+), ([\d.]+)f, (-?[\d.]+)f, "([^"]+)", (true|false)\}', HEADER)]


def harness(body, header=HEADER):
    return run("#include <cassert>\n#include <cstddef>\n" + header + "\nusing namespace DC::OrbPick;\nint main() {\n" + body
               + "\n    return 0;\n}\n")


def both(test, body, old, new):
    ok, out = harness(body)
    test.assertTrue(ok, out)
    ok, out = harness(body, mutate(HEADER, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


ROW = r'''
    auto near = [](float a, float b) { return std::fabs(a - b) < 1e-3f; };
    for (float o : {0.0f, 1.5707963f, 2.5f, -2.0f}) {
        float fx = std::cos(o), fy = std::sin(o), lx = -std::sin(o), ly = std::cos(o);  // forward, the GM's left
        std::size_t const n = Candidates.size();
        for (std::size_t i = 0; i < n; ++i) {
            Spot s = Place(10, 20, o, i, n);
            float ahead = (s.x - 10) * fx + (s.y - 20) * fy, left = (s.x - 10) * lx + (s.y - 20) * ly;
            assert(near(ahead, AheadYards));
            assert(near(left, (float(n - 1) / 2 - float(i)) * SpacingYards));
        }
        assert(((Place(10, 20, o, 0, n).x - 10) * lx + (Place(10, 20, o, 0, n).y - 20) * ly) > 0);  // first on the left
    }'''


class Row(unittest.TestCase):
    def test_in_front_first_on_the_left_evenly_spaced(self):
        both(self, ROW, "float const across = (float(n - 1) / 2.0f - float(i)) * SpacingYards;",
             "float const across = (float(i) - float(n - 1) / 2.0f) * SpacingYards;")

    def test_ahead_whichever_way_the_gm_faces(self):
        both(self, ROW, "y + AheadYards * std::sin(o)", "y + AheadYards * std::cos(o)")

    def test_spacing(self):
        both(self, ROW, "constexpr float SpacingYards = 3.0f;", "constexpr float SpacingYards = 0.0f;")


class Candidates(unittest.TestCase):
    def test_tier_one_is_the_red_reference_and_the_bare_nexus_orb(self):
        tier1 = [c for c in candidates() if not c[4]]
        self.assertEqual([8365, 7781], [c[0] for c in tier1])
        # 7800 (a base and a neck under the orb) and 7161 (the translocator pedestal) have a stand: out of the row
        for stand in (7800, 7161):
            self.assertNotIn(stand, [c[0] for c in candidates()])
        if not STOCK_DISPLAYS.exists():
            self.skipTest("no stock GameObjectDisplayInfo.dbc on this machine")
        raw = STOCK_DISPLAYS.read_bytes()
        _, count, _, size, _ = struct.unpack_from("<4s4I", raw)
        stock = {struct.unpack_from("<I", raw, 20 + n * size)[0] for n in range(count)}
        for display, *_ in tier1:
            self.assertIn(display, stock)

    def test_tier_two_is_the_sheets_rows_and_needs_the_patch(self):
        tier2 = [c for c in candidates() if c[4]]
        rows = {int(r["display_id"]): r for r in sheet("world_object_displays.csv")}
        self.assertEqual([9701, 9702, 9703, 9704], [c[0] for c in tier2])
        for display, _, _, label, _ in tier2:
            self.assertIn(display, rows)
            self.assertTrue(label.startswith(rows[display]["name"]), (label, rows[display]["name"]))
        self.assertEqual("spells\\firebomb_missle.mdx", rows[9701]["model_path"])   # the only stock orange
        self.assertNotIn("InvisibleStalker", "".join(rows[d]["model_path"] for d, *_ in tier2))
        self.assertEqual(6, len(candidates()))   # the Ethereal Sphere has no stock model (InvisibleStalker, aura without a visual)

    def test_the_spheres_are_one_size_and_height(self):
        # scale * model radius (Flame 2.3, Ice 2.0, Frost 0.8, Lightning 0.86, Nexus 0.87, read from the client's models)
        # is about a globe's 0.35 yards, and scale * model centre + lift is 0.6 yards up for each
        model = {7781: (0.87, 0.0), 9701: (2.3, 0.0), 9702: (0.8, 3.46), 9703: (2.0, 0.0), 9704: (0.86, 1.88)}
        for display, scale, lift, *_ in candidates():
            if display in model:
                radius, centre = model[display]
                self.assertAlmostEqual(0.35, scale * radius, delta=0.04, msg=display)
                self.assertAlmostEqual(0.6, scale * centre + lift, delta=0.06, msg=display)

    def test_the_template_is_one_decoration(self):
        row = [r for r in sheet("world_objects.csv") if r["entry"] == "910099"]
        self.assertEqual(1, len(row))
        self.assertEqual(("8365", "Orb candidate"), (row[0]["display_id"], row[0]["name"]))
        self.assertIn("constexpr std::uint32_t CandidateObject = 910099;", HEADER)


class Glue(unittest.TestCase):
    def test_each_copy_wears_its_look_and_goes_in_ten_minutes(self):
        self.assertIn("constexpr std::uint32_t LifetimeSeconds = 600;", HEADER)
        self.assertIn('{"orbrow", Row, SEC_GAMEMASTER, Console::No}', GLUE)
        self.assertIn("Spawn(map, candidate, spot,", GLUE)
        self.assertIn("+ candidate.lift,", GLUE)
        self.assertIn("object->DespawnOrUnsummon(std::chrono::seconds(LifetimeSeconds));", GLUE)
        self.assertIn('candidate.needsPatch ? " [needs the Nightly patch]" : ""', GLUE)

    @staticmethod
    def set_before_add(glue):
        spawn = glue[glue.index("GameObject* Spawn("):glue.index("class Command final")]
        add = spawn.index("map->AddToMap(object);")
        return (spawn.index("object->Create(") < spawn.index("object->SetDisplayId(candidate.display);") < add
                and spawn.index("object->SetObjectScale(candidate.scale);") < add)

    def test_the_display_and_scale_are_set_before_the_map_add(self):
        # the client takes a gameobject's display from the create packet only, so a SetDisplayId after AddToMap is
        # right on the server and every copy draws the template's look (ruling 2026-10-16, .dc orbrow on dev)
        self.assertTrue(self.set_before_add(GLUE))
        self.assertNotIn("map->SummonGameObject(", GLUE)   # it adds to the map inside, before a display can be set
        spawn = GLUE[GLUE.index("GameObject* Spawn("):GLUE.index("class Command final")]
        self.assertIn("SetSpawnedByDefault(false);", spawn)
        self.assertIn("SetRespawnTime(0);", spawn)

    def test_the_old_order_is_rejected(self):
        # today's order on dev: the template summoned and added, then the display and scale set. The pin must fail it.
        first = "            object->SetDisplayId(candidate.display);\n            object->SetObjectScale(candidate.scale);\n"
        late = mutate(GLUE, first, "")
        late = mutate(late, "map->AddToMap(object);\n", "map->AddToMap(object);\n" + first)
        self.assertFalse(self.set_before_add(late))
        late_scale = mutate(GLUE, "            object->SetObjectScale(candidate.scale);\n", "")
        late_scale = mutate(late_scale, "map->AddToMap(object);\n", "map->AddToMap(object);\n            object->SetObjectScale(candidate.scale);\n")
        self.assertFalse(self.set_before_add(late_scale))

    def test_a_second_command_removes_the_row(self):
        second = GLUE[GLUE.index("if (!standing.empty())"):GLUE.index("float const o = player->GetOrientation();")]
        self.assertIn("object->DespawnOrUnsummon();", second)
        self.assertIn("return true;", second)
        self.assertIn("rows.erase(found);", GLUE)
        self.assertIn("rows[player->GetGUID()] = spawned;", GLUE)

    def test_the_loader_registers_it(self):
        self.assertIn('#include "rifts/dc_orb_pick.h"', LOADER)
        self.assertIn("    DC::OrbPick::RegisterScripts();\n", LOADER)


if __name__ == "__main__":
    unittest.main()
