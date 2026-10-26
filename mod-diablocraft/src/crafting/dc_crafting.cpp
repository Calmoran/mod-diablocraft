// Constant (102000): First GM material item ID; Content range; excludes keystones. Constant (102004): Last GM
// material item ID; Content range.
// Crafting: the artisan commands, the window bridge's Game, Kanai's Cube click and script registration.
#include "dc_crafting.h"
#include "dc_crafting_internal.h"
#include "dc_crafting_window.h"
#include "dc_cube_window.h"
#include "../common/dc_bridge.h"
#include "../common/dc_economy.h"
#include "../common/dc_account_economy.h"
#include "PlayerEconomy.h"
#include "../items/dc_items.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "WorldSession.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <optional>
#include <stdexcept>
#include <vector>

namespace DC::Crafting
{
    using namespace Detail;
    namespace
    {
        // The real Game the window handlers (dc_crafting_window.h) drive: each method is the same
        // checked function the command calls, so the rules, the gold (Economy::Charge) and the
        // ownership checks are the ones the command has.
        class WindowGame final
        {
        public:
            explicit WindowGame(Player* player)
                : player_(player)
            {
            }
            static uint32 Entry(Window::Npc npc)
            {
                return npc == Window::Npc::Mystic ? Mystic : npc == Window::Npc::Jeweler ? Jeweler : Blacksmith;
            }
            void Gate(Window::Npc npc)
            {
                if (npc == Window::Npc::Nobody)
                    Reachable(player_);
                else if (npc == Window::Npc::Cube)
                    CubeInReach(player_);
                else
                    Artisan(player_, Entry(npc));
            }
            void Salvage(uint32 guid)
            {
                DC::Crafting::Salvage(player_, guid, 0);
            }
            void Bulk(uint32 rarity)
            {
                DC::Crafting::Salvage(player_, 0, rarity);
            }
            void Craft(uint32 id, uint32 count)
            {
                DC::Crafting::Craft(player_, id, count);
            }
            void Forge(uint32 id, uint32 count)
            {
                DC::Crafting::Craft(player_, id, count, true);
            }
            std::pair<std::string, bool> RepairPrice(uint32 scope, uint32 guid)
            {
                auto* npc = Artisan(player_, Blacksmith);
                uint64 cost = RepairTotal(player_, npc, RepairSelection(player_, scope, guid));
                return {std::to_string(cost), Economy::CanAfford(player_, cost)};
            }
            void RepairItems(uint32 scope, uint32 guid)
            {
                RepairSelection(player_, scope, guid); // Validate both fields before payment.
                DC::Crafting::Repair(player_, Artisan(player_, Blacksmith), scope == 0 ? Owned(player_, guid) : nullptr, scope == 1);
            }
            Window::EnchantState Place(uint32 guid)
            {
                return MysticState(player_, guid);
            }
            std::vector<Window::EnchantAffix> Preview(uint32 guid, uint32 seq)
            {
                return MysticPreview(player_, guid, seq);
            }
            void Roll(uint32 guid, uint32 seq)
            {
                DC::Crafting::Roll(player_, guid, seq);
            }
            void Pick(uint32 guid, uint32 choice)
            {
                DC::Crafting::Pick(player_, guid, choice);
            }
            void Repair(Window::Npc npc)
            {
                DC::Crafting::Repair(player_, Artisan(player_, Entry(npc)));
            }
            void Transmog()
            {
                auto* npc = Artisan(player_, Mystic);
                auto* script = ScriptRegistry<CreatureScript>::GetScriptById(npc->GetScriptId());
                Need(script, "Transmogrification is unavailable.");
                ClearGossipMenuFor(player_);
                Need(script->OnGossipHello(player_, npc), "Transmogrification could not open.");
            }
            void Socket(uint32 guid, uint32 seq, uint32 gem)
            {
                DC::Crafting::Socket(player_, guid, seq, gem);
            }
            void Combine(uint32 id, uint32 count)
            {
                DC::Crafting::Combine(player_, id, count);
            }
            void Jewelry(uint32 id, uint32 count)
            {
                DC::Crafting::Craft(player_, id, count, true, true);
            }
            Cube::Recipes Recipes()
            {
                return CubeRecipes();
            }
            void Transmute(std::string const& id, uint32 guid, std::vector<Cube::Cell> const& gems)
            {
                DC::Crafting::Transmute(player_, id, guid, gems);
            }
            std::string GemClass(uint32 guid)
            {
                return CubeGemClass(player_, guid);
            }
            std::vector<Window::CubeSlot> Slots()
            {
                return CubeSlots(player_);
            }
            std::vector<Window::CubePower> Powers(uint32 slot)
            {
                return CubePowers(player_, slot);
            }
            std::optional<Window::CubePowerText> PowerText(uint32 entry)
            {
                return CubePowerText(entry);
            }
            void Choose(uint32 slot, uint32 entry)
            {
                ChooseCubePower(player_, slot, entry);
            }
            // True when the socket row holds a gem, or when that cannot be told (not ours, no such row):
            // the strict gate then applies and Socket() refuses it by its own words.
            bool SocketFilled(uint32 guid, uint32 seq)
            {
                auto instance = Items::Get(guid);
                if (!instance)
                    return true;
                bool socket = false;
                for (auto const& a : instance->affixes)
                {
                    if (a.kind == "gem" && a.parentSeq == int(seq))
                        return true;
                    socket = socket || (a.seq == seq && a.kind == "socket");
                }
                return !socket;
            }
            Window::Bags Carried()
            {
                Window::Bags bags;
                for (auto* item : Inventory(player_))
                    bags[item->GetGUID().GetCounter()] = {item->GetEntry(), item->GetCount(), item->GetBagSlot(),
                                                          item->GetSlot()};
                return bags;
            }
            Window::Funds Balance()
            {
                Window::Funds funds;
                AccountEconomy::Snapshot snapshot;
                if (!AccountEconomy::ReadSnapshot(player_, snapshot))
                    return funds;
                funds.valid = true;
                funds.gold = snapshot.gold;
                funds.materials = snapshot.materials;
                return funds;
            }
            std::optional<Window::Rolled> Detail(uint64 guid, bool withOffers)
            {
                auto instance = Items::Get(guid);
                if (!instance)
                    return std::nullopt;
                Window::Rolled rolled;
                rolled.rarity = instance->rarity;
                rolled.locked = instance->enchantLocked;
                rolled.attempts = instance->enchantAttempts;
                for (auto const& a : instance->affixes)
                    if (a.kind != "power" && a.kind != "passive" && a.kind != "augment") // a power's roll, a granted passive and the Cube's augment are no property of the window (legendary-powers.md, cube-messages.md)
                        rolled.affixes.push_back({a.seq, a.affixId, a.kind, a.value, a.rerolled, a.parentSeq, a.gemEntry});
                if (withOffers)
                    if (auto rows = CharacterDatabase.Query(
                            "SELECT choice_id,affix_id,value FROM dc_enchant_offer WHERE item_guid={} ORDER BY choice_id",
                            guid))
                        do
                        {
                            auto* f = rows->Fetch();
                            rolled.offers.push_back({f[0].Get<uint32>(), f[1].Get<std::string>(), f[2].Get<double>()});
                        } while (rows->NextRow());
                return rolled;
            }
            void Failed()
            {
                if (auto* op = PlayerEconomy::Current(); op && (op->Dirty() || op->transaction->GetSize()))
                    PlayerEconomy::Fail();
            }

        private:
            Player* player_;
        };
        // The click's push: the records a `list` request gets (dc_cube_window.h SendCube), with no request to answer.
        struct CubePush
        {
            Player* player;
            bool Record(std::vector<std::string> const& fields) const
            {
                return Bridge::Push(player, "DCCUBE", fields);
            }
        };
        // A click on Kanai's Cube opens its window (docs/contracts/cube-messages.md). The template is type 22 with no spell, so
        // nothing else answers the click (world_0006_hub_object_use.sql).
        class KanaisCubeObject final : public AllGameObjectScript
        {
        public:
            KanaisCubeObject()
                : AllGameObjectScript("dc_kanais_cube")
            {
            }
            bool CanGameObjectGossipHello(Player* player, GameObject* go) override
            {
                if (!player || !go || go->GetEntry() != KanaisCube)
                    return false;
                WindowGame game(player);
                CubePush wire{player};
                try
                {
                    Window::SendCube(game, wire, "open");
                }
                catch (Bridge::Refusal const& refusal)
                {
                    wire.Record({"X", refusal.what()});
                }
                catch (std::exception const& error)
                {
                    LOG_ERROR("server", "[DC cube] the Cube did not open for {}: {}", player->GetName(), error.what());
                    wire.Record({"X", "That did not work."});
                }
                return true;
            }
        };
        class Commands final : public CommandScript
        {
        public:
            Commands()
                : CommandScript("dc_artisan_commands")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable dc = {{"artisan", Handle, SEC_ADMINISTRATOR, Console::No},
                                              {"jeweler", JewelerAction, SEC_ADMINISTRATOR, Console::No},
                                              {"mats", Materials, SEC_ADMINISTRATOR, Console::No}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
            static bool Handle(ChatHandler* handler, std::string action, uint32 first, Optional<uint32> second,
                               Optional<uint32> third)
            {
                auto* player = handler->GetSession()->GetPlayer();
                PlayerEconomy::Scope accountOperation(player);
                try
                {
                    if (action == "salvage")
                        Salvage(player, first, 0);
                    else if (action == "bulk")
                        Salvage(player, 0, first);
                    else if (action == "craft")
                        Craft(player, first, second.value_or(1));
                    else if (action == "roll")
                        Roll(player, first, second.value_or(UINT32_MAX));
                    else if (action == "pick")
                        Pick(player, first, second.value_or(UINT32_MAX));
                    // Read-only: what the window would draw for this item.
                    else if (action == "place")
                        Describe(player, first);
                    else if (action == "repair")
                        Repair(player, Artisan(player, first == 1 ? Mystic : Blacksmith));
                    else if (action == "transmog")
                    {
                        auto* npc = Artisan(player, Mystic);
                        auto* script = ScriptRegistry<CreatureScript>::GetScriptById(npc->GetScriptId());
                        Need(script, "Transmogrification is unavailable.");
                        ClearGossipMenuFor(player);
                        Need(script->OnGossipHello(player, npc), "Transmogrification could not open.");
                    }
                    else
                        throw std::runtime_error("Unknown artisan action.");
                    return true;
                }
                catch (std::exception const& error)
                {
                    if (auto* op = PlayerEconomy::Current(); op && (op->Dirty() || op->transaction->GetSize()))
                        PlayerEconomy::Fail();
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }
            static bool JewelerAction(ChatHandler* handler, std::string action, uint32 first, Optional<uint32> second,
                                      Optional<uint32> third)
            {
                auto* player = handler->GetSession()->GetPlayer();
                PlayerEconomy::Scope operation(player);
                try
                {
                    if (action == "socket")
                    {
                        Need(second.has_value() && third.has_value() && third.value() > 0,
                             "Choose an item, socket row and bag gem.");
                        Socket(player, first, second.value(), third.value());
                    }
                    else if (action == "remove")
                    {
                        Need(second.has_value(), "Choose an item and socket row.");
                        Socket(player, first, second.value(), 0);
                    }
                    else if (action == "combine")
                        Combine(player, first, second.value_or(1));
                    else if (action == "craft")
                        Craft(player, first, second.value_or(1), true, true);
                    else
                        throw std::runtime_error("Unknown Jeweler action.");
                    return true;
                }
                catch (std::exception const& error)
                {
                    if (auto* op = PlayerEconomy::Current(); op && (op->Dirty() || op->transaction->GetSize()))
                        PlayerEconomy::Fail();
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }
            static bool Materials(ChatHandler* handler, uint32 count)
            {
                PlayerEconomy::Scope accountOperation(handler->GetSession()->GetPlayer());
                try
                {
                    Need(count > 0 && count <= TunableCount("gm_material_grant_max_count"),
                         "Choose a material count within the configured grant limit.");
                    auto* player = handler->GetSession()->GetPlayer();
                    Amounts items;
                    for (uint32 entry = 102000; entry <= 102004; ++entry)
                        items[entry] = count;
                    // Test gems: published recipe and enchant denominations, no combining.
                    auto gems =
                        WorldDatabase.Query("SELECT entry FROM dc_gem_item WHERE tier IN ('Marquise','Imperial')");
                    if (gems)
                        do
                        {
                            items[(*gems)[0].Get<uint32>()] = std::min(count, TunableCount("gm_gem_grant_max_count"));
                        } while (gems->NextRow());
                    CheckRoom(player, items);
                    Grant(player, items);
                    Save(player, PlayerEconomy::BeginTransaction());
                    handler->SendSysMessage("Materials and test gems granted.");
                    return true;
                }
                catch (std::exception const& error)
                {
                    if (auto* op = PlayerEconomy::Current(); op && (op->Dirty() || op->transaction->GetSize()))
                        PlayerEconomy::Fail();
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }
        };
        class Bindings final : public MiscScript
        {
        public:
            Bindings()
                : MiscScript("dc_enchant_binding", {MISCHOOK_CAN_APPLY_SOULBOUND_FLAG})
            {
            }
            bool CanApplySoulboundFlag(Item* item, ItemTemplate const*) override
            {
                if (!item)
                    return true;
                auto row = CharacterDatabase.Query("SELECT bound_account FROM dc_item_instance WHERE item_guid={}",
                                                   item->GetGUID().GetCounter());
                return !row || (*row)[0].Get<uint32>() == 0;
            }
        };
    } // namespace

    std::uint32_t RollGemEntry(unsigned monsterLevel, unsigned tier)
    {
        auto rates =
            WorldDatabase.Query("SELECT gem_chance_pct,gem_imperial_share_pct FROM dc_loot_tuning WHERE source='gem'");
        if (!rates)
            return 0;
        double chance = (*rates)[0].Get<double>(), imperialShare = (*rates)[1].Get<double>();
        if (!std::isfinite(chance) || chance < 0 || chance > 100 || !std::isfinite(imperialShare) ||
            imperialShare < 0 || imperialShare > 100)
            return 0;
        if (!roll_chance_f(chance))
            return 0;
        auto rows = WorldDatabase.Query(
            "SELECT d.gem_tier,d.min_tier FROM dc_gem_drop d JOIN dc_tier_phase p ON p.tier_id={} WHERE {} BETWEEN "
            "d.min_level AND d.max_level AND d.min_tier<=p.tier_id ORDER BY d.min_tier",
            tier, monsterLevel);
        if (!rows)
            return 0;
        std::string selected = (*rows)[0].Get<std::string>();
        if (rows->NextRow() && roll_chance_f(imperialShare))
            selected = (*rows)[0].Get<std::string>();
        auto gems =
            WorldDatabase.Query("SELECT entry FROM dc_gem_item WHERE tier='{}' ORDER BY entry", Escape(selected));
        if (!gems)
            return 0;
        std::vector<uint32> entries;
        do
        {
            entries.push_back((*gems)[0].Get<uint32>());
        } while (gems->NextRow());
        return entries[urand(0, uint32(entries.size() - 1))];
    }
    void RegisterScripts()
    {
        new Commands();
        // The same actions on the window bridge. The window Lua sends them, so the old verbs
        // are GM-only test commands.
        DC::Bridge::Routes().Add(
            "DCARTISAN", {"crafting", "artisan_burst", "artisan_per_second"},
            [](Player& player, Bridge::Request const& request, Bridge::Wire<Player> const& wire)
            {
                PlayerEconomy::Scope operation(&player);
                WindowGame game(&player);
                Window::Artisan(game, request, wire);
            });
        DC::Bridge::Routes().Add(
            "DCJEWELER", {"crafting", "jeweler_burst", "jeweler_per_second"},
            [](Player& player, Bridge::Request const& request, Bridge::Wire<Player> const& wire)
            {
                PlayerEconomy::Scope operation(&player);
                WindowGame game(&player);
                Window::Jeweler(game, request, wire);
            });
        // Kanai's Cube, its window route and the click that opens it.
        DC::Bridge::Routes().Add(
            "DCCUBE", {"crafting", "cube_burst", "cube_per_second"},
            [](Player& player, Bridge::Request const& request, Bridge::Wire<Player> const& wire)
            {
                PlayerEconomy::Scope operation(&player);
                WindowGame game(&player);
                Window::CubeRequest(game, request, wire);
            });
        new KanaisCubeObject();
        RegisterCubeScripts();
        RegisterRepairScripts();
        new Bindings();
    }
} // namespace DC::Crafting
