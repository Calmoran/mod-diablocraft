// Offline harness for the 06-loot roll maths. It exercises the pure functions in
// src/loot/dc_loot.h against the real loot_tuning.csv, so the distribution can be
// checked without a running server. It does NOT test delivery, the buffer, gold,
// currencies or the hooks - those need a Player and are verified in game.

#include "../../../src/loot/dc_loot.h"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace DC::Loot;

void Check(bool ok, char const* message) { if (!ok) throw std::runtime_error(message); }

// Minimal CSV reader: loot_tuning.csv quotes its notes column, nothing else.
std::vector<std::string> Fields(std::string const& line)
{
    std::vector<std::string> out;
    std::string field;
    bool quoted = false;
    for (char c : line)
    {
        if (quoted)
        {
            if (c == '"') quoted = false; else field += c;
        }
        else if (c == '"') quoted = true;
        else if (c == ',') { out.push_back(field); field.clear(); }
        else field += c;
    }
    out.push_back(field);
    return out;
}

std::map<std::string, Tuning> ReadTuning(char const* path)
{
    std::ifstream input(path);
    Check(input.is_open(), "Could not open loot_tuning.csv");
    std::string line;
    Check(static_cast<bool>(std::getline(input, line)), "loot_tuning.csv is empty");
    std::vector<std::string> const header = Fields(line);
    auto column = [&](char const* name)
    {
        for (std::size_t i = 0; i < header.size(); ++i)
            if (header[i] == name) return i;
        throw std::runtime_error(std::string("loot_tuning.csv has no column ") + name);
    };
    std::size_t const cSource = column("source"), cMin = column("drops_min"), cMax = column("drops_max");
    std::size_t const cLeg = column("legendary_base_pct"), cNormal = column("normal_pct");
    std::size_t const cMagic = column("magic_pct"), cRare = column("rare_pct");
    std::size_t const cChest = column("chest_multiplier"), cBreath = column("deaths_breath_pct");

    std::map<std::string, Tuning> rows;
    while (std::getline(input, line))
    {
        if (line.empty()) continue;
        std::vector<std::string> const f = Fields(line);
        Check(f.size() == header.size(), "loot_tuning.csv row has the wrong field count");
        if (f[cMin].empty()) continue; // gem/identify rows are parameters, not drop sources.
        Tuning tuning;
        tuning.dropsMin = static_cast<unsigned>(std::stoul(f[cMin]));
        tuning.dropsMax = static_cast<unsigned>(std::stoul(f[cMax]));
        tuning.legendaryBasePct = std::stod(f[cLeg]);
        tuning.normalPct = std::stod(f[cNormal]);
        tuning.magicPct = std::stod(f[cMagic]);
        tuning.rarePct = std::stod(f[cRare]);
        tuning.chestMultiplier = std::stod(f[cChest]);
        tuning.deathsBreathPct = std::stod(f[cBreath]);
        rows[f[cSource]] = tuning;
    }
    return rows;
}

struct Counts { unsigned normal = 0, magic = 0, rare = 0, legendary = 0, drops = 0; };

// One kill: drop count, then per drop a legendary check and otherwise a split.
Counts Simulate(Tuning const& tuning, unsigned kills, double tierLegendaryPct, double magicFind,
                std::mt19937_64& engine)
{
    std::uniform_real_distribution<double> roll(0.0, 1.0);
    double const legendaryPct = LegendaryChancePct(tuning, tierLegendaryPct, 0.0, magicFind);
    Counts counts;
    for (unsigned kill = 0; kill < kills; ++kill)
    {
        unsigned const drops = DropCount(tuning, Source::Normal, roll(engine));
        counts.drops += drops;
        for (unsigned index = 0; index < drops; ++index)
        {
            if (roll(engine) * 100.0 < legendaryPct) { ++counts.legendary; continue; }
            switch (PickNonLegendary(tuning, magicFind, roll(engine)))
            {
                case Rarity::Rare:  ++counts.rare;  break;
                case Rarity::Magic: ++counts.magic; break;
                default:            ++counts.normal; break;
            }
        }
    }
    return counts;
}

void Report(char const* label, Counts const& counts)
{
    double const total = counts.drops ? counts.drops : 1;
    std::cout << std::fixed << std::setprecision(1)
              << label << ": " << counts.drops << " drops - "
              << counts.normal << " normal (" << 100.0 * counts.normal / total << "%), "
              << counts.magic << " magic (" << 100.0 * counts.magic / total << "%), "
              << counts.rare << " rare (" << 100.0 * counts.rare / total << "%), "
              << counts.legendary << " legendary (" << 100.0 * counts.legendary / total << "%)\n";
}

int main(int argc, char** argv)
{
    try
    {
        Check(argc == 2, "Pass the loot_tuning.csv path");
        std::map<std::string, Tuning> const tuning = ReadTuning(argv[1]);
        for (char const* source : {"normal", "elite", "boss", "rift_guardian", "chest"})
            Check(tuning.count(source) == 1, "loot_tuning.csv is missing a source row");

        Tuning const& normal = tuning.at("normal");
        Tuning const& elite = tuning.at("elite");

        // Invariants the doc fixes (L6, and the MF efficiencies of 06 §2 step 2).
        Check(normal.normalPct + normal.magicPct + normal.rarePct == 100.0, "L6 split must total 100");
        Check(DropCount(normal, Source::Normal, 0.0) == 1 && DropCount(normal, Source::Normal, 0.99) == 1,
              "L6: a normal kill drops exactly one item");
        Check(DropCount(elite, Source::Elite, 0.0) == 3 && DropCount(elite, Source::Elite, 0.99) == 5,
              "L6: an elite pack drops 3-5");
        Check(DropCount(tuning.at("chest"), Source::Chest, 0.0) == 2, "Chest multiplier must scale the count");
        Check(PickNonLegendary(normal, 0.0, 0.0) == Rarity::Normal, "The bottom of the range is Normal");
        Check(PickNonLegendary(normal, 0.0, 0.99) == Rarity::Rare, "The top of the range is Rare");
        // Magic Find moves mass out of Normal and into Magic and Rare.
        Check(PickNonLegendary(normal, 3.0, 0.55) != Rarity::Normal, "300% MF must shrink the Normal band");
        // 10% legendary efficiency: 300% MF is +30% relative, not +300%.
        Check(std::abs(LegendaryChancePct(normal, 0, 0, 3.0) - normal.legendaryBasePct * 1.3) < 1e-9,
              "Magic Find is 10% efficient against legendaries");
        Check(std::abs(LegendaryChancePct(normal, 131.0, 0, 0.0) - normal.legendaryBasePct * 2.31) < 1e-9,
              "Tier legendary bonus is applied as a percentage");
        Check(RiftLegendaryBonusPct(4) == 25.0 && RiftLegendaryBonusPct(5) == 44.0, "L2 rift bonus lookup");

        // Stock hooks must leave every non-D3 store and phase alone. The same
        // source predicate is used by the item, equal-chance and money gates.
        Check(SuppressStockLoot(StockSource::Creature, true, 1, 10, false), "tier-one creature is D3");
        Check(SuppressStockLoot(StockSource::Chest, true, 10, 10, false), "tier-ten chest is D3");
        Check(SuppressStockLoot(StockSource::Creature, false, 1, 10, true), "live rift creature is D3");
        Check(!SuppressStockLoot(StockSource::Creature, false, 1, 10, false), "stock dungeon creature stays native");
        Check(!SuppressStockLoot(StockSource::Chest, true, 11, 10, false), "outside-tier chest stays native");
        Check(!SuppressStockLoot(StockSource::Other, true, 1, 10, true), "other stores stay native even in a rift");
        Check(D3ChestTemplate(true, true, true), "party treasure chest is a D3 source");
        Check(!D3ChestTemplate(false, true, true), "non-party resource is not a D3 chest");
        Check(!D3ChestTemplate(true, true, false), "gathering lock is not a D3 chest");
        Check(!D3ChestTemplate(true, false, true), "empty template is not a D3 chest");

        // 50 normal kills at Normal (tier 1, +0%) and at Torment VI (tier 10,
        // +131%), both at 0% Magic Find, from dc_difficulty_tiers.
        std::mt19937_64 engine(20260906);
        Report("50 normal kills, Normal (tier bonus +0%)", Simulate(normal, 50, 0.0, 0.0, engine));
        Report("50 normal kills, Torment VI (tier bonus +131%)", Simulate(normal, 50, 131.0, 0.0, engine));
        // 50 kills is far too few to see a 0.1% legendary rate, so also report a
        // large sample that shows the tier bonus actually moving the rate.
        Report("200000 normal kills, Normal", Simulate(normal, 200000, 0.0, 0.0, engine));
        Report("200000 normal kills, Torment VI", Simulate(normal, 200000, 131.0, 0.0, engine));

        std::cout << "loot maths OK\n";
        return 0;
    }
    catch (std::exception const& error)
    {
        std::cerr << "FAILED: " << error.what() << "\n";
        return 1;
    }
}
