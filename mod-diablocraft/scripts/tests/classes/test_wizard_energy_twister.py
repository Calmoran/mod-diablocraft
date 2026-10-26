"""Energy Twister's travel: the base skill and its travelling runes wander forward for the skill's duration.

    python3 mod-diablocraft/scripts/tests/classes/test_wizard_energy_twister.py

  * src/classes/wizard/dc_twister_math.h compiled into a small driver and fed the sheet's numbers: the twister heads from
    the Wizard toward the aim point (its facing when the aim is at its feet), goes forward at the speed row, turns once
    per turn interval within the turn limit (forward-biased: a triangle, never past the limit, a limit of 0 is a straight
    path), covers about the skill's 20-yard range over its 6-second dot_duration_seconds, and ticks every
    interval_seconds from the first moment (12 ticks, each damage_pct / 12) at the point its path reaches; single-rule
    mutants of the header fail the same driver;
  * the four tunables rows (data/tunables/wizard.csv) and their rendering in tunables_0012;
  * source guards that the Wizard files start a travelling twister on every Energy Twister cast but Wicked Wind (which
    keeps generate_spells.py's stationary ground), reads the rows by name, strikes the base skill's share around the
    path's point each tick, moves the stock trigger carrier along the same path, and leaves the two hooks (the straight
    path, Raging Storm on every twister). They prove the calls are there, not that they run; syntax_check.sh compiles
    the C++.
"""
import csv
import math
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import wizard_source  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
MATH = MODULE / "src/classes/wizard/dc_twister_math.h"
SPELLS = MODULE / "scripts/generate/classes/generate_spells.py"
TUNABLES = MODULE / "data/tunables/wizard.csv"
# the render the sheet ships as now (every render carries the whole sheet; an applied one is frozen, so the speed row
# of the 3ypq2 render, tunables_0012, still says 3.3)
MIGRATION = MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
VALUES = MODULE / "data/d3/wizard_skill_values.csv"
TARGETING = MODULE / "data/d3/skill_targeting.csv"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch/energy-twister"

DRIVER = r"""
#include "dc_twister_math.h"
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
using namespace DC::Combat::Wizard::Twister;

int main(int, char** argv)
{
    std::ifstream in(argv[1]);
    std::string line;
    while (std::getline(in, line))
    {
        std::istringstream s(line);
        std::string op;
        s >> op;
        if (op == "turn") { double l, a, b; s >> l >> a >> b; std::printf("%.6f\n", Turn(l, a, b) * 180.0 / 3.14159265358979323846); }
        else if (op == "heading") { double wx, wy, f, ax, ay; s >> wx >> wy >> f >> ax >> ay; std::printf("%.6f\n", Heading({wx, wy}, f, {ax, ay})); }
        else if (op == "ticks") { double l, i; s >> l >> i; std::printf("%zu\n", Ticks(l, i)); }
        else if (op == "pct") { double d; std::size_t n; s >> d >> n; std::printf("%.6f\n", TickPct(d, n)); }
        else if (op == "path" || op == "at")
        {
            double x, y, h, v, life, turn, limit, t = 0, r;
            s >> x >> y >> h >> v >> life >> turn >> limit;
            if (op == "at")
                s >> t;
            std::vector<double> rolls;
            while (s >> r)
                rolls.push_back(r);
            auto path = Path({x, y}, h, v, life, turn, limit, rolls);
            if (op == "at") { Point p = At(path, turn, life, t); std::printf("%.4f %.4f\n", p.x, p.y); }
            else { for (Point const& p : path) std::printf("%.4f %.4f ", p.x, p.y); std::printf("\n"); }
        }
    }
}
"""


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def tunable(name):
    row = next(r for r in read(TUNABLES) if r["name"] == name)
    return float(row["value"] or row["d3_value"])


def sheet(token, rune=""):
    return float(next(r["value"] for r in read(VALUES)
                      if r["skill"] == "Energy Twister" and r["rune"] == rune and r["token"] == token and not r["qualifier"]))


SPEED = tunable("energy_twister_speed_yards_per_second")
LIMIT = tunable("energy_twister_turn_limit_degrees")
TURN = tunable("energy_twister_turn_interval_seconds")
LIFE, INTERVAL, DAMAGE = sheet("dot_duration_seconds"), sheet("interval_seconds"), sheet("damage_pct")
GRID = [i / 10 for i in range(10)]


def drive(lines, header_text=None, name="real"):
    """One answer line per input line; None when a mutant does not build or run."""
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="twister-%s-" % name.replace(" ", "-"), dir=str(SCRATCH)))
    try:
        (work / "dc_twister_math.h").write_text(header_text or MATH.read_text(encoding="utf-8"), encoding="utf-8")
        (work / "driver.cpp").write_text(DRIVER, encoding="utf-8")
        binary = work / "driver"
        built = subprocess.run([compiler, "-std=c++17", "-O1", str(work / "driver.cpp"), "-o", str(binary)],
                               capture_output=True, text=True)
        if built.returncode:
            if header_text is None:
                raise AssertionError("driver did not compile:\n" + built.stderr[-3000:])
            return None
        (work / "cases.txt").write_text("\n".join(lines) + "\n")
        done = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return None if done.returncode else done.stdout.splitlines()


def walk(x, y, heading, rolls, limit=LIMIT, turn=TURN):
    """The expected path: legs of `turn` seconds at SPEED (the last one shorter), a turn of limit x (a - b) before every
    leg but the first."""
    points, t, i = [(x, y)], 0.0, 0
    while t < LIFE - 1e-9:
        if i:
            heading += math.radians(limit * (rolls[2 * i - 2] - rolls[2 * i - 1]))
        seconds = min(turn, LIFE - t)
        x, y = x + SPEED * seconds * math.cos(heading), y + SPEED * seconds * math.sin(heading)
        points.append((x, y))
        t, i = t + seconds, i + 1
    return points


def cases():
    rolls = [0.9, 0.1, 0.2, 0.7, 0.5, 0.5, 0.0, 0.99, 0.6, 0.3]
    lines = ["turn %r %r %r" % (LIMIT, a, b) for a in GRID for b in GRID]
    lines += ["heading 0 0 1.25 0 0", "heading 0 0 1.25 0 5", "heading 3 4 0 -2 4"]
    lines += ["ticks %r %r" % (LIFE, INTERVAL), "pct %r %d" % (DAMAGE, 12)]
    lines += ["path 10 20 0 %r %r %r %r %s" % (SPEED, LIFE, TURN, LIMIT, " ".join(map(repr, rolls))),
              "path 10 20 0 %r %r %r 0 %s" % (SPEED, LIFE, TURN, " ".join(map(repr, rolls))),
              "path 0 0 0 %r %r %r %r" % (SPEED, LIFE, TURN, LIMIT),
              # a turn interval that does not divide the life: the last leg is shorter, the distance the same
              "path 0 0 0 %r %r 4 %r 0.9 0.1" % (SPEED, LIFE, LIMIT)]
    lines += ["at 10 20 0 %r %r %r %r %r %s" % (SPEED, LIFE, TURN, LIMIT, t, " ".join(map(repr, rolls)))
              for t in (0, 0.5, 1.0, 2.75, 5.5, LIFE)]
    return lines, rolls


def expected(rolls):
    lines = ["%.6f" % (LIMIT * (a - b)) for a in GRID for b in GRID]
    lines += ["%.6f" % 1.25, "%.6f" % (math.pi / 2), "%.6f" % math.pi]
    lines += ["12", "%.6f" % (DAMAGE / 12)]
    fmt = lambda pts: " ".join("%.4f %.4f" % p for p in pts) + " "
    turning = walk(10, 20, 0, rolls)
    lines += [fmt(turning), fmt(walk(10, 20, 0, rolls, 0)), fmt(walk(0, 0, 0, [0.5] * 20)),
              fmt(walk(0, 0, 0, [0.9, 0.1], turn=4))]
    for t in (0, 0.5, 1.0, 2.75, 5.5, LIFE):
        i = min(int(t // TURN), len(turning) - 2)
        f = min(1.0, (t - i * TURN) / min(TURN, LIFE - i * TURN))
        (ax, ay), (bx, by) = turning[i], turning[i + 1]
        lines.append("%.4f %.4f" % (ax + (bx - ax) * f, ay + (by - ay) * f))
    return lines


class Numbers(unittest.TestCase):
    """The card's defaults as rows, every number a tunable; the sheet's own numbers for the ticks."""

    def test_the_rows(self):
        rows = {r["name"]: r for r in read(TUNABLES)}
        self.assertEqual(("15", "5", "yards per second"), tuple(rows["energy_twister_speed_yards_per_second"][k] for k in ("d3_value", "value", "unit")))
        self.assertEqual(("8", "", "yards"), tuple(rows["energy_twister_hit_radius_yards"][k] for k in ("d3_value", "value", "unit")))
        self.assertEqual(("", "45", "degrees"), tuple(rows["energy_twister_turn_limit_degrees"][k] for k in ("d3_value", "value", "unit")))
        self.assertEqual(("", "1", "seconds"), tuple(rows["energy_twister_turn_interval_seconds"][k] for k in ("d3_value", "value", "unit")))
        # the radius is the targeting sheet's
        with TARGETING.open(encoding="utf-8") as stream:
            twister = next(r for r in csv.reader(stream) if r and r[0] == "Energy Twister")
        self.assertEqual(float(twister[3]), tunable("energy_twister_hit_radius_yards"))
        # The designer's final speed (q-1014-07, diablocraft-1np46): 5, not the 3.3 the skill's 20-yard range over its 6 seconds
        # gave, and not D3's 15; the code reads it from the row, so the path's reach is 5 x 6 = 30 yards
        self.assertEqual(5.0, SPEED)
        self.assertAlmostEqual(30.0, SPEED * LIFE)

    def test_the_rows_are_rendered(self):
        text = MIGRATION.read_text(encoding="utf-8")
        for row in ("('wizard', 'energy_twister_speed_yards_per_second', 15.0, 5.0, 'yards per second', ",
                    "('wizard', 'energy_twister_hit_radius_yards', 8.0, NULL, 'yards', ",
                    "('wizard', 'energy_twister_turn_limit_degrees', NULL, 45.0, 'degrees', ",
                    "('wizard', 'energy_twister_turn_interval_seconds', NULL, 1.0, 'seconds', "):
            self.assertIn(row, text)

    def test_the_sheet(self):
        self.assertEqual((6, 0.5, 1525), (LIFE, INTERVAL, DAMAGE))


class Math(unittest.TestCase):
    def test_the_path_the_turns_and_the_ticks(self):
        lines, rolls = cases()
        self.assertEqual(expected(rolls), drive(lines))

    def test_the_shape(self):
        lines, rolls = cases()
        out = drive(lines)
        turns = [abs(float(v)) for v in out[:len(GRID) ** 2]]
        self.assertLessEqual(max(turns), LIMIT + 1e-9)
        # forward-biased: the mean turn is a third of the limit (a triangle), where an even spread would be half
        self.assertLess(sum(turns) / len(turns), LIMIT / 2.5)
        straight = [float(v) for v in out[len(GRID) ** 2 + 6].split()]
        self.assertTrue(all(abs(y - 20) < 1e-3 for y in straight[1::2]), "a turn limit of 0 is a straight line")
        ahead = [float(v) for v in out[len(GRID) ** 2 + 7].split()]
        self.assertAlmostEqual(ahead[-2], SPEED * LIFE, places=3)
        self.assertAlmostEqual(ahead[-2], 30, delta=0.5)  # 5 yards a second for the 6 seconds (ruling q-1014-07)

    def test_the_mutants_fail_the_same_driver(self):
        text = MATH.read_text(encoding="utf-8")
        mutants = {
            "an even spread": ("turnLimitDegrees * (roll1 - roll2)", "turnLimitDegrees * (2 * roll1 - 1)"),
            "no turn limit": ("turnLimitDegrees * (roll1 - roll2)", "180 * (roll1 - roll2)"),
            "the turns read the wrong rolls": ("roll(2 * (i - 1)), roll(2 * (i - 1) + 1)", "roll(2 * i), roll(2 * i + 1)"),
            "turns do not add up": ("heading += Turn(", "heading = Turn("),
            "the last leg full": ("std::fmin(turnSeconds, lifeSeconds - i * turnSeconds)", "turnSeconds"),
            "no tick at once": ("lifeSeconds / intervalSeconds + 1e-9)", "lifeSeconds / intervalSeconds - 1 + 1e-9)"),
            "the whole number each tick": ("damagePct / static_cast<double>(ticks)", "damagePct"),
            "at the leg's start": ("(path[i + 1].x - path[i].x) * f", "0 * f"),
            "aim at the feet": ("dx * dx + dy * dy < 0.01 ? facing", "dx * dx + dy * dy < 0.01 ? 0.0"),
            "away from the aim": ("std::atan2(dy, dx)", "std::atan2(-dy, -dx)"),
        }
        lines, rolls = cases()
        want = expected(rolls)
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, text.count(old), old)
                self.assertNotEqual(want, drive(lines, text.replace(old, new), name))


def body(text, signature):
    start = text.index(signature)
    depth, i = 0, text.index("{", start)
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[start:j + 1]
    raise AssertionError(signature)


class Source(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dispatch = wizard_source.named("dc_wizard.cpp")
        cls.text = wizard_source.named("dc_wizard_energy_twister.cpp")
        cls.helpers = wizard_source.named("dc_wizard_helpers.cpp")

    def test_every_travelling_twister_starts_wicked_wind_does_not(self):
        self.assertIn('return IsSkill(id, "Energy Twister") && !IsRune(id, "Wicked Wind");', body(self.text, "bool Wanders(uint32 id)"))
        cast = body(self.dispatch, "    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets")
        self.assertIn("if (EnergyTwister::Wanders(id))\n            EnergyTwister::Start(player, id, center);", cast)
        # Wicked Wind spins in place on the stock ground, untouched
        self.assertIn('GROUND_DOT_RUNES = ("Energy Twister - Wicked Wind",)', SPELLS.read_text(encoding="utf-8"))

    def test_the_numbers_come_from_the_rows_and_the_sheet(self):
        start = body(self.text, "void Start(Player* player, uint32 id, Position const& center)")
        for name in ("energy_twister_turn_interval_seconds", "energy_twister_speed_yards_per_second",
                     "energy_twister_hit_radius_yards", "energy_twister_turn_limit_degrees"):
            self.assertIn('DC::Tunables::Get("wizard", "%s")' % name, start)
        self.assertIn('Num(id, "dot_duration_seconds")', start)
        self.assertIn('Num(id, "interval_seconds")', start)
        # the base skill's damage_pct: Raging Storm's is the merged tornado's, Storm Chaser's its bolt's
        self.assertIn('Twister::TickPct(Num(BaseOf("Energy Twister"), "damage_pct"), ticks)', start)
        self.assertIn("Twister::Path(start, heading, twister.speed, twister.lifeSeconds, twister.turnSeconds, limit, rolls)", start)

    def test_each_tick_strikes_around_the_path(self):
        tick = body(self.text, "void TwisterTick(Player* player, unsigned serial, double t)")
        self.assertIn("Twister::At(twister->path, twister->turnSeconds, twister->lifeSeconds, t)", tick)
        self.assertIn("Combat::StrikeArea(player, id, at, radius, pct, true);", tick)
        start = body(self.text, "void Start(Player* player, uint32 id, Position const& center)")
        self.assertIn("After(player, k * interval, [serial, t = k * interval](Player* p) { TwisterTick(p, serial, t); });", start)
        self.assertIn("for (std::size_t k = 0; k < ticks; ++k)", start)

    def test_the_carrier_follows_the_same_path(self):
        start = body(self.text, "void Start(Player* player, uint32 id, Position const& center)")
        self.assertIn("player->SummonCreature(TWISTER_CARRIER_ENTRY,", start)
        self.assertRegex(start, r"TEMPSUMMON_TIMED_DESPAWN,\s+uint32\(twister\.lifeSeconds \* 1000\)")
        for call in ("carrier->SetDisplayId(TWISTER_DISPLAY);", "carrier->SetFaction(TWISTER_FACTION);", "carrier->SetImmuneToAll(true);"):
            self.assertIn(call, start)
        self.assertIn("constexpr uint32 TWISTER_CARRIER_ENTRY = 12999;", self.text)
        self.assertIn("constexpr uint32 TWISTER_FACTION = 35;", self.text)
        self.assertIn("After(player, leg * turn, [serial, leg](Player* p) { MoveTwister(p, serial, leg); });", start)
        move = body(self.text, "void MoveTwister(Player* player, unsigned serial, std::size_t leg)")
        self.assertIn("twister->path[leg + 1]", move)
        self.assertRegex(move, r"MovePoint\(0, to\.GetPositionX\(\), to\.GetPositionY\(\), to\.GetPositionZ\(\),\s+FORCED_MOVEMENT_NONE, float\(twister->speed\), 0\.0f, false\)")
        # gone with the summons on a map change and a logout
        self.assertIn("for (LiveTwister const& twister : state.twisters)\n            Despawn(player, twister.carrier);",
                      body(self.helpers, "void ClearSummons(Player* player)"))

    def test_the_hooks(self):
        start = body(self.text, "void Start(Player* player, uint32 id, Position const& center)")
        self.assertIn('ItemPowers::SkillSetTo(player, "Energy Twister", "straight_path", 0) > 0', start)
        self.assertIn('double const limit = straight ? 0 : DC::Tunables::Get("wizard", "energy_twister_turn_limit_degrees");', start)
        self.assertIn('IsRune(id, "Raging Storm") || ItemPowers::GrantsRune(player, "Energy Twister", "Raging Storm")', start)


if __name__ == "__main__":
    unittest.main()
