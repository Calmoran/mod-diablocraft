#pragma once
// The rules of six Monk passives that need no core type, header-only so
// tests/monk_passives_harmony compiles this exact code: Harmony, Combination Strike, Near Death Experience, Unity,
// Momentum, Mythic Rhythm. The numbers come in as arguments (monk_passive_values.csv through Numbers::Num).
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <unordered_map>

namespace DC::Combat::Monk::PassivesHarmony
{
    // Harmony: "{resistance_share_pct} of your single elemental resistances from items instead increases your
    // resistance to all elements". Each element gives up `sharePct` of its item resistance and the six shares are added
    // to every element's all-element resistance.
    struct HarmonyResult
    {
        std::array<double, 7> single{}; // what comes off each element (negative)
        double all = 0;                 // what goes on All Resistance
    };

    inline HarmonyResult Harmony(std::array<double, 7> const& items, double sharePct)
    {
        HarmonyResult out;
        if (sharePct <= 0)
            return out;
        for (std::size_t i = 0; i < items.size(); ++i)
        {
            double const moved = std::max(0.0, items[i]) * sharePct / 100.0;
            out.single[i] = -moved;
            out.all += moved;
        }
        return out;
    }

    // Combination Strike (Power/Monk_Passive_CombinationStrike.pow): each DIFFERENT Spirit
    // Generator used raises all the Monk's damage by `pct` for `ms`. Using the same one again only renews it.
    struct Combination
    {
        std::unordered_map<std::uint32_t, std::uint64_t> until;

        void Use(std::uint32_t generator, std::uint64_t now, std::uint64_t ms)
        {
            until[generator] = now + ms;
        }

        // How many different generators are still running.
        unsigned Active(std::uint64_t now) const
        {
            unsigned running = 0;
            for (auto const& entry : until)
                if (now < entry.second)
                    ++running;
            return running;
        }

        // The percent added to every hit: `pct` for each different generator running.
        double Bonus(std::uint64_t now, double pct) const
        {
            return Active(now) * pct;
        }
    };

    // Mythic Rhythm: "Every third hit from a Spirit Generator increases the damage of your next damaging Spirit Spender by
    // 40%". Every `hitCount`-th generator hit arms the bonus, one at a time; the next spender deals it and spends it. The
    // count runs on through the spend. It pays no Spirit. A spender whose hits come after its cast (Seven-Sided Strike's
    // strikes) spends it with the cast, and its strikes carry what the cast found.
    struct Rhythm
    {
        unsigned hits = 0;
        bool armed = false;
        bool carried = false;

        void Hit(unsigned hitCount)
        {
            if (!hitCount)
                return;
            hits = (hits + 1) % hitCount;
            if (!hits)
                armed = true;
        }

        // The percent on a spender's hit; `delayed` for a hit of a spender whose hits come after its cast.
        double Bonus(double pct, bool delayed = false) const
        {
            return (delayed ? carried : armed) ? pct : 0.0;
        }

        // Whether a spender found it armed.
        bool Spend()
        {
            bool const was = armed;
            armed = false;
            return was;
        }

        // A delayed spender's cast: it spends the bonus, and its hits carry it if it was armed.
        void Carry()
        {
            carried = Spend();
        }
    };

    // Momentum: yards moved add up; every `needed` yards (re)starts the buff for `ms`.
    struct Momentum
    {
        double yards = 0;
        std::uint64_t until = 0;

        void Moved(double moved, std::uint64_t now, double needed, std::uint64_t ms)
        {
            if (moved <= 0 || needed <= 0)
                return;
            yards += moved;
            if (yards >= needed)
            {
                yards = std::fmod(yards, needed);
                until = now + ms;
            }
        }

        bool On(std::uint64_t now) const
        {
            return now < until;
        }
    };

    // Unity: `allies` affected by the Mantras give the Monk `perAlly` each up to `maxPct`.
    inline double UnitySelf(unsigned allies, double perAlly, double maxPct)
    {
        return std::min(maxPct, allies * perAlly);
    }

    // An ally under `monks` Monks' Unity has `perMonk` each, at most `maxStacks` of them.
    inline double UnityAlly(unsigned monks, double perMonk, unsigned maxStacks)
    {
        return std::min(monks, maxStacks) * perMonk;
    }

    // Near Death Experience: fatal damage once per `cooldownMs`; the immunity runs `immuneMs` from it.
    struct NearDeath
    {
        std::uint64_t readyAt = 0;
        std::uint64_t immuneUntil = 0;

        bool Immune(std::uint64_t now) const
        {
            return now < immuneUntil;
        }

        // Whether `damage` against `health` is fatal and the passive is ready; when it is, it starts its cooldown and
        // its immunity.
        bool Save(std::uint64_t now, std::uint64_t damage, std::uint64_t health, std::uint64_t cooldownMs,
                  std::uint64_t immuneMs)
        {
            if (damage < health || now < readyAt)
                return false;
            readyAt = now + cooldownMs;
            immuneUntil = now + immuneMs;
            return true;
        }
    };

    // The life Near Death Experience restores: a share of the maximum, never past it.
    inline std::uint64_t NearDeathHealth(std::uint64_t health, std::uint64_t maxHealth, double pct)
    {
        auto const wanted = std::uint64_t(std::llround(maxHealth * pct / 100.0));
        return std::min<std::uint64_t>(maxHealth, health + wanted);
    }
} // namespace DC::Combat::Monk::PassivesHarmony
