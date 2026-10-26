/*
 * World of DiabloCraft - the minions a class raises, the shared piece: counted and capped by group, timed or kept at a
 * number by a keeper, following their owner and striking what it strikes, commanded at a target, gone when the owner
 * leaves, dies or changes floor. A class defines its kinds (Minions::Define) and calls Raise or Keep; nothing here
 * names a class. The rules are dc_minions_math.h. The creatures are the class's summons sheet
 * (data/d3/<class>_summons.csv) and run the ScriptName "dc_minion".
 *
 * A minion belongs to its owner (owner and creator set, the owner's faction and level, no loot): the rift counts it as
 * no monster, the tier scaling leaves it alone, and killing one gives no credit. Its blows are the owner's own, dealt
 * as the spell record of the kind (Combat::Strike), so damage, crits and item powers scale with the owner as a hit of
 * the owner's skill does.
 */

#ifndef DC_MINIONS_H
#define DC_MINIONS_H

#include "Position.h"

#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <string_view>

class Creature;
class Player;
class Unit;

#include <vector>

namespace DC::Combat::Minions
{
    // One kind of minion, as a class defines it. The class fills it from its sheets when the minion is raised.
    struct Kind
    {
        std::string group;            // minions of one group are counted and capped together
        std::uint32_t entry = 0;      // the creature template
        std::uint32_t record = 0;     // the spell record a blow is dealt as
        double damagePct = 0;         // weapon damage of one swing (0: it deals none)
        unsigned hitsPerSwing = 1;    // a swing is this many blows, each an equal share of damagePct
        double commandBonusPct = 0;   // the damage bonus against the target it was commanded at
        double commandSpeedPct = 0;   // the attack speed bonus while it attacks the target it was commanded at
        double swingMs = 0;           // the time between its swings when its power fixes one (0: the owner's attack speed sets it)
        // Called for each blow and each pulse with the enemy it falls on: the percent more damage it deals to that enemy (0: none).
        std::function<double(Player*, Unit*)> bonusAgainst;
        bool firstSwingAtOnce = false; // its first swing is not made to wait out the time between swings
        std::uint32_t lifeMs = 0;     // 0: it stays until dismissed or killed
        unsigned hitsToDie = 0;       // 0: it dies of its own Life
        unsigned cap = 0;             // the most of the group alive at once (0: none); the oldest goes to make room
        bool staysPut = false;        // it stands where it was raised and neither follows its owner nor strikes (a decoy, Spirit Walk's body)
        double lifeToCopyPct = 0; // a copy of the owner with this percent of its Life (0: no copy)
        double rangeYards = 0;    // it strikes from this far off (0: from melee range)
        double auraRadius = 0;    // it strikes every enemy within this many yards of it each second ...
        double auraPct = 0;       // ... for this weapon damage per pulse (0 or no radius: no aura)
        std::uint32_t auraRecord = 0; // the spell record a pulse is dealt as (0: record)
        std::uint32_t auraEveryMs = 0; // the time between two pulses (0: one second)
        // Called where the minion is when it dies or its time is up (not when its owner goes away).
        std::function<void(Player*, Position const&)> ended;
        // Called where the minion is when its time is up (not when it dies and not when its owner goes away).
        std::function<void(Player*, Position const&)> timedOut;
        // Called after each blow the minion deals, with the enemy struck.
        std::function<void(Player*, Unit*)> struck;
        // Called after each blow of the swing, with the minion that dealt it and the enemy struck.
        std::function<void(Player*, Creature*, Unit*)> struckBy;
        // Called when an enemy hits the minion, with that enemy.
        std::function<void(Player*, Unit*)> hurt;
        // Called with the minion every `watchEveryMs` (0: never) while it stands, whether it fights or not.
        std::uint32_t watchEveryMs = 0;
        std::function<void(Player*, Creature*)> watch;
    };

    // Defines the kind `key` (once, at startup). `make` is asked each time one is raised, for the owner, so the numbers
    // are read when they are needed and not when the module starts.
    void Define(std::string key, std::function<Kind(Player*)> make);

    // Raises a minion of the kind `key` for `owner` at `at`. `display` is a look to put on it (0: the template's);
    // `copyOwner` draws the owner's own look and gear on it. nullptr when the kind is unknown, the owner cannot have
    // it, or the creature did not come.
    Creature* Raise(Player* owner, std::string const& key, Position const& at, std::uint32_t display = 0,
                    bool copyOwner = false);

    // The keeper: holds `wanted` minions of the kind `key` for `owner`, raising one every `intervalMs`, and none for
    // `returnMs` after one is lost. Called every look (about once a second) while the owner should have them; true when
    // it raised one.
    bool Keep(Player* owner, std::string const& key, unsigned wanted, std::uint32_t intervalMs, std::uint32_t returnMs);

    // The minions of `group` standing for `owner`.
    unsigned Alive(Player* owner, std::string_view group);
    // The creatures of those minions.
    std::vector<Creature*> Standing(Player* owner, std::string_view group);
    // Sends the group away (`Dismiss`) or everything the owner has (`DismissAll`); a keeper raises its own again, after
    // `holdMs` when it is given (a minion that collapses, to come back later).
    void Dismiss(Player* owner, std::string_view group, std::uint32_t holdMs = 0);
    // Sends the oldest minion of `group` away for good (its keeper is not held) and answers where it stood; nothing when none stands.
    std::optional<Position> DismissOldest(Player* owner, std::string_view group);
    // `DismissAll` answers how many it sent away.
    unsigned DismissAll(Player* owner);
    // How many minions of every group stand for `owner`.
    unsigned Count(Player* owner);

    // Orders the minions of `group` at `target` for `ms`: they strike it with the kind's command bonus.
    void Command(Player* owner, std::string_view group, Unit* target, std::uint32_t ms);
    // The group's blows deal `pct` percent more for `ms` (a second call replaces the first).
    // Boosts of different `source`s stand together and add; a second call of the same source replaces its first.
    void Boost(Player* owner, std::string_view group, double pct, std::uint32_t ms, std::string_view source = {});
    // The percent the group's blows deal more now (0 with no boost standing).
    double BoostPercent(Player* owner, std::string_view group);
    // The group swings `attackPct` percent faster and runs `movePct` percent faster for `ms` (a second call replaces the first).
    void Haste(Player* owner, std::string_view group, double attackPct, double movePct, std::uint32_t ms,
               std::string_view source = {});
    // Whether the order of `group` stands and is at `target`.
    bool IsOrdered(Player* owner, std::string_view group, Unit const* target);

    // Called with the owner and the enemy struck after every blow any of the owner's minions deals (the swing and the aura's pulse).
    // Register at startup (RegisterScripts of the class that reads the blows); the list is not locked.
    using StruckListener = std::function<void(Player* owner, Unit* target)>;
    void OnStruck(StruckListener listener);

    // The owner's script hooks (logout, floor change) and the AI of "dc_minion", and the GM command. At startup.
    void RegisterScripts();
} // namespace DC::Combat::Minions

#endif // DC_MINIONS_H
