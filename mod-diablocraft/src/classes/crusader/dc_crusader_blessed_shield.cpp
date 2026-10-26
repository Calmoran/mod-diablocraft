/*
 * Blessed Shield and its five runes: the shield is a projectile, so everything acts where it lands on an enemy: the
 * ricochet (or Piercing Shield's pierce), and what each rune does about every enemy hit. The dispatch is in
 * dc_crusader.cpp; the Block Chance share is dc_crusader_block_share.cpp's.
 */

#include "dc_crusader_blessed_shield.h"
#include "dc_crusader_block_share.h"
#include "dc_crusader_common.h"
#include "dc_crusader_nearest.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_item_powers.h"
#include "Util.h"

#include <limits>

namespace DC::Combat::Crusader::BlessedShield
{
    namespace
    {
        constexpr std::string_view Skill = "Blessed Shield";

        // The ricochet's and the rune's own strikes are hits of the same spell and land too; they must not start it
        // again.
        thread_local bool answering = false;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        bool Struck(std::vector<Unit*> const& hit, Unit const* enemy)
        {
            return std::find(hit.begin(), hit.end(), enemy) != hit.end();
        }

        // "ricochet to {target_count} nearby enemies": from each enemy hit, the nearest enemy not hit yet.
        void Ricochet(Player* player, std::uint32_t spellId, Unit* first, std::vector<Unit*>& hit)
        {
            double const radius = Tune("blessed_shield_bounce_yards");
            Unit* last = first;
            for (unsigned bounce = 0, most = unsigned(Numbers::Num(spellId, "target_count")); bounce < most; ++bounce)
            {
                std::vector<Unit*> around = Combat::Enemies(player, spellId, last->GetPosition(), radius);
                std::vector<double> distances;
                std::vector<bool> struck;
                for (Unit* enemy : around)
                {
                    distances.push_back(last->GetExactDist(enemy));
                    struck.push_back(Struck(hit, enemy));
                }
                int const next = NextBounce(distances, struck, radius);
                if (next < 0 || !Combat::Strike(player, around[std::size_t(next)], spellId))
                    return;
                last = around[std::size_t(next)];
                hit.push_back(last);
            }
        }

        // Piercing Shield: the enemies on the line from the Crusader through the one aimed at, each struck with the
        // shield's hit and perhaps knocked aside. The line's width and the distance are blank tunables with no number
        // yet: with no width the shield pierces nobody beyond the enemy aimed at.
        void Pierce(Player* player, std::uint32_t spellId, Unit* first, std::vector<Unit*>& hit)
        {
            double const length = Tune("blessed_shield_range_yards"), width = Tune("blessed_shield_pierce_width_yards");
            if (width <= 0)
                return;
            double const heading = player->GetAngle(first);
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), length))
            {
                if (enemy == first)
                    continue;
                double const dx = enemy->GetPositionX() - player->GetPositionX(),
                             dy = enemy->GetPositionY() - player->GetPositionY();
                double const along = dx * std::cos(heading) + dy * std::sin(heading),
                             across = -dx * std::sin(heading) + dy * std::cos(heading);
                if (OnLine(along, across, length, width) && Combat::Strike(player, enemy, spellId))
                    hit.push_back(enemy);
            }
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
        return Numbers::Get(BaseId(Skill), "damage_pct");
    }

    std::optional<std::pair<double, double>> Main(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        std::uint32_t const base = BaseId(Skill);
        return std::make_pair(Numbers::Num(base, "damage_pct"), Numbers::Num(base, "block_chance_share_pct"));
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (answering || !player || !target || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        std::vector<Unit*> hit{target};
        answering = true;
        if (rune == Rune::PiercingShield)
            Pierce(player, spellId, target, hit);
        else
            Ricochet(player, spellId, target, hit);

        switch (rune)
        {
            case Rune::StaggeringShield:
            {
                // A stun chance for each enemy hit, falling by the reduction for each one after the first.
                double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
                double const base = Numbers::Num(spellId, "proc_chance_pct", "base"),
                             reduction = Numbers::Num(spellId, "proc_chance_pct", "reduction");
                for (unsigned place = 0; place < hit.size(); ++place)
                    if (roll_chance_f(float(StunChance(base, reduction, place))))
                        Stun(player, hit[place], stun);
                break;
            }
            case Rune::Combust:
            {
                // "has a {proc_chance_pct} chance to explode on impact, dealing {damage_pct} weapon damage as Fire to
                // all enemies within {radius_yards} yards": a roll for each enemy the shield hit, around it.
                auto const pct = Numbers::Own(spellId, "damage_pct");
                BlockShare::OwnStrikes scope;
                for (Unit* enemy : hit)
                    if (roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        for (Unit* near : Combat::Enemies(player, spellId, enemy->GetPosition(),
                                                          Numbers::Num(spellId, "radius_yards")))
                            Combat::Strike(player, near, spellId, pct);
                break;
            }
            case Rune::DivineAegis:
                // "When the shield hits an enemy, your Armor is increased by {armor_pct} and Life regeneration by
                // {life_regen_pct} for {duration_seconds} seconds": a stack for each enemy hit. No source gives a most.
                for (std::size_t i = 0; i < hit.size(); ++i)
                {
                    Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"),
                                 std::numeric_limits<unsigned>::max(), Numbers::Num(spellId, "duration_seconds"));
                    Buffs::Stack(player, spellId, Stat::LifeRegen, Bucket::Percent,
                                 Numbers::Num(spellId, "life_regen_pct"), std::numeric_limits<unsigned>::max(),
                                 Numbers::Num(spellId, "duration_seconds"));
                }
                break;
            case Rune::ShatteringThrow:
            {
                // "it splits into {spawn_count} small fragments that bounce between nearby enemies, dealing
                // {damage_pct} weapon damage as Holy to all enemies hit": each fragment goes to one of the nearest
                // other enemies around the first.
                double const radius = Tune("blessed_shield_bounce_yards");
                std::vector<Unit*> others;
                std::vector<double> distances;
                for (Unit* enemy : Combat::Enemies(player, spellId, target->GetPosition(), radius))
                    if (enemy != target)
                    {
                        others.push_back(enemy);
                        distances.push_back(target->GetExactDist(enemy));
                    }
                auto const pct = Numbers::Own(spellId, "damage_pct");
                BlockShare::OwnStrikes scope;
                for (std::size_t index : Nearest(distances, radius, std::size_t(Numbers::Num(spellId, "spawn_count"))))
                    Combat::Strike(player, others[index], spellId, pct);
                break;
            }
            case Rune::PiercingShield:
                // "pierces through all enemies with a {proc_chance_pct} chance to knock them aside".
                for (Unit* enemy : hit)
                    if (roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        Abilities::Knockback(player, enemy, Tune("blessed_shield_knockaside_yards"));
                break;
            default:
                break;
        }
        answering = false;
    }
} // namespace DC::Combat::Crusader::BlessedShield
