// Drives the production hit arithmetic of src/combat/dc_damage_buckets.h (diablocraft-cy3o).
//   "hit <poolPct> <n> <pct1> ... <pctn>"  one hit with unit weapon/mainstat/skill/crit, an additive pool of poolPct percent
//     and n separate multipliers of those percents; prints the total.
#include "combat/dc_damage_buckets.h"

#include <cstdio>
#include <fstream>
#include <string>

int main(int argc, char** argv)
{
    using namespace DC::Combat;
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::string word;
    while (in >> word)
    {
        if (word != "hit")
            return 3;
        double pool;
        int n;
        in >> pool >> n;
        Factors factors;
        for (int i = 0; i < n; ++i)
        {
            double pct;
            in >> pct;
            AddFactor(factors, "x", pct);
        }
        std::printf("%.9f\n", Total(1, 1, 1, Additive(pool), 1, 1, 1, Product(factors), 1));
    }
    return 0;
}
