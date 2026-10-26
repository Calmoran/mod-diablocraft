// M2 additive-overlay combiner patch: registry of skin-finalize-tagged batches, and the shader that
// replaces their native substitute at bind time. See CombinerPatch.cpp for the mechanism.
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

#include <cstdint>

namespace wxl::runtime::m2combiner
{
    /**
     * @brief Tags one reshaped batch, by its final position in the skin's own batch array, as wanting
     *        the additive-overlay combiner patch. Called once per batch from skin finalize
     *        (compat/Skin.cpp), never at draw time.
     * @param skin        The live skin profile the batch belongs to (wxl::game::m2::M2SkinProfile*).
     * @param batchIndex  The batch's final position in that skin's batch array.
     */
    void MarkAddAlphaBatch(void* skin, uint32_t batchIndex);

    /** @brief True if MarkAddAlphaBatch tagged this exact (skin, batchIndex) pair. */
    bool IsAddAlphaBatch(void* skin, uint32_t batchIndex);

    /**
     * @brief Arms the very next Shader.EffectBind call to substitute the patched pixel shader.
     *        Consumed (cleared) by that same call whether or not the substitution actually runs, so a
     *        caller never needs to clear it itself. Single-threaded render path only (see
     *        CombinerPatch.cpp), so a plain flag is enough -- no atomics.
     */
    void ArmNextBind();
}

namespace wxl_modern_m2
{
    bool InstallCombinerPatch(); // render/CombinerPatch.cpp
}
