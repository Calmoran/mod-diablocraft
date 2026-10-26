#pragma once
// The Demon Hunter passives' rules that need no core type, header-only so tests/demon_hunter_passives compiles this
// exact code: which skills a Hatred spender is, which casts Tactical Advantage answers, what Night Stalker adds, when
// no enemy is near for Steady Aim, and the bonus Cull the Weak gives. The production half is
// dc_demon_hunter_passives.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::DemonHunter::Passive
{
    // "Hatred spenders": a skill that is no Primary and costs Hatred. The record carries the cost (`hatredCost`: the
    // Energy power and a cost above 0) or the module pays it (`moduleStart`: Rapid Fire's start and shots, whose record
    // has none).
    inline bool SpendsHatred(bool primary, bool hatredCost, bool moduleStart)
    {
        return !primary && (hatredCost || moduleStart);
    }

    // "Whenever you use Vault, Shadow Power, Smoke Screen, or backflip with Evasive Fire": the skills whose cast is the
    // trigger (the backflip is Evasive Fire's own call).
    inline bool TacticalAdvantageSkill(std::string_view skill)
    {
        return skill == "Vault" || skill == "Shadow Power" || skill == "Smoke Screen";
    }

    // "Your primary skills generate an additional {generated_resource} Hatred": the Hatred a skill's cast pays, before
    // the item powers' share of it. A skill that generates nothing, or is no Primary, gets nothing added.
    inline double GeneratedWith(bool primary, double generated, double bonus)
    {
        return primary && generated > 0 ? generated + std::max(0.0, bonus) : generated;
    }

    // "As long as there are no enemies within {radius_yards} yards": `distances` are the enemies' yards from the Demon
    // Hunter.
    inline bool Clear(std::vector<double> const& distances, double radius)
    {
        return std::none_of(distances.begin(), distances.end(), [radius](double yards) { return yards <= radius; });
    }

    // The game time (ms) a bonus given at `nowMs` lasts until.
    inline std::uint64_t Until(std::uint64_t nowMs, double seconds)
    {
        return nowMs + std::uint64_t(seconds > 0 ? seconds * 1000.0 + 0.5 : 0.0);
    }

    // "Increase damage against Slowed or Chilled enemies by {damage_bonus_pct}": the percent a hit takes.
    inline double CullPct(bool slowedOrChilled, double pct)
    {
        return slowedOrChilled && pct > 0 ? pct : 0.0;
    }

    // Brooding: "Gain {life_regen_pct} Life regeneration per second for every second you remain stationary, stacking up to
    // {max_stacks_count} times. This bonus is reset {duration_seconds} seconds after you move." A second standing still is a stack; a
    // move holds the stacks, and only moving on for the whole reset time (without stopping) takes them away.
    struct Still
    {
        unsigned stacks = 0;
        double stillMs = 0;  // standing still since the last whole second
        double movingMs = 0; // moving since the last time the Demon Hunter stood still
    };
    inline Still BroodingStep(Still state, bool moving, double diffMs, unsigned most, double resetSeconds)
    {
        if (moving)
        {
            state.stillMs = 0;
            state.movingMs += diffMs;
            if (state.movingMs >= resetSeconds * 1000.0)
                state.stacks = 0;
            return state;
        }
        state.movingMs = 0;
        state.stillMs += diffMs;
        while (state.stillMs >= 1000.0)
        {
            state.stillMs -= 1000.0;
            state.stacks = std::min(state.stacks + 1, most);
        }
        return state;
    }

    // Archery: the bonus follows the weapon kinds in the two hands. A bow is subclass 2; a crossbow is subclass 18, a hand crossbow
    // when one-handed.
    enum class Weapon
    {
        None,
        Bow,
        Crossbow,
        HandCrossbow
    };
    inline Weapon WeaponOf(std::uint32_t subclass, bool oneHanded)
    {
        if (subclass == 2)
            return Weapon::Bow;
        if (subclass == 18)
            return oneHanded ? Weapon::HandCrossbow : Weapon::Crossbow;
        return Weapon::None;
    }
    struct Archery
    {
        bool bow = false;       // damage
        bool crossbow = false;  // critical hit damage
        bool hand = false;      // critical hit chance (the first hand crossbow)
        bool second = false;    // Hatred a second (a second hand crossbow)
    };
    inline Archery ArcheryOf(Weapon main, Weapon off)
    {
        Archery bonus;
        bonus.bow = main == Weapon::Bow || off == Weapon::Bow;
        bonus.crossbow = main == Weapon::Crossbow || off == Weapon::Crossbow;
        unsigned const hands = unsigned(main == Weapon::HandCrossbow) + unsigned(off == Weapon::HandCrossbow);
        bonus.hand = hands >= 1;
        bonus.second = hands >= 2;
        return bonus;
    }

    // Numbing Traps: "Enemies you Slow, Chill, or hit with Fan of Knives, Spike Trap, Caltrops, Grenades, and Sentry fire": the skills
    // whose hit does it (the slow and the chill are the class's own slow).
    inline bool NumbingTrapsSkill(std::string_view skill)
    {
        return skill == "Fan of Knives" || skill == "Spike Trap" || skill == "Caltrops" || skill == "Grenade" || skill == "Sentry";
    }

    // Custom Engineering: "Increase the duration of your Caltrops, Marked for Death, Spike Trap, and Sentry by {duration_bonus_pct}", and
    // "the maximum number and charges of Sentries to {max_count:sentry} and number of Spike Traps to {max_count:spike_trap}".
    inline bool CustomEngineeringSkill(std::string_view skill)
    {
        return skill == "Caltrops" || skill == "Marked for Death" || skill == "Spike Trap" || skill == "Sentry";
    }
    inline double DurationFactorOf(bool on, std::string_view skill, double bonusPct)
    {
        return on && CustomEngineeringSkill(skill) ? 1.0 + std::max(0.0, bonusPct) / 100.0 : 1.0;
    }
    inline unsigned MostStandingOf(bool on, unsigned base, double total)
    {
        return on ? std::max(base, unsigned(std::max(0.0, total))) : base;
    }

    // The record Grenadier's giant grenade strikes with (its identity in the helper map; generate_spells.py makes it Fire).
    inline constexpr char const* GrenadierBlast = "Grenadier - giant grenade";

    // Grenadier: "grenades" are the Grenade skill, Rapid Fire's Bombardment, Vengeance's Personal Mortar, Strafe's Demolition and Rain of
    // Vengeance's Anathema: every hit of those is a grenade (the power files name Grenadier in each).
    inline bool GrenadeSkill(std::string_view skill, std::string_view rune)
    {
        return skill == "Grenade" || (skill == "Rapid Fire" && rune == "Bombardment") || (skill == "Vengeance" && rune == "Personal Mortar") ||
               (skill == "Strafe" && rune == "Demolition") || (skill == "Rain of Vengeance" && rune == "Anathema");
    }
    // Where only some of a skill's hits are grenades, as Cluster Arrow's (its impact and rockets are not), the explosion of its grenades grows
    // all the same; its grenades ask `GrenadierFactor` themselves, which no record-wide answer can do. The Spike Trap's blast grows too (its
    // power file multiplies a radius by the passive's radius share), and its damage does not: the file holds no damage term.
    inline bool GrenadeRadiusSkill(std::string_view skill, std::string_view rune)
    {
        return GrenadeSkill(skill, rune) || skill == "Cluster Arrow" || skill == "Spike Trap";
    }
    // "Increase the damage of grenades by {damage_bonus_pct}": the factor on a grenade's damage.
    inline double GrenadierFactorOf(bool on, double bonusPct)
    {
        return on ? 1.0 + std::max(0.0, bonusPct) / 100.0 : 1.0;
    }
    // "Increase the explosion size of grenades": the radius grows by the power file's share (`radiusPct`).
    inline double RadiusFactor(bool on, bool grenade, double radiusPct)
    {
        return on && grenade ? 1.0 + std::max(0.0, radiusPct) / 100.0 : 1.0;
    }
    // The enemies (their positions in `distances`) in the ring a grown explosion adds: beyond the engine's own radius `base`, within the grown one.
    inline std::vector<std::size_t> Ring(std::vector<double> const& distances, double base, double grown)
    {
        std::vector<std::size_t> ring;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] > base && distances[i] <= grown)
                ring.push_back(i);
        return ring;
    }

    // Sharpshooter: "Gain {crit_chance_pct} Critical Hit Chance every second. This bonus is reset {duration_seconds} second after you
    // successfully critically hit." A stack each tick; a critical hit sets the reset `delay` ahead, and the stacks are gone once it passes.
    struct Sharp
    {
        unsigned stacks = 0;
        std::uint64_t resetAtMs = 0; // 0: no reset waiting
    };
    inline Sharp SharpTick(Sharp state, std::uint64_t nowMs)
    {
        if (state.resetAtMs && nowMs >= state.resetAtMs)
            state = Sharp{};
        ++state.stacks;
        return state;
    }
    inline Sharp SharpCrit(Sharp state, std::uint64_t nowMs, double delaySeconds)
    {
        state.resetAtMs = nowMs + std::uint64_t(delaySeconds > 0 ? delaySeconds * 1000.0 + 0.5 : 0.0);
        return state;
    }
    // What the sheet holds: the stacks' worth, nothing once the reset has passed.
    inline double SharpWorth(Sharp const& state, std::uint64_t nowMs, double perStack)
    {
        return state.resetAtMs && nowMs >= state.resetAtMs ? 0.0 : state.stacks * perStack;
    }

    // Ballistics: "Increase damage of rockets by {damage_bonus_pct}" and "a {proc_chance_pct} chance to fire a homing rocket ... when you
    // attack" (`roll` is 0 to 1).
    inline double RocketFactorOf(bool on, double bonusPct)
    {
        return on ? 1.0 + std::max(0.0, bonusPct) / 100.0 : 1.0;
    }
    inline bool Procs(double roll, double chancePct)
    {
        return chancePct > 0 && roll * 100.0 < chancePct;
    }

    // Leech: "Gain {heal_per_hit_life} Life per Hit. Heal amount is increased by {life_per_kill_share_pct} of your Life per Kill": the power
    // file's share of D3's Healing table at the level, and the share of the Life per Kill.
    inline double LeechLifePerHit(double healingShare, double healingAtLevel, double killSharePct, double lifePerKill)
    {
        return healingShare * healingAtLevel + killSharePct / 100.0 * lifePerKill;
    }

    // Ambush: "You deal {damage_bonus_pct} additional damage to enemies above {life_threshold_pct} health": `lifePct` is the enemy's Life, 0 to 100.
    inline double AmbushPct(double lifePct, double thresholdPct, double pct)
    {
        return lifePct > thresholdPct && pct > 0 ? pct : 0.0;
    }

    // Awareness: a blow that would kill is saved when the passive is ready. The Life it regenerates, a tick at a time over its seconds.
    inline bool Saves(std::uint32_t health, std::uint32_t damage, bool ready)
    {
        return ready && damage >= health;
    }
    inline double AwarenessPerTick(double maxLife, double healPct, double seconds, double tickSeconds)
    {
        return maxLife > 0 && healPct > 0 && seconds > 0 && tickSeconds > 0 ? maxLife * healPct / 100.0 * std::min(tickSeconds, seconds) / seconds : 0.0;
    }

    // Single Out: "Gain {crit_chance_pct} Critical Hit Chance against enemies who are more than {radius_yards} yards away from any other
    // enemies": `others` are the yards from this enemy to every other enemy.
    inline bool Isolated(std::vector<double> const& others, double yards)
    {
        return std::none_of(others.begin(), others.end(), [yards](double apart) { return apart <= yards; });
    }

    // The production half (dc_demon_hunter_passives.cpp), called from dc_demon_hunter.cpp and the skill files that ask.
    // A hit of `spellId` landed on `target`: Thrill of the Hunt's slow after a Hatred spender.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);
    // A cast of `spellId` resolved: Tactical Advantage's speed after Vault, Shadow Power or Smoke Screen.
    void Cast(Player* player, std::uint32_t spellId);
    // Evasive Fire's backflip happened: Tactical Advantage's speed.
    void Backflipped(Player* player);
    // The Hatred a Primary's cast pays: Night Stalker's addition to the sheet's generation.
    double Generated(Player* player, std::uint32_t spellId, double generated);
    // An enemy was slowed or chilled by the Demon Hunter's skills (the class's own slow): Numbing Traps' weakening of it.
    void Slowed(Player* player, Unit* enemy);
    // The seconds a Caltrops, Marked for Death, Spike Trap or Sentry lasts, for `skill`: Custom Engineering's longer duration.
    double DurationFactor(Player* player, std::string_view skill);
    // How many Sentries or Spike Traps (`kind` "sentry" or "spike_trap") stand at once, given the skill's own `base`: Custom Engineering's
    // larger number.
    unsigned MostStanding(Player* player, char const* kind, unsigned base);
    // An attack connected (Combat::Connected): Ballistics' chance of a homing rocket.
    void Attack(Player* player, std::uint32_t spellId);
    // The radius (yards) of a grenade's explosion for `spellId`, given the skill's own: Grenadier's larger explosion.
    double GrenadeRadius(Player* player, std::uint32_t spellId, double radius);
    // A grenade of `spellId` went off at `center`: the ring Grenadier's larger explosion adds, hit as the explosion was.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // The factor on a rocket's damage: Ballistics' increase.
    double RocketFactor(Player* player);
    // The factor on the damage of a grenade a skill throws among hits that are not grenades (Cluster Arrow's): Grenadier's increase.
    double GrenadierFactor(Player* player);
    // Critical hit chance Single Out adds against `target` for `player`.
    double CritBonus(Player* player, Unit* target);
    // A blow of `damage` would take `player` from `health`: Awareness saves it. `damage` is zero when it did.
    void Fatal(Player* player, std::uint32_t& damage);
    // A health globe healed the Demon Hunter (the globes' pickup call, not built yet): Blood Vengeance's Hatred and
    // Discipline.
    void GlobePicked(Player* player);
    // A hit is being computed: Steady Aim's and Cull the Weak's factors.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::Passive
