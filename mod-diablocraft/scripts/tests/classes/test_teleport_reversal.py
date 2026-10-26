"""Teleport - Reversal returns you inside its window (diablocraft-teleport-reversal, GitHub #94).

    python3 mod-diablocraft/scripts/tests/classes/test_teleport_reversal.py

The rune's own sentence: "Casting Teleport again within {duration_seconds} seconds will instantly return you to
your original location and set the remaining cooldown to {cooldown_seconds} second." Nothing on the server did
it, and the record carried Teleport's inherited 11 s the whole time. Ruling q-1003-04 ruled the rule:
  1  the first cast teleports, saves where you stood and opens the window; no cooldown shows;
  2  a recast inside the window returns you there and sets the cooldown to 1 s;
  3  a window that ends unused leaves the full cooldown (after reductions) less the time it was open, never < 0;
  4  death, a map or instance change, logout and Archon form end the window; there is no return across maps.

The module's own functions are cut out of the Wizard's files (dc_wizard_teleport.cpp) and compiled against doubles:
  real      ReversalClearCooldown, ReversalBegin, ReversalEnd, ReversalCast;
  data      the window (5 s) and the return cooldown (1 s) from wizard_skill_values.csv, the record's cooldown
            from the generated spell_shells.sql, which is what the harness's "core" installs on every press;
  double    the player (a position, a map, a clock, a cooldown map by spell and by category), the timer queue,
            SendSkillCooldown (the same clear-or-add per shell of the skill as dc_combat.cpp's).
A press is modelled the way the core does it: refused while the skill's cooldown is up, otherwise OnCast (Begin),
the leap moves the caster, the core installs the record's cooldown, then AfterCast (ReversalCast).

Teleport also faces the way it travelled (diablocraft-a53s, the designer "Fix teleport now"): the core's LEAP lands the caster with
its destination's orientation, which a cursor destination does not carry (0), so the module puts the facing on after the
leap (TravelAngle, TeleportBegin, FaceTravel), and Reversal's return faces the way it travels back. The harness models
the core's near teleport as Player::TeleportTo does: the leap lands with orientation 0 but the SERVER POSITION DOES NOT
MOVE until the client's ack (IsBeingTeleportedNear stays true, GetTeleportDest holds the destination, GetPosition is
still the start); every Advance step is one update with the ack at its end.

MutationsAreCaught puts one defect back at a time and requires the harness to fail.
What this does not run: the real Spell::cast and LEAP, the client's swirl, the Update/logout/map hooks themselves
(pinned as text below, and exercised here through ReversalEnd, which they call).
"""
import csv
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env
import test_skill_swing_recovery as swing

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
WIZARD_CPP = wizard_source.CPP
INTERNAL_H = wizard_source.FOLDER / "dc_wizard_internal.h"
VALUES_CSV = MODULE / "data/d3/wizard_skill_values.csv"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/teleport-reversal"

REVERSAL, WORMHOLE = 83184, 83185
FUNCTIONS = ["Position Where(Player* player)",
             "bool Travels(uint32 id)",
             "float TravelAngle(Position const& from, Position const& to)",
             "void TeleportBegin(Player* player, State& state, uint32 spellId)",
             "void FaceTravel(Player* player, uint32 id)",
             "void ReversalClearCooldown(Player* player, uint32 id)",
             "void ReversalBegin(Player* player, State& state, uint32 spellId)",
             "void ReversalEnd(Player* player)",
             "void ReversalCast(Player* player, uint32 id)"]
definition = swing.definition


def sheet(token):
    for row in csv.reader(VALUES_CSV.read_text(encoding="utf-8").splitlines()):
        if row[:3] == ["Teleport", "Reversal", token]:
            return float(row[4])
    raise AssertionError("no Teleport/Reversal %s row" % token)


HARNESS = r'''
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <vector>
using uint32 = std::uint32_t; using uint64 = std::uint64_t;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); std::exit(3); } } while (0)

static const uint32 REVERSAL = @REVERSAL@, WORMHOLE = @WORMHOLE@, CATEGORY = 7, ARCHON_TELEPORT = 83278, OTHER = 1;
static const double WINDOW_SECONDS = @WINDOW@, RETURN_SECONDS = @RETURN@;
static uint32 fullCooldown = @RECORD@;          // what SkillCooldownMilliseconds answers (reductions change it)
static uint64 now = 100000;

struct Position {
    float x = 0, y = 0, z = 0, o = 0;
    float GetPositionX() const { return x; } float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; } float GetOrientation() const { return o; }
    float GetExactDist2d(Position const* p) const { return std::hypot(p->x - x, p->y - y); }
    float GetAbsoluteAngle(Position const* p) const {
        float a = std::atan2(p->y - y, p->x - x); return a < 0 ? a + 6.2831853f : a; }
};
struct SpellInfo { uint32 GetCategory() const { return CATEGORY; } };
struct SpellMgrD { SpellInfo info; SpellInfo const* GetSpellInfo(uint32) { return &info; } } spellMgrD;
SpellMgrD* sSpellMgr = &spellMgrD;

struct Player {
    uint32 map = 1, instance = 0; Position pos; bool alive = true;
    std::map<uint32, uint64> spellEnd, categoryEnd;          // the cooldown the core would refuse a press by
    bool pending = false; Position dest;                     // Player::teleportStore_dest and the near-teleport semaphore
    std::vector<Position> sent;                              // every near teleport the client was sent, and where to
    uint32 GetMapId() const { return map; } uint32 GetInstanceId() const { return instance; }
    Position GetPosition() const { return pos; }
    bool IsBeingTeleportedNear() const { return pending; }
    Position& GetTeleportDest() { return dest; }
    float GetExactDist2d(float x, float y) const { return std::hypot(x - pos.x, y - pos.y); }
    void RemoveCategoryCooldown(uint32 c) { categoryEnd.erase(c); }
    // Player::TeleportTo, near branch: store the destination, tell the client, leave the position where it was.
    bool NearTeleportTo(float x, float y, float z, float o, bool casting = false) {
        (void)casting; dest = {x, y, z, o}; pending = true; sent.push_back(dest); return true; }
    // HandleMoveTeleportAck: the move happens now.
    void Ack() { if (pending) { pos = dest; pending = false; } }
    uint64 Remaining(uint32 id) const {
        uint64 left = 0;
        auto s = spellEnd.find(id); if (s != spellEnd.end() && s->second > now) left = std::max(left, s->second - now);
        auto c = categoryEnd.find(CATEGORY); if (c != categoryEnd.end() && c->second > now) left = std::max(left, c->second - now);
        return left; }
};
static const uint32 FAMILY[] = {REVERSAL, WORMHOLE};          // the rune shells of Teleport (one skill, one timer)
void SendSkillCooldown(Player* p, uint32, uint32 ms) {
    for (uint32 id : FAMILY) { if (ms) p->spellEnd[id] = now + ms; else p->spellEnd.erase(id); } }
uint32 SkillCooldownMilliseconds(Player*, uint32) { return fullCooldown; }

namespace Numbers { std::optional<double> Own(uint32 id, std::string_view token, std::string_view = {}) {
    if (id == REVERSAL && token == "cooldown_seconds") return RETURN_SECONDS; return std::nullopt; } }
double Num(uint32 id, std::string_view token, std::string_view = {}) {
    return id == REVERSAL && token == "duration_seconds" ? WINDOW_SECONDS : 0.0; }
bool IsRune(uint32 id, std::string_view rune) { return id == REVERSAL && rune == "Reversal"; }
bool IsSkill(uint32 id, std::string_view skill) { return (id == REVERSAL || id == WORMHOLE) && skill == "Teleport"; }
uint32 ArchonAbilityId(std::string_view name) { return name == "Teleport" ? ARCHON_TELEPORT : 0; }
uint64 Now() { return now; }

struct State {
    uint32 reversalSpell = 0, reversalMap = 0, reversalInstance = 0;
    uint64 reversalSince = 0, reversalUntil = 0;
    unsigned reversalWindow = 0;
    Position reversalFrom;
    Position travelFrom;
    bool reversalRecast = false;
};
std::recursive_mutex mutex;
static std::map<Player*, State> states;
State& StateOf(Player* p) { return states[p]; }
struct Timer { uint64 at; std::function<void(Player*)> run; };
static std::vector<Timer> timers;
void After(Player*, double seconds, std::function<void(Player*)> run) {
    timers.push_back({now + uint64(std::max(0.0, seconds) * 1000), std::move(run)}); }

@FUNCTIONS@

// What OnPlayerUpdate does with the queue and with a dead player (pinned as text in the test).
static void Update(Player& p) {
    std::vector<Timer> due;
    for (auto it = timers.begin(); it != timers.end();) if (it->at <= now) { due.push_back(std::move(*it)); it = timers.erase(it); } else ++it;
    if (p.alive) { for (Timer& t : due) t.run(&p); } else ReversalEnd(&p);
    p.Ack();                                         // the client's acknowledgement arrives within the step
}
static void Advance(Player& p, uint64 ms) {          // one update per 100 ms, like the world's
    for (uint64 done = 0; done < ms; done += 100) { now += 100; Update(p); } }

// One press of Teleport with the Reversal rune: the core refuses it while a cooldown is up, otherwise
// OnCast (Begin), the leap, the core's own cooldown, AfterCast (Cast).
static bool PressAt(Player& p, float x, float y) {
    if (p.Remaining(REVERSAL)) return false;
    { std::lock_guard<std::recursive_mutex> g(mutex); ReversalBegin(&p, StateOf(&p), REVERSAL); TeleportBegin(&p, StateOf(&p), REVERSAL); }
    p.NearTeleportTo(x, y, 0, 0, true);                // the core's LEAP: a near teleport; a cursor destination has orientation 0
    for (uint32 id : FAMILY) p.spellEnd[id] = now + fullCooldown;
    p.categoryEnd[CATEGORY] = now + fullCooldown;
    FaceTravel(&p, REVERSAL);                          // Wizard::Cast, in this order
    ReversalCast(&p, REVERSAL);
    return true;
}
static bool Press(Player& p, float leapTo) { return PressAt(p, leapTo, 0); }
static int Count(Player& p, float x) { int n = 0; for (auto const& d : p.sent) n += d.x == x; return n; }   // teleports to x
static float Angle(float dx, float dy) { float a = std::atan2(dy, dx); return a < 0 ? a + 6.2831853f : a; }
static bool Near(float a, float b) { return std::fabs(a - b) < 0.001f; }
static Player Fresh() { Player p; p.pos = {10, 0, 0, 0}; states.clear(); timers.clear(); now = 100000; fullCooldown = @RECORD@; return p; }

int main(int argc, char** argv) {
    std::string name = argc > 1 ? argv[1] : "";
    Player p = Fresh();
    if (name == "first_cast_opens_a_window_with_no_cooldown") {
        CHECK(Press(p, 30));
        CHECK(p.pending && p.dest.x == 30 && p.pos.x == 10);   // it teleported: the leap is pending, the position not yet moved
        CHECK(p.Remaining(REVERSAL) == 0);                 // no cooldown shows, on the skill or its category
        CHECK(p.Remaining(WORMHOLE) == 0);
        CHECK(StateOf(&p).reversalUntil == now + 5000 && StateOf(&p).reversalFrom.x == 10);
    } else if (name == "recast_inside_the_window_returns_with_one_second") {
        CHECK(Press(p, 30));
        Advance(p, 2000);
        CHECK(Press(p, 50));                               // the window let the press through
        Advance(p, 100);                                   // the return lands on the next update
        CHECK(p.pos.x == 10);                              // back at the start, not at 30 and not at 50
        CHECK(Count(p, 10) == 1);
        CHECK(p.Remaining(REVERSAL) == 900);               // 1 s from the cast, 100 ms gone
        CHECK(StateOf(&p).reversalUntil == 0);
    } else if (name == "the_return_cooldown_is_one_second_exactly") {
        CHECK(Press(p, 30)); Advance(p, 1000);
        CHECK(Press(p, 50));
        CHECK(p.Remaining(REVERSAL) == 1000 && p.Remaining(WORMHOLE) == 1000);
        now += 999; CHECK(!Press(p, 70));                  // refused for the second
        now += 1;   CHECK(Press(p, 70));
    } else if (name == "the_return_cooldown_outlasts_nothing_afterwards") {
        CHECK(Press(p, 30)); Advance(p, 1000);
        CHECK(Press(p, 50)); Advance(p, 6000);             // the old window's timer would have fired at 5 s
        CHECK(p.Remaining(REVERSAL) == 0);                 // nothing was put on again
        CHECK(p.pos.x == 10 && Count(p, 10) == 1);
    } else if (name == "an_unused_window_leaves_the_full_cooldown_less_the_window") {
        CHECK(Press(p, 30));
        Advance(p, 4900); CHECK(p.Remaining(REVERSAL) == 0);       // still open
        Advance(p, 100);
        CHECK(p.Remaining(REVERSAL) == fullCooldown - 5000);       // 11 s from the first cast
        Advance(p, fullCooldown - 5000);
        CHECK(p.Remaining(REVERSAL) == 0 && Press(p, 30));
    } else if (name == "a_cooldown_reduction_is_taken_before_the_window_is") {
        CHECK(Press(p, 30));
        fullCooldown = 8000;                                       // reductions since the first cast
        Advance(p, 5000);
        CHECK(p.Remaining(REVERSAL) == 3000);
    } else if (name == "the_cooldown_is_never_below_zero") {
        CHECK(Press(p, 30));
        fullCooldown = 4000;                                       // shorter than the window
        Advance(p, 5000);
        CHECK(p.Remaining(REVERSAL) == 0);
        CHECK(Press(p, 30));
    } else if (name == "a_cast_after_the_window_is_a_new_first_cast") {
        CHECK(Press(p, 30)); Advance(p, 5000);
        Advance(p, fullCooldown - 5000);
        p.pos.x = 77;
        CHECK(Press(p, 90));
        Advance(p, 100);
        CHECK(p.pos.x == 90 && Count(p, 77) == 0);                 // no return: it opened a new window
        CHECK(StateOf(&p).reversalFrom.x == 77);
    } else if (name == "death_ends_the_window_and_the_time_open_is_counted") {
        CHECK(Press(p, 30));
        Advance(p, 2000);
        p.alive = false; Advance(p, 100);
        CHECK(p.Remaining(REVERSAL) == fullCooldown - 2100);       // 11 s from the first cast
        CHECK(StateOf(&p).reversalUntil == 0);
        p.alive = true; Advance(p, 10000);
        CHECK(Count(p, 10) == 0);                                  // never a return after dying
    } else if (name == "a_map_change_ends_the_window_and_there_is_no_return_across_maps") {
        CHECK(Press(p, 30)); Advance(p, 1000);
        ReversalEnd(&p);                                           // what OnPlayerMapChanged calls
        p.map = 2; p.pos.x = 5;
        CHECK(p.Remaining(REVERSAL) == fullCooldown - 1000);
        Advance(p, fullCooldown);
        CHECK(Press(p, 6));                                        // a first cast on the new map
        Advance(p, 100);
        CHECK(p.pos.x == 6 && Count(p, 5) == 0);
    } else if (name == "an_open_window_on_another_map_is_not_a_recast") {
        CHECK(Press(p, 30)); Advance(p, 1000);
        p.map = 2; p.pos.x = 5;                                    // a change nobody ended (the hook is the end)
        { std::lock_guard<std::recursive_mutex> g(mutex); ReversalBegin(&p, StateOf(&p), REVERSAL); }
        CHECK(!StateOf(&p).reversalRecast && StateOf(&p).reversalFrom.x == 5 && StateOf(&p).reversalMap == 2);
    } else if (name == "a_window_that_ran_out_unnoticed_is_not_a_recast") {
        CHECK(Press(p, 30));
        now += 6000;                                               // no update ran: the end was never processed
        CHECK(Press(p, 50));
        Advance(p, 100);
        CHECK(p.pos.x == 50 && Count(p, 10) == 0 && Count(p, 30) == 2);   // a new first cast, not a return (30: leap + its facing)
        CHECK(StateOf(&p).reversalFrom.x == 30 && StateOf(&p).reversalUntil != 0);
    } else if (name == "an_instance_change_is_a_map_change") {
        CHECK(Press(p, 30)); Advance(p, 1000);
        p.instance = 9;
        { std::lock_guard<std::recursive_mutex> g(mutex); ReversalBegin(&p, StateOf(&p), REVERSAL); }
        CHECK(!StateOf(&p).reversalRecast);
    } else if (name == "ending_with_no_window_does_nothing") {
        ReversalEnd(&p);
        CHECK(p.Remaining(REVERSAL) == 0 && states[&p].reversalWindow == 0);
        CHECK(Press(p, 30)); Advance(p, 1000); CHECK(Press(p, 50)); ReversalEnd(&p);
        CHECK(p.Remaining(REVERSAL) == 1000 - 0);                  // the return's second is not replaced
    } else if (name == "an_old_windows_timer_does_not_end_the_next_one") {
        CHECK(Press(p, 30)); Advance(p, 1000);
        CHECK(Press(p, 50)); Advance(p, 1100);                     // returned, 1 s over, 3.9 s of window 1 left
        CHECK(Press(p, 40));                                       // a new first cast: window 2 opens at t = 2.1 s
        Advance(p, 3000);                                          // window 1's timer fires at t = 5 s
        CHECK(StateOf(&p).reversalUntil != 0);                     // window 2 is still open
        CHECK(p.Remaining(REVERSAL) == 0);
        Advance(p, 2000);                                          // window 2 ends at 7.1 s
        CHECK(p.Remaining(REVERSAL) == fullCooldown - 5000);
    } else if (name == "other_runes_are_not_touched") {
        { std::lock_guard<std::recursive_mutex> g(mutex); ReversalBegin(&p, StateOf(&p), WORMHOLE); }
        CHECK(StateOf(&p).reversalFrom.x == 0 && !StateOf(&p).reversalRecast && StateOf(&p).reversalMap == 0);
    } else if (name == "a_teleport_faces_the_way_it_travelled") {
        float const dir[][2] = {{20, 0}, {0, 20}, {-20, 0}, {0, -20}, {10, 10}, {-7, 3}};
        for (auto const& d : dir) {
            Player q = Fresh(); q.pos = {100, 100, 0, 2.5f};
            CHECK(PressAt(q, 100 + d[0], 100 + d[1]));
            CHECK(q.sent.size() == 2);                             // the leap, then the same point turned
            CHECK(q.pending && q.pos.x == 100 && q.pos.y == 100);  // the position has not moved: the client has not acked
            CHECK(Near(q.dest.x, 100 + d[0]) && Near(q.dest.y, 100 + d[1]));
            CHECK(Near(q.dest.o, Angle(d[0], d[1])));              // the pending destination faces start toward landing
            Advance(q, 100);                                       // the ack
            CHECK(!q.pending && Near(q.pos.x, 100 + d[0]) && Near(q.pos.y, 100 + d[1]));
            CHECK(Near(q.pos.o, Angle(d[0], d[1])));
        }
    } else if (name == "the_landing_is_the_pending_destination_not_the_position") {
        p.pos = {10, 0, 0, 2.0f};
        CHECK(PressAt(p, 10, 30));                                 // north; no ack yet: GetPosition is still the start
        CHECK(Near(p.pos.y, 0) && Near(p.dest.y, 30) && Near(p.sent[1].y, 30));   // so it never turns back to the start
        CHECK(Near(p.sent[1].o, Angle(0, 30)));
        Advance(p, 100);
        CHECK(Near(p.pos.y, 30) && Near(p.pos.o, Angle(0, 30)));
    } else if (name == "a_cast_that_went_nowhere_keeps_its_facing") {
        p.pos = {10, 0, 0, 1.25f};
        CHECK(PressAt(p, 10, 0));                                  // the leap still lands with orientation 0
        CHECK(p.sent.size() == 2 && Near(p.sent[1].o, 1.25f));
        Advance(p, 100);
        CHECK(Near(p.pos.o, 1.25f) && Near(p.pos.x, 10));
    } else if (name == "a_leap_that_did_not_happen_is_not_turned") {
        { std::lock_guard<std::recursive_mutex> g(mutex); TeleportBegin(&p, StateOf(&p), REVERSAL); }
        FaceTravel(&p, REVERSAL);                                  // nothing is pending: it failed or never ran
        CHECK(p.sent.empty() && !p.pending);
    } else if (name == "a_reversal_return_faces_its_travel_direction") {
        p.pos = {10, 0, 0, 2.0f};                                  // the start's own facing is neither the way back nor 0
        CHECK(PressAt(p, 10, 30)); Advance(p, 100);                // north; the window is open
        p.sent.clear();
        CHECK(PressAt(p, 50, 30));                                 // the recast leaps east: that leap is pending
        CHECK(p.sent.size() == 2);                                 // the leap and the return; the leap is not faced as well
        CHECK(Near(p.sent[1].x, 10) && Near(p.sent[1].y, 0));
        CHECK(Near(p.sent[1].o, Angle(0, -30)));                   // from (10,30) back to (10,0): south
        CHECK(p.pending && Near(p.dest.x, 10));                    // the return replaced the pending leap
        Advance(p, 100);
        CHECK(Near(p.pos.x, 10) && Near(p.pos.y, 0) && Near(p.pos.o, Angle(0, -30)));
    } else if (name == "a_recast_before_the_first_ack_returns_from_the_true_landing") {
        p.pos = {10, 0, 0, 2.0f};
        CHECK(PressAt(p, 10, 30));                                 // north, and the client has not acked yet
        CHECK(Near(p.pos.y, 0));
        CHECK(PressAt(p, 50, 30));                                 // recast at once: it stood at (10,30) in effect
        CHECK(Near(p.dest.x, 10) && Near(p.dest.y, 0) && Near(p.dest.o, Angle(0, -30)));
        Advance(p, 100);
        CHECK(Near(p.pos.x, 10) && Near(p.pos.y, 0) && Near(p.pos.o, Angle(0, -30)));
    } else if (name == "a_return_of_no_distance_keeps_the_facing_it_had") {
        p.pos = {10, 0, 0, 0.7f};
        CHECK(PressAt(p, 10, 0)); Advance(p, 100);                 // went nowhere: opens the window
        p.pos.o = 0.9f; p.sent.clear();
        CHECK(PressAt(p, 40, 0));                                  // leaps away, returns to where it started
        CHECK(p.sent.size() == 2 && Near(p.sent[1].x, 10) && Near(p.sent[1].o, 0.9f));
        Advance(p, 100);
        CHECK(Near(p.pos.o, 0.9f));
    } else if (name == "archon_teleport_faces_the_way_it_travelled") {
        CHECK(Travels(ARCHON_TELEPORT));
        p.pos = {5, 5, 0, 3.0f};
        { std::lock_guard<std::recursive_mutex> g(mutex); TeleportBegin(&p, StateOf(&p), ARCHON_TELEPORT); }
        p.NearTeleportTo(5, 25, 0, 0, true);
        FaceTravel(&p, ARCHON_TELEPORT);
        CHECK(p.sent.size() == 2 && Near(p.sent[1].o, Angle(0, 20)));
    } else if (name == "other_spells_do_not_travel") {
        CHECK(!Travels(OTHER));
        p.pos = {5, 5, 0, 3.0f};
        { std::lock_guard<std::recursive_mutex> g(mutex); TeleportBegin(&p, StateOf(&p), OTHER); }
        CHECK(StateOf(&p).travelFrom.x == 0 && StateOf(&p).travelFrom.y == 0);
    } else {
        std::fprintf(stderr, "no case %s\n", name.c_str()); return 4;
    }
    std::puts("ok");
    return 0;
}
'''

CASES = [
    "first_cast_opens_a_window_with_no_cooldown",
    "recast_inside_the_window_returns_with_one_second",
    "the_return_cooldown_is_one_second_exactly",
    "the_return_cooldown_outlasts_nothing_afterwards",
    "an_unused_window_leaves_the_full_cooldown_less_the_window",
    "a_cooldown_reduction_is_taken_before_the_window_is",
    "the_cooldown_is_never_below_zero",
    "a_cast_after_the_window_is_a_new_first_cast",
    "death_ends_the_window_and_the_time_open_is_counted",
    "a_map_change_ends_the_window_and_there_is_no_return_across_maps",
    "an_open_window_on_another_map_is_not_a_recast",
    "an_instance_change_is_a_map_change",
    "a_window_that_ran_out_unnoticed_is_not_a_recast",
    "ending_with_no_window_does_nothing",
    "an_old_windows_timer_does_not_end_the_next_one",
    "other_runes_are_not_touched",
    "a_teleport_faces_the_way_it_travelled",
    "the_landing_is_the_pending_destination_not_the_position",
    "a_cast_that_went_nowhere_keeps_its_facing",
    "a_leap_that_did_not_happen_is_not_turned",
    "a_reversal_return_faces_its_travel_direction",
    "a_recast_before_the_first_ack_returns_from_the_true_landing",
    "a_return_of_no_distance_keeps_the_facing_it_had",
    "archon_teleport_faces_the_way_it_travelled",
    "other_spells_do_not_travel",
]


def number(value):
    return repr(float(value))


def build(source, label, stub_functions=None):
    """Compile the harness around the four functions cut out of `source`; return the binary path."""
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler on this host")
    body = "\n\n".join(stub_functions or [definition(marker, source) for marker in FUNCTIONS])
    record = swing.records()[REVERSAL][0]
    text = (HARNESS.replace("@FUNCTIONS@", body).replace("@REVERSAL@", str(REVERSAL)).replace("@WORMHOLE@", str(WORMHOLE))
            .replace("@WINDOW@", number(sheet("duration_seconds"))).replace("@RETURN@", number(sheet("cooldown_seconds")))
            .replace("@RECORD@", str(record)))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cpp = SCRATCH / (label + ".cpp")
    cpp.write_text(text, encoding="utf-8")
    binary = SCRATCH / label
    binary = harness_env.build([cpp], flags=["-std=c++17", "-O0"])
    return binary


def run(binary, case):
    return harness_env.run([str(binary), case], capture_output=True, text=True)


def failing(source, label, **kwargs):
    binary = build(source, label, **kwargs)
    return [case for case in CASES if run(binary, case).returncode != 0]


class Rule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WIZARD_CPP.read_text(encoding="utf-8")
        cls.binary = build(cls.source, "production")

    def test_the_sheet_values_are_the_rules(self):
        self.assertEqual((sheet("duration_seconds"), sheet("cooldown_seconds")), (5.0, 1.0))
        self.assertEqual(swing.records()[REVERSAL][0], 11000, "the record carries Teleport's inherited 11 s")


def make_case(case):
    def check(self):
        done = run(self.binary, case)
        self.assertEqual(done.returncode, 0, case + ": " + done.stderr.strip())
    return check


for _case in CASES:
    setattr(Rule, "test_" + _case, make_case(_case))


class Wiring(unittest.TestCase):
    """The hooks the harness cannot run: each calls the function the cases drive."""

    @classmethod
    def setUpClass(cls):
        cls.source = WIZARD_CPP.read_text(encoding="utf-8")

    def body(self, marker):
        return definition(marker, self.source)

    def test_the_state_declares_the_fields_the_harness_models(self):
        state = definition("struct State", INTERNAL_H.read_text(encoding="utf-8"))
        for field in ("reversalSpell", "reversalMap", "reversalInstance", "reversalSince", "reversalUntil",
                      "reversalWindow", "reversalFrom", "reversalRecast"):
            self.assertIn(field, state)

    def test_begin_records_the_start_before_the_leap(self):
        self.assertIn("Teleport::Begin(player, state, spellId);", self.body("void Begin(Player* player, std::uint32_t spellId, Unit* explicitTarget)"))
        self.assertIn("ReversalBegin(player, state, spellId);", self.body("void Begin(Player* player, State& state, uint32 spellId)"))
        # and Begin is what OnCast calls, which runs before the launch phase's leap
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertLess(combat.index("Wizard::Begin(player, shell.spellId"), combat.index("void Finish()"))

    def test_the_facing_hooks_are_wired(self):
        self.assertIn("TeleportBegin(player, state, spellId);", self.body("void Begin(Player* player, State& state, uint32 spellId)"))
        self.assertIn("if (Teleport::Travels(id))\n            Teleport::FaceTravel(player, id);",
                      self.body("void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets"))

    def test_the_cast_hook_calls_the_return_for_the_reversal_rune_only(self):
        self.assertIn('if (IsSkill(id, "Teleport") && IsRune(id, "Reversal"))\n            Teleport::ReversalCast(player, id);',
                      self.body("void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets"))

    def test_every_other_end_of_the_window_calls_reversal_end(self):
        self.assertIn("ReversalEnd(player);", self.body("void EnterArchon(Player* player, uint32 form)"))
        self.assertIn("ReversalEnd(player);", self.body("void OnPlayerLogout(Player* player) override"))
        self.assertIn("ReversalEnd(player);", self.body("void OnPlayerMapChanged(Player* player) override"))
        update = self.body("void OnPlayerUpdate(Player* player, uint32 diff) override")
        self.assertIn("if (player->IsAlive())\n                    for (Timer& timer : due)\n                        timer.run(player);\n                else\n                    Teleport::ReversalEnd(player);", update)

    def test_wormhole_calamity_and_safe_passage_keep_their_code(self):
        cast = self.body("void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets")
        self.assertIn('if (IsSkill(id, "Teleport"))\n            Teleport::Cast(player, id);', cast)
        teleport = self.body("void Cast(Player* player, uint32 id)")
        self.assertNotIn("Reversal", teleport)
        for needle in ('IsRune(id, "Calamity")', 'IsRune(id, "Safe Passage")', 'WormholeOf(player, id)',
                       "SendSkillCooldown(player, id, 0);", "SendSkillCooldown(p, id, SkillCooldownMilliseconds(p, id));"):
            self.assertIn(needle, teleport)

    def test_the_tooltip_still_names_both_tokens(self):
        runes = (MODULE / "data/d3/wizard_runes.csv").read_text(encoding="utf-8")
        line = next(l for l in runes.splitlines() if l.startswith('"Teleport","D","Reversal"'))
        self.assertIn("{duration_seconds}", line)
        self.assertIn("{cooldown_seconds}", line)


MUTATIONS = [
    ("a recast does not return",
     "            player->NearTeleportTo(from.GetPositionX(), from.GetPositionY(), from.GetPositionZ(), facing, true);\n",
     "",
     ["recast_inside_the_window_returns_with_one_second",
      "the_return_cooldown_outlasts_nothing_afterwards"]),
    ("the return sets no one-second cooldown",
     "SendSkillCooldown(player, id, uint32(Numbers::Own(id, \"cooldown_seconds\").value_or(0) * 1000));",
     "",
     ["the_return_cooldown_is_one_second_exactly", "recast_inside_the_window_returns_with_one_second"]),
    ("the first cast leaves the core's cooldown showing",
     "ReversalClearCooldown(player, id);\n        After(player, seconds,",
     "After(player, seconds,",
     ["first_cast_opens_a_window_with_no_cooldown", "recast_inside_the_window_returns_with_one_second"]),
    ("clearing forgets the category's cooldown",
     "if (SpellInfo const* info = sSpellMgr->GetSpellInfo(id); info && info->GetCategory())\n                player->RemoveCategoryCooldown(info->GetCategory());",
     "",
     ["first_cast_opens_a_window_with_no_cooldown", "the_return_cooldown_is_one_second_exactly"]),
    ("the lapse leaves the whole cooldown, the window not subtracted",
     "SendSkillCooldown(player, id, full > open ? full - uint32(open) : 0);",
     "SendSkillCooldown(player, id, full);",
     ["an_unused_window_leaves_the_full_cooldown_less_the_window", "a_cooldown_reduction_is_taken_before_the_window_is",
      "the_cooldown_is_never_below_zero", "death_ends_the_window_and_the_time_open_is_counted"]),
    ("an early end subtracts the whole window, not the time it was open",
     "open = std::min(Now() - state.reversalSince, state.reversalUntil - state.reversalSince);",
     "open = state.reversalUntil - state.reversalSince;",
     ["death_ends_the_window_and_the_time_open_is_counted", "a_map_change_ends_the_window_and_there_is_no_return_across_maps"]),
    ("the lapse can go below zero",
     "full > open ? full - uint32(open) : 0",
     "full - uint32(open)",
     ["the_cooldown_is_never_below_zero"]),
    ("a lapsed window still returns you",
     "state.reversalRecast = state.reversalUntil > Now() && state.reversalSpell == spellId &&",
     "state.reversalRecast = state.reversalUntil && state.reversalSpell == spellId &&",
     ["a_window_that_ran_out_unnoticed_is_not_a_recast"]),
    ("a window on another map still counts",
     "state.reversalMap == player->GetMapId() &&\n                                   state.reversalInstance == player->GetInstanceId();",
     "true;",
     ["an_open_window_on_another_map_is_not_a_recast", "an_instance_change_is_a_map_change"]),
    ("a recast overwrites the place to return to",
     "if (!state.reversalRecast)\n            {\n                state.reversalFrom",
     "{\n                state.reversalFrom",
     ["recast_inside_the_window_returns_with_one_second"]),
    ("an old window's timer ends the new one",
     "if (StateOf(p).reversalWindow != window)\n                          return;",
     "",
     ["an_old_windows_timer_does_not_end_the_next_one"]),
    ("ending forgets to close the window",
     "state.reversalUntil = 0;\n            ++state.reversalWindow;\n        }\n        uint32 const full",
     "}\n        uint32 const full",
     ["death_ends_the_window_and_the_time_open_is_counted"]),
    ("the facing is forced to 0",
     "TravelAngle(from, landing), true);",
     "0.0f, true);",
     ["a_teleport_faces_the_way_it_travelled", "archon_teleport_faces_the_way_it_travelled"]),
    ("the landing is read from the position, which has not moved until the ack (the PM's mutant)",
     "Position const landing = player->GetTeleportDest();",
     "Position const landing = player->GetPosition();",
     ["a_teleport_faces_the_way_it_travelled", "the_landing_is_the_pending_destination_not_the_position",
      "archon_teleport_faces_the_way_it_travelled"]),
    ("the start is read from the position, not the pending destination",
     "return player->IsBeingTeleportedNear() ? Position(player->GetTeleportDest()) : player->GetPosition();",
     "return player->GetPosition();",
     ["a_recast_before_the_first_ack_returns_from_the_true_landing"]),
    ("a leap that never happened is turned anyway",
     "if (!player->IsBeingTeleportedNear())\n            return;\n        Position const landing",
     "Position const landing",
     ["a_leap_that_did_not_happen_is_not_turned"]),
    ("the return is forced to face 0",
     "float const facing = TravelAngle(state.travelFrom, from);",
     "float const facing = 0.0f;",
     ["a_reversal_return_faces_its_travel_direction"]),
    ("the return restores the start's own facing, as it did",
     "float const facing = TravelAngle(state.travelFrom, from);",
     "float const facing = from.GetOrientation();",
     ["a_reversal_return_faces_its_travel_direction"]),
    ("a cast that went nowhere is turned to the angle of nothing",
     "return from.GetExactDist2d(&to) > 0.1f ? from.GetAbsoluteAngle(&to) : from.GetOrientation();",
     "return from.GetAbsoluteAngle(&to);",
     ["a_cast_that_went_nowhere_keeps_its_facing", "a_return_of_no_distance_keeps_the_facing_it_had"]),
    ("the recast's leap is faced as well as its return",
     "if (state.reversalRecast && IsRune(id, \"Reversal\"))\n                return;",
     "",
     ["a_reversal_return_faces_its_travel_direction"]),
    ("the Archon Teleport does not travel",
     " || id == ArchonAbilityId(\"Teleport\")",
     "",
     ["archon_teleport_faces_the_way_it_travelled"]),
    ("the start is never recorded",
     "if (Travels(spellId))\n                state.travelFrom = Where(player);",
     "",
     ["a_teleport_faces_the_way_it_travelled"]),
    ("every spell travels",
     "return IsSkill(id, \"Teleport\") || id == ArchonAbilityId(\"Teleport\");",
     "return true;",
     ["other_spells_do_not_travel"]),
    ("every Teleport rune is treated as Reversal",
     'if (!IsRune(spellId, "Reversal"))\n                return;',
     "",
     ["other_runes_are_not_touched"]),
]


class MutationsAreCaught(unittest.TestCase):
    def test_each_defect_fails_the_cases_that_name_it(self):
        source = WIZARD_CPP.read_text(encoding="utf-8")
        for index, (label, old, new, expected) in enumerate(MUTATIONS):
            with self.subTest(label):
                self.assertEqual(source.count(old), 1, "mutation %r does not match once" % label)
                caught = failing(source.replace(old, new), "mutant%d" % index)
                self.assertTrue(set(expected) <= set(caught), "%s: expected %s to fail, failed %s" % (label, expected, caught))


class Today(unittest.TestCase):
    """The same cases against code that does nothing for Reversal fail: nothing handled it."""

    def test_nothing_on_the_old_code_returns_you(self):
        stubs = ["Position Where(Player* player) { return player->GetPosition(); }", "bool Travels(uint32) { return false; }", "float TravelAngle(Position const&, Position const&) { return 0; }",
                 "void TeleportBegin(Player*, State&, uint32) {}", "void FaceTravel(Player*, uint32) {}",
                 "void ReversalClearCooldown(Player*, uint32) {}", "void ReversalBegin(Player*, State&, uint32) {}",
                 "void ReversalEnd(Player*) {}", "void ReversalCast(Player*, uint32) {}"]
        caught = failing("", "today", stub_functions=stubs)
        for case in ("first_cast_opens_a_window_with_no_cooldown", "recast_inside_the_window_returns_with_one_second",
                     "an_unused_window_leaves_the_full_cooldown_less_the_window",
                     "a_teleport_faces_the_way_it_travelled", "a_reversal_return_faces_its_travel_direction",
                     "archon_teleport_faces_the_way_it_travelled"):
            self.assertIn(case, caught)


if __name__ == "__main__":
    unittest.main()
