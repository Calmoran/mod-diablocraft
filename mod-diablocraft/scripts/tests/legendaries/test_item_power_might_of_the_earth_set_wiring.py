"""The source-text guards of might of the earth set: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_might_of_the_earth_set.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source
from test_item_power_might_of_the_earth_set import SRC  # noqa: E402


def landed_guard(powers, header):
    """ItemPowers::Landed: the landed spell's skill names the `land` event."""
    assert "void Landed(Player*, std::uint32_t spellId);" in header, "declared"
    body = powers[powers.index("void Landed(Player* player, std::uint32_t spellId)"):]
    body = body[:body.index("\n    }\n")]
    assert "Shells::FindAbility(spellId)" in body, "the skill of the spell"
    assert 'Fire(player, "land", skill->skill, 1.0)' in body, "the event, named by the skill"


def landing_guard(combat):
    """The landing's resolve, then the event, only for a completed landing of a living player still where they leapt."""
    body = combat[combat.index("void OnEffectMovementFinalized(Unit* unit, uint32, uint32 spline, bool completed) override"):]
    body = body[:body.index("\n            }\n")]
    branch = body[body.index("if (completed && player && player->IsAlive()"):]
    resolve = branch.index("ResolveCast(player, pending.shell, pending.center);")
    landed = branch.index("ItemPowers::Landed(player, pending.shell.spellId);")
    assert resolve < landed, "the landing's own damage and rune effects come first"
    block = branch[branch.index("{"):branch.index("}") + 1]
    assert "ItemPowers::Landed(player, pending.shell.spellId);" in block and "ResolveCast(" in block, "both in the completed branch"


def leap_guard(abilities):
    """Leap's landing marks Iron Impact chosen or given, its duration raised; Refresh raises its armor."""
    factor = 'ItemPowers::SkillFactor(p, "Leap", "rune_effect_pct")'
    leap = abilities[abilities.index("namespace DC::Combat::Abilities::Leap"):]
    leap = leap[:leap.index("} // namespace DC::Combat::Abilities::Leap")]
    cast = leap[leap.index("void OnCast("):leap.index("void OnHit(")]
    assert 'if (auto i = RuneRow(p, *r, "Iron Impact"))' in cast, "chosen or given"
    assert 'Mark(p, p, *i, Numbers::Num(i->id, "duration_seconds") * %s);' % factor in cast, "the duration raised"
    refresh = leap[leap.index("void OnRefresh("):leap.index("void OnCast(")]
    assert 'if (auto r = Buff(p, "Leap"); r && Rune(*r, "Iron Impact"))' in refresh
    assert 'Numbers::Num(r->id, "armor_pct") * %s, Bucket::Percent);' % factor in refresh, "the armor raised"


class Hooks(unittest.TestCase):
    def read(self, name):
        if name == "dc_abilities.cpp":
            return barbarian_source.abilities((".cpp",))
        if name == "dc_item_powers.cpp":
            return item_powers_source.text()
        return (SRC / "combat" / name).read_text(encoding="utf-8")

    def test_the_guards_hold(self):
        landed_guard(self.read("dc_item_powers.cpp"), self.read("dc_item_powers.h"))
        landing_guard(self.read("dc_combat_resolve.cpp"))
        leap_guard(barbarian_source.abilities((".cpp",)))

    def test_the_source_mutants_fail_the_guards(self):
        powers, header, combat, abilities = (self.read(n) for n in ("dc_item_powers.cpp", "dc_item_powers.h", "dc_combat_resolve.cpp", "dc_abilities.cpp"))
        landed = "                    ItemPowers::Landed(player, pending.shell.spellId); // Might of the Earth 4-piece: an Earthquake where Leap lands\n"
        mutants = {
            "not_declared": (lambda p, h, c, a: (p, h.replace("void Landed(Player*, std::uint32_t spellId);", ""), c, a)),
            "another_event": (lambda p, h, c, a: (p.replace('Fire(player, "land", skill->skill', 'Fire(player, "cast", skill->skill'), h, c, a)),
            "no_skill_named": (lambda p, h, c, a: (p.replace('Fire(player, "land", skill->skill', 'Fire(player, "land", ""'), h, c, a)),
            "never_landed": (lambda p, h, c, a: (p, h, c.replace(landed, ""), a)),
            "landed_before_the_resolve": (lambda p, h, c, a: (p, h, c.replace(landed, "").replace(
                "                {\n                    ResolveCast(player, pending.shell, pending.center);",
                "                {\n" + landed + "                    ResolveCast(player, pending.shell, pending.center);"), a)),
            "landed_on_a_failed_landing": (lambda p, h, c, a: (p, h, c.replace(landed, "").replace(
                "ResolveCast(player, pending.shell, pending.center);\n                }\n",
                "ResolveCast(player, pending.shell, pending.center);\n                }\n" + landed), a)),
            "iron_impact_chosen_only": (lambda p, h, c, a: (p, h, c, a.replace('if (auto i = RuneRow(p, *r, "Iron Impact"))', 'if (auto i = Rune(*r, "Iron Impact") ? r : nullptr)'))),
            "duration_not_raised": (lambda p, h, c, a: (p, h, c, a.replace('Numbers::Num(i->id, "duration_seconds") * ItemPowers::SkillFactor(p, "Leap", "rune_effect_pct")',
                                                                         'Numbers::Num(i->id, "duration_seconds")'))),
            "armor_not_raised": (lambda p, h, c, a: (p, h, c, a.replace('Numbers::Num(r->id, "armor_pct") * ItemPowers::SkillFactor(p, "Leap", "rune_effect_pct")',
                                                                      'Numbers::Num(r->id, "armor_pct")'))),
            "armor_raised_by_another_stat": (lambda p, h, c, a: (p, h, c, a.replace('"armor_pct") * ItemPowers::SkillFactor(p, "Leap", "rune_effect_pct")',
                                                                                  '"armor_pct") * ItemPowers::SkillFactor(p, "Leap", "damage_increase_pct")'))),
        }
        for name, mutate in mutants.items():
            with self.subTest(mutant=name):
                p, h, c, a = mutate(powers, header, combat, abilities)
                self.assertNotEqual((powers, header, combat, abilities), (p, h, c, a), name + " did not apply")
                with self.assertRaises((AssertionError, ValueError), msg=name + " survived"):
                    landed_guard(p, h)
                    landing_guard(c)
                    leap_guard(a)


if __name__ == "__main__":
    unittest.main()
