/*
 * Consecration and its five runes: the ground laid where the Crusader stands, healing its group while they stand on it,
 * and what each rune does to the enemies on it or at its edge. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_consecration.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"
#include "dc_crusader_dot.h"
#include "../../stats/dc_stats.h"
#include "Group.h"
#include "GroupReference.h"
#include "Random.h"

#include <algorithm>
#include <memory>

namespace DC::Combat::Crusader::Consecration
{
    namespace
    {
        constexpr std::string_view Skill = "Consecration";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // The least the barrier's look at its enemies can be. The tunable's value is 0.25, and 0 must not make the
        // look run on every update; this is a guard against 0, not a tuning number.
        constexpr double CheckFloorSeconds = 0.1;
        // How far past the edge the barrier keeps its eye on an enemy: far more than one look lets any enemy move, so
        // none can arrive on the other side unseen. A guard on the search, not a tuning number.
        constexpr double WatchMarginYards = 10.0;

        std::chrono::milliseconds CheckEvery()
        {
            return std::chrono::milliseconds(
                std::uint64_t(std::max(CheckFloorSeconds, Tune("consecration_barrier_check_seconds")) * 1000));
        }

        // Where an enemy was last seen to be allowed: the side of the edge it stood on and the place it stood.
        struct Side
        {
            bool inside = false;
            Position good;
        };

        // Aegis Purgatory: one look. An enemy now on the other side of the edge from where it was seen is put back.
        void Look(Player* player, std::uint32_t spellId, Position center, std::uint64_t until,
                  std::shared_ptr<std::unordered_map<std::uint64_t, Side>> sides)
        {
            if (!player->IsInWorld() || Now() >= until)
                return;
            double const radius = Numbers::Num(spellId, "radius_yards");
            for (Unit* enemy : Combat::Enemies(player, spellId, center, radius + WatchMarginYards))
            {
                double const distance = center.GetExactDist2d(enemy);
                auto seen = sides->find(enemy->GetGUID().GetRawValue());
                if (seen == sides->end())
                    (*sides)[enemy->GetGUID().GetRawValue()] = {OnGround(distance, radius), enemy->GetPosition()};
                else if (Crossed(seen->second.inside, distance, radius))
                    enemy->NearTeleportTo(seen->second.good.GetPositionX(), seen->second.good.GetPositionY(),
                                          seen->second.good.GetPositionZ(), enemy->GetOrientation());
                else
                    seen->second.good = enemy->GetPosition();
            }
            player->m_Events.AddEventAtOffset([player, spellId, center, until, sides]
                                              { Look(player, spellId, center, until, sides); }, CheckEvery());
        }

        // Bed of Nails: a share of the Crusader's Thorns, dealt as Thorns is, all Physical and never a critical hit.
        void Nails(Player* player, std::uint32_t spellId, Unit* enemy)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            if (!sheet)
                return;
            Hit hit;
            hit.skillName = "Thorns";
            hit.school = SPELL_SCHOOL_MASK_NORMAL;
            hit.total = ThornsShare((*sheet)[Stat::Thorns], Numbers::Num(spellId, "thorns_share_pct"));
            hit.crit = 1.0;
            if (hit.total > 0)
                Combat::DealHit(player, enemy, spellId, hit);
        }

        // One tick of the ground: the heal to the group on it, then what the rune does to the enemies on it. The ticks
        // left bound the ground by themselves: no clock test may stop the last one.
        void Tick(Player* player, std::uint32_t spellId, Position center, unsigned left, std::uint32_t intervalMs)
        {
            if (!player->IsInWorld() || left == 0)
                return;
            double const radius = Numbers::Num(spellId, "radius_yards");
            // "You and your allies heal for {heal_per_second_life} Life per second while standing on the consecrated
            // ground."
            double const heal = Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_second_life"), player->GetLevel());
            std::vector<Player*> standing{player};
            if (Group* group = player->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource(); member && member != player)
                        standing.push_back(member);
            // Only a member on the Crusader's own map: a distance reads coordinates, and another map or instance shares them.
            for (Player* ally : standing)
                if (ally->IsInWorld() && ally->GetMap() == player->GetMap() &&
                    OnGround(ally->GetExactDist(&center), radius))
                    Heal(player, ally, spellId, heal);
            Rune const rune = RuneAt(spellId);
            if (player->IsAlive() &&
                (rune == Rune::BedOfNails || rune == Rune::ShatteredGround || rune == Rune::Fearful))
                for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
                    switch (rune)
                    {
                        case Rune::BedOfNails:
                            Nails(player, spellId, enemy);
                            break;
                        case Rune::ShatteredGround:
                            // "Enemies standing on consecrated ground take {damage_pct} weapon damage as Fire per
                            // second."
                            Combat::Strike(player, enemy, spellId, Numbers::Own(spellId, "damage_pct"), true);
                            break;
                        case Rune::Fearful:
                            // "a {proc_chance_pct} chance to be Feared for {fear_duration_seconds} seconds."
                            if (Procs(rand_chance(), Numbers::Num(spellId, "proc_chance_pct")))
                                Fear(player, enemy, Numbers::Num(spellId, "fear_duration_seconds"));
                            break;
                        default:
                            break;
                    }
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, center, left, intervalMs]
                                                  { Tick(player, spellId, center, left - 1, intervalMs); },
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
        double const seconds = Numbers::Num(spellId, "duration_seconds"), tick = Tune("consecration_tick_seconds");
        Position const center = player->GetPosition();
        if (unsigned const ticks = Dot::Ticks(seconds, tick))
        {
            auto const interval = std::uint32_t(tick * 1000 + 0.5);
            player->m_Events.AddEventAtOffset([player, spellId, center, ticks, interval]
                                              { Tick(player, spellId, center, ticks, interval); },
                                              std::chrono::milliseconds(interval));
        }
        if (RuneAt(spellId) == Rune::AegisPurgatory)
            Look(player, spellId, center, Now() + std::uint64_t(seconds * 1000.0),
                 std::make_shared<std::unordered_map<std::uint64_t, Side>>());
    }
} // namespace DC::Combat::Crusader::Consecration
