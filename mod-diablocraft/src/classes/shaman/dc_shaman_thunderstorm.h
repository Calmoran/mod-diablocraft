#pragma once
// Thunderstorm's rules that need no core type, header-only so tests/shaman_thunderstorm compiles this exact code: which
// rune is which, what the thunderclap does to each enemy it struck, who a Sandstorm blinds, how a storm or a ring of
// fire ticks, and the miss chance of a blinded enemy. The production half is dc_shaman_thunderstorm.cpp, called from
// dc_shaman.cpp.
#include "../../combat/dc_periodic_strike.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <iterator>
#include <optional>
#include <string_view>
#include <unordered_map>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::Thunderstorm
{
    enum class Rune
    {
        None,
        EyeOfTheStorm, // a storm around the Shaman for seconds in place of the knockback
        GaleForce,     // the knockback doubled and the enemies stunned
        FrostStorm,    // Cold; the enemies frozen in place of the knockback
        Sandstorm,     // Physical; ordinary enemies blinded, elites and bosses only slowed
        VolcanicGale   // Fire; a ring of fire where the Shaman stood
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Eye of the Storm")
            return Rune::EyeOfTheStorm;
        if (name == "Gale Force")
            return Rune::GaleForce;
        if (name == "Frost Storm")
            return Rune::FrostStorm;
        if (name == "Sandstorm")
            return Rune::Sandstorm;
        if (name == "Volcanic Gale")
            return Rune::VolcanicGale;
        return Rune::None;
    }

    // What the thunderclap does to each enemy it struck besides the damage and the slow every rune keeps.
    struct Hold
    {
        double knockYards = 0;
        double stunSeconds = 0;
        double freezeSeconds = 0;
        bool blind = false; // an ordinary enemy is blinded (an elite is only slowed)
    };

    // `knock` is the skill's knockback, `factor` Gale Force's multiple of it, `stun` Gale Force's and `freeze` Frost
    // Storm's seconds.
    inline Hold HoldOf(Rune rune, double knock, double factor, double stun, double freeze)
    {
        Hold hold;
        switch (rune)
        {
            case Rune::None:
            case Rune::VolcanicGale:
                hold.knockYards = knock;
                break;
            case Rune::GaleForce:
                hold.knockYards = knock * factor;
                hold.stunSeconds = stun;
                break;
            case Rune::FrostStorm:
                hold.freezeSeconds = freeze;
                break;
            case Rune::Sandstorm:
                hold.knockYards = knock;
                hold.blind = true;
                break;
            case Rune::EyeOfTheStorm:
                break;
        }
        return hold;
    }

    // Sandstorm blinds an ordinary enemy; an elite or a boss is only slowed (the slow every rune keeps).
    inline bool Blinds(Hold const& hold, bool elite)
    {
        return hold.blind && !elite;
    }

    // A storm or a ring of "{damage_pct} weapon damage per second": the percent of one tick of `tickSeconds`.
    inline double TickPct(double perSecondPct, double tickSeconds)
    {
        return perSecondPct * tickSeconds;
    }

    inline unsigned Ticks(double seconds, double tickSeconds)
    {
        return PeriodicStrike::Ticks(seconds, tickSeconds);
    }

    // The enemies blinded now, each to the time it sees again and the percent of its attacks it misses.
    class Blind
    {
    public:
        // `enemy` is blind until `until`; the entries whose time is up at `now` are swept first, so an enemy that dies blind
        // does not stay for the life of the server.
        void Set(std::uint64_t enemy, std::uint64_t now, std::uint64_t until, double missPct)
        {
            for (auto it = held.begin(); it != held.end();)
                it = it->second.until <= now ? held.erase(it) : std::next(it);
            held[enemy] = {until, missPct};
        }

        std::size_t Size() const
        {
            return held.size();
        }

        // The percent of its swings `enemy` misses at `now`, 0 once its time is up.
        double Chance(std::uint64_t enemy, std::uint64_t now)
        {
            auto found = held.find(enemy);
            if (found == held.end())
                return 0.0;
            if (found->second.until <= now)
            {
                held.erase(found);
                return 0.0;
            }
            return found->second.missPct;
        }

    private:
        struct Entry
        {
            std::uint64_t until;
            double missPct;
        };
        std::unordered_map<std::uint64_t, Entry> held;
    };

    // The production half (dc_shaman_thunderstorm.cpp).
    bool Is(std::uint32_t spellId);
    // The hit of the cast itself: Eye of the Storm's and Volcanic Gale's own `damage_pct` is their storm's and ring's, so the
    // thunderclap keeps the skill's. nullopt for every other record.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The thunderclap struck `targets`: the rune's part, and the storm or the ring after it.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The percent of its swings a blinded enemy misses now (the hit table, Combat's hook).
    double MissChance(Unit const* attacker);
} // namespace DC::Combat::Shaman::Thunderstorm
