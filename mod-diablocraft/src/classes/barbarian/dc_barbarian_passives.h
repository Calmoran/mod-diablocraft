// What the shared passive code asks the Barbarian's passives; the engine's own calls go through combat/dc_passives.h.
#pragma once
class Player;
class Unit;
namespace DC::Combat::Passives::Barbarian
{
    void RegisterScripts();
    // The slotted or worn passives may have changed (Passives::Invalidate): their contributions are rebuilt at the
    // next update.
    void Changed(Player* player);
    // A hit of the player's landed on `target` (Passives::Hit).
    void Hit(Player* player, Unit* target);
    // The player was hit (Passives::Taken): `school` the hit's school mask, `ranged` whether it was a ranged attack.
    void Taken(Player* player, unsigned school, bool ranged);
} // namespace DC::Combat::Passives::Barbarian
