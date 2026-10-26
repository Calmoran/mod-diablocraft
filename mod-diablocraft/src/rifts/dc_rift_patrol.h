/*
 * World of DiabloCraft - recording a patrol route (monster spawning S5, docs/proposals/monster-spawning.md 3.6, 4.11).
 *
 * Hand-recorded routes: `.dc patrol record start` samples where the GM walks, `.dc patrol record stop` ties the walk to the
 * nearest anchor of the dungeon and writes it as a stock waypoint_data path (the same table the 516 stock patrol paths
 * are in) plus a dc_rift_route row with source 'alex'. The pure half is here, header-only and std-only so
 * tests/rift_patrol compiles it as it stands: the sampling rule, the anchor tie, the next path id and the SQL. The
 * command and the sampler are dc_rift_patrol.cpp's.
 *
 * Ids: his paths live in waypoint_data.id RouteFirst..RouteLast, above every stock path (the highest stock id is
 * 53,004,760). generate_rift_patrols.py owns the same range (it deletes only inside it) and has its own copy of the two
 * numbers; the test holds them equal.
 */

#ifndef DC_RIFT_PATROL_H
#define DC_RIFT_PATROL_H

#include "dc_rift_spawn.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace DC::Rifts::Patrol
{
    constexpr std::uint32_t RouteFirst = 900000000, RouteLast = 999999999;

    struct Point
    {
        float x = 0, y = 0, z = 0;
    };

    inline double Distance(Point const& a, Point const& b)
    {
        return std::sqrt(double(a.x - b.x) * (a.x - b.x) + double(a.y - b.y) * (a.y - b.y) +
                         double(a.z - b.z) * (a.z - b.z));
    }

    // The walk so far, on the one map it started on (a point from another map is no part of it: a leader walks
    // coordinates of its own map). The first point is where he started; a later one is kept when it is at least `step` yards
    // (straight line, height included) from the last one kept, so a long straight walk is a few points and a corner is
    // as many as it needs.
    class Recording
    {
    public:
        Recording(std::string dungeon, double stepYards, std::uint32_t mapId)
            : _dungeon(std::move(dungeon))
            , _step(stepYards)
            , _map(mapId)
        {
        }
        bool OnMap(std::uint32_t mapId) const
        {
            return mapId == _map;
        }
        // True when the point was kept; `mapId` is the map the player is on.
        bool Add(std::uint32_t mapId, Point const& point)
        {
            if (!OnMap(mapId))
                return false;
            if (!_points.empty() && !(Distance(_points.back(), point) >= _step))
                return false;
            _points.push_back(point);
            return true;
        }
        // Where he stopped is the route's last point, whatever the step: kept unless it is where the last one is.
        void Finish(std::uint32_t mapId, Point const& point)
        {
            if (!OnMap(mapId))
                return;
            if (_points.empty() || Distance(_points.back(), point) > 0.0)
                _points.push_back(point);
        }
        // A patrol walks from somewhere to somewhere: one point is not a route.
        bool Usable() const
        {
            return _points.size() >= 2;
        }
        std::string const& Dungeon() const
        {
            return _dungeon;
        }
        std::vector<Point> const& Points() const
        {
            return _points;
        }

    private:
        std::string _dungeon;
        double _step;
        std::uint32_t _map;
        std::vector<Point> _points;
    };

    // The anchor a route ties to: the nearest to its first point, in a straight line with the height included, the
    // lowest id on a tie. (The survey ties the stock paths by flat distance among the anchors within a floor's height;
    // a recording has no such number, and the straight line keeps a route off the anchor of a floor above it.) -1: the
    // dungeon has no anchor.
    inline int NearestAnchor(std::vector<Spawn::Anchor> const& anchors, Point const& point)
    {
        int best = -1;
        double bestDistance = 0;
        for (std::size_t i = 0; i < anchors.size(); ++i)
        {
            double const d = Distance({anchors[i].x, anchors[i].y, anchors[i].z}, point);
            if (best < 0 || d < bestDistance || (d == bestDistance && anchors[i].id < anchors[best].id))
                best = static_cast<int>(i), bestDistance = d;
        }
        return best;
    }

    // The next free path id given the highest in use anywhere in his range (0 when there is none yet); 0 when the range
    // is full.
    inline std::uint32_t NextPathId(std::uint32_t highestInUse)
    {
        std::uint64_t const next = highestInUse < RouteFirst ? RouteFirst : std::uint64_t(highestInUse) + 1;
        return next > RouteLast ? 0 : static_cast<std::uint32_t>(next);
    }

    inline double Length(std::vector<Point> const& points)
    {
        double sum = 0;
        for (std::size_t i = 1; i < points.size(); ++i)
            sum += Distance(points[i - 1], points[i]);
        return sum;
    }

    inline std::string Quote(std::string const& text)
    {
        std::string out = "'";
        for (char c : text)
        {
            if (c == '\'' || c == '\\')
                out += c;
            out += c;
        }
        return out + "'";
    }

    // The rows of one recorded route: its points as waypoint_data (numbered from 1, as `.wp add` does), then its
    // dc_rift_route row. All the other waypoint_data columns keep the table's defaults, which is what the generator
    // writes too. Coordinates to 4 places, the survey's own rounding for a route's start.
    inline std::vector<std::string> Statements(std::string const& dungeon, std::uint32_t path, unsigned anchor,
                                               std::vector<Point> const& points)
    {
        std::vector<std::string> out;
        char row[256];
        for (std::size_t i = 0; i < points.size(); ++i)
        {
            std::snprintf(row, sizeof row,
                          "INSERT INTO `waypoint_data` (`id`, `point`, `position_x`, `position_y`, `position_z`) "
                          "VALUES (%u, %zu, "
                          "%.4f, %.4f, %.4f)",
                          path, i + 1, points[i].x, points[i].y, points[i].z);
            out.push_back(row);
        }
        std::snprintf(row, sizeof row, ", %u, %u, %.4f, %.4f, %.4f, %zu, %.1f, 'alex')", path, anchor, points[0].x,
                      points[0].y, points[0].z, points.size(), Length(points));
        out.push_back(
            "INSERT INTO `dc_rift_route` (`dungeon`, `path_id`, `anchor`, `start_x`, `start_y`, `start_z`, `points`, "
            "`length_yards`, `source`) VALUES (" +
            Quote(dungeon) + row);
        return out;
    }
} // namespace DC::Rifts::Patrol

#endif // DC_RIFT_PATROL_H
