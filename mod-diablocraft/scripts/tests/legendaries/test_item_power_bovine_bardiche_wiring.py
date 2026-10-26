"""The source-text guards of bovine bardiche: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_bovine_bardiche.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator
from test_item_power_bovine_bardiche import COW, OWNER, REPO, SRC, mutate, read_csv, source  # noqa: E402


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not there exactly once" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def problems(powers, summons, combat, item_powers_h, summons_h, sheet_names):
    """What the source-text guards find wrong in the server files (the C++ is compile-checked, not run, here)."""
    out = []
    fire = definition("void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,", powers)
    loop = fire.index("for (ItemPower::Fired const& one : fired)")
    at = fire.find('one.stat == "summon_herd"')
    if at < 0:
        out.append("no executor for summon_herd")
    else:
        if at < loop:
            out.append("summon_herd is done before the lock is released")
        if "lock_guard" in fire[loop:]:
            out.append("the executors take the item powers' lock")
        executor = fire[at:fire.index("\n                else", at + 1) if "\n                else" in fire[at + 1:] else len(fire)]
        if "ItemSummons::Herd(player, static_cast<unsigned>(one.value), scale);" not in executor:
            out.append("the executor does not hand the row's cows and the hit's proc coefficient to ItemSummons::Herd")
    hit = definition("void Hit(Player* player, Unit* target, std::uint32_t spellId)", powers)
    if 'Fire(player, "hit", name, scale, target);' not in hit or "double const scale = coefficient && *coefficient > 0 ? *coefficient : 0;" not in hit:
        out.append("a hit does not fire `hit` with its proc coefficient")
    if '#include "dc_item_summons.h"' not in powers or "ItemSummons::RegisterScripts();" not in definition("void RegisterScripts()", powers):
        out.append("dc_item_powers.cpp does not include the summon file or register its scripts")
    if "void Herd(Player* player, unsigned cows, double coefficient);" not in summons_h:
        out.append("dc_item_summons.h does not declare Herd")
    herd = definition("void Herd(Player* player, unsigned cows, double coefficient)", summons)
    for need, why in (('Tune("bovine_bardiche_chance_pct")', "the chance is the tunable"),
                      ('Tune("bovine_bardiche_cooldown_seconds")', "the cooldown is the tunable"),
                      ('Tune("bovine_bardiche_cow_seconds")', "the cows' time is the tunable"),
                      ('Tune("bovine_bardiche_cow_life_pct_of_owner")', "the cows' Life is the tunable"),
                      ("sObjectMgr->GetCreatureBaseStats(player->GetLevel(), info->unit_class)", "a cow's Life is the stock one at the owner's level"),
                      ("ItemSummon::HerdComes(last, now,", "the rule decides"),
                      (", coefficient,", "the hit's coefficient scales the chance"),
                      ("player->SummonCreature(Cow, player->GetPosition(), TEMPSUMMON_TIMED_DESPAWN, ms)", "the core summon on the cow's own timer"),
                      ("for (unsigned i = 0; i < cows; ++i)", "the row's number of cows"),
                      ("std::lock_guard<std::mutex> lock(mutex);", "the clock under its lock")):
        if need not in herd:
            out.append("Herd lacks %s (%s)" % (need, why))
    if "lastHerd[player->GetGUID().GetRawValue()] = now;" not in herd or "ItemSummon::HerdComes(" not in herd or \
            herd.index("lastHerd[player->GetGUID().GetRawValue()] = now;") < herd.index("ItemSummon::HerdComes("):
        out.append("the cooldown is not started only after a herd came")
    if "constexpr std::uint32_t Cow = %d;" % COW not in summons or 'constexpr char const* Bardiche = "%s";' % OWNER not in summons:
        out.append("the cow entry or the item is not the sheet's")
    swing = definition("void Swing(Creature&, Player& owner, Unit& target)", summons)
    for need in ('Shells::PowerBuffFor(Bardiche, "summon_herd")', 'Tune("bovine_bardiche_cow_damage_pct")', 'Tune("bovine_bardiche_cow_damage_delta_pct")',
                 "AttacksPerSecond(&owner)", "ComputeHit(&owner, &target, record, hit, pct)", "DealHit(&owner, &target, record, hit);", "ItemSummon::SwingPct("):
        if need not in swing:
            out.append("Swing lacks %s" % need)
    if "DC::Rifts::Ally::OnSwing(Cow, SwingMs, Swing);" not in definition("void RegisterScripts()", summons):
        out.append("the swing is not registered with World's ally")
    if 'return DC::Tunables::Has("combat", name) ? DC::Tunables::Get("combat", name) : 0.0;' not in summons:
        out.append("a blank tunable does not read 0")
    for name in re.findall(r'Tune\("(\w+)"\)', summons):
        if name not in sheet_names:
            out.append("the tunable %s is not on data/tunables/combat.csv" % name)
    load = 'if (std::uint32_t const cow = Shells::PowerBuffFor("%s", "summon_herd"))' % OWNER
    if load not in combat or "loaded[shell.spellId] = shell;" not in combat[combat.find(load):combat.find(load) + 600]:
        out.append("dc_combat.cpp does not load the cows' record as a shell, so ComputeHit refuses it")
    if "void Hit(Player*, Unit* target, std::uint32_t spellId);" not in item_powers_h:
        out.append("ItemPowers::Hit is not declared")
    return out


class Hooks(unittest.TestCase):
    powers = item_powers_source.text()
    summons = source("dc_item_summons.cpp")
    combat = source("dc_combat.cpp")
    item_powers_h = source("dc_item_powers.h")
    summons_h = source("dc_item_summons.h")
    names = {r["name"] for r in read_csv("data/tunables/combat.csv")}

    def args(self, **changed):
        base = dict(powers=self.powers, summons=self.summons, combat=self.combat, item_powers_h=self.item_powers_h, summons_h=self.summons_h,
                    sheet_names=self.names)
        base.update(changed)
        return base

    def test_the_guards_hold_on_the_source(self):
        self.assertEqual([], problems(**self.args()))

    def test_one_caller_each(self):
        self.assertEqual(["dc_item_powers_effects.cpp"], [p.name for p in SRC.rglob("*.cpp") if "ItemSummons::Herd(" in p.read_text(encoding="utf-8")])
        self.assertEqual(["dc_item_summons.cpp"], [p.name for p in SRC.rglob("*.cpp") if "Ally::OnSwing(%s" % "Cow" in p.read_text(encoding="utf-8")])

    def test_the_stat_is_in_the_generator_and_the_contracts(self):
        self.assertIn("summon_herd", generator.EFFECT_STATS)
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"\| `summon_herd` \(")
        self.assertIn("### Bovine Bardiche (`diablocraft-4p9j9`", text)
        self.assertIn("| Bovine Bardiche `%s` |" % OWNER, text)
        self.assertIn("legendary_powers_0059_table.sql", text)

    def test_the_server_mutants_fail_the_guards(self):
        p, s, c = self.powers, self.summons, self.combat
        mutants = {
            "no_executor": dict(powers=mutate(p, 'one.stat == "summon_herd"', 'one.stat == "summon_cows"')),
            "the_coefficient_dropped": dict(powers=mutate(p, "ItemSummons::Herd(player, static_cast<unsigned>(one.value), scale);", "ItemSummons::Herd(player, static_cast<unsigned>(one.value), 1.0);")),
            "one_cow": dict(powers=mutate(p, "ItemSummons::Herd(player, static_cast<unsigned>(one.value), scale);", "ItemSummons::Herd(player, 1u, scale);")),
            "the_scripts_not_registered": dict(powers=mutate(p, "        ItemSummons::RegisterScripts();\n", "")),
            "the_chance_a_literal": dict(summons=mutate(s, 'Tune("bovine_bardiche_chance_pct")', "100.0")),
            "the_chance_renamed": dict(summons=mutate(s, 'Tune("bovine_bardiche_chance_pct")', 'Tune("bovine_bardiche_proc_pct")')),
            "the_chance_not_on_the_sheet": dict(sheet_names=self.names - {"bovine_bardiche_chance_pct"}),
            "the_cooldown_a_literal": dict(summons=mutate(s, 'Tune("bovine_bardiche_cooldown_seconds")', "60.0")),
            "the_cooldown_stamped_on_every_hit": dict(summons=mutate(mutate(s, "            lastHerd[player->GetGUID().GetRawValue()] = now;\n", ""),
                                                                     "            auto const found = lastHerd.find(", "            lastHerd[player->GetGUID().GetRawValue()] = now;\n            auto const found = lastHerd.find(")),
            "the_stock_life_at_the_donors_level": dict(summons=mutate(s, "GetCreatureBaseStats(player->GetLevel(),", "GetCreatureBaseStats(info->minlevel,")),
            "the_wrong_cow": dict(summons=mutate(s, "constexpr std::uint32_t Cow = 900120;", "constexpr std::uint32_t Cow = 2442;")),
            "no_timer": dict(summons=mutate(s, "TEMPSUMMON_TIMED_DESPAWN, ms)", "TEMPSUMMON_MANUAL_DESPAWN, ms)")),
            "the_damage_not_dealt": dict(summons=mutate(s, "                DealHit(&owner, &target, record, hit);", "                ;")),
            "the_damage_a_literal": dict(summons=mutate(s, 'Tune("bovine_bardiche_cow_damage_pct")', "400.0")),
            "no_attack_speed": dict(summons=mutate(s, "AttacksPerSecond(&owner)", "1.0")),
            "the_swing_not_registered": dict(summons=mutate(s, "DC::Rifts::Ally::OnSwing(Cow, SwingMs, Swing);", "")),
            "the_record_not_loaded": dict(combat=mutate(c, 'if (std::uint32_t const cow = Shells::PowerBuffFor("%s", "summon_herd"))' % OWNER, "if (std::uint32_t const cow = 0)")),
        }
        for name, changed in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual([], problems(**self.args(**changed)), name + " survived")


if __name__ == "__main__":
    unittest.main()
