// Unit test of the key table behind TormentKeyDown (client-extension/torment/KeyTable.hpp,
// docs/contracts/client-key-state.md). Built and run by the client-extension CI job on
// windows-latest, outside the module so it never lands in Torment.dll. Exit code is the number of
// failed checks.

#include "KeyTable.hpp"

#include <cstdio>

namespace
{
    int g_failed = 0;

    void Check(bool ok, const char* what)
    {
        if (!ok)
        {
            std::printf("FAIL: %s\n", what);
            ++g_failed;
        }
    }
} // namespace

int main()
{
    using torment::KeyTable;
    using torment::VirtualKeyFor;

    {
        KeyTable keys;
        Check(!keys.IsDown('1'), "a new table has no key down");
        keys.OnMessage(WM_KEYDOWN, '1');
        Check(keys.IsDown('1'), "WM_KEYDOWN puts the key down");
        Check(!keys.IsDown('2'), "WM_KEYDOWN touches only its own key");
        keys.OnMessage(WM_KEYDOWN, '1'); // auto-repeat
        keys.OnMessage(WM_KEYUP, '1');
        Check(!keys.IsDown('1'), "one WM_KEYUP releases a repeated key");
    }
    {
        KeyTable keys;
        keys.OnMessage(WM_SYSKEYDOWN, 'Q'); // a key pressed while Alt is held
        Check(keys.IsDown('Q'), "WM_SYSKEYDOWN puts the key down");
        keys.OnMessage(WM_SYSKEYUP, 'Q');
        Check(!keys.IsDown('Q'), "WM_SYSKEYUP releases it");
    }
    {
        KeyTable keys;
        keys.OnMessage(WM_KEYDOWN, '1');
        keys.OnMessage(WM_KILLFOCUS, 0);
        Check(!keys.IsDown('1'), "losing focus releases every key");
        keys.OnMessage(WM_KEYDOWN, '1');
        keys.OnMessage(WM_ACTIVATEAPP, 1);
        Check(keys.IsDown('1'), "the client being activated keeps the keys");
        keys.OnMessage(WM_ACTIVATEAPP, 0);
        Check(!keys.IsDown('1'), "the client being deactivated releases every key");
    }
    {
        KeyTable keys;
        keys.OnMessage(WM_LBUTTONDOWN, 1); // MK_LBUTTON in wParam, not a key
        Check(!keys.IsDown(1), "other messages leave the table alone");
        keys.OnMessage(WM_KEYDOWN, 0x100);
        Check(!keys.IsDown(0), "a wParam past 255 is ignored, not wrapped");
        Check(!keys.IsDown(-1) && !keys.IsDown(256), "out-of-range lookups read as up");
    }

    Check(VirtualKeyFor("Q") == 'Q', "a letter is its own key");
    Check(VirtualKeyFor("1") == '1', "a digit is its own key");
    Check(VirtualKeyFor("SHIFT-1") == '1', "a modifier prefix is skipped");
    Check(VirtualKeyFor("ALT-CTRL-SHIFT-E") == 'E', "every modifier prefix is skipped");
    Check(VirtualKeyFor("F1") == VK_F1 && VirtualKeyFor("F12") == VK_F12, "F1 and F12");
    Check(VirtualKeyFor("F0") == 0 && VirtualKeyFor("F25") == 0, "F0 and F25 are not keys");
    Check(VirtualKeyFor("NUMPAD0") == VK_NUMPAD0 && VirtualKeyFor("NUMPAD9") == VK_NUMPAD9, "NUMPAD0 and NUMPAD9");
    Check(VirtualKeyFor("NUMPAD10") == 0, "NUMPAD10 is not a key");
    Check(VirtualKeyFor("F:") == 0, "only digits count after F");
    Check(VirtualKeyFor("SPACE") == VK_SPACE, "a named key");
    Check(VirtualKeyFor("NUMPADPLUS") == VK_ADD, "a named numpad key");
    Check(VirtualKeyFor("-") == (VkKeyScanA('-') & 0xFF), "punctuation goes by the layout");
    Check(VirtualKeyFor("SHIFT--") == VirtualKeyFor("-"), "SHIFT-- is the minus key");
    Check(VirtualKeyFor("BUTTON4") == 0, "mouse buttons are not in the table");
    Check(VirtualKeyFor("SHIFT-") == 0, "a bare modifier is not a key");
    Check(VirtualKeyFor("") == 0 && VirtualKeyFor(nullptr) == 0, "nothing names no key");

    {
        // The two halves together, as TormentKeyDown uses them.
        KeyTable keys;
        keys.OnMessage(WM_KEYDOWN, VirtualKeyFor("F5"));
        Check(keys.IsDown(VirtualKeyFor("SHIFT-F5")), "F5 held reads down by its binding name");
    }

    std::printf("%d check(s) failed\n", g_failed);
    return g_failed;
}
