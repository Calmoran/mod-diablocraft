// The client sites the damage text hooks reach (docs/contracts/damage-text.md), in Wow.exe build 12340.
//
// Located in reference/wowdecomp 5d0aafad (read only; each address is the OFFSET tag on its function there)
// and checked on the stock exe (tswow's clean build, the one install/patch_wow.py patches): each AddWorld*
// function and CreateWorldText is __thiscall and pops exactly the bytes its arguments take (ret 0x18, 0x10,
// 0x14, 0x10), so a __fastcall detour with an unused EDX slot holds its frame. tests/test_damage_text_sites.py
// holds this file to the decompiled source and to the core's Warden memory checks.
//
// The engine draws a floating number in three steps: CGUnit_C::AddWorld*Text on the unit that was hit decides
// whether the active player may see it (its owner check and the combat text CVars), PlayerNameCreateText
// skips the camera target in first person, and PLAYERNAMEDESC::CreateWorldText places and creates the text.
// The module records the hit in the first step and queues it at the third, so only what the engine would
// draw is queued.

#pragma once

#include <cstddef>
#include <cstdint>

namespace torment::damage_text_sites
{
    /// CGUnit_C::AddWorldDamageText(source, amount, spell, crit, periodic, spellColor).
    constexpr uintptr_t kAddWorldDamageText = 0x00722340;
    using AddWorldDamageTextFn = void(__fastcall*)(void* unit, void* unusedEdx, const uint64_t* source, int32_t amount,
                                                   const void* spell, bool crit, bool periodic, bool spellColor);

    /// CGUnit_C::AddWorldText(source, reason, spell, periodic): the words (Miss, Dodge, Absorb...).
    constexpr uintptr_t kAddWorldText = 0x0071F990;
    using AddWorldTextFn = void(__fastcall*)(void* unit, void* unusedEdx, const uint64_t* source, int32_t reason,
                                             const void* spell, bool periodic);

    /// CGUnit_C::AddWorldHealingText(source, amount, spell, crit, unused).
    constexpr uintptr_t kAddWorldHealingText = 0x00722440;
    using AddWorldHealingTextFn = void(__fastcall*)(void* unit, void* unusedEdx, const uint64_t* source, int32_t amount,
                                                    const void* spell, bool crit, int32_t unused);

    /// PLAYERNAMEDESC::CreateWorldText(type, text, color, pvpRank). Its one caller is PlayerNameCreateText.
    constexpr uintptr_t kCreateWorldText = 0x007E5C30;
    using CreateWorldTextFn = void(__fastcall*)(void* nameDesc, void* unusedEdx, uint32_t type, const char* text,
                                                const void* color, const int32_t* pvpRank);

    /// SpellRec::m_schoolMask, in the record the engine hands the AddWorld* functions.
    constexpr size_t kSpellSchoolMask = 0x0284;

    /// The engine starts a floating text this far below the unit's name position (CreateWorldText).
    constexpr float kTextStartDrop = 0.33333334f;

    /// CGWorldFrame::s_currentWorldFrame, and CGWorldFrame::GetScreenCoordinates(world, screen, clipFlags):
    /// the projection the engine's own world text uses. Answers true only for a point inside the world frame.
    constexpr uintptr_t kCurrentWorldFrame = 0x00B7436C;
    /// CGWorldFrame::m_camera, which the projection reads without a check.
    constexpr size_t kWorldFrameCamera = 0x7E20;
    constexpr uintptr_t kGetScreenCoordinates = 0x004F6D20;
    using GetScreenCoordinatesFn = int(__fastcall*)(void* worldFrame, void* unusedEdx, const float* world,
                                                    float* screen, uint32_t* clipFlags);

    /// The coordinate globals Script_GetCursorPosition reads (Coordinate.cpp): s_ddcWidthScale and
    /// s_aspectCompensation.
    constexpr uintptr_t kDdcWidthScale = 0x00AC0CB4;
    constexpr uintptr_t kAspectCompensation = 0x00AC0CBC;
} // namespace torment::damage_text_sites
