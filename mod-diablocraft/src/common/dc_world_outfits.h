#ifndef DC_WORLD_OUTFITS_H
#define DC_WORLD_OUTFITS_H
// NPC outfits: any creature can wear a race, gender, face, hair and one item
// per visible slot, sent to the client through its mirror-image data, the way the stock Mirror
// Image shows its caster's gear. The rows live in the world table dc_npc_outfit (generated from
// data/outfits/npc_outfits.csv by generate_npc_outfits.py). This header is the part that needs no
// core: the answer's bytes and the choice of who answers, so a unit test can compile it alone.
// Written fresh after the idea of Rochet2's CreatureOutfits (TrinityCore); no code is taken from it.
#include <cstdint>

namespace DC::Outfits
{
    void RegisterScripts();

    // The visible slots in the order SMSG_MIRRORIMAGE_DATA lists them, which is the order the core's
    // WorldSession::HandleMirrorImageDataRequest writes for a player (SpellHandler.cpp).
    enum Slot : unsigned
    {
        SLOT_HEAD,
        SLOT_SHOULDERS,
        SLOT_SHIRT,
        SLOT_CHEST,
        SLOT_WAIST,
        SLOT_LEGS,
        SLOT_FEET,
        SLOT_WRISTS,
        SLOT_HANDS,
        SLOT_BACK,
        SLOT_TABARD,
        SLOT_COUNT
    };

    struct Outfit
    {
        std::uint8_t race = 0, gender = 0, skin = 0, face = 0, hair = 0, hairColor = 0, facialHair = 0;
        std::uint32_t items[SLOT_COUNT] = {}; // item entries, 0 = nothing in the slot
    };

    enum class Answer
    {
        Stock,
        Outfit
    };

    // A unit that carries the stock clone aura (the Wizard's Mirror Image, creature 900110) is always
    // answered by the core, which copies its caster; a row for such a unit is ignored. Everything
    // without a row is the core's too.
    inline Answer ChooseAnswer(bool hasCloneCasterAura, bool hasOutfit)
    {
        return (!hasCloneCasterAura && hasOutfit) ? Answer::Outfit : Answer::Stock;
    }

    // Everything after the guid in SMSG_MIRRORIMAGE_DATA, byte for byte what the core writes for a
    // player: display id, race, gender, class, skin, face, hair, hair colour, facial hair, guild
    // (unknown, 0), then one display info id per slot. `Packet` is a WorldPacket; the test uses a
    // byte buffer with the same operator<<.
    template<class Packet, class Guid>
    void WriteAnswer(Packet& data, Guid const& guid, std::uint32_t displayId, std::uint8_t unitClass,
                     Outfit const& outfit, std::uint32_t const (&slotDisplays)[SLOT_COUNT])
    {
        data << guid;
        data << std::uint32_t(displayId);
        data << std::uint8_t(outfit.race);
        data << std::uint8_t(outfit.gender);
        data << std::uint8_t(unitClass);
        data << std::uint8_t(outfit.skin);
        data << std::uint8_t(outfit.face);
        data << std::uint8_t(outfit.hair);
        data << std::uint8_t(outfit.hairColor);
        data << std::uint8_t(outfit.facialHair);
        data << std::uint32_t(0);
        for (unsigned slot = 0; slot < SLOT_COUNT; ++slot)
            data << std::uint32_t(slotDisplays[slot]);
    }
} // namespace DC::Outfits
#endif
