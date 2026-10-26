#ifndef DC_TIERS_H
#define DC_TIERS_H

#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace DC
{
unsigned LaunchTierCount();
struct Tier
{
    unsigned id = 1, phase = 1;
    std::string name, unlock;
    double health = 1, damage = 1, xpPct = 0, goldPct = 0;
};
struct PartyScaling { double health = 1, damage = 1; };

// Zero is the absence of a requirement, not a default level.
struct TierUnlockRule { unsigned characterLevel = 0, accountLevel = 0, soloGreaterRift = 0; };
TierUnlockRule const& TierUnlock(unsigned tier);
// `beatenSoloGreaterRift` is the highest Greater Rift level this character has beaten in time alone
// (Rifts::GreaterRiftBeatenSolo); a caller that has none to give passes 0, which fails closed for
// every tier that asks for one.
inline bool MeetsTierUnlock(TierUnlockRule const& rule, unsigned level, unsigned accountLevel,
                            unsigned beatenSoloGreaterRift = 0)
{
    return level >= rule.characterLevel && accountLevel >= rule.accountLevel
        && beatenSoloGreaterRift >= rule.soloGreaterRift;
}
bool TierUnlocked(unsigned tier, unsigned level, unsigned accountLevel, unsigned beatenSoloGreaterRift = 0);

// 64-bit Life: a creature's Life is a uint64, the number the core holds (core patch 0027).
// Throws when it is not a number, under 1, or past 2^64 (the worst stock template at GR 150 is 1.6e19).
inline std::uint64_t ScaledCreatureLife(double base, double tier, double party, double elite)
{
    double life = std::floor(base * tier * party * elite);
    if (!std::isfinite(life) || life < 1 || life >= 18446744073709551616.0)
        throw std::out_of_range("Creature Life is outside the 64-bit range");
    return static_cast<std::uint64_t>(life);
}

// What the AutoBalance patch is handed for one creature: `life` the real Life, `health` the multiplier it turns into
// the core's max, floor(moduleBase x health). The +0.5 keeps the floor from landing one under; the multiplier is a
// double, so the max is exactly `life` below 2^52 and within one part in 2^52 of it above.
// `base` is the Life the multipliers multiply: the creature's own, or the one Guardian Life.
struct CreatureScaling
{
    std::uint64_t life = 0;
    double health = 1;
};
inline CreatureScaling ScaleCreatureLife(double moduleBase, double base, double tier, double party, double elite)
{
    CreatureScaling scaling;
    scaling.life = ScaledCreatureLife(base, tier, party, elite);
    scaling.health = (static_cast<double>(scaling.life) + 0.5) / moduleBase;
    return scaling;
}
}
#endif
