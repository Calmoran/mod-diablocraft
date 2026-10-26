// Items: legendary gems as items (the table, the gift, the rank, who wears which) and the field socket path.
// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (65536): cap on affix rows per item instance; Storage bound.
#include "dc_items_internal.h"

#include "dc_legendary_gem_item.h"

#include "../hardcore/dc_hardcore.h"

#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Player.h"
#include "WorldSession.h"

#include <algorithm>
#include <mutex>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Items
{
using namespace Detail;

// --- legendary gems as items ------------------------------------------------
namespace
{
// The 21 templates never change while the server runs, so the table loads once.
std::unordered_map<std::uint32_t, LegendaryGemItem> const& LegendaryGemTable()
{
    static std::once_flag once;
    static std::unordered_map<std::uint32_t, LegendaryGemItem> items;
    std::call_once(once, []
    {
        if (QueryResult rows = WorldDatabase.Query("SELECT entry,gem_id,socket_slots FROM dc_legendary_gem_item"))
            do
            {
                Field* f = rows->Fetch();
                items[f[0].Get<uint32>()] = {f[1].Get<std::string>(), f[2].Get<std::string>()};
            } while (rows->NextRow());
    });
    return items;
}
} // namespace

std::optional<LegendaryGemItem> LegendaryGemItemOf(std::uint32_t entry)
{
    auto const& items = LegendaryGemTable();
    auto found = items.find(entry);
    if (found == items.end())
        return std::nullopt;
    return found->second;
}

std::vector<std::uint32_t> UnownedLegendaryGems(Player* player)
{
    std::set<std::uint32_t> owned;
    auto const& table = LegendaryGemTable();
    if (!player || !player->GetSession())
        return {};
    // The bags and what is worn, as the server holds them now (a gem picked up a moment ago is not saved yet)...
    for (auto const& gem : table)
        if (player->GetItemByEntry(gem.first))
            owned.insert(gem.first);
    // ...then what the database knows: everything the character owns (the bank too), the gems socketed in
    // those items, and the same two in the account's stash for this character's mode.
    char const* const mode = DC::Hardcore::ModeOf(player) == DC::Hardcore::Mode::Hardcore ? "hardcore" : "normal";
    std::uint32_t const account = player->GetSession()->GetAccountId();
    std::uint64_t const guid = player->GetGUID().GetCounter();
    std::string entries;
    for (auto const& gem : table)
        entries += (entries.empty() ? "" : ",") + std::to_string(gem.first);
    if (entries.empty())
        return {};
    if (QueryResult rows = CharacterDatabase.Query(
            "SELECT itemEntry FROM item_instance WHERE owner_guid={} AND itemEntry IN (" + entries + ") "
            "UNION SELECT a.gem_entry FROM dc_item_affix a JOIN item_instance i ON i.guid=a.item_guid "
            "WHERE i.owner_guid={} AND a.kind='gem' AND a.legendary_rank IS NOT NULL "
            "UNION SELECT i.itemEntry FROM dc_account_stash_item s JOIN item_instance i ON i.guid=s.item_guid "
            "WHERE s.account_id={} AND s.mode='{}' AND i.itemEntry IN (" + entries + ") "
            "UNION SELECT a.gem_entry FROM dc_account_stash_item s JOIN dc_item_affix a ON a.item_guid=s.item_guid "
            "WHERE s.account_id={} AND s.mode='{}' AND a.kind='gem' AND a.legendary_rank IS NOT NULL",
            guid, guid, account, mode, account, mode))
        do
            owned.insert((*rows)[0].Get<uint32>());
        while (rows->NextRow());
    std::vector<std::uint32_t> unowned;
    for (auto const& gem : table)
        if (!owned.count(gem.first))
            unowned.push_back(gem.first);
    std::sort(unowned.begin(), unowned.end());
    return unowned;
}

std::uint32_t LegendaryGemRankOf(std::uint64_t itemGuid)
{
    QueryResult row = CharacterDatabase.Query("SELECT gem_rank FROM dc_legendary_gem_rank WHERE item_guid={}", itemGuid);
    return row ? (*row)[0].Get<uint32>() : 0;
}

bool LegendaryGemFits(std::uint32_t baseItem, LegendaryGemItem const& gem)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    auto base = baseItems.find(baseItem);
    return base != baseItems.end() && DC::LegendaryGemItem::SlotAllowed(gem.socketSlots, base->second.slot);
}

Item* GiveLegendaryGem(Player* player, std::uint32_t entry, std::uint32_t rank,
                       CharacterDatabaseTransaction const& transaction)
{
    ItemPosCountVec destination;
    if (player->CanStoreNewItem(NULL_BAG, NULL_SLOT, destination, entry, 1) != EQUIP_ERR_OK)
        return nullptr;
    Item* gem = player->StoreNewItem(destination, entry, true);
    if (!gem)
        return nullptr;
    transaction->Append("REPLACE INTO dc_legendary_gem_rank(item_guid,gem_rank) VALUES({},{})",
                        gem->GetGUID().GetCounter(), rank);
    return gem;
}

void AppendGemRow(CharacterDatabaseTransaction const& transaction, std::uint64_t itemGuid, unsigned seq,
                  std::string const& gemId, unsigned parentSeq, std::uint32_t gemEntry, unsigned gemRank,
                  std::optional<std::uint32_t> legendaryRank)
{
    transaction->Append("INSERT INTO dc_item_affix(item_guid,seq,affix_id,value,range_min,range_max,kind,rerolled,"
                        "parent_seq,gem_entry,gem_rank,legendary_rank) VALUES({},{},'{}',0,0,0,'gem',0,{},{},{},{})",
                        itemGuid, seq, Escape(gemId), parentSeq, gemEntry, gemRank,
                        legendaryRank ? std::to_string(*legendaryRank) : std::string("NULL"));
}

std::vector<CountedLegendaryGem> CountedLegendaryGems(Player* player)
{
    std::vector<DC::LegendaryGemItem::Socketed> worn;
    for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
        if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
            if (std::optional<Instance> instance = Get(item->GetGUID().GetCounter()))
                for (Affix const& affix : instance->affixes)
                    if (affix.kind == "gem" && affix.legendaryRank)
                        worn.push_back({affix.affixId, *affix.legendaryRank});
    std::vector<CountedLegendaryGem> counted;
    for (auto const& gem : DC::LegendaryGemItem::Counted(worn))
        counted.push_back({gem.gemId, gem.rank});
    return counted;
}

Item* WornLegendaryGem(Player* player, std::string const& gemId, std::vector<std::uint64_t> const& leaving,
                       std::optional<std::pair<std::uint64_t, unsigned>> replaced)
{
    std::vector<DC::LegendaryGemItem::WornGem> worn;
    std::unordered_map<std::uint64_t, Item*> holders;
    for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
        if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
            if (std::optional<Instance> instance = Get(item->GetGUID().GetCounter()))
                for (Affix const& affix : instance->affixes)
                    if (affix.kind == "gem" && affix.legendaryRank)
                    {
                        worn.push_back({affix.affixId, item->GetGUID().GetCounter(), affix.seq});
                        holders[item->GetGUID().GetCounter()] = item;
                    }
    DC::LegendaryGemItem::WornGem const* copy = DC::LegendaryGemItem::WornCopy(worn, gemId, leaving, replaced);
    return copy ? holders[copy->item] : nullptr;
}

std::string LegendaryGemName(std::string const& gemId)
{
    QueryResult row = WorldDatabase.Query("SELECT gem_name FROM dc_legendary_gem WHERE gem_id='{}'", Escape(gemId));
    return row ? (*row)[0].Get<std::string>() : gemId;
}

namespace
{
Item* Carried(Player* player, std::uint32_t guid, char const* missing)
{
    Item* item = player->GetItemByGuid(ObjectGuid(HighGuid::Item, guid));
    NeedItem(item && item->GetOwnerGUID() == player->GetGUID() && !item->IsInTrade(), missing);
    NeedItem(Player::IsInventoryPos(item->GetPos()) || Player::IsEquipmentPos(item->GetPos()),
             "Move the item out of the bank first.");
    return item;
}
}

namespace Detail
{
// --- socketing in the field ------------------------------------------------
//
// The Jeweler's own Socket() (dc_jeweler.cpp) is untouched and keeps
// UNsocketing and combining, which stay his. This is the WoW-style field path
// for putting a gem IN, anywhere, with the same
// validation minus standing at the artisan. It costs nothing, which is why it
// needs no PlayerEconomy scope: the Jeweler charges nothing for socketing
// either.
//
// The client sends two item guids and decides nothing else. Which socket row
// the gem lands in is picked here, and every rule is checked here.
void NeedItem(bool ok, char const* message)
{
    if (!ok)
        throw std::runtime_error(message);
}

void SocketInField(Player* player, std::uint32_t itemGuid, std::uint32_t gemGuid)
{
    NeedItem(player && player->GetSession(), "No character.");
    // Socketing is open to every class.
    NeedItem(player->IsAlive(), "You must be alive to socket a gem.");
    NeedItem(!player->IsInCombat() && !player->GetTradeData(), "Finish combat or trading first.");
    NeedItem(itemGuid != gemGuid, "Choose a gem and an item to put it in.");
    Item* item = Carried(player, itemGuid, "That item is no longer yours or is being traded.");
    Item* gem = Carried(player, gemGuid, "That gem is no longer yours or is being traded.");
    NeedItem(!gem->IsEquipped(), "Choose a gem in your bags.");

    std::optional<Instance> instance = Get(itemGuid);
    NeedItem(!IsShellTemplate(item->GetEntry()), "Identify it first.");
    NeedItem(bool(instance), "Choose a rolled item.");
    // The Mystic's paid offer can be about to replace the socket affix itself,
    // so it is resolved before a gem may land in one. The Jeweler's rule.
    NeedItem(!CharacterDatabase.Query("SELECT 1 FROM dc_enchant_offer WHERE item_guid={}", itemGuid),
             "Resolve the paid enchant offer at the Mystic first.");

    unsigned next = 0, sockets = 0;
    int target = -1;
    for (Affix const& affix : instance->affixes)
        next = std::max(next, affix.seq + 1);
    for (Affix const& affix : instance->affixes)
    {
        if (affix.kind != "socket")
            continue;
        ++sockets;
        if (target >= 0)
            continue;
        bool filled = false;
        for (Affix const& child : instance->affixes)
            if (child.kind == "gem" && child.parentSeq == int(affix.seq))
            {
                filled = true;
                break;
            }
        if (!filled)
            target = int(affix.seq);
    }
    NeedItem(sockets > 0, "That item has no sockets.");
    NeedItem(target >= 0, "Every socket on that item is full. The Jeweler removes a gem.");
    NeedItem(next < 65536, "Too many affix rows.");

    std::string gemId;
    std::uint32_t gemRank = 0;
    std::optional<std::uint32_t> legendaryRank;
    if (std::optional<LegendaryGemItem> legendary = LegendaryGemItemOf(gem->GetEntry()))
    {
        // The gem keeps its own rank, in a field of its own.
        NeedItem(LegendaryGemFits(instance->baseItem, *legendary), "That gem does not fit this kind of item.");
        // Unique Equipped: not while the same gem is socketed in what is worn.
        if (Item* holder = WornLegendaryGem(player, legendary->gemId))
            NeedItem(false, (LegendaryGemName(legendary->gemId) + " is already socketed in your " +
                             holder->GetTemplate()->Name1 + ". A legendary gem can be worn only once (Unique Equipped).")
                                .c_str());
        gemId = legendary->gemId;
        legendaryRank = LegendaryGemRankOf(gem->GetGUID().GetCounter());
    }
    else
    {
        QueryResult data = WorldDatabase.Query("SELECT gem_id,`rank` FROM dc_gem_item WHERE entry={}", gem->GetEntry());
        NeedItem(bool(data), "Choose a gem.");
        gemId = (*data)[0].Get<std::string>();
        gemRank = (*data)[1].Get<uint32>();
    }
    std::uint32_t const gemEntry = gem->GetEntry();

    // The contribution comes off before the rows change and goes back on after
    // the write is durable: Apply() re-reads the rows from the database every
    // time (Load, above), so the order is what keeps the sheet honest. Same as
    // the Jeweler.
    RemoveContributions(player, item);
    std::uint32_t count = 1;
    player->DestroyItemCount(gem, count, true);
    CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
    AppendGemRow(transaction, itemGuid, next, gemId, target, gemEntry, gemRank, legendaryRank);
    player->SaveInventoryAndGoldToDB(transaction);
    // Async, never DirectCommitTransaction: the core prepares the inventory
    // statements this carries on the worker connections only, and a direct
    // commit asserts on the synchronous one (dc_stash.cpp Commit has the rest).
    if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
    {
        RefreshContributions(player, item);
        throw std::runtime_error("That gem could not be socketed. Relog before trying again.");
    }
    RefreshContributions(player, item);
    ChatHandler(player->GetSession()).SendSysMessage("Gem socketed.");
}
}
}
