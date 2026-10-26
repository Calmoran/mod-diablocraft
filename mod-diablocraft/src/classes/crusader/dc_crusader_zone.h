#pragma once
// A ground zone of the Crusader's: a place that strikes the enemies standing in it a number of times, one tick apart
// ("takes {damage_pct} weapon damage every second", "{damage_pct} weapon damage over {seconds} seconds"). The rule that
// needs no core type is the burn's (dc_crusader_dot.h Ticks and TickPct); the production half is dc_crusader_zone.cpp.
#include <cstdint>

class Player;
struct Position;

namespace DC::Combat::Crusader::Zone
{
    // Lays a zone of `spellId` at `where`: every `tickSeconds` for `seconds`, each enemy within `radius` yards of it is
    // struck for `pctPerTick` of weapon damage (the first tick a tick in). Nothing for a tick length or seconds of 0 or
    // a radius of 0.
    void Lay(Player* player, std::uint32_t spellId, Position where, double radius, double pctPerTick, double seconds,
             double tickSeconds);
} // namespace DC::Combat::Crusader::Zone
