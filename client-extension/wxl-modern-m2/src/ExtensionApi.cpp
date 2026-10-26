// wxl-modern-m2: definitions for the extension-wide service table pointer and lazy cross-binary interfaces.
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

#include "ExtensionApi.hpp"

namespace wxl_modern_m2
{
    const WXL_Api* g_api = nullptr;
    const WXL_FdidApi* g_fdid = nullptr;
    const WXL_M2ArenaApi* g_arena = nullptr;
}
