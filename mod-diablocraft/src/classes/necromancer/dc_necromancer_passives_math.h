#pragma once
// The rules of the Necromancer's passives that need no core type, header-only so tests/necromancer_passives compiles
// this exact code: Life from Death's globe roll and its rate cap, Stand Alone's armor, Bone Prison's skills and chance,
// Swift Harvesting's skills and speed, Commander of the Risen Dead's skill and cooldown cut. The production half is
// dc_necromancer_passives.cpp.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string_view>

namespace DC::Combat::Necromancer::Passive
{
    // A chance in percent held by a roll in [0, 100): a chance of 0 never (a roll is never below 0), of 100 always.
    inline bool Procs(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // Life from Death: "has a chance to spawn a health globe", at most `max` globes in any `windowMs` (the power's rate
    // cap).
    struct GlobeWindow
    {
        std::uint64_t start = 0;
        unsigned spawned = 0;

        bool Allow(std::uint64_t now, std::uint64_t windowMs, unsigned max)
        {
            if (spawned == 0 || now >= start + windowMs)
            {
                start = now;
                spawned = 0;
            }
            if (spawned >= max)
                return false;
            ++spawned;
            return true;
        }
    };

    // Stand Alone: "Increase armor by {armor_pct:base}, reduced by {armor_pct:per_minion} for each active minion":
    // never below nothing.
    inline double StandAloneArmorPct(double basePct, double perMinionPct, unsigned minions)
    {
        return std::max(0.0, basePct - perMinionPct * minions);
    }

    // Bone Prison: "Bone Spear, Bone Spikes, and Bone Spirit".
    inline bool BonePrisonSkill(std::string_view skill)
    {
        return skill == "Bone Spear" || skill == "Bone Spikes" || skill == "Bone Spirit";
    }

    // Swift Harvesting: "the attack speed of Bone Spikes, Siphon Blood, and Grim Scythe".
    inline bool SwiftHarvestingSkill(std::string_view skill)
    {
        return skill == "Bone Spikes" || skill == "Siphon Blood" || skill == "Grim Scythe";
    }

    // Attack speed bonuses add to each other (the sheet's speed is the weapon's times one plus the sum), so the
    // passive's share goes into the sum the skill's speed was built from: `aps` is the hand's attacks per second with
    // `iasPct` already in it. The result keeps to the attack speed cap and never falls below what it was.
    inline double SwiftHarvestingAps(double aps, double iasPct, double bonusPct, double cap)
    {
        if (aps <= 0 || 1.0 + iasPct / 100.0 <= 0)
            return aps;
        double const sped = aps * (1.0 + (iasPct + bonusPct) / 100.0) / (1.0 + iasPct / 100.0);
        return std::max(aps, std::min(cap, sped));
    }

    // "... and the cooldown of Command Golem": the milliseconds taken off a cooldown that has `leftMs` to run.
    inline std::uint32_t CooldownCut(std::uint32_t leftMs, double pct)
    {
        return std::uint32_t(leftMs * std::clamp(pct, 0.0, 100.0) / 100.0);
    }

    // Extended Servitude: "the duration of your Skeletal Mage and Revive minions".
    inline bool ServitudeSkill(std::string_view skill)
    {
        return skill == "Skeletal Mage" || skill == "Revive";
    }

    // What a minion's time is multiplied by: one plus the passive's share.
    inline double ServitudeFactor(double bonusPct)
    {
        return 1.0 + std::max(0.0, bonusPct) / 100.0;
    }

    // Rigor Mortis: "Poison abilities" (the module's Poison is the shadow school of a record).
    inline bool PoisonMask(std::uint32_t schoolMask)
    {
        return (schoolMask & 32u) != 0;
    }

    // Spreading Malediction: "a damage bonus for each enemy afflicted by one of your curses".
    inline double MaledictionPct(double perEnemyPct, unsigned cursed)
    {
        return std::max(0.0, perEnemyPct) * cursed;
    }

    // Eternal Torment: "Your curses ... last forever": the seconds a curse of `seconds` stands, `forever` when the passive is on.
    inline double CurseSeconds(bool eternal, double seconds, double forever)
    {
        return eternal && seconds > 0 ? std::max(seconds, forever) : seconds;
    }

    // Eternal Torment: "Your curses cost {cost_reduction_pct} less Essence": the three curse skills (necromancer_skills.csv).
    inline constexpr std::array<std::string_view, 3> CurseSkills = {"Decrepify", "Leech", "Frailty"};

    inline bool CurseSkill(std::string_view skill)
    {
        return std::find(CurseSkills.begin(), CurseSkills.end(), skill) != CurseSkills.end();
    }

    // Dark Reaping: "While using a scythe": the base item types of the one-handed and the two-handed scythe (base_items.csv).
    inline bool ScytheType(std::string_view type)
    {
        return type == "Scythe" || type == "Two-Handed Scythe";
    }

    // Dark Reaping: "gain {gain_pct} Essence and Life per kill": the share of a maximum.
    inline double ReapGain(double maximum, double gainPct)
    {
        return maximum > 0 && gainPct > 0 ? maximum * gainPct / 100.0 : 0.0;
    }

    // Final Service: "When you take lethal damage, you are sustained preventing all damage for {duration_seconds} seconds ... cannot occur more
    // than once every {internal_cooldown_seconds} seconds": the window and the wait, in the game's milliseconds.
    struct Sustain
    {
        std::uint64_t until = 0;
        std::uint64_t readyAt = 0;

        bool Active(std::uint64_t now) const
        {
            return now < until;
        }

        // A blow of `damage` on a body with `health` left: true when this blow is the lethal one that starts the window (and the wait).
        bool Save(std::uint64_t now, double damage, double health, std::uint64_t cooldownMs, std::uint64_t durationMs)
        {
            if (now < readyAt || health <= 0 || damage < health)
                return false;
            until = now + durationMs;
            readyAt = now + cooldownMs;
            return true;
        }
    };

    // Final Service: "you heal for {heal_pct} of your Life per minion".
    inline double ServiceHeal(double maxLife, double healPct, unsigned minions)
    {
        return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 * minions : 0.0;
    }

    // Grisly Tribute: "You are healed for {life_per_hit_share_pct} of your Life on Hit when one of your minions hits an enemy".
    inline double TributeHeal(double lifePerHit, double sharePct)
    {
        return lifePerHit > 0 && sharePct > 0 ? lifePerHit * sharePct / 100.0 : 0.0;
    }

    // Draw Life: "Increases your Life regeneration by {life_regen_pct} for each enemy within {radius_yards} yards".
    inline double DrawLifePct(double perEnemyPct, unsigned enemies)
    {
        return std::max(0.0, perEnemyPct) * enemies;
    }

    // Serration: "Bone Spikes, Bone Spear, and Bone Spirit".
    inline bool SerrationSkill(std::string_view skill)
    {
        return skill == "Bone Spikes" || skill == "Bone Spear" || skill == "Bone Spirit";
    }

    // Serration: "deal {damage_bonus_pct} increased damage for every {distance_yards} yards from you, up to a maximum of {max_bonus_pct}": a
    // whole step is a whole bonus.
    inline double SerrationPct(double yards, double perStepPct, double stepYards, double maxPct)
    {
        if (yards <= 0 || perStepPct <= 0 || stepYards <= 0)
            return 0.0;
        return std::min(std::max(0.0, maxPct), std::floor(yards / stepYards) * perStepPct);
    }

    // Aberrant Animator: "Your minions gain {thorns_share_pct} of your Thorns".
    inline double MinionThorns(double thorns, double sharePct)
    {
        return thorns > 0 && sharePct > 0 ? thorns * sharePct / 100.0 : 0.0;
    }

    // Blood for Blood: "Picking up a health globe removes the health cost of the next Blood spell. This effect can stack up to {max_stacks_count}
    // times."
    struct FreeCosts
    {
        unsigned stacks = 0;

        void Gain(unsigned max)
        {
            stacks = std::min(stacks + 1, max);
        }

        // A Blood spell is cast: true when a stack paid its cost.
        bool Spend()
        {
            if (!stacks)
                return false;
            --stacks;
            return true;
        }
    };

    // Blood Is Power: "After cumulatively losing {life_lost_threshold_pct} of your maximum Life, all ability cooldowns are reduced": the Life lost
    // adds up and each whole threshold of it is one reduction.
    struct LostLife
    {
        double lost = 0;

        // `amount` of Life is lost out of a maximum of `maxLife`: how many whole thresholds this completes.
        unsigned Add(double amount, double maxLife, double thresholdPct)
        {
            double const threshold = maxLife * thresholdPct / 100.0;
            if (amount <= 0 || threshold <= 0)
                return 0;
            lost += amount;
            unsigned whole = 0;
            while (lost >= threshold)
            {
                lost -= threshold;
                ++whole;
            }
            return whole;
        }
    };

    // Rathma's Shield: "You cannot lose Life for {duration_seconds} seconds after using Land of the Dead, Army of the Dead, or Simulacrum".
    inline bool RathmaSkill(std::string_view skill)
    {
        return skill == "Land of the Dead" || skill == "Army of the Dead" || skill == "Simulacrum";
    }

    // Rathma's Shield: the window and the wait ("cannot occur more than once every {internal_cooldown_seconds} seconds").
    struct Ward
    {
        std::uint64_t until = 0;
        std::uint64_t readyAt = 0;

        bool Active(std::uint64_t now) const
        {
            return now < until;
        }

        // A skill is used: true when the window opens.
        bool Open(std::uint64_t now, std::uint64_t durationMs, std::uint64_t cooldownMs)
        {
            if (now < readyAt)
                return false;
            until = now + durationMs;
            readyAt = now + cooldownMs;
            return true;
        }
    };
} // namespace DC::Combat::Necromancer::Passive
