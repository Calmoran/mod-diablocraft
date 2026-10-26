// wxl-modern-blp's BLP transcode/cap pipeline, published for whatever reads raw archive bytes to call
// via WXL_Api::GetInterface("wxl.modern-blp", WXL_MODERN_BLP_API_VERSION).
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

#ifndef WXL_MODERN_BLP_API_H
#define WXL_MODERN_BLP_API_H

#include <stdint.h>

#include "wxl/ByteSink.h"

// Ex src/host/assets/textures/blp/BlpHost.cpp: the same re-encode/cap logic (engine/assets/shared/
// textures/blp), now running in the client process. wxl-modern-blp wires Transcode to StorageHook's
// client-transform hook itself (wxl.storage, ".blp") -- this interface exists for any OTHER reader
// that already has raw .blp bytes from somewhere and wants the same re-encode/cap without going
// through a file open of its own.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_MODERN_BLP_API_VERSION 1

typedef struct WXL_ModernBlpApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Re-encodes or caps one BLP if it needs it; declines (returns 0) to leave it untouched.
     * @param name    file name, used to route texture-component/environment sizing policy.
     * @param raw     raw BLP bytes as read from wherever they came from.
     * @param rawLen  byte count of @p raw.
     * @param out     receives the transcoded/capped bytes on a claim; untouched on a decline.
     * @return non-zero when @p out was written; the caller should serve @p raw unchanged otherwise.
     */
    int(__cdecl* Transcode)(const char* name, const uint8_t* raw, uint32_t rawLen, const WXL_ByteSink* out);
} WXL_ModernBlpApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_MODERN_BLP_API_H
