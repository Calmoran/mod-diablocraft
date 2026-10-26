// Pylons and shrines P2 (diablocraft-eok78): Conduit's pick and Greater Rift strike and Speed's knock-up test, through
// the real src/combat/dc_pylon_math.h (ConduitPick, GreaterStrike, ConduitDamage, KnocksUp); scripts/tests/rifts/test_pylon_conduit_speed.py
// builds and drives it. One wearer's strike memory lives across the lines of one run.
//   "pulse <now ms> <rehit ms> <cap> <monster>..."   one Conduit pulse over the monsters found (ids, in order); prints
//                                                    the ids struck
//   "greater <life> <elite> <min> <max> <roll>"       prints the Greater Rift strike's share
//   "strike <greater> <skill hit> <share> <boss> <boss factor>"   prints what the strike deals
//   "knock <moving> <guardian> <rooted>"             prints 1 when the monster is thrown
#include "../../src/combat/dc_pylon_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::Pylons;

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::map<int, std::uint32_t> last;
    std::string line;
    while (std::getline(in, line))
    {
        std::istringstream words(line);
        std::string verb;
        words >> verb;
        if (verb == "pulse")
        {
            std::uint32_t now = 0;
            double rehit = 0, cap = 0;
            words >> now >> rehit >> cap;
            std::vector<int> near;
            for (int id; words >> id;)
                near.push_back(id);
            std::string out;
            for (std::size_t index : ConduitPick(near, last, now, rehit, cap))
                out += (out.empty() ? "" : " ") + std::to_string(near[index]);
            std::printf("%s\n", out.c_str());
        }
        else if (verb == "greater")
        {
            double life = 0, elite = 0, low = 0, high = 0, roll = 0;
            words >> life >> elite >> low >> high >> roll;
            std::printf("%.6f\n", GreaterStrike(life, elite, low, high, roll));
        }
        else if (verb == "strike")
        {
            int greater = 0, boss = 0;
            double skill = 0, share = 0, factor = 0;
            words >> greater >> skill >> share >> boss >> factor;
            std::printf("%.6f\n", ConduitDamage(greater != 0, skill, share, boss != 0, factor));
        }
        else if (verb == "knock")
        {
            int moving = 0, guardian = 0, rooted = 0;
            words >> moving >> guardian >> rooted;
            std::printf("%d\n", KnocksUp(moving, guardian, rooted) ? 1 : 0);
        }
        else
            return 3;
    }
    return 0;
}
