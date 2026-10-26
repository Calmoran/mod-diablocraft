// A heal D3 scales by the Healing table of the power formulas (Table(Healing, Effective_Level)), shared by every class.
//
// The sheets hold these heals as the tooltips show them, at the top level (the table's last row). A power file's heal is its own
// coefficient times the table at the caster's level, so the heal at a level is the sheet's number times the table at that level
// over the table at the top level: the coefficient cancels, and the sheet's number stays the one source of it.
#pragma once

#include "../combat/dc_healing_table.h"

#include <cstddef>

namespace DC::Classes
{
// The table's last row: the level the sheets' heals are written at.
inline double TopLevelHealing()
{
    return Combat::Healing::Table[sizeof(Combat::Healing::Table) / sizeof(Combat::Healing::Table[0]) - 1];
}

// `atTopLevel` (a sheet's heal, absorb or regeneration) as it is for a caster at `level`; a level past the table reads its last row.
inline double HealAtLevel(double atTopLevel, unsigned level)
{
    return atTopLevel > 0 ? atTopLevel * Combat::Healing::At(level) / TopLevelHealing() : 0.0;
}

// A standing contribution on the stat sheet (Vigilant's and Enduring Ally's regeneration) is built from `HealAtLevel` and rebuilt only
// when something else changes, so it remembers the level it was built at: it is stale when that is not the caster's level now.
inline bool BuiltAtOtherLevel(unsigned builtAt, unsigned level)
{
    return builtAt != level;
}
} // namespace DC::Classes
