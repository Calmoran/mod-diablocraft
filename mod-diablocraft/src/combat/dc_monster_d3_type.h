#pragma once
/*
 * The D3 type of a roster monster (Human, Beast, Demon, Undead, Reaper...): the monster_type column of
 * data/d3/gr_monster_progress.csv through the roster, generated into dc_monster_d3_type. The damage-to-type stats read
 * it where 3.3.5 has no type of its own: Damage to Humans, since the Humanoid type also holds orcs, trolls and murlocs.
 */
#include <string_view>

class Creature;

namespace DC::Combat::MonsterTypes
{
    // The D3 type of a creature as the sheet names it. A champion or rare clone has its base monster's type. Empty for
    // a creature outside the roster, a monster with no row and no creature at all.
    std::string_view D3TypeOf(Creature const* creature);
} // namespace DC::Combat::MonsterTypes
