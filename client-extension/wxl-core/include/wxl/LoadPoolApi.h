// Generic two-stage background job pool for load-time fixup work, published by wxl-engine-reforged
// as "wxl.loadpool".
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

#ifndef WXL_LOADPOOL_API_H
#define WXL_LOADPOOL_API_H

#include <stdint.h>

// Two stages because load-time fixups (ADT chunk build, WMO chunk walk, M2 skin finalize) mix CPU-only
// compute with a small "publish" step that touches state the renderer also reads live (see
// corpus/re_comprehension/335/async_fixup_threading_safety.md -- e.g. M2 skin finalize's material
// builder calls into CShaderEffectManager, which CShadowQuery::Render also touches with no lock). Only
// stage1 may run on a background worker; stage2 always runs on the main thread, drained a bounded
// number per frame so a streaming burst cannot spend more than that on any single frame.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_LOADPOOL_API_VERSION 1

typedef void(__cdecl* WXL_LoadPool_JobFn)(void* arg);

typedef struct WXL_LoadPoolApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Queues `stage1` to run on a background pool worker; once it returns, queues `stage2` (if
     *        non-null) to run on the MAIN thread, drained a bounded number per frame.
     *
     * `arg` is passed to both stages unchanged; its lifetime is the caller's own -- stage1 typically
     * fills a result into it, stage2 reads the result back and frees it. Falls back to running stage1
     * then stage2 synchronously, inline, on the calling thread when the pool is disabled, so a caller
     * never needs to branch on whether it is live.
     */
    void(__cdecl* Submit)(WXL_LoadPool_JobFn stage1, WXL_LoadPool_JobFn stage2, void* arg);
} WXL_LoadPoolApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_LOADPOOL_API_H
