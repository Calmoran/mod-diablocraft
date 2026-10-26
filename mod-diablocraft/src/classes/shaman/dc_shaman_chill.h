#pragma once
// The Shaman's chill: a slow every Shaman skill of the Cold element gives, and the question whether an enemy carries
// one. A chill is the effects file's Slow; "Chilled" is the stock Dazed it puts on, held by this Shaman. Defined in
// dc_shaman_chill.cpp.
class Player;
class Unit;

namespace DC::Combat::Shaman
{
    // A chill of `pct` percent on `target` for `seconds`: the slow of the effects file.
    void Chill(Player* player, Unit* target, double pct, double seconds);
    // Whether `target` is chilled by `player` now.
    bool Chilled(Player* player, Unit const* target);
    // Whether `target` is held by `player` now: the stun hold a Shaman's freeze and stun put on (one hold for both).
    bool Held(Player* player, Unit const* target);
} // namespace DC::Combat::Shaman
