// wxl-m2's one-shot draw interceptor, published for other extensions to consume via
// WXL_Api::GetInterface("wxl.m2draw", WXL_M2DRAW_API_VERSION).
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

#ifndef WXL_M2DRAW_API_H
#define WXL_M2DRAW_API_H

#include <stdint.h>

// wxl-m2 owns the IDirect3DDevice9::DrawIndexedPrimitive vtable slot (patched per-device, like the
// core's own EndScene/Present/Reset swaps -- see wxl-m2's Module.cpp) because the M2 batch-draw path
// (OnM2BatchDraw/OnRibbonDraw) needs per-call granularity events can't carry. A second consumer that
// must bracket ONE native draw with raw device state (extra vertex stream, custom declaration -- e.g.
// wxl-wmo's four-layer material) arms this one-shot slot instead of fighting for the vtable itself.
// Render is single-threaded on this client, so the slot is consumed (cleared) before the interceptor
// runs, same discipline the core's own DIP hook already followed pre-split.

#ifdef __cplusplus
extern "C" {
#endif

#define WXL_M2DRAW_API_VERSION 1

/// IDirect3DDevice9::DrawIndexedPrimitive signature (the stdcall thunk taking the device as `this`).
typedef long(__stdcall* WXL_M2Draw_DIPFn)(void* device, int primType, int baseVertex,
                                          unsigned minIndex, unsigned numVertices,
                                          unsigned startIndex, unsigned primCount);

/**
 * @brief One-shot interceptor signature: wraps exactly the next DrawIndexedPrimitive.
 * @param device      D3D9 device.
 * @param primType    primitive type, native enum value.
 * @param baseVertex  base vertex index.
 * @param minIndex    minimum vertex index referenced.
 * @param numVertices vertex count referenced.
 * @param startIndex  starting index buffer position.
 * @param primCount   primitive count.
 * @param orig        trampoline to the native DrawIndexedPrimitive; the interceptor issues the actual
 *                    draw through this and must restore every device state it touched.
 */
typedef long(__cdecl* WXL_M2Draw_InterceptFn)(void* device, int primType, int baseVertex,
                                              unsigned minIndex, unsigned numVertices,
                                              unsigned startIndex, unsigned primCount,
                                              WXL_M2Draw_DIPFn orig);

typedef struct WXL_M2DrawApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Arms the one-shot interceptor for the very next DrawIndexedPrimitive call.
     * @param fn  interceptor to run once; pass NULL to disarm a previously armed one.
     */
    void(__cdecl* SetOneShotIntercept)(WXL_M2Draw_InterceptFn fn);
} WXL_M2DrawApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_M2DRAW_API_H
