/*
 * Doubles for what the Mystic functions (dc_mystic.cpp, dc_crafting_shared.cpp) ask of the core (diablocraft-xw2m
 * return, review point 6).
 *
 * scripts/tests/crafting/test_mystic_crafting.py cuts the module's own Need, AffixRow, Affix, StoredOffers, AsPick, Shown,
 * MysticState and Pick out of src/crafting/dc_crafting_shared.cpp and dc_mystic.cpp exactly as they are and compiles
 * them after this header. What is doubled is only what lives in the core or in another file:
 *
 *   Player, Item, WorldSession, ChatHandler   a bag with one item (its template's class); ChatHandler records what it says
 *   Owned, Rolled, Artisan, Save              the item the harness holds, its Instance, no NPC gate; Save
 *                                              moves the transaction's statements to g_saved
 *   Items::EnchantLines / Remove / Refresh    the lines the harness lists; counters for the contributions
 *   Economy::Charge, CostOf, PlayerEconomy    counters, so "Pick charges nothing" can fail
 *
 * The rules (Enchant::Waiting), the Items::Instance / Affix types and the Window records are the real headers.
 */
#ifndef MYSTIC_CRAFTING_SHIM_H
#define MYSTIC_CRAFTING_SHIM_H

#include "DatabaseEnv.h"
#include "dc_crafting_window.h"
#include "dc_enchant_rule.h"
#include "dc_items.h"

#include <algorithm>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

class WorldSession
{
};
// The core's item classes Pick reads (ItemTemplate.h): a weapon, and the armour class rings and amulets are.
constexpr std::uint32_t ITEM_CLASS_WEAPON = 2, ITEM_CLASS_ARMOR = 4;
struct ItemTemplate
{
    std::uint32_t Class = ITEM_CLASS_WEAPON;
};
class Item
{
public:
    std::uint32_t GetEntry() const
    {
        return 4242;
    }
    ItemTemplate const* GetTemplate() const
    {
        return &proto;
    }
    ItemTemplate proto; // the harness sets Class: a weapon by default, armour for a ring
};
class Player
{
public:
    WorldSession* GetSession()
    {
        return &session;
    }
    WorldSession session;
};
class ChatHandler
{
public:
    explicit ChatHandler(WorldSession*) {}
    void SendSysMessage(char const* text)
    {
        said.push_back(text);
    }
    template<class... A>
    void PSendSysMessage(char const* text, A const&... a)
    {
        said.push_back(Fill(text, a...));
    }
    static inline std::vector<std::string> said;
};
// ChatHandler(...) is a temporary in the module; give it somewhere to write that survives.
#define MYSTIC_SAID ChatHandler::said

// The harness owns these.
extern DC::Items::Instance g_instance;
extern std::vector<DC::Items::EnchantLine> g_lines;
extern std::vector<std::string> g_saved;
extern int g_charges, g_removed, g_refreshed;
extern Item g_item;

namespace PlayerEconomy
{
    inline CharacterDatabaseTransaction BeginTransaction()
    {
        return std::make_shared<Transaction>();
    }
} // namespace PlayerEconomy

namespace DC::Economy
{
    inline bool CanAfford(Player*, std::uint64_t)
    {
        return true;
    }
    inline bool Charge(Player*, std::uint64_t)
    {
        ++g_charges;
        return true;
    }
    inline std::uint64_t GoldCost(std::uint64_t gold)
    {
        return gold;
    }
} // namespace DC::Economy

namespace DC::Items
{
    inline std::vector<EnchantLine> EnchantLines(Player*, Instance const&)
    {
        return g_lines;
    }
    inline void RemoveContributions(Player*, Item*)
    {
        ++g_removed;
    }
    inline void RefreshContributions(Player*, Item*)
    {
        ++g_refreshed;
    }
} // namespace DC::Items

namespace DC::Crafting
{
    namespace
    {
        using Amounts = std::map<std::uint32_t, std::uint64_t>;
        constexpr std::uint32_t Mystic = 910001; // the NPC's entry; the stand-in Artisan ignores it
        std::string Escape(std::string value)
        {
            return value;
        }
        std::uint32_t SourcedCount(char const*)
        {
            return 2; // mystic_offer_count: the Mystic rolls two new properties
        }
        void Artisan(Player*, std::uint32_t) {}
        Item* Owned(Player*, std::uint32_t)
        {
            return &g_item;
        }
        Items::Instance Rolled(Item*)
        {
            return g_instance;
        }
        void Save(Player*, CharacterDatabaseTransaction transaction)
        {
            for (auto const& statement : transaction->statements)
                g_saved.push_back(statement);
        }
        struct EnchantCost
        {
            std::uint64_t gold = 0, shown = 0;
            bool jewelry = false;
            std::string gemTier;
            std::uint32_t gemCount = 0, gem = 0;
            Amounts materials;
            std::vector<std::uint32_t> order;
        };
        EnchantCost CostOf(Player*, Items::Instance const&)
        {
            ++g_charges; // reading the price in Pick or in the pending screen would be a defect
            return {};
        }
        std::uint64_t Held(Player*, std::uint32_t)
        {
            return 0;
        }
        bool Enough(Player*, std::uint32_t, std::uint64_t)
        {
            return true;
        }
        std::string MaterialName(std::uint32_t)
        {
            return "";
        }
    } // namespace
} // namespace DC::Crafting

#endif
