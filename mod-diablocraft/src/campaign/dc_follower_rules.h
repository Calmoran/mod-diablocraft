/*
 * World of DiabloCraft - the follower companion's rules, as pure functions (contract docs/contracts/followers.md).
 *
 * When the hired follower stands beside its player, how long it stays down after it falls, how long it stays after a
 * second player joins, and when it jumps to its player. No core types, so the harness test
 * (tests/followers/harness.cpp) compiles and drives this file itself. The numbers come from
 * data/d3/followers_rules.csv through the dc_follower_rule table; nothing is a literal here.
 */

#ifndef DC_FOLLOWER_RULES_H
#define DC_FOLLOWER_RULES_H

#include <cstdint>
#include <string_view>

namespace DC::Campaign::Followers
{
    // The follower ids of the roster sheet and of dc_character_follower.follower; None is "no follower hired".
    enum class Id : std::uint8_t
    {
        None = 0,
        Templar = 1,
        Scoundrel = 2,
        Enchantress = 3
    };
    constexpr unsigned Count = 3;

    constexpr bool Valid(unsigned raw)
    {
        return raw >= 1 && raw <= Count;
    }

    // Whether talking to `follower` offers Hire (hiring is a talk option on the follower's NPC): the player stands in
    // the hub and that follower is not the one hired. Hiring another replaces the hired one; the hired follower is
    // dismissed from the Follower window, anywhere.
    constexpr bool OffersHire(bool inHub, Id hired, Id follower)
    {
        return inHub && follower != Id::None && hired != follower;
    }

    // The one ScriptName of all three follower creatures (data/d3/followers_roster.csv); the generator checks the
    // sheet against it.
    constexpr std::string_view Script = "dc_follower";

    constexpr bool IsFollowerScript(std::string_view script)
    {
        return script == Script;
    }

    // The side of the player the companion walks on, as the stock pet's follow offset (PET_FOLLOW_ANGLE, a quarter
    // turn off the player's facing); a companion that trailed behind would sit at pi.
    constexpr float FollowAngle = 1.57079637f;

    // data/d3/followers_rules.csv, in the units the code uses.
    struct Rules
    {
        std::uint32_t reviveMs = 0;     // a fallen follower returns after this
        std::uint32_t partyLeaveMs = 0; // a follower leaves this long after a second player joins; 0 is at once
        std::uint32_t catchUpMs = 0;    // a follower left this long beyond catchUpYards jumps to its player
        float catchUpYards = 0.0f;
    };

    struct Clock
    {
        std::uint32_t reviveLeftMs = 0;
        std::uint32_t partyMs = 0;
        bool ownerDown = false;
    };

    struct Situation
    {
        bool hired = false; // a follower is hired
        bool alone = true;  // the player is in no group of two or more
        bool ownerAlive = true;
        bool out = false; // the companion stands beside the player now
    };

    constexpr void Countdown(Clock& clock, std::uint32_t diff)
    {
        clock.reviveLeftMs = diff >= clock.reviveLeftMs ? 0 : clock.reviveLeftMs - diff;
    }

    // The follower fell (a dead follower with no relic comes back after reviveMs).
    constexpr void Fell(Clock& clock, Rules const& rules)
    {
        clock.reviveLeftMs = rules.reviveMs;
    }

    // One step of `diff` milliseconds; true when the companion should stand beside the player after it.
    //  - nothing hired: no companion, clock cleared;
    //  - the player falls: the follower goes down with them, and the revive timer starts at that moment;
    //  - a second player joins: a follower already out stays for partyLeaveMs (none at the sheet's 0: it goes in that
    //    step), one not out does not come;
    //  - alone again: it returns once its own timer is spent.
    constexpr bool Tick(Clock& clock, std::uint32_t diff, Situation const& now, Rules const& rules)
    {
        if (!now.hired)
        {
            clock = Clock{};
            return false;
        }
        if (!now.ownerAlive)
        {
            if (!clock.ownerDown)
            {
                clock.ownerDown = true;
                clock.reviveLeftMs = rules.reviveMs;
            }
            Countdown(clock, diff);
            return false;
        }
        clock.ownerDown = false;
        if (now.alone)
            clock.partyMs = 0;
        else
        {
            clock.partyMs = diff >= UINT32_MAX - clock.partyMs ? UINT32_MAX : clock.partyMs + diff;
            if (!now.out || clock.partyMs >= rules.partyLeaveMs)
                return false;
        }
        Countdown(clock, diff);
        return clock.reviveLeftMs == 0;
    }

    // The catch-up: `farMs` counts the time the follower has stood beyond catchUpYards of its player; true once
    // it has stood there catchUpMs, and it starts over.
    constexpr bool CatchUp(std::uint32_t& farMs, std::uint32_t diff, float distance, Rules const& rules)
    {
        if (!(distance > rules.catchUpYards))
        {
            farMs = 0;
            return false;
        }
        farMs = diff >= UINT32_MAX - farMs ? UINT32_MAX : farMs + diff;
        if (farMs < rules.catchUpMs)
            return false;
        farMs = 0;
        return true;
    }

    // What a rule row of the sheet needs to be before the server takes it: the revive and catch-up rules above zero (the
    // party rule may be zero, "at once"; the server checks the row is there).
    constexpr bool Usable(Rules const& rules)
    {
        return rules.reviveMs > 0 && rules.catchUpMs > 0 && rules.catchUpYards > 0.0f;
    }
} // namespace DC::Campaign::Followers

#endif
