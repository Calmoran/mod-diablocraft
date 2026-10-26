"""Shaman Elemental Blast and its five runes (src/classes/shaman/dc_shaman_elemental_blast.h and .cpp, dc_shaman_damage_mark.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_elemental_blast/harness.cpp compiles the real dc_shaman_elemental_blast.h and
    dc_shaman_damage_mark.h with the sheets' own names and numbers: each rune name is its rune; Prismatic Cycle moves the Attunement
    Fire, Lightning, Cold, Physical, Fire; Elemental Echo adds a burn, an arc, a freeze or a knockback by element; the buff gives
    critical hit chance except under Elemental Mastery, whose rune gives damage of the Attunement's element instead; the splash is
    its share of the blast's damage; Primal Wellspring refunds for a kill or an elite; the buff and the mark hold for their seconds.
    Mutations planted in a scratch copy must each make it fail.
  * **Every record's hit loads above 0.** The skill states a duration (the buff's), so the loader would give every record of it no hit
    (DamageWaits): the test reads the records from the sheet and pins that the skill hands the loader the skill's 760 for every one.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Elemental Blast (or the
    rune that states it); the three numbers the draft does not give are rows of data/tunables/combat.csv, rendered into the tunables
    migration current_migration.txt names.
  * **The wiring.** The class dispatch answers the seams (the cast, the element, the hit, the multipliers, the base percent), the blast
    keeps the Attunement and follows it, the buff lasts its seconds and a second cast replaces it, and Prismatic Cycle moves the
    Attunement after the hits.

What it does not prove: anything on a running server. The element, the buff, the cycle, the echo, the splash, the refund and the rune's
damage are docs/test-diablocraft-xnrvn.28.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_elemental_blast.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADERS = ["src/classes/shaman/dc_shaman_elemental_blast.h", "src/classes/shaman/dc_shaman_damage_mark.h", "src/combat/dc_damage_buckets.h"]
HEADER = HEADERS[0]
MARK = HEADERS[1]
HARNESS = MODULE / "tests/shaman_elemental_blast/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_elemental_blast.cpp"
SKILL = "Elemental Blast"
RUNES = ["Prismatic Cycle", "Elemental Echo", "Unstable Elements", "Elemental Mastery", "Primal Wellspring"]
TUNABLES = {"elemental_blast_burn_tick_seconds": "0.5", "elemental_blast_arc_radius_yards": "15", "elemental_blast_knockback_yards": "6"}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def waiting_runes():
    """The runes whose record the loader would give no hit (dc_combat_internal.h DamageWaits): the record or its skill states a duration."""
    waits = {"dot_duration_seconds", "duration_seconds", "duration_minutes"}
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL]
    states = lambda rune: any(r["rune"] == rune and (r["token"] in waits or (r["token"], r["qualifier"]) == ("damage_pct", "ramp")) for r in rows)
    return [rune for rune in [""] + RUNES if states("") or states(rune)]


def runes():
    rows = sorted((r for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in HEADERS}
    if mutate:
        header, old, new = mutate
        key = header[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {header}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = RUNES + [value("", "crit_chance_pct"), value("Elemental Mastery", "damage_bonus_pct"), value("Unstable Elements", "damage_share_pct"),
                       value("Primal Wellspring", "gain_resource"), value("", "damage_pct"), value("Elemental Echo", "damage_taken_pct"),
                       value("Elemental Echo", "duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 10, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Unstable Elements")\n            return Rune::UnstableElements;', 'if (name == "Unstable Elements")\n            return Rune::ElementalEcho;')),
            ("the cycle skips Cold", (HEADER, 'if (element == "lightning")\n            return "cold";', 'if (element == "lightning")\n            return "physical";')),
            ("the cycle never returns to Fire", (HEADER, 'if (element == "physical")\n            return "fire";', "")),
            ("the cycle goes the other way", (HEADER, 'if (element == "fire")\n            return "lightning";', 'if (element == "fire")\n            return "physical";')),
            ("Cold burns", (HEADER, 'if (element == "cold")\n            return Echo::Freeze;', 'if (element == "cold")\n            return Echo::Burn;')),
            ("Physical adds nothing", (HEADER, 'if (element == "physical")\n            return Echo::Knock;', "")),
            ("the buff always gives critical hit chance", (HEADER, "return rune == Rune::ElementalMastery || pct <= 0 ? 0.0 : pct;", "return pct <= 0 ? 0.0 : pct;")),
            ("the buff never gives critical hit chance", (HEADER, "return rune == Rune::ElementalMastery || pct <= 0 ? 0.0 : pct;", "return 0.0;")),
            ("the rune's damage is for every element", (HEADER, "return rune == Rune::ElementalMastery && sameElement && pct > 0 ? pct : 0.0;", "return rune == Rune::ElementalMastery && pct > 0 ? pct : 0.0;")),
            ("every rune gives the damage", (HEADER, "return rune == Rune::ElementalMastery && sameElement && pct > 0 ? pct : 0.0;", "return sameElement && pct > 0 ? pct : 0.0;")),
            ("the splash is the whole damage", (HEADER, "return hitPct > 0 && sharePct > 0 ? hitPct * sharePct / 100.0 : 0.0;", "return hitPct;")),
            ("Primal Wellspring refunds for any hit", (HEADER, "return (killed || elite) && gain > 0 ? gain : 0.0;", "return gain > 0 ? gain : 0.0;")),
            ("Primal Wellspring refunds only a kill that is an elite", (HEADER, "return (killed || elite) && gain > 0 ? gain : 0.0;", "return (killed && elite) && gain > 0 ? gain : 0.0;")),
            ("a hit deals its record's school even where the seam names another", (HEADER, "return seam && *seam ? std::string_view(seam) : std::string_view(record);", "return std::string_view(record);")),
            ("a hit deals the seam's element even where there is none", (HEADER, "return seam && *seam ? std::string_view(seam) : std::string_view(record);", "return std::string_view(seam ? seam : \"\");")),
            ("the buff holds a millisecond long", (HEADER, "return nowMs < untilMs;", "return nowMs <= untilMs;")),
            ("the mark raises an unmarked enemy's hit", (MARK, "return marked && pct > 0 ? pct : 0.0;", "return pct > 0 ? pct : 0.0;")),
            ("the mark holds a millisecond long", (MARK, "return nowMs < untilMs;", "return nowMs <= untilMs;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), RUNES)

    def test_every_record_states_a_duration_so_the_skill_hands_the_loader_its_hit(self):
        # The skill states the buff's seconds, so DamageWaits reads every record (every rune inherits it) as a damage that waits.
        self.assertEqual(waiting_runes(), [""] + RUNES)

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|gave|BaseId\(\)), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 9, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct"), value("", "duration_seconds"), value("", "crit_chance_pct"),
                          value("Elemental Echo", "damage_pct", "fire"), value("Elemental Echo", "dot_duration_seconds"), value("Elemental Echo", "target_count"),
                          value("Elemental Echo", "damage_pct", "lightning"), value("Elemental Echo", "freeze_duration_seconds"),
                          value("Elemental Echo", "damage_taken_pct"), value("Elemental Echo", "duration_seconds"), value("Unstable Elements", "damage_share_pct"),
                          value("Unstable Elements", "radius_yards"), value("Elemental Mastery", "damage_bonus_pct"), value("Primal Wellspring", "gain_resource")],
                         [40, 760, 6, 10, 300, 3, 3, 200, 1, 15, 4, 50, 12, 15, 20])

    def test_the_tunables_are_rows_of_the_combat_sheet_and_of_the_migration(self):
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / name).read_text(encoding="utf-8")
        self.assertEqual(migration, (MODULE / "data/generated" / name).read_text(encoding="utf-8"))
        for tunable_name, number in TUNABLES.items():
            with self.subTest(tunable_name):
                self.assertEqual(rows[tunable_name]["value"], number)
                self.assertTrue(rows[tunable_name]["notes"].strip())
                self.assertIn(f"('combat', '{tunable_name}', NULL, {float(number)},", migration)

    def test_the_code_reads_only_tunables_the_sheet_has(self):
        used = set(re.findall(r'Tune\("([a-z_]+)"\)', CODE.read_text(encoding="utf-8")))
        self.assertEqual(used, set(TUNABLES))

    def test_the_blast_keeps_the_attunement(self):
        # Elemental Blast follows the Attunement and never moves it by itself (Attunement.h KeepsAttunement): only Prismatic Cycle does.
        header = (MODULE / "src/classes/shaman/dc_shaman_attunement.h").read_text(encoding="utf-8")
        self.assertIn('{"Elemental Blast", "*"}', header)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))
        self.attunement = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_attunement.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("LavaBurst::Landed(player, target, spellId); ElementalBlast::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("Earthquake::Multipliers(player, target, spellId, out); ElementalBlast::Multipliers(player, spellId, out); Ascendance::Multipliers(player, spellId, out); Passive::Multipliers(player, target, spellId, out); DamageMark::Multipliers(player, target, out);", self.dispatch)
        self.assertIn("if (auto lavaBurst = LavaBurst::BasePct(spellId)) return lavaBurst; return ElementalBlast::BasePct(spellId);", self.dispatch)
        self.assertIn("if (char const* element = FlameShock::Element(player, spellId)) return element; return ElementalBlast::Element(player, spellId);", self.dispatch)
        self.assertIn("LavaBurst::Cast(player, spellId); ElementalBlast::Cast(player, spellId);", self.dispatch)

    def test_the_blast_follows_the_attunement_and_hits_for_the_skills_number(self):
        self.assertIn("return Is(spellId) ? Attunement::Current(player) : nullptr;", self.code)
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("char const* Element(")]
        self.assertIn("if (!Is(spellId)) return std::nullopt;", base)
        self.assertIn('return Numbers::Num(BaseId(), "damage_pct");', base)

    def test_every_cast_gives_the_buff_for_its_seconds_and_a_second_cast_replaces_it(self):
        mastery = self.code[self.code.index("void GiveMastery("):self.code.index("char const* ElementOfSpell(")]
        self.assertIn('double const seconds = Numbers::Num(BaseId(), "duration_seconds");', mastery)
        self.assertIn("stamp = mastery.stamp = ++stamps;", mastery)
        self.assertIn("if (found == masteries.end() || found->second.stamp != stamp) return;", mastery)
        self.assertIn('PutCrit(player, CritBonus(rune, Numbers::Num(BaseId(), "crit_chance_pct")));', mastery)
        self.assertIn("PutCrit(player, 0);", mastery)
        put = self.code[self.code.index("void PutCrit("):self.code.index("void GiveMastery(")]
        self.assertIn("Stats::RemoveContribution(guid, Source::Temporary, Stat::CritChance, BaseId());", put)
        self.assertIn("{Source::Temporary, Stat::CritChance, BaseId(), pct, Bucket::Flat}", put)

    def test_prismatic_cycle_moves_the_attunement_after_the_hits(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn("GiveMastery(player, rune, spellId);", cast)
        self.assertIn("if (rune == Rune::PrismaticCycle) if (auto const next = NextElement(Attunement::Current(player))) Attunement::MoveTo(player, *next);", cast)
        self.assertIn("void MoveTo(Player* player, std::string_view element) { if (!IsShaman(player)) return;", self.attunement)

    def test_each_runes_code(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Multipliers(")]
        self.assertIn("if (striking || !player || !target || !Is(spellId)) return;", landed)
        self.assertIn("switch (EchoOf(Attunement::Current(player)).value_or(Echo::Knock))", landed)
        self.assertIn('Burning::Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct", "fire"), seconds, Tune("elemental_blast_burn_tick_seconds"));', landed)
        self.assertIn('Freeze(player, target, Numbers::Num(spellId, "freeze_duration_seconds"));', landed)
        self.assertIn('Abilities::Knockback(player, target, Tune("elemental_blast_knockback_yards"));', landed)
        self.assertIn('DamageMark::Set(player, target, Numbers::Num(spellId, "damage_taken_pct"), Numbers::Num(spellId, "duration_seconds"));', landed)
        self.assertIn('Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct", "lightning"));', self.code)
        self.assertIn('Tune("elemental_blast_arc_radius_yards")', self.code)
        self.assertIn("if (enemy != target) Strikes( player, enemy, spellId, SplashPct(Numbers::Num(BaseId(), \"damage_pct\"), Numbers::Num(spellId, \"damage_share_pct\")));", landed)
        self.assertIn('Gain(player, spellId, Refund(!target->IsAlive(), IsElite(target), Numbers::Num(spellId, "gain_resource")));', landed)

    def test_the_rune_raises_hits_of_the_attunements_element(self):
        multipliers = self.code[self.code.index("void Multipliers("):]
        # The hit's element is the one the blast really deals (the seam), not its record's fixed school.
        self.assertIn("DealtElement(DC::Combat::Shaman::Element(player, spellId), ElementOfSpell(spellId)) == std::string_view(Attunement::Current(player))", multipliers)
        self.assertNotIn("std::string_view(ElementOfSpell(spellId)) == std::string_view(Attunement::Current(player))", multipliers)
        self.assertIn('DamageBonus(rune, same, Numbers::Num(gave, "damage_bonus_pct"))', multipliers)
        self.assertIn('AddFactor(out, "Elemental Mastery", bonus);', multipliers)
        self.assertIn("if (!Holds(Now(), found->second.until)) { masteries.erase(found); return; }", multipliers)


if __name__ == "__main__":
    unittest.main()
