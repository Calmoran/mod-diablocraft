"""The devices a class lays on the ground, the shared piece (src/combat/dc_ground_device*.h/.cpp), diablocraft-vawmy.32.

What this proves, and how:

  * **The rules that need no core type.** tests/ground_device/harness.cpp compiles the real dc_ground_device_math.h and is driven with cases worked
    out from the brief's words, not from the code: a device fires nothing before it is armed; a Proximity device looks for an enemy once every look
    interval, fires once when one stands in reach and is gone; a Command device never fires by itself and can be detonated once armed; a Periodic
    device fires every interval while an enemy stands in range, is ready (and waits, silently) when none does, and fires the moment one comes; a
    device is gone when its life is over (the end inclusive) and never without a life; no more than `most` of a kind stand and the oldest give way;
    a lag spike does not pay out an unbounded backlog. The enemy test is asked only when it decides something. Planted differences in a scratch
    copy of the header must each make the driver fail.
  * **The wiring.** The piece is not a creature: nothing is summoned but the optional display holder (a friendly, untouchable stock trigger), no
    monster is counted, no loot or experience is given; devices go with their owner on death, logout and floor change; a firing runs the class's
    own callback outside the piece's lock; Detonate fires the armed Command devices of one kind in the order they were laid; the look interval is
    the tunable `ground_device_look_seconds` (0.25, the designer's standing default for a trigger check); the scripts are registered in Combat::RegisterScripts.
    The shared files name no class and no skill (test_class_checks.py holds that).

What it does not prove: anything on a running server (the client sees a display only if a skill asks for one).

    python mod-diablocraft/scripts/tests/combat/test_ground_device.py
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src/combat"
MATH = SRC / "dc_ground_device_math.h"
ENGINE = SRC / "dc_ground_device.cpp"
HEADER = SRC / "dc_ground_device.h"
COMBAT = SRC / "dc_combat.cpp"
HARNESS = MODULE / "tests/ground_device/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def cases():
    """[(command line, expected output line or None)] from the device's meaning."""
    out = []

    def spec(mode, radius, arm, life, interval, most):
        out.append((T("spec", mode, radius, arm, life, interval, most), None))

    def step(diff, near, look, want):
        out.append((T("step", diff, near, look), want))

    # Proximity (12 yards, armed after 1.5 s, a life of 30 s, a look every 250 ms)
    spec("proximity", 12, 1500, 30000, 0, 4)
    step(1000, 1, 250, "fires=0 gone=0 asked=0")       # not armed: nothing fires and nobody is asked
    out.append((T("armed"), "0"))
    step(500, 1, 250, "fires=1 gone=1 asked=1")        # armed at 1.5 s and an enemy there: it fires and is gone
    spec("proximity", 12, 1500, 30000, 0, 4)
    step(2000, 0, 250, "fires=0 gone=0 asked=1")       # armed, looked, nobody there
    out.append((T("armed"), "1"))
    step(100, 1, 250, "fires=0 gone=0 asked=0")        # between looks: it does not look, so it does not fire
    step(100, 1, 250, "fires=0 gone=0 asked=0")
    step(100, 1, 250, "fires=1 gone=1 asked=1")        # the look comes due
    spec("proximity", 12, 1500, 30000, 0, 4)
    step(1499, 1, 250, "fires=0 gone=0 asked=0")       # one ms short of armed
    step(1, 1, 250, "fires=1 gone=1 asked=1")          # armed at exactly 1.5 s (the end inclusive), and the look falls due in the same step
    spec("proximity", 12, 0, 30000, 0, 4)
    step(250, 1, 250, "fires=1 gone=1 asked=1")        # no arming delay: the first look fires
    spec("proximity", 12, 0, 30000, 0, 4)
    step(29999, 0, 250, "fires=0 gone=0 asked=1")      # a life of 30 s: not over at 29,999 ms ...
    step(1, 0, 250, "fires=0 gone=1 asked=0")          # ... over at 30,000, the end inclusive
    spec("proximity", 12, 0, 30000, 0, 4)
    step(30000, 1, 250, "fires=1 gone=1 asked=1")      # fires on its last step and is gone
    spec("proximity", 12, 0, 0, 0, 4)
    step(1000000, 0, 250, "fires=0 gone=0 asked=1")    # no life: it stands until it fires
    spec("proximity", 12, 0, 30000, 0, 4)
    step(1000, 1, 0, "fires=0 gone=0 asked=0")         # no look interval: it never looks
    # Command (armed after 1 s, a life of 30 s)
    spec("command", 8, 1000, 30000, 500, 4)   # an interval it must ignore
    step(500, 1, 250, "fires=0 gone=0 asked=0")
    out.append((T("detonable"), "0"))                  # not armed: a detonation passes it by
    step(500, 1, 250, "fires=0 gone=0 asked=0")        # armed, an enemy beside it: it still does not fire by itself
    out.append((T("detonable"), "1"))
    step(60000, 1, 250, "fires=0 gone=1 asked=0")      # but it lapses at the end of its life
    spec("proximity", 8, 0, 0, 0, 4)
    out.append((T("detonable"), "0"))                  # only a Command device is detonated
    spec("periodic", 8, 0, 0, 500, 2)
    out.append((T("detonable"), "0"))
    # Periodic (60 yards, armed at once, a life of 30 s, a shot every 500 ms)
    spec("periodic", 60, 0, 30000, 500, 2)
    step(400, 1, 250, "fires=0 gone=0 asked=0")        # nothing due, nobody asked
    step(100, 1, 250, "fires=1 gone=0 asked=1")        # 500 ms: the first shot
    step(1250, 1, 250, "fires=2 gone=0 asked=1")       # two whole intervals, 250 ms over
    step(250, 1, 250, "fires=1 gone=0 asked=1")        # the 250 ms over and 250 more make the next
    step(2000, 0, 250, "fires=0 gone=0 asked=1")       # nobody in range: no shot, and the turret is left ready
    step(10, 1, 250, "fires=1 gone=0 asked=1")         # the moment one stands there it shoots (ready + 10 ms)
    step(490, 1, 250, "fires=1 gone=0 asked=1")        # then every interval again
    spec("periodic", 60, 1000, 30000, 500, 2)
    step(600, 1, 250, "fires=0 gone=0 asked=0")        # not armed: it does not shoot
    step(600, 1, 250, "fires=1 gone=0 asked=1")        # armed on this step: shoots
    spec("periodic", 60, 0, 30000, 500, 2)
    step(100000, 1, 250, "fires=40 gone=1 asked=1")    # a lag spike pays at most 40 shots (and its life is over)
    spec("periodic", 60, 0, 0, 500, 2)
    step(100000, 1, 250, "fires=40 gone=0 asked=1")
    step(500, 1, 250, "fires=1 gone=0 asked=1")        # the rest of the backlog is dropped, not paid later
    spec("periodic", 60, 0, 30000, 0, 2)
    step(5000, 1, 250, "fires=0 gone=0 asked=0")       # no interval: it never shoots
    spec("periodic", 60, 0, 30000, 500, 2)
    step(29999, 1, 250, "fires=40 gone=0 asked=1")
    step(1, 1, 250, "fires=0 gone=1 asked=0")          # the end of its life, the end inclusive
    # the cap of a kind: the oldest give way
    for placed, most, want in ((0, 4, 0), (3, 4, 0), (4, 4, 1), (5, 4, 2), (7, 4, 4), (4, 1, 4), (1, 1, 1), (0, 1, 0), (9, 0, 0), (0, 0, 0)):
        out.append((T("overflow", placed, most), str(want)))
    # the shared clock: whole intervals, the rest kept, no interval none, a cap and a cleared backlog
    for clock, diff, interval, cap, want in ((0, 250, 250, 40, "due=1 clock=0"), (100, 100, 250, 40, "due=0 clock=200"), (0, 1000, 250, 40, "due=4 clock=0"),
                                              (240, 20, 250, 40, "due=1 clock=10"), (0, 100000, 250, 40, "due=40 clock=0"), (0, 100, 0, 40, "due=0 clock=0"),
                                              (0, 1000, 250, 2, "due=2 clock=0"), (0, 1100, 250, 2, "due=2 clock=0"), (30, 0, 250, 40, "due=0 clock=30")):
        out.append((T("due", clock, diff, interval, cap), want))
    return out


def drive(header_text, name="real"):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_ground_device_math.h": header_text})
    work = Path(tempfile.mkdtemp(prefix="groundev-%s-" % name, dir=str(SCRATCH)))
    try:
        lines = cases()
        (work / "cases.txt").write_text("\n".join(line for line, _ in lines) + "\n")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return [w for _, w in lines if w is not None], run.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Rules(unittest.TestCase):
    def test_every_rule_agrees_with_the_brief(self):
        want, got = drive(MATH.read_text(encoding="utf-8"))
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        want, _ = drive(real)
        mutants = {
            "overflow_waits_for_one_more": ("return most > 0 && placed >= most ? placed - most + 1 : 0;", "return most > 0 && placed > most ? placed - most + 1 : 0;"),
            "overflow_takes_one": ("placed - most + 1 : 0;", "1 : 0;"),
            "no_cap_is_a_cap": ("return most > 0 && placed >= most", "return placed >= most"),
            "armed_one_ms_late": ("return state.age >= spec.armMs;", "return state.age > spec.armMs;"),
            "the_clock_end_is_exclusive": ("while (clock >= interval && due < cap)", "while (clock > interval && due < cap)"),
            "the_clock_pays_the_backlog": ("        if (clock >= interval)\n            clock = 0;\n        return due;", "        return due;"),
            "no_interval_runs": ("        if (interval <= 0)\n        {\n            clock = 0;\n            return 0;\n        }", ""),
            "fires_before_armed": ("if (armed && looks && enemyNear())", "if (looks && enemyNear())"),
            "fires_without_a_look": ("if (armed && looks && enemyNear())", "if (armed && enemyNear())"),
            "fires_without_an_enemy": ("if (armed && looks && enemyNear())", "if (armed && looks)"),
            "stays_after_firing": ("                out.fires = 1;\n                out.gone = true;", "                out.fires = 1;"),
            "fires_twice": ("                out.fires = 1;\n                out.gone = true;", "                out.fires = 2;\n                out.gone = true;"),
            "life_end_is_exclusive": ("if (spec.lifetimeMs > 0 && state.age >= spec.lifetimeMs)", "if (spec.lifetimeMs > 0 && state.age > spec.lifetimeMs)"),
            "no_life_is_over_at_once": ("if (spec.lifetimeMs > 0 && state.age >= spec.lifetimeMs)", "if (state.age >= spec.lifetimeMs)"),
            "the_shot_clock_runs_before_arming": ("            if (!armed || spec.intervalMs <= 0)\n                state.sinceShot = 0;", "            if (spec.intervalMs <= 0)\n                state.sinceShot = 0;"),
            "shoots_without_an_enemy": ("if (state.sinceShot >= spec.intervalMs && enemyNear())", "if (state.sinceShot >= spec.intervalMs)"),
            "not_left_ready": ("                else if (state.sinceShot >= spec.intervalMs)\n                    state.sinceShot = spec.intervalMs;", "                else if (state.sinceShot >= spec.intervalMs)\n                    state.sinceShot = 0;"),
            "one_shot_a_step": ("out.fires = std::min(40u, static_cast<unsigned>(state.sinceShot / spec.intervalMs));", "out.fires = 1;"),
            "no_shot_cap": ("std::min(40u, static_cast<unsigned>(state.sinceShot / spec.intervalMs))", "static_cast<unsigned>(state.sinceShot / spec.intervalMs)"),
            "the_remainder_is_lost": ("state.sinceShot -= out.fires * spec.intervalMs;", "state.sinceShot = 0;"),
            "the_backlog_is_paid_later": ("                    if (state.sinceShot >= spec.intervalMs)\n                        state.sinceShot = 0; // a backlog past the cap is dropped, not paid out later\n", ""),
            "no_shot_interval_runs": ("if (!armed || spec.intervalMs <= 0)", "if (!armed)"),
            "a_command_device_fires": ("        else if (spec.mode == Mode::Periodic)", "        else if (spec.mode != Mode::Proximity)"),
            "any_device_is_detonable": ("return spec.mode == Mode::Command && Armed(state, spec);", "return Armed(state, spec);"),
            "an_unarmed_device_is_detonable": ("return spec.mode == Mode::Command && Armed(state, spec);", "return spec.mode == Mode::Command;"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = drive(real.replace(old, new, 1), name)
                self.assertNotEqual(want, got, name + " survived")


def engine_failures(engine, combat, header):
    """What is wrong with the engine half ([] when it is right)."""
    flat = re.sub(r"\s+", " ", engine)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    def body(opening, closing):
        at = flat.find(opening)
        end = flat.find(closing, at + len(opening)) if at >= 0 else -1
        return flat[at:end] if at >= 0 and end > at else ""

    place = body("void Place(Player* player, Setup const& setup, Position const& at) {", "unsigned Detonate(")
    need("Place exists", bool(place))
    need("no player lays nothing", "if (!player) return;" in place)
    need("the oldest of the kind give way to the cap of the kind, counted under the lock",
         "std::lock_guard<std::mutex> guard(mutex);" in place and
         "std::count_if(laid.begin(), laid.end(), [&](Device const& d) { return d.setup.kind == setup.kind; })" in place and
         "for (std::size_t give = Overflow(of, setup.spec.most); give > 0; --give)" in place and
         "auto oldest = std::find_if(laid.begin(), laid.end(), [&](Device const& d) { return d.setup.kind == setup.kind; }); away.push_back(oldest->holder); laid.erase(oldest);" in place)
    need("the display is shown and the device laid, then the displaced are hidden outside the lock",
         place.find("Show(player, device); laid.push_back(device);") < place.find("for (ObjectGuid holder : away) Hide(player, holder);"))

    detonate = body("unsigned Detonate(Player* player, std::uint32_t kind) {", "std::size_t Count(")
    need("Detonate exists", bool(detonate))
    need("a dead player detonates nothing", "if (!player || !player->IsAlive()) return 0;" in detonate)
    need("the armed Command devices of the kind fire, in the order they were laid, and are taken away",
         "if (device.setup.kind == kind && Detonable(device.state, device.setup.spec)) firing.push_back(device);" in detonate and
         "std::erase_if(laid, [&](Device const& d) { return d.setup.kind == kind && Detonable(d.state, d.setup.spec); });" in detonate)
    need("a firing runs outside the lock, then the display goes",
         detonate.find("std::lock_guard<std::mutex> guard(mutex);") < detonate.find("for (Device const& device : firing) { Discharge(player, device, Near(player, device)); Hide(player, device.holder); }"))
    need("the count is how many fired", "return static_cast<unsigned>(firing.size());" in detonate)

    update = body("void OnPlayerUpdate(Player* player, uint32 diff) override {", "void OnPlayerLogout(")
    need("the update exists", bool(update))
    need("a dead owner loses every device", "if (!player->IsAlive()) { Clear(player); return; }" in update)
    need("a step is the rule with the tunable look interval and a lazy enemy test", "Advance(device.state, device.setup.spec, diff, LookEveryMs()," in update and
         "enemies = Near(player, device); looked = true; return !enemies.empty();" in update)
    need("each firing is the class's callback outside the lock, with the enemies already found",
         "for (unsigned i = 0; i < outcome.fires; ++i) Discharge(player, device, looked ? enemies : Near(player, device));" in update and
         update.find("Discharge(") < update.rfind("std::lock_guard<std::mutex> guard(mutex);"))
    need("a device that is gone has its display hidden and is taken away", "if (outcome.gone) { Hide(player, device.holder); gone.push_back(device.serial); }" in update and
         "std::erase_if(found->second, [&](Device const& d) { return std::find(gone.begin(), gone.end(), d.serial) != gone.end(); });" in update)
    need("each stored device takes its new state, and a device laid during the update is kept", "stored.state = updated->state;" in update)

    need("devices go with the owner on logout and floor change",
         "void OnPlayerLogout(Player* player) override { Clear(player); }" in flat and "void OnPlayerMapChanged(Player* player) override { Clear(player); }" in flat and
         "PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED" in flat)
    places = body("std::vector<Position> Places(Player const* player, std::uint32_t kind) {", "void Clear(Player* player) {")
    need("Places lists the places of the devices of the kind, in the order laid, under the lock",
         "std::lock_guard<std::mutex> guard(mutex);" in places and "if (device.setup.kind == kind) places.push_back(device.at);" in places and
         "if (!player) return places;" in places)
    clear = body("void Clear(Player* player) {", "void RegisterScripts()")
    need("Clear takes every device and hides every display, outside the lock", "removed = std::move(found->second); devices.erase(found); }" in clear and
         clear.find("devices.erase(found); }") < clear.find("for (Device const& device : removed) Hide(player, device.holder);"))

    need("the look interval is the tunable, in ms", 'return DC::Tunables::Get("combat", "ground_device_look_seconds") * 1000.0;' in flat)
    need("a device is not a creature: the one summon is the display holder, behind the asked display",
         flat.count("SummonCreature(") == 1 and "if (!device.setup.display) return;" in flat and
         "TEMPSUMMON_TIMED_DESPAWN" in flat and "holder->SetFaction(HolderFaction); holder->SetImmuneToAll(true);" in flat and "constexpr std::uint32_t HolderEntry = 12999; constexpr std::uint32_t HolderFaction = 35;" in flat)
    need("a firing is the class's callback, told the device's place and the enemies",
         "void Discharge(Player* player, Device const& device, std::vector<Unit*> const& enemies) { if (device.setup.fire) device.setup.fire(player, device.at, enemies); }" in flat)
    need("the enemies are those the record's area resolves to around the device", "return Combat::Enemies(player, device.setup.record, device.at, device.setup.spec.radiusYards);" in flat)
    need("a device deals no loot, experience or progress of its own", not re.search(r"Loot|Experience|Rift|GiveXP|Kill", engine))
    need("the scripts are registered with the combat's", "GroundDevice::RegisterScripts();" in combat and '#include "dc_ground_device.h"' in combat)
    need("the public header declares the five calls",
         all(sig in re.sub(r"\s+", " ", header) for sig in (
             "void Place(Player* player, Setup const& setup, Position const& at);", "unsigned Detonate(Player* player, std::uint32_t kind);",
             "std::size_t Count(Player const* player, std::uint32_t kind);", "void Clear(Player* player);", "void RegisterScripts();",
             "std::vector<Position> Places(Player const* player, std::uint32_t kind);")))
    return wrong


class Wiring(unittest.TestCase):
    def test_the_engine(self):
        self.assertEqual([], engine_failures(ENGINE.read_text(encoding="utf-8"), COMBAT.read_text(encoding="utf-8"), HEADER.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        engine, combat, header = (p.read_text(encoding="utf-8") for p in (ENGINE, COMBAT, HEADER))
        mutants = {
            "no_cap": ("for (std::size_t give = Overflow(of, setup.spec.most); give > 0; --give)", "for (std::size_t give = 0; give > 0; --give)"),
            "the_cap_counts_every_kind": ("return d.setup.kind == setup.kind; }));\n            for", "return true; }));\n            for"),
            "the_newest_give_way": ("auto oldest = std::find_if(laid.begin(), laid.end()", "auto oldest = std::find_if(laid.rbegin(), laid.rend()") if False else
            ("away.push_back(oldest->holder);\n                laid.erase(oldest);", "away.push_back(laid.back().holder);\n                laid.pop_back();"),
            "a_dead_player_detonates": ("if (!player || !player->IsAlive())\n            return 0;", "if (!player)\n            return 0;"),
            "an_unarmed_device_detonates": ("if (device.setup.kind == kind && Detonable(device.state, device.setup.spec))\n                    firing.push_back(device);", "if (device.setup.kind == kind)\n                    firing.push_back(device);"),
            "detonated_devices_stay": ("            std::erase_if(laid,\n                          [&](Device const& d) { return d.setup.kind == kind && Detonable(d.state, d.setup.spec); });\n", ""),
            "a_dead_owner_keeps_them": ("if (!player->IsAlive())\n                {\n                    Clear(player);\n                    return;\n                }", "if (!player->IsAlive())\n                    return;"),
            "the_look_interval_is_a_literal": ('DC::Tunables::Get("combat", "ground_device_look_seconds") * 1000.0', "250.0"),
            "the_look_interval_is_in_seconds": ('DC::Tunables::Get("combat", "ground_device_look_seconds") * 1000.0', 'DC::Tunables::Get("combat", "ground_device_look_seconds")'),
            "stays_after_logout": ("void OnPlayerLogout(Player* player) override\n            {\n                Clear(player);\n            }", "void OnPlayerLogout(Player* player) override\n            {\n            }"),
            "stays_over_a_floor_change": ("void OnPlayerMapChanged(Player* player) override\n            {\n                Clear(player);\n            }", "void OnPlayerMapChanged(Player* player) override\n            {\n            }"),
            "always_a_creature": ("if (!device.setup.display)\n                return;", ""),
            "a_hostile_holder": ("holder->SetFaction(HolderFaction);\n", ""),
            "a_holder_that_can_be_hit": ("holder->SetImmuneToAll(true);\n", ""),
            "enemies_from_the_owner": ("device.at, device.setup.spec.radiusYards)", "player->GetPosition(), device.setup.spec.radiusYards)"),
            "the_firing_is_dropped": ("device.setup.fire(player, device.at, enemies);", ";"),
            "places_of_every_kind": ("            if (device.setup.kind == kind)\n                places.push_back(device.at);", "            places.push_back(device.at);"),
            "the_displays_stay": ("        for (Device const& device : removed)\n            Hide(player, device.holder);", ""),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, engine.count(old), name + " does not apply")
                self.assertNotEqual([], engine_failures(engine.replace(old, new, 1), combat, header), name + " survived")
        old = "        GroundDevice::RegisterScripts();\n"
        self.assertEqual(1, combat.count(old))
        self.assertNotEqual([], engine_failures(engine, combat.replace(old, "", 1), header))

    def test_the_look_interval_is_alexs_standing_default(self):
        with (MODULE / "data/tunables/combat.csv").open(encoding="utf-8", newline="") as stream:
            rows = {r["name"]: r for r in csv.DictReader(stream)}
        row = rows["ground_device_look_seconds"]
        self.assertEqual(("0.25", "", "seconds"), (row["d3_value"], row["value"], row["unit"]))
        self.assertIn("standing default", row["notes"])

    def test_the_math_header_is_the_only_one_the_harness_needs(self):
        text = MATH.read_text(encoding="utf-8")
        self.assertEqual([], [m for m in re.findall(r'#include "([^"]+)"', text)])
        self.assertIn("namespace DC::Combat::GroundDevice", text)


if __name__ == "__main__":
    unittest.main()
