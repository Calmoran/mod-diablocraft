// Drives the production rules of src/items/dc_legendary_gem_item.h.
//   "slot <socket_slots> <base_slot>"            prints 1 or 0
//   "counted <n> <gem_id> <rank> ..."            prints "<gem_id>:<rank>,..." (sorted by gem_id) or "-"
//   "worn <n> <gem_id> <item> <seq> ... <asked gem_id> <m> <leaving item>... <replaced item> <replaced seq>"
//                                                prints the item that already holds the asked gem, or "-"
#include "dc_legendary_gem_item.h"

#include <cstdio>
#include <fstream>
#include <string>

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::string command;
    while (in >> command)
    {
        if (command == "slot")
        {
            std::string slots, base;
            in >> slots >> base;
            std::printf("%d\n", DC::LegendaryGemItem::SlotAllowed(slots, base) ? 1 : 0);
        }
        else if (command == "counted")
        {
            unsigned n;
            in >> n;
            std::vector<DC::LegendaryGemItem::Socketed> worn(n);
            for (auto& gem : worn)
                in >> gem.gemId >> gem.rank;
            auto counted = DC::LegendaryGemItem::Counted(worn);
            if (counted.empty())
                std::printf("-");
            for (std::size_t i = 0; i < counted.size(); ++i)
                std::printf("%s%s:%u", i ? "," : "", counted[i].gemId.c_str(), counted[i].rank);
            std::printf("\n");
        }
        else if (command == "worn")
        {
            unsigned n;
            in >> n;
            std::vector<DC::LegendaryGemItem::WornGem> worn(n);
            for (auto& gem : worn)
                in >> gem.gemId >> gem.item >> gem.seq;
            std::string asked;
            unsigned m;
            in >> asked >> m;
            std::vector<std::uint64_t> leaving(m);
            for (auto& item : leaving)
                in >> item;
            std::uint64_t replacedItem;
            unsigned replacedSeq;
            in >> replacedItem >> replacedSeq;
            std::optional<std::pair<std::uint64_t, unsigned>> replaced;
            if (replacedItem)
                replaced = std::make_pair(replacedItem, replacedSeq);
            auto const* found = DC::LegendaryGemItem::WornCopy(worn, asked, leaving, replaced);
            if (found)
                std::printf("%llu\n", static_cast<unsigned long long>(found->item));
            else
                std::printf("-\n");
        }
        else
            return 3;
    }
    return 0;
}
