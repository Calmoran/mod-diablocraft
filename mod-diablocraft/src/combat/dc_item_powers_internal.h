// What the dc_item_powers*.cpp files share: their includes, the item powers' state and the helpers that more than one of them calls
// (declarations only; the rules are in dc_item_power_math.h, the definitions in the file of each power kind).
#ifndef DC_ITEM_POWERS_INTERNAL_H
#define DC_ITEM_POWERS_INTERNAL_H

#include "dc_item_powers.h"
#include "../classes/barbarian/dc_barbarian.h"
#include "dc_combat.h"
#include "dc_cost_math.h"
#include "dc_passives.h"
#include "../classes/barbarian/dc_barbarian_primaries.h"
#include "dc_item_block_math.h"
#include "dc_item_proc.h"
#include "dc_item_trail.h"
#include "dc_item_summons.h"
#include "dc_proc_math.h"
#include "dc_pylons.h"
#include "dc_spell_numbers.h"
#include "dc_spell_shells.h"
#include "../classes/dc_classes.h"
#include "../classes/dc_resources.h"
#include "../classes/wizard/dc_wizard.h"
#include "../common/dc_tunables.h"
#include "../items/dc_inventory.h"
#include "../items/dc_items.h"
#include "../items/dc_quality_rule.h"
#include "../items/dc_roll_class.h"
#include "../rifts/dc_rifts.h"
#include "../stats/dc_stats.h"

#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Timer.h"
#include "WorldSession.h"

#include <algorithm>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <unordered_map>

namespace DC::Combat::Detail
{
    // Read once, on first use. A missing table is an empty one: no item has a power built, no set piece counts.
    struct Table
    {
        std::vector<ItemPower::Row> rows;
        std::unordered_map<std::uint32_t, ItemPower::Piece> pieces; // base item entry -> its set and name
        std::unordered_map<std::uint32_t, std::string> owners;      // base item entry -> its power id (a legacy twin's is its pool id), for the items with an item-owned power row, a stat-only power too
        std::set<std::uint32_t> sweep;                              // the entries with an item-owned row of a kind that rolls: the login sweep reads these
        std::map<std::string, std::string> ids;                     // legacy d3_id -> pool d3_id (ItemPower::PowerIds): the key of a power is one id
        std::unordered_map<std::string, std::pair<std::string, std::string>> poolClass; // a pool d3_id -> its usable_by and designated_class: the class fit of `choose`
        std::vector<unsigned> cubeSlots;                            // the Cube's slot numbers: dc_cube_slot_item, from data/d3/cube_slots.csv
        std::set<std::string> events;                               // the events some row fires on: the others cost nothing
        std::set<std::string> watched;                              // the skills a `skills_active` row names: only these are looked at
        bool resource = false;                                      // some row reads the primary resource (`resource_above`)
        bool life = false;                                          // some row reads the player's own Life (`life_missing`)
        bool controls = false;                                      // some row fires on a `control_*` event: only then is an aura put on a monster looked at
        bool prevents = false;                                      // some row prevents an element's damage taken (`damage_prevented_pct`): only then is a hit taken looked at
        bool marks = false;                                         // some row fires on the first hit on an enemy (`first_hit_on_target`): only then are the enemies a hit strikes marked
        bool enemyStacks = false;                                   // some row counts the enemies a cast hit for the next (`damage_per_enemy_hit_pct`): only then are casts and hits counted
        bool quietCost = false;                                     // some row cuts the resource costs by a condition (`resource_cost_reduction_pct`): only then is the cut kept on the sheet
        bool missingRegen = false;                                  // some row raises the Life Regen by the Life missing (`life_regen_by_missing_pct`): only then is the Life watched
        bool still = false;                                         // some row holds `standing_still`: only then is the player's movement watched
        bool impaired = false;                                      // some `player` row is a bonus against impaired enemies (`damage_vs_impaired_pct`): only then is a target's control state read
        bool blockReduction = false;                                // some `player` row cuts damage by a share of the Block Chance (`damage_reduction_of_block_pct`): only then is it worked out
        bool speed = false;                                         // some `player` row gives movement speed (`movement_speed_pct`): only then is it looked at
        bool stunned = false;                                       // some row reduces the damage taken per stunned enemy (`damage_reduction_per_stunned_pct`): only then are the enemies around a wearer counted
        bool vitalityThorns = false;                                // some row gives Thorns by the sheet's Vitality (`thorns_per_vitality_pct`): only then is the Vitality watched
        bool moves = false;                                         // some row holds `moving` or `not_moving`: only then is the player's movement read when a number is
    };

    Table const& Data();

    extern std::mutex mutex;

    extern std::unordered_map<std::uint64_t, std::map<std::string, unsigned>> counts; // player guid -> set -> worn pieces

    // What the conditions read, per player (guid): the channel spans, the last damage taken and the worn items with the
    // moment each was put on.
    struct Clock
    {
        std::map<std::string, ItemPower::Span> channels;
        std::map<std::string, ItemPower::EnemyStack> enemyStacks;   // skill -> the enemies its last cast hit and the ones its cast in progress spends (Saffron Wrap)
        bool hurt = false;
        std::uint32_t lastHurt = 0;
        double quietCost = 0;                       // the percent the `resource_cost_reduction_pct` rows take off the costs now (a Temporary contribution of QuietCostId)
        double missingRegen = 0;                    // the percent the `life_regen_by_missing_pct` rows add to the Life Regen now (a Temporary Percent contribution of MissingRegenId)
        std::uint32_t missingRegenAt = 0;           // the server clock of the last look at the wearer's Life (MissingLifeRegen)
        std::map<std::string, std::uint32_t> wornSince;
        std::map<std::string, std::uint32_t> fired; // ItemPower::FireKey -> when the row last fired
        std::map<std::string, double> spentCarry;   // ItemPower::FireKey -> the points spent toward the next step of a `resource_spent` row
        bool stillTracked = false;                  // the stood-still timer has started (StandStill)
        std::uint32_t stillSince = 0;               // the server clock the player last stopped moving
        bool speedLooked = false;                   // the movement speed has been looked at (MovementSpeed)
        std::uint32_t speedAt = 0;                  // the server clock it was last looked at
        double movementSpeed = 0;                   // the movement speed the `movement_speed_pct` rows put on the sheet now (a Temporary contribution of SpeedId)
        double lifeRegen = 0;                       // the Life Regen the `life_regen` rows put on the sheet now (a Temporary contribution of RegenId)
        std::uint32_t stunScanAt = 0;               // the server clock of the last look at the stunned enemies around the wearer (StunScan)
        unsigned stunnedNear = 0;                   // the stunned enemies within the item's radius at that look
        double vitalityThorns = 0;                  // the Thorns the `thorns_per_vitality_pct` rows put on the sheet now (a Temporary contribution of VitalityThornsId)
        ItemPower::ElementState elements;           // Tal Rasha's Elements: the element buffs, the last Meteor, the 6-piece window
        ItemBlock::Spent nextSpent;                 // Blood Brother: the attack the armed bonus was spent on (the cast still carries it)
    };

    extern std::unordered_map<std::uint64_t, Clock> clocks;

    extern std::unordered_map<std::uint64_t, std::map<std::uint64_t, std::vector<ItemPower::Value>>> worn; // player guid -> item guid -> its powers

    extern std::unordered_map<std::uint64_t, std::map<std::uint64_t, bool>> legendaries; // player guid -> worn Legendary or Set item guid -> Ancient or Primal

    // Lut Socks: the window a skill's casts are being re-used in, with the cast that opened it (a rune of the skill).
    struct Window
    {
        ItemPower::Reuse state;
        std::uint32_t spellId = 0;
    };

    extern std::unordered_map<std::uint64_t, std::map<std::string, Window>> windows; // player guid -> skill -> its open window

    extern std::unordered_map<std::uint64_t, std::set<std::string>> immune;               // player guid -> the immunities put on the unit

    extern std::unordered_map<std::uint64_t, std::map<unsigned, ItemPower::Cubed>> cubes; // player guid -> Cube slot (one of Data().cubeSlots) -> the power chosen in it

    // Arreat's Law: the players whose resource maximum carries the item's extra points now, as a Temporary contribution of this
    // id (an item's affix ids are its guid << 16 | seq, a Cube slot's 256..65535, the weapon's 1 and 2: none can reach 1 << 62).
    extern std::set<std::uint64_t> raised;

    constexpr std::uint64_t OverCapId = 1ULL << 62;

    // Kekegi's Unbreakable Spirit: when each player's window of free abilities ends (server clock), and the id of its
    // Temporary Resource Cost Reduction (beside OverCapId, out of every affix id's reach).
    extern std::unordered_map<std::uint64_t, std::uint32_t> costFree;

    constexpr std::uint64_t CostFreeId = OverCapId + 1;

    constexpr std::uint64_t QuietCostId = OverCapId + 4;     // the `resource_cost_reduction_pct` rows' Temporary Resource Cost Reduction (Pride's Fall)
    constexpr std::uint64_t MissingRegenId = OverCapId + 5;  // the `life_regen_by_missing_pct` rows' Temporary Percent Life Regen (Rogar's Huge Stone)

    constexpr std::uint64_t RegenId = OverCapId + 2;   // the `life_regen` rows' Temporary contribution (Boots of Disregard)
    constexpr std::uint64_t SpeedId = OverCapId + 3;   // the `movement_speed_pct` rows' Temporary contribution (Irontoe Mudsputters)

    constexpr std::uint64_t VitalityThornsId = OverCapId + 4;   // the `thorns_per_vitality_pct` rows' Temporary contribution (Heart of Iron)

    std::vector<ItemPower::Cubed> CubedOf(std::uint64_t guid);

    ItemPower::Situation Seen(Player const* player);

    ItemPower::Situation SituationOf(std::uint64_t guid, ItemPower::Situation situation = {});

    std::map<std::string, unsigned> const& CountsOf(std::uint64_t guid);

    void StackBuff(Player* player, ItemPower::Row const& row, double add);

    void MarkEnemy(Player* player, Unit* target, ItemPower::Row const& row, double pct);

    void ArmNextAttack(Player* player, std::string const& owner, double pct);

    double ArmedPct(Player const* player);

    void NextAttackConnected(Player* player, std::uint32_t spellId);

    void NextAttackPressed(Player* player);

    // ---- Tal Rasha's Elements ----
    // The set's buffs are Temporary contributions on the sheet, one id per element (an item's affix ids are its guid << 16 | seq, so these cannot meet them).
    constexpr std::uint64_t ElementResistId = 1ULL << 61, ElementImmuneId = 1ULL << 60;

    char const* ElementOfSchool(unsigned school);

    void ElementBuff(Player* player, std::string const& element, std::map<std::string, std::uint32_t> ItemPower::ElementState::* ends, Stat stat,
                     Bucket bucket, std::uint64_t base, double value, std::uint32_t ms);

    void ElementWindowHit(Player* player, std::string const& element, ItemPower::Row const& row);

    void ElementMeteor(Player* player, Unit* target, std::string const& element);

    void EnemyStackPress(Player* player, std::string const& skill);

    void EnemyStackConnect(Player* player, std::uint32_t spellId, unsigned enemies);

    void OpenCostFree(Player* player, double seconds);

    bool& Saved();

    void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target = nullptr, unsigned enemies = 0,
              double yards = 0, double lifeBefore = 100.0, double lifeAfter = 100.0);

    void Immunize(Player* player, std::string const& control, bool on);

    void Immunize(Player* player);

    void CostAuras(Player* player);

    void DropStacks(Player* player);

    double CooldownCut(Player* player);

    bool ReuseCast(Player* player, std::uint32_t spellId, std::string const& skill);


    void NoDamageCost(Player* player);

    void MissingLifeRegen(Player* player);
    void ReuseLogout(Player* player);

    void MovementSpeed(Player* player);

    void StandStill(Player* player);

    void StunScan(Player* player);

    void VitalityThorns(Player* player);
    // The scripts of the buff and event files, made by RegisterScripts in the order they always were.
    void RegisterBuffScripts();
    void RegisterEventScripts();
} // namespace DC::Combat::Detail

// Each side names the other's declarations unqualified, as the one anonymous namespace did.
namespace DC::Combat::ItemPowers
{
    using namespace DC::Combat::Detail;
}

namespace DC::Combat::Detail
{
    using namespace DC::Combat::ItemPowers;
}

#endif
