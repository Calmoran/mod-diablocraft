/*
 * A place the Crusader holds shut: the enemies near its edge are looked at, and one that has crossed it is put back.
 */

#include "dc_crusader_hold.h"
#include "dc_crusader_common.h"
#include "dc_crusader_consecration.h"

#include <algorithm>
#include <chrono>
#include <memory>

namespace DC::Combat::Crusader::Hold
{
    namespace
    {
        // The least a look can be apart: 0 must not make the look run on every update. A guard against 0, not a tuning
        // number.
        constexpr double CheckFloorSeconds = 0.1;
        // How far past the edge a held place keeps its eye on an enemy: far more than one look lets any enemy move, so
        // none can arrive on the other side unseen. A guard on the search, not a tuning number.
        constexpr double WatchMarginYards = 10.0;

        // Where an enemy was last seen to be allowed: the side of the place it stood on and the spot.
        struct Side
        {
            bool inside = false;
            Position good;
        };
        using Seen = std::unordered_map<std::uint64_t, Side>;

        void Look(Player* player, std::uint32_t spellId, Position where, double radius, std::uint64_t until,
                  std::chrono::milliseconds every, std::shared_ptr<Seen> seen)
        {
            if (!player->IsInWorld() || Now() >= until)
                return;
            for (Unit* enemy : Combat::Enemies(player, spellId, where, radius + WatchMarginYards))
            {
                double const distance = where.GetExactDist2d(enemy);
                auto found = seen->find(enemy->GetGUID().GetRawValue());
                if (found == seen->end())
                    (*seen)[enemy->GetGUID().GetRawValue()] = {Consecration::OnGround(distance, radius),
                                                               enemy->GetPosition()};
                else if (Consecration::Crossed(found->second.inside, distance, radius))
                    enemy->NearTeleportTo(found->second.good.GetPositionX(), found->second.good.GetPositionY(),
                                          found->second.good.GetPositionZ(), enemy->GetOrientation());
                else
                    found->second.good = enemy->GetPosition();
            }
            player->m_Events.AddEventAtOffset([player, spellId, where, radius, until, every, seen]
                                              { Look(player, spellId, where, radius, until, every, seen); }, every);
        }
    } // namespace

    void Place(Player* player, std::uint32_t spellId, Position where, double radius, double seconds,
               double checkSeconds)
    {
        if (!player || radius <= 0 || seconds <= 0)
            return;
        auto const every = std::chrono::milliseconds(std::uint64_t(std::max(CheckFloorSeconds, checkSeconds) * 1000));
        Look(player, spellId, where, radius, Now() + std::uint64_t(seconds * 1000), every, std::make_shared<Seen>());
    }
} // namespace DC::Combat::Crusader::Hold
