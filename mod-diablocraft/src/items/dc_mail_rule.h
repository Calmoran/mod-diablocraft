#ifndef DC_MAIL_RULE_H
#define DC_MAIL_RULE_H

#include <cstdint>
#include <string>

// Items are account bound, so a letter may
// carry gold and text but no attachment, the same rule as the trade window.
// The packet filter (dc_account_economy.cpp) asks this before the core reads a
// CMSG_SEND_MAIL. The layout is the core's HandleSendMail: mailbox guid (u64),
// receiver, subject, body, two u32, then the u8 attachment count. Header-only
// and templated on the packet type so the test compiles this very code. The
// packet is taken by copy: the core still reads the original from the start.
namespace DC::Mail
{
template <typename Packet>
bool SendMailCarriesItem(Packet packet)
{
    try
    {
        std::string text;
        uint32_t word;
        uint8_t count;
        packet.template read<uint64_t>();               // mailbox guid
        packet >> text >> text >> text;                 // receiver, subject, body
        packet >> word >> word >> count;                // stationery, unused, attachment count
        return count != 0;
    }
    catch (...)
    {
        return true;                                    // unreadable: refuse, never guess
    }
}
}

#endif // DC_MAIL_RULE_H
