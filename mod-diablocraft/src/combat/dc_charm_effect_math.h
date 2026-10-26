#pragma once
// The rules of putting a charm on a monster, with no core type, so tests/charm_effect compiles this exact code: who may
// be charmed, the roll of a charm that has a chance, and which foe a charmed monster is first sent at. The production
// half is dc_charm_effect.cpp; the rules a charmed monster follows afterwards are the rifts' (rifts/dc_charm.h).
#include <cstddef>
#include <optional>
#include <vector>

namespace DC::Combat::CharmEffect
{
    // What the charm asks of the monster it would take.
    struct Target
    {
        bool creature = false; // a monster; a player is never charmed
        bool alive = false;
        bool hostile = false;            // an enemy of the charmer, so not a friend, a pet or a neutral
        bool alreadyCharmed = false;     // the core refuses a second charm on a charmed unit
        bool controlledByPlayer = false; // a pet, guardian or totem of a player
        bool boss = false;               // a world or dungeon boss, or a rift Guardian
    };

    // A charm of `seconds` takes this monster: bosses and Guardians are never charmed (D3: bosses are immune), and a
    // unit that is not an enemy monster, is dead, or is charmed already is not either.
    inline bool CanCharm(Target const& target, double seconds)
    {
        return seconds > 0 && target.creature && target.alive && target.hostile && !target.alreadyCharmed &&
               !target.controlledByPlayer && !target.boss;
    }

    // "a chance to be charmed": a roll in [0, 100) against the chance in percent. No chance never rolls.
    inline bool Rolls(double roll, double chancePct)
    {
        return chancePct > 0 && roll < chancePct;
    }

    // The foe a new charmed monster is sent at: the nearest of the distances (a tie keeps the first), none when there
    // is no foe.
    inline std::optional<std::size_t> NearestFoe(std::vector<double> const& distances)
    {
        std::optional<std::size_t> best;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (!best || distances[i] < distances[*best])
                best = i;
        return best;
    }

    // What the charmer of a monster is: the core's own charm has a player for a charmer; ours has the invisible holder, and
    // the holder's summoner is the player.
    struct Charmer
    {
        bool player = false;         // the charmer is a player (the core's own charm)
        bool holder = false;         // the charmer is the holder this charm summons
        bool summonerPlayer = false; // and the holder was summoned by a player
    };
    enum class Master
    {
        None,
        Charmer,        // the charmer itself is the player
        HoldersSummoner // the player behind the holder
    };

    // Whose charm it is. A holder summoned by anything but a player, or any other creature, is nobody's.
    inline Master MasterKindOf(Charmer const& charmer)
    {
        if (charmer.player)
            return Master::Charmer;
        return charmer.holder && charmer.summonerPlayer ? Master::HoldersSummoner : Master::None;
    }

    // A charmed monster with no victim, or one whose victim is dead, is sent at the next enemy.
    inline bool Retarget(bool hasVictim, bool victimAlive)
    {
        return !hasVictim || !victimAlive;
    }
} // namespace DC::Combat::CharmEffect
