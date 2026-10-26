// The real dc_demon_hunter_rain_of_vengeance.h (and the DoT rules and the pick it uses). The rune names and numbers come from argv (read from
// the sheets and the tunables by test_demon_hunter_rain_of_vengeance.py); nothing is typed in here. Prints "cases=N" and exits 0, or names
// the first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_rain_of_vengeance.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::RainOfVengeance;

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

static bool near(double a, double b)
{
    return std::fabs(a - b) < 1e-6;
}

int main(int argc, char** argv)
{
    // argv: the five runes A to E, then the rain's total, seconds and tick, the cloud's total, seconds and storm interval, Anathema's total, seconds
    // and grenade interval, the delay, Flying Strike's flyers and total, Stampede's beasts, seconds and radius.
    if (argc < 21)
        return 2;
    std::string const shade = argv[1], cloud = argv[2], anathema = argv[3], flying = argv[4], stampede = argv[5];
    double const total = std::atof(argv[6]), seconds = std::atof(argv[7]), tick = std::atof(argv[8]), cloudTotal = std::atof(argv[9]),
                 cloudSeconds = std::atof(argv[10]), storm = std::atof(argv[11]), grenadeTotal = std::atof(argv[12]), grenadeSeconds = std::atof(argv[13]),
                 grenade = std::atof(argv[14]), delay = std::atof(argv[15]), flyerTotal = std::atof(argv[17]), waveSeconds = std::atof(argv[19]),
                 radius = std::atof(argv[20]);
    unsigned const flyers = unsigned(std::atoi(argv[16])), beasts = unsigned(std::atoi(argv[18]));

    expect(RuneOf(shade) == Rune::Shade && RuneOf(cloud) == Rune::DarkCloud && RuneOf(anathema) == Rune::Anathema &&
               RuneOf(flying) == Rune::FlyingStrike && RuneOf(stampede) == Rune::Stampede,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {shade, cloud, anathema, flying, stampede})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The rain, the cloud's storms and Anathema's grenades: how many fit, and the shares make each rune's total.
    unsigned const ticks = Count(seconds, tick), storms = Count(cloudSeconds, storm), grenades = Count(grenadeSeconds, grenade);
    expect(ticks > 1 && storms > 1 && grenades > 1, "each series has more than one", ticks, storms);
    expect(near(Share(total, ticks) * ticks, total) && near(Share(cloudTotal, storms) * storms, cloudTotal) && near(Share(grenadeTotal, grenades) * grenades, grenadeTotal),
           "the shares make the rune's total", Share(total, ticks) * ticks, total);
    expect(Share(total, 0) == 0 && Count(seconds, 0) == 0, "no interval, no series");
    expect(near(Share(flyerTotal, flyers) * flyers, flyerTotal) && near(Share(flyerTotal, flyers), flyerTotal / flyers), "Flying Strike's beasts share the total", Share(flyerTotal, flyers), flyerTotal / flyers);

    // When each lands: the delay all versions have, then an interval apart.
    expect(StartMs(0, delay, tick) == std::uint32_t(delay * 1000.0 + 0.5), "the first after the delay", StartMs(0, delay, tick), delay * 1000.0);
    expect(StartMs(ticks - 1, delay, tick) == std::uint32_t((delay + tick * (ticks - 1)) * 1000.0 + 0.5), "the last an interval each after the first");
    expect(StartMs(3, 0, 0) == 0 && StartMs(0, -1, -1) == 0, "no delay, no interval, at once");

    // A random place in the area: inside the disc whatever the rolls, even over it, the ends of the rolls at the edge and the middle.
    bool inside = true;
    for (int a = 0; a <= 20; ++a)
        for (int b = 0; b <= 20; ++b)
        {
            Spot spot = DiscPoint(100, -50, 30, a / 20.0, b / 20.0);
            inside = inside && std::hypot(spot.x - 100, spot.y + 50) <= 30 + 1e-9;
        }
    expect(inside, "every point is inside the disc");
    Spot middle = DiscPoint(100, -50, 30, 0.0, 0.3), edge = DiscPoint(100, -50, 30, 1.0, 0.0);
    expect(near(middle.x, 100) && near(middle.y, -50) && near(edge.x, 130) && near(edge.y, -50), "the least distance is the middle, the most the edge", edge.x, 130);
    int near_half = 0;
    for (int a = 0; a < 1000; ++a)
        near_half += DiscPoint(0, 0, 30, a / 1000.0, 0.0).x < 15 ? 1 : 0;
    expect(near_half > 200 && near_half < 300, "the distances are even over the area, a quarter inside half the radius", near_half, 250);

    // Stampede: the beasts spread evenly along the line to its end, the wave reaching each in turn over its seconds.
    expect(beasts > 1, "more than one beast", beasts, 2);
    Spot firstBeast = WavePoint(0, 0, 0.0, 0, beasts, 40), lastBeast = WavePoint(0, 0, 0.0, beasts - 1, beasts, 40), up = WavePoint(0, 0, 3.14159265358979323846 / 2, beasts - 1, beasts, 40);
    expect(near(firstBeast.x, 40.0 / beasts) && near(lastBeast.x, 40) && near(up.y, 40) && near(up.x, 0), "the beasts run to the end of the line", lastBeast.x, 40);
    expect(WavePoint(0, 0, 0.0, 0, 0, 40).x == 0, "no beasts, no distance");
    expect(WaveMs(beasts - 1, beasts, delay, waveSeconds) == std::uint32_t((delay + waveSeconds) * 1000.0 + 0.5), "the wave reaches the last beast at its end",
           WaveMs(beasts - 1, beasts, delay, waveSeconds), (delay + waveSeconds) * 1000.0);
    expect(WaveMs(0, beasts, delay, waveSeconds) > WaveMs(0, beasts, delay, 0) && WaveMs(1, beasts, delay, waveSeconds) > WaveMs(0, beasts, delay, waveSeconds), "later beasts, later times");
    expect(radius > 0, "the radius is a number", radius, 1);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
