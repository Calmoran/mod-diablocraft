// Scene hit-test / opaque-sort SEH guards: quarantine stale scene reads without dropping geometry.
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

#include "../ExtensionApi.hpp"

#include "offsets/game/M2.hpp"

#include <windows.h>

#include <atomic>
#include <cstdint>

namespace
{
    namespace m2 = wxl::offsets::game::m2;

    m2::M2_SceneTriangleHitTestFn g_origSceneTriangleHitTest = nullptr;
    m2::M2_SortOpaqueGeoBatchesFn g_origSortOpaqueGeoBatches = nullptr;
    std::atomic<uint32_t>         g_sceneHitTestFaults{ 0 };
    std::atomic<uint32_t>         g_opaqueSortFaults{ 0 };

    /**
     * @brief Contains a stale M2 collision-buffer read after disconnect/reconnect world teardown.
     *
     * Returning the caller's current hit is the native loop's no-new-triangle result. Keeping the guard at
     * this leaf lets the scene's outer geometry/collision code finish its cleanup and matrix restoration.
     */
    int __fastcall hkSceneTriangleHitTest(
        void* scratch, void* /*edx*/, uint16_t* indexBegin, uint16_t* indexEnd, int vertexBase,
        float* point, int mode, int candidate, float* bestDepth, int currentHit)
    {
        __try
        {
            return g_origSceneTriangleHitTest(
                scratch, nullptr, indexBegin, indexEnd, vertexBase, point, mode, candidate, bestDepth, currentHit);
        }
        __except (EXCEPTION_EXECUTE_HANDLER)
        {
            const uint32_t faults = g_sceneHitTestFaults.fetch_add(1, std::memory_order_relaxed) + 1;
            if (faults == 1 || (faults & (faults - 1)) == 0)
                WLOG_WARN("M2 scene hit-test skipped stale collision data (faults=%u)", faults);
            return currentHit;
        }
    }

    /**
     * @brief Probes the optional shader-effect sort key carried by one 0x44-byte scene element.
     *
     * The scene's opaque-batch sort reads two effect-owned arrays through element+0x30 using the
     * vertex/pixel shader indices at +0x34/+0x38. The effect pointer is not needed by DrawBatch itself;
     * it only refines ordering. A stale key can therefore be cleared without dropping the geometry.
     */
    bool ProbeOpaqueEffectKey(void* rawEntry, void** effectOut, int32_t* vertexIndexOut,
                              int32_t* pixelIndexOut) noexcept
    {
        if (effectOut) *effectOut = nullptr;
        if (vertexIndexOut) *vertexIndexOut = -1;
        if (pixelIndexOut) *pixelIndexOut = -1;
        if (!rawEntry) return false;

        __try
        {
            auto* entry = static_cast<uint8_t*>(rawEntry);
            void* effect = *reinterpret_cast<void**>(entry + 0x30);
            const int32_t vertexIndex = *reinterpret_cast<int32_t*>(entry + 0x34);
            const int32_t pixelIndex = *reinterpret_cast<int32_t*>(entry + 0x38);
            if (effectOut) *effectOut = effect;
            if (vertexIndexOut) *vertexIndexOut = vertexIndex;
            if (pixelIndexOut) *pixelIndexOut = pixelIndex;
            if (!effect) return true;

            // ComputeElementShaders produces small non-negative table indices. Rejecting absurd values
            // also prevents signed index wrap before touching the effect-owned arrays.
            if (vertexIndex < 0 || pixelIndex < 0 || vertexIndex > 0x10000 || pixelIndex > 0x10000)
                return false;

            volatile uint32_t vertexKey = *reinterpret_cast<uint32_t*>(
                static_cast<uint8_t*>(effect) + 0x2C + static_cast<uint32_t>(vertexIndex) * 4u);
            volatile uint32_t pixelKey = *reinterpret_cast<uint32_t*>(
                static_cast<uint8_t*>(effect) + 0x194 + static_cast<uint32_t>(pixelIndex) * 4u);
            (void)vertexKey;
            (void)pixelKey;
            return true;
        }
        __except (EXCEPTION_EXECUTE_HANDLER)
        {
            return false;
        }
    }

    void ClearOpaqueEffectKey(void* rawEntry) noexcept
    {
        if (!rawEntry) return;
        __try
        {
            *reinterpret_cast<void**>(static_cast<uint8_t*>(rawEntry) + 0x30) = nullptr;
        }
        __except (EXCEPTION_EXECUTE_HANDLER) {}
    }

    int PointerOrder(const void* lhs, const void* rhs) noexcept
    {
        const uintptr_t a = reinterpret_cast<uintptr_t>(lhs);
        const uintptr_t b = reinterpret_cast<uintptr_t>(rhs);
        return a < b ? -1 : (a > b ? 1 : 0);
    }

    int __cdecl hkSortOpaqueGeoBatches(void* lhs, void* rhs)
    {
        void* lhsEffect = nullptr;
        void* rhsEffect = nullptr;
        int32_t lhsVs = -1, lhsPs = -1, rhsVs = -1, rhsPs = -1;
        const bool lhsOk = ProbeOpaqueEffectKey(lhs, &lhsEffect, &lhsVs, &lhsPs);
        const bool rhsOk = ProbeOpaqueEffectKey(rhs, &rhsEffect, &rhsVs, &rhsPs);

        if (!lhsOk) ClearOpaqueEffectKey(lhs);
        if (!rhsOk) ClearOpaqueEffectKey(rhs);
        if (!lhsOk || !rhsOk)
        {
            const uint32_t faults = g_opaqueSortFaults.fetch_add(1, std::memory_order_relaxed) + 1;
            if (faults == 1 || (faults & (faults - 1)) == 0)
                WLOG_WARN("M2 opaque-sort: cleared stale effect key (faults=%u lhsFx=%p lhsVS=%d lhsPS=%d rhsFx=%p rhsVS=%d rhsPS=%d)",
                          faults, lhsEffect, lhsVs, lhsPs, rhsEffect, rhsVs, rhsPs);
        }

        __try
        {
            return g_origSortOpaqueGeoBatches(lhs, rhs);
        }
        __except (EXCEPTION_EXECUTE_HANDLER)
        {
            const uint32_t faults = g_opaqueSortFaults.fetch_add(1, std::memory_order_relaxed) + 1;
            if (faults == 1 || (faults & (faults - 1)) == 0)
                WLOG_WARN("M2 opaque-sort: native comparator fault quarantined (faults=%u lhs=%p rhs=%p)",
                          faults, lhs, rhs);
            return PointerOrder(lhs, rhs);
        }
    }
}

namespace wxl_modern_m2
{
    bool InstallM2SceneHitTestSort()
    {
        HookAttachByName("M2.SceneTriangleHitTest", &hkSceneTriangleHitTest, &g_origSceneTriangleHitTest);
        HookAttachByName("M2.SortOpaqueGeoBatches", &hkSortOpaqueGeoBatches, &g_origSortOpaqueGeoBatches);
        return true;
    }
}
