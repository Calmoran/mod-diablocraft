"""The Shaman's Searing Totem and its five runes (src/classes/shaman/dc_shaman_searing_totem.cpp, dc_shaman_searing_totem_math.h).

What this proves, and how:

  * **The rules.** tests/shaman_searing_totem/harness.cpp compiles the real dc_shaman_searing_totem_math.h with the sheets' numbers: Searing
    Flames stacks a bolt up to its most and all end together a while after the last, each stack adds its percent; Frostflame freezes with
    every Nth bolt and starts the count again; Stoneclaw takes its percent off the damage taken; Capacitor's chain goes to the nearest
    enemy it has not been on, never back, and stops when none is left. Planted differences in a scratch copy of the header must each make
    it fail.
  * **The sheets.** Every number the code reads is a row of shaman_skill_values.csv for the skill or the rune that reads it, and the three
    numbers the draft leaves out (how long Searing Flames and the chill last, how far a chain jumps) are tunables rows with their
    migration.
  * **The wiring.** The totem seam hands a standing Searing Totem to this file; a bolt strikes the nearest enemy within the skill's range
    as the Shaman; each rune's part (Magma's pulse on its own interval, Searing Flames' stacks, Capacitor's chain and stun, Frostflame's chill
    and freeze, Stoneclaw's pull) is read from its own record; the stacks and Stoneclaw's reduction are read by the damage path; the three
    shared edits (the target given to the Shaman's multipliers and the Shaman's factor on damage taken in both places) are pinned. Planted
    differences in the source must each be caught.

What it does not prove: the bolts, the stacks, the chain, the chill, the freeze, the stun and the pull on a running server
(docs/test-diablocraft-xnrvn.21.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_searing_totem.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/shaman/dc_shaman_searing_totem_math.h"
HARNESS = MODULE / "tests/shaman_searing_totem/harness.cpp"
FOLDER = MODULE / "src/classes/shaman"
SKILL = "Searing Totem"


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token):
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"]) == (SKILL, rune, token)]
    assert len(rows) == 1, (rune, token, len(rows))
    return float(rows[0]["value"])


def tunable(name):
    rows = [r for r in read(MODULE / "data/tunables/combat.csv") if r["name"] == name]
    assert len(rows) == 1, name
    return float(rows[0]["value"])


def scratch_tree(mutate=None):
    key = HEADER[len("src/"):]
    files = {key: (MODULE / HEADER).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Searing Flames", "max_stacks_count"), value("Searing Flames", "damage_taken_pct"), tunable("searing_flames_seconds"),
               value("Frostflame Totem", "trigger_count"), value("Stoneclaw Totem", "damage_reduction_pct"), value("Capacitor Totem", "target_count")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 22, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("stacks go past the most", ("flames.stacks = std::min(flames.stacks + 1, most);", "flames.stacks = flames.stacks + 1;")),
            ("ended stacks are kept", ("if (flames.untilMs <= nowMs)\n            flames.stacks = 0;", "")),
            ("a bolt does not move the end", ("flames.untilMs = nowMs + Millis(seconds);", "flames.untilMs = flames.untilMs ? flames.untilMs : nowMs + Millis(seconds);")),
            ("stacks last a millisecond too long", ("return flames.untilMs > nowMs ? flames.stacks : 0;", "return flames.untilMs >= nowMs ? flames.stacks : 0;")),
            ("a stack adds nothing more than the first", ("return perStackPct > 0 ? stacks * perStackPct : 0.0;", "return perStackPct > 0 && stacks ? perStackPct : 0.0;")),
            ("a negative percent takes from the target", ("return perStackPct > 0 ? stacks * perStackPct : 0.0;", "return stacks * perStackPct;")),
            ("the freeze is one bolt late", ("if (++bolts < every)", "if (bolts++ < every)")),
            ("the freeze never starts the count again", ("bolts = 0;\n        return true;", "return true;")),
            ("no count freezes every bolt", ("if (!every)\n        {\n            bolts = 0;\n            return false;\n        }", "if (!every)\n            return true;")),
            ("Stoneclaw takes nothing off", ("return 1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0;", "return 1.0;")),
            ("Stoneclaw takes off more than the damage", ("std::clamp(reductionPct, 0.0, 100.0)", "reductionPct")),
            ("the chain goes to the farthest", ("candidates[i].distance < candidates[std::size_t(best)].distance", "candidates[i].distance > candidates[std::size_t(best)].distance")),
            ("the chain goes back to enemies it has been on", ("if (!candidates[i].hit && (best < 0", "if ((best < 0")),
            ("the chain forgets the first enemy", ("std::vector<Unit> out, hit{first};", "std::vector<Unit> out, hit{};")),
            ("the chain jumps one time too many", ("while (out.size() < jumps)", "while (out.size() <= jumps)")),
            ("seconds are hundredths", ("std::llround(seconds * 1000.0)", "std::llround(seconds * 100.0)")),
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
    # The tokens each part of the totem reads, by the record it reads them from.
    READS = {
        "": ("interval_seconds", "radius_yards", "duration_seconds", "damage_pct"),
        "Magma Totem": ("interval_seconds", "radius_yards", "damage_pct"),
        "Searing Flames": ("max_stacks_count", "damage_taken_pct"),
        "Capacitor Totem": ("target_count", "interval_seconds", "radius_yards", "stun_duration_seconds"),
        "Frostflame Totem": ("chill_pct", "trigger_count", "freeze_duration_seconds"),
        "Stoneclaw Totem": ("interval_seconds", "radius_yards", "damage_reduction_pct"),
    }

    def test_every_number_the_code_reads_is_a_row_of_the_sheet(self):
        for rune, tokens in self.READS.items():
            for token in tokens:
                with self.subTest(rune=rune, token=token):
                    self.assertGreater(value(rune, token), 0)
        code = (FOLDER / "dc_shaman_searing_totem.cpp").read_text(encoding="utf-8")
        read = set(re.findall(r'Numbers::Num\([^,()]*(?:\([^()]*\))?, "([a-z_]+)"\)', code))
        listed = {token for tokens in self.READS.values() for token in tokens}
        self.assertEqual(set(), read - listed, "a number the code reads that the sheet test does not name")

    def test_every_record_of_the_skill_has_a_hit_above_zero_though_it_states_a_duration(self):
        # The shell loader reads a duration_seconds, dot_duration_seconds or duration_minutes as damage that waits and loads no hit, unless the class
        # claims the record (Shaman::BasePct). The Searing Totem's records are NOT claimed: the cast that places the totem is a ground area of the shell's
        # size, and a shell that loaded a hit would strike every enemy in range as the totem was placed. So the shell loads none (a duration, no claim), the
        # placement hits nothing, and every bolt and pulse carries its own record's percent (HitPct), which is above 0 for every record of the skill.
        skill = {r["token"]: float(r["value"]) for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL and r["rune"] == ""}
        self.assertIn("duration_seconds", skill)
        by_rune = {}
        for r in read(D3 / "shaman_skill_values.csv"):
            if r["skill"] == SKILL and r["rune"]:
                by_rune.setdefault(r["rune"], {})[r["token"]] = float(r["value"])
        runes = [r["rune_name"] for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL]
        self.assertEqual(5, len(runes))
        for rune in [""] + runes:
            with self.subTest(rune=rune):
                states = {**skill, **by_rune.get(rune, {})}
                self.assertTrue(set(states) & {"duration_seconds", "dot_duration_seconds", "duration_minutes"})
                self.assertGreater(states["damage_pct"], 0)

    def test_the_runes_are_the_sheets(self):
        runes = [r["rune_name"] for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL]
        self.assertEqual(["Magma Totem", "Searing Flames", "Capacitor Totem", "Frostflame Totem", "Stoneclaw Totem"], runes)
        code = (FOLDER / "dc_shaman_searing_totem.cpp").read_text(encoding="utf-8")
        for rune in runes:
            self.assertIn('"%s"' % rune, code, rune)

    def test_the_numbers_the_draft_leaves_out_are_tunables_with_their_migration(self):
        names = ("searing_flames_seconds", "frostflame_chill_seconds", "totem_chain_yards")
        number = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / number).read_text(encoding="utf-8")
        for name in names:
            with self.subTest(name):
                self.assertGreater(tunable(name), 0)
                self.assertIn("'%s'" % name, migration)
        code = (FOLDER / "dc_shaman_searing_totem.cpp").read_text(encoding="utf-8")
        self.assertEqual(set(names), set(re.findall(r'Tunable\("([a-z_]+)"\)', code)))


def flat_of(text):
    return re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", text)).replace("( ", "(").replace(" )", ")")


FILES = {name: (FOLDER / name).read_text(encoding="utf-8") for name in
         ("dc_shaman_searing_totem.cpp", "dc_shaman.cpp", "dc_shaman_effects.cpp")}
COMBAT = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")


def failures(cpp, dispatch, effects, combat):
    flat = flat_of(cpp)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    bolt = flat[flat.find("void Bolt("):flat.find("void Update(")]
    need("a bolt reaches the skill's own range, not the rune's", 'Combat::Enemies(player, source, totem->GetPosition(), Numbers::Num(BaseId(Skill), "radius_yards"))' in bolt)
    need("the bolt goes to the nearest enemy and strikes as the Shaman", "Totems::Nearest(distances)" in bolt and "Unit* target = enemies[nearest];" in bolt and "if (!Combat::Strike(player, target, source, HitPct(source))) return;" in bolt)
    need("Searing Flames stacks on a bolt that hit", 'if (rune == "Searing Flames") AddFlame(player, target, source);' in bolt)
    need("Capacitor Totem chains the bolt", 'else if (rune == "Capacitor Totem") Chain(player, target, source);' in bolt)
    need("Frostflame chills with the rune's percent for the tunable seconds",
         'Slow(player, target, Numbers::Num(source, "chill_pct"), Tunable("frostflame_chill_seconds"));' in bolt)
    need("every Nth bolt freezes for the rune's seconds",
         'if (Freezes(state.bolts, unsigned(Numbers::Num(source, "trigger_count")))) Freeze(player, target, Numbers::Num(source, "freeze_duration_seconds"));' in bolt)
    chain = flat[flat.find("void Chain("):flat.find("void Bolt(")]
    need("the chain goes to the rune's count within the tunable reach, each struck as the bolt was",
         'Walk(first, unsigned(Numbers::Num(source, "target_count"))' in chain and 'double const reach = Tunable("totem_chain_yards");' in chain
         and "Combat::Enemies(player, source, on->GetPosition(), reach)" in chain and "Combat::Strike(player, enemy, source, HitPct(source));" in chain)
    flame = flat[flat.find("void AddFlame("):flat.find("void Chain(")]
    need("a stack is the rune's most for the tunable seconds on the enemy",
         'Stack(on, now, unsigned(Numbers::Num(source, "max_stacks_count")), Tunable("searing_flames_seconds"))' in flame)
    need("ended stacks are let go", "it = Live(it->second, now) ? std::next(it) : mine.erase(it);" in flame)
    update = flat[flat.find("void Update("):flat.find("void Multipliers(")]
    need("Magma Totem pulses on its own interval over its radius round the totem instead of bolting",
         'if (rune == "Magma Totem") { for (unsigned due = Totems::Pulses(state.clock[0], diff, Numbers::Num(source, "interval_seconds")); due; --due)'
         ' Combat::StrikeArea(player, source, totem->GetPosition(), Numbers::Num(source, "radius_yards"), HitPct(source)); return; }' in update)
    need("the bolt is the skill's interval", 'Totems::Pulses(state.clock[0], diff, Numbers::Num(BaseId(Skill), "interval_seconds")); due; --due) Bolt(player, totem, source, state);' in update)
    need("only Capacitor and Stoneclaw have a second pulse, on the rune's interval", 'if (rune != "Capacitor Totem" && rune != "Stoneclaw Totem") return;' in update
         and 'Totems::Pulses(state.clock[1], diff, Numbers::Num(source, "interval_seconds"))' in update)
    need("Capacitor stuns for the rune's seconds, Stoneclaw pulls to the totem",
         'if (rune == "Capacitor Totem") Stun(player, enemy, Numbers::Num(source, "stun_duration_seconds") * ItemPowers::StunFactor(player)); else Combat::Abilities::Pull(enemy, totem->GetPosition());' in update)
    mult = flat[flat.find("void Multipliers("):flat.find("double TakenFactor(")]
    need("only a Fire skill's hit takes the stacks", "!(info->SchoolMask & SPELL_SCHOOL_MASK_FIRE)) return;" in mult)
    need("the percent a stack adds is the rune's", 'MorePct(stacks, Numbers::Num(RuneId("Searing Flames"), "damage_taken_pct"))' in mult and 'AddFactor(out, "Searing Flames", pct);' in mult)
    taken = flat[flat.find("double TakenFactor("):flat.find("void Forget(")]
    need("the reduction holds while a Stoneclaw Totem stands in the fire slot",
         'Totems::Standing(player, Totems::FireSlot); return standing && RuneOf(standing) == "Stoneclaw Totem"'
         ' ? TakenFactorOf(Numbers::Num(standing, "damage_reduction_pct")) : 1.0;' in taken)
    need("the flames go with the Shaman", "flames.erase(player->GetGUID().GetRawValue());" in flat[flat.find("void Forget("):])
    d = flat_of(dispatch)
    need("the dispatch gives the multipliers the target", "void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)" in d
         and "Searing::Multipliers(player, target, spellId, out);" in d)
    need("the dispatch does not claim the skill's record for the shell loader (the placement cast would then hit every enemy in range)", "Searing::BasePct" not in d)
    need("the dispatch answers the factor on damage taken", "double TakenFactor(Unit* victim) { return Searing::TakenFactor(victim); }" in d)
    need("the flames are let go on logout", "Searing::Forget(player);" in d[d.find("void OnPlayerLogout"):])
    c = flat_of(combat)
    need("the loader claims the Shaman's hit before the second pass reads a duration as damage that waits",
         "else if (auto shaman = Shaman::BasePct(ability.id)) shell.damagePct = *shaman;" in c
         and c.index("Shaman::BasePct(ability.id)") < c.index("DamageWaits(ability.id)"))
    need("the file claims nothing for the shell loader and every strike carries the record's percent",
         "BasePct" not in flat and 'double HitPct(std::uint32_t source) { return Numbers::Num(source, "damage_pct"); }' in flat)
    need("the combat path gives the Shaman the target", "Shaman::Multipliers(player, target, shell.spellId, hit.factors);" in c)
    need("both damage-taken paths take the Shaman's factor", c.count("Monk::TakenFactor(victim) * Shaman::TakenFactor(victim)") + c.count("Monk::TakenFactor(victim)*Shaman::TakenFactor(victim)") == 2)
    e = flat_of(effects)
    need("a freeze holds still as a stun does", "void Freeze(Player* player, Unit* target, double seconds) { Hold(player, target, StunHold, seconds); }" in e)
    need("a stun is the plain hold (the call site lengthens the seconds)", "void Stun(Player* player, Unit* target, double seconds) { Hold(player, target, StunHold, seconds); }" in e)
    need("a slow is the percent negated", "-static_cast<int>(std::lround(pct))" in e)
    return wrong


class Wiring(unittest.TestCase):
    def test_the_totem_bolts_and_each_rune_does_its_part(self):
        self.assertEqual([], failures(FILES["dc_shaman_searing_totem.cpp"], FILES["dc_shaman.cpp"], FILES["dc_shaman_effects.cpp"], COMBAT))

    def test_the_source_guards_fail_their_mutants(self):
        mutants = [
            ("cpp", "the_bolt_reaches_the_runes_range", 'Numbers::Num(BaseId(Skill), "radius_yards"));', 'Numbers::Num(source, "radius_yards"));'),
            ("cpp", "the_bolt_goes_to_the_first", "Unit* target = enemies[nearest];", "Unit* target = enemies[0];"),
            ("cpp", "a_bolt_that_missed_stacks", "if (!Combat::Strike(player, target, source, HitPct(source)))", "if (!Combat::Strike(player, target, source, HitPct(source)) && false)"),
            ("cpp", "the_bolt_has_no_percent", "Combat::Strike(player, target, source, HitPct(source))", "Combat::Strike(player, target, source)"),
            ("cpp", "the_chain_has_no_percent", "Combat::Strike(player, enemy, source, HitPct(source));", "Combat::Strike(player, enemy, source);"),
            ("cpp", "the_pulse_has_no_percent", 'Numbers::Num(source, "radius_yards"), HitPct(source));', 'Numbers::Num(source, "radius_yards"));'),
            ("cpp", "the_percent_is_the_duration", 'return Numbers::Num(source, "damage_pct");', 'return Numbers::Num(source, "duration_seconds");'),
            ("cpp", "the_file_claims_the_hit", "    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)\n    {", "    std::optional<double> BasePct(std::uint32_t spellId)\n    {\n        return Numbers::Get(spellId, \"damage_pct\");\n    }\n\n    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)\n    {"),
            ("cpp", "flames_never_stack", 'if (rune == "Searing Flames")', 'if (rune == "Nothing")'),
            ("cpp", "the_chain_is_never_run", 'else if (rune == "Capacitor Totem")', 'else if (rune == "Nothing")'),
            ("cpp", "the_chill_is_the_tunable_for_the_wrong_seconds", 'Tunable("frostflame_chill_seconds")', 'Tunable("searing_flames_seconds")'),
            ("cpp", "the_freeze_is_every_bolt", "if (Freezes(state.bolts, unsigned(Numbers::Num(source, \"trigger_count\"))))", "if (true)"),
            ("cpp", "the_chain_forgets_its_count", 'unsigned(Numbers::Num(source, "target_count"))', "2u"),
            ("cpp", "stacks_have_no_most", 'unsigned(Numbers::Num(source, "max_stacks_count"))', "99u"),
            ("cpp", "ended_stacks_are_kept", "it = Live(it->second, now) ? std::next(it) : mine.erase(it);", "it = std::next(it);"),
            ("cpp", "magma_also_bolts", 'if (rune == "Magma Totem")', 'if (rune == "Nothing")'),
            ("cpp", "the_bolt_is_the_runes_interval", 'Numbers::Num(BaseId(Skill), "interval_seconds")', 'Numbers::Num(source, "interval_seconds")'),
            ("cpp", "every_rune_has_a_second_pulse", 'if (rune != "Capacitor Totem" && rune != "Stoneclaw Totem")', "if (false)"),
            ("cpp", "capacitor_pulls", "if (rune == \"Capacitor Totem\")\n                    Stun", "if (rune == \"Nothing\")\n                    Stun"),
            ("cpp", "every_school_takes_the_flames", "!(info->SchoolMask & SPELL_SCHOOL_MASK_FIRE)", "false"),
            ("cpp", "stoneclaw_always_reduces", 'standing && RuneOf(standing) == "Stoneclaw Totem"', "standing"),
            ("cpp", "stoneclaw_looks_in_the_wrong_slot", "Totems::Standing(player, Totems::FireSlot)", "Totems::Standing(player, Totems::EarthSlot)"),
            ("cpp", "flames_stay_after_logout", "flames.erase(player->GetGUID().GetRawValue());", ""),
            ("dispatch", "no_target_for_the_multipliers", "Searing::Multipliers(player, target, spellId, out);", ""),
            ("dispatch", "no_factor_on_damage_taken", "return Searing::TakenFactor(victim);", "return 1.0;"),
            ("dispatch", "flames_stay_after_logout_in_the_dispatch", "Searing::Forget(player);", ""),
            ("combat", "the_loader_does_not_claim_the_hit", "else if (auto shaman = Shaman::BasePct(ability.id))", "else if (false)"),
            ("dispatch", "the_dispatch_claims_the_skill", "        if (auto const ghostWolf = GhostWolf::BasePct(spellId))", "        if (auto const searing = Searing::BasePct(spellId))\n            return searing;\n        if (auto const ghostWolf = GhostWolf::BasePct(spellId))"),
            ("combat", "the_hit_is_not_given_the_target", "Shaman::Multipliers(player, target, shell.spellId, hit.factors);", "Shaman::Multipliers(player, nullptr, shell.spellId, hit.factors);"),
            ("combat", "one_damage_taken_path_misses_it", "ItemPowers::IncomingFactor(victim->ToPlayer()) * Monk::TakenFactor(victim) * Shaman::TakenFactor(victim);", "ItemPowers::IncomingFactor(victim->ToPlayer()) * Monk::TakenFactor(victim);"),
            ("effects", "a_freeze_is_a_stun_with_items", "void Freeze(Player* player, Unit* target, double seconds)\n    {\n        Hold(player, target, StunHold, seconds);", "void Freeze(Player* player, Unit* target, double seconds)\n    {\n        Hold(player, target, StunHold, seconds * 2);"),
        ]
        for which, name, old, new in mutants:
            with self.subTest(name):
                parts = {"cpp": FILES["dc_shaman_searing_totem.cpp"], "dispatch": FILES["dc_shaman.cpp"], "effects": FILES["dc_shaman_effects.cpp"], "combat": COMBAT}
                self.assertEqual(1, parts[which].count(old), name + " does not apply")
                parts[which] = parts[which].replace(old, new, 1)
                self.assertNotEqual([], failures(parts["cpp"], parts["dispatch"], parts["effects"], parts["combat"]), name + " survived")


if __name__ == "__main__":
    unittest.main()
