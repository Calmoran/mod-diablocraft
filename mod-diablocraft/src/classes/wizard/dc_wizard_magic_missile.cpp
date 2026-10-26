#include "dc_wizard_magic_missile.h"
#include "SpellAuras.h"

namespace DC::Combat::Wizard::MagicMissile
{
    using namespace Shared;

    void RefreshBurn(Player* player, Unit* target)
    {
        // Conflagrate: "any Fire damage taken from your other spells refresh
        // all stacks to their maximum duration".
        if (uint32 burn = Shells::HelperFor("Magic Missile - Conflagrate - burn"))
            if (Aura* aura = target->GetAura(burn, player->GetGUID()))
                aura->RefreshDuration();
    }

    void BurnTick(Player* player, uint32 id, double seconds, Unit* target, uint8 stacks)
    {
        // One tick of the burn: damage_pct x stacks over the
        // ticks in dot_duration_seconds (wizard.js:40, 1.3 x
        // stacks / 12 at 15 frames over 180).
        uint32 const source = GroundSource(id);
        double const total = Num(source, "dot_duration_seconds");
        if (target && target->IsAlive() && total > 0)
            Combat::Strike(player, target, source,
                           Num(source, "damage_pct") * stacks * seconds / total, true);
    }
} // namespace DC::Combat::Wizard::MagicMissile

namespace DC::Combat::Wizard
{
    using namespace Shared;

    bool Afflict(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || !IsRune(spellId, "Conflagrate"))
            return false;
        // "causes them to burn for {damage_pct} weapon damage as Fire over
        // {dot_duration_seconds} seconds. Burn damage stacks up to
        // {max_stacks_count} times": the stock stacking aura (a new stack
        // refreshes the duration), ticked in dc_wizard_buff.
        if (uint32 burn = Shells::HelperFor("Magic Missile - Conflagrate - burn"); burn && target->IsAlive())
            player->AddAura(burn, target);
        return true;
    }
} // namespace DC::Combat::Wizard
