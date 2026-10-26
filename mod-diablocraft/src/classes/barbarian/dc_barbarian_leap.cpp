#include "dc_barbarian_leap.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_item_powers.h"

namespace DC::Combat::Abilities::Leap
{
    using namespace Shared;

    void OnRefresh(Player* p)
    {
        // Might of the Earth 4-piece: the Iron Impact rune's effect raised by the set's rune_effect_pct (1 with none).
        if (auto r = Buff(p, "Leap"); r && Rune(*r, "Iron Impact"))
            Add(p, AuraId(r->id), Stat::Armor,
                Numbers::Num(r->id, "armor_pct") * ItemPowers::SkillFactor(p, "Leap", "rune_effect_pct"), Bucket::Percent);
    }

    void OnCast(Player* p, Row const* r, std::vector<Unit*> const& targets)
    {
        // Might of the Earth 4-piece: Iron Impact given without choosing it, its duration raised by the set's rune_effect_pct.
        if (auto i = RuneRow(p, *r, "Iron Impact"))
            Mark(p, p, *i, Numbers::Num(i->id, "duration_seconds") * ItemPowers::SkillFactor(p, "Leap", "rune_effect_pct"));
        if (Rune(*r, "Call of Arreat"))
            for (auto u : targets)
                Pull(u, p->GetPosition());
        if (Rune(*r, "Toppling Impact"))
            for (auto u : targets)
                Knock(p, u, Tune("leap_toppling_knockback_yards"));
    }

    void OnHit(Player* p, Unit* target, Row const* r, Row const* b)
    {
        Control(p, target, *r, Numbers::Num(b->id, "slow_duration_seconds"));
    }

    void OnLaunch(Player* p, uint32 id)
    {
        auto r = Shells::FindAbility(id);
        if (!r || std::string(r->skill) != "Leap" || !Rune(*r, "Launch"))
            return;
        for (auto u : Nearby(p, p, Numbers::Num(r->id, "radius_yards")))
        {
            Hit h;
            if (ComputeHit(p, u, id, h))
            {
                h.areaDamage = 0;
                DealHit(p, u, id, h);
                Control(p, u, *r, Numbers::Num(r->id, "slow_duration_seconds"));
            }
        }
    }
} // namespace DC::Combat::Abilities::Leap
