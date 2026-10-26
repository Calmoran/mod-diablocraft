"""The source-text guards of Fire Walkers: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_fire_walkers.py, which a .cpp edit then does not re-run.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402
from test_item_power_fire_walkers import GENERATED, MODULE, OWNER, REPO, SRC, STAT, TUNABLES, definition, mutate, read_csv, source  # noqa: E402


def problems(powers, trail, trail_h, combat, sheet_names):
    """What the source-text guards find wrong in the server files (the C++ is compile-checked, not run, here)."""
    out = []
    fire = definition("void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,", powers)
    loop = fire.index("for (ItemPower::Fired const& one : fired)")
    at = fire.find('one.stat == "burn_trail"')
    if at < 0:
        out.append("no executor for burn_trail")
    else:
        if at < loop:
            out.append("burn_trail is done before the lock is released")
        if "lock_guard" in fire[loop:]:
            out.append("the executors take the item powers' lock")
        executor = fire[at:fire.index("\n                else", at + 1) if "\n                else" in fire[at + 1:] else len(fire)]
        if "ItemTrail::Burn(player, one.row->owner, one.value, one.row->icdSeconds);" not in executor:
            out.append("the executor does not hand the item, its rolled damage and the clock's period to ItemTrail::Burn")
    if '#include "dc_item_trail.h"' not in powers:
        out.append("dc_item_powers.cpp does not include the trail file")
    logout = definition("void OnPlayerLogout(Player* player) override", powers)
    if "ItemTrail::Clear(player->GetGUID().GetRawValue());" not in logout:
        out.append("a logout does not clear the wearer's patches")
    if "void Burn(Player* player, std::string const& owner, double perSecondPct, double periodSeconds);" not in trail_h or "void Clear(std::uint64_t guid);" not in trail_h:
        out.append("dc_item_trail.h does not declare Burn and Clear")
    burn = definition("void Burn(Player* player, std::string const& owner, double perSecondPct, double periodSeconds)", trail)
    for need, why in (("player->IsAlive()", "the dead drop and burn nothing"),
                      ('Tune("fire_walkers_radius_yards")', "the reach is the sheet's"),
                      ('Tune("fire_walkers_patch_seconds")', "the patch's time is the sheet's"),
                      ("player->isMoving()", "a patch drops only while the wearer moves"),
                      ("Drop(trail.patches, now, patchMs,", "the rule drops the patch"),
                      ("PulseSeconds(trail.last, now, periodSeconds)", "the pulse pays the time since the last"),
                      ("trail.last = now;", "the pulse clock moves on"),
                      ("PulsePct(perSecondPct, seconds)", "the damage is the item's per second for those seconds"),
                      ('Shells::PowerBuffFor(owner.c_str(), "burn_trail")', "the fire is dealt under the item's hit record"),
                      ("Reach(patches, now,", "one search of the trail's reach"),
                      ("Enemies(player, record, player->GetPosition(), reach)", "the enemies of the wearer's reach"),
                      ("Burns(patches, now,", "each enemy burns once, only within a live patch"),
                      ("ComputeHit(player, enemy, record, hit, pct, true)", "a damage-over-time tick at the pulse's percent"),
                      ("DealHit(player, enemy, record, hit);", "the core's damage log"),
                      ("enemy->IsAlive()", "a dead enemy takes no fire")):
        if need not in burn:
            out.append("Burn lacks %s (%s)" % (need, why))
    if "Strike(" in burn or "Passives::Hit" in burn or "Connected(" in burn:
        out.append("Burn goes through Strike, Passives::Hit or Connected, so the fire would proc (its proc coefficient is 0)")
    if "lock_guard" in burn[burn.index("ComputeHit"):]:
        out.append("the fire is dealt under the trail's lock")
    if 'return DC::Tunables::Has("combat", name) ? DC::Tunables::Get("combat", name) : 0.0;' not in trail:
        out.append("a blank tunable does not read 0")
    for name in re.findall(r'Tune\("(fire_walkers_\w+)"\)', trail):
        if name not in sheet_names:
            out.append("the tunable %s is not on data/tunables/combat.csv" % name)
    load = 'Shells::PowerBuffFor("%s", "%s")' % (OWNER, STAT)
    if load not in combat or "loaded[shell.spellId] = shell;" not in combat[combat.find(load):combat.find(load) + 600]:
        out.append("dc_combat.cpp does not load the fire's record as a shell, so ComputeHit refuses it")
    return out


class Hooks(unittest.TestCase):
    powers = item_powers_source.text()
    trail = source("dc_item_trail.cpp")
    trail_h = source("dc_item_trail.h")
    combat = source("dc_combat.cpp")
    names = {r["name"] for r in read_csv(MODULE / "data/tunables/combat.csv")}

    def args(self, **changed):
        base = dict(powers=self.powers, trail=self.trail, trail_h=self.trail_h, combat=self.combat, sheet_names=self.names)
        base.update(changed)
        return base

    def test_the_guards_hold_on_the_source(self):
        self.assertEqual([], problems(**self.args()))

    def test_one_caller(self):
        self.assertEqual(["dc_item_powers_effects.cpp"], [p.name for p in SRC.rglob("*.cpp") if "ItemTrail::Burn(" in p.read_text(encoding="utf-8")])

    def test_the_trail_names_both_tunables_it_reads(self):
        self.assertEqual(set(TUNABLES), set(re.findall(r'Tune\("(fire_walkers_\w+)"\)', self.trail)))

    def test_the_stat_is_in_the_generator_and_the_contract(self):
        self.assertIn(STAT, generator.EFFECT_STATS)
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"\| `burn_trail` \(")
        self.assertIn("### Fire Walkers (`diablocraft-4na3e`", text)
        self.assertIn(GENERATED.name, text)

    def test_the_server_mutants_fail_the_guards(self):
        p, s, c = self.powers, self.trail, self.combat
        mutants = {
            "no_executor": dict(powers=mutate(p, 'one.stat == "burn_trail"', 'one.stat == "fire_trail"')),
            "the_item_dropped": dict(powers=mutate(p, "ItemTrail::Burn(player, one.row->owner, one.value, one.row->icdSeconds);", "ItemTrail::Burn(player, \"\", one.value, one.row->icdSeconds);")),
            "the_period_dropped": dict(powers=mutate(p, "ItemTrail::Burn(player, one.row->owner, one.value, one.row->icdSeconds);", "ItemTrail::Burn(player, one.row->owner, one.value, 1.0);")),
            "the_damage_dropped": dict(powers=mutate(p, "ItemTrail::Burn(player, one.row->owner, one.value, one.row->icdSeconds);", "ItemTrail::Burn(player, one.row->owner, 100.0, one.row->icdSeconds);")),
            "the_include_dropped": dict(powers=mutate(p, '#include "dc_item_trail.h"\n', "")),
            "no_clear_on_logout": dict(powers=mutate(p, "ItemTrail::Clear(player->GetGUID().GetRawValue());", ";")),
            "the_radius_a_literal": dict(trail=mutate(s, 'Tune("fire_walkers_radius_yards")', "5.0")),
            "the_radius_renamed": dict(trail=mutate(s, 'Tune("fire_walkers_radius_yards")', 'Tune("fire_walkers_radius")')),
            "the_patch_time_not_on_the_sheet": dict(sheet_names=self.names - {"fire_walkers_patch_seconds"}),
            "the_patch_time_a_literal": dict(trail=mutate(s, 'Tune("fire_walkers_patch_seconds") * 1000.0', "1500.0")),
            "drops_while_still": dict(trail=mutate(s, "player->isMoving()", "true")),
            "the_dead_burn": dict(trail=mutate(s, "if (!player || !player->IsAlive())", "if (!player)")),
            "the_rule_not_asked": dict(trail=mutate(s, "PulsePct(perSecondPct, seconds)", "perSecondPct")),
            "the_pulse_clock_stuck": dict(trail=mutate(s, "trail.last = now;", ";")),
            "any_enemy_burns": dict(trail=mutate(s, "!Burns(patches, now,", "!Burn(patches, now,")),
            "the_fire_proccing": dict(trail=mutate(s, "ComputeHit(player, enemy, record, hit, pct, true)", "Strike(player, enemy, record, pct)")),
            "not_periodic": dict(trail=mutate(s, "ComputeHit(player, enemy, record, hit, pct, true)", "ComputeHit(player, enemy, record, hit, pct)")),
            "the_damage_not_dealt": dict(trail=mutate(s, "DealHit(player, enemy, record, hit);", ";")),
            "a_dead_enemy_takes_fire": dict(trail=mutate(s, "!enemy->IsAlive() || ", "")),
            "no_reach": dict(trail=mutate(s, "Enemies(player, record, player->GetPosition(), reach)", "Enemies(player, record, player->GetPosition(), 5.0)")),
            "a_blank_tunable_reads_more": dict(trail=mutate(s, "DC::Tunables::Get(\"combat\", name) : 0.0;", "DC::Tunables::Get(\"combat\", name) : 1.0;")),
            "the_record_not_loaded": dict(combat=mutate(c, 'Shells::PowerBuffFor("%s", "%s")' % (OWNER, STAT), "0")),
        }
        for name, changed in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual([], problems(**self.args(**changed)), name + " survived")


if __name__ == "__main__":
    unittest.main()
