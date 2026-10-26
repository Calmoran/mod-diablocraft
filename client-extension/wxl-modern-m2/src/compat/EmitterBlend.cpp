// Emitter blending: gives a source blend mode the stock map has no arm for its real blend state.
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

// An emitter's record names a blend mode, which model construction maps through a fixed set of arms
// into a device blend state. Source content asks for a mode past the last arm, and the default arm
// resolves it to opaque with alpha testing left on -- a fire sprite drawn as a solid quad.
//
// What that mode actually means was recovered from the donor images: the version that introduced it
// added exactly one usable blend state alongside it, a screen blend -- incoming times what is NOT
// already there, added on top -- which brightens toward white without ever clipping. That state now
// exists here too, appended to the device's own tables, so the mode has a real home rather than a
// nearest-looking substitute.
//
// The correction is applied AFTER construction rather than by rewriting the record, so the model keeps
// the blend mode it was authored with. It has to be after, because the default arm and a genuine mode
// 0 leave the emitter in identical states -- only the record can still tell them apart, and the
// emitter's back-pointer to its own record is wired up during that same construction.

#include "../ExtensionApi.hpp"

#include "engine/assets/shared/models/m2/M2Format.hpp"
#include "offsets/engine/Gx.hpp"
#include "offsets/game/M2.hpp"

#include <cstdint>
#include <cstring>

namespace
{
    namespace gx  = wxl::offsets::engine::gx;
    namespace off = wxl::offsets::game::m2;

    off::M2_InitializeLoadedFn g_origInitializeLoaded = nullptr;

    template <typename T>
    T Read(const void* base, size_t at)
    {
        T v{};
        std::memcpy(&v, static_cast<const uint8_t*>(base) + at, sizeof v);
        return v;
    }

    template <typename T>
    void Write(void* base, size_t at, T value)
    {
        std::memcpy(static_cast<uint8_t*>(base) + at, &value, sizeof value);
    }

    /// The emitter's own record, recovered from the back-pointer construction leaves in it.
    const uint8_t* RecordOf(const void* emitter)
    {
        const auto* headCells = Read<const uint8_t*>(emitter, off::kOffEmitterHeadCellBlock);
        return headCells ? headCells - off::kParticleRecHeadCells : nullptr;
    }

    /// Re-resolves one emitter whose record names a blend mode the stock map has no arm for.
    /// @return true when this emitter needed the correction.
    bool ResolveBlendState(void* emitter)
    {
        const uint8_t* record = RecordOf(emitter);
        if (!record) return false;
        if (record[off::kParticleRecBlendMode] <= off::kParticleBlendModeMax) return false;

        Write<uint32_t>(emitter, off::kOffEmitterBlendState, gx::kBlendStateScreenAdd);
        // Alpha testing belongs to the two modes that do not blend at all; the default arm left it on.
        Write<uint32_t>(emitter, off::kOffEmitterMaterialFlags,
                        Read<uint32_t>(emitter, off::kOffEmitterMaterialFlags) &
                            ~off::kEmitterMaterialAlphaTest);
        return true;
    }

    /**
     * @brief Re-resolves every emitter of a model once construction has built and wired them all.
     * @return construction's own result, untouched.
     */
    uint32_t __fastcall hkInitializeLoaded(void* model, void* edx)
    {
        const uint32_t result = g_origInitializeLoaded(model, edx);

        const auto* shared = reinterpret_cast<const uint8_t*>(static_cast<off::M2Instance*>(model)->model);
        auto* const* emitters = Read<void* const*>(model, off::kOffInstEmitterArray);
        if (!shared || !emitters) return result;
        const auto* header = reinterpret_cast<const wxl::structure::m2::M2Header*>(
            reinterpret_cast<const off::M2Model*>(shared)->header);
        if (!header) return result;

        const uint32_t count = header->particleEmitters.count;
        for (uint32_t i = 0; i < count; ++i)
            if (emitters[i]) ResolveBlendState(emitters[i]);
        return result;
    }
}

namespace wxl_modern_m2
{
    bool InstallEmitterBlend()
    {
        if (!HookAttachByName("M2.InitializeLoaded", &hkInitializeLoaded, &g_origInitializeLoaded))
            return false;
        WLOG_INFO("m2native-particles: emitter blend modes past the stock map resolved natively");
        return true;
    }
}
