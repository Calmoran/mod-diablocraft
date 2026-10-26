// The key table behind TormentKeyDown (docs/contracts/client-key-state.md): which keyboard keys are
// down, kept from the client window's own messages, and the binding names the addon asks by. Plain
// logic with no client calls, so client-extension/tests/key_table_test.cpp runs it on the CI runner.

#pragma once

#include <windows.h>

#include <cstdint>
#include <cstring>

namespace torment
{
    class KeyTable
    {
    public:
        /// One window message, as the client window receives it. Reads only; never consumes it.
        void OnMessage(uint32_t message, uintptr_t wparam)
        {
            switch (message)
            {
                case WM_KEYDOWN:
                case WM_SYSKEYDOWN:
                    Set(wparam, true);
                    break;
                case WM_KEYUP:
                case WM_SYSKEYUP:
                    Set(wparam, false);
                    break;
                // A key held while the window loses focus never gets its key-up here: forget them all,
                // so a channel stops rather than running on a key nobody holds.
                case WM_KILLFOCUS:
                    Clear();
                    break;
                case WM_ACTIVATEAPP:
                    if (!wparam)
                        Clear();
                    break;
            }
        }

        /// True while the virtual key is down.
        bool IsDown(int vk) const
        {
            return vk >= 0 && vk < 256 && down_[vk];
        }

    private:
        void Set(uintptr_t vk, bool down)
        {
            if (vk < 256)
                down_[vk] = down;
        }
        void Clear()
        {
            std::memset(down_, 0, sizeof down_);
        }

        bool down_[256] = {};
    };

    namespace detail
    {
        /// The number after prefix when name is prefix and then digits only; -1 otherwise.
        inline int NumberAfter(const char* name, const char* prefix)
        {
            const size_t n = std::strlen(prefix);
            if (std::strncmp(name, prefix, n) != 0 || !name[n])
                return -1;
            int value = 0;
            for (const char* p = name + n; *p; ++p)
            {
                if (*p < '0' || *p > '9' || value > 99)
                    return -1;
                value = value * 10 + (*p - '0');
            }
            return value;
        }
    } // namespace detail

    /**
     * @brief The virtual key a WoW binding name stands for, as GetBindingKey returns it.
     *
     * Modifier prefixes ("SHIFT-1", "CTRL-SHIFT--") are skipped: the answer is for the last key.
     * Letters and digits are their own key; other single characters go through the player's
     * keyboard layout, as WoW names them. Mouse buttons and anything else unknown are 0.
     */
    inline int VirtualKeyFor(const char* name)
    {
        if (!name)
            return 0;

        static const char* const kModifiers[] = {"ALT-", "CTRL-", "SHIFT-"};
        for (bool skipped = true; skipped;)
        {
            skipped = false;
            for (const char* m : kModifiers)
            {
                const size_t n = std::strlen(m);
                if (std::strncmp(name, m, n) == 0)
                {
                    name += n;
                    skipped = true;
                }
            }
        }

        if (name[0] && !name[1])
        {
            const char c = name[0];
            if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))
                return c;
            const SHORT scan = VkKeyScanA(c);
            return scan == -1 ? 0 : (scan & 0xFF);
        }

        struct Named
        {
            const char* name;
            int vk;
        };
        static const Named kNamed[] = {
            {"SPACE", VK_SPACE},
            {"TAB", VK_TAB},
            {"ENTER", VK_RETURN},
            {"ESCAPE", VK_ESCAPE},
            {"BACKSPACE", VK_BACK},
            {"INSERT", VK_INSERT},
            {"DELETE", VK_DELETE},
            {"HOME", VK_HOME},
            {"END", VK_END},
            {"PAGEUP", VK_PRIOR},
            {"PAGEDOWN", VK_NEXT},
            {"UP", VK_UP},
            {"DOWN", VK_DOWN},
            {"LEFT", VK_LEFT},
            {"RIGHT", VK_RIGHT},
            {"NUMPADPLUS", VK_ADD},
            {"NUMPADMINUS", VK_SUBTRACT},
            {"NUMPADMULTIPLY", VK_MULTIPLY},
            {"NUMPADDIVIDE", VK_DIVIDE},
            {"NUMPADDECIMAL", VK_DECIMAL},
        };
        for (const Named& k : kNamed)
            if (std::strcmp(name, k.name) == 0)
                return k.vk;

        const int f = detail::NumberAfter(name, "F");
        if (f >= 1 && f <= 24)
            return VK_F1 + f - 1;
        const int pad = detail::NumberAfter(name, "NUMPAD");
        if (pad >= 0 && pad <= 9)
            return VK_NUMPAD0 + pad;
        return 0;
    }
} // namespace torment
