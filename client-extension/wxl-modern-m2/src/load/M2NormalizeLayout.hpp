// Native modern-M2 reader: the record map of every array whose record width follows the source era.
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

#pragma once

// Record widths and record SHAPES are the only things that move between source eras, and both are
// expressed here as data: one table entry per header array whose record is wider in some era, giving
// the two widths, the era the wider form starts at, and the rewrite that turns one source record into
// one target record. Everything downstream -- the pointer walk, and every consumer past it -- then
// works on a single record shape whatever the model came from.
//
// Adding a record type is one entry plus one rewrite function; nothing else in the reader changes.

#include "engine/assets/shared/models/m2/M2Format.hpp"
#include "offsets/game/M2.hpp"

#include <cstddef>
#include <cstdint>

namespace wxl::runtime::m2native::detail
{
    /// What a rewrite may reach besides the record itself: the body it lives in (nested arrays are
    /// still body-relative at this point) and the header that bounds its index fields.
    struct NormalizeCtx
    {
        uint8_t*                  body;
        uint32_t                  size;
        structure::m2::M2Header*  header;
    };

    /**
     * @brief Writes one target-shaped record at dst from one source-shaped record at src.
     *
     * dst never runs ahead of src (every widened record shrinks), so the driver's front-to-back walk
     * cannot overwrite a record before it has been read. A rewrite returns false when the record
     * points outside the body, which fails the whole load rather than leaving a wild pointer.
     */
    using NormalizeRecordFn = bool (*)(const NormalizeCtx& ctx, const uint8_t* src, uint8_t* dst);

    bool NormalizeParticleRecord(const NormalizeCtx& ctx, const uint8_t* src, uint8_t* dst);
    bool NormalizeCameraRecord(const NormalizeCtx& ctx, const uint8_t* src, uint8_t* dst);

    /** @brief One header array whose record width follows the source era. */
    struct RecordNormalizer
    {
        uint32_t          at;               ///< byte offset of the count+offset pair inside the header
        uint32_t          sourceStride;     ///< record width from sourceMinVersion up
        uint32_t          targetStride;     ///< the one width every consumer past the walk steps
        uint32_t          sourceMinVersion; ///< below it the record already has the target shape
        NormalizeRecordFn rewrite;
        const char*       label;            ///< names this record type in the load log
    };

    inline constexpr RecordNormalizer kRecordNormalizers[] = {
        { offsetof(structure::m2::M2Header, particleEmitters),
          offsets::game::m2::kParticleStrideModern, offsets::game::m2::kParticleStrideClient,
          offsets::game::m2::kParticleModernMinVer, &NormalizeParticleRecord, "particles" },
        { offsetof(structure::m2::M2Header, cameras),
          offsets::game::m2::kCameraStrideModern, offsets::game::m2::kCameraStrideClient,
          offsets::game::m2::kCameraModernMinVer, &NormalizeCameraRecord, "cameras" },
    };

    inline constexpr uint32_t kRecordNormalizerCount =
        static_cast<uint32_t>(sizeof(kRecordNormalizers) / sizeof(kRecordNormalizers[0]));

    /// Records rewritten per table entry, in table order -- what the per-model log reports.
    struct NormalizeReport
    {
        uint32_t records[kRecordNormalizerCount];
    };
}
