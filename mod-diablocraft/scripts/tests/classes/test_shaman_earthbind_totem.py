"""The Shaman's Earthbind Totem and its five runes (src/classes/shaman/dc_shaman_earthbind_totem.cpp, dc_shaman_earthbind_totem_math.h).

What this proves, and how:

  * **The rules.** tests/shaman_earthbind_totem/harness.cpp compiles the real dc_shaman_earthbind_totem_math.h with the sheets' numbers: Earthgrab
    roots an enemy the first time the totem meets it and never again, a mark holds for the hold seconds and no longer, the edge of the radius is
    within it, and a marked enemy takes Glacial Ground's percent more where an unmarked one takes none. Planted differences in a scratch copy of
    the header must each make it fail.
  * **The sheets and the control immunity.** Every number the code reads is a row of shaman_skill_values.csv for the skill or the rune that reads
    it, the two numbers the draft leaves out (how often the totem looks, how long its holds last) are tunables rows with their migration, and
    Tremor Totem's immunity is Fear, Charm and Stun alone: the shared control immunity gives exactly those mechanics and auras.
  * **The wiring.** The totem seam hands a standing Earthbind Totem to this file; each look slows the enemies within the radius by the skill's
    slow_pct; Earthgrab, Glacial Ground, Gale Vortex and Magma Seep each do their part from their own record; Tremor Totem's immunity follows the
    Shaman into and out of the radius and ends with the totem; the hit loads through the one Shaman::BasePct. Planted differences in the source
    must each be caught.

What it does not prove: the slow, the root, the mark, the pull, the immunity and the burn on a running server (docs/test-diablocraft-xnrvn.22.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_earthbind_totem.py
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
HEADER = "src/classes/shaman/dc_shaman_earthbind_totem_math.h"
HARNESS = MODULE / "tests/shaman_earthbind_totem/harness.cpp"
FOLDER = MODULE / "src/classes/shaman"
SKILL = "Earthbind Totem"


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
    numbers = [value("", "radius_yards"), value("Glacial Ground", "damage_taken_pct"), tunable("earthbind_hold_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 12, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("an enemy is met for the first time every time", ("return seen.insert(enemy).second;", "return true;")),
            ("no enemy is ever met for the first time", ("return seen.insert(enemy).second;", "seen.insert(enemy);\n        return false;")),
            ("seconds are hundredths", ("std::llround(seconds * 1000.0)", "std::llround(seconds * 100.0)")),
            ("a mark holds a millisecond too long", ("return untilMs > nowMs;", "return untilMs >= nowMs;")),
            ("a mark never ends in time", ("return untilMs > nowMs;", "return true;")),
            ("a mark with no hold lasts", ("return holdSeconds > 0 ? nowMs + Millis(holdSeconds) : 0;", "return nowMs + Millis(holdSeconds) + 1;")),
            ("the hold is counted from time zero", ("nowMs + Millis(holdSeconds)", "Millis(holdSeconds)")),
            ("the edge of the radius is outside it", ("return radius > 0 && yards <= radius;", "return radius > 0 && yards < radius;")),
            ("no radius reaches everything", ("return radius > 0 && yards <= radius;", "return yards <= radius || radius <= 0;")),
            ("an unmarked enemy takes the percent", ("return marked && pct > 0 ? pct : 0.0;", "return pct > 0 ? pct : 0.0;")),
            ("a marked enemy takes a negative percent", ("return marked && pct > 0 ? pct : 0.0;", "return marked ? pct : 0.0;")),
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
        "": ("radius_yards", "slow_pct", "duration_seconds"),
        "Earthgrab": ("immobilize_duration_seconds",),
        "Glacial Ground": ("damage_taken_pct",),
        "Gale Vortex": ("interval_seconds", "radius_yards"),
        "Magma Seep": ("damage_pct",),
    }

    def test_every_number_the_code_reads_is_a_row_of_the_sheet(self):
        for rune, tokens in self.READS.items():
            for token in tokens:
                with self.subTest(rune=rune, token=token):
                    self.assertGreater(value(rune, token), 0)
        code = (FOLDER / "dc_shaman_earthbind_totem.cpp").read_text(encoding="utf-8")
        read = set(re.findall(r'Numbers::Num\([^,()]*(?:\([^()]*\))?, "([a-z_]+)"\)', code))
        listed = {token for tokens in self.READS.values() for token in tokens}
        self.assertEqual(set(), read - listed, "a number the code reads that the sheet test does not name")

    def test_the_runes_are_the_sheets(self):
        runes = [r["rune_name"] for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL]
        self.assertEqual(["Earthgrab", "Tremor Totem", "Glacial Ground", "Gale Vortex", "Magma Seep"], runes)
        code = (FOLDER / "dc_shaman_earthbind_totem.cpp").read_text(encoding="utf-8")
        for rune in runes:
            self.assertIn('"%s"' % rune, code, rune)

    def test_the_numbers_the_draft_leaves_out_are_tunables_with_their_migration(self):
        names = ("earthbind_tick_seconds", "earthbind_hold_seconds")
        number = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / number).read_text(encoding="utf-8")
        for name in names:
            with self.subTest(name):
                self.assertGreater(tunable(name), 0)
                self.assertIn("'%s'" % name, migration)
        self.assertGreater(tunable("earthbind_hold_seconds"), tunable("earthbind_tick_seconds"), "a hold must outlast the look that renews it")
        code = (FOLDER / "dc_shaman_earthbind_totem.cpp").read_text(encoding="utf-8")
        self.assertEqual(set(names), set(re.findall(r'Tunable\("([a-z_]+)"\)', code)))

    def test_every_record_of_the_skill_that_states_a_hit_loads_it_though_it_states_a_duration(self):
        # The shell loader reads duration_seconds as damage that waits (DamageWaits); Magma Seep is the one record with a hit and it is claimed by BasePct.
        tokens = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL and r["rune"] == ""}
        self.assertIn("duration_seconds", tokens)
        self.assertNotIn("damage_pct", tokens)
        self.assertEqual(150.0, value("Magma Seep", "damage_pct"))

    def test_tremor_totems_immunity_is_fear_charm_and_stun_alone(self):
        text = (MODULE / "src/combat/dc_control_immunity.cpp").read_text(encoding="utf-8")
        body = text[text.index("void SetFearCharmStun("):text.index("bool Impaired(")]
        self.assertEqual({"MECHANIC_CHARM", "MECHANIC_FEAR", "MECHANIC_STUN"}, set(re.findall(r"MECHANIC_[A-Z_]+", body)))
        self.assertEqual({"SPELL_AURA_MOD_STUN", "SPELL_AURA_MOD_FEAR", "SPELL_AURA_MOD_CHARM"}, set(re.findall(r"SPELL_AURA_MOD_[A-Z_]+", body)))
        self.assertIn("player->RemoveAurasWithMechanic(Mechanics);", body)


def flat_of(text):
    return re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", text)).replace("( ", "(").replace(" )", ")")


FILES = {name: (FOLDER / name).read_text(encoding="utf-8") for name in
         ("dc_shaman_earthbind_totem.cpp", "dc_shaman.cpp", "dc_shaman_totems.cpp", "dc_shaman_effects.cpp")}


def failures(cpp, dispatch, totems, effects):
    flat = flat_of(cpp)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    mark = flat[flat.find("void Mark("):flat.find("void Tick(")]
    need("a mark ends the hold after the look and stale marks are let go",
         "HeldUntil(now, holdSeconds)" in mark and "it = Marked(it->second, now) ? std::next(it) : mine.erase(it);" in mark)
    tick = flat[flat.find("void Tick("):flat.find("void Update(")]
    need("the enemies are those within the record's radius round the totem", 'Combat::Enemies(player, source, totem->GetPosition(), radius)' in tick
         and 'double const radius = Numbers::Num(source, "radius_yards");' in tick)
    need("every enemy in the radius is slowed by the record's slow for the hold", 'Slow(player, enemy, Numbers::Num(source, "slow_pct"), hold);' in tick
         and 'double const hold = Tunable("earthbind_hold_seconds");' in tick)
    need("Earthgrab roots each enemy once for the rune's seconds",
         'if (rune == "Earthgrab" && FirstEntry(state.seen, enemy->GetGUID().GetRawValue())) Root(player, enemy, Numbers::Num(source, "immobilize_duration_seconds"));' in tick)
    need("Glacial Ground marks the enemies in the radius for the hold", 'else if (rune == "Glacial Ground") Mark(player, enemy, hold);' in tick)
    need("Magma Seep burns its percent a second: the percent times the look's share of a second",
         'if (rune == "Magma Seep") Combat::StrikeArea(player, source, totem->GetPosition(), radius, Numbers::Num(source, "damage_pct") * tick);' in tick)
    update = flat[flat.find("void Update("):flat.find("void Upkeep(")]
    need("the look is the tunable tick", 'Totems::Pulses(state.clock[0], diff, tick); due; --due) Tick(player, totem, source, state, tick);' in update
         and 'double const tick = Tunable("earthbind_tick_seconds");' in update)
    need("only Gale Vortex pulls, on the rune's interval over the rune's radius, to the totem",
         'if (RuneOf(source) != "Gale Vortex") return;' in update and 'Totems::Pulses(state.clock[1], diff, Numbers::Num(source, "interval_seconds"))' in update
         and 'Combat::Enemies(player, source, totem->GetPosition(), Numbers::Num(source, "radius_yards"))' in update
         and "Combat::Abilities::Pull(enemy, totem->GetPosition());" in update)
    upkeep = flat[flat.find("void Upkeep("):flat.find("std::optional<double> BasePct(")]
    need("the immunity is the Tremor Totem of the earth slot, the Shaman within the rune's radius",
         'Totems::Standing(player, Totems::EarthSlot); standing && RuneOf(standing) == "Tremor Totem"' in upkeep
         and 'Within(player->GetExactDist(totem), Numbers::Num(standing, "radius_yards"))' in upkeep)
    need("the immunity goes on and off under the rune's own key", "if (worn == wanted) return; if (worn) ControlImmunity::SetFearCharmStun(player, worn, false);"
         " if (wanted) ControlImmunity::SetFearCharmStun(player, wanted, true);" in upkeep)
    mult = flat[flat.find("void Multipliers("):flat.find("void Forget(")]
    need("a marked enemy takes the rune's percent from every skill", 'MorePct(marked, Numbers::Num(RuneId("Glacial Ground"), "damage_taken_pct"))' in mult
         and 'AddFactor(out, "Glacial Ground", pct);' in mult and "marked = on != mine->second.end() && Marked(on->second, Now());" in mult)
    need("the hit of a record of the skill is the sheet's", 'return row && std::string_view(row->skill) == Skill ? Numbers::Get(spellId, "damage_pct") : std::nullopt;' in flat)
    need("the immunity and the marks go with the Shaman", "marks.erase(player->GetGUID().GetRawValue());" in flat and "if (worn) ControlImmunity::SetFearCharmStun(player, worn, false); } }" in flat)
    d = flat_of(dispatch)
    need("the dispatch claims the hit", "if (auto const earthbind = Earthbind::BasePct(spellId)) return earthbind;" in d)
    need("the dispatch gives the multipliers the target", "Earthbind::Multipliers(player, target, spellId, out);" in d)
    need("the upkeep and the logout reach the totem", "Earthbind::Upkeep(player);" in d and "Earthbind::Forget(player);" in d[d.find("void OnPlayerLogout"):])
    t = flat_of(totems)
    need("the seam hands a standing Earthbind Totem to this file",
         'else if (std::string_view(row->skill) == "Earthbind Totem") Earthbind::Update(player, totem, source, state, diff);' in t)
    need("the seam gives the totem of a slot", "Creature* Totem(Player const* player, unsigned slot)" in t and "std::uint32_t Standing(Player const* player, unsigned slot) { Creature* totem = Totem(player, slot);" in t)
    need("a root is the stock hold", "constexpr std::uint32_t RootHold = 64695;" in flat_of(effects) and "void Root(Player* player, Unit* target, double seconds) { Hold(player, target, RootHold, seconds); }" in flat_of(effects))
    return wrong


class Wiring(unittest.TestCase):
    def test_the_totem_slows_and_each_rune_does_its_part(self):
        self.assertEqual([], failures(*(FILES[n] for n in ("dc_shaman_earthbind_totem.cpp", "dc_shaman.cpp", "dc_shaman_totems.cpp", "dc_shaman_effects.cpp"))))

    def test_the_source_guards_fail_their_mutants(self):
        mutants = [
            ("cpp", "the_slow_is_not_applied", 'Slow(player, enemy, Numbers::Num(source, "slow_pct"), hold);', ""),
            ("cpp", "the_slow_holds_nothing", 'Slow(player, enemy, Numbers::Num(source, "slow_pct"), hold);', 'Slow(player, enemy, Numbers::Num(source, "slow_pct"), 0);'),
            ("cpp", "the_radius_is_the_runes_own_dummy", 'double const radius = Numbers::Num(source, "radius_yards");', 'double const radius = 20.0;'),
            ("cpp", "earthgrab_roots_every_look", 'if (rune == "Earthgrab" && FirstEntry(state.seen, enemy->GetGUID().GetRawValue()))', 'if (rune == "Earthgrab")'),
            ("cpp", "earthgrab_roots_for_the_slow", 'Numbers::Num(source, "immobilize_duration_seconds")', 'Numbers::Num(source, "slow_pct")'),
            ("cpp", "glacial_ground_marks_nobody", 'else if (rune == "Glacial Ground")', 'else if (rune == "Nothing")'),
            ("cpp", "magma_seep_burns_a_tick_not_a_second", "Numbers::Num(source, \"damage_pct\") * tick", "Numbers::Num(source, \"damage_pct\")"),
            ("cpp", "magma_seep_never_burns", 'if (rune == "Magma Seep")', 'if (rune == "Nothing")'),
            ("cpp", "the_tick_is_not_the_tunable", 'Tunable("earthbind_tick_seconds")', 'Tunable("earthbind_hold_seconds")'),
            ("cpp", "every_rune_pulls", 'if (RuneOf(source) != "Gale Vortex")', "if (false)"),
            ("cpp", "gale_vortex_pulls_from_the_player", "Combat::Abilities::Pull(enemy, totem->GetPosition());", "Combat::Abilities::Pull(enemy, player->GetPosition());"),
            ("cpp", "tremor_wherever_the_shaman_stands", "Within(player->GetExactDist(totem), Numbers::Num(standing, \"radius_yards\"))", "true"),
            ("cpp", "tremor_for_any_earth_totem", 'standing && RuneOf(standing) == "Tremor Totem"', "standing"),
            ("cpp", "tremor_never_ends", "if (worn)\n            ControlImmunity::SetFearCharmStun(player, worn, false);\n        if (wanted)", "if (wanted)"),
            ("cpp", "glacial_ground_is_the_wrong_percent", 'RuneId("Glacial Ground"), "damage_taken_pct"', 'RuneId("Glacial Ground"), "slow_pct"'),
            ("cpp", "every_skill_claims_the_hit", "std::string_view(row->skill) == Skill ? Numbers::Get", "true ? Numbers::Get"),
            ("dispatch", "the_hit_is_not_claimed", "if (auto const earthbind = Earthbind::BasePct(spellId))", "if (false)"),
            ("dispatch", "no_target_for_the_mark", "Earthbind::Multipliers(player, target, spellId, out);", ""),
            ("dispatch", "no_upkeep", "Earthbind::Upkeep(player);", ""),
            ("dispatch", "the_marks_stay_after_logout", "Earthbind::Forget(player);", ""),
            ("totems", "the_seam_does_not_update_it", "Earthbind::Update(player, totem, source, state, diff);", ""),
            ("effects", "a_root_is_a_stun", "Hold(player, target, RootHold, seconds);", "Hold(player, target, StunHold, seconds);"),
        ]
        for which, name, old, new in mutants:
            with self.subTest(name):
                parts = {"cpp": FILES["dc_shaman_earthbind_totem.cpp"], "dispatch": FILES["dc_shaman.cpp"], "totems": FILES["dc_shaman_totems.cpp"],
                         "effects": FILES["dc_shaman_effects.cpp"]}
                self.assertEqual(1, parts[which].count(old), name + " does not apply")
                parts[which] = parts[which].replace(old, new, 1)
                self.assertNotEqual([], failures(parts["cpp"], parts["dispatch"], parts["totems"], parts["effects"]), name + " survived")


if __name__ == "__main__":
    unittest.main()
