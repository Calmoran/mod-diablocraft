"""The source-text guards of k4: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_k4.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source
import generate_legendary_powers as generator
from test_item_power_k4 import SRC, wrath_runes  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.abilities = barbarian_source.abilities((".cpp",))
        cls.passives = (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8")

    def test_every_rune_effect_of_the_two_skills_reads_its_rune_through_one_lookup(self):
        # the effect is read from the rune's own row, found by RuneRow: the chosen rune's or the one a power gives
        for rune in wrath_runes():
            self.assertEqual(1, len(re.findall(r'RuneRow\(p, \*\w+, "%s"\)' % re.escape(rune), self.abilities)), rune)
            self.assertNotRegex(self.abilities, r'Rune\(\*\w+, "%s"\)' % re.escape(rune))
        self.assertEqual(1, len(re.findall(r'RuneRow\(p,\*row,"Dust Devils"\)', self.abilities)))
        self.assertNotRegex(self.abilities, r'Rune\(\*row,\s*"Dust Devils"\)')
        lookup = self.abilities[self.abilities.index("Row const* RuneRow("):self.abilities.index("Row const* Active(")]
        self.assertIn("if (Rune(active, rune))\n                return &active;", lookup)       # a chosen rune counts once
        self.assertIn("ItemPowers::GrantsRune(p, active.skill, rune)", lookup)
        self.assertIn("Rune(r, rune)", lookup)                                                  # the rune's own row, with its numbers

    def test_a_granted_rune_deals_and_heals_under_its_own_row(self):
        for text in ('Eruption(p, p, g->id, Numbers::Num(g->id, "damage_pct"), Numbers::Num(g->id, "radius_yards"))',
                     'Eruption(p, target, g->id, Numbers::Num(g->id, "damage_pct"), Numbers::Num(g->id, "radius_yards"))',
                     'Heal(p, p, g->id, fury * Classes::HealAtLevel(Numbers::Num(g->id, "heal_per_hit_life"), p->GetLevel())',
                     'AddFactor(out, "Insanity", Numbers::Num(g->id, "damage_bonus_pct"))',
                     'Stat::SpecificReduction, Numbers::Num(g->id, "damage_reduction_pct")'):
            self.assertIn(text, self.abilities)
        self.assertIn('Numbers::Num(devils->id, "damage_pct")/(hit.skill*100)', self.abilities)
        self.assertIn("s.devils.push_back({p->GetPosition(),p->GetOrientation(),0,devils->id,hit,{}});", self.abilities)

    def test_the_hit_event_carries_the_target_and_the_apply_effect_has_its_executor(self):
        self.assertIn("ItemPowers::Hit(p, target, spellId);", self.passives)
        hit = self.powers[self.powers.index("void Hit(Player* player, Unit* target, std::uint32_t spellId)"):self.powers.index("void Taken(Player* player)")]
        self.assertIn('Fire(player, "hit", name, scale, target);', hit)
        self.assertIn('Data().events.count("hit")', hit)
        for stat in generator.EFFECT_STATS:
            self.assertIn('one.stat == "%s"' % stat, self.powers)
        self.assertIn('else if (one.stat == "apply_skill" && target)\n                    Abilities::ApplySkillBleed(player, target, one.skill.c_str());', self.powers)
        applied = self.abilities[self.abilities.index("void ApplySkillBleed("):self.abilities.index("bool CutRunningCooldown(")]
        self.assertIn("auto r = Active(p, skill);\n        if (!r)\n            r = Base(skill);", applied)       # the bar's rune, else the skill's own
        self.assertIn("Combat::ApplySkillBleed(p, target, r->id)", applied)
        self.assertIn("HitEffects(p, target, r->id);", applied)                                  # Mutilate's mark, as a Rend hit leaves it
        self.assertLess(applied.index("Combat::ApplySkillBleed"), applied.index("HitEffects("))   # and only when the bleed was applied

    def test_a_running_bleed_is_kept_by_an_applied_one_and_stacks_follow_the_cap(self):
        rend = barbarian_source.named("dc_barbarian_rend.cpp")
        apply = " ".join(rend[rend.index("bool Apply("):rend.index("std::optional<bool> OnResolve(")].split())
        self.assertIn('ItemPowers::SkillSetTo(player, "Rend", "dot_max_stacks", 1)', apply)
        self.assertIn("if (keepRunning && running >= cap) return false;", apply)
        self.assertIn("if (cap > 1)", apply)
        self.assertIn('bleed->AddStack(player, cap)', apply)
        self.assertLess(apply.index("AddStack"), apply.index("RemoveAurasDueToSpell"))          # a stack before a replacement
        self.assertIn("Abilities::Bleed(player, target, shell->spellId, shell->skill, true)", self.combat)   # the public path keeps the running bleed
        self.assertIn("HitEffects(player, target, spellId); return Apply(player, target, spellId, skill);", " ".join(rend.split()))   # a cast replaces

    def test_the_bleed_carries_its_stacks_and_each_has_its_own_snapshot(self):
        rend = barbarian_source.named("dc_barbarian_rend.cpp")
        bleed = rend[rend.index("class dc_rend_bleed"):rend.index("class RendPeriodicProvider")]
        self.assertIn("std::vector<ItemPower::BleedStack> stacks;", bleed)
        self.assertIn("stacks = {Fresh(caster->ToPlayer(), snapshot, 0)};", bleed)              # the first, on the real apply
        self.assertIn("ItemPower::AddStack(stacks, Fresh(player, fresh, effect->GetTickNumber()), cap);", bleed)
        self.assertIn('ItemPowers::SkillLowest(player, "Rend", "dot_payout_seconds", length)', bleed)
        self.assertIn("ItemPower::BleedEnd(stacks)", bleed)
        self.assertIn("tick.total = ItemPower::BleedDamage(stacks, number);", bleed)
        self.assertEqual(1, bleed.count("Fit(aura);") + bleed.count("Fit(GetAura());") - 1)       # the real apply and AddStack
        self.assertIn("(mode & AURA_EFFECT_HANDLE_REAL)", bleed)

    def test_mutilates_mark_lasts_as_long_as_the_bleed_pays(self):
        self.assertIn('ItemPowers::SkillLowest(p, "Rend", "dot_payout_seconds",', self.abilities)

    def test_the_vocabulary_has_a_reader_for_each_new_stat(self):
        for stat in ("dot_max_stacks", "dot_payout_seconds"):
            self.assertIn(stat, generator.SKILL_STATS)
            self.assertIn('"%s"' % stat, self.combat + barbarian_source.named("dc_barbarian_rend.cpp"))
        self.assertIn("rune", generator.KINDS)
        self.assertIn("GrantsRune", self.abilities)


if __name__ == "__main__":
    unittest.main()
