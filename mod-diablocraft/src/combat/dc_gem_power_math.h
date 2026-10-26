/*
 * World of DiabloCraft - what the always-on legendary gems add up to.
 *
 * Group A: the base powers that need no event. Given the gems that count (one per kind, Unique
 * Equipped: src/items/dc_legendary_gem_item.h) and the lookup of their numbers
 * (src/common/dc_legendary_gem.h, the legendary_gems.csv columns), Resolve() answers each power's
 * value at the gem's own rank. The factors below are what combat multiplies a hit by. No core
 * dependency, so scripts/tests/legendaries/test_legendary_gem_powers.py compiles this exact file.
 *
 * Which gem is which power is code; every number is read from the lookup, none is written here.
 *
 * Group C is the spell-driven procs: the numbers each proc needs
 * (chance, weapon damage %, seconds, the rank-25 stun and taunt), the stagger pool of Moratorium and the
 * split of a damage-over-time total into ticks. What they cast is src/combat/dc_gem_powers.cpp.
 *
 * Group D is the rank-25 bonuses: the numbers each one needs (a gem's
 * `rank25_value_1/2`, read at rank >= Rank25 and zero below it), and Wanted(), which turns the state that moves
 * them (stacks, the Life, the Wreath, the bleeding enemies around) into the sheet contributions they are.
 *
 * Enforcer is the one gem that acts on something other than the wearer: its pets. Which skills
 * and creatures are pets is data (data/legendary_gem_pets.csv -> dc_legendary_gem_pet), read into `Pets`; no skill
 * and no class is named here.
 *
 * Legacy of Dreams counts the worn Legendary and Set items while no set bonus is on; the count is
 * ItemPowers' (the set counter's), the per-item numbers and the rank-25 gate are here.
 */

#ifndef DC_GEM_POWER_MATH_H
#define DC_GEM_POWER_MATH_H

#include "../common/dc_legendary_gem.h"
#include "../items/dc_legendary_gem_item.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace DC::Combat::GemPower
{
    // gems.csv ids (is_legendary=1).
    inline constexpr char const* Wildebeest = "Unique_Gem_017_x1"; // Molten Wildebeest's Gizzard: Life per Second
    inline constexpr char const* Boyarsky = "Unique_Gem_020_x1";   // Boyarsky's Chip: Thorns
    inline constexpr char const* Esoteric = "Unique_Gem_016_x1";   // Esoteric Alteration: non-Physical damage reduction
    inline constexpr char const* Mutilation = "Unique_Gem_019_x1"; // Mutilation Guard: melee damage reduction
    inline constexpr char const* Simplicity = "Unique_Gem_013_x1"; // Simplicity's Strength: primary skill damage
    inline constexpr char const* Enforcer = "Unique_Gem_010_x1";   // Enforcer: pets deal more damage; the targetable ones take less
    // Group B: the damage multipliers and the stacking buffs.
    inline constexpr char const* Powerful = "Unique_Gem_001_x1";     // Bane of the Powerful: damage after an elite kill
    inline constexpr char const* Trapped = "Unique_Gem_002_x1";      // Bane of the Trapped: damage vs control-impaired
    inline constexpr char const* Gogok = "Unique_Gem_008_x1";        // Gogok of Swiftness: attack speed + dodge stacks
    inline constexpr char const* Invigorating = "Unique_Gem_009_x1"; // Invigorating Gemstone: healing received stacks
    inline constexpr char const* Zei = "Unique_Gem_012_x1";          // Zei's Stone of Vengeance: damage by distance
    inline constexpr char const* Taeguk = "Unique_Gem_015_x1";       // Taeguk: damage stacks on a channeled skill
    inline constexpr char const* Stricken = "Unique_Gem_018_x1";     // Bane of the Stricken: damage taken per attack
    // Group C: the spell-driven procs. Zei's stun (rank 25) and Boyarsky's taunt (rank 25) belong to gems above.
    inline constexpr char const* Wreath = "Unique_Gem_004_x1";     // Wreath of Lightning: a 3 s pulse on a chance on hit
    inline constexpr char const* Toxin = "Unique_Gem_005_x1";      // Gem of Efficacious Toxin: poison on every enemy hit
    inline constexpr char const* Pain = "Unique_Gem_006_x1";       // Pain Enhancer: a bleed on a critical hit
    inline constexpr char const* Mirinae = "Unique_Gem_007_x1";    // Mirinae, Teardrop of the Starweaver: smite on a chance on hit
    inline constexpr char const* Moratorium = "Unique_Gem_011_x1"; // Moratorium: a share of damage taken is staggered
    inline constexpr char const* Iceblink = "Unique_Gem_021_x1";   // Iceblink: Cold skills chill, chills slow more
    // Legacy of Dreams: per worn legendary item, while no set bonus is on.
    inline constexpr char const* Legacy = "Unique_Gem_023_x1";

    // "(Requires Rank 25)": the rank at which a gem's second power applies (the tooltip line).
    inline constexpr unsigned Rank25 = 25;

    // A buff that stacks and holds one expiry: each new stack refreshes it (d3planner treats every stacking gem so;
    // the sheet gives a duration, never one per stack).
    struct StackBuff
    {
        double perStack = 0;  // the % per stack that scales with rank (Gogok: Dodge)
        double perStack2 = 0; // a second per-stack % that does not (Gogok: Attack Speed)
        double seconds = 0;
        unsigned max = 0; // 0: not worn
    };

    struct Powers
    {
        double lifeRegen = 0; // Life per Second, a sheet contribution
        double thorns = 0;    // Thorns, a sheet contribution
        double nonPhysicalReductionPct = 0;
        double meleeReductionPct = 0;
        double primaryDamagePct = 0;
        // Group B. Zero everywhere when the gem is not worn.
        double powerfulPct = 0, powerfulSeconds = 0; // the buff after an elite kill
        double trappedPct = 0;
        double strickenPctPerAttack = 0;
        double zeiPctPerStep = 0, zeiYardsPerStep = 0, zeiMaxPct = 0;
        StackBuff taeguk, gogok, invigorating;
        // Group C. Zero everywhere when the gem is not worn (or, for the two rank-25 powers, not yet rank 25).
        double mirinaePct = 0, mirinaeChancePct = 0, mirinaeHealPct = 0; // smite: weapon damage %, chance on hit, % max Life
        double wreathPct = 0, wreathChancePct = 0, wreathSeconds = 0;    // per pulse, chance on hit, how long it lasts
        double painPct = 0, painSeconds = 0;                             // bleed total over its seconds
        double toxinPct = 0, toxinSeconds = 0;                           // poison total over its seconds
        double staggerPct = 0, staggerSeconds = 0;                       // share of damage taken, the seconds it is spread over
        double zeiStunChancePct = 0, zeiStunSeconds = 0;                 // rank 25
        double boyarskyTauntSeconds = 0;                                 // rank 25
        double iceblinkSlowPct = 0;                                      // the additional slow of a Chill
        // Group D, the rank-25 bonuses. Zero when the gem is not worn or is below rank 25.
        double powerfulEliteDamagePct = 0, powerfulEliteDefencePct = 0; // more damage to elites, less damage from them
        double strickenBossPct = 0;                                     // more damage to bosses and Rift Guardians
        double trappedYards = 0, trappedSlowPct = 0;                    // the aura: its radius, the slow it puts on
        double esotericBelowLifePct = 0, esotericResistPct = 0;         // below this share of Life, resistances up by this
        double toxinTakenPct = 0, toxinDealtPct = 0;                    // a poisoned enemy takes this much more, deals this much less
        double gogokCooldownPerStack = 0;                               // Cooldown Reduction per stack of Swiftness
        double iceblinkCritPct = 0;                                     // more chance to crit a chilled enemy
        bool controlImmune = false;                                     // Invigorating Gemstone: immune to control impairing effects
        double mirinaeEverySeconds = 0;                                 // a smite on this clock as well
        double wildebeestQuietSeconds = 0, wildebeestShieldPct = 0;     // seconds unhurt, shield as % of Life per Second
        double moratoriumClearChancePct = 0;                            // chance on a kill to clear what is staggered
        double painFrenzyPct = 0, painFrenzyYards = 0;                  // Attack Speed per bleeding enemy, and how near
        double simplicityHealPct = 0;                                   // a Primary hit heals this % of maximum Life
        double taegukArmorPctPerStack = 0;                              // Armor per stack of Taeguk
        double wreathMovePct = 0;                                       // Movement Speed while the Wreath is on
        // Enforcer: the damage of the pets, and (rank 25) how much less damage the pets enemies can target take.
        double petDamagePct = 0, petDefencePct = 0;
        // Legacy of Dreams: damage and damage-taken reduction per legendary item that counts, and (rank 25) Ancients count twice.
        double legacyDamagePct = 0, legacyReductionPct = 0;
        bool legacyAncientsTwice = false;
    };

    // What counts as a pet for a gem: skill names (the skill sheets' own, rune-less) and the creature entries of the
    // summons enemies can target. Filled from dc_legendary_gem_pet; an empty list is a class with no pets.
    struct Pets
    {
        std::set<std::string> skills;
        std::set<std::uint32_t> entries;
    };

    inline void AddPet(Pets& pets, std::string const& skill, std::optional<std::uint32_t> entry)
    {
        pets.skills.insert(skill);
        if (entry)
            pets.entries.insert(*entry);
    }

    inline bool IsPetSkill(Pets const& pets, std::string const& skill)
    {
        return pets.skills.count(skill) != 0;
    }

    inline bool IsPetEntry(Pets const& pets, std::uint32_t entry)
    {
        return pets.entries.count(entry) != 0;
    }

    // A fixed number of a gem's base effect (legendary_gems.csv fixed_1..3, text order); a gem the sheet
    // gives none of cannot be built, which is a data error and not a zero.
    inline double Fixed(LegendaryGem::Row const& row, int index)
    {
        if (!row.fixed[index])
            throw std::runtime_error(row.name + ": fixed_" + std::to_string(index + 1) + " is empty");
        return *row.fixed[index];
    }

    // A number of a gem's rank-25 bonus (legendary_gems.csv rank25_value_1/2, text order); a gem the sheet gives none
    // of cannot be built, like Fixed().
    inline double Rank25Number(LegendaryGem::Row const& row, int index)
    {
        if (!row.rank25[index])
            throw std::runtime_error(row.name + ": rank25_value_" + std::to_string(index + 1) + " is empty");
        return *row.rank25[index];
    }

    // `find` answers LegendaryGem::Row const* for a gem id (nullptr: none). A gem the lookup does not
    // know adds nothing.
    template<typename Find>
    inline Powers Resolve(std::vector<LegendaryGemItem::Socketed> const& active, Find&& find)
    {
        Powers powers;
        for (auto const& gem : active)
        {
            LegendaryGem::Row const* row = find(gem.gemId);
            if (!row)
                continue;
            double const value = LegendaryGem::Value(*row, gem.rank);
            bool const rank25 = gem.rank >= Rank25;
            if (gem.gemId == Wildebeest)
            {
                powers.lifeRegen = value;
                if (rank25)
                {
                    powers.wildebeestQuietSeconds = Rank25Number(*row, 0);
                    powers.wildebeestShieldPct = Rank25Number(*row, 1);
                }
            }
            else if (gem.gemId == Boyarsky)
            {
                powers.thorns = value;
                if (rank25)
                    powers.boyarskyTauntSeconds = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Esoteric)
            {
                powers.nonPhysicalReductionPct = value;
                if (rank25)
                {
                    powers.esotericBelowLifePct = Rank25Number(*row, 0);
                    powers.esotericResistPct = Rank25Number(*row, 1);
                }
            }
            else if (gem.gemId == Enforcer)
            {
                powers.petDamagePct = value;
                if (rank25)
                    powers.petDefencePct = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Mutilation)
                powers.meleeReductionPct = value; // its rank-25 power, moving through enemies, needs no code (the contract says why)
            else if (gem.gemId == Simplicity)
            {
                powers.primaryDamagePct = value;
                if (rank25)
                    powers.simplicityHealPct = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Powerful)
            {
                powers.powerfulPct = Fixed(*row, 0);
                powers.powerfulSeconds = value;
                if (rank25)
                {
                    powers.powerfulEliteDamagePct = Rank25Number(*row, 0);
                    powers.powerfulEliteDefencePct = Rank25Number(*row, 1);
                }
            }
            else if (gem.gemId == Trapped)
            {
                powers.trappedPct = value;
                if (rank25)
                {
                    powers.trappedYards = Rank25Number(*row, 0);
                    powers.trappedSlowPct = Rank25Number(*row, 1);
                }
            }
            else if (gem.gemId == Stricken)
            {
                powers.strickenPctPerAttack = value;
                if (rank25)
                    powers.strickenBossPct = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Zei)
            {
                powers.zeiPctPerStep = value;
                powers.zeiYardsPerStep = Fixed(*row, 0);
                powers.zeiMaxPct = LegendaryGem::Value2(*row, gem.rank);
                if (rank25)
                {
                    powers.zeiStunChancePct = Rank25Number(*row, 0);
                    powers.zeiStunSeconds = Rank25Number(*row, 1);
                }
            }
            else if (gem.gemId == Taeguk)
            {
                powers.taeguk = {value, 0, Fixed(*row, 0), unsigned(Fixed(*row, 1))};
                if (rank25)
                    powers.taegukArmorPctPerStack = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Gogok)
            {
                powers.gogok = {value, Fixed(*row, 0), Fixed(*row, 1), unsigned(Fixed(*row, 2))};
                if (rank25)
                    powers.gogokCooldownPerStack = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Invigorating)
            {
                powers.invigorating = {value, 0, Fixed(*row, 0), unsigned(Fixed(*row, 1))};
                powers.controlImmune = rank25; // its rank-25 text has no number: the gate is the rank
            }
            else if (gem.gemId == Mirinae)
            {
                powers.mirinaePct = value;
                powers.mirinaeChancePct = Fixed(*row, 0);
                powers.mirinaeHealPct = Fixed(*row, 1);
                if (rank25)
                    powers.mirinaeEverySeconds = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Wreath)
            {
                powers.wreathPct = value;
                powers.wreathChancePct = Fixed(*row, 0);
                powers.wreathSeconds = Fixed(*row, 1);
                if (rank25)
                    powers.wreathMovePct = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Pain)
            {
                powers.painPct = value;
                powers.painSeconds = Fixed(*row, 0);
                if (rank25)
                {
                    powers.painFrenzyPct = Rank25Number(*row, 0);
                    powers.painFrenzyYards = Rank25Number(*row, 1);
                }
            }
            else if (gem.gemId == Toxin)
            {
                powers.toxinPct = value;
                powers.toxinSeconds = Fixed(*row, 0);
                if (rank25)
                {
                    powers.toxinTakenPct = Rank25Number(*row, 0);
                    powers.toxinDealtPct = Rank25Number(*row, 1);
                }
            }
            else if (gem.gemId == Moratorium)
            {
                powers.staggerPct = Fixed(*row, 0);
                powers.staggerSeconds = value;
                if (rank25)
                    powers.moratoriumClearChancePct = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Iceblink)
            {
                powers.iceblinkSlowPct = value;
                if (rank25)
                    powers.iceblinkCritPct = Rank25Number(*row, 0);
            }
            else if (gem.gemId == Legacy)
            {
                powers.legacyDamagePct = value;
                powers.legacyReductionPct = Fixed(*row, 0);
                powers.legacyAncientsTwice = rank25; // "doubled for Ancient items" has no number: the gate is the rank
            }
        }
        return powers;
    }

    // Both reductions are specific damage reductions (mitigation.csv): each multiplies the damage taken
    // by (1 - DR). Esoteric Alteration takes any school but Physical, Mutilation Guard a melee hit.
    inline double IncomingFactor(Powers const& powers, bool physical, bool melee)
    {
        double factor = 1.0;
        if (!physical)
            factor *= 1.0 - powers.nonPhysicalReductionPct / 100.0;
        if (melee)
            factor *= 1.0 - powers.meleeReductionPct / 100.0;
        return factor;
    }

    // damage_formula.csv step 8 (standalone multipliers and legendary gems): Simplicity's Strength
    // multiplies a primary skill's hit.
    inline double PrimaryFactor(Powers const& powers, bool primary)
    {
        return primary ? 1.0 + powers.primaryDamagePct / 100.0 : 1.0;
    }

    // Enforcer: "increase the damage of your pets" is a multiplier (the Enforcer wiki page: "the damage increase is
    // multiplicative"), so it is a step-8 factor on a pet's hit; "your pets take 90% less damage" is on the hit a
    // targetable pet takes.
    inline double PetDamageFactor(Powers const& powers, bool pet)
    {
        return pet ? 1.0 + powers.petDamagePct / 100.0 : 1.0;
    }

    inline double PetIncomingFactor(Powers const& powers, bool targetablePet)
    {
        return targetablePet ? 1.0 - powers.petDefencePct / 100.0 : 1.0;
    }

    // Legacy of Dreams: the legendary items that count. Each worn Legendary or Set item once (d3planner counts both
    // qualities), an Ancient once more from rank 25 (a Primal is a Primal Ancient); none while any set bonus is on.
    // The doubling is the gem's rank-25 power, not d3planner's every-level reading.
    inline unsigned LegacyItems(Powers const& powers, unsigned legendaries, unsigned ancients, bool setBonusOn)
    {
        if (setBonusOn)
            return 0;
        return legendaries + (powers.legacyAncientsTwice ? ancients : 0);
    }

    // One multiplier of its own for the whole gem (d3planner: one dmgmul of value x items; damage_formula.csv step 8),
    // and one damage-taken reduction (one dmgred of 2 x items).
    inline double LegacyFactor(Powers const& powers, unsigned items)
    {
        return 1.0 + powers.legacyDamagePct * items / 100.0;
    }

    inline double LegacyIncomingFactor(Powers const& powers, unsigned items)
    {
        return 1.0 - powers.legacyReductionPct * items / 100.0;
    }

    // The stacks of one buff and the moment they all lapse. `nowMs` is the server clock (wraps; the difference is
    // read signed).
    struct Stacks
    {
        unsigned count = 0;
        std::uint32_t untilMs = 0;
    };

    inline unsigned Live(Stacks const& stacks, std::uint32_t nowMs)
    {
        return static_cast<std::int32_t>(stacks.untilMs - nowMs) > 0 ? stacks.count : 0;
    }

    // One more stack, capped, and the whole buff lasts `seconds` from now.
    inline void AddStack(Stacks& stacks, std::uint32_t nowMs, double seconds, unsigned max)
    {
        stacks.count = std::min(Live(stacks, nowMs) + 1, max);
        stacks.untilMs = nowMs + static_cast<std::uint32_t>(std::llround(seconds * 1000.0));
    }

    // Zei's Stone of Vengeance: the % per `zeiYardsPerStep` yards between the player and the enemy, up to the
    // maximum the sheet gives (the same 20% + 0.4% per rank at 50 yards that d3planner's distance * value / 10
    // reaches).
    inline double ZeiPct(Powers const& powers, double yards)
    {
        if (powers.zeiYardsPerStep <= 0)
            return 0;
        return std::min(std::max(yards, 0.0) / powers.zeiYardsPerStep * powers.zeiPctPerStep, powers.zeiMaxPct);
    }

    // damage_formula.csv step 8: each gem is its own multiplier. `stricken` is the attacks this player has made on
    // the target, `powerful` whether the elite-kill buff is up, `trapped` whether the target is control-impaired,
    // `boss` whether it is a boss or a Rift Guardian (Bane of the Stricken, rank 25).
    inline double StandaloneFactor(Powers const& powers, bool powerful, bool trapped, unsigned stricken, double yards,
                                   bool boss = false)
    {
        double factor = 1.0;
        if (boss)
            factor *= 1.0 + powers.strickenBossPct / 100.0;
        if (powerful)
            factor *= 1.0 + powers.powerfulPct / 100.0;
        if (trapped)
            factor *= 1.0 + powers.trappedPct / 100.0;
        factor *= 1.0 + powers.strickenPctPerAttack * stricken / 100.0;
        factor *= 1.0 + ZeiPct(powers, yards) / 100.0;
        return factor;
    }

    // damage_formula.csv step 4 lists Taeguk among the additive buffs.
    inline double AdditivePct(Powers const& powers, unsigned taegukStacks)
    {
        return powers.taeguk.perStack * taegukStacks;
    }

    inline double DodgePct(Powers const& powers, unsigned gogokStacks)
    {
        return powers.gogok.perStack * gogokStacks;
    }

    inline double AttackSpeedPct(Powers const& powers, unsigned gogokStacks)
    {
        return powers.gogok.perStack2 * gogokStacks;
    }

    // Healing received, in percent, at these stacks (the buff's addon line shows it).
    inline double HealingPct(Powers const& powers, unsigned invigoratingStacks)
    {
        return powers.invigorating.perStack * invigoratingStacks;
    }

    inline double HealingFactor(Powers const& powers, unsigned invigoratingStacks)
    {
        return 1.0 + HealingPct(powers, invigoratingStacks) / 100.0;
    }

    // Group C ------------------------------------------------------------------------------------------------

    // A damage-over-time gem deals its total weapon damage % over its seconds, one tick per `periodMs` of its
    // record (the aura's EffectAuraPeriod): the ticks, and each tick's share. At least one tick.
    inline unsigned Ticks(double seconds, double periodMs)
    {
        if (periodMs <= 0)
            return 1;
        return static_cast<unsigned>(std::max<long long>(1, std::llround(seconds * 1000.0 / periodMs)));
    }

    inline double TickPct(double totalPct, double seconds, double periodMs)
    {
        return totalPct / Ticks(seconds, periodMs);
    }

    // Moratorium: `staggerPct` of a hit that is not already staggered is put off and paid over `staggerSeconds`.
    // Returns the damage dealt now; `owed` receives what was put off.
    inline double StaggerSplit(Powers const& powers, double damage, double& owed)
    {
        owed = powers.staggerPct > 0 ? damage * powers.staggerPct / 100.0 : 0.0;
        return damage - owed;
    }

    // What is owed, as hits put off at their own moment and each paid evenly over `durationMs` (the signed
    // difference reads the wrapping server clock). Pay() answers what has come due since the last call.
    struct StaggerPool
    {
        struct Entry
        {
            double total = 0;
            double paid = 0;
            std::uint32_t startMs = 0;
            std::uint32_t durationMs = 0;
        };
        std::vector<Entry> entries;

        void Add(double amount, double seconds, std::uint32_t nowMs)
        {
            if (amount > 0)
                entries.push_back({amount, 0.0, nowMs, static_cast<std::uint32_t>(std::llround(std::max(0.0, seconds) * 1000.0))});
        }

        double Owed() const
        {
            double owed = 0;
            for (Entry const& entry : entries)
                owed += entry.total - entry.paid;
            return owed;
        }

        double Pay(std::uint32_t nowMs)
        {
            double due = 0;
            for (Entry& entry : entries)
            {
                std::int32_t const elapsed = static_cast<std::int32_t>(nowMs - entry.startMs);
                bool const finished = entry.durationMs == 0 || elapsed >= static_cast<std::int64_t>(entry.durationMs);
                double const share = finished ? 1.0 : std::max(0, elapsed) / static_cast<double>(entry.durationMs);
                double const paidNow = finished ? entry.total - entry.paid : entry.total * share - entry.paid;
                if (paidNow > 0)
                {
                    entry.paid = finished ? entry.total : entry.paid + paidNow;
                    due += paidNow;
                }
            }
            entries.erase(std::remove_if(entries.begin(), entries.end(),
                                         [](Entry const& entry) { return entry.paid >= entry.total; }),
                          entries.end());
            return due;
        }
    };

    // Group D, the rank-25 bonuses -----------------------------------------------------------------------

    // Bane of the Powerful: "take 15% reduced damage from elites", on one incoming hit.
    inline double EliteIncomingFactor(Powers const& powers, bool attackerIsElite)
    {
        return attackerIsElite ? 1.0 - powers.powerfulEliteDefencePct / 100.0 : 1.0;
    }

    // Gem of Efficacious Toxin: a poisoned enemy "deals 10% less damage" (the factor on its hit), and "takes 10%
    // increased damage from all sources" (damage_formula.csv step 4 lists the gem among the monster damage-taken
    // debuffs, so it is a percentage in that sum). Both numbers are the poisoner's: the wearer of the gem.
    inline double WeakenedFactor(Powers const& powers)
    {
        return 1.0 - powers.toxinDealtPct / 100.0;
    }

    inline double VictimTakesMorePct(Powers const& powers)
    {
        return powers.toxinTakenPct;
    }

    // Molten Wildebeest's Gizzard: after `wildebeestQuietSeconds` without taking damage, a shield of
    // `wildebeestShieldPct` % of the Life per Second. It is armed by a damage taken and spent when it is put on, so
    // one quiet spell is one shield. `quietMs` is the time since the last damage.
    inline bool ShieldDue(Powers const& powers, bool armed, std::uint32_t quietMs)
    {
        return armed && powers.wildebeestShieldPct > 0 && quietMs >= powers.wildebeestQuietSeconds * 1000.0;
    }

    inline double ShieldAmount(Powers const& powers, double lifePerSecond)
    {
        return lifePerSecond * powers.wildebeestShieldPct / 100.0;
    }

    // A chance on a kill (no proc coefficient: a kill is not a skill's hit). `roll` is in [0, 100).
    inline bool ChanceHits(double pct, double roll)
    {
        return pct > 0 && roll < pct;
    }

    // What the gems add to the sheet that follows a state and not the rank alone, as of this moment. Every value is
    // the sheet's own unit (percent). `resistBase` is each of Fire, Cold, Lightning, Poison and Arcane resistance as the
    // sheet has it without this gem's own contribution.
    struct Dynamic
    {
        unsigned gogok = 0, taeguk = 0; // live stacks
        unsigned bleeding = 0;          // enemies within Blood Frenzy's reach that Pain Enhancer's bleed is on
        bool wreath = false;            // the Wreath of Lightning is on the player
        bool belowLife = false;         // Life is below Esoteric Alteration's share
        double resistBase[5] = {};
    };

    struct Sheeted
    {
        double gogokAttackSpeed = 0;    // Gogok of Swiftness (base power)
        double gogokCooldown = 0;       // Gogok, rank 25
        double taegukArmor = 0;         // Taeguk, rank 25 (a percentage of Armor)
        double frenzyAttackSpeed = 0;   // Pain Enhancer, rank 25: Blood Frenzy
        double wreathMovement = 0;      // Wreath of Lightning, rank 25
        double eliteDamage = 0;         // Bane of the Powerful, rank 25
        double resist[5] = {};          // Esoteric Alteration, rank 25
        // Equal to a millionth of a percent: the resistances are worked out from a sheet that already holds the last
        // ones, and (a + b) - b is not always a.
        bool operator==(Sheeted const& other) const
        {
            auto const same = [](double a, double b) { return std::fabs(a - b) < 1e-6; };
            for (int i = 0; i < 5; ++i)
                if (!same(resist[i], other.resist[i]))
                    return false;
            return same(gogokAttackSpeed, other.gogokAttackSpeed) && same(gogokCooldown, other.gogokCooldown) &&
                   same(taegukArmor, other.taegukArmor) && same(frenzyAttackSpeed, other.frenzyAttackSpeed) &&
                   same(wreathMovement, other.wreathMovement) && same(eliteDamage, other.eliteDamage);
        }
    };

    inline Sheeted Wanted(Powers const& powers, Dynamic const& now)
    {
        Sheeted out;
        out.gogokAttackSpeed = AttackSpeedPct(powers, now.gogok);
        // A Cooldown Reduction is a percentage between 0 and 100 (dc_common.cpp Validate).
        out.gogokCooldown = std::min(100.0, powers.gogokCooldownPerStack * now.gogok);
        out.taegukArmor = powers.taegukArmorPctPerStack * now.taeguk;
        out.frenzyAttackSpeed = powers.painFrenzyPct * now.bleeding;
        out.wreathMovement = now.wreath ? powers.wreathMovePct : 0.0;
        out.eliteDamage = powers.powerfulEliteDamagePct;
        if (now.belowLife && powers.esotericResistPct > 0)
            for (int i = 0; i < 5; ++i)
                out.resist[i] = now.resistBase[i] * powers.esotericResistPct / 100.0;
        return out;
    }
} // namespace DC::Combat::GemPower

#endif
