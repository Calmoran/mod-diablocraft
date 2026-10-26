/*
 * Bone Spear and its five runes. The engine sends the spear along the line and hits each enemy it meets for the skill's
 * weapon damage; here: Crystallization slows what it hits and speeds the Necromancer up, Shatter makes the first enemy
 * hit the place of a detonation instead of a pierce, Blighted Marrow adds to each hit for the enemies already passed,
 * Blood Spear takes Life for its larger hit, Teeth stop short.
 */

#include "dc_necromancer_bone_spear.h"
#include "dc_necromancer_bone_spear_math.h"
#include "dc_necromancer_common.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::Necromancer::BoneSpear
{
    namespace
    {
        constexpr std::string_view Skill = "Bone Spear";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // How many enemies the spear has passed when its next hit is computed: set at each impact, read by the hit that
        // follows at once.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, unsigned> passed;
    } // namespace

    void Casting(Player* player, std::uint32_t spellId)
    {
        // "Damage is increased to {damage_pct} weapon damage as Physical at the cost of 10% Health."
        if (player && RuneAt(spellId) == Rune::BloodSpear)
            SpendLife(player, Tune("blood_spear_life_cost_pct"));
    }

    bool Impact(Player* player, Unit* target, std::uint32_t spellId, unsigned index)
    {
        if (!player || !target)
            return false;
        switch (RuneAt(spellId))
        {
            case Rune::Shatter:
                // "Instead of piercing now detonates on the first enemy hit dealing {damage_pct} weapon damage as
                // Physical to all enemies within {radius_yards} yards."
                if (Detonates(index))
                    Combat::StrikeArea(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards"));
                return true;
            case Rune::Teeth:
                return !WithinReach(player->GetExactDist(target), Tune("bone_spear_teeth_reach_yards"));
            case Rune::BlightedMarrow:
            {
                std::lock_guard<std::mutex> guard(mutex);
                passed[player->GetGUID().GetRawValue()] = index;
                return false;
            }
            default:
                return false;
        }
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || RuneAt(spellId) != Rune::Crystallization)
            return;
        // "Each enemy hit has their attack speed reduced by {attack_speed_pct:enemy} and your attack speed is increased
        // by {attack_speed_pct:self} for {duration_seconds} seconds stacking up to {max_stacks_count} times."
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        Weary(player, target, Numbers::Num(spellId, "attack_speed_pct", "enemy"), seconds);
        Buffs::Stack(player, spellId, Stat::AttackSpeed, Bucket::Flat,
                     Numbers::Num(spellId, "attack_speed_pct", "self"),
                     unsigned(Numbers::Num(spellId, "max_stacks_count")), seconds);
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!player || RuneAt(spellId) != Rune::BlightedMarrow)
            return;
        unsigned count;
        {
            std::lock_guard<std::mutex> guard(mutex);
            count = passed[player->GetGUID().GetRawValue()];
        }
        // "Damage is increased by {damage_bonus_pct} for each enemy Bone Spear passes through."
        if (double const bonus = PierceBonusPct(Numbers::Num(spellId, "damage_bonus_pct"), count))
            AddFactor(out, "Blighted Marrow", bonus);
    }
} // namespace DC::Combat::Necromancer::BoneSpear
