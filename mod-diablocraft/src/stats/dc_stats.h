#ifndef DC_STATS_H
#define DC_STATS_H

#include "../common/dc_common.h"
#include "dc_sheet_summary.h"
#include <optional>

class Player;
class Unit;

namespace DC::Stats
{
    // Mutations/Recompute must run on the owning player's world/map thread. Readers
    // receive a copy, never a pointer into the GUID-keyed store. Mutations mark inputs
    // only; the caller explicitly Recomputes once after a batch of changes.
    std::optional<StatSheet> Get(std::uint64_t playerGuid);
    bool AddContribution(std::uint64_t playerGuid, Contribution const& contribution);
    // What one source has put on one stat (one element for a single resistance): Harmony reads the resistances items give.
    double Sum(std::uint64_t playerGuid, Source source, Stat stat, Element element = Element::Physical);
    bool RemoveContribution(std::uint64_t playerGuid, Source source, Stat stat, std::uint64_t id);
    // A copy of every contribution the player's sheet holds (the saved ones after a load): Items::RefreshCubedStats' login sweep reads it.
    std::vector<Contribution> Contributions(std::uint64_t playerGuid);
    bool Recompute(Player* player);
    bool ReplaceParagon(Player* player, std::vector<Contribution> const& contributions);

    // Life per Hit (stats.csv row 15). Patch 2.1+ restores 100% of the sheet value
    // once per cast that hit at least one target, so combat calls this once per
    // connected cast and never per splash target: the same row excludes Area
    // Damage, Thorns and passive/secondary procs. Implemented in dc_sustain.cpp.
    void SkillHit(Player* player);
    // N-THDEAL (Hack): a Thorns hit of `amount` dealt by `player` to the enemy `target` it just hit, as Thorns are dealt to an attacker (Physical, no
    // critical). Nothing for an amount of 0, a target that cannot be attacked, or while a Thorns hit is being dealt.
    void ThornsHit(Player* player, Unit* target, double amount);

    // Life per Fury Spent (d3planner lifefury): the Barbarian spent `fury` points of Fury now, and the sheet's Life per
    // Fury Spent is restored for each. Called once per payment from Abilities::Spent, so a cast, a Whirlwind tick and
    // a spender's own charge each pay once. Implemented in dc_sustain.cpp.
    void FurySpent(Player* player, double fury);

    // The equipped weapon as a stat source, so the sheet's own APS is the one
    // number combat uses (02 §3, C7). Sets Stat::WeaponAPS from the main hand and
    // D3's additive +15% sheet IAS while dual wielding; recomputes the sheet.
    void RefreshWeapon(Player* player);

    // The player's Summary (dc_sheet_summary.h holds the formula the player and a follower share): the equipped weapons
    // and the player's own damage buckets, over the player's sheet.
    Summary SheetSummary(Player* player);

    void RegisterScripts();
} // namespace DC::Stats

#endif // DC_STATS_H
