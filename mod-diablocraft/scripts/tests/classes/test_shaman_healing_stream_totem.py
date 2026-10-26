"""The Shaman's Healing Stream Totem and its five runes (src/classes/shaman/dc_shaman_healing_stream_totem.cpp, dc_shaman_healing_stream_totem_math.h).

What this proves, and how:

  * **The rules.** tests/shaman_healing_stream_totem/harness.cpp compiles the real dc_shaman_healing_stream_totem_math.h with the sheets' numbers:
    a look heals its share of a second of the percent of maximum Life, Healing Tide heals its percent once and never more than all the Life,
    Maelstrom Spring gives its number a second, Cleansing Stream's immunity ends the seconds after the placing and not a millisecond later,
    Ancestral Protection prevents the first lethal blow within the radius once and heals to the Life floor, never to less than the Life they had.
    Planted differences in a scratch copy of the header must each make it fail.
  * **The sheets.** Every number the code reads is a row of shaman_skill_values.csv for the skill or the rune that reads it, and the one number the
    draft leaves out (how often the totem heals) is a tunables row with its migration.
  * **The wiring.** The totem seam hands a standing Healing Stream Totem to this file; a look heals the Shaman and the party within the radius;
    each rune's part is read from its own record; the class's upkeep ends Cleansing Stream's immunity with its seconds or its totem; the damage hook
    asks the Shaman beside the other classes' saves; the hit of Riptide loads through the one Shaman::BasePct. Planted differences in the source
    must each be caught.

What it does not prove: the heals, the Maelstrom, the cleanse, the water bolts and the saved death on a running server
(docs/test-diablocraft-xnrvn.23.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_healing_stream_totem.py
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
HEADER = "src/classes/shaman/dc_shaman_healing_stream_totem_math.h"
HARNESS = MODULE / "tests/shaman_healing_stream_totem/harness.cpp"
FOLDER = MODULE / "src/classes/shaman"
SKILL = "Healing Stream Totem"


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
    numbers = [value("", "life_regen_pct"), value("Healing Tide", "heal_pct"), value("Maelstrom Spring", "regen_per_second_resource"),
               value("Cleansing Stream", "duration_seconds"), value("Ancestral Protection", "life_floor_pct"),
               tunable("healing_stream_tick_seconds"), value("", "radius_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a look heals the whole percent whatever its length", ("maxLife * pctPerSecond / 100.0 * tickSeconds", "maxLife * pctPerSecond / 100.0")),
            ("a negative percent takes Life away", ("return maxLife > 0 && pctPerSecond > 0 && tickSeconds > 0 ?", "return maxLife > 0 && pctPerSecond != 0 && tickSeconds > 0 ?")),
            ("a heal is the percent of a hundred", ("maxLife * pctPerSecond / 100.0 * tickSeconds", "maxLife * pctPerSecond * tickSeconds")),
            ("Healing Tide heals more than all the Life", ("maxLife * std::min(pct, 100.0) / 100.0", "maxLife * pct / 100.0")),
            ("Healing Tide heals nothing", ("return maxLife > 0 && pct > 0 ? maxLife * std::min(pct, 100.0) / 100.0 : 0.0;", "return 0.0;")),
            ("Maelstrom Spring gives a number a look", ("return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;", "return perSecond > 0 ? perSecond : 0.0;")),
            ("seconds are hundredths", ("std::llround(seconds * 1000.0)", "std::llround(seconds * 100.0)")),
            ("the immunity ends a millisecond late", ("return untilMs > nowMs;", "return untilMs >= nowMs;")),
            ("the immunity never ends", ("return untilMs > nowMs;", "return true;")),
            ("the immunity is counted from time zero", ("return seconds > 0 ? placedMs + Millis(seconds) : 0;", "return seconds > 0 ? Millis(seconds) : 0;")),
            ("a blow that leaves Life is prevented", ("damage > 0 && damage >= health;", "damage > 0;")),
            ("a blow that kills one point short is not", ("damage > 0 && damage >= health;", "damage > 0 && damage > health;")),
            ("a death outside the radius is prevented", ("return !alreadySaved && within && damage > 0", "return !alreadySaved && damage > 0")),
            ("a second death is prevented", ("return !alreadySaved && within && damage > 0", "return within && damage > 0")),
            ("the heal can take Life away", ("return std::max(health, maxLife > 0", "return (maxLife > 0")),
            ("the floor is past all the Life", ("std::clamp(floorPct, 0.0, 100.0)", "floorPct")),
            ("the edge of the radius is outside it", ("return radius > 0 && yards <= radius;", "return radius > 0 && yards < radius;")),
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
        "": ("radius_yards", "life_regen_pct", "duration_seconds"),
        "Healing Tide": ("heal_pct",),
        "Maelstrom Spring": ("regen_per_second_resource",),
        "Cleansing Stream": ("duration_seconds",),
        "Riptide": ("interval_seconds", "damage_pct"),
        "Ancestral Protection": ("life_floor_pct", "cooldown_seconds"),
    }

    def test_every_number_the_code_reads_is_a_row_of_the_sheet(self):
        for rune, tokens in self.READS.items():
            for token in tokens:
                with self.subTest(rune=rune, token=token):
                    self.assertGreater(value(rune, token), 0)
        code = (FOLDER / "dc_shaman_healing_stream_totem.cpp").read_text(encoding="utf-8")
        read = set(re.findall(r'Numbers::Num\([^,()]*(?:\([^()]*\))?, "([a-z_]+)"\)', code))
        listed = {token for tokens in self.READS.values() for token in tokens}
        self.assertEqual(set(), read - listed, "a number the code reads that the sheet test does not name")

    def test_the_runes_are_the_sheets(self):
        runes = [r["rune_name"] for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL]
        self.assertEqual(["Healing Tide", "Maelstrom Spring", "Cleansing Stream", "Riptide", "Ancestral Protection"], runes)
        code = (FOLDER / "dc_shaman_healing_stream_totem.cpp").read_text(encoding="utf-8")
        for rune in runes:
            self.assertIn('"%s"' % rune, code, rune)

    def test_the_number_the_draft_leaves_out_is_a_tunable_with_its_migration(self):
        number = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / number).read_text(encoding="utf-8")
        self.assertGreater(tunable("healing_stream_tick_seconds"), 0)
        self.assertIn("'healing_stream_tick_seconds'", migration)
        code = (FOLDER / "dc_shaman_healing_stream_totem.cpp").read_text(encoding="utf-8")
        self.assertEqual({"healing_stream_tick_seconds"}, set(re.findall(r'Tunable\("([a-z_]+)"\)', code)))

    def test_the_cooldowns_are_the_sheets(self):
        self.assertEqual(30.0, value("", "cooldown_seconds"))
        self.assertEqual(90.0, value("Ancestral Protection", "cooldown_seconds"))

    def test_every_record_of_the_skill_that_states_a_hit_loads_it_though_it_states_a_duration(self):
        # The shell loader reads duration_seconds as damage that waits (DamageWaits); Riptide is the one record with a hit and it is claimed by BasePct.
        tokens = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL and r["rune"] == ""}
        self.assertIn("duration_seconds", tokens)
        self.assertNotIn("damage_pct", tokens)
        self.assertEqual(200.0, value("Riptide", "damage_pct"))


def flat_of(text):
    return re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", text)).replace("( ", "(").replace(" )", ")")


FILES = {name: (FOLDER / name).read_text(encoding="utf-8") for name in
         ("dc_shaman_healing_stream_totem.cpp", "dc_shaman.cpp", "dc_shaman_totems.cpp")}
HOOKS = (MODULE / "src/combat/dc_combat_hooks.cpp").read_text(encoding="utf-8")


def failures(cpp, dispatch, totems, hooks):
    flat = flat_of(cpp)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    allies = flat[flat.find("std::vector<Player*> Allies("):flat.find("void HealTarget(")]
    need("the allies are the Shaman and the party members alive in the map within the radius of the totem",
         "if (Within(player->GetExactDist(totem), radius)) out.push_back(player);" in allies and "member != player && member->IsAlive() && member->IsInMap(player) &&"
         " Within(member->GetExactDist(totem), radius)" in allies)
    placed = flat[flat.find("void Placed("):flat.find("void Tick(")]
    need("Healing Tide heals each ally its percent when the totem is placed",
         'if (rune == "Healing Tide") for (Player* ally : allies) HealTarget(player, ally, source, PlacedHeal(ally->GetMaxHealth(), Numbers::Num(source, "heal_pct")));' in placed)
    need("Cleansing Stream gives each ally the immunity under the record's key for the rune's seconds",
         'if (rune != "Cleansing Stream") return;' in placed and 'ImmuneUntil(Now(), Numbers::Num(source, "duration_seconds"))' in placed
         and "ControlImmunity::Set(ally, source, true); now.wearers.push_back(ally->GetGUID());" in placed)
    tick = flat[flat.find("void Tick("):flat.find("void Bolt(")]
    need("each look heals every ally the skill's percent of their own maximum Life",
         'HealTarget(player, ally, source, TickHeal(ally->GetMaxHealth(), Numbers::Num(source, "life_regen_pct"), tick))' in tick
         and 'Allies(player, totem, Numbers::Num(source, "radius_yards"))' in tick)
    need("Maelstrom Spring gives the Shaman, in range, the rune's number a second through the class's one Gain",
         'if (RuneOf(source) == "Maelstrom Spring" && !allies.empty() && allies.front() == player) Gain(player, source,'
         ' TickGain(Numbers::Num(source, "regen_per_second_resource"), tick));' in tick)
    bolt = flat[flat.find("void Bolt("):flat.find("void Release(")]
    need("Riptide's bolt goes to the nearest enemy within the radius as the Shaman",
         "Totems::Nearest(distances)" in bolt and "Combat::Strike(player, enemies[nearest], source);" in bolt
         and 'Combat::Enemies(player, source, totem->GetPosition(), Numbers::Num(source, "radius_yards"))' in bolt)
    update = flat[flat.find("void Update("):flat.find("void Upkeep(")]
    need("the placing is told once", "if (!state.placed) { state.placed = true; Placed(player, totem, source); }" in update)
    need("the look is the tunable", 'Tunable("healing_stream_tick_seconds")' in update and "Totems::Pulses(state.clock[0], diff, tick); due; --due) Tick(player, totem, source, tick);" in update)
    need("only Riptide bolts, on the rune's interval", 'if (RuneOf(source) != "Riptide") return;' in update
         and 'Totems::Pulses(state.clock[1], diff, Numbers::Num(source, "interval_seconds"))' in update)
    upkeep = flat[flat.find("void Upkeep("):flat.find("std::optional<double> BasePct(")]
    need("the immunity ends with its seconds or with the totem that gave it",
         "if (Immune(found->second.untilMs, Now()) && Totems::Standing(player, Totems::WaterSlot) == found->second.key) return;" in upkeep and "Release(worn);" in upkeep)
    need("the immunity is taken off each wearer under the key it was given", "ControlImmunity::Set(wearer, worn.key, false);" in flat)
    fatal = flat[flat.find("void Fatal("):flat.find("void Forget(")]
    need("only a Shaman with an Ancestral Protection totem in the water slot", "if (!IsShaman(player) || !damage) return;" in fatal
         and 'standing && RuneOf(standing) == "Ancestral Protection" ? Totems::Totem(player, Totems::WaterSlot) : nullptr;' in fatal)
    need("a death within the radius of a totem that has not saved is prevented and the Shaman healed to the floor",
         'Saves(player->GetHealth(), damage, Within(player->GetExactDist(totem), Numbers::Num(standing, "radius_yards")), already)' in fatal
         and "damage = 0; player->SetHealth(std::uint32_t(SavedHealth(player->GetHealth(), player->GetMaxHealth(), Numbers::Num(standing, \"life_floor_pct\"))));" in fatal)
    need("a totem saves once", "already = saved[player->GetGUID().GetRawValue()] == guid;" in fatal and "saved[player->GetGUID().GetRawValue()] = guid;" in fatal)
    need("the hit of a record of the skill is the sheet's", 'return row && std::string_view(row->skill) == Skill ? Numbers::Get(spellId, "damage_pct") : std::nullopt;' in flat)
    need("the immunity and the saves go with the Shaman", "saved.erase(player->GetGUID().GetRawValue());" in flat and flat.rstrip().endswith("Release(worn); } }"))
    d = flat_of(dispatch)
    need("the dispatch claims the hit", "if (auto const healingStream = HealingStream::BasePct(spellId)) return healingStream;" in d)
    need("the dispatch asks the save", "void Fatal(Player* player, std::uint32_t& damage) { HealingStream::Fatal(player, damage); }" in d)
    need("the upkeep and the logout reach the totem", "HealingStream::Upkeep(player);" in d and "HealingStream::Forget(player);" in d[d.find("void OnPlayerLogout"):])
    t = flat_of(totems)
    need("the seam hands a standing Healing Stream Totem to this file",
         'else if (std::string_view(row->skill) == "Healing Stream Totem") HealingStream::Update(player, totem, source, state, diff);' in t)
    h = flat_of(hooks)
    need("the damage hook asks the Shaman beside the other classes' saves", "DemonHunter::Fatal(player, damage); Shaman::Fatal(player, damage);" in h)
    return wrong


class Wiring(unittest.TestCase):
    def test_the_totem_heals_and_each_rune_does_its_part(self):
        self.assertEqual([], failures(FILES["dc_shaman_healing_stream_totem.cpp"], FILES["dc_shaman.cpp"], FILES["dc_shaman_totems.cpp"], HOOKS))

    def test_the_source_guards_fail_their_mutants(self):
        mutants = [
            ("cpp", "the_shaman_is_not_healed", "if (Within(player->GetExactDist(totem), radius))\n                out.push_back(player);", ""),
            ("cpp", "the_dead_are_healed_as_allies", "member->IsAlive() && member->IsInMap(player) &&", "member->IsInMap(player) &&"),
            ("cpp", "allies_from_everywhere", "Within(member->GetExactDist(totem), radius))", "true)"),
            ("cpp", "the_tide_heals_the_look_s_percent", 'PlacedHeal(ally->GetMaxHealth(), Numbers::Num(source, "heal_pct"))', 'PlacedHeal(ally->GetMaxHealth(), Numbers::Num(source, "life_regen_pct"))'),
            ("cpp", "every_rune_tides", 'if (rune == "Healing Tide")', "if (true)"),
            ("cpp", "cleansing_lasts_forever", "ImmuneUntil(Now(), Numbers::Num(source, \"duration_seconds\"))", "ImmuneUntil(Now(), 3600)"),
            ("cpp", "cleansing_gives_it_to_nobody", "ControlImmunity::Set(ally, source, true);", ""),
            ("cpp", "the_look_heals_a_flat_percent", 'TickHeal(ally->GetMaxHealth(), Numbers::Num(source, "life_regen_pct"), tick)', 'TickHeal(ally->GetMaxHealth(), Numbers::Num(source, "life_regen_pct"), 1)'),
            ("cpp", "the_spring_gives_to_anyone", "allies.front() == player", "true"),
            ("cpp", "the_spring_never_flows", 'RuneOf(source) == "Maelstrom Spring"', 'RuneOf(source) == "Nothing"'),
            ("cpp", "the_bolt_goes_to_the_first", "Combat::Strike(player, enemies[nearest], source);", "Combat::Strike(player, enemies[0], source);"),
            ("cpp", "every_rune_bolts", 'if (RuneOf(source) != "Riptide")', "if (false)"),
            ("cpp", "the_placing_is_told_every_look", "if (!state.placed)", "if (true)"),
            ("cpp", "the_tick_is_the_wrong_tunable", 'Tunable("healing_stream_tick_seconds")', 'Tunable("earthbind_tick_seconds")'),
            ("cpp", "the_immunity_never_ends", "if (Immune(found->second.untilMs, Now()) &&", "if (true ||"),
            ("cpp", "the_immunity_outlives_its_totem", "Totems::Standing(player, Totems::WaterSlot) == found->second.key", "true"),
            ("cpp", "the_immunity_is_never_taken_off", "ControlImmunity::Set(wearer, worn.key, false);", ""),
            ("cpp", "any_water_totem_saves", 'standing && RuneOf(standing) == "Ancestral Protection"', "standing"),
            ("cpp", "the_save_ignores_the_radius", "Within(player->GetExactDist(totem), Numbers::Num(standing, \"radius_yards\"))", "true"),
            ("cpp", "the_save_is_not_used_up", "saved[player->GetGUID().GetRawValue()] = guid;", ""),
            ("cpp", "the_blow_still_lands", "damage = 0;", ""),
            ("cpp", "the_floor_is_the_wrong_number", 'Numbers::Num(standing, "life_floor_pct")', 'Numbers::Num(standing, "heal_pct")'),
            ("cpp", "every_skill_claims_the_hit", "std::string_view(row->skill) == Skill ? Numbers::Get", "true ? Numbers::Get"),
            ("cpp", "the_saves_stay_after_logout", "saved.erase(player->GetGUID().GetRawValue());", ""),
            ("dispatch", "the_hit_is_not_claimed", "if (auto const healingStream = HealingStream::BasePct(spellId))", "if (false)"),
            ("dispatch", "the_save_is_not_asked", "HealingStream::Fatal(player, damage);", ""),
            ("dispatch", "no_upkeep", "HealingStream::Upkeep(player);", ""),
            ("dispatch", "the_immunity_stays_after_logout", "HealingStream::Forget(player);", ""),
            ("totems", "the_seam_does_not_update_it", "HealingStream::Update(player, totem, source, state, diff);", ""),
            ("hooks", "the_hook_does_not_ask_the_shaman", "Shaman::Fatal(player, damage);", ""),
        ]
        for which, name, old, new in mutants:
            with self.subTest(name):
                parts = {"cpp": FILES["dc_shaman_healing_stream_totem.cpp"], "dispatch": FILES["dc_shaman.cpp"], "totems": FILES["dc_shaman_totems.cpp"], "hooks": HOOKS}
                self.assertEqual(1, parts[which].count(old), name + " does not apply")
                parts[which] = parts[which].replace(old, new, 1)
                self.assertNotEqual([], failures(parts["cpp"], parts["dispatch"], parts["totems"], parts["hooks"]), name + " survived")


if __name__ == "__main__":
    unittest.main()
