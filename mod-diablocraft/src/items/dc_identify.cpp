/*
 * World of DiabloCraft - identification.
 *
 * The shell holds no roll. Identification is where the roll happens - but for
 * the class the drop rolled for, stored on the shell's row, never for whoever
 * identifies it (dc_roll_class.h rule 4).
 */

#include "dc_identify.h"
#include "dc_identify_rule.h"

#include "dc_items.h"
#include "dc_roll_class.h"
#include "../common/dc_account_economy.h"

#include "Chat.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "WorldSession.h"

#include <mutex>
#include <string>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (910016, 81203, 81204, 910002): Tome entry, identify spell ids, stash NPC entry; Identifiers.

namespace DC::Identify
{
    namespace
    {
        // The tunables, read once from the same table every other loot number comes
        // from. Zero means "not set", and the module says so rather than guessing a
        // cast length - the town portal's own runtime override is the pattern.
        std::mutex tuningMutex;
        double itemCastSeconds = 0.0, tomeCastSeconds = 0.0;
        bool tuningLoaded = false;

        void LoadTuning()
        {
            std::lock_guard<std::mutex> lock(tuningMutex);
            if (tuningLoaded)
                return;
            tuningLoaded = true;
            if (QueryResult row = WorldDatabase.Query("SELECT identify_item_cast_seconds, identify_tome_cast_seconds "
                                                      "FROM dc_loot_tuning WHERE source='identify'"))
            {
                itemCastSeconds = (*row)[0].Get<double>();
                tomeCastSeconds = (*row)[1].Get<double>();
            }
            else
                LOG_ERROR("server", "[DC identify] dc_loot_tuning has no 'identify' row; "
                                    "cast times fall back to the spell data. Apply loot_tuning_0002_csv.sql.");
        }

        // Every shell the player is carrying, bags included. Equipped is impossible -
        // the equip veto sees to that - and the bank is not reachable from here.
        std::vector<Item*> CarriedShells(Player* player)
        {
            std::vector<Item*> found;
            auto consider = [&](Item* item)
            {
                if (item && DC::Items::IsUnidentifiedTemplate(item->GetEntry()) && !item->IsInTrade())
                    found.push_back(item);
            };
            for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
                consider(player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));
            for (uint8 bag = INVENTORY_SLOT_BAG_START; bag < INVENTORY_SLOT_BAG_END; ++bag)
                if (Bag* container = player->GetBagByPos(bag))
                    for (uint32 slot = 0; slot < container->GetBagSize(); ++slot)
                        consider(player->GetItemByPos(bag, static_cast<uint8>(slot)));
            return found;
        }
    } // namespace

    bool IdentifyOne(Player* player, Item* shell, std::string& error)
    {
        if (!player || !shell)
        {
            error = "That item is no longer yours.";
            return false;
        }
        if (!DC::Items::IsUnidentifiedTemplate(shell->GetEntry()))
        {
            error = "That item is already identified.";
            return false;
        }
        // G7: the same rule whichever door the roll came through.
        if (char const* refused = Refusal(player->IsAlive(), player->IsInCombat(), shell->IsInTrade()))
        {
            error = refused;
            return false;
        }
        // The COUNTER, not the raw GUID: dc_item_instance is keyed that way and
        // it is the only form Lua can produce, so the grid, the tooltip and
        // salvage all speak it.
        std::uint64_t const key = shell->GetGUID().GetCounter();
        auto row = DC::Items::GetUnidentified(key);
        if (!row)
        {
            // The sweep logs these and never rolls them; neither does this. The
            // drop context is gone and inventing one invents an item.
            error = "That item has lost its drop record and cannot be identified. Report it.";
            LOG_ERROR("server", "[DC identify] {} tried to identify shell {} with no dc_item_unidentified row",
                      player->GetName(), key);
            return false;
        }

        // Rule 4: the class stored at the drop. A row from before roll classes
        // were stored has none and rolls for the looter it dropped for.
        std::string ownerClass;
        if (row->rollClass.empty())
            if (QueryResult owner = CharacterDatabase.Query("SELECT class FROM characters WHERE guid={}", row->ownerGuid))
                ownerClass = DC::Items::ClassKeyOf((*owner)[0].Get<uint8>());
        std::string const rollClass = DC::RollClass::ShellClass(row->rollClass, ownerClass);
        if (rollClass.empty())
        {
            error = "That item has lost its drop class and cannot be identified. Report it.";
            LOG_ERROR("server", "[DC identify] {} tried to identify shell {}: no roll_class and owner {} has no "
                                "playable class", player->GetName(), key, row->ownerGuid);
            return false;
        }

        // The slot the shell is in: the roll lands exactly where it was, which
        // is also why identifying never needs a free bag slot.
        uint8 const bag = shell->GetBagSlot(), slot = shell->GetSlot();

        // The Scope is what makes AccountEconomy::Commit willing to commit at
        // all; without it every identify failed after the shell was already
        // gone. Everything destructive happens after the commit
        // has succeeded, so a refusal leaves the shell exactly where it was.
        PlayerEconomy::Scope operation(player);
        auto transaction = PlayerEconomy::BeginTransaction();
        // DestroyItem and StoreNewItem change the in-memory bags immediately,
        // while the transaction only carries the rows. Without this guard a
        // failure after the destroy would leave the player looking at an empty
        // cell whose shell is still in the database until they relog.
        // Same shape dc_inventory.cpp
        // uses for the potion swap.
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

        // The shell's slot is freed first, inside this transaction, so the roll
        // has somewhere to go even when every other cell is full.
        DC::Items::DestroyShell(player, shell, transaction);

        // The roll happens HERE, into THIS player's bag, for the shell's own
        // class: a traded shell stays the class it dropped as (rule 4).
        auto staged = DC::Items::StageRoll(player, row->baseItem, row->itemLevel, row->rarity, transaction, rollClass,
                                          row->qualityTier);
        if (!staged || !staged->GetItem())
        {
            error = "That item could not be identified. Nothing was changed.";
            return false;   // the guard discards the unsaved bag change
        }
        player->SaveInventoryAndGoldToDB(transaction);
        if (!DC::AccountEconomy::Commit(player, transaction))
        {
            error = "The identification could not be saved. Nothing was changed.";
            return false;
        }
        mutation.saved = true;
        Item* published = staged->Publish();
        if (!published)
        {
            error = "The identification could not be completed.";
            return false;
        }
        // Back into the shell's own cell. The destroy above freed it, so this is
        // a move into a hole the player is already looking at.
        if (published->GetBagSlot() != bag || published->GetSlot() != slot)
        {
            uint16 const source = published->GetPos();
            uint16 const destination = static_cast<uint16>((bag << 8) | slot);
            if (source != destination)
                player->SwapItem(source, destination);
        }
        player->SendNewItem(published, 1, false, false, false, true);
        LOG_INFO("server", "[DC identify] {} identified {} ({} {} item level {}, source {}, tier {}, class {})",
                 player->GetName(), row->baseItem, row->qualityTier, row->rarity, row->itemLevel, row->dropSource, row->tier,
                 rollClass);
        return true;
    }

    unsigned IdentifyAll(Player* player)
    {
        if (!player)
            return 0;
        unsigned identified = 0;
        // The list is taken first: identifying mutates the bags, and iterating them
        // while they change would skip items or revisit slots.
        for (Item* shell : CarriedShells(player))
        {
            std::string error;
            if (IdentifyOne(player, shell, error))
                ++identified;
            else if (player->GetSession())
                ChatHandler(player->GetSession()).SendSysMessage(error.c_str());
        }
        return identified;
    }

    namespace
    {
        // generate_hub_placements.py --tome. Type 22 with spellId 0, so GameObject::Use
// reaches this hook before its type switch and the PLAYER casts - which is what
// gives a cast bar that movement and damage interrupt. The object casts nothing.
constexpr std::uint32_t TOME_ENTRY = 910016;

class IdentifyTome final : public AllGameObjectScript
{
public:
    IdentifyTome() : AllGameObjectScript("dc_identify_tome") { }
    bool CanGameObjectGossipHello(Player* player, GameObject* go) override
    {
        if (!go || go->GetEntry() != TOME_ENTRY || !player || !player->GetSession())
            return false;
        ChatHandler handler(player->GetSession());
        if (player->IsInCombat() || !player->IsAlive())
        {
            handler.SendSysMessage("Use the tome out of combat, and alive.");
            return true;
        }
        if (CarriedShells(player).empty())
        {
            handler.SendSysMessage("You have nothing to identify.");
            return true;
        }
        // The player casts, not the object: the interrupt rules, the cast bar
        // and the completion hook are then all the ordinary ones.
        player->CastSpell(player, DC::Items::IdentifyTomeSpell(), false);
        return true;
    }
};

// The cast, and only the cast. The identification itself runs off the
        // successful-cast hook exactly as the town portal's teleport does, so movement
        // and damage interrupt it through the core's own rules rather than ours.
        class IdentifySpellData final : public GlobalScript
        {
        public:
            IdentifySpellData()
                : GlobalScript("dc_identify_spell_data", {GLOBALHOOK_ON_LOAD_SPELL_CUSTOM_ATTR})
            {
            }
            void OnLoadSpellCustomAttr(SpellInfo* info) override
            {
                std::uint32_t const item = DC::Items::IdentifyItemSpell(), tome = DC::Items::IdentifyTomeSpell();
                if (info->Id != item && info->Id != tome)
                    return;
                LoadTuning();
                info->InterruptFlags =
                    SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT | SPELL_INTERRUPT_FLAG_ABORT_ON_DMG;
                double const seconds = info->Id == item ? itemCastSeconds : tomeCastSeconds;
                if (seconds <= 0.0)
                    return; // no tunable: keep the generated cast time from the DBC
                auto const milliseconds = static_cast<std::uint32_t>(seconds * 1000.0);
                for (std::uint32_t id = 0; id < sSpellCastTimesStore.GetNumRows(); ++id)
                    if (auto* entry = sSpellCastTimesStore.LookupEntry(id))
                        if (static_cast<std::uint32_t>(entry->CastTime) == milliseconds)
                        {
                            info->CastTimeEntry = entry;
                            break;
                        }
            }
        };

        class IdentifyCast final : public AllSpellScript
        {
        public:
            IdentifyCast()
                : AllSpellScript("dc_identify_cast", {ALLSPELLHOOK_ON_SPELL_CHECK_CAST, ALLSPELLHOOK_ON_CAST})
            {
            }

            void OnSpellCheckCast(Spell* spell, bool, SpellCastResult& result) override
            {
                if (!spell)
                    return;
                std::uint32_t const id = spell->GetSpellInfo()->Id;
                if (id != DC::Items::IdentifyItemSpell() && id != DC::Items::IdentifyTomeSpell())
                    return;
                Player* player = spell->GetCaster() ? spell->GetCaster()->ToPlayer() : nullptr;
                if (!player)
                {
                    result = SPELL_FAILED_ERROR;
                    return;
                }
                // Refuse a cast that has nothing to do before it starts, rather than
                // letting the player watch a bar and then be told.
                if (id == DC::Items::IdentifyTomeSpell() && CarriedShells(player).empty())
                    result = SPELL_FAILED_NOTHING_TO_DISPEL;
            }

            void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override
            {
                if (!spell || !info)
                    return;
                Player* player = caster ? caster->ToPlayer() : nullptr;
                if (!player || !player->GetSession())
                    return;
                ChatHandler handler(player->GetSession());
                if (info->Id == DC::Items::IdentifyItemSpell())
                {
                    // The item that was right-clicked is the spell's cast item; there
                    // is no other way to know which shell the player meant.
                    std::string error;
                    if (!IdentifyOne(player, spell->m_CastItem, error))
                        handler.SendSysMessage(error.c_str());
                    return;
                }
                if (info->Id != DC::Items::IdentifyTomeSpell())
                    return;
                unsigned const count = IdentifyAll(player);
                if (count)
                    handler.PSendSysMessage("Identified {} item(s).", count);
                else
                    handler.SendSysMessage("You have nothing to identify.");
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new IdentifySpellData();
        new IdentifyCast();
        // The tome's own script: without it, clicking the tome does nothing at all.
        new IdentifyTome();
    }
} // namespace DC::Identify
