"""Urshi's arrival spot and beam, and D3's "Greater Rift Complete!" line (diablocraft-8fwkr; brief urshi-spawn-2026-10-22.md).

What this proves, and how:

  * **The decisions with no core in them.** tests/urshi_spawn/harness.cpp compiles the real dc_gr_urshi.h (SpawnAngles, FacingAngle, SpotFits) and
    dc_gr_complete.h (CompleteParts) and dc_rift_text.h (Fields) and is driven against a model written here: the eight directions tried (towards the players, then 45, 90 and
    135 degrees to each side, last away), the way to the players, a spot that fits (line of sight, at least the share of the wanted yards, no great
    climb), and the line's record with the colour of each part, its plural, a dropped unit at 0 and "0 seconds" for an empty clock. Mutants of all three headers fail it.
  * **The tunables.** rifts.csv holds gr_urshi_spawn_yards at 10 in the designer's column, and the two numbers the spot needs, marked PLACEHOLDER; the code
    reads exactly these.
  * **The beam is stock.** Spell 62893 "Blue Skybeam" is in the client's own Spell.dbc, a self dummy aura whose visual leads, through the stock visual
    and kit tables, to the effect "Skybeam, Blue" (Spells\\FrostBeam_State_Base.mdx); nothing ships (skipped where that file is not on this machine).
  * **The source scans.** BeginUrshi stands her at the spot (the core's collision walk from the Guardian, the angle taken from its facing, line of sight
    asked of the core, the Guardian's own spot as the fallback, facing the players), puts the beam on her with no end of its own, and the in-time
    kill sends the line once, in the pending branch, to every enrolled member who is online, over the DCRIFTTEXT channel
    (docs/contracts/rift-centre-text.md), and nothing in the file uses the core's area-trigger text any more.

What it does not prove: how it looks on a running server. The beam, the spot and the line are docs/test-diablocraft-8fwkr.md's, live.

    python mod-diablocraft/scripts/tests/rifts/test_urshi_spawn.py
"""
import csv
import math
import re
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
URSHI_H = "src/rifts/dc_gr_urshi.h"
COMPLETE_H = "src/rifts/dc_gr_complete.h"
TEXT_H = "src/rifts/dc_rift_text.h"
HARNESS = MODULE / "tests/urshi_spawn/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
TAU = 2 * math.pi
GREY, GREEN = "b2b2b2", "00ff00"


def read(path):
    return (MODULE / path).read_text(encoding="utf-8")


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def tunables():
    with (MODULE / "data/tunables/rifts.csv").open(encoding="utf-8", newline="") as stream:
        return {r["name"]: r for r in csv.DictReader(stream)}


def build_and_run(commands, urshi=None, complete=None, text=None):
    files = {"rifts/dc_gr_urshi.h": urshi or read(URSHI_H), "rifts/dc_gr_complete.h": complete or read(COMPLETE_H),
             "rifts/dc_rift_text.h": text or read(TEXT_H)}
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="urshispawn-", dir=str(SCRATCH)))
    try:
        (work / "cases.txt").write_text("\n".join("\t".join(str(c) for c in line) for line, _ in commands) + "\n")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return run.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def model_line(left):
    """The record's fields joined by '|': C, the kind, then a colour and the words of each part."""
    minutes, seconds = divmod(left, 60)
    units = []
    if minutes:
        units.append((GREEN, "%d %s" % (minutes, "minute" if minutes == 1 else "minutes")))
    if seconds or not minutes:
        units.append((GREEN, "%d %s" % (seconds, "second" if seconds == 1 else "seconds")))
    parts = [(GREY, "Greater Rift Complete! You finished with ")]
    for i, unit in enumerate(units):
        parts += [(GREY, " and ")] * (i > 0) + [unit]
    parts.append((GREY, " remaining."))
    return "|".join(["C", "gr_complete"] + [field for part in parts for field in part])


def model_angles(base):
    return ["%.9f" % ((base + k * math.pi / 4) % TAU) for k in (0, 1, -1, 2, -2, 3, -3, 4)]


def model_facing(fx, fy, tx, ty, fallback):
    if (fx, fy) == (tx, ty):
        return fallback
    angle = math.atan2(ty - fy, tx - fx)
    return angle + TAU if angle < 0 else angle


def model_fits(wanted, got, climb, los, share, most):
    return int(los and wanted > 0 and got >= wanted * share / 100 and abs(climb) <= most)


def cases():
    out = []
    for base in (0.0, 1.0, 3.0, 6.0, 0.3):
        out.append((("angles", base), " ".join(model_angles(base)) + " "))
    for args in ((0, 0, 5, 0, 9.0), (0, 0, 0, 5, 9.0), (0, 0, -5, 0, 9.0), (0, 0, 0, -5, 9.0), (3, 4, 3, 4, 1.25), (10, 10, 4, 4, 0.0)):
        out.append((("facing", *args), "%.9f" % model_facing(*args)))
    for args in ((10, 10, 0, 1, 70, 3), (10, 7, 0, 1, 70, 3), (10, 6.9, 0, 1, 70, 3), (10, 10, 3, 1, 70, 3), (10, 10, 3.1, 1, 70, 3), (10, 10, -3, 1, 70, 3),
                 (10, 10, -3.1, 1, 70, 3), (10, 10, 0, 0, 70, 3), (10, 0, 0, 1, 70, 3), (0, 10, 0, 1, 70, 3), (10, 5, 0, 1, 50, 3), (10, 4.9, 0, 1, 50, 3)):
        out.append((("fits", *args), str(model_fits(args[0], args[1], args[2], bool(args[3]), args[4], args[5]))))
    for left in (828, 44, 780, 60, 61, 1, 0, 3599, 120, 59):
        out.append((("line", left), model_line(left)))
    return out


class Rules(unittest.TestCase):
    def test_the_headers_agree_with_the_model(self):
        want = [expect for _, expect in cases()]
        self.assertEqual(want, build_and_run(cases()))

    def test_the_contract_example_and_the_wire_cap(self):
        contract = (REPO / "docs/contracts/rift-centre-text.md").read_text(encoding="utf-8")
        self.assertIn("DCRIFTTEXT<TAB>" + model_line(300), contract)                 # the contract's example is the 300-second record
        self.assertIn("Prefix **`DCRIFTTEXT`**", contract)
        self.assertIn('constexpr char const* Prefix = "DCRIFTTEXT";', read(TEXT_H))
        for left in range(0, 3600):                                                  # a whole clock's worth, inside the client's 255 bytes
            self.assertLessEqual(len("DCRIFTTEXT\t" + model_line(left)), 255, left)
        self.assertEqual(141, len("DCRIFTTEXT\t" + model_line(59 * 60 + 59)))         # the figure the contract states

    def test_the_mutants_fail_the_same_driver(self):
        urshi, complete, text = read(URSHI_H), read(COMPLETE_H), read(TEXT_H)
        want = [expect for _, expect in cases()]
        mutants = {
            "angles_in_the_wrong_order": (urshi.replace("{0, 1, -1, 2, -2, 3, -3, 4}", "{0, -1, 1, -2, 2, -3, 3, 4}"), None, None),
            "angles_not_normalised": (urshi.replace("out[i] = angle < 0 ? angle + 2.0 * Pi : angle;", "out[i] = angle;"), None, None),
            "angles_a_quarter_turn_apart": (urshi.replace("Step = Pi / 4.0", "Step = Pi / 2.0"), None, None),
            "facing_axes_swapped": (urshi.replace("std::atan2(toY - fromY, toX - fromX)", "std::atan2(toX - fromX, toY - fromY)"), None, None),
            "facing_negative_kept": (urshi.replace("return angle < 0 ? angle + 2.0 * 3.14159265358979323846 : angle;", "return angle;"), None, None),
            "facing_without_a_fallback": (urshi.replace("        if (fromX == toX && fromY == toY)\n            return fallback;\n", ""), None, None),
            "fits_without_line_of_sight": (urshi.replace("return lineOfSight && wantedYards > 0 &&", "return wantedYards > 0 &&"), None, None),
            "fits_at_any_distance": (urshi.replace("gotYards >= wantedYards * minSharePct / 100.0 &&", ""), None, None),
            "fits_at_any_height": (urshi.replace("&& std::fabs(climbYards) <= maxClimbYards", ""), None, None),
            "fits_only_above": (urshi.replace("std::fabs(climbYards) <= maxClimbYards", "climbYards <= maxClimbYards"), None, None),
            "fits_past_the_share": (urshi.replace("gotYards >= wantedYards * minSharePct / 100.0", "gotYards > wantedYards * minSharePct / 100.0"), None, None),
            "line_green_is_grey": (None, complete.replace('NumberColour = "00ff00"', 'NumberColour = "b2b2b2"'), None),
            "line_grey_is_green": (None, complete.replace('LineColour = "b2b2b2"', 'LineColour = "00ff00"'), None),
            "line_keeps_a_zero_minute": (None, complete.replace("if (minutes > 0)\n            parts.push_back(Counted(minutes", "if (true)\n            parts.push_back(Counted(minutes"), None),
            "line_drops_the_zero_clock": (None, complete.replace("if (seconds > 0 || minutes == 0)", "if (seconds > 0)"), None),
            "line_always_plural": (None, complete.replace('(count == 1 ? one : many)', 'many'), None),
            "line_and_always": (None, complete.replace("if (minutes > 0 && seconds > 0)\n            parts.push_back({LineColour, \" and \"});", "parts.push_back({LineColour, \" and \"});"), None),
            "line_without_the_end": (None, complete.replace('        parts.push_back({LineColour, " remaining."});\n', ''), None),
            "record_without_the_kind": (None, None, text.replace("fields{LineRecord, kind}", "fields{LineRecord}")),
            "record_text_before_colour": (None, None, text.replace("fields.push_back(part.colour);\n            fields.push_back(part.text);", "fields.push_back(part.text);\n            fields.push_back(part.colour);")),
            "record_without_the_marker": (None, None, text.replace("fields{LineRecord, kind}", "fields{kind}")),
            "record_kind_renamed": (None, None, text.replace('GreaterRiftComplete = "gr_complete"', 'GreaterRiftComplete = "complete"')),
        }
        for name, (u, c, t) in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual((u, c, t), (urshi if u else None, complete if c else None, text if t else None))
                self.assertNotEqual(want, build_and_run(cases(), urshi=u, complete=c, text=t), name + " survived")


class Sheet(unittest.TestCase):
    def test_the_tunables(self):
        rows = tunables()
        row = rows["gr_urshi_spawn_yards"]
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("", "10", "yards"))
        self.assertNotIn("PLACEHOLDER", row["notes"])
        for name, value, unit in (("gr_urshi_spawn_min_share_pct", "70", "percent"), ("gr_urshi_spawn_max_climb_yards", "3", "yards")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"], rows[name]["unit"]), ("", value, unit), name)
            self.assertIn("PLACEHOLDER", rows[name]["notes"], name)

    def test_the_code_reads_exactly_these(self):
        code = read("src/rifts/dc_gr_urshi.cpp")
        self.assertEqual({"gr_urshi_spawn_yards", "gr_urshi_spawn_min_share_pct", "gr_urshi_spawn_max_climb_yards"},
                         set(re.findall(r'Yards\("(gr_urshi_spawn_[a-z_]+)"\)', code)))


def dbc(path):
    raw = path.read_bytes()
    magic, count, fields, size, strings = struct.unpack_from("<4s4I", raw)
    assert magic == b"WDBC"
    block = raw[20 + count * size:]
    rows = [struct.unpack_from("<%dI" % fields, raw, 20 + i * size) for i in range(count)]
    return rows, lambda off: block[off:block.index(0, off)].decode("utf-8", "replace")


class Beam(unittest.TestCase):
    DBC = REPO / "client-patch/dbc"

    def test_the_beam_is_a_stock_blue_skybeam_aura(self):
        if not (self.DBC / "Spell.dbc").exists():
            self.skipTest("the client's Spell.dbc is not on this machine")
        spells, spell_s = dbc(self.DBC / "Spell.dbc")
        spell = next(r for r in spells if r[0] == 62893)
        self.assertEqual("Blue Skybeam", spell_s(spell[136]))
        self.assertEqual((6, 4, 1), (spell[71], spell[95], spell[86]))   # an apply-aura effect, the dummy aura, on the caster
        visuals, _ = dbc(self.DBC / "SpellVisual.dbc")
        kits, _ = dbc(self.DBC / "SpellVisualKit.dbc")
        effects, effect_s = dbc(self.DBC / "SpellVisualEffectName.dbc")
        visual = next(r for r in visuals if r[0] == spell[131])
        state = next(r for r in kits if r[0] == visual[4])
        names = {effect_s(e[1]): effect_s(e[2]) for e in effects if e[0] in state[1:]}
        self.assertEqual({"Skybeam, Blue": "Spells\\FrostBeam_State_Base.mdx"}, names)

    def test_it_is_the_spell_the_code_puts_on_her(self):
        self.assertIn("constexpr std::uint32_t URSHI_BEAM_SPELL = 62893;", read("src/rifts/dc_gr_urshi.cpp"))


class Source(unittest.TestCase):
    def setUp(self):
        self.urshi = squeeze(read("src/rifts/dc_gr_urshi.cpp"))
        self.progress = squeeze(read("src/rifts/dc_gr_progress.cpp"))

    def test_she_stands_at_the_spot(self):
        spot = self.urshi[self.urshi.index("Position UrshiSpot("):self.urshi.index("// The blue column")]
        self.assertIn('Yards("gr_urshi_spawn_yards")', spot)
        self.assertIn("for (double angle : Gr::SpawnAngles(toward))", spot)
        self.assertIn("guardian->GetFirstCollisionPosition(static_cast<float>(wanted), static_cast<float>(angle - guardian->GetOrientation()))", spot)
        self.assertIn("guardian->IsWithinLOS(found.GetPositionX(), found.GetPositionY(), found.GetPositionZ())", spot)
        self.assertIn('Yards("gr_urshi_spawn_min_share_pct"), Yards("gr_urshi_spawn_max_climb_yards")', spot)
        self.assertIn("found.SetOrientation(", spot)
        self.assertTrue(spot.rstrip().endswith("return home; }"), "the Guardian's own spot is the fallback")
        begin = self.urshi[self.urshi.index("void BeginUrshi("):self.urshi.index("std::string UrshiBlocksClose")]
        self.assertIn("UrshiSpot(guardian, onFloor > 0,", begin)
        self.assertIn("if (member->GetMap() == map)", begin)
        self.assertNotIn("Position(guardian->GetPositionX()", begin)

    def test_the_beam_goes_on_her_with_no_end_of_its_own(self):
        beam = self.urshi[self.urshi.index("void ShowBeam("):self.urshi.index("Gr::ChanceTable Chances()")]
        self.assertIn("urshi->AddAura(URSHI_BEAM_SPELL, urshi)", beam)
        self.assertIn("beam->SetMaxDuration(-1);", beam)
        self.assertIn("beam->SetDuration(-1);", beam)
        begin = self.urshi[self.urshi.index("void BeginUrshi("):self.urshi.index("std::string UrshiBlocksClose")]
        self.assertLess(begin.index("SummonCreature"), begin.index("ShowBeam(urshi);"))
        self.assertLess(begin.index("ShowBeam(urshi);"), begin.index("runs[rift.instanceId] = run;"))

    def test_the_in_time_kill_sends_the_line_once_to_every_enrolled_member(self):
        record = self.progress[self.progress.index("void RecordGuardianResult("):]
        pending = record[record.index('if (rift.outcome == "pending")'):record.index("if (rift.outcome == Gr::OutcomeName(true))")]
        self.assertIn("if (beaten) GrantGreaterUnlocks(rift); if (beaten) ShowComplete(rift);", pending)
        show = self.progress[self.progress.index("void ShowComplete("):self.progress.index("// The clock reached 0:00")]
        self.assertIn("Text::Fields(Text::GreaterRiftComplete, Gr::CompleteParts(rift.timeLeft))", show)
        self.assertIn("for (ObjectGuid const& guid : EnrolledGuids(rift.id))", show)
        self.assertIn("ObjectAccessor::FindPlayer(guid)", show)
        self.assertIn("Bridge::Push(member, Text::Prefix, fields);", show)
        self.assertNotIn("SendAreaTriggerMessage", self.progress)
        self.assertEqual(1, self.progress.count("ShowComplete(rift);"))
        self.assertIn('#include "dc_gr_complete.h"', self.progress)


if __name__ == "__main__":
    unittest.main()
