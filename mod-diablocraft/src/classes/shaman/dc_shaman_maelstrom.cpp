/*
 * World of DiabloCraft - the Shaman's Maelstrom: what a Primary generates when it connects, and the split of a gain
 * between the bar and Overcharge (dc_shaman_maelstrom.h has the rule).
 */

#include "dc_shaman_common.h"
#include "dc_shaman_elemental_weapon.h"
#include "dc_shaman_elemental_lash.h"
#include "dc_shaman_passives.h"
#include "dc_shaman_maelstrom.h"
#include "../../combat/dc_item_powers.h"
#include "../../stats/dc_stats.h"

namespace DC::Combat::Shaman
{
    void Gain(Player* player, std::uint32_t spellId, double points)
    {
        if (!IsShaman(player) || points <= 0 || !Resources::Displayed(player, Resources::Maelstrom))
            return;
        Maelstrom::Gain const split = Maelstrom::Split(Resources::Get(player, Resources::Maelstrom),
                                                       Resources::Max(player, Resources::Maelstrom), points);
        if (split.paid > 0)
            Resources::Energize(player, Resources::Maelstrom, spellId, split.paid);
        Overcharge::Overflow(player, split.overflow);
    }

    void Connected(Player* player, std::uint32_t spellId, unsigned enemies)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!IsShaman(player) || !row)
            return;
        // "Generate: N Maelstrom": the skill states the number unqualified and its runes inherit it; a rune that
        // changes the generation states its own as the `new` one.
        auto const sheet = Numbers::Get(spellId, "generated_resource", "new")
                               .value_or(Numbers::Get(spellId, "generated_resource").value_or(0.0));
        // Gear: points more from each Primary, and a percent more from every generating skill (the sheet's Maelstrom lines).
        double primaryFlat = 0, percent = 0;
        if (auto const stats = Stats::Get(player->GetGUID().GetRawValue()))
        {
            primaryFlat = (*stats)[Stat::PrimaryMaelstrom] + Passive::PrimaryGain(player);
            percent = (*stats)[Stat::MaelstromGeneration];
        }
        double const points = Maelstrom::Generated(sheet, Classes::CategoryOf(spellId) == "Primary", primaryFlat, percent) *
                              ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") *
                              (1.0 + ElementalWeapon::GenerationPct(player, spellId) / 100.0);
        Gain(player, spellId, points);
        ElementalLash::Connected(player, spellId, enemies);
    }
} // namespace DC::Combat::Shaman
