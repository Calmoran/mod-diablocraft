// The production header src/common/dc_world_outfits.h, included as it is (test_npc_outfits.py puts
// the copy to run on the include path first, so a mutant of the header is run the same way).
//
//   harness answer <guid> <display> <class> <race> <gender> <skin> <face> <hair> <hairColor>
//                  <facialHair> <11 slot display ids>      -> the answer's bytes in hex
//   harness choose <hasCloneCasterAura 0|1> <hasOutfit 0|1> -> Stock | Outfit
#include "dc_world_outfits.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace
{
    // A WorldPacket's write side: little-endian, no padding, what the client reads.
    struct Packet
    {
        std::vector<std::uint8_t> bytes;
        template<class T>
        Packet& put(T value)
        {
            for (unsigned i = 0; i < sizeof(T); ++i)
                bytes.push_back(std::uint8_t(value >> (8 * i)));
            return *this;
        }
    };
    struct Guid
    {
        std::uint64_t raw;
    };
    Packet& operator<<(Packet& p, std::uint8_t v)
    {
        return p.put(v);
    }
    Packet& operator<<(Packet& p, std::uint32_t v)
    {
        return p.put(v);
    }
    Packet& operator<<(Packet& p, Guid const& g)
    {
        return p.put(g.raw);
    }

    std::uint32_t Number(char const* text)
    {
        return std::uint32_t(std::strtoul(text, nullptr, 10));
    }
} // namespace

int main(int argc, char** argv)
{
    using namespace DC::Outfits;
    if (argc == 4 && !std::strcmp(argv[1], "choose"))
    {
        std::puts(ChooseAnswer(Number(argv[2]) != 0, Number(argv[3]) != 0) == Answer::Outfit ? "Outfit" : "Stock");
        return 0;
    }
    if (argc != 5 + 7 + SLOT_COUNT || std::strcmp(argv[1], "answer"))
    {
        std::fputs("usage: see the top of this file\n", stderr);
        return 2;
    }
    Outfit outfit;
    outfit.race = std::uint8_t(Number(argv[5]));
    outfit.gender = std::uint8_t(Number(argv[6]));
    outfit.skin = std::uint8_t(Number(argv[7]));
    outfit.face = std::uint8_t(Number(argv[8]));
    outfit.hair = std::uint8_t(Number(argv[9]));
    outfit.hairColor = std::uint8_t(Number(argv[10]));
    outfit.facialHair = std::uint8_t(Number(argv[11]));
    std::uint32_t displays[SLOT_COUNT];
    for (unsigned slot = 0; slot < SLOT_COUNT; ++slot)
        displays[slot] = Number(argv[12 + slot]);
    Packet packet;
    WriteAnswer(packet, Guid{std::uint64_t(std::strtoull(argv[2], nullptr, 10))}, Number(argv[3]),
                std::uint8_t(Number(argv[4])), outfit, displays);
    for (std::uint8_t byte : packet.bytes)
        std::printf("%02x", byte);
    std::puts("");
    return 0;
}
