#pragma once
// The holds on an enemy that the Witch Doctor's skills put, and its heal: what more than one skill of the class calls. Defined in
// dc_witch_doctor_effects.cpp.
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor
{
    // The enemy Feared for `seconds` (stock "Fear", one MOD_FEAR effect): it runs from the Witch Doctor. True when the
    // fear took hold: an enemy the core's immunity turns away answers false.
    bool Fear(Player* player, Unit* target, double seconds);
    // An Immobilize of `seconds` on `target` (stock "Earthgrab", one MOD_ROOT effect). True when the root took hold.
    bool Root(Player* player, Unit* target, double seconds);
    // The enemy hexed for `seconds`: turned into a chicken that cannot attack or cast (stock "Polymorph: Chicken", a transform, a
    // silence and a cut of the damage it deals, and stock "Pacify", one MOD_PACIFY). Damage does not end it. True when the
    // chicken took hold.
    bool HexEnemy(Player* player, Unit* target, double seconds);
    // The Witch Doctor turned into an angry chicken for `seconds` (stock "Chicken", one TRANSFORM effect, and Pacify): it cannot
    // melee. `EndChicken` ends it at once.
    void TurnIntoChicken(Player* player, double seconds);
    void EndChicken(Player* player);
    // A slow of `pct` percent on `target` for `seconds` (stock "Dazed", one MOD_DECREASE_SPEED effect): a second one
    // restarts it. Nothing for no percent, no seconds or an enemy that is dead.
    void Slow(Player* player, Unit* target, double pct, double seconds);
    // The enemy confused for `seconds` (stock "Dizzy", one MOD_CONFUSE effect): it wanders and does not attack. Nothing for no seconds or an enemy
    // that is dead.
    void Confuse(Player* player, Unit* target, double seconds);
    // A stun of `seconds` on `target` (stock "Ice Blast", one MOD_STUN effect): a second one restarts it. A freeze is a
    // stun. The caller stretches `seconds` by ItemPowers::StunFactor.
    void Stun(Player* player, Unit* target, double seconds);
    // `amount` of Life healed to the Witch Doctor by the spell `spellId`, through the core's own heal. Nothing for no amount or a dead
    // Witch Doctor.
    void Heal(Player* player, std::uint32_t spellId, double amount);
    // Every point of damage `player` would take, of any school, absorbed for `seconds` (the stock Power Word: Shield with the amount
    // set past any hit): the Witch Doctor takes no damage while it lasts. Nothing for no seconds or a Witch Doctor that is dead.
    void Invulnerable(Player* player, double seconds);
} // namespace DC::Combat::WitchDoctor
