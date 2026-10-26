#include "dc_barbarian_furious_charge.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_combat.h"

namespace DC::Combat::Abilities::FuriousCharge
{
    using namespace Shared;

    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets, State& s)
    {
        if (s.charge.count)
            --s.charge.count;
        if (s.charge.left <= 0)
            // The recharge is the record's now - CategoryRecoveryTime, read
            // back by name - and cooldown reduction reaches it the way it
            // reaches a cooldown: through the core's own SPELLMOD_COOLDOWN
            // modifiers, not a factor the module works out (as
            // D3's fixCooldown, which scales a recharge and a cooldown with
            // the same function: skilldata.js:636-642).
            s.charge.left = s.charge.period = ReducedCooldownMilliseconds(
                p, b->id, uint32(std::lround(Numbers::Num(b->id, "charge_recharge_seconds") * 1000)));
        if (Rune(*r, "Stamina"))
            Fury(p, Numbers::Num(r->id, "generated_resource") * targets.size());
        if (Rune(*r, "Cold Rush"))
            for (auto u : targets)
                Control(p, u, *r, Numbers::Num(r->id, "freeze_duration_seconds"));
        for (auto u : targets)
            Knock(p, u, Tune("fury_charge_knockback_yards"));
        if (Rune(*r, "Merciless Assault"))
            s.charge.left = std::max(0.0, s.charge.left - std::min(Numbers::Num(r->id, "duration_seconds"), Numbers::Num(r->id, "charge_recharge_reduction_seconds") * targets.size()) * 1000);
        SendSkillCooldown(p, id, s.charge.count ? 0 : uint32(std::ceil(s.charge.left)));
    }

    void OnUpdate(Player* p, State& s, uint32 diff)
    {
        auto recharge = Recharger(diff);
        auto r = Active(p, "Furious Charge");
        auto chargeCount = s.charge.count;
        recharge(s.charge,
                 r && Rune(*r, "Dreadnought") ? unsigned(Numbers::Num(r->id, "charge_count")) : unsigned(Numbers::Num(Base("Furious Charge")->id, "charge_count")));
        if (r && s.charge.count != chargeCount)
            SendSkillCooldown(p, r->id, s.charge.count ? 0 : uint32(std::ceil(s.charge.left)));
    }
} // namespace DC::Combat::Abilities::FuriousCharge
