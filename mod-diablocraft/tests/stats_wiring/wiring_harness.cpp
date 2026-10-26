/*
 * Issues #54 and #55, on the production path.
 *
 * Every function under test below is the module's own, cut out of its file by
 * scripts/tests/stats/test_stats_wiring.py and compiled here: PublishMovement, ApplySlow,
 * SheetAward and the levelling hook's body. The stat sheet is the
 * real one - dc_common.cpp is linked - so the cap and the level-70 XP penalty
 * are the server's, not a model of them. What is a double is listed in
 * wiring_shim.h, and the one that matters is that no aura here changes a speed:
 * these tests say which aura is asked for and when, never how fast anyone runs.
 */

#include "wiring_shim.h"

#include "../../src/common/dc_common.h"
#include "../../src/combat/dc_spell_shells.h"
#include "../../src/stats/dc_movement_math.h"
#include "../../src/paragon/dc_paragon_math.h"

#include <algorithm>
#include <cassert>
#include <cstdio>
#include <map>
#include <mutex>
#include <stdexcept>
#include <vector>
#include <set>

// The four numbers dc_common.cpp asks the world for, as stat_tests.cpp supplies
// them: no database behind these tests.
namespace DC::NumericData
{
std::map<std::string, double> rules{
    {"crit_chance_pct", 5}, {"crit_damage_pct", 50}, {"attack_speed_cap", 5},
    {"movement_cap_pct", 25}, {"magic_find_cap_pct", 300}, {"gold_find_cap_pct", 300},
    {"xp_penalty_level", 70}, {"xp_divisor", 10}, {"all_res_per_int", 0.1},
    {"class_dr_pct", 30}, {"armor_level_coefficient", 50}, {"resistance_level_coefficient", 5}};
double Rule(char const* name) { return rules.at(name); }
unsigned MaximumLevel() { return 70; }
double BaseFury(unsigned) { return 100; }
BlockTuning Block() { return {75, 100, 1}; }
}

// The sheet the module reads. SheetAward and PublishMovement both go through a
// sheet; this is the only way one reaches them here.
namespace DC::Stats
{
std::map<std::uint64_t, StatSheet> sheets;
std::optional<StatSheet> Get(std::uint64_t guid)
{
    auto found = sheets.find(guid);
    if (found == sheets.end())
        return std::nullopt;
    return found->second;
}
}

// dc_rift_elites.cpp's hold donors, which ReleasePlayerControls takes off a player.
namespace DC::Rifts
{
constexpr std::uint32_t JAILER_DEBUFF = 53077;
constexpr std::uint32_t FEAR_HOLD = 29168;
constexpr std::uint32_t FREEZE_HOLD = 15878;
}

#include "dc_spell_records_extract.h"
#include "dc_stats_extract.h"
#include "dc_rift_elites_extract.h"
#include "dc_gray_extract.h"
namespace DC::Rifts
{
bool throwOnQuery = false;
inline bool InRift(Creature*, unsigned&)
{
    if (throwOnQuery) throw std::runtime_error("injected rift lookup failure");
    return false;
}
// Greater Rift part 7's XP split: outside a Greater Rift it returns the amount it is given.
inline std::uint64_t GreaterRiftXp(Creature const*, std::uint64_t amount) { return amount; }
}
namespace DC::Difficulty
{
inline unsigned CurrentTier(Player*) { return 1; }
}
namespace DC::Paragon
{
std::mutex mutex;
bool ready = true;
std::map<uint32, bool> characters;
std::map<unsigned, XP> tierBonuses{{1, 0}};
XP baseXP = 1000;
unsigned partyPerMember = 1000, partyCap = 3000;
std::map<uint32, XP> awards;
inline uint32 Guid(Player* player) { return player->GetGUID().GetCounter(); }
inline bool ParagonClass(Player* player) { return player->playable; }
inline void AddXP(Player* player, XP amount) { awards[Guid(player)] += amount; }
struct Hooks { static void Kill(Creature* victim); };
}
// Pylons and shrines P1 (diablocraft-plgq2): the Enlightened Shrine's percent, as the buff would answer it.
namespace DC::Combat::Pylons
{
inline double enlightenedPct = 0;
inline double ExperiencePct(Player*) { return enlightenedPct; }
}
#include "dc_paragon_extract.h"
void DC::Paragon::Hooks::Kill(Creature* victim) { DC::Paragon::Kill(victim); }

using namespace DC;

namespace
{
void Check(bool ok, char const* why) { if (!ok) throw std::runtime_error(why); }

BaseStats const& Seventy()
{
    static BaseStats base = [] { BaseStats b; b.level = 70; b.baseLife = 15000; return b; }();
    return base;
}

// A sheet built by the real engine, so a cap in a test is the server's cap.
StatSheet SheetWith(std::vector<Contribution> const& contributions)
{
    return Calculate(Seventy(), contributions);
}

void Publish(Player& player, std::vector<Contribution> const& contributions)
{
    StatSheet sheet = SheetWith(contributions);
    Stats::sheets[player.guid.GetRawValue()] = sheet;
    Stats::PublishMovement(&player, sheet);
}

constexpr uint32 AGGREGATE = Combat::Shells::MovementAggregate;

// One slow record per affix (Architect, 2026-09-21), looked up by the affix's
// name exactly as the module looks it up. SLOW is Knockback's, which is the
// site that calls ApplySlow directly; OTHER is Frozen Pulse's, which reaches it
// through the hazard, and having two of them is what the cross-affix case
// below needs.
uint32 SlowRecord(char const* affix)
{
    uint32 id = Combat::Shells::AffixSlowFor(affix);
    Check(id != 0, "the generated header has no slow record for that affix");
    return id;
}
uint32 const SLOW = SlowRecord("Knockback");
uint32 const OTHER = SlowRecord("Frozen Pulse");

// --- #54, the publisher ----------------------------------------------------

void ThePublisherCastsTheSheetsTotalAsOneAura()
{
    Player player;
    Publish(player, {});
    Check(!player.Has(AGGREGATE), "an empty sheet published an aura");

    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 12}});
    Check(player.Has(AGGREGATE), "a movement item published nothing");
    Check(player.AuraAmount(AGGREGATE) == 12, "the aura does not carry the sheet's value");
    Check(player.Casts(AGGREGATE) == 1, "more than one aura was cast");

    // The cap is the sheet's, and what is published is what the sheet says
    // after it - 12 + 20 asked, 25 allowed.
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 12},
                     {Source::Paragon, Stat::MovementSpeed, 2, 20}});
    Check(player.AuraAmount(AGGREGATE) == 25, "the capped total is not what was published");

    // A skill bonus is uncapped and rides on top, in the same single aura.
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 12},
                     {Source::Paragon, Stat::MovementSpeed, 2, 20},
                     {Source::Temporary, Stat::MovementSpeed, 3, 30, Bucket::Uncapped}});
    Check(player.AuraAmount(AGGREGATE) == 55, "a skill bonus did not reach the aura");
    Check(player.auras.size() == 1, "the publisher is casting more than one aura");
}

void ThePublisherUpdatesInPlaceAndTakesTheAuraAwayAgain()
{
    Player player;
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 10}});
    unsigned const casts = player.Casts(AGGREGATE);

    // Recomputing with the same sheet must not churn the aura: the amount is
    // already right, so nothing is removed and nothing is recast.
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 10}});
    Check(player.Casts(AGGREGATE) == casts, "an unchanged sheet recast the aura");
    Check(player.AuraAmount(AGGREGATE) == 10, "an unchanged sheet lost the aura");

    // A changed sheet replaces it.
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 18}});
    Check(player.AuraAmount(AGGREGATE) == 18, "a changed sheet did not republish");

    // And unequipping everything takes it off rather than leaving a stale one.
    Publish(player, {});
    Check(!player.Has(AGGREGATE), "the aura outlived the bonus that caused it");
}

// --- #54, the affix slows --------------------------------------------------

void ASlowLandsBesideTheBonusAndLeavesItAlone()
{
    Player player;
    Unit elite;
    elite.guid.raw = 10;
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 20}});
    Rifts::ApplySlow(&elite, &player, SLOW, 0.4, 3000);
    Check(player.AuraAmount(AGGREGATE) == 20, "the slow disturbed the movement bonus");
    Check(player.AuraAmount(SLOW) == -60, "0.4 of normal speed is not -60%");
    Check(player.GetAura(SLOW)->GetDuration() == 3000, "the slow did not take the affix's milliseconds");
    Check(player.GetAura(SLOW)->caster == elite.guid, "the slow is not the elite's own aura");

    // Not a slow at all.
    Player other;
    Rifts::ApplySlow(&elite, &other, SLOW, 1.0, 3000);
    Rifts::ApplySlow(&elite, &other, SLOW, 1.5, 3000);
    Rifts::ApplySlow(&elite, &other, SLOW, 0.4, 0);
    Rifts::ApplySlow(nullptr, &other, SLOW, 0.4, 3000);
    // And a record that does not exist: an affix the generator has no slow for
    // resolves to 0, which must cast nothing rather than cast spell 0.
    Rifts::ApplySlow(&elite, &other, 0, 0.4, 3000);
    Check(!other.Has(SLOW), "something that is not a slow was cast as one");
    Check(other.auras.empty(), "a slow with no record cast something anyway");
}

// Where the aura lands is the record's decision. The elite casts it, the
// PLAYER carries it, and the elite's guid is on it - that last part is what the
// caster-keyed lifetimes are built on, so it is checked here rather than
// assumed by the tests that rely on it.
void TheSlowLandsOnThePlayerAndCarriesTheElitesGuid()
{
    Player player;
    Unit elite;
    elite.guid.raw = 21;
    Rifts::ApplySlow(&elite, &player, SLOW, 0.4, 3000);
    Check(player.Has(SLOW), "the slow never reached the player");
    Check(player.GetAura(SLOW)->caster == elite.guid, "the slow is not the elite's own aura");
    Check(elite.auras.empty(), "the elite slowed itself instead of the player");
    // And the aggregate is the other way round: the player's own, on itself.
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 15}});
    Check(player.AuraAmount(AGGREGATE) == 15, "the movement aura did not land on the player");
    Check(player.GetAura(AGGREGATE)->caster == player.guid, "the movement aura is not the player's own");
}

// The counterexample the review supplied, both ways round, and now with the
// SAME affix on both elites - which is the case one record per affix does NOT
// solve by itself. Two Knockback elites are one spell id from two casters, so
// what keeps them apart is the record's per-caster stacking attribute and the
// core keying an aura by its caster, exactly as before. Two lifetimes: the
// strongest still running is what is felt, and when it expires the weaker one
// is still there to fall back to.
void TwoElitesSlowingAtOnceEachKeepTheirOwnClock()
{
    for (bool strongerFirst : {true, false})
    {
        Player player;
        Unit strong, weak;
        strong.guid.raw = 11;
        weak.guid.raw = 12;
        Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 20}});
        if (strongerFirst)
        {
            Rifts::ApplySlow(&strong, &player, SLOW, 0.4, 1000);   // -60% for 1s
            Rifts::ApplySlow(&weak, &player, SLOW, 0.8, 5000);     // -20% for 5s
        }
        else
        {
            Rifts::ApplySlow(&weak, &player, SLOW, 0.8, 5000);
            Rifts::ApplySlow(&strong, &player, SLOW, 0.4, 1000);
        }
        Check(player.Count(SLOW) == 2, "two elites did not leave two auras");
        Check(player.StrongestSlow() == -60, "the strongest running slow is not what applies");
        Check(player.GetAura(SLOW, strong.guid)->GetDuration() == 1000, "the short slow was extended");
        Check(player.GetAura(SLOW, weak.guid)->GetDuration() == 5000, "the long slow was cut short");

        // One second in: the strong one is gone and the weak one is still
        // running, so the player speeds up to -20% rather than to no slow at
        // all - and rather than staying at -60% for another four seconds,
        // which is what the merged single aura used to do.
        player.Elapse(1000);
        Check(!player.Has(SLOW, strong.guid), "the short slow outlived its own duration");
        Check(player.StrongestSlow() == -20, "the slow did not fall back to the weaker one");
        Check(player.GetAura(SLOW, weak.guid)->GetDuration() == 4000, "the weaker slow lost time");

        // And four seconds after that the last one goes, leaving the movement
        // bonus untouched behind it.
        player.Elapse(4000);
        Check(player.Count(SLOW) == 0, "a slow outlived every duration it was given");
        Check(player.StrongestSlow() == 0, "the player is still slowed by nothing");
        Check(player.AuraAmount(AGGREGATE) == 20, "the movement bonus did not survive the slows");
    }
}

// Two DIFFERENT affixes on one player. Separate records, so they coexist for a
// different reason than the case above - nothing has to permit it - and the
// player feels the stronger of the two while both run. Both halves are worth
// having: this one would still pass if the stacking attribute were lost, and
// the one above would still pass if the records were merged back into one.
void TwoAffixesSlowingAtOnceAreTwoSeparateDebuffs()
{
    Player player;
    Unit knockback, pulse;
    knockback.guid.raw = 31;
    pulse.guid.raw = 32;
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 20}});
    Rifts::ApplySlow(&knockback, &player, SLOW, 0.2, 3000);    // -80% for 3s
    Rifts::ApplySlow(&pulse, &player, OTHER, 0.4, 10000);      // -60% for 10s
    Check(player.Slows() == 2, "two affixes did not leave two auras");
    Check(player.Has(SLOW, knockback.guid) && player.Has(OTHER, pulse.guid),
          "each affix does not hold its own record");
    Check(player.StrongestSlow() == -80, "the strongest running slow is not what applies");

    // The knockback runs out first; the pulse is still going and is now what
    // applies, on its own remaining time.
    player.Elapse(3000);
    Check(!player.Has(SLOW), "the knockback slow outlived its own duration");
    Check(player.StrongestSlow() == -60, "the slow did not fall back to the other affix");
    Check(player.GetAura(OTHER, pulse.guid)->GetDuration() == 7000, "the pulse slow lost time");
    player.Elapse(7000);
    Check(player.Slows() == 0, "a slow outlived every duration it was given");
    Check(player.AuraAmount(AGGREGATE) == 20, "the movement bonus did not survive the slows");
}

// Why the two elites above are allowed to coexist at all, said out loud. The slow is
// drawn for the player now (Architect, 2026-09-21), so its record is no longer
// passive - and a passive record was what made it a multi-slot aura, which was
// what let two casters hold it for free. `Aura::CanStackWith`'s answer for a
// non-passive record with no stacking attribute is no, and `Unit::_ApplyAura`
// acts on that answer by removing the other elite's copy. The record has to
// say "stack separately for each caster" instead, and this asserts the record
// says it - so clearing the attribute fails here with its own reason, not only
// as a confusing count in the case above.
void TheVisibleSlowStillSaysTwoCastersMayHoldIt()
{
    for (auto const& row : Combat::Shells::AffixSlows)
    {
        Check(!(RecordAttributesOf(row.id) & SPELL_ATTR0_PASSIVE),
              "a slow record is passive again, so the player cannot see it");
        Check(RecordAttributesEx3Of(row.id) & SPELL_ATTR3_DOT_STACKING_RULE,
              "a visible slow lost per-caster stacking: one elite would end another's");
        Check(RecordStacksAcrossCasters(row.id), "two elites' slows would no longer coexist");
    }
    // The aggregate is the other case: passive, hidden, and the player's own,
    // so it needs nothing of the kind.
    Check(RecordAttributesOf(AGGREGATE) & SPELL_ATTR0_PASSIVE,
          "the player's own movement total became visible");
}

// One caster re-applying its own slow refreshes that one, which is what a
// caster re-applying its own aura does. It does not add a second.
void OneEliteRefreshesItsOwnSlow()
{
    Player player;
    Unit elite;
    elite.guid.raw = 13;
    Rifts::ApplySlow(&elite, &player, SLOW, 0.4, 3000);
    player.Elapse(2000);
    Check(player.GetAura(SLOW, elite.guid)->GetDuration() == 1000, "the slow did not run down");
    Rifts::ApplySlow(&elite, &player, SLOW, 0.8, 5000);
    Check(player.Count(SLOW) == 1, "a refresh added a second aura");
    Check(player.AuraAmount(SLOW, elite.guid) == -20, "the refresh kept the old amount");
    Check(player.GetAura(SLOW, elite.guid)->GetDuration() == 5000, "the refresh kept the old duration");
    player.Elapse(5000);
    Check(player.Count(SLOW) == 0, "the refreshed slow never expired");
}

// Leaving the map takes every slow, whoever cast it, and leaves the sheet's
// own aura alone. This runs the real ReleasePlayerControls.
void AMapChangeTakesEverySlowAndNothingElse()
{
    Player player;
    player.guid.raw = 77;
    Unit one, two;
    one.guid.raw = 14;
    two.guid.raw = 15;
    Publish(player, {{Source::Items, Stat::MovementSpeed, 1, 20}});
    Rifts::ApplySlow(&one, &player, SLOW, 0.4, 30000);
    Rifts::ApplySlow(&two, &player, SLOW, 0.8, 30000);
    Rifts::ApplySlow(&two, &player, OTHER, 0.5, 30000);   // a second affix, a second record
    Check(player.Slows() == 3, "the three slows did not land");
    for (uint32 donor : {Rifts::FEAR_HOLD, Rifts::FREEZE_HOLD, Rifts::JAILER_DEBUFF})
    {
        Aura hold;
        hold.id = donor;
        hold.caster = one.guid;
        player.auras.push_back(hold);
    }

    Rifts::ReleasePlayerControls(&player);
    Check(player.Slows() == 0, "a slow rode the map change with nothing left to end it");
    Check(player.AuraAmount(AGGREGATE) == 20, "the map change took the movement bonus too");
    Check(!player.Has(Rifts::FEAR_HOLD) && !player.Has(Rifts::FREEZE_HOLD) && !player.Has(Rifts::JAILER_DEBUFF),
          "a hold aura rode the map change with nothing left to end it");
}

// --- #55, the sheet on an award --------------------------------------------

void TheSheetIsAppliedToAKillAndOnlyToAKill()
{
    Player player;
    Stats::sheets[player.guid.GetRawValue()] = SheetWith({});
    Check(Paragon::SheetAward(&player, 1000, true) == 1000, "an empty sheet changed an award");

    // A +50% XP item is +5% at level 70: the /10 penalty is the sheet's own,
    // applied by dc_common.cpp before anything here sees it.
    StatSheet withXP = SheetWith({{Source::Items, Stat::XPBonus, 1, 50}});
    Check(withXP[Stat::XPBonus] == 5, "the level-70 XP penalty is not the sheet's");
    Stats::sheets[player.guid.GetRawValue()] = withXP;
    Check(Paragon::SheetAward(&player, 72000, true) == 75600, "the percentage did not reach the award");
    Check(Paragon::SheetAward(&player, 72000, false) == 72000, "a non-kill was paid the bonus");
    Check(Paragon::SheetAward(nullptr, 72000, true) == 72000, "a null player was paid");
    Check(Paragon::SheetAward(&player, 0, true) == 0, "nothing became something");

    // Enlightened (pylons.md 4.3): 25% more on the finished award, gear bonus included; not on a non-kill.
    Combat::Pylons::enlightenedPct = 25;
    Check(Paragon::SheetAward(&player, 72000, true) == 94500, "Enlightened did not multiply the finished award");
    Check(Paragon::SheetAward(&player, 72000, false) == 72000, "a non-kill was paid Enlightened");
    Combat::Pylons::enlightenedPct = 0;

    // Flat XP per kill: the flat bucket, and it is added after the percentage.
    StatSheet both = SheetWith({{Source::Items, Stat::XPBonus, 1, 50},
                                {Source::Items, Stat::XPBonus, 2, 7, Bucket::FlatXP}});
    Check(both.flatXP == 7, "the flat XP bucket is not on the sheet");
    Stats::sheets[player.guid.GetRawValue()] = both;
    Check(Paragon::SheetAward(&player, 72000, true) == 75607, "percent-then-flat is not what was paid");

    // A character the store has never heard of is paid its plain award.
    Player unknown;
    unknown.guid.raw = 999;
    Check(Paragon::SheetAward(&unknown, 500, true) == 500, "a missing sheet changed an award");
    auto const largest = std::numeric_limits<Paragon::XP>::max();
    Check(Paragon::SheetAward(&unknown, largest, true) == largest,
        "solo missing-sheet passthrough acquired an overflow");
}

void TheLevellingHookPaysBelowTheCapAndZeroesAtIt()
{
    Player player;
    Stats::sheets[player.guid.GetRawValue()] = SheetWith({{Source::Items, Stat::XPBonus, 1, 50}});
    Creature killed;
    Unit* victim = &killed;

    player.level = 69;
    uint32 amount = 1000;
    Paragon::OnPlayerGiveXP(&player, amount, victim, 0);
    Check(amount == 1050, "the levelling hook did not pay the sheet's bonus");

    // Quest and exploration XP have no victim, and stats.csv pays for kills.
    amount = 1000;
    Paragon::OnPlayerGiveXP(&player, amount, nullptr, 0);
    Check(amount == 1000, "a non-kill award was paid the bonus");

    // At the cap the core's XP is still zeroed, bonus or no bonus: Paragon has
    // its own award and this hook must not hand out both.
    player.level = 70;
    amount = 1000;
    Paragon::OnPlayerGiveXP(&player, amount, victim, 0);
    Check(amount == 0, "level 70 was paid levelling XP");
}
// #59: execute the production snapshot, both awards and all lifecycle hooks.
void SetXP(Player& player, unsigned id, uint8 level, double gear, double flat = 0)
{
    player.guid.raw = id;
    player.level = level;
    BaseStats base = Seventy();
    base.level = level;
    Stats::sheets[id] = Calculate(base, {{Source::Items, Stat::XPBonus, 1, gear},
        {Source::Items, Stat::XPBonus, 2, flat, Bucket::FlatXP}});
    Paragon::characters[id] = true;
}

void PartyAwards()
{
    for (uint8 level : {69, 70})
        for (unsigned count : {2u, 4u})
        {
            Player a, b, c, d;
            SetXP(a, 101, level, 20);
            SetXP(b, 102, level, 60);
            SetXP(c, 103, level, 100);
            SetXP(d, 104, level, 140);
            std::vector<Player*> members{&a, &b};
            if (count == 4) members.insert(members.end(), {&c, &d});
            Group group(members);
            Creature victim;
            victim.group = &group;
            victim.recipient = &a;
            unsigned const average = count == 2 ? 40 : 80;
            if (level < 70)
            {
                for (Player* member : members)
                {
                    uint32 amount = 1000;
                    Paragon::OnPlayerGiveXP(member, amount, &victim, 0);
                    Check(amount == 1000 + average * 10, "leveling members did not share gear XP");
                }
            }
            else
            {
                Paragon::awards.clear();
                Paragon::OnUnitDeath(&victim, nullptr);
                // Party factor remains 1.1 / 1.3, gear is 4% / 8% at cap.
                auto expected = count == 2 ? 1144u : 1404u;
                for (Player* member : members)
                    Check(Paragon::awards.at(member->GetGUID().GetCounter()) == expected,
                        "Paragon members did not share gear XP after party scaling");
            }
            Paragon::OnUnitDeath(&victim, nullptr);
            Check(!victim.CustomData.Get<Paragon::PartyXPBonus>("DCPartyXPBonus"), "death retained gear snapshot");
        }
}

void EligibilityAndMixedLevels()
{
    Player a, b, c;
    SetXP(a, 201, 69, 20);
    SetXP(b, 202, 70, 60);
    SetXP(c, 203, 70, 100);
    Group group({&a, &b, &c, nullptr});
    Creature victim;
    victim.group = &group;
    victim.recipient = &a;
    c.alive = false;
    auto const* bonus = Paragon::PartyBonus(&victim);
    Check(bonus->hundredths == 1300 && bonus->recipients.size() == 2,
        "mixed party must average 20 and 6, excluding the dead member");
    uint32 amount = 1000;
    Paragon::OnPlayerGiveXP(&a, amount, &victim, 0);
    Check(amount == 1130, "mixed leveling award lost shared percentage");
    Paragon::awards.clear();
    Paragon::OnUnitDeath(&victim, nullptr);
    Check(Paragon::awards.at(202) == 1243 && !Paragon::awards.count(203),
        "mixed Paragon award or dead exclusion is wrong");

    // Paragon keeps its own gates: a gray victim/stock XP-off flag does not
    // disable an otherwise valid at-cap Torment award.
    victim.level = 32;
    b.flags = PLAYER_FLAGS_NO_XP_GAIN;
    Check(Paragon::PartyBonus(&victim)->recipients.size() == 1 &&
        Paragon::PartyBonus(&victim)->hundredths == 600, "leveling gates leaked into Paragon");
    Paragon::ClearPartyBonus(&victim);
    victim.level = 70;
    b.flags = 0;
    c.alive = true;
    c.inRange = false;
    bonus = Paragon::PartyBonus(&victim);
    Check(bonus->recipients.size() == 2, "distant member diluted the average");
    Paragon::ClearPartyBonus(&victim);
    c.inRange = true;
    c.samePhase = false;
    Check(Paragon::PartyBonus(&victim)->recipients.size() == 2, "other phase Paragon member counted");
    Paragon::ClearPartyBonus(&victim);
    c.samePhase = true;
    c.playable = false;
    Check(Paragon::PartyBonus(&victim)->recipients.size() == 2, "unsupported Paragon class counted");
    Paragon::ClearPartyBonus(&victim);
    c.playable = true;
    Paragon::characters.erase(203);
    Check(Paragon::PartyBonus(&victim)->recipients.size() == 2, "unloaded Paragon member counted");
    Paragon::ClearPartyBonus(&victim);

    SetXP(a, 201, 30, 20);
    SetXP(b, 202, 69, 60);
    SetXP(c, 203, 30, 100);
    victim.level = 32;
    c.flags = PLAYER_FLAGS_NO_XP_GAIN;
    bonus = Paragon::PartyBonus(&victim);
    Check(bonus->recipients.size() == 1 && bonus->hundredths == 2000,
        "gray and XP-disabled members diluted the average");
    Paragon::ClearPartyBonus(&victim);
    c.flags = PLAYER_FLAGS_NO_PLAY_TIME;
    Check(Paragon::PartyBonus(&victim)->recipients.size() == 1, "no-play-time member counted");
    Paragon::ClearPartyBonus(&victim);
    c.flags = 0;
    c.session.trial = true;
    Check(Paragon::PartyBonus(&victim)->recipients.size() == 1, "trial cap member counted");
    Paragon::ClearPartyBonus(&victim);

    c.session.trial = false;
    c.samePhase = false;
    Check(Paragon::PartyBonus(&victim)->recipients.size() == 2,
        "stock other-phase leveling recipient was omitted");
    for (Player* member : {&a, &c})
    {
        uint32 amount = 1000;
        Paragon::OnPlayerGiveXP(member, amount, &victim, 0);
        Check(amount == 1600, "other-phase leveling member did not share the same average");
    }
    Paragon::ClearPartyBonus(&victim);
    c.samePhase = true;
    // The same-map tapper remains eligible outside group reward distance.
    a.inRange = false;
    Check(Paragon::PartyBonus(&victim, &a)->recipients.count(201) == 1,
        "remote tapper lost its stock distance exception");
    Paragon::ClearPartyBonus(&victim);
    a.sameMap = false;
    Check(!Paragon::PartyBonus(&victim, &a)->recipients.count(201),
        "remote tapper exception crossed maps");
    Paragon::ClearPartyBonus(&victim);
    a.sameMap = true;
    a.inRange = true;
    // Zero-gear and missing-sheet eligible members still belong in the divisor.
    Stats::sheets.erase(203);
    Check(Paragon::PartyBonus(&victim)->hundredths == 1000, "missing sheet omitted from divisor");
    uint32 sharedAward = 1000;
    Paragon::OnPlayerGiveXP(&c, sharedAward, &victim, 0);
    Check(sharedAward == 1100, "eligible missing-sheet member did not receive shared gear bonus");
}

void NativeTapperSurvivesRoundRobinLoot()
{
    Player tapper, looter;
    SetXP(tapper, 401, 69, 20);
    SetXP(looter, 402, 69, 60);
    Group group({&tapper, &looter});
    Creature victim;
    victim.group = &group;
    victim.recipient = &looter; // Unit::Kill already reassigned round-robin loot.
    tapper.inRange = false;
    KillRewarder rewarder{&tapper, &victim};
    float rate = 1;
    Paragon::OnPlayerRewardKillRewarder(&tapper, &rewarder, false, rate);
    Check(rate == 1, "snapshot changed the native party rate");
    Check(Paragon::PartyBonus(&victim)->recipients.size() == 2,
        "round-robin loot recipient replaced the native remote tapper");
    for (Player* member : {&tapper, &looter})
    {
        uint32 amount = 1000;
        Paragon::OnPlayerRewardKillRewarder(member, &rewarder, false, rate);
        Paragon::OnPlayerGiveXP(member, amount, &victim, 0);
        Check(amount == 1400, "native tapper and looter received different percentages");
    }
    Paragon::OnUnitDeath(&victim, nullptr);
    // A stale round-robin looter outside range is not the native tapper and
    // must not gain a distance exemption merely by owning the loot GUID.
    looter.inRange = false;
    Paragon::OnPlayerRewardKillRewarder(&tapper, &rewarder, false, rate);
    auto const* bonus = Paragon::PartyBonus(&victim);
    Check(bonus->recipients.size() == 1 && bonus->recipients.count(401) && bonus->hundredths == 2000,
        "stale distant round-robin looter diluted the native tapper average");
    Paragon::OnUnitDeath(&victim, nullptr);
    victim.group = nullptr;
    Paragon::OnPlayerRewardKillRewarder(&tapper, &rewarder, false, rate);
    Check(!victim.CustomData.Get<Paragon::PartyXPBonus>("DCPartyXPBonus"),
        "native solo reward hook created a party snapshot");
    Unit nonCreature;
    rewarder.victim = &nonCreature;
    Paragon::OnPlayerRewardKillRewarder(&tapper, &rewarder, false, rate);
    Check(!nonCreature.CustomData.Get<Paragon::PartyXPBonus>("DCPartyXPBonus"),
        "native non-creature reward hook created a snapshot");
}

void SnapshotLifetimeAndSolo()
{
    Player a, b;
    SetXP(a, 301, 69, 20, 7);
    SetXP(b, 302, 69, 60, 11);
    Group group({&a, &b});
    Creature victim;
    victim.group = &group;
    victim.recipient = &a;
    uint32 amount = 1000;
    Paragon::OnPlayerGiveXP(&a, amount, &victim, 0);
    Check(amount == 1407, "flat XP was averaged");
    // Architect's scoped eligibility: a later zero share still counts. The
    // module does not recreate stock group rounding/ModHealth/vehicle math.
    uint32 zeroShare = 0;
    Paragon::OnPlayerGiveXP(&b, zeroShare, &victim, 0);
    Check(zeroShare == 0 && Paragon::PartyBonus(&victim)->recipients.size() == 2,
        "a zero share changed eligibility or gained flat XP");
    // Earlier recipient levels up and its effective sheet changes. The later
    // recipient must still get the original kill's 40% snapshot and own flat.
    SetXP(a, 301, 70, 20, 7);
    amount = 1000;
    Paragon::OnPlayerGiveXP(&b, amount, &victim, 0);
    Check(amount == 1411, "snapshot was recomputed mid-kill");
    victim.disabled = true; // death with no Paragon award still clears it
    Paragon::OnUnitDeath(&victim, nullptr);
    Check(!victim.CustomData.Get<Paragon::PartyXPBonus>("DCPartyXPBonus"), "no-award death retained snapshot");
    victim.disabled = false;
    SetXP(a, 301, 69, 100, 7);
    amount = 1000;
    Paragon::OnPlayerGiveXP(&b, amount, &victim, 0);
    Check(amount == 1811, "second kill/respawn reused first kill average");
    Paragon::OnUnitEnterEvadeMode(&victim, 0);
    Check(!victim.CustomData.Get<Paragon::PartyXPBonus>("DCPartyXPBonus"), "evade retained snapshot");
    Paragon::PartyBonus(&victim);
    Paragon::OnCreatureRemoveWorld(&victim);
    Check(!victim.CustomData.Get<Paragon::PartyXPBonus>("DCPartyXPBonus"), "despawn retained snapshot");
    Paragon::PartyBonus(&victim);
    Paragon::OnCreatureAddWorld(&victim);
    Check(!victim.CustomData.Get<Paragon::PartyXPBonus>("DCPartyXPBonus"), "respawn retained snapshot");

    Paragon::PartyBonus(&victim);
    Rifts::throwOnQuery = true;
    bool threw = false;
    try { Paragon::OnUnitDeath(&victim, nullptr); }
    catch (std::runtime_error const&) { threw = true; }
    Rifts::throwOnQuery = false;
    Check(threw && !victim.CustomData.Get<Paragon::PartyXPBonus>("DCPartyXPBonus"),
        "exception escaped death with a stale snapshot");

    victim.group = nullptr;
    for (uint8 level : {69, 70})
    {
        SetXP(a, 301, level, 20, 7);
        Check(Paragon::PartyBonus(&victim) == nullptr, "solo made a party snapshot");
        if (level < 70)
        {
            amount = 1000;
            Paragon::OnPlayerGiveXP(&a, amount, &victim, 0);
            Check(amount == 1207, "solo leveling changed");
        }
        else
        {
            Paragon::awards.clear();
            Paragon::OnUnitDeath(&victim, nullptr);
            Check(Paragon::awards.at(301) == 1027, "solo Paragon changed");
        }
    }
}

}

int main()
{
    try
    {
        PartyAwards();
        EligibilityAndMixedLevels();
        SnapshotLifetimeAndSolo();
        NativeTapperSurvivesRoundRobinLoot();
        ThePublisherCastsTheSheetsTotalAsOneAura();
        ThePublisherUpdatesInPlaceAndTakesTheAuraAwayAgain();
        ASlowLandsBesideTheBonusAndLeavesItAlone();
        TheSlowLandsOnThePlayerAndCarriesTheElitesGuid();
        TwoElitesSlowingAtOnceEachKeepTheirOwnClock();
        TwoAffixesSlowingAtOnceAreTwoSeparateDebuffs();
        TheVisibleSlowStillSaysTwoCastersMayHoldIt();
        OneEliteRefreshesItsOwnSlow();
        AMapChangeTakesEverySlowAndNothingElse();
        TheSheetIsAppliedToAKillAndOnlyToAKill();
        TheLevellingHookPaysBelowTheCapAndZeroesAtIt();
        std::printf("ok\n");
        return 0;
    }
    catch (std::exception const& error)
    {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
