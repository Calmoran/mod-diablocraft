/*
 * diablocraft-7oozd: a swap of two wells is one server step, so a refused half can never drop a skill.
 *
 * Runs the module's own DC::Classes::SwapSlots, cut out of src/classes/dc_classes.cpp by
 * scripts/tests/classes/test_swap_slots.py and included here as dc_swap_slots_extract.h, against the core doubles of
 * tests/swap_on_cooldown/swap_shim.h and a fake dc_character_skillbar table. The commit applies the statements the way
 * MySQL would, all of them or (when the harness says the database refuses) none.
 *
 * Output: one line per scenario, "PASS <name>" or "FAILED <name>", each failed check printed above it. Exit 1 when any
 * failed.
 */

#include "swap_shim.h"
#include "dc_swap_slots_extract.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <set>

namespace DC::Classes
{
    std::vector<Slot> fakeBar;
    unsigned barWrites = 0;

    bool Playable(Player const* player)
    {
        return player && player->wowClass != 0;
    }

    unsigned ActiveSlots()
    {
        return 6;
    }

    std::vector<Slot> Bar(Player*)
    {
        std::vector<Slot> bar = fakeBar;
        std::sort(bar.begin(), bar.end(), [](Slot const& a, Slot const& b) { return a.slot < b.slot; });
        return bar;
    }

    void WriteActionBar(Player*)
    {
        ++barWrites;
    }
} // namespace DC::Classes

namespace
{
    bool databaseRefuses = false;
    unsigned deletes = 0, inserts = 0;
} // namespace

Commit Database::AsyncCommitTransaction(CharacterDatabaseTransaction const& transaction)
{
    using DC::Classes::fakeBar;
    using DC::Classes::Slot;
    ++commits;
    std::promise<bool> promise;
    if (databaseRefuses)
    {
        promise.set_value(false);
        return Commit{promise.get_future()};
    }
    for (Transaction::Statement const& statement : transaction->statements)
    {
        auto const& a = statement.args;
        if (statement.format.rfind("DELETE FROM dc_character_skillbar WHERE guid={} AND slot IN", 0) == 0 &&
            a.size() == 3)
        {
            ++deletes;
            unsigned const first = std::stoul(a[1]), second = std::stoul(a[2]);
            fakeBar.erase(std::remove_if(fakeBar.begin(), fakeBar.end(),
                                         [&](Slot const& row) { return row.slot == first || row.slot == second; }),
                          fakeBar.end());
        }
        else if (statement.format.rfind("INSERT INTO dc_character_skillbar", 0) == 0 && a.size() == 6)
        {
            ++inserts;
            Slot row;
            row.slot = std::stoul(a[1]);
            row.skillId = std::stoul(a[2]);
            row.spellId = std::stoul(a[3]);
            row.skill = a[4];
            row.rune = a[5];
            fakeBar.push_back(row);
        }
        else
        {
            std::printf("FATAL: SwapSlots wrote a statement this harness does not know: %s\n",
                        statement.format.c_str());
            std::abort();
        }
    }
    promise.set_value(true);
    return Commit{promise.get_future()};
}

namespace
{
    using namespace DC::Classes;

    int failures = 0;
    bool scenarioFailed = false;

    void check(bool ok, char const* what)
    {
        if (!ok)
        {
            std::printf("  check failed: %s\n", what);
            scenarioFailed = true;
        }
    }

    // Four skills on slots 0 to 3 (Frenzy, Bash, Cleave, Whirlwind as base shells), slots 4 and 5 empty.
    void reset(Player& player)
    {
        player = Player();
        player.wowClass = 1;
        fakeBar.clear();
        barWrites = 0;
        deletes = inserts = 0;
        databaseRefuses = false;
        CharacterDatabase.commits = 0;
        struct Seed
        {
            char const* skill;
            char const* rune;
            std::uint32_t skillId, spellId;
        };
        Seed const seeds[] = {{"Frenzy", "", 11, 81000},
                              {"Bash", "Punish", 12, 81102},
                              {"Cleave", "", 13, 81003},
                              {"Whirlwind", "Dust Devils", 14, 81210}};
        for (unsigned slot = 0; slot < 4; ++slot)
        {
            Slot row;
            row.slot = slot;
            row.skillId = seeds[slot].skillId;
            row.spellId = seeds[slot].spellId;
            row.skill = seeds[slot].skill;
            row.rune = seeds[slot].rune;
            fakeBar.push_back(row);
        }
    }

    Slot const* in(unsigned slot)
    {
        auto found = std::find_if(fakeBar.begin(), fakeBar.end(), [slot](Slot const& row) { return row.slot == slot; });
        return found == fakeBar.end() ? nullptr : &*found;
    }

    std::multiset<std::uint32_t> skills()
    {
        std::multiset<std::uint32_t> ids;
        for (Slot const& row : fakeBar)
            ids.insert(row.skillId);
        return ids;
    }

    template<class Body>
    void scenario(char const* name, Body body)
    {
        scenarioFailed = false;
        Player player;
        reset(player);
        body(player);
        std::printf("%s %s\n", scenarioFailed ? "FAILED" : "PASS", name);
        failures += scenarioFailed ? 1 : 0;
    }
} // namespace

int main()
{
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    scenario("two_skills_trade_wells_in_one_step",
             [](Player& player)
             {
                 std::string error;
                 check(SwapSlots(&player, 0, 3, error), "the swap succeeds");
                 check(in(0) && in(0)->skillId == 14 && in(3) && in(3)->skillId == 11,
                       "each skill is in the other's well");
                 check(fakeBar.size() == 4, "no row is gained or lost");
                 check(CharacterDatabase.commits == 1 && deletes == 1 && inserts == 2,
                       "one transaction: one delete and two inserts");
                 check(barWrites == 1, "the action bar is written once");
             });

    scenario("a_skill_keeps_its_shell_and_names",
             [](Player& player)
             {
                 std::string error;
                 check(SwapSlots(&player, 1, 3, error), "the swap succeeds");
                 check(in(3) && in(3)->spellId == 81102 && in(3)->rune == "Punish" && in(3)->skill == "Bash",
                       "Bash keeps Punish");
                 check(in(1) && in(1)->spellId == 81210 && in(1)->rune == "Dust Devils", "Whirlwind keeps Dust Devils");
             });

    scenario("a_skill_moves_to_an_empty_well",
             [](Player& player)
             {
                 std::string error;
                 check(SwapSlots(&player, 2, 5, error), "the move succeeds");
                 check(in(5) && in(5)->skillId == 13 && !in(2), "Cleave is in well 6 and well 3 is empty");
                 check(fakeBar.size() == 4 && inserts == 1, "one insert");
             });

    scenario("an_empty_well_moves_nothing_to_a_full_one_the_other_way",
             [](Player& player)
             {
                 std::string error;
                 check(SwapSlots(&player, 5, 0, error), "the move succeeds either way round");
                 check(in(5) && in(5)->skillId == 11 && !in(0), "Frenzy is in well 6");
             });

    scenario("two_empty_wells_are_refused_and_write_nothing",
             [](Player& player)
             {
                 std::string error;
                 check(!SwapSlots(&player, 4, 5, error) && error == "Both slots are empty.", "refused with its line");
                 check(CharacterDatabase.commits == 0 && barWrites == 0 && fakeBar.size() == 4, "nothing written");
             });

    scenario("the_same_well_is_refused",
             [](Player& player)
             {
                 std::string error;
                 check(!SwapSlots(&player, 2, 2, error) && error == "Pick two different slots.",
                       "refused with its line");
                 check(CharacterDatabase.commits == 0, "nothing written");
             });

    scenario("a_well_past_the_bar_is_refused",
             [](Player& player)
             {
                 std::string error;
                 check(!SwapSlots(&player, 0, 6, error) && error == "Slots are 1 to 6.", "the well past the bar");
                 check(!SwapSlots(&player, 99, 1, error), "the well far past it");
                 check(CharacterDatabase.commits == 0, "nothing written");
             });

    scenario("combat_refuses_and_changes_nothing",
             [](Player& player)
             {
                 std::string error;
                 player.inCombat = true;
                 check(!SwapSlots(&player, 0, 1, error) && error == "Not in combat.", "refused with its line");
                 check(in(0) && in(0)->skillId == 11 && in(1) && in(1)->skillId == 12 && CharacterDatabase.commits == 0 && barWrites == 0,
                       "the bar is as it was");
             });

    scenario("an_instance_refuses_and_changes_nothing",
             [](Player& player)
             {
                 std::string error;
                 player.map.instanceable = true;
                 check(!SwapSlots(&player, 0, 1, error) && error == "Not inside an instance or rift.",
                       "refused with its line");
                 check(in(0) && in(0)->skillId == 11 && CharacterDatabase.commits == 0, "the bar is as it was");
             });

    scenario("a_class_with_no_skills_is_refused",
             [](Player& player)
             {
                 std::string error;
                 player.wowClass = 0;
                 check(!SwapSlots(&player, 0, 1, error) && error == "This class has no Diablocraft skills.",
                       "refused with its line");
                 check(CharacterDatabase.commits == 0, "nothing written");
             });

    scenario("a_refused_save_leaves_both_skills_on_the_bar",
             [](Player& player)
             {
                 std::string error;
                 databaseRefuses = true;
                 check(!SwapSlots(&player, 0, 1, error) && error == "The skill bar could not be saved.",
                       "refused with its line");
                 check(in(0) && in(0)->skillId == 11 && in(1) && in(1)->skillId == 12 && fakeBar.size() == 4,
                       "both skills are where they were");
                 check(barWrites == 0, "the action bar is not rewritten");
             });

    scenario("a_skill_on_cooldown_swaps_like_any_other",
             [](Player& player)
             {
                 std::string error;
                 player.cooldownLeft[81000] = 5000;
                 player.cooldownLeft[81102] = 9000;
                 check(SwapSlots(&player, 0, 1, error), "nothing it casts changes, so nothing is refused");
                 check(in(0) && in(0)->skillId == 12 && in(1) && in(1)->skillId == 11, "swapped");
             });

    scenario("no_swap_of_any_two_wells_ever_loses_a_skill",
             [](Player& player)
             {
                 std::string error;
                 auto const before = skills();
                 for (unsigned from = 0; from < 6; ++from)
                     for (unsigned to = 0; to < 6; ++to)
                     {
                         SwapSlots(&player, from, to, error);
                         check(skills() == before, "the skills on the bar are the same");
                     }
                 std::set<unsigned> slots;
                 for (Slot const& row : fakeBar)
                     slots.insert(row.slot);
                 check(slots.size() == fakeBar.size(), "no two skills share a well");
             });

    return failures ? 1 : 0;
}
