// Items: the roll (the plan, the staged roll, the pool draws) and the Ancient / Primal quality decision.
// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (10): one-decimal rounding of a rolled affix value; Rounding, not a game value.
#include "dc_items_internal.h"

#include "../combat/dc_item_powers.h"
#include "../classes/dc_resources.h"
#include "../common/dc_tunables.h"
#include "../difficulty/dc_difficulty.h"
#include "../rifts/dc_rifts.h"
#include "dc_granted_passive_rule.h"
#include "dc_resource_affix_rule.h"
#include "dc_roll_class.h"

#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "Player.h"
#include "ScriptMgr.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <random>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Items
{
namespace
{
// What ".dc item" reports with no argument: the last thing this session rolled.
std::mutex lastMutex;
std::unordered_map<std::uint64_t, std::uint64_t> lastRolled;
}

namespace Detail
{
std::uint64_t LastRolled(std::uint64_t playerGuid)
{
    std::lock_guard<std::mutex> lock(lastMutex);
    auto found = lastRolled.find(playerGuid);
    return found == lastRolled.end() ? 0 : found->second;
}

// --- rolling ---------------------------------------------------------------
// I8: Rare = 4 primary + 2 secondary, Magic = 1-2 total, Normal = 0,
// Legendary/Set = presets then random fill to 4 + 2. The numbers are data:
// the full roll is D3's Rare maximum, read from
// rarity_tiers.csv into loot/full_roll_*_affixes; the Magic split is ours (D3
// publishes only "1-2 total") in data/tunables/loot.csv.
Counts CountsFor(std::string const& rarity)
{
    if (rarity == "magic")
        return {static_cast<unsigned>(DC::Tunables::Get("loot", "magic_primary_affixes")),
                static_cast<unsigned>(DC::Tunables::Get("loot", "magic_secondary_affixes"))};
    // Every other rarity rolls the full budget. A generic base carries no
    // rarity of its own; which rarity it drops as is 06-loot's decision. Until
    // that exists, roll it as Rare so the base is usable, which is also I8's
    // fully-random case.
    return {static_cast<unsigned>(DC::Tunables::Get("loot", "full_roll_primary_affixes")),
            static_cast<unsigned>(DC::Tunables::Get("loot", "full_roll_secondary_affixes"))};
}
// Which statLimits bracket the pool is read from: the item's rarity, and for a Legendary or Set item its
// quality tier (an Ancient reads the ancient rows, a Primal the primal rows).
std::string BracketFor(std::string const& rarity, std::string const& quality)
{
    return DC::Quality::Bracket(rarity, quality);
}

double RollValue(PoolEntry const& entry)
{
    if (entry.max <= entry.min)
        return entry.min;
    std::uniform_real_distribution<double> distribution(entry.min, entry.max);
    double rolled = distribution(Engine());
    // Issue #56: a row with a sourced step rolls on that step - glove crit
    // chance 8-10 by 0.5 reaches 8.5 and 9.5 - snapped the same way a whole
    // number is, and printed to the step's own decimals.
    if (entry.step > 0)
    {
        double scale = 1;
        while (scale < 1e6 && std::fabs(entry.step * scale - std::round(entry.step * scale)) > 1e-9)
            scale *= 10;
        double const steps = std::floor((rolled - entry.min) / entry.step + 0.5);
        return std::round((entry.min + steps * entry.step) * scale) / scale;
    }
    // No step in the source: whole-number ranges produce whole numbers;
    // fractional ranges keep the one decimal D3 shows.
    bool whole = entry.min == std::floor(entry.min) && entry.max == std::floor(entry.max);
    return whole ? std::floor(rolled + 0.5) : std::floor(rolled * 10 + 0.5) / 10;
}
// Legendary powers: an item that dropped before its power's row existed has no stored roll. The first time the server
// reads it (Load: equip, login, every consumer of Get) it rolls the powers it lacks, a Primal at the top, and stores them beside its affixes.
// Under one lock, held until the commit has landed, so two threads reading the item at once store one row and Load's own SELECT
// sees it; the hit path never gets here (it reads WornRolls).
void BackfillPowers(std::uint64_t itemGuid, std::uint32_t baseItem, std::string const& qualityTier)
{
    std::string d3Id;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        auto base = baseItems.find(baseItem);
        if (base == baseItems.end())
            return;
        d3Id = base->second.d3Id;
    }
    std::vector<DC::Combat::ItemPower::Row> const rows = DC::Combat::ItemPowers::ItemRows(d3Id);
    if (rows.empty())
        return;
    static std::mutex backfillMutex;
    std::lock_guard<std::mutex> lock(backfillMutex);
    std::vector<DC::Combat::ItemPower::Stored> have;
    unsigned next = 0;
    if (QueryResult stored = CharacterDatabase.Query("SELECT affix_id, kind, seq FROM dc_item_affix WHERE item_guid={}", itemGuid))
        do
        {
            Field* fields = stored->Fetch();
            if (fields[1].Get<std::string>() == "power")
                have.push_back({fields[0].Get<std::string>(), 0});
            next = std::max(next, fields[2].Get<uint16>() + 1u);
        } while (stored->NextRow());
    unsigned const firstSeq = next;
    CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
    for (auto const& power : DC::Combat::ItemPower::RollPowers(rows, d3Id, DC::Quality::AtTop(qualityTier),
                                                                [](double low, double high)
                                                                {
                                                                    PoolEntry range;
                                                                    range.min = low;
                                                                    range.max = high;
                                                                    return RollValue(range);
                                                                }, have))
        transaction->Append(
            "INSERT INTO dc_item_affix (item_guid, seq, affix_id, value, range_min, range_max, kind, rerolled) "
            "VALUES ({}, {}, '{}', {}, {}, {}, 'power', 0)",
            itemGuid, next++, Escape(power.key), power.value, power.min, power.max);
    if (next != firstSeq)
        CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get();
}

// G1: the seven weapon elemental affixes (data_stats.js:16-22) are D3's one exclusive "weapon"
// group (statExclusiveGroups :383-385): a weapon carries exactly one. The pool marks their rows
// with a weapon_class, so group membership is visible there too; this list answers the one
// question the pool cannot: whether an item's authored preset already chooses its element.
bool WeaponDamageAffix(std::string const& id)
{
    static char const* const ids[] = {"wpnphy", "wpnfir", "wpncol", "wpnpsn", "wpnarc", "wpnlit", "wpnhol"};
    for (char const* candidate : ids)
        if (id == candidate)
            return true;
    return false;
}
// G1: a weapon elemental affix rolls D3's two parts - the min endpoint in [min,max] and a delta
// in [min2-min, max2-max] (max = min + delta lands in [min2,max2] and stays above min).
double RollWeaponDelta(PoolEntry const& entry)
{
    double const low = entry.min2 - entry.min, high = entry.max2 - entry.max;
    if (high <= low)
        return std::max(0.0, low);
    std::uniform_real_distribution<double> distribution(low, high);
    return std::floor(distribution(Engine()) + 0.5);
}

// `.dc quality force`: a GM's override of the whole quality decision, per player, until relog or restart.
std::mutex forceMutex;
std::unordered_map<std::uint64_t, std::string> forcedQuality;

DC::Quality::Rule QualityRule()
{
    DC::Quality::Rule rule;
    rule.ancientPct = DC::Tunables::Get("loot", "ancient_chance_pct");
    rule.primalPct = DC::Tunables::Get("loot", "primal_chance_pct");
    rule.minTier = static_cast<unsigned>(DC::Tunables::Get("loot", "ancient_min_tier"));
    rule.gambleMinTier = static_cast<unsigned>(DC::Tunables::Get("loot", "ancient_min_tier_gamble"));
    rule.minItemLevel = static_cast<unsigned>(DC::Tunables::Get("loot", "ancient_min_item_level"));
    return rule;
}

// D3 unlocks Primals once per game mode for the whole account (drop_rates.csv ancient_primal "Primal
// chance"; kadala.csv primal_ancient_chance): the account's best solo Greater Rift in the character's mode.
bool PrimalUnlocked(Player* player)
{
    return DC::Rifts::AccountGreaterRiftBeatenSolo(player->GetGUID().GetCounter()) >=
           static_cast<unsigned>(DC::Tunables::Get("loot", "primal_unlock_solo_gr"));
}
}

using namespace Detail;

StagedRoll::~StagedRoll()
{
    if (!item_ || published_)
        return;
    auto* bag = item_->GetContainer();
    player_->RemoveItem(item_->GetBagSlot(), item_->GetSlot(), false);
    item_->RemoveFromUpdateQueueOf(player_);
    if (item_->IsInWorld())
        item_->RemoveFromWorld();
    delete item_;
    if (bag)
        bag->SetState(ITEM_CHANGED, player_);
}

Item* StagedRoll::Publish()
{
    if (published_)
        return item_;
    published_ = true;
    if (player_->IsInWorld())
    {
        item_->AddToWorld();
        item_->SendUpdateToPlayer(player_);
    }
    player_->ItemAddedQuestCheck(item_->GetEntry(), 1);
    player_->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_RECEIVE_EPIC_ITEM, item_->GetEntry(), 1);
    player_->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_OWN_ITEM, item_->GetEntry(), 1);
    player_->AdditionalSavingAddMask(ADDITIONAL_SAVING_INVENTORY_AND_GOLD);
    sScriptMgr->OnPlayerStoreNewItem(player_, item_, 1);
    {
        std::lock_guard<std::mutex> lock(lastMutex);
        lastRolled[player_->GetGUID().GetRawValue()] = item_->GetGUID().GetCounter();
    }
    return item_;
}

// The planning step StageRoll executes: the fixed affixes in take order and the per-kind random
// counts the fill will take. Pure - no Player, no RNG, no writes. A preset naming something
// outside this slot's pool rolls in the item's own range (itemPresets) or, with none, is skipped
// rather than invented; a shield's required block lines, a Source's, Mojo's or Phylactery's
// damage and a Quiver's attack speed come first and outside the budget; the fill never exceeds what the pool still holds.
RollPlan PlanRoll(RollPlanInput const& in)
{
    RollPlan plan;
    std::vector<std::string> used;
    // G1: the seven weapon elemental affixes are one exclusive group (a row carries a
    // weapon_class), so only the first is ever taken and the fill can never add a second.
    bool weaponDamageTaken = false;
    auto unused = [&](PoolEntry const& entry)
    {
        return std::find(used.begin(), used.end(), entry.affixId) == used.end() &&
               !(!entry.weaponClass.empty() && weaponDamageTaken);
    };
    auto take = [&](PoolEntry const& entry, bool counted)
    {
        RollPlanFixed fixed;
        fixed.entry = entry;
        fixed.counted = counted;
        fixed.socket = entry.affixId == "sockets";
        fixed.skill = std::find(in.skillGroups.begin(), in.skillGroups.end(), entry.affixId) != in.skillGroups.end();
        plan.fixed.push_back(fixed);
        used.push_back(entry.affixId);
        if (!entry.weaponClass.empty())
            weaponDamageTaken = true;
    };
    if (in.shield)
        for (PoolEntry const& entry : in.primary)
            if (RequiredShieldAffix(entry.affixId) && unused(entry))
                take(entry, false);
    if (in.damageOffhand)
        for (PoolEntry const& entry : in.primary)
            if (entry.affixId == "wpnphy" && unused(entry))
                take(entry, false);
    if (in.speedQuiver)
        for (PoolEntry const& entry : in.primary)
            if (entry.affixId == "ias" && unused(entry))
                take(entry, false);
    unsigned presetPrimaries = 0, presetSecondaries = 0;
    for (std::string const& preset : in.presets)
    {
        auto found = std::find_if(in.primary.begin(), in.primary.end(),
                                  [&](PoolEntry const& entry) { return entry.affixId == preset; });
        bool primary = found != in.primary.end();
        if (!primary)
        {
            found = std::find_if(in.secondary.begin(), in.secondary.end(),
                                 [&](PoolEntry const& entry) { return entry.affixId == preset; });
            if (found == in.secondary.end())
            {
                found = std::find_if(in.itemPresets.begin(), in.itemPresets.end(),
                                     [&](PoolEntry const& entry) { return entry.affixId == preset; });
                if (found == in.itemPresets.end())
                    continue;
                primary = found->kind != "secondary";
            }
        }
        if (!unused(*found))
            continue;
        take(*found, true);
        (primary ? presetPrimaries : presetSecondaries)++;
    }
    auto available = [&](std::vector<PoolEntry> const& pool)
    {
        unsigned count = 0;
        for (PoolEntry const& entry : pool)
            if (unused(entry))
                ++count;
        return count;
    };
    unsigned const wantPrimary = in.counts.primary > presetPrimaries ? in.counts.primary - presetPrimaries : 0;
    unsigned const wantSecondary =
        in.counts.secondary > presetSecondaries ? in.counts.secondary - presetSecondaries : 0;
    plan.randomPrimary = std::min(wantPrimary, available(in.primary));
    plan.randomSecondary = std::min(wantSecondary, available(in.secondary));
    return plan;
}

std::unique_ptr<StagedRoll> StageRoll(Player* player, std::uint32_t baseItemId, unsigned itemLevel,
                                      std::string const& rarity, CharacterDatabaseTransaction const& transaction,
                                      std::string const& rollClass, std::string const& quality,
                                      std::string const& mainStat)
{
    if (!player || !transaction)
        return nullptr;
    // A recipe that fixes the main stat (the Hellfire Amulet's Strength, Intelligence and Dexterity versions) names
    // its pool id; anything else is a data error and rolls nothing.
    if (!mainStat.empty() && mainStat != "str" && mainStat != "dex" && mainStat != "int")
        return nullptr;
    // The quality is decided at the drop and passed in; a caller with no drop of its own (the set and bounty caches,
    // the starter kit, the GM roll) passes "" and it is decided here, with the monster drop's Torment I gate. Kadala,
    // the slot vendors, the Cube and the artisans pass RollQuality(.., gambled) instead (the level gate only).
    std::string qualityTier = quality.empty() ? RollQuality(player, baseItemId, itemLevel) : DC::Quality::Clean(quality);
    BaseItem base;
    std::vector<PoolEntry> primaryPool, secondaryPool, itemPresets;
    std::unordered_map<std::string, std::vector<SkillAffix>> groups;
    // Rule 3: one class for the main stat and every skill affix - a class-only
    // base's own, otherwise the class the drop rolled for (the player's own when
    // the caller names none: the starter kit, crafting, the GM roll).
    std::string affixClass;
    // The `resource` preset's affix id for affixClass (dc_resource_affix_rule.h); empty rolls nothing.
    std::string resourceAffix;
    // G1: the base's own damage bracket (dc_weapon_class), empty for a non-weapon or a weapon
    // type the map does not name (which then rolls no elemental damage).
    std::string weaponClass;
    std::unordered_map<std::string, std::string> mainStats;
    // The roll class's whole passive list, when the base grants one.
    std::vector<std::string> passiveChoices;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        if (!dataReady)
            return nullptr;
        auto found = baseItems.find(baseItemId);
        if (found == baseItems.end())
            return nullptr;
        base = found->second;
        // Only a Legendary or Set base has a quality; a caller cannot make a Rare Ancient. A Bottomless potion is
        // Legendary but never Ancient, as in D3: its power rolls in its range, not at the top.
        if (!DC::Quality::Eligible(base.rarity) || base.slot == "potion")
            qualityTier = "normal";
        // A follower relic is Legendary only until the switch (followers_relic_rules.csv relic_ancient_primal) says otherwise.
        qualityTier = DC::Relic::Quality({base.relicPrimary, base.relicSecondary}, relicAncientPrimal, qualityTier);
        affixClass = DC::RollClass::AffixClass(base.designatedClass,
            rollClass.empty() ? ClassKeyOfLocked(player->getClass()) : rollClass);
        mainStats = classMainStats;
        for (auto const& [groupId, choices] : skillGroups)
            groups[groupId] = SkillChoices(skillGroups, groupId, affixClass);
        // A generic base's rarity belongs to the roll. The starter kit requests
        // rare explicitly; unique bases must retain their own source rarity.
        if (!rarity.empty())
        {
            if (rarity != "rare" && rarity != base.rarity)
                return nullptr;
            if (!base.rarity.empty() && rarity != base.rarity)
                return nullptr;
            base.rarity = rarity;
        }
        if (base.slot == "onehand" || base.slot == "twohand")
            if (auto found = weaponClassByType.find(base.type); found != weaponClassByType.end())
                weaponClass = found->second;
        if (DC::GrantedPassive::Rolls(base.presets, base.rarity))
            if (auto id = classIds.find(affixClass); id != classIds.end())
                if (auto list = classPassiveNames.find(id->second); list != classPassiveNames.end())
                    passiveChoices = list->second;
        if (auto own = itemPresetRanges.find(baseItemId); own != itemPresetRanges.end())
            if (auto rows = own->second.find(BracketFor(base.rarity, qualityTier)); rows != own->second.end())
                itemPresets = rows->second;
        if (std::find(base.presets.begin(), base.presets.end(), DC::ResourceAffix::Preset) != base.presets.end())
        {
            std::vector<std::string> resources;
            if (auto id = classIds.find(affixClass); id != classIds.end())
                for (auto role : {DC::Resources::Data::Role::Primary, DC::Resources::Data::Role::Second})
                    for (auto const& row : DC::Resources::Data::Rows)
                        if (row.classId == id->second && row.role == role)
                            resources.push_back(row.d3Name);
            resourceAffix = DC::ResourceAffix::For(resources, itemPresets);
            if (resourceAffix.empty())
                LOG_ERROR("server", "[DC items] base item {} ({}): roll class '{}' has no Maximum <resource> row in "
                          "item_preset_ranges.csv, so the resource preset is not rolled",
                          base.entry, base.name, affixClass);
        }
        for (PoolEntry const& entry : PoolFor(base, BracketFor(base.rarity, qualityTier)))
        {
            // G1: only the weapon-damage rows for this weapon type's own bracket - the
            // pool carries all four (slot, weapon_class) combinations.
            if (!entry.weaponClass.empty() && entry.weaponClass != weaponClass)
                continue;
            if (BlockAffix(entry.affixId) && !DC::Relic::RollsBlock(Shield(base), {base.relicPrimary, base.relicSecondary}))
                continue;
            if (OffhandDamageAffix(base, entry.affixId) && !DamageOffhand(base))
                continue;
            if (OffhandSpeedAffix(base, entry.affixId) && !SpeedQuiver(base))
                continue;
            // A skill affix with no choice for this class is not rolled;
            // the fill takes another affix in its place.
            if (auto group = groups.find(entry.affixId); group != groups.end() && group->second.empty())
                continue;
            (entry.kind == "secondary" ? secondaryPool : primaryPool).push_back(entry);
        }
    }

    ItemPosCountVec destination;
    if (player->CanStoreNewItem(NULL_BAG, NULL_SLOT, destination, baseItemId, 1) != EQUIP_ERR_OK)
        return nullptr;
    std::vector<Affix> rolled;
    std::vector<std::string> used;
    // G1: the weapon elemental group is exclusive; once one is taken the fill cannot take another.
    bool weaponDamageTaken = false;
    // A Primal rolls every affix at the top of the ancient bracket.
    bool const atTop = DC::Quality::AtTop(qualityTier);
    auto valueOf = [&](PoolEntry const& entry) { return atTop ? entry.max : RollValue(entry); };
    auto take = [&](PoolEntry const& entry, char const* kind)
    {
        // A socket affix rolls a count, then becomes that many socket rows (05 §5).
        if (entry.affixId == "sockets")
        {
            unsigned sockets = static_cast<unsigned>(valueOf(entry));
            for (unsigned index = 0; index < sockets; ++index)
                rolled.push_back({static_cast<unsigned>(rolled.size()), entry.affixId, entry.name, 0, entry.min,
                                  entry.max, "socket", entry.isPercent, false});
        }
        else if (entry.max2 > 0)
        {
            // G1: a row with a second range rolls D3's two parts (a weapon's elemental damage,
            // jewelry's +X-Y Physical Damage) - min in [a,b], delta in [c-a,d-b], so the max
            // (value2) lands in [c,d] and stays above the min.
            Affix affix;
            affix.seq = static_cast<unsigned>(rolled.size());
            affix.affixId = entry.affixId;
            affix.name = entry.name;
            affix.value = valueOf(entry);
            affix.rangeMin = entry.min;
            affix.rangeMax = entry.max;
            affix.value2 = atTop ? entry.max2 : affix.value + RollWeaponDelta(entry);
            affix.rangeMin2 = entry.min2;
            affix.rangeMax2 = entry.max2;
            affix.kind = kind;
            affix.isPercent = entry.isPercent;
            rolled.push_back(affix);
            if (!entry.weaponClass.empty())
                weaponDamageTaken = true;
        }
        else if (entry.affixId == ELEMENTAL_POOL_ID)
        {
            ElementalAffix const& affix = RollElemental();
            rolled.push_back({static_cast<unsigned>(rolled.size()), affix.id, affix.name, valueOf(entry),
                              entry.min, entry.max, kind, true, false});
        }
        else if (entry.affixId == RESIST_POOL_ID)
        {
            ElementalAffix const& pick = RollResist();
            rolled.push_back({static_cast<unsigned>(rolled.size()), pick.id, pick.name, valueOf(entry),
                              entry.min, entry.max, kind, entry.isPercent, false});
        }
        else if (auto group = groups.find(entry.affixId); group != groups.end())
        {
            auto const& choices = group->second;
            auto const& choice =
                choices[std::uniform_int_distribution<std::size_t>(0, choices.size() - 1)(Engine())];
            rolled.push_back({static_cast<unsigned>(rolled.size()), choice.id, choice.name, valueOf(entry),
                              entry.min, entry.max, kind, true, false});
        }
        else
        {
            auto id = entry.affixId != "mainstat" ? entry.affixId
                      : mainStat.empty() ? PrimaryStat(base, affixClass, mainStats)
                                         : mainStat;
            // Issue #47: no main stat is a logged data error, and nothing is rolled.
            if (id.empty())
                return;
            rolled.push_back({static_cast<unsigned>(rolled.size()), id,
                              entry.affixId == "mainstat" ? PrimaryName(id) : entry.name, valueOf(entry),
                              entry.min, entry.max, kind, entry.isPercent, false});
        }
        used.push_back(entry.affixId);
    };
    auto unused = [&](PoolEntry const& entry)
    {
        return std::find(used.begin(), used.end(), entry.affixId) == used.end() &&
               !(!entry.weaponClass.empty() && weaponDamageTaken);
    };

    // The decision the roll executes, shared with the Blacksmith preview: shield block lines
    // and offhand damage and quiver speed first and outside the budget, then the presets (one outside the pool rolls in the item's own range,
    // dc_item_preset_range, or is skipped), then the random fill to the rarity's counts, never repeating
    // an affix id.
    RollPlanInput planning;
    planning.primary = primaryPool;
    planning.secondary = secondaryPool;
    planning.presets = base.presets;
    // The `resource` preset rolls as the roll class's own Maximum <resource> row, or not at all.
    for (std::string& preset : planning.presets)
        if (preset == DC::ResourceAffix::Preset)
            preset = resourceAffix;
    planning.itemPresets = itemPresets;
    // Legendary powers P0: the stat rows of the item power table are the item's own presets, rolled in the
    // table's range (data/legendary_powers.csv), whether or not the base item lists them.
    std::vector<DC::Combat::ItemPower::Row> const powerStats = DC::Combat::ItemPowers::ItemStats(base.d3Id);
    for (auto const& row : powerStats)
        if (std::find(planning.presets.begin(), planning.presets.end(), row.stat) == planning.presets.end())
            planning.presets.push_back(row.stat);
    // G1: a weapon with no authored elemental preset still rolls exactly one of the seven, at
    // 1/7. StageRoll owns the RNG, so it picks the element and hands it to
    // PlanRoll as a preset; PlanRoll then enforces the group's exclusivity.
    if (!weaponClass.empty())
    {
        bool authored = false;
        for (std::string const& preset : base.presets)
            if (WeaponDamageAffix(preset))
                authored = true;
        std::vector<PoolEntry const*> elements;
        if (!authored)
            for (PoolEntry const& entry : primaryPool)
                if (!entry.weaponClass.empty())
                    elements.push_back(&entry);
        if (!elements.empty())
            planning.presets.push_back(
                elements[std::uniform_int_distribution<std::size_t>(0, elements.size() - 1)(Engine())]->affixId);
    }
    planning.shield = Shield(base);
    planning.damageOffhand = DamageOffhand(base);
    planning.speedQuiver = SpeedQuiver(base);
    Counts const rarityCounts = CountsFor(base.rarity);
    DC::Relic::Roll const counts =
        DC::Relic::Counts({base.relicPrimary, base.relicSecondary}, {rarityCounts.primary, rarityCounts.secondary});
    planning.counts = {counts.primary, counts.secondary};
    for (auto const& [groupId, choices] : groups)
        if (!choices.empty())
            planning.skillGroups.push_back(groupId);
    RollPlan const plan = PlanRoll(planning);

    for (RollPlanFixed const& fixed : plan.fixed)
    {
        PoolEntry entry = fixed.entry;
        DC::Combat::ItemPower::RollRange(powerStats, base.d3Id, entry.affixId, entry.min, entry.max);
        take(entry, "preset");
    }
    auto fill = [&](std::vector<PoolEntry>& pool, unsigned wanted, char const* kind)
    {
        std::vector<PoolEntry> available;
        std::copy_if(pool.begin(), pool.end(), std::back_inserter(available), unused);
        std::shuffle(available.begin(), available.end(), Engine());
        for (unsigned index = 0; index < wanted && index < available.size(); ++index)
            take(available[index], kind);
    };
    fill(primaryPool, plan.randomPrimary, "primary");
    fill(secondaryPool, plan.randomSecondary, "secondary");
    // Legendary powers: an item-owned power with a range rolls once, stored beside the affixes as a row of kind
    // 'power'. A Primal takes the top of the range.
    for (auto const& power : DC::Combat::ItemPower::RollPowers(DC::Combat::ItemPowers::ItemRows(base.d3Id), base.d3Id, atTop,
                                                                [](double low, double high)
                                                                {
                                                                    PoolEntry range;
                                                                    range.min = low;
                                                                    range.max = high;
                                                                    return RollValue(range);
                                                                }))
        rolled.push_back({static_cast<unsigned>(rolled.size()), power.key, "", power.value, power.min, power.max, "power", false, false});
    // A class passive for the roll's class, stored beside the affixes as a row of kind 'passive'.
    if (!passiveChoices.empty())
        rolled.push_back({static_cast<unsigned>(rolled.size()),
                          DC::GrantedPassive::Pick(passiveChoices, std::uniform_real_distribution<double>(0.0, 1.0)(Engine())),
                          "", 0, 0, 0, DC::GrantedPassive::Kind, false, false});

    // Only a fresh, empty slot is allowed: never merge a staged roll with an
    // existing item or publish StoreNewItem hooks before the caller commits.
    if (destination.size() != 1 || destination.front().count != 1 || player->GetItemByPos(destination.front().pos))
        return nullptr;
    std::unique_ptr<Item> fresh(Item::CreateItem(baseItemId, 1, player));
    if (!fresh || fresh->GetTemplate()->GetMaxStackSize() != 1)
        return nullptr;
    Item* item = player->StoreItem(destination, fresh.get(), false);
    if (!item)
        return nullptr;
    // StoreItem took ownership, so the guard must let go without deleting. The
    // released pointer is deliberately dropped: `item` is the same object and is
    // what the rest of this function uses.
    static_cast<void>(fresh.release());
    auto staged = std::unique_ptr<StagedRoll>(new StagedRoll(player, item));
    std::uint64_t const itemGuid = item->GetGUID().GetCounter();
    transaction->Append("DELETE FROM dc_item_affix WHERE item_guid={}", itemGuid);
    transaction->Append("DELETE FROM dc_item_instance WHERE item_guid={}", itemGuid);
    transaction->Append(
        "INSERT INTO dc_item_instance (item_guid, base_item, quality_tier, rarity) VALUES ({}, {}, '{}', '{}')",
        itemGuid, baseItemId, qualityTier, Escape(base.rarity.empty() ? "rare" : base.rarity));
    for (Affix const& affix : rolled)
        transaction->Append(
            "INSERT INTO dc_item_affix (item_guid, seq, affix_id, value, range_min, range_max, value2, "
            "range_min2, range_max2, kind, rerolled) "
            "VALUES ({}, {}, '{}', {}, {}, {}, {}, {}, {}, '{}', 0)",
            itemGuid, affix.seq, Escape(affix.affixId), affix.value, affix.rangeMin, affix.rangeMax, affix.value2,
            affix.rangeMin2, affix.rangeMax2, Escape(affix.kind));
    LOG_DEBUG("server.loading", "[DC items] Staged {} (entry {}, guid {}, ilvl {}) with {} affixes for {}",
              base.name, baseItemId, itemGuid, itemLevel, rolled.size(), player->GetName());
    return staged;
}

Item* RollItem(Player* player, std::uint32_t baseItemId, unsigned itemLevel, std::string const& rarity,
               std::string const& rollClass, std::string const& quality)
{
    auto transaction = CharacterDatabase.BeginTransaction();
    auto staged = StageRoll(player, baseItemId, itemLevel, rarity, transaction, rollClass, quality);
    if (!staged || !CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
        return nullptr;
    // Preserve immediate callers: affix rows exist before they equip/read back.
    return staged->Publish();
}

std::string RollQuality(Player* player, std::uint32_t baseItemId, unsigned itemLevel, unsigned tier, bool gambled)
{
    std::string rarity;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        auto found = baseItems.find(baseItemId);
        // A Bottomless potion is never Ancient (StageRoll).
        if (found == baseItems.end() || found->second.slot == "potion")
            return "normal";
        // A follower relic is Legendary only until the switch (followers_relic_rules.csv relic_ancient_primal) says otherwise.
        if (!DC::Relic::MayBeAncient({found->second.relicPrimary, found->second.relicSecondary}, relicAncientPrimal))
            return "normal";
        rarity = found->second.rarity;
    }
    if (!DC::Quality::Eligible(rarity) || !player)
        return "normal";
    {
        std::lock_guard<std::mutex> lock(forceMutex);
        auto forced = forcedQuality.find(player->GetGUID().GetRawValue());
        if (forced != forcedQuality.end())
            return forced->second;
    }
    std::uniform_real_distribution<double> distribution(0.0, 1.0);
    return DC::Quality::Decide(rarity, QualityRule(), tier ? tier : DC::Difficulty::CurrentTier(player), itemLevel,
                               PrimalUnlocked(player), distribution(Engine()), gambled);
}
}
