#include "dc_barbarian_ignore_pain.h"
#include "../dc_level_heal.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_passives.h"

namespace DC::Combat::Abilities::IgnorePain
{
    using namespace Shared;

    void OnRefresh(Player* p)
    {
        if (auto r = Buff(p, "Ignore Pain"))
        {
            auto b = Base("Ignore Pain");
            Add(p, AuraId(r->id), Stat::SpecificReduction,
                Rune(*r, "Mob Rule") && p->GetAura(AuraId(r->id))->GetCasterGUID() != p->GetGUID() ? Numbers::Num(r->id, "damage_reduction_pct")
                                                                                                   : Numbers::Num(b->id, "damage_reduction_pct"));
            if (Rune(*r, "Bravado"))
                Add(p, AuraId(r->id), Stat::MovementSpeed, Numbers::Num(r->id, "movement_speed_pct"), Bucket::Uncapped);
        }
    }

    void OnCast(Player* p, uint32 id, Row const* r, Row const* b)
    {
        double duration = 0;
        duration = Rune(*r, "Iron Hide") ? Numbers::Num(r->id, "duration_seconds") : Numbers::Num(b->id, "duration_seconds");
        duration = ItemPowers::DurationSeconds(p, "Ignore Pain", duration); // N-DUR: Pride of Cassius
        Mark(p, p, *r, duration);
        // The control immunity is on the marker's record (aura 147 and 77, the PURGES attribute): applying the
        // marker refuses new holds and strips the ones already on (aura review row 5).
        if (Rune(*r, "Contempt for Weakness"))
            Heal(p, p, id, p->GetMaxHealth() * Numbers::Num(r->id, "heal_pct") / 100);
        if (Rune(*r, "Mob Rule"))
            for (auto u : Nearby(p, p, Numbers::Num(r->id, "radius_yards"), true))
                if (u != p)
                {
                    Mark(p, u, *r, ItemPowers::DurationSeconds(p, "Ignore Pain", Numbers::Num(r->id, "duration_seconds")));
                    if (auto ally = u->ToPlayer())
                        Refresh(ally);
                }
    }

    void OnSpent(Player* p, double fury)
    {
        if (auto buff = Buff(p, "Ignore Pain"); buff && Rune(*buff, "Ignorance is Bliss"))
            Heal(p, p, buff->id, fury * Classes::HealAtLevel(Numbers::Num(buff->id, "heal_per_hit_life"), p->GetLevel()) * Passives::FuryHealFactor(p));
    }
} // namespace DC::Combat::Abilities::IgnorePain
