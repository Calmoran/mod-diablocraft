/*
 * World of DiabloCraft - the Shaman's class code. The combat engine and the shared mechanics ask the class through
 * these entry points, each answered in the file of the mechanic it belongs to. Everything shared reads the class from
 * dc_class_map and the sheets; the Shaman's name stays in this folder.
 */

#ifndef DC_SHAMAN_H
#define DC_SHAMAN_H

#include "../../combat/dc_damage_buckets.h"
#include <optional>

#include <cstdint>
#include <optional>
#include <vector>

class Player;
struct Position;
class Unit;

namespace DC::Combat::Shaman
{
    // An attack of `spellId` connected on `enemies` enemies (Combat::Connected, once per attack): a Primary or Thunderstorm pays
    // the Maelstrom its sheet row generates.
    void Connected(Player* player, std::uint32_t spellId, unsigned enemies);

    // A cast of `spellId` began (Combat's OnCast, before the cost is taken): a Secondary spends the Overcharge, and a
    // Secondary or Primal skill moves the Attunement.
    void Casting(Player* player, std::uint32_t spellId);

    // A hit of `spellId` landed on `target` (`critical` when it was a critical hit): a skill's riders on the enemy it hit.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);

    // The hit of `spellId` on `target` being computed (Combat::ComputeHit): the Shaman's multipliers of their own.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);

    // The weapon damage percent the cast's own hit of a Primary's or Secondary's record deals, for the loader that gives every shell its hit
    // (dc_combat.cpp). nullopt for a spell these skills do not claim: the loader's own rule applies.
    std::optional<double> PrimaryBasePct(std::uint32_t spellId);

    // A ground spell of `spellId` was cast at `center` (Combat::ResolveCast, after its hits): the Earthquake starts.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);

    // The element a hit of `spellId` deals when it is not the record's school (Combat::ComputeHit), nullptr for none.
    char const* Element(Player* player, std::uint32_t spellId);

    // A blow of `damage` on a Shaman (the damage hook, with the other classes' saves): a skill that prevents a death sets the damage to 0.
    void Fatal(Player* player, std::uint32_t& damage);

    // The factor on the damage `victim` takes from the Shaman's own skills' effects (1 for anyone else).
    double TakenFactor(Unit* victim);

    // `points` of Maelstrom the Shaman generates, from `spellId`: the bar takes what fits and the rest is banked as
    // Overcharge. Every generation of the class goes through here, the skills' own and a rune's. Nothing for another
    // class.
    void Gain(Player* player, std::uint32_t spellId, double points);

    // The Overcharge stacks the Shaman holds now.
    unsigned OverchargeStacks(Player* player);

    // ---- The Defensive skills (Thunderstorm, Elemental Shield, Ghost Wolf, Purge): the entry points the engine asks them through.

    // The weapon-damage percentage the cast's own hit of a Shaman skill that states a duration_seconds and an upfront hit deals, for the loader
    // that gives every shell its hit (dc_combat.cpp; it would otherwise load as none, DamageWaits). nullopt for a spell these skills do not
    // claim: the loader's own rule applies.
    std::optional<double> BasePct(std::uint32_t spellId);

    // A cast of `spellId` is aimed at `targets`, before any of them is hit (Combat::ResolveCast): what a skill takes off an enemy
    // before its hit lands.
    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // A cast of `spellId` was paid and launched, whichever way it reaches its hits (Combat's AfterCast; `triggered` for a free cast).
    void Launched(Player* player, std::uint32_t spellId, bool triggered);

    // Whether the hits being resolved on this thread are a free cast Lightning Overload made; and the same set to `on`, giving what it was.
    bool FreeCast();
    bool FreeCast(bool on);

    // The hits resolved in its scope are a free cast's (or not): a projectile's impact lands them long after the cast that made them returned.
    class FreeHits
    {
    public:
        explicit FreeHits(bool on) : before(FreeCast(on)) {}
        ~FreeHits() { FreeCast(before); }
        FreeHits(FreeHits const&) = delete;
        FreeHits& operator=(FreeHits const&) = delete;

    private:
        bool before;
    };

    // A cast of `spellId` resolved its hits on `targets` (Combat::ResolveCast, after them and before Connected).
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);

    // The percent of its swings a blinded enemy `attacker` misses now (the hit table, Combat's hook).
    double MissChance(Unit const* attacker);

    // The damage a hit by `attacker` does to `victim` once the Shaman's Elemental Shield has taken its part (Combat::Mitigate).
    double Reduce(Unit* victim, Unit* attacker, double damage);

    // `target` took `damage` of school `school` from the Shaman's hit of `spellId` (Combat::DealHit, every hit and tick): a Spirit Link shares it.
    void Dealt(Player* player, Unit* target, std::uint32_t spellId, unsigned school, bool critical, double damage);

    // A hit by `attacker` landed on `victim` for `damage` (the core's damage event, after every roll): an Elemental Shield pays its charge.
    void Damaged(Unit* attacker, Unit* victim, std::uint32_t damage);

    // A hit of `spellId` landed on `target` (Combat's ResolveHit, not a tick): a Primary may add a charge to a Lightning Shield.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);

    void RegisterScripts();
} // namespace DC::Combat::Shaman

#endif // DC_SHAMAN_H
