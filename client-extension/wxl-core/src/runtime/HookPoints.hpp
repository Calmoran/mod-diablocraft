// Named hook points: the addresses behind WXL_Api::HookAttachByName, so an extension can attach to
// one without including an offsets/ header itself.
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

namespace wxl::runtime::hookpoints
{
    /**
     * @brief Resolves pointName against the core's hook-point table and installs a detour there.
     * @param pointName  name a hook point is registered under (see HookPoints.cpp).
     * @param detour     replacement function.
     * @param original   receives the next link in the chain.
     * @param priority   chain position; see wxl::hook::kDefaultPriority.
     * @return non-zero if the detour was registered; zero if pointName is not registered.
     */
    int AttachByName(const char* pointName, void* detour, void** original, int priority);
}
