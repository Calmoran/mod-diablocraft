// Stand-ins for the core and ALE types the two patched readers touch. Only the
// members the readers call exist here, with the core's own names and shapes
// (Mail.h, TradeData.h, Player.h at the pin); the reader bodies themselves are
// the patch's own lines, extracted by test_mail_trade_readers.py.
#pragma once
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <map>
#include <vector>

using uint8 = uint8_t; using uint32 = uint32_t;
struct lua_State { std::vector<uint32> args; uint32 pushed = 0; bool pushedNil = true; };
struct Item { uint32 guid; };
enum MailState { MAIL_STATE_UNCHANGED = 1, MAIL_STATE_CHANGED = 2, MAIL_STATE_DELETED = 3 };
struct MailItemInfo { uint32 item_guid; };
struct Mail { MailState state; time_t deliver_time; time_t expire_time; std::vector<MailItemInfo> items; };
enum TradeSlots { TRADE_SLOT_COUNT = 7 };
class Player;
class TradeData
{
public:
    TradeData(Player* owner) : _owner(owner) {}
    Item* GetItem(TradeSlots slot) const;
    TradeData* GetTraderData() const;
    Player* _owner; Player* _trader = nullptr; Item* slots[TRADE_SLOT_COUNT] = {};
};
class Player
{
public:
    std::deque<Mail*> mail; std::map<uint32, Item*> mItems; TradeData* trade = nullptr;
    std::deque<Mail*> const& GetMails() const { return mail; }
    Item* GetMItem(uint32 guid) { auto i = mItems.find(guid); return i == mItems.end() ? nullptr : i->second; }
    TradeData* GetTradeData() const { return trade; }
};
inline Item* TradeData::GetItem(TradeSlots slot) const
{
    if (unsigned(slot) >= TRADE_SLOT_COUNT) { std::cerr << "GetItem read slot " << slot << "\n"; std::abort(); }
    return slots[slot];
}
inline TradeData* TradeData::GetTraderData() const { return _trader ? _trader->GetTradeData() : nullptr; }
namespace GameTime { inline std::chrono::seconds GetGameTime() { return std::chrono::seconds(1000000); } }
namespace ALE
{
    template<typename T> T CHECKVAL(lua_State* L, int i, T def) { return unsigned(i - 2) < L->args.size() ? T(L->args[i - 2]) : def; }
    template<typename T> T CHECKVAL(lua_State* L, int i) { return T(L->args.at(i - 2)); }
    inline void Push(lua_State* L, Item* item) { L->pushedNil = !item; L->pushed = item ? item->guid : 0; }
}
// What a "read everyone's" mutation reaches for.
namespace World { extern std::deque<Mail*> allMail; extern TradeData* someoneElsesTrade; }
