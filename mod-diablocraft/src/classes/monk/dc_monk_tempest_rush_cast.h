#pragma once
// Tempest Rush: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_tempest_rush.h.
#include "dc_monk.h"

namespace DC::Combat::Monk::TempestRush
{
    // Whether `spellId` is Tempest Rush or one of its runes.
    bool Is(std::uint32_t spellId);
    // The press while the channel runs stops it (and is refused, so it costs nothing): true when it stopped one.
    bool Toggle(Player* player, std::uint32_t spellId);
    // The channel's weapon damage per second, for the loader that gives every shell its hit: Electric Field's and Flurry's own
    // damage_pct are for their extras, so the channel itself stays the skill's. nullopt for any other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The press that starts: the weapon damage the first tick deals through the cast's own hit.
    Punch Begin(Player* player, std::uint32_t spellId);
    // After that hit: the channel begins.
    void Cast(Player* player, std::uint32_t spellId);
    // End the channel now (the stop message of the hold-to-channel list will call this).
    void Stop(Player* player);
} // namespace DC::Combat::Monk::TempestRush
