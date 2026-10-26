/*
 * World of DiabloCraft - a timed cut to what a skill costs, the shared piece: a rune or a passive that says "the next X
 * costs N% less" gives the cut here, and the cost the core charges is lower BEFORE the cast, through the skill's hidden
 * cost aura (the SPELLMOD_COST record per skill in combat/dc_spell_shells.h SkillCostModifiers), so the full price is
 * never taken and handed back. A source is a key of the caller's; a second cut under the same key replaces the first,
 * cuts of different sources multiply (dc_cost_cut_math.h), and the cuts the worn items give the same skill
 * (`cost_reduction_pct` rows) multiply with them. The skill must be one that has a hidden cost aura
 * (generate_spells.py, skill_cost_skills).
 */

#ifndef DC_COST_CUT_H
#define DC_COST_CUT_H

#include "dc_cost_cut_math.h"

#include <cstdint>
#include <string_view>

class Player;

namespace DC::Combat::CostCut
{
    // `player` pays `pct` percent less for `skill` (every rune of it) for `seconds` from now, under `key`. No percent
    // or no seconds takes the key's cut off.
    void Hold(Player* player, std::string_view skill, std::uint32_t key, double pct, double seconds);
    // The same for as long as the source stands (a slotted passive): `skill` costs `pct` percent less under `key` until the caller takes it away with a
    // percent of 0 (or Clear). The cost auras follow at once.
    void Stand(Player* player, std::string_view skill, std::uint32_t key, double pct);
    // The percent off `skill` the live cuts give `player` now, combined (0 for none).
    double Pct(Player const* player, std::string_view skill);
    // Takes every cut of the player away.
    void Clear(Player* player);
    void RegisterScripts();
} // namespace DC::Combat::CostCut

#endif
