/*
 * World of DiabloCraft - the item power table and the set counter, the pure half
 * (the table, the (skill, stat) modifiers, the conditions and the player's
 * numbers, the events and procs, the K4 patterns, the element rows,
 * immunities and the skills_active / resource_above conditions). dc_item_powers.cpp loads the rows of
 * dc_legendary_power and the worn pieces; the rules live here so a test compiles and drives them with the generated rows. Contract:
 * docs/contracts/legendary-powers.md.
 */

#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iterator>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace DC::Combat::ItemPower
{
    // One row of dc_legendary_power. `owner` is an item's d3_id (pieces 0) or a set's name (pieces 2, 3, 4 or 6). A `skill`
    // row names the skill it modifies, a `player` row modifies the player; a set bonus's number is `min` (its `max` is the
    // same). `cond` (blank: always) is a condition from Holds below with `arg` seconds over the skills in `condSkills`.
    struct Row
    {
        std::string owner;
        unsigned pieces = 0;
        std::string kind, skill, stat;
        double min = 0, max = 0;
        std::string cond;
        double arg = 0;
        std::vector<std::string> condSkills;
        double stackSeconds = 0;   // `quiet_stacks`, `standing_still`: one stack per this many seconds, at most stackMax
        unsigned stackMax = 0;
        // The event that fires the row (Fire below): `cast`, `hit`, `hit_spender`, `hit_generator`, `kill`, `kill_elite`, `taken`, `image_death`, `block`.
        // Blank: the row is simply on. A `triggered` condition holds for `arg` seconds after the row last fired; a row of kind
        // `effect` does something once each time it fires (its stat says what, its number is the amount).
        std::string fireOn;
        std::vector<std::string> fireSkills; // `cast`, `hit`: the skills whose cast or hit fires it
        double chancePct = 100;              // per event, scaled by the hit's proc coefficient on a hit event; 100 or more: always
        double icdSeconds = 0;               // the internal cooldown: no fire for this long after the last one
    };

    // How long a skill has been, or was, channelled, in milliseconds on the server's clock: `start` when it began, `end` when it
    // stopped (unread while `running`).
    struct Span
    {
        std::uint32_t start = 0, end = 0;
        bool running = false;
    };

    // One number a worn item gives: the (skill, stat) of the row and its value (the stored roll of a ranged row, the table's number of
    // a fixed one).
    struct Value
    {
        std::string skill, stat;
        double value;
        std::string owner; // the item's d3_id, so a condition can be read per item
        bool fixed = false; // the table's number of a fixed row, which a ranged row of the same skill and stat must not read as its own roll
    };

    // What a condition reads: the clock now, the player's channel spans by skill name, when the player last took damage,
    // when each worn item (by d3_id) was put on, the skills that are active now and the primary resource's percent of its maximum.
    struct Situation
    {
        std::uint32_t now = 0;
        std::map<std::string, Span> channels;
        bool hurt = false;
        std::uint32_t lastHurt = 0;
        std::map<std::string, std::uint32_t> wornSince;
        std::map<std::string, std::vector<Value>> itemValues; // worn item (d3_id) -> its WornValues: the stored roll of a ranged row
        std::map<std::string, std::uint32_t> fired;           // FireKey of a row -> the server clock when it last fired
        std::set<std::string> active;                         // `skills_active`: the skills whose buff is on or whose summons live
        double resourcePct = 0;                               // `resource_above`: the primary resource, percent of its maximum
        bool stillTracked = false;                            // `standing_still`: the player's stood-still timer has started (StillSince)
        std::uint32_t stillSince = 0;                         // `standing_still`: the server clock when the player last stopped moving
        unsigned enemiesHit = 0;                              // `enemies_hit_at_most`: the enemies the firing cast hit, 0 when not counted
        double eventYards = 0;                                // `event_distance_yards`: the yards to the enemy the event is about, 0 when it has none
        bool elementWindow = false;                           // `element_window`: Tal Rasha's Elements 6-piece window is open now
        double lifeBeforePct = 100, lifeAfterPct = 100;       // `life_below`: the player's Life, percent of the maximum, before and after the hit being dealt 
        double castCooldownSeconds = 0;                       // the cooldown of a `cast_skill` row whose number is 0: Won Khim Lau's, monk.won_khim_lau_cooldown_seconds
        unsigned hitPlace = 0;                                // `first_hits`: the hit's place among the enemies its cast hits, nearest first (1 the first), 0 when not counted
        unsigned castEnemies = 0;                             // `cast_enemies_at_most`: the enemies the hit's cast hits in all, 0 when not counted
        double targetLifePct = -1;                            // `target_life_at_least`: the target's Life, percent of its maximum; -1 when the reader has no target
        bool firstHit = false;                                // `first_hit_on_target` (N-MARK): the enemy the event is about has not been hit by this player before (ItemPower::FirstHit)
        unsigned targetControl = 0;                           // N-TCTRL: the states of the hit's target (TargetSlowed), 0 when the reader has no target
        unsigned stunnedNear = 0;                             // N-TCTRL: the stunned enemies within the wearer's `stunned_radius_yards` at the last look (StunScan)
        bool moving = false;                                  // `moving`, `not_moving` (N-MOVE): the player is moving now (Unit::isMoving), read when the number is read
        std::string targetType;                               // N-CTF: the creature type name (CreatureTypeName) of the enemy the event is about, "" when it has none
        double lifePct = 100;                                 // `life_missing` (N-PLIFE): the player's own Life, percent of its maximum, read when the number is read
    };

    // N-TCTRL (Fjord Cutter): the bits of Situation::targetControl, a state of the hit's target that a `target_` condition reads.
    constexpr unsigned TargetSlowed = 1; // `target_slowed`: a slow is on it (a Chill is one: Slowed or Chilled)
    constexpr unsigned TargetControlled = 2; // N-TCTRL (Krysbin's Sentence): a control-impairing effect other than a slow is on it

    // N-CTF: WoW's creature types by number (the core's CreatureType: CREATURE_TYPE_BEAST 1 ... CREATURE_TYPE_GAS_CLOUD 13), named as a row's `cond_skills`
    // spells them. dc_item_powers.cpp asserts each number against the core's enum. A number outside the list has no name ("").
    inline constexpr char const* CreatureTypes[] = {"",         "beast",    "dragonkin",       "demon",     "elemental",
                                                    "giant",    "undead",   "humanoid",        "critter",   "mechanical",
                                                    "not_specified", "totem", "non_combat_pet", "gas_cloud"};
    inline std::string CreatureTypeName(unsigned type)
    {
        return type < std::size(CreatureTypes) ? CreatureTypes[type] : "";
    }

    // N-CTF: whether the enemy an event is about is of one of the types a `target_creature_type` row names (its `cond_skills`). An event with no
    // enemy (`type` blank) is of none.
    inline bool CreatureTypeIs(Row const& row, std::string const& type)
    {
        return !type.empty() && std::find(row.condSkills.begin(), row.condSkills.end(), type) != row.condSkills.end();
    }

    // What identifies a row for the fire clock: every column of its key, so two rows of one owner fire and expire on their own.
    inline std::string FireKey(Row const& row)
    {
        return row.owner + '|' + std::to_string(row.pieces) + '|' + row.skill + '|' + row.stat + '|' + row.cond + '|' + row.fireOn;
    }

    // The stacks of a `quiet_stacks` row: one per stackSeconds since its item was put on or, after the player took damage, since
    // `arg` seconds after that damage (a hit removes every stack and none build for those seconds), at most stackMax. 0 when the
    // item is not worn. Any other row counts as one "stack" (its number as it is).
    // The stood-still timer (N-MOVE): the server clock the player last stopped moving. Moving restarts it at `now`; the first look starts it too (a
    // player not yet watched has stood still for no time); standing still keeps it.
    inline std::uint32_t StillSince(bool moving, bool tracked, std::uint32_t since, std::uint32_t now)
    {
        return moving || !tracked ? now : since;
    }

    // N-PSPD (Irontoe Mudsputters): whether a sheet number that follows a figure that keeps changing (the Life missing) is due to be looked at
    // again: never looked at yet, or `periodMs` have passed since the last look (an unsigned clock subtracts across a wrap).
    inline bool LookDue(bool looked, std::uint32_t lastMs, std::uint32_t nowMs, std::uint32_t periodMs)
    {
        return !looked || static_cast<std::uint32_t>(nowMs - lastMs) >= periodMs;
    }

    // The stacks of a `standing_still` row: one per stackSeconds the player has stood still while the item was worn (the later of the moment
    // it went on and the moment the player last stopped moving), at most stackMax. 0 when the item is not worn or the timer has not started.
    inline unsigned StillStacks(Row const& row, Situation const& situation)
    {
        auto worn = situation.wornSince.find(row.owner);
        if (worn == situation.wornSince.end() || !situation.stillTracked || row.stackSeconds <= 0)
            return 0;
        std::uint32_t start = situation.stillSince;
        if (static_cast<std::int32_t>(worn->second - start) > 0)
            start = worn->second;
        std::int32_t const elapsed = static_cast<std::int32_t>(situation.now - start);
        if (elapsed <= 0)
            return 0;
        unsigned const built = static_cast<unsigned>(elapsed / (row.stackSeconds * 1000.0));
        return built < row.stackMax ? built : row.stackMax;
    }

    inline unsigned Stacks(Row const& row, Situation const& situation)
    {
        if (row.cond == "standing_still")
            return StillStacks(row, situation);
        if (row.cond != "quiet_stacks")
            return 1;
        auto worn = situation.wornSince.find(row.owner);
        if (worn == situation.wornSince.end() || row.stackSeconds <= 0)
            return 0;
        std::uint32_t start = worn->second;
        if (situation.hurt)
        {
            std::uint32_t const resume = situation.lastHurt + static_cast<std::uint32_t>(row.arg * 1000.0);
            if (static_cast<std::int32_t>(resume - start) > 0)
                start = resume;
        }
        std::int32_t const elapsed = static_cast<std::int32_t>(situation.now - start);
        if (elapsed <= 0)
            return 0;
        unsigned const built = static_cast<unsigned>(elapsed / (row.stackSeconds * 1000.0));
        return built < row.stackMax ? built : row.stackMax;
    }

    // N-PLIFE (Lornelle's Sunstone): the percent of Life the player is missing, 0 to 100 (a player at full Life, or with no maximum, misses none).
    inline double LifeMissing(Situation const& situation)
    {
        return std::clamp(100.0 - situation.lifePct, 0.0, 100.0);
    }

    // The factor a row's number is counted by: `life_missing` counts it once per 1% of Life the player is missing (the row's number is "per 1% Life
    // missing", so the number at 40% missing is 40 x it); a stacking row once per stack; any other row once.
    // `per_prior_hit` (N-NHIT, Vile Ward) counts it once per enemy the charge has hit up to and including this hit: the hit's place, so the
    // first enemy takes one step. The name is the condition's, from when the first enemy took none; 0 for a hit no cast counted.
    inline double PriorHits(Situation const& situation)
    {
        return static_cast<double>(situation.hitPlace);
    }

    inline double Counted(Row const& row, Situation const& situation)
    {
        if (row.cond == "per_prior_hit")
            return PriorHits(situation);
        return row.cond == "life_missing" ? LifeMissing(situation) : static_cast<double>(Stacks(row, situation));
    }

    // The percent a `resource_above` row of `owner` needs: the item's own `resource_threshold_pct` (its stored roll). None: it never holds.
    inline bool Threshold(std::string const& owner, Situation const& situation, double& pct)
    {
        auto item = situation.itemValues.find(owner);
        if (item == situation.itemValues.end())
            return false;
        for (Value const& value : item->second)
            if (value.skill.empty() && value.stat == "resource_threshold_pct")
            {
                pct = value.value;
                return true;
            }
        return false;
    }

    // Shi Mizu's Haori: the Life percent below which the item's `own_life_below` rows hold, the item's own `own_life_threshold_pct` (its stored roll, or its
    // fixed number). None: it never holds.
    inline bool OwnLifeThreshold(std::string const& owner, Situation const& situation, double& pct)
    {
        auto item = situation.itemValues.find(owner);
        if (item == situation.itemValues.end())
            return false;
        for (Value const& value : item->second)
            if (value.skill.empty() && value.stat == "own_life_threshold_pct")
            {
                pct = value.value;
                return true;
            }
        return false;
    }

    // Pride's Fall: whether the player has taken no damage for `seconds`, counted from the later of the moment the item `owner` went on and the last damage taken
    // (a wrapped clock subtracts correctly in unsigned arithmetic). The item not worn: never.
    inline bool QuietFor(std::string const& owner, double seconds, Situation const& situation)
    {
        auto worn = situation.wornSince.find(owner);
        if (worn == situation.wornSince.end() || seconds <= 0)
            return false;
        std::uint32_t start = worn->second;
        if (situation.hurt && static_cast<std::int32_t>(situation.lastHurt - start) > 0)
            start = situation.lastHurt;
        return static_cast<std::int32_t>(situation.now - start) >= static_cast<std::int32_t>(seconds * 1000.0);
    }

    // Dark Mage's Shade. The event `life_below` is Life falling below the item's own level: the hit takes it from the level or
    // above to under it ("when you fall below 35% Life"), so a hit that stays above, one that finds Life already under and one that lands on the level
    // itself are not it. The level is the item's `life_threshold_pct` row (its stored or fixed number); none, never.
    inline bool LifeThreshold(std::string const& owner, Situation const& situation, double& pct)
    {
        auto item = situation.itemValues.find(owner);
        if (item == situation.itemValues.end())
            return false;
        for (Value const& value : item->second)
            if (value.skill.empty() && value.stat == "life_threshold_pct")
            {
                pct = value.value;
                return true;
            }
        return false;
    }
    inline bool LifeFell(double before, double after, double level)
    {
        return before >= level && after < level;
    }

    // N-SCHOOLEV (Krede's Flame). The percent of the player's maximum Life a hit takes: the damage over the maximum, no more than the Life
    // there is (a killing hit loses what was left), 0 for no maximum or no damage.
    inline double LifeLostPct(double health, double maxHealth, double damage)
    {
        if (maxHealth <= 0 || damage <= 0 || health <= 0)
            return 0.0;
        return 100.0 * std::min(damage, health) / maxHealth;
    }

    // Krede's Flame: "Resource % Gain Per 1% HP Lost" is the power file's number (1): for each 1% of the maximum Life lost, `pctPerPct` percent of the
    // maximum primary resource is gained. `lostPct` is LifeLostPct, `maxResource` the points of the class's primary resource at its best.
    inline double ResourceFromLifeLost(double pctPerPct, double lostPct, double maxResource)
    {
        if (pctPerPct <= 0 || lostPct <= 0 || maxResource <= 0)
            return 0.0;
        return maxResource * pctPerPct * lostPct / 100.0;
    }

    // N-FATAL (Ancestors' Grace). The event `fatal` is a hit that would take all the Life the player has left: damage at least the Life now.
    // A player with no Life left (already dead) is not it, and so is no hit that deals nothing.
    inline bool IsFatal(std::uint32_t damage, std::uint32_t health)
    {
        return health > 0 && damage >= health;
    }

    // N-NHIT (Bracers of Destruction): the place of the cast's `index`th target among all its targets by `distances` from the
    // cast's centre, nearest first (D3's wave reaches the near ones first), 1 the nearest; equal distances keep the list's order. 0 past the list.
    inline unsigned NearestPlace(std::vector<double> const& distances, std::size_t index)
    {
        if (index >= distances.size())
            return 0;
        unsigned place = 1;
        for (std::size_t other = 0; other < distances.size(); ++other)
            if (distances[other] < distances[index] || (distances[other] == distances[index] && other < index))
                ++place;
        return place;
    }

    // Whether a row's condition holds. `skills_active`: every one of the skills is active. `resource_above`: the primary resource is at
    // least the item's threshold percent (Berserker Rage's "above" is the same test). `triggered`: the row fired within `arg` seconds. `quiet_stacks`, `standing_still`: at least one stack. `life_missing`: the player is missing some Life. `channel_held`: any of the skills has been channelled for `arg` seconds without a break. `channel_or_after`: any of the skills is channelled now, or ended within `arg` seconds
    // (a wrapped clock subtracts correctly in unsigned arithmetic). `first_hits` (N-NHIT): the hit is one of the first `arg` enemies its cast hits. `cast_enemies_at_most` (N-NHIT): its cast hits at least one and at most `arg` enemies.
    inline bool Holds(Row const& row, Situation const& situation)
    {
        if (row.cond.empty())
            return true;
        if (row.cond == "skills_active")
            return !row.condSkills.empty() && std::all_of(row.condSkills.begin(), row.condSkills.end(),
                                                          [&](std::string const& skill) { return situation.active.count(skill) != 0; });
        if (row.cond == "resource_above")
        {
            double pct = 0;
            return Threshold(row.owner, situation, pct) && situation.resourcePct >= pct;
        }
        // Envious Blade (N-TLIFE): the target's Life is at least `cond_arg` percent of its maximum (100: full health). A reader that looks at no target
        // leaves -1 and the row never holds.
        if (row.cond == "target_life_at_least")
            return situation.targetLifePct >= 0 && situation.targetLifePct >= row.arg;
        if (row.cond == "quiet_stacks" || row.cond == "standing_still")
            return Stacks(row, situation) > 0;
        // N-PLIFE: on while the player is missing any Life, at full Life the row is simply absent (its number is scaled by LifeMissing in Counted).
        if (row.cond == "life_missing")
            return LifeMissing(situation) > 0;
        if (row.cond == "first_hits")
            return situation.hitPlace >= 1 && situation.hitPlace <= row.arg;
        if (row.cond == "cast_enemies_at_most")
            return situation.castEnemies >= 1 && situation.castEnemies <= row.arg;
        // N-NHIT (Vile Ward): on from the cast's first counted hit; a hit no cast counted takes nothing (its number is scaled by PriorHits in Counted).
        if (row.cond == "per_prior_hit")
            return PriorHits(situation) > 0;
        // N-COST (Pride's Fall): no damage taken for `arg` seconds. Shi Mizu's Haori: the player's Life is below the item's own threshold percent.
        if (row.cond == "no_damage_for")
            return QuietFor(row.owner, row.arg, situation);
        if (row.cond == "own_life_below")
        {
            double pct = 0;
            return OwnLifeThreshold(row.owner, situation, pct) && situation.lifePct < pct;
        }
        if (row.cond == "target_slowed")
            return (situation.targetControl & TargetSlowed) != 0;
        // N-MOVE (Hexing Pants of Mr. Yan): on while the player is moving, or while not.
        if (row.cond == "moving")
            return situation.moving;
        if (row.cond == "not_moving")
            return !situation.moving;
        if (row.cond == "element_window")
            return situation.elementWindow;
        if (row.cond == "triggered")
        {
            auto last = situation.fired.find(FireKey(row));
            return last != situation.fired.end() && (situation.now - last->second) <= static_cast<std::uint32_t>(row.arg * 1000.0);
        }
        if (row.cond == "channel_held")
            for (std::string const& skill : row.condSkills)
            {
                auto span = situation.channels.find(skill);
                if (span != situation.channels.end() && span->second.running &&
                    (situation.now - span->second.start) >= static_cast<std::uint32_t>(row.arg * 1000.0))
                    return true;
            }
        if (row.cond == "channel_or_after")
            for (std::string const& skill : row.condSkills)
            {
                auto span = situation.channels.find(skill);
                if (span == situation.channels.end())
                    continue;
                if (span->second.running || (situation.now - span->second.end) <= static_cast<std::uint32_t>(row.arg * 1000.0))
                    return true;
            }
        return false;
    }

    // A worn set piece: its set and its name (two worn copies of one piece are one piece).
    struct Piece
    {
        std::string set, name;
    };

    // The worn pieces of each set.
    inline std::map<std::string, unsigned> CountSets(std::vector<Piece> const& worn)
    {
        std::map<std::string, std::set<std::string>> names;
        for (Piece const& piece : worn)
            if (!piece.set.empty())
                names[piece.set].insert(piece.name);
        std::map<std::string, unsigned> counts;
        for (auto const& [set, pieces] : names)
            counts[set] = static_cast<unsigned>(pieces.size());
        return counts;
    }

    // Whether a set bonus is on: the worn count reaches its level and the table has a power for it (a bonus with no
    // row is not built, and reads inactive however many pieces are worn).
    inline bool BonusActive(std::vector<Row> const& rows, std::string const& set, unsigned pieces, unsigned worn)
    {
        if (worn < pieces || !pieces)
            return false;
        for (Row const& row : rows)
            if (row.owner == set && row.pieces == pieces)
                return true;
        return false;
    }

    // N-SETSTAT: the set rows of kind `stat` (a set level's plain sheet stats, an item affix id such as `resall`) whose
    // level the worn count reaches, each with its place among the table's set `stat` rows, which keys its sheet contribution.
    inline std::vector<std::pair<unsigned, Row>> SetStats(std::vector<Row> const& rows, std::map<std::string, unsigned> const& worn)
    {
        std::vector<std::pair<unsigned, Row>> out;
        unsigned index = 0;
        for (Row const& row : rows)
        {
            if (!row.pieces || row.kind != "stat")
                continue;
            auto found = worn.find(row.owner);
            if (found != worn.end() && found->second >= row.pieces)
                out.push_back({index, row});
            ++index;
        }
        return out;
    }

    // The contribution id of the `index`th set stat row: 3..255, between the weapon source's 1 and 2 (dc_stats.cpp) and the Cube's 256 and up
    // (CubeContributionId); an item's own are 65536 and up. 0 past the range.
    inline std::uint32_t SetStatContributionId(unsigned index)
    {
        return index < 253 ? 3 + index : 0;
    }

    // A set's first bonus: two pieces for every set (d3planner itemSets, each worn set's lowest bonus; test_legendary_gem_legacy.py).
    inline constexpr unsigned SetBonusPieces = 2;

    // Whether any set bonus is worn, built or not (as if every set already works): what turns Legacy of Dreams off.
    inline bool AnySetBonus(std::map<std::string, unsigned> const& counts)
    {
        for (auto const& [set, worn] : counts)
            if (worn >= SetBonusPieces)
                return true;
        return false;
    }

    // The stat rows an item rolls as its own presets (pieces 0).
    inline std::vector<Row> ItemStats(std::vector<Row> const& rows, std::string const& d3Id)
    {
        std::vector<Row> out;
        for (Row const& row : rows)
            if (row.owner == d3Id && !row.pieces && row.kind == "stat")
                out.push_back(row);
        return out;
    }

    // The roll range of `stat` on `d3Id`: the table's when it has a row, otherwise the pool's, as given.
    inline void RollRange(std::vector<Row> const& rows, std::string const& d3Id, std::string const& stat, double& min,
                          double& max)
    {
        for (Row const& row : ItemStats(rows, d3Id))
            if (row.stat == stat)
            {
                min = row.min;
                max = row.max;
                return;
            }
    }

    // A power that rolls once per item: an item-owned row of any kind but `stat` (a stat row is an ordinary
    // preset) that shows a range. A fixed row (min = max) stores nothing; the item's number is the table's.
    inline bool Rolls(Row const& row)
    {
        return !row.pieces && row.kind != "stat" && row.min < row.max;
    }

    // A row's `skill` may name several skills joined by ';' that share the row's number and, for a range, its one roll (Oathkeeper's four
    // primaries). The first name is the roll's key, so a long list never outgrows dc_item_affix.affix_id.
    inline std::string FirstSkill(std::string const& names)
    {
        return names.substr(0, names.find(';'));
    }

    // Whether `skill` is one of the skills a row's `skill` cell names ("" names none and matches "" for a row with no skill).
    inline bool NamesSkill(std::string const& names, std::string const& skill)
    {
        for (std::size_t from = 0; from <= names.size();)
        {
            std::size_t to = names.find(';', from);
            if (to == std::string::npos)
                to = names.size();
            if (names.compare(from, to - from, skill) == 0)
                return true;
            from = to + 1;
        }
        return false;
    }

    // What a rolled power is stored under: dc_item_affix.affix_id of the item's row of kind 'power'.
    inline std::string RollKey(Row const& row)
    {
        return "power:" + FirstSkill(row.skill) + ":" + row.stat;
    }

    struct Rolled
    {
        std::string key;
        double value, min, max;
    };

    // A stored power row of one item (kind 'power'), and one number a worn item gives.
    struct Stored
    {
        std::string key;
        double value;
    };

    // The best end of a row's range, what a Primal Ancient stores: the top, except for a number whose lower is the better (Aquila Cuirass's
    // threshold and the cut of Hexing Pants of Mr. Yan's standing still, d3planner `best: "min"`).
    inline double Best(Row const& row)
    {
        return row.stat == "resource_threshold_pct" || row.stat == "damage_generation_cut_pct" ? row.min : row.max;
    }

    // The powers `d3Id` rolls once that `have` (the item's stored power rows) does not hold yet, each rolled by `roll(min, max)`; a
    // Primal Ancient (atTop) takes the best end of every range (Best). The roller passes no `have`; an item that dropped before its power's row
    // existed passes what it has and gets the rest, once, the first time the server reads it.
    template <class Roll>
    inline std::vector<Rolled> RollPowers(std::vector<Row> const& rows, std::string const& d3Id, bool atTop, Roll roll,
                                          std::vector<Stored> const& have = {})
    {
        std::vector<Rolled> out;
        for (Row const& row : rows)
            if (row.owner == d3Id && Rolls(row) &&
                std::none_of(have.begin(), have.end(), [&](Stored const& s) { return s.key == RollKey(row); }))
                out.push_back({RollKey(row), atTop ? Best(row) : roll(row.min, row.max), row.min, row.max});
        return out;
    }

    // What an item of `d3Id` gives while it is worn: its fixed rows at the table's number, its ranged rows at the stored roll. A ranged
    // row with no stored roll (an item rolled before rolls were stored) gives nothing: no value, no power.
    inline std::vector<Value> WornValues(std::vector<Row> const& rows, std::string const& d3Id, std::vector<Stored> const& stored)
    {
        std::vector<Value> out;
        for (Row const& row : rows)
        {
            if (row.owner != d3Id || row.pieces || row.kind == "stat")
                continue;
            if (!Rolls(row))
            {
                out.push_back({row.skill, row.stat, row.min, d3Id, true});
                continue;
            }
            auto found = std::find_if(stored.begin(), stored.end(), [&](Stored const& s) { return s.key == RollKey(row); });
            if (found != stored.end())
                out.push_back({row.skill, row.stat, found->value, d3Id});
        }
        return out;
    }

    // The numbers of `skill`'s `stat` over a player's worn items (item guid -> WornValues), one per item that has the row.
    inline std::vector<double> WornRolls(std::map<std::uint64_t, std::vector<Value>> const& worn, std::string const& skill,
                                         std::string const& stat)
    {
        std::vector<double> out;
        for (auto const& [guid, values] : worn)
            for (Value const& value : values)
                if (NamesSkill(value.skill, skill) && value.stat == stat)
                    out.push_back(value.value);
        return out;
    }

    // ---- Kanai's Cube: the second source of a power (docs/research/kanais-cube.md 5.2, docs/contracts/legendary-powers.md) ----
    // A power is keyed by its id (the pool item's d3_id), not by an item. It is in play from a worn item or from a Cube choice; the readers
    // above take one Situation either way (AddCubed), so none of them changes.

    enum class Source
    {
        Worn,
        Cube
    };

    // The Cube's slots are the ones `data/d3/cube_slots.csv` names (world table dc_cube_slot_item, the same rows the window and the `choose` verb
    // read): no count lives here. A slot number only has to fit the contribution id below.
    inline constexpr unsigned CubeSlotLimit = 255;

    // Whether `slot` is one of the Cube's slots (the numbers the world table gives).
    inline bool CubeSlotExists(std::vector<unsigned> const& slots, unsigned slot)
    {
        return std::find(slots.begin(), slots.end(), slot) != slots.end();
    }

    // One base item of dc_base_item, for the twin map.
    struct BaseItem
    {
        std::string id, name, rarity;
        bool pool = false; // pool_version 'yes'
    };

    // Legacy id -> pool id: a legacy twin (pool_version 'no') of the same name and rarity as exactly one pool row is that pool row's power
    // (Magefist: Unique_Gloves_014_x1 -> P41_Unique_Gloves_014). The rarity keeps a legendary legacy row off an ethereal pool row of its name; a name
    // two pool rows share maps nothing. A pool row, and a legacy row with no twin, is its own id (absent from the map).
    inline std::map<std::string, std::string> PowerIds(std::vector<BaseItem> const& items)
    {
        auto const named = [](BaseItem const& item) { return std::make_pair(item.name, item.rarity); };
        std::map<std::pair<std::string, std::string>, std::vector<std::string>> pools;
        for (BaseItem const& item : items)
            if (item.pool)
                pools[named(item)].push_back(item.id);
        std::map<std::string, std::string> ids;
        for (BaseItem const& item : items)
        {
            if (item.pool)
                continue;
            auto found = pools.find(named(item));
            if (found != pools.end() && found->second.size() == 1)
                ids[item.id] = found->second.front();
        }
        return ids;
    }

    inline std::string PowerId(std::map<std::string, std::string> const& ids, std::string const& d3Id)
    {
        auto found = ids.find(d3Id);
        return found == ids.end() ? d3Id : found->second;
    }

    // Whether a power is built: the table has an item-owned row for it, of any kind but a Bottomless potion's (its row is only the slot's roll
    // range). A stat-only power (Sun Keeper, The Furnace) is built; a set bonus (pieces above 0) is not an item's power.
    inline bool Built(std::vector<Row> const& rows, std::string const& powerId)
    {
        return std::any_of(rows.begin(), rows.end(), [&](Row const& row) { return row.owner == powerId && !row.pieces && row.kind != "potion"; });
    }

    // The numbers a power gives from one source. Worn: the item's stored rolls (WornValues). Cube: the top of every range (Best), whatever any item
    // stores; a fixed row is the table's number. `stored` is read for the worn source only.
    inline std::vector<Value> PowerValues(std::vector<Row> const& rows, std::string const& powerId, Source source, std::vector<Stored> const& stored)
    {
        if (source == Source::Worn)
            return WornValues(rows, powerId, stored);
        std::vector<Value> out;
        for (Row const& row : rows)
            if (row.owner == powerId && !row.pieces && row.kind != "stat")
                out.push_back({row.skill, row.stat, Best(row), powerId, !Rolls(row)});
        return out;
    }

    // A power in play: its id, where it came from and its numbers.
    struct Active
    {
        std::string id;
        Source source;
        std::vector<Value> values;
    };

    inline bool Has(std::vector<Active> const& list, std::string const& id)
    {
        return std::any_of(list.begin(), list.end(), [&](Active const& power) { return power.id == id; });
    }

    // The powers in play: the worn ones first, in their order, then the cubed ones in theirs, each id once (the first copy wins, so a cubed copy
    // of a worn power adds nothing and takes over when the worn item comes off) and only a built power.
    inline std::vector<Active> ActivePowers(std::vector<Row> const& rows, std::vector<Active> const& worn, std::vector<std::string> const& cubed)
    {
        std::vector<Active> out;
        for (Active const& power : worn)
            if (!Has(out, power.id))
                out.push_back(power);
        for (std::string const& id : cubed)
            if (!Has(out, id) && Built(rows, id))
                out.push_back({id, Source::Cube, PowerValues(rows, id, Source::Cube, {})});
        return out;
    }

    // A power chosen in the Cube and the server clock when it was chosen (a `quiet_stacks` row counts from it).
    struct Cubed
    {
        std::string id;
        std::uint32_t since = 0;
    };

    inline std::uint32_t SinceOf(std::vector<Cubed> const& cubed, std::string const& id)
    {
        for (Cubed const& one : cubed)
            if (one.id == id)
                return one.since;
        return 0;
    }

    // Puts the cubed powers into a situation that already holds the worn ones (wornSince, itemValues): the worn ones stay as they are, a cubed power
    // that is not worn gets its moment and its Cube numbers. Every reader of the situation then answers for both sources.
    inline void AddCubed(Situation& situation, std::vector<Row> const& rows, std::vector<Cubed> const& cubed)
    {
        if (cubed.empty()) // every hit of every player comes through here
            return;
        std::vector<Active> worn;
        for (auto const& held : situation.wornSince)
        {
            auto values = situation.itemValues.find(held.first);
            worn.push_back({held.first, Source::Worn, values == situation.itemValues.end() ? std::vector<Value>{} : values->second});
        }
        std::vector<std::string> ids;
        for (Cubed const& one : cubed)
            ids.push_back(one.id);
        for (Active const& power : ActivePowers(rows, worn, ids))
            if (power.source == Source::Cube)
            {
                situation.wornSince[power.id] = SinceOf(cubed, power.id);
                situation.itemValues[power.id] = power.values;
            }
    }

    // The contribution id of the `seq`th stat contribution of a Cube slot (slot 1 to CubeSlotLimit, seq 0 to 255): slot << 8 | seq, in 256..65535.
    // Item affix contributions are itemGuid << 16 | seq (an item guid is never 0, so 65536 and up) and the weapon source keeps 1 and 2
    // (dc_stats.cpp), so the range 256..65535 is free and no unequip of an item removes a cubed contribution. 0 for a slot or seq that is not one.
    inline std::uint32_t CubeContributionId(unsigned slot, unsigned seq)
    {
        if (slot < 1 || slot > CubeSlotLimit || seq > 255)
            return 0;
        return (slot << 8) | seq;
    }

    // Whether a Source::Items contribution id is one Items::RefreshCubedStats places: a set stat's (SetStatContributionId, 3..255) or a
    // cubed power's (CubeContributionId, 256..65535); the weapon source's 1 and 2 and an item's own (65536 and up) are not. The first refresh
    // after a login takes every saved one of these as placed, so a cubed or set stat the character no longer has is swept.
    inline bool CubedStatId(std::uint64_t id)
    {
        return id >= SetStatContributionId(0) && id <= CubeContributionId(CubeSlotLimit, 255);
    }

    // The item-owned rows (pieces 0, every kind) of the power an item stands for, as that item's own: a legacy twin owns its pool item's rows (the
    // roller and the backfill ask by the item's own d3_id, so `owner` is rewritten to it).
    inline std::vector<Row> Rebased(std::vector<Row> rows, std::string const& owner)
    {
        for (Row& row : rows)
            row.owner = owner;
        return rows;
    }

    inline std::vector<Row> RowsOf(std::vector<Row> const& rows, std::map<std::string, std::string> const& ids, std::string const& d3Id)
    {
        std::string const powerId = PowerId(ids, d3Id);
        std::vector<Row> out;
        for (Row const& row : rows)
            if (row.owner == powerId && !row.pieces)
                out.push_back(row);
        return Rebased(std::move(out), d3Id);
    }

    // The stat rows the item rolls as presets (ItemStats), twin-aware.
    inline std::vector<Row> StatsOf(std::vector<Row> const& rows, std::map<std::string, std::string> const& ids, std::string const& d3Id)
    {
        return Rebased(ItemStats(rows, PowerId(ids, d3Id)), d3Id);
    }

    // The number a row gives while its owner is in play: a set bonus whose worn count reaches its level, or a worn item, at the item's own
    // stored roll when the row has a range (no stored roll, no power). False when the owner is not in play.
    inline bool Owned(Row const& row, std::map<std::string, unsigned> const& counts, Situation const& situation, double& number)
    {
        if (row.pieces)
        {
            auto worn = counts.find(row.owner);
            if (worn == counts.end() || worn->second < row.pieces)
                return false;
        }
        else if (!situation.wornSince.count(row.owner))
            return false;
        number = row.min;
        if (!row.pieces && Rolls(row))
        {
            auto item = situation.itemValues.find(row.owner);
            if (item == situation.itemValues.end())
                return false;
            auto found = std::find_if(item->second.begin(), item->second.end(),
                                      [&](Value const& v) { return !v.fixed && v.skill == row.skill && v.stat == row.stat; });
            if (found == item->second.end())
                return false;
            number = found->value;
        }
        return true;
    }

    // The numbers of `kind` (`skill`, `skill`'s) `stat` that are on: each set bonus whose worn count reaches its level and each worn
    // item's row (pieces 0), whose condition holds now, a stacking row once per stack. `counts` is the player's set -> worn pieces,
    // the situation's `wornSince` the worn items. A `player` row names no skill.
    inline std::vector<double> ActiveValues(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts,
                                            std::string const& kind, std::string const& skill, std::string const& stat,
                                            Situation const& situation)
    {
        std::vector<double> out;
        for (Row const& row : rows)
        {
            double number = 0;
            if (row.kind == kind && NamesSkill(row.skill, skill) && row.stat == stat && Owned(row, counts, situation, number) &&
                Holds(row, situation))
                out.push_back(number * Counted(row, situation));
        }
        return out;
    }

    // The multiplier of a `_pct` stat: every active source is a multiplier of its own, 1 + N/100 (damage-buckets.md; the hit's
    // legendary term), and they multiply.
    inline double SkillFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts,
                              std::string const& skill, std::string const& stat, Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "skill", skill, stat, situation))
            factor *= 1.0 + pct / 100.0;
        return factor;
    }

    // The multiplier of the `damage_by_missing_resource_pct` rows of a skill (Dishonored Legacy): "up to N%" by the
    // primary resource that is missing, each active source a multiplier of its own, 1 + N/100 x missing/100, missing the 100 less the
    // resource's percent of its maximum (`situation.resourcePct`), continuous (the text states no step), 0 to 100.
    inline double MissingResourceFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts,
                                        std::string const& skill, Situation const& situation)
    {
        double const missing = std::clamp(100.0 - situation.resourcePct, 0.0, 100.0);
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "skill", skill, "damage_by_missing_resource_pct", situation))
            factor *= 1.0 + pct / 100.0 * missing / 100.0;
        return factor;
    }

    // N-DERIVED (Standoff): the multiplier of a skill's damage that is a share of one of the player's sheet stats, a
    // `damage_per_<stat>_pct` row: each active source a multiplier of its own, 1 + N/100 x the stat/100 (Standoff's Furious Charge: [400-500]% of the
    // bonus movement speed, so 450 at 25% movement speed is x2.125). A stat at or below 0 adds nothing. 1 with no row.
    inline double DerivedFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                                std::string const& stat, double statValue, Situation const& situation)
    {
        double const value = std::max(0.0, statValue);
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "skill", skill, stat, situation))
            factor *= 1.0 + pct / 100.0 * value / 100.0;
        return factor;
    }

    // The multiplier of a skill's damage that grows with a count a class keeps, a `<stat>` row such as `damage_by_wind_stacks_pct`: each
    // active source a multiplier of its own, 1 + N/100 x the count (a set's 1500% for each stack of a vortex, so 3 stacks is x46). A count at or below 0 adds nothing. 1 with no row.
    inline double PerStackFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                                std::string const& stat, double stacks, Situation const& situation)
    {
        double const count = std::max(0.0, stacks);
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "skill", skill, stat, situation))
            factor *= 1.0 + pct / 100.0 * count;
        return factor;
    }

    // N-THDEAL (Hack): the Thorns damage an attack applies, `pct` percent (clamped to 0 to 100) of the Thorns damage the sheet holds.
    inline double ThornsShare(double thorns, double pct)
    {
        return std::max(0.0, thorns) * std::min(100.0, std::max(0.0, pct)) / 100.0;
    }

    // The Fury a skill takes (Blade of the Warlord): what the player `have`s up to the most the item's `resource_spent_cap` row
    // names, continuous; 0 with no item that is worn and rolled (the damage row must be on too, so no Fury goes for no bonus).
    inline double ResourceSpend(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                                double have, Situation const& situation)
    {
        if (ActiveValues(rows, counts, "skill", skill, "damage_by_resource_spent_pct", situation).empty())
            return 0.0;
        double cap = 0.0;
        for (double value : ActiveValues(rows, counts, "skill", skill, "resource_spent_cap", situation))
            cap = std::max(cap, value);
        return std::max(0.0, std::min(have, cap));
    }

    // The multiplier of the `damage_by_resource_spent_pct` rows of a skill: "up to N%" by the resource it took, each active source a multiplier
    // of its own, 1 + N/100 x taken/cap, taken/cap from 0 (nothing) to 1 (the cap), continuous. 1 when there is no cap or no source.
    inline double ResourceSpentFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                                      double spent, Situation const& situation)
    {
        double cap = 0.0;
        for (double value : ActiveValues(rows, counts, "skill", skill, "resource_spent_cap", situation))
            cap = std::max(cap, value);
        if (cap <= 0.0)
            return 1.0;
        double const fraction = std::clamp(spent / cap, 0.0, 1.0);
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "skill", skill, "damage_by_resource_spent_pct", situation))
            factor *= 1.0 + pct / 100.0 * fraction;
        return factor;
    }

    // N-DUR: the seconds of a skill's duration (Pride of Cassius): the skill's own `base` seconds plus the `duration_add_seconds` of every power that
    // is on, each source adding its own number; a skill with no duration (`base` 0 or less) is left as it is, there is nothing to lengthen.
    inline double DurationSeconds(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill, double base,
                                  Situation const& situation)
    {
        if (base <= 0.0)
            return base;
        for (double add : ActiveValues(rows, counts, "skill", skill, "duration_add_seconds", situation))
            base += add;
        return base;
    }

    // N-HYDRA (Serpent's Sparker): how many of a skill's summons may be up at once, the skill's own `base` plus the
    // `extra_active_count` of every power that is on, each source adding its own whole number.
    inline double ActiveCount(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill, double base,
                              Situation const& situation)
    {
        for (double add : ActiveValues(rows, counts, "skill", skill, "extra_active_count", situation))
            base += add;
        return base;
    }

    // How many of the `up` summons already standing go, the oldest first, when one more comes and `cap` may be up at once: the new one
    // counts, so `cap` - 1 of the old ones stay (none for a cap of 0 or 1).
    inline std::size_t Dismissed(std::size_t up, unsigned cap)
    {
        std::size_t const keep = cap > 1 ? cap - 1 : 0;
        return up > keep ? up - keep : 0;
    }

    // The multiplier of a `player` `_pct` stat, the same way (a damage reduction is a negative number: 1 + -50/100).
    inline double PlayerFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts,
                               std::string const& stat, Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "player", "", stat, situation))
            factor *= 1.0 + pct / 100.0;
        return factor;
    }

    // A `set to` stat: the skill's own number `base`, or the highest active source when that is more (a power that sets a
    // duration never shortens one).
    inline double SkillSetTo(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                             std::string const& stat, double base, Situation const& situation)
    {
        for (double value : ActiveValues(rows, counts, "skill", skill, stat, situation))
            if (value > base)
                base = value;
        return base;
    }

    // A passive's number a worn item raises (kind `passive`, Primordial Soul's Elemental Exposure): the passive's own
    // number `base`, or the highest active source when that is more (a raise never lowers). The caller reads it only for a player who has
    // the passive: the item does not grant it.
    inline double PassiveSetTo(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& passive,
                               std::string const& token, double base, Situation const& situation)
    {
        for (double value : ActiveValues(rows, counts, "passive", passive, token, situation))
            if (value > base)
                base = value;
        return base;
    }

    // A `player` stat that sets a number (Gloves of Worship's shrine seconds): `base`, or the highest active source when that is more (a
    // power that sets a duration never shortens one).
    inline double PlayerSetTo(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& stat,
                              double base, Situation const& situation)
    {
        for (double value : ActiveValues(rows, counts, "player", "", stat, situation))
            if (value > base)
                base = value;
        return base;
    }

    // A `set to` stat that only ever shortens: the skill's own number `base`, or the lowest active source when that is less (the time a
    // bleed's whole damage is dealt in).
    inline double SkillLowest(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                              std::string const& stat, double base, Situation const& situation)
    {
        for (double value : ActiveValues(rows, counts, "skill", skill, stat, situation))
            if (value < base)
                base = value;
        return base;
    }

    // Whether a rune of `skill` is given without choosing it (kind `rune`): an active row names that rune, or `all`. The caller
    // asks of every rune it has an effect for, and treats the rune the bar holds as given as well.
    inline bool GrantsRune(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                           std::string const& rune, Situation const& situation)
    {
        return !ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||
               !ActiveValues(rows, counts, "rune", skill, "all", situation).empty();
    }

    // The multiplier of the `damage_reduction_pct` rows: a reduction is a positive number, one multiplier per source, 1 - N/100 (a
    // range of a reduction rolls to its top for a Primal, so it is not written as a negative `damage_taken_pct`).
    inline double ReductionFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "player", "", "damage_reduction_pct", situation))
            factor *= 1.0 - pct / 100.0;
        return factor;
    }

    // N-TCTRL (Ancient Parthan Defenders): the multiplier of the damage taken for the stunned enemies near the wearer. Each active
    // `damage_reduction_per_stunned_pct` row cuts the damage by N% for every stunned enemy within its radius, a multiplier of its own per enemy,
    // (1 - N/100) to the power of the enemies (`situation.stunnedNear`, counted by StunScan): five enemies at 12% leave x0.53, never nothing.
    // 1 with no row, no stunned enemy or a number that is not below 100.
    inline double StunnedReduction(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "player", "", "damage_reduction_per_stunned_pct", situation))
            if (pct > 0 && pct < 100)
                factor *= std::pow(1.0 - pct / 100.0, static_cast<double>(situation.stunnedNear));
        return factor;
    }

    // Whether a look that was due every `seconds` is due now: `last` is the server clock of the last one (a wrapped clock subtracts correctly in
    // unsigned arithmetic). A cadence that is not above 0 never looks.
    inline bool ScanDue(std::uint32_t last, std::uint32_t now, double seconds)
    {
        return seconds > 0 && static_cast<std::uint32_t>(now - last) >= static_cast<std::uint32_t>(seconds * 1000.0);
    }

    // N-DERIVED (Justice Lantern): the multiplier of the `damage_reduction_of_block_pct` rows, damage reduction equal to N percent of the Block Chance: one multiplier
    // per source, 1 - N x B/10000 for the item's number N and the Block Chance B in percent (D3's dmgred += block x N x 0.01), the reduction held to 0-100 percent.
    // 1.0 when no source is worn or the Block Chance is none.
    inline double BlockReductionFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation,
                                       double blockChancePct)
    {
        double factor = 1.0;
        for (double share : ActiveValues(rows, counts, "player", "", "damage_reduction_of_block_pct", situation))
            factor *= 1.0 - std::clamp(share * std::max(0.0, blockChancePct) / 100.0, 0.0, 100.0) / 100.0;
        return factor;
    }

    // The multiplier of a `player` stat that cuts something by N percent (`blocked_damage_cut_pct`, Blood Brother): one multiplier per
    // source, 1 - N/100; 1.0 when no source is worn.
    inline double CutFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& stat,
                            Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "player", "", stat, situation))
            factor *= 1.0 - pct / 100.0;
        return factor;
    }

    // The multiplier of the `town_portal_bubble_pct` rows (Homing Pads): the damage a Town Portal cast takes, one multiplier per source,
    // 1 - N/100; 1.0 when no source is worn, so a factor below 1 is also "an item that lets the cast go on".
    inline double PortalBubbleFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "player", "", "town_portal_bubble_pct", situation))
            factor *= 1.0 - pct / 100.0;
        return factor;
    }

    // A stun's duration in milliseconds stretched by `factor` (Dovu Energy Trap: ItemPowers::StunFactor, the product of the
    // `stun_duration_pct` rows, each 1 + N/100). A duration that is not positive (-1, permanent) stays as it is.
    inline std::int32_t StunMilliseconds(std::int32_t milliseconds, double factor)
    {
        return milliseconds > 0 && factor > 0 ? static_cast<std::int32_t>(std::lround(milliseconds * factor)) : milliseconds;
    }

    // The sum of a `player` stat over its active sources (the flat seconds a cooldown loses: `cooldown_reduction_seconds`).
    inline double PlayerSum(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& stat,
                            Situation const& situation)
    {
        double sum = 0;
        for (double value : ActiveValues(rows, counts, "player", "", stat, situation))
            sum += value;
        return sum;
    }

    // N-DERIVED (Heart of Iron): the flat Thorns the worn `thorns_per_vitality_pct` rows give, each active source N% of the sheet's Vitality (the sources add: it is a
    // flat Thorns source, which the sheet's Thorns bonuses then multiply). A Vitality at or below 0 gives none.
    inline double ThornsOfVitality(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, double vitality, Situation const& situation)
    {
        return PlayerSum(rows, counts, "thorns_per_vitality_pct", situation) * std::max(0.0, vitality) / 100.0;
    }

    // N-MOVE (Hexing Pants of Mr. Yan): the percent the worn powers add to the additive pool of a hit (damage_formula.csv step 4, the DIBS bucket): the sum of the active
    // `damage_generation_pct` rows less the sum of the active `damage_generation_cut_pct` rows (the cut is a positive number, so it enters as a minus). 0 with none.
    inline double GenerationDamagePct(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        return PlayerSum(rows, counts, "damage_generation_pct", situation) - PlayerSum(rows, counts, "damage_generation_cut_pct", situation);
    }

    // The multiplier of the primary resource a class pays itself from the same two stats: each active `damage_generation_pct` source 1 + N/100, each active
    // `damage_generation_cut_pct` source 1 - N/100 (a cut of 100 or more would take everything, so it takes none: the generator refuses it). 1 with none.
    inline double GenerationFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "player", "", "damage_generation_pct", situation))
            factor *= 1.0 + pct / 100.0;
        for (double pct : ActiveValues(rows, counts, "player", "", "damage_generation_cut_pct", situation))
            if (pct > 0 && pct < 100)
                factor *= 1.0 - pct / 100.0;
        return factor;
    }

    // Rogar's Huge Stone: whether the look at the wearer's Life that is due every `seconds` is due now, `last` being the server clock of the last one (a wrapped clock
    // subtracts correctly in unsigned arithmetic). A cadence that is not above 0 never waits.
    inline bool LifeLookDue(std::uint32_t last, std::uint32_t now, double seconds)
    {
        return seconds <= 0 || static_cast<std::uint32_t>(now - last) >= static_cast<std::uint32_t>(seconds * 1000.0);
    }

    // N-PLIFE (Rogar's Huge Stone): the percent the worn `life_regen_by_missing_pct` rows add to the sheet's Life Regen at `lifePct` percent of Life: each active
    // source N x the percent of Life missing / 100 (N at no Life, nothing at full Life), the sources adding; rounded to 0.1 so a tiny change of Life moves nothing.
    inline double RegenByMissing(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, double lifePct, Situation const& situation)
    {
        double const missing = std::clamp(100.0 - lifePct, 0.0, 100.0);
        return std::round(PlayerSum(rows, counts, "life_regen_by_missing_pct", situation) * missing / 100.0 * 10.0) / 10.0;
    }

    // N-COST (Pride's Fall): the percent off every resource cost the worn `resource_cost_reduction_pct` rows give now, whose condition holds (the sources add).
    inline double CostCutPct(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        return PlayerSum(rows, counts, "resource_cost_reduction_pct", situation);
    }

    // The sum of an `element` stat for a hit of `element` over its active sources (Magefist's Fire damage: the hit's elemental bonus).
    inline double ElementSum(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& element,
                             std::string const& stat, Situation const& situation)
    {
        double sum = 0;
        for (double value : ActiveValues(rows, counts, "element", element, stat, situation))
            sum += value;
        return sum;
    }

    // N-PREVENT (Countess Julia's Cameo): what an element's damage taken becomes when the worn powers prevent `preventedPct` percent of it and heal
    // `healPct` percent of the prevented amount: the damage still taken and the Life healed, both whole numbers rounded down. A share is clamped to
    // 0 to 100.
    struct Prevented
    {
        std::uint32_t taken = 0;
        std::uint32_t healed = 0;
    };

    inline Prevented PreventDamage(std::uint32_t damage, double preventedPct, double healPct)
    {
        double const share = std::min(100.0, std::max(0.0, preventedPct)) / 100.0;
        std::uint32_t const prevented = static_cast<std::uint32_t>(std::floor(damage * share + 1e-9));
        double const heal = std::min(100.0, std::max(0.0, healPct)) / 100.0;
        return {damage - prevented, static_cast<std::uint32_t>(std::floor(prevented * heal + 1e-9))};
    }

    // The same for the worn rows: the `damage_prevented_pct` and `heal_of_prevented_pct` rows of `element` that are on, summed. No prevention
    // row on means the damage is taken whole and nothing heals.
    inline Prevented PreventFor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& element,
                                std::uint32_t damage, Situation const& situation)
    {
        double const prevented = ElementSum(rows, counts, element, "damage_prevented_pct", situation);
        if (prevented <= 0)
            return {damage, 0};
        return PreventDamage(damage, prevented, ElementSum(rows, counts, element, "heal_of_prevented_pct", situation));
    }

    // What the `skill` rows of `stat` that are on add up to for `skill` (`cost_reduction_pct`, N-COST: Fury of the Vanished Peak):
    // the sum of their numbers, as ElementSum is for an element; 0 when none.
    inline double SkillSum(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                           std::string const& stat, Situation const& situation)
    {
        double sum = 0;
        for (double value : ActiveValues(rows, counts, "skill", skill, stat, situation))
            sum += value;
        return sum;
    }

    // The multiplier of the `damage_per_distance_pct` rows for a hit of `element` at `distance` yards (Starfire): each active
    // source is a multiplier of its own, 1 + N x steps / 100, N its number (the item's stored roll), steps the whole `distance_step_yards` in the
    // distance cut at `distance_cap_yards`, both fixed rows of the same owner and element. An owner with no step is skipped.
    inline double DistanceFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& element,
                                 double distance, Situation const& situation)
    {
        double factor = 1.0;
        for (Row const& row : rows)
        {
            double number = 0;
            if (row.kind != "element" || row.skill != element || row.stat != "damage_per_distance_pct" ||
                !Owned(row, counts, situation, number) || !Holds(row, situation))
                continue;
            double step = 0, cap = 0;
            for (Row const& mate : rows)
                if (mate.owner == row.owner && mate.pieces == row.pieces && mate.kind == "element" && mate.skill == row.skill)
                {
                    if (mate.stat == "distance_step_yards")
                        step = mate.min;
                    else if (mate.stat == "distance_cap_yards")
                        cap = mate.min;
                }
            if (step <= 0)
                continue;
            double const steps = std::floor(std::min(distance, cap) / step);
            factor *= 1.0 + number * steps / 100.0;
        }
        return factor;
    }

    // Bastion's Revered: the extra hits a Frenzy swing makes while its buff holds `stacks`: `perStack` (the
    // `extra_hits_per_stack` source, SkillSetTo from 0) a stack, whole.
    inline unsigned ExtraHits(double perStack, unsigned stacks)
    {
        return perStack < 1.0 ? 0u : static_cast<unsigned>(perStack) * stacks;
    }

    // What each of `victims` enemies takes of one extra hit of `total`: the damage is split equally between them.
    inline double ChainShare(double total, unsigned victims)
    {
        return victims ? total / victims : 0.0;
    }

    // The share of `most` points that `yards` earns when the share is full at `full` yards (Arreat's Law): a straight line from 0 at no
    // distance to `most` at `full` and beyond. 0 when `full` is not above 0.
    inline double DistanceShare(double most, double yards, double full)
    {
        return full > 0 ? most * std::min(std::max(yards, 0.0), full) / full : 0.0;
    }

    // The fixed number of `owner`'s row of `kind` and `stat` (the two `player` rows the Fury-by-distance effects read): 0 when it has none.
    inline double OwnerNumber(std::vector<Row> const& rows, std::string const& owner, std::string const& kind, std::string const& stat)
    {
        for (Row const& row : rows)
            if (row.owner == owner && row.kind == kind && row.stat == stat)
                return row.min;
        return 0.0;
    }

    // A mark (`mark_enemy`, Bindings of the Lesser Gods): the factor a hit of the marked skill gets on a marked enemy,
    // 1 + pct/100, the percent times `split` for a split hit (`mark_split_factor`; 1 for any other). No mark (pct 0 or less): 1.
    inline double MarkFactor(double pct, double split)
    {
        return pct > 0 ? 1.0 + pct * std::max(split, 1.0) / 100.0 : 1.0;
    }

    // The controls the player is immune to now: the `stat` of every `immune` row whose owner is in play (Ice Climbers: freeze, root).
    inline std::set<std::string> Immunities(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        std::set<std::string> out;
        for (Row const& row : rows)
            if (row.kind == "immune" && !ActiveValues(rows, counts, "immune", "", row.stat, situation).empty())
                out.insert(row.stat);
        return out;
    }

    // What a hit of a skill is to the hit events: a generator (a Primary, or a skill that generates resource) and a spender (a skill
    // with a resource cost). `cost` and `generated` are the skill's own numbers, 0 when it states none.
    struct HitKind
    {
        bool generator, spender;
    };
    inline HitKind HitKinds(bool primary, double cost, double generated)
    {
        return {primary || generated > 0, cost > 0};
    }

    // The yards an item's event must be farther than: its own fixed `event_distance_yards` row (Halo of Karini: Storm Armor's shock "more
    // than 15 yards away"). 0: the item asks for no distance.
    inline double MinYards(std::vector<Row> const& rows, std::string const& owner)
    {
        for (Row const& row : rows)
            if (row.owner == owner && !row.pieces && row.kind == "player" && row.stat == "event_distance_yards")
                return row.min;
        return 0;
    }

    // N-STUN (Hellrack). A control effect puts a stock aura the client already has on the enemy the event is about, for the
    // row's seconds (dc_item_powers.cpp Control): `root_seconds` is stock 64695 "Earthgrab" (one MOD_ROOT effect, mechanic Root). A new control is
    // a stat here and in the generator's CONTROL_EFFECTS. 0: not a control effect.
    constexpr std::uint32_t StunHold = 853;   // stock "Hammer of Justice": one MOD_STUN effect, mechanic Stun; the item's stun is a stun and not Torment's freeze hold
    constexpr std::uint32_t RootHold = 64695;
    // N-FEAR (Maloth's Focus): `fear_enemies` puts stock 5782 "Fear" (one MOD_FEAR effect): the enemy runs from the player.
    constexpr std::uint32_t FearHold = 5782;
    inline std::uint32_t ControlSpell(std::string const& stat)
    {
        return stat == "root_seconds" ? RootHold : stat == "stun_seconds" ? StunHold : stat == "fear_enemies" ? FearHold : 0;
    }

    // N-FEAR. The clock is getMSTime(), a uint32 of milliseconds that wraps after about 49.7 days, so times are compared as differences in unsigned
    // arithmetic, which is right across the wrap. A stamp set ahead of now (DelayedStamp) is told from an old one by its distance: ahead is 1 ms to
    // MaxStampAheadMs in front of now; anything else in front, read as a difference, is a stamp from long ago.
    constexpr std::uint32_t MaxStampAheadMs = 3600000;
    inline bool StampAhead(std::uint32_t now, std::uint32_t last)
    {
        std::uint32_t const ahead = last - now;
        return ahead != 0 && ahead <= MaxStampAheadMs;
    }

    // N-FEAR. A row that fires on the clock waits its cooldown (`icd_seconds`) and, after a proc that feared someone, up to `deltaSeconds` more (the power
    // file's 'Cooldown Delta'): the row's stamp is set that far ahead of now, so Fire holds it for the extra time and then the cooldown. `unit` is a draw
    // from 0 to 1.
    inline std::uint32_t DelayedStamp(std::uint32_t now, double deltaSeconds, double unit)
    {
        return now + static_cast<std::uint32_t>(std::max(0.0, deltaSeconds) * 1000.0 * std::min(1.0, std::max(0.0, unit)));
    }

    // N-FEAR. A proc that found nobody in reach does not spend its cooldown: the row may try again after `retrySeconds` (the standing default for a trigger
    // check, 0.25 s), which is the stamp that leaves that much of the cooldown to wait (modular, so right across the clock's wrap). Now, when the cooldown is no
    // longer than the retry.
    constexpr double TriggerCheckSeconds = 0.25;
    inline std::uint32_t RetryStamp(std::uint32_t now, double icdSeconds, double retrySeconds)
    {
        double const wait = std::max(0.0, retrySeconds) * 1000.0, cooldown = std::max(0.0, icdSeconds) * 1000.0;
        if (wait >= cooldown)
            return now;
        return now + static_cast<std::uint32_t>(wait) - static_cast<std::uint32_t>(cooldown);
    }

    // N-PULLFX (The Butcher's Sickle). Whether a hit may drag the enemy it struck: the enemy is within `yards` of the wearer (the power file's 'max Range', the end
    // inclusive; no reach, no drag) and the item's last drag (`dragged`, at `last`) is at least `cooldownSeconds` ago (the end inclusive). The chance is rolled only when this
    // holds, so a failed roll costs no cooldown; a drag that happened starts it.
    inline bool DragReady(double distance, double yards, std::uint32_t now, bool dragged, std::uint32_t last, double cooldownSeconds)
    {
        if (yards <= 0 || distance < 0 || distance > yards)
            return false;
        if (!dragged)
            return true;
        // An unsigned difference: right across the clock's wrap (getMSTime is a uint32 of ms, about 49.7 days), where a stamp from before it is above now.
        return (now - last) >= static_cast<std::uint32_t>(std::max(0.0, cooldownSeconds) * 1000.0);
    }

    // N-LESSER (Ranslor's Folly): a lesser enemy is a monster that is neither an elite (a native elite, or any monster of a champion or rare pack) nor a boss
    // (a world or dungeon boss, a Rift Guardian). A unit that is not a monster is not one.
    inline bool IsLesser(bool monster, bool elite, bool boss)
    {
        return monster && !elite && !boss;
    }

    // N-LESSER. Whether a twister's pull takes one enemy now: it is a lesser enemy, within `yards` of the twister (the power file's 'Radius', the end inclusive) and
    // not pulled by the wearer's twisters in the last `cooldownSeconds` (the file's 'Per Target ICD', the end inclusive; `pulled` says there was a pull at `last`).
    // The reach and the clock are DragReady's, including across the clock's wrap.
    inline bool LesserPull(bool lesser, double distance, double yards, std::uint32_t now, bool pulled, std::uint32_t last, double cooldownSeconds)
    {
        return lesser && DragReady(distance, yards, now, pulled, last, cooldownSeconds);
    }

    // N-ABSGRANT (Wall of Man). Whether an item's wait is over: nothing has started it yet (`started` false), or `seconds` have passed since `last`, the end
    // inclusive (an unsigned difference: right across the clock's wrap). A failed chance roll does not start the wait; the caller stamps `last` only for a shield.
    inline bool CooldownOver(std::uint32_t now, bool started, std::uint32_t last, double seconds)
    {
        return !started || (now - last) >= static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);
    }

    // N-HEAL (Vambraces of Sescheron). The heal of `pct` percent of the Life the player is missing; nothing at full Life, with no maximum or for a share that is not above 0.
    inline double MissingLifeHeal(double pct, double health, double maxHealth)
    {
        if (pct <= 0 || maxHealth <= 0 || health >= maxHealth)
            return 0.0;
        return (maxHealth - std::max(0.0, health)) * pct / 100.0;
    }

    // N-PULLFX. The hook's damage: from `minimum` to `minimum` plus `delta` (the power file's 'damage' and 'damage Delta'), by a draw from 0 to 1.
    inline double DragDamage(double minimum, double delta, double unit)
    {
        return std::max(0.0, minimum) + std::max(0.0, delta) * std::min(1.0, std::max(0.0, unit));
    }

    // The event a control aura a player put on an enemy is (dc_item_powers.cpp ControlEvents), from the aura's effects and mechanic: a Stun aura
    // is a freeze when it carries the Freeze mechanic (the Wizard's Frozen) or is Torment's freeze hold (stock 15878 "Ice Blast", mechanic Stun: the
    // a skill's and the rift elites' freeze), else a stun; a confuse is Torment's blind (stock 9992 "Dizzy", Blinding Flash); a root a root. An aura
    // with none of them is no event (""). Stun is read first: an aura that stuns and roots holds the enemy as a stun does.
    constexpr std::uint32_t FreezeHold = 15878;
    inline char const* ControlEvent(std::uint32_t spellId, bool stun, bool freeze, bool confuse, bool root)
    {
        if (stun)
            return freeze || spellId == FreezeHold ? "control_freeze" : "control_stun";
        if (confuse)
            return "control_blind";
        if (root)
            return "control_root";
        return "";
    }

    // N-TCTRL (Ancient Parthan Defenders): whether one MOD_STUN aura of the record `spellId` holds its enemy stunned in D3's sense, a stun and not a freeze
    // (the control event the aura raises is `control_stun`: the Wizard's Frozen and Torment's freeze hold are freezes, `freeze` being the record's Freeze mechanic).
    inline bool StunAura(std::uint32_t spellId, bool freeze)
    {
        return std::string(ControlEvent(spellId, true, freeze, false, false)) == "control_stun";
    }

    // N-MARK (Madawc's Sorrow): the players who have hit an enemy, by guid; a hit by `player` is the first when it was not in the set (it is put in). The caller keeps one set
    // per creature.
    inline bool FirstHit(std::set<std::uint64_t>& hitBy, std::uint64_t player)
    {
        return hitBy.insert(player).second;
    }

    // Whether the worn powers mark the enemies a hit strikes: some active effect row holds `first_hit_on_target`. Without one, no enemy is marked.
    inline bool MarksFirstHits(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        double number = 0;
        for (Row const& row : rows)
            if (row.cond == "first_hit_on_target" && Owned(row, counts, situation, number))
                return true;
        return false;
    }

    // N-NEXT (Saffron Wrap): the enemies a skill's last cast hit, carried to its next cast. `carried` is what the last cast left (with the moment of its last hit), `riding` what the
    // cast in progress spends: the next cast pressed within `seconds` of that moment takes the carried count (ItemPower::EnemyPress) and leaves none behind; when that cast
    // has hit, its own enemies, at most `most`, are carried instead (ItemPower::EnemyConnect). A cast pressed too late rides on nothing.
    struct EnemyStack
    {
        unsigned riding = 0, carried = 0;
        std::uint32_t carriedAt = 0;
    };

    inline EnemyStack EnemyPress(EnemyStack stack, std::uint32_t now, double seconds)
    {
        bool const fresh = stack.carried > 0 && seconds > 0 && static_cast<std::int32_t>(now - stack.carriedAt) <= static_cast<std::int32_t>(seconds * 1000.0);
        return {fresh ? stack.carried : 0u, 0u, 0u};
    }

    inline EnemyStack EnemyConnect(EnemyStack stack, unsigned enemies, unsigned most, std::uint32_t now)
    {
        if (enemies == 0)
            return stack;
        stack.carried = std::min(enemies, most);
        stack.carriedAt = now;
        return stack;
    }

    // N-MONSLOW (Jang's Envelopment). The `slow_pct` effect slows the enemy the hit struck by its number for its owner's
    // `slow_seconds` (OwnerNumber), through stock 13496 "Dazed" (one MOD_DECREASE_SPEED effect, mechanic Snare; no other Torment code uses it, so it
    // never replaces a skill's own slow on the same enemy: the core slows a unit by its strongest snare) at SlowAmount, the percent as the aura's
    // negative whole amount (dc_item_powers.cpp Slow).
    constexpr std::uint32_t SlowHold = 13496;
    inline int SlowAmount(double pct)
    {
        return -static_cast<int>(std::lround(pct));
    }

    // What one fired `effect` row does: its stat names the effect, `value` is the amount (the item's stored roll when it has a range).
    struct Fired
    {
        std::string stat;
        double value;
        std::string skill; // the skill an `apply_skill` effect applies (blank for the others)
        Row const* row = nullptr; // the row that fired: a `stack_buff` reads its owner, seconds and stack_max
        std::string on;           // the `skill` the event carried: an element for `hit_element` (Tal Rasha's Elements)
    };

    // An event happened (`fireOn`, with the cast skill's name for `cast`). Every row of that event whose owner is in play, whose skills
    // allow it, whose internal cooldown is over and whose chance falls fires: its time is recorded in `situation.fired` (a `triggered`
    // condition reads it) and an `effect` row is returned for the caller to do. `scale` is what a chance is multiplied by: the hit's proc
    // coefficient on a hit event (0 for a hit that states none, which cannot proc: dc_proc_math.h), 1 on any other. A row whose chance is
    // 100 or more fires always. `roll` takes a percent and answers whether it fell.
    template <class Roll>
    inline std::vector<Fired> Fire(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation& situation,
                                   std::string const& fireOn, std::string const& skill, double scale, Roll roll)
    {
        std::vector<Fired> out;
        for (Row const& row : rows)
        {
            double number = 0;
            if (row.fireOn != fireOn || !Owned(row, counts, situation, number))
                continue;
            if (!row.fireSkills.empty() && std::find(row.fireSkills.begin(), row.fireSkills.end(), skill) == row.fireSkills.end())
                continue;
            // Halo of Karini: only an event farther than the item's yards (strictly: "more than").
            double const farther = MinYards(rows, row.owner);
            if (farther > 0 && !(situation.eventYards > farther))
                continue;
            // N-MARK (Madawc's Sorrow): only the first hit this player lands on the enemy (the caller marks the enemy and says whether this was the first).
            if (row.cond == "first_hit_on_target" && !situation.firstHit)
                continue;
            // N-CTF (Ahavarion): only an event about an enemy of one of the row's creature types (a kill of a demon).
            if (row.cond == "target_creature_type" && !CreatureTypeIs(row, situation.targetType))
                continue;
            // The Gavel of Judgment: only a cast that hit at least one and at most `arg` enemies (a caller that does not count passes 0).
            if (row.cond == "enemies_hit_at_most" && !(situation.enemiesHit >= 1 && situation.enemiesHit <= row.arg))
                continue;
            // Dark Mage's Shade: only a hit that takes Life from the item's level or above to under it.
            double level = 0;
            if (row.fireOn == "life_below" &&
                (!LifeThreshold(row.owner, situation, level) || !LifeFell(situation.lifeBeforePct, situation.lifeAfterPct, level)))
                continue;
            std::string const key = FireKey(row);
            auto last = situation.fired.find(key);
            // A `cast_skill` row's number is its internal cooldown in seconds (a range, so the item rolls it), or 0 for the caller's tunable
            // (Won Khim Lau); every other row has the column.
            double const icd = row.stat == "cast_skill" ? (number > 0 ? number : situation.castCooldownSeconds) : row.icdSeconds;
            if (last != situation.fired.end() && (StampAhead(situation.now, last->second) || (situation.now - last->second) < static_cast<std::uint32_t>(icd * 1000.0)))
                continue;   // a stamp ahead of now is the extra wait DelayedStamp put on the row
            if (row.chancePct < 100 && !(row.chancePct * scale > 0 && roll(row.chancePct * scale)))
                continue;
            situation.fired[key] = situation.now;
            if (row.kind == "effect")
                out.push_back({row.stat, number, row.skill, &row});
            if (row.kind == "effect" && row.fireOn == "hit_element")
                out.back().on = skill;
        }
        return out;
    }

    // N-SPENT (Immortal King's Call 4-piece): the `effect` rows fired on `resource_spent` ("for every N Fury you spend", N the
    // row's `cond_arg`). `spent` points added to the row's `carry` (the part of a step not yet paid, kept per row by the caller) give whole steps; the row fires once
    // with its number times the steps, so 25 spent at a step of 10 pays two now and keeps 5. Nothing spent, a row not owned or with no step: nothing.
    inline std::vector<Fired> SpentFires(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation,
                                         double spent, std::map<std::string, double>& carry)
    {
        std::vector<Fired> out;
        if (spent <= 0)
            return out;
        for (Row const& row : rows)
        {
            double number = 0;
            if (row.fireOn != "resource_spent" || row.kind != "effect" || row.arg <= 0 || !Owned(row, counts, situation, number))
                continue;
            double& held = carry[FireKey(row)];
            held += spent;
            double const steps = std::floor(held / row.arg);
            held -= steps * row.arg;
            if (steps >= 1)
                out.push_back({row.stat, number * steps, row.skill, &row});
        }
        return out;
    }

    // The `triggered` rows of `fireOn` that fired at this moment (Fire records it): the windows that open now, each shown for `arg` seconds
    // as its buff (The Burning Axe of Sankis). A row held by its internal cooldown fired earlier and is not one.
    inline std::vector<Row const*> Opened(std::vector<Row> const& rows, Situation const& situation, std::string const& fireOn)
    {
        std::vector<Row const*> out;
        for (Row const& row : rows)
            if (row.fireOn == fireOn && row.cond == "triggered")
                if (auto at = situation.fired.find(FireKey(row)); at != situation.fired.end() && at->second == situation.now)
                    out.push_back(&row);
        return out;
    }

    // Archmage's Vicalyke. A Mirror Image's death is the owner's `image_death` event only when something killed it and that was
    // an enemy of its owner: the end of its duration, the owner leaving and a friend's hit are not kills.
    inline bool ImageDeathCounts(bool killerKnown, bool killerHostileToOwner)
    {
        return killerKnown && killerHostileToOwner;
    }

    // Whether a killed Image multiplies. The chance is a tunable's percent (the sheet's blank placeholder reads 0: never), 100 or more is always;
    // `roll` takes a percent and answers whether it fell.
    template <class Roll>
    inline bool ImageMultiplies(double chancePct, Roll roll)
    {
        return chancePct > 0 && (chancePct >= 100 || roll(chancePct));
    }

    // The milliseconds the Image that replaces a dead one lives: the dead one's remaining time, and only for an Image of the owner's own
    // (another player's, or any other pet, gives none). No time left, none.
    inline std::uint32_t ImageCopyMs(bool own, std::uint32_t remainingMs)
    {
        return own ? remainingMs : 0;
    }

    // The number of `owner`'s `buff` row of `stat`: one stack's (Stone Gauntlets). 0 when it has none.
    inline double BuffValue(std::vector<Row> const& rows, std::string const& owner, std::string const& stat)
    {
        for (Row const& row : rows)
            if (row.owner == owner && !row.pieces && row.kind == "buff" && row.stat == stat)
                return row.min;
        return 0;
    }

    // The stacks after a `stack_buff` row fired on `held`: `add` more, at most `most`.
    inline unsigned Stacked(unsigned held, double add, unsigned most)
    {
        return std::min(held + static_cast<unsigned>(add), most);
    }

    // What `stacks` of `owner`'s slow leave of the attacks per second: 1 + stacks x its attack_speed_pct / 100, never under its
    // attack_speed_floor_pct / 100 (Stone Gauntlets: 1.0, 0.8, 0.6, 0.4, 0.2, then the floor 0.1).
    inline double StackedSpeedFactor(std::vector<Row> const& rows, std::string const& owner, unsigned stacks)
    {
        return std::max(BuffValue(rows, owner, "attack_speed_floor_pct") / 100.0, 1.0 + stacks * BuffValue(rows, owner, "attack_speed_pct") / 100.0);
    }

    // N-STACKBUFF (Orb of Infinite Depth): the multiplier of the `buff` rows of `stat` at the stacks of their owner's
    // record (`stacks`: owner -> the stacks on the player), each owner one multiplier, 1 + sign x stacks x N/100 (a reduction is sign -1),
    // N the item's own roll (Owned: a cubed power's top). 1 with no stacks. Never under 0: a cap raised by a tunable (Binding of the
    // Lost) can take a reduction to all of the damage, never past it. `skill` is the skill a row names (Fleshrake's Dashing Strike), blank for
    // the rows that name none.
    inline double StackedFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::map<std::string, unsigned> const& stacks,
                                std::string const& stat, double sign, Situation const& situation, std::string const& skill = "")
    {
        double factor = 1.0;
        for (Row const& row : rows)
        {
            auto held = stacks.find(row.owner);
            double number = 0;
            if (held != stacks.end() && row.kind == "buff" && row.stat == stat && row.skill == skill && Owned(row, counts, situation, number))
                factor *= std::max(0.0, 1.0 + sign * held->second * number / 100.0);
        }
        return factor;
    }

    // ---- Tal Rasha's Elements: N-ELEMEV, N-STACKBUFF, N-ELEMIMM ----
    // An attack's element is an event of its own (`hit_element`, fired with the element's name where a skill fires with its name, so a row names the
    // elements it fires on in `fire_skills`). The four elements the set reads, as the hit names them:
    inline constexpr char const* SetElements[] = {"arcane", "cold", "fire", "lightning"};

    // The state of the set for one player: when each element's buff (4-piece resistances, 2-piece immunity) ends, the element of the last Meteor the
    // 2-piece dropped, and the 6-piece window (its end, the elements that stacked, the last attack's element, the milliseconds it was extended by).
    struct ElementState
    {
        std::map<std::string, std::uint32_t> resistUntil, immuneUntil;
        std::string lastMeteor;
        std::uint32_t windowUntil = 0, extendedMs = 0;
        std::set<std::string> stacks;
        std::string lastHit;
    };

    // Whether the server clock `now` is before `until` (a wrapped clock subtracts correctly in unsigned arithmetic).
    inline bool Before(std::uint32_t now, std::uint32_t until)
    {
        return until != 0 && static_cast<std::int32_t>(until - now) > 0;
    }

    // N-COST (Kekegi's Unbreakable Spirit): a fired `cost_free_seconds` row makes every ability cost nothing for its number of seconds.
    // `until` is when the open window ends on the server clock (0: none open); the end after one more fires at `now`. A window never
    // shortens one already open.
    inline std::uint32_t CostFreeEnd(std::uint32_t until, std::uint32_t now, double seconds)
    {
        std::uint32_t const end = now + static_cast<std::uint32_t>(std::max(0.0, seconds) * 1000.0);
        bool const holds = until != 0 && static_cast<std::int32_t>(until - end) > 0;
        return holds ? until : end;
    }

    // Whether the window that ends at `until` is open at `now` (its last millisecond is not).
    inline bool CostFreeAt(std::uint32_t until, std::uint32_t now)
    {
        return Before(now, until);
    }

    // `element`'s buff (in `ends`) starts or starts again for `ms` from `now`; true when it was off before.
    inline bool Touch(std::map<std::string, std::uint32_t>& ends, std::string const& element, std::uint32_t now, std::uint32_t ms)
    {
        bool const was = Before(now, ends[element]);
        ends[element] = now + ms;
        return !was;
    }

    // How many of the buffs in `ends` are on now.
    inline unsigned CountOn(std::map<std::string, std::uint32_t> const& ends, std::uint32_t now)
    {
        unsigned on = 0;
        for (auto const& [element, until] : ends)
            on += Before(now, until) ? 1u : 0u;
        return on;
    }

    // The 6-piece window is open at `now`.
    inline bool WindowOn(ElementState const& state, std::uint32_t now)
    {
        return Before(now, state.windowUntil);
    }

    // An attack of `element` at `now` (Tal Rasha's 6-piece, the worker's reading): with no window open it opens one for `seconds` with this
    // element as its one stack; in an open window each new element is a stack; once `fullAt` stacks are held, every attack of an element other than the
    // last attack's extends the window by `extendSeconds`, all the extensions together at most `extendMaxSeconds`. Attacks do not renew a window.
    inline void WindowAttack(ElementState& state, std::string const& element, std::uint32_t now, double seconds, unsigned fullAt,
                             double extendSeconds, double extendMaxSeconds)
    {
        if (!WindowOn(state, now))
        {
            state.windowUntil = now + static_cast<std::uint32_t>(seconds * 1000.0);
            state.extendedMs = 0;
            state.stacks = {element};
            state.lastHit = element;
            return;
        }
        bool const full = state.stacks.size() >= fullAt;
        state.stacks.insert(element);
        if (full && element != state.lastHit)
        {
            std::uint32_t const most = static_cast<std::uint32_t>(extendMaxSeconds * 1000.0);
            std::uint32_t const add = std::min(static_cast<std::uint32_t>(extendSeconds * 1000.0), most - std::min(state.extendedMs, most));
            state.windowUntil += add;
            state.extendedMs += add;
        }
        state.lastHit = element;
    }

    // Whether the 2-piece drops a Meteor of `element` now: Meteor is on the bar, and it is not the element of the Meteor it dropped last.
    inline bool MeteorDrops(ElementState const& state, std::string const& element, bool meteorOnBar)
    {
        return meteorOnBar && element != state.lastMeteor;
    }

    // The rune of Meteor that deals `element`: the skill's own (no rune) is Fire, Comet Cold, Star Pact Arcane, Thunder Crash Lightning
    // (wizard_runes.csv). "" for the base skill and for an element Meteor has no rune for.
    inline std::string MeteorRune(std::string const& element)
    {
        if (element == "cold")
            return "Comet";
        if (element == "arcane")
            return "Star Pact";
        if (element == "lightning")
            return "Thunder Crash";
        return "";
    }

    // One tick of a bleed whose total is `total` over `baseTicks` ticks of one second, lasting as many ticks as the aura
    // has: the damage per second is the total over the base length, so a longer bleed pays more ticks of the same size and
    // its total grows with its length. The ticks are rounded so that they sum to the total of that length.
    inline double BleedTick(double total, unsigned baseTicks, unsigned tick)
    {
        return std::floor(total * tick / baseTicks) - std::floor(total * (tick - 1) / baseTicks);
    }

    // The ticks (whole seconds, at least one) of a bleed of `seconds`.
    inline unsigned Ticks(double seconds)
    {
        return seconds < 1.0 ? 1u : static_cast<unsigned>(std::lround(seconds));
    }

    // One bleed of a skill that stacks (Lamentation): a snapshot's `total` for `baseTicks` ticks, lasting `lengthTicks` (a longer
    // bleed pays more ticks of the same size, BleedTick) and paying out over `payTicks` of them (Ambo's Pride deals the whole damage in
    // one tick); it began after tick `start` of the aura that carries all the bleeds of one enemy.
    struct BleedStack
    {
        double total;
        unsigned baseTicks, lengthTicks, payTicks, start;
    };

    // What one bleed pays at the aura's tick number `tick` (0 outside its own ticks). Paid in full over its length, its ticks are
    // BleedTick's; compressed into fewer, the whole damage of its length is split over them.
    inline double StackTick(BleedStack const& stack, unsigned tick)
    {
        if (tick <= stack.start || tick > stack.start + stack.payTicks)
            return 0;
        unsigned const n = tick - stack.start;
        if (stack.payTicks == stack.lengthTicks)
            return BleedTick(stack.total, stack.baseTicks, n);
        return BleedTick(stack.total * stack.lengthTicks / stack.baseTicks, stack.payTicks, n);
    }

    // What all the bleeds pay at that tick, and the aura's tick on which the last of them ends.
    inline double BleedDamage(std::vector<BleedStack> const& stacks, unsigned tick)
    {
        double sum = 0;
        for (BleedStack const& stack : stacks)
            sum += StackTick(stack, tick);
        return sum;
    }

    inline unsigned BleedEnd(std::vector<BleedStack> const& stacks)
    {
        unsigned end = 0;
        for (BleedStack const& stack : stacks)
            end = std::max(end, stack.start + stack.payTicks);
        return end;
    }

    // A new bleed beside the running ones: while there are fewer than `cap` it is added, at the cap it replaces the oldest.
    inline void AddStack(std::vector<BleedStack>& stacks, BleedStack const& add, unsigned cap)
    {
        while (!stacks.empty() && stacks.size() >= (cap ? cap : 1))
            stacks.erase(std::min_element(stacks.begin(), stacks.end(), [](BleedStack const& a, BleedStack const& b) { return a.start < b.start; }));
        stacks.push_back(add);
    }

    // N-CD (Gesture of Orpheus): the multiplier on a skill's cooldown from its `cooldown_reduction_pct` rows, each active
    // source its own 1 - N/100 (D3 multiplies cooldown reductions), never below 0. 1.0 when none.
    inline double CooldownFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                                 Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "skill", skill, "cooldown_reduction_pct", situation))
            factor *= std::max(0.0, 1.0 - pct / 100.0);
        return factor;
    }

    // N-TCTRL (Fjord Cutter): the multiplier of a skill's `damage_increase_pct` rows whose condition is a state of the hit's target
    // (`target_slowed`), each active source 1 + N/100, with the target's states in `situation.targetControl`. SkillFactor reads the same rows with
    // no target, so a target row never holds there: it counts once, here.
    inline double TargetFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, std::string const& skill,
                               Situation const& situation)
    {
        double factor = 1.0;
        for (Row const& row : rows)
        {
            double number = 0;
            if (row.kind == "skill" && row.stat == "damage_increase_pct" && row.cond.rfind("target_", 0) == 0 && NamesSkill(row.skill, skill) &&
                Owned(row, counts, situation, number) && Holds(row, situation))
                factor *= 1.0 + number / 100.0;
        }
        return factor;
    }

    // N-TCTRL (Krysbin's Sentence): the multiplier of the `damage_vs_impaired_pct` rows on a hit, one multiplier per source: 1 + N/100 against a slowed target, 1 + 3N/100
    // against a target under any other control-impairing effect (the stronger one when it is both), 1 against a target under none. The target's states are in
    // `situation.targetControl`, so a reader that has no target gives 1.
    inline double ImpairedFactor(std::vector<Row> const& rows, std::map<std::string, unsigned> const& counts, Situation const& situation)
    {
        double factor = 1.0;
        for (double pct : ActiveValues(rows, counts, "player", "", "damage_vs_impaired_pct", situation))
        {
            if ((situation.targetControl & TargetControlled) != 0)
                factor *= 1.0 + 3.0 * pct / 100.0;
            else if ((situation.targetControl & TargetSlowed) != 0)
                factor *= 1.0 + pct / 100.0;
        }
        return factor;
    }

    // N-CLOCK's first effect (Bul-Kathos's Wedding Band): one pulse of `drain_life`. Each enemy loses `pct` percent of its
    // maximum Life, at most `capWeapons` x the player's weapon damage (ItemPassive_Unique_Ring_020_x1.pow SF_0, SF_1); the player gains what was
    // drained, at most `healPct` percent of its own maximum Life (SF_3). A cap of 0 caps nothing away: nothing is drained or healed.
    struct Drained
    {
        std::vector<double> taken; // per enemy, in the order given
        double healed = 0;
    };

    inline Drained DrainPulse(std::vector<double> const& enemyMaxLife, double pct, double weaponDamage, double capWeapons, double playerMaxLife,
                              double healPct)
    {
        Drained out;
        double sum = 0;
        for (double most : enemyMaxLife)
        {
            double const one = std::max(0.0, std::min(most * pct / 100.0, capWeapons * weaponDamage));
            out.taken.push_back(one);
            sum += one;
        }
        out.healed = std::max(0.0, std::min(sum, playerMaxLife * healPct / 100.0));
        return out;
    }

    // Lut Socks (N-CHG): a skill that can be cast `casts` times within `windowSeconds` of the first before its cooldown begins.
    // The first cast opens a window (`until` is its last millisecond, the end inclusive); the casts inside it keep the skill open; the
    // last one closes the window and leaves the cooldown the core installed. `token` numbers the windows, so that the end event of
    // a window that already closed finds nothing to close.
    struct Reuse
    {
        unsigned used = 0;
        std::uint32_t until = 0, token = 0;
        bool open = false;
    };

    struct ReuseStep
    {
        bool keepOpen = false, opened = false;
        unsigned used = 0;
        std::uint32_t token = 0;
    };

    // One pressed cast at `now` (milliseconds): whether the skill stays castable (the cooldown the core just installed is cleared) and
    // whether this cast opened the window (its end is scheduled). Fewer than two casts, or no window, is no rule at all.
    inline ReuseStep ReuseCast(Reuse& state, unsigned casts, double windowSeconds, std::uint32_t now)
    {
        ReuseStep step;
        if (casts < 2 || windowSeconds <= 0)
            return step;
        if (!state.open || static_cast<std::int32_t>(state.until - now) < 0)
        {
            state.open = true;
            state.used = 1;
            ++state.token;
            state.until = now + static_cast<std::uint32_t>(std::lround(windowSeconds * 1000.0));
            step.opened = true;
        }
        else
            ++state.used;
        step.keepOpen = state.used < casts;
        if (!step.keepOpen)
        {
            state.open = false;
            state.used = 0;
        }
        step.used = state.used;
        step.token = state.token;
        return step;
    }

    // The end of the window numbered `token`: true when it was still open (the cooldown begins now). An end event of a window the last
    // cast already closed, or one a new window replaced, closes nothing.
    inline bool ReuseEnded(Reuse& state, std::uint32_t token)
    {
        if (!state.open || state.token != token)
            return false;
        state.open = false;
        return true;
    }
} // namespace DC::Combat::ItemPower
