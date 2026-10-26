// Constant (65536): Affix sequence exclusive upper bound; Storage bound.
// Crafting: the Mystic's enchant (cost, roll, pick, the window's read-out).
#include "dc_crafting_internal.h"
#include "../common/dc_economy.h"
#include "PlayerEconomy.h"
#include "../items/dc_enchant_rule.h"
#include "../items/dc_items.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "Player.h"
#include "WorldSession.h"
#include <algorithm>
#include <map>
#include <stdexcept>
#include <vector>

namespace DC::Crafting
{
    using namespace Detail;
    namespace
    {
        // The Mystic, the D3 way (docs/contracts/mystic-enchant-messages.md).
        // A roll costs mystic_base_gold times D3's scalar for the item's next paid roll
        // (data/d3/mystic_cost_scalars.csv), plus the materials its rarity and slot name (data/d3/mystic_rules.csv):
        // 3 Arcane Dust + 3 Veiled Crystal on a weapon or armor, 2 + 2 on a rare ring or amulet; a legendary or set
        // ring or amulet pays one Imperial gem and nothing else, no gold. Materials stay the same on every roll.
        // 12-ui section 2: this is the ONLY place the enchant price exists. Roll() charges exactly this and
        // MysticState() shows exactly this, so the screen and the charge cannot disagree.
        struct EnchantCost
        {
            uint64 gold = 0;      // what Economy::Charge is given
            uint64 shown = 0;     // the same figure in published D3 gold
            bool jewelry = false; // Gem payment flag retained in the existing quote protocol.
            std::string gemTier;
            uint32 gemCount = 0;
            uint32 gem = 0; // the held Imperial gem, or 0 when the player has none
            Amounts materials;
            // The same entries in the order the window draws them, because a map reads back by entry id.
            std::vector<uint32> order;
        };
        EnchantCost CostOf(Player* player, Items::Instance const& instance)
        {
            auto base = WorldDatabase.Query("SELECT slot FROM dc_base_item WHERE entry={}", instance.baseItem);
            Need(bool(base), "Missing base item.");
            std::string slot = (*base)[0].Get<std::string>();
            EnchantCost cost;
            auto rule = WorldDatabase.Query(
                "SELECT payment_kind,material_1_entry,material_2_entry,material_count,gem_tier,gem_count_rule "
                "FROM dc_mystic_rule WHERE rarity='{}' AND slot IN ('{}','*') ORDER BY slot='*' LIMIT 1",
                Escape(instance.rarity), Escape(slot));
            Need(bool(rule), "The Mystic has no rule for this item rarity/slot.");
            auto* policy = rule->Fetch();
            auto payment = policy[0].Get<std::string>();
            Need(payment == "gold" || payment == "gem", "Invalid Mystic payment rule.");
            cost.jewelry = payment == "gem";
            if (!cost.jewelry)
            {
                auto tuning = WorldDatabase.Query("SELECT mystic_base_gold FROM dc_loot_tuning WHERE source='normal'");
                Need(bool(tuning), "Mystic prices are unavailable.");
                auto table = WorldDatabase.Query("SELECT use_count,scalar_tenths FROM dc_mystic_scalar ORDER BY use_count");
                Need(bool(table), "The Mystic's price table is unavailable.");
                std::vector<Enchant::Scalar> scalars;
                do
                {
                    auto* f = table->Fetch();
                    scalars.push_back({f[0].Get<uint32>(), f[1].Get<uint32>()});
                } while (table->NextRow());
                // The next paid roll is the count so far plus one. D3's table ends at its last breakpoint and no
                // price is invented past it, so the roll after that is refused.
                Need(instance.enchantAttempts + 1 <= scalars.back().count,
                     "The Mystic's price table ends at this roll: the item cannot be enchanted again.");
                auto gold = Enchant::Price((*tuning)[0].Get<double>(), instance.enchantAttempts + 1, scalars);
                Need(gold && *gold < UINT64_MAX / Economy::CopperPerGold,
                     "The next enchant exceeds supported currency capacity.");
                cost.shown = *gold;
                cost.gold = Economy::GoldCost(cost.shown);
                uint32 count = policy[3].Get<uint32>();
                cost.order = {policy[1].Get<uint32>(), policy[2].Get<uint32>()};
                Need(count > 0 && cost.order[0] && cost.order[1] && cost.order[0] != cost.order[1],
                     "Invalid Mystic material rule.");
                for (auto entry : cost.order)
                    cost.materials[entry] = count;
                return cost;
            }
            cost.gemTier = policy[4].Get<std::string>();
            auto countRule = policy[5].Get<std::string>();
            Need(!cost.gemTier.empty() && !countRule.empty(), "Missing Mystic gem rule.");
            cost.gemCount = SourcedCount(countRule.c_str());
            Need(cost.gemCount > 0, "Invalid Mystic gem count.");
            auto rows = WorldDatabase.Query("SELECT entry FROM dc_gem_item WHERE tier='{}' ORDER BY entry",
                                            Escape(cost.gemTier));
            if (rows)
                do
                {
                    auto entry = (*rows)[0].Get<uint32>();
                    if (player->HasItemCount(entry, cost.gemCount, false))
                    {
                        cost.gem = entry;
                        break;
                    }
                } while (rows->NextRow());
            if (cost.gem)
            {
                cost.materials[cost.gem] = cost.gemCount;
                cost.order.push_back(cost.gem);
            }
            return cost;
        }
        // A jewelry enchant with no Imperial gem in the bags would otherwise throw
        // the generic "Not enough materials." while the screen listed only the two
        // materials the player did hold. Name the gem instead; the cost is correct.
        void NeedGem(EnchantCost const& cost)
        {
            if (cost.jewelry && !cost.gem)
                throw std::runtime_error("Jewelry enchanting requires " + std::to_string(cost.gemCount) + " " +
                                         cost.gemTier + " gem(s) of any colour instead of gold.");
        }
        // A paid roll waits in dc_enchant_offer for a choice: its two new rolls, in choice order. The line it is
        // about is kept as it is on the item, so the first of the three choices is always its current value, and
        // an offer stored by the code before the rebuild (two rows, no second part) reads the same way.
        struct StoredOffer
        {
            unsigned target = 0;
            Items::Affix affix;
        };
        std::vector<StoredOffer> StoredOffers(uint64 guid)
        {
            std::vector<StoredOffer> offers;
            auto rows = CharacterDatabase.Query("SELECT target_seq,affix_id,value,range_min,range_max,kind,value2,"
                                                "range_min2,range_max2 FROM dc_enchant_offer WHERE item_guid={} "
                                                "ORDER BY choice_id",
                                                guid);
            if (rows)
                do
                {
                    auto* f = rows->Fetch();
                    StoredOffer offer;
                    offer.target = f[0].Get<uint16>();
                    auto& a = offer.affix;
                    a.seq = offer.target;
                    a.affixId = f[1].Get<std::string>();
                    a.value = f[2].Get<double>();
                    a.rangeMin = f[3].Get<double>();
                    a.rangeMax = f[4].Get<double>();
                    a.kind = f[5].Get<std::string>();
                    a.value2 = f[6].Get<double>();
                    a.rangeMin2 = f[7].Get<double>();
                    a.rangeMax2 = f[8].Get<double>();
                    a.rerolled = true;
                    offers.push_back(offer);
                } while (rows->NextRow());
            return offers;
        }
        // The listed line a seq stands for: the sockets are one line, so any socket row's seq is it.
        Items::EnchantLine const& ListedLine(std::vector<Items::EnchantLine> const& lines,
                                             Items::Instance const& instance, uint32 seq)
        {
            bool socket = Affix(instance, seq).kind == "socket";
            auto found = std::find_if(lines.begin(), lines.end(), [&](Items::EnchantLine const& l)
                                      { return l.affix.seq == seq || (socket && l.affix.kind == "socket"); });
            Need(found != lines.end(), instance.enchantLocked ? "Only the previously enchanted property can be replaced."
                                                              : "That property cannot be enchanted.");
            return *found;
        }
        void NeedReplaceable(Items::EnchantLine const& line)
        {
            Need(line.state != int(Enchant::State::Gems), "Remove the socketed gems first.");
            Need(line.state != int(Enchant::State::Nothing), "This property cannot be replaced.");
        }
        void NeedMysticItem(Items::Instance const& instance)
        {
            Need(Enchant::Eligible(instance.rarity), "The Mystic only enchants rare, legendary and set items.");
        }
        Enchant::Pick AsPick(Items::Affix const& a)
        {
            return {a.seq, a.affixId, a.kind, a.value, a.value2, a.rangeMin, a.rangeMax, a.rangeMin2, a.rangeMax2};
        }
        Window::EnchantAffix Shown(Enchant::Pick const& p, int state = 0)
        {
            Window::EnchantAffix out;
            out.seq = p.seq;
            out.id = p.id;
            out.kind = p.kind;
            out.state = state;
            out.value = p.value;
            out.value2 = p.value2;
            out.min = p.min;
            out.max = p.max;
            out.min2 = p.min2;
            out.max2 = p.max2;
            return out;
        }
    } // namespace
    namespace Detail
    {
        // What the window draws for one item (the N record and what follows it): a waiting roll's three choices,
        // or the lines, the next price and the materials. Read-only. The caller has passed the NPC gate.
        Window::EnchantState MysticState(Player* player, uint32 guid)
        {
            auto* item = Owned(player, guid);
            auto instance = Rolled(item);
            NeedMysticItem(instance);
            Window::EnchantState state;
            state.guid = guid;
            state.entry = item->GetEntry();
            state.rarity = instance.rarity;
            state.enchanted = instance.enchantLocked;
            state.attempts = instance.enchantAttempts;
            state.bind = instance.boundAccount == 0;
            auto offers = StoredOffers(guid);
            if (!offers.empty())
            {
                // The line as it is on the item first, then the stored rolls.
                std::vector<Enchant::Pick> lines, stored;
                for (auto const& line : Items::EnchantLines(player, instance))
                    lines.push_back(AsPick(line.affix));
                for (auto const& offer : offers)
                    stored.push_back(AsPick(offer.affix));
                bool socket = Affix(instance, offers.front().target).kind == "socket";
                auto three = Enchant::Waiting(lines, offers.front().target, socket, stored);
                Need(bool(three), "The enchanted property is missing.");
                for (auto const& choice : *three)
                    state.choices.push_back(Shown(choice));
                state.pending = true;
                return state;
            }
            for (auto const& line : Items::EnchantLines(player, instance))
                state.lines.push_back(Shown(AsPick(line.affix), line.state));
            auto cost = CostOf(player, instance);
            state.gold = std::to_string(cost.shown);
            state.goldOk = Economy::CanAfford(player, cost.gold);
            for (auto entry : cost.order)
            {
                uint64 count = cost.materials.at(entry);
                state.materials.push_back({entry, std::to_string(count), std::to_string(Held(player, entry)),
                                           MaterialName(entry), Enough(player, entry, count)});
            }
            // The gem is a cost whether or not the player holds one, so it is listed either way; entry 0 says
            // "any colour" because none is chosen yet.
            if (cost.jewelry && !cost.gem)
                state.materials.push_back(
                    {0, std::to_string(cost.gemCount), "0", cost.gemTier + " gem of any colour", false});
            return state;
        }
        // The `?` on one line: everything it can become, with the range each would roll in.
        std::vector<Window::EnchantAffix> MysticPreview(Player* player, uint32 guid, uint32 seq)
        {
            auto* item = Owned(player, guid);
            auto instance = Rolled(item);
            NeedMysticItem(instance);
            Need(StoredOffers(guid).empty(), "Choose one of the three properties first.");
            auto lines = Items::EnchantLines(player, instance);
            auto const& line = ListedLine(lines, instance, seq);
            NeedReplaceable(line);
            std::vector<Window::EnchantAffix> out;
            for (auto const& a : Items::EnchantPreview(player, instance, line.affix.seq))
                out.push_back(Shown(AsPick(a)));
            return out;
        }
        // Pays now, on the roll: the gold and the materials are taken, the item is bound to the account and locked
        // to this property, and the three choices are stored with the item until one is picked.
        void Roll(Player* player, uint32 guid, uint32 seq)
        {
            Artisan(player, Mystic);
            auto* item = Owned(player, guid);
            auto instance = Rolled(item);
            NeedMysticItem(instance);
            Need(StoredOffers(guid).empty(), "Choose one of the three properties first.");
            auto lines = Items::EnchantLines(player, instance);
            auto const& line = ListedLine(lines, instance, seq);
            NeedReplaceable(line);
            auto const& target = Affix(instance, line.affix.seq);
            auto options = Items::EnchantOptions(player, instance, line.affix.seq);
            Need(options.size() == SourcedCount("mystic_offer_count"), "This property cannot be replaced.");
            auto cost = CostOf(player, instance);
            uint64 price = cost.gold;
            Amounts const& materials = cost.materials;
            NeedGem(cost);
            CheckMaterials(player, materials);
            Need(Economy::CanAfford(player, price), "Not enough account gold.");
            auto tx = PlayerEconomy::BeginTransaction();
            Need(Economy::Charge(player, price), "Gold changed before the enchant could complete.");
            SpendMaterials(player, materials);
            item->SetBinding(true);
            item->SetState(ITEM_CHANGED, player);
            tx->Append("UPDATE dc_item_instance SET "
                       "enchant_locked=1,enchant_attempts=enchant_attempts+1,bound_account={} WHERE item_guid={}",
                       player->GetSession()->GetAccountId(), guid);
            tx->Append("UPDATE dc_item_affix SET rerolled=1 WHERE item_guid={} AND {}", guid,
                       target.kind == "socket" ? "kind='socket'" : "seq=" + std::to_string(target.seq));
            for (unsigned i = 0; i < options.size(); ++i)
            {
                auto const& a = options[i];
                tx->Append("INSERT INTO dc_enchant_offer(item_guid,choice_id,target_seq,affix_id,value,range_min,"
                           "range_max,kind,value2,range_min2,range_max2) VALUES({},{},{},'{}',{},{},{},'{}',{},{},{})",
                           guid, i + 1, target.seq, Escape(a.affixId), a.value, a.rangeMin, a.rangeMax, Escape(a.kind),
                           a.value2, a.rangeMin2, a.rangeMax2);
            }
            Save(player, tx);
            // The charged figures, so a tester can compare this line with the quoted price.
            std::string paid;
            for (auto entry : cost.order)
                paid += (paid.empty() ? "" : ", ") + std::to_string(materials.at(entry)) + " " + MaterialName(entry);
            ChatHandler(player->GetSession())
                .PSendSysMessage("Enchant paid: {} gold and {}. Choose one of three properties.", cost.shown,
                                 paid.empty() ? "no materials" : paid);
        }
        // Choice 1 is the line as it was: the item stays as it is and the roll stays paid. Choices 2 and 3 are
        // the stored rolls. Free: everything was paid on the roll.
        void Pick(Player* player, uint32 guid, uint32 choice)
        {
            Artisan(player, Mystic);
            Need(choice >= 1 && choice <= SourcedCount("mystic_offer_count") + 1, "That choice is not available.");
            auto* item = Owned(player, guid);
            auto instance = Rolled(item);
            auto offers = StoredOffers(guid);
            Need(!offers.empty(), "Nothing is waiting to be chosen.");
            Need(offers.size() == SourcedCount("mystic_offer_count"), "That paid offer is damaged.");
            unsigned seq = offers.front().target;
            auto target = Affix(instance, seq);
            Need(target.rerolled && instance.enchantLocked, "The enchanted affix changed unexpectedly.");
            // A weapon's damage line only ever becomes a damage line. Rolls stored by the code before the
            // rebuild (one part each) on such a line cannot replace it; keeping the line (choice 1) still works.
            // Jewelry's two-part damage line is an ordinary line and may become any offer.
            Need(choice < 2 || target.value2 <= 0 || item->GetTemplate()->Class != ITEM_CLASS_WEAPON ||
                     offers[choice - 2].affix.value2 > 0,
                 "A weapon's damage line can only become another damage line.");
            auto tx = PlayerEconomy::BeginTransaction();
            if (choice > 1)
            {
                if (target.kind == "socket")
                    for (auto const& a : instance.affixes)
                        Need(a.kind != "gem", "Remove gems before replacing sockets.");
                tx->Append("DELETE FROM dc_item_affix WHERE item_guid={} AND {}", guid,
                           target.kind == "socket" ? "kind='socket'" : "seq=" + std::to_string(seq));
                Items::Affix a = offers[choice - 2].affix;
                a.seq = seq;
                unsigned next = 0;
                for (auto const& old : instance.affixes)
                    next = std::max(next, old.seq + 1);
                unsigned count = a.kind == "socket" ? unsigned(a.value) : 1;
                Need(count > 0 && next + count < 65536, "Invalid affix count.");
                if (a.kind == "socket")
                {
                    auto cap = WorldDatabase.Query("SELECT MAX(p.value_max) FROM dc_affix_pool p JOIN dc_base_item b "
                                                   "ON p.slot=b.slot WHERE b.entry={} AND p.affix_id='sockets'",
                                                   instance.baseItem);
                    Need(cap && !(*cap)[0].IsNull() && count <= (*cap)[0].Get<double>(),
                         "Socket count exceeds the sourced slot cap.");
                }
                Items::RemoveContributions(player, item);
                if (a.kind == "socket")
                    a.value = a.rangeMin = a.rangeMax = 1;
                for (unsigned i = 0; i < count; ++i)
                {
                    if (i)
                        a.seq = next++;
                    AffixRow(tx, guid, a);
                }
            }
            tx->Append("DELETE FROM dc_enchant_offer WHERE item_guid={}", guid);
            Save(player, tx);
            if (choice > 1)
                Items::RefreshContributions(player, item);
            ChatHandler(player->GetSession())
                .SendSysMessage(choice > 1 ? "Property replaced." : "Current property kept. The next roll costs more.");
        }
        // The GM read-out of what the window would draw for an item.
        void Describe(Player* player, uint32 guid)
        {
            Artisan(player, Mystic);
            auto state = MysticState(player, guid);
            ChatHandler chat(player->GetSession());
            chat.PSendSysMessage("{} {} bind={} enchanted={} rolls paid={} pending={}", state.guid, state.rarity,
                                 state.bind, state.enchanted, state.attempts, state.pending);
            auto show = [&](char const* label, Window::EnchantAffix const& a)
            {
                chat.PSendSysMessage("{} seq={} {} ({}) state={} {}-{} [{} - {}] [{} - {}]", label, a.seq, a.id, a.kind,
                                     a.state, a.value, a.value2, a.min, a.max, a.min2, a.max2);
            };
            for (auto const& line : state.lines)
                show("line", line);
            for (auto const& choice : state.choices)
                show("choice", choice);
            if (!state.pending)
            {
                chat.PSendSysMessage("next roll: {} gold, gold ok={}", state.gold, state.goldOk);
                for (auto const& m : state.materials)
                    chat.PSendSysMessage("  {} {} need {} have {} ok={}", m.entry, m.name, m.need, m.have, m.ok);
            }
        }
    } // namespace Detail
} // namespace DC::Crafting
