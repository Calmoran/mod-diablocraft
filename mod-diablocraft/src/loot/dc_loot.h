/*
 * World of DiabloCraft - loot (06-loot §2-§5).
 *
 * The roll maths live here as pure inline functions so the offline harness in
 * scripts/tests/loot can exercise them without linking the core, the same way
 * dc_tiers.h works for difficulty.
 */

#ifndef DC_LOOT_H
#define DC_LOOT_H

#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (0.999999): clamp on the drop-count roll; Keeps the roll inside its bucket.

class Player;
class Creature;
class Position;

namespace DC::Kadala { struct SlotFilter; }

namespace DC::Loot
{
enum class Source : unsigned { Normal, Elite, Boss, RiftGuardian, Chest, Count };
enum class Rarity : unsigned { Normal, Magic, Rare, Legendary };

// Stock loot is replaced only for the creature/chest sources served by the D3
// roller. The active open-world tier phase or a live rift supplies the context;
// item, skinning, pickpocketing and other stock stores stay native.
enum class StockSource : unsigned { Other, Creature, Chest };
inline bool SuppressStockLoot(StockSource source, bool openWorld, unsigned phase,
                              unsigned launchTiers, bool liveRift)
{
    return source != StockSource::Other &&
        (liveRift || (openWorld && phase >= 1 && phase <= launchTiers));
}

// Stock group-loot chests have a native open/treasure lock and a loot template.
// Gathering nodes and unlocked resources use the same GO type but fail this gate.
inline bool D3ChestTemplate(bool groupLootRules, bool hasLoot, bool openTreasureLock)
{
    return groupLootRules && hasLoot && openTreasureLock;
}

// One dc_loot_tuning row (06 §3).
//
// Audit rows 47-49: the rarity split used to default to the table's own
// 60/30/10 here. Those defaults were never the numbers in play - the loader
// refuses to start when a source row is missing ("dc_loot_tuning is missing a
// source row", dc_loot.cpp) - so they were a second copy of the table and are
// gone. A zero here means "not loaded yet", not "no drops".
struct Tuning
{
    unsigned dropsMin = 1, dropsMax = 1;
    double legendaryBasePct = 0, normalPct = 0, magicPct = 0, rarePct = 0;
    double chestMultiplier = 1, deathsBreathPct = 0;
};

inline char const* Name(Source source)
{
    switch (source)
    {
        case Source::Normal:       return "normal";
        case Source::Elite:        return "elite";
        case Source::Boss:         return "boss";
        case Source::RiftGuardian: return "rift_guardian";
        case Source::Chest:        return "chest";
        default:                   return "";
    }
}

inline char const* Name(Rarity rarity)
{
    switch (rarity)
    {
        case Rarity::Magic:     return "magic";
        case Rarity::Rare:      return "rare";
        case Rarity::Legendary: return "legendary";
        default:                return "normal";
    }
}

// L2. Only two values on our tier range are published: +25% for Normal-Master
// and +44% for Torment I. Torment II and above are NOT PUBLISHED, so they hold
// at Torment I's value rather than being invented; revisit when the numbers are
// sourced. Tiers 1-4 are Normal, Hard, Expert, Master; 5+ are Torment I upward.
inline double RiftLegendaryBonusPct(unsigned tier)
{
    return tier <= 4 ? 25.0 : 44.0;
}

// 06 §2 step 2. Percentages in, percentage out. magicFind is a fraction, so a
// sheet value of +300% Magic Find arrives here as 3.0; its efficiency against
// legendaries is 10% (drop_rates.csv magic_find).
inline double LegendaryChancePct(Tuning const& tuning, double tierLegendaryBonusPct,
                                 double riftBonusPct, double magicFind)
{
    double chance = tuning.legendaryBasePct
        * (1.0 + tierLegendaryBonusPct / 100.0)
        * (1.0 + riftBonusPct / 100.0)
        * (1.0 + 0.10 * magicFind);
    return std::clamp(chance, 0.0, 100.0);
}

// 06 §2 step 2, the non-legendary split. Magic Find is 100% efficient against
// Magic and 30% against Rare; the mass it adds comes out of Normal, so the three
// weights still sum to the tuning row's total.
inline Rarity PickNonLegendary(Tuning const& tuning, double magicFind, double roll)
{
    double const magic = tuning.magicPct * (1.0 + 1.00 * magicFind);
    double const rare = tuning.rarePct * (1.0 + 0.30 * magicFind);
    double const shifted = (magic - tuning.magicPct) + (rare - tuning.rarePct);
    double const normal = std::max(0.0, tuning.normalPct - shifted);
    double const total = normal + magic + rare;
    if (total <= 0)
        return Rarity::Normal;
    double const point = std::clamp(roll, 0.0, 1.0) * total;
    if (point < normal)
        return Rarity::Normal;
    return point < normal + magic ? Rarity::Magic : Rarity::Rare;
}

// L6 drop count, times the chest multiplier for chests (L11).
inline unsigned DropCount(Tuning const& tuning, Source source, double roll)
{
    unsigned const span = tuning.dropsMax > tuning.dropsMin ? tuning.dropsMax - tuning.dropsMin : 0;
    unsigned count = tuning.dropsMin + static_cast<unsigned>(std::clamp(roll, 0.0, 0.999999) * (span + 1));
    if (source == Source::Chest && tuning.chestMultiplier > 0)
        count = static_cast<unsigned>(count * tuning.chestMultiplier);
    return count;
}

// What a Greater Rift Guardian adds to its kill, by level (built by
// DC::Rifts::GuardianReward). `legendaries` is the average number of legendaries of the level's curve:
// RollLoot pays its whole part and the fraction as the chance of one more, in place of the guaranteed
// first drop and of the ordinary drops' own legendary chance. `goldFactor` multiplies the gold.
// `gems` are the legendary gem entries the character does not own yet; one is dropped, none when empty.
struct GreaterReward
{
    double legendaries = 0, goldFactor = 1;
    std::vector<std::uint32_t> gems;
};

// What one call to RollLoot produced, for the GM command and the logs.
struct Result
{
    unsigned rolled = 0, delivered = 0, buffered = 0, grounded = 0, oncorpse = 0;
    unsigned normal = 0, magic = 0, rare = 0, legendary = 0;
    std::uint32_t gold = 0;
    unsigned deathsBreath = 0;
    bool ok = false;
    bool duplicate = false;      // a receipted reward that already settled
};

// 06 §2. One entry point for kills, chests, and later rifts and Kadala (§5).
// receipt, when a durable reward source supplies one (the rift guardian, 09 F7),
// is that source's stable per-run identifier: a retried or replayed reward whose
// receipt already committed is skipped whole, so the drops, gold, Death's Breath
// and keystone stay paid once. An ordinary kill passes none.
Result RollLoot(Player* player, Source source, unsigned monsterLevel, unsigned tier, bool inRift,
                std::string const& receipt = "", Creature* deathSource = nullptr,
                Position const* dropOrigin = nullptr, GreaterReward const* greater = nullptr);

// One checked delivery of an account material (the five crafting materials and
// the Greater Rift Keystone). With the account economy on this is a receipt-backed
// ledger credit and no bag is involved; with it off the item is stored and any
// part that does not fit is held in dc_loot_buffer rather than discarded.
// receipt must be a stable source identifier for a retryable reward, empty otherwise.
bool GrantMaterial(Player* player, std::uint32_t entry, unsigned count, std::string const& receipt = "");

// Cain's Destiny 3-piece (dc_keystone_rule.h): the extra Greater Rift Keystones a Guardian pays the player along with its one, 0 or 1.
// One roll per call, so call it once for each keystone paid; the caller grants the result under a receipt of its own.
unsigned ExtraKeystones(Player const* player);

// The item the corpse window shows for a corpse row: the unidentified shell for a
// legendary or set drop, the base item for everything else.
std::uint32_t WindowItem(std::uint32_t baseItem, std::string const& contentKind);

// Pays one corpse row to `player` through the pay-once claim (dc_loot_delivery.cpp). False
// means nothing was paid, and storeError says why when the store refused the item:
// it is the core's own InventoryResult (EQUIP_ERR_OK when the row was simply not
// there to claim, so the caller can tell "already looted" from a real refusal).
bool ClaimCorpseRow(Player* player, std::uint64_t rowId, Creature* corpse, std::uint8_t& storeError);

// The base item a drop of this rarity would roll for this class at this level (the unique pool for
// Legendary, the generic one otherwise); 0 when nothing is eligible. filter narrows it to Kadala's slot.
std::uint32_t PickBaseItem(Rarity rarity, unsigned monsterLevel, std::string const& rollClass, unsigned tier = 0,
                           DC::Kadala::SlotFilter const* filter = nullptr);

// Kadala's gamble (kadala.md 4.7): the base a purchase rolls, 0 when the slot has nothing for this class and level.
std::uint32_t PickGamble(DC::Kadala::SlotFilter const& filter, unsigned level, std::string const& rollClass,
                         double legendaryPct);

void RegisterScripts();
// dc_kadala.cpp: the purchase hook on Kadala's entries.
void RegisterKadalaScripts();
}

#endif // DC_LOOT_H
