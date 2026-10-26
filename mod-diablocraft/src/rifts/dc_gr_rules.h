/*
 * World of DiabloCraft - the six Greater Rift rules and the XP split.
 *
 * The decisions with no core in them: when a run is still locked, how long a death waits, which
 * dungeon objects a Greater Rift refuses, how the XP split scales a kill. The hooks that read
 * players, creatures and objects are dc_gr_rules.cpp; this file is what the test compiles.
 * Internal to the rifts folder.
 */

#ifndef DC_GR_RULES_H
#define DC_GR_RULES_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>

namespace DC::Rifts::Gr
{
    // Rules 4 and 6 hold "until the Guardian is dead": dc_rift.state is open until the Guardian
    // spawns, guardian while it lives, complete once its kill is paid, closed after the run ends.
    inline bool GuardianAlive(std::string const& state)
    {
        return state == "open" || state == "guardian";
    }

    // Rule 5. The wait after the Nth death of one character in one run: the first wait, plus the
    // step for every death after the first, never above the maximum. `step` 0 (the tunable is
    // not set yet) keeps every wait at the first one.
    inline unsigned ReviveWaitSeconds(unsigned deaths, unsigned first, unsigned step, unsigned max)
    {
        if (!deaths)
            return 0;
        unsigned long long const grown = first + static_cast<unsigned long long>(step) * (deaths - 1);
        return static_cast<unsigned>(std::min<unsigned long long>(grown, std::max(first, max)));
    }

    // Whole seconds still to wait, rounded up so "0 seconds" is never shown while the wait runs.
    // Both times are the server's 32-bit ms clock, wrap-safe like dc_gr_ready.h's Expired.
    inline unsigned WaitLeftSeconds(std::uint32_t diedAt, unsigned waitSeconds, std::uint32_t now)
    {
        std::uint64_t const waitMs = static_cast<std::uint64_t>(waitSeconds) * 1000;
        std::uint64_t const elapsed = static_cast<std::uint32_t>(now - diedAt);
        return elapsed >= waitMs ? 0u : static_cast<unsigned>((waitMs - elapsed + 999) / 1000);
    }

    // Rule 3. The dungeon objects a player clicks, by GameobjectTypes value (SharedDefines.h,
    // cross-checked by the test): chests (mining and herb nodes too), goobers (levers, altars,
    // and every shrine-like object), summoning rituals, spell casters and meeting stones.
    // Doors and buttons stay usable, because some pool dungeons need them to be crossed.
    inline bool ClickableDenied(unsigned goType)
    {
        return goType == 3 || goType == 10 || goType == 18 || goType == 22 || goType == 23;
    }

    // Rule 3's exception: the two halves of the caster's own Town Portal are goobers the module
    // summons (rifts_0007), and leaving by one is not a clickable of the dungeon.
    inline bool TownPortalEntry(std::uint32_t entry)
    {
        return entry == 910012 || entry == 910013;
    }

    // The XP split. Monsters give `monsterPct` percent of their normal kill XP and the Guardian
    // `guardianMultiple` times its own. Either number unset (not chosen yet) leaves that
    // kill's XP as it was.
    struct XpSplit
    {
        bool monsterSet = false, guardianSet = false;
        double monsterPct = 100.0, guardianMultiple = 1.0;
    };

    inline std::uint64_t SplitXp(std::uint64_t amount, bool guardian, XpSplit const& split)
    {
        double const factor = guardian ? (split.guardianSet ? split.guardianMultiple : 1.0)
                                       : (split.monsterSet ? split.monsterPct / 100.0 : 1.0);
        if (!(factor >= 0.0) || !std::isfinite(factor))
            return amount; // a negative or broken number is no split
        double const scaled = std::floor(static_cast<double>(amount) * factor);
        return scaled >= 1.8446744073709552e19 ? UINT64_MAX : static_cast<std::uint64_t>(scaled);
    }
} // namespace DC::Rifts::Gr

#endif // DC_GR_RULES_H
