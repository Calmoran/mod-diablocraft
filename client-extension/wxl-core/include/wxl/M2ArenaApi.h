// The core-owned large-M2 buffer arena, published to wxl-m2 as "wxl.m2arena".
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

#ifndef WXL_M2ARENA_API_H
#define WXL_M2ARENA_API_H

#include <stdint.h>

// The dedicated large-M2 VA reservation has to be taken on the loader thread, inside DllMain, before
// world loading fragments the 32-bit address space -- strictly earlier than any extension can exist
// (extensions load once EngineInit is reached). So the reservation itself stays a core Boot-phase
// feature; only the ALLOCATOR detours that route large M2 buffers into it move to wxl-m2. This table is
// how they reach the arena without linking against it, published via
// wxl::runtime::extensions::PublishInterface once the Boot-phase reservation has run -- before wxl-m2's
// own WXL_Load, so no lazy-fetch dance is needed on its side.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_M2ARENA_API_VERSION 1

typedef struct WXL_M2ArenaApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Reserves, commits and prepares one arena range for a buffer of `size` bytes.
     * @param size       requested payload size.
     * @param outOffset  receives the arena-relative byte offset of the reserved range (for Free).
     * @param outSize    receives the actual (padded, page-aligned) range size (for Free).
     * @return the writable pointer to hand to the client, or NULL when the arena is disabled,
     *         exhausted, or the commit failed -- the caller then falls back to its own standalone
     *         allocation.
     */
    void*(__cdecl* Alloc)(uint32_t size, uint32_t* outOffset, uint32_t* outSize);

    /** @brief Decommits and returns a range previously obtained from Alloc. */
    void(__cdecl* Free)(uint32_t offset, uint32_t size);

    /** @brief Logs a coarse process VA snapshot (commit/reserve/free, arena free/largest) under `reason`. */
    void(__cdecl* LogAddressSpace)(const char* reason);
} WXL_M2ArenaApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_M2ARENA_API_H
