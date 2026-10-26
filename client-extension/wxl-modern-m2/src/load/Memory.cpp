// M2 buffer allocator: routes large model buffers into the core-owned arena (wxl.m2arena), with a
// standalone-VirtualAlloc fallback.
// Copyright (C) 2026 WarcraftXL
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

// The arena RESERVATION itself lives in core (src/client/CM2Shared/Memory.cpp, Boot phase -- see its
// own comment for why). This file only owns the DECISION of which allocations to route there: past a
// size threshold, ask wxl.m2arena for a range; if the arena is disabled/exhausted/failed, fall back to
// a standalone VirtualAlloc; below the threshold, or with the whole thing disabled, defer to the
// client's own allocator untouched.

#include "../ExtensionApi.hpp"

#include "offsets/game/M2.hpp"

#include <windows.h>

#include <cstdint>
#include <mutex>
#include <unordered_map>

namespace
{
    namespace m2 = wxl::offsets::game::m2;

    m2::M2_BufferAllocFn g_origM2BufferAlloc = nullptr;
    m2::M2_BufferFreeFn  g_origM2BufferFree  = nullptr;

    constexpr uint32_t kDefaultVirtualM2AllocThreshold = 1u * 1024u * 1024u;

    struct VirtualM2Allocation
    {
        void* base = nullptr;      // non-null for standalone VirtualAlloc
        uint32_t arenaOffset = 0;  // valid when base == nullptr
        uint32_t arenaSize = 0;
    };

    std::mutex g_virtualM2AllocMutex;
    std::unordered_map<void*, VirtualM2Allocation> g_virtualM2Allocs;

    bool LargeM2VirtualAllocEnabled()
    {
        static const bool enabled =
            wxl_modern_m2::ConfigFlag("WXL_M2_VIRTUAL_ALLOC", "WarcraftXL_m2_virtual_alloc.disable");
        return enabled;
    }

    uint32_t VirtualM2AllocThreshold()
    {
        static const uint32_t bytes = wxl_modern_m2::ConfigBytesMbKb(
            "WXL_M2_VIRTUAL_ALLOC_THRESHOLD_MB", "WXL_M2_VIRTUAL_ALLOC_THRESHOLD_KB",
            kDefaultVirtualM2AllocThreshold, 64, 2048u * 1024u);
        return bytes;
    }

    void* TryVirtualM2Alloc(uint32_t size)
    {
        const SIZE_T total = static_cast<SIZE_T>(size) + 0x20u;
        auto* base = static_cast<uint8_t*>(VirtualAlloc(nullptr, total, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
        if (!base)
            return nullptr;

        const uintptr_t aligned = (reinterpret_cast<uintptr_t>(base) + 0x1Fu) & ~uintptr_t(0x0Fu);
        auto* ptr = reinterpret_cast<uint8_t*>(aligned);
        const uintptr_t shift = reinterpret_cast<uintptr_t>(ptr) - reinterpret_cast<uintptr_t>(base);
        if (shift == 0 || shift > 0xFF)
        {
            VirtualFree(base, 0, MEM_RELEASE);
            return nullptr;
        }
        ptr[-1] = static_cast<uint8_t>(shift);

        std::lock_guard<std::mutex> lock(g_virtualM2AllocMutex);
        g_virtualM2Allocs.emplace(ptr, VirtualM2Allocation{ base, 0, 0 });
        return ptr;
    }

    void __cdecl hkM2BufferFree(void* ptr)
    {
        if (!ptr)
            return;

        VirtualM2Allocation alloc{};
        bool ours = false;
        {
            std::lock_guard<std::mutex> lock(g_virtualM2AllocMutex);
            auto it = g_virtualM2Allocs.find(ptr);
            if (it != g_virtualM2Allocs.end())
            {
                alloc = it->second;
                g_virtualM2Allocs.erase(it);
                ours = true;
            }
        }

        if (ours && !alloc.base)
        {
            if (const WXL_M2ArenaApi* arena = wxl_modern_m2::Arena())
                arena->Free(alloc.arenaOffset, alloc.arenaSize);
            return;
        }

        if (ours && alloc.base)
        {
            VirtualFree(alloc.base, 0, MEM_RELEASE);
            return;
        }

        g_origM2BufferFree(ptr);
    }

    void* __cdecl hkM2BufferAlloc(uint32_t size, const char* tag, int line)
    {
        if (size >= VirtualM2AllocThreshold() && LargeM2VirtualAllocEnabled())
        {
            if (const WXL_M2ArenaApi* arena = wxl_modern_m2::Arena())
            {
                uint32_t offset = 0, allocSize = 0;
                if (void* ptr = arena->Alloc(size, &offset, &allocSize))
                {
                    {
                        std::lock_guard<std::mutex> lock(g_virtualM2AllocMutex);
                        g_virtualM2Allocs.emplace(ptr, VirtualM2Allocation{ nullptr, offset, allocSize });
                    }
                    WLOG_DEBUG("m2-memory: arena buffer %u bytes (%s)", size, tag ? tag : "M2");
                    if (size >= 8u * 1024u * 1024u) arena->LogAddressSpace("m2-arena");
                    return ptr;
                }
            }

            if (void* standalone = TryVirtualM2Alloc(size))
            {
                WLOG_DEBUG("m2-memory: virtual buffer %u bytes (%s)", size, tag ? tag : "M2");
                if (size >= 8u * 1024u * 1024u)
                    if (const WXL_M2ArenaApi* arena = wxl_modern_m2::Arena())
                        arena->LogAddressSpace("m2-virtual");
                return standalone;
            }
            if (size >= 8u * 1024u * 1024u)
                if (const WXL_M2ArenaApi* arena = wxl_modern_m2::Arena())
                    arena->LogAddressSpace("m2-virtual-failed");
            WLOG_WARN("m2-memory: VirtualAlloc failed for %u bytes, falling back to native allocator", size);
        }

        return g_origM2BufferAlloc(size, tag, line);
    }
}

namespace wxl_modern_m2
{
    bool InstallM2Memory()
    {
        HookAttachByName("M2.BufferAlloc", &hkM2BufferAlloc, &g_origM2BufferAlloc);
        HookAttachByName("M2.BufferFree", &hkM2BufferFree, &g_origM2BufferFree);
        return true;
    }
}
