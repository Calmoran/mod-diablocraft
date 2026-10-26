"""diablocraft-revive-choices-server + diablocraft-uxps (Revive R1): the revive choices, compiled from production.

The harness cuts the whole revive block out of dc_hardcore.cpp (Resolve, Respawn, Choose, the button rules, the
three-in-a-row count, the town spread) and drives it through the real dc_bridge.h router against a player/core double,
as test_respawn.py does for the release path (docs/contracts/revive-choices-messages.md). Every rule is then removed
one at a time from the production text and the run must go red: a test that cannot fail proves nothing.
"""
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import host_cmake

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "mod-diablocraft/src"
MAIN = ROOT / "mod-diablocraft/tests/revive_choices/main.cpp"
HARDCORE = (SRC / "hardcore/dc_hardcore.cpp").read_text(encoding="utf-8")
BRIDGE = (SRC / "common/dc_bridge.h").read_text(encoding="utf-8")
GAP = (SRC / "common/dc_request_gap.h").read_text(encoding="utf-8")

PRELUDE = r'''
#include <cassert>
#include <cmath>
#include <limits>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
namespace DC::Tunables {
std::map<std::string, double> rows;   // a row that is not here is a blank one
double Get(std::string const& c, std::string const& n) { auto f = rows.find(c + "/" + n); return f == rows.end() ? 0 : f->second; }
bool Has(std::string const& c, std::string const& n) { return rows.count(c + "/" + n) != 0; }
}
'''


def definition(source, marker):
    """The full brace-balanced definition that starts at `marker`."""
    start = source.index(marker)
    end, depth = source.index("{", start) + 1, 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    # The file is clang-formatted with its code two namespaces deep; take that indent off so the mutation anchors
    # below read like the function bodies.
    return source[start:end].replace(" override", "").replace("\n        ", "\n")


def mutate(source, old, new):
    assert source.count(old) == 1, f"mutation anchor not unique: {old!r}"
    return source.replace(old, new)


def run(code):
    """Compile and run one harness; (passed, output). A harness that does not compile raises: a mutation
    that breaks the build is a bad mutation, not a red test."""
    binary = harness_env.build([MAIN], flags=["-std=gnu++17", host_cmake.undebug()], files={"program.h": code}, includes=[SRC / "common"])
    ran = harness_env.run([str(binary)], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout + ran.stderr


def production():
    """Name(Mode) and the whole revive block, from `enum class Choice` to the end of Choose."""
    start = HARDCORE.index("enum class Choice")
    block = HARDCORE[start:HARDCORE.index("void QueueLogout(Player* player)")].rstrip()
    return definition(HARDCORE, "char const* Name(Mode mode)") + "\n" + block.replace("\n        ", "\n") + "\n"


DOUBLES = r'''
#include <cstdint>
#include <functional>
#include <algorithm>
using uint32 = std::uint32_t;
constexpr uint32 PHASEMASK_NORMAL = 1;
constexpr float INVALID_HEIGHT = -100000.0f;
constexpr float DEFAULT_COLLISION_HEIGHT = 2.03128f;
enum LineOfSightChecks { LINEOFSIGHT_ALL_CHECKS = 3 };
namespace VMAP { enum class ModelIgnoreFlags : uint32 { Nothing = 0 }; }
struct WorldLocation {
    uint32 map = 0; float x = 0, y = 0, z = 0;
    WorldLocation() = default;
    WorldLocation(uint32 m, float a, float b, float c) : map(m), x(a), y(b), z(c) {}
    uint32 GetMapId() const { return map; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
    void Relocate(float a, float b, float c) { x = a; y = b; z = c; }
    bool operator==(WorldLocation const& o) const { return map == o.map && x == o.x && y == o.y && z == o.z; }
};
// The hub map (530 in this double) and what the town spread asks it. Ground is 40 everywhere unless a test says otherwise.
struct Map {
    uint32 id = 530;
    mutable int reads = 0;                 // every terrain question asked: a revive must ask none (diablocraft-bqo2)
    uint32 GetId() const { return id; }
    float minHeight = -500;
    std::function<float(float, float)> ground = [](float, float) { return 40.0f; };
    std::function<bool(float, float)> water = [](float, float) { return false; };
    std::function<bool(float, float)> sight = [](float, float) { return true; };
    std::vector<std::string> asked;
    float GetMinHeight(float, float) const { return minHeight; }
    float GetHeight(uint32 phase, float x, float y, float z, bool vmap, float search) const { ++reads; assert(phase == 1 && vmap && z == 43.0f && search == 6.0f); return ground(x, y); }
    bool IsInWater(uint32, float x, float y, float, float) const { ++reads; return water(x, y); }
    bool isInLineOfSight(float x1, float y1, float z1, float x2, float y2, float, uint32, LineOfSightChecks, VMAP::ModelIgnoreFlags) const {
        ++reads;
        assert((x1 == 10 || x1 == 11) && y1 == 30 && z1 == 42.0f);   // from the spawn (or where a test moved it), eye-high
        return sight(x2, y2);
    }
} theMap;
std::vector<double> rolls; std::size_t rollAt = 0;   // what rand_norm() gives, in order; 0.5 when empty
double rand_norm() { return rolls.empty() ? 0.5 : rolls[rollAt++ % rolls.size()]; }
enum class DeathState { Alive, JustDied, Corpse, Dead };
std::vector<std::string> events;   // what the core was asked, in order
std::vector<std::string> said;     // what the player was told
struct Session {};
struct ChatHandler {
    explicit ChatHandler(Session*) {}
    void SendSysMessage(char const* text) { said.push_back(text); }
};
#define LOG_INFO(...) ((void)0)
struct Guid { uint32 id = 5; std::uint64_t GetRawValue() const { return id; } uint32 GetCounter() const { return id; } };
struct Player {
    uint32 guid = 5;
    DeathState state = DeathState::Corpse;
    bool veto = false, teleporting = false, coreRefusesTeleport = false, graveyard = false;
    int health = 0, bones = 0;
    WorldLocation at{602, 1, 2, 3};
    Session session;
    bool IsAlive() const { return state == DeathState::Alive; }
    DeathState getDeathState() const { return state; }
    void KillPlayer() { events.push_back("kill"); state = DeathState::Corpse; }
    bool IsBeingTeleported() const { return teleporting; }
    Guid GetGUID() const { return Guid{guid}; }
    Map* GetMap() const { return &theMap; }
    float GetPositionX() const { return at.x; }
    float GetPositionY() const { return at.y; }
    float GetPositionZ() const { return at.z; }
    void ResurrectPlayer(float pct) { assert(pct == 1.0f); if (!veto) { state = DeathState::Alive; events.push_back("resurrect"); } }
    void SpawnCorpseBones() { ++bones; }
    int GetMaxHealth() const { return 12345; }
    void SetHealth(int n) { health = n; }
    Session* GetSession() { return &session; }
    bool TeleportTo(WorldLocation const& to) {
        if (coreRefusesTeleport) return false;
        events.push_back("teleport " + std::to_string(int(to.map)) + ":" + std::to_string(int(to.x)));
        at = to;
        return true;
    }
    void RepopAtGraveyard() { graveyard = true; }   // production must never reach it
};
namespace DC::Hardcore { enum class Mode { Unchosen, Normal, Hardcore }; Mode mode = Mode::Normal; Mode Load(uint32) { return mode; } }
namespace DC::World {
bool hubLoaded = true, inHub = false;
float hubX = 10;
bool HubLocation(WorldLocation& out) { if (!hubLoaded) return false; out = WorldLocation(530, hubX, 30, 40); return true; }
bool IsInHub(Player const*) { return inHub; }
}
namespace DC::Rifts {
struct Rift { std::string mode = "nr"; };
bool inRift = false;           // in a rift instance whose run is still open
std::string riftMode = "nr";   // "gr" makes it a Greater Rift
bool Current(Player const*, Rift& rift) { rift.mode = riftMode; return inRift; }
bool EntryPosition(Player const*, WorldLocation& out) { if (!inRift) return false; out = WorldLocation(602, 100, 200, 300); return true; }
bool townRefused = false;      // a live Greater Rift (diablocraft-214r): no revive in town
unsigned waitLeft = 0;         // and the seconds a dead character still waits there
bool GreaterRiftTownReviveRefused(Player const*) { return townRefused; }
unsigned GreaterRiftReviveWaitLeft(Player const*) { return waitLeft; }
}
namespace DC::Rifts::TownPortal {
bool opens = true;
bool OpenPair(Player* p) { if (!opens) return false; events.push_back("portal " + std::to_string(int(p->at.map)) + ":" + std::to_string(int(p->at.x))); return true; }
}
'''

DRIVER = r'''
using DC::Bridge::Outcome;
struct Rig {
    std::vector<std::string> sent;
    DC::Bridge::Router<Player> router{[this](Player*, std::string const& prefix, std::string const& record) { sent.push_back(prefix + "\t" + record); }};
    Rig() {
        DC::Tunables::rows["combat/revive_burst"] = 50;
        DC::Tunables::rows["combat/revive_per_second"] = 50;
        DC::Tunables::rows["combat/revive_body_limit"] = 3;      // the D3 row, d3_value 3
        bool ok = router.Add("DCREVIVE", {"combat", "revive_burst", "revive_per_second"}, DC::Hardcore::Choose);
        assert(ok);
    }
    void die(Player& p) { p.state = DeathState::Corpse; }
    // One request from a fresh dead, Normal character standing in the dungeon at 602:1.
    std::string ask(Player& p, std::string const& message) {
        events.clear(); said.clear(); sent.clear();
        router.Dispatch(&p, message, 0);
        return sent.empty() ? "" : sent.back();
    }
};
'''


def harness(body, source=None):
    code = PRELUDE + "#include <string>\n#include <vector>\n" + GAP.replace('#ifndef DC_REQUEST_GAP_H', '#ifndef DC_REQUEST_GAP_H_T')
    code = code.replace("#define DC_REQUEST_GAP_H\n", "#define DC_REQUEST_GAP_H_T\n")
    code += BRIDGE.replace('#include "dc_request_gap.h"', '').replace('#include "dc_tunables.h"', '')
    code += DOUBLES + "namespace DC::Hardcore {\nnamespace {\n" + (source if source is not None else production())
    code += "\n}\n}\n" + DRIVER + "\nint main() {\n    using namespace DC;\n    Rig rig; Player p;\n" + body + "\n    return 0;\n}\n"
    return code


# `Choose`/`Respawn` sit in an anonymous namespace in production; the harness reaches them as DC::Hardcore::Choose.
def build(body, source=None):
    return harness(body, source)


def passes(body, source=None):
    ok, out = run(build(body, source))
    return ok, out


def both(test, body, old, new):
    """Green on production; red on the production text with one rule taken out."""
    ok, out = passes(body)
    test.assertTrue(ok, out)
    ok, out = passes(body, mutate(production(), old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class Choices(unittest.TestCase):
    def test_here_revives_where_it_fell_with_full_health(self):
        both(self, '''
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here");
    assert(p.IsAlive() && p.health == 12345 && p.bones == 1);
    assert((events == std::vector<std::string>{"resurrect"}));          // no move at all
    assert(p.at == WorldLocation(602, 1, 2, 3) && !p.graveyard);
''', "    if (to.done != Choice::Here)\n    {", "    if (true)\n    {")

    def test_town_lands_on_the_hub_spawn_and_opens_no_portal_outside_a_rift(self):
        both(self, '''
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
    assert(p.IsAlive() && p.health == 12345);
    assert((events == std::vector<std::string>{"resurrect", "teleport 530:10"}));   // open world: no way back
    assert(p.at == WorldLocation(530, 10, 30, 40) && !p.graveyard);                 // no spread row: the spawn itself
''', "to.wayBack = DC::Rifts::Current(player, rift);", "to.wayBack = true;")

    def test_town_from_a_rift_opens_the_pair_where_it_fell_before_the_move(self):
        both(self, '''
    DC::Rifts::inRift = true;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
    assert((events == std::vector<std::string>{"resurrect", "portal 602:1", "teleport 530:10"}));
''', "if (to.wayBack && !DC::Rifts::TownPortal::OpenPair(player))", "if (false && !DC::Rifts::TownPortal::OpenPair(player))")

    def test_the_pair_is_opened_before_the_move_not_after(self):
        source = production()
        block_start = source.index("        // The pair is opened where it fell")
        block_end = source.index("        if (!player->TeleportTo(to.at))")
        block = source[block_start:block_end]
        moved = source[:block_start] + source[block_end:]
        after = moved.index("            to.done = Choice::Here;\n") + len("            to.done = Choice::Here;\n")
        moved = moved[:after] + block + moved[after:]
        body = '''
    DC::Rifts::inRift = true;
    rig.ask(p, "DCREVIVE\\ttown");
    assert((events == std::vector<std::string>{"resurrect", "portal 602:1", "teleport 530:10"}));
'''
        ok, out = passes(body)
        self.assertTrue(ok, out)
        ok, out = passes(body, moved)
        self.assertFalse(ok, "the portal must be opened before the character is moved")

    def test_a_portal_that_will_not_open_still_revives_in_town(self):
        both(self, '''
    DC::Rifts::inRift = true; DC::Rifts::TownPortal::opens = false;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
    assert((events == std::vector<std::string>{"resurrect", "teleport 530:10"}));
    assert(said.size() == 2 && said[0].find("no way back") != std::string::npos);
''', "if (to.wayBack && !DC::Rifts::TownPortal::OpenPair(player))\n            chat.SendSysMessage(",
             "if (to.wayBack && DC::Rifts::TownPortal::OpenPair(player))\n            chat.SendSysMessage(")

    def test_checkpoint_lands_on_the_floors_arrival_point_inside_the_rift(self):
        both(self, '''
    DC::Rifts::inRift = true;
    assert(rig.ask(p, "DCREVIVE\\tcheckpoint") == "DCREVIVE\\tR|checkpoint|checkpoint");
    assert((events == std::vector<std::string>{"resurrect", "teleport 602:100"}));
    assert(p.at == WorldLocation(602, 100, 200, 300) && !p.graveyard);
    assert(said.back().find("checkpoint") != std::string::npos);
''', "to.done = Choice::Checkpoint;", "to.done = Choice::Here;")

    def test_checkpoint_outside_a_rift_is_refused_and_revives_nobody(self):
        # It used to fall back to `here`; that would hand a void or third-in-a-row body the revive it was refused.
        both(self, '''
    assert(rig.ask(p, "DCREVIVE\\tcheckpoint") == "DCREVIVE\\tX|There is no checkpoint here.");   // open world, or a rift whose run closed
    assert(events.empty() && !p.IsAlive() && !p.graveyard);
''', "    if (!DC::Rifts::EntryPosition(player, place))", "    if (false)")

    def test_checkpoint_in_the_hub_is_refused_as_the_same_spot_as_town(self):
        both(self, '''
    DC::World::inHub = true;
    assert(rig.ask(p, "DCREVIVE\\tcheckpoint") == "DCREVIVE\\tX|There is no checkpoint in town.");
    assert(events.empty() && !p.IsAlive());
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");   // town from the hub is still the spawn
''', "return DC::World::IsInHub(player) ?", "return false ?")

    def test_town_with_no_hub_loaded_is_refused(self):
        both(self, '''
    DC::World::hubLoaded = false;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tX|Town is not available right now.");
    assert(events.empty() && !p.IsAlive() && !p.graveyard);
''', "    if (!DC::World::HubLocation(place))", "    if (false)")

    def test_a_move_the_core_refuses_leaves_it_alive_where_it_fell(self):
        both(self, '''
    p.coreRefusesTeleport = true;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|here");
    assert(p.IsAlive() && p.at == WorldLocation(602, 1, 2, 3) && !p.graveyard);
    assert(said.back().find("where you fell") != std::string::npos);
''', "        if (!player->TeleportTo(to.at))\n            to.done = Choice::Here;", "        player->TeleportTo(to.at);")


class Refusals(unittest.TestCase):
    def test_a_living_character_gets_nothing(self):
        both(self, '''
    p.state = DeathState::Alive; p.at = WorldLocation(530, 5, 5, 5);
    for (char const* verb : {"here", "town", "checkpoint", "options"}) {
        DC::Rifts::inRift = true;
        assert(rig.ask(p, std::string("DCREVIVE\\t") + verb) == "DCREVIVE\\tX|You are not dead.");
        assert(events.empty() && p.bones == 0 && p.health == 0 && p.at == WorldLocation(530, 5, 5, 5));
    }
''', '    if (player.IsAlive())\n        throw DC::Bridge::Refusal("You are not dead.");',
             '    if (false)\n        throw DC::Bridge::Refusal("You are not dead.");')

    def test_a_hardcore_character_gets_nothing(self):
        both(self, '''
    DC::Hardcore::mode = DC::Hardcore::Mode::Hardcore;
    for (char const* verb : {"here", "town", "checkpoint", "options"}) {
        DC::Rifts::inRift = true;
        assert(rig.ask(p, std::string("DCREVIVE\\t") + verb) == "DCREVIVE\\tX|Hardcore deaths are final.");
        assert(events.empty() && !p.IsAlive() && p.bones == 0 && p.at == WorldLocation(602, 1, 2, 3));
    }
''', "if (Load(player.GetGUID().GetCounter()) == Mode::Hardcore)", "if (false)")

    def test_a_resurrection_another_module_vetoes_leaves_it_dead(self):
        both(self, '''
    p.veto = true; DC::Rifts::inRift = true;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tX|You could not be revived.");
    assert(!p.IsAlive() && p.health == 0 && p.bones == 0 && events.empty() && p.at == WorldLocation(602, 1, 2, 3));
''', "    if (!player->IsAlive())\n        return false;", "    if (false)\n        return false;")

    def test_a_character_in_the_middle_of_a_teleport_is_asked_to_wait(self):
        both(self, '''
    p.teleporting = true;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tX|Try again in a moment.");
    assert(events.empty() && !p.IsAlive());
''', "    if (player.IsBeingTeleported())\n        throw", "    if (false)\n        throw")

    def test_a_death_the_core_has_not_processed_finishes_first(self):
        both(self, '''
    p.state = DeathState::JustDied;
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here");
    assert((events == std::vector<std::string>{"kill", "resurrect"}));
''', "    if (player.getDeathState() == DeathState::JustDied)\n        player.KillPlayer();", "")

    def test_bad_requests_are_refused_and_change_nothing(self):
        both(self, '''
    for (char const* message : {"DCREVIVE", "DCREVIVE\\t", "DCREVIVE\\tgraveyard", "DCREVIVE\\ttown\\there", "DCREVIVE\\ttown\\t",
                                "DCREVIVE\\tHERE", "DCREVIVE\\tcorpse", "DCREVIVE\\toptions\\t1", "DCREVIVE\\trift",
                                "DCREVIVE\\tcheckpoint\\tx", "DCREVIVE\\tcheckpoints"}) {
        assert(rig.ask(p, message) == std::string("DCREVIVE\\tX|") + DC::Bridge::TextMalformed);
        assert(events.empty() && !p.IsAlive());
    }
''', "    if (!verb || request.Count() != 1)", "    if (!verb)")

    def test_an_unknown_verb_is_not_taken_for_here(self):
        both(self, '''
    assert(rig.ask(p, "DCREVIVE\\trevive") == std::string("DCREVIVE\\tX|") + DC::Bridge::TextMalformed);   // 10 bytes or less: only the verb rule can catch it
    assert(events.empty() && !p.IsAlive());
''', '    else if (*verb != "here" && !options)\n        throw', '    else if (false)\n        throw')

    def test_the_longest_verb_fits_the_token_the_route_reads(self):
        both(self, '''
    DC::Rifts::inRift = true;
    assert(rig.ask(p, "DCREVIVE\\tcheckpoint") == "DCREVIVE\\tR|checkpoint|checkpoint");
''', "request.Token(0, 10)", "request.Token(0, 8)")


class Options(unittest.TestCase):
    # O|corpse|checkpoint|town: each field is "1" (works now) or the reason it does not.
    def test_every_button_works_inside_an_open_rift(self):
        both(self, '''
    DC::Rifts::inRift = true;
    assert(rig.ask(p, "DCREVIVE\\toptions") == "DCREVIVE\\tO|1|1|1");
    assert(events.empty() && !p.IsAlive());                              // asking revives nobody
''', 'wire.Record({"O", corpse.empty() ? "1" : corpse,', 'wire.Record({"O", corpse.empty() ? "0" : corpse,')

    def test_the_open_world_has_no_checkpoint_and_says_why(self):
        both(self, '''
    assert(rig.ask(p, "DCREVIVE\\toptions") == "DCREVIVE\\tO|1|There is no checkpoint here.|1");
''', 'checkpoint.empty() ? "1" : checkpoint,', 'checkpoint.empty() ? "1" : "",')

    def test_the_hub_has_no_checkpoint_either(self):
        both(self, '''
    DC::World::inHub = true;
    assert(rig.ask(p, "DCREVIVE\\toptions") == "DCREVIVE\\tO|1|There is no checkpoint in town.|1");
''', 'town.empty() ? "1" : town});', 'town.empty() ? "0" : town});')

    def test_a_live_greater_rift_greys_town_and_keeps_the_other_two(self):
        both(self, '''
    DC::Rifts::inRift = true; DC::Rifts::riftMode = "gr"; DC::Rifts::townRefused = true;
    assert(rig.ask(p, "DCREVIVE\\toptions") == "DCREVIVE\\tO|1|1|You cannot revive in town inside a Greater Rift.");
    DC::Rifts::townRefused = false;                                      // the Guardian is dead
    assert(rig.ask(p, "DCREVIVE\\toptions") == "DCREVIVE\\tO|1|1|1");
''', "    if (DC::Rifts::GreaterRiftTownReviveRefused(player))", "    if (false)")

    def test_a_fall_into_the_void_greys_the_corpse(self):
        both(self, '''
    p.at.z = -600;                                                       // the map's lowest point is -500
    DC::Rifts::inRift = true;
    assert(rig.ask(p, "DCREVIVE\\toptions") == "DCREVIVE\\tO|Your body is below the world.|1|1");
    DC::Rifts::inRift = false;
    assert(rig.ask(p, "DCREVIVE\\toptions") == "DCREVIVE\\tO|Your body is below the world.|There is no checkpoint here.|1");
''', "    if (DiedBelowTheMap(player))", "    if (false)")

    def test_the_limit_greys_the_corpse_with_the_number(self):
        both(self, '''
    DC::Rifts::inRift = true;
    for (int i = 0; i < 3; ++i) { rig.die(p); assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); }
    rig.die(p);
    assert(rig.ask(p, "DCREVIVE\\toptions") == "DCREVIVE\\tO|You can revive at your body only 3 times in a row.|1|1");
''', "    if (BodyLimitReached(player))", "    if (false)")

    def test_a_grey_button_is_exactly_a_refused_request(self):
        # The window greys from `O`; the server refuses the same click with the same words, in every state.
        ok, out = passes('''
    struct State { char const* name; std::function<void(Player&)> set; };
    auto threeAtTheBody = [&](Player& q) { for (int i = 0; i < 3; ++i) { rig.die(q); rig.ask(q, "DCREVIVE\\there"); } rig.die(q); };
    std::vector<State> states = {
        {"open world", [](Player&) {}},
        {"hub", [](Player&) { DC::World::inHub = true; }},
        {"no hub loaded", [](Player&) { DC::World::hubLoaded = false; }},
        {"rift", [](Player&) { DC::Rifts::inRift = true; }},
        {"rift void", [](Player& q) { DC::Rifts::inRift = true; q.at.z = -600; }},
        {"open void", [](Player& q) { q.at.z = -600; }},
        {"gr, guardian alive", [](Player&) { DC::Rifts::inRift = true; DC::Rifts::riftMode = "gr"; DC::Rifts::townRefused = true; }},
        {"gr, guardian dead", [](Player&) { DC::Rifts::inRift = true; DC::Rifts::riftMode = "gr"; }},
        {"fourth body, open", threeAtTheBody},
        {"fourth body, rift", [&](Player& q) { DC::Rifts::inRift = true; threeAtTheBody(q); }},
        {"fourth body, hub", [&](Player& q) { DC::World::inHub = true; threeAtTheBody(q); }},
    };
    char const* verbs[] = {"here", "checkpoint", "town"};
    uint32 next = 100;
    int refused = 0, worked = 0;
    for (auto const& state : states) {
        for (int field = 0; field < 3; ++field) {
            DC::World::hubLoaded = true; DC::World::inHub = false; DC::Rifts::inRift = false;
            DC::Rifts::riftMode = "nr"; DC::Rifts::townRefused = false;
            Player q; q.guid = next++; q.at = WorldLocation(602, 1, 2, 3);
            state.set(q);
            std::string o = rig.ask(q, "DCREVIVE\\toptions");
            std::vector<std::string> f; std::string rest = o.substr(o.find("O|") + 2);
            for (std::size_t from = 0;;) {
                std::size_t bar = rest.find('|', from);
                f.push_back(rest.substr(from, bar == std::string::npos ? bar : bar - from));
                if (bar == std::string::npos) break;
                from = bar + 1;
            }
            assert(f.size() == 3);                                           // nothing in a reason breaks the record
            std::string reply = rig.ask(q, std::string("DCREVIVE\\t") + verbs[field]);
            if (f[field] == "1") { assert(reply.rfind("DCREVIVE\\tR|", 0) == 0); ++worked; }
            else { assert(reply == "DCREVIVE\\tX|" + f[field]); ++refused; }
        }
    }
    assert(worked == 20 && refused == 13);                                   // 33 clicks, both sides of every rule exercised
''')
        self.assertTrue(ok, out)

    def test_asking_what_is_offered_never_revives(self):
        both(self, '''
    rig.ask(p, "DCREVIVE\\toptions");
    assert(events.empty() && !p.IsAlive() && p.bones == 0);
''', "    if (options)\n    {", "    if (false)\n    {")


class GreaterRift(unittest.TestCase):
    # Greater Rift rule 5 (diablocraft-214r): the town choice is refused, every revive waits, here and checkpoint are kept.
    def test_town_is_refused_and_here_and_checkpoint_are_kept(self):
        both(self, '''
    DC::Rifts::inRift = true; DC::Rifts::riftMode = "gr"; DC::Rifts::townRefused = true;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tX|You cannot revive in town inside a Greater Rift.");
    assert(!p.IsAlive() && events.empty());                                // nothing happened, no portal pair either
    assert(rig.ask(p, "DCREVIVE\\tcheckpoint") == "DCREVIVE\\tR|checkpoint|checkpoint");
''', "    if (DC::Rifts::GreaterRiftTownReviveRefused(player))", "    if (false)")

    def test_a_revive_inside_the_wait_is_refused_with_the_seconds(self):
        both(self, '''
    DC::Rifts::inRift = true; DC::Rifts::riftMode = "gr"; DC::Rifts::waitLeft = 5;
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tX|You can revive in 5 seconds.");
    assert(rig.ask(p, "DCREVIVE\\tcheckpoint") == "DCREVIVE\\tX|You can revive in 5 seconds.");
    assert(!p.IsAlive() && events.empty());
    DC::Rifts::waitLeft = 0;
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here");
''', "if (unsigned const wait = DC::Rifts::GreaterRiftReviveWaitLeft(&player))", "if (unsigned const wait = 0u)")

    def test_town_is_told_first_and_the_wait_comes_before_any_move(self):
        source = production()
        choose = source[source.index("void Choose("):]
        self.assertLess(choose.index("Unavailable(&player, asked)"), choose.index("GreaterRiftReviveWaitLeft(&player)"))
        self.assertLess(choose.index("GreaterRiftReviveWaitLeft(&player)"), choose.index("Destination to = Resolve(&player, asked);"))


class Void(unittest.TestCase):
    # Ruling 2026-10-09 3.3: after a death below the map, Revive at Corpse is greyed; Checkpoint and Town remain.
    def test_the_corpse_is_refused_and_the_other_two_work(self):
        both(self, '''
    p.at.z = -600; DC::Rifts::inRift = true;
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tX|Your body is below the world.");
    assert(events.empty() && !p.IsAlive());
    assert(rig.ask(p, "DCREVIVE\\tcheckpoint") == "DCREVIVE\\tR|checkpoint|checkpoint");
    rig.die(p); p.at.z = -600;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
''', "    if (DiedBelowTheMap(player))", "    if (false)")

    def test_a_body_exactly_on_the_lowest_point_is_not_a_fall(self):
        both(self, '''
    p.at.z = -500;                                                         // the core kills for z below the minimum, not at it
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here");
''', "player->GetPositionZ() < player->GetMap()", "player->GetPositionZ() <= player->GetMap()")

    def test_the_void_is_read_from_the_map_under_the_body(self):
        both(self, '''
    theMap.minHeight = 20; p.at.z = 3;                                     // a map whose floor is higher than -500
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tX|Your body is below the world.");
''', "player->GetMap()->GetMinHeight(player->GetPositionX(), player->GetPositionY())", "-500.0f")


class Limit(unittest.TestCase):
    # Ruling 2026-10-09 3.5, D3 patch 2.0.1: at most three revives at the body in a row, outside a Greater Rift.
    def test_the_fourth_revive_at_the_body_is_refused(self):
        both(self, '''
    for (int i = 0; i < 3; ++i) { rig.die(p); assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); }
    rig.die(p);
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tX|You can revive at your body only 3 times in a row.");
    assert(!p.IsAlive() && events.empty());
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tX|You can revive at your body only 3 times in a row.");   // a refusal counts for nothing
''', "found->second >= limit", "found->second > limit")

    def test_the_limit_is_the_row_not_a_constant(self):
        both(self, '''
    DC::Tunables::rows["combat/revive_body_limit"] = 1;
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here");
    rig.die(p);
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tX|You can revive at your body only 1 times in a row.");
    DC::Tunables::rows["combat/revive_body_limit"] = 5;
    for (int i = 0; i < 4; ++i) { assert(rig.ask(p, "DCREVIVE\\there")[9] == 'R'); rig.die(p); }
    assert(rig.ask(p, "DCREVIVE\\there")[9] == 'X');
''', "static_cast<unsigned>(DC::Tunables::Get(\"combat\", \"revive_body_limit\"))", "3u")

    def test_a_blank_or_zero_row_is_no_limit(self):
        both(self, '''
    DC::Tunables::rows.erase("combat/revive_body_limit");
    for (int i = 0; i < 6; ++i) { assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p); }
    DC::Tunables::rows["combat/revive_body_limit"] = 0;
    for (int i = 0; i < 6; ++i) { assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p); }
''', "    if (!limit || InGreaterRift(player))", "    if (InGreaterRift(player))")

    def test_a_checkpoint_or_town_revive_starts_the_count_again(self):
        both(self, '''
    DC::Rifts::inRift = true;
    for (int i = 0; i < 2; ++i) { assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p); }
    assert(rig.ask(p, "DCREVIVE\\tcheckpoint") == "DCREVIVE\\tR|checkpoint|checkpoint"); rig.die(p);
    for (int i = 0; i < 2; ++i) { assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p); }
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town"); rig.die(p);
    for (int i = 0; i < 3; ++i) { assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p); }
    assert(rig.ask(p, "DCREVIVE\\there")[9] == 'X');
''', "bodyRevives.erase(player->GetGUID().GetCounter());", "(void)0;")

    def test_each_character_has_its_own_count(self):
        both(self, '''
    for (int i = 0; i < 3; ++i) { rig.die(p); rig.ask(p, "DCREVIVE\\there"); }
    rig.die(p);
    assert(rig.ask(p, "DCREVIVE\\there")[9] == 'X');
    Player other; other.guid = 6;
    assert(rig.ask(other, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here");
''', "bodyRevives.find(player->GetGUID().GetCounter())", "bodyRevives.find(5)")

    def test_inside_a_greater_rift_there_is_no_limit_and_nothing_is_counted(self):
        both(self, '''
    DC::Rifts::inRift = true; DC::Rifts::riftMode = "gr";
    for (int i = 0; i < 6; ++i) { assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p); }
    DC::Rifts::riftMode = "nr";                                            // out in an ordinary rift: the six counted for nothing
    for (int i = 0; i < 3; ++i) { assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p); }
    assert(rig.ask(p, "DCREVIVE\\there")[9] == 'X');
''', "    else if (!free)", "    else")

    def test_a_greater_rift_is_not_limited_even_after_three_outside(self):
        both(self, '''
    DC::Rifts::inRift = true;
    for (int i = 0; i < 3; ++i) { rig.ask(p, "DCREVIVE\\there"); rig.die(p); }
    assert(rig.ask(p, "DCREVIVE\\there")[9] == 'X');
    DC::Rifts::riftMode = "gr";
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here");
''', "    if (!limit || InGreaterRift(player))", "    if (!limit)")

    def test_a_greater_rift_body_revive_does_not_break_the_run(self):
        both(self, '''
    DC::Rifts::inRift = true;
    for (int i = 0; i < 2; ++i) { rig.ask(p, "DCREVIVE\\there"); rig.die(p); }
    DC::Rifts::riftMode = "gr";
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p);
    DC::Rifts::riftMode = "nr";
    assert(rig.ask(p, "DCREVIVE\\there") == "DCREVIVE\\tR|here|here"); rig.die(p);       // the third outside, not the fourth
    assert(rig.ask(p, "DCREVIVE\\there")[9] == 'X');
''', "bool const free = done == Choice::Here && InGreaterRift(player);", "bool const free = false;")

    def test_the_count_is_dropped_when_the_character_is_deleted(self):
        self.assertIn("bodyRevives.erase(low);", HARDCORE[HARDCORE.index("void OnPlayerDelete("):])


class Release(unittest.TestCase):
    # Release, the release timer and a login while dead: the body, else the checkpoint, else town.
    def test_the_body_when_it_works(self):
        both(self, '''
    assert(DC::Hardcore::ReleaseChoice(&p) == DC::Hardcore::Choice::Here);
''', "for (Choice choice : {Choice::Here, Choice::Checkpoint, Choice::Town})", "for (Choice choice : {Choice::Town, Choice::Here})")

    def test_a_void_body_goes_to_the_checkpoint_else_town(self):
        both(self, '''
    p.at.z = -600;
    assert(DC::Hardcore::ReleaseChoice(&p) == DC::Hardcore::Choice::Town);                 // open world: no checkpoint
    DC::World::inHub = true;
    assert(DC::Hardcore::ReleaseChoice(&p) == DC::Hardcore::Choice::Town);                 // the hub: none either
    DC::World::inHub = false; DC::Rifts::inRift = true;
    assert(DC::Hardcore::ReleaseChoice(&p) == DC::Hardcore::Choice::Checkpoint);           // a rift floor
''', "for (Choice choice : {Choice::Here, Choice::Checkpoint, Choice::Town})", "for (Choice choice : {Choice::Here, Choice::Town})")

    def test_a_fourth_body_goes_to_the_checkpoint_else_town(self):
        both(self, '''
    for (int i = 0; i < 3; ++i) { rig.die(p); rig.ask(p, "DCREVIVE\\there"); }
    rig.die(p);
    assert(DC::Hardcore::ReleaseChoice(&p) == DC::Hardcore::Choice::Town);
    DC::Rifts::inRift = true;
    assert(DC::Hardcore::ReleaseChoice(&p) == DC::Hardcore::Choice::Checkpoint);
    DC::Rifts::riftMode = "gr";                                                          // no limit there
    assert(DC::Hardcore::ReleaseChoice(&p) == DC::Hardcore::Choice::Here);
''', "for (Choice choice : {Choice::Here, Choice::Checkpoint, Choice::Town})", "for (Choice choice : {Choice::Here, Choice::Town})")

    def test_when_nothing_works_it_stays_where_it_fell_rather_than_dead_for_good(self):
        both(self, '''
    p.at.z = -600; DC::World::hubLoaded = false;
    assert(DC::Hardcore::ReleaseChoice(&p) == DC::Hardcore::Choice::Here);
''', "            return choice;\n    return Choice::Here;", "            return choice;\n    return Choice::Town;")


class Spread(unittest.TestCase):
    # Ruling 2026-10-09 3.4: town arrivals spread round the spawn on walkable ground, radius a tunable row; logins not included.
    # diablocraft-bqo2: the hub map's own thread keeps the points (RefreshSpread, one try a tick); a revive only draws one.
    SET = '''
    DC::Tunables::rows["combat/revive_town_spread_yards"] = 10;
    theMap.ground = [](float, float) { return 41.0f; };
    auto keep = [&](std::initializer_list<double> pair) { rolls = pair; rollAt = 0; DC::Hardcore::RefreshSpread(&theMap); };
'''

    def test_a_kept_point_is_drawn_and_the_pool_holds_the_rolled_bearing_and_distance(self):
        both(self, self.SET + '''
    keep({0.25, 1.0});                                                     // a quarter turn, the whole radius: (10,40)
    keep({0.0, 0.25});                                                     // due east, a quarter of the area: half the radius: (15,30)
    assert(DC::Hardcore::spreadPoints.size() == 2);
    assert(std::fabs(DC::Hardcore::spreadPoints[0].x - 10) < 1e-3 && std::fabs(DC::Hardcore::spreadPoints[0].y - 40) < 1e-3);
    assert(std::fabs(DC::Hardcore::spreadPoints[1].x - 15) < 1e-3 && std::fabs(DC::Hardcore::spreadPoints[1].y - 30) < 1e-3);
    rolls = {0.0}; rollAt = 0;                                             // the draw takes the first
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
    assert(p.at.map == 530 && std::fabs(p.at.x - 10) < 1e-3 && std::fabs(p.at.y - 40) < 1e-3 && p.at.z == 41.0f);
    rig.die(p); rolls = {0.99}; rollAt = 0;                                // and the last
    rig.ask(p, "DCREVIVE\\ttown");
    assert(std::fabs(p.at.x - 15) < 1e-3 && std::fabs(p.at.y - 30) < 1e-3);
''', "radius * static_cast<float>(std::sqrt(rand_norm()))", "radius * static_cast<float>(rand_norm())")

    def test_never_farther_than_the_radius(self):
        ok, out = passes(self.SET + '''
    unsigned seed = 12345;
    for (int i = 0; i < 400; ++i) { seed = seed * 1103515245u + 12345u; rolls.push_back(((seed >> 8) & 0xFFFF) / 65535.0); }
    for (int i = 0; i < 200; ++i) DC::Hardcore::RefreshSpread(&theMap);
    assert(DC::Hardcore::spreadPoints.size() == 200);                      // two rolls a try, 400 of them
    for (int i = 0; i < 45; ++i) {                                         // the route's budget is 50 a character
        rig.die(p);
        assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
        float dx = p.at.x - 10, dy = p.at.y - 30;
        assert(std::sqrt(dx * dx + dy * dy) <= 10.0f + 1e-3f);
    }
''')
        self.assertTrue(ok, out)

    def test_a_revive_a_release_and_a_kick_read_no_map(self):
        # They run on the map the character is leaving. The pool is read under the lock and the map is not asked.
        body = self.SET + '''
    keep({0.25, 1.0});
    int before = theMap.reads;
    assert(before > 0);
    rolls = {0.0}; rollAt = 0;
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");        // Respawn
    assert(std::fabs(p.at.y - 40) < 1e-3);                                 // from the pool
    Player q; q.state = DeathState::Alive; q.guid = 9;
    assert(DC::Hardcore::SendToTown(&q));                                  // the kick, the reset, .unstuck
    assert(std::fabs(q.at.y - 40) < 1e-3);
    DC::Hardcore::ReleaseChoice(&p);
    assert(theMap.reads == before);
'''
        ok, out = passes(body)
        self.assertTrue(ok, out)
        for where, mutant in (
            ("Respawn and SendToTown (TownArrival)", ("    SpreadAround(at);\n    return true;", "    { WorldLocation t = at; SpreadCandidate(&theMap, at, 10, t); }\n    SpreadAround(at);\n    return true;")),
            ("SpreadAround", ("void SpreadAround(WorldLocation& at)\n{", "void SpreadAround(WorldLocation& at)\n{\n    { WorldLocation t = at; SpreadCandidate(&theMap, at, 10, t); }")),
        ):
            ok, out = passes(body, mutate(production(), *mutant))
            self.assertFalse(ok, "mutation survived: a map read from " + where)

    def test_a_blank_or_zero_row_keeps_no_points_and_the_spawn_is_the_spawn(self):
        both(self, '''
    theMap.ground = [](float, float) { return 41.0f; };
    for (double radius : {0.0, -5.0}) {
        DC::Tunables::rows["combat/revive_town_spread_yards"] = radius;
        DC::Hardcore::RefreshSpread(&theMap);
        assert(DC::Hardcore::spreadPoints.empty());
    }
    DC::Tunables::rows.erase("combat/revive_town_spread_yards");           // blank
    DC::Hardcore::RefreshSpread(&theMap);
    assert(DC::Hardcore::spreadPoints.empty() && theMap.reads == 0);
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
    assert(p.at == WorldLocation(530, 10, 30, 40));
''', "if (radius <= 0.0f || spreadPoints.size() >= SPREAD_POOL)", "if (spreadPoints.size() >= SPREAD_POOL)")

    def test_an_empty_pool_gives_the_spawn(self):
        both(self, self.SET + '''
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");     // the hub has been empty: nothing kept yet
    assert(p.at == WorldLocation(530, 10, 30, 40) && theMap.reads == 0);
    theMap.ground = [](float, float) { return INVALID_HEIGHT; };
    keep({0.25, 1.0});                                                     // the pool is for this row now, and still empty
    rig.die(p);
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
    assert(p.at == WorldLocation(530, 10, 30, 40));
''', "if (spreadPoints.empty() || spreadRadius", "if (spreadRadius")

    def test_points_kept_for_another_radius_or_spawn_are_not_used(self):
        both(self, self.SET + '''
    keep({0.25, 1.0});
    DC::Tunables::rows["combat/revive_town_spread_yards"] = 20;           // the designer moved the row
    assert(rig.ask(p, "DCREVIVE\\ttown") == "DCREVIVE\\tR|town|town");
    assert(p.at == WorldLocation(530, 10, 30, 40));
    DC::Tunables::rows["combat/revive_town_spread_yards"] = 10;
    DC::World::hubX = 11;                                                  // or the spawn row moved
    rig.die(p); rig.ask(p, "DCREVIVE\\ttown");
    assert(p.at == WorldLocation(530, 11, 30, 40));
''', "|| spreadRadius != radius || !SameSpot(spreadCenter, at))\n        return;\n    at =", "|| !SameSpot(spreadCenter, at))\n        return;\n    at =")

    def test_a_moved_spawn_or_row_starts_the_pool_again(self):
        both(self, self.SET + '''
    keep({0.25, 1.0}); keep({0.25, 1.0});
    assert(DC::Hardcore::spreadPoints.size() == 2);
    DC::Tunables::rows["combat/revive_town_spread_yards"] = 20;
    keep({0.25, 1.0});
    assert(DC::Hardcore::spreadPoints.size() == 1 && std::fabs(DC::Hardcore::spreadPoints[0].y - 50) < 1e-3);
    DC::World::hubX = 11;
    keep({0.25, 1.0});
    assert(DC::Hardcore::spreadPoints.size() == 1 && std::fabs(DC::Hardcore::spreadPoints[0].x - 11) < 1e-3);
''', "if (spreadRadius != radius || !SameSpot(spreadCenter, center))", "if (spreadRadius != radius)")

    def test_only_the_hub_map_fills_the_pool(self):
        both(self, self.SET + '''
    Map other; other.id = 1;
    DC::Hardcore::RefreshSpread(&other);
    assert(DC::Hardcore::spreadPoints.empty() && other.reads == 0);
    DC::World::hubLoaded = false;
    DC::Hardcore::RefreshSpread(&theMap);
    assert(DC::Hardcore::spreadPoints.empty() && theMap.reads == 0);
''', "map->GetId() != center.GetMapId()", "false")

    def test_the_pool_stops_at_its_size(self):
        both(self, self.SET + '''
    for (int i = 0; i < 400; ++i) DC::Hardcore::RefreshSpread(&theMap);   // 0.5 and 0.5 every time: a good point each
    assert(DC::Hardcore::spreadPoints.size() == 256);
    int reads = theMap.reads; DC::Hardcore::RefreshSpread(&theMap);
    assert(theMap.reads == reads);                                         // full: the map is not asked again
''', "constexpr std::size_t SPREAD_POOL = 256;", "constexpr std::size_t SPREAD_POOL = 257;")

    def test_ground_the_spawn_cannot_stand_on_is_not_kept(self):
        # Each rule alone: the first try fails only that rule, the second is good.
        cases = (
            ("if (std::fabs(z - center.GetPositionZ()) > SPREAD_STEP ||", "if (false ||", "the step",
             "theMap.ground = [](float, float y) { return std::fabs(y - 40) < 0.01 ? 60.0f : 41.0f; };"),
            ("!map->isInLineOfSight(", "false && !map->isInLineOfSight(", "the sight line",
             "theMap.ground = [](float, float) { return 41.0f; }; theMap.sight = [](float x, float) { return std::fabs(x - 15) < 0.01; };"),
            ("map->IsInWater(PHASEMASK_NORMAL, x, y, z, DEFAULT_COLLISION_HEIGHT) ||", "false ||", "the water",
             "theMap.ground = [](float, float) { return 41.0f; }; theMap.water = [](float x, float) { return std::fabs(x - 10) < 0.01; };"),
            ("if (std::fabs(z - center.GetPositionZ()) > SPREAD_STEP ||", "if (false ||", "no ground at all",
             "theMap.ground = [](float, float y) { return std::fabs(y - 40) < 0.01 ? INVALID_HEIGHT : 41.0f; };"),
        )
        for old, new, why, setup in cases:
            body = self.SET + setup + '''
    keep({0.25, 1.0});                                                     // (10,40): fails the one rule
    assert(DC::Hardcore::spreadPoints.empty());
    keep({0.0, 0.25});                                                     // (15,30): good
    assert(DC::Hardcore::spreadPoints.size() == 1 && std::fabs(DC::Hardcore::spreadPoints[0].x - 15) < 1e-3);
'''
            ok, out = passes(body)
            self.assertTrue(ok, out)
            ok, out = passes(body, mutate(production(), old, new))
            self.assertFalse(ok, "mutation survived: " + why)

    def test_a_step_of_exactly_the_limit_is_walkable_and_just_over_is_not(self):
        both(self, self.SET + '''
    theMap.ground = [](float, float y) { return std::fabs(y - 40) < 0.01 ? 43.0f : 43.5f; };         // 3 yards above the spawn is fine
    keep({0.25, 1.0}); keep({0.0, 0.25});
    assert(DC::Hardcore::spreadPoints.size() == 1 && std::fabs(DC::Hardcore::spreadPoints[0].y - 40) < 1e-3 && DC::Hardcore::spreadPoints[0].z == 43.0f);
''', "> SPREAD_STEP", ">= SPREAD_STEP")

    def test_the_hub_map_script_calls_the_refresh_and_the_revive_path_never_asks_the_map(self):
        # Source pins: the only caller of RefreshSpread is the hub map's OnMapUpdate; nothing else names a Map or MapMgr.
        self.assertEqual(HARDCORE.count("RefreshSpread(map)"), 1)
        self.assertIn("ALLMAPHOOK_ON_MAP_UPDATE", HARDCORE)
        self.assertNotIn("sMapMgr", HARDCORE)
        self.assertNotIn("FindBaseNonInstanceMap", HARDCORE)
        self.assertIn("new HubSpread();", HARDCORE)


class Graveyard(unittest.TestCase):
    # Plan R1 gap 2: a living player the core would send to a graveyard goes to town (the hook calls SendToTown).
    def test_a_living_player_goes_to_the_hub_spawn(self):
        both(self, '''
    p.state = DeathState::Alive; p.at = WorldLocation(602, 1, 2, 3);
    events.clear();
    assert(DC::Hardcore::SendToTown(&p));
    assert((events == std::vector<std::string>{"teleport 530:10"}) && p.at == WorldLocation(530, 10, 30, 40));
    assert(!p.graveyard && p.IsAlive());
''', "    if (!TownArrival(town))\n        return false;\n    if (!player->IsBeingTeleported())\n        player->TeleportTo(town);\n    return true;",
             "    return false;")

    def test_it_arrives_spread_like_any_town_arrival(self):
        both(self, '''
    DC::Tunables::rows["combat/revive_town_spread_yards"] = 10;
    theMap.ground = [](float, float) { return 41.0f; }; rolls = {0.0, 0.25}; DC::Hardcore::RefreshSpread(&theMap);
    rolls = {0.0}; rollAt = 0;
    p.state = DeathState::Alive; events.clear();
    assert(DC::Hardcore::SendToTown(&p));
    assert(std::fabs(p.at.x - 15) < 1e-3 && std::fabs(p.at.y - 30) < 1e-3 && p.at.map == 530);
''', "    if (!TownArrival(town))\n        return false;", "    if (!DC::World::HubLocation(town))\n        return false;")

    def test_before_the_hub_is_loaded_the_core_keeps_its_own_move(self):
        both(self, '''
    DC::World::hubLoaded = false; p.state = DeathState::Alive; events.clear();
    assert(!DC::Hardcore::SendToTown(&p) && events.empty());
''', "    if (!TownArrival(town))\n        return false;", "    if (!TownArrival(town))\n        return true;")

    def test_a_player_already_being_teleported_is_left_to_that_move(self):
        both(self, '''
    p.state = DeathState::Alive; p.teleporting = true; events.clear();
    assert(DC::Hardcore::SendToTown(&p) && events.empty());           // the core must still not send it to a graveyard
''', "    if (!player->IsBeingTeleported())\n        player->TeleportTo(town);", "    player->TeleportTo(town);")


class Floods(unittest.TestCase):
    def test_a_flood_is_dropped_and_an_unset_row_closes_the_route(self):
        ok, out = passes('''
    DC::Tunables::rows["combat/revive_burst"] = 1; DC::Tunables::rows["combat/revive_per_second"] = 1;
    assert(rig.router.Dispatch(&p, "DCREVIVE\\toptions", 0) == Outcome::Handled);
    assert(rig.router.Dispatch(&p, "DCREVIVE\\toptions", 0) == Outcome::Throttled);      // no reply, nothing revived
    DC::Tunables::rows["combat/revive_burst"] = 0;
    Player q; q.at = WorldLocation(1, 1, 1, 1);
    assert(rig.router.Dispatch(&q, "DCREVIVE\\there", 100000) == Outcome::Throttled && !q.IsAlive());   // a blank row refuses all
''')
        self.assertTrue(ok, out)


class Source(unittest.TestCase):
    def test_the_route_is_registered_on_the_budget_rows_the_contract_names(self):
        self.assertIn('Routes().Add("DCREVIVE", {"combat", "revive_burst", "revive_per_second"}, Choose)', HARDCORE)


if __name__ == "__main__":
    unittest.main()
