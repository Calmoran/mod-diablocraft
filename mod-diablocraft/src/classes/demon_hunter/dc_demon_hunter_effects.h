#pragma once
// The holds on an enemy that the Demon Hunter's skills put: what more than one skill of the class calls. Defined in
// dc_demon_hunter_effects.cpp.
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::DemonHunter
{
    // A slow of `pct` percent on `target` for `seconds` (stock "Dazed", one MOD_DECREASE_SPEED effect): a second one
    // restarts it. Nothing for no percent, no seconds, an enemy that is dead or a slow it is immune to.
    void Slow(Player* player, Unit* target, double pct, double seconds);
    // Takes off the slow `player` put on `target` before its seconds are up. Nothing when there is none.
    void Unslow(Player* player, Unit* target);
    // A stun of `seconds` on `target` (stock "Ice Blast", one MOD_STUN effect): a second one restarts it. A freeze is a
    // stun. The caller stretches `seconds` by ItemPowers::StunFactor.
    void Stun(Player* player, Unit* target, double seconds);
    // `player` becomes invisible to enemies for `seconds` (stock "Super Invis", one MOD_INVISIBILITY effect that
    // nothing breaks): a second one restarts it. Nothing for no seconds.
    void Vanish(Player* player, double seconds);
    // An Immobilize of `seconds` on `target` (stock "Earthgrab", one MOD_ROOT effect): a second one restarts it.
    void Root(Player* player, Unit* target, double seconds);
    // `amount` Life given to `player` as a heal of `spellId`. Nothing
    // for no Life, or a Demon Hunter that is dead.
    void Heal(Player* player, std::uint32_t spellId, double amount);
} // namespace DC::Combat::DemonHunter
