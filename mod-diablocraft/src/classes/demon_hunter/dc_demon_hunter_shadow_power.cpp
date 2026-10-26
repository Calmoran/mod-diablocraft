/*
 * Shadow Power and its five runes. The cast is the engine's self-cast spell (a record and the sheet's numbers) with no
 * hit; here: the Life per Hit for its seconds (the level-scaled number of the power file and a share of Life per Kill,
 * doubled by Blood Moon) and the rune's part: Night Bane's slow, Shadow Glide's speed, Gloom's damage reduction. Well
 * of Darkness' cheaper cast is a sheet number the same code reads.
 */

#include "dc_demon_hunter_shadow_power.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_healing_table.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../stats/dc_stats.h"
#include "Player.h"
#include "Unit.h"

namespace DC::Combat::DemonHunter::ShadowPower
{
    namespace
    {
        constexpr std::string_view Skill = "Shadow Power";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The Life per Kill on the Demon Hunter's sheet now.
        double LifePerKill(Player* player)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            return sheet ? (*sheet)[Stat::LifePerKill] : 0.0;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId))
            return;
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        Rune const rune = RuneAt(spellId);
        Buffs::Stack(player, spellId, Stat::LifePerHit, Bucket::Flat,
                     LifePerHit(rune, Tune("shadow_power_life_on_hit_healing_share"), Healing::At(player->GetLevel()),
                                Numbers::Num(spellId, "life_per_kill_share_pct"), LifePerKill(player)),
                     1, seconds);
        switch (rune)
        {
            case Rune::NightBane:
                // "Slow the movement speed of enemies within {radius_yards} yards by {slow_pct} for
                // {slow_duration_seconds} seconds."
                for (Unit* enemy :
                     Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                    Slow(player, enemy, Numbers::Num(spellId, "slow_pct"),
                         Numbers::Num(spellId, "slow_duration_seconds"));
                break;
            case Rune::ShadowGlide:
                // "Gain {movement_speed_pct} increased movement speed while Shadow Power is active."
                Buffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped,
                             Numbers::Num(spellId, "movement_speed_pct"), 1, seconds);
                break;
            case Rune::Gloom:
                // "Reduce damage taken by {damage_reduction_pct} while Shadow Power is active."
                Buffs::Stack(player, spellId, Stat::SpecificReduction, Bucket::Flat,
                             Numbers::Num(spellId, "damage_reduction_pct"), 1, seconds);
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::DemonHunter::ShadowPower
