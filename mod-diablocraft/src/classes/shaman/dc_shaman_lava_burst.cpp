/*
 * Lava Burst and its five runes: the flat bonus against a Burning enemy, a free cast Lava Surge gave, Path of Flames'
 * spread, Pyroclasm's eruption, Obsidian Burst's knock down, Steam Burst's freeze and Volcanic Lightning's strikes. The
 * cast is the engine's single-enemy spell and its Maelstrom cost the core's; the dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_lava_burst.h"
#include "dc_shaman_burning.h"
#include "dc_shaman_chill.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "dc_shaman_free_lava_burst.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_periodic_strike.h"
#include "Random.h"
#include "Unit.h"

#include <vector>

namespace DC::Combat::Shaman::LavaBurst
{
    namespace
    {
        constexpr std::string_view Skill = "Lava Burst";

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

        // A strike this file starts is itself a hit of the skill and starts nothing.
        thread_local bool striking = false;

        void Strikes(Player* player, Unit* target, std::uint32_t spellId, double pct)
        {
            striking = true;
            Combat::Strike(player, target, spellId, pct);
            striking = false;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // Every rune but Obsidian Burst states a damage of its own that is not the lava's hit, and Obsidian Burst a
        // duration beside its own: the loader would give a record of either no hit.
        if (!Is(spellId))
            return std::nullopt;
        return HitIsRunes(RuneAt(spellId)) ? Numbers::Num(spellId, "damage_pct") : Numbers::Num(BaseId(), "damage_pct");
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        // The cost of a Lava Burst Lava Surge made free was waived before the cast; the state is spent with it.
        if (player && Is(spellId) && FreeLavaBurst::Pending(player))
            FreeLavaBurst::Spend(player);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (striking || !player || !target || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        switch (rune)
        {
            case Rune::PathOfFlames:
                // "If the target is Burning, every enemy within {radius_yards} yards also Burns for {damage_pct} weapon
                // damage as Fire over {dot_duration_seconds} seconds."
                if (Spreads(rune, Burning::Is(player, target)))
                    for (Unit* enemy :
                         Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                    {
                        Burning::Burn(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                                      Numbers::Num(spellId, "dot_duration_seconds"),
                                      Tunables::Get("combat", "lava_burst_burn_tick_seconds"));
                    }
                break;
            case Rune::Pyroclasm:
                // "The lava erupts on impact and deals {damage_pct} weapon damage as Fire to all enemies within
                // {radius_yards} yards."
                for (Unit* enemy :
                     Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                    Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));
                break;
            case Rune::ObsidianBurst:
                // "Knocks Down the target for {duration_seconds} second."
                Stun(player, target, Numbers::Num(spellId, "duration_seconds"));
                break;
            case Rune::SteamBurst:
                // "Enemies hit are Frozen for {freeze_duration_seconds} second."
                Freeze(player, target, Numbers::Num(spellId, "freeze_duration_seconds"));
                break;
            case Rune::VolcanicLightning:
            {
                // "After impact, {hit_count} lightning strikes hit random enemies within {radius_yards} yards for
                // {damage_pct} weapon damage as Lightning each."
                std::vector<Unit*> const near =
                    Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards"));
                for (unsigned strike = 0, count = unsigned(Numbers::Num(spellId, "hit_count")); strike < count;
                     ++strike)
                    if (auto const pick = Pick(frand(0.0f, 1.0f), near.size()))
                        Strikes(player, near[*pick], spellId, Numbers::Num(spellId, "damage_pct"));
                break;
            }
            default:
                break;
        }
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!player || !target || !Is(spellId))
            return;
        // "Deals {damage_bonus_pct} more damage to Burning enemies, meaning enemies affected by any Fire
        // damage-over-time or burn effect from you."
        if (BonusApplies(RuneAt(spellId), Burning::Is(player, target), Chilled(player, target)))
            AddFactor(out, "Burning", Numbers::Num(BaseId(), "damage_bonus_pct"));
    }
} // namespace DC::Combat::Shaman::LavaBurst
