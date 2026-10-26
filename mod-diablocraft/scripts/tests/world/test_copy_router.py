#!/usr/bin/env python3
"""Bounties R0 (diablocraft-dm9vg.7): the copy router.

src/rifts/dc_copy_router.h is compiled as it is and driven through the rulings (clustering.md section 2; decisions.md
2026-10-11 "Shared bounty zones" and 2026-10-12 "Bounties R0 copy key"), with the caps, the linger and the seat timeout
parsed out of the generated tunables_0012.sql and the party size out of the generated party_scaling.sql. Then the glue in
dc_open_rift.cpp is held to the router: the trip, the hook, the counts, the join (compiled: only a joiner is marked, never
the leader Group::Create adds) and `.dc copies`. Bounty acts A4 (diablocraft-hyoic.7): copies are keyed by (map, tier), and
the glue routes, binds, counts and caps each copy on its zone's map. Every single-rule mutant the review asked for is named in MUTANTS below
and run by MutantsAreKilled: each must break at least one expectation.
"""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROUTER_H = MODULE / "src/rifts/dc_copy_router.h"
OPEN_RIFT = MODULE / "src/rifts/dc_open_rift.cpp"
TUNABLES = MODULE / "data/sql/db-world/updates/tunables_0012.sql"
PARTY = MODULE / "data/generated/party_scaling.sql"
ZONES = MODULE / "data/d3/rift_open_zones.csv"
SCRATCH = MODULE.parent / "azerothcore-wotlk/build/_agent-scratch/copy-router"
CXX = shutil.which("c++") or shutil.which("g++")


def tunable(name: str) -> int:
    found = re.search(rf"\('rifts', '{name}', (NULL|[\d.]+), (NULL|[\d.]+),", TUNABLES.read_text(encoding="utf-8"))
    assert found, f"{name} is not in {TUNABLES.name}"
    d3, tuned = found.groups()
    return int(float(tuned if tuned != "NULL" else d3))


def zone_keys() -> list[str]:
    with ZONES.open(encoding="utf-8", newline="") as stream:
        return [row["key"] for row in csv.DictReader(stream)]


def party_size() -> int:
    return PARTY.read_text(encoding="utf-8").count("'open_world'")


# The scenarios, in C++ against the header. Each prints "CHECK <name> <got>"; Python holds the expected values.
DRIVER = r"""
#include "dc_copy_router.h"
#include <iostream>
using namespace DC::Rifts::CopyRouter;
static Rules rules;
static std::map<std::string, unsigned> caps;
static void Fill(Router& r, std::uint32_t instance, unsigned tier, std::string const& zone, unsigned n, std::uint64_t from)
{
    for (unsigned i = 0; i < n; ++i)
        r.Enter(0, instance, 751, tier, from + i, zone, false);
}
static void Show(char const* name, Pick const& p)
{
    std::cout << "CHECK " << name << " " << (p.open ? "open" : "copy") << ":" << p.number << ":" << p.instanceId
              << ":" << p.party << "\n";
}
int main()
{
    rules.cap = [](std::string const& zone) { return caps.count(zone) ? caps[zone] : 0u; };
    rules.linger = LINGER;
    rules.seatTimeout = SEAT;
CAPS
    unsigned const cap = caps["ungoro"];
    { // the designer's example: copy 1 full, copy 2 has room -> 2; two leave copy 1 -> the next player goes to 1
        Router r;
        r.Opened(751, 5, 1, 101); r.Opened(751, 5, 2, 102);
        Fill(r, 101, 5, "ungoro", cap, 1000);
        Fill(r, 102, 5, "ungoro", 4, 2000);
        Show("example_first", r.Route(rules, 10, 751, 5, "ungoro", 1, {}));
        r.Leave(11, 101, 1000); r.Leave(11, 101, 1001);
        Show("example_later", r.Route(rules, 12, 751, 5, "ungoro", 2, {}));
    }
    { // the cap is per zone inside the copy: Un'Goro full, Tanaris empty -> Tanaris still goes to copy 1
        Router r;
        r.Opened(751, 5, 1, 101);
        Fill(r, 101, 5, "ungoro", cap, 1000);
        Show("per_zone_tanaris", r.Route(rules, 1, 751, 5, "tanaris", 1, {}));
        Show("per_zone_ungoro", r.Route(rules, 1, 751, 5, "ungoro", 1, {}));
    }
    { // a party is never split: a member in full copy 1 -> copy 1; the leader's copy wins over a member's
        Router r;
        r.Opened(751, 5, 1, 101); r.Opened(751, 5, 2, 102);
        Fill(r, 101, 5, "ungoro", cap, 1000);
        Show("party_full_copy", r.Route(rules, 1, 751, 5, "ungoro", 7, {9, 1000, 7}));
        r.Enter(1, 102, 751, 5, 9, "tanaris", false);
        Show("party_leader_first", r.Route(rules, 1, 751, 5, "ungoro", 7, {9, 1000, 7}));
        std::cout << "CHECK party_past_cap " << (r.Promise(rules, 1, 101, 7, "ungoro"), r.Find(101)->InZone("ungoro", 0)) << "\n";
    }
    { // promised seats: the last seat goes once; after the timeout it is free again
        Router r;
        r.Opened(751, 5, 1, 101);
        Fill(r, 101, 5, "ungoro", cap - 1, 1000);
        Pick a = r.Route(rules, 100, 751, 5, "ungoro", 1, {});
        r.Promise(rules, 100, a.instanceId, 1, "ungoro");
        Show("seat_first", a);
        Show("seat_second", r.Route(rules, 100, 751, 5, "ungoro", 2, {}));
        Show("seat_before_timeout", r.Route(rules, 100 + SEAT - 1, 751, 5, "ungoro", 2, {}));
        Show("seat_after_timeout", r.Route(rules, 100 + SEAT, 751, 5, "ungoro", 2, {}));
        r.Promise(rules, 200, 101, 3, "ungoro");
        r.Enter(201, 101, 751, 5, 3, "ungoro", false); // arrival uses the seat, it does not add a second
        std::cout << "CHECK seat_used " << r.Find(101)->InZone("ungoro", 0) << " " << r.Find(101)->promised.size() << "\n";
    }
    { // a trip between copies leaves the old one during the loading screen: the seat in the new one stays
        Router r;
        r.Opened(751, 5, 1, 101); r.Opened(751, 5, 2, 102);
        r.Enter(0, 101, 751, 5, 1, "ungoro", false);
        r.Promise(rules, 0, 102, 1, "tanaris");
        r.Leave(1, 101, 1);
        std::cout << "CHECK loading_screen_seat " << r.Find(102)->promised.size() << " " << r.Find(101)->emptySince << "\n";
    }
    { // linger: an empty copy is still a copy with room until the linger has passed, then it closes
        Router r;
        r.Opened(751, 5, 1, 101); r.Opened(751, 5, 2, 102);
        Fill(r, 101, 5, "ungoro", cap, 1000);
        r.Enter(0, 102, 751, 5, 1, "ungoro", false);
        r.Leave(1000, 102, 1);
        Show("linger_open", r.Route(rules, 1000 + LINGER - 1, 751, 5, "ungoro", 2, {}));
        Show("linger_closed", r.Route(rules, 1000 + LINGER, 751, 5, "ungoro", 2, {}));
        std::cout << "CHECK linger_copies " << r.Copies().size() << "\n";
    }
    { // a copy opened for a seat that never arrived empties when the seat times out, then lingers from there
        Router r;
        r.Opened(751, 5, 1, 101);
        r.Promise(rules, 0, 101, 1, "ungoro");
        r.Tidy(rules, SEAT);
        std::cout << "CHECK unused_copy " << r.Find(101)->emptySince << "\n";
        r.Tidy(rules, SEAT + LINGER);
        std::cout << "CHECK unused_copy_closed " << r.Copies().size() << "\n";
    }
    { // the lowest free number: copies 1 and 3 open -> a new copy is 2; tiers number apart
        Router r;
        r.Opened(751, 5, 1, 101); r.Opened(751, 5, 3, 103); r.Opened(751, 6, 1, 201);
        Fill(r, 101, 5, "ungoro", cap, 1000);
        Fill(r, 103, 5, "ungoro", cap, 3000);
        Show("lowest_free", r.Route(rules, 1, 751, 5, "ungoro", 1, {}));
        Show("tier_apart", r.Route(rules, 1, 751, 7, "ungoro", 1, {}));
        Show("tier_own", r.Route(rules, 1, 751, 6, "ungoro", 1, {}));
    }
    { // never merged: copy 1 thins out, nobody in copy 2 moves
        Router r;
        r.Opened(751, 5, 1, 101); r.Opened(751, 5, 2, 102);
        Fill(r, 101, 5, "ungoro", 3, 1000);
        Fill(r, 102, 5, "ungoro", 2, 2000);
        r.Leave(5, 101, 1000); r.Leave(5, 101, 1001);
        r.Route(rules, 6, 751, 5, "ungoro", 9, {});
        std::cout << "CHECK never_merged " << r.Find(101)->inside.size() << " " << r.Find(102)->inside.size() << "\n";
    }
    { // a GM is never counted; an instance the router does not know is adopted on arrival
        Router r;
        r.Opened(751, 5, 1, 101);
        r.Enter(0, 101, 751, 5, 1, "ungoro", true);
        std::cout << "CHECK gm " << r.Find(101)->inside.size() << "\n";
        r.Enter(0, 555, 751, 5, 2, "tanaris", false);
        std::cout << "CHECK adopted " << r.Find(555)->number << " " << r.Find(555)->tier << "\n";
    }
    { // bounty acts A4 (diablocraft-hyoic.7): copies are keyed by (map, tier); a copy of 751 is never one of 752
        Router r;
        r.Opened(751, 5, 1, 101);
        Show("map_apart", r.Route(rules, 1, 752, 5, "ungoro", 1, {}));          // room on 751 is no room on 752
        r.Opened(752, 5, 1, 301);
        Show("map_own", r.Route(rules, 1, 752, 5, "ungoro", 1, {}));
        r.Enter(1, 101, 751, 5, 9, "ungoro", false);                            // the leader in a 751 copy
        Show("party_other_map", r.Route(rules, 1, 753, 5, "ungoro", 7, {9, 7})); // another continent: no party rule there
        Show("party_same_map", r.Route(rules, 1, 751, 5, "ungoro", 7, {9, 7}));
        r.Enter(1, 555, 753, 5, 2, "ungoro", false);                            // an unknown 753 instance is adopted on 753
        std::cout << "CHECK adopted_map " << r.Find(555)->map << " " << r.Find(555)->number << "\n";
    }
    std::cout << "CHECK hard_cap " << Router::HardCap(ZONES, rules, PARTY - 1) << "\n";
}
"""


def run_driver(header: Path = ROUTER_H) -> dict[str, str]:
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    zones = zone_keys()
    code = (DRIVER.replace("LINGER", str(tunable("copy_linger_seconds")))
            .replace("SEAT", str(tunable("copy_seat_timeout_seconds")))
            .replace("CAPS", "\n".join(f'    caps["{z}"] = {tunable("copy_cap_" + z)};' for z in zones))
            .replace("ZONES", "{" + ", ".join(f'"{z}"' for z in zones) + "}")
            .replace("PARTY", str(party_size())))
    try:   # the cached compile: the green driver repeats once per mutant
        binary = harness_env.build_text(code, flags=["-std=c++17", "-Wall", "-Werror"], files={"dc_copy_router.h": header.read_bytes()})
    except harness_env.BuildError as error:
        raise AssertionError("the router did not compile:\n" + error.stderr[-4000:])
    out = harness_env.run([str(binary)], capture_output=True, text=True, check=True).stdout
    return dict(re.findall(r"^CHECK (\S+) (.*)$", out, re.M))


def expected() -> dict[str, str]:
    """What each CHECK line of the driver must print, from the generated numbers."""
    cap, seat = tunable("copy_cap_ungoro"), tunable("copy_seat_timeout_seconds")
    zones = zone_keys()
    return {
        "example_first": "copy:2:102:0", "example_later": "copy:1:101:0",                       # fill first copy with room
        "per_zone_tanaris": "copy:1:101:0", "per_zone_ungoro": "open:2:0:0",                   # the cap is per zone
        "party_full_copy": "copy:1:101:1", "party_leader_first": "copy:2:102:1",               # a party is never split
        "party_past_cap": str(cap + 1),
        "seat_first": "copy:1:101:0", "seat_second": "open:2:0:0",                             # promised seats
        "seat_before_timeout": "open:2:0:0", "seat_after_timeout": "copy:1:101:0",
        "seat_used": f"{cap} 0", "loading_screen_seat": "1 1",
        "linger_open": "copy:2:102:0", "linger_closed": "open:2:0:0", "linger_copies": "1",    # linger, then close
        "unused_copy": str(seat), "unused_copy_closed": "0",
        "lowest_free": "open:2:0:0", "tier_apart": "open:1:0:0", "tier_own": "copy:1:201:0",   # numbers and tiers
        "never_merged": "1 2", "gm": "0", "adopted": "2 5",
        "map_apart": "open:1:0:0", "map_own": "copy:1:301:0",                                  # (map, tier), A4
        "party_other_map": "open:1:0:0", "party_same_map": "copy:1:101:1", "adopted_map": "753 1",
        "hard_cap": str(sum(tunable("copy_cap_" + z) for z in zones) + len(zones) * (party_size() - 1)),
    }


def rule_problems(got: dict[str, str]) -> list[str]:
    return [f"{name}: {got.get(name)!r} != {want!r}" for name, want in expected().items() if got.get(name) != want]


def body(source: str, marker: str) -> str:
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


# Rule 8's mark, compiled: Group::Create adds the leader with AddMember too, so the hook must mark the joiner only.
JOIN_DOUBLES = r"""
#include <cstdint>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <unordered_set>
typedef std::uint32_t uint32; typedef std::uint64_t uint64;
struct ObjectGuid { uint64 raw; uint64 GetRawValue() const { return raw; } };
struct Player { uint32 map; uint32 GetMapId() const { return map; } };
std::map<uint64, Player*> online;
namespace ObjectAccessor { Player* FindConnectedPlayer(ObjectGuid g) { auto f = online.find(g.raw); return f == online.end() ? nullptr : f->second; } }
struct Group { uint64 leader; bool IsLeader(ObjectGuid g) const { return g.raw == leader; } };
bool IsOpenZoneMap(uint32 map) { return map == 751; } std::mutex routerMutex; std::unordered_set<uint64> joined;
struct PartyJoin {
"""
JOIN_MAIN = r"""
};
int main() {
    Player inviter{751}, joiner{751}, away{0};
    online = {{1, &inviter}, {2, &joiner}, {3, &away}};
    Group group{1}; PartyJoin hook;
    hook.OnAddMember(&group, ObjectGuid{1});   // Group::Create: the leader first
    hook.OnAddMember(&group, ObjectGuid{2});   // the joiner, in another copy
    hook.OnAddMember(&group, ObjectGuid{3});   // a joiner not on map 751
    std::set<uint64> marked(joined.begin(), joined.end());
    std::cout << "JOINED";
    for (uint64 g : marked) std::cout << " " << g;
    std::cout << "\n";
}
"""


def join_marks(source: str) -> str:
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    code = JOIN_DOUBLES + body(source, "void OnAddMember(").replace(") override", ")") + JOIN_MAIN
    try:
        binary = harness_env.build_text(code, flags=["-std=c++17"])
    except harness_env.BuildError as error:
        return "did not compile: " + error.stderr[-500:]
    return harness_env.run([str(binary)], capture_output=True, text=True, check=True).stdout.strip()


def glue_problems(source: str) -> list[str]:
    out = []
    travel = body(source, "std::string TravelToOpenZone(")
    if "OpenRift::SendTo(player, *zone, error)" not in travel or re.search(r"player->TeleportTo\(", travel):
        out.append("the trip is not routed")
    send = body(source, "uint32 SendTo(")
    # binds the traveller and the leader, opens a copy the way a rift is made, refuses a party in a rift
    for piece in ("router.Route(rules, now, mapId, tier, zone.key, me, party)", "BindTo(player->GetGUID(), save)", "BindTo(leader, save)",
                  "sMapMgr->CreateMap(mapId, player)", "router.Opened(mapId, tier, pick.number, save->GetInstanceId())", "router.Promise(",
                  "IsLiveInstance(mapId, current)", "router.Drop(", "uint32 const mapId = zone.mapId;"):
        if piece not in send:
            out.append("SendTo lacks " + piece)
    arrive = body(source, "bool Arrive(")
    if "!sameCopy && player->GetMapId() == zone.mapId" not in arrive or "player->TeleportTo(zone.mapId, x, y, z, o," not in arrive:
        out.append("no far teleport between copies")
    shared = body(source, "bool IsInstanceShared(")
    if "if (!router.Find(instanceId))" not in shared or "Router::HardCap(keys, rules, party > 0 ? party - 1 : 0)" not in shared:
        out.append("the hook answers more than the router's copies, or not with the hard cap")
    if "router.Enter(" not in body(source, "void OnPlayerEnterAll(") or "router.Leave(" not in body(source, "void OnPlayerLeaveAll("):
        out.append("the counts are not kept by the map hooks")
    if ("router.Enter(Now(), map->GetInstanceId(), map->GetId()," not in body(source, "void OnPlayerEnterAll(")
            or "if (zone.mapId == mapId)\n                        keys.push_back(zone.key);" not in shared):
        out.append("a copy is not counted or capped by its own map (A4)")
    bind = body(source, "void BindTo(")
    if "PlayerGetBoundInstance(guid, save->GetMapId(), difficulty)" not in bind or "PlayerUnbindInstance(guid, save->GetMapId()," not in bind:
        out.append("a bind is not moved on the copy's own map")
    for script in ("new CopyCounts();", "new SharedCopies();", "new PartyJoin();"):
        if script not in source:
            out.append("not registered: " + script)
    if "SendTo(player, *zone, error, true)" not in body(source, "void MoveToParty("):
        out.append("the join move is not party-only")
    if (marks := join_marks(source)) != "JOINED 2":
        out.append("rule 8 marks the wrong players: " + marks)
    if '{"copies", HandleCopies, SEC_GAMEMASTER' not in source or "router.Tidy(rules, now)" not in body(source, "static bool HandleCopies("):
        out.append("`.dc copies` is missing or does not tidy first")
    return out


# The single-rule mutants (reviewer.md check 4), each named: (file, name, the text, its replacement). Each must break an
# expectation: a header mutant through the compiled driver, a glue mutant through glue_problems.
MUTANTS = [
    (ROUTER_H, "no party rule", "            if (Copy const* together = leaderCopy ? leaderCopy : memberCopy)", "            if (Copy const* together = nullptr)"),
    (ROUTER_H, "a member's copy before the leader's", "leaderCopy ? leaderCopy : memberCopy", "memberCopy ? memberCopy : leaderCopy"),
    (ROUTER_H, "the cap off by one", "copy.InZone(zone, player) + 1 <= rules.cap(zone)", "copy.InZone(zone, player) <= rules.cap(zone)"),
    (ROUTER_H, "the cap counts every zone", "n += player != except && where == zone;", "n += player != except;"),
    (ROUTER_H, "promised seats not counted", "                n += seat.player != except && seat.zone == zone;\n", ""),
    (ROUTER_H, "a seat outlives its timeout", "if (s.until > now)", "if (s.until >= now)"),
    (ROUTER_H, "the linger closes one second late", "now - c.emptySince >= rules.linger", "now - c.emptySince > rules.linger"),
    (ROUTER_H, "no lowest free number", "            return {0, FreeNumber(map, tier), true, false};",
     "            return {0, static_cast<unsigned>(copies.size() + 1), true, false};"),
    (ROUTER_H, "the tier ignored", "if (copy.map == map && copy.tier == tier && copy.InZone", "if (copy.map == map && copy.InZone"),
    (ROUTER_H, "the map ignored for room (A4)", "if (copy.map == map && copy.tier == tier && copy.InZone", "if (copy.tier == tier && copy.InZone"),
    (ROUTER_H, "the party rule crosses maps (A4)", "if (copy.map == map && party[i] != player && copy.Holds(party[i]))",
     "if (party[i] != player && copy.Holds(party[i]))"),
    (ROUTER_H, "numbers shared across maps (A4)", "[&](Copy const& c) { return c.map == map && c.tier == tier && c.number == number; }",
     "[&](Copy const& c) { return c.tier == tier && c.number == number; }"),
    (ROUTER_H, "an adopted copy on the wrong map (A4)", "                Opened(map, tier, FreeNumber(map, tier), instanceId);",
     "                Opened(751, tier, FreeNumber(map, tier), instanceId);"),
    (ROUTER_H, "a leave drops the seat promised elsewhere",
     "        void Leave(std::int64_t now, std::uint32_t instanceId, std::uint64_t player)\n        {\n",
     "        void Leave(std::int64_t now, std::uint32_t instanceId, std::uint64_t player)\n        {\n"
     "            for (Copy& c : copies)\n                c.promised.erase(std::remove_if(c.promised.begin(), c.promised.end(),\n"
     "                                                [&](Seat const& s) { return s.player == player; }), c.promised.end());\n"),
    (ROUTER_H, "a GM counted", "            if (!gm)\n                copy->inside[player] = zone;", "            copy->inside[player] = zone;"),
    (ROUTER_H, "no party overflow in the hard cap", "total += rules.cap(zone) + partyOverflow;", "total += rules.cap(zone);"),
    (ROUTER_H, "an unused copy never empties",
     "                if (copy.inside.empty() && copy.promised.empty() && copy.emptySince < 0)\n"
     "                    copy.emptySince = lastSeat >= 0 ? lastSeat : now;\n", ""),
    (OPEN_RIFT, "the trip not routed", "        std::uint32_t const routed = OpenRift::SendTo(player, *zone, error);",
     "        std::uint32_t const routed = 1;"),
    (OPEN_RIFT, "a near teleport between copies", "!sameCopy && player->GetMapId() == zone.mapId))", "false))"),
    (OPEN_RIFT, "a copy capped by every map's zones (A4)", "                    if (zone.mapId == mapId)\n                        keys.push_back(zone.key);",
     "                    keys.push_back(zone.key);"),
    (OPEN_RIFT, "the leader's bind looked up on a fixed map (A4)", "PlayerGetBoundInstance(guid, save->GetMapId(), difficulty)",
     "PlayerGetBoundInstance(guid, 751, difficulty)"),
    (OPEN_RIFT, "the leader not bound", "                if (!leader.IsEmpty() && leader != player->GetGUID())\n                    BindTo(leader, save);\n", ""),
    (OPEN_RIFT, "the hook answers every open-zone instance", "                if (!router.Find(instanceId))\n                    return false;\n", ""),
    (OPEN_RIFT, "rule 8 marks the leader (diablocraft-xcx0h)", "                if (group && group->IsLeader(guid))\n                    return;\n", ""),
]


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.got = run_driver()

    def test_the_sheet_numbers(self):
        # decisions 79aac985 point 9 (20 a zone), 93a51de7 point 5 (5 minutes); the seat timeout is a PLACEHOLDER row.
        self.assertEqual({z: tunable("copy_cap_" + z) for z in zone_keys()}, {z: 20 for z in zone_keys()})
        self.assertEqual(tunable("copy_linger_seconds"), 300)
        self.assertGreater(tunable("copy_seat_timeout_seconds"), 0)

    def test_every_scenario(self):
        self.assertEqual(rule_problems(self.got), [])


class Glue(unittest.TestCase):
    source = OPEN_RIFT.read_text(encoding="utf-8")

    def test_the_glue_holds_the_router(self):
        self.assertEqual(glue_problems(self.source), [])

    def test_only_the_joiner_is_marked(self):
        self.assertEqual(join_marks(self.source), "JOINED 2")

    def test_every_tunable_the_glue_reads_is_generated(self):
        for name in re.findall(r'DC::Tunables::Get\("rifts", "(copy_[a-z_]+)"\)', self.source):
            tunable(name)
        self.assertIn('"copy_cap_" + zone', self.source)
        for zone in zone_keys():
            tunable("copy_cap_" + zone)


class MutantsAreKilled(unittest.TestCase):
    def test_each_named_mutant_breaks_an_expectation(self):
        self.assertEqual(len(MUTANTS), 24)
        for path, name, old, new in MUTANTS:
            with self.subTest(mutant=name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count(old), 1, f"{name}: its target moved")
                mutant = text.replace(old, new)
                if path == ROUTER_H:
                    SCRATCH.mkdir(parents=True, exist_ok=True)
                    folder = Path(tempfile.mkdtemp(prefix="mutant-", dir=SCRATCH))
                    try:
                        (folder / "dc_copy_router.h").write_text(mutant, encoding="utf-8")
                        try:
                            problems = rule_problems(run_driver(folder / "dc_copy_router.h"))
                        except AssertionError as error:  # a mutant that does not compile is killed too
                            problems = [str(error)[:80]]
                    finally:
                        shutil.rmtree(folder)
                else:
                    problems = glue_problems(mutant)
                self.assertNotEqual(problems, [], f"mutant survived: {name}")


if __name__ == "__main__":
    unittest.main()
