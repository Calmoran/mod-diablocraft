/*
 * World of DiabloCraft - Greater Rift level per character.
 *
 * The store the later parts read: the highest Greater Rift level a character has
 * unlocked and the highest it has beaten, per realm mode. The level of one run is
 * dc_rift.gr_rank (Rift::grRank). Internal to the rifts folder.
 */

#ifndef DC_GR_LEVEL_H
#define DC_GR_LEVEL_H

#include <cstdint>
#include <string>

namespace DC::Rifts
{
    // `beaten` 0 means none. A character with no row is {start level, 0}; the start level
    // and the cap are the rifts tunables greater_rift_start_level / greater_rift_max_level,
    // and a stored row is held inside them on every read.
    struct GrLevels
    {
        unsigned unlocked = 1, beaten = 0;
    };

    GrLevels GreaterRiftLevels(std::uint32_t guid);

    // Writes both numbers. Refuses (false, `error` filled) an unlocked level outside the
    // tunables' start..cap, or a beaten level above the unlocked one.
    bool SetGreaterRiftLevels(std::uint32_t guid, unsigned unlocked, unsigned beaten, std::string& error);

    // GreaterRiftBeatenSolo, the highest level beaten in time alone, is on dc_rifts.h's public
    // surface: the difficulty module reads it for Torment VII to XVI.
    // A run of `level` was beaten in time with `secondsLeft` on the clock: raises this character's
    // numbers (dc_gr_unlock.h Beat; the bonus is the rifts.csv gr_unlock_plus_N rows) and says what
    // they were and are. Never lowers anything, so a repeat changes nothing.
    struct GrUnlock
    {
        GrLevels before, after;
    };
    GrUnlock RecordGreaterRiftBeaten(std::uint32_t guid, unsigned level, unsigned secondsLeft, bool solo);

    void RegisterGreaterRiftLevelScripts();
} // namespace DC::Rifts

#endif // DC_GR_LEVEL_H
