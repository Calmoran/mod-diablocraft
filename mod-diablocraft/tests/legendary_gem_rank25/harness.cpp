// Drives the production group D math of src/combat/dc_gem_power_math.h (the rank-25 bonuses, part 10b-4) with the
// number rows the generator emitted.
//   "row <gem_id> <base> <per_rank> <max|none> <base2|none> <per2|none> <fixed1|none> <fixed2|none> <fixed3|none>
//        <rank25_1|none> <rank25_2|none>"
//   "case <n> <gem_id> <rank> ..."  prints the 21 rank-25 numbers Resolve() gives, in the order of the FIELDS list of the test
//   "wanted <n> <gem_id> <rank> ... <gogok> <taeguk> <bleeding> <wreath 0|1> <below 0|1> <base0..base4>"
//        prints Wanted(): gogok Attack Speed, gogok Cooldown, taeguk Armor, frenzy Attack Speed, wreath Movement
//        Speed, elite damage, then the five resistances
//   "factors <n> <gem_id> <rank> ... <boss 0|1>"
//        prints: EliteIncomingFactor(elite), EliteIncomingFactor(not elite), WeakenedFactor, VictimTakesMorePct,
//        StandaloneFactor with no buff and the target a boss, then not a boss (Stricken's, 3 attacks)
//   "shield <n> <gem_id> <rank> ... <armed 0|1> <quietMs> <lifePerSecond>"  prints: ShieldDue, ShieldAmount
//   "chance <pct> <roll>"  prints ChanceHits
//   "same <a> <b>"         prints whether two Sheeted that differ only in eliteDamage by (b - a) compare equal
#include "combat/dc_gem_power_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <optional>
#include <string>

static std::optional<double> Cell(std::string const& text)
{
    if (text == "none")
        return std::nullopt;
    return std::stod(text);
}

namespace GP = DC::Combat::GemPower;

static GP::Powers Read(std::istream& in, std::map<std::string, DC::LegendaryGem::Row> const& rows)
{
    unsigned n;
    in >> n;
    std::vector<DC::LegendaryGemItem::Socketed> worn(n);
    for (auto& gem : worn)
        in >> gem.gemId >> gem.rank;
    auto const active = DC::LegendaryGemItem::Counted(worn);
    return GP::Resolve(active, [&](std::string const& id) -> DC::LegendaryGem::Row const* {
        auto it = rows.find(id);
        return it == rows.end() ? nullptr : &it->second;
    });
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::map<std::string, DC::LegendaryGem::Row> rows;
    std::string command;
    while (in >> command)
    {
        if (command == "row")
        {
            DC::LegendaryGem::Row row;
            std::string cells[8];
            in >> row.id >> row.base >> row.perRank;
            for (auto& cell : cells)
                in >> cell;
            row.name = row.id;
            if (auto v = Cell(cells[0]))
                row.maxRank = static_cast<uint32_t>(*v);
            row.base2 = Cell(cells[1]);
            row.perRank2 = Cell(cells[2]);
            for (int i = 0; i < 3; ++i)
                row.fixed[i] = Cell(cells[3 + i]);
            row.rank25[0] = Cell(cells[6]);
            row.rank25[1] = Cell(cells[7]);
            rows[row.id] = row;
        }
        else if (command == "case")
        {
            GP::Powers const p = Read(in, rows);
            std::printf("%.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %d %.9g %.9g %.9g %.9g %.9g %.9g %.9g "
                        "%.9g %.9g\n",
                        p.powerfulEliteDamagePct, p.powerfulEliteDefencePct, p.strickenBossPct, p.trappedYards,
                        p.trappedSlowPct, p.esotericBelowLifePct, p.esotericResistPct, p.toxinTakenPct, p.toxinDealtPct,
                        p.gogokCooldownPerStack, p.iceblinkCritPct, p.controlImmune ? 1 : 0, p.mirinaeEverySeconds,
                        p.wildebeestQuietSeconds, p.wildebeestShieldPct, p.moratoriumClearChancePct, p.painFrenzyPct,
                        p.painFrenzyYards, p.simplicityHealPct, p.taegukArmorPctPerStack, p.wreathMovePct);
        }
        else if (command == "wanted")
        {
            GP::Powers const p = Read(in, rows);
            GP::Dynamic now;
            int wreath, below;
            in >> now.gogok >> now.taeguk >> now.bleeding >> wreath >> below;
            for (double& base : now.resistBase)
                in >> base;
            now.wreath = wreath != 0;
            now.belowLife = below != 0;
            GP::Sheeted const w = GP::Wanted(p, now);
            std::printf("%.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g\n", w.gogokAttackSpeed, w.gogokCooldown,
                        w.taegukArmor, w.frenzyAttackSpeed, w.wreathMovement, w.eliteDamage, w.resist[0], w.resist[1],
                        w.resist[2], w.resist[3], w.resist[4]);
        }
        else if (command == "factors")
        {
            GP::Powers const p = Read(in, rows);
            std::printf("%.9g %.9g %.9g %.9g %.9g %.9g\n", GP::EliteIncomingFactor(p, true),
                        GP::EliteIncomingFactor(p, false), GP::WeakenedFactor(p), GP::VictimTakesMorePct(p),
                        GP::StandaloneFactor(p, false, false, 3, 0.0, true),
                        GP::StandaloneFactor(p, false, false, 3, 0.0, false));
        }
        else if (command == "shield")
        {
            GP::Powers const p = Read(in, rows);
            int armed;
            std::uint32_t quiet;
            double lps;
            in >> armed >> quiet >> lps;
            std::printf("%d %.9g\n", GP::ShieldDue(p, armed != 0, quiet) ? 1 : 0, GP::ShieldAmount(p, lps));
        }
        else if (command == "chance")
        {
            double pct, roll;
            in >> pct >> roll;
            std::printf("%d\n", GP::ChanceHits(pct, roll) ? 1 : 0);
        }
        else if (command == "same")
        {
            double a, b;
            in >> a >> b;
            GP::Sheeted x, y;
            x.eliteDamage = a;
            y.eliteDamage = b;
            x.resist[3] = a;
            y.resist[3] = b;
            std::printf("%d\n", x == y ? 1 : 0);
        }
    }
    return 0;
}
