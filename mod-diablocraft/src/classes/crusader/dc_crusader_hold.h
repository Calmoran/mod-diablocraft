#pragma once
// A place held shut: an enemy seen on one side of the edge of a circle is put back where it was seen when a later look finds
// it on the other. The production half is dc_crusader_hold.cpp.
#include <cstdint>

class Player;
struct Position;

namespace DC::Combat::Crusader::Hold
{
    // Holds the circle of `radius` yards round `where` for `seconds`, so no enemy goes in or out: a look every
    // `checkSeconds` (never under a tenth of a second). Nothing for a radius or seconds of 0.
    void Place(Player* player, std::uint32_t spellId, Position where, double radius, double seconds, double checkSeconds);
} // namespace DC::Combat::Crusader::Hold
