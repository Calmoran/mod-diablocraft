"""Legendary rest, bead diablocraft-5kkgd: Ranslor's Folly (wizard bracers, list row 68, K4), and the piece it builds, N-LESSER.

  "The damage of Energy Twister is increased by [225-300]% and it periodically pulls in lesser enemies within 30 yards."
  * the words and the range are d3planner's (item_wrists.js:514-523, P61_Unique_Bracer_108_x1: custom leg_ranslorsfolly_p6, min 225 max 300); the numbers are the power file's, read through
    decode_pow.py (Item_Power_Passive P61_ItemPassive_Unique_Ring_018.pow: the item's own number 2.25-3; SF_0 'Tickrate' = 2, SF_1 'Radius' = 30, SF_2 'Per Target ICD' = 6). The table
    (data/legendary_powers.csv) holds FOUR `skill` rows for the bracers on Energy Twister: `damage_increase_pct` [225-300] (rolled once per item) and the three fixed
    `twister_pull_yards` 30, `twister_pull_seconds` 2 and `twister_pull_target_cooldown_seconds` 6;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the three pull stats only as an item's one
    fixed number above 0, simply on, for Energy Twister, with the other two beside them;
  * the production rules (src/combat/dc_item_power_math.h: IsLesser, LesserPull, SkillSetTo) are compiled and driven with the generated rows: a lesser enemy is a monster that is neither an elite nor a
    boss; the pull takes it only within 30 yards of the twister (the end inclusive) and not within 6 seconds of its last pull (the end inclusive, right across the clock's wrap); the twister reads the
    numbers only while the bracers are worn; mutants of the rows and the rules fail the same driver;
  * source-text guards that the twister's start reads the three numbers and schedules the pull ticks (the first as it appears, like the damage tick), that a pull walks the enemies around where the path
    puts the twister, judges each by the rule over the wearer's per-target stamps, and draws the ones taken to the twister after the loop; and that Combat::IsLesser is the elite and boss tests the
    loot and the damage formula use. The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-5kkgd.md.
  * Wicked Wind (the rune whose twister stays in place on the generic ground area) is pulled from the cast point by EnergyTwister::Stay (diablocraft-1kyw7), on the ground's life.
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
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
TWISTER = SRC / "classes/wizard/dc_wizard_energy_twister.cpp"
COMBAT = SRC / "combat/dc_combat.cpp"
RESOLVE = SRC / "combat/dc_combat_resolve.cpp"
INTERNAL = SRC / "classes/wizard/dc_wizard_internal.h"
WIZARD = SRC / "classes/wizard/dc_wizard.cpp"
HARNESS = MODULE / "tests/item_power_ranslors_folly/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P61_Unique_Bracer_108_x1"
SKILL = "Energy Twister"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
PULL = {"twister_pull_yards": 30.0, "twister_pull_seconds": 2.0, "twister_pull_target_cooldown_seconds": 6.0}
YARDS, COOLDOWN = 30.0, 6.0


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_225_to_300_and_a_pull_of_lesser_enemies_within_30_yards(self):
        text = (REPO / "reference/d3planner/item_wrists.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('format: "The damage of Energy Twister is increased by %d%% and it periodically pulls in lesser enemies within 30 yards.", min: 225, max: 300', item)
        self.assertIn("pulls in lesser enemies within 30 yards", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda *a: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), *a], capture_output=True, text=True).stdout  # noqa: E731
        power = run("power", "P61_ItemPassive_Unique_Ring_018")
        for label, number in (("Tickrate", "2"), ("Radius", "30"), ("Per Target ICD", "6")):
            self.assertRegex(power, r"'%s' = %s\b" % (label, number))
        self.assertIn("P61_ItemPassive_Unique_Ring_018.pow: 2.25-3", run("item", OWNER))

    def test_four_rows_for_the_bracers(self):
        expected = [(OWNER, 0, "skill", SKILL, "damage_increase_pct", 225.0, 300.0, *BLANK)]
        expected += [(OWNER, 0, "skill", SKILL, stat, number, number, *BLANK) for stat, number in sorted(PULL.items())]
        self.assertEqual(expected, sorted(mine(), key=lambda r: (r[4] != "damage_increase_pct", r[4])))

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0067_table.sql")


class WickedWind(unittest.TestCase):
    """Wicked Wind's twister is the generic ground area (the engine's damage over time at a point), not a wandering one; Ranslor's pull reaches it from the cast point."""

    def test_the_rune_is_the_generic_ground(self):
        targeting = {r["skill"]: r for r in read_csv("data/d3/skill_targeting.csv")}
        self.assertEqual("ground_area", targeting[SKILL]["target_type"])
        values = {(r["skill"], r["rune"], r["token"]): r["value"] for r in read_csv("data/d3/wizard_skill_values.csv")}
        self.assertEqual("0.5", values[(SKILL, "", "interval_seconds")])
        self.assertEqual("6", values[(SKILL, "Wicked Wind", "dot_duration_seconds")])
        resolve = re.sub(r"\s+", " ", RESOLVE.read_text(encoding="utf-8"))
        self.assertIn('return shell.targeting.Destination() && Numbers::Has(id, "interval_seconds") && Numbers::Has(id, "dot_duration_seconds");', resolve)
        twister = re.sub(r"\s+", " ", TWISTER.read_text(encoding="utf-8"))
        self.assertIn('return IsSkill(id, "Energy Twister") && !IsRune(id, "Wicked Wind");', twister)

    def test_a_wicked_wind_cast_with_the_item_pulls_and_without_it_does_not(self):
        """The pull of a stationary twister is scheduled only for yards above 0, which only the worn bracers give (SkillSetTo from a base of 0)."""
        twister = re.sub(r"\s+", " ", TWISTER.read_text(encoding="utf-8"))
        stay = twister[twister.find("void Stay("):twister.find("void Start(")]
        self.assertIn('double const yards = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_yards", 0);', stay)
        self.assertIn("std::size_t const pulls = yards > 0 ?", stay)
        with (MODULE / "data/legendary_powers.csv").open(encoding="utf-8", newline="") as stream:
            owners = {r["owner"] for r in csv.DictReader(stream) if r["stat"] == "twister_pull_yards"}
        self.assertEqual({OWNER}, owners)


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": "damage_increase_pct", "value_min": "225", "value_max": "300", "cond": "", "cond_arg": "",
            "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, edits=None, drop=()):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="ranslor-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            added = [dict(self.BASE)]
            for stat, number in PULL.items():
                if stat not in drop:
                    added.append({**self.BASE, "stat": stat, "value_min": g(number), "value_max": g(number), **((edits or {}).get(stat, {}))})
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + added)
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(4, len([r for r in self.render_with() if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {}
        for stat in PULL:
            refused.update({
                stat + " a range": dict(edits={stat: {"value_max": "99"}}),
                stat + " none": dict(edits={stat: {"value_min": "0", "value_max": "0"}}),
                stat + " a condition": dict(edits={stat: {"cond": "triggered", "cond_arg": "5"}}),
                stat + " an event": dict(edits={stat: {"fire_on": "cast", "fire_skills": SKILL}}),
                stat + " a set level": dict(edits={stat: {"pieces": "2"}}),
                stat + " another skill": dict(edits={stat: {"skill": "Teleport"}}),
                stat + " alone": dict(drop=tuple(s for s in PULL if s != stat)),
            })
        for name, kw in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(**kw)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        for other in ("dc_item_proc_math.h", "dc_proc_math.h"):
            files["combat/" + other] = (SRC / "combat" / other).read_text(encoding="utf-8")
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemranslor-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the power file's numbers, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = clear + [(T("wears", OWNER), None)]
        # the numbers the twister reads: only while the bracers are worn, only for Energy Twister, the highest of the sources over the twister's own 0
        for stat, number in PULL.items():
            out += wear + [(T("setto", SKILL, stat, 0), g(number)), (T("setto", "Teleport", stat, 0), "0"), (T("setto", SKILL, "damage_pct", 0), "0")]
            out += clear + [(T("setto", SKILL, stat, 0), "0")]
            out += clear + [(T("wears", "Other Bracers"), None), (T("setto", SKILL, stat, 0), "0")]
        # a lesser enemy: a monster that is neither an elite nor a boss
        for monster, elite, boss, want in ((1, 0, 0, 1), (1, 1, 0, 0), (1, 0, 1, 0), (1, 1, 1, 0), (0, 0, 0, 0), (0, 1, 0, 0)):
            out.append((T("lesser", monster, elite, boss), str(want)))
        cool = int(COOLDOWN * 1000)
        # reach: within 30 yards of the twister, the end inclusive; nothing past it, behind it or with no reach
        for distance, yards, want in ((0, 30, 1), (10, 30, 1), (29.99, 30, 1), (30, 30, 1), (30.01, 30, 0), (100, 30, 0), (-1, 30, 0), (10, 0, 0), (10, -5, 0)):
            out.append((T("pull", 1, distance, yards, 100000, 0, 0, COOLDOWN), str(want)))
        # a boss or an elite is not pulled, however near
        out += [(T("pull", 0, 5, 30, 100000, 0, 0, COOLDOWN), "0"), (T("pull", 0, 5, 30, 200000, 1, 100000, COOLDOWN), "0")]
        # the per-target clock: nothing before 6 seconds, the end inclusive; none before the first pull
        for now, want in ((100000, 0), (100001, 0), (100000 + cool - 1, 0), (100000 + cool, 1), (200000, 1)):
            out.append((T("pull", 1, 10, 30, now, 1, 100000, COOLDOWN), str(want)))
        # across the clock's wrap (a uint32 of ms): a pull just below 2^32 is 796 ms old at now 500, and 6 seconds old at 5704
        for now, last, want in ((500, 4294967000, 0), (5703, 4294967000, 0), (5704, 4294967000, 1), (20000, 4294967000, 1), (99999, 100000, 1)):
            out.append((T("pull", 1, 10, 30, now, 1, last, COOLDOWN), str(want)))
        out.append((T("pull", 1, 10, 30, 100000, 0, 99999999, COOLDOWN), "1"))
        out.append((T("pull", 1, 10, 30, 100000, 0, 100000, COOLDOWN), "1"))   # no pull yet: a stamp that happens to be now is nothing
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(4, len(rows))
        want, _ = self.drive(real, rows, "want")
        by_stat = {r[4]: r for r in rows}
        row_mutants = {
            "twenty_yards": [r if r[4] != "twister_pull_yards" else r[:5] + (20.0, 20.0) + r[7:] for r in rows],
            "five_second_clock": [r if r[4] != "twister_pull_target_cooldown_seconds" else r[:5] + (5.0, 5.0) + r[7:] for r in rows],
            "no_yards_row": [r for r in rows if r[4] != "twister_pull_yards"],
            "another_skill": [r[:3] + ("Teleport",) + r[4:] for r in rows],
            "no_rows": [],
        }
        self.assertEqual(set(PULL), set(by_stat) - {"damage_increase_pct"})
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        for name, (old, new) in {
            "an_elite_is_lesser": ("return monster && !elite && !boss;", "return monster && !boss;"),
            "a_boss_is_lesser": ("return monster && !elite && !boss;", "return monster && !elite;"),
            "a_non_monster_is_lesser": ("return monster && !elite && !boss;", "return !elite && !boss;"),
            "everyone_is_pulled": ("return lesser && DragReady(", "return DragReady("),
            "nobody_is_pulled": ("return lesser && DragReady(", "return false && DragReady("),
            "no_per_target_clock": ("return lesser && DragReady(distance, yards, now, pulled, last, cooldownSeconds);", "return lesser && DragReady(distance, yards, now, false, last, cooldownSeconds);"),
            "reach_end_is_exclusive": ("distance < 0 || distance > yards", "distance < 0 || distance >= yards"),
            "no_reach_limit": ("distance < 0 || distance > yards", "distance < 0"),
            "cooldown_end_is_exclusive": ("(now - last) >= static_cast<std::uint32_t>(std::max(0.0, cooldownSeconds)", "(now - last) > static_cast<std::uint32_t>(std::max(0.0, cooldownSeconds)"),
            "the_wrap_blocks_the_pull": ("return (now - last) >= static_cast<std::uint32_t>", "return now >= last && (now - last) >= static_cast<std::uint32_t>"),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def twister_failures(twister, combat, internal, wizard=""):
    """What is wrong with the twister's pull ([] when it is right)."""
    flat = re.sub(r"\s+", " ", twister)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    start = flat.find("void PullAt(Player* player, uint32 id, Position const& at, double yards, double cooldown) {")
    end = flat.find("// The pull of a twister that wanders", start)
    body = flat[start:end] if start >= 0 and end > start else ""
    need("the pull exists", bool(body))
    wander = flat[flat.find("void TwisterPull(Player* player, unsigned serial, double t, double yards, double cooldown) {"):flat.find("} // namespace", start)]
    need("a twister that is gone pulls nothing", "LiveTwister const* twister = TwisterOf(player, serial); if (!twister) return;" in wander)
    need("the pull is at where the path puts the twister now", "at = TwisterGround(player, *twister, Twister::At(twister->path, twister->turnSeconds, twister->lifeSeconds, t));" in wander)
    need("a wandering twister pulls through the shared rule", "PullAt(player, id, at, yards, cooldown);" in wander)
    need("a dead wearer pulls nothing", "if (!player->IsAlive()) return;" in body)
    need("the enemies are those around the twister, within the item's yards", "for (Unit* enemy : Combat::Enemies(player, id, at, yards))" in body)
    need("each is judged by the rule over the wearer's stamps, lesser, from the twister",
         "ItemPower::LesserPull(Combat::IsLesser(enemy), enemy->GetExactDist(&at), yards, now, last != stamps.end(), last != stamps.end() ? last->second : 0, cooldown)" in body)
    need("the stamps are the wearer's own, under the lock", "std::lock_guard<std::recursive_mutex> guard(mutex); auto& stamps = StateOf(player).twisterPulled;" in body)
    need("a pulled enemy is stamped and the old stamps dropped",
         "std::erase_if(stamps, [now, cooldown](auto const& stamp) { return now - stamp.second >= cooldown * 1000.0; }); stamps[guid] = now; pulled.push_back(enemy);" in body)
    need("an enemy the rule refuses is skipped before it is stamped", body.find("continue;") < body.find("stamps[guid] = now;"))
    need("the taken are drawn to the twister after the loop", "for (Unit* enemy : pulled) Combat::Abilities::Pull(enemy, at);" in body)
    need("the movement header is included", '#include "../../combat/dc_movement_effects.h"' in twister)
    begin = flat.find("void Start(Player* player, uint32 id, Position const& center) {")
    start_body = flat[begin:]
    for stat in ("twister_pull_yards", "twister_pull_seconds", "twister_pull_target_cooldown_seconds"):
        need("Start reads %s" % stat, 'double const pull%s = ItemPowers::SkillSetTo(player, "Energy Twister", "%s", 0);' % ({"twister_pull_yards": "Yards", "twister_pull_seconds": "Every", "twister_pull_target_cooldown_seconds": "Cooldown"}[stat], stat) in start_body)
    need("no yards, no pulls; the pull ticks are the twister's life over the item's seconds",
         "std::size_t const pulls = pullYards > 0 ? Twister::Ticks(life, pullEvery) : 0;" in start_body)
    need("each pull tick is scheduled at its own offset, the first at once",
         "for (std::size_t k = 0; k < pulls; ++k) After(player, k * pullEvery, [serial, t = k * pullEvery, pullYards, pullCooldown](Player* p) { TwisterPull(p, serial, t, pullYards, pullCooldown); });" in start_body)
    need("the twister is registered before its pull is scheduled", start_body.find("state.twisters.push_back(std::move(twister));") < start_body.find("TwisterPull(p, serial"))
    # Wicked Wind's twister stays on the generic ground: the same numbers, the same rule, from the cast point, for the ground's life
    stay = flat[flat.find("void Stay(Player* player, uint32 id, Position const& center) {"):flat.find("void Start(Player* player, uint32 id, Position const& center) {")]
    need("Stay exists", "void Stay(" in stay)
    for stat, name in (("twister_pull_yards", "yards"), ("twister_pull_seconds", "every"), ("twister_pull_target_cooldown_seconds", "cooldown")):
        need("Stay reads %s" % stat, 'double const %s = ItemPowers::SkillSetTo(player, "Energy Twister", "%s", 0);' % (name, stat) in stay)
    need("no yards, no pulls; the ground's life over the item's seconds",
         'std::size_t const pulls = yards > 0 ? Twister::Ticks(Num(id, "dot_duration_seconds"), every) : 0;' in stay)
    need("each pull is scheduled at its own offset from the cast point, the first at once",
         "for (std::size_t k = 0; k < pulls; ++k) After(player, k * every, [id, center, yards, cooldown](Player* p) { PullAt(p, id, center, yards, cooldown); });" in stay)
    if wizard:
        wflat = re.sub(r"\s+", " ", wizard)
        need("a cast of an Energy Twister rune that does not wander stays where it was aimed",
             'if (EnergyTwister::Wanders(id)) EnergyTwister::Start(player, id, center); else if (IsSkill(id, "Energy Twister")) EnergyTwister::Stay(player, id, center);' in wflat)
    cflat = re.sub(r"\s+", " ", combat)
    need("Combat::IsLesser is a monster that is not IsElite and not a boss (world, dungeon, Rift Guardian)",
         "bool IsLesser(Unit const* unit) { Creature const* creature = unit ? unit->ToCreature() : nullptr; return ItemPower::IsLesser(creature != nullptr, IsElite(unit), "
         "creature && (creature->isWorldBoss() || creature->IsDungeonBoss() || DC::Rifts::IsGuardianEntry(creature->GetEntry()))); }" in cflat)
    need("the player's state keeps the per-target stamps", "std::unordered_map<uint64, std::uint32_t> twisterPulled;" in internal)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_twister_pull(self):
        self.assertEqual([], twister_failures(TWISTER.read_text(encoding="utf-8"), COMBAT.read_text(encoding="utf-8"), INTERNAL.read_text(encoding="utf-8"),
                                              WIZARD.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        twister = TWISTER.read_text(encoding="utf-8")
        combat = COMBAT.read_text(encoding="utf-8")
        internal = INTERNAL.read_text(encoding="utf-8")
        wizard = WIZARD.read_text(encoding="utf-8")
        mutants = {
            "a_gone_twister_pulls": ("if (!twister)\n                    return;\n                id = twister->id;", "id = twister ? twister->id : 0;"),
            "a_dead_wearer_pulls": ("            if (!player->IsAlive())\n                return;\n            std::vector<Unit*> pulled;", "            std::vector<Unit*> pulled;"),
            "pulled_from_the_wearer": ("Combat::Enemies(player, id, at, yards)", "Combat::Enemies(player, id, player->GetPosition(), yards)"),
            "everyone_is_pulled": ("Combat::IsLesser(enemy), enemy->GetExactDist(&at)", "true, enemy->GetExactDist(&at)"),
            "reach_from_the_wearer": ("enemy->GetExactDist(&at)", "enemy->GetExactDist(player)"),
            "no_clock": ("last != stamps.end() ? last->second : 0, cooldown))", "0, cooldown))"),
            "stamps_are_not_kept": ("                stamps[guid] = now;\n", ""),
            "stamps_are_a_locals": ("auto& stamps = StateOf(player).twisterPulled;", "std::unordered_map<std::uint64_t, std::uint32_t> stamps;"),
            "not_dropped": ("                std::erase_if(stamps, [now, cooldown](auto const& stamp) { return now - stamp.second >= cooldown * 1000.0; });\n", ""),
            "pulled_to_the_wearer": ("Combat::Abilities::Pull(enemy, at);", "Combat::Abilities::Pull(enemy, player->GetPosition());"),
            "never_pulled": ("            for (Unit* enemy : pulled)\n                Combat::Abilities::Pull(enemy, at);\n", ""),
            "no_include": ('#include "../../combat/dc_movement_effects.h"\n', ""),
            "yards_not_read": ('pullYards = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_yards", 0);', 'pullYards = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_yard", 0);'),
            "seconds_not_read": ('pullEvery = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_seconds", 0);', 'pullEvery = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_second", 0);'),
            "cooldown_not_read": ('pullCooldown = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_target_cooldown_seconds", 0);', 'pullCooldown = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_cooldown", 0);'),
            "pulls_without_yards": ("pullYards > 0 ? Twister::Ticks(life, pullEvery) : 0;", "Twister::Ticks(life, pullEvery);"),
            "the_first_pull_waits": ("After(player, k * pullEvery,", "After(player, (k + 1) * pullEvery,"),
            "a_wandering_twister_pulls_its_own_way": ("            PullAt(player, id, at, yards, cooldown);\n", ""),
            "stay_yards_not_read": ('double const yards = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_yards", 0);', 'double const yards = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_yard", 0);'),
            "stay_seconds_not_read": ('double const every = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_seconds", 0);', 'double const every = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_second", 0);'),
            "stay_cooldown_not_read": ('double const cooldown = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_target_cooldown_seconds", 0);', 'double const cooldown = ItemPowers::SkillSetTo(player, "Energy Twister", "twister_pull_cooldown", 0);'),
            "stay_pulls_without_the_item": ('yards > 0 ? Twister::Ticks(Num(id, "dot_duration_seconds"), every) : 0;', 'Twister::Ticks(Num(id, "dot_duration_seconds"), every);'),
            "stay_pulls_for_no_life": ('Twister::Ticks(Num(id, "dot_duration_seconds"), every)', 'Twister::Ticks(Num(id, "interval_seconds"), every)'),
            "stay_waits_for_the_first": ("After(player, k * every,", "After(player, (k + 1) * every,"),
            "stay_pulls_from_the_wearer": ("[id, center, yards, cooldown](Player* p) { PullAt(p, id, center, yards, cooldown); }", "[id, yards, cooldown](Player* p) { PullAt(p, id, p->GetPosition(), yards, cooldown); }"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, twister.count(old), name + " does not apply")
                self.assertNotEqual([], twister_failures(twister.replace(old, new, 1), combat, internal, wizard), name + " survived")
        for name, (old, new) in {
            "an_elite_is_lesser": ("IsElite(unit),", "false,"),
            "a_boss_is_lesser": ("creature->isWorldBoss() || creature->IsDungeonBoss() ||\n                                                DC::Rifts::IsGuardianEntry(creature->GetEntry())", "creature->isWorldBoss()"),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, combat.count(old), name + " does not apply")
                self.assertNotEqual([], twister_failures(twister, combat.replace(old, new, 1), internal, wizard), name + " survived")
        old = "std::unordered_map<uint64, std::uint32_t> twisterPulled;"
        self.assertNotEqual([], twister_failures(twister, combat, internal.replace(old, "", 1), wizard))
        for name, (old, new) in {
            "wicked_wind_is_not_stayed": ("        else if (IsSkill(id, \"Energy Twister\"))\n            EnergyTwister::Stay(player, id, center);\n", ""),
            "every_twister_stays": ("        if (EnergyTwister::Wanders(id))\n            EnergyTwister::Start(player, id, center);\n        else if", "        if (false)\n            EnergyTwister::Start(player, id, center);\n        else if"),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, wizard.count(old), name + " does not apply")
                self.assertNotEqual([], twister_failures(twister, combat, internal, wizard.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
