/*
 * Chain Lightning and its five runes: the jumps to more enemies, Chain Lava's burn, Chain Frost's chill and growing
 * damage, Chain Heal's Life and Thunderhead's refund. The cast is the engine's single-enemy spell for the first enemy;
 * the jumps are this file's. The Maelstrom it costs is Maelstrom's (the cost row). The dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_chain_lightning.h"
#include "dc_shaman_ascendance.h"
#include "dc_shaman_burning.h"
#include "dc_shaman_chill.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_periodic_strike.h"
#include "Unit.h"

namespace DC::Combat::Shaman::ChainLightning
{
    namespace
    {
        constexpr std::string_view Skill = "Chain Lightning";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? RuneOf(row->rune) : Rune::None;
        }

        // The record of the skill itself: the numbers a rune takes from it are stated there.
        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        double Tune(char const* name)
        {
            return Tunables::Get("combat", name);
        }

        // A strike this file starts is itself a hit of the skill and starts nothing.
        thread_local bool striking = false;
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // Chain Lava states its burn as a damage of its own beside a duration; the bolt still hits for the skill's.
        if (!Is(spellId) || !HitIsSkills(RuneAt(spellId)))
            return std::nullopt;
        return Numbers::Num(BaseId(), "damage_pct");
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (striking || !player || !target || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        // "... hits the target for {damage_pct} weapon damage as Lightning and jumps to up to {target_count} more
        // enemies within {radius_yards} yards. Each jump deals the same damage."
        double const hitPct = Numbers::Num(BaseId(), "damage_pct");
        double const radius = Numbers::Num(spellId, "radius_yards");
        std::vector<Unit*> const walk = Walk(
            target, unsigned(Numbers::Num(spellId, "target_count")) + Ascendance::ExtraChainJumps(player),
            [&](Unit* on) { return Combat::Enemies(player, spellId, on->GetPosition(), radius); },
            [](Unit* a, Unit* b) { return double(a->GetExactDist(b)); });
        std::vector<Unit*> struck{target};
        striking = true;
        for (std::size_t jump = 1; jump < walk.size(); ++jump)
        {
            // Chain Frost: "... deals {damage_bonus_pct} more damage than the one before it."
            double const pct = rune == Rune::ChainFrost
                                   ? JumpPct(hitPct, Numbers::Num(spellId, "damage_bonus_pct"), unsigned(jump))
                                   : hitPct;
            if (Combat::Strike(player, walk[jump], spellId, pct))
                struck.push_back(walk[jump]);
        }
        striking = false;
        for (Unit* enemy : struck)
            switch (rune)
            {
                case Rune::ChainLava:
                {
                    // "Enemies hit also burn for {damage_pct} weapon damage as Fire over {dot_duration_seconds}
                    // seconds."
                    double const seconds = Numbers::Num(spellId, "dot_duration_seconds");
                    Burning::Burn(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"), seconds,
                                  Tune("chain_lightning_burn_tick_seconds"));
                    break;
                }
                case Rune::ChainFrost:
                    // "Each jump Chills by {chill_pct}": every enemy the bolt hits.
                    Chill(player, enemy, Numbers::Num(spellId, "chill_pct"), Tune("chain_lightning_chill_seconds"));
                    break;
                case Rune::ChainHeal:
                    // "Each enemy hit heals you for {heal_pct} of your maximum Life."
                    Heal(player, spellId,
                         HealAmount(double(player->GetMaxHealth()), Numbers::Num(spellId, "heal_pct")));
                    break;
                default:
                    break;
            }
        if (rune == Rune::Thunderhead)
            Gain(player, spellId,
                 Refund(unsigned(struck.size()), Numbers::Num(spellId, "nearby_enemy_count"),
                        Numbers::Num(spellId, "gain_resource")));
    }
} // namespace DC::Combat::Shaman::ChainLightning
