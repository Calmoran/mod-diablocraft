// M2 bone compatibility: post-fill bone-palette event, and the shadow-batch and main-draw doodad-batch
// detours the client carries exactly one owner of each for.
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
#include "ShadowSpace.hpp"
#include "../compat/BoneBudget.hpp"

#include "engine/events/Event.hpp"
#include "engine/assets/shared/models/m2/M2Format.hpp"
#include "game/M2.hpp"

#include "offsets/engine/Gx.hpp"
#include "offsets/game/M2.hpp"

#include <windows.h>

#include <algorithm>
#include <cstdint>

namespace
{
    namespace ev    = wxl::events;
    namespace m2    = wxl::offsets::game::m2;
    namespace gxoff = wxl::offsets::engine::gx;
    namespace bones = wxl::modern::assets::common::bones;

    m2::M2_BuildBonePaletteFn     g_origBuildBonePalette     = nullptr;
    m2::M2_RenderBatchShadowMapFn g_origRenderBatchShadowMap = nullptr;

    using DrawBatchDoodadFn = void (__fastcall*)(void* ctx, void* edx, void* elements, void* indices);
    DrawBatchDoodadFn g_origDrawBatchDoodad = nullptr;

    // The pair of native functions that own the shared ground-shadow index buffer
    // (model+0x178/0x17C) and vertex buffer (model+0x180/0x184) respectively -- see
    // orchestration/docs/r&d/m2-shadow-coinstance-rendering.md. kRenderBatchShadowMap normally calls
    // both itself, but ONLY when the co-instance count requested for that specific native call is
    // > 1 (a confirmed disassembly finding, "Gate A") -- for a call requesting exactly 1
    // co-instance, NEITHER function runs, so the device's currently bound index/vertex buffer is
    // never (re)confirmed for this model at all; it just keeps drawing from whatever buffer some
    // unrelated prior draw left bound. This is the leading, disassembly-confirmed explanation for
    // the shadow-merge corruption: splitting a run into several native calls (this module's own fix
    // for a real bone-budget overflow crash) can produce calls requesting exactly 1 co-instance each
    // (guaranteed for any model whose chunkSize computes to 1, e.g. felhound), which never gets its
    // own buffer bound at all.
    //
    // CALLING CONVENTIONS, disassembly-confirmed against ALL real native call sites (2026-09-29,
    // after an earlier version of this fix -- calling sub_8360a0 correctly but sub_8362b0 with a
    // MISSING second argument -- caused a real, reproducible client crash: sub_8362b0 ends in
    // `ret 4`, popping a stack argument that was never pushed, corrupting the caller's frame on
    // every single call):
    //   sub_8360a0: thiscall(model)          -- genuinely zero stack args, confirmed at all 5 sites.
    //   sub_8362b0: thiscall(model, int flag) -- ONE stack arg, `ret 4`; 4 of 6 real call sites push
    //               literal 0, so 0 is used here too.
    using ShadowIndexBufferRebuildFn  = void (__thiscall*)(void* model);
    using ShadowVertexBufferRebuildFn = void (__thiscall*)(void* model, int flag);
    constexpr uintptr_t kShadowIndexBufferRebuild  = 0x8360A0; // sub_8360a0
    constexpr uintptr_t kShadowVertexBufferRebuild = 0x8362B0; // sub_8362b0

    /**
     * @brief Forces the shared ground-shadow index/vertex buffers to be (re)bound for this
     *        instance's model, working around the native "skip binding when this call's own
     *        requested co-instance count is <= 1" gate (see the comment above). Calling these
     *        directly, unconditionally, before every split sub-call is intended to be safe: both
     *        functions already do their own "already valid, nothing to do" checks internally (the
     *        cache-valid flag bytes / null-buffer checks documented in the R&D doc) -- so calling
     *        them when the native code would ALSO have called them (requestedCount > 1) is simply
     *        redundant, and calling them when it would NOT have (requestedCount <= 1) is the actual
     *        fix. NOT YET FULLY VERIFIED: calling these before the native function's own
     *        `AllocInstances` call (for THIS specific request) could still tag internal per-section
     *        offset state (`model+0x18C`, found this session, not yet in the R&D doc) against a
     *        stale/zero `model+0x190` for a model whose co-instance pool has never been grown before
     *        -- test cautiously, watch for silent visual wrongness even if this no longer crashes.
     */
    void ForceShadowBufferBind(void* instance)
    {
        __try
        {
            auto* inst = static_cast<m2::M2Instance*>(instance);
            if (!inst || !inst->model) return;
            auto* model = reinterpret_cast<void*>(inst->model);
            reinterpret_cast<ShadowIndexBufferRebuildFn>(kShadowIndexBufferRebuild)(model);
            reinterpret_cast<ShadowVertexBufferRebuildFn>(kShadowVertexBufferRebuild)(model, 0);
        }
        __except (EXCEPTION_EXECUTE_HANDLER) {}
    }

    // --- crash fix: bad device vertex stream on the shadow draw -------------------------------------
    // Restored (2026-09-29) from this session's earlier, separate crash-fix work (a real,
    // independently-confirmed native crash -- kGxDeviceDraw's `baseVertex = stream.offset /
    // stream.stride`, hardware divide-by-zero when a stale device vertex stream's stride is 0 --
    // unrelated to the shadow-merge corruption fixed above; both bugs happened to live in the same
    // function). Unchanged from its working, tested form.

    /// Why BadBaseVertexGuard flagged a draw -- distinguishes the hard-crash case, the previously
    /// already-caught out-of-bounds case, and the newly-added in-bounds-but-still-wrong case, purely
    /// for logging; the mitigation (force zero-base-vertex) is the same for all three.
    enum class BaseVertexFault { kNone, kZeroStride, kNonzeroOutOfBounds, kNonzeroInBounds };

    /// Raw numbers behind a BadBaseVertexGuard verdict, carried out purely for diagnostic logging --
    /// enough to tell a stale/wrong-skin cached vertex count apart from any other kind of corruption.
    struct BaseVertexDiag
    {
        BaseVertexFault fault          = BaseVertexFault::kNone;
        uint32_t        stride         = 0;
        uint32_t        offset         = 0;
        uint32_t        derivedBase    = 0;
        uint32_t        skinVertexCount = 0;
        uint32_t        coInstances    = 0;
        uint64_t        ownCapacity    = 0;
    };

    /**
     * @brief Peeks at the device's currently-bound vertex stream and reports whether the native draw
     *        this shadow batch is about to make would compute a bad base vertex (kGxDeviceDraw,
     *        0x006A3620: `baseVertex = stream.offset / stream.stride`, taken only when
     *        kGxDeviceBaseVertexMode is 0 -- see offsets/engine/Gx.hpp). For this draw type, base
     *        vertex 0 is the only correct value -- flags ANY nonzero derived value, not just
     *        out-of-bounds ones. This is device-global state, not anything specific to the model
     *        about to draw -- something earlier in the frame left a bad stream bound.
     * @param instance  the model instance about to draw (for the sanity-bound diagnostics).
     * @param outDiag   filled with the raw numbers behind the verdict, for logging.
     * @return the field's address (write 1 to it to force the safe zero-base-vertex path for one
     *         call, then restore) when the draw is unsafe; nullptr when it's fine or unreadable.
     */
    uint32_t* BadBaseVertexGuard(void* instance, BaseVertexDiag& outDiag)
    {
        __try
        {
            void* devPtr = *reinterpret_cast<void* const*>(gxoff::kGxDevicePtr);
            if (!devPtr) return nullptr;
            auto* dev = static_cast<uint8_t*>(devPtr);
            auto* modeField = reinterpret_cast<uint32_t*>(dev + gxoff::kGxDeviceBaseVertexMode);
            if (*modeField != 0) return nullptr; // already takes the safe zero-base-vertex path

            auto* stream = *reinterpret_cast<uint8_t* const*>(dev + gxoff::kGxDeviceVertexStream);
            if (!stream) return nullptr;
            const uint32_t stride = *reinterpret_cast<const uint32_t*>(stream + gxoff::kGxBufStreamStride);
            outDiag.stride = stride;
            if (stride == 0) { outDiag.fault = BaseVertexFault::kZeroStride; return modeField; }

            const uint32_t offset = *reinterpret_cast<const uint32_t*>(stream + gxoff::kGxBufStreamOffset);
            const uint32_t derivedBaseVertex = offset / stride;
            outDiag.offset      = offset;
            outDiag.derivedBase = derivedBaseVertex;

            if (derivedBaseVertex == 0) return nullptr; // the one legitimate value for this draw type

            __try
            {
                auto* inst = static_cast<m2::M2Instance*>(instance);
                if (inst && inst->model)
                {
                    auto* mdl = reinterpret_cast<m2::M2Model*>(inst->model);
                    auto* skin = static_cast<wxl::game::m2::M2SkinProfile*>(mdl->skin);
                    if (skin && skin->vertexCount)
                    {
                        const uint32_t coInstances = *reinterpret_cast<const uint32_t*>(
                            reinterpret_cast<uint8_t*>(inst->model) + m2::kOffSharedCoInstanceCount);
                        outDiag.skinVertexCount = skin->vertexCount;
                        outDiag.coInstances     = coInstances;
                        outDiag.ownCapacity     = static_cast<uint64_t>(skin->vertexCount) *
                                                   std::max<uint32_t>(coInstances, 1);
                    }
                }
            }
            __except (EXCEPTION_EXECUTE_HANDLER) {}

            outDiag.fault = (outDiag.ownCapacity && derivedBaseVertex >= outDiag.ownCapacity)
                ? BaseVertexFault::kNonzeroOutOfBounds
                : BaseVertexFault::kNonzeroInBounds;
            return modeField;
        }
        __except (EXCEPTION_EXECUTE_HANDLER) { return nullptr; }
    }

    /**
     * @brief Calls the native ground-shadow draw, guarded against the bad-base-vertex crash above.
     *        Logs the model, run index and the raw diagnostic numbers the first several hundred
     *        times it fires per session.
     */
    void CallShadowMapGuarded(void* instance, uint32_t batchMode, void* skinBatch, void* drawList,
                              uint32_t runIndex, void* skinSection, void* previousSection)
    {
        BaseVertexDiag diag;
        uint32_t* modeField = BadBaseVertexGuard(instance, diag);
        if (modeField)
        {
            static unsigned logged = 0;
            if (logged < 500)
            {
                ++logged;
                const char* stem = "(unknown)";
                __try
                {
                    auto* inst = static_cast<m2::M2Instance*>(instance);
                    if (inst && inst->model)
                        stem = wxl::game::m2::M2Model(reinterpret_cast<void*>(inst->model)).GetPathStem();
                }
                __except (EXCEPTION_EXECUTE_HANDLER) {}
                const char* faultName =
                    diag.fault == BaseVertexFault::kZeroStride         ? "zero stride" :
                    diag.fault == BaseVertexFault::kNonzeroOutOfBounds ? "out-of-bounds base vertex" :
                                                                          "in-bounds but nonzero base vertex";
                WLOG_WARN("m2shadow: bad device vertex stream (%s) at shadow draw for '%s' run=%u -- "
                          "stride=%u offset=%u derivedBase=%u skinVertexCount=%u coInstances=%u "
                          "ownCapacity=%llu -- forcing zero-base-vertex path to avoid crashing",
                          faultName, stem ? stem : "(unreadable)", runIndex,
                          diag.stride, diag.offset, diag.derivedBase, diag.skinVertexCount,
                          diag.coInstances, static_cast<unsigned long long>(diag.ownCapacity));
            }

            *modeField = 1;
            __try
            {
                g_origRenderBatchShadowMap(instance, nullptr, batchMode, skinBatch, drawList,
                                           runIndex, skinSection, previousSection);
            }
            __except (EXCEPTION_EXECUTE_HANDLER)
            {
                WLOG_WARN("m2shadow: native shadow draw faulted even after mitigation (run=%u) -- "
                          "swallowed, this shadow batch is skipped", runIndex);
            }
            *modeField = 0;
            return;
        }
        g_origRenderBatchShadowMap(instance, nullptr, batchMode, skinBatch, drawList,
                                   runIndex, skinSection, previousSection);
    }

    /**
     * @brief Detours bone-palette build, emitting OnBuildBonePalette after the engine fills the buffer.
     *
     * Called from two sites per collection M2 per frame:
     *   (a) the attached-model update path, inside kM2PerFrameUpdate of the parent character.
     *   (b) The outer scene-traversal loop (0x821B4E), which runs AFTER the parent's PerFrameUpdate.
     *
     * Site (b) overwrites any bone-palette modifications that OnM2PerFrameUpdate subscribers made,
     * reverting the collection M2 to its bind pose every frame. By hooking POST-order here,
     * subscribers can re-apply their modifications immediately after the engine's fill -- guaranteed
     * to be the last write before the GPU upload regardless of scene-list ordering.
     *
     * Calling convention: fastcall, ecx = renderCtx, 5 stack args, ret 0x14 (callee-cleanup).
     */
    void __fastcall hkBuildBonePalette(void* renderCtx, void* edx,
        void* sa1, void* sa2, void* sa3, uint32_t sa4, uint32_t sa5)
    {
        g_origBuildBonePalette(renderCtx, edx, sa1, sa2, sa3, sa4, sa5);
        ev::BuildBonePaletteArgs a{ renderCtx };
        wxl_modern_m2::g_api->Emit(uint32_t(ev::Event::OnBuildBonePalette), &a);
    }

    /**
     * @brief Detours the M2 ground-shadow batch draw, splitting an over-budget co-instance run into
     *        several native calls instead of drawing it as one.
     *
     * This detour is the ONLY one the client's real M2 ground-shadow draw can carry (MinHook
     * rejects a second on the same target), so the shadow bone probe rides it from here too.
     *
     * The native function's own bone-copy loop (c31-based, 3 registers/bone) is unbounded across the
     * whole co-instance run -- boneCount * coInstanceCount can exceed the 75-bone VS-constant budget
     * even when boneCount alone is small, overflowing past c255 into the device's own vertex-stream
     * slot cache. That overflow is a confirmed, disasm-verified crash: it corrupts a slot record's
     * "count" dword with a bone-matrix float, which FUN_006844c0 later reads as an array index and
     * faults on a wild address (see corpus/re_comprehension/335/m2_instance_0x184_gx_cache.md §14 for
     * the original trace, and the register-level confirmation recorded in this session's own crash
     * triage). Mirrors DrawBatchDoodad's fix exactly, using the run-list shape
     * kShadowRunStride/kShadowRunCountField document: shrink the run's requested-count field to a
     * bone-budget-safe value per sub-call, advance drawIndex by however many co-instances were
     * actually drawn, and restore the field to the original total before returning -- the caller
     * (RenderModelBatchListShadowMap) reads that same field a second time, right after this call
     * returns, to advance its own run cursor.
     */
    void __fastcall hkRenderBatchShadowMap(
        void* instance, void*, uint32_t batchMode, void* skinBatch, void* drawList,
        uint32_t drawIndex, void* skinSection, void* previousSection)
    {
        if constexpr (wxl_modern_m2::kEnabled)
            wxl::runtime::m2shadow::OnShadowBatch(instance, skinSection);

        uint32_t* runs          = nullptr;
        uint32_t  originalCount = 0;
        uint32_t  chunkSize     = 0;
        __try
        {
            if (drawList && skinSection)
            {
                auto* listData = *reinterpret_cast<uint32_t* const*>(drawList);
                if (listData)
                {
                    runs = listData;
                    originalCount = runs[drawIndex * m2::kShadowRunStride + m2::kShadowRunCountField];

                    const uint32_t boneCount =
                        static_cast<const wxl::structure::m2::M2SkinSection*>(skinSection)->boneCount;
                    chunkSize = boneCount > 0
                        ? std::max<uint32_t>(1u, bones::kMaxBonesPerDraw / boneCount)
                        : originalCount;
                }
            }
        }
        __except (EXCEPTION_EXECUTE_HANDLER)
        {
            runs = nullptr; // fail safe: single native call below, run list left untouched
        }

        if (!runs || chunkSize >= originalCount)
        {
            CallShadowMapGuarded(instance, batchMode, skinBatch, drawList,
                                 drawIndex, skinSection, previousSection);
            return;
        }

        // Splitting an over-budget batch into several native calls (below) is what exposes the
        // buffer-bind gap ForceShadowBufferBind works around -- see its own comment. Combined here
        // with the (unrelated) bad-base-vertex crash guard via CallShadowMapGuarded, since both bugs
        // happen to live on the same native call.
        uint32_t drawn = 0;
        while (drawn < originalCount)
        {
            const uint32_t thisChunk = std::min(chunkSize, originalCount - drawn);
            const uint32_t thisIndex = drawIndex + drawn;
            runs[thisIndex * m2::kShadowRunStride + m2::kShadowRunCountField] = thisChunk;
            ForceShadowBufferBind(instance);
            CallShadowMapGuarded(instance, batchMode, skinBatch, drawList,
                                 thisIndex, skinSection, previousSection);
            drawn += thisChunk;
        }
        runs[drawIndex * m2::kShadowRunStride + m2::kShadowRunCountField] = originalCount;
    }

    /**
     * @brief Detours the main-draw batched-doodad path, splitting an over-budget co-instance batch into
     *        several native calls instead of drawing it as one.
     *
     * The native function already loops internally over groups of AllocInstances' granted capacity, but
     * that capacity is sized for GPU buffer space, not for the c31-based VS-constant budget -- a group
     * can still ask for more than kMaxBonesPerDraw total bones across its co-instances. The fix mirrors
     * that same internal loop shape from the outside: shrink the batch record's run-length field
     * (kM2ElementRunLengthField) to a bone-budget-safe count per call, advance the indices pointer by
     * what was actually drawn, and restore the field to its original value before returning -- the
     * caller (CM2SceneRender::Draw) reads that same field a second time, right after this call returns,
     * to advance its own sorted-index cursor past the whole run.
     */
    void __fastcall hkDrawBatchDoodad(void* ctx, void* edx, void* elements, void* indices)
    {
        uint32_t* countField    = nullptr;
        uint32_t  originalCount = 0;
        uint32_t  chunkSize     = 0;
        __try
        {
            auto* c = static_cast<gxoff::DrawBatchContext*>(ctx);
            if (c->element)
            {
                auto* elementBytes = static_cast<uint8_t*>(c->element);
                countField    = reinterpret_cast<uint32_t*>(elementBytes + gxoff::kM2ElementRunLengthField);
                originalCount = *countField;

                const void* section =
                    *reinterpret_cast<void* const*>(elementBytes + gxoff::kM2ElementSectionField);
                const uint32_t boneCount = section
                    ? static_cast<const wxl::structure::m2::M2SkinSection*>(section)->boneCount
                    : 0;

                chunkSize = boneCount > 0
                    ? std::max<uint32_t>(1u, bones::kMaxBonesPerDraw / boneCount)
                    : originalCount;
            }
        }
        __except (EXCEPTION_EXECUTE_HANDLER)
        {
            countField = nullptr; // fail safe: single native call below, batch record left untouched
        }

        if (!countField || chunkSize >= originalCount)
        {
            g_origDrawBatchDoodad(ctx, edx, elements, indices);
            return;
        }

        auto*    indexBytes = static_cast<uint8_t*>(indices);
        uint32_t drawn       = 0;
        while (drawn < originalCount)
        {
            const uint32_t thisChunk = std::min(chunkSize, originalCount - drawn);
            *countField = thisChunk;
            g_origDrawBatchDoodad(ctx, edx, elements, indexBytes + static_cast<size_t>(drawn) * 4);
            drawn += thisChunk;
        }
        *countField = originalCount;
    }
}

namespace wxl_modern_m2
{
    bool InstallM2CompatBones()
    {
        HookAttachByName("M2.BuildBonePalette", &hkBuildBonePalette, &g_origBuildBonePalette);
        const bool shadowHooked = HookAttachByName("M2.RenderBatchShadowMap",
                                                    &hkRenderBatchShadowMap, &g_origRenderBatchShadowMap);
        HookAttachByName("M2.DrawBatchDoodad", &hkDrawBatchDoodad, &g_origDrawBatchDoodad);
        if constexpr (kEnabled)
            wxl::runtime::m2shadow::Arm(shadowHooked);
        return true;
    }
}
