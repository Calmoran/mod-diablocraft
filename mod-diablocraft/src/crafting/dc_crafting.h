/*
 * World of DiabloCraft - mod-diablocraft
 *
 * crafting: salvage, blacksmith, jeweler, mystic, cube
 *
 * Public surface of the crafting folder. Other folders include only this header.
 * Artisan operations and stat mutations stay on the C++ side.
 */

#ifndef DC_CRAFTING_H
#define DC_CRAFTING_H

#include <cstdint>
class Player;
namespace DC::Crafting
{
    void RegisterScripts();
    // Normal monster gems only; zero means no drop. Data and tuning belong here.
    std::uint32_t RollGemEntry(unsigned monsterLevel, unsigned tier);
} // namespace DC::Crafting

#endif // DC_CRAFTING_H
