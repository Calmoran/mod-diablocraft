"""diablocraft-dm9vg.5: bounties W5, travel (brief bounties-first-set-2026-10-11 W5, contract
docs/contracts/bounty-messages.md Travel, decisions a123f96a for the gate).

1. The gate and the cell's zone (src/bounties/dc_bounty_board.h, compiled as it is) with the generated catalogue: a
   bounty's button lands at its zone's waypoint, Kill and Click alike, as D3 (dm9vg.10, the designer's playtest 2026-10-12).
2. The window (Window, Travel and TravelToCell cut out of src/bounties/dc_bounties.cpp) behind the real bridge header,
   against a Player double: the facts the gate reads come from the player (an open-zone copy by its map id), a refusal
   is X|text and moves nobody, a success sends no record and makes one trip, a bad field is the bridge's malformed text.
   dm9vg.10: from the Sanctum the trip is instant; from the open world it is the travel cast, and the trip goes only when
   that cast ends (TravelCastDone), on the player's next update, after the gate again; an interrupted cast moves nobody.
   The cast's spell data and its damage interrupt (TravelSpellData, TravelDamage) are compiled against doubles too.
3. The trip (TravelToOpenZone cut out of src/rifts/dc_open_rift.cpp) against doubles of its zone sheet and of the core's
   copy pick: a zone with no entrance moves nobody, neither does a party copy that is a live rift (the PM's ruling), the zone edge already holds the new zone when the teleport runs, a failed teleport puts the
   old zone back.

Every compiled test runs again on a source mutation that removes the rule it checks, and that run must fail. Not
covered: the core's own copy pick (the party leader's bind on map 751) and the teleport itself; the designer's check on dev
covers those.
"""
import re
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_bounties import BOARD, HELPERS, MIGRATION, PRELUDE, SERVER, both, catalogue_cpp, first_set_sql
from test_class_parity import SRC, definition, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

OPEN = (SRC / "rifts/dc_open_rift.cpp").read_text(encoding="utf-8")
RIFT = "You cannot travel from inside a rift."
SANCTUM_RULE = "if (at.sanctum)\n                return Go(player, trip);"
ELSEWHERE = "You can travel only from the Sanctum or the open world."
COMBAT = "You cannot travel while in combat."


class Gate(unittest.TestCase):
    CASES = '''
    auto is = [](Standing s, char const* want) { char const* got = TravelRefusal(s); return want ? got && std::string(got) == want : !got; };
    Standing continent;                                           // the open world on a stock continent
    Standing sanctum; sanctum.sanctum = true;
    Standing copy; copy.instanced = copy.openZone = true;         // an open-zone copy (Un'Goro, map 751)
    Standing riftCopy = copy; riftCopy.rift = true;               // a rift on that same map
    Standing riftDungeon; riftDungeon.instanced = riftDungeon.rift = true;
    Standing dungeon; dungeon.instanced = true;                   // any other instance: a dungeon, a battleground
    Standing sanctumFight = sanctum; sanctumFight.inCombat = true;
    Standing copyFight = copy; copyFight.inCombat = true;
'''

    def check(self, line, old, new):
        both(self, self.CASES + line, old, new)

    def test_the_sanctum_and_the_open_world_go(self):
        self.check('assert(is(sanctum, nullptr) && is(continent, nullptr));', 'if (!at.sanctum && at.instanced && !at.openZone)', 'if (!at.sanctum)')

    def test_an_open_zone_copy_is_open_world_though_it_is_an_instance(self):
        self.check('assert(is(copy, nullptr) && is(dungeon, "' + ELSEWHERE + '"));', 'at.instanced && !at.openZone', 'at.instanced')

    def test_never_from_inside_a_rift_even_on_the_open_zone_map(self):
        self.check('assert(is(riftCopy, "' + RIFT + '") && is(riftDungeon, "' + RIFT + '"));', '        if (at.rift)\n', '        if (false)\n')

    def test_out_of_combat_only(self):
        self.check('assert(is(sanctumFight, "' + COMBAT + '") && is(copyFight, "' + COMBAT + '"));', '        if (at.inCombat)\n', '        if (false)\n')


class CellZone(unittest.TestCase):
    def test_a_cell_names_its_zone_and_a_locked_cell_nothing(self):
        both(self, '''
    Seq rng; Board b = Draw(catalog, targets, Rules{0, 3, 6}, std::ref(rng));
    // diablocraft-hyoic.1: a column is an act; the fixed sequence (with each Kill's target pick, hyoic.2) draws act 1 as
    // Azshara, Moonglade and act 2 as Tanaris, Un'Goro, Thousand Needles (bounties.csv)
    std::string const* z = CellZone(b, catalog, 1, 1); assert(z && *z == "azshara");
    assert(*CellZone(b, catalog, 1, 2) == "moonglade" && *CellZone(b, catalog, 2, 2) == "ungoro");
    assert(!CellZone(b, catalog, 1, 3) && !CellZone(b, catalog, 2, 4) && !CellZone(b, catalog, 3, 1));   // locked cells''',
             "if (c.column == column && c.cell == cell)\n                if (Bounty const* b",
             "if (c.column == column)\n                if (Bounty const* b")


# --- 2. the window, cut out of dc_bounties.cpp, behind the real bridge header ------------------------------------------

WINDOW_DOUBLES = r'''
#include <chrono>
#include <functional>
#include <map>
#include <mutex>
#include <tuple>
#include "dc_bridge.h"
using namespace std::chrono_literals;
enum SpellCastResult { SPELL_FAILED_NOT_READY = 1, SPELL_CAST_OK = 255 };
namespace DC::Combat::Shells { constexpr unsigned BountyTravel = 83601; }
struct Map { bool instanceable = false; bool Instanceable() const { return instanceable; } };
struct Guid { std::uint64_t raw; std::uint64_t GetRawValue() const { return raw; } };
struct Events {
    std::vector<std::function<void()>> queued;
    void AddEventAtOffset(std::function<void()> f, std::chrono::milliseconds) { queued.push_back(std::move(f)); }
    void Update() { auto now = std::move(queued); queued.clear(); for (auto& f : now) f(); }
};
struct WorldSession {};
std::vector<std::string> said;
struct ChatHandler { explicit ChatHandler(WorldSession*) {} void SendSysMessage(std::string const& s) { said.push_back(s); } };
struct Player {
    bool teleporting = false, combat = false, hub = false, rift = false; Map map; unsigned mapId = 0;
    std::uint64_t id = 1; std::vector<unsigned> casts; SpellCastResult castResult = SPELL_CAST_OK; Events m_Events;
    bool IsBeingTeleported() const { return teleporting; } Map const* GetMap() const { return &map; }
    unsigned GetMapId() const { return mapId; } bool IsInCombat() const { return combat; }
    Guid GetGUID() const { return {id}; } WorldSession* GetSession() { return nullptr; }
    SpellCastResult CastSpell(Player*, unsigned spell, bool) { casts.push_back(spell); return castResult; }
};
namespace DC::World { bool IsInHub(Player const* p) { return p->hub; } }
namespace DC::Rifts {
    struct Rift {}; bool Current(Player const* p, Rift&) { return p->rift; } bool IsOpenZoneMap(std::uint32_t m) { return m == 751; }
    std::vector<std::tuple<std::string, bool, float>> trips; std::string refuse;
    std::string TravelToOpenZone(Player*, std::string const& key, float const* spot) { trips.emplace_back(key, spot != nullptr, spot ? spot[0] : 0.f); return refuse; }
}
namespace DC::Bounties {
    std::mutex boardMutex; Board theBoard; struct Owner {}; int shows = 0;
    Owner OwnerOf(Player*) { return {}; } Board& LoadLocked(Owner) { return theBoard; } bool IsLeader(Player*) { return true; }
    void Show(Player*, Owner, bool) { ++shows; } std::string Reroll(Player*) { return "reroll refused"; }
'''

WINDOW_MAIN = r'''
    std::string const prefix = "DCBOUNTY";
    DC::Bridge::Wire<Player>::Sender const send = [](Player*, std::string const&, std::string const&) { assert(false); };
    auto ask = [&](Player& p, std::vector<std::string> f) {
        DC::Bridge::Request r; r.fields = f;
        try { DC::Bounties::Window(p, r, DC::Bridge::Wire<Player>(send, &p, prefix)); return std::string(); }
        catch (DC::Bridge::Refusal const& e) { return std::string(e.what()); }
    };
    using DC::Rifts::trips;
    Seq rng; DC::Bounties::theBoard = Draw(catalog, targets, Rules{0, 1, 3}, std::ref(rng));
    Player sanctum; sanctum.hub = true;
    Player copy; copy.mapId = 751; copy.map.instanceable = true; copy.id = 2;
    Player continent; continent.mapId = 1; continent.id = 3;
    Player rift = copy; rift.rift = true;
    Player dungeon; dungeon.mapId = 36; dungeon.map.instanceable = true;
    Player fight = copy; fight.combat = true;
    Player busy = sanctum; busy.teleporting = true;
'''


def window_source(server=SERVER):
    state = re.search(r"std::mutex tripMutex;\s*std::map<std::uint64_t, Trip> casting;", server)
    return (definition(server, "struct Trip") + ";\n" + (state.group(0) if state else "") + "\n" +
            "\n".join(definition(server, marker) for marker in
                      ("Standing StandingOf(", "std::string Go(", "std::string Travel(Player* player", "void TravelCastDone(",
                       "std::string TravelToCell(", "void Window(Player& player")))


def compile_window(body, server=SERVER):
    code = (PRELUDE + BOARD + catalogue_cpp(first_set_sql()) + HELPERS + WINDOW_DOUBLES
            + window_source(server) + "\n}\nint main() {\n" + WINDOW_MAIN + body + "\n    return 0;\n}\n")
    return run(code)


def window_both(test, body, old, new):
    ok, out = compile_window(body)
    test.assertTrue(ok, out)
    ok, out = compile_window(body, mutate(SERVER, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class Window(unittest.TestCase):
    def test_a_bounty_button_moves_the_clicker_to_its_zones_waypoint_and_sends_no_record(self):
        window_both(self, '''
    assert(ask(sanctum, {"travel", "1", "2"}).empty() && trips.back() == std::make_tuple(std::string("moonglade"), false, 0.f));
    assert(ask(copy, {"travel", "2", "2"}).empty() && trips.size() == 1);
    DC::Bounties::TravelCastDone(&copy); copy.m_Events.Update();
    assert(trips.back() == std::make_tuple(std::string("ungoro"), false, 0.f));   // the waypoint, not the bounty's spot
    assert(trips.size() == 2);''',
                    "at.openZone = DC::Rifts::IsOpenZoneMap(player->GetMapId());", "at.openZone = false;")

    def test_a_waypoint_moves_the_clicker_to_the_zone_entrance(self):
        window_both(self, '''
    assert(ask(sanctum, {"waypoint", "tanaris"}).empty() && trips.back() == std::make_tuple(std::string("tanaris"), false, 0.f));
    DC::Rifts::refuse = "That zone has no way in yet.";
    assert(ask(sanctum, {"waypoint", "duskwood"}) == "That zone has no way in yet." && trips.size() == 2);''',
                    'else if (*verb == "waypoint" && request.Count() == 2)', 'else if (*verb == "waypoint" && request.Count() == 9)')

    def test_the_gate_refuses_and_moves_nobody(self):
        window_both(self, '''
    assert(ask(rift, {"travel", "1", "1"}) == "''' + RIFT + '''");
    assert(ask(rift, {"waypoint", "ungoro"}) == "''' + RIFT + '''");
    assert(ask(dungeon, {"waypoint", "ungoro"}) == "''' + ELSEWHERE + '''");
    assert(ask(fight, {"travel", "1", "1"}) == "''' + COMBAT + '''");
    assert(ask(busy, {"travel", "1", "1"}) == "You are already on your way.");
    assert(trips.empty());''',
                    "at.rift = DC::Rifts::Current(player, rift);", "at.rift = false;")

    def test_combat_is_read_from_the_player(self):
        window_both(self, 'assert(ask(fight, {"waypoint", "ungoro"}) == "' + COMBAT + '" && trips.empty());',
                    "at.inCombat = player->IsInCombat();", "at.inCombat = false;")

    def test_a_trip_already_under_way_is_refused(self):
        window_both(self, 'assert(ask(busy, {"waypoint", "ungoro"}) == "You are already on your way." && trips.empty());',
                    "if (player->IsBeingTeleported())", "if (false)")

    def test_a_locked_cell_is_refused(self):
        window_both(self, 'assert(ask(sanctum, {"travel", "1", "3"}) == "That bounty is not on your board." && trips.empty());',
                    'return "That bounty is not on your board.";', 'return "";')

    def test_bad_fields_are_the_bridges_malformed_text(self):
        window_both(self, '''
    std::string const bad = DC::Bridge::TextMalformed;
    for (auto const& f : std::vector<std::vector<std::string>>{{"travel", "0", "1"}, {"travel", "6", "1"}, {"travel", "1", "6"},
            {"travel", "1"}, {"travel", "1", "1", "1"}, {"travel", "x", "1"}, {"travel", "+1", "1"}, {"waypoint"},
            {"waypoint", "a-b"}, {"waypoint", "ungoro", "x"}, {"list", "x"}, {"new", "1"}, {"fly"}})
        assert(ask(sanctum, f) == bad);
    assert(trips.empty());
    assert(ask(sanctum, {"list"}).empty() && DC::Bounties::shows == 1);
    assert(ask(sanctum, {"new"}) == "reroll refused");''',
                    "auto column = request.Uint(1, 1, Columns)", "auto column = request.Uint(1, 0, 9)")


    # dm9vg.10: instant from the Sanctum, a cast from the open world.
    def test_the_sanctum_is_instant_and_casts_nothing(self):
        window_both(self, '''
    assert(ask(sanctum, {"waypoint", "tanaris"}).empty() && trips.size() == 1 && sanctum.casts.empty());''',
                    SANCTUM_RULE, "if (false)\n                return Go(player, trip);")

    def test_the_open_world_casts_and_moves_nobody_until_the_cast_ends(self):
        window_both(self, '''
    assert(ask(continent, {"waypoint", "tanaris"}).empty() && trips.empty());
    assert(continent.casts == std::vector<unsigned>{DC::Combat::Shells::BountyTravel});
    assert(ask(copy, {"travel", "1", "1"}).empty() && trips.empty() && copy.casts.size() == 1);
    DC::Bounties::TravelCastDone(&continent);
    assert(trips.empty());                               // not inside the cast's own completion
    continent.m_Events.Update();
    assert(trips.size() == 1 && trips.back() == std::make_tuple(std::string("tanaris"), false, 0.f));
    DC::Bounties::TravelCastDone(&continent); continent.m_Events.Update();
    assert(trips.size() == 1);                           // one cast, one trip''',
                    SANCTUM_RULE, "return Go(player, trip);")

    def test_the_trip_goes_on_the_next_update_not_inside_the_cast(self):
        window_both(self, '''
    assert(ask(continent, {"waypoint", "tanaris"}).empty());
    DC::Bounties::TravelCastDone(&continent);
    assert(trips.empty() && continent.m_Events.queued.size() == 1);''',
                    "            player->m_Events.AddEventAtOffset(\n                [player, trip]",
                    "            ([](auto f, auto) { f(); })(\n                [player, trip]")

    def test_the_trip_waits_for_its_own_cast(self):
        window_both(self, '''
    assert(ask(continent, {"waypoint", "tanaris"}).empty());
    DC::Bounties::TravelCastDone(&copy); copy.m_Events.Update();
    assert(trips.empty());                               // another player's cast end moves nobody
    DC::Bounties::TravelCastDone(&continent); continent.m_Events.Update();
    assert(trips.size() == 1);''',
                    "auto found = casting.find(player->GetGUID().GetRawValue());", "auto found = casting.begin();")

    def test_an_interrupted_cast_moves_nobody_and_a_new_click_replaces_the_trip(self):
        window_both(self, '''
    assert(ask(continent, {"waypoint", "tanaris"}).empty());
    continent.m_Events.Update();
    assert(trips.empty());                               // interrupted: the cast never ended
    assert(ask(continent, {"waypoint", "ungoro"}).empty());
    DC::Bounties::TravelCastDone(&continent); continent.m_Events.Update();
    assert(trips.size() == 1 && std::get<0>(trips.back()) == "ungoro");''',
                    "casting[guid] = trip;", "casting.emplace(guid, trip);")

    def test_the_gate_is_asked_again_when_the_cast_ends(self):
        window_both(self, '''
    assert(ask(continent, {"waypoint", "tanaris"}).empty());
    continent.combat = true;
    DC::Bounties::TravelCastDone(&continent); continent.m_Events.Update();
    assert(trips.empty() && said.back() == "''' + COMBAT + '''");''',
                    "std::string const said = why ? std::string(why) : Go(player, trip);",
                    "std::string const said = Go(player, trip);")

    def test_a_cast_that_does_not_start_is_the_answer_and_keeps_no_trip(self):
        window_both(self, '''
    continent.castResult = SPELL_FAILED_NOT_READY;
    assert(ask(continent, {"waypoint", "tanaris"}) == "You cannot travel right now.");
    DC::Bounties::TravelCastDone(&continent); continent.m_Events.Update();
    assert(trips.empty());''',
                    "            casting.erase(guid);\n            return \"You cannot", "            return \"You cannot")

    def test_a_logout_drops_the_trip(self):
        self.assertIn("casting.erase(player->GetGUID().GetRawValue());", definition(SERVER, "void OnPlayerLogout("))

# --- 2b. the travel cast's spell data and damage interrupt (dm9vg.10), cut out of dc_bounties.cpp -----------------------

CAST_DOUBLES = r"""
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
using uint32 = std::uint32_t; using int32 = std::int32_t;
#define LOG_ERROR(...) (void)0
enum { SPELL_INTERRUPT_FLAG_MOVEMENT = 0x01, SPELL_INTERRUPT_FLAG_INTERRUPT = 0x08, SPELL_INTERRUPT_FLAG_ABORT_ON_DMG = 0x10 };
enum CurrentSpellTypes { CURRENT_GENERIC_SPELL = 1 };
enum SpellState { SPELL_STATE_PREPARING = 1, SPELL_STATE_CASTING = 2 };
namespace DC::Combat::Shells { constexpr uint32 BountyTravel = 83601; }
struct SpellCastTimesEntry { uint32 ID; int32 CastTime; };
struct Store {
    std::vector<SpellCastTimesEntry> rows{{1, 0}, {4, 1500}, {14, 3000}, {15, 4000}};
    uint32 GetNumRows() const { return 20; }
    SpellCastTimesEntry const* LookupEntry(uint32 id) const { for (auto& r : rows) if (r.ID == id) return &r; return nullptr; }
} sSpellCastTimesStore;
double tunable = 1500;
namespace DC::Tunables { double Get(char const* category, char const* name) { assert(std::string(category) == "rifts" && std::string(name) == "bounty_travel_cast_ms"); return tunable; } }
struct SpellInfo { uint32 Id = 0; uint32 InterruptFlags = 0; SpellCastTimesEntry const* CastTimeEntry = nullptr; };
struct Spell { SpellInfo info; SpellState state = SPELL_STATE_PREPARING; SpellInfo const* GetSpellInfo() const { return &info; } SpellState getState() const { return state; } };
struct Unit {
    bool player = true; Spell* current = nullptr; std::vector<uint32> interrupted;
    bool IsPlayer() const { return player; } Spell* GetCurrentSpell(CurrentSpellTypes) const { return current; }
    void InterruptNonMeleeSpells(bool, uint32 id) { interrupted.push_back(id); }
};
struct Hooks {
"""


def cast_source(server=SERVER):
    return (CAST_DOUBLES + definition(server, "void OnLoadSpellCustomAttr(SpellInfo* info)") + "\n"
            + definition(server, "void OnDamage(Unit*, Unit* victim, uint32& damage)") + "\n};\nint main() {\n    Hooks hooks;\n")


def cast_both(test, body, old, new):
    ok, out = run(cast_source() + body + "\n    return 0;\n}\n")
    test.assertTrue(ok, out)
    ok, out = run(cast_source(mutate(SERVER, old, new)) + body + "\n    return 0;\n}\n")
    test.assertFalse(ok, "mutation survived: " + new)


class TravelCastRules(unittest.TestCase):
    def test_moving_an_interrupt_or_damage_stops_it_and_its_length_is_the_tunable(self):
        cast_both(self, """
    SpellInfo travel; travel.Id = 83601; hooks.OnLoadSpellCustomAttr(&travel);
    assert(travel.InterruptFlags == (SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT | SPELL_INTERRUPT_FLAG_ABORT_ON_DMG));
    assert(travel.CastTimeEntry && travel.CastTimeEntry->CastTime == 1500);
    tunable = 4000; SpellInfo longer; longer.Id = 83601; hooks.OnLoadSpellCustomAttr(&longer);
    assert(longer.CastTimeEntry->CastTime == 4000);
    tunable = 1234; SpellInfo none; none.Id = 83601; hooks.OnLoadSpellCustomAttr(&none);
    assert(!none.CastTimeEntry);                         // no row of that length: the spell's own
    SpellInfo other; other.Id = 81167; hooks.OnLoadSpellCustomAttr(&other);
    assert(!other.InterruptFlags && !other.CastTimeEntry);""",
                  "SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT | SPELL_INTERRUPT_FLAG_ABORT_ON_DMG;\n"
                  "                auto const ms = static_cast<int32>(DC::Tunables::Get(\"rifts\", \"bounty_travel_cast_ms\"));",
                  "SPELL_INTERRUPT_FLAG_INTERRUPT | SPELL_INTERRUPT_FLAG_ABORT_ON_DMG;\n"
                  "                auto const ms = static_cast<int32>(DC::Tunables::Get(\"rifts\", \"bounty_travel_cast_ms\"));")

    def test_the_length_follows_the_tunable(self):
        cast_both(self, """
    tunable = 4000; SpellInfo travel; travel.Id = 83601; hooks.OnLoadSpellCustomAttr(&travel);
    assert(travel.CastTimeEntry && travel.CastTimeEntry->CastTime == 4000);""",
                  "if (time->CastTime == ms)\n                        {\n                            info->CastTimeEntry = time;\n"
                  "                            return;",
                  "if (time->CastTime == 1500)\n                        {\n                            info->CastTimeEntry = time;\n"
                  "                            return;")

    def test_any_damage_interrupts_the_travel_cast_and_nothing_else(self):
        cast_both(self, """
    Spell travel; travel.info.Id = 83601; Unit victim; victim.current = &travel; uint32 hit = 5, none = 0;
    hooks.OnDamage(nullptr, &victim, none); assert(victim.interrupted.empty());
    hooks.OnDamage(nullptr, &victim, hit); assert(victim.interrupted == std::vector<uint32>{83601});
    Spell portal; portal.info.Id = 81167; Unit other; other.current = &portal;
    hooks.OnDamage(nullptr, &other, hit); assert(other.interrupted.empty());
    Spell done; done.info.Id = 83601; done.state = SPELL_STATE_CASTING; Unit late; late.current = &done;
    hooks.OnDamage(nullptr, &late, hit); assert(late.interrupted.empty());
    Unit npc; npc.player = false; npc.current = &travel; hooks.OnDamage(nullptr, &npc, hit); assert(npc.interrupted.empty());""",
                  "if (cast && cast->GetSpellInfo()->Id == DC::Combat::Shells::BountyTravel &&",
                  "if (cast && cast->GetSpellInfo()->Id != DC::Combat::Shells::BountyTravel &&")

# --- 3. the trip, cut out of dc_open_rift.cpp -------------------------------------------------------------------------

TRIP_DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
struct ObjectGuid { std::uint64_t raw; std::uint64_t GetRawValue() const { return raw; } };
namespace DC::Rifts::OpenRift {
    struct OpenZone { std::string key, name, entryTunable; std::uint32_t zoneId = 0, act = 0, mapId = 0; };
    std::vector<OpenZone> zones = {{"ungoro", "Un'Goro Crater", "open_rift_entry", 490, 2, 751}, {"tanaris", "Tanaris", "open_rift_entry_tanaris", 440, 2, 751},
                                   {"hinterlands", "The Hinterlands", "open_rift_entry_hinterlands", 47, 3, 752}};
    struct Entry { float x = 0, y = 0, z = 0, o = 0; bool set = false; };
    Entry EntryPoint(OpenZone const& zone) { return zone.key != "tanaris" ? Entry{1, 2, 3, 4, true} : Entry{}; }
    std::mutex mutex; std::unordered_map<std::uint64_t, std::string> asked;
}
struct Player;
// The copy router (bounties R0, test_copy_router.py): the copy the trip is routed to, then the teleport into it.
namespace DC::Rifts::OpenRift {
    std::uint32_t routed = 12; std::string routeError;
    std::uint32_t SendTo(Player*, OpenZone const&, std::string& error) { error = routeError; return routed; }
    bool Arrive(Player* p, std::uint32_t, OpenZone const& zone, float x, float y, float z, float o);
}
// The core's copy pick: the instance a trip to `map` would land in (0: a new copy); a live rift is one of them.
std::uint32_t destination = 0; std::uint32_t liveRift = 0, liveMap = 751, pickedMap = 0; int lastDifficulty = -1;
struct InstanceSaveMgr { std::uint32_t PlayerGetDestinationInstanceId(Player*, std::uint32_t map, int difficulty) {
    pickedMap = map; lastDifficulty = difficulty; return destination; } } instanceSaveMgr, *sInstanceSaveMgr = &instanceSaveMgr;
namespace DC::Rifts { bool IsLiveInstance(std::uint32_t map, std::uint32_t instance) { return map == liveMap && instance && instance == liveRift; } }
struct Player {
    ObjectGuid guid{7}; bool works = true; int teleports = 0; float x = 0; std::uint32_t map = 0; std::string zoneAtTeleport;
    ObjectGuid GetGUID() const { return guid; } int GetDifficulty(bool raid) const { return raid ? 9 : 0; }
    bool TeleportTo(std::uint32_t to, float px, float, float, float) {
        ++teleports; map = to; x = px; zoneAtTeleport = DC::Rifts::OpenRift::asked[guid.raw]; return works;
    }
};
bool DC::Rifts::OpenRift::Arrive(Player* p, std::uint32_t, OpenZone const& zone, float x, float y, float z, float o) { return p->TeleportTo(zone.mapId, x, y, z, o); }
namespace DC::Rifts {
'''


def compile_trip(body, source=OPEN):
    code = TRIP_DOUBLES + definition(source, "std::string TravelToOpenZone(") + "\n}\nint main() {\n" + r'''
    using DC::Rifts::TravelToOpenZone; using DC::Rifts::OpenRift::asked;
    Player p; float const spot[4] = {9, 8, 7, 6};
''' + body + "\n    return 0;\n}\n"
    return run(code)


def trip_both(test, body, old, new):
    ok, out = compile_trip(body)
    test.assertTrue(ok, out)
    ok, out = compile_trip(body, mutate(OPEN, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class Trip(unittest.TestCase):
    def test_a_zone_without_an_entrance_moves_nobody(self):
        trip_both(self, '''
    assert(TravelToOpenZone(&p, "tanaris", nullptr) == "That zone has no way in yet.");
    assert(TravelToOpenZone(&p, "duskwood", spot) == "That zone has no way in yet.");
    assert(p.teleports == 0 && asked.empty());''',
                  "if (!entry.set) // a zone off the sheet", "if (false) // a zone off the sheet")

    def test_the_zone_edge_holds_the_new_zone_when_the_player_lands(self):
        trip_both(self, '''
    asked[7] = "tanaris";                                                      // last trip's zone
    assert(TravelToOpenZone(&p, "ungoro", spot).empty() && p.x == 9 && p.zoneAtTeleport == "ungoro" && asked[7] == "ungoro");
    assert(TravelToOpenZone(&p, "ungoro", nullptr).empty() && p.x == 1);      // the waypoint: the zone's entrance''',
                  "            OpenRift::asked[guid] = zone->key; // before the move", "            // before the move")

    def test_never_into_the_partys_live_rift(self):
        trip_both(self, '''
    destination = 40; liveRift = 40;                                           // the party runs an open-zone rift in copy 40
    assert(TravelToOpenZone(&p, "ungoro", spot) == "Your party is in a rift; travel after it closes.");
    assert(p.teleports == 0 && asked.empty() && lastDifficulty == 0);         // the dungeon difficulty, as the core asks
    liveRift = 41;                                                             // a rift elsewhere: the copy is open world
    assert(TravelToOpenZone(&p, "ungoro", spot).empty() && p.teleports == 1);
    destination = 0; liveRift = 0;                                             // no copy yet: the core makes one
    assert(TravelToOpenZone(&p, "ungoro", nullptr).empty() && p.teleports == 2);''',
                  "if (copy && IsLiveInstance(zone->mapId, copy))", "if (false)")

    def test_the_trip_is_on_the_zones_map(self):
        # bounty acts A4 (diablocraft-hyoic.7): a 752 zone's trip asks the core for a 752 copy and lands on 752
        body = '''
    assert(TravelToOpenZone(&p, "ungoro", spot).empty() && pickedMap == 751 && p.map == 751);
    assert(TravelToOpenZone(&p, "hinterlands", spot).empty() && pickedMap == 752 && p.map == 752 && asked[7] == "hinterlands");
    destination = 40; liveRift = 40; liveMap = 751;                            // a live rift on 751 with the same instance id
    assert(TravelToOpenZone(&p, "hinterlands", spot).empty());                 // is not the 752 copy
    liveMap = 752;
    assert(TravelToOpenZone(&p, "hinterlands", spot) == "Your party is in a rift; travel after it closes.");'''
        for old, new in (("PlayerGetDestinationInstanceId(player, zone->mapId,", "PlayerGetDestinationInstanceId(player, 751,"),
                         ("IsLiveInstance(zone->mapId, copy)", "IsLiveInstance(751, copy)")):
            with self.subTest(mutation=new):
                trip_both(self, body, old, new)

    def test_a_failed_teleport_puts_the_old_zone_back(self):
        trip_both(self, '''
    p.works = false; asked[7] = "tanaris";
    assert(TravelToOpenZone(&p, "ungoro", spot) == "The way there would not open." && asked[7] == "tanaris");
    asked.erase(7);
    assert(TravelToOpenZone(&p, "ungoro", spot) == "The way there would not open." && !asked.count(7));''',
                  "            OpenRift::asked[guid] = was;\n", "            ;\n")

    def test_a_logout_keeps_the_zone(self):
        # A source scan (the hook needs the core): a player who logs out in Tanaris logs back in sealed to Tanaris, not to
        # the sheet's first zone.
        self.assertNotIn("asked.erase", definition(OPEN, "void OnPlayerLogout("))


# --- 4. the arrival check (diablocraft-ryacm), cut out of dc_open_rift.cpp and dc_rifts.cpp ----------------------------

RIFTS = (SRC / "rifts/dc_rifts.cpp").read_text(encoding="utf-8")
PARTY_IN_RIFT = "Your party is in a rift; travel after it closes."

ARRIVAL_DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
typedef std::uint32_t uint32; typedef std::uint64_t uint64;
struct ObjectGuid { uint64 raw; uint64 GetRawValue() const { return raw; } bool operator==(ObjectGuid o) const { return raw == o.raw; } };
template <> struct std::hash<ObjectGuid> { std::size_t operator()(ObjectGuid g) const { return g.raw; } };
struct WorldLocation { uint32 map = 0; };
struct Player {
    ObjectGuid guid{7}; uint32 mapId = 751, instanceId = 40; bool gm = false, teleporting = false;
    std::vector<std::string> said; std::vector<uint32> trips;
    ObjectGuid GetGUID() const { return guid; } uint32 GetMapId() const { return mapId; } uint32 GetInstanceId() const { return instanceId; }
    bool IsGameMaster() const { return gm; } bool IsBeingTeleported() const { return teleporting; } Player* GetSession() { return this; }
    float GetPositionX() const { return 0; } float GetPositionY() const { return 0; } float GetPositionZ() const { return 0; }
    bool TeleportTo(WorldLocation const& where) { trips.push_back(where.map); return true; }
};
struct ChatHandler { Player* p; explicit ChatHandler(Player* session) : p(session) {} void SendSysMessage(char const* t) { p->said.push_back(t); } };
namespace DC::World { bool HubLocation(WorldLocation& where) { where.map = 1; return true; } }   // the Sanctum: map 1 here
namespace DC::Rifts {
    struct Rift { uint64 id = 0; std::string state = "open"; };
    struct Book {
        std::map<std::pair<uint32, uint32>, Rift> runs;   // (instance, map) -> run
        Rift const* FindByInstance(uint32 instance, uint32 map) { auto f = runs.find({instance, map}); return f == runs.end() ? nullptr : &f->second; }
    } live;
    std::mutex riftMutex, workMutex;
    std::unordered_map<ObjectGuid, uint64> playerRun;      // the membership cache
    void ForcedTeleport(Player* p, std::function<void(Player*)> const& move) { move(p); }
'''

ARRIVAL_OPEN_DOUBLES = r'''
namespace DC::Rifts::OpenRift {
    bool IsOpenZoneMap(uint32 m) { return m == 751; } std::mutex mutex; std::unordered_set<uint64> arrived;
    struct OpenZone {}; bool wall = false; int bounces = 0;
    bool InWallSpot(uint32 m, float, float, float) { return wall && m == 751; }
    OpenZone const* ZoneOf(Player*) { static OpenZone zone; return &zone; }
    void Bounce(Player*, OpenZone const&) { ++bounces; }
    std::mutex routerMutex; std::unordered_set<uint64> joined; int moves = 0;   // the copy router's join move (R0)
    void MoveToParty(Player*) { ++moves; }
'''

ARRIVAL_MAIN = r'''
    using namespace DC::Rifts; using DC::Rifts::OpenRift::Boundary;
    Boundary hooks;
    live.runs[{40, 751}] = Rift{5};                         // the party's open-zone rift, run 5, in copy 40
    auto arrive = [&](Player& p) { hooks.OnPlayerMapChanged(&p); hooks.OnPlayerUpdate(&p, 0); };
    auto turnedAway = [](Player const& p) { return p.trips == std::vector<uint32>{1} && p.said == std::vector<std::string>{"PARTY_IN_RIFT"}; };
    auto stayed = [](Player const& p) { return p.trips.empty() && p.said.empty(); };
'''.replace("PARTY_IN_RIFT", PARTY_IN_RIFT)


def arrival_source(open_src=OPEN, rifts_src=RIFTS):
    return (ARRIVAL_DOUBLES + definition(rifts_src, "bool OutsiderInRift(") + "\n}\n" + ARRIVAL_OPEN_DOUBLES
            + definition(open_src, "bool TurnAwayOutsider(") + "\nstruct Boundary {\n"
            + definition(open_src, "void OnPlayerMapChanged(") + "\n" + definition(open_src, "void OnPlayerUpdate(")
            + "\n};\n}\n")


def compile_arrival(body, open_src=OPEN, rifts_src=RIFTS):
    return run(arrival_source(open_src, rifts_src) + "int main() {\n" + ARRIVAL_MAIN + body + "\n    return 0;\n}\n")


def arrival_both(test, body, source, old, new):
    ok, out = compile_arrival(body)
    test.assertTrue(ok, out)
    mutated = {"open_src": mutate(OPEN, old, new)} if source == "open" else {"rifts_src": mutate(RIFTS, old, new)}
    ok, out = compile_arrival(body, **mutated)
    test.assertFalse(ok, "mutation survived: " + new)


class Arrival(unittest.TestCase):
    def test_a_traveller_landing_in_the_partys_live_rift_goes_to_the_sanctum(self):
        # The rift opened while they were on the loading screen, so nobody enrolled them. One move out, and no wall bounce
        # on top of it in the same update.
        arrival_both(self, '''
    DC::Rifts::OpenRift::wall = true;
    Player p; arrive(p);
    assert(turnedAway(p) && DC::Rifts::OpenRift::bounces == 0);''',
                     "open", "                if (first && TurnAwayOutsider(player))\n                    return;",
                     "                if (first && TurnAwayOutsider(player))\n                    ;")

    def test_the_arrival_is_marked_by_the_map_change(self):
        arrival_both(self, 'Player p; arrive(p); assert(turnedAway(p));',
                     "open", "arrived.insert(player->GetGUID().GetRawValue());", ";")

    def test_an_enrolled_member_stays(self):
        arrival_both(self, '''
    Player p; playerRun[p.guid] = 5; arrive(p); assert(stayed(p));
    Player other; other.guid = ObjectGuid{8}; playerRun[other.guid] = 4; arrive(other);   // enrolled in another party's run
    assert(turnedAway(other));''',
                     "rifts", "return found == playerRun.end() || found->second != run;", "return found == playerRun.end();")

    def test_a_copy_that_is_no_live_rift_holds_anyone(self):
        arrival_both(self, '''
    Player open; open.instanceId = 41; arrive(open); assert(stayed(open));                 // a plain open-zone copy
    live.runs[{40, 751}].state = "closed"; Player late; arrive(late); assert(stayed(late)); // the run has closed''',
                     "rifts", 'if (!here || here->state == "closed")', "if (!here)")

    def test_a_gm_in_gm_mode_stays(self):
        arrival_both(self, 'Player p; p.gm = true; arrive(p); assert(stayed(p));',
                     "open", "player->IsGameMaster() || !OutsiderInRift", "!OutsiderInRift")

    def test_checked_once_per_arrival_after_the_login_sweep(self):
        # The login sweep (OnPlayerLogin) runs between the map change and the first update and may enrol the player:
        # 7.9.7 lets a party member join at login. After that first update nobody is checked again.
        arrival_both(self, '''
    Player login; hooks.OnPlayerMapChanged(&login); playerRun[login.guid] = 5; hooks.OnPlayerUpdate(&login, 0);
    assert(stayed(login));
    playerRun.erase(login.guid); hooks.OnPlayerUpdate(&login, 0); assert(stayed(login));''',
                     "open", "if (first && TurnAwayOutsider(player))", "if (TurnAwayOutsider(player))")

    def test_the_text_is_the_trips_refusal(self):
        # the trip's refusal, the router's (bounties R0: every route refuses a party in a rift) and the arrival's
        self.assertEqual(OPEN.count('"' + PARTY_IN_RIFT + '"'), 3)


if __name__ == "__main__":
    unittest.main()
