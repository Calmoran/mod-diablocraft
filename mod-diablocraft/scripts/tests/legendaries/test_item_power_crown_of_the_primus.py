"""Crown of the Primus (diablocraft-bl9iz, legendary rest bead 023): "Slow Time gains the effect of every rune except Point of No Return and
permanently follows you."

  * data/legendary_powers.csv gains its five rows: four `rune` rows on Slow Time (every rune of the sheet but Point of No Return, read from
    wizard_runes.csv, not listed here) and the `skill` row `follow_caster` 1. The words are read from d3planner's data.json;
  * the generator refuses a `follow_caster` that is not value 1, simply on, on Slow Time;
  * generate_spells.py makes one follow record per Slow Time record (83365-83370): the bubble's two enemy effects as the stock enemy area aura
    at the bubble's radius, Stretch Time's ally effect as the stock party area aura, infinite, bound to dc_wizard_slow, named after the record
    it belongs to. The records are checked in data/generated; a mutated record fails the same check;
  * source-text guards on dc_wizard.cpp (they prove the calls are there, not that they run; the C++ is compile-checked by syntax_check.sh and the
    in-game steps are in docs/test-diablocraft-bl9iz.md): the cast follows (an aura on the Wizard, the old one removed, no bubble) only when
    `follow_caster` reads 1; Time Warp, Exhaustion and Stretch Time are read from the follow aura through its caster's given runes; the slow
    and the cooldown are Time Shell's whichever rune is chosen; the aura ends when the hat is off, on a map change and on a logout. Each guard
    has a mutant that must fail it.
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import test_item_power_math as power_math  # noqa: E402  (a module, so its test classes are not run twice)
import test_wizard_aura_binding as binding  # noqa: E402
from test_item_power_math import generator, read_csv  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
CROWN = "P74_Unique_WizardHat_104"
WORDS = "Slow Time gains the effect of every rune except Point of No Return and permanently follows you."
FOLLOWS = ["Slow Time", "Slow Time - Time Warp", "Slow Time - Point of No Return", "Slow Time - Time Shell", "Slow Time - Exhaustion",
           "Slow Time - Stretch Time"]
ENEMY_AREA, PARTY_AREA, SLOW, MELEE_SLOW = 129, 35, 33, 193


def helper_ids():
    return {r["identity"]: int(r["spell_id"]) for r in read_csv("data/generated/spell_helper_ids.csv")}


def problems(records, ids, scripted):
    """What is wrong with the follow records: the check every mutant of the records must fail."""
    bad = []
    bubble = records[ids["Slow Time - bubble"]]
    infinite = records[ids["Wizard - Frozen"]]["DurationIndex"]
    for record_name in FOLLOWS:
        name = record_name + " - follow"
        if name not in ids:
            bad.append("%s has no record" % name)
            continue
        record = records[ids[name]]
        want = ((ENEMY_AREA, SLOW), (ENEMY_AREA, MELEE_SLOW), (PARTY_AREA, MELEE_SLOW))
        for slot, (effect, aura) in enumerate(want, 1):
            if (int(record["Effect_%d" % slot]), int(record["EffectAura_%d" % slot])) != (effect, aura):
                bad.append("%s slot %d is not %d/%d" % (name, slot, effect, aura))
            if record["EffectRadiusIndex_%d" % slot] != bubble["EffectRadiusIndex_1"]:
                bad.append("%s slot %d is not the bubble's radius" % (name, slot))
            if record["ImplicitTargetA_%d" % slot] != "1" or record["ImplicitTargetB_%d" % slot] != "0":
                bad.append("%s slot %d does not start at the caster" % (name, slot))
        if record["DurationIndex"] != infinite:
            bad.append("%s is not infinite" % name)
        if ids[name] not in scripted:
            bad.append("%s is not bound to dc_wizard_slow" % name)
    return bad


class Table(unittest.TestCase):
    def test_the_rows_are_the_sources(self):
        data = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))
        item = next(i for i in data["items"] if i.get("name") == "Crown of the Primus" and WORDS in json.dumps(i))
        self.assertEqual(WORDS, item["required"]["custom"]["format"])
        ours = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == CROWN]
        # every rune of Slow Time but the one the words name; the sheet is the source of the names
        runes = {r["rune_name"] for r in read_csv("data/d3/wizard_runes.csv") if r["skill_name"] == "Slow Time"}
        self.assertIn("Point of No Return", runes)
        given = {r["stat"] for r in ours if r["kind"] == "rune"}
        self.assertEqual(runes - {"Point of No Return"}, given)
        self.assertEqual(4, len([r for r in ours if r["kind"] == "rune"]))
        for r in ours:
            self.assertEqual(("", "1", "1", "", "", "", ""), (r["pieces"], r["value_min"], r["value_max"], r["cond"], r["cond_arg"], r["fire_on"],
                                                           r["icd_seconds"]), r)
            self.assertEqual("Slow Time", r["skill"])
        self.assertEqual(1, len([r for r in ours if r["kind"] == "skill" and r["stat"] == "follow_caster"]))
        self.assertEqual(5, len(ours))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == CROWN)
        self.assertEqual(("Crown of the Primus", "yes", "wizard"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))

    def test_the_generator_refuses_a_follow_it_cannot_read(self):
        row = {"owner": CROWN, "pieces": "", "kind": "skill", "skill": "Slow Time", "stat": "follow_caster", "value_min": "1", "value_max": "1",
               "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "",
               "chance_pct": "", "icd_seconds": "", "source": "x", "note": ""}
        bad = {
            "another skill": dict(row, skill="Teleport"),
            "a list of skills": dict(row, skill="Slow Time;Teleport"),
            "a two": dict(row, value_min="2", value_max="2"),
            "a range": dict(row, value_max="2"),
            "zero": dict(row, value_min="0", value_max="0"),
            "from zero": dict(row, value_min="0"),
            "from a half": dict(row, value_min="0.5"),
            "a set's": dict(row, owner="Wrath of the Wastes", pieces="6"),
            "a condition, no event": dict(row, cond="triggered", cond_arg="5"),
            "under a condition": dict(row, cond="triggered", cond_arg="5", fire_on="cast"),
            "fired by an event": dict(row, fire_on="cast"),
        }
        for name, one in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([one])
        self.assertEqual(1, len(power_math.Table.rows_of([row])))
        self.assertIn("follow_caster", generator.SKILL_STATS)
        # the rune rows need no new rule: a rune that is not on the sheet is refused as it always was
        with self.assertRaises(ValueError):
            power_math.Table.rows_of([dict(row, kind="rune", stat="Time Stop")])
        self.assertEqual(1, len(power_math.Table.rows_of([dict(row, kind="rune", stat="Time Shell")])))


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        cls.records, cls.scripts = binding.rows(sql), binding.scripted(sql)
        cls.ids = helper_ids()
        cls.slow = set(cls.scripts["dc_wizard_slow"])
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        cls.header = header

    def test_the_six_follow_records_are_what_the_generator_means(self):
        self.assertEqual([], problems(self.records, self.ids, self.slow))
        self.assertEqual(6, len([n for n in self.ids if n.endswith(" - follow")]))

    def test_every_follow_is_owned_by_its_record_in_the_shells_header(self):
        for record in FOLLOWS:
            shell = re.search(r'\{(\d+), "%s", \d+\},' % re.escape(record + " - bubble"), self.header)[0]
            owner = re.search(r'\{(\d+), "%s", (\d+)\}' % re.escape(record + " - follow"), self.header)
            self.assertTrue(owner, record)
            self.assertEqual(int(re.search(r', (\d+)\}', shell)[1]), int(owner[2]), record)
            self.assertEqual(self.ids[record + " - follow"], int(owner[1]))

    def test_the_stretch_ally_hook_binds_to_every_follow(self):
        # the follow records carry an effect in the third slot, so the ally hooks (registered when the record has one) bind
        ally = [sid for sid in self.slow if binding.matches(self.records[sid], binding.SPELL_AURA_ANY, 2)]
        for record in FOLLOWS:
            self.assertIn(self.ids[record + " - follow"], ally)
        self.assertEqual([], binding.mismatches(self.records, self.slow, binding.slow_hooks(True)))

    def test_the_mutants_of_the_records_fail_the_check(self):
        ids, slow = self.ids, self.slow
        follow = lambda: dict(self.records[ids["Slow Time - Time Shell - follow"]])  # noqa: E731
        mutants = {}
        for name, change in {
            "the_slow_is_not_an_area_aura": {"Effect_1": "6"},
            "the_ally_effect_is_an_enemy_one": {"Effect_3": str(ENEMY_AREA)},
            "the_attack_slow_is_lost": {"EffectAura_2": "0"},
            "the_ally_slow_is_lost": {"EffectAura_3": "0"},
            "the_radius_is_not_the_bubbles": {"EffectRadiusIndex_1": "0"},
            "the_ally_radius_is_not_the_bubbles": {"EffectRadiusIndex_3": "0"},
            "a_duration_that_ends": {"DurationIndex": "1"},
            "not_from_the_caster": {"ImplicitTargetA_2": "6"},
        }.items():
            records = dict(self.records)
            records[ids["Slow Time - Time Shell - follow"]] = dict(follow(), **change)
            mutants[name] = (records, ids, slow)
        mutants["not_scripted"] = (self.records, ids, slow - {ids["Slow Time - Time Shell - follow"]})
        mutants["one_missing"] = (self.records, {n: i for n, i in ids.items() if n != "Slow Time - Exhaustion - follow"}, slow)
        for name, args in mutants.items():
            self.assertNotEqual([], problems(*args), "mutant %s passed" % name)


def guards(text):
    """What is wrong with the Wizard's Crown of the Primus code: every mutant of the source must fail one of these."""
    bad = []

    def has(label, snippet, in_text=text):
        if snippet not in in_text:
            bad.append(label)

    def part(start, end):
        i = text.find(start)
        j = text.find(end, i + len(start)) if i >= 0 else -1
        return text[i:j] if i >= 0 and j >= 0 else ""

    has("the cast goes to Slow Time's file", 'if (IsSkill(id, "Slow Time"))\n            SlowTime::Cast(player, id, center);')
    cast = part("void Cast(Player* player, uint32 id, Position const& center)", "void RegisterScripts()")
    has("the cast reads follow_caster", 'bool const follows = ItemPowers::SkillSetTo(player, "Slow Time", "follow_caster", 0) > 0;', cast)
    has("a recast replaces the aura", "if (follows)\n            RemoveFollow(player);", cast)
    has("the follow is cast on the Wizard", "if (follows)\n                    player->CastSpell(player, helper.id, true);", cast)
    has("the bubble only without the hat", "helper.owner == id && IsFollow(helper) == follows", cast)
    has("the bubble still falls at the target", "player->CastSpell(center.GetPositionX(), center.GetPositionY(), center.GetPositionZ()", cast)
    has("Time Shell's cooldown is given", 'ItemPowers::GrantsRune(player, "Slow Time", "Time Shell")', cast)
    has("not when Time Shell is the rune", '!IsRune(id, "Time Shell")', cast)
    has("the cooldown is Time Shell's own", 'Numbers::Own(shell, "cooldown_seconds")', cast)
    has("with the Wizard's reduction", "SendSkillCooldown(player, id, ReducedCooldownMilliseconds(player, id, ms));", cast)

    given = part("bool GivenFollow(Unit const* unit, char const* rune)", "// The record of one of Slow Time's runes")
    has("a follow aura only", "if (IsFollow(helper))", given)
    has("by its caster", "aura->GetCaster()", given)
    has("whose items give the rune", 'ItemPowers::GrantsRune(caster->ToPlayer(), "Slow Time", rune)', given)
    has("the follow is a name", 'ends_with(" - follow")', part("bool IsFollow(", "bool Following("))

    has("Time Warp reads the follow", '(warp && target->HasAura(warp)) || SlowTime::GivenFollow(target, "Time Warp")')
    has("Exhaustion reads the follow", '(exhaustion && attacker->HasAura(exhaustion)) || SlowTime::GivenFollow(attacker, "Exhaustion")')
    has("Stretch Time reads the follow, before the lock", 'bool const stretching = SlowTime::GivenFollow(player, "Stretch Time");\n        std::lock_guard<std::recursive_mutex> guard(mutex);')
    has("and gives the allies' attack speed", "if ((stretch && player->HasAura(stretch)) || stretching)")

    slow = part("case SPELL_AURA_MOD_DECREASE_SPEED:", "case SPELL_AURA_MELEE_SLOW:")
    has("the slow is Time Shell's when it is given", 'ItemPowers::GrantsRune(caster->ToPlayer(), "Slow Time", "Time Shell")', slow)
    has("from the Time Shell record", 'SlowTimeRune("Time Shell")', slow)
    has("and the rune on the bar otherwise", "uint32 slow = owner;", slow)
    has("point of no return's stun is the chosen rune's", 'IsRune(owner, "Point of No Return")')

    update = part("// Crown of the Primus: Slow Time follows only while the hat is worn.", "Passive::Evocation(player);")
    has("the hat off takes the aura off", 'if (SlowTime::Following(player) && ItemPowers::SkillSetTo(player, "Slow Time", "follow_caster", 0) <= 0)\n                    SlowTime::RemoveFollow(player);', update)
    logout = part("void OnPlayerLogout(Player* player) override", "void OnPlayerMapChanged")
    has("a logout takes it off", "SlowTime::RemoveFollow(player);", logout)
    changed = part("void OnPlayerMapChanged(Player* player) override", "private:")
    has("a map change takes it off", "SlowTime::RemoveFollow(player);", changed)
    return bad


class Source(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = wizard_source.CPP.read_text(encoding="utf-8")

    def test_the_code_is_there(self):
        self.assertEqual([], guards(self.text))

    def test_the_remover_takes_off_every_follow_record_and_nothing_else(self):
        remove = self.text[self.text.index("void RemoveFollow(Player* player)"):]
        remove = remove[:remove.index("// Whether `unit` stands")]
        self.assertIn("if (IsFollow(helper))\n                player->RemoveAurasDueToSpell(helper.id);", remove)

    def test_the_mutants_fail_a_guard(self):
        real = self.text
        mutants = {
            "the_cast_is_not_sent": ('if (IsSkill(id, "Slow Time"))\n            SlowTime::Cast(player, id, center);', 'if (IsSkill(id, "Slow Time"))\n            ;'),
            "the_cast_ignores_the_hat": ('bool const follows = ItemPowers::SkillSetTo(player, "Slow Time", "follow_caster", 0) > 0;', "bool const follows = true;"),
            "no_replacement": ("if (follows)\n            RemoveFollow(player);", ""),
            "the_bubble_too": ("helper.owner == id && IsFollow(helper) == follows", "helper.owner == id"),
            "follow_cast_at_the_target": ("player->CastSpell(player, helper.id, true);", "player->CastSpell(center.GetPositionX(), center.GetPositionY(), center.GetPositionZ(), helper.id, true);"),
            "no_time_shell_cooldown": ("ItemPowers::GrantsRune(player, \"Slow Time\", \"Time Shell\"))\n            if (uint32 const ms", "false)\n            if (uint32 const ms"),
            "time_shell_recut": ('!IsRune(id, "Time Shell") &&', ""),
            "an_unreduced_cooldown": ("ReducedCooldownMilliseconds(player, id, ms)", "ms"),
            "time_warp_not_read": (' || SlowTime::GivenFollow(target, "Time Warp")', ""),
            "exhaustion_not_read": (' || SlowTime::GivenFollow(attacker, "Exhaustion")', ""),
            "stretch_not_read": ("|| stretching)", ")"),
            "stretch_read_in_the_lock": ("        bool const stretching = SlowTime::GivenFollow(player, \"Stretch Time\");\n        std::lock_guard<std::recursive_mutex> guard(mutex);",
                                         "        std::lock_guard<std::recursive_mutex> guard(mutex);\n        bool const stretching = SlowTime::GivenFollow(player, \"Stretch Time\");"),
            "any_aura_gives_the_runes": ('ItemPowers::GrantsRune(caster->ToPlayer(), "Slow Time", rune)', "true"),
            "any_aura_is_a_follow": ("if (IsFollow(helper))\n                    if (Aura const* aura", "if (true)\n                    if (Aura const* aura"),
            "the_slow_stays_the_runes": ('ItemPowers::GrantsRune(caster->ToPlayer(), "Slow Time", "Time Shell")', "false"),
            "the_hat_off_keeps_it": ('ItemPowers::SkillSetTo(player, "Slow Time", "follow_caster", 0) <= 0)', "false)"),
            "a_logout_keeps_it": ("            void OnPlayerLogout(Player* player) override\n            {\n                SlowTime::RemoveFollow(player);\n", "            void OnPlayerLogout(Player* player) override\n            {\n"),
            "a_map_change_keeps_it": ("            void OnPlayerMapChanged(Player* player) override\n            {\n                SlowTime::RemoveFollow(player);\n", "            void OnPlayerMapChanged(Player* player) override\n            {\n"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies" % name)
            self.assertNotEqual([], guards(real.replace(old, new)), "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
