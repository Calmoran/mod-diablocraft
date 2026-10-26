#include "dc_inventory.h"

#include "../common/dc_common.h"
#include "../common/dc_account_economy.h"
#include "../classes/dc_classes.h"
#include "../classes/dc_potion.h"
#include "../combat/dc_item_powers.h"
#include "../rifts/dc_rifts.h"
#include "dc_identify.h"
#include "dc_identify_rule.h"
#include "dc_items.h"
#include "dc_trade_rule.h"
#include "../stats/dc_stats.h"
#include "Bag.h"
#include "Chat.h"
#include "Item.h"
#include "Log.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <iomanip>
#include <locale>
#include <memory>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (25600): upper bound on a packed bag/slot index; Matches the 8-bit bag/slot packing used two lines below it, but nothing states that.
// Constant (160): chat line width before wrapping; Output formatting.

namespace DC::Inventory
{
    namespace
    {
        using Acore::ChatCommands::ChatCommandTable;

        void Need(bool ok, char const* message)
        {
            if (!ok)
                throw std::runtime_error(message);
        }

        // ------------------------------------------------------------ addressing

        // The stash's encoding, unchanged, so one addon helper addresses both
        // screens and a cell moved between them needs no translation.
        void DecodeBag(std::int32_t index, std::uint8_t& bag, std::uint8_t& slot)
        {
            Need(index >= 0 && index < 25600, "That is not a bag slot.");
            bag = std::uint8_t(index / 100);
            slot = std::uint8_t(index % 100);
            if (bag == INVENTORY_SLOT_BAG_0)
            {
                Need(slot >= INVENTORY_SLOT_ITEM_START && slot < INVENTORY_SLOT_ITEM_END, "That is not a bag slot.");
                return;
            }
            Need(bag >= INVENTORY_SLOT_BAG_START && bag < INVENTORY_SLOT_BAG_END, "That is not a bag slot.");
        }

        // The first free cell in the order the grid draws them, so "the first
        // free cell" means the same thing to the player as it does here.
        bool FirstFreeBagSlot(Player* player, std::uint8_t& bag, std::uint8_t& slot)
        {
            for (std::uint8_t position = INVENTORY_SLOT_ITEM_START; position < INVENTORY_SLOT_ITEM_END; ++position)
                if (!player->GetItemByPos(INVENTORY_SLOT_BAG_0, position))
                {
                    bag = INVENTORY_SLOT_BAG_0;
                    slot = position;
                    return true;
                }
            for (std::uint8_t container = INVENTORY_SLOT_BAG_START; container < INVENTORY_SLOT_BAG_END; ++container)
            {
                Bag* pack = player->GetBagByPos(container);
                if (!pack)
                    continue;
                for (std::uint32_t position = 0; position < pack->GetBagSize(); ++position)
                    if (!player->GetItemByPos(container, std::uint8_t(position)))
                    {
                        bag = container;
                        slot = std::uint8_t(position);
                        return true;
                    }
            }
            return false;
        }

        // 12-ui §3: weapons and the potion may change in combat as stock allows; other gear
        // stays the core's rule. This
        // command does not second-guess a fight: SwapItem answers with the core's own refusal
        // for armor (EQUIP_ERR_NOT_IN_COMBAT, PlayerStorage.cpp CanEquipItem), and the potion
        // slot is ours alone, with no core rule to ask. What stays refused here is a dead
        // character and one whose economy aborted. The potion's cooldown is per spell id and
        // is resent on every swap (Classes::WriteActionBar), so a swap never skips or resets it.
        // Identify keeps its own combat refusal (DC::Identify::Refusal).
        Player* Acting(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            Need(player != nullptr, "No character.");
            Need(!player->GetSession()->EconomyAborted(), "Relog before changing gear.");
            Need(player->IsAlive(), "You cannot change gear while dead.");
            return player;
        }

        // ----------------------------------------------------------- the intents

        // The potion in the slot and the power roll it keeps; no roll: a potion whose power does not roll,
        // or one that never rolled.
        struct SlotPotion
        {
            std::uint32_t entry = 0;
            std::optional<double> roll;
        };

        SlotPotion EquippedPotion(Player* player)
        {
            SlotPotion potion;
            auto row = CharacterDatabase.Query(
                "SELECT item_entry, power_roll FROM dc_character_potion WHERE guid={}", player->GetGUID().GetCounter());
            if (row && !(*row)[0].IsNull())
            {
                potion.entry = (*row)[0].Get<uint32>();
                if (!(*row)[1].IsNull())
                    potion.roll = (*row)[1].Get<double>();
            }
            return potion;
        }

        std::uint32_t EquippedPotionEntry(Player* player)
        {
            return EquippedPotion(player).entry;
        }

        // A Bottomless potion's power roll is its dc_item_affix row of kind 'power' (contract legendary-powers.md "Per-item
        // rolls"). A potion owns one power, so it has at most one such row.
        std::optional<double> PowerRoll(Item* potion)
        {
            if (auto instance = Items::Get(potion->GetGUID().GetCounter()))
                for (Items::Affix const& affix : instance->affixes)
                    if (affix.kind == "power")
                        return affix.value;
            return std::nullopt;
        }

        // The returned potion gets its roll back as the rows StageRoll writes: an instance (never Ancient) and the power row,
        // its key and range from the table through the roller's own rule, the value the slot kept.
        void WritePowerRoll(Item* potion, double roll, CharacterDatabaseTransaction const& transaction)
        {
            auto base = WorldDatabase.Query("SELECT d3_id, rarity FROM dc_base_item WHERE entry={}", potion->GetEntry());
            if (!base)
                return;
            std::string const d3Id = (*base)[0].Get<std::string>();
            std::string rarity = (*base)[1].Get<std::string>();
            CharacterDatabase.EscapeString(rarity);
            std::uint64_t const guid = potion->GetGUID().GetCounter();
            transaction->Append("INSERT INTO dc_item_instance (item_guid, base_item, quality_tier, rarity) "
                                "VALUES ({}, {}, 'normal', '{}')", guid, potion->GetEntry(), rarity);
            unsigned seq = 0;
            for (auto const& power : Combat::ItemPower::RollPowers(Combat::ItemPowers::ItemRows(d3Id), d3Id, false,
                                                                     [roll](double, double) { return roll; }))
            {
                std::string key = power.key;
                CharacterDatabase.EscapeString(key);
                transaction->Append("INSERT INTO dc_item_affix (item_guid, seq, affix_id, value, range_min, range_max, kind, "
                                    "rerolled) VALUES ({}, {}, '{}', {}, {}, {}, 'power', 0)",
                                    guid, seq++, key, power.value, power.min, power.max);
            }
        }

        bool IsPotionItem(std::uint32_t entry)
        {
            return bool(WorldDatabase.Query("SELECT entry FROM dc_base_item WHERE entry={} AND slot='potion'", entry));
        }

        // source == nullptr unequips. Otherwise one item becomes the recorded
        // potion, returning the previous choice to the bag (including a full-bag
        // swap when consuming the source frees its cell). No legendary data is
        // shipped yet; eligibility comes only from the base row's potion slot.
        void ChangePotion(Player* player, Item* source)
        {
            // Greater Rift rule 6: the potion slot is gear, and no core rule guards it. Not even
            // the combat exception above lets it change before the Guardian is dead.
            Need(!DC::Rifts::GreaterRiftGearLocked(player),
                 "You cannot change your gear in a Greater Rift until its Guardian is dead.");
            SlotPotion const slotted = EquippedPotion(player);
            std::uint32_t const previous = slotted.entry;
            std::uint32_t const next = source ? source->GetEntry() : 0;
            if (source)
            {
                Need(IsPotionItem(next), "That item does not belong in the potion slot.");
                Need(source->GetOwnerGUID() == player->GetGUID() && !source->IsInTrade(),
                     "That item is no longer yours or is being traded.");
            }
            else
                Need(previous != 0, "The potion slot is empty.");

            std::unique_ptr<Item> returned;
            ItemPosCountVec destination;
            if (previous)
            {
                returned.reset(Item::CreateItem(previous, 1, player));
                Need(bool(returned), "The equipped potion's item template is unavailable.");
                std::uint8_t bag = 0, slot = 0;
                bool const swap = source && source->GetCount() == 1;
                if (swap)
                {
                    bag = source->GetBagSlot();
                    slot = source->GetSlot();
                }
                else
                    Need(FirstFreeBagSlot(player, bag, slot), "Your bags are full.");
                Need(player->CanStoreItem(bag, slot, destination, returned.get(), swap) == EQUIP_ERR_OK,
                     "The potion does not fit in that bag cell.");
            }

            PlayerEconomy::Scope operation(player);
            auto transaction = PlayerEconomy::BeginTransaction();
            // Match the account economy's failed-mutation behavior even when
            // its ledger is disabled: discard unsaved in-memory inventory on
            // disconnect, never save a failed potion move over committed truth.
            struct MutationGuard
            {
                Player* player;
                bool saved = false;
                ~MutationGuard()
                {
                    if (!saved)
                    {
                        PlayerEconomy::Fail();
                        player->GetSession()->AbortEconomy();
                    }
                }
            } mutation{player};
            // Read before the item and its rows are destroyed: the slot keeps the roll.
            std::optional<double> const nextRoll = source ? PowerRoll(source) : std::nullopt;
            if (source)
            {
                if (source->GetCount() == 1)
                    Items::DestroyWithRows(player, source, transaction);
                else
                {
                    source->SetCount(source->GetCount() - 1);
                    source->SetState(ITEM_CHANGED, player);
                    source->SendUpdateToPlayer(player);
                }
            }
            if (returned)
            {
                Need(player->StoreItem(destination, returned.get(), true) != nullptr,
                     "Could not return the equipped potion to the bag.");
                Item* stored = returned.release(); // StoreItem owns the recreated item.
                if (slotted.roll)
                    WritePowerRoll(stored, *slotted.roll, transaction);
            }
            if (next && nextRoll)
                transaction->Append("INSERT INTO dc_character_potion(guid,item_entry,power_roll) VALUES({},{},{}) "
                                    "ON DUPLICATE KEY UPDATE item_entry=VALUES(item_entry), power_roll=VALUES(power_roll)",
                                    player->GetGUID().GetCounter(), next, *nextRoll);
            else if (next)
                transaction->Append("INSERT INTO dc_character_potion(guid,item_entry,power_roll) VALUES({},{},NULL) "
                                    "ON DUPLICATE KEY UPDATE item_entry=VALUES(item_entry), power_roll=NULL",
                                    player->GetGUID().GetCounter(), next);
            else
                transaction->Append("INSERT INTO dc_character_potion(guid,item_entry,power_roll) VALUES({},NULL,NULL) "
                                    "ON DUPLICATE KEY UPDATE item_entry=NULL, power_roll=NULL", player->GetGUID().GetCounter());
            player->SaveInventoryAndGoldToDB(transaction);
            Need(AccountEconomy::Commit(player, transaction), "The potion move could not be saved; relog.");
            mutation.saved = true;
            Classes::WriteActionBar(player);
        }

        // Right-click a grid item. FindEquipSlot picks the destination exactly as
        // the core's own CMSG_AUTOEQUIP_ITEM does (ItemHandler.cpp:169), and
        // SwapItem owns every rule after that - level, class, unique, two-handed,
        // off-hand, and putting whatever was worn back in the bag. It answers the
        // client itself when it refuses.
        void Equip(Player* player, std::int32_t index)
        {
            std::uint8_t bag = 0, slot = 0;
            DecodeBag(index, bag, slot);
            Item* item = player->GetItemByPos(bag, slot);
            Need(item != nullptr, "There is no item in that slot.");
            if (IsPotionItem(item->GetEntry()))
            {
                ChangePotion(player, item);
                return;
            }
            ItemTemplate const* proto = item->GetTemplate();
            Need(proto != nullptr, "That item cannot be equipped.");
            Need(!item->IsBag() || !item->IsNotEmptyBag(), "Empty that bag first.");
            std::uint8_t const destination = player->FindEquipSlot(proto, NULL_SLOT, !item->IsBag());
            Need(destination != NULL_SLOT, "That item cannot be equipped.");
            std::uint16_t const target = std::uint16_t(INVENTORY_SLOT_BAG_0 << 8) | destination;
            Need(target != item->GetPos(), "That item is already worn.");
            player->SwapItem(item->GetPos(), target);
        }

        // Right-click a worn item: it goes to the first free cell of the grid.
        // The slot is an equipment slot, never a bag
        // index, so it cannot be used to rearrange bags.
        void Unequip(Player* player, std::int32_t slot)
        {
            if (slot == Potion::InventorySlot)
            {
                ChangePotion(player, nullptr);
                return;
            }
            Need(slot >= 0 && slot < EQUIPMENT_SLOT_END, "That is not an equipment slot.");
            std::uint16_t const source = std::uint16_t(INVENTORY_SLOT_BAG_0 << 8) | std::uint8_t(slot);
            Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, std::uint8_t(slot));
            Need(item != nullptr, "Nothing is worn in that slot.");
            std::uint8_t bag = 0, cell = 0;
            Need(FirstFreeBagSlot(player, bag, cell), "Your bags are full.");
            player->SwapItem(source, std::uint16_t(bag << 8) | cell);
        }

        // ------------------------------------------------------------- the sheet

        // Trimmed decimals, the same shape dc_paragon.cpp sends its numbers in:
        // enough precision for any row the addon formats, no trailing zeroes and
        // no locale separators, so the client parses one token per value.
        std::string Number(double value)
        {
            std::ostringstream out;
            out.imbue(std::locale::classic());
            out << std::fixed << std::setprecision(4) << value;
            std::string text = out.str();
            while (text.back() == '0')
                text.pop_back();
            if (text.back() == '.')
                text.pop_back();
            return text;
        }

        void Wire(Player* player, std::string const& message)
        {
            WorldPacket packet;
            ChatHandler::BuildChatPacket(packet, CHAT_MSG_WHISPER, LANG_ADDON, player, player, "DCSHEET\t" + message);
            player->GetSession()->SendPacket(&packet);
        }

        // key=value pairs, flushed well inside one chat packet. The addon keys
        // its rows off these names, so the order they arrive in does not matter;
        // B clears the buffer and E is what makes it visible.
        class Block
        {
        public:
            explicit Block(Player* player)
                : owner(player)
            {
            }

            void Add(char const* key, double value)
            {
                std::string const pair = std::string(key) + "=" + Number(value);
                if (!line.empty() && line.size() + pair.size() > 160)
                    Flush();
                if (!line.empty())
                    line += ";";
                line += pair;
            }

            void Flush()
            {
                if (line.empty())
                    return;
                Wire(owner, "V|" + line);
                line.clear();
            }

        private:
            Player* owner;
            std::string line;
        };

        char const* ElementKeys[] = {"ele0", "ele1", "ele2", "ele3", "ele4", "ele5", "ele6"};
        char const* ResistKeys[] = {"res0", "res1", "res2", "res3", "res4", "res5", "res6"};
        char const* ReductionKeys[] = {"def0", "def1", "def2", "def3", "def4", "def5", "def6"};
    } // namespace

    std::uint32_t ActivePotionSpell(Player* player)
    {
        return Potion::SpellFor(EquippedPotionEntry(player));
    }

    std::optional<double> ActivePotionRoll(Player* player)
    {
        return EquippedPotion(player).roll;
    }

    void PushSheet(Player* player)
    {
        if (!player || !player->GetSession())
            return;
        auto found = Stats::Get(player->GetGUID().GetRawValue());
        if (!found)
        {
            // No D3 sheet (not a Barbarian, or stats failed to load). Say so
            // rather than drawing a screen full of zeroes.
            Wire(player, "N");
            return;
        }
        StatSheet const& sheet = *found;
        Stats::Summary const summary = Stats::SheetSummary(player);

        Wire(player, "B|" + std::to_string(sheet.level));
        Block block(player);
        // stats.csv rows 1-22, in its own order, plus the derived values D3's
        // own Details panel shows beside them (Attacks per Second, Maximum Life,
        // Maximum Fury). Nothing here is computed: every number is read off the
        // sheet Calculate() produced.
        block.Add("str", sheet[Stat::Strength]);
        block.Add("dex", sheet[Stat::Dexterity]);
        block.Add("int", sheet[Stat::Intelligence]);
        block.Add("vit", sheet[Stat::Vitality]);
        block.Add("chc", sheet[Stat::CritChance]);
        block.Add("chd", sheet[Stat::CritDamage]);
        block.Add("ias", sheet[Stat::AttackSpeed]);
        block.Add("cdr", sheet[Stat::CooldownReduction]);
        block.Add("rcr", sheet[Stat::ResourceCostReduction]);
        block.Add("ad", sheet[Stat::AreaDamage]);
        block.Add("resall", sheet[Stat::AllResistance]);
        block.Add("armor", sheet[Stat::Armor]);
        // Block (docs/research/block.md). Two player-facing
        // numbers: the chance, already clamped and totalled by Calculate, and
        // the Amount, which is a MIN-MAX range a blocked hit rolls inside and
        // therefore travels as two keys. BaseBlockChance is not sent: it is an
        // input to the chance, not a row D3 shows.
        block.Add("block", sheet[Stat::BlockChance]);
        block.Add("blockmin", sheet[Stat::BlockAmountMin]);
        block.Add("blockmax", sheet[Stat::BlockAmountMax]);
        block.Add("loh", sheet[Stat::LifePerHit]);
        block.Add("lpk", sheet[Stat::LifePerKill]);
        block.Add("regen", sheet[Stat::LifeRegen]);
        block.Add("lifepct", sheet[Stat::LifePercent]);
        block.Add("ms", sheet[Stat::MovementSpeed]);
        block.Add("thorns", sheet[Stat::Thorns]);
        block.Add("mf", sheet[Stat::MagicFind]);
        block.Add("gf", sheet[Stat::GoldFind]);
        block.Add("xp", sheet[Stat::XPBonus]);
        for (unsigned element = 0; element < ElementCount; ++element)
        {
            block.Add(ElementKeys[element], sheet.elementalDamage[element]);
            block.Add(ResistKeys[element], sheet.resistance[element]);
            // "Reduces damage from <element> attacks by X%" (Stat::ElementReduction), 0 when nothing worn has it.
            block.Add(ReductionKeys[element], sheet.elementReduction[element]);
        }
        block.Add("aps", sheet.attacksPerSecond);
        block.Add("life", sheet.maxLife);
        block.Add("fury", sheet[Stat::MaxFury]);
        block.Add("dmg", summary.damage);
        block.Add("tough", summary.toughness);
        block.Add("recov", summary.recovery);
        block.Flush();
        Wire(player, "E");
    }

    namespace
    {
        class Commands final : public CommandScript
        {
        public:
            Commands()
                : CommandScript("dc_inventory_commands")
            {
            }

            ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // All three are what the addon's AIO bridge runs through
                // Player:RunCommand, the same way the stash and the artisans do.
                static ChatCommandTable inventory = {{"equip", HandleEquip, SEC_PLAYER, Console::No},
                                                     {"unequip", HandleUnequip, SEC_PLAYER, Console::No},
                                                     {"sheet", HandleSheet, SEC_PLAYER, Console::No}};
                // The pre-patch fallback for the AIO
                // right-click. The native item Use is the decided route and
                // reaches the same Identify::IdentifyOne, so the two cannot
                // produce different rolls.
                static ChatCommandTable identify = {{"slot", HandleIdentify, SEC_PLAYER, Console::No}};
                static ChatCommandTable dc = {{"inventory", inventory}, {"identify", identify}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            static bool HandleIdentify(ChatHandler* handler, int32 index)
            {
                try
                {
                    Player* player = Acting(handler);
                    std::uint8_t bag = 0, slot = 0;
                    DecodeBag(index, bag, slot);
                    Item* item = player->GetItemByPos(bag, slot);
                    Need(item != nullptr, "There is no item in that slot.");
                    Need(DC::Items::IsUnidentifiedTemplate(item->GetEntry()), "That item is already identified.");
                    // G7: refuse before the cast starts, then cast the same spell a
                    // right-click casts so the usual cast time applies; the roll
                    // happens when that cast completes (dc_identify.cpp).
                    if (char const* refused = DC::Identify::Refusal(player->IsAlive(), player->IsInCombat(), item->IsInTrade()))
                    {
                        handler->SendErrorMessage(refused);
                        return false;
                    }
                    if (player->CastSpell(player, DC::Items::IdentifyItemSpell(), TRIGGERED_NONE, item) != SPELL_CAST_OK)
                    {
                        handler->SendErrorMessage("That item cannot be identified right now.");
                        return false;
                    }
                    return true;
                }
                catch (std::exception const& error)
                {
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }

            static bool HandleEquip(ChatHandler* handler, int32 index)
            {
                try
                {
                    Player* player = Acting(handler);
                    Equip(player, index);
                    return true;
                }
                catch (std::exception const& error)
                {
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }

            static bool HandleUnequip(ChatHandler* handler, int32 slot)
            {
                try
                {
                    Player* player = Acting(handler);
                    Unequip(player, slot);
                    return true;
                }
                catch (std::exception const& error)
                {
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }

            // Read-only, so unlike the two above it is allowed in combat.
            static bool HandleSheet(ChatHandler* handler)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                PushSheet(player);
                return true;
            }
        };
    } // namespace

    namespace
    {
        // Items are account bound; the trade window is gold only.
        // The hook runs for every slot the client can fill, so a modified client
        // gets the same refusal. Money is not an item and never reaches it.
        class TradeBlock final : public PlayerScript
        {
        public:
            TradeBlock() : PlayerScript("dc_trade_block", {PLAYERHOOK_CAN_SET_TRADE_ITEM}) { }

            bool OnPlayerCanSetTradeItem(Player* player, Item*, uint8) override
            {
                if (player && player->GetSession())
                    ChatHandler(player->GetSession()).SendSysMessage(DC::Trade::ItemRefusal());
                return false;
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Commands();
        new TradeBlock();
    }
} // namespace DC::Inventory
