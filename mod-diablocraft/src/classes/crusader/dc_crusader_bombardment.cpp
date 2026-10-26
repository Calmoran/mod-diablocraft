/*
 * Bombardment and its five runes. The cast is aimed at the ground (skill_targeting.csv: 60 yards, 12 yards of area) and
 * deals no hit of its own: spheres of burning pitch fall one after another on the enemies near the point, each a strike
 * in its area, and what each rune does to them is here. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_bombardment.h"
#include "dc_crusader_common.h"
#include "../../stats/dc_stats.h"
#include "ObjectAccessor.h"
#include "Random.h"

#include <chrono>
#include <cmath>
#include <memory>

namespace DC::Combat::Crusader::Bombardment
{
    namespace
    {
        constexpr std::string_view Skill = "Bombardment";
        // The least a look at the mines can be apart: 0 must not make the look run on every update. A guard against 0,
        // not a tuning number.
        constexpr double MineCheckFloorSeconds = 0.1;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        double Roll()
        {
            return rand_chance() / 100.0;
        }

        std::chrono::milliseconds Millis(double seconds)
        {
            return std::chrono::milliseconds(std::llround(std::max(0.0, seconds) * 1000.0));
        }

        // What one barrage keeps from the first impact to the last.
        struct Barrage
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            Position center;
            ObjectGuid first;  // Targeted: the enemy every impact falls on
            Position firstAt;  // where it was last seen
            unsigned left = 0; // impacts still to fall
            double pctEach = 0;
            double radius = 0;
            double minWait = 0;
            double extraWait = 0;
        };

        // One mine of Mine Field: it waits `until`, and goes off on the first enemy within its radius.
        void Mine(Player* player, std::uint32_t spellId, Position at, double radius, std::uint64_t until,
                  std::chrono::milliseconds every)
        {
            if (!player->IsInWorld() || !player->IsAlive() || Now() >= until)
                return;
            std::vector<Unit*> near = Combat::Enemies(player, spellId, at, radius);
            double nearest = radius + 1.0;
            for (Unit* enemy : near)
                nearest = std::min(nearest, double(at.GetExactDist(enemy)));
            if (MineGoesOff(nearest, radius))
            {
                // "explode when enemies walk near them, dealing {damage_pct} weapon damage as Fire to all enemies
                // within {radius_yards} yards."
                if (!Combat::StrikeArea(player, spellId, at, radius, Numbers::Num(spellId, "damage_pct")).empty())
                    Combat::Connected(player, spellId, 1);
                return;
            }
            player->m_Events.AddEventAtOffset([player, spellId, at, radius, until, every]
                                              { Mine(player, spellId, at, radius, until, every); }, every);
        }

        // Mine Field: the impact scatters its mines between the nearest and the farthest a mine lies.
        void Scatter(Player* player, std::uint32_t spellId, Position const& impact)
        {
            unsigned const mines = unsigned(Numbers::Num(spellId, "spawn_count"));
            double const radius = Numbers::Num(spellId, "radius_yards");
            double const seconds = Tune("bombardment_mine_seconds");
            auto const every = Millis(std::max(MineCheckFloorSeconds, Tune("bombardment_mine_check_seconds")));
            for (unsigned i = 0; i < mines; ++i)
            {
                double const angle = 2.0 * M_PI * Roll();
                double const distance =
                    MineDistance(Tune("bombardment_mine_min_yards"), Tune("bombardment_mine_max_yards"), Roll());
                Position at = impact;
                at.Relocate(impact.GetPositionX() + float(std::cos(angle) * distance),
                            impact.GetPositionY() + float(std::sin(angle) * distance), impact.GetPositionZ());
                Mine(player, spellId, at, radius, Now() + std::uint64_t(seconds * 1000.0), every);
            }
        }

        // Barrels of Spikes: a share of the Crusader's Thorns on top of the barrel's hit, dealt as Thorns is, all
        // Physical and never a critical hit.
        void Barrel(Player* player, std::uint32_t spellId, Unit* enemy)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            if (!sheet)
                return;
            Hit hit;
            hit.skillName = "Thorns";
            hit.school = SPELL_SCHOOL_MASK_NORMAL;
            hit.total =
                BarrelBonus(Rune::BarrelsOfSpikes, (*sheet)[Stat::Thorns], Numbers::Num(spellId, "thorns_share_pct"));
            hit.crit = 1.0;
            if (hit.total > 0)
                Combat::DealHit(player, enemy, spellId, hit);
        }

        // The impact: every enemy in the area takes the sphere's share of the total.
        void Impact(Player* player, std::shared_ptr<Barrage> plan, Position at)
        {
            if (!player->IsInWorld() || !player->IsAlive())
                return;
            std::vector<Unit*> const hit = Combat::StrikeArea(player, plan->spellId, at, plan->radius, plan->pctEach);
            for (Unit* enemy : hit)
                if (plan->rune == Rune::BarrelsOfSpikes)
                    Barrel(player, plan->spellId, enemy);
            if (!hit.empty())
                Combat::Connected(player, plan->spellId, unsigned(hit.size()));
            if (plan->rune == Rune::MineField)
                Scatter(player, plan->spellId, at);
        }

        // Where the next sphere falls: on the first target for Targeted, on the aimed point for the single ball, and on
        // a random enemy near the point for the rest (the point itself when none is there).
        Position Where(Player* player, Barrage& plan)
        {
            if (plan.rune == Rune::Targeted)
            {
                if (Unit* first = ObjectAccessor::GetUnit(*player, plan.first); first && first->IsAlive())
                    plan.firstAt = first->GetPosition();
                return plan.firstAt;
            }
            if (plan.rune == Rune::ImpactfulBombardment)
                return plan.center;
            std::vector<Unit*> const near =
                Combat::Enemies(player, plan.spellId, plan.center, Tune("bombardment_search_radius_yards"));
            if (auto const pick = Pick(near.size(), Roll()))
                return near[*pick]->GetPosition();
            return plan.center;
        }

        // One sphere leaves, falls after the impact delay, and the next leaves after its wait.
        void Spawn(Player* player, std::shared_ptr<Barrage> plan)
        {
            if (!player->IsInWorld() || !player->IsAlive() || plan->left == 0)
                return;
            Position const at = Where(player, *plan);
            player->m_Events.AddEventAtOffset([player, plan, at] { Impact(player, plan, at); },
                                              Millis(Tune("bombardment_impact_delay_seconds")));
            if (--plan->left > 0)
                player->m_Events.AddEventAtOffset([player, plan] { Spawn(player, plan); },
                                                  Millis(Wait(plan->minWait, plan->extraWait, Roll())));
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

    double CritBonus(std::uint32_t spellId)
    {
        return Is(spellId) ? CritBonusPct(RuneAt(spellId), Numbers::Num(spellId, "crit_chance_pct")) : 0.0;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        std::uint32_t const base = BaseId(Skill);
        auto plan = std::make_shared<Barrage>();
        plan->spellId = spellId;
        plan->rune = rune;
        plan->center = center;
        plan->firstAt = center;
        // "raining {spawn_count} spheres ... dealing {damage_pct} total weapon damage to enemies within {radius_yards}
        // yards of the impact zone": the skill's own numbers, Impactful Bombardment's the exception (its sheet states a
        // total and a radius for its single ball).
        plan->left = Impacts(rune, unsigned(Numbers::Num(base, "spawn_count")));
        plan->pctEach =
            PctEach(rune, Numbers::Num(base, "damage_pct"), Numbers::Num(spellId, "damage_pct"), plan->left);
        plan->radius = ImpactRadius(rune, Numbers::Num(base, "radius_yards"), Numbers::Num(spellId, "radius_yards"));
        plan->minWait =
            MinWait(rune, Tune("bombardment_spawn_wait_seconds"), Tune("bombardment_barrels_wait_added_seconds"),
                    Tune("bombardment_mine_field_wait_added_seconds"));
        plan->extraWait = Tune("bombardment_spawn_wait_extra_seconds");
        if (rune == Rune::Targeted)
        {
            // "the bombardment will continue to fall on your initial target": the enemy nearest the aimed point.
            Unit* nearest = nullptr;
            for (Unit* enemy : Combat::Enemies(player, spellId, center, Tune("bombardment_search_radius_yards")))
                if (!nearest || center.GetExactDist(enemy) < center.GetExactDist(nearest))
                    nearest = enemy;
            if (nearest)
            {
                plan->first = nearest->GetGUID();
                plan->firstAt = nearest->GetPosition();
            }
        }
        player->m_Events.AddEventAtOffset([player, plan] { Spawn(player, plan); },
                                          Millis(Tune("bombardment_first_delay_seconds")));
    }
} // namespace DC::Combat::Crusader::Bombardment
