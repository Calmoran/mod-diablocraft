// Drives the production group C math of src/combat/dc_gem_power_math.h and dc_proc_math.h with the number rows the
// generator emitted.
//   "row <gem_id> <base> <per_rank> <max|none> <base2|none> <per2|none> <fixed1|none> <fixed2|none> <fixed3|none>
//        <rank25_1|none> <rank25_2|none>"
//   "case <n> <gem_id> <rank> ..."  prints: mirinae pct/chance/heal, wreath pct/chance/seconds, pain pct/seconds,
//        toxin pct/seconds, stagger pct/seconds, zei stun chance/seconds, boyarsky taunt seconds, iceblink slow
//   "ticks <totalPct> <seconds> <periodMs>"  prints: the ticks and each tick's weapon damage %
//   "split <staggerPct> <damage>"            prints: the damage dealt now and the damage put off
//   "pool <n> <amount> <seconds> <startMs> ... <m> <t1> ... <tm>"
//        n debts put off at their own moment, then Pay() at each of the m times in order; prints what each paid and
//        what is still owed at the end
//   "chance <coefficient|none> <basePct>"    prints: ChancePct, and the hit rate of 200000 Rolls
#include "combat/dc_gem_power_math.h"
#include "combat/dc_proc_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <optional>
#include <random>
#include <string>

static std::optional<double> Cell(std::string const& text)
{
    if (text == "none")
        return std::nullopt;
    return std::stod(text);
}

int main(int argc, char** argv)
{
    namespace GP = DC::Combat::GemPower;
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
            unsigned n;
            in >> n;
            std::vector<DC::LegendaryGemItem::Socketed> worn(n);
            for (auto& gem : worn)
                in >> gem.gemId >> gem.rank;
            auto const active = DC::LegendaryGemItem::Counted(worn);
            auto const p = GP::Resolve(active, [&](std::string const& id) -> DC::LegendaryGem::Row const* {
                auto it = rows.find(id);
                return it == rows.end() ? nullptr : &it->second;
            });
            std::printf("%.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g\n",
                        p.mirinaePct, p.mirinaeChancePct, p.mirinaeHealPct, p.wreathPct, p.wreathChancePct,
                        p.wreathSeconds, p.painPct, p.painSeconds, p.toxinPct, p.toxinSeconds, p.staggerPct,
                        p.staggerSeconds, p.zeiStunChancePct, p.zeiStunSeconds, p.boyarskyTauntSeconds,
                        p.iceblinkSlowPct);
        }
        else if (command == "ticks")
        {
            double total, seconds, period;
            in >> total >> seconds >> period;
            std::printf("%u %.9g\n", GP::Ticks(seconds, period), GP::TickPct(total, seconds, period));
        }
        else if (command == "split")
        {
            GP::Powers p;
            double damage, owed = 0;
            in >> p.staggerPct >> damage;
            double const now = GP::StaggerSplit(p, damage, owed);
            std::printf("%.9g %.9g\n", now, owed);
        }
        else if (command == "pool")
        {
            unsigned n, m;
            in >> n;
            GP::StaggerPool pool;
            for (unsigned i = 0; i < n; ++i)
            {
                double amount, seconds;
                uint32_t start;
                in >> amount >> seconds >> start;
                pool.Add(amount, seconds, start);
            }
            in >> m;
            for (unsigned i = 0; i < m; ++i)
            {
                uint32_t t;
                in >> t;
                std::printf("%.9g ", pool.Pay(t));
            }
            std::printf("%.9g\n", pool.Owed());
        }
        else if (command == "chance")
        {
            std::string coefficientText;
            double base;
            in >> coefficientText >> base;
            std::optional<double> const coefficient = Cell(coefficientText);
            std::mt19937_64 engine(20261006);
            std::uniform_real_distribution<double> draw(0.0, 100.0);
            auto roll = [&](float pct) { return pct > float(draw(engine)); };
            int hits = 0;
            constexpr int rolls = 200000;
            for (int i = 0; i < rolls; ++i)
                hits += DC::Combat::Proc::Rolls(coefficient, base, roll) ? 1 : 0;
            std::printf("%.9g %d\n", DC::Combat::Proc::ChancePct(coefficient, base), hits);
        }
    }
    return 0;
}
