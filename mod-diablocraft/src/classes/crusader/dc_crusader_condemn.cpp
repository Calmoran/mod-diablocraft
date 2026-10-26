/*
 * Condemn and its five runes: the explosion that builds around the Crusader and goes off after a few seconds, and what
 * each rune does while it builds or when it goes off. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_condemn.h"
#include "dc_crusader_common.h"
#include "dc_crusader_nearest.h"
#include "../../combat/dc_movement_effects.h"
#include "Random.h"
#include "SpellMgr.h"

#include <cmath>

namespace DC::Combat::Crusader::Condemn
{
    namespace
    {
        constexpr std::string_view Skill = "Condemn";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // The explosion each Crusader has building: which cast it is (a later cast replaces it), when its time is over
        // and the damage Reciprocate has counted so far.
        struct Build
        {
            std::uint64_t cast = 0;
            std::uint64_t until = 0;
            double taken = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Build> builds;
        std::uint64_t lastCast = 0;

        // The cooldown Eternal Retaliation gives back: the records of every rune share one, and the core installed it
        // at the cast.
        void Cut(Player* player, double seconds)
        {
            if (seconds <= 0)
                return;
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && player->GetSpellCooldownDelay(row.id))
                    player->ModifySpellCooldown(row.id, -static_cast<int32>(seconds * 1000.0));
        }

        // Reciprocate's counted damage, dealt on top of the explosion as one more hit of the rune's own school.
        void Added(Player* player, std::uint32_t spellId, Unit* enemy, double damage)
        {
            if (damage <= 0)
                return;
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            Hit hit;
            hit.skillName = Skill;
            hit.school = info ? unsigned(info->GetSchoolMask()) : unsigned(SPELL_SCHOOL_MASK_HOLY);
            hit.total = damage;
            hit.crit = 1.0;
            Combat::DealHit(player, enemy, spellId, hit);
        }

        // The explosion goes off round the Crusader where it stands now: dead or gone, it does not.
        void Explode(Player* player, std::uint32_t spellId, std::uint64_t cast)
        {
            double taken = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = builds.find(player->GetGUID().GetRawValue());
                if (found != builds.end() && found->second.cast == cast)
                {
                    taken = found->second.taken;
                    builds.erase(found);
                }
            }
            if (!player->IsInWorld() || !player->IsAlive())
                return;
            Rune const rune = RuneAt(spellId);
            double const extra = Reciprocated(rune, taken, Numbers::Num(spellId, "damage_share_pct"));
            unsigned hits = 0;
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
            {
                if (Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct")))
                    ++hits;
                Added(player, spellId, enemy, extra);
            }
            Cut(player, CooldownCut(rune, hits, Numbers::Num(spellId, "cooldown_reduction_seconds")));
        }

        // One draw of Vacuum: the nearest enemies beyond the explosion and inside this pulse's reach, up to the most it
        // takes, drawn in to a little way from the Crusader.
        void Suck(Player* player, std::uint32_t spellId, unsigned pulse, unsigned pulses, std::uint32_t intervalMs)
        {
            if (!player->IsInWorld() || !player->IsAlive() || pulse > pulses)
                return;
            double const radius = Numbers::Num(spellId, "radius_yards");
            double const reach = PullReach(radius, Tune("condemn_vacuum_radius_step_yards"), pulse);
            std::vector<Unit*> candidates;
            std::vector<double> distances;
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), reach))
            {
                double const distance = player->GetExactDist(enemy);
                if (SuckedIn(distance, radius, reach))
                {
                    candidates.push_back(enemy);
                    distances.push_back(distance);
                }
            }
            Position const here = player->GetPosition();
            for (std::size_t i : Nearest(distances, reach, std::size_t(Tune("condemn_vacuum_max_targets"))))
            {
                Unit* enemy = candidates[i];
                double const stop = Tune("condemn_vacuum_offset_min_yards") +
                                    frand(0.0f, float(Tune("condemn_vacuum_offset_extra_yards")));
                double const share = std::min(1.0, stop / distances[i]);
                Position point = here;
                point.Relocate(here.GetPositionX() + (enemy->GetPositionX() - here.GetPositionX()) * share,
                               here.GetPositionY() + (enemy->GetPositionY() - here.GetPositionY()) * share,
                               here.GetPositionZ() + (enemy->GetPositionZ() - here.GetPositionZ()) * share);
                Abilities::Pull(enemy, point);
            }
            if (pulse < pulses)
                player->m_Events.AddEventAtOffset([player, spellId, pulse, pulses, intervalMs]
                                                  { Suck(player, spellId, pulse + 1, pulses, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
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
        return 0.0;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        double const seconds = BuildSeconds(rune, Numbers::Num(spellId, "duration_seconds"));
        std::uint64_t cast = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            cast = ++lastCast;
            builds[player->GetGUID().GetRawValue()] = {cast, Now() + std::uint64_t(seconds * 1000.0), 0.0};
        }
        if (seconds <= 0)
        {
            Explode(player, spellId, cast);
            return;
        }
        if (rune == Rune::Vacuum)
        {
            double const interval = Tune("condemn_vacuum_interval_seconds");
            if (unsigned const pulses = Pulses(seconds, interval))
            {
                auto const intervalMs = std::uint32_t(interval * 1000 + 0.5);
                player->m_Events.AddEventAtOffset([player, spellId, pulses, intervalMs]
                                                  { Suck(player, spellId, 1, pulses, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
            }
        }
        player->m_Events.AddEventAtOffset([player, spellId, cast] { Explode(player, spellId, cast); },
                                          std::chrono::milliseconds(std::uint64_t(seconds * 1000.0)));
    }

    void Taken(Player* victim, double damage)
    {
        if (!victim || damage <= 0)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = builds.find(victim->GetGUID().GetRawValue());
        if (found != builds.end() && Building(Now(), found->second.until))
            found->second.taken += damage;
    }
} // namespace DC::Combat::Crusader::Condemn
