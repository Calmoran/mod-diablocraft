#pragma once
// The Shaman's free Lava Burst: a state that Elemental Lash's Lava Surge rune gives and that the next Lava Burst spends
// to cost nothing. One state per Shaman, so a second Lava Surge before the Lava Burst changes nothing. Defined in
// dc_shaman_free_lava_burst.cpp.
class Player;

namespace DC::Combat::Shaman::FreeLavaBurst
{
    // The next Lava Burst of `player` is free.
    void Grant(Player* player);
    // Whether the next Lava Burst of `player` is free.
    bool Pending(Player const* player);
    // The Lava Burst was cast free: the state is spent. Nothing if it was not there.
    void Spend(Player* player);
} // namespace DC::Combat::Shaman::FreeLavaBurst
