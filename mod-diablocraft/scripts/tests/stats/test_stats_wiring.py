"""Issues #54, #55 and #59 on the production path, not beside it.

The first review of this wiring shipped tests that exercised `Calculate`,
`MovementAuraAmount` and `AwardXP` and then claimed both award paths and an
end-to-end movement check. They did not: nothing ran `PublishMovement`, the
affix slow, `SheetAward` or either award caller. This suite runs those, and
says plainly what it still does not run.

Three kinds of check, and they prove different things:

  * **Executions.** `tests/stats_wiring/wiring_harness.cpp` compiles the
    module's own `PublishMovement`, `ApplySlow`, `SheetAward`
    and both XP award hooks plus party eligibility/cache lifecycle, cut out by this script,
    against the doubles in `wiring_shim.h` and the real `dc_common.cpp`. Delete
    a cast, change an aura id or drop a gate and these fail.

  * **Source wiring guards.** Two things cannot be executed here: `Display`
    itself (it writes a dozen core fields). Its call is checked by reading
    source. `Hooks::Kill` now also executes against group/creature doubles;
    its source guard still pins the unchanged party-factor call.

  * **Record assertions.** The two generated spell records are read out of the
    generated SQL by column name: aura type, target, duration and the amount
    convention the module relies on.

What no test here covers: `Unit::UpdateSpeed`. Nothing in this file says how
fast a player ends up running - only which aura is asked for, with what amount,
and when it is taken away. That is docs/test-stats-wiring.md's job, live.
"""
import csv
import importlib.util
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import affixes_text  # noqa: E402
import harness_env
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE = REPO_ROOT / "mod-diablocraft"
HARNESS = MODULE / "tests" / "stats_wiring"
CORE = REPO_ROOT / "azerothcore-wotlk"
SCRATCH = CORE / "build" / "_agent-scratch" / "stats_wiring"
GENERATED = MODULE / "data" / "generated"

D3 = MODULE / "data" / "d3"

STATS = (MODULE / "src" / "stats" / "dc_stats.cpp").read_text(encoding="utf-8")
ELITES = affixes_text()
PARAGON = (MODULE / "src" / "paragon" / "dc_paragon.cpp").read_text(encoding="utf-8")
SHELLS = (MODULE / "src" / "combat" / "dc_spell_shells.h").read_text(encoding="utf-8")
SQL = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
HELPER_IDS = (GENERATED / "spell_helper_ids.csv").read_text(encoding="utf-8")


def definition(marker, source):
    """One function, braces balanced, exactly as the module has it."""
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end].replace(" override", "")


def affix_csv(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def affix_slows():
    """The generated header's slow records, as (id, affix name) pairs."""
    block = re.search(r"inline constexpr AffixSlow AffixSlows\[\] = \{(.*?)\};", SHELLS, re.S)
    assert block, "the generated shells header has no AffixSlows table"
    rows = re.findall(r'\{\s*(\d+),\s*"([^"]+)"\s*\}', block.group(1))
    assert rows, "the AffixSlows table is empty"
    return [(int(spell), affix) for spell, affix in rows]


def helper_map():
    """The persisted identity -> id map, which is append-only, with each row's class.

    diablocraft-wizard-records: the map holds every class's helpers since the
    second class and names the owner in a `class` column; a row without one is
    from the Barbarian-only map it replaced.
    """
    rows = csv.DictReader(io.StringIO(HELPER_IDS))
    return [(row["identity"], int(row["spell_id"]), row.get("class") or "barbarian")
            for row in rows]


def helper_blocks():
    """{class: (first, last)} helper blocks, read from generate_spells.py's CLASS_BLOCKS.

    diablocraft-wizard-records: read from the table that reserves them rather
    than copied, so a new class's helpers are checked against its own block.
    """
    spec = importlib.util.spec_from_file_location("generate_spells_blocks",
                                                  MODULE / "scripts" / "generate/classes/generate_spells.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {stem: block.helpers for stem, block in module.CLASS_BLOCKS.items()}


def shell_id(name):
    found = re.search(r"inline constexpr uint32_t %s = (\d+);" % name, SHELLS)
    assert found, "%s is not in the generated shells header" % name
    return int(found.group(1))


def spell_record(spell_id):
    """One generated spell_dbc row, by column name."""
    columns = [c.strip(" `") for c in
               re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\)", SQL).group(1).split(",")]
    for line in SQL.splitlines():
        line = line.strip()
        if not line.startswith("(%d," % spell_id):
            continue
        row = line[1:].rstrip(";").rstrip(",").rstrip(")")
        # Values are ints or quoted strings; only the numeric ones are read here.
        values = re.findall(r"'(?:[^']|'')*'|[^,]+", row)
        assert len(values) == len(columns), "row %d has %d values for %d columns" % (
            spell_id, len(values), len(columns))
        return dict(zip(columns, values))
    raise AssertionError("no generated record %d" % spell_id)


class StatsWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("c++") or shutil.which("g++")
        if not cls.compiler:
            raise unittest.SkipTest("no C++ compiler")
        SCRATCH.mkdir(parents=True, exist_ok=True)
        head = ("// Generated by scripts/tests/stats/test_stats_wiring.py from the module's own\n"
                "// source. Do not edit; edit the module and run the suite.\n#pragma once\n\n")
        (SCRATCH / "dc_stats_extract.h").write_text(
            head + "namespace DC::Stats\n{\n"
            + definition("void PublishMovement(Player* player, StatSheet const& sheet)", STATS)
            + "\n}\n", encoding="utf-8")
        (SCRATCH / "dc_rift_elites_extract.h").write_text(
            head + "namespace DC::Rifts\n{\n"
            + definition("void ApplySlow(Unit* caster, Player* player, std::uint32_t spell, "
                         "double rate,", ELITES)
            + "\n\n" + definition("void ReleasePlayerControls(Player* player)", ELITES)
            + "\n}\n", encoding="utf-8")
        # The records' own target selection and attribute words, so the harness
        # cannot pass while the record sends the aura somewhere else, or while
        # the flags that decide whether two casters' copies coexist have been
        # changed underneath it. Both are read out of the generated SQL; nothing
        # here restates them.
        every = [shell_id("MovementAggregate")] + [spell for spell, _ in affix_slows()]

        def table(name, kind, column, default):
            cases = "\n".join("    case %du: return %s;" % (spell, spell_record(spell)[column])
                               for spell in every)
            return ("inline %s %s(uint32 spell)\n{\n    switch (spell)\n    {\n"
                    % (kind, name)) + cases + "\n    default: return %s;\n    }\n}\n" % default
        (SCRATCH / "dc_spell_records_extract.h").write_text(
            head + "#include \"wiring_shim.h\"\n\n"
            + table("RecordTargetOf", "int", "ImplicitTargetA_1", "TARGET_UNIT_CASTER") + "\n"
            + table("RecordAuraOf", "int", "EffectAura_1", "0") + "\n"
            + table("RecordAttributesOf", "uint32", "Attributes", "0") + "\n"
            + table("RecordAttributesEx3Of", "uint32", "AttributesEx3", "0"),
            encoding="utf-8")
        (SCRATCH / "dc_paragon_extract.h").write_text(
            head + "namespace DC::Paragon\n{\n"
            + definition("struct PartyXPBonus : DataMap::Base", PARAGON) + ";\n"
            + "\n".join(definition(marker, PARAGON) for marker in (
                "bool ParagonKillMember(Player* player, Unit* victim)",
                "bool LevellingKillMember(Player* player, Creature* victim, Player* tapper)",
                "PartyXPBonus const* PartyBonus(Creature* victim, Player* tapper = nullptr)",
                "void ClearPartyBonus(Unit* victim)",
                "XP SheetAward(Player* player, XP amount, bool fromKill, PartyXPBonus const* bonus = nullptr)"))
            + "\n" + definition("void OnPlayerRewardKillRewarder(Player*, KillRewarder* rewarder, bool, float&)", PARAGON)
            + "\n\n" + definition("void OnPlayerGiveXP(Player* player, uint32& amount, Unit* victim, uint8)",
                                  PARAGON)
            + "\n" + definition("static void Kill(Creature* victim)", PARAGON)
            + "\n" + definition("void OnUnitDeath(Unit* victim, Unit*)", PARAGON)
            + "\n" + definition("void OnUnitEnterEvadeMode(Unit* unit, uint8)", PARAGON)
            + "\n" + definition("void OnCreatureRemoveWorld(Creature* creature)", PARAGON)
            + "\n" + definition("void OnCreatureAddWorld(Creature* creature)", PARAGON)
            + "\n}\n", encoding="utf-8")
        # Native gray thresholds, so eligibility tests use the pinned rule.
        formulas = (CORE / "src/server/game/Miscellaneous/Formulas.h").read_text()
        (SCRATCH / "dc_gray_extract.h").write_text(
            head + "namespace Acore::XP {\n" + definition("inline uint8 GetGrayLevel", formulas)
            + "\n}\n", encoding="utf-8")
        binary = SCRATCH / "wiring_harness"
        built = subprocess.run(
            [cls.compiler, "-std=c++17", "-O0", "-UNDEBUG", "-I", str(SCRATCH), "-I", str(HARNESS),
             str(HARNESS / "wiring_harness.cpp"), str(MODULE / "src" / "common" / "dc_common.cpp"),
             "-o", str(binary)],
            capture_output=True, text=True)
        if built.returncode:
            raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])
        cls.binary = binary

    # --- executions ---------------------------------------------------------

    def test_the_production_functions_do_what_the_issues_asked_for(self):
        """Publisher, slow, release, SheetAward and the levelling hook, run."""
        run = harness_env.run([str(self.binary)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, "a case failed:\n" + run.stderr[-4000:])
        self.assertEqual(run.stdout.strip(), "ok")

    # --- source wiring guards ----------------------------------------------

    def test_display_still_publishes_the_movement_aura(self):
        """`Display` cannot be executed here, so this reads it.

        Comment lines are dropped first: a call that has been commented out is
        not a call, and reading the raw text would have accepted one.
        """
        display = definition("void Display(Player* player, StatSheet const& sheet)", STATS)
        display = "\n".join(line for line in display.splitlines()
                            if not line.lstrip().startswith("//"))
        self.assertIn("PublishMovement(player, sheet);", display,
                      "the publisher is no longer called from Display")
        publish = definition("void PublishMovement(Player* player, StatSheet const& sheet)", STATS)
        self.assertIn("Combat::Shells::MovementAggregate", publish)
        self.assertNotIn("82408", publish, "the aura id is written out instead of taken from the shells header")

    def test_the_kill_award_still_goes_through_the_sheet(self):
        """Supplement the executed Kill body with its party-factor wiring guard."""
        kill = definition("static void Kill(Creature* victim)", PARAGON)
        self.assertIn("AddXP(member,SheetAward(member,amount,true,bonus));", kill,
                      "the at-cap award no longer applies the sheet")
        self.assertIn("KillXP(baseXP,", kill, "the kill award stopped computing its base")
        # Architect, 2026-09-21: kill-only. The rift-quest payout is unchanged.
        grant = definition("bool GrantXP(Player* player, std::uint64_t amount, std::string& error)", PARAGON)
        self.assertNotIn("SheetAward", grant, "the quest payout was given the kill bonus")

    def test_every_affix_slow_is_cast_by_its_elite_with_its_own_milliseconds(self):
        """The caster is the aura's identity, so every site must pass one."""
        # Which record each site passes is the other test; this one is about
        # the caster and the clock. Every site hands its own caster in.
        calls = re.findall(r"ApplySlow\((\w+), player,", ELITES)
        self.assertEqual(sorted(calls), sorted(["elite", "caster", "source"]),
                         "an affix slow does not pass its own caster, or a new call site appeared")
        # The merge that was not equivalent to independent auras is gone, and
        # the aura is keyed by the caster at every touch.
        apply = definition("void ApplySlow(Unit* caster, Player* player, std::uint32_t spell, "
                           "double rate,", ELITES)
        self.assertIn("RemoveAurasDueToSpell(spell, from);", apply)
        self.assertIn("GetAura(spell, from)", apply)
        self.assertNotIn("std::min", apply, "the strongest/longest merge is back")
        self.assertNotIn("std::max", apply, "the strongest/longest merge is back")
        # No player's run rate is written directly any more.
        self.assertNotIn("player->SetSpeed(MOVE_RUN", ELITES,
                         "a player's run rate is being written directly again")
        # The three creature speeds (Fast, Juggernaut, Avenger) are stock auras now (diablocraft-l5ge, conformance C9), so the
        # elite file writes no run rate at all; test_elite_conformance.py holds the replacement.
        self.assertEqual(ELITES.count("SetSpeed(MOVE_RUN"), 0, "a creature run rate is written directly again")

    def test_a_hold_no_longer_owns_a_slow_and_a_map_change_still_ends_one(self):
        apply = definition("bool ApplyHold(Unit* source, Player* player, std::uint32_t donor, std::uint32_t ms)", ELITES)
        self.assertNotIn("AffixSlow", apply,
                         "a hold removes an affix slow aura again")
        self.assertEqual(apply.count("RemoveAurasDueToSpell"), 1,
                         "a hold removes more than its own prior aura")
        code = "\n".join(line for line in ELITES.splitlines() if not line.lstrip().startswith("//"))
        self.assertNotIn("restoreSpeed", code,
                         "the hold still carries a speed to restore (comments may name it; code may not)")
        controls = definition("void ReleasePlayerControls(Player* player)", ELITES)
        self.assertIn("player->RemoveAurasDueToSpell(row.id);", controls,
                      "a slow now rides a map change with nothing to end it")

    # --- the generated records ---------------------------------------------

    def test_both_records_share_the_shape_the_module_relies_on(self):
        """What is the same for both, and is the module's own convention."""
        aggregate = shell_id("MovementAggregate")
        self.assertEqual(aggregate, 82408)
        reference = spell_record(82403)               # the gear cost modifier: a known permanent aura
        shapes = [(aggregate, "31")] + [(spell, "33") for spell, _ in affix_slows()]
        for spell, aura in shapes:
            record = spell_record(spell)
            self.assertEqual(record["Effect_1"], "6", "record %d is not an aura" % spell)
            self.assertEqual(record["EffectAura_1"], aura, "record %d is the wrong aura type" % spell)
            # The amount convention the module relies on: the record carries no
            # number of its own and no die side, so the custom value IS the amount.
            self.assertEqual(record["EffectBasePoints_1"], "0", "record %d carries its own amount" % spell)
            self.assertEqual(record["EffectDieSides_1"], "0", "record %d would roll its amount" % spell)
            # No duration of the record's own: the aggregate never expires and
            # the slow is given the affix's milliseconds by ApplySlow.
            self.assertEqual(record["DurationIndex"], reference["DurationIndex"],
                             "record %d expires on its own clock" % spell)
            self.assertEqual(record["Effect_2"], "0", "record %d brought a second effect along" % spell)

    def test_the_aggregate_is_the_players_own_and_the_slow_is_cast_at_the_player(self):
        """The two are targeted differently, and each has to be checked apart.

        The record decides where its aura lands, not the unit handed to
        `CastCustomSpell`. The aggregate is the player's own, so it names the
        caster. The slow is cast by the elite ON the player, so it has to name
        an explicit target - with `TARGET_UNIT_CASTER` the elite would slow
        itself and the player would never be touched.
        """
        aggregate = spell_record(shell_id("MovementAggregate"))
        self.assertEqual(aggregate["ImplicitTargetA_1"], "1",
                         "the aggregate is no longer the player's own aura")
        self.assertEqual(aggregate["RangeIndex"], "1", "a self-cast aura took a range")
        for spell, affix in affix_slows():
            slow = spell_record(spell)
            self.assertEqual(slow["ImplicitTargetA_1"], "6",
                             "%s's slow selects the caster, so the elite slows itself" % affix)
            # A self-only range on a record cast at someone else is the same
            # class of mismatch. 100 yards is the stock row, and the triggered
            # cast never checks it.
            self.assertEqual(slow["RangeIndex"], "6",
                             "%s's slow record still says self-only range" % affix)

    def test_the_slow_is_shown_to_the_player_and_the_aggregate_is_not(self):
        """The Architect's 2026-09-21 ruling, and the flag it costs.

        `Aura::CanBeSentToClient` is `!IsPassive() || area || ignore-aurastate`,
        so the visibility of a record IS its passive bit and nothing else. The
        aggregate keeps it and stays out of the player's aura bar; the slow
        loses it and is drawn.

        Losing it is not free. A passive aura is a multi-slot aura
        (`SpellInfo::IsMultiSlotAura`), which is the clause that let two elites
        each hold their own copy for nothing; without it `Aura::CanStackWith`
        runs on to "same spell with same caster should not stack", returns
        false, and `Unit::_ApplyAura` then removes the other elite's slow. The
        stock attribute for exactly this - "Stack separately for each caster" -
        is what keeps the per-caster lifetimes, so the two flags are pinned
        together here and their consequence is executed in the harness.
        """
        aggregate = spell_record(shell_id("MovementAggregate"))
        PASSIVE, ALWAYS_HIT, PER_CASTER = 0x40, 0x40000, 0x80
        self.assertTrue(int(aggregate["Attributes"]) & PASSIVE,
                        "the aggregate became visible; it is the player's own hidden total")
        self.assertFalse(int(aggregate["AttributesEx3"]) & PER_CASTER,
                         "the aggregate took a stacking rule it has no use for")
        # Pinned exactly, so any other flag arriving on a record has to be
        # argued for here rather than appearing in a regenerated file.
        self.assertEqual(int(aggregate["Attributes"]), 0x200050)
        self.assertEqual(int(aggregate["AttributesEx3"]), ALWAYS_HIT)
        for spell, affix in affix_slows():
            slow = spell_record(spell)
            self.assertFalse(int(slow["Attributes"]) & PASSIVE,
                             "%s's slow is passive again, so the player cannot see it" % affix)
            self.assertTrue(int(slow["AttributesEx3"]) & PER_CASTER,
                            "%s's slow lost per-caster stacking: two of them would end each "
                            "other's" % affix)
            self.assertEqual(int(slow["Attributes"]), 0x200010)
            self.assertEqual(int(slow["AttributesEx3"]), ALWAYS_HIT | PER_CASTER)

    def test_each_slowing_affix_has_its_own_record_named_from_the_sheet(self):
        """The Architect's 2026-09-21 option A: one record per slowing affix.

        Which affixes slow is data, not a list in the generator: an affix slows
        if `elite_affix_mechanics.csv` gives it a `slow_percent`. The name the
        record carries is the affix's own, exactly as `elite_affixes.csv`
        spells it, because that string is what a player reads off the debuff.
        """
        named = {row["affix_name"] for row in affix_csv("elite_affixes.csv")}
        slowing = {row["affix_name"] for row in affix_csv("elite_affix_mechanics.csv")
                   if row["parameter"] == "slow_percent"}
        self.assertTrue(slowing, "no affix has a slow_percent row any more")
        self.assertTrue(slowing <= named,
                        "an affix slows but is not named in elite_affixes.csv: %r"
                        % sorted(slowing - named))
        self.assertEqual({affix for _spell, affix in affix_slows()}, slowing,
                         "the generated slow records are not one per slowing affix")
        # And the record itself carries that name, not the generator's identity.
        for spell, affix in affix_slows():
            self.assertEqual(spell_record(spell)["Name_Lang_enUS"], "'%s'" % affix,
                             "record %d does not show the affix's name" % spell)

    def test_the_helper_ids_are_stable_and_the_shared_slow_is_retired_not_reused(self):
        """Append-only: an identity keeps its id, and a spent id stays spent.

        82409 held the single shared slow while it was hidden. Option A retires
        it rather than renaming it, so its row stays in the map, its id is
        handed to nobody, and no record is written at it. Nothing was ever
        published there - no migration, no client patch - so the cost is one
        number.
        """
        classed = helper_map()
        blocks = helper_blocks()
        # Identities and ids stay unique across the whole file, every class
        # together: two classes can no more share a helper id than two skills.
        rows = [(identity, spell) for identity, spell, _owner in classed]
        identities = [identity for identity, _ in rows]
        ids = [spell for _, spell in rows]
        self.assertEqual(len(set(identities)), len(identities), "an identity is mapped twice")
        self.assertEqual(len(set(ids)), len(ids), "two identities share an id")
        # diablocraft-wizard-records: each row sits in its own class's helper
        # block, and the Barbarian's is still 82400-82499 exactly.
        self.assertEqual(blocks["barbarian"], (82400, 82499),
                         "the Barbarian's helper block moved")
        for identity, spell, owner in classed:
            self.assertIn(owner, blocks, "%r names a class with no reserved blocks" % identity)
            first, last = blocks[owner]
            self.assertTrue(first <= spell <= last,
                            "%r is outside the reserved helper block" % identity)
        mapped = dict(rows)
        for spell, affix in affix_slows():
            self.assertEqual(mapped.get("%s - affix slow" % affix), spell,
                             "%s's record is not the id its identity is mapped to" % affix)
        retired = "Movement speed - elite affix slow - movement modifier"
        self.assertIn(retired, mapped, "the retired shared slow was dropped from the map")
        self.assertEqual(mapped[retired], 82409)
        self.assertNotIn("(82409,", SQL, "the retired id has a record again")
        self.assertEqual([identity for identity, spell in rows if spell == 82409], [retired],
                         "82409 was handed to another identity")

    def test_every_slow_record_has_a_caller_and_every_caller_has_a_record(self):
        """The per-affix mapping, both ways round.

        A record nothing casts is dead weight; a call site with no record is a
        slow that silently never lands. Neither is visible from a green test
        that only looks at one end, so both ends are read here.
        """
        asked = set(re.findall(r'AffixSlowFor\("([^"]+)"\)', ELITES))
        self.assertEqual(asked, {affix for _spell, affix in affix_slows()},
                         "the affixes the module asks for are not the affixes with records")
        # Each call site passes a record, and it is the one its affix resolved.
        calls = re.findall(r"ApplySlow\(([^;]+)\);", ELITES)
        self.assertEqual(sorted(calls),
                         sorted(["elite, player, n.knockbackSlowSpell, n.knockbackSlow, n.knockbackMs",
                                 "caster, player, zone.slowSpell, zone.slow, zone.tickMs * 2",
                                 "source, player, h.slowSpell, h.slow, h.tickMs * 2"]),
                         "an affix slow does not pass its own record, or a new call site appeared")
        self.assertIn("n.pulseSlowSpell = Combat::Shells::AffixSlowFor(\"Frozen Pulse\");", ELITES)
        self.assertIn("n.knockbackSlowSpell = Combat::Shells::AffixSlowFor(\"Knockback\");", ELITES)
        # Frozen Pulse reaches ApplySlow through the hazard it spawns, so the
        # hazard has to carry the record with the rate.
        self.assertIn("hz.slowSpell = n.pulseSlowSpell;", ELITES,
                      "the frozen pulse hazard no longer carries its own slow record")
        # An unresolved id is a startup error, not a slow that quietly does nothing.
        self.assertIn("if (!n.pulseSlowSpell || !n.knockbackSlowSpell)", ELITES,
                      "a missing generated slow record is no longer reported at startup")
        # And a map change has to take every affix's slow, not one id.
        controls = definition("void ReleasePlayerControls(Player* player)", ELITES)
        self.assertIn("for (auto const& row : Combat::Shells::AffixSlows)", controls,
                      "a map change only takes one affix's slow off again")


if __name__ == "__main__":
    unittest.main(verbosity=2)
