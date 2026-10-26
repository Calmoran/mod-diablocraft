// Runs the patch's own GetMailAttachment / GetTradeItem (readers.inc) against a
// small world and exits non-zero on the first wrong answer.
#include "shim.h"
namespace World { std::deque<Mail*> allMail; TradeData* someoneElsesTrade = nullptr; }
namespace LuaPlayer {
#include "readers.inc"
}
static int failures = 0;
#define CHECK(cond, what) do { if (!(cond)) { ++failures; std::cerr << "FAIL: " << what << "\n"; } } while (0)
static uint32 mail(Player& p, uint32 idx, uint32 att) { lua_State L{{idx, att}}; LuaPlayer::GetMailAttachment(&L, &p); return L.pushedNil ? 0 : L.pushed; }
static uint32 trade(Player& p, uint32 slot, int partner) { lua_State L{{slot, uint32(partner)}}; LuaPlayer::GetTradeItem(&L, &p); return L.pushedNil ? 0 : L.pushed; }

int main()
{
    time_t now = GameTime::GetGameTime().count();
    Item a1{101}, a2{102}, a3{103}, hidden1{201}, hidden2{202}, hidden3{203}, b1{301}, c1{401}, tA{501}, tAe{502}, tB{601}, tC{701};
    Player A, B, C;
    auto add = [&](Player& p, Item& it) { p.mItems[it.guid] = &it; return it.guid; };
    // A's inbox in the core's order: a deleted mail, two we should see, an undelivered one, an expired one, and a
    // mail whose attachment guid belongs to B's mailbox, not A's.
    Mail deleted{MAIL_STATE_DELETED, now - 10, now + 10, {{add(A, hidden1)}}};
    Mail first{MAIL_STATE_UNCHANGED, now - 10, now + 10, {{add(A, a1)}, {add(A, a2)}}};
    Mail undelivered{MAIL_STATE_UNCHANGED, now + 5, now + 10, {{add(A, hidden2)}}};
    Mail expired{MAIL_STATE_UNCHANGED, now - 20, now - 1, {{add(A, hidden3)}}};
    Mail second{MAIL_STATE_UNCHANGED, now - 10, now + 10, {{add(A, a3)}}};
    Mail foreign{MAIL_STATE_UNCHANGED, now - 10, now + 10, {{b1.guid}}};
    A.mail = {&deleted, &first, &undelivered, &expired, &second, &foreign};
    Mail bMail{MAIL_STATE_UNCHANGED, now - 10, now + 10, {{add(B, b1)}}};
    Mail cMail{MAIL_STATE_UNCHANGED, now - 10, now + 10, {{add(C, c1)}}};
    B.mail = {&bMail}; C.mail = {&cMail};
    World::allMail = {&bMail, &cMail, &deleted, &first, &undelivered, &expired, &second, &foreign};

    // index counts only the mails the client is listed
    CHECK(mail(A, 1, 1) == 101, "row 1 attachment 1 is the first listed mail, the deleted one skipped");
    CHECK(mail(A, 1, 2) == 102, "row 1 attachment 2");
    CHECK(mail(A, 1, 3) == 0, "attachment past the mail's own items is nil");
    CHECK(mail(A, 2, 1) == 103, "row 2 skips the undelivered and the expired mail");
    CHECK(mail(A, 3, 1) == 0, "row 3 does not exist (a foreign attachment is not a row)");
    CHECK(mail(A, 0, 1) == 0 && mail(A, 1, 0) == 0, "index 0 and attachment 0 are nil");
    // only A's own mail
    for (uint32 i = 0; i <= 60; ++i) for (uint32 j = 0; j <= 14; ++j)
    {
        uint32 g = mail(A, i, j);
        CHECK(g == 0 || g == 101 || g == 102 || g == 103, "player A was served item " << g);
    }
    CHECK(mail(A, 2, 1) != 301, "B's item never comes out of A's inbox");
    CHECK(mail(B, 1, 1) == 301 && mail(C, 1, 1) == 401, "each player reads their own mailbox");
    // the list stops at 50
    Player D; std::deque<Mail> many(60, Mail{MAIL_STATE_UNCHANGED, now - 10, now + 10, {}}); std::vector<Item> items(60);
    for (int i = 0; i < 60; ++i) { items[i].guid = 900 + i; many[i].items = {{add(D, items[i])}}; D.mail.push_back(&many[i]); }
    CHECK(mail(D, 50, 1) == 949 && mail(D, 51, 1) == 0, "row 51 is past the client's 50-mail list");

    // trade: A trades with B, C is not trading
    TradeData dA(&A), dB(&B); dA._trader = &B; dB._trader = &A;
    dA.slots[0] = &tA; dA.slots[6] = &tAe; dB.slots[0] = &tB;
    A.trade = &dA; B.trade = &dB;
    TradeData dC(&C); dC.slots[0] = &tC; C.trade = nullptr; World::someoneElsesTrade = &dC;
    CHECK(trade(A, 0, 0) == 501 && trade(A, 6, 0) == 502, "own offered items, including the non-traded slot");
    CHECK(trade(A, 0, 1) == 601, "the partner's offered item");
    CHECK(trade(A, 1, 0) == 0 && trade(A, 1, 1) == 0, "an empty slot is nil");
    CHECK(trade(A, 7, 0) == 0 && trade(A, 7, 1) == 0 && trade(A, 255, 1) == 0, "a slot past the window is nil, never read");
    CHECK(trade(C, 0, 0) == 0 && trade(C, 0, 1) == 0, "a player who is not trading gets nothing, own or partner");
    for (uint32 s = 0; s < 8; ++s) for (int p = 0; p < 2; ++p)
        CHECK(trade(A, s, p) != 701 && trade(C, s, p) != 601 && trade(C, s, p) != 501, "a trade the caller is not in was served");
    dA._trader = nullptr;   // partner gone: their data is unreachable
    CHECK(trade(A, 0, 1) == 0, "no partner data means nil, not a crash");
    A.trade = nullptr;
    CHECK(trade(A, 0, 0) == 0 && trade(A, 0, 1) == 0, "the trade closed: nil");

    if (failures) return 1;
    std::cout << "ALL OK\n";
}
