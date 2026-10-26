/*
 * World of DiabloCraft - the allies a legendary item summons (N-SUMMON).
 *
 * The creature templates are generated from data/legendary_summons.csv; this is their AI and the one hook
 * the power that summons them uses. Contract: docs/contracts/legendary-world-pieces.md.
 */

#ifndef DC_ALLY_H
#define DC_ALLY_H

#include <cstdint>
#include <functional>
#include <string_view>

class Creature;
class Player;
class Unit;

namespace DC::Rifts::Ally
{
    // The two ScriptNames of data/legendary_summons.csv (generate_legendary_summons.py checks the sheet against them).
    constexpr std::string_view Fighting = "dc_legendary_ally", Pawn = "dc_legendary_pawn";

    // Creature entries 900120-900128, one per ally (the sheet is the list of names).
    constexpr std::uint32_t FirstEntry = 900120, Count = 9;
    // A set's decoy, the ninth (a pawn: the 4-piece puts it down and Combat drives it).
    constexpr std::uint32_t DecoyEntry = 900128;
    constexpr bool IsAllyEntry(std::uint32_t entry)
    {
        return entry >= FirstEntry && entry < FirstEntry + Count;
    }

    // Our own allies are not monsters of the tier: difficulty scaling leaves them alone, as it leaves a pet.
    constexpr bool IsAllyScript(std::string_view script)
    {
        return script == Fighting || script == Pawn;
    }

    // What a fighting ally does each time it swings: the damage is the power's, never the ally's own melee.
    // Called every `intervalMs` while the ally stands within melee range of the target it chose, with the ally,
    // its owner (online, alive, same map) and the target (alive, attackable by the owner).
    using Swing = std::function<void(Creature& ally, Player& owner, Unit& target)>;

    // Registers the swing of one entry. At startup only (from the power's RegisterScripts); the ally reads the
    // table without a lock. A second call for an entry replaces the first. An entry with no swing follows and
    // chases and deals nothing.
    void OnSwing(std::uint32_t entry, std::uint32_t intervalMs, Swing swing);

    void RegisterScripts();
} // namespace DC::Rifts::Ally

#endif
