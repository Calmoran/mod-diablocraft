// Native modern-M2 reader: in-place field deltas (sequences/materials) and post-fixup name injections.
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

// The in-place deltas run on the RAW body (array offsets still body-relative), before the pointer walk;
// the injections run after it (offsets are raw pointers). Each is a field the source model states
// differently from the target -- a value rewritten, never a value dropped.

#include "../ExtensionApi.hpp"
#include "M2NativeInternal.hpp"

#include <cstdint>
#include <cstring>

namespace fmt = wxl::structure::m2;

namespace wxl::runtime::m2native::detail
{
    namespace
    {
        /// Finds the index of the first sequence whose id equals anim (Animations.cpp semantics).
        int16_t SequenceIndexById(const fmt::M2Sequence* seqs, uint32_t count, uint16_t anim)
        {
            for (uint32_t i = 0; i < count; ++i)
                if (seqs[i].id == anim) return static_cast<int16_t>(i);
            return -1;
        }

        /// Points lookup[newId] at newPos if it still holds oldPos, else rewrites the first entry holding
        /// oldPos (Animations.cpp semantics).
        void PatchSequenceLookup(int16_t* lookup, uint32_t lookupCount, int16_t oldPos, uint16_t newId,
                                 int16_t newPos)
        {
            if (!lookup) return;
            if (newId < lookupCount && lookup[newId] == oldPos) { lookup[newId] = newPos; return; }
            for (uint32_t i = 0; i < lookupCount; ++i)
                if (lookup[i] == oldPos) { lookup[i] = newPos; break; }
        }
    }

    /**
     * @brief Sequence deltas in place: masks the split u16 in|out blendTime to the client's single u32
     *        (read whole it is a huge blend so transitions never complete) and remaps the curated set of
     *        source ids above the client's id table onto client ids, patching the lookup. Counts the
     *        sequences whose data streams from a .anim file (flags bit 0x20 clear -- Phase 2) into
     *        extSeqPending.
     */
    void FixSequencesRaw(uint8_t* base, uint32_t size, fmt::M2Header* h, uint32_t& extSeqPending)
    {
        constexpr uint16_t kClientMaxAnimId = 505;
        if (!h->sequences.count || !h->sequences.offset) return;
        if (h->sequences.offset > size ||
            h->sequences.count * sizeof(fmt::M2Sequence) > size - h->sequences.offset)
            return; // walk will reject it
        auto* seqs = reinterpret_cast<fmt::M2Sequence*>(base + h->sequences.offset);

        int16_t* lookup = nullptr;
        uint32_t lookupCount = 0;
        if (h->sequenceLookup.count && h->sequenceLookup.offset &&
            h->sequenceLookup.offset <= size &&
            h->sequenceLookup.count * 2 <= size - h->sequenceLookup.offset)
        {
            lookup      = reinterpret_cast<int16_t*>(base + h->sequenceLookup.offset);
            lookupCount = h->sequenceLookup.count;
        }

        for (uint32_t i = 0; i < h->sequences.count; ++i)
        {
            const uint16_t id = seqs[i].id;
            if (id > kClientMaxAnimId)
            {
                uint16_t anim = id;
                switch (id)
                {
                    case 564: anim = 37;  break;
                    case 548: anim = 41;  break;
                    case 556: anim = 42;  break;
                    case 552: anim = 43;  break;
                    case 554: anim = 44;  break;
                    case 562: anim = 45;  break;
                    case 572: anim = 39;  break;
                    case 574: anim = 187; break;
                }
                if (anim != id)
                {
                    PatchSequenceLookup(lookup, lookupCount,
                                        SequenceIndexById(seqs, h->sequences.count, anim), anim,
                                        static_cast<int16_t>(i));
                    seqs[i].id = anim;
                }
            }
            seqs[i].blendTime &= 0xFFFFu;
            if (!(seqs[i].flags & 0x20u)) ++extSeqPending;
        }
    }

    /**
     * @brief Material deltas in place: a blend mode above the client's 7-entry blend table is clamped to
     *        Add (4, flags forced |0x5) and flags are masked to the low 5 bits -- the same FixRenderFlags
     *        contract the skin-finalize half re-applies idempotently.
     */
    void FixMaterialsRaw(uint8_t* base, uint32_t size, fmt::M2Header* h)
    {
        if (!h->materials.count || !h->materials.offset) return;
        if (h->materials.offset > size || h->materials.count * 4 > size - h->materials.offset)
            return;
        auto* mats = reinterpret_cast<uint16_t*>(base + h->materials.offset);
        for (uint32_t i = 0; i < h->materials.count; ++i)
        {
            uint16_t& flag  = mats[i * 2 + 0];
            uint16_t& blend = mats[i * 2 + 1];
            if (blend > 6) { blend = 4; flag |= 0x5; }
            flag &= 0x1F;
        }
    }

    /**
     * @brief Points each hardcoded (type 0) texture with no inline name at its TXID-resolved client path.
     *        Post-fixup, M2Texture.filename.offset is a raw pointer, so it can aim directly at the
     *        resolver's process-lifetime cached string -- no buffer growth. The stock shared-initialize
     *        step then creates a texture for exactly that path; an unresolved id keeps count 0 and falls
     *        back to the stock solid-white placeholder.
     */
    void InjectTxidNames(fmt::M2Header* h, const Scan& s, Outcome& out)
    {
        if (!h->textures.count || !h->textures.offset) return;
        auto* tex = reinterpret_cast<fmt::M2Texture*>(static_cast<uintptr_t>(h->textures.offset));
        for (uint32_t i = 0; i < h->textures.count; ++i)
        {
            if (tex[i].type != fmt::kTexTypeHardcoded) continue;   // dynamic slots stay empty
            if (tex[i].filename.count >= 2 && tex[i].filename.offset) continue; // inline name kept
            const uint32_t fdid = i < s.txidCount ? s.txid[i] : 0;
            if (!fdid) continue;
            const char* path = wxl_modern_m2::ResolveTexture(fdid);
            if (!path)
            {
                ++out.texUnresolved;
                WLOG_WARN("m2native: TXID %u unresolved (texture %u) -- solid white fallback", fdid, i);
                continue;
            }
            tex[i].filename.offset = static_cast<uint32_t>(reinterpret_cast<uintptr_t>(path));
            tex[i].filename.count  = static_cast<uint32_t>(std::strlen(path)) + 1u;
            ++out.texResolved;
        }
    }

    /// Drops each camera reference that points past the camera array. The source exporter already emits
    /// the "no camera" sentinel for unused slots, so a consumer reads a dropped entry the same way.
    void ClampCameraRefs(fmt::M2Header* h)
    {
        if (!h->cameraLookup.count || !h->cameraLookup.offset) return;
        auto* lookup = reinterpret_cast<int16_t*>(static_cast<uintptr_t>(h->cameraLookup.offset));
        const auto limit = static_cast<int32_t>(h->cameras.count);
        for (uint32_t i = 0; i < h->cameraLookup.count; ++i)
            if (lookup[i] >= limit) lookup[i] = -1;
    }

    /// Clamps each ribbon's texture/material reference values into the header tables: the source
    /// exporter can emit indices past what the model itself declares.
    void ClampRibbonRefs(fmt::M2Header* h)
    {
        if (!h->ribbonEmitters.count || !h->ribbonEmitters.offset) return;
        auto* rib = reinterpret_cast<fmt::M2Ribbon*>(static_cast<uintptr_t>(h->ribbonEmitters.offset));
        for (uint32_t i = 0; i < h->ribbonEmitters.count; ++i)
        {
            auto clamp = [](const fmt::M2Array& a, uint32_t limit) {
                if (!a.count || !a.offset || !limit) return;
                auto* v = reinterpret_cast<uint16_t*>(static_cast<uintptr_t>(a.offset));
                for (uint32_t n = 0; n < a.count; ++n)
                    if (v[n] >= limit) v[n] = static_cast<uint16_t>(limit - 1);
            };
            clamp(rib[i].textureIndices, h->textures.count);
            clamp(rib[i].materialIndices, h->materials.count);
        }
    }
}
