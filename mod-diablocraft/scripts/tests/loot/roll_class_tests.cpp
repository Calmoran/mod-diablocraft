// Offline harness for diablocraft-class-roll-rules. It compiles the production
// header src/items/dc_roll_class.h - the functions dc_loot.cpp, dc_items.cpp and
// dc_identify.cpp call - and drives them with what the generators emit, which
// scripts/tests/loot/test_class_roll_rules.py extracts into TSV files:
//
//   argv[1] classes.tsv  class_id \t class_key          (generated dc_class_map)
//   argv[2] bases.tsv    usable_by \t designated_class \t set_class \t rarity \t source_set_class
//                        \t pool_version \t craft_only  (every generated dc_base_item row; the loader keeps
//                        the ones DC::RollClass::InDropPool admits; source_set_class is D3Planner's own)
//   argv[3] skills.tsv   group_id \t affix_id \t class_id  (items_0012_skill_affix_classes.sql)
//   argv[4] the loot/smart_loot_off_class_pct value      (generated tunables_0001.sql)
//
// It does NOT test delivery, the database columns or the hooks; those need a
// Player and are the GM steps in docs/test-class-roll-rules.md.

#include "dc_roll_class.h"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
    unsigned failures = 0;

    void Check(bool ok, std::string const& message)
    {
        if (!ok)
        {
            std::cerr << "FAILED: " << message << "\n";
            ++failures;
        }
    }

    std::vector<std::vector<std::string>> Rows(char const* path, std::size_t columns)
    {
        std::ifstream input(path);
        if (!input)
            throw std::runtime_error(std::string("cannot open ") + path);
        std::vector<std::vector<std::string>> rows;
        std::string line;
        while (std::getline(input, line))
        {
            if (!line.empty() && line.back() == '\r')
                line.pop_back();
            std::vector<std::string> cells;
            std::string cell;
            std::istringstream fields(line);
            while (std::getline(fields, cell, '\t'))
                cells.push_back(cell);
            while (cells.size() < columns)
                cells.emplace_back();
            rows.push_back(cells);
        }
        return rows;
    }

    struct Base
    {
        std::string usable, designated, setClass, rarity, sourceClass, poolVersion, craftOnly;
    };
    struct Choice
    {
        std::string group, affix;
        unsigned classId = 0;
    };
} // namespace

int main(int argc, char** argv)
{
    try
    {
        if (argc != 5)
            throw std::runtime_error("usage: roll_class_tests classes.tsv bases.tsv skills.tsv off_class_pct");
        std::map<std::string, unsigned> ids;
        std::vector<std::string> playable;
        for (auto const& row : Rows(argv[1], 2))
        {
            ids[row[1]] = static_cast<unsigned>(std::stoul(row[0]));
            playable.push_back(row[1]);
        }
        std::vector<Base> bases;
        unsigned etherealRows = 0;
        for (auto const& row : Rows(argv[2], 7))
        {
            if (row[3] == "ethereal")
                ++etherealRows;
            // Exactly the rows the loot loader keeps (dc_loot.cpp LootWorld).
            if (DC::RollClass::InDropPool(row[3], row[5], row[6], "no")) // the cache-only rule: test_cache_only_legendaries.py
                bases.push_back({row[0], row[1], row[2], row[3], row[4], row[5], row[6]});
        }
        std::vector<Choice> skills;
        std::set<std::string> groups;
        for (auto const& row : Rows(argv[3], 3))
        {
            skills.push_back({row[0], row[1], static_cast<unsigned>(std::stoul(row[2]))});
            groups.insert(row[0]);
        }
        double const offPct = std::stod(argv[4]);
        Check(playable.size() >= 2, "the generated class map needs two playable classes to test an off-class roll");
        Check(offPct > 0 && offPct < 100, "smart_loot_off_class_pct must be a share");
        std::cout << std::fixed << std::setprecision(2) << "playable=" << playable.size() << " bases=" << bases.size()
                  << " skills=" << skills.size() << " off_class_pct=" << offPct << "\n";

        // Rule 1: the split, measured over a seeded run for every looter class.
        std::mt19937_64 engine(20260923);
        std::uniform_real_distribution<double> roll(0.0, 1.0);
        unsigned const draws = 200000;
        for (std::string const& looter : playable)
        {
            std::map<std::string, unsigned> seen;
            for (unsigned index = 0; index < draws; ++index)
                ++seen[DC::RollClass::Pick(looter, playable, offPct, roll(engine), roll(engine))];
            double const own = 100.0 * seen[looter] / draws;
            std::cout << "rule1 looter=" << looter << " own=" << own << "%";
            for (auto const& [key, count] : seen)
            {
                if (key == looter)
                    continue;
                std::cout << " " << key << "=" << 100.0 * count / draws << "%";
                Check(ids.count(key) != 0, "rule 1: an off-class roll chose a class that is not playable: " + key);
            }
            std::cout << "\n";
            Check(std::fabs(own - (100.0 - offPct)) < 0.5,
                  "rule 1: " + looter + " own-class share is not 100 - off_class_pct");
            for (std::string const& other : playable)
                if (other != looter)
                    Check(seen[other] > 0, "rule 1: " + looter + " never rolled off-class for " + other);
        }
        // A realm with one playable class has nobody else to roll for.
        Check(DC::RollClass::Pick(playable[0], {playable[0]}, offPct, 0.0, 0.0) == playable[0],
              "rule 1: with one playable class the looter's class must be kept");

        // Rule 2: every class's pool, off-class included, holds its class-only
        // items and never another class's. A class that owns no class-only item in the data yet (a
        // class whose weapons and sets have not landed) has none to hold: it is checked for foreign
        // items only, and at least two classes must own items so the rule is never proved over nothing.
        unsigned classesWithItems = 0;
        for (std::string const& rollClass : playable)
        {
            unsigned owned = 0;
            for (Base const& base : bases)
                owned += DC::RollClass::DropClass(base.designated, base.setClass) == rollClass;
            classesWithItems += owned > 0;
        }
        Check(classesWithItems >= 2, "rule 2: fewer than two classes own class-only items, so the rule proves nothing");
        for (std::string const& rollClass : playable)
        {
            unsigned eligible = 0, classOnly = 0, foreign = 0, owned = 0;
            for (Base const& base : bases)
            {
                owned += DC::RollClass::DropClass(base.designated, base.setClass) == rollClass;
                if (!DC::RollClass::DropEligible(base.usable, base.designated, base.setClass, rollClass))
                    continue;
                std::string const own = DC::RollClass::DropClass(base.designated, base.setClass);
                ++eligible;
                if (own == rollClass)
                    ++classOnly;
                else if (!own.empty())
                    ++foreign;
            }
            std::cout << "rule2 roll=" << rollClass << " eligible=" << eligible << " class_only=" << classOnly
                      << " owned=" << owned << "\n";
            Check(owned == 0 || classOnly > 0, "rule 2: " + rollClass + " rolls none of its class-only items");
            Check(foreign == 0, "rule 2: " + rollClass + " rolls another class's class-only items");
        }

        // Ethereals never drop (ruling q-1003-22, diablocraft-ethereal-no-drop). Every drop source -
        // kills, chests, the rift guardian, the first-kill legendary - picks its base from this one
        // pool, so a long run of the real pick for every roll class, off-class included, covers them all.
        unsigned superseded = 0, crafted = 0;
        for (Base const& base : bases)
        {
            superseded += base.poolVersion != "yes";
            crafted += base.craftOnly == "yes";
        }
        Check(superseded == 0, "pool rule 1: a superseded pool version is in the drop pool");
        Check(crafted == 0, "pool rule: a Blacksmith-crafted set is in the drop pool");
        Check(etherealRows > 0, "ethereal rule: the data holds no Ethereal, so this proves nothing");
        unsigned etherealPicked = 0, uniquePicks = 0;
        for (std::string const& rollClass : playable)
        {
            std::vector<std::size_t> pool;
            for (std::size_t index = 0; index < bases.size(); ++index)
                if (!bases[index].rarity.empty() &&
                    DC::RollClass::DropEligible(bases[index].usable, bases[index].designated, bases[index].setClass, rollClass))
                    pool.push_back(index);
            Check(!pool.empty(), "ethereal rule: " + rollClass + " has no unique base left to drop");
            for (unsigned index = 0; index < 200000 && !pool.empty(); ++index)
            {
                ++uniquePicks;
                if (bases[pool[static_cast<std::size_t>(roll(engine) * pool.size())]].rarity == "ethereal")
                    ++etherealPicked;
            }
        }
        std::cout << "ethereal rows=" << etherealRows << " unique_picks=" << uniquePicks << " ethereal_picked=" << etherealPicked << "\n";
        Check(etherealPicked == 0, "ethereal rule: an Ethereal dropped");

        // Rule 2 for sets (diablocraft-set-class-drop): the real rule, with the real 85/15
        // pick and the loot roller's uniform choice over what is eligible, run for every
        // looter class. On the looter's own roll no other class's set may ever drop, and
        // across the rolls the off-class share of the class-set drops is the tunable.
        // Classless sets (Cain's Destiny and the like) are everyone's and stay out of the share.
        unsigned setPieces = 0, classedPieces = 0, unplayablePieces = 0;
        std::set<std::string> setClassesSeen;
        for (Base const& base : bases)
            if (base.rarity == "set")
            {
                ++setPieces;
                std::string const own = base.sourceClass;
                Check(DC::RollClass::DropClass(base.designated, base.setClass) == own,
                      "set rule: a piece of a " + (own.empty() ? std::string("classless") : own) +
                          " set does not drop for its source class (drop class '" +
                          DC::RollClass::DropClass(base.designated, base.setClass) + "')");
                if (!own.empty())
                {
                    ++classedPieces;
                    setClassesSeen.insert(own);
                    // A set of a class that is not playable yet drops for nobody, like its designated pieces today.
                    if (ids.count(own) == 0)
                        ++unplayablePieces;
                }
                Check(base.designated.empty() || base.setClass.empty() || base.designated == base.setClass,
                      "set rule: a piece's designated_class and its set's class disagree");
            }
        std::cout << "sets pieces=" << setPieces << " with_class=" << classedPieces
                  << " classes=" << setClassesSeen.size() << " not_playable_yet=" << unplayablePieces << "\n";
        Check(classedPieces > 0, "set rule: no set piece carries a class; class sets drop for everyone");
        for (std::string const& looter : playable)
        {
            std::vector<std::vector<std::size_t>> pools;   // eligible set pieces per roll class
            std::map<std::string, std::size_t> poolOf;
            for (std::string const& rollClass : playable)
            {
                std::vector<std::size_t> pool;
                for (std::size_t index = 0; index < bases.size(); ++index)
                    if (bases[index].rarity == "set" &&
                        DC::RollClass::DropEligible(bases[index].usable, bases[index].designated, bases[index].setClass, rollClass))
                        pool.push_back(index);
                poolOf[rollClass] = pools.size();
                pools.push_back(pool);
            }
            // The off-class share the rule gives: the looter's own roll is 100 - offPct %, each other class
            // gets an equal part of offPct %, and a roll only yields a class-set drop in proportion to the
            // class pieces in that class's pool (a class with no set yet gives none, so its part is lost
            // from the class-set drops and the others' share falls with it).
            double ownWeight = 0.0, offWeight = 0.0;
            for (std::string const& rollClass : playable)
            {
                auto const& pool = pools[poolOf[rollClass]];
                unsigned pieces = 0;
                for (std::size_t index : pool)
                    pieces += !bases[index].sourceClass.empty();
                double const classedPart = pool.empty() ? 0.0 : static_cast<double>(pieces) / pool.size();
                if (rollClass == looter)
                    ownWeight += (100.0 - offPct) * classedPart;
                else
                    offWeight += offPct / (playable.size() - 1) * classedPart;
            }
            double const expected = ownWeight + offWeight > 0 ? 100.0 * offWeight / (ownWeight + offWeight) : 0.0;
            unsigned classed = 0, offClass = 0, ownRollForeign = 0;
            unsigned const setDraws = 400000;
            for (unsigned index = 0; index < setDraws; ++index)
            {
                std::string const rollClass = DC::RollClass::Pick(looter, playable, offPct, roll(engine), roll(engine));
                auto const& pool = pools[poolOf[rollClass]];
                if (pool.empty())
                    continue;
                Base const& base = bases[pool[static_cast<std::size_t>(roll(engine) * pool.size())]];
                std::string const& own = base.sourceClass;
                if (own.empty())
                    continue;
                ++classed;
                if (own != looter)
                {
                    ++offClass;
                    if (rollClass == looter)
                        ++ownRollForeign;
                }
            }
            double const share = classed ? 100.0 * offClass / classed : 0.0;
            std::cout << "rule2sets looter=" << looter << " class_set_drops=" << classed << " off_class=" << share
                      << "% expected=" << expected << "%\n";
            Check(ownRollForeign == 0, "set rule: " + looter + " got another class's set on its own roll");
            Check(std::fabs(share - expected) < 1.5,
                  "set rule: " + looter + "'s off-class share of class-set drops is not off_class_pct");
        }

        // Rule 3: one class per item. Every base a class can roll takes that
        // class for its main stat and skills, and every skill group offers that
        // class only its own skills.
        for (std::string const& rollClass : playable)
        {
            for (Base const& base : bases)
                if (DC::RollClass::DropEligible(base.usable, base.designated, base.setClass, rollClass))
                    Check(DC::RollClass::AffixClass(base.designated, rollClass) == rollClass,
                          "rule 3: a " + rollClass + " drop took another class's affixes");
            for (std::string const& group : groups)
            {
                std::vector<Choice> inGroup;
                for (Choice const& choice : skills)
                    if (choice.group == group)
                        inGroup.push_back(choice);
                auto const choices = DC::RollClass::ChoicesFor(inGroup, ids[rollClass]);
                std::cout << "rule3 roll=" << rollClass << " " << group << " choices=" << choices.size() << "\n";
                Check(!choices.empty(), "rule 3/6: " + rollClass + " has no " + group + " skill affix");
                for (Choice const& choice : choices)
                    Check(choice.affix.rfind("skill_" + rollClass + "_", 0) == 0,
                          "rule 3: " + rollClass + " was offered " + choice.affix);
            }
        }
        // A class-only item keeps its own class whatever class the roll names.
        Check(DC::RollClass::AffixClass(playable[1], playable[0]) == playable[1],
              "rule 3: a class-only item took the roll class");

        // Rule 4: the shell rolls its stored class, never another holder's.
        for (std::string const& stored : playable)
            for (std::string const& owner : playable)
                Check(DC::RollClass::ShellClass(stored, owner) == stored,
                      "rule 4: a shell stored as " + stored + " rolled for " + owner);
        Check(DC::RollClass::ShellClass("", playable[1]) == playable[1],
              "rule 4: a pre-migration shell must roll for the looter it dropped for");

        // Rule 5: the Mystic, each case.
        for (std::string const& reroller : playable)
        {
            Check(DC::RollClass::MysticClass("", reroller) == reroller,
                  "rule 5: an ordinary item must re-roll for " + reroller);
            for (std::string const& own : playable)
                Check(DC::RollClass::MysticClass(own, reroller) == own,
                      "rule 5: a " + own + "-only item re-rolled for " + reroller);
        }

        if (failures)
        {
            std::cerr << failures << " check(s) failed\n";
            return 1;
        }
        std::cout << "class roll rules OK\n";
        return 0;
    }
    catch (std::exception const& error)
    {
        std::cerr << "FAILED: " << error.what() << "\n";
        return 2;
    }
}
