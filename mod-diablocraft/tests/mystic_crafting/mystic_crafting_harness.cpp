/*
 * The Mystic's server functions, executed (diablocraft-xw2m return, review point 6).
 *
 * dc_mystic_extract.h is cut out of src/crafting/dc_crafting_shared.cpp and dc_mystic.cpp by
 * scripts/tests/crafting/test_mystic_crafting.py:
 * Pick, MysticState, StoredOffers and what they call, as they are in the module. This file feeds them a stored
 * offer and reads back every statement Pick would save. Each scenario prints PASS <name> or FAILED <name>.
 */
#include "crafting_shim.h"

std::vector<std::vector<Field>> g_offerTable, g_worldRows;
DC::Items::Instance g_instance;
std::vector<DC::Items::EnchantLine> g_lines;
std::vector<std::string> g_saved;
int g_charges = 0, g_removed = 0, g_refreshed = 0;
Item g_item;

#include "dc_mystic_extract.h"

#include <cstdio>
#include <functional>

using namespace DC;
using namespace DC::Crafting;

namespace
{
    constexpr std::uint32_t Guid = 7;
    constexpr unsigned Plain = 1, Damage = 2; // the seq of an ordinary line, and of a weapon's damage line

    Items::Affix Row(unsigned seq, char const* id, double value, double value2 = 0)
    {
        Items::Affix a;
        a.seq = seq;
        a.affixId = id;
        a.kind = "primary";
        a.value = value;
        a.rangeMin = 1;
        a.rangeMax = 500;
        a.value2 = value2;
        a.rangeMin2 = value2 ? 5 : 0;
        a.rangeMax2 = value2 ? 90 : 0;
        return a;
    }
    // One stored choice, as dc_enchant_offer holds it: target, id, value, range, kind, value2, range2, and (hidden,
    // for the double's ORDER BY) its choice_id. The rows go in out of order, so only the ORDER BY puts them right.
    std::vector<Field> Stored(int choice, unsigned target, char const* id, double value, double value2)
    {
        auto n = [](double v) { return Field(std::to_string(v)); };
        return {Field(std::to_string(target)),
                Field(id),
                n(value),
                n(1),
                n(900),
                Field("primary"),
                n(value2),
                n(value2 ? 7 : 0),
                n(value2 ? 95 : 0),
                Field(std::to_string(choice))};
    }

    // The item after a paid roll on `target`: locked to that line, which is marked rerolled.
    void Reset(unsigned target, bool bound = false)
    {
        g_instance = {};
        g_instance.itemGuid = Guid;
        g_instance.rarity = "legendary";
        g_instance.enchantLocked = true;
        g_instance.enchantAttempts = 1;
        g_instance.boundAccount = bound ? 5 : 0;
        g_instance.affixes = {Row(0, "mainstat", 300), Row(Plain, "vit", 120), Row(Damage, "wpnfir", 40, 60)};
        g_item.proto.Class = ITEM_CLASS_WEAPON;
        for (auto& a : g_instance.affixes)
            a.rerolled = a.seq == target;
        g_lines.clear();
        for (auto const& a : g_instance.affixes)
            if (a.seq == target)
                g_lines.push_back({a, 1});
        g_offerTable.clear();
        g_worldRows.clear();
        g_saved.clear();
        ChatHandler::said.clear();
        g_charges = g_removed = g_refreshed = 0;
    }
    void Offer(unsigned target, bool twoPart)
    {
        if (twoPart)
            g_offerTable = {Stored(2, target, "wpnarc", 66, 88), Stored(1, target, "wpncol", 55, 77)};
        else
            g_offerTable = {Stored(2, target, "armor", 322, 0), Stored(1, target, "dex", 211, 0)};
    }

    int failures = 0;
    void check(char const* name, bool ok)
    {
        std::printf("%s %s\n", ok ? "PASS" : "FAILED", name);
        failures += !ok;
    }
    bool refused(std::function<void()> action, char const* text)
    {
        try
        {
            action();
        }
        catch (std::runtime_error const& e)
        {
            return std::string(e.what()) == text;
        }
        return false;
    }
    bool saved(std::string const& part)
    {
        return std::any_of(g_saved.begin(), g_saved.end(),
                           [&](std::string const& s) { return s.find(part) != std::string::npos; });
    }
    bool onlyTheOfferDeleted()
    {
        return g_saved.size() == 1 && g_saved[0] == "DELETE FROM dc_enchant_offer WHERE item_guid=7";
    }
    Player player;
    void pick(std::uint32_t choice)
    {
        Pick(&player, Guid, choice);
    }

    void KeepLeavesTheRowsAndChargesNothing()
    {
        Reset(Plain);
        Offer(Plain, false);
        pick(1);
        check("pick 1: only the offer is deleted, the item's rows are left", onlyTheOfferDeleted());
        check("pick 1: nothing charged, no price read, no contributions touched",
              g_charges == 0 && g_removed == 0 && g_refreshed == 0);
        check("pick 1: says the line was kept",
              ChatHandler::said.size() == 1 && ChatHandler::said[0].find("kept") != std::string::npos);
    }
    void SecondAndThirdWriteTheStoredRoll()
    {
        Reset(Plain);
        Offer(Plain, false);
        pick(2);
        check("pick 2: the line's row is deleted by seq",
              saved("DELETE FROM dc_item_affix WHERE item_guid=7 AND seq=1"));
        check("pick 2: the first stored roll is written whole (id, value, ranges, second part)",
              saved("INSERT INTO dc_item_affix") && saved("'dex',211,1,900,0,0,0,'primary',1"));
        check("pick 2: the offer is deleted and nothing is charged",
              saved("DELETE FROM dc_enchant_offer WHERE item_guid=7") && g_charges == 0);
        check("pick 2: contributions removed then refreshed once", g_removed == 1 && g_refreshed == 1);

        Reset(Plain);
        Offer(Plain, false);
        pick(3);
        check("pick 3: the second stored roll is written", saved("'armor',322,1,900,0,0,0,'primary',1"));
        check("pick 3: nothing but the stored roll is inserted", !saved("'dex'") && g_charges == 0);
    }
    void TwoPartRollsKeepBothParts()
    {
        Reset(Damage);
        Offer(Damage, true);
        pick(3);
        check("pick 3 on a damage line writes value2 and the second bracket",
              saved("'wpnarc',66,1,900,88,7,95,'primary',1") && saved("seq=2"));
    }
    void ChoicesOutsideTheThreeAreRefused()
    {
        Reset(Plain);
        Offer(Plain, false);
        check("pick 0 is refused", refused([] { pick(0); }, "That choice is not available."));
        check("pick 4 is refused", refused([] { pick(4); }, "That choice is not available."));
        check("a refused pick writes nothing", g_saved.empty());
        Reset(Plain);
        check("pick with nothing waiting is refused", refused([] { pick(1); }, "Nothing is waiting to be chosen."));
    }
    void ADamageLineOnlyBecomesADamageLine()
    {
        char const* text = "A weapon's damage line can only become another damage line.";
        Reset(Damage);
        Offer(Damage, false); // an offer stored before the rebuild: one part each
        check("old one-part offer on a damage line: pick 2 refused", refused([] { pick(2); }, text));
        check("old one-part offer on a damage line: pick 3 refused", refused([] { pick(3); }, text));
        check("a refused pick saved nothing", g_saved.empty());
        pick(1);
        check("old one-part offer on a damage line: keeping the line still works", onlyTheOfferDeleted());
        Reset(Damage);
        Offer(Damage, true);
        pick(2);
        check("two-part offer on a damage line: pick 2 goes through", saved("'wpncol',55,1,900,77,7,95,'primary',1"));
        Reset(Plain);
        Offer(Plain, false);
        pick(2);
        check("one-part offer on an ordinary line: unaffected", saved("'dex',211"));
        // A ring's +X-Y Physical Damage is two parts too, but an ordinary line: it may become any offer.
        Reset(Damage);
        g_item.proto.Class = ITEM_CLASS_ARMOR;
        Offer(Damage, false);
        pick(2);
        check("one-part offer on a ring's two-part damage line: pick 2 goes through", saved("'dex',211"));
    }
    void ThePendingScreenLeadsWithTheLineAsItIs()
    {
        Reset(Plain);
        Offer(Plain, false); // two stored rows, no second part: what the code before the rebuild left
        auto state = MysticState(&player, Guid);
        check("pending: three choices", state.pending && state.choices.size() == 3);
        check("pending: the first is the line as it is on the item",
              state.choices.size() == 3 && state.choices[0].id == "vit" && state.choices[0].value == 120);
        check("pending: then the stored rolls in order",
              state.choices.size() == 3 && state.choices[1].id == "dex" && state.choices[2].id == "armor" &&
                  state.choices[1].value == 211 && state.choices[2].value == 322);
        check("pending: an old offer has no second part", state.choices.size() == 3 && state.choices[1].value2 == 0);
        check("pending: lists no price", state.lines.empty() && state.materials.empty());
        Reset(Damage);
        Offer(Damage, true);
        state = MysticState(&player, Guid);
        check("pending on a damage line: the current line keeps both parts",
              state.choices.size() == 3 && state.choices[0].id == "wpnfir" && state.choices[0].value == 40 &&
                  state.choices[0].value2 == 60 && state.choices[2].value2 == 88);
    }
    void TheBindWarningIsTheFirstEnchantOnly()
    {
        Reset(Plain, false);
        Offer(Plain, false);
        check("bind warning on while the item is not bound to an account", MysticState(&player, Guid).bind);
        Reset(Plain, true);
        Offer(Plain, false);
        check("bind warning off once it is bound", !MysticState(&player, Guid).bind);
    }
    void StoredChoicesSurviveARelog()
    {
        Reset(Plain);
        Offer(Plain, false);
        auto before = MysticState(&player, Guid);
        // A relog drops everything in memory but the characters database: a new Player, the same table.
        Player again;
        auto after = MysticState(&again, Guid);
        check("a new session reads the same three choices from the table alone",
              before.choices.size() == 3 && after.choices.size() == 3 && after.choices[1].id == "dex" &&
                  after.choices[2].id == "armor");
        g_offerTable.clear();
        check("with the rows gone nothing is pending", !MysticState(&again, Guid).pending);
    }
} // namespace

int main()
{
    KeepLeavesTheRowsAndChargesNothing();
    SecondAndThirdWriteTheStoredRoll();
    TwoPartRollsKeepBothParts();
    ChoicesOutsideTheThreeAreRefused();
    ADamageLineOnlyBecomesADamageLine();
    ThePendingScreenLeadsWithTheLineAsItIs();
    TheBindWarningIsTheFirstEnchantOnly();
    StoredChoicesSurviveARelog();
    return failures ? 1 : 0;
}
