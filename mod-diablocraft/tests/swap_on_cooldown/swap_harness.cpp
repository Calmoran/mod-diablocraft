/*
 * diablocraft-7sh0 (the designer, "Wizard - Meteor Bug"): a skill that is on cooldown cannot
 * be changed - not swapped for another skill, not given another rune - until its
 * cooldown ends. A skill that is off cooldown swaps freely, whatever else is cooling.
 *
 * Runs the module's own SetSlot (and the catalogue lookups and data it stands on),
 * cut out of src/classes/dc_classes.cpp by scripts/tests/classes/test_swap_on_cooldown.py and
 * included here as dc_swap_extract.h, against the core doubles in swap_shim.h. The
 * catalogue is filled the way ClassWorld::OnStartup fills it, from the rows the
 * generator wrote (data/generated/class_catalogue.sql, handed over as a TSV), so the
 * skills, runes and ids below are the shipped ones, not hand-typed.
 *
 * Output: one line per scenario, "PASS <name>" or "FAILED <name>", each failed check
 * printed above it. Exit 1 when any scenario failed.
 */

#include "swap_shim.h"
#include "dc_swap_extract.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <tuple>

namespace DC::Classes
{
    // What the extracted code calls and lives in the same file as in production.

    std::vector<Slot> fakeBar; // the rows of dc_character_skillbar for the one test character
    unsigned barWrites = 0;    // how many times WriteActionBar ran

    unsigned ActiveSlots()
    {
        return 6; // D3's six; production reads combat/active_skill_slots from dc_tunables
    }

    std::vector<Slot> Bar(Player*)
    {
        // Production reads (slot, skill_id, spell_id) and names the row from the catalogue.
        std::vector<Slot> bar = fakeBar;
        for (Slot& entry : bar)
            std::tie(entry.skill, entry.rune) = LabelFor(entry.spellId);
        std::sort(bar.begin(), bar.end(), [](Slot const& a, Slot const& b) { return a.slot < b.slot; });
        return bar;
    }

    void WriteActionBar(Player*)
    {
        ++barWrites;
    }
} // namespace DC::Classes

// The two statements SetSlot commits, applied to the fake table the way MySQL would.
// Anything else is a statement this harness has not been told about: stop loudly.
Commit Database::AsyncCommitTransaction(CharacterDatabaseTransaction const& transaction)
{
    using DC::Classes::fakeBar;
    using DC::Classes::Slot;
    ++commits;
    for (Transaction::Statement const& statement : transaction->statements)
    {
        auto const& a = statement.args;
        if (statement.format.rfind("DELETE FROM dc_character_skillbar", 0) == 0 && a.size() == 3)
        {
            unsigned const slot = std::stoul(a[1]);
            std::uint32_t const skillId = std::stoul(a[2]);
            fakeBar.erase(std::remove_if(fakeBar.begin(), fakeBar.end(),
                                         [&](Slot const& row) { return row.slot == slot || row.skillId == skillId; }),
                          fakeBar.end());
        }
        else if (statement.format.rfind("INSERT INTO dc_character_skillbar", 0) == 0 && a.size() == 6)
        {
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
            std::printf("FATAL: SetSlot wrote a statement this harness does not know: %s\n", statement.format.c_str());
            std::abort();
        }
    }
    std::promise<bool> promise;
    promise.set_value(true);
    return Commit{promise.get_future()};
}

namespace DC::Classes
{
    namespace
    {
        // ---- the generated catalogue, loaded as ClassWorld::OnStartup loads it ---------

        struct Row
        {
            std::uint32_t classId = 0, skillId = 0, runeId = 0, spellId = 0;
            unsigned unlock = 0;
            std::string category, skill, rune;
        };

        std::vector<Row> rows; // the same rows, kept for the sweep's own grouping by skill_id

        std::vector<std::string> Split(std::string const& line)
        {
            std::vector<std::string> fields;
            std::size_t from = 0;
            for (;;)
            {
                std::size_t const tab = line.find('\t', from);
                if (tab == std::string::npos)
                {
                    fields.push_back(line.substr(from));
                    return fields;
                }
                fields.push_back(line.substr(from, tab - from));
                from = tab + 1;
            }
        }

        void Load(char const* path)
        {
            std::ifstream in(path);
            if (!in)
            {
                std::printf("FATAL: cannot read %s\n", path);
                std::abort();
            }
            std::string line;
            while (std::getline(in, line))
            {
                std::vector<std::string> const f = Split(line);
                if (f.size() == 3 && f[0] == "M") // M wow_class_id class_id
                {
                    classMap[static_cast<unsigned>(std::stoul(f[1]))] = static_cast<std::uint32_t>(std::stoul(f[2]));
                }
                else if (f.size() == 10 && f[0] == "C") // C class skill rune spell unlock indicator category skill rune
                {
                    CatalogueEntry entry;
                    entry.classId = std::stoul(f[1]);
                    entry.skillId = std::stoul(f[2]);
                    entry.runeId = std::stoul(f[3]);
                    entry.spellId = std::stoul(f[4]);
                    entry.unlockLevel = static_cast<unsigned>(std::stoul(f[5]));
                    entry.indicatorSpellId = std::stoul(f[6]);
                    entry.category = f[7];
                    catalogueById[entry.spellId] = entry;
                    labelById[entry.spellId] = {f[8], f[9]};
                    catalogue.emplace(std::make_pair(entry.classId, Key(f[8], f[9])), entry);
                    Row row;
                    row.classId = entry.classId;
                    row.skillId = entry.skillId;
                    row.runeId = entry.runeId;
                    row.spellId = entry.spellId;
                    row.unlock = entry.unlockLevel;
                    row.category = f[7];
                    row.skill = f[8];
                    row.rune = f[9];
                    rows.push_back(row);
                }
                else
                {
                    std::printf("FATAL: unreadable catalogue line: %s\n", line.c_str());
                    std::abort();
                }
            }
            if (classMap.empty() || catalogue.empty())
            {
                std::printf("FATAL: the catalogue is empty\n");
                std::abort();
            }
        }

        // ---- checks ---------------------------------------------------------------------

        std::string currentScenario;
        int failures = 0;
        int printed = 0;

        void Check(bool ok, std::string const& what)
        {
            if (ok)
                return;
            ++failures;
            if (printed++ < 6)
                std::printf("FAIL %s: %s\n", currentScenario.c_str(), what.c_str());
        }

        // One character: a Wizard (or a Barbarian) of level 100 out of combat, on an open map,
        // with a bar in the fake table and cooldowns in the fake cooldown map.
        struct World
        {
            Player player;
            std::string error;

            explicit World(unsigned wowClass = 8)
            {
                player.wowClass = wowClass;
                fakeBar.clear();
                barWrites = 0;
                CharacterDatabase.commits = 0;
            }

            // Ids come out of the module's own ShellFor, from the generated catalogue.
            void Resolve(std::string const& skill, std::string const& rune, std::uint32_t& skillId,
                         std::uint32_t& spellId)
            {
                if (!ShellFor(&player, skill, rune, skillId, spellId))
                {
                    std::printf("FATAL: no catalogue row for %s - %s\n", skill.c_str(), rune.c_str());
                    std::abort();
                }
            }

            std::uint32_t Shell(std::string const& skill, std::string const& rune = "")
            {
                std::uint32_t skillId = 0, spellId = 0;
                Resolve(skill, rune, skillId, spellId);
                return spellId;
            }

            void Put(unsigned slot, std::string const& skill, std::string const& rune = "")
            {
                Slot row;
                row.slot = slot;
                row.skill = skill;
                row.rune = rune;
                Resolve(skill, rune, row.skillId, row.spellId);
                fakeBar.push_back(row);
            }

            void Cool(std::uint32_t spellId, std::uint32_t milliseconds)
            {
                player.cooldownLeft[spellId] = milliseconds;
            }

            bool Set(unsigned slot, std::string const& skill, std::string const& rune = "")
            {
                error.clear();
                return SetSlot(&player, slot, skill, rune, error);
            }

            std::map<unsigned, std::uint32_t> Held() const // slot -> the shell the bar holds
            {
                std::map<unsigned, std::uint32_t> held;
                for (Slot const& row : fakeBar)
                    held[row.slot] = row.spellId;
                return held;
            }
        };

        // A refused change says why and changes nothing: not the saved bar, not the action bar.
        void ExpectRefused(World& w, unsigned slot, std::string const& skill, std::string const& rune,
                           std::string const& message)
        {
            std::vector<Slot> const saved = fakeBar;
            auto const before = w.Held();
            unsigned const commits = CharacterDatabase.commits, writes = barWrites;
            bool const ok = w.Set(slot, skill, rune);
            std::string const what =
                "slot " + std::to_string(slot + 1) + " -> " + skill + (rune.empty() ? "" : " - " + rune);
            Check(!ok, "refused: " + what);
            Check(w.error == message, "the refusal reads '" + message + "', got '" + w.error + "' (" + what + ")");
            Check(w.Held() == before, "the saved bar is unchanged (" + what + ")");
            Check(CharacterDatabase.commits == commits, "nothing is committed (" + what + ")");
            Check(barWrites == writes, "the action bar is not rewritten (" + what + ")");
            fakeBar = saved; // a scenario that went wrong must not poison the next step
        }

        void ExpectAllowed(World& w, unsigned slot, std::string const& skill, std::string const& rune)
        {
            unsigned const commits = CharacterDatabase.commits, writes = barWrites;
            bool const ok = w.Set(slot, skill, rune);
            std::string const what =
                "slot " + std::to_string(slot + 1) + " -> " + skill + (rune.empty() ? "" : " - " + rune);
            Check(ok, "allowed: " + what + " (said '" + w.error + "')");
            auto const held = w.Held();
            auto const at = held.find(slot);
            Check(at != held.end() && at->second == w.Shell(skill, rune),
                  "the slot holds the new shell (" + what + ")");
            Check(CharacterDatabase.commits == commits + 1, "one commit (" + what + ")");
            Check(barWrites == writes + 1, "the action bar is rewritten once (" + what + ")");
        }

        // ---- scenarios ------------------------------------------------------------------
        // Real Wizard names. Meteor - Molten Impact states a 15 s cooldown, Comet states none;
        // the harness sets the milliseconds itself, it does not depend on those numbers.

        void RuneSwapRefusedOnCooldown()
        {
            World w;
            w.Put(0, "Magic Missile");
            w.Put(2, "Meteor", "Molten Impact");
            w.Cool(w.Shell("Meteor", "Molten Impact"), 15000);
            ExpectRefused(w, 2, "Meteor", "Comet", "Meteor is on cooldown (15 s left).");
            ExpectRefused(w, 2, "Meteor", "", "Meteor is on cooldown (15 s left).");
            w.player.cooldownLeft.clear(); // the cooldown ended
            ExpectAllowed(w, 2, "Meteor", "Comet");
        }

        void SpellSwapRefusedOnCooldown()
        {
            World w;
            w.Put(0, "Magic Missile");
            w.Put(2, "Meteor", "Molten Impact");
            w.Cool(w.Shell("Meteor", "Molten Impact"), 9000);
            ExpectRefused(w, 2, "Frost Nova", "", "Meteor is on cooldown (9 s left).");
            ExpectRefused(w, 2, "Teleport", "Wormhole", "Meteor is on cooldown (9 s left).");
            w.player.cooldownLeft.clear();
            ExpectAllowed(w, 2, "Frost Nova", "");
        }

        // The cooldown belongs to the skill, not to the rune that was slotted when it started:
        // a sibling rune's remaining time blocks the skill too.
        void CooldownOnAnyRuneOfTheSkillCounts()
        {
            World w;
            w.Put(2, "Meteor", "Comet"); // the slotted rune has no cooldown of its own
            w.Cool(w.Shell("Meteor", "Molten Impact"), 7000);
            ExpectRefused(w, 2, "Meteor", "Star Pact", "Meteor is on cooldown (7 s left).");
            ExpectRefused(w, 2, "Frost Nova", "", "Meteor is on cooldown (7 s left).");
        }

        void TheLongestCooldownOfTheSkillIsQuoted()
        {
            World w;
            w.Put(2, "Meteor", "Molten Impact");
            w.Cool(w.Shell("Meteor", "Comet"), 11000);
            w.Cool(w.Shell("Meteor", "Molten Impact"), 3000);
            w.Cool(w.Shell("Meteor", "Star Pact"), 5000);
            ExpectRefused(w, 2, "Meteor", "Thunder Crash", "Meteor is on cooldown (11 s left).");
        }

        void OffCooldownSkillsSwapFreelyWhateverElseIsCooling()
        {
            World w;
            w.Put(0, "Magic Missile");
            w.Put(1, "Frost Nova", "Bone Chill");
            w.Put(2, "Meteor", "Molten Impact");
            w.Cool(w.Shell("Meteor", "Molten Impact"), 15000);
            ExpectAllowed(w, 1, "Frost Nova", "Shatter"); // a rune swap of a ready skill
            ExpectAllowed(w, 0, "Teleport", "");          // a spell swap of a ready skill
            ExpectAllowed(w, 1, "Hydra", "Frost Hydra");
            Check(w.Held().at(2) == w.Shell("Meteor", "Molten Impact"),
                  "the skill on cooldown is where it was, untouched");
        }

        // 04 K6 moves a skill that is already on the bar. A move that brings another rune is
        // still a rune swap of a skill on cooldown.
        void AMoveWithAnotherRuneIsARuneSwap()
        {
            World w;
            w.Put(2, "Meteor", "Molten Impact");
            w.Put(4, "Magic Missile");
            w.Cool(w.Shell("Meteor", "Molten Impact"), 15000);
            ExpectRefused(w, 4, "Meteor", "Comet", "Meteor is on cooldown (15 s left).");
        }

        // The slot's current skill is replaced, so it is checked even when the skill arriving is
        // a move of one that is itself ready.
        void AMoveReplacesASkillWhichIsChecked()
        {
            World w;
            w.Put(2, "Meteor", "Molten Impact");
            w.Put(4, "Frost Nova", "Shatter");
            w.Cool(w.Shell("Frost Nova", "Shatter"), 6000);
            ExpectRefused(w, 4, "Meteor", "Molten Impact", "Frost Nova is on cooldown (6 s left).");
            w.player.cooldownLeft.clear();
            ExpectAllowed(w, 4, "Meteor", "Molten Impact");
            Check(w.Held().count(2) == 0, "K6: the move freed the slot the skill came from");
        }

        // Same skill, same rune, another slot: what the skill casts is exactly what it was, and the
        // cooldown is the shell's own, so it follows. Not a swap, so not refused; the identical
        // write (nothing to change) is not either.
        void MovingTheSameShellIsNotAChange()
        {
            World w;
            w.Put(2, "Meteor", "Molten Impact");
            w.Put(4, "Magic Missile");
            w.Cool(w.Shell("Meteor", "Molten Impact"), 15000);
            ExpectAllowed(w, 4, "Meteor", "Molten Impact");
            Check(w.Held().count(2) == 0, "K6: the move freed the slot the skill came from");
            ExpectAllowed(w, 4, "Meteor", "Molten Impact"); // the very same row again
        }

        void TheTimeLeftRoundsUpAndZeroIsReady()
        {
            struct Case
            {
                std::uint32_t milliseconds;
                char const* seconds;
            };
            for (Case const& c :
                 {Case{1, "1"}, Case{999, "1"}, Case{1000, "1"}, Case{1001, "2"}, Case{12000, "12"}, Case{12001, "13"}})
            {
                World w;
                w.Put(2, "Meteor", "Molten Impact");
                w.Cool(w.Shell("Meteor", "Molten Impact"), c.milliseconds);
                ExpectRefused(w, 2, "Meteor", "Comet",
                              std::string("Meteor is on cooldown (") + c.seconds + " s left).");
            }
            World w;
            w.Put(2, "Meteor", "Molten Impact");
            w.Cool(w.Shell("Meteor", "Molten Impact"), 0);
            ExpectAllowed(w, 2, "Meteor", "Comet");
        }

        // 04 §3 is unchanged: combat and an instance still say their own line first.
        void CombatAndInstanceStillRefuseFirst()
        {
            {
                World w;
                w.Put(2, "Meteor", "Molten Impact");
                w.Cool(w.Shell("Meteor", "Molten Impact"), 15000);
                w.player.inCombat = true;
                ExpectRefused(w, 2, "Meteor", "Comet", "Not in combat.");
            }
            {
                World w;
                w.Put(2, "Meteor", "Molten Impact");
                w.Cool(w.Shell("Meteor", "Molten Impact"), 15000);
                w.player.map.instanceable = true;
                ExpectRefused(w, 2, "Meteor", "Comet", "Not inside an instance or rift.");
            }
        }

        // Every skill the generator shipped, both classes, grouped by the generated skill_id
        // column (restated here, not read back out of the module's own scan): whichever rune is
        // slotted and whichever rune of the same skill is cooling, a swap is refused; once nothing
        // cools it is allowed; and a cooldown on another skill's shells blocks nothing.
        void EverySkillIsOneUnitWhateverItsRunes()
        {
            int skills = 0, cases = 0;
            for (auto const& [wowClass, classId] : classMap)
            {
                std::map<std::uint32_t, std::vector<Row const*>> byBaseSkill; // skill_id -> base shell and its runes
                for (Row const& row : rows)
                    if (row.classId == classId)
                        byBaseSkill[row.skillId].push_back(&row);
                for (auto const& [skillId, shells] : byBaseSkill)
                {
                    ++skills;
                    std::string const name = shells.front()->skill;
                    // Another skill of the class, for the change a single-shell skill is asked for and for the leak
                    // check.
                    Row const* other = nullptr;
                    for (auto const& [otherId, otherShells] : byBaseSkill)
                        if (otherId != skillId && !other)
                            other = otherShells.front();
                    for (Row const* slotted : shells)
                    {
                        // The change asked for: another rune of the same skill, else another skill.
                        Row const* wanted = nullptr;
                        for (Row const* candidate : shells)
                            if (candidate != slotted && !wanted)
                                wanted = candidate;
                        if (!wanted)
                            wanted = other;
                        for (Row const* cooling : shells)
                        {
                            ++cases;
                            World w(wowClass);
                            w.Put(2, slotted->skill, slotted->rune);
                            w.Cool(cooling->spellId, 5000);
                            ExpectRefused(w, 2, wanted->skill, wanted->rune, name + " is on cooldown (5 s left).");
                            w.player.cooldownLeft.clear();
                            ExpectAllowed(w, 2, wanted->skill, wanted->rune);
                        }
                        // Another skill's shells, all cooling, are nobody's business here.
                        World w(wowClass);
                        w.Put(2, slotted->skill, slotted->rune);
                        std::uint32_t const wantedSkill = wanted->skillId;
                        for (Row const& row : rows)
                            if (row.classId == classId && row.skillId != skillId && row.skillId != wantedSkill)
                                w.Cool(row.spellId, 5000);
                        ++cases;
                        ExpectAllowed(w, 2, wanted->skill, wanted->rune);
                    }
                }
            }
            Check(skills > 40 && cases > 400, "the sweep covered the catalogue (" + std::to_string(skills) +
                                                  " skills, " + std::to_string(cases) + " cases)");
            std::printf("sweep: %d skills, %d cases\n", skills, cases);
        }

        struct Scenario
        {
            char const* name;
            void (*run)();
        };

        Scenario const scenarios[] = {
            {"rune_swap_refused_while_the_skill_is_on_cooldown", RuneSwapRefusedOnCooldown},
            {"spell_swap_refused_while_the_skill_is_on_cooldown", SpellSwapRefusedOnCooldown},
            {"a_cooldown_on_any_rune_of_the_skill_counts", CooldownOnAnyRuneOfTheSkillCounts},
            {"the_longest_cooldown_of_the_skill_is_quoted", TheLongestCooldownOfTheSkillIsQuoted},
            {"off_cooldown_skills_swap_freely_whatever_else_is_cooling",
             OffCooldownSkillsSwapFreelyWhateverElseIsCooling},
            {"a_move_with_another_rune_is_a_rune_swap", AMoveWithAnotherRuneIsARuneSwap},
            {"a_move_replaces_a_skill_which_is_checked", AMoveReplacesASkillWhichIsChecked},
            {"moving_the_same_shell_is_not_a_change", MovingTheSameShellIsNotAChange},
            {"the_time_left_rounds_up_and_zero_is_ready", TheTimeLeftRoundsUpAndZeroIsReady},
            {"combat_and_instance_still_refuse_first", CombatAndInstanceStillRefuseFirst},
            {"every_skill_is_one_unit_whatever_its_runes", EverySkillIsOneUnitWhateverItsRunes},
        };
    } // namespace

    int RunAll(char const* path)
    {
        Load(path);
        int bad = 0;
        for (Scenario const& scenario : scenarios)
        {
            currentScenario = scenario.name;
            failures = 0;
            printed = 0;
            scenario.run();
            std::printf("%s %s\n", failures ? "FAILED" : "PASS", scenario.name);
            bad += failures != 0;
        }
        return bad ? 1 : 0;
    }
} // namespace DC::Classes

int main(int argc, char** argv)
{
    if (argc != 2)
    {
        std::printf("usage: swap_harness <catalogue.tsv>\n");
        return 2;
    }
    return DC::Classes::RunAll(argv[1]);
}
