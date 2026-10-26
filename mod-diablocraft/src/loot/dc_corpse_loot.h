#ifndef DC_CORPSE_LOOT_H
#define DC_CORPSE_LOOT_H
#include "ObjectGuid.h"
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
class Player;
class Creature;
namespace DC::Loot
{
    // Personal corpse loot (docs/proposals/corpse-loot-minimum.md). A kill's
    // drops are each player's rows on the corpse (dc_loot_buffer, kind 'corpse');
    // the module answers the stock loot window with only the looter's rows.

    // The corpse can hold rows: migration applied, dead, tagged, loot mode on.
    bool CorpseCanHold(Creature const* corpse);

    // One drop as one row of `owner` on `corpse`. Inside an economy scope the row
    // commits with it and is shown after the commit; outside one it commits here.
    bool DropCorpseLoot(Player* owner, Creature* corpse, std::uint32_t entry, unsigned itemLevel,
                        std::string const& rarity, char const* source, unsigned tier, char const* contentKind,
                        unsigned count, std::string const& rollClass = "",
                        std::string const& quality = "normal");

    // Players who may loot this corpse but were not paid when it died (the rift Guardian's party members who were not
    // on its floor, rift floors F7). `pay` runs once for each of them, the first time they open the corpse, on their
    // own map thread; it returns whether it committed, and a player whose pay did not commit stays owed. The corpse
    // stays open while anyone is owed, until it decays or its rift closes. False when the corpse cannot hold loot.
    using OwedPay = std::function<bool(Player*, Creature*)>;
    bool OweCorpse(Creature* corpse, std::vector<ObjectGuid> const& owed, OwedPay pay);

    // The corpse still holds rows; the death hook keeps its window alive.
    bool CorpseHoldsRows(Creature const* corpse);
    void KeepCorpseLootable(Creature* corpse);

    void RegisterCorpseLootScripts();
} // namespace DC::Loot
#endif
