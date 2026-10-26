"""diablocraft-g400: item mail and the auction house are refused in the packet filter.

Compiles the module's real DC::Mail::SendMailCarriesItem (dc_mail_rule.h)
against a byte-buffer double laid out like the core's CMSG_SEND_MAIL, and reads
the filter's switch from dc_account_economy.cpp. It requires:

  * a letter with gold and no attachment passes; one attachment (or six) is refused;
  * a short or unreadable packet is refused, and the copy leaves the original unread;
  * the filter refuses CMSG_SEND_MAIL through that rule and every auction opcode;
  * each requirement fails when the code is mutated back (item mail let through,
    an auction opcode dropped).

    python mod-diablocraft/scripts/tests/items/test_mail_auction_block.py
"""
import re
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_class_parity import ROOT, SRC, definition, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

FILTER = SRC / "common/dc_account_economy.cpp"
HEADER = SRC / "items/dc_mail_rule.h"
CORE_MAIL = ROOT / ("azeroth" + "core-wotlk") / "src/server/game/Handlers/MailHandler.cpp"
AUCTION = ["MSG_AUCTION_HELLO", "CMSG_AUCTION_SELL_ITEM", "CMSG_AUCTION_REMOVE_ITEM",
           "CMSG_AUCTION_LIST_ITEMS", "CMSG_AUCTION_LIST_OWNER_ITEMS", "CMSG_AUCTION_PLACE_BID",
           "CMSG_AUCTION_LIST_BIDDER_ITEMS", "CMSG_AUCTION_LIST_PENDING_SALES"]

DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>
typedef uint8_t uint8;
struct Packet {                                   // ByteBuffer's read side, same wire layout
    std::vector<uint8_t> data; size_t rpos = 0;
    template <typename T> T read() {
        if (rpos + sizeof(T) > data.size()) throw std::runtime_error("short");
        T v; std::memcpy(&v, &data[rpos], sizeof(T)); rpos += sizeof(T); return v; }
    Packet& operator>>(uint32_t& v) { v = read<uint32_t>(); return *this; }
    Packet& operator>>(uint8_t& v) { v = read<uint8_t>(); return *this; }
    Packet& operator>>(std::string& s) {
        s.clear(); for (char c; (c = (char)read<uint8_t>());) s.push_back(c); return *this; }
    template <typename T> void put(T v) { auto p = (uint8_t*)&v; data.insert(data.end(), p, p + sizeof(T)); }
    void str(char const* s) { data.insert(data.end(), s, s + std::strlen(s) + 1); }
};
#include "../items/dc_mail_rule.h"
static Packet mail(int attachments, bool complete = true) {
    Packet p; p.put<uint64_t>(24053); p.str("Friend"); p.str("hi"); p.str("body");
    p.put<uint32_t>(0); p.put<uint32_t>(0); p.put<uint8_t>((uint8_t)attachments);
    for (int i = 0; i < attachments; ++i) { p.put<uint8_t>(i); p.put<uint64_t>(100 + i); }
    p.put<uint32_t>(5000); p.put<uint32_t>(0);    // gold, COD
    p.put<uint64_t>(0); p.put<uint8_t>(0);
    if (!complete) p.data.resize(12);
    return p;
}
int main() {
    assert(!DC::Mail::SendMailCarriesItem(mail(0)));          // letter with gold
    for (int n : {1, 2, 6}) assert(DC::Mail::SendMailCarriesItem(mail(n)));
    assert(DC::Mail::SendMailCarriesItem(mail(0, false)));    // truncated: refused
    assert(DC::Mail::SendMailCarriesItem(Packet()));          // empty: refused
    Packet original = mail(1);
    DC::Mail::SendMailCarriesItem(original);
    assert(original.rpos == 0);                               // the core still reads from the start
    return 0;
}
'''


def harness(header):
    return DOUBLES.replace('#include "../items/dc_mail_rule.h"', header)


def filter_switch():
    return definition(FILTER.read_text(), "bool CanPacketReceive(WorldSession*, WorldPacket const& packet)")


def refusals(body):
    """(mail goes through the item rule, the auction opcodes that return false)."""
    mail = "case CMSG_SEND_MAIL:\n                        return !DC::Mail::SendMailCarriesItem(packet);" in body
    tail = body[body.index("case MSG_AUCTION_HELLO:"):body.index("default:")]
    listed = set(re.findall(r"case ((?:CMSG|MSG)_AUCTION_\w+):", tail)) if "return false;" in tail else set()
    return mail, listed


class MailAuctionBlock(unittest.TestCase):
    def test_the_rule_passes_letters_and_refuses_attachments(self):
        ok, out = run(harness(HEADER.read_text()), extra=())
        self.assertTrue(ok, out)

    def test_letting_an_attachment_through_fails_the_test(self):
        ok, _ = run(harness(mutate(HEADER.read_text(), "return count != 0;", "return false;")))
        self.assertFalse(ok)

    def test_reading_the_wrong_field_fails_the_test(self):
        ok, _ = run(harness(mutate(HEADER.read_text(), "packet >> text >> text >> text;",
                                   "packet >> text >> text;")))
        self.assertFalse(ok)

    def test_the_filter_refuses_item_mail_and_every_auction_opcode(self):
        self.assertEqual(refusals(filter_switch()), (True, set(AUCTION)))

    def test_dropping_an_auction_opcode_or_the_mail_rule_is_caught(self):
        body = filter_switch()
        dropped = mutate(body, "case CMSG_AUCTION_PLACE_BID:", "")
        self.assertNotEqual(refusals(dropped), (True, set(AUCTION)))
        open_mail = mutate(body, "return !DC::Mail::SendMailCarriesItem(packet);", "return true;")
        self.assertNotEqual(refusals(open_mail), (True, set(AUCTION)))

    def test_the_filter_lists_every_core_auction_opcode(self):
        # No auction opcode the client can send is left out of the filter.
        opcodes = (SRC.parents[1] / "azeroth" "core-wotlk" / "src/server/game/Server/Protocol/Opcodes.h").read_text()
        client_side = set(re.findall(r"\b((?:CMSG|MSG)_AUCTION_\w+)\s*=", opcodes))
        self.assertEqual(client_side, set(AUCTION))

    def test_gold_and_letters_stay_allowed(self):
        # The rule reads the count only; it names no money field, and the core
        # still takes gold from the same packet.
        self.assertNotIn("money", HEADER.read_text().lower().replace("gold and text", ""))
        self.assertIn("recvData >> money >> COD;", definition(CORE_MAIL.read_text(), "void WorldSession::HandleSendMail("))
        self.assertIn("recvData >> items_count;", CORE_MAIL.read_text())


if __name__ == "__main__":
    unittest.main()
