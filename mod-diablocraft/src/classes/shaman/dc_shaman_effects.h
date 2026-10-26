#pragma once
// The holds the Shaman's skills put on an enemy and the small pieces more than one skill calls. Each hold is a stock
// aura of a few seconds on the enemy, so control immunity answers nothing and the core shows it as it shows any other.
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::Shaman
{
    // A stun of `seconds` on `target` (stock "Ice Blast": one MOD_STUN effect).
    void Stun(Player* player, Unit* target, double seconds);
    // A root of `seconds` on `target`: held in place, free to fight (stock "Earthgrab": one MOD_ROOT effect).
    void Root(Player* player, Unit* target, double seconds);
    // A freeze of `seconds`: held in place (the same stock stun, the module's one hold for a frozen enemy).
    void Freeze(Player* player, Unit* target, double seconds);
    // A slow of `pct` percent for `seconds` (stock "Dazed": one MOD_DECREASE_SPEED effect). Nothing for no percent.
    void Slow(Player* player, Unit* target, double pct, double seconds);
    // `amount` of Life healed to the Shaman by the spell `spellId`, through the core's own heal.
    void Heal(Player* player, std::uint32_t spellId, double amount);
    // Whether `enemy` is an elite or a boss: a native elite, a champion or rare pack's monster, a Rift Guardian.
    bool IsElite(Unit const* enemy);
} // namespace DC::Combat::Shaman
