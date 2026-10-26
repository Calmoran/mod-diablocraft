// Constant (2): Highest bulk-salvage rarity (Rare); Rarity ordinal implementing explicit Normal/Magic/Rare policy.
// Crafting: what the artisans and the Cube share (reach, ownership, materials, rolled items), salvage and the
// Blacksmith's craft.
#include "dc_crafting_internal.h"
#include "dc_salvage_rule.h"
#include "../common/dc_economy.h"
#include "../common/dc_numeric_data.h"
#include "../common/dc_tunables.h"
#include "../common/dc_account_economy.h"
#include "PlayerEconomy.h"
#include "../items/dc_items.h"
#include "Bag.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Random.h"
#include "WorldSession.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <memory>
#include <stdexcept>
#include <vector>

namespace DC::Crafting
{
    using namespace Detail;
    namespace
    {
        constexpr float CubeSearchYards = 30.0f;
    } // namespace
    namespace Detail
    {
        bool AccountMaterial(uint32 entry)
        {
            return AccountEconomy::Enabled() && AccountEconomy::IsMaterial(entry);
        }
        void Need(bool ok, char const* message)
        {
            if (!ok)
                throw std::runtime_error(message);
        }
    } // namespace Detail
    namespace
    {
        double Tunable(char const* name)
        {
            Need(Tunables::Has("crafting", name), "Missing crafting tunable.");
            double value = Tunables::Get("crafting", name);
            Need(std::isfinite(value) && value >= 0, "Invalid crafting tunable.");
            return value;
        }
    } // namespace
    namespace Detail
    {
        uint32 TunableCount(char const* name)
        {
            double value = Tunable(name);
            Need(value == std::floor(value) && value <= UINT32_MAX, "Invalid crafting count.");
            return uint32(value);
        }
        uint32 SourcedCount(char const* name)
        {
            double value = NumericData::Rule(name);
            Need(value >= 0 && value == std::floor(value) && value <= UINT32_MAX, "Invalid sourced artisan count.");
            return uint32(value);
        }
        std::string Escape(std::string value)
        {
            CharacterDatabase.EscapeString(value);
            return value;
        }
        // The player's own half of Artisan(): what an action that needs no NPC still asks of them.
        void Reachable(Player* player)
        {
            Need(player && player->IsAlive(), "A living player is required.");
            Need(!player->IsInCombat() && !player->GetTradeData(), "Finish combat or trading before using an artisan.");
        }
        Creature* Artisan(Player* player, uint32 entry)
        {
            Reachable(player);
            auto* npc = player->FindNearestCreature(entry, float(Tunable("artisan_interaction_range_yards")));
            Need(npc && player->GetNPCIfCanInteractWith(npc->GetGUID(), UNIT_NPC_FLAG_GOSSIP),
                 "Stand next to the artisan.");
            return npc;
        }
    } // namespace Detail
    namespace
    {
        // Kanai's Cube has no unlock yet; a questline later changes this one place (plan 6.1).
        bool Unlocked(Player*)
        {
            return true;
        }
    } // namespace
    namespace Detail
    {
        // The Cube's gate: the player's own state, then the Cube within the reach the core lets a player click it from
        // (GetGameObjectIfCanInteractWith: same map and phase, the object's interaction box).
        void CubeInReach(Player* player)
        {
            Reachable(player);
            Need(Unlocked(player), "Kanai's Cube is not yours to use yet.");
            auto* cube = player->FindNearestGameObject(KanaisCube, CubeSearchYards);
            Need(cube && player->GetGameObjectIfCanInteractWith(cube->GetGUID(), GAMEOBJECT_TYPE_SPELLCASTER),
                 "Stand next to Kanai's Cube.");
        }
        std::vector<Item*> Inventory(Player* player)
        {
            std::vector<Item*> items;
            for (uint8 slot = EQUIPMENT_SLOT_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
                if (slot < EQUIPMENT_SLOT_END || slot >= INVENTORY_SLOT_ITEM_START)
                    if (auto* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                        items.push_back(item);
            for (uint8 bag = INVENTORY_SLOT_BAG_START; bag < INVENTORY_SLOT_BAG_END; ++bag)
                if (auto* container = player->GetBagByPos(bag))
                    for (uint32 slot = 0; slot < container->GetBagSize(); ++slot)
                        if (auto* item = player->GetItemByPos(bag, slot))
                            items.push_back(item);
            return items;
        }
        Item* Owned(Player* player, uint32 guid)
        {
            auto* item = player->GetItemByGuid(ObjectGuid(HighGuid::Item, guid));
            Need(item && item->GetOwnerGUID() == player->GetGUID() && !item->IsInTrade(),
                 "That item is no longer yours or is being traded.");
            Need(Player::IsInventoryPos(item->GetPos()) || Player::IsEquipmentPos(item->GetPos()),
                 "Move the item out of the bank first.");
            return item;
        }
        Items::Instance Rolled(Item* item)
        {
            auto instance = Items::Get(item->GetGUID().GetCounter());
            // A shell already fails the nullopt test - it has no instance row,
            // which is the whole point of the design - so this only replaces
            // the message with one that says what to do about it.
            Need(!Items::IsUnidentifiedTemplate(item->GetEntry()), "Identify it first.");
            Need(bool(instance), "Choose a rolled item.");
            return *instance;
        }
        void Save(Player* player, CharacterDatabaseTransaction transaction)
        {
            player->SaveInventoryAndGoldToDB(transaction);
            // Core inventory/money prepared statements exist on worker connections only.
            // Wait for that transaction before reading the new offer or reporting success.
            Need(AccountEconomy::Commit(player, transaction), "The artisan transaction could not be saved.");
        }
        std::string MaterialName(uint32 entry)
        {
            auto* proto = sObjectMgr->GetItemTemplate(entry);
            return proto && !proto->Name1.empty() ? proto->Name1 : "material " + std::to_string(entry);
        }
        // The decision. Account materials are ledger totals; everything else is a bag
        // count, and Artisan() has already refused a player who is trading.
        bool Enough(Player* player, uint32 entry, uint64 count)
        {
            return AccountMaterial(entry) ? AccountEconomy::MaterialBalance(player, entry) >= count
                                          : count <= UINT32_MAX && player->HasItemCount(entry, uint32(count), false);
        }
        // The same total as a number, for the message and for the published quote.
        uint64 Held(Player* player, uint32 entry)
        {
            return AccountMaterial(entry) ? AccountEconomy::MaterialBalance(player, entry)
                                          : player->GetItemCount(entry, false);
        }
        void CheckMaterials(Player* player, Amounts const& amounts)
        {
            // Name the short material: the generic
            // sentence never said which material was short, so a screen listing only the
            // materials the player did hold read as a wrong cost. Name it, with both numbers.
            for (auto [entry, count] : amounts)
                if (!Enough(player, entry, count))
                    throw std::runtime_error("Not enough " + MaterialName(entry) + ": you have " +
                                             std::to_string(Held(player, entry)) + " of " + std::to_string(count) +
                                             ".");
        }
        void SpendMaterials(Player* player, Amounts const& amounts)
        {
            for (auto [entry, count] : amounts)
                if (AccountMaterial(entry))
                    Need(AccountEconomy::DebitMaterial(player, entry, count), "Material balance changed.");
                else
                {
                    Need(count <= UINT32_MAX, "Gem count exceeds native capacity.");
                    player->DestroyItemCount(entry, uint32(count), true);
                }
        }
        void CheckRoom(Player* player, Amounts const& amounts)
        {
            std::vector<std::unique_ptr<Item>> owned;
            std::vector<Item*> items;
            for (auto [entry, count] : amounts)
            {
                if (AccountMaterial(entry))
                    continue;
                Need(count <= UINT32_MAX, "Item count exceeds native capacity.");
                auto* proto = sObjectMgr->GetItemTemplate(entry);
                Need(proto, "Artisan item data is missing.");
                if (proto->BagFamily & BAG_FAMILY_MASK_CURRENCY_TOKENS)
                    Need(uint64(player->GetItemCount(entry, false)) + count <= INT32_MAX,
                         "That currency is at its capacity.");
                while (count)
                {
                    uint32 stack = uint32(std::min<uint64>(count, proto->GetMaxStackSize()));
                    auto item = std::unique_ptr<Item>(Item::CreateItem(entry, stack, player));
                    Need(bool(item), "Could not prepare the artisan reward.");
                    items.push_back(item.get());
                    owned.push_back(std::move(item));
                    count -= stack;
                }
            }
            uint32 limited = 0;
            Need(player->CanStoreItems(items.data(), int(items.size()), &limited) == EQUIP_ERR_OK,
                 "Make room for the returned gems and materials first.");
        }
        void Grant(Player* player, Amounts const& amounts)
        {
            for (auto [entry, count] : amounts)
            {
                if (AccountMaterial(entry))
                    Need(AccountEconomy::CreditMaterial(player, entry, count),
                         "The material reward could not be stored.");
                else
                {
                    Need(count <= UINT32_MAX && player->AddItem(entry, uint32(count)),
                         "The prepared reward could not be stored.");
                    Economy::KnowCurrency(player, entry);
                }
            }
        }
        void AffixRow(CharacterDatabaseTransaction const& tx, uint64 guid, Items::Affix const& a)
        {
            // G1: a weapon elemental affix carries a second value and bracket; the copy must keep
            // them or a Mystic save would drop the rolled element.
            tx->Append("INSERT INTO dc_item_affix(item_guid,seq,affix_id,value,range_min,range_max,value2,"
                       "range_min2,range_max2,kind,rerolled) "
                       "VALUES({},{},'{}',{},{},{},{},{},{},'{}',{})",
                       guid, a.seq, Escape(a.affixId), a.value, a.rangeMin, a.rangeMax, a.value2, a.rangeMin2,
                       a.rangeMax2, Escape(a.kind), a.rerolled ? 1 : 0);
        }
        Items::Affix const& Affix(Items::Instance const& item, uint32 seq)
        {
            auto found =
                std::find_if(item.affixes.begin(), item.affixes.end(), [&](auto const& a) { return a.seq == seq; });
            Need(found != item.affixes.end(), "That affix no longer exists.");
            return *found;
        }
        // A gem row's entry is a normal gem (dc_gem_item) or one of the 21 legendary gems.
        bool IsGemEntry(uint32 entry)
        {
            return Items::LegendaryGemItemOf(entry) ||
                   bool(WorldDatabase.Query("SELECT entry FROM dc_gem_item WHERE entry={}", entry));
        }
        // Gives back the gem a socket row holds. A legendary one returns as an item of its own rank (its rank
        // row goes into the request's transaction); a normal one is a plain stack count. Room was checked.
        void GrantGem(Player* player, Items::Affix const& socketed, CharacterDatabaseTransaction const& tx)
        {
            if (socketed.legendaryRank)
                Need(Items::GiveLegendaryGem(player, socketed.gemEntry, *socketed.legendaryRank, tx),
                     "The prepared reward could not be stored.");
            else
                Grant(player, {{socketed.gemEntry, 1}});
        }
        void Salvage(Player* player, uint32 guid, uint32 rarity)
        {
            Artisan(player, Blacksmith);
            std::vector<Item*> selected;
            if (guid)
            {
                auto* single = Owned(player, guid);
                // G8: bulk salvage already skips equipped items; single salvage refuses one.
                Need(SalvageEligible(single->IsEquipped(), single->IsInTrade()),
                     "Unequip the item before salvaging it.");
                selected.push_back(single);
            }
            else
            {
                Need(rarity <= 2, "Bulk salvage is limited to Normal, Magic and Rare.");
                char const* names[] = {"normal", "magic", "rare"};
                for (auto* item : Inventory(player))
                    if (SalvageEligible(item->IsEquipped(), item->IsInTrade()))
                        if (auto instance = Items::Get(item->GetGUID().GetCounter());
                            instance && instance->rarity == names[rarity])
                            selected.push_back(item);
            }
            Need(!selected.empty(), "No matching items to salvage.");
            Amounts rewards;
            std::vector<Items::Affix> legendaryGems;
            for (auto* item : selected)
            {
                // An unidentified shell CAN be
                // salvaged, D3 behaviour, and it pays the REAL rarity's
                // materials from the row rather than the shell's own template.
                // It has no affixes and no sockets, so there are no gems to
                // return - the roll never happened.
                auto shell = Items::GetUnidentified(item->GetGUID().GetCounter());
                std::string rarityName, quality;
                bool crafted = false;
                if (shell)
                {
                    rarityName = shell->rarity;
                    quality = SalvageQuality(false, shell->qualityTier);
                }
                else
                {
                    auto instance = Rolled(item);
                    rarityName = instance.rarity;
                    crafted = instance.crafted;
                    quality = SalvageQuality(crafted, instance.qualityTier);
                    for (auto const& a : instance.affixes)
                        if (a.kind == "gem")
                        {
                            Need(a.gemEntry != 0, "A socketed gem has invalid data.");
                            // A legendary gem returns as an item of its own rank, not a stack count.
                            if (a.legendaryRank)
                                legendaryGems.push_back(a);
                            else
                                ++rewards[a.gemEntry];
                        }
                }
                auto rows = WorldDatabase.Query(
                    "SELECT item_entry,amount_min,amount_max FROM dc_salvage_rule WHERE rarity='{}' AND crafted={} AND quality='{}'",
                    Escape(rarityName), crafted ? 1 : 0, Escape(quality));
                Need(bool(rows), "No salvage rule exists for this rarity.");
                do
                {
                    auto* f = rows->Fetch();
                    rewards[f[0].Get<uint32>()] += urand(f[1].Get<uint32>(), f[2].Get<uint32>());
                } while (rows->NextRow());
            }
            Amounts room = rewards;
            for (auto const& gem : legendaryGems)
                ++room[gem.gemEntry];
            CheckRoom(player, room);
            Need(Economy::CanAfford(player, 0), "Unable to access gold.");
            Grant(player, rewards);
            auto tx = PlayerEconomy::BeginTransaction();
            for (auto const& gem : legendaryGems)
                GrantGem(player, gem, tx);
            Economy::Charge(player, 0);
            for (auto* item : selected)
            {
                // A shell takes its unidentified row with it, in the same
                // transaction, or it would pay again on the next salvage.
                if (Items::IsUnidentifiedTemplate(item->GetEntry()))
                    Items::DestroyShell(player, item, tx);
                else
                    Items::DestroyWithRows(player, item, tx);
            }
            Save(player, tx);
            ChatHandler(player->GetSession())
                .PSendSysMessage("Salvaged {} item(s). Socketed gems were returned.", selected.size());
        }
        void Craft(Player* player, uint32 id, uint32 count, bool mapped, bool jewelry)
        {
            Artisan(player, jewelry ? Jeweler : Blacksmith);
            uint32 capacity = INVENTORY_SLOT_ITEM_END - INVENTORY_SLOT_ITEM_START;
            for (uint8 bag = INVENTORY_SLOT_BAG_START; bag < INVENTORY_SLOT_BAG_END; ++bag)
                if (auto* container = player->GetBagByPos(bag))
                    capacity += container->GetBagSize();
            Need(count > 0 && count <= capacity, "Choose a positive craft count that fits your bag capacity.");
            auto recipe = jewelry
                ? WorldDatabase.Query("SELECT slot,gold_d3,rarity,item_level,output_entry,enabled,main_stat FROM dc_jeweler_catalog WHERE id={}", id)
                : mapped
                ? WorldDatabase.Query("SELECT slot,gold_d3,rarity,item_level,output_entry,enabled FROM dc_blacksmith_catalog WHERE id={}", id)
                : WorldDatabase.Query("SELECT slot,gold_d3,rarity,item_level,0,1 FROM dc_blacksmith_recipe WHERE id={}", id);
            Need(bool(recipe), "Unknown recipe.");
            std::string slot = (*recipe)[0].Get<std::string>();
            Need((*recipe)[5].Get<uint32>() != 0, "This recipe is unavailable until its missing crafting support is implemented.");
            uint64 price = Economy::GoldCost((*recipe)[1].Get<uint64>());
            std::string rarity = (*recipe)[2].Get<std::string>();
            uint32 level = (*recipe)[3].Get<uint32>();
            // A recipe that fixes the main stat (the Hellfire Amulet's three versions) names the pool id; only the
            // Jeweler's catalogue has the column.
            std::string const mainStat = recipe->GetFieldCount() > 6 ? (*recipe)[6].Get<std::string>() : "";
            Need(level > 0 && level <= NumericData::MaximumLevel(), "Unsupported Blacksmith recipe level.");
            Amounts materials;
            if (auto rows =
                    WorldDatabase.Query(jewelry ? "SELECT item_entry,amount FROM dc_jeweler_catalog_material WHERE recipe_id={}" : mapped ? "SELECT item_entry,amount FROM dc_blacksmith_catalog_material WHERE recipe_id={}" : "SELECT item_entry,amount FROM dc_recipe_material WHERE recipe_id={}", id))
                do
                {
                    auto* f = rows->Fetch();
                    materials[f[0].Get<uint32>()] = f[1].Get<uint32>();
                } while (rows->NextRow());
            Amounts totalMaterials;
            for (auto [entry, amount] : materials)
            {
                Need(amount <= UINT64_MAX / count, "Recipe material total exceeds supported capacity.");
                totalMaterials[entry] = amount * count;
            }
            CheckMaterials(player, totalMaterials);
            Need(price <= UINT64_MAX / count && Economy::CanAfford(player, price * count), "Not enough account gold.");
            // The same recipe/base list is offered to every living crafter.
            // Item restriction and player class are resolved only by the existing roll path.
            auto base = mapped ? WorldDatabase.Query("SELECT entry FROM dc_base_item WHERE entry={} AND pool_version='yes'", (*recipe)[4].Get<uint32>()) : WorldDatabase.Query(
                "SELECT b.entry FROM dc_base_item b JOIN dc_blacksmith_rule r ON r.base_slot=b.slot AND "
                "r.base_rarity=b.rarity WHERE r.recipe_slot='{}' AND r.output_rarity='{}' AND b.pool_version='yes' "
                "AND (b.level_req IS NULL OR b.level_req<={}) ORDER BY b.entry",
                Escape(slot), Escape(rarity), level);
            Need(bool(base), "No eligible base item is available for this recipe.");
            std::vector<uint32> candidates, selected;
            do
            {
                candidates.push_back((*base)[0].Get<uint32>());
            } while (base->NextRow());
            Amounts outputs;
            for (uint32 i = 0; i < count; ++i)
            {
                auto entry = candidates[urand(0, uint32(candidates.size() - 1))];
                selected.push_back(entry);
                ++outputs[entry];
            }
            CheckRoom(player, outputs);
            // Each completed item and its payment persist together. An unexpected roller
            // failure stops the batch; AIO returns the actual persisted item GUIDs/count.
            for (auto entry : selected)
            {
                auto tx = PlayerEconomy::BeginTransaction();
                // An artisan craft is a craft, not a monster drop: the level gate only.
                auto staged = Items::StageRoll(player, entry, level, rarity, tx, "",
                                               Items::RollQuality(player, entry, level, 0, true), mainStat);
                Need(bool(staged), "Crafting stopped before completing the requested count.");
                Item* item = staged->GetItem();
                Need(Economy::Charge(player, price), "Gold changed before the purchase could complete.");
                SpendMaterials(player, materials);
                tx->Append("UPDATE dc_item_instance SET crafted=1 WHERE item_guid={}", item->GetGUID().GetCounter());
                Save(player, tx);
                staged->Publish();
            }
            ChatHandler(player->GetSession()).PSendSysMessage("Crafted {} level-{} {} item(s).", count, level, rarity);
            LOG_INFO("server", "[DC crafting] {} crafted recipe={} count={} gold_copper={}", player->GetName(), id,
                     count, price * count);
        }
    } // namespace Detail
} // namespace DC::Crafting
