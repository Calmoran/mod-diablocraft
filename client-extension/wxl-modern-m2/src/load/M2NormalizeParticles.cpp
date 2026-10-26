// Native modern-M2 reader: rewrites one source-era particle emitter as a target-shaped emitter.
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

// The source emitter keeps every field of the target emitter at its own offset and appends the
// multi-texture scroll parameters past the end, so the record body copies straight down. What does NOT
// carry over is a handful of ENCODINGS the target emitter reads differently, and each is decoded here
// once at load rather than at every read: a packed multi-layer texture slot, and a gravity track whose
// keys are packed direction+magnitude instead of a scalar.
//
// The blend mode is deliberately NOT touched. A mode the runtime's own map has no arm for is resolved
// against the real blend state it names, once the emitter exists to carry it -- rewriting the record
// to the nearest mode the map already knows would throw the distinction away here, permanently.
//
// Flipbook cell keys are deliberately NOT touched. A cell ramp runs from 0 to rows*columns across the
// particle's life -- the end key is one past the last cell on purpose, so the sweep covers every cell
// evenly -- and the runtime decodes a cell by mask and shift, which handles that end key on its own.
// Folding the end key back into range flattens the ramp and freezes the flipbook on its first cell.

#include "M2NativeInternal.hpp"

#include <cmath>
#include <cstdint>
#include <cstring>

namespace off = wxl::offsets::game::m2;
namespace fmt = wxl::structure::m2;

namespace wxl::runtime::m2native::detail
{
    namespace
    {
        // Fields of one emitter record.
        constexpr uint32_t kOffFlags        = 0x004;
        constexpr uint32_t kOffTextureId    = 0x016;
        constexpr uint32_t kOffGravityTrack = 0x084;

        // An animation track heads its two count+offset pairs with the interpolation fields; the value
        // pair is the second one. Both pairs are one slot list per sequence, values inside -- unless
        // the track is keyed to a global loop, in which case the slots are the loop's own.
        constexpr uint32_t kTrackGlobalLoop = 0x02;
        constexpr uint32_t kTrackValues     = 0x0C;
        constexpr int16_t  kNoGlobalLoop    = -1;

        // Only the first of the three packed layer ids has a target home; the id also has to land
        // inside the model's texture table or it selects nothing.
        constexpr uint16_t kPackedTextureIdMask = 0x1F;

        // Gravity keys packed as {int8 x, int8 y, int16 magnitude} instead of a downward scalar.
        constexpr uint32_t kFlagCompressedGravity = 0x800000;
        constexpr float    kGravityMagnitudeUnit  = 0.04238648f;
        constexpr float    kPackedDirectionUnit   = 1.0f / 128.0f;

        // A sequence keeps its keys in this model only when this bit is set; otherwise they arrive with
        // a companion file and the offsets in the record do not address this body at all.
        constexpr uint32_t kSeqKeysInline = 0x20;

        // Every field above lives inside the target record; the source record is this one with the
        // multi-texture scroll parameters appended.
        static_assert(kOffGravityTrack + 0x14 <= off::kParticleStrideClient, "emitter fields");
        static_assert(off::kParticleStrideClient < off::kParticleStrideModern, "emitter widths");

        /**
         * @brief Expands packed gravity keys into the plain downward scalar the target reads, and clears
         *        the flag that said they were packed.
         * @return false when an inline sequence's key list addresses outside the body.
         */
        bool ExpandGravityKeys(const NormalizeCtx& ctx, uint8_t* rec, uint32_t flags)
        {
            int16_t globalLoop;
            std::memcpy(&globalLoop, rec + kOffGravityTrack + kTrackGlobalLoop, 2);

            const uint32_t slots  = Rd32(rec + kOffGravityTrack + kTrackValues);
            const uint32_t offset = Rd32(rec + kOffGravityTrack + kTrackValues + 4);
            if (slots && offset)
            {
                if (!FitsInBody(ctx.size, offset, slots, sizeof(fmt::M2Array))) return false;
                // Slots of a global-loop track all live in this body; slots keyed per sequence only do
                // when that sequence keeps its keys here.
                const auto* seqs = (globalLoop == kNoGlobalLoop && ctx.header->sequences.count &&
                                    ctx.header->sequences.offset)
                    ? reinterpret_cast<const fmt::M2Sequence*>(ctx.body + ctx.header->sequences.offset)
                    : nullptr;
                for (uint32_t s = 0; s < slots; ++s)
                {
                    // Keys that stream in with a companion file are not addressed against this body;
                    // leaving them packed is correct, that file's arrival brings its own.
                    if (seqs && s < ctx.header->sequences.count &&
                        !(seqs[s].flags & kSeqKeysInline)) continue;

                    const uint8_t* slot = ctx.body + offset + s * sizeof(fmt::M2Array);
                    const uint32_t keyCount  = Rd32(slot);
                    const uint32_t keyOffset = Rd32(slot + 4);
                    if (!keyCount || !keyOffset) continue;
                    if (!FitsInBody(ctx.size, keyOffset, keyCount, 4)) return false;

                    uint8_t* keys = ctx.body + keyOffset;
                    for (uint32_t k = 0; k < keyCount; ++k)
                    {
                        uint8_t* key = keys + k * 4;
                        const float dx = static_cast<int8_t>(key[0]) * kPackedDirectionUnit;
                        const float dy = static_cast<int8_t>(key[1]) * kPackedDirectionUnit;
                        int16_t packedMag; std::memcpy(&packedMag, key + 2, 2);

                        const float planar = dx * dx + dy * dy;
                        float z   = std::sqrt(planar < 1.0f ? 1.0f - planar : 0.0f);
                        float mag = packedMag * kGravityMagnitudeUnit;
                        if (mag < 0.0f) { z = -z; mag = -mag; }
                        const float scalar = -(z * mag);
                        std::memcpy(key, &scalar, 4);
                    }
                }
            }
            Wr32(rec + kOffFlags, flags & ~kFlagCompressedGravity);
            return true;
        }
    }

    /**
     * @brief Writes one target-shaped particle emitter at dst from the source-shaped record at src.
     * @param ctx  body, its size, and the header bounding the record's index fields.
     * @param src  source-shaped record.
     * @param dst  where the target-shaped record goes (never ahead of src).
     * @return false when the record reaches outside the body.
     */
    bool NormalizeParticleRecord(const NormalizeCtx& ctx, const uint8_t* src, uint8_t* dst)
    {
        // The trailing multi-texture scroll parameters stop here: no part of the pipeline downstream
        // reads them, and keeping them would mean keeping a second record width alive everywhere.
        std::memmove(dst, src, off::kParticleStrideClient);

        const uint32_t flags = Rd32(dst + kOffFlags);

        // A multi-layer emitter packs three layer ids into the texture slot. Only the first layer has a
        // home in a single-texture emitter, and an id past the model's table would select nothing.
        uint16_t texId = Rd16(dst + kOffTextureId);
        if (flags & off::kParticleFlagMultiTex) texId &= kPackedTextureIdMask;
        if (ctx.header->textures.count && texId >= ctx.header->textures.count) texId = 0;
        Wr16(dst + kOffTextureId, texId);

        if ((flags & kFlagCompressedGravity) && !ExpandGravityKeys(ctx, dst, flags)) return false;
        return true;
    }
}
