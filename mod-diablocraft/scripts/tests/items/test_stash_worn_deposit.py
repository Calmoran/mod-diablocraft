"""Stash deposit of a WORN item (diablocraft-inventory-grid-removal, q-1001-34; the stash
audit's section 7): unequip and deposit as one server operation, or refuse whole.

The production IsWornIndex, DecodeBag, CheckDepositable and DepositWorn of dc_stash.cpp are
compiled against stubs. Before this change none of them existed in that shape: a worn
index (bag 255, slot below 23) was refused by DecodeBag and there was no worn path.
"""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
SOURCE = (ROOT / "mod-diablocraft/src/items/dc_stash.cpp").read_text(encoding="utf-8")
OUT = ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts/stash-worn-deposit-tests"


def extract(signature):
    start = SOURCE.index(signature)
    opening = SOURCE.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (SOURCE[end] == "{") - (SOURCE[end] == "}")
        end += 1
    return SOURCE[start:end]


CODE = r'''
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
constexpr std::uint8_t INVENTORY_SLOT_BAG_0 = 255, EQUIPMENT_SLOT_END = 19, INVENTORY_SLOT_ITEM_START = 23,
                       INVENTORY_SLOT_ITEM_END = 39, INVENTORY_SLOT_BAG_START = 19, INVENTORY_SLOT_BAG_END = 23,
                       NULL_BAG = 0, NULL_SLOT = 255;
enum InventoryResult { EQUIP_ERR_OK = 0, EQUIP_ERR_BAG_FULL = 1 };
constexpr std::uint32_t ITEM_FIELD_DURATION = 1;
struct ObjectGuid { std::uint32_t v = 0; std::uint32_t GetCounter() const { return v; } };
struct Item {
    uint32 entry = 5000; bool tradable = true, emptyBag = true;
    std::uint16_t pos = 0;
    uint32 GetEntry() const { return entry; }
    bool IsNotEmptyBag() const { return !emptyBag; }
    bool IsInTrade() const { return false; }
    bool IsWrapped() const { return false; }
    uint32 GetUInt32Value(uint32) const { return 0; }
    ObjectGuid GetGUID() const { return {entry}; }
    bool CanBeTraded() const { return tradable; }
    bool IsBoundAccountWide() const { return false; }
};
namespace Economy { constexpr std::uint32_t GoldBarEntry = 1; }
namespace AccountEconomy { bool IsMaterial(std::uint32_t) { return false; } }
struct Rolled { std::uint32_t boundAccount = 0; };
namespace Items { std::shared_ptr<Rolled> Get(std::uint32_t) { return nullptr; } }
struct ItemPosCount { std::uint16_t pos; std::uint32_t count; };
using ItemPosCountVec = std::vector<ItemPosCount>;
std::vector<std::string> events;
struct Session { bool aborted = false; bool EconomyAborted() const { return aborted; } };
struct Player {
    std::map<std::uint16_t, Item*> cells;
    bool bagsFull = false;
    Session session;
    Session* GetSession() { return &session; }
    Item* GetItemByPos(uint8 b, uint8 s) const {
        auto it = cells.find(std::uint16_t(b << 8) | s); return it == cells.end() ? nullptr : it->second;
    }
    InventoryResult CanStoreItem(uint8, uint8, ItemPosCountVec& dest, Item*, bool) {
        if (bagsFull) return EQUIP_ERR_BAG_FULL;
        dest.push_back({std::uint16_t((INVENTORY_SLOT_BAG_0 << 8) | 24), 1});
        return EQUIP_ERR_OK;
    }
    void SwapItem(std::uint16_t from, std::uint16_t to) {
        events.push_back("swap " + std::to_string(from >> 8) + ":" + std::to_string(from & 255) + ">" +
                         std::to_string(to >> 8) + ":" + std::to_string(to & 255));
        Item* item = cells[from]; cells.erase(from);
        if (item) cells[to] = item;
    }
};
struct Key { std::uint32_t account = 1; };
struct Container { std::map<std::uint16_t, Item*> items; unsigned tabs = 1; };
namespace {
constexpr std::int32_t AutoPlace = -1;
constexpr unsigned SlotsPerTab = 70;
void Need(bool ok, char const* message) { if (!ok) throw std::runtime_error(message); }
std::uint16_t FirstFreeStashSlot(Container const& c) {
    for (std::uint16_t p = 0; p < c.tabs * SlotsPerTab; ++p) if (!c.items.count(p)) return p;
    throw std::runtime_error("The Stash is full.");
}
std::uint16_t StashSlot(Container const& c, std::int32_t index) {
    Need(index >= 0 && index < std::int32_t(c.tabs) * std::int32_t(SlotsPerTab), "That stash slot is not unlocked.");
    return std::uint16_t(index);
}
bool failDeposit = false, abortOnFail = false;
std::int32_t depositedFrom = -2, depositedTo = -2;
@DECODE@
@CHECK@
@WORN@
void Deposit(Player* player, Key const&, Container&, std::int32_t from, std::int32_t to) {
    events.push_back("deposit");
    depositedFrom = from; depositedTo = to;
    if (failDeposit && abortOnFail) player->session.aborted = true;  // BagMove: the session is aborted and the item freed
    if (failDeposit) throw std::runtime_error("The Stash could not save that move. Nothing was moved.");
}
@DEPOSITWORN@
}
int checks = 0;
void check(bool pass, char const* name) { ++checks; if (!pass) throw std::runtime_error(name); }
template <class F> std::string refusal(F fn) {
    try { fn(); } catch (std::runtime_error const& e) { return e.what(); }
    return "";
}
int main() {
    for (int slot = 0; slot < 19; ++slot) check(IsWornIndex(25500 + slot), "worn slots 0-18 are worn indexes");
    for (int index : {25519, 25520, 25522, 25523, 25538, 25574, 25600, 0, 2300, 2400, 1903}) check(!IsWornIndex(index), "19-22, backpack, bank, bags are not worn indexes");
    uint8 bag = 0, slot = 0;
    check(!refusal([&] { DecodeBag(25500, bag, slot); }).empty(), "DecodeBag still refuses a worn index");
    check(!refusal([&] { DecodeBag(25519, bag, slot); }).empty(), "DecodeBag still refuses the bag-slot buttons");
    check(refusal([&] { DecodeBag(25523, bag, slot); }).empty() && bag == 255 && slot == 23, "the backpack still decodes");
    Key key; Item sword; sword.entry = 7001;
    auto fresh = [&](Player& p, Container& c) {
        events.clear(); failDeposit = false; abortOnFail = false; depositedFrom = depositedTo = -2;
        c.items.clear(); p.cells.clear(); p.cells[std::uint16_t((255 << 8) | 15)] = &sword; p.bagsFull = false; sword.tradable = true;
    };
    {   // success: taken off first (SwapItem, which fires OnPlayerUnequip), then the ordinary deposit
        Player p; Container c; fresh(p, c);
        DepositWorn(&p, key, c, 25515, AutoPlace);
        check(events.size() == 2 && events[0] == "swap 255:15>255:24" && events[1] == "deposit", "SwapItem off the body, then deposit");
        check(depositedFrom == 25524 && depositedTo == 0, "deposited from the cell it was taken to, into the first free slot");
        check(p.GetItemByPos(255, 15) == nullptr, "no longer worn");
    }
    {   // explicit empty slot
        Player p; Container c; fresh(p, c);
        DepositWorn(&p, key, c, 25515, 12);
        check(depositedTo == 12, "an explicit empty slot is used");
    }
    // Every refusal happens BEFORE anything moves: no SwapItem at all.
    {
        Player p; Container c; fresh(p, c); Item other; c.items[3] = &other;
        check(!refusal([&] { DepositWorn(&p, key, c, 25515, 3); }).empty() && events.empty() && p.GetItemByPos(255, 15) == &sword,
              "a worn item onto an occupied stash slot is refused, still worn");
    }
    {
        Player p; Container c; fresh(p, c); p.bagsFull = true;
        check(!refusal([&] { DepositWorn(&p, key, c, 25515, AutoPlace); }).empty() && events.empty(), "no bag cell: refused, still worn");
    }
    {
        Player p; Container c; fresh(p, c); sword.tradable = false;
        std::string text = refusal([&] { DepositWorn(&p, key, c, 25515, AutoPlace); });
        check(text.find("bound to you when you put it on") != std::string::npos && events.empty(), "a worn soulbound item: refused with the reason");
        sword.tradable = true;
    }
    {
        Player p; Container c; fresh(p, c);
        check(!refusal([&] { DepositWorn(&p, key, c, 25515, 70); }).empty() && events.empty(), "a locked tab (slot beyond the unlocked ones): refused");
    }
    {
        Player p; Container c; fresh(p, c);
        for (std::uint16_t i = 0; i < 70; ++i) c.items[i] = &sword;
        check(!refusal([&] { DepositWorn(&p, key, c, 25515, AutoPlace); }).empty() && events.empty(), "a full stash: refused, still worn");
    }
    {
        Player p; Container c; fresh(p, c); p.cells.clear();
        check(!refusal([&] { DepositWorn(&p, key, c, 25515, AutoPlace); }).empty() && events.empty(), "nothing worn there: refused");
    }
    {   // the deposit itself fails after every check: the item goes back on
        Player p; Container c; fresh(p, c); failDeposit = true;
        std::string text = refusal([&] { DepositWorn(&p, key, c, 25515, AutoPlace); });
        check(!text.empty(), "the failure is reported");
        check(events.size() == 3 && events[2] == "swap 255:24>255:15", "and the item is put back on with SwapItem");
        check(p.GetItemByPos(255, 15) == &sword, "still worn");
    }
    {   // the deposit fails AFTER it changed the bags: the session is aborted, the item is freed, nothing is swapped back
        Player p; Container c; fresh(p, c); failDeposit = true; abortOnFail = true;
        std::string text = refusal([&] { DepositWorn(&p, key, c, 25515, AutoPlace); });
        check(!text.empty(), "an aborted failure is reported");
        check(events.size() == 2 && events[0] == "swap 255:15>255:24" && events[1] == "deposit", "no swap back on an aborted session");
    }
    std::cout << "PASS " << checks << " production worn-deposit checks\n";
}
'''


def main():
    deposit = extract("void Deposit(Player* player, Key const& key, Container& container, std::int32_t fromIndex, std::int32_t toIndex)\n        {")
    # Route: the production Deposit hands a worn index to DepositWorn before it decodes a bag cell.
    head = deposit[:deposit.index("std::uint8_t bag = 0, slot = 0;")]
    assert "IsWornIndex(fromIndex)" in head and "DepositWorn(player, key, container, fromIndex, toIndex)" in head, \
        "Deposit routes a worn index to DepositWorn"
    code = (CODE.replace("@DECODE@", extract("void DecodeBag("))
            .replace("@CHECK@", extract("void CheckDepositable("))
            .replace("@WORN@", extract("bool IsWornIndex("))
            .replace("@DEPOSITWORN@", extract("void DepositWorn(")))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "test.cpp").write_text(code, encoding="utf-8")
    binary = OUT / "stash_worn_test"
    harness_env.run(["c++", "-std=c++17", "-Wall", "-o", str(binary), str(OUT / "test.cpp")], check=True)
    harness_env.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
