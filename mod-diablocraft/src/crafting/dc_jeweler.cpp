// Constant (65536): Socket affix sequence exclusive upper bound; Storage bound. Constant (102000): Combine Death's
// Breath identity; Quantity already read from dc_jeweler_recipe.
// Crafting: the Jeweler's socketing and gem combine.
#include "dc_crafting_internal.h"
#include "../common/dc_economy.h"
#include "PlayerEconomy.h"
#include "../items/dc_items.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Player.h"
#include "WorldSession.h"
#include <algorithm>
#include <map>
#include <optional>

namespace DC::Crafting
{
    using namespace Detail;
    namespace Detail
    {
        // gemGuid 0 removes the socket's gem; a gem into an EMPTY socket works anywhere;
        // a gem into a FILLED socket swaps: the old gem comes back to the bags. Removing and swapping are
        // the Jeweler's alone (Window::SocketGate, the one place that rule is written).
        void Socket(Player* player, uint32 guid, uint32 seq, uint32 gemGuid)
        {
            auto* item = Owned(player, guid);
            auto instance = Rolled(item);
            Need(Affix(instance, seq).kind == "socket", "Choose a socket.");
            auto child = std::find_if(instance.affixes.begin(), instance.affixes.end(),
                                      [&](auto const& a) { return a.kind == "gem" && a.parentSeq == int(seq); });
            if (Window::SocketGate(gemGuid != 0, child != instance.affixes.end()) == Window::Npc::Nobody)
                Reachable(player);
            else
                Artisan(player, Jeweler);
            Need(!CharacterDatabase.Query("SELECT 1 FROM dc_enchant_offer WHERE item_guid={}", guid),
                 "Resolve the paid enchant offer first.");
            auto tx = PlayerEconomy::BeginTransaction();
            if (!gemGuid)
            {
                Need(child != instance.affixes.end(), "That socket is already empty.");
                Need(IsGemEntry(child->gemEntry), "Only gems can be removed here.");
                uint64 unsocketGold = SourcedCount("jeweler_unsocket_gold");
                Need(Economy::CanAfford(player, Economy::GoldCost(unsocketGold)), "Not enough gold to remove the gem.");
                Amounts returned = {{child->gemEntry, 1}};
                CheckRoom(player, returned);
                Need(Economy::Charge(player, Economy::GoldCost(unsocketGold)),
                     "Gold changed before the gem could be removed.");
                Items::RemoveContributions(player, item);
                GrantGem(player, *child, tx);
                tx->Append("DELETE FROM dc_item_affix WHERE item_guid={} AND seq={}", guid, child->seq);
            }
            else
            {
                auto* gem = Owned(player, gemGuid);
                Need(!gem->IsEquipped(), "Choose a gem in your bags.");
                std::string id;
                uint32 entry = gem->GetEntry(), rank = 0;
                std::optional<uint32> legendaryRank;
                if (auto legendary = Items::LegendaryGemItemOf(entry))
                {
                    Need(Items::LegendaryGemFits(instance.baseItem, *legendary),
                         "That gem does not fit this kind of item.");
                    // Unique Equipped: not while the same gem is socketed in what is
                    // worn; a swap's own old gem leaves, so it does not count.
                    if (Item* holder = Items::WornLegendaryGem(
                            player, legendary->gemId, {},
                            child != instance.affixes.end() ? std::optional<std::pair<std::uint64_t, unsigned>>(
                                                                  std::make_pair(std::uint64_t(guid), child->seq))
                                                            : std::nullopt))
                        Need(false, (Items::LegendaryGemName(legendary->gemId) + " is already socketed in your " +
                                     holder->GetTemplate()->Name1 +
                                     ". A legendary gem can be worn only once (Unique Equipped).")
                                        .c_str());
                    id = legendary->gemId;
                    legendaryRank = Items::LegendaryGemRankOf(gem->GetGUID().GetCounter());
                }
                else
                {
                    auto data =
                        WorldDatabase.Query("SELECT gem_id,`rank` FROM dc_gem_item WHERE entry={}", entry);
                    Need(bool(data), "Choose a gem.");
                    id = (*data)[0].Get<std::string>();
                    rank = (*data)[1].Get<uint32>();
                }
                unsigned next = 0;
                for (auto const& a : instance.affixes)
                    next = std::max(next, a.seq + 1);
                Need(next < 65536, "Too many affix rows.");
                Amounts returned;
                if (child != instance.affixes.end())
                {
                    // A swap is a removal and a socketing in one request: the removal's own checks first,
                    // before anything is taken.
                    Need(IsGemEntry(child->gemEntry), "Only gems can be removed here.");
                    uint64 unsocketGold = SourcedCount("jeweler_unsocket_gold");
                    Need(Economy::CanAfford(player, Economy::GoldCost(unsocketGold)),
                         "Not enough gold to remove the gem.");
                    returned = {{child->gemEntry, 1}};
                    CheckRoom(player, returned);
                    Need(Economy::Charge(player, Economy::GoldCost(unsocketGold)),
                         "Gold changed before the gem could be removed.");
                }
                Items::RemoveContributions(player, item);
                uint32 count = 1;
                player->DestroyItemCount(gem, count, true);
                if (child != instance.affixes.end())
                {
                    GrantGem(player, *child, tx);
                    tx->Append("DELETE FROM dc_item_affix WHERE item_guid={} AND seq={}", guid, child->seq);
                }
                Items::AppendGemRow(tx, guid, next, id, seq, entry, rank, legendaryRank);
            }
            Save(player, tx);
            Items::RefreshContributions(player, item);
            ChatHandler(player->GetSession())
                .SendSysMessage(!gemGuid ? "Gem returned to your bag."
                                : child != instance.affixes.end() ? "Gem replaced; the old gem is back in your bag."
                                                                  : "Gem socketed.");
        }
        // count gems in one request. Every material, the gold and the room are checked
        // for the whole count before anything is taken, so a short stack makes none rather than some.
        void Combine(Player* player, uint32 output, uint32 count)
        {
            Artisan(player, Jeweler);
            Need(count > 0, "Choose a positive combine count.");
            auto row = WorldDatabase.Query(
                "SELECT r.input_entry,r.input_count,r.gold_d3,r.deaths_breath FROM dc_jeweler_recipe r JOIN "
                "dc_gem_item i ON i.entry=r.input_entry JOIN dc_gem_item o ON o.entry=r.output_entry WHERE "
                "r.output_entry={} AND i.colour=o.colour AND o.`rank`=i.`rank`+1",
                output);
            Need(bool(row), "Unknown normal-gem combine recipe.");
            auto* f = row->Fetch();
            uint32 input = f[0].Get<uint32>(), each = f[1].Get<uint32>(), breath = f[3].Get<uint32>();
            Need(each > 0, "Invalid combine ingredient count.");
            uint64 price = Economy::GoldCost(f[2].Get<uint32>());
            Need(price <= UINT64_MAX / count, "The combine total exceeds supported currency capacity.");
            price *= count;
            Amounts materials = {{input, uint64(each) * count}};
            if (breath)
                materials[102000] = uint64(breath) * count;
            CheckMaterials(player, materials);
            Need(Economy::CanAfford(player, price), "Not enough account gold.");
            CheckRoom(player, {{output, count}});
            auto tx = PlayerEconomy::BeginTransaction();
            Need(Economy::Charge(player, price), "Gold changed before combining.");
            SpendMaterials(player, materials);
            Grant(player, {{output, count}});
            Save(player, tx);
            ChatHandler(player->GetSession()).SendSysMessage("Gems combined.");
        }
    } // namespace Detail
} // namespace DC::Crafting
