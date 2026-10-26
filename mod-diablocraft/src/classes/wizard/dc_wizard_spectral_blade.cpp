#include "dc_wizard_spectral_blade.h"
#include "SpellAuras.h"
#include <algorithm>
#include <cmath>

namespace DC::Combat::Wizard::SpectralBlade
{
    using namespace Shared;

    void Begin(Player* player, std::uint32_t spellId)
    {
        // Barrier Blades: "With each cast, gain a protective shield for
        // {absorb_duration_seconds} seconds that absorbs
        // {absorb_capacity_life_pct} of your Life in damage". A cast's effect,
        // not a hit's, so it is given here, where every committed cast passes.
        // It was given in Cast, which dc_ability_targets::Finish does not call
        // for a projectile record, and this rune's record keeps its donor
        // Arcane Barrage's speed: the shield never went on.
        // The core refreshes this caster's own aura on a recast and Apply sets
        // the full time again, so a recast is one fresh shield, never two.
        if (IsRune(spellId, "Barrier Blades"))
            Shield(player, "Spectral Blade - Barrier Blades - shield", Num(spellId, "absorb_capacity_life_pct"),
                   Num(spellId, "absorb_duration_seconds"));
    }

    // Spectral Blade - Flame Blades: "Each enemy hit increases the damage of your Fire spells by
    // {damage_bonus_pct}, up to a maximum of {max_bonus_pct}, for {bonus_duration_seconds} seconds". The bonus is
    // the aura "Flame Blades" the Wizard wears, one stack for each enemy hit, so what the buff shows is what the
    // damage uses (ElementalBonus reads it back). Each hit's stack has its own clock, as in d3planner's simulator
    // (wizard.js:98, refresh: false, maxstacks 30): the oldest goes first when the stacks are full, and the aura's
    // own time is the newest stack's, so a hit puts it back to the full time while the count falls as the older
    // hits run out (SyncFlameBlades, every update). Diablocraft-o2be.
    void FlameBlade(Player* player, uint32 id)
    {
        uint32 const buff = Shells::HelperFor("Flame Blades");
        double const perHit = Num(id, "damage_bonus_pct");
        if (!buff || perHit <= 0)
            return;
        double const seconds = Num(id, "bonus_duration_seconds");
        std::size_t const most = std::size_t(std::lround(Num(id, "max_bonus_pct") / perHit));
        std::size_t count = 0;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            uint64 const now = Now();
            std::vector<uint64>& stacks = StateOf(player).flameBlades;
            // No aura: it was cancelled, and the hits it counted went with it.
            if (!player->HasAura(buff))
                stacks.clear();
            std::erase_if(stacks, [now](uint64 until) { return until <= now; });
            stacks.push_back(now + uint64(seconds * 1000));
            if (stacks.size() > most)
                stacks.erase(stacks.begin());
            count = stacks.size();
        }
        if (Aura* aura = Apply(player, player, "Flame Blades", seconds))
            aura->SetStackAmount(uint8(count));
    }

    void SyncFlameBlades(Player* player)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        std::vector<uint64>& stacks = StateOf(player).flameBlades;
        if (stacks.empty())
            return;
        uint64 const now = Now();
        std::erase_if(stacks, [now](uint64 until) { return until <= now; });
        uint32 const buff = Shells::HelperFor("Flame Blades");
        Aura* aura = player->GetAura(buff);
        if (aura && !stacks.empty())
            aura->SetStackAmount(uint8(stacks.size()));
        else
        {
            // The last stack ran out, or the buff was cancelled: neither leaves a bonus.
            stacks.clear();
            player->RemoveAurasDueToSpell(buff);
        }
    }

    void IceBlades(Player* player, Unit* target, uint32 id)
    {
        // Spectral Blade - Ice Blades: "Chilled enemies have a
        // {proc_chance_pct} chance to be Frozen": an enemy chilled before
        // this hit may freeze for 60 frames, then every hit chills it for 36
        // (wizard.js:107-110).
        if (Chilled(player, target) && Roll() < Num(id, "proc_chance_pct"))
            Freeze(player, target, Num(id, "freeze_duration_seconds"));
        Chill(player, target, Num(id, "chill_duration_seconds"));
    }

    void FlameBladesBonus(Player* player, double& bonus)
    {
        // Flame Blades: the stacks of the buff the Wizard wears, one rune's per-stack bonus up to its cap.
        uint32 const buff = Shells::HelperFor("Flame Blades");
        Aura const* aura = buff ? player->GetAura(buff) : nullptr;
        for (Row const& row : Shells::Abilities)
            if (aura && IsSkill(row.id, "Spectral Blade") && IsRune(row.id, "Flame Blades"))
                bonus += std::min(aura->GetStackAmount() * Num(row.id, "damage_bonus_pct"),
                                  Num(row.id, "max_bonus_pct"));
    }
} // namespace DC::Combat::Wizard::SpectralBlade
