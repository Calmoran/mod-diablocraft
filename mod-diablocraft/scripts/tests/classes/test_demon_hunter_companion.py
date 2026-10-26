"""Demon Hunter Companion and its five runes (src/classes/demon_hunter/dc_demon_hunter_companion*.h/.cpp), diablocraft-vawmy.33.

What this proves, and how:

  * **The rules that need no core type.** tests/demon_hunter_companion/harness.cpp compiles the real dc_demon_hunter_companion_math.h and is driven
    with the sheets' own rune names and numbers: each rune name is its form (the skill with no rune is the raven); the ferret is a pair and every
    other form one; each form wears its own creature; the boar's Life share is its own and the others' the common one; only the spider and the wolf
    reach a cone, and a point is in the cone when it is within the reach and the half angle of the centre (both ends inclusive, across the wrap of
    the heading); a party member is in range of the boar inside the radius; the boar's regeneration is the Healing table's share (D3's 0.02 of the
    level 70 value is the sheet's 10,728). Planted differences in a scratch copy must each make the driver fail.
  * **The code reads what the sheets state.** Every token dc_demon_hunter_companion.cpp reads is a row of demon_hunter_skill_values.csv for Companion
    (or the rune that states it) with D3's number; every tunable is a row of data/tunables/demonhunter.csv with the number of the power file, which
    decode_pow.py cross-checks where the game archives are on this machine.
  * **The creatures.** demon_hunter_summons.csv names six creatures from donors that exist in the core, with a model, entries no other sheet owns and
    that the math header's EntryOf agrees with; the migration is the generator's render of the sheet.
  * **The wiring.** The dispatch answers BasePct (the cast hits nothing), Cast and RegisterScripts; the pet is a permanent minion of its form with
    the power's Life share, respawn and pet count; the spider slows and the spider and wolf strike a cone; the boar, bat and ferret give their
    gifts while a pet stands; each active does what its sentence says; the ferret's pick-up has nothing to pick up.

What it does not prove: anything on a running server (the look of the pets, the charge and the taunt are docs/test-diablocraft-vawmy.33.md's, live).

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_companion.py
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
import generate_demon_hunter_summons as summons  # noqa: E402
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
SRC = MODULE / "src/classes/demon_hunter"
MATH = SRC / "dc_demon_hunter_companion_math.h"
CODE = SRC / "dc_demon_hunter_companion.cpp"
DISPATCH = SRC / "dc_demon_hunter.cpp"
HARNESS = MODULE / "tests/demon_hunter_companion/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
CORE_SQL = REPO / "azerothcore-wotlk/data/sql/base/db_world"
SKILL = "Companion"
RUNES = {"Spider Companion": (1, 900161), "Boar Companion": (2, 900162), "Wolf Companion": (3, 900163), "Bat Companion": (4, 900164),
         "Ferret Companion": (5, 900165)}
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "demon_hunter_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "demonhunter.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def cases():
    out = []
    # the forms: the skill with no rune is the raven, each rune its own, an unknown name the raven
    out.append((T("rune", ""), "0"))
    out.append((T("rune", "Companion"), "0"))
    out.append((T("rune", "Hunting"), "0"))
    for name, (number, _) in RUNES.items():
        out.append((T("rune", name), str(number)))
    # the pets of a form: the ferret's pair, one of every other
    for name in ("", *RUNES):
        out.append((T("pets", name), "2" if name == "Ferret Companion" else "1"))
    # the creature of a form
    out.append((T("entry", ""), "900160"))
    for name, (_, entry) in RUNES.items():
        out.append((T("entry", name), str(entry)))
    # a pet's Life share: the boar's own, the others' the common one
    life, boar = tune("companion_life_pct"), tune("companion_boar_life_pct")
    for name in ("", *RUNES):
        out.append((T("life", name, life, boar), "%.10g" % (boar if name == "Boar Companion" else life)))
    # a cone for the spider and the wolf alone
    for name in ("", *RUNES):
        out.append((T("cone", name), "1" if name in ("Spider Companion", "Wolf Companion") else "0"))
    # the smallest angle between two headings, across the wrap
    for a, b, want in ((0, 0, "0"), (0, 1, "1"), (1, 0, "1"), (0.1, 6.2, "%.10g" % (6.2832 - 6.1 - 0.0000146 + 0.0000146 if False else (2 * 3.141592653589793 - 6.1))), (0, 3.141592653589793, "%.10g" % 3.141592653589793),
                       (0, 6.283185307179586, "0")):
        out.append((T("angle", a, b), want))
    # the cone: 120 degrees wide, 10 yards deep, the ends inclusive
    yards, degrees = tune("companion_cone_radius_yards"), tune("companion_cone_degrees")
    half = 3.141592653589793 / 3  # 60 degrees
    for heading, centre, distance, want in ((0, 0, 5, 1), (half, 0, 5, 1), (half + 0.01, 0, 5, 0), (-half, 0, 5, 1), (-half - 0.01, 0, 5, 0), (0, 0, yards, 1), (0, 0, yards + 0.01, 0),
                                            (0, 0, 0, 1), (0, 0, -1, 0), (3.141592653589793, 0, 5, 0), (0.1, 6.2, 5, 1), (6.2, 0.1, 5, 1)):
        out.append((T("incone", heading, centre, distance, yards, degrees), str(want)))
    out += [(T("incone", 0, 0, 5, yards, 0), "0"), (T("incone", 0, 0, 5, 0, degrees), "0"), (T("incone", 0, 0, 5, -3, degrees), "0")]
    # a member of the boar's party: within the radius, the end inclusive
    radius = tune("companion_boar_party_radius_yards")
    for distance, yards_, want in ((0, 0, 0), (0, radius, 1), (50, radius, 1), (radius, radius, 1), (radius + 0.01, radius, 0), (-1, radius, 0), (10, 0, 0), (10, -5, 0)):
        out.append((T("party", distance, yards_), str(want)))
    # the boar's regeneration: the Healing table's share; none without a table value or a share
    share = tune("companion_boar_regen_healing_share")
    for table, share_, want in ((536421, share, "%.10g" % (536421 * share)), (1, share, "%.10g" % share), (0, share, "0"), (-5, share, "0"), (536421, 0, "0"), (536421, -1, "0")):
        out.append((T("regen", table, share_), want))
    # whole milliseconds
    for seconds, want in ((5, 5000), (0.5, 500), (0.0004, 0), (3, 3000), (0, 0), (-2, 0), (1.0005, 1001)):
        out.append((T("millis", seconds), str(want)))
    return out


def drive(header_text, name="real"):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"classes/demon_hunter/dc_demon_hunter_companion_math.h": header_text})
    work = Path(tempfile.mkdtemp(prefix="companion-%s-" % name, dir=str(SCRATCH)))
    try:
        lines = cases()
        (work / "cases.txt").write_text("\n".join(line for line, _ in lines) + "\n")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return [w for _, w in lines if w is not None], run.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Rules(unittest.TestCase):
    def test_every_rule_agrees_with_the_sheets(self):
        want, got = drive(MATH.read_text(encoding="utf-8"))
        self.assertGreater(len(want), 70)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        want, _ = drive(real)
        mutants = {
            "the_spider_is_the_raven": ('if (name == "Spider Companion")\n            return Rune::Spider;', ""),
            "the_boar_is_the_wolf": ('if (name == "Boar Companion")\n            return Rune::Boar;', 'if (name == "Boar Companion")\n            return Rune::Wolf;'),
            "the_bat_is_a_ferret": ('if (name == "Bat Companion")\n            return Rune::Bat;', 'if (name == "Bat Companion")\n            return Rune::Ferret;'),
            "a_pair_of_ravens": ("return rune == Rune::Ferret ? 2u : 1u;", "return rune == Rune::Raven ? 2u : 1u;"),
            "one_ferret": ("return rune == Rune::Ferret ? 2u : 1u;", "return 1u;"),
            "the_wolf_wears_the_boar": ("case Rune::Wolf:\n                return 900163;", "case Rune::Wolf:\n                return 900162;"),
            "the_raven_wears_nothing": ("case Rune::Raven:\n                return 900160;", "case Rune::Raven:\n                return 0;"),
            "the_boar_has_the_common_life": ("return rune == Rune::Boar ? boarPct : formsPct;", "return formsPct;"),
            "everyone_has_the_boars_life": ("return rune == Rune::Boar ? boarPct : formsPct;", "return boarPct;"),
            "the_bat_has_a_cone": ("return rune == Rune::Spider || rune == Rune::Wolf;", "return rune == Rune::Spider || rune == Rune::Wolf || rune == Rune::Bat;"),
            "the_wolf_has_no_cone": ("return rune == Rune::Spider || rune == Rune::Wolf;", "return rune == Rune::Spider;"),
            "the_angle_is_not_folded": ("return difference > twoPi / 2 ? twoPi - difference : difference;", "return difference;"),
            "the_cone_end_is_exclusive": ("return AngleBetween(heading, centre) <= half + 1e-9;", "return AngleBetween(heading, centre) < half - 1e-9;"),
            "the_cone_is_too_wide": ("double const half = degrees * 0.017453292519943295 / 2.0;", "double const half = degrees * 0.017453292519943295;"),
            "the_cone_reach_is_exclusive": ("distance < 0 || distance > yards", "distance < 0 || distance >= yards"),
            "no_cone_reach": ("distance < 0 || distance > yards", "distance < 0"),
            "negative_distance_counts": ("distance < 0 || distance > yards", "distance > yards"),
            "no_width_is_a_cone": ("if (degrees <= 0 || yards <= 0 ||", "if (yards <= 0 ||"),
            "the_party_end_is_exclusive": ("return yards > 0 && distance >= 0 && distance <= yards;", "return yards > 0 && distance >= 0 && distance < yards;"),
            "no_reach_is_the_party": ("return yards > 0 && distance >= 0 && distance <= yards;", "return distance >= 0 && distance <= yards;"),
            "the_regen_ignores_the_share": ("return healingAtLevel > 0 && share > 0 ? healingAtLevel * share : 0.0;", "return healingAtLevel > 0 && share > 0 ? healingAtLevel : 0.0;"),
            "a_negative_regen": ("return healingAtLevel > 0 && share > 0 ? healingAtLevel * share : 0.0;", "return healingAtLevel * share;"),
            "millis_truncate": ("static_cast<std::uint32_t>(std::llround(seconds * 1000.0))", "static_cast<std::uint32_t>(seconds * 1000.0)"),
            "millis_of_a_negative": ("return seconds > 0 ?", "return seconds != 0 ?"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = drive(real.replace(old, new, 1), name)
                self.assertNotEqual(want, got, name + " survived")


class Sheets(unittest.TestCase):
    def test_the_skill_rows_are_the_researched_numbers(self):
        expected = {("", "cooldown_seconds", ""): 30, ("", "damage_bonus_pct", ""): 500, ("", "damage_pct", ""): 100,
                    ("Spider Companion", "radius_yards", ""): 25, ("Spider Companion", "slow_pct", "active"): 80, ("Spider Companion", "slow_duration_seconds", "active"): 5,
                    ("Spider Companion", "damage_pct", ""): 140, ("Spider Companion", "slow_pct", "passive"): 60, ("Spider Companion", "slow_duration_seconds", "passive"): 3,
                    ("Boar Companion", "radius_yards", ""): 20, ("Boar Companion", "duration_seconds", ""): 5, ("Boar Companion", "damage_pct", ""): 50,
                    ("Boar Companion", "heal_per_second_life", ""): 10728, ("Boar Companion", "resistance_pct", ""): 20,
                    ("Wolf Companion", "radius_yards", ""): 60, ("Wolf Companion", "damage_bonus_pct", ""): 15, ("Wolf Companion", "duration_seconds", ""): 10,
                    ("Wolf Companion", "damage_pct", ""): 150, ("Bat Companion", "gain_resource", ""): 50, ("Bat Companion", "damage_pct", ""): 60,
                    ("Bat Companion", "regen_per_second_resource", ""): 1, ("Ferret Companion", "radius_yards", ""): 60, ("Ferret Companion", "damage_pct", ""): 50,
                    ("Ferret Companion", "gold_find_pct", ""): 10, ("Ferret Companion", "movement_speed_pct", ""): 10}
        for (rune, token, qualifier), number in expected.items():
            self.assertEqual(number, value(rune, token, qualifier), (rune, token, qualifier))

    def test_the_boar_regeneration_is_the_healing_share_at_level_70(self):
        table = re.search(r"Table\[71\] = \{(.*?)\};", (MODULE / "src/combat/dc_healing_table.h").read_text(encoding="utf-8"), re.S)[1]
        values = [float(x) for x in table.replace("\n", "").split(",") if x.strip()]
        self.assertEqual(71, len(values))
        self.assertAlmostEqual(value("Boar Companion", "heal_per_second_life"), tune("companion_boar_regen_healing_share") * values[70], delta=0.5)

    def test_every_token_the_code_reads_is_a_row(self):
        text = CODE.read_text(encoding="utf-8")
        tokens = set(re.findall(r'Num\((?:record|base|spellId), "([a-z_]+)"(?:, "([a-z]*)")?\)', text))
        self.assertGreaterEqual(len(tokens), 12)
        known = {(r["token"], r["qualifier"]) for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        for token, qualifier in tokens:
            self.assertIn((token, qualifier), known, token)

    def test_every_tunable_the_code_reads_is_a_row_with_the_power_files_number(self):
        text = CODE.read_text(encoding="utf-8")
        names = set(re.findall(r'Tune\("([a-z_]+)"\)', text))
        self.assertEqual({"companion_life_pct", "companion_boar_life_pct", "companion_cone_radius_yards", "companion_cone_degrees", "companion_respawn_seconds",
                          "companion_boar_party_radius_yards", "companion_boar_party_seconds", "companion_boar_regen_healing_share",
                          "companion_poll_seconds", "companion_gift_hold_polls"}, names)
        # The keeper's look and the gifts' hold are the code's own cadence (as the Necromancer's minion_keeper_poll_seconds): not in a power file.
        cadence = {"companion_poll_seconds": 1, "companion_gift_hold_polls": 3}
        for name, number in cadence.items():
            row = tunables()[name]
            self.assertEqual(number, float(row["d3_value"]), name)
            self.assertEqual("", row["value"], name)
            self.assertIn("not D3", row["notes"], name)
        want = {"companion_respawn_seconds": 5, "companion_life_pct": 35, "companion_boar_life_pct": 50, "companion_cone_radius_yards": 10, "companion_cone_degrees": 120,
                "companion_boar_party_radius_yards": 100, "companion_boar_party_seconds": 3, "companion_boar_regen_healing_share": 0.02}
        for name in names - set(cadence):
            row = tunables()[name]
            self.assertEqual(want[name], float(row["d3_value"]), name)
            self.assertEqual("", row["value"], name)
            self.assertIn("pow", row["notes"], name)

    def test_the_power_files_hold_the_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda name: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", name], capture_output=True, text=True).stdout  # noqa: E731
        passive = run("x1_DemonHunter_Companion_Passive")
        for label, number in (("Pet Respawn Time \\(seconds\\)", "5.0"), ("A: AOE Radius", "10"), ("C: Pie Angle", "120"), ("B: Party Radius", "100"), ("B: Party Duraton", "3"),
                              ("B: Resistance bonus", "0.20"), ("D: Hatred Per Second Buff", "1"), ("E: Additional Gold Percent", "0.10"), ("E: Increased Movement Speed", "0.1")):
            self.assertRegex(passive, r"'%s' = %s\b" % (label, number))
        self.assertIn("'B: Life Regeneration' = 0.02 * Table(Healing,Effective_Level)", passive)
        self.assertIn("'Pet HP Scalar' = Rune_B ? 0.5 : 0.35", passive)
        self.assertIn("'Max Companion Pets' = 1 + SF_4", passive)
        active = run("X1_DemonHunter_Companion")
        for label, number in (("Raven Bonus Damage %", "5.0"), ("Spider Web Radius", "25"), ("Boar Taunt Radius", "20"), ("Boar Taunt Duration", "5"), ("Wolf Roar Damage Bonus %", "0.15"),
                              ("Wolf Roar Radius", "60"), ("Wolf Roar Duration", "10"), ("Bat Bonus Hatred", "50"), ("Ferret Health Globe Pickup Radius", "60")):
            self.assertRegex(active, r"'%s' = %s\b" % (label, number))
        self.assertIn("CooldownTime = 30", active)


class Creatures(unittest.TestCase):
    def test_six_forms_with_entries_no_other_sheet_owns(self):
        rows = read(D3 / "demon_hunter_summons.csv")
        self.assertEqual(["Companion"] * 6, [r["skill"] for r in rows])
        self.assertEqual(["", *RUNES], [r["rune"] for r in rows])
        self.assertEqual([900160, *[e for _, e in RUNES.values()]], [int(r["entry"]) for r in rows])
        taken = set()
        for name in summons.OTHER_SHEETS:
            taken |= {int(r["entry"]) for r in read(MODULE / name)}
        self.assertEqual(set(), taken & {int(r["entry"]) for r in rows})
        self.assertEqual({"dc_minion"}, {r["script"] for r in rows})
        self.assertEqual(6, len(summons.rows()))

    def test_the_header_and_the_sheet_agree_on_the_creature_of_each_form(self):
        header = MATH.read_text(encoding="utf-8")
        for r in read(D3 / "demon_hunter_summons.csv"):
            self.assertIn("return %s;" % r["entry"], header, r["summon"])

    def test_the_donors_exist_in_the_core_with_a_model(self):
        templates = (CORE_SQL / "creature_template.sql").read_text(encoding="utf-8", errors="replace")
        models = (CORE_SQL / "creature_template_model.sql").read_text(encoding="utf-8", errors="replace")
        for r in read(D3 / "demon_hunter_summons.csv"):
            donor = int(r["donor_creature"])
            self.assertTrue(re.search(r"\(%d,0,0,0,0,0,'" % donor, templates), donor)
            self.assertTrue(re.search(r"\(%d,\d+,\d+,[\d.]+,\d+,\d+\)" % donor, models), donor)

    def test_the_migration_is_the_generators_render_of_the_sheet(self):
        migration = MODULE / "data/sql/db-world/updates" / summons.MIGRATION
        self.assertEqual(summons.render(), migration.read_text(encoding="utf-8"))
        self.assertEqual(6, migration.read_text(encoding="utf-8").count("INSERT INTO creature_template SELECT"))


def code_failures(code, dispatch):
    """What is wrong with the Companion's code and its dispatch ([] when it is right)."""
    flat = re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", code)).replace("( ", "(").replace(" )", ")")
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    make = flat[flat.find("Minions::Kind Make(Player* owner) {"):flat.find("// The members of the Demon Hunter's party")]
    need("the kind is a permanent minion of the form on the bar with the sheet's damage, the form's pet count and the power's Life share",
         'kind.group = "companion"; kind.entry = EntryOf(rune); kind.record = record; kind.damagePct = Num(record, "damage_pct"); kind.cap = Pets(rune);'
         ' kind.lifeToCopyPct = LifePct(rune, Tune("companion_life_pct"), Tune("companion_boar_life_pct"));' in make and "kind.lifeMs" not in make)
    need("the rune on the bar, else the skill's own record, is the form", "std::uint32_t const record = slotted ? slotted : BaseId(Skill);" in make)
    need("each blow runs the form's part", "kind.struck = [record, rune](Player* player, Unit* enemy) { Struck(player, enemy, record, rune); };" in make)

    struck = flat[flat.find("void Struck(Player* player, Unit* enemy, std::uint32_t record, Rune rune) {"):flat.find("Minions::Kind Make(")]
    need("the raven's first blow spends the armed bonus", "flag = false; } if (armed) Minions::Boost(player, \"companion\", 0.0, 0); }" in struck)
    need("the spider's blow slows its enemy and the spider and wolf reach the cone",
         "if (rune == Rune::Spider) SlowOne(player, enemy, record); if (HasCone(rune)) Cone(player, enemy, record, rune);" in struck)
    need("the spider's slow is the passive's percent for the passive's seconds",
         'Slow(player, enemy, Num(record, "slow_pct", "passive"), Num(record, "slow_duration_seconds", "passive"));' in flat)
    cone = flat[flat.find("void Cone("):flat.find("// After each blow of the pet.")]
    need("the cone is round the pet, centred on the enemy struck, tunable, and strikes the others for the form's damage",
         'double const yards = Tune("companion_cone_radius_yards"), degrees = Tune("companion_cone_degrees"); double const centre = pet->GetAngle(struck);' in cone and
         "if (other != struck && other->IsAlive() && InCone(pet->GetAngle(other), centre, pet->GetExactDist(other), yards, degrees) &&"
         ' Combat::Strike(player, other, record, Num(record, "damage_pct")) && rune == Rune::Spider) SlowOne(player, other, record);' in cone)

    gifts = flat[flat.find("void Gifts("):flat.find("class Keeper")]
    need("the boar gives each party member within the radius Life regeneration from the Healing table at their level and the percent resistance",
         'for (Player* member : Party(player, Tune("companion_boar_party_radius_yards"))) { Buffs::Stack(member, record, Stat::LifeRegen, Bucket::Flat,'
         ' RegenPerSecond(Healing::At(member->GetLevel()), Tune("companion_boar_regen_healing_share")), 1, seconds);'
         ' Buffs::Stack(member, record, Stat::AllResistance, Bucket::Percent, Num(record, "resistance_pct"), 1, seconds); }' in gifts)
    need("the boar's gifts last the power's party seconds", 'double const seconds = Tune("companion_boar_party_seconds");' in gifts)
    need("the bat pays its Hatred a second", 'Generate(player, Classes::ClassIdOf(player), record, Num(record, "regen_per_second_resource") * PollMs() / 1000.0);' in gifts)
    need("the ferrets give gold find and movement speed for the held polls",
         'Buffs::Stack(player, record, Stat::GoldFind, Bucket::Flat, Num(record, "gold_find_pct"), 1, hold); Buffs::Stack(player, record, Stat::MovementSpeed,'
         ' Bucket::Flat, Num(record, "movement_speed_pct"), 1, hold);' in gifts and "double const hold = HoldPolls() * PollMs() / 1000.0;" in gifts)
    party = flat[flat.find("std::vector<Player*> Party("):flat.find("// What the form gives")]
    need("the party is the Demon Hunter first, then the alive members of its group on its map within the radius",
         "std::vector<Player*> party{owner};" in party and "member != owner && member->IsAlive() && member->IsInWorld() && member->GetMap() == owner->GetMap()"
         " && InPartyRange(member->GetExactDist(owner), yards)" in party)

    keeper = flat[flat.find("class Keeper final"):flat.find("// \"Active: Your spider throws webs")]
    need("only a Demon Hunter in the world is looked at, once a poll", "if (!IsDemonHunter(player) || !player->IsInWorld()) return;" in keeper and
         "else if ((found->second += diff) < PollMs()) return;" in keeper)
    need("no companion on the bar sends the pet away", "if (!record) { { std::lock_guard<std::mutex> guard(mutex); heldAs.erase(player->GetGUID().GetRawValue()); }"
         ' Minions::Dismiss(player, "companion"); return; }' in keeper)
    need("a rune changed on the bar sends the pet away", 'changed = held && held != record; held = record; } if (changed) Minions::Dismiss(player, "companion");' in keeper)
    need("the pet is kept at the form's count and comes again after the power's respawn seconds",
         'Minions::Keep(player, "companion", Pets(rune), 0, Millis(Tune("companion_respawn_seconds")));' in keeper)
    need("the gifts are given only while a pet stands and the Demon Hunter lives",
         'if (player->IsAlive() && Minions::Alive(player, "companion") > 0) Gifts(player, record, rune);' in keeper)
    need("the keeper forgets the player on logout", "void OnPlayerLogout(Player* player) override { std::lock_guard<std::mutex> guard(mutex);"
         " waited.erase(player->GetGUID().GetRawValue()); heldAs.erase(player->GetGUID().GetRawValue()); ravenArmed.erase(player->GetGUID().GetRawValue()); }" in keeper)

    web = flat[flat.find("void Web("):flat.find("// \"Active: Your boar charges")]
    need("the web reaches the enemies within the radius of the Demon Hunter and of the pet, each once, and slows them by the active's numbers",
         'Combat::Enemies(player, record, player->GetPosition(), radius)' in web and "Combat::Enemies(player, record, pet->GetPosition(), radius)" in web and
         "if (std::find(reached.begin(), reached.end(), enemy) == reached.end()) reached.push_back(enemy);" in web and
         'Slow(player, enemy, Num(record, "slow_pct", "active"), Num(record, "slow_duration_seconds", "active"));' in web)
    taunt = flat[flat.find("void Taunt("):flat.find("void Intervene(")]
    need("the taunt is the boar's stock aura on every enemy within the radius of the Demon Hunter, for the power's seconds, engaged and with threat",
         'Num(record, "radius_yards")' in taunt and "enemy->EngageWithTarget(boar); enemy->GetThreatMgr().AddThreat(boar, 1.0f); if (Aura* taunt = boar->AddAura(TauntAura, enemy))" in taunt and
         "taunt->SetMaxDuration(int32(Millis(seconds))); taunt->SetDuration(int32(Millis(seconds)));" in taunt and 'double const seconds = Num(record, "duration_seconds");' in taunt)
    need("a boar that is gone or a Demon Hunter who died taunts nothing", "if (!boar || !boar->IsAlive() || !player->IsAlive()) return;" in taunt)
    intervene = flat[flat.find("void Intervene("):flat.find("// \"Active: Your wolf howls")]
    need("the boar charges to the Demon Hunter and taunts when it arrives",
         "boar->GetMotionMaster()->MoveCharge(to.GetPositionX(), to.GetPositionY(), to.GetPositionZ());" in intervene and
         "double const travel = boar->GetExactDist(&to) / SPEED_CHARGE;" in intervene and "After(player, travel, [player, guid = boar->GetGUID(), record] { Taunt(player, guid, record); });" in intervene)
    howl = flat[flat.find("void Howl("):flat.find("} // namespace")]
    need("the howl boosts the Demon Hunter and its party within the radius for the power's seconds, under the skill's key",
         'for (Player* member : Party(player, Num(record, "radius_yards"))) DamageBoost::Hold(member, BaseId(Skill), Num(record, "damage_bonus_pct"), Num(record, "duration_seconds"));' in howl)

    cast = flat[flat.find("void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&) {"):flat.find("void RegisterScripts()")]
    need("the raven arms its next attack and boosts the pet for the skill's cooldown",
         "ravenArmed[player->GetGUID().GetRawValue()] = true;" in cast and
         'Minions::Boost(player, "companion", Num(base, "damage_bonus_pct"), Millis(Num(base, "cooldown_seconds")));' in cast)
    need("each rune's active is its own", all(s in cast for s in ("case Rune::Spider: Web(player, spellId);", "case Rune::Boar: Intervene(player, spellId);", "case Rune::Wolf: Howl(player, spellId);",
                                                                  'case Rune::Bat: Generate(player, Classes::ClassIdOf(player), spellId, Num(spellId, "gain_resource"));')))
    need("the ferret's pick-up has nothing to pick up", "case Rune::Ferret:" in cast and "nothing lies on the ground to be picked up" in re.sub(r"\s+", " ", re.sub(r"\n\s*// ?", " ", code)))
    need("the cast hits nothing", "return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;" in flat)
    need("the kind and the keeper are registered", 'Minions::Define("companion", Make); new Keeper();' in flat)

    dflat = re.sub(r"\s+", " ", dispatch)
    need("the dispatch answers BasePct, Cast and RegisterScripts and includes the skill",
         '#include "dc_demon_hunter_companion.h"' in dispatch and "if (auto pet = Companion::BasePct(spellId)) return pet;" in dflat and "Companion::Cast(player, spellId, targets);" in dflat and
         "Companion::RegisterScripts();" in dflat)
    return wrong


class Wiring(unittest.TestCase):
    def test_the_code(self):
        self.assertEqual([], code_failures(CODE.read_text(encoding="utf-8"), DISPATCH.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        code, dispatch = CODE.read_text(encoding="utf-8"), DISPATCH.read_text(encoding="utf-8")
        mutants = {
            "the_pet_has_a_life_time": ("kind.cap = Pets(rune);", "kind.cap = Pets(rune);\n            kind.lifeMs = 30000;"),
            "one_pet_for_every_form": ("kind.cap = Pets(rune);", "kind.cap = 1;"),
            "the_form_is_not_the_bars": ("std::uint32_t const record = slotted ? slotted : BaseId(Skill);", "std::uint32_t const record = BaseId(Skill);"),
            "the_blows_do_nothing": ("kind.struck = [record, rune](Player* player, Unit* enemy) { Struck(player, enemy, record, rune); };", ""),
            "the_boost_is_never_spent": ("if (armed)\n                    Minions::Boost(player, \"companion\", 0.0, 0);", ""),
            "the_spider_does_not_slow": ("if (rune == Rune::Spider)\n                SlowOne(player, enemy, record);\n            if (HasCone(rune))", "if (HasCone(rune))"),
            "the_cone_is_the_targets": ("double const centre = pet->GetAngle(struck);", "double const centre = 0.0;"),
            "the_cone_strikes_the_struck_again": ("if (other != struck && other->IsAlive()", "if (other->IsAlive()"),
            "the_cone_deals_no_damage": ('Combat::Strike(player, other, record, Num(record, "damage_pct"))', 'Combat::Strike(player, other, record, 0.0)'),
            "the_boar_gives_only_the_owner": ("for (Player* member : Party(player, Tune(\"companion_boar_party_radius_yards\")))", "for (Player* member : std::vector<Player*>{player})"),
            "the_regen_is_a_flat_number": ("RegenPerSecond(Healing::At(member->GetLevel()), Tune(\"companion_boar_regen_healing_share\"))", "Num(record, \"heal_per_second_life\")"),
            "the_boar_gives_no_resistance": ("Buffs::Stack(member, record, Stat::AllResistance, Bucket::Percent,\n                                     Num(record, \"resistance_pct\"), 1, seconds);", ""),
            "the_resistance_is_flat": ("Stat::AllResistance, Bucket::Percent", "Stat::AllResistance, Bucket::Flat"),
            "the_bat_pays_per_poll": ('Num(record, "regen_per_second_resource") * PollMs() / 1000.0', 'Num(record, "regen_per_second_resource")'),
            "no_movement_speed": ("Buffs::Stack(player, record, Stat::MovementSpeed, Bucket::Flat, Num(record, \"movement_speed_pct\"),\n                                 1, hold);", ""),
            "no_gold_find": ("Buffs::Stack(player, record, Stat::GoldFind, Bucket::Flat, Num(record, \"gold_find_pct\"), 1, hold);", ""),
            "gifts_without_a_pet": ("if (player->IsAlive() && Minions::Alive(player, \"companion\") > 0)\n                    Gifts(player, record, rune);", "Gifts(player, record, rune);"),
            "a_rune_change_keeps_the_pet": ("if (changed)\n                    Minions::Dismiss(player, \"companion\");", ""),
            "no_respawn_wait": ('Millis(Tune("companion_respawn_seconds"))', "0"),
            "an_unslotted_skill_keeps_the_pet": ("Minions::Dismiss(player, \"companion\");\n                    return;", "return;"),
            "the_web_misses_the_pet": ("if (Creature* pet = Pet(player))\n                for (Unit* enemy : Combat::Enemies(player, record, pet->GetPosition(), radius))\n                    if (std::find(reached.begin(), reached.end(), enemy) == reached.end())\n                        reached.push_back(enemy);", ""),
            "the_web_is_the_passives_slow": ('Num(record, "slow_pct", "active")', 'Num(record, "slow_pct", "passive")'),
            "the_taunt_has_no_threat": ("enemy->GetThreatMgr().AddThreat(boar, 1.0f);", ""),
            "the_taunt_is_endless": ("taunt->SetMaxDuration(int32(Millis(seconds)));\n                    taunt->SetDuration(int32(Millis(seconds)));", ""),
            "the_boar_does_not_charge": ("boar->GetMotionMaster()->MoveCharge(to.GetPositionX(), to.GetPositionY(), to.GetPositionZ());", ""),
            "the_taunt_comes_at_once": ("After(player, travel, [player, guid = boar->GetGUID(), record] { Taunt(player, guid, record); });", "Taunt(player, boar->GetGUID(), record);"),
            "the_howl_boosts_only_the_owner": ("for (Player* member : Party(player, Num(record, \"radius_yards\")))", "for (Player* member : std::vector<Player*>{player})"),
            "the_howl_is_the_raven_bonus": ('DamageBoost::Hold(member, BaseId(Skill), Num(record, "damage_bonus_pct"),', 'DamageBoost::Hold(member, BaseId(Skill), Num(BaseId(Skill), "damage_bonus_pct"),'),
            "the_raven_is_never_armed": ("ravenArmed[player->GetGUID().GetRawValue()] = true;", ""),
            "the_raven_bonus_lasts_forever": ('Millis(Num(base, "cooldown_seconds"))', "0xFFFFFFFFu"),
            "the_cast_hits": ("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", "return std::nullopt;"),
            "not_registered": ('Minions::Define("companion", Make);\n        new Keeper();', 'Minions::Define("companion", Make);'),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, code.count(old), name + " does not apply")
                self.assertNotEqual([], code_failures(code.replace(old, new, 1), dispatch), name + " survived")
        for name, (old, new) in {
            "no_base_pct": ("        if (auto pet = Companion::BasePct(spellId))\n            return pet;\n", ""),
            "no_cast": ("        Companion::Cast(player, spellId, targets);\n", ""),
            "no_scripts": ("        Companion::RegisterScripts();\n", ""),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, dispatch.count(old), name + " does not apply")
                self.assertNotEqual([], code_failures(code, dispatch.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
