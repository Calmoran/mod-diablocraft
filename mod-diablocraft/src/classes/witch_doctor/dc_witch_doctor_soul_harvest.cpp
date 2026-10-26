/*
 * Soul Harvest and its five runes. The cast is the engine's self-centred area cast (a spell record and the sheet's
 * numbers: the cooldown, the radius, each rune's school); here: the Intelligence every harvested enemy adds for a
 * while, and each rune's part: Siphon's Life, Soul to Waste's speed, Languish's armor and slow, Swallow Your Soul's
 * larger pool and Mana, Vengeful Spirit's hit (the engine's, through the damage seam).
 */

#include "dc_witch_doctor_soul_harvest.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_mana.h"
#include "dc_witch_doctor_sheet_buffs.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_healing_table.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../stats/dc_stats.h"
#include "Player.h"
#include "Unit.h"

namespace DC::Combat::WitchDoctor::SoulHarvest
{
    namespace
    {
        constexpr std::string_view Skill = "Soul Harvest";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The Mana pool's points without the buff Swallow Your Soul puts on it.
        double BasePool(Player* player, std::uint32_t spellId)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            return sheet ? (*sheet)[Stat::MaxFury] - SheetBuffs::Current(player, spellId, Stat::MaxFury) : 0.0;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return HitPct(RuneAt(spellId), Numbers::Get(spellId, "damage_pct").value_or(0.0));
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || targets.empty() || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        unsigned const enemies = unsigned(targets.size());
        unsigned const most = unsigned(Numbers::Num(spellId, "max_stacks_count"));
        unsigned const adds = StacksAdded(enemies, most);
        // Languish states its slow's seconds as its own: the buff keeps the skill's.
        double const seconds =
            Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(Skill), "duration_seconds"));
        // "Gain {primary_stat_pct} Intelligence for {duration_seconds} seconds for each affected enemy."
        SheetBuffs::Stack(player, spellId, Stat::Intelligence, Bucket::Percent,
                          Numbers::Num(spellId, "primary_stat_pct"), most, seconds, adds);
        switch (rune)
        {
            case Rune::Siphon:
                // "Gain {heal_life} Life for every harvested enemy."
                Heal(player, spellId,
                     SiphonHeal(Tune("soul_harvest_healing_share"), Healing::At(player->GetLevel()), enemies));
                break;
            case Rune::SoulToWaste:
                // "Gain {movement_speed_pct} increased movement speed for each enemy harvested."
                SheetBuffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Flat,
                                  Numbers::Num(spellId, "movement_speed_pct"), most, seconds, adds);
                break;
            case Rune::Languish:
                // "Increase your Armor by {armor_pct} per harvested enemy and reduce their movement speed by {slow_pct}
                // for {duration_seconds} seconds."
                SheetBuffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"),
                                  most, seconds, adds);
                for (Unit* enemy : targets)
                    Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "duration_seconds"));
                break;
            case Rune::SwallowYourSoul:
            {
                // "Gain mana and increase maximum Mana by {max_pool_pct} for each enemy harvested": the pool rises for
                // the buff's time and the same points are gained at once.
                double const rise =
                    Buffs::PoolPerStack(BasePool(player, spellId), Numbers::Num(spellId, "max_pool_pct"));
                SheetBuffs::Stack(player, spellId, Stat::MaxFury, Bucket::Flat, rise, most, seconds, adds);
                Gain(player, Classes::ClassIdOf(player), spellId, Buffs::PerEnemy(adds, rise), 1);
                break;
            }
            default:
                break;
        }
    }
} // namespace DC::Combat::WitchDoctor::SoulHarvest
