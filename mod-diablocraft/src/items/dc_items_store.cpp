// Items: the item rows (load, erase), the unidentified shells' rows and the destroy path that takes them along.
#include "dc_items_internal.h"

#include "DatabaseEnv.h"
#include "Item.h"
#include "Player.h"

#include <algorithm>
#include <mutex>
#include <optional>
#include <string>

namespace DC::Items
{
namespace
{
thread_local CharacterDatabaseTransaction removalTransaction;
}

namespace Detail
{
// --- persistence -----------------------------------------------------------
std::optional<Instance> Load(std::uint64_t itemGuid)
{
    QueryResult head = CharacterDatabase.Query(
        "SELECT base_item,quality_tier,rarity,enchant_locked,enchant_attempts,crafted,bound_account FROM dc_item_instance WHERE item_guid={}", itemGuid);
    if (!head)
        return std::nullopt;
    Instance instance;
    instance.itemGuid = itemGuid;
    instance.baseItem = (*head)[0].Get<uint32>();
    instance.qualityTier = (*head)[1].Get<std::string>();
    instance.rarity = (*head)[2].Get<std::string>();
    instance.enchantLocked = (*head)[3].Get<uint8>() != 0;
    instance.enchantAttempts = (*head)[4].Get<uint32>();
    instance.crafted = (*head)[5].Get<uint8>() != 0;
    instance.boundAccount = (*head)[6].Get<uint32>();
    BackfillPowers(itemGuid, instance.baseItem, instance.qualityTier);
    if (QueryResult rows = CharacterDatabase.Query(
            "SELECT seq, affix_id, value, range_min, range_max, kind, rerolled,COALESCE(parent_seq,-1),COALESCE(gem_entry,0),gem_rank, "
            "value2, range_min2, range_max2, legendary_rank FROM dc_item_affix WHERE item_guid={} ORDER BY seq", itemGuid))
    {
        do
        {
            Field* fields = rows->Fetch();
            Affix affix;
            affix.seq = fields[0].Get<uint16>();
            affix.affixId = fields[1].Get<std::string>();
            affix.value = fields[2].Get<double>();
            affix.rangeMin = fields[3].Get<double>();
            affix.rangeMax = fields[4].Get<double>();
            affix.kind = fields[5].Get<std::string>();
            affix.rerolled = fields[6].Get<uint8>() != 0;
            affix.parentSeq = fields[7].Get<int32>();
            affix.gemEntry = fields[8].Get<uint32>();
            affix.gemRank = fields[9].Get<uint32>();
            affix.value2 = fields[10].Get<double>();
            affix.rangeMin2 = fields[11].Get<double>();
            affix.rangeMax2 = fields[12].Get<double>();
            if (!fields[13].IsNull())
                affix.legendaryRank = fields[13].Get<uint32>();
            instance.affixes.push_back(affix);
        } while (rows->NextRow());
    }
    // Display names live in the world-side pool, not on the instance row.
    std::lock_guard<std::mutex> lock(dataMutex);
    auto base = baseItems.find(instance.baseItem);
    if (base != baseItems.end())
    {
        // The slot's pool, then the lines of the base's own type ("<slot>:<type>": the Totem's Maximum Maelstrom).
        for (std::string const& key : {base->second.slot, base->second.slot + ":" + base->second.type})
            if (auto slot = pools.find(key); slot != pools.end())
                for (Affix& affix : instance.affixes)
                    for (auto const& [bracket, entries] : slot->second)
                    {
                        auto found = std::find_if(entries.begin(), entries.end(),
                            [&](PoolEntry const& entry) { return entry.affixId == affix.affixId; });
                        if (found != entries.end())
                        {
                            affix.name = found->name;
                            affix.isPercent = found->isPercent;
                            break;
                        }
                    }
    }
    for (Affix& affix : instance.affixes)
    {
        if (affix.affixId=="str" || affix.affixId=="dex" || affix.affixId=="int") affix.name=PrimaryName(affix.affixId);
        if (auto found = skillAffixes.find(affix.affixId); found != skillAffixes.end())
        {
            affix.name = found->second.name;
            affix.isPercent = true;
        }
        if (ElementalAffix const* element = ElementalAffixOf(affix.affixId))
        {
            affix.name = element->name;
            affix.isPercent = true;
        }
        if (ElementalAffix const* resist = ResistAffixOf(affix.affixId))
            affix.name = resist->name;
    }
    return instance;
}

void Erase(std::uint64_t itemGuid)
{
    CharacterDatabaseTransaction transaction = removalTransaction ? removalTransaction : CharacterDatabase.BeginTransaction();
    transaction->Append("DELETE FROM dc_item_affix WHERE item_guid={}", itemGuid);
    transaction->Append("DELETE FROM dc_item_instance WHERE item_guid={}", itemGuid);
    transaction->Append("DELETE FROM dc_enchant_offer WHERE item_guid={}", itemGuid);
    transaction->Append("DELETE FROM dc_legendary_gem_rank WHERE item_guid={}", itemGuid);
    // An unidentified shell the player destroys takes its drop record with it
    // too. This is the same removal hook the rolled rows use, so a
    // vendor buyback slot keeps its row until that slot is really destroyed,
    // and a traded or mailed shell keeps its row for the new holder.
    transaction->Append("DELETE FROM dc_item_unidentified WHERE item_guid={}", itemGuid);
    if (!removalTransaction) CharacterDatabase.CommitTransaction(transaction);
}
}

using namespace Detail;

std::optional<Instance> Get(std::uint64_t itemGuid)
{
    return Load(itemGuid);
}

void DestroyWithRows(Player* player, Item* item, CharacterDatabaseTransaction const& transaction)
{
    struct Scope
    {
        CharacterDatabaseTransaction previous = removalTransaction;
        explicit Scope(CharacterDatabaseTransaction const& current) { removalTransaction=current; }
        ~Scope() { removalTransaction=previous; }
    } scope(transaction);
    player->DestroyItem(item->GetBagSlot(),item->GetSlot(),true);
}

std::optional<Unidentified> GetUnidentified(std::uint64_t itemGuid)
{
    QueryResult row = CharacterDatabase.Query(
        "SELECT item_guid, base_item, item_level, rarity, drop_source, tier, owner_guid, roll_class, quality_tier "
        "FROM dc_item_unidentified WHERE item_guid={}", itemGuid);
    if (!row)
        return std::nullopt;
    Field* f = row->Fetch();
    Unidentified shell;
    shell.itemGuid = f[0].Get<uint64>();
    shell.baseItem = f[1].Get<uint32>();
    shell.itemLevel = static_cast<unsigned>(f[2].Get<uint32>());
    shell.rarity = f[3].Get<std::string>();
    shell.dropSource = f[4].Get<std::string>();
    shell.tier = static_cast<unsigned>(f[5].Get<uint8>());
    shell.ownerGuid = f[6].Get<uint64>();
    shell.rollClass = f[7].Get<std::string>();
    shell.qualityTier = DC::Quality::Clean(f[8].Get<std::string>());
    return shell;
}

void DestroyShell(Player* player, Item* item, CharacterDatabaseTransaction const& transaction)
{
    if (!player || !item)
        return;
    // Row and item go together, in the caller's transaction: a shell whose row
    // survived would be unidentifiable, and a row whose shell survived would
    // pay its materials twice.
    transaction->Append("DELETE FROM dc_item_unidentified WHERE item_guid={}",
                        item->GetGUID().GetCounter());
    DestroyWithRows(player, item, transaction);
}
}
