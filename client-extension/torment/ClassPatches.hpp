// tswow's three class patches (Monk 1c, diablocraft-3oetm; docs/contracts/monk-class.md), which Torment.cpp
// writes into Wow.exe's code from WXL_Load instead of into the exe file.
//
// Source: reference/tswow 00608832 tswow-scripts/util/ClientPatches.ts:48-73 ('allow-custom-gluexml',
// 'unlimited race/class pairs patch', 'class roles'). tswow's numbers are FILE offsets; these are the
// addresses they load at. Wow.exe's code section is raw 0x400 at VA 0x401000, so VA = file + kTextFileToVa:
// wxl-core's own glue-unlock script (wxl-core/src/patcher/GlueUnlock.cpp) lists the six glue sites as VAs at
// exactly that shift. tests/test_class_patches.py holds this file to both lists and to the core's Warden
// memory checks.
//
// They fit our exe because this DLL loads only through the loader patch, and that goes only onto tswow's
// clean build (install/patch_wow.py KNOWN, launcher exe.rs: its MD5 is tswow's CLEAN_CLIENT_MD5).
//
// Left out: 'allow-custom-gluexml' also sets the large-address-aware bit (file 0x126, the PE header). The
// Windows loader reads it before any DLL runs, so writing it here would do nothing; wxl's glue script does
// not set it either.

#pragma once

#include <cstddef>
#include <cstdint>

namespace torment::class_patches
{
    constexpr uintptr_t kTextFileToVa = 0x400C00;

    struct Edit
    {
        uintptr_t va;
        uint8_t len;
        uint8_t bytes[7];
    };

    // 'allow-custom-gluexml': the client stops refusing an edited GlueXML or FrameXML (the interface
    // signature check, wxl-core/src/offsets/engine/Addon.hpp kCheckSignature, returns 3 on every path).
    // An addon that declares "## Secure: 1" is still held to its digest by LoadAddOn (Addon.hpp, statuses).
    inline constexpr Edit kGlueXml[] = {
        {0x5F4DBF, 1, {0xEB}}, {0x816625, 1, {0xEB}}, {0x81663F, 1, {0x03}},
        {0x816695, 1, {0x03}}, {0x816746, 1, {0xEB}}, {0x81675F, 7, {0xB8, 0x03, 0x00, 0x00, 0x00, 0xEB, 0xED}},
    };

    // 'unlimited race/class pairs patch': four bytes in the character-creation code (CCharacterCreation,
    // 0x004E1xxx in wxl-core/src/offsets/game/CharCreate.hpp), so the create screen takes the CharBaseInfo
    // pairs of a class past the stock ones.
    inline constexpr Edit kRaceClassPairs[] = {
        {0x4E0F55, 1, {0x78}},
        {0x4E0F8E, 1, {0x88}},
        {0x4E0FA3, 1, {0x88}},
        {0x4E0FC3, 1, {0x88}},
    };

    // 'class roles': the client reads a class's LFG role mask as a byte at table[class id], through five
    // instructions that each carry the table's address as a 4-byte operand. tswow moves the table into a
    // cave of the exe sized for 32 classes; Torment.cpp moves it into the DLL instead and copies the stock
    // entries, so no byte of the exe's data is written. A class past the stock ones gets 0, no role
    // (monk-class.md: Torment uses no LFG role).
    inline constexpr uintptr_t kRoleTableSites[] = {
        0x552948, 0x553B7D, 0x553B94, 0x553DE7, 0x554922,
    };
    constexpr size_t kStockRoleEntries = 12; // class ids 0..11, Druid the last stock class
    constexpr size_t kRoleEntries = 33;      // tswow's: index 0 and 32 classes
} // namespace torment::class_patches
