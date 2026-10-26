// Native modern-M2 reader: rewrites source-era-wide records to the one shape the runtime steps.
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

// Runs on the raw body, before the offset->pointer walk: array offsets are still body-relative, so a
// record can still be moved. Every widened record SHRINKS, which is what makes this in place and
// allocation-free -- the buffer keeps its identity and its size, only the used span of each array
// gets shorter, and the header count is unchanged so nothing downstream needs telling.
//
// After this pass the body carries exactly one record shape, which is why the walk and every consumer
// past it can use a single stride whatever era the model came from.

#include "M2NativeInternal.hpp"

#include <cstdint>

namespace fmt = wxl::structure::m2;

namespace wxl::runtime::m2native::detail
{
    /**
     * @brief Rewrites every source-era-wide record listed in the normalizer table to the target shape.
     * @param base    body bytes; nested arrays inside a record are offsets into them.
     * @param size    body byte size, the bound every record and nested array is checked against.
     * @param h       header sitting at the body base.
     * @param report  receives the record count rewritten per table entry.
     * @return false when a record, or an array nested in one, does not fit the body -- the caller must
     *         treat that as a failed load, never as a partially normalized array.
     */
    bool NormalizeRecords(uint8_t* base, uint32_t size, fmt::M2Header* h, NormalizeReport& report)
    {
        const NormalizeCtx ctx{ base, size, h };
        for (uint32_t e = 0; e < kRecordNormalizerCount; ++e)
        {
            const RecordNormalizer& entry = kRecordNormalizers[e];
            report.records[e] = 0;
            if (h->version < entry.sourceMinVersion) continue; // already the target shape

            // A record that GREW would need a bigger home than the array it sits in; refusing here keeps
            // "normalization is always in place" a property of the code, not of the current table.
            if (entry.targetStride > entry.sourceStride) return false;

            auto& array = *reinterpret_cast<fmt::M2Array*>(h->base() + entry.at);
            if (!array.count || !array.offset) continue;
            if (!FitsInBody(size, array.offset, array.count, entry.sourceStride)) return false;

            const uint8_t* src = base + array.offset;
            uint8_t*       dst = base + array.offset;
            for (uint32_t i = 0; i < array.count; ++i)
            {
                if (!entry.rewrite(ctx, src, dst)) return false;
                src += entry.sourceStride;
                dst += entry.targetStride;
            }
            report.records[e] = array.count;
        }
        return true;
    }
}
