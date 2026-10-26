#include "../../../src/common/dc_tiers.h"
#include <iostream>
#include <limits>
#include <stdexcept>

int main()
{
    auto check = [](bool condition) { if (!condition) throw std::runtime_error("Difficulty rule failed"); };
    // Source-shaped fixtures; change thresholds to ensure no hidden level-60 rule.
    check(DC::MeetsTierUnlock({}, 1, 1));
    check(!DC::MeetsTierUnlock({0, 60, 0}, 59, 59));
    check(DC::MeetsTierUnlock({0, 60, 0}, 1, 60));
    check(!DC::MeetsTierUnlock({60, 0, 0}, 59, 70));
    check(DC::MeetsTierUnlock({60, 0, 0}, 60, 1));
    check(!DC::MeetsTierUnlock({62, 0, 0}, 60, 70));
    check(DC::MeetsTierUnlock({62, 0, 0}, 62, 1));
    check(!DC::MeetsTierUnlock({70, 0, 30}, 70, 70));
    check(DC::ScaledCreatureLife(100, 1, 1, 1) == 100);
    check(DC::ScaledCreatureLife(100, 85.90, 1, 1) == 8590);
    check(DC::ScaledCreatureLife(100, 85.90, 1.5, 1) == 12885);
    check(DC::ScaledCreatureLife(100, 85.90, 1.5, 2) == 25770);
    // 64-bit Life (diablocraft-12in): no 32-bit ceiling, 2^64 is the limit
    check(DC::ScaledCreatureLife(14154175, 138887.70, 4, 1) > 4294967295ull);
    check(DC::ScaledCreatureLife(100, 1e15, 1, 1) == 100000000000000000ull);
    for (double bad : {0.0, -1.0, std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN(), 1e18})
    {
        bool rejected = false;
        try { DC::ScaledCreatureLife(100, bad, 1, 1); } catch (std::out_of_range const&) { rejected = true; }
        check(rejected);
    }
    std::cout << "Unlock boundaries, tier/party/elite products and overflow checks passed\n";
}
