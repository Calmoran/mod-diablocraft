#pragma once
// Blinding Flash's rules that need no core type, header-only so
// tests/monk_blinding_flash compiles this exact code: who is blind and for how long, what an elite does while blind, the
// delay of Crippling Light's weakening.
#include <algorithm>
#include <cstdint>
#include <map>

namespace DC::Combat::Monk::BlindingFlash
{
    // "Elite enemies recover faster, but suffer a {miss_chance_pct} chance to miss with attacks": an ordinary enemy is
    // disoriented for the whole blind; an elite for `eliteSeconds` (no source states it: 0 until a tunable is set, so an
    // elite is not disoriented at all) and misses `missPct` of its attacks for the whole blind.
    inline double DisorientSeconds(bool elite, double blindSeconds, double eliteSeconds)
    {
        if (blindSeconds <= 0)
            return 0.0;
        return elite ? std::min(std::max(eliteSeconds, 0.0), blindSeconds) : blindSeconds;
    }

    inline double MissPct(bool elite, double missPct)
    {
        return elite && missPct > 0 ? missPct : 0.0;
    }

    // The enemies that miss: each until the end of its blind. A new flash on the same enemy starts over.
    class Blind
    {
    public:
        void Set(std::uint64_t enemy, std::uint64_t untilMs, double missPct)
        {
            if (missPct > 0)
                book_[enemy] = {untilMs, missPct};
            else
                book_.erase(enemy);
        }

        // The percent of its attacks the enemy misses at `now`; 0 when it is not blind or has run out.
        double Chance(std::uint64_t enemy, std::uint64_t now)
        {
            auto const found = book_.find(enemy);
            if (found == book_.end())
                return 0.0;
            if (now >= found->second.untilMs)
            {
                book_.erase(found);
                return 0.0;
            }
            return found->second.pct;
        }

    private:
        struct Value
        {
            std::uint64_t untilMs = 0;
            double pct = 0;
        };
        std::map<std::uint64_t, Value> book_;
    };

    // Crippling Light: "deal {enemy_damage_pct} reduced damage for {duration_seconds} seconds after the Blind wears off": the
    // weakening begins when the blind ends.
    inline std::uint32_t WeakenAfterMs(double blindSeconds)
    {
        return blindSeconds > 0 ? static_cast<std::uint32_t>(blindSeconds * 1000.0 + 0.5) : 0u;
    }
} // namespace DC::Combat::Monk::BlindingFlash
