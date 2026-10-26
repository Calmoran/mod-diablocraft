// m2: in-memory loading of modern M2 assets on the target client.
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

/**
 * @brief The live-engine half of modern-M2 support: what the client must be taught to DO with a model the
 *        native MD21 reader (NativeLoad.cpp) filled, once the bytes are already in the runtime.
 *
 * Owns the set of those models (via the shared AssetRegistry) and binds the core events to the M2 themes:
 * the universal bone-budget split plus, for registered models, the material/texunit contract rebuild at skin
 * finalize, and the alpha-key / multi-texture ribbon fixups at draw. No bytes are reshaped anywhere here.
 */
namespace wxl::modern::assets::m2
{
    /**
     * @brief Registers a model the native MD21 reader (NativeLoad.cpp) direct-filled, so the
     *        live-engine half owned by this module (bone-budget split + material/texunit contract
     *        rebuild at skin finalize, alpha-key and ribbon draw fixups) applies to it unchanged.
     *        No-op when the modern-M2 module is compiled out.
     * @param model Runtime model pointer.
     */
    void RegisterNativeLoaded(void* model);

    /**
     * @brief Drops a native-reader registration (failed fill after registration). Safe on a model
     *        that was never registered.
     * @param model Runtime model pointer.
     */
    void ForgetNativeLoaded(void* model);
}
