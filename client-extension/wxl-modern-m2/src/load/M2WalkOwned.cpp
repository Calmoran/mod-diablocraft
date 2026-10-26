// Native modern-M2 reader: our own offset->pointer walk over the model body.
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

// The body is parsed in place: every count+offset pair in it is rewritten into a real pointer, so
// after the walk the runtime can chase the model without ever consulting the file layout again.
//
// Two invariants make this safe and reversible:
//  - an array only becomes a pointer once count * stride is proven to fit inside the body, so a
//    truncated or hostile file fails the walk instead of leaving wild pointers behind;
//  - a track slot belonging to a sequence whose keyframes live in a companion file is left
//    file-relative, because it is that file's arrival -- not this walk -- that gives it a base.

#include "M2NativeInternal.hpp"
#include "M2WalkLayout.hpp"

#include <cstdint>

namespace fmt = wxl::structure::m2;

namespace wxl::runtime::m2native::detail
{
    namespace
    {
        constexpr uint32_t kSeqKeysInline    = 0x20; ///< keyframes live in this file, not a companion one
        constexpr uint32_t kSeqPlaysOnce     = 0x01; ///< runs to its end instead of looping
        constexpr uint32_t kSeqPlayOnceReady = 0x80; ///< load-time twin of kSeqPlaysOnce
        constexpr int16_t  kNoGlobalLoop     = -1;   ///< track is keyed per sequence, not to a global loop

        /// Sequences that must loop whatever their record asks for -- the movement/idle set the pose
        /// system expects to be able to hold indefinitely.
        constexpr uint16_t kAlwaysLoopingIds[] = {
            0x00, 0x04, 0x05, 0x0D, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x45, 0x77, 0x78, 0x8F, 0xDF,
        };

        bool AlwaysLoops(uint16_t id)
        {
            for (uint16_t looping : kAlwaysLoopingIds)
                if (looping == id) return true;
            return false;
        }

        /// Turns one count+offset pair into a pointer, rejecting anything that does not fit the body.
        /// An empty array resolves to null so a consumer cannot walk stale bytes.
        bool Resolve(uint8_t* base, uint32_t size, fmt::M2Array& array, uint32_t stride)
        {
            const uint32_t offset = array.offset;
            if (!FitsInBody(size, offset, array.count, stride)) return false;
            array.offset = array.count
                ? static_cast<uint32_t>(reinterpret_cast<uintptr_t>(base) + offset) : 0;
            return true;
        }

        /// An array of arrays: the outer slot list plus every inner list, each bounds-checked.
        bool ResolveNested(uint8_t* base, uint32_t size, fmt::M2Array& outer, uint32_t innerStride)
        {
            if (!Resolve(base, size, outer, sizeof(fmt::M2Array))) return false;
            if (!outer.count) return true;
            auto* slot = reinterpret_cast<fmt::M2Array*>(static_cast<uintptr_t>(outer.offset));
            for (uint32_t i = 0; i < outer.count; ++i)
                if (!Resolve(base, size, slot[i], innerStride)) return false;
            return true;
        }

        /// A per-sequence slot list: one slot per sequence, and only the slots whose sequence keeps its
        /// keyframes in this file get a base now. The rest stay file-relative for their own arrival.
        void ResolvePerSequence(uint8_t* base, fmt::M2Array& outer, uint32_t slots,
                                const fmt::M2Sequence* sequences)
        {
            outer.offset = outer.count
                ? static_cast<uint32_t>(reinterpret_cast<uintptr_t>(base) + outer.offset) : 0;
            if (!slots) return;
            auto* slot = reinterpret_cast<fmt::M2Array*>(static_cast<uintptr_t>(outer.offset));
            for (uint32_t i = 0; i < slots; ++i)
            {
                if (!(sequences[i].flags & kSeqKeysInline)) continue;
                slot[i].offset = slot[i].count
                    ? static_cast<uint32_t>(reinterpret_cast<uintptr_t>(base) + slot[i].offset) : 0;
            }
        }

        /// One animation track. Both halves of a per-sequence track are indexed by the SAME slot count
        /// (the timestamp list's) -- the two lists describe one key set, so they are walked in lockstep.
        bool ResolveTrack(uint8_t* base, uint32_t size, uint8_t* at, uint32_t valueStride,
                          const fmt::M2Sequence* sequences)
        {
            auto* track = reinterpret_cast<fmt::M2TrackHeader*>(at);
            if (track->globalSequence == kNoGlobalLoop)
            {
                const uint32_t slots = track->timestamps.count;
                ResolvePerSequence(base, track->timestamps, slots, sequences);
                if (valueStride) ResolvePerSequence(base, track->values, slots, sequences);
                return true;
            }
            if (!ResolveNested(base, size, track->timestamps, sizeof(uint32_t))) return false;
            return !valueStride || ResolveNested(base, size, track->values, valueStride);
        }

        /// Applies one header entry's record map to every record it holds.
        bool ResolveRecords(uint8_t* base, uint32_t size, const fmt::M2Array& array, uint32_t stride,
                            const HeaderArray& entry, const fmt::M2Sequence* sequences)
        {
            if (!array.count) return true;
            auto* record = reinterpret_cast<uint8_t*>(static_cast<uintptr_t>(array.offset));
            for (uint32_t i = 0; i < array.count; ++i, record += stride)
                for (uint32_t s = 0; s < entry.stepCount; ++s)
                {
                    const RecordStep& step = entry.steps[s];
                    uint8_t* at = record + step.at;
                    if (step.kind == kStepArray)
                    {
                        if (!Resolve(base, size, *reinterpret_cast<fmt::M2Array*>(at), step.stride))
                            return false;
                    }
                    else if (!ResolveTrack(base, size, at, step.stride, sequences))
                    {
                        return false;
                    }
                }
            return true;
        }

        /// Sequence flag pass: a play-once record raises its load-time twin bit, and the ids that must
        /// stay loopable have the play-once bit taken back off.
        void ApplySequenceFlags(const fmt::M2Array& array)
        {
            if (!array.count) return;
            auto* sequences = reinterpret_cast<fmt::M2Sequence*>(static_cast<uintptr_t>(array.offset));
            for (uint32_t i = 0; i < array.count; ++i)
            {
                uint32_t flags = sequences[i].flags;
                if (flags & kSeqPlaysOnce) flags |= kSeqPlayOnceReady;
                if (AlwaysLoops(sequences[i].id)) flags &= ~kSeqPlaysOnce;
                sequences[i].flags = flags;
            }
        }
    }

    /**
     * @brief Resolves every array in the header, and every array nested in the records they reach.
     * @param base  body bytes; the pointers written point back into them.
     * @param size  body byte size, the bound every array is checked against.
     * @param h     header sitting at the body base.
     * @return true when every array fit the body; false leaves the walk abandoned mid-way, which is
     *         why the caller must treat a false as a failed load rather than a partial model.
     */
    bool WalkHeaderArrays(uint8_t* base, uint32_t size, fmt::M2Header* h)
    {
        for (const HeaderArray& entry : kHeaderArrays)
        {
            if ((entry.traits & kArrayCombinerGated) &&
                !(h->globalFlags & fmt::kFlagUseTextureCombinerCombos))
                continue;

            auto& array = *reinterpret_cast<fmt::M2Array*>(h->base() + entry.at);
            if (!Resolve(base, size, array, entry.stride)) return false;
            if (entry.traits & kArraySequenceFlags) ApplySequenceFlags(array);
            if (!entry.steps) continue;

            // Sequences resolve first in the table, so every later record can read them to decide
            // which of its track slots this file actually carries.
            const auto* sequences =
                reinterpret_cast<const fmt::M2Sequence*>(static_cast<uintptr_t>(h->sequences.offset));
            if (!ResolveRecords(base, size, array, entry.stride, entry, sequences)) return false;
        }
        return true;
    }
}
