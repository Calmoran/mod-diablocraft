#include "dc_barbarian_war_cry.h"
#include "../dc_level_heal.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>

namespace DC::Combat::Abilities::WarCry
{
    using namespace Shared;

    void OnRefresh(Player* p, std::optional<StatSheet> const& baseline, double& wrathSeconds)
    {
        if (auto r = Buff(p, "War Cry"))
        {
            auto b = Base("War Cry");
            double armor = Numbers::Num(b->id, "armor_pct");
            auto aura = p->GetAura(AuraId(r->id));
            if (Rune(*r, "Hardened Wrath") && aura->GetMaxDuration() - aura->GetDuration() < Numbers::Num(r->id, "duration_seconds") * 1000)
            {
                armor += Numbers::Num(r->id, "armor_pct");
                wrathSeconds = (Numbers::Num(r->id, "duration_seconds") * 1000 - (aura->GetMaxDuration() - aura->GetDuration())) / 1000;
            }
            Add(p, AuraId(r->id), Stat::Armor, armor, Bucket::Percent);
            if (Rune(*r, "Impunity") && baseline)
                for (unsigned e = 0; e < ElementCount; ++e)
                    Stats::AddContribution(p->GetGUID().GetRawValue(), {Source::Temporary, Stat::SingleResistance,
                                                                        uint64(AuraId(r->id)) * ElementCount + e,
                                                                        baseline->resistance[e] * Numbers::Num(r->id, "resistance_pct") / 100,
                                                                        Bucket::Flat, static_cast<Element>(e)});
            if (Rune(*r, "Invigorate"))
            {
                Add(p, AuraId(r->id), Stat::LifePercent, Numbers::Num(r->id, "max_life_pct"));
                Add(p, AuraId(r->id), Stat::LifeRegen, Classes::HealAtLevel(Numbers::Num(r->id, "heal_per_second_life"), p->GetLevel()));
            }
        }
    }

    void OnDodge(Player const* p, double& chance)
    {
        if (auto r = Buff(p, "War Cry"); r && Rune(*r, "Veteran's Warning"))
            chance += Numbers::Num(r->id, "dodge_pct");
    }

    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets)
    {
        double duration = 0;
        // Inspiring Presence is a SPELLMOD_DURATION aura now, so
        // the doubling comes back out of the core rather than out of a
        // multiplication here - the same number, through the modifier a
        // tooltip can read.
        duration = Combat::ModifiedDurationSeconds(p, id, Numbers::Num(b->id, "duration_seconds"));
        for (auto u : targets)
        {
            Mark(p, u, *r, duration);
            if (auto ally = u->ToPlayer())
                Refresh(ally);
        }
        if (Rune(*r, "Charge!"))
            Fury(p, Numbers::Num(r->id, "generated_resource") - Numbers::Num(b->id, "generated_resource"));
    }

    void OnSignature(Player* p, uint64& signature)
    {
        auto hardened = Buff(p, "War Cry");
        if (hardened && Rune(*hardened, "Hardened Wrath"))
            signature = signature * 131 + (p->GetAura(AuraId(hardened->id))->GetMaxDuration() -
                                               p->GetAura(AuraId(hardened->id))->GetDuration() <
                                           Numbers::Num(hardened->id, "duration_seconds") * 1000);
    }
} // namespace DC::Combat::Abilities::WarCry
