// Synthetic per-tier model names: lets a caller (wxl-modern-adt's doodad placement) request "this
// model, but its LOD skin N" as if it were a distinct model path, so the native model cache loads and
// shares it independently of the base model.
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

#include <cstddef>
#include <cstdint>

namespace wxl::runtime::m2lodvariant
{
    /**
     * @brief Builds the synthetic request name for one LOD tier of a model.
     *
     * "world\...\prop.m2", tier 2 -> "world\...\prop$LOD02.m2". A caller passes the result to
     * whatever native entry point would otherwise take the real model path (e.g. the doodad spawn
     * point); the file-open redirect installed by this module transparently serves the real .m2/.skin
     * bytes for it, and the real "_lodNN.skin" sibling gets attached in place of the base skin once
     * the model finishes loading.
     * @param realModelPath the model's real path, with extension.
     * @param tier           1-based LOD tier, matching "_lodNN.skin" numbering (1..99).
     * @return false (outBuf untouched) if tier is out of range or the result would not fit.
     */
    bool BuildVariantName(const char* realModelPath, uint32_t tier, char* outBuf, size_t outBufSize);

    /** @brief True once the file-open redirect and the load-time skin swap are installed. */
    bool Installed();
}
