// Native modern-M2 reader: reads a modern MD21 container directly and fills the client's own model
// runtime with it.
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

// MECHANISM (orchestration -- the phases live in M2Demux / M2Fixups / M2Walk):
//
//   Detour      The existing kInit detour (CompatLoader.cpp, 0x83CF00) routes here when the resident
//               load buffer starts with the raw 'MD21' chunk tag. A stock MD20 v264 model takes the
//               untouched original parser -- the modern path costs stock models one magic compare.
//   Demux       One chunk walk (M2Demux::ScanContainer) harvests the body location + auxiliary chunks.
//               The MD20 body is slid to the buffer base IN PLACE so model+0x150 lands on the header
//               while the ALLOCATION POINTER stays what the destructor free / m2memory arena expect.
//   Fill        In-place field deltas (M2Fixups), then record normalization (M2Normalize) which brings
//               every source-era-wide record onto the one shape the rest of the pipeline steps, then our
//               own offset->pointer walk (M2WalkOwned, driven by the record map in M2WalkLayout), then
//               TXID name injection, then the stock shared-initialize step + stock tail.
//   Live half   The model registers in the modern-M2 AssetRegistry (kFlagHotReshaped); the already-
//               shipping live-engine half (skin-finalize contract rebuild, draw fixups) applies unchanged.
//   Safety      The whole fill runs under SEH: malformed data becomes a logged failure, never a crash.

#include "../ExtensionApi.hpp"
#include "NativeLoad.hpp"
#include "M2NativeInternal.hpp"

#include "engine/events/Event.hpp"
#include "engine/assets/shared/models/m2/M2Format.hpp"
#include "../compat/ModernM2.hpp"
#include "engine/assets/shared/models/m2/Contract.hpp"
#include "game/Binding.hpp"
#include "game/M2.hpp"
#include "offsets/game/M2.hpp"

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace off = wxl::offsets::game::m2;
namespace ev  = wxl::events;
namespace fmt = wxl::structure::m2;

namespace
{
    using namespace wxl::runtime::m2native::detail;

    // ---------------------------------------------------------------- session counters
    std::atomic<uint32_t> g_statNative{ 0 };
    std::atomic<uint32_t> g_statFailed{ 0 };
    std::atomic<uint32_t> g_statTexResolved{ 0 };
    std::atomic<uint32_t> g_statTexUnresolved{ 0 };
    std::atomic<uint32_t> g_statNormalized[kRecordNormalizerCount]{};
    std::atomic<uint32_t> g_statSkipTxac{ 0 };
    std::atomic<uint32_t> g_statSkipLdv1{ 0 };
    std::atomic<uint32_t> g_statSkipAfid{ 0 };
    std::atomic<uint32_t> g_statSkipSkid{ 0 };
    std::atomic<uint32_t> g_statSkipOther{ 0 };
    std::atomic<uint32_t> g_statExtSeqPending{ 0 };
    std::atomic<uint32_t> g_statShadowGateForced{ 0 };

    /**
     * @brief The full native load: demux, in-place deltas, stock walk, TXID injection, the stock
     *        shared-initialize step, stock tail. POD locals only (lives under the SEH guard).
     * @param model  runtime model whose buffer holds the raw MD21 bytes.
     * @param out    receives the outcome for stats / the OnM2NativeLoad event.
     */
    void NativeLoadCore(void* model, Outcome& out)
    {
        auto* mdl = static_cast<off::M2Model*>(model);
        if (mdl->flags & 1u)
        {
            // Stock re-entry contract: already loaded, return success. Re-register (the pre-load event
            // Forgets the pointer defensively on every entry) and skip the stats/event.
            wxl::modern::assets::m2::RegisterNativeLoaded(model);
            out.ok = 2;
            return;
        }

        auto* buf = static_cast<uint8_t*>(mdl->header);
        const uint32_t size = mdl->fileSize;
        if (!buf || size < 8) { out.fail = "no buffer"; return; }

        Scan s;
        if (!ScanContainer(buf, size, s)) { out.fail = "no MD20 body in container"; return; }
        out.skipMask = s.skipMask;

        auto* h = reinterpret_cast<fmt::M2Header*>(buf + s.bodyOff);
        if (h->magic != fmt::kMagicMD20) { out.fail = "body magic"; return; }
        out.version = h->version;
        if (h->version < wxl::modern::assets::m2::kSourceVersionMin ||
            h->version > wxl::modern::assets::m2::kSourceVersionMax)
        {
            out.fail = "inner version outside the supported source window";
            return;
        }

        // A split-skeleton model (SKID / empty bone+sequence arrays) has no Phase-1 home: without the
        // .skel splice it would stand unboned. Refuse the load (a clean miss, like an absent file) rather
        // than filling a broken runtime. Phase 3 lifts this.
        if ((s.skipMask & kSkipSkid) || (!h->bones.count && !h->sequences.count))
        {
            out.fail = "split skeleton (.skel) model -- Phase 3";
            return;
        }

        // Slide the body onto the allocation base (chunk-header bytes ahead of it are dead after the
        // harvest; trailing chunks are beyond the moved range and already harvested). The model keeps its
        // original allocation pointer -- the destructor free and the m2memory arena's exact-pointer
        // bookkeeping stay valid -- and +0x150 now IS the header.
        if (s.bodyOff != 0)
            std::memmove(buf, buf + s.bodyOff, s.bodySize);
        wxl::game::m2::M2Model(model).SetBuffer(buf, s.bodySize);
        h = reinterpret_cast<fmt::M2Header*>(buf);

        // --- in-place field deltas on the raw body ---
        // Two global-flag bits claim that the runtime owns the texture combo arrays, which would have
        // the teardown free interior pointers of this one buffer. We hand it nothing to free.
        h->globalFlags &= ~0x60u;
        FixSequencesRaw(buf, s.bodySize, h, out.extSeqPending);
        FixMaterialsRaw(buf, s.bodySize, h);

        // The stock skin chooser walks a 4-entry threshold table indexed 4 - numSkinProfiles; more
        // profiles than the client ever shipped (LDV1-era LOD counts) would underflow it.
        if (h->numSkinProfiles > 4)
        {
            out.skipMask |= kSkipLdv1;
            h->numSkinProfiles = 1; // profile 0 = full detail; LOD chains need skin ownership first
        }

        // --- record normalization: one record shape for every source era, in place ---
        if (!NormalizeRecords(buf, s.bodySize, h, out.normalized))
        {
            out.fail = "record normalization rejected a record";
            return;
        }

        // --- the offset->pointer walk ---
        if (!WalkHeaderArrays(buf, s.bodySize, h)) { out.fail = "header walk rejected an array"; return; }

        // --- post-fixup injections on the now-pointer-based header ---
        InjectTxidNames(h, s, out);
        ClampRibbonRefs(h);
        ClampCameraRefs(h);

        // Register for the live-engine half BEFORE the stock skin load can schedule its finalize: the
        // finalize-time contract rebuild (packed shaderId decode, textureUnitLookup synth) and the draw
        // fixups key off this registry.
        wxl::modern::assets::m2::RegisterNativeLoaded(model);

        // --- stock shared-initialize: skin select + name-based skin load + texture handles ---
        if (!wxl::game::Native<off::M2_SharedInitializeFn>(off::kSharedInitialize)(model))
        {
            out.fail = "shared initialize failed (skin profile / texture array)";
            return;
        }

        // Shadow-path animate gate. Initialize has just tallied, at +0x198, how many bones carry a
        // specific flag combination. The shadow-pass animate step reads that count: at zero it takes a
        // fast path that never rebuilds the bone palette, so the palette still holds an older frame's
        // view matrix while the shadow renderer uploads the current view -- the two stop cancelling and
        // the shadow rotates with the camera. Stock content's exporter always bakes that flag into
        // practically every bone, so it always takes the full path; a model exported by a newer toolchain
        // can ship every bone flag empty and would not. Forcing the count to 1 puts our models on the
        // exact path stock content already takes. This writes the RUNTIME object, never the model bytes.
        auto* animGate = reinterpret_cast<uint16_t*>(static_cast<uint8_t*>(model) +
                                                     off::kOffSharedAnimGateCount);
        if (*animGate == 0)
        {
            *animGate = 1;
            out.shadowGateForced = 1;
        }
        // Read back so the log can tell "the write never ran" apart from "the write ran and something
        // later reset it" -- the probe sees 0 at the shadow draw, and only this distinguishes the two.
        out.shadowGateAfter = *animGate;

        // --- stock tail: the external-sequence table the .anim streamer indexes, then the loaded flag ---
        uint32_t extCount = 0;
        if (h->sequences.count && h->sequences.offset)
        {
            auto* seqs = reinterpret_cast<fmt::M2Sequence*>(static_cast<uintptr_t>(h->sequences.offset));
            for (uint32_t i = 0; i < h->sequences.count; ++i)
                if (!(seqs[i].flags & 0x20u)) ++extCount;
        }
        void* extArr = wxl::game::Native<off::SMemAllocFn>(off::kSMemAlloc)(
            extCount * 4u, ".\\M2Shared.cpp", 0x2DC, 8);
        auto* bytes = static_cast<uint8_t*>(model);
        *reinterpret_cast<void**>(bytes + off::kOffModelExtSeqArray)     = extArr;
        *reinterpret_cast<uint32_t*>(bytes + off::kOffModelExtSeqCount)  = extCount;
        mdl->flags |= 1u;
        *reinterpret_cast<uint32_t*>(bytes + off::kOffModelExtSeqCursor) = 0;

        out.ok = 1;
    }

    /// SEH shell around the fill: a fault on malformed data becomes a logged failure, never a crash.
    /// No unwindable locals here (C2712).
    void NativeLoadGuarded(void* model, Outcome* out)
    {
        __try
        {
            NativeLoadCore(model, *out);
        }
        __except (EXCEPTION_EXECUTE_HANDLER)
        {
            out->ok   = 0;
            out->fail = "access violation during native fill";
        }
    }
}

namespace wxl_modern_m2
{
    bool InstallM2Native()
    {
        WLOG_INFO("m2native: native MD21 reader active (source versions %u-%u, direct native fill)",
                  wxl::modern::assets::m2::kSourceVersionMin,
                  wxl::modern::assets::m2::kSourceVersionMax);
        return true;
    }
}

namespace wxl::runtime::m2native
{
    Stats GetStats()
    {
        Stats s{};
        s.modelsNative       = g_statNative.load(std::memory_order_relaxed);
        s.modelsFailed       = g_statFailed.load(std::memory_order_relaxed);
        s.texturesResolved   = g_statTexResolved.load(std::memory_order_relaxed);
        s.texturesUnresolved = g_statTexUnresolved.load(std::memory_order_relaxed);
        s.recordsNormalized  = 0;
        for (uint32_t i = 0; i < detail::kRecordNormalizerCount; ++i)
            s.recordsNormalized += g_statNormalized[i].load(std::memory_order_relaxed);
        s.skippedTxac        = g_statSkipTxac.load(std::memory_order_relaxed);
        s.skippedLdv1        = g_statSkipLdv1.load(std::memory_order_relaxed);
        s.skippedAfid        = g_statSkipAfid.load(std::memory_order_relaxed);
        s.skippedSkid        = g_statSkipSkid.load(std::memory_order_relaxed);
        s.skippedOtherChunks = g_statSkipOther.load(std::memory_order_relaxed);
        s.externalSeqPending = g_statExtSeqPending.load(std::memory_order_relaxed);
        s.shadowGateForced   = g_statShadowGateForced.load(std::memory_order_relaxed);
        return s;
    }

    bool Enabled() { return wxl_modern_m2::kEnabled; }

    bool IsModernContainer(void* model)
    {
        if (!model) return false;
        auto* mdl = static_cast<off::M2Model*>(model);
        if (!mdl->header || mdl->fileSize < 8) return false;
        return detail::Rd32(mdl->header) == wxl::structure::m2::kMagicMD21;
    }

    int NativeLoad(void* model)
    {
        detail::Outcome out{};
        NativeLoadGuarded(model, &out);
        if (out.ok == 2) return 1; // already-loaded re-entry: no stats, no event

        const char* stem = wxl::game::m2::M2Model(model).GetPathStem();
        if (!stem) stem = "(no stem)";

        if (!out.ok)
        {
            g_statFailed.fetch_add(1, std::memory_order_relaxed);
            wxl::modern::assets::m2::ForgetNativeLoaded(model); // undo a pre-Initialize registration
            WLOG_WARN("m2native: '%s' native fill FAILED: %s (v=%u skips=0x%X)",
                      stem, out.fail ? out.fail : "unknown", out.version, out.skipMask);
            return 0;
        }

        g_statNative.fetch_add(1, std::memory_order_relaxed);
        g_statTexResolved.fetch_add(out.texResolved, std::memory_order_relaxed);
        g_statTexUnresolved.fetch_add(out.texUnresolved, std::memory_order_relaxed);
        if (out.skipMask & detail::kSkipTxac)      g_statSkipTxac.fetch_add(1, std::memory_order_relaxed);
        if (out.skipMask & detail::kSkipLdv1)      g_statSkipLdv1.fetch_add(1, std::memory_order_relaxed);
        if (out.skipMask & detail::kSkipAfid)      g_statSkipAfid.fetch_add(1, std::memory_order_relaxed);
        if (out.skipMask & detail::kSkipSkid)      g_statSkipSkid.fetch_add(1, std::memory_order_relaxed);
        if (out.skipMask & detail::kSkipOther)     g_statSkipOther.fetch_add(1, std::memory_order_relaxed);
        g_statExtSeqPending.fetch_add(out.extSeqPending, std::memory_order_relaxed);
        g_statShadowGateForced.fetch_add(out.shadowGateForced, std::memory_order_relaxed);

        // What this model needed reshaping, named by the normalizer table so a new record type shows up
        // in the log the moment its entry exists.
        char   norm[96]{};
        size_t at = 0;
        for (uint32_t i = 0; i < detail::kRecordNormalizerCount && at + 1 < sizeof norm; ++i)
        {
            const uint32_t n = out.normalized.records[i];
            if (!n) continue;
            g_statNormalized[i].fetch_add(n, std::memory_order_relaxed);
            const int wrote = std::snprintf(norm + at, sizeof norm - at, " %s=%u",
                                            detail::kRecordNormalizers[i].label, n);
            if (wrote <= 0) break;
            at += static_cast<size_t>(wrote);
        }

        WLOG_INFO("m2native: '%s' read natively (v=%u tex=%u/%u skips=0x%X extseq=%u gate=%u forced=%u"
                  " normalized:%s)",
                  stem, out.version, out.texResolved, out.texResolved + out.texUnresolved,
                  out.skipMask, out.extSeqPending, out.shadowGateAfter, out.shadowGateForced,
                  norm[0] ? norm : " none");
        if (out.extSeqPending)
            WLOG_INFO("m2native: '%s' has %u streamed (.anim) sequence(s) -- bind pose until they arrive",
                      stem, out.extSeqPending);

        ev::M2NativeLoadArgs a{ model, out.version, out.texResolved, out.texUnresolved, out.skipMask };
        wxl_modern_m2::g_api->Emit(uint32_t(ev::Event::OnM2NativeLoad), &a);
        return 1;
    }
}
