#ifndef DC_GROUND_LOOT_H
#define DC_GROUND_LOOT_H
#include <cstdint>
#include <string>
class Player;
class Creature;
struct Position;
namespace DC::Loot
{
bool GroundDeliveryEnabled();
unsigned BossMaterialCount();
bool DropGroundLoot(Player*, std::uint32_t entry, unsigned itemLevel, std::string const& rarity,
                    char const* source, unsigned tier, char const* contentKind, unsigned count,
                    Position const& position, std::string const& rollClass = "",
                    std::string const& quality = "normal");
// Pays a ground carrier's row. storeError receives the core's own InventoryResult
// when the store refused it (see ClaimCorpseRow); it is EQUIP_ERR_OK otherwise.
bool ClaimGroundLoot(Player*, Creature*, std::uint8_t* storeError = nullptr);
void LoseGroundLoot(std::uint64_t carrier, std::uint32_t mapId, std::uint32_t instanceId);
void LosePlayerGroundLoot(Player*);
void RegisterGroundLootScripts();
}
#endif
