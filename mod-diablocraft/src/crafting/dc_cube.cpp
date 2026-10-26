// Constant (65536): Affix sequence exclusive upper bound; Storage bound.
// Crafting: Kanai's Cube (recipes, powers, transmute, the character hooks).
#include "dc_crafting_internal.h"
#include "dc_salvage_rule.h"
#include "../combat/dc_item_powers.h"
#include "../common/dc_economy.h"
#include "../common/dc_tunables.h"
#include "../common/dc_account_economy.h"
#include "PlayerEconomy.h"
#include "../items/dc_items.h"
#include "../items/dc_slot_vendor_rule.h"
#include "../loot/dc_kadala_rule.h"
#include "../loot/dc_loot.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "WorldSession.h"
#include <algorithm>
#include <cstdlib>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <vector>

namespace DC::Crafting
{
    using namespace Detail;
    namespace Detail
    {
        // Kanai's Cube's recipes: dc_cube_recipe and its lines in dc_cube_rule (generate_cube.py), read per request.
        Cube::Recipes CubeRecipes()
        {
            Cube::Recipes recipes;
            if (auto rows = WorldDatabase.Query("SELECT recipe_id,sort,rule,name FROM dc_cube_recipe ORDER BY sort"))
                do
                {
                    auto* f = rows->Fetch();
                    Cube::Recipe recipe;
                    recipe.id = f[0].Get<std::string>();
                    recipe.sort = f[1].Get<uint32>();
                    recipe.rule = f[2].Get<std::string>();
                    recipe.name = f[3].Get<std::string>();
                    recipes.push_back(recipe);
                } while (rows->NextRow());
            if (auto rows = WorldDatabase.Query(
                    "SELECT recipe_id,line,kind,rarity,item_entry,amount FROM dc_cube_rule ORDER BY recipe_id,line"))
                do
                {
                    auto* f = rows->Fetch();
                    for (auto& recipe : recipes)
                        if (recipe.id == f[0].Get<std::string>())
                            recipe.lines.push_back({f[1].Get<uint32>(), f[2].Get<std::string>(), f[3].Get<std::string>(),
                                                    f[4].Get<uint32>(), f[5].Get<uint64>()});
                } while (rows->NextRow());
            // The Recipes panel's page text (dc_cube_page, cube_pages.csv).
            if (auto rows =
                    WorldDatabase.Query("SELECT recipe_id,subtitle,item,note,quote,quote_source FROM dc_cube_page"))
                do
                {
                    auto* f = rows->Fetch();
                    for (auto& recipe : recipes)
                        if (recipe.id == f[0].Get<std::string>())
                        {
                            recipe.subtitle = f[1].Get<std::string>();
                            recipe.item = f[2].Get<std::string>();
                            recipe.note = f[3].Get<std::string>();
                            recipe.quote = f[4].Get<std::string>();
                            recipe.quoteSource = f[5].Get<std::string>();
                        }
                } while (rows->NextRow());
            return recipes;
        }
    } // namespace Detail
    namespace
    {
        // The Cube's powers (docs/contracts/cube-messages.md). A slot takes the powers of the legendary
        // items whose base item slot dc_cube_slot_item gives it, never by a class or a slot named here: the pool items
        // (pool_version yes, rarity legendary) that have a built power row (dc_legendary_power, pieces 0), less the items D3
        // marks cube: false (dc_cube_excluded, cube_excluded.csv: Ancestors' Grace). A power's id is
        // its item's d3_id, the legendary framework's key; the entry it travels under is the item's, for its icon and name.
        // What an account has extracted is dc_cube_power (the Archive writes it, TransmuteItem's
        // `extract`); what a character chose is dc_cube_slot, which the character's login hands to the framework's Cube list
        // (CubeCharacters).
        constexpr char const* CubePowerItems =
            "FROM dc_base_item b JOIN dc_cube_slot_item s ON s.item_slot=b.slot LEFT JOIN dc_item_tooltip t ON "
            "t.d3_id=b.d3_id WHERE b.rarity='legendary' AND "
            "b.pool_version='yes' AND EXISTS(SELECT 1 FROM dc_legendary_power p WHERE p.owner=b.d3_id AND p.pieces=0) AND "
            "NOT EXISTS(SELECT 1 FROM dc_cube_excluded x WHERE x.d3_id=b.d3_id)";
        // The account and mode the extracted powers are keyed by, as the ledger is; nothing when the ledger cannot be read.
        std::optional<std::pair<uint32, std::string>> CubeAccount(Player* player)
        {
            AccountEconomy::Snapshot snapshot;
            if (!AccountEconomy::ReadSnapshot(player, snapshot))
                return std::nullopt;
            return std::make_pair(snapshot.account, snapshot.mode);
        }
    } // namespace
    namespace Detail
    {
        std::vector<Window::CubeSlot> CubeSlots(Player* player)
        {
            std::vector<Window::CubeSlot> slots;
            if (auto rows = WorldDatabase.Query("SELECT DISTINCT slot,label FROM dc_cube_slot_item ORDER BY slot"))
                do
                {
                    auto* f = rows->Fetch();
                    slots.push_back({f[0].Get<uint32>(), f[1].Get<std::string>(), 0, ""});
                } while (rows->NextRow());
            if (auto rows = CharacterDatabase.Query("SELECT slot,power_id FROM dc_cube_slot WHERE guid={}",
                                                    player->GetGUID().GetCounter()))
                do
                {
                    auto* f = rows->Fetch();
                    auto item = WorldDatabase.Query("SELECT entry,d3_name FROM dc_base_item WHERE d3_id='{}'",
                                                    Escape(f[1].Get<std::string>()));
                    for (auto& slot : slots)
                        if (item && slot.slot == f[0].Get<uint32>())
                        {
                            slot.entry = (*item)[0].Get<uint32>();
                            slot.name = (*item)[1].Get<std::string>();
                        }
                } while (rows->NextRow());
            return slots;
        }
        // Every power the slot can hold, by name, with the account's extracted set and whether this character's class may
        // use each (RollClass::Eligible: the item's usable_by and designated class, as the drop rule reads them).
        std::vector<Window::CubePower> CubePowers(Player* player, uint32 slot)
        {
            std::set<std::string> extracted;
            if (auto account = CubeAccount(player))
                if (auto rows = CharacterDatabase.Query("SELECT power_id FROM dc_cube_power WHERE account_id={} AND mode='{}'",
                                                        account->first, account->second))
                    do
                        extracted.insert(rows->Fetch()[0].Get<std::string>());
                    while (rows->NextRow());
            std::string const mine = Items::ClassKeyOf(player->getClass());
            std::vector<Window::CubePower> powers;
            if (auto rows = WorldDatabase.Query(std::string("SELECT b.entry,b.d3_id,b.d3_name,b.usable_by,b.designated_class ") +
                                                    CubePowerItems + " AND s.slot={} ORDER BY b.d3_name,b.entry",
                                                slot))
                do
                {
                    auto* f = rows->Fetch();
                    powers.push_back({f[0].Get<uint32>(), f[2].Get<std::string>(), extracted.count(f[1].Get<std::string>()) != 0,
                                      RollClass::Eligible(f[3].Get<std::string>(), f[4].Get<std::string>(), mine)});
                } while (rows->NextRow());
            return powers;
        }
        std::optional<Window::CubePowerText> CubePowerText(uint32 entry)
        {
            auto row = WorldDatabase.Query(
                std::string("SELECT b.d3_name,COALESCE(t.power_text,'') ") + CubePowerItems +
                    " AND b.entry={}",
                entry);
            // The join above takes one row per slot item; a base item sits in one slot, so there is one.
            return row ? std::optional<Window::CubePowerText>(
                             Window::CubePowerText{(*row)[0].Get<std::string>(), (*row)[1].Get<std::string>()})
                       : std::nullopt;
        }
        // Put an extracted power in a slot, or empty it (entry 0): free, with the Cube in reach (plan 6.2). The power must be
        // one that slot holds, the account's own, and one this class may use; a power is only ever in the slot of its item.
        void ChooseCubePower(Player* player, uint32 slot, uint32 entry)
        {
            Need(slot >= 1 && slot <= CubeSlots(player).size(), "There is no such slot.");
            uint32 const guid = player->GetGUID().GetCounter();
            if (entry == 0)
            {
                CharacterDatabase.DirectExecute("DELETE FROM dc_cube_slot WHERE guid={} AND slot={}", guid, slot);
                Combat::ItemPowers::CubeClear(player, slot);
                Items::RefreshCubedStats(player);
                return;
            }
            auto row = WorldDatabase.Query(std::string("SELECT b.d3_id,b.usable_by,b.designated_class ") + CubePowerItems +
                                               " AND s.slot={} AND b.entry={}",
                                           slot, entry);
            Need(bool(row), "That power does not go in this slot.");
            std::string const power = (*row)[0].Get<std::string>();
            Need(RollClass::Eligible((*row)[1].Get<std::string>(), (*row)[2].Get<std::string>(),
                                     Items::ClassKeyOf(player->getClass())),
                 "Your class cannot use that power.");
            auto account = CubeAccount(player);
            Need(bool(account), "Kanai's Cube needs the account ledger.");
            Need(bool(CharacterDatabase.Query("SELECT 1 FROM dc_cube_power WHERE account_id={} AND mode='{}' AND power_id='{}'",
                                              account->first, account->second, Escape(power))),
                 "You have not extracted that power.");
            // The framework's Cube list is what makes the power act (docs/contracts/legendary-powers.md "The Cube source"); it
            // refuses a power that is not built or one this class may not choose, before anything is stored.
            Need(Combat::ItemPowers::CubeSet(player, slot, power), "That power is not available yet.");
            CharacterDatabase.DirectExecute("REPLACE INTO dc_cube_slot (guid,slot,power_id) VALUES ({},{},'{}')", guid, slot,
                                            Escape(power));
            Items::RefreshCubedStats(player);
            LOG_INFO("server", "[DC cube] {} put power {} in slot {}", player->GetName(), power, slot);
        }
    } // namespace Detail
    namespace
    {
        // Skill of Nilfur (set_convert) and Hope of Cain (rare_upgrade), plan 7 row 6, and Law of Kulle
        // (reforge, row 9): the item is consumed, its gems come back, and a new item is rolled in its
        // place, in one account operation.
        // Nilfur: another piece of the same set from the drop pool, rolled for the piece's own class (the set caches' rule)
        // and never Ancient or Primal (D3); a crafted item or a set of fewer than crafting/cube_set_min_pieces pieces is
        // refused. Hope: a legendary or set item of the Rare's item type through the drop's own pick (Loot::PickBaseItem:
        // equal chance, never a cache-only item), rolled for the upgrader's class or a class-only item's
        // own (D3's Smart Loot), with the drop's Ancient and Primal rule. Both roll at the character's level,
        // as Kadala and the slot vendors do: a rolled item stores no level of its own.
        // Kulle: the same legendary or set item rolled again as a fresh drop (every affix and power new, the Mystic's changes
        // gone with the old instance), not a crafted one (maxroll); Ancient and Primal at the drop's rates whatever it was, for
        // the reforger's class or a class-only item's own (D3: Smart Loot always, never another class's primary stat).
        // Curiosity of Lorath Nahr (primal_upgrade, row 5): the same item rolled again at quality
        // `primal` (every affix, socket row and power at the top of its range), for the upgrader's class or a class-only item's
        // own, not a crafted one; the new item carries its maker (Items::MarkMade; the one-worn rule, dc_made_rule.h, counts it).
        // The Archive's commit (extract): the account learns the power in the same transaction as the ledger spend and the
        // destroyed item (INSERT IGNORE: a second tab's extraction of the same power is a no-op, never an error).
        void FinishExtract(Player* player, Cube::Recipe const& recipe, std::string const& itemName,
                           std::pair<uint32, std::string> const& account, std::string const& power,
                           CharacterDatabaseTransaction const& tx)
        {
            tx->Append("INSERT IGNORE INTO dc_cube_power (account_id,mode,power_id) VALUES ({},'{}','{}')", account.first,
                       account.second, Escape(power));
            Economy::Charge(player, 0);
            Save(player, tx);
            ChatHandler(player->GetSession()).PSendSysMessage("{}: the power of {} is yours.", recipe.name, itemName);
            LOG_INFO("server", "[DC cube] {} extracted power {} from {}", player->GetName(), power, itemName);
        }
        void TransmuteItem(Player* player, Cube::Recipe const& recipe, uint32 guid)
        {
            auto* item = Owned(player, guid);
            auto instance = Rolled(item);
            Need(Cube::Takes(recipe, instance.rarity), "The Cube takes no item of that rarity for this recipe.");
            Need(SalvageEligible(item->IsEquipped(), item->IsInTrade()), "Unequip the item first.");
            auto base = WorldDatabase.Query("SELECT b.slot,b.type,b.designated_class,b.set_name,b.craft_only,"
                                            "COALESCE(sc.class_key,'') FROM dc_base_item b LEFT JOIN dc_set_class sc "
                                            "ON sc.set_name=b.set_name WHERE b.entry={}",
                                            instance.baseItem);
            Need(bool(base), "Missing base item.");
            std::string const slot = (*base)[0].Get<std::string>(), type = (*base)[1].Get<std::string>(),
                              designated = (*base)[2].Get<std::string>(), setName = (*base)[3].Get<std::string>(),
                              craftOnly = (*base)[4].Get<std::string>(), setClass = (*base)[5].Get<std::string>();
            std::string const playerClass = Items::ClassKeyOf(player->getClass());
            uint32 pick = 0;
            std::string rollClass, quality, power;
            std::optional<std::pair<uint32, std::string>> account;
            if (recipe.rule == "set_convert")
            {
                Need(!instance.crafted && craftOnly != "yes", "The Cube takes no crafted item for this recipe.");
                std::vector<uint32> pieces;
                std::map<uint32, std::string> designation;
                if (auto rows = WorldDatabase.Query(
                        "SELECT b.entry,b.rarity,b.pool_version,b.craft_only,IF(c.item_entry IS NULL,'no','yes'),"
                        "b.designated_class FROM dc_base_item b LEFT JOIN (SELECT DISTINCT item_entry FROM "
                        "dc_bounties_cache_legendary) c ON c.item_entry=b.entry WHERE b.set_name='{}' ORDER BY b.entry",
                        Escape(setName)))
                    do
                    {
                        auto* f = rows->Fetch();
                        if (RollClass::InDropPool(f[1].Get<std::string>(), f[2].Get<std::string>(),
                                                  f[3].Get<std::string>(), f[4].Get<std::string>()))
                        {
                            pieces.push_back(f[0].Get<uint32>());
                            designation[pieces.back()] = f[5].Get<std::string>();
                        }
                    } while (rows->NextRow());
                auto const least = static_cast<unsigned>(Tunables::Get("crafting", "cube_set_min_pieces"));
                auto const others = Cube::OtherPieces(pieces, instance.baseItem, least);
                if (setName.empty() || others.empty())
                    throw std::runtime_error("The Cube converts a piece of a set of at least " + std::to_string(least) +
                                             " items.");
                pick = others[urand(0, uint32(others.size() - 1))];
                rollClass = SlotVendor::RollClassFor(designation[pick], setClass, playerClass);
                quality = "normal"; // D3: the new piece never rolls Ancient or Primal, even from one that was
            }
            else if (recipe.rule == "rare_upgrade")
            {
                rollClass = SlotVendor::RollClassFor(designated, "", playerClass);
                Kadala::SlotFilter const filter{slot, {type}};
                pick = Loot::PickBaseItem(Loot::Rarity::Legendary, player->GetLevel(), rollClass, 0, &filter);
                Need(pick != 0, "The Cube has no legendary of that item type for you.");
            }
            else if (recipe.rule == "reforge")
            {
                Need(!instance.crafted && craftOnly != "yes", "The Cube takes no crafted item for this recipe.");
                pick = instance.baseItem;
                rollClass = SlotVendor::RollClassFor(designated, "", playerClass);
            }
            else if (recipe.rule == "primal_upgrade")
            {
                Need(!instance.crafted && craftOnly != "yes", "The Cube takes no crafted item for this recipe.");
                pick = instance.baseItem;
                rollClass = SlotVendor::RollClassFor(designated, "", playerClass);
                quality = "primal";
            }
            else if (recipe.rule == "extract")
            {
                // The Archive of Tal Rasha (extract, row 11): the item is destroyed and its power is learned by
                // the account and mode (dc_cube_power). Every refusal comes before anything is taken (Cube::ExtractRefusal).
                Need(craftOnly != "yes" && !instance.crafted, "The Cube takes no crafted item for this recipe.");
                auto id = WorldDatabase.Query("SELECT d3_id FROM dc_base_item WHERE entry={}", instance.baseItem);
                Need(bool(id), "Missing base item.");
                power = Combat::ItemPowers::PowerIdOf((*id)[0].Get<std::string>());
                account = CubeAccount(player);
                Need(bool(account), "Kanai's Cube needs the account ledger.");
                bool const listed = bool(WorldDatabase.Query(std::string("SELECT 1 ") + CubePowerItems + " AND b.d3_id='{}'",
                                                             Escape(power)));
                bool const known = bool(CharacterDatabase.Query(
                    "SELECT 1 FROM dc_cube_power WHERE account_id={} AND mode='{}' AND power_id='{}'", account->first,
                    account->second, Escape(power)));
                auto const refusal = Cube::ExtractRefusal(Combat::ItemPowers::Built(power), listed, known);
                Need(refusal.empty(), refusal.c_str());
            }
            Amounts spend;
            for (auto const& line : recipe.lines)
                if (line.kind == "spend")
                    spend[line.entry] += line.amount;
            for (auto const& [entry, amount] : spend)
                Need(AccountMaterial(entry), "Kanai's Cube needs the account ledger.");
            CheckMaterials(player, spend);
            // The gems come back as a salvage returns them: a normal gem as a stack count, a legendary one as its own rank.
            Amounts gems;
            std::vector<Items::Affix> legendaryGems;
            for (auto const& a : instance.affixes)
                if (a.kind == "gem")
                {
                    Need(a.gemEntry != 0, "A socketed gem has invalid data.");
                    if (a.legendaryRank)
                        legendaryGems.push_back(a);
                    else
                        ++gems[a.gemEntry];
                }
            Amounts room = gems;
            for (auto const& gem : legendaryGems)
                ++room[gem.gemEntry];
            CheckRoom(player, room);
            Need(Economy::CanAfford(player, 0), "Unable to access gold.");
            auto tx = PlayerEconomy::BeginTransaction();
            SpendMaterials(player, spend);
            Grant(player, gems);
            for (auto const& gem : legendaryGems)
                GrantGem(player, gem, tx);
            // The item goes first, inside this transaction, so its bag cell takes the new one (the set caches' order).
            std::string const gone = item->GetTemplate()->Name1;
            Items::DestroyWithRows(player, item, tx);
            item = nullptr;
            if (recipe.rule == "extract")
                return FinishExtract(player, recipe, gone, *account, power, tx);
            // A Cube roll is a craft, not a monster drop: Ancient and Primal need the level only, on any difficulty (D3).
            // Nilfur (normal) and Curiosity (primal) decided theirs above.
            if (quality.empty())
                quality = Items::RollQuality(player, pick, player->GetLevel(), 0, true);
            auto staged = Items::StageRoll(player, pick, player->GetLevel(), "", tx, rollClass, quality);
            Need(staged && staged->GetItem(), "The Cube could not make the new item. Nothing was changed.");
            if (recipe.rule == "primal_upgrade")
                Items::MarkMade(player, staged->GetItem(), player, tx);
            Economy::Charge(player, 0);
            Save(player, tx);
            Item* made = staged->Publish();
            ChatHandler(player->GetSession())
                .PSendSysMessage("{}: {}.", recipe.name, made ? made->GetTemplate()->Name1 : MaterialName(pick));
            LOG_INFO("server", "[DC cube] {} transmuted {} with item {} ({} base {}) into base {} for {}", player->GetName(),
                     recipe.id, guid, instance.rarity, instance.baseItem, pick, rollClass);
        }
        // Caldesann's Despair's data: dc_cube_augment (cube_augment.csv, generate_cube.py).
        Cube::AugmentRules CubeAugmentRules()
        {
            Cube::AugmentRules rules;
            if (auto rows = WorldDatabase.Query("SELECT part,`key`,value FROM dc_cube_augment"))
                do
                {
                    auto* f = rows->Fetch();
                    std::string const part = f[0].Get<std::string>(), key = f[1].Get<std::string>(),
                                      value = f[2].Get<std::string>();
                    uint64 const number = std::strtoull(value.c_str(), nullptr, 10);
                    if (part == "colour")
                        rules.stat[key] = value;
                    else if (part == "per_rank")
                        rules.perRank = number;
                    else
                        rules.minRank[key] = number;
                } while (rows->NextRow());
            return rules;
        }
    } // namespace
    namespace Detail
    {
        // What a bag item is to a recipe's take lines: legendary_gem, a normal gem's tier (Flawless Royal), or empty for any
        // other item or one the player does not own. The grid matches a recipe on these (Cube::Match).
        std::string CubeGemClass(Player* player, uint32 guid)
        {
            auto* item = player->GetItemByGuid(ObjectGuid(HighGuid::Item, guid));
            if (!item || item->GetOwnerGUID() != player->GetGUID())
                return {};
            if (Items::LegendaryGemItemOf(item->GetEntry()))
                return Cube::LegendaryGem;
            if (auto row = WorldDatabase.Query("SELECT tier FROM dc_gem_item WHERE entry={}", item->GetEntry()))
                return (*row)[0].Get<std::string>();
            return {};
        }
    } // namespace Detail
    namespace
    {
        // Caldesann's Despair (augment, row 7): the Ancient or Primal item stays and gains one row of kind
        // `augment` (the attribute of the gems' colour, +5 of it for each rank of the Legendary Gem; D3: "overwrites, not
        // stacks", so an earlier augment row goes); the Legendary Gem and the three Flawless Royal gems are consumed. All checks
        // run before anything is taken. Cube::Augment is the rule; this fetches what it reads. The item is never worn here, so
        // nothing needs refreshing: Apply reads the row when it is equipped, as any affix.
        void TransmuteAugment(Player* player, Cube::Recipe const& recipe, uint32 guid, std::vector<Cube::Cell> const& cells)
        {
            auto* item = Owned(player, guid);
            auto instance = Rolled(item);
            Need(Cube::Takes(recipe, instance.rarity), "The Cube takes no item of that rarity for this recipe.");
            Need(SalvageEligible(item->IsEquipped(), item->IsInTrade()), "Unequip the item first.");
            struct Stack
            {
                Item* item;
                uint32 count;
            };
            std::vector<Stack> stacks;
            std::set<uint32> seen{guid};
            uint32 legendary = 0;
            std::vector<std::string> colours;
            for (auto const& cell : cells)
            {
                Need(seen.insert(cell.entry).second, "Put each gem in the Cube once.");
                auto* gem = Owned(player, cell.entry);
                Need(!gem->IsEquipped() && cell.amount <= gem->GetCount(), "Choose gems in your bags.");
                stacks.push_back({gem, uint32(cell.amount)});
                if (CubeGemClass(player, cell.entry) == Cube::LegendaryGem)
                    legendary = cell.entry;
                else if (auto row = WorldDatabase.Query("SELECT colour FROM dc_gem_item WHERE entry={}", gem->GetEntry()))
                    colours.insert(colours.end(), size_t(cell.amount), (*row)[0].Get<std::string>());
            }
            Need(legendary != 0, "The Cube cannot use what is in the grid.");
            std::string label;
            if (auto row = WorldDatabase.Query("SELECT s.label FROM dc_base_item b JOIN dc_cube_slot_item s ON s.item_slot=b.slot "
                                               "WHERE b.entry={}",
                                               instance.baseItem))
                label = (*row)[0].Get<std::string>();
            auto const augment = Cube::Augment(CubeAugmentRules(), instance.qualityTier, label,
                                               Items::LegendaryGemRankOf(legendary), colours);
            Need(augment.refusal.empty(), augment.refusal.c_str());
            unsigned next = 0;
            for (auto const& a : instance.affixes)
                next = std::max(next, a.seq + 1);
            Need(next < 65536, "Too many affix rows.");
            Need(Economy::CanAfford(player, 0), "Unable to access gold.");
            auto tx = PlayerEconomy::BeginTransaction();
            tx->Append("DELETE FROM dc_item_affix WHERE item_guid={} AND kind='augment'", guid);
            Items::Affix row;
            row.seq = next;
            row.affixId = augment.stat;
            row.value = row.rangeMin = row.rangeMax = double(augment.value);
            row.kind = "augment";
            AffixRow(tx, guid, row);
            for (auto const& stack : stacks)
            {
                uint32 count = stack.count;
                player->DestroyItemCount(stack.item, count, true);
            }
            Economy::Charge(player, 0);
            Save(player, tx);
            ChatHandler(player->GetSession())
                .PSendSysMessage("{}: {} gains +{} {}.", recipe.name, item->GetTemplate()->Name1, augment.value, augment.stat);
            LOG_INFO("server", "[DC cube] {} augmented item {} (base {}, {}) with +{} {}", player->GetName(), guid,
                     instance.baseItem, instance.qualityTier, augment.value, augment.stat);
        }
    } // namespace
    namespace Detail
    {
        // A convert recipe (D3's Iben Fahd three): the controlling item stays; the recipe's spend lines leave the ledger and
        // the make line of the item's rarity enters it, in one account operation. An item recipe goes to TransmuteItem.
        void Transmute(Player* player, std::string const& id, uint32 guid, std::vector<Cube::Cell> const& gems)
        {
            CubeInReach(player);
            auto recipes = CubeRecipes();
            auto const* recipe = Cube::Find(recipes, id);
            Need(recipe && (recipe->rule == "convert" || recipe->rule == "augment" || Cube::Consumes(*recipe)), "Choose a recipe.");
            if (recipe->rule == "augment")
                return TransmuteAugment(player, *recipe, guid, gems);
            if (recipe->rule != "convert")
                return TransmuteItem(player, *recipe, guid);
            auto instance = Rolled(Owned(player, guid));
            auto const* make = Cube::Makes(*recipe, instance.rarity);
            Need(make, "The Cube takes no item of that rarity for this recipe.");
            Amounts spend;
            for (auto const& line : recipe->lines)
                if (line.kind == "spend")
                    spend[line.entry] += line.amount;
            for (auto const& [entry, amount] : spend)
                Need(AccountMaterial(entry), "Kanai's Cube needs the account ledger.");
            Need(AccountMaterial(make->entry), "Kanai's Cube needs the account ledger.");
            CheckMaterials(player, spend);
            Need(Economy::CanAfford(player, 0), "Unable to access gold.");
            SpendMaterials(player, spend);
            Grant(player, {{make->entry, make->amount}});
            auto tx = PlayerEconomy::BeginTransaction();
            Economy::Charge(player, 0);
            Save(player, tx);
            ChatHandler(player->GetSession())
                .PSendSysMessage("{}: {} {}.", recipe->name, make->amount, MaterialName(make->entry));
            LOG_INFO("server", "[DC cube] {} transmuted {} with item {} ({}) into {} x{}", player->GetName(), id, guid,
                     instance.rarity, make->entry, make->amount);
        }
    } // namespace Detail
    namespace
    {
        // A deleted character takes its Cube slots with it; the account's extracted powers stay (dc_cube_power is not theirs).
        // At login the character's chosen powers go into the framework's Cube list, which is in memory only and forgotten at
        // logout (docs/contracts/legendary-powers.md "The Cube source"). A row the framework refuses (a power no longer built, a
        // class that may not choose it) is left as it is and does nothing.
        class CubeCharacters final : public PlayerScript
        {
        public:
            CubeCharacters()
                : PlayerScript("dc_cube_characters", {PLAYERHOOK_ON_DELETE_FROM_DB, PLAYERHOOK_ON_LOGIN})
            {
            }
            void OnPlayerLogin(Player* player) override
            {
                if (auto rows = CharacterDatabase.Query("SELECT slot,power_id FROM dc_cube_slot WHERE guid={} ORDER BY slot",
                                                        player->GetGUID().GetCounter()))
                    do
                    {
                        auto* f = rows->Fetch();
                        if (!Combat::ItemPowers::CubeSet(player, f[0].Get<uint32>(), f[1].Get<std::string>()))
                            LOG_WARN("server", "[DC cube] {}'s power {} in slot {} is not in play", player->GetName(),
                                     f[1].Get<std::string>(), f[0].Get<uint32>());
                    } while (rows->NextRow());
                Items::RefreshCubedStats(player);
            }
            void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
            {
                trans->Append("DELETE FROM dc_cube_slot WHERE guid={}", guid);
            }
        };
    } // namespace
    namespace Detail
    {
        void RegisterCubeScripts()
        {
            new CubeCharacters();
        }
    } // namespace Detail
} // namespace DC::Crafting
