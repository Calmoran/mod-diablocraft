// The core's client-side file-serving hook, published for an extension to consume via
// WXL_Api::GetInterface("wxl.storage", WXL_STORAGE_API_VERSION).
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

#ifndef WXL_STORAGE_API_H
#define WXL_STORAGE_API_H

#include <stdint.h>

#include "wxl/ByteSink.h"

// Wraps wxl::runtime::storage::RegisterClientProvider (engine/storage/StorageHook.hpp), the hook
// checked in the client's own file-open detour before any archive read. A provider that supplies
// whole bytes for a name -- e.g. a drop-in model converted on the spot from a loose source file --
// registers here instead of going through a separate process. `std::vector<uint8_t>&` cannot cross
// the boundary (see PluginApi.h: no STL, no C++ ABI), so the byte count is unknown up front and the
// core hands the provider a growable sink (WXL_ByteSink) to write into instead.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_STORAGE_API_VERSION 1

/**
 * @brief Client-side file provider: supplies whole bytes for `name` without an archive read.
 * @param name  file name requested by the engine, in whatever form the client opened it.
 * @param sink  receives the bytes on a claim; untouched on a decline.
 * @return non-zero when this provider claims `name` and has written to `sink`.
 */
typedef int(__cdecl* WXL_ProvideFn)(const char* name, const WXL_ByteSink* sink);

/**
 * @brief Client-side byte transform: reshapes bytes a native archive read already produced.
 * @param name    file name opened.
 * @param raw     the bytes as natively read.
 * @param rawLen  byte count of @p raw.
 * @param sink    receives the reshaped bytes on a claim; untouched on a decline.
 * @return non-zero when this transform reshaped @p raw and wrote to @p sink.
 */
typedef int(__cdecl* WXL_TransformFn)(const char* name, const uint8_t* raw, uint32_t rawLen, const WXL_ByteSink* sink);

/**
 * @brief Answers a file request with a different name, without moving any bytes.
 * @param name    file name requested by the engine.
 * @param out     receives the replacement name, NUL-terminated, on a claim.
 * @param outCap  capacity of @p out in bytes, terminator included.
 * @return non-zero when this redirect claims @p name and has written @p out.
 */
typedef int(__cdecl* WXL_RedirectFn)(const char* name, char* out, uint32_t outCap);

typedef struct WXL_StorageApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Registers a client-side file provider, checked before any archive read.
     *
     * Providers are tried in registration order; the first to claim a name wins. Safe to call from
     * an extension's WXL_Load.
     * @param fn  provider callback.
     */
    void(__cdecl* RegisterClientProvider)(WXL_ProvideFn fn);

    /**
     * @brief Registers a client-side transform for names ending with @p suffix (case-insensitive).
     *
     * Runs after a successful native archive open, offered the bytes the client just read, so it can
     * reshape a format the client cannot decode as-is (e.g. an uncompressed texture encoding) before
     * the native caller sees the result. Filtering by suffix keeps every unrelated open free.
     * @param suffix  lowercase suffix a name must end with to be offered to fn (e.g. ".blp").
     * @param fn      transform callback.
     */
    void(__cdecl* RegisterClientTransform)(const char* suffix, WXL_TransformFn fn);

    /**
     * @brief Registers a client-side name redirect, consulted before providers and before any read.
     *
     * Where a provider answers a name with bytes, this answers it with a different file, so nothing
     * is copied and everything downstream sees only the name that won. That is what suits it to
     * swapping a whole asset family at once: a model's skin, animations and skeleton are all named
     * after the model, so redirecting each request redirects the set without them having to agree.
     *
     * A redirect must decline any name it would itself produce, or the first request never settles.
     * Redirects are tried in registration order; the first to claim a name wins.
     * @param fn  redirect callback.
     */
    void(__cdecl* RegisterClientRedirect)(WXL_RedirectFn fn);
} WXL_StorageApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_STORAGE_API_H
