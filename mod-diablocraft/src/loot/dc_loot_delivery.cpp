// Constant (65535): material delivery chunk size; uint16 bound.
// Loot: delivery. A drop reaches the player here: the bags, the buffer behind a full bag, a ground carrier's or a
// corpse's rows, the pay-once claim, and the account materials.
#include "dc_loot_internal.h"
#include "dc_ground_loot.h"
#include "dc_corpse_loot.h"
#include "dc_broken_crown_rule.h"

#include "../difficulty/dc_difficulty.h"
#include "../items/dc_items.h"
#include "../items/dc_quality_rule.h"
#include "../rifts/dc_rifts.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_economy.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "Bag.h"
#include "TemporarySummon.h"
#include <functional>
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "WorldSession.h"

#include <algorithm>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

namespace DC::Loot
{
using namespace Detail;

namespace
{
// tunables:loot (06-loot L5).
inline unsigned BufferSeconds()
{
    return static_cast<unsigned>(DC::Tunables::Get("loot", "loot_buffer_seconds"));
}

// Buffered material rows never expire: 0007 holds a reward that cannot be
// delivered rather than discarding it, and `expires_at` is a TIMESTAMP, whose
// range ends in 2038. Rolled items and gems keep L5's 60-second window.
constexpr char const* NeverExpires = "'2038-01-01 00:00:00'";

// Player::AddItem stores what fits and silently discards the rest while still
// returning true (Player.cpp:16061), so what actually landed is measured here
// rather than assumed. Legacy path only: with the account economy on, materials
// are ledger rows and never touch a bag.
unsigned StoreMaterial(Player* player, std::uint32_t entry, unsigned count)
{
    std::uint32_t const before = player->GetItemCount(entry, false);
    player->AddItem(entry, count);
    std::uint32_t const after = player->GetItemCount(entry, false);
    // The client will not list a currency until the matching bit of
    // PLAYER_FIELD_KNOWN_CURRENCIES is set; DC::Economy::KnowCurrency does that
    // and is itself a no-op once the account economy owns the display.
    DC::Economy::KnowCurrency(player, entry);
    return after > before ? after - before : 0;
}

void BufferMaterial(Player* player, std::uint32_t entry, unsigned count)
{
    // dc_loot_buffer.item_level is SMALLINT UNSIGNED, so a large grant is held
    // as several rows rather than truncated.
    while (count)
    {
        unsigned const chunk = std::min(count, 65535u);
        CharacterDatabase.Execute(
            "INSERT INTO dc_loot_buffer (guid, base_item, item_level, expires_at, kind) "
            "VALUES ({}, {}, {}, {}, 'material')",
            player->GetGUID().GetRawValue(), entry, chunk, NeverExpires);
        count -= chunk;
    }
}

// Every inventory-bearing descriptor delivery stages into one transaction.
// The conditional DELETE + enforced ROW_COUNT guard is the database claim;
// only its durable commit publishes inventory and retires a ground carrier.
struct FlatDelivery
{
    Player* player;
    Item* item;
    uint32 before;
    bool published = false;
    FlatDelivery(Player* p, Item* i, uint32 b) : player(p), item(i), before(b) { }
    ~FlatDelivery()
    {
        if (published) return;
        if (before) { item->SetCount(before); item->SetState(ITEM_CHANGED,player); return; }
        Bag* bag = item->GetContainer();
        player->RemoveItem(item->GetBagSlot(),item->GetSlot(),false);
        item->RemoveFromUpdateQueueOf(player);
        if (item->IsInWorld()) item->RemoveFromWorld();
        delete item;
        if (bag) bag->SetState(ITEM_CHANGED,player);
    }
    void Publish()
    {
        published = true;
        if (player->IsInWorld()) { if (!item->IsInWorld()) item->AddToWorld(); item->SendUpdateToPlayer(player); }
        player->ItemAddedQuestCheck(item->GetEntry(),1);
        player->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_RECEIVE_EPIC_ITEM,item->GetEntry(),1);
        player->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_OWN_ITEM,item->GetEntry(),1);
        player->AdditionalSavingAddMask(ADDITIONAL_SAVING_INVENTORY_AND_GOLD);
        sScriptMgr->OnPlayerStoreNewItem(player,item,1);
        player->SendNewItem(item,1,false,false,false,true);
    }
};
struct DeliveryContext
{
    CharacterDatabaseTransaction transaction;
    std::vector<std::function<void()>> publish;
};
thread_local DeliveryContext* activeDelivery = nullptr;
std::mutex claimMutex;

Item* StageFlat(Player* player, uint32 entry)
{
    ItemPosCountVec destinations;
    if (player->CanStoreNewItem(NULL_BAG,NULL_SLOT,destinations,entry,1) != EQUIP_ERR_OK ||
        destinations.size() != 1 || destinations.front().count != 1) return nullptr;
    Item* prior = player->GetItemByPos(destinations.front().pos);
    uint32 before = prior ? prior->GetCount() : 0;
    std::unique_ptr<Item> fresh(Item::CreateItem(entry,1,player));
    if (!fresh) return nullptr;
    Item* item = player->StoreItem(destinations,fresh.get(),false);
    if (!item) return nullptr;
    static_cast<void>(fresh.release());
    auto guard = std::make_shared<FlatDelivery>(player,item,before);
    activeDelivery->publish.push_back([guard]() { guard->Publish(); });
    return item;
}
}

namespace Detail
{
// A kill's drops go on its corpse as each player's own rows when ground delivery is
// off (the rollback switch) and the corpse can hold them; otherwise the old delivery.
bool CorpseDelivery(Creature const* deathSource)
{
    return deathSource && !GroundDeliveryEnabled() && CorpseCanHold(deathSource);
}

// The shell, and the row that remembers what it will become. Nothing is rolled
// here: no dc_item_instance row exists yet, which is exactly what makes
// Items::Get return nullopt and the artisans refuse it.
// Rule 4: the shell's row carries the class the drop rolled for, so identify
// rolls that class whoever holds the shell by then.
// It also carries the quality tier decided at the drop, so the beam showed it and
// identify rolls in its bracket.
bool DeliverShell(Player* player, std::uint32_t baseItem, unsigned itemLevel,
                  std::string const& rarity, std::uint32_t shellEntry,
                  char const* source, unsigned tier, std::string const& rollClass,
                  std::string const& quality)
{
    std::string safeClass = rollClass;
    CharacterDatabase.EscapeString(safeClass);
    if (activeDelivery)
    {
        Item* item = StageFlat(player,shellEntry);
        if (!item) return false;
        activeDelivery->transaction->Append(
            "INSERT INTO dc_item_unidentified (item_guid,base_item,item_level,rarity,drop_source,tier,owner_guid,roll_class,quality_tier) "
            "VALUES ({},{},{},'{}','{}',{},{},'{}','{}')",
            item->GetGUID().GetCounter(),baseItem,itemLevel,rarity,source,tier,player->GetGUID().GetRawValue(),safeClass,
            DC::Quality::Clean(quality));
        return true;
    }
    ItemPosCountVec destinations;
    if (player->CanStoreNewItem(NULL_BAG, NULL_SLOT, destinations, shellEntry, 1) != EQUIP_ERR_OK)
        return false;
    Item* item = player->StoreNewItem(destinations, shellEntry, true);
    if (!item)
        return false;
    CharacterDatabase.Execute(
        "INSERT INTO dc_item_unidentified "
        "(item_guid, base_item, item_level, rarity, drop_source, tier, owner_guid, roll_class, quality_tier) "
        "VALUES ({}, {}, {}, '{}', '{}', {}, {}, '{}', '{}')",
        // The COUNTER, matching dc_item_instance and the only form Lua can
        // produce.
        item->GetGUID().GetCounter(), baseItem, itemLevel, rarity, source, tier,
        player->GetGUID().GetRawValue(), safeClass, DC::Quality::Clean(quality));
    player->SendNewItem(item, 1, false, false, false, true);
    return true;
}

bool DeliverItem(Player* player, std::uint32_t baseItem, unsigned itemLevel,
                 char const* source, unsigned tier, std::string const& rollClass,
                 std::string const& quality)
{
    std::string rarity;
    std::uint32_t shellEntry = 0;
    if (ShellFor(baseItem, rarity, shellEntry))
        return DeliverShell(player, baseItem, itemLevel, rarity, shellEntry, source, tier, rollClass, quality);
    if (activeDelivery)
    {
        auto staged = std::shared_ptr<DC::Items::StagedRoll>(
            DC::Items::StageRoll(player,baseItem,itemLevel,"",activeDelivery->transaction,rollClass,quality).release());
        if (!staged) return false;
        activeDelivery->publish.push_back([player,staged]()
        {
            if (Item* item = staged->Publish()) player->SendNewItem(item,1,false,false,false,true);
        });
        return true;
    }
    Item* item = DC::Items::RollItem(player, baseItem, itemLevel, "", rollClass, quality);
    if (!item)
        return false;
    // StoreNewItem updates the inventory but does not send a loot receipt.
    // Personal drops use the native item-link chat message for this player only.
    player->SendNewItem(item, 1, false, false, false, true);
    return true;
}

// L5. The row has to carry enough to build the SAME drop later: a legendary
// that waited out a full bag must still come back as a shell of the same
// rarity, from the same source and tier, or the roller would invent a
// different item when the slot frees up.
// The roll class travels with it too (rule 4), or a held drop would come back
// rolled for a different class than the base was picked for.
void Buffer(Player* player, std::uint32_t baseItem, unsigned itemLevel,
            char const* source, unsigned tier, std::string const& rollClass,
            std::string const& quality)
{
    std::string rarity;
    std::uint32_t shellEntry = 0;
    ShellFor(baseItem, rarity, shellEntry);
    std::string safeClass = rollClass;
    CharacterDatabase.EscapeString(safeClass);
    CharacterDatabase.Execute(
        "INSERT INTO dc_loot_buffer (guid, base_item, item_level, expires_at, rarity, drop_source, tier, roll_class, quality_tier) "
        "VALUES ({}, {}, {}, DATE_ADD(NOW(), INTERVAL {} SECOND), '{}', '{}', {}, '{}', '{}')",
        player->GetGUID().GetRawValue(), baseItem, itemLevel, BufferSeconds(), rarity, source, tier, safeClass,
        DC::Quality::Clean(quality));
}
}

namespace
{
// Flat templates never pass through the rolled-item affix path.
bool DeliverGem(Player* player, std::uint32_t entry)
{
    if (activeDelivery) return StageFlat(player,entry) != nullptr;
    ItemPosCountVec destinations;
    if (player->CanStoreNewItem(NULL_BAG, NULL_SLOT, destinations, entry, 1) != EQUIP_ERR_OK)
        return false;
    Item* item = player->StoreNewItem(destinations, entry, true);
    if (!item)
        return false;
    player->SendNewItem(item, 1, false, false, false, true);
    return true;
}

void BufferGem(Player* player, std::uint32_t entry, unsigned monsterLevel)
{
    CharacterDatabase.Execute(
        "INSERT INTO dc_loot_buffer (guid, base_item, item_level, expires_at, kind) "
        "VALUES ({}, {}, {}, DATE_ADD(NOW(), INTERVAL {} SECOND), 'gem')",
        player->GetGUID().GetRawValue(), entry, monsterLevel, BufferSeconds());
}
}

namespace Detail
{
// One gem drop, wherever the source says drops go: a corpse row, a ground carrier, or the bags with
// the held buffer behind a full one. The kill hook's normal gems and a Greater Rift Guardian's
// legendary gem both end here.
void DeliverGemDrop(Player* player, std::uint32_t gem, unsigned level, char const* source, unsigned tier,
                    Creature* deathSource, bool corpse, bool ground, Position const& at)
{
    if (corpse)
    {
        if (!DropCorpseLoot(player,deathSource,gem,level,"rare",source,tier,"gem",1))
            LOG_ERROR("server", "[DC loot] Corpse gem row refused for {}.",player->GetName());
    }
    else if (ground)
    {
        if (!DropGroundLoot(player,gem,level,"rare",source,tier,"gem",1,at))
            LOG_ERROR("server", "[DC loot] Ground gem descriptor refused for {}.",player->GetName());
    }
    else if (!DeliverGem(player,gem)) BufferGem(player,gem,level);
}

// Broken Crown (dc_broken_crown_rule.h): the extra gem of the worn Crown's socketed type, 0 when the head slot
// holds no Crown, the Crown is broken, or its socket holds no ordinary gem.
std::uint32_t BrokenCrownGem(Player* player, std::uint32_t dropped)
{
    Item* helm = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_HEAD);
    if (!helm || helm->IsBroken()) return 0; // a broken item counts for nothing (dc_item_powers.cpp)
    std::optional<DC::Items::Instance> const instance = DC::Items::Get(helm->GetGUID().GetCounter());
    if (!instance) return 0;
    if (!WorldDatabase.Query("SELECT 1 FROM dc_base_item WHERE entry={} AND d3_id='{}'", instance->baseItem,
                             DC::Loot::BrokenCrown::BaseId))
        return 0;
    std::uint32_t helmGem = 0;
    for (DC::Items::Affix const& affix : instance->affixes)
        if (affix.kind == "gem") { helmGem = affix.gemEntry; break; }
    QueryResult rows = WorldDatabase.Query("SELECT entry,colour,tier FROM dc_gem_item");
    if (!helmGem || !rows) return 0;
    std::vector<DC::Loot::BrokenCrown::Gem> gems;
    do gems.push_back({(*rows)[0].Get<std::uint32_t>(), (*rows)[1].Get<std::string>(), (*rows)[2].Get<std::string>()});
    while (rows->NextRow());
    return DC::Loot::BrokenCrown::BonusGem(helmGem, dropped, gems);
}
}

namespace
{
// L5, one material row. A material row never expires, so a row that was
// credited but not removed would pay a second, permanent stack on the next
// login or bag move. The row is claimed in the same transaction that grants:
// with the account economy on the buffer row id is the receipt, so a replay is
// a no-op; in legacy mode the store and the row update/removal commit together
// and a failed commit takes the in-memory stack back off, leaving the row to
// deliver once. False means nothing more could be
// taken this pass - a full bag, or a failure the caller must stop on.
bool DeliverBufferedMaterial(Player* player, std::uint64_t id, std::uint32_t entry, unsigned count)
{
    if (activeDelivery)
        return DC::AccountEconomy::CreditMaterial(player,entry,count,"loot_buffer:"+std::to_string(id));
    if (DC::AccountEconomy::Enabled())
    {
        // The row id is the receipt: a repeat resolves to the same operation
        // and credits nothing a second time (dc_account_economy.cpp:313-338).
        std::string const receipt = "loot_buffer:" + std::to_string(id);
        if (!DC::AccountEconomy::CreditMaterial(player, entry, count, receipt))
            return false;
        CharacterDatabase.DirectExecute("DELETE FROM dc_loot_buffer WHERE id={}", id);
        return true;
    }
    unsigned const stored = StoreMaterial(player, entry, count);
    if (!stored)
        return false;                   // full: leave the row untouched
    CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
    if (stored == count)
        transaction->Append("DELETE FROM dc_loot_buffer WHERE id={}", id);
    else                                // part of the stack fitted; keep the rest
        transaction->Append("UPDATE dc_loot_buffer SET item_level={} WHERE id={}", count - stored, id);
    player->SaveInventoryAndGoldToDB(transaction);
    if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
    {
        // The rollback left the row saying what it said before, so the store
        // has to come off the player as well or the next inventory save writes
        // it while the row still holds the reward.
        player->DestroyItemCount(entry, stored, true);
        return false;
    }
    return stored == count;
}

// L5. Called whenever a bag slot might have freed; delivers what still fits and
// drops whatever has already expired.
// Defined above DeliverBuffered, which is its first caller: a forward declaration
// here would let a stale parameter type become a link error.
bool ClaimBufferedRow(Player* player, uint64 id, Creature* carrier = nullptr, std::uint8_t* storeError = nullptr)
{
    // The byte travels because the corpse decision header compiles without the
    // core; every comparison here is against the real enum.
    static_assert(EQUIP_ERR_OK == 0, "storeError 0 must mean EQUIP_ERR_OK");
    std::lock_guard<std::mutex> lock(claimMutex);
    auto row = CharacterDatabase.Query(
        "SELECT base_item,item_level,kind,content_kind,drop_source,tier,carrier_guid,map_id,instance_id,phase_mask,in_rift,drop_count,roll_class,quality_tier "
        "FROM dc_loot_buffer WHERE id={} AND guid={} AND expires_at>NOW()",
        id,player->GetGUID().GetRawValue());
    if (!row) return false;
    auto* f = row->Fetch();
    uint32 const base = f[0].Get<uint32>();
    unsigned const level = f[1].Get<uint16>();
    std::string const kind = f[2].Get<std::string>();
    // A ground carrier and a corpse row both keep their content in content_kind.
    bool const dropped = kind == "ground" || kind == "corpse";
    std::string const content = dropped ? f[3].Get<std::string>() : kind;
    std::string source = f[4].Get<std::string>();
    CharacterDatabase.EscapeString(source);
    unsigned const tier = f[5].Get<uint8>();
    // Rule 4. A row from before roll classes were stored has none; it was
    // buffered for this player, so it rolls this player's class as it always did.
    std::string const rollClass = f[12].Get<std::string>().empty() ? D3Class(player) : f[12].Get<std::string>();
    if (dropped != (carrier != nullptr)) return false;
    if (carrier && (f[6].Get<uint64>() != carrier->GetGUID().GetRawValue() ||
        f[7].Get<uint32>() != carrier->GetMapId() || f[8].Get<uint32>() != carrier->GetInstanceId() ||
        f[9].Get<uint32>() != player->GetPhaseMask() ||
        (f[10].Get<uint8>() && !DC::Rifts::IsLiveInstance(carrier->GetMapId(),carrier->GetInstanceId())))) return false;
    if (content != "rolled" && content != "gem" && content != "material") return false;
    if (!dropped && content == "material" && !DC::AccountEconomy::Enabled())
        return DeliverBufferedMaterial(player,id,base,level); // unchanged legacy partial-stack grant
    if (content != "material")
    {
        std::string rarity;
        uint32 storageEntry = base, shell = 0;
        if (content == "rolled" && ShellFor(base,rarity,shell)) storageEntry = shell;
        ItemPosCountVec destinations;
        // BEFORE a claim is appended or any item/affix is created. The refusal is
        // the core's own result - a full bag, a Unique limit, a level gate - and
        // the pickup window sends exactly that, never a guessed "inventory full".
        InventoryResult const storable = player->CanStoreNewItem(NULL_BAG,NULL_SLOT,destinations,storageEntry,1);
        if (storable != EQUIP_ERR_OK)
        {
            if (storeError) *storeError = static_cast<std::uint8_t>(storable);
            return false;
        }
    }
    PlayerEconomy::Scope operation(player);
    auto context = std::make_shared<DeliveryContext>();
    context->transaction = PlayerEconomy::BeginTransaction();
    context->transaction->Append("DELETE FROM dc_loot_buffer WHERE id={} AND guid={} AND expires_at>NOW()",id,player->GetGUID().GetRawValue());
    context->transaction->Append("INSERT INTO dc_loot_claim_check(id,valid) VALUES({},IF(ROW_COUNT()=1,1,0))",id);
    context->transaction->Append("DELETE FROM dc_loot_claim_check WHERE id={}",id);
    struct RestoreDelivery
    {
        DeliveryContext* previous;
        ~RestoreDelivery() { activeDelivery = previous; }
    } restore{activeDelivery};
    activeDelivery = context.get();
    bool delivered = content == "gem" ? DeliverGem(player,base) : content == "material"
        ? DeliverBufferedMaterial(player,id,base,dropped ? f[11].Get<uint32>() : level)
        : DeliverItem(player,base,level,source.c_str(),tier ? tier : 1,rollClass,DC::Quality::Clean(f[13].Get<std::string>()));
    activeDelivery = restore.previous;
    if (!delivered) { context->publish.clear(); PlayerEconomy::Fail(); return false; }
    player->SaveInventoryAndGoldToDB(context->transaction);
    // Only a ground carrier is retired by its pickup; a corpse outlives its rows.
    bool const retire = kind == "ground";
    auto publish = [context,carrier,retire]()
    {
        for (auto& callback : context->publish) callback();
        context->publish.clear();
        if (retire && carrier) if (auto* summon = carrier->ToTempSummon()) summon->UnSummon();
    };
    if (PlayerEconomy::Current())
    {
        PlayerEconomy::AfterCommit(publish);
        PlayerEconomy::OnRollback([context]() { context->publish.clear(); });
        return operation.Finish();
    }
    if (!CharacterDatabase.AsyncCommitTransaction(context->transaction).m_future.get()) return false;
    publish();
    return true;
}
}

namespace Detail
{
void DeliverBuffered(Player* player)
{
    if (!player) return;
    // Ground descriptors never participate in automatic delivery or its expiry
    // sweep: their carriers own lifecycle and explicit pickup.
    CharacterDatabase.DirectExecute("DELETE FROM dc_loot_buffer WHERE guid={} AND kind NOT IN ('ground','corpse') AND expires_at<NOW()",player->GetGUID().GetRawValue());
    auto rows = CharacterDatabase.Query("SELECT id FROM dc_loot_buffer WHERE guid={} AND kind NOT IN ('ground','corpse') ORDER BY id",player->GetGUID().GetRawValue());
    if (!rows) return;
    do
    {
        if (!ClaimBufferedRow(player,(*rows)[0].Get<uint64>())) break;
        ChatHandler(player->GetSession()).SendSysMessage("A held drop has been delivered.");
    } while (rows->NextRow());
}


// L11. One guaranteed legendary the first time a character kills an act boss.
// The one-time flag is written only after a legendary has actually been picked
// and handed over (delivered or buffered): the old order set it first, so a
// boss with no eligible legendary at this level burned the drop forever, and
// the unchecked INSERT could repeat a drop whose flag write failed. The flag is
// INSERT IGNORE against the (guid, flag) primary key and its commit is checked,
// so it is never assumed to have landed.
void FirstBossKill(Player* player, std::uint32_t creatureEntry, unsigned monsterLevel, Creature* deathSource)
{
    if (!player)
        return;
    std::string const flag = "boss_first_kill:" + std::to_string(creatureEntry);
    std::uint64_t const guid = player->GetGUID().GetRawValue();
    if (CharacterDatabase.Query("SELECT value FROM dc_character_flags WHERE guid={} AND flag='{}'", guid, flag))
        return;
    // The guaranteed legendary is always the looter's own class: a deliberate
    // exception to the 85/15 roll class (the first-kill legendary belongs to
    // the campaign).
    std::string const rollClass = D3Class(player);
    // FirstBossKill carries no tier of its own; the kill has just happened, so
    // the player's current tier is the tier this drop rolls at.
    unsigned const bossTier = DC::Difficulty::CurrentTier(player);
    std::uint32_t const base = PickBaseItem(Rarity::Legendary, monsterLevel, rollClass, bossTier);
    if (!base)
        return;                         // nothing eligible: keep the one-time drop
    // Hand the legendary over first. A full bag holds it in dc_loot_buffer (L5)
    // rather than losing it, the same as any other drop.
    // The first-kill legendary rolls its quality like any drop.
    std::string const quality = DC::Items::RollQuality(player, base, monsterLevel, bossTier);
    if (CorpseDelivery(deathSource))
    {
        std::string rarity = "legendary";
        uint32 shell = 0;
        ShellFor(base,rarity,shell);
        if (!DropCorpseLoot(player,deathSource,base,monsterLevel,rarity,Name(Source::Boss),bossTier,"rolled",1,rollClass,quality)) return;
    }
    else if (GroundDeliveryEnabled())
    {
        std::string rarity = "legendary";
        uint32 shell = 0;
        ShellFor(base,rarity,shell);
        if (!DropGroundLoot(player,base,monsterLevel,rarity,Name(Source::Boss),bossTier,"rolled",1,deathSource->GetPosition(),rollClass,quality)) return;
    }
    else if (!DeliverItem(player, base, monsterLevel, Name(Source::Boss), bossTier, rollClass, quality))
        Buffer(player, base, monsterLevel, Name(Source::Boss), bossTier, rollClass, quality);

    // Only now is the drop spent. INSERT IGNORE is a no-op if it is already set;
    // the commit answers, so a failed write is logged rather than silently
    // leaving a repeatable "one-time" drop.
    CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
    transaction->Append("INSERT IGNORE INTO dc_character_flags (guid, flag, value) VALUES ({}, '{}', 1)",
                        guid, flag);
    if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
        LOG_ERROR("server", "[DC loot] first-kill flag {} for {} did not persist; "
                            "the guaranteed legendary may repeat", flag, player->GetName());
}
}

std::uint32_t WindowItem(std::uint32_t baseItem, std::string const& contentKind)
{
    std::string rarity;
    std::uint32_t shell = 0;
    return contentKind == "rolled" && ShellFor(baseItem, rarity, shell) ? shell : baseItem;
}

bool ClaimCorpseRow(Player* player, std::uint64_t rowId, Creature* corpse, std::uint8_t& storeError)
{
    storeError = EQUIP_ERR_OK;
    if (!player || !corpse || !player->IsAlive() || !player->IsInMap(corpse)) return false;
    return ClaimBufferedRow(player, rowId, corpse, &storeError);
}

bool ClaimGroundLoot(Player* player, Creature* carrier, std::uint8_t* storeError)
{
    if (storeError) *storeError = EQUIP_ERR_OK;
    if (!player || !carrier || !player->IsAlive() || !player->IsInMap(carrier) ||
        !player->InSamePhase(carrier) || !player->IsWithinDistInMap(carrier,INTERACTION_DISTANCE)) return false;
    auto* summon = carrier->ToTempSummon();
    if (!summon || summon->GetSummonerGUID() != player->GetGUID()) return false;
    auto row = CharacterDatabase.Query("SELECT id FROM dc_loot_buffer WHERE carrier_guid={} AND guid={} AND kind='ground' AND map_id={} AND instance_id={}",
                                      carrier->GetGUID().GetRawValue(),player->GetGUID().GetRawValue(),carrier->GetMapId(),carrier->GetInstanceId());
    return row && ClaimBufferedRow(player,(*row)[0].Get<uint64>(),carrier,storeError);
}
void LoseGroundLoot(uint64 carrier, uint32 mapId, uint32 instanceId)
{
    std::lock_guard<std::mutex> lock(claimMutex);
    CharacterDatabase.DirectExecute("DELETE FROM dc_loot_buffer WHERE carrier_guid={} AND kind='ground' AND map_id={} AND instance_id={}",carrier,mapId,instanceId);
}
void LosePlayerGroundLoot(Player* player)
{
    std::lock_guard<std::mutex> lock(claimMutex);
    CharacterDatabase.DirectExecute("DELETE FROM dc_loot_buffer WHERE guid={} AND kind='ground'",player->GetGUID().GetRawValue());
}

bool GrantMaterial(Player* player, std::uint32_t entry, unsigned count, std::string const& receipt)
{
    if (!player || !count)
        return false;
    // Account mode: a checked ledger credit, no bag item and no currency slot.
    // The receipt makes a retried reward credit once and only once.
    if (DC::AccountEconomy::Enabled())
        return DC::AccountEconomy::CreditMaterial(player, entry, count, receipt);
    // Legacy mode (the account economy off): the item is stored and whatever did not
    // fit is held rather than silently eaten by a full bag.
    unsigned const stored = StoreMaterial(player, entry, count);
    if (stored < count)
    {
        BufferMaterial(player, entry, count - stored);
        ChatHandler(player->GetSession())
            .PSendSysMessage("Your bags are full; {} held until a slot frees.", count - stored);
    }
    return true;
}
}
