// Drives the production planner (src/rifts/dc_rift_spawn.h) with the generated sheets (test_rift_spawn.py writes them as
// tab-separated lines) and prints what it plans for each `run` line. No game code, no rolls of its own.
#include "dc_rift_spawn.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>

using namespace DC::Rifts::Spawn;

static std::vector<std::string> Split(std::string const& line)
{
    std::vector<std::string> out;
    std::stringstream stream(line);
    std::string cell;
    while (std::getline(stream, cell, '\t'))
        out.push_back(cell);
    return out;
}

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    Sheets sheets;
    Knobs knobs;
    std::map<std::string, Survey> dungeons;
    std::map<std::string, unsigned> monsterIndex;
    Survey* current = nullptr;
    std::ifstream input(argv[1]);
    std::string line;
    while (std::getline(input, line))
    {
        auto f = Split(line);
        if (f.empty())
            continue;
        if (f[0] == "monster")
        {
            Monster m;
            m.name = f[1], m.entry = std::stoul(f[2]), m.family = f[3], m.solo = f[5] == "1", m.wanderYards = std::stod(f[6]);
            if (!RoleOf(f[4], m.role))
            {
                std::cerr << "role " << f[4] << "\n";
                return 3;
            }
            monsterIndex[m.name] = static_cast<unsigned>(sheets.monsters.size());
            sheets.monsters.push_back(m);
        }
        else if (f[0] == "set")
        {
            MonsterSet s;
            s.id = std::stoul(f[1]), s.weight = std::stod(f[2]), s.nephalem = f[3] == "1", s.greater = f[4] == "1", s.name = f[5];
            sheets.sets.push_back(s);
        }
        else if (f[0] == "member")
        {
            for (auto& s : sheets.sets)
                if (s.id == std::stoul(f[1]))
                    s.members.push_back(monsterIndex.at(f[2]));
        }
        else if (f[0] == "sfam")
        {
            for (auto& s : sheets.sets)
                if (s.id == std::stoul(f[1]))
                    s.families.push_back({f[2], std::stod(f[3]), f[4] == "1"});
        }
        else if (f[0] == "recipe")
        {
            Recipe r;
            unsigned size = f[1] == "small" ? Small : f[1] == "medium" ? Medium : f[1] == "large" ? Large : Patrol;
            r.bodies = {static_cast<unsigned>(std::stoul(f[3])), static_cast<unsigned>(std::stoul(f[4]))};
            for (unsigned role = 0; role < RoleCount; ++role)
                r.role[role] = {static_cast<unsigned>(std::stoul(f[5 + 2 * role])), static_cast<unsigned>(std::stoul(f[6 + 2 * role]))};
            sheets.recipes[{size, f[2] == "-" ? "" : f[2]}] = r;
        }
        else if (f[0] == "area_default")
        {
            AreaDefault& d = sheets.defaults[TagIndex(f[1][0])];
            d.anchors = {static_cast<unsigned>(std::stoul(f[2])), static_cast<unsigned>(std::stoul(f[3]))};
            d.size[Small] = f[4] == "1", d.size[Medium] = f[5] == "1", d.size[Large] = f[6] == "1";
        }
        else if (f[0] == "knob")
        {
            double v = std::stod(f[2]);
            if (f[1] == "elite_chance_pct") knobs.elitePct = v;
            else if (f[1] == "elite_champion_pct") knobs.championPct = v;
            else if (f[1] == "solo_share_pct") knobs.soloPct = v;
            else if (f[1] == "patrol_share_pct") knobs.patrolPct = v;
            else if (f[1] == "cluster_radius_small_yards") knobs.radiusSmallYards = v;
            else if (f[1] == "entry_clear_yards") knobs.entryClearYards = v;
            else if (f[1] == "cluster_min_spacing_yards") knobs.minSpacingYards = v;
            else if (f[1] == "elite_packs_min") knobs.eliteMin = static_cast<unsigned>(v);
            else if (f[1] == "elite_packs_max") knobs.eliteMax = static_cast<unsigned>(v);
            else if (f[1] == "floor_body_cap") knobs.bodyCap = static_cast<unsigned>(v);
            else if (f[1] == "champion_pack_size") knobs.championPack = static_cast<unsigned>(v);
            else if (f[1] == "rare_minions_max") knobs.rareMinionsMax = static_cast<unsigned>(v);
            else if (f[1] == "horde_multiplier") knobs.hordeMultiplier = static_cast<unsigned>(v);
        }
        else if (f[0] == "dungeon")
        {
            current = &dungeons[f[1]];
            current->name = f[1];
        }
        else if (f[0] == "area")
        {
            Area a;
            a.id = std::stoul(f[1]), a.tag = f[2][0], a.hasDensity = f[3] != "-1", a.nospawn = f[5] == "1";
            if (a.hasDensity)
                a.density = {static_cast<unsigned>(std::stoul(f[3])), static_cast<unsigned>(std::stoul(f[4]))};
            current->areas.push_back(a);
        }
        else if (f[0] == "anchor")
        {
            Anchor a;
            a.id = std::stoul(f[1]), a.area = std::stoul(f[2]), a.x = std::stof(f[3]), a.y = std::stof(f[4]), a.z = std::stof(f[5]);
            a.o = std::stof(f[6]);
            a.hasWalk = f[7] != "-1";
            a.entryWalk = a.hasWalk ? std::stod(f[7]) : 0;
            current->anchors.push_back(a);
        }
        else if (f[0] == "route")
        {
            // route <path> <anchor> <x> <y> <z>
            Route r;
            r.path = std::stoul(f[1]), r.anchor = std::stoul(f[2]), r.x = std::stof(f[3]), r.y = std::stof(f[4]), r.z = std::stof(f[5]);
            current->routes.push_back(r);
        }
        else if (f[0] == "run")
        {
            // run <dungeon> <greater 0|1> <seed> <floor> <previous set id>
            Rng rng(std::stoull(f[3]), std::stoull(f[4]));
            int const set = PickSet(sheets, f[2] == "1", static_cast<unsigned>(std::stoul(f[5])), rng);
            FloorPlan plan = PlanFloor(sheets, set, dungeons.at(f[1]), knobs, rng);
            std::printf("RUN\t%s\t%s\t%s\t%s\t%s\n", f[1].c_str(), f[2].c_str(), f[3].c_str(), f[4].c_str(), f[5].c_str());
            std::printf("SET\t%d\n", set < 0 ? 0 : static_cast<int>(sheets.sets[set].id));
            for (Placement const& p : plan.placements)
            {
                std::string names;
                for (unsigned m : p.monsters)
                    names += (names.empty() ? "" : "|") + sheets.monsters[m].name;
                std::printf("P\t%u\t%s\t%u\t%s\t%u\t%s\t%s\t%s\n", p.anchor, p.kind == Kind::Solo ? "solo" : p.kind == Kind::Patrol ? "patrol" : "cluster",
                            static_cast<unsigned>(p.size), p.family.c_str(), static_cast<unsigned>(p.elite),
                            p.elite == Elite::None ? "-" : sheets.monsters[p.leader].name.c_str(), names.c_str(),
                            p.kind == Kind::Patrol ? std::to_string(p.route).c_str() : "");
                for (Spot const& s : p.spots)
                    std::printf("S\t%u\t%.4f\t%.4f\n", p.anchor, s.dx, s.dy);
            }
            std::printf("PAT\t%u\n", plan.patrols);
            std::printf("SUM\t%u\t%u\t%u\t%u\t%u\n", plan.clusters, plan.solos, plan.elitePacks, plan.bodies, plan.cutByCap);
        }
    }
    return 0;
}
