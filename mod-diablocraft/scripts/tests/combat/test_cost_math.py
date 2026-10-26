"""The payment path: what a cast is charged, and what that costs in precision.

Step 5 moved the Fury cost into the spell record and the payment into the
core. The record and value-map suites prove the numbers are stored and read
back; this one exercises the arithmetic a payment actually goes through.

Nothing here models the core's arithmetic. `tests/cost_math/core_shim.h`
compiles `Player::ApplySpellMod` itself, extracted from the core pin with or
without `core-patches/0014`, beside the module's own
`src/combat/dc_cost_math.h`, and `tests/cost_math/display_harness.cpp` adds
the module's real `dc_common.cpp` so the character sheet's Resource Cost
Reduction goes through the same accumulation the server uses. A mutation of
the patch's executable combine fails these tests, which is what the evidence
is for.

Two things here are transcriptions and not the server's own code, and the
tests that cover them are source assertions rather than executions: the order
`Passives::Refresh` does its work in, which `display_harness.cpp` repeats,
and the family mask that decides a modifier applies at all, which
`core_shim.h` answers `true` to and the record suite is what proves.

Three deviations are accepted by the 2026-09-20 ruling and this states the
maximum it observed for each:

  * a spell modifier's amount is whole percent, so a fractional Resource Cost
    Reduction is rounded - at most half a percent of a cost;
  * the core works in integer Rage units, one a Fury point (class_resources.csv
    storage_scale), so a cast's charge truncates to a whole Fury, as Arcane
    Power's always has;
  * the Fury pool is those same units, so the module's channel tick costs the
    exact share (6.6667 at one attack a second) and the pool takes its whole
    units, carrying the rest to the next tick (dc_resources.h WholeUnits,
    test_resource_registry.py drives the carry).

    python mod-diablocraft/scripts/tests/combat/test_cost_math.py
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import barbarian_source  # noqa: E402
import harness_env
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE = REPO_ROOT / "mod-diablocraft"
HARNESS = MODULE / "tests" / "cost_math"
D3 = MODULE / "data" / "d3"
GENERATED = MODULE / "data" / "generated"
CORE = REPO_ROOT / "azerothcore-wotlk"
# Scratch belongs in the build tree (AGENTS.md), not the system temp; the
# fallback is for a checkout that has never been configured.
SCRATCH = CORE / "build" / "_agent-scratch" / "cost_math"
PIN = (Path(REPO_ROOT) / "core-commit.txt").read_text().split()[0]  # the pin moves with core-commit.txt
PATCH = REPO_ROOT / "core-patches" / "0014-spell-modifier-d3-arithmetic.patch"

# The ruling's accepted bounds. Half a percent of the cost is the worst a
# whole-percent modifier can be out; one Rage unit is the registry's share of a
# Fury point (1 / storage_scale), and
# a debit rounded to one of those is out by at most half a unit.
ROUNDING_SHARE = 0.005
RAGE_UNIT_FURY = 1.0 / next(e["scale"] for e in __import__("generate_class_resources").registry()
                             if e["d3_class"] == "Barbarian" and e["role"] == "primary")
TRUNCATION_FURY = RAGE_UNIT_FURY
# The module asks the core what its modifiers make of a 10000-unit probe cost,
# so a factor it reads back is itself one probe unit coarse.
PROBE_SHARE = 1.0 / 10000


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def records_durations():
    """{SpellDuration.dbc row: its base duration in ms}, for the shout checks."""
    import test_spell_records
    return test_spell_records.load_dbc_column("SpellDuration.dbc", 4)


def generated_records():
    """{spell id: {column: value}} straight out of the generated spell SQL.

    Step 6 asks what the core will be handed, not what a sheet says, so the
    cooldown tests read the record the migration carries.
    """
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    names = [name.strip(" `") for name in
             re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES", text)[1].split(",")]
    out = {}
    for line in text.splitlines():
        line = line.strip().rstrip(",;")
        if not line.startswith("(") or not line.endswith(")"):
            continue
        cells, current, quoted = [], "", False
        index = 1
        while index < len(line) - 1:
            char = line[index]
            if quoted:
                if char == "'" and line[index + 1:index + 2] == "'":
                    current += "'"
                    index += 1
                elif char == "'":
                    quoted = False
                else:
                    current += char
            elif char == "'":
                quoted = True
            elif char == ",":
                cells.append(current)
                current = ""
            else:
                current += char
            index += 1
        cells.append(current)
        if len(cells) == len(names):
            out[int(cells[0])] = dict(zip(names, cells))
    return out


def cooldown_affix_maxima():
    """Every percentage of Cooldown Reduction the item tables can produce.

    A generous upper bound, on purpose: every slot that can roll the affix at
    its highest roll, both rings and both weapon hands, and the best head gem.
    Nothing a character can actually wear beats this, so a floor this cannot
    reach is a floor nothing reaches.
    """
    pools = (GENERATED / "affix_pools.sql").read_text(encoding="utf-8")
    best = {}
    for slot, high in re.findall(r"\('([a-z]+)', 'cdr', 'Cooldown Reduction', 'primary', "
                                 r"\d+, (\d+),", pools):
        best[slot] = max(best.get(slot, 0.0), float(high))
    percents = []
    for slot, high in sorted(best.items()):
        percents.append(high)
        if slot in ("finger", "onehand"):   # two rings, two hands
            percents.append(high)
    gems = (GENERATED / "crafting.sql").read_text(encoding="utf-8")
    percents.append(max(float(value) for value in
                        re.findall(r"dc_gem_effect` VALUES \(\d+,'head','cdr',([0-9.]+)\)", gems)))
    return percents


def sheet_costs():
    """Every Fury cost the sheets state, base skills and the runes' own."""
    return sorted({float(row["value"]) for row in read_csv(D3 / "barbarian_skill_values.csv")
                   if row["token"] == "cost_resource"})


def channel_terms():
    """Whirlwind's four channel rows, by token."""
    return {row["token"]: float(row["value"])
            for row in read_csv(D3 / "barbarian_skill_values.csv")
            if row["skill"] == "Whirlwind" and row["token"].startswith("channel_")}


# --- the core's own code, taken out of the pin -----------------------------

def at_pin(path):
    """A core file exactly as the pin has it. The core is never written to."""
    shown = subprocess.run(["git", "-C", str(CORE), "show", "%s:%s" % (PIN, path)],
                           capture_output=True, text=True)
    if shown.returncode:
        raise AssertionError("the core pin has no %s:\n%s" % (path, shown.stderr))
    return shown.stdout


def block(text, opener, what):
    """The text from `opener` through the brace that closes it."""
    start = text.find(opener)
    if start < 0:
        raise AssertionError("the core pin no longer has %s" % what)
    depth = 0
    for position in range(text.index("{", start), len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[start:text.find("\n", position) + 1]
    raise AssertionError("%s is not closed" % what)


def player_cpp(patched, work):
    """Player.cpp at the pin, with core-patches/0014 applied or not.

    The patch is applied to a copy in a temporary tree; the core checkout is
    read-only here, as it is everywhere.
    """
    text = at_pin("src/server/game/Entities/Player/Player.cpp")
    if not patched:
        return text
    target = work / "src/server/game/Entities/Player"
    target.mkdir(parents=True, exist_ok=True)
    (target / "Player.cpp").write_text(text, encoding="utf-8")
    applied = subprocess.run(["git", "apply", "--unsafe-paths", "--directory", ".", str(PATCH)],
                             cwd=str(work), capture_output=True, text=True)
    if applied.returncode:
        raise AssertionError("core-patches/0014 does not apply at the pin:\n" + applied.stderr)
    return (target / "Player.cpp").read_text(encoding="utf-8")


def extract(patched, into, mutate=None):
    """Write the four extracted pieces the harnesses include."""
    into.mkdir(parents=True, exist_ok=True)
    combine = block(player_cpp(patched, into / "tree"),
                    "template <class T>\nvoid Player::ApplySpellMod(",
                    "Player::ApplySpellMod")
    if mutate:
        before, after = mutate
        if before not in combine:
            raise AssertionError("the mutation target %r is not in the extracted combine" % before)
        combine = combine.replace(before, after)
    (into / "apply_spell_mod.inc").write_text(combine, encoding="utf-8")

    defines = at_pin("src/server/game/Spells/SpellDefines.h")
    header = at_pin("src/server/game/Entities/Player/Player.h")
    maximum = re.search(r"^#define MAX_SPELLMOD \d+$", defines, re.M)
    if not maximum:
        raise AssertionError("the core pin no longer has MAX_SPELLMOD")
    (into / "spell_mod_enums.inc").write_text(
        block(defines, "enum SpellModOp", "SpellModOp") + "\n" + maximum.group(0) + "\n\n" +
        block(header, "enum SpellModType", "SpellModType") + "\n" +
        block(header, "struct SpellModifier", "SpellModifier"), encoding="utf-8")
    (into / "calculate_pct.inc").write_text(
        block(at_pin("src/common/Utilities/Util.h"),
              "template <class T, class U>\ninline T CalculatePct(", "CalculatePct"),
        encoding="utf-8")
    return combine


class CostMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("c++") or shutil.which("g++")
        if not cls.compiler:
            raise unittest.SkipTest("no C++ compiler")
        cls.costs = sheet_costs()
        cls.terms = channel_terms()
        try:
            SCRATCH.mkdir(parents=True, exist_ok=True)
            cls.work = Path(tempfile.mkdtemp(prefix="run-", dir=str(SCRATCH)))
        except OSError:
            cls.work = Path(tempfile.mkdtemp(prefix="dc-cost-math-"))
        cls.binaries = {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def build(self, source, patched=True, name=None, mutate=None):
        """Compile a harness against the core code extracted from the pin."""
        name = name or ("%s-%s" % (Path(source).stem, "patched" if patched else "pinned"))
        if name in self.binaries:
            return self.binaries[name]
        into = self.work / name
        extract(patched, into, mutate)
        binary = into / "harness"
        sources = [str(HARNESS / source)]
        if source == "display_harness.cpp":
            sources.append(str(MODULE / "src" / "common" / "dc_common.cpp"))
        built = subprocess.run(
            [self.compiler, "-std=c++17", "-O0", "-I", str(into)] + sources + ["-o", str(binary)],
            capture_output=True, text=True)
        if built.returncode:
            raise AssertionError("%s did not compile:\n%s" % (source, built.stderr[-4000:]))
        self.binaries[name] = binary
        return binary

    def drive(self, cases, source="core_harness.cpp", patched=True, mutate=None, name=None):
        """Run a harness over `cases`, returning one answer line per case."""
        binary = self.build(source, patched, name=name, mutate=mutate)
        cases_file = self.work / "cases.tsv"
        cases_file.write_text(
            "\n".join("\t".join(str(cell) for cell in case) for case in cases) + "\n",
            encoding="utf-8")
        run = harness_env.run([str(binary), str(cases_file)], capture_output=True, text=True)
        if run.returncode:
            raise AssertionError("the harness did not run:\n" + run.stderr[-2000:])
        answers = [[float(cell) for cell in line.split("\t")] for line in run.stdout.splitlines()]
        self.assertEqual(len(answers), len(cases), "the harness answered a different count")
        return [row[0] if len(row) == 1 else row for row in answers]

    # --- what a cast is charged -------------------------------------------

    def test_a_cast_is_charged_what_the_reduction_says(self):
        """Every sheet cost against every reduction, to the accepted bounds."""
        percents = [step / 20 for step in range(0, 2001)]     # 0 .. 100 in 0.05 steps
        cases = [("cost", cost, percent) for cost in self.costs for percent in percents]
        answers = self.drive(cases)
        worst, worst_case = 0.0, None
        for (_kind, cost, percent), charged in zip(cases, answers):
            exact = cost * (1 - percent / 100)
            self.assertLessEqual(charged, cost + 1e-9, "a reduction made a cost bigger")
            self.assertGreaterEqual(charged, 0.0)
            allowed = cost * ROUNDING_SHARE + TRUNCATION_FURY + 1e-9
            gap = abs(charged - exact)
            if gap > worst:
                worst, worst_case = gap, (cost, percent, charged, exact)
            self.assertLessEqual(gap, allowed,
                                 "%g Fury at %g%%: charged %g, exact %g" % (cost, percent, charged, exact))
        print("\n  worst cast deviation: %.4f Fury (%g Fury at %g%%: charged %g, exact %g)"
              % ((worst,) + worst_case))
        self.assertLessEqual(worst, max(self.costs) * ROUNDING_SHARE + TRUNCATION_FURY + 1e-9)

    def test_a_cost_keeps_its_fraction_over_casts(self):
        """A reduced cost keeps its part below a point (the designer, q-1017-05): 25 Fury at 30% off is 17.5, and the core,
        which charges whole Rage units, takes 17 a cast; the module's carry takes the dropped halves back, so two
        casts spend 35, not 34. Over many casts every sheet cost at every reduction spends its exact sum to under a
        point, the half-percent the whole-percent modifier rounds aside."""
        one, two, ten = self.drive([("casts", 25, 30, 1), ("casts", 25, 30, 2), ("casts", 25, 30, 10)])
        self.assertEqual((one, two, ten), (17.0, 35.0, 175.0))
        percents = [0, 7.5, 12.3, 30, 33.3, 50, 55.5, 70, 99]
        cases = [("casts", cost, percent, 20) for cost in self.costs for percent in percents]
        for (_kind, cost, percent, count), taken in zip(cases, self.drive(cases)):
            exact = count * cost * (1 - round(percent) / 100)
            self.assertLess(abs(taken - exact), 1.0 + 1e-6,
                            "%d casts of %g Fury at %g%%: took %g, exact %g" % (count, cost, percent, taken, exact))

    def test_a_full_reduction_is_free_and_none_is_the_whole_cost(self):
        answers = self.drive([("cost", cost, percent)
                              for cost in self.costs for percent in (0, 100)])
        for index, cost in enumerate(self.costs):
            self.assertEqual(answers[index * 2], cost, "no reduction must charge the sheet number")
            self.assertEqual(answers[index * 2 + 1], 0.0, "a full reduction must be free")

    # --- what a channel tick debits ---------------------------------------

    def test_the_whirlwind_tick_costs_the_simulators_share(self):
        """cost = 7 / speed + 3, reduced, scaled by 40 frames of 60.

        The order is the simulator's: the reduction applies to the per-second
        rate before the channel scaling (d3planner cast.js:136-147, quoted in
        docs/research/d3-cost-cooldown-math.md). The tick's cost is that share
        unrounded; the integer Rage pool takes its whole units and carries the
        rest (dc_resources.h WholeUnits), so over a channel it pays the exact sum.
        """
        speed = self.terms["channel_cost_speed_term_resource"]
        flat = self.terms["channel_cost_flat_resource"]
        frames = self.terms["channel_tick_frames_count"]
        rate = self.terms["channel_frames_per_second_count"]
        self.assertEqual((speed, flat, frames, rate), (7.0, 3.0, 40.0, 60.0))
        attacks = [step / 20 for step in range(10, 61)]        # 0.5 .. 3.0 attacks/s
        percents = [0, 7.5, 12.3, 30, 50, 55.5, 70]
        cases = [("tick", speed, flat, aps, frames, rate, percent)
                 for aps in attacks for percent in percents]
        answers = self.drive(cases)
        worst, worst_case = 0.0, None
        for (_kind, _s, _f, aps, _fr, _r, percent), debited in zip(cases, answers):
            per_second = speed / aps + flat
            exact = per_second * (1 - percent / 100) * frames / rate
            # The modifier's whole percent and the probe's own unit.
            allowed = per_second * (ROUNDING_SHARE + PROBE_SHARE) * frames / rate + 1e-9
            gap = abs(debited - exact)
            if gap > worst:
                worst, worst_case = gap, (aps, percent, debited, exact)
            self.assertLessEqual(gap, allowed,
                                 "%g attacks/s at %g%%: debited %g, exact %g"
                                 % (aps, percent, debited, exact))
        print("  worst Whirlwind tick deviation: %.4f Fury (%g attacks/s at %g%%: debited %g, exact %g)"
              % ((worst,) + worst_case))
        # At one attack a second the tooltip's 10 Fury a second is what the
        # channel asks for: 6.6667 a tick, not a rounded one.
        one = self.drive([("tick", speed, flat, 1.0, frames, rate, 0)])[0]
        self.assertAlmostEqual(one, 6.666667, places=6, msg="the tick's cost was rounded")
        self.assertAlmostEqual(10 * frames / rate, 6.666667, places=6)

    def test_the_cadence_is_the_simulators_and_not_the_cost_scaling(self):
        """floor(channeling / attack speed) frames, recomputed as speed changes.

        d3planner's simulator sets the channel's tick rate to
        `Math.floor(channeling / info.speed)` frames and recomputes it every
        tick (simulator/cast.js:504 and :508; the identical formula sits
        unused in Sim.channelDelay at :491-495), with `info.speed` the
        attacks per second of the hand being swung (cast.js:438-440). The
        tick's cost keeps the unrounded `channeling / 60` scaling, so the two
        numbers part company as soon as attack speed is not 1.0 (the ruling
        recorded at the end of decisions.md, 2026-09-20).
        """
        frames = self.terms["channel_tick_frames_count"]
        fps = self.terms["channel_frames_per_second_count"]
        scheduled = self.drive([("schedule", frames, aps) for aps in (1.0, 1.5, 2.0, 0.5, 1.25)])
        self.assertEqual(scheduled[0], 40, "one attack a second ticks every 40 frames")
        self.assertEqual(scheduled[1], 26, "1.5 attacks a second ticks every 26 frames")
        self.assertEqual(scheduled[2], 20)
        self.assertEqual(scheduled[3], 80)
        self.assertEqual(scheduled[4], 32, "floor, not round: 40 / 1.25 is 32 exactly")
        # the interval in seconds, which is what the module schedules on
        self.assertAlmostEqual(scheduled[1] / fps, 26 / 60, places=9)
        # and the cost scaling is still the unrounded 40/60 at 1.5 attacks/s
        speed = self.terms["channel_cost_speed_term_resource"]
        flat = self.terms["channel_cost_flat_resource"]
        debited = self.drive([("tick", speed, flat, 1.5, frames, fps, 0)])[0]
        self.assertAlmostEqual(debited, (speed / 1.5 + flat) * frames / fps,
                               places=6, msg="the tick's cost used the rounded interval")
        self.assertNotAlmostEqual(debited, (speed / 1.5 + flat) * scheduled[1] / fps, places=2)

    def test_dual_wielding_alternates_the_hands(self):
        """Each tick is its own hand's cadence and its own hand's cost.

        D3 swings the hands alternately (simulator/cast.js:391-397) and takes
        that hand's speed for the cast (cast.js:438-440), so a 1.0 and a 1.4
        attacks-per-second pair ticks 40 frames, then 28, then 40. The
        tooltip data file's blended `info.aps` (skill_barbarian.js:336) is a
        display number and governs none of this (decisions.md, 2026-09-20).
        """
        speed = self.terms["channel_cost_speed_term_resource"]
        flat = self.terms["channel_cost_flat_resource"]
        frames = self.terms["channel_tick_frames_count"]
        fps = self.terms["channel_frames_per_second_count"]
        hands = (1.0, 1.4)
        scheduled = self.drive([("schedule", frames, aps) for aps in hands])
        self.assertEqual(scheduled, [40, 28], "the hands do not tick at 40 and 28 frames")
        costs = self.drive([("tick", speed, flat, aps, frames, fps, 0) for aps in hands])
        # 7/1.0 + 3 = 10 Fury a second, 6.6667 a tick;
        # 7/1.4 + 3 = 8 a second, 5.3333 a tick.
        self.assertEqual([round(c, 4) for c in costs], [6.6667, 5.3333], "a hand's tick does not cost that hand's rate")
        for aps, scheduled_frames, charged in zip(hands, scheduled, costs):
            rate = speed / aps + flat
            self.assertAlmostEqual(charged, rate * frames / fps, places=6)
            self.assertEqual(scheduled_frames, int(frames // aps))
        # and the two are a pair: one hand decides both
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src" / "combat" / "dc_combat_internal.h", *sorted((MODULE / "src" / "combat").glob("dc_combat*.cpp"))])
        for function in ("double WhirlwindTickSeconds(Player* player, std::uint32_t spellId, bool offhand)",
                         "double WhirlwindTickCost(Player* player, std::uint32_t spellId, bool offhand = false)"):
            self.assertIn(function, combat, "a channel helper does not take the hand")
            body = combat.split(function, 1)[1].split("\n    }\n", 1)[0]
            self.assertIn("HandAttacksPerSecond(player, spellId, offhand)", body,
                          "%s does not use the hand it was given" % function.split("(")[0])
        abilities = barbarian_source.abilities((".cpp",))
        self.assertIn("s.whirlwindOffhand=DualWielding(p) && !hand;", abilities,
                      "the channel does not alternate hands")
        self.assertIn("if(!PayWhirlwindTick(p,row->id,hand))", abilities,
                      "the tick is not paid for by the hand that swings it")
        self.assertIn("state.whirlwindOffhand=false;", abilities,
                      "a channel must start on the main hand")
        # one weapon: the sheet has no offhand speed, so both are the main hand
        stats = (MODULE / "src" / "stats" / "dc_stats.cpp").read_text(encoding="utf-8")
        self.assertIn("RemoveContribution(guid, Source::Items, Stat::OffhandWeaponAPS, WEAPON_APS_ID);", stats,
                      "the offhand speed outlives the offhand")
        common = (MODULE / "src" / "common" / "dc_common.cpp").read_text(encoding="utf-8")
        self.assertIn("sheet.offhandAttacksPerSecond = sheet[Stat::OffhandWeaponAPS] > 0", common)

    def test_a_weapons_own_attack_speed_stays_on_its_own_hand(self):
        """An affix on the offhand must not speed the main hand.

        D3 reads a weapon's `weaponias` off that weapon
        (stats_full.js:331); the module pooled both hands' into one sheet
        number, so an offhand affix shortened the main hand's channel ticks
        too. The speeds here come out of the production Calculate, and the
        frames and costs below out of the core's own combine.
        """
        frames = self.terms["channel_tick_frames_count"]
        fps = self.terms["channel_frames_per_second_count"]
        speed = self.terms["channel_cost_speed_term_resource"]
        flat = self.terms["channel_cost_flat_resource"]
        # main 1.0 base with no affix, off 1.0 base with 40 % of its own, and
        # the same pair without the affix at all
        cases = [("hands", 1.0, 0, 1.0, 40, 0),
                 ("hands", 1.0, 0, 1.0, 0, 0),
                 ("hands", 1.0, 25, 1.0, 0, 0),
                 ("hands", 1.0, 0, 0, 0, 0)]
        with_affix, without, main_only, single = self.drive(cases, source="display_harness.cpp")
        self.assertEqual(with_affix[0], without[0],
                         "the offhand's own attack speed moved the main hand")
        self.assertAlmostEqual(with_affix[1], 1.4, places=9, msg="the offhand kept its own affix")
        self.assertAlmostEqual(without[1], 1.0, places=9)
        self.assertAlmostEqual(main_only[0], 1.25, places=9, msg="the main hand kept its own affix")
        self.assertAlmostEqual(main_only[1], 1.0, places=9,
                               msg="the main hand's own attack speed moved the offhand")
        self.assertEqual(single[1], 0.0, "an empty hand has no speed")

        # and downstream: the hands tick and cost on their own speeds
        pairs = [("schedule", frames, aps) for aps in with_affix]
        self.assertEqual(self.drive(pairs), [40, 28],
                         "the per-hand speeds do not give 40 and 28 frames")
        costs = self.drive([("tick", speed, flat, aps, frames, fps, 0) for aps in with_affix])
        self.assertEqual([round(c, 4) for c in costs], [6.6667, 5.3333], "a hand's tick does not cost its own speed")
        # without the offhand affix both hands are the same tick again
        self.assertEqual(self.drive([("schedule", frames, aps) for aps in without]), [40, 40])

    def test_a_weapons_attack_speed_does_not_follow_it_to_the_other_hand(self):
        """Equip, unequip and swap all clear the hand the weapon left."""
        items = items_source.read("dc_items_equip.cpp")
        apply = items.split("void Apply(Player* player, Item* item, bool equipping)")[1]
        self.assertIn("mapping->second.bucket == Bucket::WeaponLocal", apply,
                      "the weapon-local affix is not handed")
        self.assertIn("stat = offhand ? Stat::OffhandWeaponIAS : Stat::AttackSpeed;", apply)
        self.assertIn("Stat const other = offhand ? Stat::AttackSpeed : Stat::OffhandWeaponIAS;", apply,
                      "nothing clears the hand the weapon left")
        # the removal of the other hand's copy runs for equip and unequip alike:
        # it sits above the `if (equipping)` that follows it
        cleared = apply.index("Stat const other =")
        branch = apply.index("if (equipping)", cleared)
        self.assertLess(cleared, branch, "the other hand is only cleared on one path")
        common = (MODULE / "src" / "common" / "dc_common.cpp").read_text(encoding="utf-8")
        self.assertIn("c.stat == Stat::OffhandWeaponIAS ? sheet.offhandWeaponIAS : sheet.weaponIAS", common)
        self.assertIn("sheet[Stat::OffhandWeaponAPS] * (1 + sheet.offhandWeaponIAS / 100)", common,
                      "the offhand speed still uses the pooled weapon IAS")

    def test_the_module_schedules_on_the_speed_dependent_interval(self):
        """The module reads the interval from the player, every update."""
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src" / "combat" / "dc_combat_internal.h", *sorted((MODULE / "src" / "combat").glob("dc_combat*.cpp"))])
        opener = "double WhirlwindTickSeconds(Player* player, std::uint32_t spellId, bool offhand)"
        self.assertIn(opener, combat)
        # only the function's own body, or this passes on any other use of the
        # same call further down the file
        body = combat.split(opener, 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("CostMath::ScheduleSeconds", body)
        self.assertIn("HandAttacksPerSecond(player, spellId, offhand)", body,
                      "the interval no longer depends on that hand's attack speed")
        # the cost keeps the unrounded scaling, which is a different helper
        self.assertIn("CostMath::CostScaleSeconds", combat)
        abilities = barbarian_source.abilities((".cpp",))
        self.assertIn("double interval=WhirlwindTickSeconds(p,row->id,s.whirlwindOffhand);", abilities,
                      "the tick loop must ask for the swinging hand's own interval")

    # --- the patch, run rather than quoted ---------------------------------

    def test_three_reductions_multiply_the_way_d3_does(self):
        """core-patches/0014, the cost half: 0.7 x 0.8 x 0.5 = 0.28 remains.

        Both answers come out of `Player::ApplySpellMod` itself, compiled from
        the pin with the patch and without it.
        """
        gear, sword, relentless = 30, 20, 50
        cases = [("stack", 25, gear, sword, relentless),
                 ("stack", 25, gear),
                 ("stack", 25, sword, relentless)]
        patched, one, two = self.drive(cases, patched=True)
        unpatched = self.drive([cases[0]], patched=False)[0]
        self.assertAlmostEqual(patched, 25 * 0.7 * 0.8 * 0.5, places=6)
        self.assertEqual(patched, 7.0, "25 Fury at 28 % remaining is 7 Fury")
        self.assertEqual(unpatched, 0.0,
                         "without the patch the three reductions add up to a free cast")
        # 25 Rage x 0.7f is 17.5 and the core truncates it to a whole unit, 17
        # Fury at one unit a point: the core evaluates this combine in float,
        # and so does the harness, because it is the same code.
        self.assertAlmostEqual(one, int(25 * 0.7 / RAGE_UNIT_FURY + 1e-6) * RAGE_UNIT_FURY, places=6)
        self.assertAlmostEqual(two, 25 * 0.8 * 0.5, places=6)
        # and the passives' percentages are the sheet's, not this test's
        percents = {row["skill"]: float(row["value"])
                    for row in read_csv(D3 / "barbarian_passive_values.csv")
                    if row["token"] == "cost_reduction_pct"}
        self.assertEqual(percents, {"Relentless": float(relentless),
                                    "Sword and Board": float(sword)})

    def test_boon_on_wrath_of_the_berserker_is_fifty_four_seconds(self):
        """core-patches/0014, the cooldown half: flat before percentage.

        Wrath of the Berserker's 120 seconds, Boon of Bul-Kathos's flat 30 and
        40 % cooldown reduction. D3 subtracts first: (120 - 30) x 0.6 = 54.
        The core's own order gives 120 x 0.6 - 30 = 42. Step 6 writes the
        modifiers; this proves the arithmetic they will land in, by running it.
        """
        skills = {row["skill_name"]: row for row in read_csv(D3 / "barbarian_skills.csv")}
        base = float(skills["Wrath of the Berserker"]["cooldown_seconds"])
        flat = next(float(row["value"]) for row in read_csv(D3 / "barbarian_passive_values.csv")
                    if row["skill"] == "Boon of Bul-Kathos"
                    and row["qualifier"] == "wrath_of_the_berserker")
        self.assertEqual((base, flat), (120.0, 30.0), "the sheets moved")
        case = [("cooldown", int(base * 1000), -int(flat * 1000), 40)]
        self.assertEqual(self.drive(case, patched=True)[0], 54000, "flat first gives 54 seconds")
        self.assertEqual(self.drive(case, patched=False)[0], 42000,
                         "the core's own order gives 42")

    def test_the_record_and_the_modifiers_give_d3_its_cooldowns(self):
        """Step 6, end to end from the generated record.

        The previous test proves the arithmetic with the sheets' numbers; this
        one proves what will actually be loaded. Every number comes out of
        `data/generated/spell_shells.sql`: the skill's own RecoveryTime, and
        the amount the Boon of Bul-Kathos modifier record carries. They go
        through the core's own combine and have to land on D3's results.
        """
        records = generated_records()
        shells = {row["name"]: int(row["spell_id"])
                  for row in read_csv(GENERATED / "spell_shells.csv")
                  if row["kind"] in ("active", "rune")}
        boon = {}
        for row in read_csv(GENERATED / "spell_shells.csv"):
            if row["kind"] != "cooldown_modifier" or not row["name"].startswith("Boon"):
                continue
            boon[-int(records[int(row["spell_id"])]["EffectBasePoints_1"])] = row["name"]
        self.assertEqual(sorted(boon), [15000, 30000], "the Boon records moved")
        # (cooldown - flat) x (1 - cdr), which is D3's order and the one
        # core-patches/0014 gives SPELLMOD_COOLDOWN.
        for skill, flat, cdr, wanted in (("Wrath of the Berserker", 30000, 40, 54000),
                                         ("Call of the Ancients", 30000, 40, 54000),
                                         ("Earthquake", 15000, 40, 27000),
                                         ("Earthquake", 15000, 0, 45000),
                                         ("Wrath of the Berserker", 0, 50, 60000)):
            base = int(records[shells[skill]]["RecoveryTime"])
            if flat:
                self.assertIn(flat, boon, "%s: no Boon record carries %d ms" % (skill, flat))
            got = self.drive([("cooldown", base, -flat, cdr)], patched=True)[0]
            self.assertEqual(got, wanted,
                             "%s: %d ms less %d at %d%% gave %d" % (skill, base, flat, cdr, got))
        # the rune that shortens its parent keeps its own number, and the
        # reduction applies to that
        stomp = int(records[shells["Ground Stomp - Deafening Crash"]]["RecoveryTime"])
        self.assertEqual(stomp, 8000, "the rune's own cooldown left the record")
        self.assertEqual(self.drive([("cooldown", stomp, 0, 25)], patched=True)[0], 6000)

    def test_a_charge_recharge_is_reduced_the_way_a_cooldown_is(self):
        """The recharge is a record field and goes through the same modifiers.

        D3 runs a charge recharge through the same `fixCooldown` a cooldown
        goes through (skilldata.js:636-642), so the module asks the core the
        same question it asks for a cooldown - one `ApplySpellMod` on
        SPELLMOD_COOLDOWN - instead of multiplying by a factor of its own.
        """
        records = generated_records()
        shells = {row["name"]: int(row["spell_id"])
                  for row in read_csv(GENERATED / "spell_shells.csv")
                  if row["kind"] in ("active", "rune")}
        charge = records[shells["Furious Charge"]]
        self.assertEqual(int(charge["RecoveryTime"]), 0, "a charge skill has no cooldown of its own")
        recharge = int(charge["CategoryRecoveryTime"])
        sheet = next(float(row["value"]) for row in read_csv(D3 / "barbarian_skill_values.csv")
                     if row["skill"] == "Furious Charge" and row["token"] == "charge_recharge_seconds")
        self.assertEqual(recharge, int(sheet * 1000), "the record and the sheet disagree")
        for cdr, wanted in ((0, 10000), (40, 6000), (25, 7500)):
            self.assertEqual(self.drive([("cooldown", recharge, 0, cdr)], patched=True)[0], wanted,
                             "%d%% off a %d ms recharge" % (cdr, recharge))
        # and the module asks the core rather than working out a factor
        abilities = barbarian_source.abilities((".cpp",))
        self.assertNotIn("CooldownFactor", abilities, "the module still scales by a factor of its own")
        self.assertIn('ReducedCooldownMilliseconds( p, b->id, uint32(std::lround('
                      'Numbers::Num(b->id, "charge_recharge_seconds") * 1000)))', re.sub(r"\s+", " ", abilities))

    def test_the_shouts_are_doubled_by_the_record_and_not_by_the_module(self):
        """Step 8: Inspiring Presence is a SPELLMOD_DURATION aura.

        "The duration of your shouts is doubled" was three `duration *= 2`
        lines in dc_abilities, which nothing outside those three branches
        could see. It is now one record - +100% on SPELLMOD_DURATION with the
        three shouts in its mask - and the module asks the core for the
        duration, so the same doubling is a modifier the tooltip and the
        character sheet can read. The answer here comes out of
        `Player::ApplySpellMod` itself; SPELLMOD_DURATION was already in the
        flat-first branch before core-patches/0014 touched it, so this holds
        patched or not.
        """
        records = generated_records()
        manifest = read_csv(GENERATED / "spell_shells.csv")
        modifiers = [row for row in manifest if row["kind"] == "duration_modifier"]
        self.assertEqual([row["name"] for row in modifiers],
                         ["Inspiring Presence - duration modifier"],
                         "the duration modifiers are no longer the one this test knows")
        record = records[int(modifiers[0]["spell_id"])]
        self.assertEqual(int(record["Effect_1"]), 6, "SPELL_EFFECT_APPLY_AURA")
        self.assertEqual(int(record["EffectAura_1"]), 108, "SPELL_AURA_ADD_PCT_MODIFIER")
        self.assertEqual(int(record["EffectMiscValue_1"]), 1, "SPELLMOD_DURATION")
        self.assertEqual(int(record["EffectDieSides_1"]), 0,
                         "a modifier amount is exact, so no die side may roll it")
        percent = int(record["EffectBasePoints_1"])
        self.assertEqual(percent, 100, "doubled is +100 percent")
        self.assertEqual(int(record["SpellClassSet"]), 20, "the Diablocraft family")

        # the mask names the three shouts and nothing else. A mask bit means a
        # skill only inside the modifier's own family (SpellClassSet): the
        # Wizard's family-21 records reuse the same bit numbers and the core
        # never matches them to a family-20 aura (diablocraft-wizard-records).
        family = int(record["SpellClassSet"])
        bit_of = {row["name"]: int(records[int(row["spell_id"])]["SpellClassMask_1"])
                  for row in manifest if row["kind"] == "active"
                  and int(records[int(row["spell_id"])]["SpellClassSet"]) == family}
        mask = int(record["EffectSpellClassMaskA_1"])
        named = sorted(skill for skill, bit in bit_of.items() if bit & mask)
        self.assertEqual(named, ["Battle Rage", "Threatening Shout", "War Cry"],
                         "the mask no longer names exactly the shouts")

        # every shout's own sheet duration, doubled by the core
        sheet = {row["skill"]: float(row["value"])
                 for row in read_csv(D3 / "barbarian_skill_values.csv")
                 if row["token"] == "duration_seconds" and not row["rune"]}
        cases, wanted = [], []
        for skill in named:
            self.assertIn(skill, sheet, "%s has no duration on the sheet" % skill)
            milliseconds = int(sheet[skill] * 1000)
            cases.append(("duration", milliseconds, percent))
            wanted.append(milliseconds * 2)
        self.assertEqual(self.drive(cases, patched=True), [float(ms) for ms in wanted],
                         "the core did not double the shouts")
        self.assertEqual(self.drive(cases, patched=False), [float(ms) for ms in wanted],
                         "the doubling is native and must not depend on the patch")

        # and the module asks the core rather than multiplying by two itself
        abilities = barbarian_source.abilities((".cpp",))
        self.assertNotIn("duration *= 2", abilities,
                         "the module still doubles a shout duration itself")
        self.assertNotIn("Inspiring Presence\"", abilities,
                         "the module still asks whether the passive is learned")
        self.assertEqual(abilities.count("Combat::ModifiedDurationSeconds("), 3,
                         "the three shouts no longer all go through the core")
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertIn("player->ApplySpellMod(spellId, SPELLMOD_DURATION, value);", combat)

    def test_a_side_effect_inside_a_shout_is_not_doubled(self):
        """Architect ruling, decisions.md 8d89601: 5 s, 4 s and 3 s stay.

        Inspiring Presence doubles a shout, and a spell modifier's mask is a
        skill bit, so it reaches every record of that skill. Three of those
        records carry a number that is not the shout's duration - Hardened
        Wrath's armour window, Demoralize's taunt, Terrify's fear - and the
        Ruling is that those do not change. They are out of the modifier's
        reach by construction: the field it moves is DurationIndex, and those
        three live in dc_spell_values as exact values instead. What the core
        does to each is driven here, so the difference is executed and not
        argued.
        """
        records = generated_records()
        manifest = read_csv(GENERATED / "spell_shells.csv")
        # A name is not unique in the manifest - every skill and rune also has
        # an ability_aura companion of the same name - so this is the
        # selectable record only.
        by_name = {row["name"]: int(row["spell_id"]) for row in manifest
                   if row["kind"] in ("active", "rune")}
        percent = int(records[next(int(row["spell_id"]) for row in manifest
                                   if row["kind"] == "duration_modifier")]["EffectBasePoints_1"])
        durations = records_durations()

        # the shout durations, doubled
        shouts = {"War Cry": 120.0, "Battle Rage": 120.0, "Threatening Shout": 15.0}
        sheet = {row["skill"]: float(row["value"]) for row in read_csv(D3 / "barbarian_skill_values.csv")
                 if row["token"] == "duration_seconds" and not row["rune"]}
        self.assertEqual({skill: sheet[skill] for skill in shouts}, shouts,
                         "a shout's own duration moved in the sheet")
        cases = [("duration", int(seconds * 1000), percent) for seconds in shouts.values()]
        self.assertEqual(self.drive(cases, patched=True),
                         [float(int(seconds * 1000) * 2) for seconds in shouts.values()],
                         "a shout is not doubled")

        # the three side effects: not in the field, so nothing to double
        side = {"War Cry - Hardened Wrath": ("duration_seconds", 5.0),
                "Threatening Shout - Demoralize": ("duration_seconds", 4.0),
                "Threatening Shout - Terrify": ("fear_duration_seconds", 3.0)}
        exact = dict(((int(spell), token), float(value)) for spell, token, _q, value in
                     re.findall(r"\((\d+),'([a-z_]+)','([a-z_]*)',([0-9.]+)\)",
                                (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")))
        for name, (token, seconds) in side.items():
            spell = by_name[name]
            self.assertEqual(exact.get((spell, token)), seconds,
                             "%s: %s is not an exact value of %g s" % (name, token, seconds))
            held = durations[int(records[spell]["DurationIndex"])]
            self.assertNotEqual(held, int(seconds * 1000),
                                "%s still keeps its side effect in DurationIndex" % name)
            self.assertEqual(held, int(shouts[name.partition(" - ")[0]] * 1000),
                             "%s does not carry its skill's shout duration" % name)
        # and the module reads those literals, undoubled, where it always did
        abilities = barbarian_source.abilities((".cpp",))
        for read in ('Numbers::Num(r->id, "duration_seconds")',
                     'Numbers::Num(r->id, "fear_duration_seconds")'):
            self.assertIn(read, abilities, "%s is no longer read" % read)
        self.assertNotIn("ModifiedDurationSeconds(p, id, Numbers::Num(r->id", abilities,
                         "a side effect was routed through the modifier")

    def test_the_duration_aura_is_switched_on_where_the_others_are(self):
        """A modifier nothing casts is a number nobody gets.

        The cost and cooldown modifiers are added and removed in one place,
        the passive refresh, and the duration one has to be in that same pass
        or a player who respecs keeps a doubling they no longer own.
        """
        passives = barbarian_source.PASSIVES.read_text(encoding="utf-8")
        # the one pass that rebuilds a player's modifiers, in its own order
        self.assertIn("            CooldownModifiers(p, Has(p, \"Boon of Bul-Kathos\"));\n"
                      "            DurationModifiers(p, Has(p, \"Inspiring Presence\"));\n"
                      "            CostModifiers(p, relentless, swordAndBoard);\n",
                      passives, "the duration modifier is not rebuilt with the other two")
        self.assertIn("p->RemoveAurasDueToSpell(row.id);",
                      passives[passives.index("void DurationModifiers("):][:900],
                      "the duration modifier is never taken off again")
        shells = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn("inline constexpr DurationModifier DurationModifiers[] = {", shells)
        self.assertIn("{82407, \"Inspiring Presence\"},", shells)

    def test_no_barbarian_cooldown_reaches_the_half_second_floor(self):
        """The ruling's question (decisions.md), answered from the data.

        D3 floors a reduced cooldown at 0.5 s (skilldata.js:642); the core has
        no floor and would install nothing at all if a flat reduction took a
        cooldown to zero. This states what today's numbers can actually reach,
        so the day something makes 0.5 s reachable this fails and the ruling
        is asked for rather than assumed.
        """
        records = generated_records()
        manifest = read_csv(GENERATED / "spell_shells.csv")
        # every flat reduction that exists: the Boon records, by skill bit.
        # A bit is a skill only within the modifier's own family, so the key is
        # (family, skill): the Wizard's family-21 records reuse the Barbarian's
        # bit numbers and no Boon record reaches them (diablocraft-wizard-records).
        flats = {}
        bit_of = {(int(records[int(row["spell_id"])]["SpellClassSet"]), row["name"]):
                  int(records[int(row["spell_id"])]["SpellClassMask_1"])
                  for row in manifest if row["kind"] == "active"}
        for row in manifest:
            if row["kind"] != "cooldown_modifier" or not row["name"].startswith("Boon"):
                continue
            record = records[int(row["spell_id"])]
            mask = int(record["EffectSpellClassMaskA_1"])
            for (family, skill), bit in bit_of.items():
                if family == int(record["SpellClassSet"]) and bit & mask:
                    flats[(family, skill)] = max(flats.get((family, skill), 0),
                                                 -int(record["EffectBasePoints_1"]))
        self.assertTrue(flats and all(family == 20 for family, _skill in flats),
                        "the Boon records reach the Barbarian's skills and no other class's")
        # the most percentage reduction the game can produce: the paragon cap
        # and every rollable Cooldown Reduction source, multiplied as the sheet
        # multiplies them. Read, not assumed: the rules row and the gem table.
        paragon = next(float(row.split("','")[4]) for row in
                       (GENERATED / "paragon_0001_rules.sql").read_text(encoding="utf-8").splitlines()
                       if "'cdr'" in row and "INSERT" in row)
        cap = next(float(row.split("','")[5]) for row in
                   (GENERATED / "paragon_0001_rules.sql").read_text(encoding="utf-8").splitlines()
                   if "'cdr'" in row and "INSERT" in row)
        best = 1 - paragon * cap / 100
        for percent in cooldown_affix_maxima():
            best *= 1 - percent / 100
        reachable = 100 * (1 - best)
        self.assertLess(reachable, 100, "cooldown reduction can reach a free cast")
        # Per family: the Barbarian's (20) is the ruling's question, and every
        # other class's records are held to the same floor.
        shortest = {}
        for row in manifest:
            if row["kind"] not in ("active", "rune"):
                continue
            record = records[int(row["spell_id"])]
            base = int(record["RecoveryTime"]) or int(record["CategoryRecoveryTime"])
            if not base:
                continue
            family = int(record["SpellClassSet"])
            flat = flats.get((family, row["name"].split(" - ")[0]), 0)
            left = self.drive([("cooldown", base, -flat, reachable)], patched=True)[0]
            shortest[family] = min(shortest.get(family, left), left)
        self.assertIn(20, shortest, "no Barbarian record carries a cooldown")
        self.assertGreater(shortest[20], 500,
                           "a Barbarian cooldown now reaches D3's 0.5 s floor, which the core "
                           "does not apply: ask for the ruling before shipping this")
        for family, left in shortest.items():
            self.assertGreater(left, 500,
                               "a family-%d cooldown now reaches D3's 0.5 s floor, which the "
                               "core does not apply: ask for the ruling before shipping this"
                               % family)

    def test_the_module_no_longer_installs_a_skill_cooldown(self):
        """The core installs it from the record; the module keeps one exception."""
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        start = combat.split("void StartSkillCooldown(Player* player, std::uint32_t spellId, bool offhand)")[1]
        start = start[:start.index("\n    }\n")]
        self.assertIn("!PrimaryData::Find(spellId)", start,
                      "the module still installs a cooldown for something other than a primary")
        self.assertNotIn("Tectonic Rift", start, "the stored-charge exemption outlived the record")
        # and the ability cast path does not call it at all any more
        finish = combat.split("void Finish()")[1]
        finish = finish[:finish.index("\n            }\n")]
        self.assertNotIn("StartSkillCooldown", finish,
                         "AfterCast still replaces the cooldown the core installed")
        # Boon is a modifier, not a subtraction from a running timer
        passives = (MODULE / "src/combat/dc_passives.cpp").read_text(encoding="utf-8") + barbarian_source.PASSIVES.read_text(encoding="utf-8")
        self.assertNotIn("ModifySpellCooldown", passives,
                         "Boon of Bul-Kathos still refunds instead of modifying")
        self.assertIn("Shells::CooldownModifiers", passives)
        # the runtime shell carries no second copy of the number
        self.assertNotIn("shell.cooldown", combat)
        self.assertNotIn("shell->cooldown", combat)

    def test_a_flat_cost_reduction_comes_off_after_the_percentages(self):
        """core-patches/0014 keeps D3's order for a flat cost beside a percentage one.

        Prism (flat 9 Arcane Power) and Power of the Storm (flat 3) are flat
        SPELLMOD_COST auras. D3 multiplies the percentages first and subtracts
        the flat amount after (d3-cost-cooldown-math.md 2.2: 40 at 30% with a
        flat 9 pays 19). Upstream 27e096204 (#27388) puts SPELLMOD_COST in the
        flat-first branch, which would charge 21.7; the patch keeps it out.
        """
        cases = [("costflat", 1000, -225, 30), ("costflat", 40, -9, 30), ("costflat", 100, -150, 30)]
        self.assertEqual(self.drive(cases, patched=True), [475, 19, 0],
                         "a flat cost reduction must come off after the percentages, floored at 0")
        flat_first = self.drive([cases[0]], mutate=(
            "if (op == SPELLMOD_CASTING_TIME || op == SPELLMOD_DURATION || op == SPELLMOD_COOLDOWN)",
            "if (op == SPELLMOD_CASTING_TIME || op == SPELLMOD_DURATION || op == SPELLMOD_COST || op == SPELLMOD_COOLDOWN)"),
            name="mutated-flat-first")[0]
        self.assertNotEqual(flat_first, 475, "the flat-after proof does not come from the extracted combine")

    def test_the_evidence_is_the_executable_combine(self):
        """Mutate the extracted code and the proofs above fail.

        The point of extracting `Player::ApplySpellMod` rather than modelling
        it: if what the patch changes stopped being what runs, these numbers
        would move. Both mutations are of the patched lines themselves.
        """
        cost = self.drive([("stack", 25, 30, 20, 50)], mutate=(
            "if (mod->op == SPELLMOD_DAMAGE || mod->op == SPELLMOD_DOT || mod->op == SPELLMOD_COST)",
            "if (mod->op == SPELLMOD_DAMAGE || mod->op == SPELLMOD_DOT)"), name="mutated-cost")[0]
        self.assertNotEqual(cost, 7.0, "the cost proof does not come from the extracted combine")
        cooldown = self.drive([("cooldown", 120000, -30000, 40)], mutate=(
            "if (op == SPELLMOD_CASTING_TIME || op == SPELLMOD_DURATION || op == SPELLMOD_COOLDOWN)",
            "if (op == SPELLMOD_CASTING_TIME || op == SPELLMOD_DURATION)"),
            name="mutated-cooldown")[0]
        self.assertNotEqual(cooldown, 54000,
                            "the cooldown proof does not come from the extracted combine")

    def test_the_patch_says_what_this_arithmetic_assumes(self):
        """The header states the sources and the stock-class side effects."""
        text = PATCH.read_text(encoding="utf-8")
        self.assertIn("--- a/src/server/game/Entities/Player/Player.cpp", text)
        self.assertRegex(text, r"^# Reason:", "the patch has no reason header")
        self.assertIn("Approved: ruling 2026-09-20", text)
        for source in ("d3planner simulator/cast.js:136-147", "skilldata.js:636-642",
                       "docs/research/d3-cost-cooldown-math.md"):
            self.assertIn(source, text, "the header does not cite %s" % source)
        self.assertIn("Side effects on stock classes", text)

    # --- what the character sheet shows ------------------------------------

    def test_the_sheet_shows_what_the_paying_aura_charges(self):
        """Exactly, including the round-down cases. No tolerance.

        The gear aura carries whole percent, so gear 33.4 pays 33 - and the
        sheet shows 33, because what it publishes is the measured number
        itself and not the product of its own contributions (decisions.md,
        2026-09-20). The harness runs the module's own Calculate and the
        core's own combine.
        """
        gears = [0, 5, 12.34, 30, 33.4, 47.5, 49.9, 60, 99.6, 100]
        passives = [(), (50,), (20,), (50, 20)]
        cases = [("display", gear) + percents for gear in gears for percents in passives]
        answers = self.drive(cases, source="display_harness.cpp")
        for (_kind, gear, *percents), (applied, shown, again) in zip(cases, answers):
            self.assertAlmostEqual(shown, applied, places=9,
                                   msg="the sheet does not show what is charged: "
                                       "%g with %s shows %g, charges %g"
                                       % (gear, percents, shown, applied))
            self.assertAlmostEqual(shown, again, places=9,
                                   msg="a second refresh moved the sheet: %g with %s"
                                       % (gear, percents))
        # the two cases the rulings named
        applied, shown, _again = answers[cases.index(("display", 30, 50, 20))]
        self.assertAlmostEqual(applied, 72.0, places=6)
        self.assertAlmostEqual(shown, 72.0, places=6)
        _applied, rounded, _again = answers[cases.index(("display", 33.4))]
        self.assertAlmostEqual(rounded, 33.0, places=6,
                               msg="gear 33.4 pays 33 and must show 33, not 33.4")

    def test_the_sheet_shows_what_the_cooldown_aura_takes_off(self):
        """Step 6's half of the same ruling, on a real RecoveryTime.

        The cooldown is the core's now, the gear reduction is a whole-percent
        SPELLMOD_COOLDOWN aura, and the sheet shows what that aura takes off -
        measured, not the product of the sheet's own Cooldown Reduction rows.
        A record's own RecoveryTime is the base, so this is the number a
        player would see on their own cooldown.
        """
        probe = int(re.search(r"COOLDOWN_PROBE = (\d+);",
                              (MODULE / "src/combat/dc_cost_math.h").read_text(encoding="utf-8"))[1])
        # a millisecond of the probe, which is what the core's truncation to a
        # whole millisecond can cost the measurement; twice it, because the
        # combine itself is evaluated in float and the last unit is not exact
        grain = 2 * 100.0 / probe
        gears = [0, 5, 12.34, 30, 33.4, 47.5, 49.9, 60]
        cases = [("cooldown", gear, probe) for gear in gears]
        answers = self.drive(cases, source="display_harness.cpp")
        for (_kind, gear, _probe), (applied, shown, again) in zip(cases, answers):
            self.assertAlmostEqual(shown, applied, places=9,
                                   msg="the sheet does not show what the aura takes off: "
                                       "%g shows %g, takes %g" % (gear, shown, applied))
            self.assertAlmostEqual(shown, again, places=9,
                                   msg="a second refresh moved the sheet: %g" % gear)
            self.assertAlmostEqual(applied, round(gear), delta=grain,
                                   msg="%g: the aura carries whole percent" % gear)
        # the named case, the cooldown twin of gear 33.4 paying 33
        _applied, rounded, _again = answers[cases.index(("cooldown", 33.4, probe))]
        self.assertAlmostEqual(rounded, 33.0, delta=grain,
                               msg="gear 33.4 takes 33% off and must show 33, not 33.4")
        # and a real skill's own cooldown is that same percentage, to the
        # millisecond the core rounds it to
        records = generated_records()
        shells = {row["name"]: int(row["spell_id"])
                  for row in read_csv(GENERATED / "spell_shells.csv")
                  if row["kind"] in ("active", "rune")}
        base = int(records[shells["Ignore Pain"]]["RecoveryTime"])
        self.assertEqual(base, 30000, "Ignore Pain's cooldown moved")
        left = self.drive([("cooldown", base, 0, 33.4)], patched=True)[0]
        self.assertEqual(left, 20099, "30 s less 33 %% is 20099 ms, not %d" % left)

    def test_equipping_a_ring_changes_what_the_next_cast_pays(self):
        """The regression the migration owes: the aura follows the item.

        The payment is an aura now, so an item that changes Resource Cost
        Reduction has to reach the aura. Each case wears `gear`, puts on a
        ring worth `ring`, and casts 25 Fury before and after.
        """
        cases = [("equip", 0, 10), ("equip", 30, 10), ("equip", 12.34, 7.5),
                 ("equip", 30, 10, 50, 20), ("equip", 0, 33.4)]
        answers = self.drive(cases, source="display_harness.cpp")
        for (_kind, gear, ring, *passives), (shown, paid, shownAfter, paidAfter) in zip(cases, answers):
            after = 100 * (1 - (1 - gear / 100) * (1 - ring / 100))
            self.assertGreater(shownAfter, shown + 1e-9,
                               "the ring did not reach the sheet: %g + %g" % (gear, ring))
            self.assertLess(paidAfter, paid - 1e-9,
                            "the next cast still paid the old aura: %g + %g" % (gear, ring))
            # what it pays after is what the rebuilt auras charge, to the Rage
            # unit the record is stored in
            percents = [round(after)] + list(passives)
            expected = 25.0
            for percent in percents:
                expected *= 1 - percent / 100
            self.assertAlmostEqual(paidAfter, int(expected / RAGE_UNIT_FURY + 1e-6) * RAGE_UNIT_FURY, places=6,
                                   msg="%g + %g with %s paid %g" % (gear, ring, passives, paidAfter))
            factor = 1 - round(after) / 100
            for percent in passives:
                factor *= 1 - percent / 100
            self.assertAlmostEqual(shownAfter, 100 * (1 - factor), places=6,
                                   msg="the sheet disagrees with the auras after the ring")

    def test_the_display_is_derived_once_and_never_read_back(self):
        """The one rebuild removes it and recomputes before it reads gear."""
        passives = (MODULE / "src" / "combat" / "dc_passives.cpp").read_text(encoding="utf-8")
        self.assertNotIn("applied - gear}", passives, "the additive correction is back")
        self.assertNotIn("DisplayComplement", passives, "the complement is back")
        # Step 6 made it one helper for both reductions, because they are the
        # same six steps on a different modifier.
        rebuild = passives.split("void RebuildGearModifier(Player* p, uint32 gearId")[1]
        removal = rebuild.index("RemoveContribution(guid, Source::Temporary, stat, gearId)")
        recompute = rebuild.index("Stats::Recompute(p);")
        read = rebuild.index("(*sheet)[stat]")
        self.assertLess(removal, recompute, "the derived contribution outlived the recompute")
        self.assertLess(recompute, read, "the gear number was read from a stale sheet")
        # and it is published as the measured value, in its own bucket
        self.assertIn("stat, gearId, measure(),", rebuild)
        self.assertIn("Bucket::Derived}", rebuild)

    def test_everything_that_changes_a_reduction_rebuilds_the_aura(self):
        """One refresh function, called from item, paragon and passive paths."""
        calls = {
            "src/items/dc_items_equip.cpp": "DC::Combat::Passives::RefreshModifiers(player);",
            "src/stats/dc_stats.cpp": "DC::Combat::Passives::RefreshModifiers(player);",
            "src/classes/barbarian/dc_barbarian_passives.cpp": "RefreshModifiers(p);",
        }
        for path, call in calls.items():
            text = (MODULE / path).read_text(encoding="utf-8")
            self.assertIn(call, text, "%s does not rebuild the gear auras" % path)
        items = items_source.read("dc_items_equip.cpp")
        # equip, unequip and socket all reach Apply, which is where the call is
        apply = items.split("void Apply(Player* player, Item* item, bool equipping)")[1]
        self.assertIn("DC::Stats::Recompute(player);\n        // The Fury cost reductions", apply,
                      "the rebuild does not follow the item recompute")
        stats = (MODULE / "src/stats/dc_stats.cpp").read_text(encoding="utf-8")
        paragon = stats.split("bool ReplaceParagon(")[1].split("\n    }\n")[0]
        self.assertIn("RefreshModifiers(player);", paragon,
                      "a paragon point in a reduction never reaches the aura")
        # one call rebuilds BOTH gear auras, so a cooldown ring is not a second
        # path somebody has to remember
        passives = (MODULE / "src/combat/dc_passives.cpp").read_text(encoding="utf-8")
        refresh = passives.split("void RefreshModifiers(Player* p)")[1]
        self.assertIn("Stat::ResourceCostReduction", refresh)
        self.assertIn("Stat::CooldownReduction", refresh)
        # the measured display is a bucket of its own, not a reduction factor
        common = (MODULE / "src/common/dc_common.cpp").read_text(encoding="utf-8")
        self.assertIn("Derived bucket is only for the measured cost and cooldown reductions", common)
        self.assertIn("measuredCost ? *measuredCost : (1 - cost) * 100", common)
        self.assertIn("measuredCooldown ? *measuredCooldown : (1 - cooldown) * 100", common)

    # --- the sheet is where the numbers live -------------------------------

    def test_the_module_reads_the_channel_terms_from_the_sheet(self):
        """No term of the channel model is a literal in the module."""
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src" / "combat" / "dc_combat_internal.h", *sorted((MODULE / "src" / "combat").glob("dc_combat*.cpp"))])
        for token in ("channel_cost_speed_term_resource", "channel_cost_flat_resource",
                      "channel_tick_frames_count", "channel_frames_per_second_count"):
            self.assertIn('"%s"' % token, combat, "%s is not read from the record" % token)
        model = combat.split("double WhirlwindTickSeconds")[-1][:1600]
        for literal in (" 7 /", "7.0 /", "/ 60", "* 40", "40.0", "60.0"):
            self.assertNotIn(literal, model, "the channel model has a literal %r in it" % literal)
        # and the retired tunable is gone from the module's code and the sheet
        # (the comment that says it was retired is allowed to name it)
        code = [line for line in
                barbarian_source.abilities((".cpp",)).splitlines()
                if not line.lstrip().startswith("//")]
        self.assertNotIn("whirlwind_tick_interval_seconds", "\n".join(code))
        self.assertNotIn("whirlwind_tick_interval_seconds",
                         (MODULE / "data" / "tunables" / "ability_tunables.csv").read_text(encoding="utf-8"))

    def test_the_channel_rows_are_in_the_record_for_the_module_to_read(self):
        """Every Whirlwind shell answers for all four channel terms."""
        every = [row for row in read_csv(GENERATED / "spell_value_map.csv")
                 if row["token"].startswith("channel_")]
        for row in every:
            self.assertEqual(row["source"], "exact", "a channel term left the exact table")
        rows = [row for row in every if row["skill"] == "Whirlwind"]
        self.assertEqual(len(rows), 24, "four terms on Whirlwind and its five runes")
        # The Wizard's three channels carry the two frame terms on every skill
        # and rune record (diablocraft-wizard-resource item 4, 2026-09-22) and
        # none of Whirlwind's cost terms; nothing else carries a channel term.
        # Archon form's Disintegration Wave is the fourth Wizard channel
        # (diablocraft-wizard-mechanics, wizard_archon_values.csv), one record.
        wizard = [row for row in every if row["skill"] != "Whirlwind"]
        self.assertEqual({row["skill"] for row in wizard},
                         {"Ray of Frost", "Arcane Torrent", "Disintegrate", "Archon form"})
        self.assertEqual({row["rune"] for row in wizard if row["skill"] == "Archon form"},
                         {"Disintegration Wave"})
        self.assertEqual({row["token"] for row in wizard},
                         {"channel_tick_frames_count", "channel_frames_per_second_count"})
        self.assertEqual(len(wizard), 38, "two terms on three channels, their fifteen runes and Archon's wave")
        sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        for token in ("channel_cost_speed_term_resource", "channel_tick_frames_count"):
            self.assertEqual(len(re.findall(r"\(81\d+,'%s','',[0-9.]+\)" % token, sql)), 6,
                             "%s is not on all six Whirlwind records" % token)
        self.assertEqual(len(re.findall(r"\(83\d+,'channel_tick_frames_count','',[0-9.]+\)", sql)), 19,
                         "the frame count is not on all nineteen Wizard channel records")


if __name__ == "__main__":
    unittest.main(verbosity=2)
