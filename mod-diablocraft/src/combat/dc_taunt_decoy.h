#pragma once
// A decoy a player's skill or item puts down: it stands beside an enemy, holds the taunt on the enemies near it for a
// while, then explodes for weapon damage, for any class's skill or item that does this. The decoy is a summoned unit of
// the player's side (a creature template of data/legendary_summons.csv), the taunt is the core's own taunt aura cast
// from it, and the explosion is the player's own hit. A class includes this and calls Place;
// src/combat/dc_taunt_decoy.cpp defines it.
#include "Position.h"

#include <cstdint>
#include <functional>

class Player;
class Unit;

namespace DC::Combat::TauntDecoy
{
    // What one decoy does. `blastPct` is asked when it goes off, so it can follow a count that moved meanwhile.
    struct Spec
    {
        std::uint32_t entry = 0;          // the decoy's creature template
        std::uint32_t spellId = 0;        // the spell its taunt targets and its explosion hits are dealt under
        double tauntRadius = 0;           // yards from the decoy within which enemies are taunted
        double delaySeconds = 0;          // how long it holds the taunt before it explodes
        double blastRadius = 0;           // yards from the decoy within which the explosion hits
        std::function<double()> blastPct; // the explosion's weapon-damage percent, when it goes off
    };

    // A decoy at `where`, for `owner`: false, and nothing placed, when the spec is not fully set (a zero number) or the
    // summon fails. The decoy and its taunt end with the explosion, or with the owner leaving.
    bool Place(Player* owner, Position const& where, Spec const& spec);
} // namespace DC::Combat::TauntDecoy
