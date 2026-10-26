/*
 * World of DiabloCraft - items (05-items §2-§6).
 *
 * Public surface of the items folder. Other folders include only this header.
 */

#ifndef DC_ITEMS_H
#define DC_ITEMS_H

#include <cstdint>
#include <optional>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>
#include "DatabaseEnv.h"

class Creature;
class Item;
class Player;
struct ItemTemplate;

namespace DC::Items
{
// One rolled affix row of dc_item_affix, in display order.
struct Affix
{
    unsigned seq = 0;
    std::string affixId;      // dc_affix_pool.affix_id, or dc_gem.gem_id on a gem row
    std::string name;         // resolved display name, empty when the pool has none
    double value = 0, rangeMin = 0, rangeMax = 0;
    std::string kind;         // primary | secondary | socket | gem | preset | power | passive
    bool isPercent = false;
    bool rerolled = false;
    int parentSeq = -1;
    std::uint32_t gemEntry = 0;
    unsigned gemRank = 0;
    // G1: a weapon elemental affix, and jewelry's Physical Damage, roll two numbers (D3 Min +
    // Delta), as does any pool row with a second range. value2 is the second
    // endpoint (max = value + delta), range_min2/range_max2 the second bracket [c,d] it was
    // rolled in. A single-part affix keeps all three at 0. Kept last so the positional aggregate
    // initialisers above stay valid.
    double value2 = 0, rangeMin2 = 0, rangeMax2 = 0;
    // The rank of a socketed legendary gem (dc_item_affix.legendary_rank); empty on every other row.
    // Not gemRank, which is a normal gem's tier.
    std::optional<std::uint32_t> legendaryRank;
};

// One rolled item instance: dc_item_instance plus its dc_item_affix rows.
struct Instance
{
    std::uint64_t itemGuid = 0;
    std::uint32_t baseItem = 0;
    std::string qualityTier = "normal";
    std::string rarity;
    bool enchantLocked = false, crafted = false;
    unsigned enchantAttempts = 0, boundAccount = 0;
    std::vector<Affix> affixes;
};

// Rolls a new item into the player's bags and writes its rows (05 §3). Returns
// nullptr when the base item is unknown or the bags are full. itemLevel is
// recorded for the roll but selects nothing yet: the extracted ranges are
// level-70 only, bracketed by quality rather than by item level.
// rollClass is the dc_class_map class_key the drop rolled for (loot rule 1);
// empty means the player's own class. A class-only base ignores it and rolls
// its own class (dc_roll_class.h AffixClass).
Item* RollItem(Player* player, std::uint32_t baseItemId, unsigned itemLevel, std::string const& rarity = "",
               std::string const& rollClass = "", std::string const& quality = "");

// A fresh unstackable roll reserved in inventory without publishing a reward.
// StageRoll appends affix rows to the caller's transaction, never commits it.
// The caller saves inventory and payment into that same transaction, waits for
// durable success, then calls Publish. On failure discard the transaction;
// destroying the staged roll removes its unpublished in-memory item, with no SQL.
// Keep this object on the player's thread and within the synchronous operation.
class StagedRoll
{
public:
    ~StagedRoll();
    StagedRoll(StagedRoll const&) = delete;
    StagedRoll& operator=(StagedRoll const&) = delete;
    Item* GetItem() const
    {
        return item_;
    }
    Item* Publish();

private:
    friend std::unique_ptr<StagedRoll> StageRoll(Player*, std::uint32_t, unsigned, std::string const&,
                                                 CharacterDatabaseTransaction const&, std::string const&,
                                                 std::string const&, std::string const&);
    StagedRoll(Player* player, Item* item)
        : player_(player)
        , item_(item)
    {
    }
    Player* player_;
    Item* item_;
    bool published_ = false;
};
std::unique_ptr<StagedRoll> StageRoll(Player* player, std::uint32_t baseItemId, unsigned itemLevel,
                                      std::string const& rarity, CharacterDatabaseTransaction const& transaction,
                                      std::string const& rollClass = "", std::string const& quality = "",
                                      std::string const& mainStat = "");

// The quality tier ("normal" | "ancient" | "primal") of a drop, decided ONCE at the drop
// so the beam can show it and identify can roll inside its bracket. Anything but a Legendary or Set base is
// "normal"; so is a drop under loot/ancient_min_tier or loot/ancient_min_item_level; a Primal also needs the
// player's account to have beaten a solo Greater Rift loot/primal_unlock_solo_gr in this mode. `tier` 0 means
// the player's current difficulty tier. A GM's `.dc quality force` overrides the whole decision.
// StageRoll's `quality` argument: "" decides here (Kadala, the set cache, crafting), anything else is the
// quality already decided at the drop (identify passes the shell's).
// `gambled` is a Kadala gamble, a slot vendor sale, a Kanai's Cube roll or an artisan craft: it reads
// loot/ancient_min_tier_gamble (level 70 on any difficulty, D3) instead of ancient_min_tier.
// StageRoll's "" leaves it false: the set and bounty caches, like a monster drop, keep the Torment I gate.
std::string RollQuality(Player* player, std::uint32_t baseItemId, unsigned itemLevel, unsigned tier = 0,
                        bool gambled = false);

// The roller's planning step, with no Player, no RNG and no writes. Given the slot's bracket
// pools already split by kind (and already filtered by BlockAffix and by skill-group emptiness
// for affixClass), the base's presets, whether the base is a shield and the rarity's budget, it
// decides which fixed affixes the roll takes, in take order, and how many random affixes of each
// kind the fill takes. StageRoll calls it, so the roll and the Blacksmith preview cannot drift.
struct PoolEntry
{
    std::string affixId, name, kind, bracket;
    double min = 0, max = 0;
    // G1: the second endpoint bracket [c,d] of a weapon elemental affix (value_min2/value_max2);
    // 0 for a single-part affix. weaponClass names which 1H/2H damage bracket the row carries
    // (damage1HNormal / damage1HFast / damage2H), empty for every non-weapon affix.
    double min2 = 0, max2 = 0;
    std::string weaponClass;
    // Issue #56: the sourced roll step (affix_pools.csv value_step); 0 where the source gives none.
    double step = 0;
    bool isPercent = false;
    // dc_affix_pool.display_order: the tooltip's order, which the Mystic's window follows.
    unsigned order = 0;
};
struct Counts
{
    unsigned primary = 0, secondary = 0;
};
struct RollPlanFixed
{
    PoolEntry entry;
    bool counted = true;   // false: a required line (a shield's block, an offhand's damage, a quiver's speed), outside the affix budget
    bool socket = false;   // the roll expands it into RollValue(entry) socket rows
    bool skill = false;    // the roll resolves it to a group choice for affixClass
};
struct RollPlanInput
{
    std::vector<PoolEntry> primary;        // the slot's bracket pool, non-secondary kind
    std::vector<PoolEntry> secondary;
    std::vector<std::string> presets;      // base.presets, in order; one outside the pool and itemPresets is skipped
    bool shield = false;                   // base.type is Shield or Crusader Shield
    bool damageOffhand = false;            // base.type is Source, Mojo or Phylactery (wpnphy is required)
    bool speedQuiver = false;              // base.type is Quiver (ias is required)
    Counts counts;                         // CountsFor(rarity)
    std::vector<std::string> skillGroups;  // the ids whose choices were resolved for affixClass
    // The item's own ranges (dc_item_preset_range) for presets its slot's pool lacks;
    // taken only as a preset, never by the fill.
    std::vector<PoolEntry> itemPresets;
};
struct RollPlan
{
    std::vector<RollPlanFixed> fixed;      // in take order
    unsigned randomPrimary = 0;            // the fill takes exactly this many
    unsigned randomSecondary = 0;
};
RollPlan PlanRoll(RollPlanInput const& input);

// The legendary slot vendors' buy hook (dc_slot_vendor.cpp), registered with the item scripts.
void RegisterSlotVendorScripts();

// The set caches' open hook (dc_set_cache.cpp), registered with the item scripts.
void RegisterSetCacheScripts();

// The dc_class_map class_key a WoW class plays, "" for a class with no catalogue.
std::string ClassKeyOf(unsigned wowClass);

// Reads back the rows for one item guid; nullopt when the item was never rolled.
std::optional<Instance> Get(std::uint64_t itemGuid);

// Artisan mutations remove the old contribution before updating rows, then
// reapply only if equipped. All stat work stays in C++.
void RemoveContributions(Player* player, Item* item);
void RefreshContributions(Player* player, Item* item);
void DestroyWithRows(Player* player, Item* item, CharacterDatabaseTransaction const& transaction);
// Kanai's Cube's made-by mark (dc_made_rule.h): the 3.3.5 creator field (the client's own
// "<Made by Name>", kept by the core and by the stash) and the maker's name on the item's record (dc_item_instance.made_by,
// which the tooltip draws, so it outlives a deleted maker). The name's row goes into `transaction`; the field is saved with
// the item. `owner` holds the item.
void MarkMade(Player* owner, Item* item, Player* maker, CharacterDatabaseTransaction const& transaction);

// The free bag slots every one of `items` can go into (dc_set_cache.cpp): the backpack, and each bag
// the core lets every item into. A cache counts its room with this before it destroys itself.
unsigned FreeSlotsFor(Player* player, std::vector<ItemTemplate const*> const& items);

// Kanai's Cube's powers that are item affixes: puts the stat rows of the cubed powers (ItemPowers::ActivePowers
// from the Cube, never a worn copy) on the sheet at the top of their range, and takes off what an earlier call put. Called after
// every change of the Cube list (the Archive's choose and login load) and by Apply on every equip and unequip.
void RefreshCubedStats(Player* player);

// The Mystic (the rules are dc_enchant_rule.h). One line of an item as the window
// lists it: the affix (kind is its pool, primary or secondary, or socket; value2 and the min2/max2
// range only on a two-part damage line; the sockets are ONE line whose value is their count) and
// Enchant::State as an int (0 open, 1 enchanted, 2 gems in the sockets, 3 nothing else it could become).
struct EnchantLine
{
    Affix affix;
    int state = 0;
};
// Every line the window may list, in tooltip order; an enchant-locked item lists only its one line.
std::vector<EnchantLine> EnchantLines(Player* player, Instance const& item);
// The two new choices for the line at `seq`, each rolled fresh; empty when the line cannot be enchanted.
// Writes nothing: the caller stores them.
std::vector<Affix> EnchantOptions(Player* player, Instance const& item, unsigned seq);
// What the `?` shows: every property the line can become, with the range it would roll in (value 0).
std::vector<Affix> EnchantPreview(Player* player, Instance const& item, unsigned seq);
// G1: the extra damage the equipped item adds to each swing, cached per item so combat never
// reads the database: the socketed gem's flat damage on both endpoints plus the rolled weapon
// elemental range (value2 to high, value to low). Zero for an item with neither.
struct WeaponExtraDamage
{
    double low = 0, high = 0;
};
WeaponExtraDamage WeaponExtraDamageOf(std::uint64_t playerGuid, std::uint64_t itemGuid);

// Hellfire Amulet: `chosen` plus the class passives the player's worn, unbroken items grant, each once
// (a granted copy of a chosen passive adds nothing). Cached per worn item: no database read. Passives::Has is the reader.
std::vector<std::string> WithGrantedPassives(Player const* player, std::vector<std::string> chosen);

// Cached equipped-item skill percentage for combat step 4; no DB reads per hit.
// K5: the base skill's spell id, not its name.
double SkillDamageBonus(std::uint64_t playerGuid, std::uint32_t skillId);

// One unidentified shell: the drop context the roller will need, held until the
// player identifies it. The item deliberately has no
// Instance and no affix rows until then.
struct Unidentified
{
    std::uint64_t itemGuid = 0;
    std::uint32_t baseItem = 0;
    unsigned itemLevel = 0;
    std::string rarity;        // legendary | set
    std::string qualityTier = "normal"; // normal | ancient | primal, decided at the drop
    std::string dropSource;    // dc_loot_tuning.source the drop came from
    unsigned tier = 1;
    std::uint64_t ownerGuid = 0;
    // The class the drop rolled for (loot rule 4); "" on a row written before
    // roll classes were stored.
    std::string rollClass;
};

// The unidentified row for an item guid; nullopt when the item is not a shell.
// This is the mirror of Get(): exactly one of the two ever answers for an item.
std::optional<Unidentified> GetUnidentified(std::uint64_t itemGuid);

// True for the generic shell templates, so callers can recognise one without a
// database round trip.
bool IsUnidentifiedTemplate(std::uint32_t entry);

// Destroys a shell and its unidentified row together, in the caller's
// transaction. Salvage uses it; identification uses its own path.
void DestroyShell(Player* player, Item* item, CharacterDatabaseTransaction const& transaction);

// The two identify shells generate_spells.py emits.
// Exposed so the loot folder can find the shell templates by their use spell
// rather than by an entry range it would have to keep in step with.
std::uint32_t IdentifyItemSpell();
std::uint32_t IdentifyTomeSpell();

// --- legendary gems as items (docs/contracts/legendary-gems.md) ---
// One gem item per instance, with its own rank in dc_legendary_gem_rank (by item guid). Socketed, it is a
// dc_item_affix row of kind 'gem' with gem_entry the item's entry and legendary_rank its rank.
struct LegendaryGemItem
{
    std::string gemId;        // Unique_Gem_NNN_x1, the key of dc_legendary_gem (src/common/dc_legendary_gem.h)
    std::string socketSlots;  // the base-item slots it may be socketed into, '|' joined
};
// nullopt when the entry is not one of the 21 legendary gem templates.
std::optional<LegendaryGemItem> LegendaryGemItemOf(std::uint32_t entry);
// The legendary gem entries this character does not own yet, sorted: not in its bags, bank or worn
// items, not socketed in any of them, and not in its account stash (same Normal or Hardcore mode).
// Empty when it owns all 21. It is what a Greater Rift Guardian may drop.
std::vector<std::uint32_t> UnownedLegendaryGems(Player* player);
// The rank of one gem item; 0 when it has no row (a gem that never got one starts at rank 0).
std::uint32_t LegendaryGemRankOf(std::uint64_t itemGuid);
// True when the rolled item's base slot is one the gem may be socketed into.
bool LegendaryGemFits(std::uint32_t baseItem, LegendaryGemItem const& gem);
// A new gem item of that rank in the bags, its rank row appended to the caller's transaction (the
// caller saves the inventory into the same transaction). nullptr when there is no room: check room first.
Item* GiveLegendaryGem(Player* player, std::uint32_t entry, std::uint32_t rank,
                       CharacterDatabaseTransaction const& transaction);
// The one INSERT of a socketed gem's row, normal or legendary (legendaryRank empty for a normal gem).
void AppendGemRow(CharacterDatabaseTransaction const& transaction, std::uint64_t itemGuid, unsigned seq,
                  std::string const& gemId, unsigned parentSeq, std::uint32_t gemEntry, unsigned gemRank,
                  std::optional<std::uint32_t> legendaryRank);
// The legendary gems whose powers apply to this character, one per gem (Unique
// Equipped), read from the gems socketed on what is worn. Sorted by gem_id; the rank is the gem's own.
struct CountedLegendaryGem
{
    std::string gemId;
    std::uint32_t rank = 0;
};
std::vector<CountedLegendaryGem> CountedLegendaryGems(Player* player);
// Unique Equipped: the worn item that holds a legendary gem of this id and is not about
// to go, nullptr when none does. `leaving` are the guids of worn items being taken off; `replaced` is the
// (item guid, affix seq) of the socket a swap empties. See DC::LegendaryGemItem::WornCopy.
Item* WornLegendaryGem(Player* player, std::string const& gemId, std::vector<std::uint64_t> const& leaving = {},
                       std::optional<std::pair<std::uint64_t, unsigned>> replaced = std::nullopt);
// The name of a legendary gem, for a refusal's words (its gem_id when the table has none).
std::string LegendaryGemName(std::string const& gemId);

// --- followers' gear (docs/contracts/followers.md; follower ids are Campaign::Followers::Id) ---
namespace FollowerGear
{
void RegisterScripts();
// A follower's companion stands beside its player: it takes the life, armor, resistances and swing of that follower's gear.
void OnCompanionSummoned(Player* player, Creature* companion, unsigned follower);
// Whether `follower` wears a relic of this power (data/d3/followers.csv power: cannot_die, all_skills, cooldown_half).
bool HasPower(Player const* player, unsigned follower, std::string_view power);
// Whether the hired follower wears a relic that keeps it from dying.
bool CannotDie(Player const* player);
// The hub's follower, or the companion beside its player, was talked to: push the Follower window's records for `follower`
// (the DCFOLLOWER open reply, with no request), and the window opens on the first.
void OpenWindow(Player* player, unsigned follower);
// What a follower's skills read of its sheet: its main stat (the number the skills scale with), its level, one swing's range (0 for a
// follower with no weapon) and its critical hit chance and damage. False when the follower has no sheet (the gear data is not loaded).
struct SkillStats
{
    double mainStat = 0;
    double swingMin = 0;
    double swingMax = 0;
    double critChance = 0; // percent
    double critDamage = 0; // percent: the multiplier of a critical hit is one plus this over a hundred
    unsigned level = 0;
};
bool SkillStatsOf(Player const* player, unsigned follower, SkillStats& out);
}

void RegisterScripts();
}

#endif // DC_ITEMS_H
