#include "dc_barbarian_overpower.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "ScriptMgr.h"
#include "SpellScript.h"

namespace DC::Combat::Abilities::Overpower
{
    using namespace Shared;

namespace
    {
        class dc_overpower_axes final : public SpellScript
        {
            PrepareSpellScript(dc_overpower_axes);
            void Impact()
            {
                auto p = GetCaster()->ToPlayer();
                auto u = GetHitUnit();
                if (!p || !p->IsAlive() || !u || !u->IsAlive() || !p->IsInMap(u) || !p->InSamePhase(u) ||
                    !p->IsValidAttackTarget(u))
                    return;
                auto active = GetSpellInfo()->Id - 81910 + First;
                Hit hit;
                if (ComputeHit(p, u, active, hit))
                {
                    hit.areaDamage = 0;
                    DealHit(p, u, active, hit);
                }
            }
            void Register() override
            {
                AfterHit += SpellHitFn(dc_overpower_axes::Impact);
            }
        };
    }

    void OnReflect(Player* p, Unit* attacker, uint32& damage)
    {
        if (auto r = Buff(p, "Overpower"); r && Rune(*r, "Crushing Advance"))
        {
            Hit reflected;
            reflected.total = damage * Numbers::Num(r->id, "damage_share_pct") / 100;
            reflected.school = SPELL_SCHOOL_MASK_FROST;
            damage -= uint32(reflected.total);
            DealHit(p, attacker, r->id, reflected);
        }
    }

    void OnRefresh(Player* p)
    {
        if (auto r = Buff(p, "Overpower"); r && Rune(*r, "Killing Spree"))
            Add(p, AuraId(r->id), Stat::CritChance, Numbers::Num(r->id, "crit_chance_pct"));
    }

    void OnCast(Player* p, uint32 id, Row const* r, std::vector<Unit*> const& targets)
    {
        if (Rune(*r, "Killing Spree") || Rune(*r, "Crushing Advance"))
            Mark(p, p, *r, Numbers::Num(r->id, "duration_seconds"));
        if (Rune(*r, "Momentum"))
            Fury(p, Numbers::Num(r->id, "gain_resource") * targets.size());
        if (Rune(*r, "Storm of Steel"))
        {
            auto enemies = Nearby(p, p, Tune("overpower_storm_axes_radius_yards"));
            unsigned count = 0;
            for (auto u : enemies)
            {
                if (count++ >= unsigned(Numbers::Num(r->id, "max_count")))
                    break;
                p->CastSpell(u, 81910 + id - First, true);
            }
        }
    }

    void OnCritical(Player* p, uint32 spellId)
    {
        if (Procs(spellId))
            Reduce(p, "Overpower", Numbers::Num(Base("Overpower")->id, "cooldown_reduction_seconds") * 1000);
    }

    void RegisterScripts()
    {
        RegisterSpellScript(dc_overpower_axes);
    }
} // namespace DC::Combat::Abilities::Overpower
