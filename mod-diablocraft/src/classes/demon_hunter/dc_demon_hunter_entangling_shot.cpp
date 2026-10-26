/*
 * Entangling Shot and its five runes. The shot is the engine's single-target hit (a spell record and the sheet's
 * numbers); here: the slow on the enemy hit and on the others it entangles, kept so that a shot at an enemy still
 * entangled refreshes all of them, and Shock Collar's Lightning over time on every enemy entangled. Heavy Burden's longer
 * slow, Chain Gang's count, Bounty Hunter's stronger slow and Justice is Served's Hatred are sheet numbers the same code
 * reads.
 */

#include "dc_demon_hunter_entangling_shot.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_dot.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_seek.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_tunables.h"
#include "GameTime.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::EntanglingShot
{
    namespace
    {
        constexpr std::string_view Skill = "Entangling Shot";

        // The ties each Demon Hunter's last shot left, kept for the next shot to refresh.
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::vector<Tie>> held;

        // The other enemies around `primary`, nearest first, inside the search radius.
        std::vector<std::uint64_t> Nearest(Player* player, std::uint32_t spellId, Unit* primary, std::size_t count)
        {
            double const radius = Tune("entangling_shot_search_yards");
            std::vector<Unit*> around;
            std::vector<double> distances, bearings;
            std::vector<bool> excluded;
            for (Unit* enemy : Combat::Enemies(player, spellId, primary->GetPosition(), radius))
            {
                around.push_back(enemy);
                distances.push_back(primary->GetExactDist(enemy));
                bearings.push_back(0.0);
                excluded.push_back(enemy == primary);
            }
            std::vector<std::uint64_t> found;
            for (std::size_t index : Seek(distances, bearings, excluded, radius, 0.0, 360.0, count))
                found.push_back(around[index]->GetGUID().GetRawValue());
            return found;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return Numbers::Get(BaseId(Skill), "damage_pct");
    }

    bool Impact(Player* player, Unit* target, Unit* aimed, std::uint32_t spellId)
    {
        return player && target && aimed && RowOf(spellId, Skill) && !LeftToEngine(target == aimed);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId, Skill);
        if (!player || !target || !row)
            return;
        // "entangles up to {target_count} enemies, slowing their movement by {slow_pct} for {slow_duration_seconds} seconds":
        // the count is the enemies entangled, the one hit among them.
        auto const count = std::size_t(Numbers::Num(spellId, "target_count"));
        double const seconds = Numbers::Num(spellId, "slow_duration_seconds");
        std::uint64_t const now = std::uint64_t(GameTime::GetGameTimeMS().count());
        auto const nearest = Nearest(player, spellId, target, count);
        std::vector<std::uint64_t> group;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto& ties = held[player->GetGUID().GetRawValue()];
            group = Entangled(ties, now, target->GetGUID().GetRawValue(), nearest, count);
            ties.clear();
            for (std::uint64_t enemy : group)
                ties.push_back({enemy, now + std::uint64_t(seconds * 1000)});
        }
        bool const shock = RuneOf(row->rune) == Rune::ShockCollar;
        for (std::uint64_t guid : group)
        {
            Unit* enemy = ObjectAccessor::GetUnit(*player, ObjectGuid(guid));
            if (!enemy)
                continue;
            Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), seconds);
            // "Entangled enemies take {damage_pct} weapon damage as Lightning over {dot_duration_seconds} seconds."
            if (shock)
                Dot::Start(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                           Numbers::Num(spellId, "dot_duration_seconds"), Tune("entangling_shot_shock_collar_tick_seconds"));
        }
    }
} // namespace DC::Combat::DemonHunter::EntanglingShot
