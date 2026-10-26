/*
 * World of DiabloCraft - touch-up of the survey in game (monster spawning S4,
 * docs/proposals/monster-spawning.md 3.5.3).
 *
 * The pure half of `.dc anchor` and `.dc area`: which anchor is near, what to number a new one, and the SQL each edit
 * sends to the dev world database. No server types, so tests/rift_touchup/harness.cpp compiles this very file and a
 * test runs its statements on a scratch copy of rift_survey_0001.sql; dc_rift_touchup.cpp is the glue (the player's
 * position, the markers, the transaction, the reload).
 *
 * Every edit marks the area it touches `source = 'alex'`, a removal included: generate_rift_survey.py --survey refuses
 * to run over sheets that hold such a row, so a removed anchor is not brought back by a new survey, and --export writes
 * the edits into the committed sheets.
 *
 * Internal to the rifts folder.
 */

#ifndef DC_RIFT_TOUCHUP_H
#define DC_RIFT_TOUCHUP_H

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace DC::Rifts::TouchUp
{
    struct AnchorRow
    {
        unsigned id = 0, area = 0;
        double x = 0, y = 0, z = 0, o = 0;
    };
    struct AreaRow
    {
        unsigned id = 0;
        char tag = 'S';
        bool hasDensity = false, nospawn = false;
        unsigned densityMin = 0, densityMax = 0, natives = 0;
    };

    inline double Distance(AnchorRow const& a, double x, double y, double z)
    {
        return std::sqrt((a.x - x) * (a.x - x) + (a.y - y) * (a.y - y) + (a.z - z) * (a.z - z));
    }

    // The rows within `yards` of the point, nearest first (ties by id, so the order is the same every time).
    inline std::vector<AnchorRow> Around(std::vector<AnchorRow> rows, double x, double y, double z, double yards)
    {
        rows.erase(
            std::remove_if(rows.begin(), rows.end(), [&](AnchorRow const& a) { return Distance(a, x, y, z) > yards; }),
            rows.end());
        std::sort(rows.begin(), rows.end(),
                  [&](AnchorRow const& a, AnchorRow const& b)
                  {
                      double const da = Distance(a, x, y, z), db = Distance(b, x, y, z);
                      return da != db ? da < db : a.id < b.id;
                  });
        return rows;
    }

    // The nearest row, or -1 for none.
    inline int Nearest(std::vector<AnchorRow> const& rows, double x, double y, double z)
    {
        int best = -1;
        for (std::size_t i = 0; i < rows.size(); ++i)
            if (best < 0 || Distance(rows[i], x, y, z) < Distance(rows[best], x, y, z))
                best = static_cast<int>(i);
        return best;
    }

    inline unsigned NextAnchorId(std::vector<AnchorRow> const& rows)
    {
        unsigned top = 0;
        for (AnchorRow const& a : rows)
            top = std::max(top, a.id);
        return top + 1;
    }
    inline unsigned NextAreaId(std::vector<AreaRow> const& rows)
    {
        unsigned top = 0;
        for (AreaRow const& a : rows)
            top = std::max(top, a.id);
        return top + 1;
    }

    // S, M or L in either case; 0 for anything else.
    inline char ParseTag(std::string const& word)
    {
        if (word.size() != 1)
            return 0;
        char const c = static_cast<char>(word[0] & ~0x20);
        return c == 'S' || c == 'M' || c == 'L' ? c : 0;
    }

    // A dungeon name or any text as an SQL string. The text only ever comes from the survey's own sheet, but a name
    // with an apostrophe must not end the string.
    inline std::string Quote(std::string const& text)
    {
        std::string out = "'";
        for (char c : text)
        {
            if (c == '\'' || c == '\\')
                out += '\\';
            out += c;
        }
        return out + "'";
    }

    inline std::string Number(double value)
    {
        char buffer[48];
        std::snprintf(buffer, sizeof buffer, "%.4f", value);
        return buffer;
    }

    inline std::string Where(std::string const& dungeon, char const* key, unsigned id)
    {
        return " WHERE `dungeon` = " + Quote(dungeon) + " AND `" + key + "` = " + std::to_string(id);
    }

    inline std::string Touch(std::string const& dungeon, unsigned area)
    {
        return "UPDATE `dc_rift_area` SET `source` = 'alex'" + Where(dungeon, "area", area);
    }

    // A new anchor at a point, in an existing area or in a new one. A new area starts tagged S (the smallest) and is
    // for the GM to tag. `walk` is the distance from the dungeon's entry point (negative: unknown, stored as NULL).
    inline std::vector<std::string> AddAnchor(std::string const& dungeon, unsigned id, unsigned area, bool newArea,
                                              double x, double y, double z, double o, double walk)
    {
        std::vector<std::string> out;
        if (newArea)
            out.push_back("INSERT INTO `dc_rift_area` (`dungeon`, `area`, `tag`, `natives`, `density_min`, "
                          "`density_max`, `nospawn`, `source`) VALUES (" +
                          Quote(dungeon) + ", " + std::to_string(area) + ", 'S', 0, NULL, NULL, 0, 'alex')");
        out.push_back("INSERT INTO `dc_rift_anchor` (`dungeon`, `anchor`, `area`, `x`, `y`, `z`, `o`, `pack_size`, "
                      "`native_guid`, `native_entry`, "
                      "`entry_walk_yards`, `source`) VALUES (" +
                      Quote(dungeon) + ", " + std::to_string(id) + ", " + std::to_string(area) + ", " + Number(x) +
                      ", " + Number(y) + ", " + Number(z) + ", " + Number(o) + ", 1, NULL, NULL, " +
                      (walk < 0 ? "NULL" : Number(walk)) + ", 'alex')");
        out.push_back(Touch(dungeon, area));
        return out;
    }

    inline std::vector<std::string> MoveAnchor(std::string const& dungeon, unsigned id, unsigned area, double x,
                                               double y, double z, double o, double walk)
    {
        return {"UPDATE `dc_rift_anchor` SET `x` = " + Number(x) + ", `y` = " + Number(y) + ", `z` = " + Number(z) +
                    ", `o` = " + Number(o) + ", `entry_walk_yards` = " + (walk < 0 ? "NULL" : Number(walk)) +
                    ", `source` = 'alex'" + Where(dungeon, "anchor", id),
                Touch(dungeon, area)};
    }

    // A removed anchor takes its place off the sheet. A stock patrol path tied to it is tied to the nearest anchor
    // left, by the path's first point, as the survey ties them (3.5.1 step 7); the caller has checked that one is left.
    inline std::vector<std::string> RemoveAnchor(std::string const& dungeon, unsigned id, unsigned area)
    {
        std::string const d = Quote(dungeon);
        return {"UPDATE `dc_rift_route` r SET r.`anchor` = (SELECT a.`anchor` FROM `dc_rift_anchor` a WHERE "
                "a.`dungeon` = r.`dungeon` AND "
                "a.`anchor` <> " +
                    std::to_string(id) +
                    " ORDER BY POW(a.`x` - r.`start_x`, 2) + POW(a.`y` - r.`start_y`, 2) + "
                    "POW(a.`z` - r.`start_z`, 2), a.`anchor` LIMIT 1), r.`source` = 'alex' WHERE r.`dungeon` = " +
                    d + " AND r.`anchor` = " + std::to_string(id),
                "DELETE FROM `dc_rift_anchor`" + Where(dungeon, "anchor", id), Touch(dungeon, area)};
    }

    inline std::vector<std::string> SetTag(std::string const& dungeon, unsigned area, char tag)
    {
        return {"UPDATE `dc_rift_area` SET `tag` = '" + std::string(1, tag) + "', `source` = 'alex'" +
                Where(dungeon, "area", area)};
    }

    // The area's own anchor count, or `clear` for the tag's default (NULL both).
    inline std::vector<std::string> SetDensity(std::string const& dungeon, unsigned area, bool clear, unsigned low,
                                               unsigned high)
    {
        return {"UPDATE `dc_rift_area` SET `density_min` = " + (clear ? std::string("NULL") : std::to_string(low)) +
                ", `density_max` = " + (clear ? std::string("NULL") : std::to_string(high)) + ", `source` = 'alex'" +
                Where(dungeon, "area", area)};
    }

    inline std::vector<std::string> SetNospawn(std::string const& dungeon, unsigned area, bool on)
    {
        return {"UPDATE `dc_rift_area` SET `nospawn` = " + std::string(on ? "1" : "0") + ", `source` = 'alex'" +
                Where(dungeon, "area", area)};
    }

    // One line of `.dc anchor show` for an area: its tag and what it will fill.
    inline std::string DescribeArea(AreaRow const& area, std::size_t anchors)
    {
        std::string text = "area " + std::to_string(area.id) + ": tag " + std::string(1, area.tag) + ", " +
                           std::to_string(anchors) + " anchors, " + std::to_string(area.natives) +
                           " natives when surveyed, density ";
        text += area.hasDensity ? std::to_string(area.densityMin) + " to " + std::to_string(area.densityMax) + " (set)"
                                : "the tag's default";
        return text + (area.nospawn ? ", NOSPAWN" : "");
    }
} // namespace DC::Rifts::TouchUp

#endif // DC_RIFT_TOUCHUP_H
