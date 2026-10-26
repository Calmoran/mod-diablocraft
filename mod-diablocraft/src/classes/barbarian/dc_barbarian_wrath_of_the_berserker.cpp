#include "dc_barbarian_wrath_of_the_berserker.h"
#include "../dc_level_heal.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_passives.h"

namespace DC::Combat::Abilities::Wrath
{
    using namespace Shared;

    void OnRefresh(Player* p)
    {
        if (auto r = Buff(p, "Wrath of the Berserker"))
        {
            auto b = Base("Wrath of the Berserker");
            Add(p, AuraId(r->id), Stat::CritChance, Numbers::Num(b->id, "crit_chance_pct"));
            Add(p, AuraId(r->id), Stat::AttackSpeed, Numbers::Num(b->id, "attack_speed_pct"));
            Add(p, AuraId(r->id), Stat::MovementSpeed, Numbers::Num(b->id, "movement_speed_pct"), Bucket::Uncapped);
            if (auto g = RuneRow(p, *r, "Striding Giant"))
                Add(p, AuraId(r->id), Stat::SpecificReduction, Numbers::Num(g->id, "damage_reduction_pct"));
        }
    }

    void OnMultipliers(Player* p, DC::Combat::Factors& out)
    {
        if (auto r = Buff(p, "Wrath of the Berserker"))
            if (auto g = RuneRow(p, *r, "Insanity"))
                AddFactor(out, "Insanity", Numbers::Num(g->id, "damage_bonus_pct"));
    }

    void OnDodge(Player const* p, double& chance)
    {
        if (Buff(p, "Wrath of the Berserker"))
            chance += Numbers::Num(Base("Wrath of the Berserker")->id, "dodge_pct");
    }

    void OnCast(Player* p, Row const* r, Row const* b)
    {
        Mark(p, p, *r, Numbers::Num(b->id, "duration_seconds"));
        if (auto g = RuneRow(p, *r, "Arreat's Wail"))
            Eruption(p, p, g->id, Numbers::Num(g->id, "damage_pct"), Numbers::Num(g->id, "radius_yards"));
    }

    void OnSpent(Player* p, double fury)
    {
        if (auto buff = Buff(p, "Wrath of the Berserker"))
            if (auto g = RuneRow(p, *buff, "Thrive on Chaos"))
                Heal(p, p, g->id, fury * Classes::HealAtLevel(Numbers::Num(g->id, "heal_per_hit_life"), p->GetLevel()) * Passives::FuryHealFactor(p));
    }

    void OnCritical(Player* p, Unit* target, uint32 spellId)
    {
        if (auto r = Buff(p, "Wrath of the Berserker"))
            if (auto g = RuneRow(p, *r, "Slaughter"); g && Procs(spellId))
                Eruption(p, target, g->id, Numbers::Num(g->id, "damage_pct"), Numbers::Num(g->id, "radius_yards"));
    }
} // namespace DC::Combat::Abilities::Wrath
