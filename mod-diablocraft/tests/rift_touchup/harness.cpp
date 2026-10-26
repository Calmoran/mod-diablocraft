// Drives the production touch-up code (src/rifts/dc_rift_touchup.h) one tab-separated line at a time (test_rift_touchup.py writes them)
// and prints the answer, one tab-separated line per result. No game code, no choices of its own.
#include "dc_rift_touchup.h"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>

using namespace DC::Rifts::TouchUp;

static std::vector<std::string> Split(std::string const& line)
{
    std::vector<std::string> out;
    std::stringstream stream(line);
    std::string cell;
    while (std::getline(stream, cell, '\t'))
        out.push_back(cell);
    return out;
}

static void Statements(std::vector<std::string> const& sql)
{
    for (std::string const& statement : sql)
        std::cout << "SQL\t" << statement << "\n";
}

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    std::ifstream input(argv[1]);
    std::vector<AnchorRow> anchors;
    std::vector<AreaRow> areas;
    for (std::string line; std::getline(input, line);)
    {
        std::vector<std::string> c = Split(line);
        if (c.empty())
            continue;
        if (c[0] == "anchor") // anchor id area x y z o
            anchors.push_back({unsigned(std::stoul(c[1])), unsigned(std::stoul(c[2])), std::stod(c[3]), std::stod(c[4]), std::stod(c[5]), std::stod(c[6])});
        else if (c[0] == "area") // area id tag natives hasDensity min max nospawn
        {
            AreaRow row;
            row.id = unsigned(std::stoul(c[1])), row.tag = c[2][0], row.natives = unsigned(std::stoul(c[3])), row.hasDensity = c[4] == "1",
            row.densityMin = unsigned(std::stoul(c[5])), row.densityMax = unsigned(std::stoul(c[6])), row.nospawn = c[7] == "1";
            areas.push_back(row);
        }
        else if (c[0] == "nearest") // nearest x y z
            std::cout << "NEAREST\t" << Nearest(anchors, std::stod(c[1]), std::stod(c[2]), std::stod(c[3])) << "\n";
        else if (c[0] == "around") // around x y z yards
        {
            std::cout << "AROUND";
            for (AnchorRow const& row : Around(anchors, std::stod(c[1]), std::stod(c[2]), std::stod(c[3]), std::stod(c[4])))
                std::cout << "\t" << row.id;
            std::cout << "\n";
        }
        else if (c[0] == "next")
            std::cout << "NEXT\t" << NextAnchorId(anchors) << "\t" << NextAreaId(areas) << "\n";
        else if (c[0] == "tag") // tag word
            std::cout << "TAG\t" << int(ParseTag(c.size() > 1 ? c[1] : "")) << "\n";
        else if (c[0] == "quote")
            std::cout << "QUOTE\t" << Quote(c.size() > 1 ? c[1] : "") << "\n";
        else if (c[0] == "describe") // describe area-id anchors
        {
            for (AreaRow const& row : areas)
                if (row.id == unsigned(std::stoul(c[1])))
                    std::cout << "DESCRIBE\t" << DescribeArea(row, std::stoul(c[2])) << "\n";
        }
        else if (c[0] == "add") // add dungeon id area new x y z o walk
            Statements(AddAnchor(c[1], unsigned(std::stoul(c[2])), unsigned(std::stoul(c[3])), c[4] == "1", std::stod(c[5]), std::stod(c[6]),
                                 std::stod(c[7]), std::stod(c[8]), std::stod(c[9])));
        else if (c[0] == "move") // move dungeon id area x y z o walk
            Statements(MoveAnchor(c[1], unsigned(std::stoul(c[2])), unsigned(std::stoul(c[3])), std::stod(c[4]), std::stod(c[5]), std::stod(c[6]),
                                  std::stod(c[7]), std::stod(c[8])));
        else if (c[0] == "remove") // remove dungeon id area
            Statements(RemoveAnchor(c[1], unsigned(std::stoul(c[2])), unsigned(std::stoul(c[3]))));
        else if (c[0] == "settag") // settag dungeon area tag
            Statements(SetTag(c[1], unsigned(std::stoul(c[2])), c[3][0]));
        else if (c[0] == "density") // density dungeon area clear low high
            Statements(SetDensity(c[1], unsigned(std::stoul(c[2])), c[3] == "1", unsigned(std::stoul(c[4])), unsigned(std::stoul(c[5]))));
        else if (c[0] == "nospawn") // nospawn dungeon area on
            Statements(SetNospawn(c[1], unsigned(std::stoul(c[2])), c[3] == "1"));
        else
            return 3;
    }
    return 0;
}
