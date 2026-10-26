// Native modern-M2 reader: rewrites one source-era camera as a target-shaped camera.
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

// Unlike the other widened records, this one is not the target record with fields appended: the source
// camera moved its field of view from a plain float ahead of the tracks to an animated track after
// them. So the rewrite is a real reshape -- the track body slides back by that float's width, and the
// float is filled from the first key the source track carries. The two forms agree on everything else,
// including the diagonal-radians unit of the value itself, so the reconstructed camera frames exactly
// what the source camera framed.

#include "M2NativeInternal.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace fmt = wxl::structure::m2;

namespace wxl::runtime::m2native::detail
{
    namespace
    {
        // Target record: type, field of view, then the clip planes ahead of the track body.
        constexpr uint32_t kOffType     = 0x00;
        constexpr uint32_t kOffFov      = 0x04;
        constexpr uint32_t kOffFarClip  = 0x08;
        constexpr uint32_t kOffNearClip = 0x0C;
        constexpr uint32_t kOffBody     = 0x10;

        // Source record: no field-of-view float, so the clip planes and the whole track body sit one
        // float earlier, and the field of view follows the body as a track of its own.
        constexpr uint32_t kSrcFarClip  = 0x04;
        constexpr uint32_t kSrcNearClip = 0x08;
        constexpr uint32_t kSrcBody     = 0x0C;
        constexpr uint32_t kSrcFovTrack = 0x60;

        // Position and target spline tracks with their bases, then roll: identical in both forms.
        constexpr uint32_t kBodyBytes = 0x54;

        // An animation track heads its two count+offset pairs with the interpolation fields; the value
        // pair is the second one, and it is a slot list -- one entry per sequence -- of key lists.
        constexpr uint32_t kTrackGlobalLoop = 0x02;
        constexpr uint32_t kTrackValues     = 0x0C;
        constexpr uint32_t kTrackBytes      = 0x14;
        constexpr int16_t  kNoGlobalLoop    = -1;
        constexpr uint32_t kSeqKeysInline   = 0x20;

        // One spline key is its value plus the two tangents around it; the value comes first.
        constexpr uint32_t kSplineKeyBytes = 0x0C;

        // Used when the source track carries no key we can address: a 45 degree diagonal view, the
        // conventional framing for a model that never animates its field of view.
        constexpr float kDefaultFov = 0.7853982f;

        // Both layouts have to add up: the target record is the one the runtime steps, and the source
        // record is exactly the same body with the field-of-view float traded for a trailing track.
        static_assert(offsetof(fmt::M2Camera, fov) == kOffFov, "camera fov");
        static_assert(offsetof(fmt::M2Camera, body) == kOffBody, "camera track body");
        static_assert(sizeof(fmt::M2Camera) == kOffBody + kBodyBytes, "camera record");
        static_assert(kOffBody + kBodyBytes == offsets::game::m2::kCameraStrideClient, "target width");
        static_assert(kSrcBody + kBodyBytes == kSrcFovTrack, "source track body");
        static_assert(kSrcFovTrack + kTrackBytes == offsets::game::m2::kCameraStrideModern,
                      "source width");
        static_assert(sizeof(fmt::M2TrackHeader) == kTrackBytes, "track head");

        /**
         * @brief Reads the first key of the source field-of-view track.
         * @return the key value, or the default when the track is empty or addresses another file.
         */
        float FirstFovKey(const NormalizeCtx& ctx, const uint8_t* track)
        {
            int16_t globalLoop; std::memcpy(&globalLoop, track + kTrackGlobalLoop, 2);

            const uint32_t slots  = Rd32(track + kTrackValues);
            const uint32_t offset = Rd32(track + kTrackValues + 4);
            if (!slots || !offset) return kDefaultFov;
            if (!FitsInBody(ctx.size, offset, slots, sizeof(fmt::M2Array))) return kDefaultFov;

            // Keyed per sequence, the first slot belongs to the first sequence -- and only reaches into
            // this body when that sequence keeps its keys here rather than in a companion file.
            if (globalLoop == kNoGlobalLoop)
            {
                if (!ctx.header->sequences.count || !ctx.header->sequences.offset) return kDefaultFov;
                const auto* seqs = reinterpret_cast<const fmt::M2Sequence*>(
                    ctx.body + ctx.header->sequences.offset);
                if (!(seqs[0].flags & kSeqKeysInline)) return kDefaultFov;
            }

            const uint8_t* slot = ctx.body + offset;
            const uint32_t keyCount  = Rd32(slot);
            const uint32_t keyOffset = Rd32(slot + 4);
            if (!keyCount || !keyOffset) return kDefaultFov;
            if (!FitsInBody(ctx.size, keyOffset, keyCount, kSplineKeyBytes)) return kDefaultFov;

            float fov; std::memcpy(&fov, ctx.body + keyOffset, 4);
            return fov;
        }
    }

    /**
     * @brief Writes one target-shaped camera at dst from the source-shaped record at src.
     * @param ctx  body, its size, and the header whose sequences say which keys live in this body.
     * @param src  source-shaped record.
     * @param dst  where the target-shaped record goes (never ahead of src).
     * @return true; a source track this cannot address yields the default view rather than a failure.
     */
    bool NormalizeCameraRecord(const NormalizeCtx& ctx, const uint8_t* src, uint8_t* dst)
    {
        // Read every scalar out before anything moves: at the first record dst and src are the same
        // address, so the body slide overwrites the near clip plane where it lay in the source form.
        const uint32_t type     = Rd32(src + kOffType);
        const uint32_t farClip  = Rd32(src + kSrcFarClip);
        const uint32_t nearClip = Rd32(src + kSrcNearClip);
        const float    fov      = FirstFovKey(ctx, src + kSrcFovTrack);

        std::memmove(dst + kOffBody, src + kSrcBody, kBodyBytes);
        Wr32(dst + kOffType, type);
        std::memcpy(dst + kOffFov, &fov, 4);
        Wr32(dst + kOffFarClip, farClip);
        Wr32(dst + kOffNearClip, nearClip);
        return true;
    }
}
