#pragma once
// The forced movement of an enemy that any class's skill may give: a shove away from the caster and a pull toward a
// point. Both ride the stock jump at the module's two knockback speeds (the ability_knockback_speed_xy and _z
// tunables); a class includes this and calls these, and src/combat/dc_movement_effects.cpp defines them.
class Player;
class Position;
class Unit;

namespace DC::Combat::Abilities
{
    // `yards` straight away from `player`. Nothing for a rooted enemy or a landing out of sight, and nothing while the
    // speeds are not tuned.
    void Knock(Player* player, Unit* target, double yards);
    // `target` drawn to `point`. Nothing for a rooted enemy or a point out of sight, and nothing while the speeds are
    // not tuned.
    void Pull(Unit* target, Position const& point);
    // The shove a skill gives: Knock under the name the other classes call.
    void Knockback(Player* player, Unit* target, double yards);
    // The pull a skill gives: `target` drawn to a point `yards` in front of `player`.
    void PullToward(Player* player, Unit* target, double yards);

    void RegisterMovementScripts();
} // namespace DC::Combat::Abilities
