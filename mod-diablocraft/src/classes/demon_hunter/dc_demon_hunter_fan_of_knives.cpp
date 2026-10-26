/*
 * Fan of Knives and its five runes. The fan is the engine's burst round the Demon Hunter (a spell record and the
 * sheet's numbers) that hits every enemy within its radius; here: the slow every enemy hit takes, Fan of Daggers'
 * knockback and stun, Assassin's Knives' long-range knives at more enemies and Bladed Armor's armor. Knives Expert's
 * cost and missing cooldown and Pinpoint Accuracy's damage and cooldown are sheet numbers the same engine reads.
 */

#include "dc_demon_hunter_fan_of_knives.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Unit.h"

namespace DC::Combat::DemonHunter::FanOfKnives
{
    namespace
    {
        constexpr std::string_view Skill = "Fan of Knives";

        // The long-range knives strike too; they are no fan, so they neither slow nor stun.
        thread_local bool throwing = false;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (throwing || !player || !target || !Is(spellId))
            return;
        // "Your knives will also Slow the movement of enemies by {slow_pct} for {slow_duration_seconds} second."
        Slow(player, target, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"));
        // Fan of Daggers: "Enemies hit are Stunned for {stun_duration_seconds} seconds"; the power file gives the rune
        // a knockback and a stun, each with a chance of 1.
        if (RuneAt(spellId) == Rune::FanOfDaggers)
        {
            Abilities::Knockback(player, target, Tune("fan_of_knives_knockback_yards"));
            Stun(player, target, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
        }
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::AssassinsKnives:
            {
                // The enemies the fan did not reach, within the power file's search radius, nearest first.
                double const search = Tune("fan_of_knives_knife_range_yards");
                auto const nearby = Combat::Enemies(player, spellId, player->GetPosition(), search);
                std::vector<double> distances;
                for (Unit* enemy : nearby)
                    distances.push_back(player->GetExactDist(enemy));
                Scope scope(throwing);
                for (std::size_t index : ExtraTargets(distances, Numbers::Num(spellId, "radius_yards"), search,
                                                      unsigned(Numbers::Num(spellId, "target_count"))))
                    Combat::Strike(player, nearby[index], spellId, Numbers::Num(spellId, "damage_pct"));
                break;
            }
            case Rune::BladedArmor:
                // "Gain {armor_pct} additional armor for {duration_seconds} seconds."
                Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1,
                             Numbers::Num(spellId, "duration_seconds"));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::DemonHunter::FanOfKnives
