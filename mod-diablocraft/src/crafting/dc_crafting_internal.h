/*
 * World of DiabloCraft - mod-diablocraft
 *
 * crafting: the declarations the crafting files share
 *
 * Internal to src/crafting: declarations only, no logic. The shared helpers (dc_crafting_shared.cpp) and the
 * artisans' entry points that another artisan or the window bridge calls. Other folders include dc_crafting.h.
 */

#ifndef DC_CRAFTING_INTERNAL_H
#define DC_CRAFTING_INTERNAL_H

// Constant (910000): Blacksmith NPC identity; Content identifier. Constant (910001): Mystic NPC identity; Content
// identifier. Constant (910004): Jeweler NPC identity; Content identifier.
#include "dc_crafting_window.h"
#include "dc_cube_window.h"
#include "../items/dc_items.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Player.h"
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace DC::Crafting::Detail
{
    using Amounts = std::map<uint32, uint64>;
    constexpr uint32 Blacksmith = 910000, Mystic = 910001, Jeweler = 910004;
    // Kanai's Cube's template (data/d3/cube_object.csv, world_0042_kanais_cube.sql). The search
    // only finds it: whether the player may use it is the core's own click reach (CubeInReach), as the rift code finds
    // its obelisk (dc_rifts.cpp OBELISK_SEARCH_YARDS); the Sanctum has one Cube in its one shared phase.
    constexpr uint32 KanaisCube = 910047;
    // dc_crafting_shared.cpp
    bool AccountMaterial(uint32 entry);
    void Need(bool ok, char const* message);
    uint32 TunableCount(char const* name);
    uint32 SourcedCount(char const* name);
    std::string Escape(std::string value);
    void Reachable(Player* player);
    Creature* Artisan(Player* player, uint32 entry);
    void CubeInReach(Player* player);
    std::vector<Item*> Inventory(Player* player);
    Item* Owned(Player* player, uint32 guid);
    Items::Instance Rolled(Item* item);
    void Save(Player* player, CharacterDatabaseTransaction transaction);
    std::string MaterialName(uint32 entry);
    bool Enough(Player* player, uint32 entry, uint64 count);
    uint64 Held(Player* player, uint32 entry);
    void CheckMaterials(Player* player, Amounts const& amounts);
    void SpendMaterials(Player* player, Amounts const& amounts);
    void CheckRoom(Player* player, Amounts const& amounts);
    void Grant(Player* player, Amounts const& amounts);
    void AffixRow(CharacterDatabaseTransaction const& tx, uint64 guid, Items::Affix const& a);
    Items::Affix const& Affix(Items::Instance const& item, uint32 seq);
    bool IsGemEntry(uint32 entry);
    void GrantGem(Player* player, Items::Affix const& socketed, CharacterDatabaseTransaction const& tx);
    void Salvage(Player* player, uint32 guid, uint32 rarity);
    void Craft(Player* player, uint32 id, uint32 count, bool mapped = false, bool jewelry = false);
    // dc_mystic.cpp
    Window::EnchantState MysticState(Player* player, uint32 guid);
    std::vector<Window::EnchantAffix> MysticPreview(Player* player, uint32 guid, uint32 seq);
    void Roll(Player* player, uint32 guid, uint32 seq);
    void Pick(Player* player, uint32 guid, uint32 choice);
    void Describe(Player* player, uint32 guid);
    // dc_jeweler.cpp
    void Socket(Player* player, uint32 guid, uint32 seq, uint32 gemGuid);
    void Combine(Player* player, uint32 output, uint32 count = 1);
    // dc_repair.cpp
    std::vector<Item*> RepairSelection(Player* player, uint32 scope, uint32 guid);
    uint64 RepairTotal(Player* player, Creature* npc, std::vector<Item*> const& items);
    void Repair(Player* player, Creature* npc, Item* only = nullptr, bool equippedOnly = false);
    // dc_cube.cpp
    Cube::Recipes CubeRecipes();
    std::vector<Window::CubeSlot> CubeSlots(Player* player);
    std::vector<Window::CubePower> CubePowers(Player* player, uint32 slot);
    std::optional<Window::CubePowerText> CubePowerText(uint32 entry);
    void ChooseCubePower(Player* player, uint32 slot, uint32 entry);
    std::string CubeGemClass(Player* player, uint32 guid);
    void Transmute(Player* player, std::string const& id, uint32 guid, std::vector<Cube::Cell> const& gems);
    // Called from RegisterScripts, in its order.
    void RegisterCubeScripts();
    void RegisterRepairScripts();
} // namespace DC::Crafting::Detail

#endif // DC_CRAFTING_INTERNAL_H
