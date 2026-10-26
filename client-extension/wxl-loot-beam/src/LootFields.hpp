// wxl-loot-beam: the identity of the client's single live-loot record, kept apart so it is the only
// raw global the feature names.
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

// In 3.3.5a (12340) the client holds exactly one loot at a time: the object whose loot is open, or the
// one the server most recently answered a loot request for. Its GUID sits in a pair of neighbouring
// globals; the slot data (item ids, quantities, qualities) is reached through the client's own
// GetNumLootItems / GetLootSlotInfo script functions, which the module calls through the core's SDK
// rather than reimplementing the item cache. The identity of the open loot has no script getter, so it
// is the one address named here.
//
// The client is not told a corpse's loot until loot is requested for it (the loot window opening, on
// this client), so quality is only known for the currently open loot. The module caches what it sees
// against the corpse's GUID; a body that was never opened keeps the configured colour.
namespace wxl_loot_beam
{
    /// Combined low/high dwords of the GUID the live loot belongs to, both zero when none is open.
    /// The 8 bytes at kLootSourceGuid hold the whole 64-bit GUID.
    constexpr uintptr_t kLootSourceGuid = 0x00BFA8D8;

    /// The client's own ceiling on loot slots (18 possible slots plus the money entry); the count read
    /// from GetNumLootItems is clamped to this before it is iterated.
    constexpr int kMaxLootSlots = 19;
}
