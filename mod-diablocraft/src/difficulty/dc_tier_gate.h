#ifndef DC_TIER_GATE_H
#define DC_TIER_GATE_H

#include <cstdint>
#include <string>

// G10 (docs/security.md): a player changes Torment tier only in the hub
// (the difficulty obelisk is gone), and not again inside the cooldown. Pure decision, no
// core types, so the test compiles this very header.
namespace DC::Difficulty
{
// `cooldownMs` 0 means no cooldown (`monsters/tier_change_cooldown_seconds`,
// set to 10 seconds; a blank or zero row disables it).
inline bool TierChangeAllowed(bool inHub, bool hasLast, std::uint64_t lastMs, std::uint64_t nowMs,
                              std::uint64_t cooldownMs, std::string& error)
{
    if (!inHub)
    {
        error = "Choose difficulty in the hub.";
        return false;
    }
    if (hasLast && cooldownMs && nowMs - lastMs < cooldownMs)
    {
        error = "You changed difficulty a moment ago; wait before choosing again.";
        return false;
    }
    return true;
}

// The leader changes tier only when every ONLINE party member
// is in the Sanctum (the hub) and out of combat; SelectTier skips offline members before asking.
inline bool PartyMemberReady(bool inHub, bool inCombat, std::string& error)
{
    if (!inHub)
    {
        error = "All online party members must be in the Sanctum to change difficulty.";
        return false;
    }
    if (inCombat)
    {
        error = "All online party members must be out of combat.";
        return false;
    }
    return true;
}
}

#endif // DC_TIER_GATE_H
