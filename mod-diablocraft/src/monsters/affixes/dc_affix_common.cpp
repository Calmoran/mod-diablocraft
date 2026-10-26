// World of DiabloCraft - elite packs: the affix numbers, the roll, promotion, the `.dc elite` harness and the pack helpers.

#include "dc_affix_internal.h"
#include "../dc_family_ai.h"
#include "ABScriptMgr.h"
#include "../../rifts/dc_rift_pace.h"

#include "../../rifts/dc_rifts.h"
#include "../../common/dc_tunables.h"
#include "../dc_monster_ai.h"
#include "../../rifts/dc_gr_progress.h"
#include "../../rifts/dc_rifts_internal.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_pylons.h"
#include "../../combat/dc_spell_shells.h"
#include "../../stats/dc_movement_math.h"
#include "../../difficulty/dc_difficulty.h"
#include "../../common/dc_world.h"

#include "Chat.h"
#include "CombatAI.h"
#include "Creature.h"
#include "ScriptedCreature.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "ThreatManager.h"
#include "DatabaseEnv.h"
#include "GridNotifiers.h"
#include "Group.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PathGenerator.h"
#include "ScriptMgr.h"
#include "World.h"
#include "WorldSession.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <chrono>
#include <functional>
#include <list>
#include <iterator>
#include <map>
#include <memory>
#include <unordered_set>
#include <limits>
#include <mutex>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>


namespace DC::Rifts
{
std::vector<Affix> affixPool;
std::vector<std::pair<unsigned, unsigned>> affixCounts;
double elitePromotionPct = 0;
// Audit row 75: loaded from dc_loot_tuning's elite row at world load
// (dc_rifts.cpp), so this is only the value before that load has happened. It
// used to repeat the table's 3; 0 says "unknown yet" and costs a champion its
// companions for that window rather than inventing a pack size.
unsigned championPackSize = 0;
// The tunables, or null before the world has loaded. Every affix path takes its
// own copy of the pointer and works off that, so it can never see half a reload.
std::shared_ptr<AffixNumbers const> Numbers()
{
    std::lock_guard<std::mutex> lock(dataMutex);
    return affixNumbers;
}
// The table is in seconds, because that is how D3 published it; the module runs
// on milliseconds.
std::uint32_t Ms(double seconds)
{
    double const milliseconds = seconds * 1000.0;
    return static_cast<std::uint32_t>(std::clamp(milliseconds, 0.0,
        double(std::numeric_limits<std::uint32_t>::max()) - 0.5) + 0.5);
}
// Read dc_affix_tunables and build one snapshot of it. Every parameter the
// module reads has to be there: a missing row means the migration has not been
// applied, and inventing a fallback here would put back into the code the
// constant 13-elite-affixes §2 says must not be in it. Returns null and fills
// `error` instead, which is what `.dc affix reload` prints and what startup logs.
std::shared_ptr<AffixNumbers const> BuildAffixNumbers(std::string& error)
{
    QueryResult rows = WorldDatabase.Query(
        "SELECT affix_name, parameter, d3_value, tuned_value FROM dc_affix_tunables");
    if (!rows)
    {
        error = "dc_affix_tunables is empty or missing; apply rifts_0010_affix_tunables.sql";
        return nullptr;
    }
    auto built = std::make_shared<AffixNumbers>();
    do
    {
        Field* f = rows->Fetch();
        std::string const key = f[0].Get<std::string>() + "|" + f[1].Get<std::string>();
        // tuned_value when one has been set, d3_value otherwise. A row with
        // neither is a parameter nobody has chosen a value for yet; it is left
        // out, so asking for it is a missing-parameter error and not a silent 0.
        if (!f[3].IsNull())
            built->value[key] = f[3].Get<double>();
        else if (!f[2].IsNull())
            built->value[key] = f[2].Get<double>();
        else
            built->unconfigured[f[0].Get<std::string>()].push_back(f[1].Get<std::string>());
        auto const value = built->value.find(key);
        if (value != built->value.end() && (!std::isfinite(value->second) || value->second < 0.0))
        {
            error = "Invalid non-finite/negative affix parameter: " + key;
            return nullptr;
        }
    } while (rows->NextRow());

    std::vector<std::string> missing;
    auto need = [&](char const* affix, char const* parameter) -> double
    {
        std::string const key = std::string(affix) + "|" + parameter;
        auto found = built->value.find(key);
        if (found != built->value.end())
            return found->second;
        if (std::string(affix) == "_global" || built->Enabled(affix))
            missing.push_back(key);
        return 0.0; // Unconfigured affixes cannot reach the execution paths.
    };
    // A percentage in the table, a multiplier in the code, in the direction the
    // affix reads: +40% move speed is x1.40, an 80% slow is x0.20 of base speed.
    auto gain = [&](char const* affix, char const* parameter)
    { return 1.0 + need(affix, parameter) / 100.0; };
    auto loss = [&](char const* affix, char const* parameter)
    { return 1.0 - need(affix, parameter) / 100.0; };

    AffixNumbers& n = *built;
    // A cadence of zero would fire an affix on every map update rather than on a
    // timer, so the two shared clocks have a one-millisecond floor. It is a
    // guard against a typo in `.dc affix set`, not a tuning decision.
    n.castMs = std::max<std::uint32_t>(1, Ms(need("_global", "cast_interval")));
    n.tickMs = std::max<std::uint32_t>(1, Ms(need("_global", "tick_interval")));
    n.procPct = need("_global", "proc_chance");
    // Reuse the difficulty CSV's existing WORLD table. Cache at startup/reload,
    // never query the database during a hit or multiply by party/swing scaling.
    if (QueryResult tiers = WorldDatabase.Query(
        "SELECT p.tier_id,t.monster_damage_multiplier_pct FROM dc_tier_phase p "
        "JOIN dc_difficulty_tiers t ON t.tier=p.tier_name"))
        do
        {
            Field* row = tiers->Fetch();
            double const factor = row[1].Get<double>() / 100.0;
            if (std::isfinite(factor) && factor > 0.0)
                n.tierDamage[row[0].Get<unsigned>()] = factor;
        } while (tiers->NextRow());
    for (unsigned tier = 1; tier <= DC::LaunchTierCount(); ++tier)
        if (!n.tierDamage.count(tier))
            missing.push_back("difficulty tier " + std::to_string(tier));
    n.minionSpread = static_cast<float>(need("_global", "minion_spread"));
    n.knockbackSpeedZ = static_cast<float>(need("_global", "knockback_speed_z"));
    n.rareMinionsMin = static_cast<unsigned>(need("_global", "rare_minions_min"));
    n.rareMinionsMax = static_cast<unsigned>(need("_global", "rare_minions_max"));
    n.offensiveMin = static_cast<unsigned>(need("_global", "offensive_min"));
    n.offensiveMax = static_cast<unsigned>(need("_global", "offensive_max"));
    n.defensiveMax = static_cast<unsigned>(need("_global", "defensive_max"));
    n.crowdControlMax = static_cast<unsigned>(need("_global", "crowd_control_max"));
    n.levelLimitFrom = static_cast<unsigned>(need("_global", "level_limit_from"));
    n.levelLimitMax = static_cast<unsigned>(need("_global", "level_limit_max"));

    n.beamArmMs = Ms(need("Arcane Enchanted", "arming_delay"));
    n.beamMs = Ms(need("Arcane Enchanted", "duration"));
    n.beamLength = static_cast<float>(need("Arcane Enchanted", "beam_length"));
    n.avengerDamage = need("Avenger", "damage_bonus") / 100.0;
    n.desecratorArmMs = Ms(need("Desecrator", "arming_delay"));
    n.desecratorRadius = static_cast<float>(need("Desecrator", "radius"));
    n.fastMove = static_cast<float>(gain("Fast", "move_speed"));
    n.fastAttack = gain("Fast", "attack_speed");
    n.chainsWidth = static_cast<float>(need("Fire Chains", "chain_width"));
    n.chainsMembers = static_cast<unsigned>(need("Fire Chains", "activation_members"));
    n.frozenArmMs = Ms(need("Frozen", "time_to_explode"));
    n.frozenRadius = static_cast<float>(need("Frozen", "radius"));
    n.pulseArmMs = Ms(need("Frozen Pulse", "arming_delay"));
    n.pulseMs = Ms(need("Frozen Pulse", "duration"));
    n.pulseRadius = static_cast<float>(need("Frozen Pulse", "radius"));
    n.pulseSlow = static_cast<float>(loss("Frozen Pulse", "slow_percent"));
    n.pulseSlowSpell = Combat::Shells::AffixSlowFor("Frozen Pulse");
    n.healthLinkFloor = need("Health Link", "low_life_floor") / 100.0;
    n.hordeMultiplier = static_cast<unsigned>(need("Horde", "minion_multiplier"));
    n.illusionMin = static_cast<unsigned>(need("Illusionist", "copies_min"));
    n.illusionMax = static_cast<unsigned>(need("Illusionist", "copies_max"));
    n.illusionLife = need("Illusionist", "copy_life") / 100.0;
    n.illusionTrigger = need("Illusionist", "trigger_hp") / 100.0;
    n.jailerReach = static_cast<float>(need("Jailer", "reach"));
    n.jailerRootMs = Ms(need("Jailer", "root_duration"));
    n.juggernautMove = static_cast<float>(loss("Juggernaut", "move_speed_reduction"));
    // +30% damage TAKEN, and no Life bonus.
    n.juggernautTaken = gain("Juggernaut", "damage_taken_increase");
    n.juggernautLife = gain("Juggernaut", "health_bonus");
    n.knockbackSlow = static_cast<float>(loss("Knockback", "slow_percent"));
    n.knockbackSlowSpell = Combat::Shells::AffixSlowFor("Knockback");
    n.knockbackMs = Ms(need("Knockback", "slow_duration"));
    n.moltenTrailRadius = static_cast<float>(need("Molten", "trail_radius"));
    n.moltenBlastRadius = static_cast<float>(need("Molten", "explosion_radius"));
    n.moltenFuseMs = Ms(need("Molten", "explosion_delay"));
    n.mortarShells = static_cast<unsigned>(need("Mortar", "shells_per_volley"));
    n.mortarVolleyMs = Ms(need("Mortar", "volley_interval"));
    n.mortarArmMs = Ms(need("Mortar", "impact_warning"));
    n.mortarDeadZone = static_cast<float>(need("Mortar", "dead_zone"));
    n.mortarSplash = static_cast<float>(need("Mortar", "collateral_radius"));
    n.nightmarishMs = Ms(need("Nightmarish", "fear_duration"));
    n.orbiterRadius = static_cast<float>(need("Orbiter", "central_radius"));
    n.orbiterMs = Ms(need("Orbiter", "duration"));
    n.plaguedRadius = static_cast<float>(need("Plagued", "radius"));
    n.poisonPools = static_cast<unsigned>(need("Poison Enchanted", "trails_per_cast"));
    n.poisonArmMs = Ms(need("Poison Enchanted", "arming_delay"));
    n.poisonMs = Ms(need("Poison Enchanted", "trail_lifetime"));
    n.poisonWidth = static_cast<float>(need("Poison Enchanted", "trail_width"));
    n.reflectArmMs = Ms(need("Reflects Damage", "warning"));
    n.reflectMs = Ms(need("Reflects Damage", "active_duration"));
    n.shieldingMs = Ms(need("Shielding", "duration"));
    n.shieldingGapMs = Ms(need("Shielding", "gap"));
    n.teleporterRange = static_cast<float>(need("Teleporter", "range"));
    n.thunderstormStrikes = static_cast<unsigned>(need("Thunderstorm", "strikes_per_cast"));
    n.thunderstormRadius = static_cast<float>(need("Thunderstorm", "radius"));
    n.vortexRange = static_cast<float>(need("Vortex", "pull_range"));

    // Knockback and Vortex both cover a DISTANCE, and MotionMaster wants two
    // speeds; the horizontal one is the core's own parabola solved for the
    // distance on the tuned vertical speed (docs/research/knockback-speeds.md).
    // Passing the distance itself is what launched a player off the map.
    if (n.knockbackSpeedZ > 0.0f)
        n.knockbackSpeedXY = static_cast<float>(need("Knockback", "distance"))
            * KNOCKBACK_GRAVITY / (2.0f * n.knockbackSpeedZ);
    else
        missing.emplace_back("_global|knockback_speed_z (must be above zero)");

    // Each slowing affix casts its own record, so the
    // debuff the player is shown carries the affix's name. The ids come from
    // the generated shells header and are looked up by that same name, so a
    // zero here means the generator and this file disagree about which affixes
    // slow. That is a mistake to report at startup, not one to discover as a
    // slow that silently never lands - and it is a different failure from an
    // unconfigured tunable, so it says so in its own words.
    if (!n.pulseSlowSpell || !n.knockbackSlowSpell)
    {
        error = "no generated slow record for Frozen Pulse or Knockback; "
                "re-run scripts/generate/classes/generate_spells.py and apply the spell migration";
        return nullptr;
    }

    if (!missing.empty())
    {
        std::ostringstream list;
        for (std::string const& key : missing)
            list << (list.tellp() > 0 ? ", " : "") << key;
        error = "dc_affix_tunables has no value for: " + list.str()
              + "; apply rifts_0010_affix_tunables.sql";
        return nullptr;
    }
    auto disableMissing = [&](std::string const& key)
    {
        auto const split = key.find('|');
        auto& parameters = built->unconfigured[key.substr(0, split)];
        std::string const parameter = key.substr(split + 1);
        if (std::find(parameters.begin(), parameters.end(), parameter) == parameters.end())
            parameters.push_back(parameter);
    };
    for (char const* key : {
        "Arcane Enchanted|wedge_width",
        "Avenger|attack_speed_bonus",
        "Avenger|model_size_bonus",
        "Avenger|move_speed_bonus",
        "Desecrator|damage_stack_interval",
        "Desecrator|damage_stack_max",
        "Desecrator|damage_stack_multiplier",
        "Desecrator|pool_lifetime",
        "Electrified|bolt_length",
        "Electrified|bolt_radius",
        "Electrified|bolt_speed",
        "Electrified|bolts_full_life",
        "Electrified|bolts_near_death",
        "Electrified|internal_cooldown",
        "Fire Chains|tick_rate",
        "Frozen Pulse|chase_speed",
        "Fast|cast_speed",
        "Juggernaut|crowd_control_immune",
        "Frozen|crystal_spread",
        "Frozen|freeze_duration",
        "Frozen|orbs_per_cast",
        "Health Link|link_range",
        "Illusionist|cooldown",
        "Illusionist|despawn_distance",
        "Jailer|cooldown",
        "Knockback|cooldown",
        "Molten|trail_interval",
        "Molten|trail_lifetime",
        "Mortar|direct_radius",
        "Orbiter|max_radius",
        "Orbiter|max_radius_champion",
        "Orbiter|orbit_speed",
        "Orbiter|sphere_radius",
        "Orbiter|spheres_max",
        "Orbiter|spheres_min",
        "Plagued|cast_interval",
        "Plagued|damage_stack_interval",
        "Plagued|damage_stack_max",
        "Plagued|damage_stack_multiplier",
        "Plagued|pool_lifetime",
        "Poison Enchanted|cooldown",
        "Poison Enchanted|trail_length",
        "Reflects Damage|internal_cooldown",
        "Thunderstorm|follow_speed",
        "Thunderstorm|strike_interval"})
        if (!built->value.count(key))
            disableMissing(key);
    for (char const* name : {"Arcane Enchanted", "Desecrator", "Electrified", "Fire Chains", "Frozen",
                            "Frozen Pulse", "Jailer", "Molten", "Mortar", "Orbiter", "Plagued",
                            "Poison Enchanted", "Reflects Damage", "Thunderstorm"})
        if (!built->value.count(std::string(name) + "|base_damage"))
            disableMissing(std::string(name) + "|base_damage");
    for (char const* key : {"Molten|base_explosion_damage", "Mortar|base_collateral_damage",
                           "Electrified|bolt_speed", "Electrified|bolt_radius", "Electrified|bolt_length",
                           "Orbiter|orbit_speed", "Orbiter|max_radius", "Orbiter|max_radius_champion", "Poison Enchanted|trail_length",
                           "Plagued|pool_lifetime", "Desecrator|pool_lifetime",
                           "Health Link|link_range", "Frozen Pulse|chase_speed", "Frozen|crystal_spread", "Thunderstorm|strike_interval", "Thunderstorm|follow_speed"})
        if (!built->value.count(key))
            disableMissing(key);
    return built;
}
// Swap in a fresh snapshot. `.dc affix reload` and startup both come here, and
// a failed read leaves the previous snapshot in place rather than disarming
// every affix on the map.
bool ReloadAffixNumbers(std::string& error)
{
    std::shared_ptr<AffixNumbers const> built = BuildAffixNumbers(error);
    if (!built)
        return false;
    for (auto const& disabled : built->unconfigured)
    {
        std::ostringstream list;
        for (auto const& parameter : disabled.second)
            list << (list.tellp() > 0 ? ", " : "") << parameter;
        LOG_WARN("server", "[DC affixes] {} DISABLED: the designer sets {}. No fallback values; fill CSV and regenerate/apply SQL, then .dc affix reload.", disabled.first, list.str());
    }
    std::lock_guard<std::mutex> lock(dataMutex);
    affixNumbers = std::move(built);
    return true;
}
// All affix damage enters here, Reflects Damage too.
// Unchosen damage is blocked,
// not silently converted back into a monster-swing fraction.
double AffixDamage(AffixNumbers const& n, unsigned tier, std::string const& name,
                   char const* parameter)
{
    auto const base = n.value.find(name + "|" + parameter);
    auto const factor = n.tierDamage.find(tier);
    if (base == n.value.end() || factor == n.tierDamage.end())
        return 0.0;
    double const damage = base->second * factor->second;
    return std::isfinite(damage) && damage > 0.0 ? damage : 0.0;
}
// Inside a Greater Rift (grLevel above 0) the same base number is multiplied
// by the level's damage factor instead of the tier's, as the monster's own damage is.
double AffixDamage(AffixNumbers const& n, unsigned tier, unsigned grLevel, std::string const& name,
                   char const* parameter)
{
    if (!grLevel)
        return AffixDamage(n, tier, name, parameter);
    auto const base = n.value.find(name + "|" + parameter);
    if (base == n.value.end())
        return 0.0;
    double const damage = base->second * DC::Difficulty::GreaterRiftDamage(grLevel);
    return std::isfinite(damage) && damage > 0.0 ? damage : 0.0;
}
std::vector<Promotion> promotions;
std::vector<Burst> bursts;
std::vector<Zone> zones;
std::mutex harnessMutex;
std::unordered_map<std::uint64_t, HarnessPack> harnessPacks;
std::atomic<unsigned> harnessCount{0};
// Guardians retain their existing mechanics. Elite affixes never use this
// swing helper: their damage is their own base amount times the tier multiplier.
double SwingDamage(Unit const* unit)
{
    double const low = unit->GetFloatValue(UNIT_FIELD_MINDAMAGE);
    double const high = unit->GetFloatValue(UNIT_FIELD_MAXDAMAGE);
    double const average = (low + high) / 2.0;
    // A creature with no weapon damage on its template still has to hit for
    // something; its level is the only other scale available. tunables:monsters.
    return average > 0
               ? average
               : unit->GetLevel() * DC::Tunables::Get("monsters", "fallback_swing_damage_per_level");
}
// elite_affix_count.csv: 1 affix below level 30, rising to 4 at 60-70.
unsigned AffixCountFor(unsigned level)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    for (auto const& [maxLevel, count] : affixCounts)
        if (level <= maxLevel)
            return count;
    return affixCounts.empty() ? 0 : affixCounts.back().second;
}
// 13-elite-affixes §4.3. Plagued and Desecrator are the same pool of escalating
// sludge with two placements, and the wiki says a pack never gets both.
bool ExcludedBy(std::vector<Affix> const& chosen, Affix const& candidate)
{
    for (Affix const& taken : chosen)
        if ((taken.name == "Plagued" && candidate.name == "Desecrator")
            || (taken.name == "Desecrator" && candidate.name == "Plagued"))
            return true;
    return false;
}
// Draw `wanted` affixes out of `from`, refusing any the rules already forbid.
// Returns false when the pool runs out of candidates the rules allow, which is
// what makes the caller try a different pool split rather than a shorter pack.
bool DrawInto(std::vector<Affix>& chosen, std::vector<Affix> from, unsigned wanted,
              unsigned level, AffixNumbers const& numbers)
{
    for (unsigned drawn = 0; drawn < wanted; ++drawn)
    {
        // §4.3: from level 60 a pack carries at most three of the eleven, and
        // that list crosses all three pools, so it is counted over the whole
        // selection and not per pool.
        unsigned limited = 0;
        for (Affix const& taken : chosen)
            if (taken.levelLimited)
                ++limited;
        bool const capped = level >= numbers.levelLimitFrom && limited >= numbers.levelLimitMax;

        std::vector<std::size_t> allowed;
        for (std::size_t index = 0; index < from.size(); ++index)
            if (!(capped && from[index].levelLimited) && !ExcludedBy(chosen, from[index]))
                allowed.push_back(index);
        if (allowed.empty())
            return false;
        std::size_t const pick =
            allowed[std::uniform_int_distribution<std::size_t>(0, allowed.size() - 1)(Engine())];
        chosen.push_back(from[pick]);
        from.erase(from.begin() + static_cast<long>(pick));
    }
    return true;
}
// The affixes a pack rolls (13-elite-affixes §4).
//
// Eligibility is the CSVs' own: `appears_on` for champion versus rare, the level
// and tier gates parsed out of min_difficulty, and `rollable`, which is how
// Missile Dampening stays out of the pool while 3.3.5a cannot slow a projectile.
//
// Composition is maxroll's rule rather than a table of forbidden pairs: 2-3
// Offensive, at most 1 Defensive, at most 1 Crowd Control. That plus appears_on
// enforces every real pair in elite_affix_exclusions.csv for free. The two extra
// rules are §4.3's - Plagued never with Desecrator, and at most three of the
// eleven from level 60.
std::vector<Affix> RollAffixes(bool rare, unsigned tier, unsigned level)
{
    std::shared_ptr<AffixNumbers const> const numbers = Numbers();
    if (!numbers)
        return {};
    std::vector<Affix> offensive, defensive, crowdControl;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        for (Affix const& affix : affixPool)
        {
            if (!affix.rollable || affix.behaviour.empty() || !numbers->Enabled(affix.name))
                continue;
            if (affix.appearsOn != "both" && affix.appearsOn != (rare ? "rare" : "champion"))
                continue;
            if (tier < affix.minTier || level < affix.minLevel)
                continue;
            if (affix.pool == "defensive")
                defensive.push_back(affix);
            else if (affix.pool == "crowd_control")
                crowdControl.push_back(affix);
            else
                offensive.push_back(affix);
        }
    }
    unsigned const wanted = AffixCountFor(level);
    if (!wanted)
        return {};

    // Every split of `wanted` the composition rule allows. At four affixes those
    // are 2/1/1, 3/1/0 and 3/0/1; below three the offensive floor comes down to
    // the pack size, because a pack of one cannot carry two of anything.
    unsigned const offMin = std::min(numbers->offensiveMin, wanted);
    unsigned const offMax = std::min(numbers->offensiveMax, wanted);
    std::vector<std::array<unsigned, 3>> splits;
    for (unsigned off = offMin; off <= offMax; ++off)
        for (unsigned def = 0; def <= numbers->defensiveMax; ++def)
            for (unsigned cc = 0; cc <= numbers->crowdControlMax; ++cc)
                if (off + def + cc == wanted && off <= offensive.size()
                    && def <= defensive.size() && cc <= crowdControl.size())
                    splits.push_back(std::array<unsigned, 3>{off, def, cc});
    std::shuffle(splits.begin(), splits.end(), Engine());

    // The small pools are drawn first: they are the ones the level-60 cap and
    // the Plagued/Desecrator rule are most likely to empty.
    std::vector<Affix> best;
    for (std::array<unsigned, 3> const& split : splits)
    {
        std::vector<Affix> chosen;
        bool const filled = DrawInto(chosen, defensive, split[1], level, *numbers)
                         && DrawInto(chosen, crowdControl, split[2], level, *numbers)
                         && DrawInto(chosen, offensive, split[0], level, *numbers);
        if (filled)
            return chosen;
        if (chosen.size() > best.size())
            best = std::move(chosen);
    }
    // No split filled - a pool was too small, or the rules ruled out the last
    // pick. The pack takes the longest legal partial rather than nothing.
    if (best.empty())
        DrawInto(best, offensive, std::min<unsigned>(wanted, offensive.size()), level, *numbers);
    LOG_DEBUG("server", "[DC rifts] affix roll fell back to {} of {} affixes for a {} pack",
              best.size(), wanted, rare ? "rare" : "champion");
    return best;
}
// 03 §5. Everything the stock 3.3.5a client can be told about one spawn: the
// glow aura, and a size bump on top of whatever scale the clone's model row
// gives it. The rank (elite border on the nameplate and the target frame) is
// on the clone template itself - rank travels per entry, not per spawn
// (engine-facts.md Q3.2), so generate_rift_elites.py sets it to 1 for a
// champion and 2 for a rare and nothing here can change it.
void ApplyEliteLook(Creature* creature, bool rare, bool minion)
{
    if (!creature)
        return;
    double scale = 1.0;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        scale = minion ? minionScale : rare ? rareScale : championScale;
    }
    if (scale > 0)
        creature->SetObjectScale(creature->GetNativeObjectScale() * static_cast<float>(scale));
    if (minion)
        return;                       // 03 §5: minions keep the pack's affixes, not its look
    // The aura is applied rather than cast: a dummy visual has no cast time,
    // no school and nothing to resist, and AddAura skips all of it.
    if (Aura* glow = creature->AddAura(rare ? RARE_GLOW : CHAMPION_GLOW, creature))
    {
        // Both spells are already infinite in Spell.dbc; setting it again means
        // a future data change cannot quietly make the glow fall off mid-fight.
        glow->SetMaxDuration(-1);
        glow->SetDuration(-1);
    }
    else
        LOG_WARN("server", "[DC rifts] elite glow {} could not be applied to creature {}",
                 rare ? RARE_GLOW : CHAMPION_GLOW, creature->GetEntry());
}
void PublishElite(Creature const* elite, EliteState const& state, std::uint32_t instanceId)
{
    std::string affixes;
    for (Affix const& affix : state.affixes)
        affixes += (affixes.empty() ? "" : ", ") + affix.name;
    CharacterDatabase.Execute(
        "REPLACE INTO dc_rift_elite (instance_id,creature_guid,entry,elite_rank,name,affixes) "
        "VALUES ({},{},{},'{}','{}','{}')",
        instanceId, elite->GetGUID().GetCounter(), elite->GetEntry(),
        state.rare ? "Rare" : "Champion",
        Escape(elite->GetName()), Escape(affixes));
}
void UnpublishElite(std::uint32_t instanceId, std::uint64_t creatureGuid)
{
    CharacterDatabase.Execute("DELETE FROM dc_rift_elite WHERE instance_id={} AND creature_guid={}",
                              instanceId, creatureGuid);
}
// What a member of this pack carries.
//
// 13-elite-affixes §4.1: minion inheritance is PER AFFIX and not all-or-nothing,
// and elite_affix_eligibility.csv's `minion` column is the authority. Ten of the
// 28 pass to a Rare's minions - Electrified, Fast, Knockback, Molten, Mortar,
// Nightmarish, Plagued, Reflects Damage, Shielding, Teleporter - and the other
// eighteen are leader-only, because ground casts, projectile casts, portals,
// walls and beams do not come from minions. This supersedes the
// "every member carries every affix" rule for ROLLED packs.
//
// `.dc elite` is the exception and passes inherit = false: the harness forces
// one affix onto the whole pack on purpose, so that a leader-only affix can be
// watched on three bodies at once. It is a test tool, not the game.
std::vector<Affix> MemberAffixes(std::vector<Affix> const& packAffixes, bool inherit)
{
    if (!inherit)
        return packAffixes;
    std::vector<Affix> mine;
    for (Affix const& affix : packAffixes)
        if (affix.minionInherits)
            mine.push_back(affix);
    return mine;
}
// Everything a promotion is once the body and the place are settled: the clone
// entry, the elite look, the affixes, the nameplate row and the companions.
// Promote() feeds it a native spawn's entry and position and asks for rolled
// affixes; `.dc elite` feeds it the harness body, the caller's position and the
// caller as summoner (which puts the pack in the caller's tier phase), and the
// one affix to carry instead of a roll. Every member carries the pack's
// per-member affixes and runs them (09 §2 step 2), so the
// harness and a real promotion produce the same pack. The affixes are settled
// before the companions are summoned, because Horde is an affix that changes
// how many there are. Returns the pack leader.
Creature* SpawnElitePack(Map* map, std::uint32_t entry, Position const& at, bool rare,
                         unsigned tier, unsigned level, bool rollAffixes,
                         std::vector<Affix> const& preset,
                         std::uint32_t instanceId, WorldObject* summoner)
{
    std::uint32_t const clone = (rare ? RARE_BASE : CHAMPION_BASE) + entry;
    if (!map || !sObjectMgr->GetCreatureTemplate(clone))
        return nullptr;               // not in the pool generate_rift_elites.py saw
    float const x = at.GetPositionX(), y = at.GetPositionY();
    float const z = at.GetPositionZ(), o = at.GetOrientation();

    Creature* elite = map->SummonCreature(clone, at, nullptr, 0, summoner);
    if (!elite)
        return nullptr;
    // This map now holds elite work for its unit hook to find. The flag clears
    // when the map dies or the last `.dc elite` pack on it is cleared.
    map->CustomData.GetDefault<AffixMapFlag>("DCRiftAffixMap");
    // 09 F2: no rift monster keeps its WoW abilities. In a rift the add-to-world
    // hook has already done this; outside one it is what makes the pack a plain
    // melee body carrying nothing but the affix.
    StripNativeAbilities(elite);
    auto* state = elite->CustomData.GetDefault<EliteState>("DCRiftElite");
    state->rare = rare;
    state->tier = tier;
    state->grLevel = DC::Rifts::GreaterRiftLevel(map);
    state->affixes = rollAffixes ? RollAffixes(rare, tier, level) : preset;
    ApplyEliteLook(elite, rare, false);
    ApplyPassiveAffixes(elite, *state);
    PublishElite(elite, *state, instanceId);

    // 03 §5 calls a champion a blue *pack*, and Avenger, Fire Chains and Health
    // Link are champion-only affixes with nothing to act on unless a champion
    // has company. A champion brings championPackSize - 1 identical champions
    // (3 in total, itself included, a fixed count and
    // not a range). A rare brings the base 2 to 4 minions, doubled to 4 to 8
    // when it rolled Horde. elite_affix_eligibility.csv's `minion` column
    // filters a RARE's minions only (13-elite-affixes §4.1): a
    // champion is three of the same monster, so every clone carries all rolled
    // affixes in full.
    std::shared_ptr<AffixNumbers const> const numbers = Numbers();
    unsigned count;
    if (rare && numbers)
    {
        unsigned const low = numbers->rareMinionsMin, high = numbers->rareMinionsMax;
        count = low + static_cast<unsigned>(Roll() * (high - low + 1));
        count = HordeMinions(*state, *numbers, count);
    }
    else if (rare)
        count = 0;
    else
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        count = championPackSize > 0 ? championPackSize - 1 : 0;
    }
    std::uint32_t const companion = rare ? entry : clone;
    for (unsigned index = 0; index < count; ++index)
    {
        float const angle = static_cast<float>(index) / count * 2.0f * float(M_PI);
        float const spread = numbers ? numbers->minionSpread : HARNESS_SPREAD;
        Position spot(x + spread * std::cos(angle),
                      y + spread * std::sin(angle), z, o);
        // A summon has no spawn id, so a member can never be promoted in its own
        // right. It is a normal kill for loot.
        Creature* member = map->SummonCreature(companion, spot, nullptr, 0, summoner);
        if (!member)
            continue;
        StripNativeAbilities(member);
        ApplyEliteLook(member, rare, rare);
        member->CustomData.GetDefault<MinionState>("DCRiftMinion")->leader = elite->GetGUID();
        auto* mine = member->CustomData.GetDefault<EliteState>("DCRiftElite");
        mine->rare = rare;
        mine->member = true;
        mine->tier = tier;
        mine->grLevel = state->grLevel;
        mine->life = state->life;
        mine->life->Joined();
        mine->affixes = MemberAffixes(state->affixes, rollAffixes && rare);
        ApplyPassiveAffixes(member, *mine);
        state->pack.push_back(member->GetGUID());
    }
    // 13 S10 visuals: the pair set is settled once the members exist, and the
    // beams live until a member dies (TearDownBeams). Fire Chains keeps its own
    // activation count; Health Link is active from two members.
    if (numbers)
    {
        if (HasAffix(*state, "chains"))
            ApplyPackBeams(elite, *state, FIRE_CHAINS_BEAM, numbers->chainsMembers);
        if (HasAffix(*state, "healthlink"))
            ApplyPackBeams(elite, *state, HEALTH_LINK_BEAM, 2);
    }
    return elite;
}
// Swap one native spawn for its champion or rare clone. Runs on the map's own
// update, never inside the add-to-world hook that chose it: summoning there
// would re-enter the same hook, and despawning a creature while it is being
// added is not something the core expects.
void Promote(Map* map, Promotion const& promotion, unsigned tier)
{
    Creature* native = map->GetCreature(promotion.guid);
    if (!native || !native->IsAlive() || native->IsInCombat())
        return;
    std::uint32_t const entry = native->GetEntry();
    if (!sObjectMgr->GetCreatureTemplate((promotion.rare ? RARE_BASE : CHAMPION_BASE) + entry))
        return;                       // not in the pool generate_rift_elites.py saw
    Position const at(native->GetPositionX(), native->GetPositionY(),
                      native->GetPositionZ(), native->GetOrientation());
    unsigned const level = native->GetLevel();

    // The native is gone for the run: a respawn longer than any instance lives
    // keeps it from coming back and being promoted a second time.
    native->DespawnOrUnsummon(0ms, Seconds(7 * DAY));

    SpawnElitePack(map, entry, at, promotion.rare, tier, level, true, {},
                   promotion.instanceId, nullptr);
}
// True when a `.dc elite` pack is standing on this map, which is what makes an
// open-world map drain the affix work a rift map drains. The atomic keeps the
// common answer - no harness anywhere - off the mutex.
bool HarnessOnMap(Map const* map)
{
    if (!map || harnessCount.load(std::memory_order_relaxed) == 0)
        return false;
    std::lock_guard<std::mutex> lock(harnessMutex);
    for (auto const& owned : harnessPacks)
        if (owned.second.mapId == map->GetId()
            && owned.second.instanceId == map->GetInstanceId())
            return true;
    return false;
}
// Despawn this GM's test pack, leader and members, and take its nameplate row
// with it. Returns how many creatures went, so `.dc elite clear` can say.
unsigned ClearHarness(Player const* player)
{
    HarnessPack pack;
    {
        std::lock_guard<std::mutex> lock(harnessMutex);
        auto found = harnessPacks.find(player ? player->GetGUID().GetRawValue() : 0);
        if (found == harnessPacks.end())
            return 0;
        pack = found->second;
        harnessPacks.erase(found);
        harnessCount.store(static_cast<unsigned>(harnessPacks.size()),
                           std::memory_order_relaxed);
    }
    UnpublishElite(pack.instanceId, pack.leader.GetCounter());
    Map* map = sMapMgr->FindMap(pack.mapId, pack.instanceId);
    if (!map)
        return 0;
    ClearPackAffixWork(map, pack);
    unsigned gone = 0;
    // Members are held on the pack as well as on the leader, so a pack whose
    // leader is already dead still clears completely.
    for (ObjectGuid const& guid : pack.members)
        if (Creature* member = map->GetCreature(guid))
        {
            member->DespawnOrUnsummon();
            ++gone;
        }
    if (Creature* leader = map->GetCreature(pack.leader))
    {
        leader->DespawnOrUnsummon();
        ++gone;
    }
    // An open-world map keeps its elite flag only while some harness pack is
    // still standing on it; a rift map clears its own when the map is destroyed.
    if (!map->IsDungeon())
    {
        bool other = false;
        {
            std::lock_guard<std::mutex> lock(harnessMutex);
            for (auto const& owned : harnessPacks)
                if (owned.second.mapId == pack.mapId
                    && owned.second.instanceId == pack.instanceId)
                {
                    other = true;
                    break;
                }
        }
        if (!other)
            map->CustomData.Erase("DCRiftAffixMap");
    }
    return gone;
}
// `.dc elite champion|rare|affix`. One pack per GM: whatever the caller had is
// cleared first, so the affix under test is never confounded by an older pack.
// `affix` empty means the pack rolls nothing at all, which is the whole point -
// `.dc rift affix` rewrites one creature and leaves its pack-mates carrying
// what they rolled.
Creature* SpawnHarness(Player* player, bool rare, std::vector<Affix> const& affixes,
                       Position const* where)
{
    if (!player)
        return nullptr;
    Map* map = player->GetMap();
    if (!map)
        return nullptr;
    ClearHarness(player);

    Position at = where ? *where : player->GetNearPosition(HARNESS_SPREAD, 0.0f);
    if (!where)
    {
        float z = at.GetPositionZ();
        player->UpdateGroundPositionZ(at.m_positionX, at.m_positionY, z);
        at.m_positionZ = z;
        // Facing the caller, so a melee affix reaches them the moment it pulls.
        at.SetOrientation(player->GetOrientation() + float(M_PI));
    }

    // The pack's tier is the caller's saved tier (03 D5), which is what the affix rules
    // read. Outside the Sanctum the summoner's phase is that tier and is what the
    // open-world scaling reads (dc_difficulty CreatureContext); in the Sanctum every
    // tier shares one phase, so scaling there reads that phase, not the tier.
    unsigned const tier = DC::Difficulty::CurrentTier(player);
    Creature* leader = SpawnElitePack(map, HARNESS_ENTRY, at, rare, tier,
                                      player->GetLevel(), false, affixes,
                                      map->GetInstanceId(), player);
    if (!leader)
        return nullptr;
    auto* state = leader->CustomData.GetDefault<EliteState>("DCRiftElite");

    HarnessPack pack;
    pack.leader = leader->GetGUID();
    pack.members = state->pack;
    pack.mapId = map->GetId();
    pack.instanceId = map->GetInstanceId();
    pack.rare = rare;
    pack.spot = at;
    {
        std::lock_guard<std::mutex> lock(harnessMutex);
        harnessPacks[player->GetGUID().GetRawValue()] = pack;
        harnessCount.store(static_cast<unsigned>(harnessPacks.size()),
                           std::memory_order_relaxed);
    }
    return leader;
}
// One affix or guardian hit on everyone standing in it. The shell supplies the
// animation and the school; 02 §5 supplies the number.
void BlastPlayers(Unit* source, Map* map, float x, float y, float z, float radius,
                  std::uint32_t shell, double damage)
{
    if (!source || !map || damage <= 0)
        return;
    map->DoForAllPlayers([&](Player* player)
    {
        if (!player || !player->IsAlive() || !player->IsWithinDist3d(x, y, z, radius))
            return;
        if (!source->IsValidAttackTarget(player))
            return;
        DC::Combat::DealMonsterHit(source, player, shell, damage);
    });
}
// Molten's death explosion arms before its one-shot damage.
void QueueBurst(Unit* source, Rift const& rift, float x, float y, float z, float radius,
                std::uint32_t shell, double damage, std::uint32_t delayMs)
{
    Burst burst;
    if (EliteState* state = source->CustomData.Get<EliteState>("DCRiftElite"))
    {
        burst.tier = state->tier;
        burst.grLevel = state->grLevel;
        for (Affix const& affix : state->affixes)
            if (affix.shell == shell)
                burst.affixName = affix.name;
    }
    burst.instanceId = rift.instanceId;
    burst.mapId = rift.mapId;
    burst.caster = source->GetGUID();
    burst.shell = shell;
    burst.x = x; burst.y = y; burst.z = z;
    burst.radius = radius;
    burst.damage = damage;
    burst.at = getMSTime() + delayMs;
    std::lock_guard<std::mutex> lock(workMutex);
    bursts.push_back(burst);
}
// The lasting version of QueueBurst: ticks every tickMs from armMs until
// armMs + lifeMs, on whoever is standing in it at the time.
void QueueZone(Unit* source, Rift const& rift, float x, float y, float z, float radius,
               std::uint32_t shell, double damage, std::uint32_t armMs,
               std::uint32_t lifeMs, std::uint32_t tickMs, float slow = 0.0f,
               std::uint32_t slowSpell = 0)
{
    if (!source)
        return;
    Zone zone;
    zone.instanceId = rift.instanceId;
    zone.mapId = rift.mapId;
    zone.caster = source->GetGUID();
    zone.shell = shell;
    zone.x = x; zone.y = y; zone.z = z;
    zone.radius = radius;
    zone.damage = damage;
    zone.tickMs = tickMs;
    zone.nextTick = getMSTime() + armMs;
    zone.endsAt = getMSTime() + armMs + lifeMs;
    zone.slow = slow;
    zone.slowSpell = slowSpell;
    std::lock_guard<std::mutex> lock(workMutex);
    zones.push_back(zone);
}
// Hold a player with a stock control aura (stock WoW
// records for now, D3's own icons later). The hold is the aura: it carries the tuned length on its own duration, so
// there is no timer to run out, the debuff tray shows it, the core's immunity refuses it (Unit::AddAura checks
// IsImmunedToSpell, so a player under Ignore Pain or Nerves of Steel, whose records carry the control immunity,
// is not held) and Juggernaut sees it as a control and shortens it. Returns whether it landed on the player. The donors, and why:
//   FEAR_HOLD 29168 "Fear": one instant MOD_FEAR effect, spell mechanic FEAR, no aura interrupt flags (damage does not break it),
//   FREEZE_HOLD 15878 "Ice Blast": one instant MOD_STUN effect, mechanic STUN, a frost icon, no aura interrupt flags,
//   JAILER_DEBUFF 53077 "Ensnaring Trap": one instant MOD_ROOT effect, the Jailer's root since 13 §10.
// A re-application from the same caster replaces its own hold so it runs the new length from now.
bool ApplyHold(Unit* source, Player* player, std::uint32_t donor, std::uint32_t ms)
{
    if (!source || !player || !donor || !ms)
        return false;
    player->RemoveAurasDueToSpell(donor, source->GetGUID());
    Aura* hold = source->AddAura(donor, player);
    if (!hold)
        return false;
    // AddAura also hands back an aura the player refused when it was applied: a hold refused by id (Ice Climbers' freeze,
    // IMMUNITY_ID) passes AddAura's effect check and is turned away by the target map's. Not held,
    // so no interrupt; and the unapplied aura goes, or the core would apply it on a later target-map update.
    if (!hold->GetApplicationOfTarget(player->GetGUID()))
    {
        player->RemoveOwnedAura(hold);
        return false;
    }
    hold->SetMaxDuration(static_cast<std::int32_t>(ms));
    hold->SetDuration(static_cast<std::int32_t>(ms));
    return true;
}
// An affix slow is the stock SPELL_AURA_MOD_DECREASE_SPEED
// now, not a direct SetSpeed, and it owns its own lifetime.
//
// SetSpeed writes the run rate itself, so it overwrote whatever the stat
// sheet's Movement Speed aura had put there, and the release then had to put
// something back - which it did by writing 1.0f, the rate of a player with no
// bonus at all. Two speed effects cannot both own one rate. As auras they do
// not have to: Unit::UpdateSpeed takes the largest positive
// MOD_INCREASE_SPEED and the largest negative MOD_DECREASE_SPEED and combines
// them, so the slow lands on top of the bonus and lifting it gives the bonus
// back without anyone having to remember what it was.
//
// The caster IS the slow's identity, and that is what makes several of them
// behave. The core keys an aura by the unit that cast it
// (Unit::_TryStackingOrRefreshingExistingAura, Unit.cpp:4656, which looks the
// existing aura up by casterGUID), so two elites slowing the same player hold
// two separate auras, each with its own clock, and Unit::UpdateSpeed applies
// the strongest one STILL RUNNING. When that one expires the weaker one is
// still there and the player speeds up to it; when the last expires the slow is
// gone and the movement aura alone is left. Nothing here has to arrange any of
// that, and nothing here may get in its way: this function touches only the
// aura its own caster owns.
//
// It is worth saying what this replaced, because the second version was wrong
// in a way the first was not obviously wrong in. One shared aura cannot hold
// two lifetimes, so the module merged them - strongest amount, longest time -
// and that is not what independent auras do: a -60% with one second left and a
// new -20% for five seconds became -60% for five, where the core gives -60% for
// one and then -20% for four. There is no merge any more, and no module-invented
// stacking rule of any kind; the core's own identity and lifetimes are the rule.
//
// Re-applying from the SAME caster refreshes that caster's slow to the new
// amount and the new duration, which is what a caster re-applying its own aura
// does. The removal first is to refresh rather than add a stack.
//
// The rate the affix sheet carries is a multiplier (0.4 is "40% of normal"),
// and an aura amount is a percentage change, so it is (rate - 1) x 100 - whole
// percent, at most half a percent of movement speed out. A rate of 1 or more
// is not a slow and casts nothing.
void ApplySlow(Unit* caster, Player* player, std::uint32_t spell, double rate, std::uint32_t ms)
{
    if (!caster || !player || !spell || !ms)
        return;
    std::int32_t const amount = Stats::SlowAuraAmount(rate);
    if (!amount)
        return;
    ObjectGuid const from = caster->GetGUID();
    player->RemoveAurasDueToSpell(spell, from);
    int32 value = int32(amount);
    caster->CastCustomSpell(player, spell, &value, nullptr, nullptr, true);
    // The record carries no duration of its own, deliberately: the affix's
    // tuned milliseconds are the only clock this aura ever runs on.
    if (Aura* applied = player->GetAura(spell, from))
    {
        applied->SetMaxDuration(static_cast<std::int32_t>(ms));
        applied->SetDuration(static_cast<std::int32_t>(ms));
    }
}

// A charmed elite is on the players' side, so its affixes act on its former allies (AffixFoesOf), and
// those are monsters: ApplyHold, ApplySlow and DC::Combat::DealMonsterHit take a player. These are their twins for a
// monster, the same aura and the same base damage without the layers only a player has (a D3 sheet's mitigation).
bool HoldFoe(Unit* source, Unit* foe, std::uint32_t donor, std::uint32_t ms)
{
    if (!source || !foe || !donor || !ms)
        return false;
    foe->RemoveAurasDueToSpell(donor, source->GetGUID());
    Aura* hold = source->AddAura(donor, foe);
    if (hold)
    {
        hold->SetMaxDuration(static_cast<std::int32_t>(ms));
        hold->SetDuration(static_cast<std::int32_t>(ms));
    }
    return hold != nullptr;
}
void SlowFoe(Unit* caster, Unit* foe, std::uint32_t spell, double rate, std::uint32_t ms)
{
    if (!caster || !foe || !spell || !ms)
        return;
    std::int32_t const amount = Stats::SlowAuraAmount(rate);
    if (!amount)
        return;
    ObjectGuid const from = caster->GetGUID();
    foe->RemoveAurasDueToSpell(spell, from);
    int32 value = int32(amount);
    caster->CastCustomSpell(foe, spell, &value, nullptr, nullptr, true);
    if (Aura* applied = foe->GetAura(spell, from))
    {
        applied->SetMaxDuration(static_cast<std::int32_t>(ms));
        applied->SetDuration(static_cast<std::int32_t>(ms));
    }
}
void HitFoe(Unit* source, Unit* foe, std::uint32_t shell, double damage)
{
    SpellInfo const* info = sSpellMgr->GetSpellInfo(shell);
    if (!source || !foe || !foe->IsAlive() || !info || damage <= 0)
        return;
    double const scaled = damage * EliteDamageMultiplier(source);
    uint32 const dealt = static_cast<uint32>(std::min<double>(scaled, std::numeric_limits<uint32>::max()));
    if (!dealt)
        return;
    // The same path as DealMonsterHit's tail: the core's absorbs, the combat log, the spell damage.
    DamageInfo absorbing(source, foe, dealt, info, SPELL_SCHOOL_MASK_NORMAL, SPELL_DIRECT_DAMAGE);
    Unit::CalcAbsorbResist(absorbing);
    SpellNonMeleeDamage log(source, foe, info, info->SchoolMask);
    log.damage = absorbing.GetDamage();
    log.absorb = absorbing.GetAbsorb();
    log.cleanDamage = log.damage;
    log.physicalLog = info->SchoolMask == SPELL_SCHOOL_MASK_NORMAL;
    source->SendSpellNonMeleeDamageLog(&log);
    source->DealSpellDamage(&log, true);
}
// A charmed elite's single-target pick, in place of Family::PickPlayer: a random former ally within `reach`.
Unit* PickFoe(Creature* elite, float reach)
{
    std::vector<Unit*> near;
    for (Unit* foe : AffixFoesOf(elite))
        if (elite->GetExactDist(foe) <= reach && elite->InSamePhase(foe))
            near.push_back(foe);
    return near.empty() ? nullptr : near[std::min(near.size() - 1, static_cast<std::size_t>(Roll() * near.size()))];
}
// The unit a tracking or following hazard is homing on: a player, or, for a charmed elite's, a former ally.
Unit* HazardTarget(Map* map, ObjectGuid guid)
{
    return guid.IsPlayer() ? static_cast<Unit*>(ObjectAccessor::FindPlayer(guid)) : map->GetCreature(guid);
}

// A controlled player who changes map is unreachable by the map that queued the
// hold, so let everything of theirs go the moment they arrive on the new map.
// Without this a jail root or a fear ridden through a town portal survives
// forever.
void ReleasePlayerControls(Player* player)
{
    if (!player)
        return;
    // A hold or a slow is a plain aura with a duration, so it rides a map change: nothing on the old map is left to
    // end it. This is the one place that takes them off a player outright.
    for (std::uint32_t hold : {FEAR_HOLD, FREEZE_HOLD, JAILER_DEBUFF})
        player->RemoveAurasDueToSpell(hold);
    for (auto const& row : Combat::Shells::AffixSlows)
        player->RemoveAurasDueToSpell(row.id);
}
bool HasAffix(EliteState const& state, std::string const& behaviour)
{
    for (Affix const& affix : state.affixes)
        if (affix.behaviour == behaviour)
            return true;
    return false;
}
std::uint32_t AffixShell(EliteState const& state, std::string const& behaviour)
{
    for (Affix const& affix : state.affixes)
        if (affix.behaviour == behaviour)
            return affix.shell;
    return 0;
}
// The leader of the pack this creature belongs to, or null if it is not a
// member of one. Every member carries its leader's guid for Avenger.
Creature* PackLeaderOf(Creature* member)
{
    MinionState const* mine = member ? member->CustomData.Get<MinionState>("DCRiftMinion") : nullptr;
    Map* map = member ? member->GetMap() : nullptr;
    return mine && map ? map->GetCreature(mine->leader) : nullptr;
}
// The state holding this pack's shared windows - Shielding's, and the Health
// Link tether. The leader's, or the creature's own when it is the leader or has
// lost it. A monster with no pack is its own pack.
EliteState* PackStateOf(Creature* creature, EliteState* own)
{
    if (!own->member)
        return own;
    Creature* leader = PackLeaderOf(creature);
    EliteState* leaderState = leader ? leader->CustomData.Get<EliteState>("DCRiftElite") : nullptr;
    return leaderState ? leaderState : own;
}
// Every living member of the pack, the leader first. A charmed one is still in it: its affixes keep working for the
// charmer, so the chain, link, shield and Avenger steps count it.
std::vector<Creature*> PackMembers(Creature* leader, EliteState const& state)
{
    std::vector<Creature*> out;
    if (!leader)
        return out;
    if (leader->IsAlive())
        out.push_back(leader);
    Map* map = leader->GetMap();
    if (!map)
        return out;
    for (ObjectGuid const& guid : state.pack)
        if (Creature* member = map->GetCreature(guid))
            if (member->IsAlive())
                out.push_back(member);
    return out;
}
// The beams for one affix: every pair of living pack members gets one dummy
// aura, ordered by raw guid so each pair is applied exactly once. `minimum` is
// the activation count - Fire Chains joins nothing below activation_members,
// Health Link below two. Aura::TryRefreshStackOrCreate keys on (spell, caster),
// so the three pairs of a champion pack are three auras, not one refreshed.
void ApplyPackBeams(Creature* leader, EliteState const& state, std::uint32_t spell,
                    unsigned minimum)
{
    if (!leader || !spell)
        return;
    std::vector<Creature*> members = PackMembers(leader, state);
    if (members.size() < minimum)
        return;
    for (std::size_t i = 0; i < members.size(); ++i)
        for (std::size_t j = i + 1; j < members.size(); ++j)
        {
            Creature* a = members[i];
            Creature* b = members[j];
            if (a->GetGUID().GetRawValue() > b->GetGUID().GetRawValue())
                std::swap(a, b);
            if (!b->HasAura(spell, a->GetGUID()))
                a->AddAura(spell, b);
        }
}
// A dead champion's outgoing beam auras outlive it - the aura sits on the other
// member and the core does not strip a caster's auras when the caster dies - so
// they are removed here. The aura on the dead champion itself dies with it.
void TearDownBeams(Creature* dead)
{
    if (!dead)
        return;
    Map* map = dead->GetMap();
    if (!map)
        return;
    Creature* leader = nullptr;
    if (MinionState* member = dead->CustomData.Get<MinionState>("DCRiftMinion"))
        leader = map->GetCreature(member->leader);
    else if (EliteState* own = dead->CustomData.Get<EliteState>("DCRiftElite"))
        if (!own->member)
            leader = dead;          // the leader is itself a member of the pack
    if (!leader)
        return;
    EliteState* pack = leader->CustomData.Get<EliteState>("DCRiftElite");
    if (!pack)
        return;
    for (std::uint32_t spell : {FIRE_CHAINS_BEAM, HEALTH_LINK_BEAM})
        for (Creature* member : PackMembers(leader, *pack))
            member->RemoveAura(spell, dead->GetGUID());
}
// C9: speed and haste are stock auras carrying the composed percent. Unit::UpdateSpeed takes the largest positive
// MOD_INCREASE_SPEED and the strongest MOD_DECREASE_SPEED and multiplies the two, so Fast and Avenger (ratios above one)
// share one increase aura and Juggernaut (below one) rides a decrease aura of its own (DC::Rifts::SpeedAuraFor); a negative
// amount on the increase aura would count as nothing. MOD_MELEE_HASTE stacks and takes either sign, so haste has the one.
// The donors are bare single-effect auras with no stance, no visual and a self target (Tamed Pet Passive 04 and 10, "DND";
// Saurfang Slow Down, infinite, with no mechanic, so Juggernaut's snare immunity cannot refuse it); the amount is ours.
constexpr std::uint32_t PACE_SPEED_DONOR = 19582, PACE_SLOW_DONOR = 61458, PACE_HASTE_DONOR = 34675;
void ComposePace(Unit* unit, std::uint32_t donor, double ratio)
{
    if (!unit || ratio == 1.0)
        return;
    Aura* aura = unit->GetAura(donor, unit->GetGUID());
    bool const fresh = !aura;
    if (fresh)
        aura = unit->AddAura(donor, unit);
    if (AuraEffect* effect = aura ? aura->GetEffect(EFFECT_0) : nullptr)
        effect->ChangeAmount(ComposePercent(fresh ? 0 : effect->GetAmount(), ratio)); // a fresh aura starts from no bonus
}
void AddPace(Unit* unit, double speedRatio, double hasteRatio)
{
    ComposePace(unit, SpeedAuraFor(speedRatio) == SpeedAura::Decrease ? PACE_SLOW_DONOR : PACE_SPEED_DONOR, speedRatio);
    ComposePace(unit, PACE_HASTE_DONOR, hasteRatio);
}
double EliteLifeFactor(Creature const* creature)
{
    LifeFactor const* held = creature ? creature->CustomData.Get<LifeFactor>("DCEliteLife") : nullptr;
    return held ? held->factor : 1.0;
}
// Juggernaut's and an Illusionist copy's Life is the creature's Life times a factor, so it goes through the scaling
// owner, which multiplies the real Life.
void ScaleLife(Creature* creature, double factor)
{
    creature->CustomData.GetDefault<LifeFactor>("DCEliteLife")->factor = factor;
    if (sABScriptMgr->RefreshCreatureScaling(creature))
    {
        creature->SetHealth(creature->GetMaxHealth());
        return;
    }
    // Not module-scaled (a `.dc elite` pack in the open world): there is no owner to hold the factor, so it is written
    // the way it always was.
    double const scaled = static_cast<double>(creature->GetMaxHealth()) * factor;
    std::uint64_t const life = scaled >= 18446744073709551616.0 ? std::numeric_limits<std::uint64_t>::max()
                               : scaled > 1.0                  ? static_cast<std::uint64_t>(scaled)
                                                               : 1;
    creature->SetMaxHealth(life);
    creature->SetHealth(creature->GetMaxHealth());
}
// The always-on affixes, applied once when the pack is promoted. Everything
// here is a published number; nothing is on a timer.
void ApplyPassiveAffixes(Creature* elite, EliteState const& state)
{
    std::shared_ptr<AffixNumbers const> const numbers = Numbers();
    if (!elite || !numbers)
        return;
    FastPassive(elite, state, *numbers);
    JuggernautPassive(elite, state, *numbers);
}
}
