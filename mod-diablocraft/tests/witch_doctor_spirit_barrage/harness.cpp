// The real dc_witch_doctor_spirit_barrage.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_witch_doctor_spirit_barrage.py); nothing is typed in here but levels and distances to try. Prints
// "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_spirit_barrage.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor::SpiritBarrage;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

int main(int argc, char** argv)
{
    // argv: the five runes A to E, the bolts, their total damage, the delay until a hit, the base gap and its delta,
    // the sheet's Life a hit, Well of Souls' spirits, its buff seconds and fire rate, Manitou's total damage, seconds
    // and tick, the most barrages.
    if (argc < 19)
        return 2;
    std::string const phlebotomize = argv[1], well = argv[2], phantasm = argv[3], willing = argv[4], manitou = argv[5];
    unsigned const bolts = unsigned(std::atoi(argv[6])), spirits = unsigned(std::atoi(argv[12])),
                   most = unsigned(std::atoi(argv[18]));
    double const total = std::atof(argv[7]), hit = std::atof(argv[8]), gap = std::atof(argv[9]),
                 delta = std::atof(argv[10]), life = std::atof(argv[11]), buff = std::atof(argv[13]),
                 rate = std::atof(argv[14]), spectre = std::atof(argv[15]), spectreSeconds = std::atof(argv[16]),
                 spectreTick = std::atof(argv[17]);

    expect(RuneOf(phlebotomize) == Rune::Phlebotomize && RuneOf(well) == Rune::WellOfSouls &&
               RuneOf(phantasm) == Rune::Phantasm && RuneOf(willing) == Rune::TheSpiritIsWilling &&
               RuneOf(manitou) == Rune::Manitou,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {phlebotomize, well, phantasm, willing, manitou})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Only Well of Souls' extra spirits take the rune's Fire; the barrage's bolts stay Cold.
    expect(!BoltTakesRuneElement(Rune::WellOfSouls) && BoltTakesRuneElement(Rune::Phlebotomize) &&
               BoltTakesRuneElement(Rune::Manitou) && BoltTakesRuneElement(Rune::None),
           "only Well of Souls' bolts keep the skill's element");

    // The bolts share the total, and land one after another from the delay until a hit.
    expect(bolts > 1 && std::fabs(BoltPct(total, bolts) * bolts - total) < 1e-9, "the bolts make the total damage",
           BoltPct(total, bolts) * bolts, total);
    expect(BoltPct(total, 0) == 0, "no bolts, no damage");
    expect(BoltLandsMs(0, hit, gap, delta) == std::uint32_t(hit * 1000.0 + 0.5),
           "the first bolt lands after the delay until a hit", double(BoltLandsMs(0, hit, gap, delta)), hit * 1000.0);
    expect(BoltLandsMs(1, hit, gap, delta) == std::uint32_t((hit + gap) * 1000.0 + 0.5), "the second a gap later",
           double(BoltLandsMs(1, hit, gap, delta)), (hit + gap) * 1000.0);
    expect(BoltLandsMs(3, hit, gap, delta) == std::uint32_t((hit + 3 * gap + delta * (0 + 1 + 2)) * 1000.0 + 0.5),
           "each later gap is longer by the delta", double(BoltLandsMs(3, hit, gap, delta)),
           (hit + 3 * gap + 3 * delta) * 1000.0);
    expect(BoltLandsMs(2, hit, gap, delta) > BoltLandsMs(1, hit, gap, delta), "the bolts land in order");

    // Phlebotomize: the sheet's Life is the level-70 number; a lower level returns less.
    expect(std::fabs(LevelLife(life, 70) - life) < 1e-9, "the sheet's Life at level 70", LevelLife(life, 70), life);
    expect(LevelLife(life, 60) < LevelLife(life, 70) && LevelLife(life, 60) > 0, "less Life at a lower level",
           LevelLife(life, 60), life);
    expect(LevelLife(life, 99) == LevelLife(life, 70), "a level past the table reads the last row");

    // Well of Souls: the sheet's spirits, one every fire rate while the buff lasts, never more.
    expect(WellSpirits(spirits, buff, rate) == spirits, "the sheet's spirits fly", WellSpirits(spirits, buff, rate),
           spirits);
    expect(WellSpirits(spirits + 5, buff, rate) <= unsigned(std::floor(buff / rate + 1e-9)) + 1,
           "no more than the buff lasts for");
    expect(WellSpirits(spirits, buff, 0) == 0, "no fire rate, no spirits");
    expect(WellFliesMs(0, rate) == 0 && WellFliesMs(2, rate) == std::uint32_t(2 * rate * 1000.0 + 0.5),
           "a spirit every fire rate", double(WellFliesMs(2, rate)), 2 * rate * 1000.0);

    // Manitou: the bolts of the spectre together deal the sheet's damage.
    unsigned const ticks = unsigned(std::floor(spectreSeconds / spectreTick + 1e-9));
    expect(ticks > 1 && std::fabs(SpectreBoltPct(spectre, spectreSeconds, spectreTick) * ticks - spectre) < 1e-6,
           "the spectre's bolts make the damage", SpectreBoltPct(spectre, spectreSeconds, spectreTick) * ticks,
           spectre);
    expect(SpectreBoltPct(spectre, spectreSeconds, 0) == 0, "no tick, no bolts");

    // Barrages in the air.
    expect(MayBombard(most - 1, most) && !MayBombard(most, most) && !MayBombard(most + 3, most),
           "no more barrages than the most", most, 0);
    expect(MayBombard(1000, 0), "no limit, none refused");

    // Well of Souls' spirits seek enemies other than the one aimed at, within the radius.
    std::vector<double> const field = {0, 9, 41, 12, 40};
    auto others = Others(field, 0, 40);
    expect(others.size() == 3 && others[0] == 1 && others[1] == 3 && others[2] == 4,
           "the others within reach, not the aimed one", double(others.size()), 3);
    expect(Others(field, none, 40).size() == 4, "no aimed enemy, every one within reach",
           double(Others(field, none, 40).size()), 4);
    expect(Others({0}, 0, 40).empty(), "a lone enemy has no others");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
