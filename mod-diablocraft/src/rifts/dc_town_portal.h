#pragma once
#include <cstdint>

class Player;

namespace DC::Rifts::TownPortal
{
    // Opens the player's Town Portal pair where it stands, replacing its old one, and moves nobody.
    // False when it cannot open (the player must be alive, out of the hub, and in the open world or a
    // live rift). Revive in town uses it for the way back from a rift (dc_hardcore.cpp).
    bool OpenPair(Player* player);
    void CloseInstance(std::uint32_t instanceId);
    void RegisterScripts();
} // namespace DC::Rifts::TownPortal
