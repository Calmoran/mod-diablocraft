// Items: the startup load, the equip, login and removal hooks, the login sweeps, the .dc commands and the script registration.
#include "dc_items_internal.h"
#include "dc_made_rule.h"
#include "dc_roll_class.h"

#include "../combat/dc_item_powers.h"
#include "../common/dc_tunables.h"
#include "../difficulty/dc_difficulty.h"
#include "../rifts/dc_rifts.h"

#include "Bag.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WorldSession.h"

#include <algorithm>
#include <cctype>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (70): default item level for .dc item roll when none is given; GM command default.
// Constant (910016, 81203, 81204, 910002): Tome entry, identify spell ids, stash NPC entry; Identifiers.

namespace DC::Items
{
using namespace Detail;

namespace
{
class ItemWorld final : public WorldScript
{
public:
    ItemWorld() : WorldScript("dc_item_world", {WORLDHOOK_ON_STARTUP}) { }
    void OnStartup() override
    {
        try
        {
            std::unordered_map<std::uint32_t, BaseItem> loadedItems;
            QueryResult items = WorldDatabase.Query(
                "SELECT entry, d3_id, d3_name, slot, type, rarity, preset_affixes,designated_class FROM dc_base_item");
            if (!items)
                throw std::runtime_error("dc_base_item is missing or empty");
            do
            {
                Field* fields = items->Fetch();
                BaseItem base;
                base.entry = fields[0].Get<uint32>();
                base.d3Id = fields[1].Get<std::string>();
                base.name = fields[2].Get<std::string>();
                base.slot = fields[3].Get<std::string>();
                base.type = fields[4].Get<std::string>();
                base.rarity = fields[5].Get<std::string>();
                base.presets = Split(fields[6].Get<std::string>(), ';');
                base.designatedClass = fields[7].Get<std::string>();
                loadedItems.emplace(base.entry, std::move(base));
            } while (items->NextRow());

            // The follower relics' own affix counts (followers_0006_relic_rolls.sql) and the Ancient switch. The table is
            // required: a relic with no row would roll the rarity's counts.
            QueryResult relicRolls = WorldDatabase.Query(
                "SELECT item_entry, primary_affixes, secondary_affixes FROM dc_follower_relic_roll");
            if (!relicRolls)
                throw std::runtime_error("dc_follower_relic_roll is missing or empty; apply followers_0006_relic_rolls.sql");
            do
            {
                Field* fields = relicRolls->Fetch();
                if (auto relic = loadedItems.find(fields[0].Get<uint32>()); relic != loadedItems.end())
                {
                    relic->second.relicPrimary = fields[1].Get<uint32>();
                    relic->second.relicSecondary = fields[2].Get<uint32>();
                }
                else
                    LOG_ERROR("server", "[DC items] dc_follower_relic_roll names item {}, which is not a base item",
                              fields[0].Get<uint32>());
            } while (relicRolls->NextRow());
            QueryResult relicSwitch = WorldDatabase.Query(
                "SELECT value FROM dc_follower_relic_rule WHERE rule='relic_ancient_primal'");
            if (!relicSwitch)
                throw std::runtime_error("dc_follower_relic_rule has no relic_ancient_primal row; apply followers_0006_relic_rolls.sql");
            bool const loadedRelicSwitch = (*relicSwitch)[0].Get<double>() > 0.0;

            // Issue #47: every class's main stat, keyed the way base_items.csv
            // spells a designated class.
            std::unordered_map<std::string, std::string> mainStats;
            QueryResult classes = WorldDatabase.Query("SELECT class, primary_stat FROM dc_class_primary_stats");
            if (!classes)
                throw std::runtime_error("dc_class_primary_stats is missing or empty");
            do
            {
                Field* fields = classes->Fetch();
                std::string const stat = StatAffix(fields[1].Get<std::string>());
                if (stat.empty())
                    LOG_ERROR("server", "[DC items] class_primary_stats.csv: {} has main stat '{}', which no "
                              "main-stat affix rolls", fields[0].Get<std::string>(), fields[1].Get<std::string>());
                else
                    mainStats[ClassKey(fields[0].Get<std::string>())] = stat;
            } while (classes->NextRow());
            // The playable classes, and the
            // catalogue id each class's skill-affix rows carry.
            std::unordered_map<unsigned, std::string> loadedKeys;
            std::unordered_map<std::string, std::uint32_t> loadedIds;
            QueryResult mapped = WorldDatabase.Query("SELECT class_id, class_key, wow_class_id FROM dc_class_map");
            if (!mapped)
                throw std::runtime_error("dc_class_map is missing or empty");
            do
            {
                Field* fields = mapped->Fetch();
                loadedIds[fields[1].Get<std::string>()] = fields[0].Get<uint32>();
                loadedKeys[fields[2].Get<uint32>()] = fields[1].Get<std::string>();
            } while (mapped->NextRow());
            for (auto const& [key, id] : loadedIds)
                if (!mainStats.count(key))
                    LOG_ERROR("server", "[DC items] playable class '{}' has no class_primary_stats.csv row; its "
                              "ordinary items roll no main-stat affix", key);
            for (std::string const& designated : ResolveMainStats(loadedItems, mainStats))
                LOG_ERROR("server", "[DC items] designated class '{}' has no class_primary_stats.csv row; its "
                          "items roll no main-stat affix", designated);

            std::unordered_map<std::string, std::unordered_map<std::string, std::vector<PoolEntry>>> loadedPools;
            QueryResult affixes = WorldDatabase.Query(
                "SELECT slot, affix_id, affix_name, kind, value_min, value_max, item_level_bracket, is_percent, "
                "value_step, value_min2, value_max2, weapon_class, display_order FROM dc_affix_pool");
            if (!affixes)
                throw std::runtime_error("dc_affix_pool is missing or empty");
            do
            {
                Field* fields = affixes->Fetch();
                PoolEntry entry;
                std::string const slot = fields[0].Get<std::string>();
                entry.affixId = fields[1].Get<std::string>();
                entry.name = fields[2].Get<std::string>();
                entry.kind = fields[3].Get<std::string>();
                entry.min = fields[4].Get<double>();
                entry.max = fields[5].Get<double>();
                entry.bracket = fields[6].Get<std::string>();
                entry.isPercent = fields[7].Get<int64>() != 0;
                entry.step = fields[8].IsNull() ? 0 : fields[8].Get<double>();
                entry.min2 = fields[9].IsNull() ? 0 : fields[9].Get<double>();
                entry.max2 = fields[10].IsNull() ? 0 : fields[10].Get<double>();
                entry.weaponClass = fields[11].Get<std::string>();
                entry.order = fields[12].IsNull() ? 0 : fields[12].Get<uint32>();
                loadedPools[slot][entry.bracket].push_back(entry);
            } while (affixes->NextRow());

            // An item's own range for a preset its slot's pool lacks. Without the table
            // those presets are skipped as before; the rest of the roll is unaffected.
            std::unordered_map<std::uint32_t, std::unordered_map<std::string, std::vector<PoolEntry>>> loadedPresets;
            if (QueryResult presets = WorldDatabase.Query(
                    "SELECT entry, affix_id, affix_name, kind, value_min, value_max, value_step, item_level_bracket, "
                    "is_percent, display_order FROM dc_item_preset_range"))
                do
                {
                    Field* fields = presets->Fetch();
                    PoolEntry entry;
                    entry.affixId = fields[1].Get<std::string>();
                    entry.name = fields[2].Get<std::string>();
                    entry.kind = fields[3].Get<std::string>();
                    entry.min = fields[4].Get<double>();
                    entry.max = fields[5].Get<double>();
                    entry.step = fields[6].IsNull() ? 0 : fields[6].Get<double>();
                    entry.bracket = fields[7].Get<std::string>();
                    entry.isPercent = fields[8].Get<int8>() != 0;
                    entry.order = fields[9].Get<uint32>();
                    loadedPresets[fields[0].Get<uint32>()][entry.bracket].push_back(entry);
                } while (presets->NextRow());
            else
                LOG_ERROR("server", "[DC items] dc_item_preset_range is missing or empty; apply "
                          "items_0024_item_preset_ranges.sql. Presets outside their slot's pool are skipped");

            // G1: the one sourced type -> damage bracket map. A weapon row with no class here
            // cannot roll its elemental damage; the generator refuses to emit such a row, and
            // this load refuses to start without the table.
            QueryResult weaponClassRows = WorldDatabase.Query("SELECT weapon_type, weapon_class FROM dc_weapon_class");
            if (!weaponClassRows)
                throw std::runtime_error("dc_weapon_class is missing or empty");
            std::unordered_map<std::string, std::string> loadedWeaponClasses;
            do
            {
                Field* fields = weaponClassRows->Fetch();
                loadedWeaponClasses[fields[0].Get<std::string>()] = fields[1].Get<std::string>();
            } while (weaponClassRows->NextRow());

            if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_item_instance") ||
                !CharacterDatabase.Query("SELECT COUNT(*) FROM dc_item_affix"))
                throw std::runtime_error("dc_item_instance/dc_item_affix migrations have not been applied");
            if (!CharacterDatabase.Query("SELECT COUNT(quality_tier) FROM dc_item_unidentified"))
                throw std::runtime_error("dc_item_unidentified has no quality_tier; apply loot_0011_quality_tier.sql");

            std::unordered_map<std::string, SkillAffix> loadedSkills;
            std::unordered_map<std::string, std::vector<SkillAffix>> loadedGroups;
            QueryResult skills = WorldDatabase.Query(
                "SELECT group_id,affix_id,skill_name,affix_name,class_id,skill_id FROM dc_skill_affix "
                "ORDER BY group_id,choice_index");
            if (!skills) throw std::runtime_error("dc_skill_affix is missing or empty");
            do
            {
                Field* fields = skills->Fetch();
                SkillAffix skill{fields[1].Get<std::string>(), fields[2].Get<std::string>(),
                                 fields[3].Get<std::string>(), fields[4].Get<uint32>(),
                                 fields[5].Get<uint32>()};
                if (!skill.skillId)
                    throw std::runtime_error("dc_skill_affix row has no skill_id: " + skill.id);
                loadedGroups[fields[0].Get<std::string>()].push_back(skill);
                loadedSkills.emplace(skill.id, skill);
            } while (skills->NextRow());
            for (auto const& [slot, brackets] : loadedPools)
                for (auto const& [bracket, entries] : brackets)
                    for (auto const& entry : entries)
                        if (entry.affixId.rfind("skill_", 0) == 0 && !loadedGroups.count(entry.affixId))
                            throw std::runtime_error("Unresolved skill pool: " + entry.affixId);
            // Rule 6: every playable class has its own choices in every skill
            // group; one without them rolls no skill affix on that slot.
            for (auto const& [groupId, choices] : loadedGroups)
                for (auto const& [key, id] : loadedIds)
                    if (DC::RollClass::ChoicesFor(choices, id).empty())
                        LOG_ERROR("server", "[DC items] dc_skill_affix group {} has no choice for playable class '{}'; "
                                  "its items roll no skill affix there. Re-run generate_skill_affixes.py", groupId, key);

            std::unordered_map<uint32,std::unordered_map<std::string,GemEffect>> loadedGems;
            auto gems=WorldDatabase.Query("SELECT e.entry,e.slot_class,e.stat,e.value,g.name FROM dc_gem_effect e JOIN dc_gem_item g ON g.entry=e.entry");
            if(!gems) throw std::runtime_error("Missing crafting gem effects");
            do {auto* f=gems->Fetch(); loadedGems[f[0].Get<uint32>()][f[1].Get<std::string>()]={f[2].Get<std::string>(),f[4].Get<std::string>(),f[3].Get<double>()};} while(gems->NextRow());
            // A class with no passives rolls none on the amulet (the roll skips it).
            std::unordered_map<std::uint32_t, std::vector<std::string>> loadedPassives;
            if (QueryResult passives = WorldDatabase.Query(
                    "SELECT p.class_id, l.passive_name FROM dc_class_passive p "
                    "JOIN dc_class_passive_label l ON l.spell_id = p.spell_id ORDER BY p.class_id, p.unlock_level, p.spell_id"))
                do
                    loadedPassives[(*passives)[0].Get<uint32>()].push_back((*passives)[1].Get<std::string>());
                while (passives->NextRow());
            else
                LOG_ERROR("server", "[DC items] dc_class_passive is missing or empty; the Hellfire Amulet rolls no passive");
            std::lock_guard<std::mutex> lock(dataMutex);
            classPassiveNames = std::move(loadedPassives);
            gemEffects=std::move(loadedGems);
            baseItems = std::move(loadedItems);
            relicAncientPrimal = loadedRelicSwitch;
            pools = std::move(loadedPools);
            itemPresetRanges = std::move(loadedPresets);
            skillAffixes = std::move(loadedSkills);
            skillGroups = std::move(loadedGroups);
            weaponClassByType = std::move(loadedWeaponClasses);
            classKeys = std::move(loadedKeys);
            classIds = std::move(loadedIds);
            classMainStats = std::move(mainStats);
            dataReady = true;
            LOG_INFO("server.loading", "[DC items] Loaded {} base items and {} slot affix pools",
                     baseItems.size(), pools.size());
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("server", "D3 item startup failed: {}. Rolling is disabled.", error.what());
        }
    }
};

// An unidentified shell and its row must exist or not
// exist together. Either half alone is a defect, never a silent roll: rolling a
// row whose item is gone would hand out a free legendary, and rolling a shell
// whose row is gone would invent an item the drop never chose.
// Legendary powers: the tooltip reads dc_item_affix itself (Lua), so a bag item whose power row came after it dropped
// needs its roll stored before the tooltip is built: read every backpack and bag item that has an item-owned power once at login (Load stores
// the missing roll). Worn items are read by Apply. Bank, stash, mail, trade and buyback items get theirs when they are worn or in a bag at a login.
void SweepPowerRolls(Player* player)
{
    auto read = [](Item* item)
    {
        if (item && DC::Combat::ItemPowers::HasItemPower(item->GetEntry()))
            Load(item->GetGUID().GetCounter());
    };
    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        read(player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));
    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        if (Bag* bag = player->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                read(bag->GetItemByPos(slot));
}

void SweepUnidentified(Player* player)
{
    if (!player)
        return;
    std::uint64_t const guid = player->GetGUID().GetRawValue();
    QueryResult rows = CharacterDatabase.Query(
        "SELECT item_guid, base_item FROM dc_item_unidentified WHERE owner_guid={}", guid);
    if (!rows)
        return;
    unsigned orphanRows = 0;
    do
    {
        ObjectGuid const itemGuid = ObjectGuid::Create<HighGuid::Item>((*rows)[0].Get<uint64>());
        // item_guid is the counter, which is what ObjectGuid::Create takes.
        if (player->GetItemByGuid(itemGuid))
            continue;
        // The item is not on this character. It may have been traded, mailed or
        // destroyed; the row stays until the item is gone for good, because the
        // new holder still needs it to identify. Only a row whose item exists
        // nowhere is a leak, and that is a question for the item's own
        // destruction path, not for a login. Logged, never guessed at.
        ++orphanRows;
    } while (rows->NextRow());
    if (orphanRows)
        LOG_INFO("server", "[DC items] {} has {} unidentified row(s) whose item is not in their bags; "
                           "left alone (traded, mailed or banked items keep their row)",
                 player->GetName(), orphanRows);

    // The other half: a shell in the bag with no row cannot be identified and
    // would sit there forever. It is reported, not rolled - the drop context is
    // gone and inventing one would be inventing an item.
    unsigned orphanShells = 0;
    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
    {
        Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot);
        if (!item || !IsShellTemplate(item->GetEntry()))
            continue;
        if (CharacterDatabase.Query("SELECT 1 FROM dc_item_unidentified WHERE item_guid={}",
                                    item->GetGUID().GetCounter()))
            continue;
        ++orphanShells;
    }
    if (orphanShells)
        LOG_ERROR("server", "[DC items] {} holds {} unidentified shell(s) with no dc_item_unidentified row; "
                            "they cannot be identified and were NOT rolled. Investigate before deleting.",
                  player->GetName(), orphanShells);
}

class ItemPlayer final : public PlayerScript
{
public:
    ItemPlayer() : PlayerScript("dc_item_player", {PLAYERHOOK_ON_EQUIP, PLAYERHOOK_ON_UNEQUIP_ITEM,
        PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_CUSTOM_SCALING_STAT_VALUE_BEFORE,
        PLAYERHOOK_CAN_EQUIP_ITEM}) { }

    // An unidentified item cannot be equipped. This is
    // the veto rather than a post-equip undo, so the item never reaches a slot
    // and no stat contribution is ever applied and removed.
    bool OnPlayerCanEquipItem(Player* player, uint8 slot, uint16&, Item* item, bool, bool notLoading) override
    {
        if (!player || !item)
            return true;
        if (!IsShellTemplate(item->GetEntry()))
            // A worn set that logs in as it was saved is kept (an old pair counts once: CountedLegendaryGems).
            // So is a made Primal past the limit (dc_made_rule.h): the rule refuses only a new equip.
            return !notLoading || (UniqueEquippedAllows(player, slot, item) && MadeEquipAllows(player, slot, item));
        if (player->GetSession())
            ChatHandler(player->GetSession()).SendSysMessage("Identify it first.");
        return false;
    }
    void OnPlayerCustomScalingStatValueBefore(Player* player, ItemTemplate const* proto,
        uint8 slot, bool apply, uint32&) override
    {
        // This hook runs for _ApplyItemBonuses even on zero-native-stat templates.
        // Native durability transitions call it once on break/repair; no hit polling.
        if (slot >= EQUIPMENT_SLOT_END) return;
        if (auto* item=player->GetItemByPos(INVENTORY_SLOT_BAG_0,slot);
            item && item->GetTemplate()==proto)
            Apply(player,item,apply);
    }
    void OnPlayerLogin(Player* player) override
    {
        {
            std::lock_guard<std::mutex> lock(bonusMutex);
            skillBonuses.erase(player->GetGUID().GetRawValue());
            weaponExtra.erase(player->GetGUID().GetRawValue());
            grantedPassive.erase(player->GetGUID().GetRawValue());
            cubedStats.erase(player->GetGUID().GetRawValue());
        }
        for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
            Apply(player, player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot), true);
        SweepUnidentified(player);
        SweepPowerRolls(player);
    }
    void OnPlayerLogout(Player* player) override
    {
        std::lock_guard<std::mutex> lock(bonusMutex);
        skillBonuses.erase(player->GetGUID().GetRawValue());
        weaponExtra.erase(player->GetGUID().GetRawValue());
        grantedPassive.erase(player->GetGUID().GetRawValue());
        cubedStats.erase(player->GetGUID().GetRawValue());
    }
    void OnPlayerEquip(Player* player, Item* item, uint8, uint8, bool) override { Apply(player, item, true); }
    void OnPlayerUnequip(Player* player, Item* item) override { Apply(player, item, false); }
};

// Player::DestroyItem is the core's single destroy path; CanItemRemove is the
// hook it fires. Selling to a vendor keeps the item in buyback, so its rows stay
// until the buyback slot is actually destroyed.
class ItemRemoval final : public AllItemScript
{
public:
    ItemRemoval() : AllItemScript("dc_item_removal") { }
    bool CanItemRemove(Player* player, Item* item) override
    {
        if (item)
        {
            Apply(player, item, false);
            Erase(item->GetGUID().GetCounter());
        }
        return true;
    }
};

class ItemCommand final : public CommandScript
{
public:
    ItemCommand() : CommandScript("dc_item_command") { }
    Acore::ChatCommands::ChatCommandTable GetCommands() const override
    {
        using namespace Acore::ChatCommands;
        static ChatCommandTable items = {
            {"roll", HandleRoll, SEC_ADMINISTRATOR, Console::No},
            {"item", HandleItem, SEC_ADMINISTRATOR, Console::No},
            // The Ancient / Primal decision's state, and a GM's override of it.
            {"quality", HandleQuality, SEC_ADMINISTRATOR, Console::No},
            // Any legendary gem at any rank, for testing before the Guardian drops them.
            {"gem", HandleGem, SEC_ADMINISTRATOR, Console::No},
            // Mark one of your rolled items as made by you, as the Cube's Primal upgrade will.
            {"made", HandleMade, SEC_ADMINISTRATOR, Console::No},
            // What the inventory screen's AIO bridge runs through
            // Player:RunCommand, the same way the stash and the artisans do.
            {"socket", HandleSocket, SEC_PLAYER, Console::No},
        };
        static ChatCommandTable root = {{"dc", items}};
        return root;
    }

    static bool HandleRoll(ChatHandler* handler, uint32 baseItemId, Optional<uint32> itemLevel)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
        {
            handler->SendSysMessage("This command needs a player.");
            return false;
        }
        Item* item = RollItem(player, baseItemId, itemLevel.value_or(70));
        if (!item)
        {
            handler->SendSysMessage("Roll failed: unknown base item, item data not loaded, or bags full.");
            return false;
        }
        Report(handler, item->GetGUID().GetCounter());
        return true;
    }

    // `.dc quality` shows what the drop decision reads for you; `.dc quality force <normal|ancient|primal|off>`
    // makes every Legendary or Set drop, Kadala gamble and roll of yours that quality (gates and unlock
    // ignored). To test the gates instead, `.dc tunables set loot ancient_chance_pct 100`.
    static bool HandleMade(ChatHandler* handler, uint32 guid)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        Item* item = player ? player->GetItemByGuid(ObjectGuid(HighGuid::Item, guid)) : nullptr;
        std::optional<Instance> instance = item ? Get(guid) : std::nullopt;
        if (!instance)
        {
            handler->SendSysMessage("Usage: .dc made <item guid> (a rolled item you carry or wear)");
            return false;
        }
        CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
        MarkMade(player, item, player, transaction);
        player->SaveInventoryAndGoldToDB(transaction);
        CharacterDatabase.CommitTransaction(transaction);
        handler->PSendSysMessage("{} is marked as made by {}; {}", item->GetTemplate()->Name1, player->GetName(),
                                 MadePrimal(true, instance->qualityTier)
                                     ? "a Primal Ancient, so the one-worn limit counts it."
                                     : "not a Primal Ancient, so the one-worn limit does not count it.");
        return true;
    }

    static bool HandleQuality(ChatHandler* handler, Optional<std::string> verb, Optional<std::string> value)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
        {
            handler->SendSysMessage("This command needs a player.");
            return false;
        }
        std::uint64_t const key = player->GetGUID().GetRawValue();
        if (verb && *verb == "force")
        {
            std::string const choice = value ? *value : std::string();
            if (choice == "off")
            {
                std::lock_guard<std::mutex> lock(forceMutex);
                forcedQuality.erase(key);
            }
            else if (choice == "normal" || choice == "ancient" || choice == "primal")
            {
                std::lock_guard<std::mutex> lock(forceMutex);
                forcedQuality[key] = choice;
            }
            else
            {
                handler->SendSysMessage("Usage: .dc quality force <normal|ancient|primal|off>");
                return false;
            }
        }
        else if (verb)
        {
            handler->SendSysMessage("Usage: .dc quality [force <normal|ancient|primal|off>]");
            return false;
        }
        DC::Quality::Rule const rule = QualityRule();
        std::string forced = "off";
        {
            std::lock_guard<std::mutex> lock(forceMutex);
            auto found = forcedQuality.find(key);
            if (found != forcedQuality.end())
                forced = found->second;
        }
        std::ostringstream line;
        line.imbue(std::locale::classic());
        line << "Quality: forced " << forced << "; Ancient " << rule.ancientPct << "% and Primal " << rule.primalPct
             << "% of Legendary/Set drops from tier " << rule.minTier << " (yours " << DC::Difficulty::CurrentTier(player)
             << ") at item level " << rule.minItemLevel << "+; Primal unlocked: " << (PrimalUnlocked(player) ? "yes" : "no")
             << " (account solo Greater Rift " << DC::Rifts::AccountGreaterRiftBeatenSolo(player->GetGUID().GetCounter())
             << ", needs " << DC::Tunables::Get("loot", "primal_unlock_solo_gr") << ")";
        handler->SendSysMessage(line.str());
        LOG_INFO("server.loading", "[DC items output] {}", line.str());
        return true;
    }

    static bool HandleItem(ChatHandler* handler, Optional<uint32> itemGuid)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        if (!player)
        {
            handler->SendSysMessage("This command needs a player.");
            return false;
        }
        if (itemGuid)
        {
            Report(handler, *itemGuid);
            return true;
        }
        // No guid given: the item this player last rolled, else the first
        // equipped or carried item that has rows.
        if (std::uint64_t last = LastRolled(player->GetGUID().GetRawValue()))
        {
            Report(handler, last);
            return true;
        }
        for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
            if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                if (Get(item->GetGUID().GetCounter()))
                {
                    Report(handler, item->GetGUID().GetCounter());
                    return true;
                }
        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                if (Get(item->GetGUID().GetCounter()))
                {
                    Report(handler, item->GetGUID().GetCounter());
                    return true;
                }
        handler->SendSysMessage("No rolled item found in your equipment or backpack.");
        return false;
    }

    // .dc gem list | .dc gem <gem_id or item entry> [rank]: one legendary gem item at that rank (0 when left out).
    static bool HandleGem(ChatHandler* handler, std::string which, Optional<uint32> rank)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        try
        {
            if (!player)
                throw std::runtime_error("This command needs a player.");
            if (which == "list")
            {
                QueryResult rows = WorldDatabase.Query(
                    "SELECT i.entry,i.gem_id,g.gem_name FROM dc_legendary_gem_item i "
                    "LEFT JOIN dc_legendary_gem g ON g.gem_id=i.gem_id ORDER BY i.entry");
                NeedItem(bool(rows), "No legendary gem items are loaded.");
                do
                {
                    Field* f = rows->Fetch();
                    handler->PSendSysMessage("{} {} {}", f[0].Get<uint32>(), f[1].Get<std::string>(),
                                             f[2].Get<std::string>());
                } while (rows->NextRow());
                return true;
            }
            QueryResult row = WorldDatabase.Query(
                "SELECT entry FROM dc_legendary_gem_item WHERE gem_id='{}' OR entry={}", Escape(which),
                std::all_of(which.begin(), which.end(), ::isdigit) && !which.empty() ? which : "0");
            NeedItem(bool(row), "No such legendary gem. .dc gem list shows them.");
            CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
            Item* gem = GiveLegendaryGem(player, (*row)[0].Get<uint32>(), rank.value_or(0), transaction);
            NeedItem(gem, "No room in your bags.");
            player->SaveInventoryAndGoldToDB(transaction);
            NeedItem(CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get(),
                     "The gem could not be saved. Relog before trying again.");
            handler->PSendSysMessage("Gem {} at rank {} added.", gem->GetGUID().GetCounter(), rank.value_or(0));
            return true;
        }
        catch (std::exception const& error)
        {
            handler->SendErrorMessage(error.what());
            return false;
        }
    }

    // The field socket path. Player-level, because the inventory screen is
    // where it is used; every rule it could break is checked in SocketInField.
    static bool HandleSocket(ChatHandler* handler, uint32 itemGuid, uint32 gemGuid)
    {
        Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
        try
        {
            if (!player)
                throw std::runtime_error("This command needs a player.");
            SocketInField(player, itemGuid, gemGuid);
            return true;
        }
        catch (std::exception const& error)
        {
            handler->SendErrorMessage(error.what());
            return false;
        }
    }

    static void Report(ChatHandler* handler, std::uint64_t itemGuid)
    {
        std::optional<Instance> instance = Get(itemGuid);
        if (!instance)
        {
            // An unidentified shell already knows its quality (the beam showed it).
            if (auto shell = GetUnidentified(itemGuid))
            {
                std::string const line = "Item " + std::to_string(itemGuid) + ": unidentified " + shell->rarity +
                                         " shell [" + shell->qualityTier + "]";
                handler->SendSysMessage(line);
                LOG_INFO("server.loading", "[DC items output] {}", line);
                return;
            }
            handler->SendSysMessage("That item has no rolled rows.");
            return;
        }
        std::string name = "?";
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            auto base = baseItems.find(instance->baseItem);
            if (base != baseItems.end())
                name = base->second.name + " (" + base->second.slot + ", " +
                    (base->second.rarity.empty() ? "normal" : base->second.rarity) + ")";
        }
        auto emit = [&](std::string const& text)
        {
            handler->SendSysMessage(text);
            LOG_INFO("server.loading", "[DC items output] {}", text);
        };
        emit("Item " + std::to_string(itemGuid) + ": " + name + " [" + instance->qualityTier + "]");
        for (Affix const& affix : instance->affixes)
        {
            std::ostringstream line;
            line.imbue(std::locale::classic());
            line << "  " << affix.seq << " " << affix.kind << " " << affix.affixId;
            if (!affix.name.empty())
                line << " (" << affix.name << ")";
            if (affix.kind != "socket")
                line << " = " << affix.value << " [" << affix.rangeMin << "-" << affix.rangeMax << "]";
            emit(line.str());
        }
    }
};
} // namespace

std::uint32_t IdentifyItemSpell() { return IDENTIFY_ITEM_SPELL; }
std::uint32_t IdentifyTomeSpell() { return IDENTIFY_TOME_SPELL; }

void RegisterScripts()
{
    new ItemWorld();
    new ItemPlayer();
    new ItemRemoval();
    new ItemCommand();
    RegisterSlotVendorScripts();
    RegisterSetCacheScripts();
    FollowerGear::RegisterScripts();
}
}
