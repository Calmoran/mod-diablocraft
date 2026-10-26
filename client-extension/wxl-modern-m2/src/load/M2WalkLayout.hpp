// Native modern-M2 reader: the record map the owned header walk follows.
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

// The walk is a table, not thirty hand-written passes: every header array is described once by where
// its count+offset pair sits, how wide one record is, and which nested arrays / animation tracks live
// inside that record. The tables are ordered exactly as the walk must run -- sequences resolve before
// anything that reads them, and each entry's records are only reachable once its own array resolved.
//
// One width per record type is enough here because record normalization (M2NormalizeLayout) has
// already brought every source era onto the same record shape by the time the walk runs.

#include "engine/assets/shared/models/m2/M2Format.hpp"

#include <cstddef>
#include <cstdint>

namespace wxl::runtime::m2native::detail
{
    /// What a record step fixes: a plain nested count+offset pair, or an animation track head.
    enum : uint8_t
    {
        kStepArray = 0,
        kStepTrack = 1,
    };

    /// Traits that change how a header entry is walked.
    enum : uint8_t
    {
        kArrayPlain         = 0x00,
        kArraySequenceFlags = 0x01, ///< sequence records also take the looping-id flag pass
        kArrayCombinerGated = 0x02, ///< present only when the header advertises the combiner table
    };

    /**
     * @brief One fixup inside a record.
     *
     * For kStepArray, stride is the element width of the nested array. For kStepTrack it is the width
     * of one animated value; 0 means the track carries timestamps only and has no value array.
     */
    struct RecordStep
    {
        uint32_t at;
        uint32_t stride;
        uint8_t  kind;
    };

    /** @brief One header array: where it is, how wide its records are, and what to fix inside each. */
    struct HeaderArray
    {
        uint32_t          at;        ///< byte offset of the count+offset pair inside the header
        uint32_t          stride;    ///< record width
        uint8_t           traits;
        const RecordStep* steps;     ///< null when the record has nothing nested
        uint32_t          stepCount;
    };

    template <size_t N>
    constexpr uint32_t StepCount(const RecordStep (&)[N]) { return static_cast<uint32_t>(N); }

    // --- per-record maps -------------------------------------------------------------------------
    // Bone: translation, rotation, scale.
    inline constexpr RecordStep kBoneSteps[] = {
        { 0x10, 0x0C, kStepTrack },
        { 0x24, 0x08, kStepTrack },
        { 0x38, 0x0C, kStepTrack },
    };

    // Vertex colour: colour then alpha.
    inline constexpr RecordStep kColorSteps[] = {
        { 0x00, 0x0C, kStepTrack },
        { 0x14, 0x02, kStepTrack },
    };

    // Texture weight: one alpha track.
    inline constexpr RecordStep kTextureWeightSteps[] = {
        { 0x00, 0x02, kStepTrack },
    };

    // Texture transform: translation, rotation (quaternion), scaling.
    inline constexpr RecordStep kTextureTransformSteps[] = {
        { 0x00, 0x0C, kStepTrack },
        { 0x14, 0x10, kStepTrack },
        { 0x28, 0x0C, kStepTrack },
    };

    // Texture: the inline filename bytes.
    inline constexpr RecordStep kTextureSteps[] = {
        { 0x08, 0x01, kStepArray },
    };

    // Attachment: the animate-attached track.
    inline constexpr RecordStep kAttachmentSteps[] = {
        { 0x14, 0x01, kStepTrack },
    };

    // Event: a timestamps-only track -- the event IS the key, it carries no value.
    inline constexpr RecordStep kEventSteps[] = {
        { 0x18, 0x00, kStepTrack },
    };

    // Light: ambient colour/intensity, diffuse colour/intensity, attenuation start/end, visibility.
    inline constexpr RecordStep kLightSteps[] = {
        { 0x10, 0x0C, kStepTrack },
        { 0x24, 0x04, kStepTrack },
        { 0x38, 0x0C, kStepTrack },
        { 0x4C, 0x04, kStepTrack },
        { 0x60, 0x04, kStepTrack },
        { 0x74, 0x04, kStepTrack },
        { 0x88, 0x01, kStepTrack },
    };

    // Camera: position and target spline tracks, then roll.
    inline constexpr RecordStep kCameraSteps[] = {
        { 0x10, 0x24, kStepTrack },
        { 0x30, 0x24, kStepTrack },
        { 0x50, 0x0C, kStepTrack },
    };

    // Ribbon: texture/material reference tables, then colour, alpha, height above/below, texture slot,
    // visibility.
    inline constexpr RecordStep kRibbonSteps[] = {
        { 0x14, 0x02, kStepArray },
        { 0x1C, 0x02, kStepArray },
        { 0x24, 0x0C, kStepTrack },
        { 0x38, 0x02, kStepTrack },
        { 0x4C, 0x04, kStepTrack },
        { 0x60, 0x04, kStepTrack },
        { 0x84, 0x02, kStepTrack },
        { 0x98, 0x01, kStepTrack },
    };

    // Particle emitter: the two spawn-model name strings, the emission tracks, the colour/alpha/scale
    // and flipbook cell blocks, then the spline points and the per-sequence enable track.
    inline constexpr RecordStep kParticleSteps[] = {
        { 0x018, 0x01, kStepArray },
        { 0x020, 0x01, kStepArray },
        { 0x034, 0x04, kStepTrack },
        { 0x048, 0x04, kStepTrack },
        { 0x05C, 0x04, kStepTrack },
        { 0x070, 0x04, kStepTrack },
        { 0x084, 0x04, kStepTrack },
        { 0x098, 0x04, kStepTrack },
        { 0x0B0, 0x04, kStepTrack },
        { 0x0C8, 0x04, kStepTrack },
        { 0x0DC, 0x04, kStepTrack },
        { 0x0F0, 0x04, kStepTrack },
        { 0x104, 0x02, kStepArray },
        { 0x10C, 0x0C, kStepArray },
        { 0x114, 0x02, kStepArray },
        { 0x11C, 0x02, kStepArray },
        { 0x124, 0x02, kStepArray },
        { 0x12C, 0x08, kStepArray },
        { 0x13C, 0x02, kStepArray },
        { 0x144, 0x02, kStepArray },
        { 0x14C, 0x02, kStepArray },
        { 0x154, 0x02, kStepArray },
        { 0x1C0, 0x0C, kStepArray },
        { 0x1C8, 0x01, kStepTrack },
    };

    // --- the header walk order -------------------------------------------------------------------
    // Sequences come early because every per-sequence track slot is keyed off them, and the lookup
    // tables follow the array they index so a rejected array stops the walk before its readers run.
    inline constexpr HeaderArray kHeaderArrays[] = {
        { offsetof(structure::m2::M2Header, name),                  0x01, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, globalLoops),           0x04, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, sequences),             0x40, kArraySequenceFlags, nullptr, 0 },
        { offsetof(structure::m2::M2Header, sequenceLookup),        0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, bones),                 0x58, kArrayPlain,         kBoneSteps,             StepCount(kBoneSteps) },
        { offsetof(structure::m2::M2Header, boneLookup),            0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, vertices),              0x30, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, colors),                0x28, kArrayPlain,         kColorSteps,            StepCount(kColorSteps) },
        { offsetof(structure::m2::M2Header, textures),              0x10, kArrayPlain,         kTextureSteps,          StepCount(kTextureSteps) },
        { offsetof(structure::m2::M2Header, textureWeights),        0x14, kArrayPlain,         kTextureWeightSteps,    StepCount(kTextureWeightSteps) },
        { offsetof(structure::m2::M2Header, textureTransforms),     0x3C, kArrayPlain,         kTextureTransformSteps, StepCount(kTextureTransformSteps) },
        { offsetof(structure::m2::M2Header, textureReplacements),   0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, materials),             0x04, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, boneCombos),            0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, textureCombos),         0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, textureUnitLookup),     0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, textureWeightCombos),   0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, textureTransformCombos),0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, collisionIndices),      0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, collisionPositions),    0x0C, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, collisionNormals),      0x0C, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, attachments),           0x28, kArrayPlain,         kAttachmentSteps,       StepCount(kAttachmentSteps) },
        { offsetof(structure::m2::M2Header, attachmentLookup),      0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, events),                0x24, kArrayPlain,         kEventSteps,            StepCount(kEventSteps) },
        { offsetof(structure::m2::M2Header, lights),                0x9C, kArrayPlain,         kLightSteps,            StepCount(kLightSteps) },
        { offsetof(structure::m2::M2Header, cameras),               0x64, kArrayPlain,         kCameraSteps,           StepCount(kCameraSteps) },
        { offsetof(structure::m2::M2Header, cameraLookup),          0x02, kArrayPlain,         nullptr, 0 },
        { offsetof(structure::m2::M2Header, ribbonEmitters),        0xB0, kArrayPlain,         kRibbonSteps,           StepCount(kRibbonSteps) },
        { offsetof(structure::m2::M2Header, particleEmitters),     0x1DC, kArrayPlain,         kParticleSteps,         StepCount(kParticleSteps) },
        { offsetof(structure::m2::M2Header, textureCombinerCombos), 0x02, kArrayCombinerGated, nullptr, 0 },
    };
}
