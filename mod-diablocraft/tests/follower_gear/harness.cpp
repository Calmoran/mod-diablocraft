// The follower gear rules (src/items/dc_follower_gear_rule.h) compiled with the real dc_common.cpp and driven with the sheets'
// own values. Arguments: the kinds file (one `follower slot itemSlot itemType` line per row of data/d3/followers_gear.csv),
// the three rules of followers_gear_rules.csv (main stat multiplier, crit damage cap, player share), then name=value pairs
// for every numeric rule dc_common.cpp asks the world for (data/generated/numeric_rules_0001.sql).
#include "../../src/common/dc_common.h"
#include "../../src/common/dc_numeric_data.h"
#include "../../src/items/dc_follower_gear_rule.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>

using namespace DC;
namespace G = DC::Items::FollowerGear;

static std::map<std::string, double> numeric;

namespace DC::NumericData
{
double Rule(char const* name)
{
    auto found = numeric.find(name);
    if (found == numeric.end())
        throw std::logic_error(std::string("no numeric rule ") + name);
    return found->second;
}
unsigned MaximumLevel() { return 70; }
double BaseFury(unsigned) { return 0; }
BlockTuning Block() { return BlockTuning{75, 75, 1}; }
}

static int failures = 0;
static void Check(bool ok, char const* what)
{
    if (!ok)
    {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", what);
    }
}

static bool Near(double a, double b, double tolerance)
{
    return std::fabs(a - b) <= tolerance;
}

enum { Templar = 1, Scoundrel = 2, Enchantress = 3 };

static G::Offered Base(char const* slot, char const* type)
{
    G::Offered item;
    item.itemSlot = slot;
    item.itemType = type;
    return item;
}

static G::Offered Relic(unsigned follower)
{
    G::Offered item;
    item.relic = true;
    item.relicFollower = follower;
    return item;
}

static StatSheet Calc(BaseStats const& base, std::vector<Contribution> const& gear)
{
    return DC::Calculate(base, gear);
}

static Contribution Gear(Stat stat, double value, Bucket bucket = Bucket::Flat, std::uint64_t id = 1)
{
    Contribution c;
    c.source = Source::Items;
    c.stat = stat;
    c.id = id;
    c.value = value;
    c.bucket = bucket;
    return c;
}

int main(int argc, char** argv)
{
    if (argc < 5)
        return 2;
    std::vector<G::Kind> kinds;
    {
        std::ifstream in(argv[1]);
        std::string line;
        while (std::getline(in, line))
        {
            std::istringstream fields(line);
            unsigned follower;
            std::string slot, itemSlot, itemType;
            fields >> follower >> slot >> itemSlot;
            std::getline(fields >> std::ws, itemType);
            auto parsed = G::SlotOf(slot);
            if (!parsed)
                return 3;
            kinds.push_back({follower, *parsed, itemSlot, itemType});
        }
    }
    G::StatRules rules;
    rules.mainStatMultiplier = std::atof(argv[2]);
    rules.critDamageCap = std::atof(argv[3]);
    rules.playerSharePct = std::atof(argv[4]);
    for (int index = 5; index < argc; ++index)
    {
        std::string pair = argv[index];
        auto eq = pair.find('=');
        numeric[pair.substr(0, eq)] = std::atof(pair.c_str() + eq + 1);
    }
    Check(G::Usable(rules), "the sheet's rules are usable");
    Check(!G::Usable(G::StatRules{}), "a zero rule is refused");
    Check(!kinds.empty(), "the kinds sheet has rows");
    Check(G::SlotCount == 14, "a follower has fourteen slots");
    for (unsigned index = 0; index < G::SlotCount; ++index)
        Check(G::SlotOf(G::KeyOf(G::Slot(index))) == G::Slot(index), "every slot key reads back to its slot");
    Check(!G::SlotOf("cloak"), "an unknown slot key is nothing");

    G::Held none;
    auto place = [&](unsigned follower, G::Offered const& item, std::optional<G::Slot> wanted = std::nullopt,
                     G::Held held = G::Held{}) { return G::Place(follower, item, kinds, wanted, held); };

    // Weapon kinds per follower (R1a section 4).
    Check(place(Templar, Base("onehand", "Sword")).slot == G::Slot::MainHand && place(Templar, Base("onehand", "Sword")).refusal == G::Refusal::None,
          "the Templar wields a one-handed sword");
    for (char const* type : {"Axe", "Dagger", "Mace", "Spear", "Sword"})
        Check(place(Templar, Base("onehand", type)).refusal == G::Refusal::None, "the Templar wields every one-handed kind");
    Check(place(Templar, Base("offhand", "Shield")).slot == G::Slot::OffHand, "the Templar's shield goes in the off-hand");
    Check(place(Templar, Base("offhand", "Crusader Shield")).refusal == G::Refusal::WrongKind, "not a Crusader's shield");
    Check(place(Templar, Base("twohand", "Two-Handed Sword")).refusal == G::Refusal::WrongKind, "the Templar has no two-hander");
    Check(place(Templar, Base("twohand", "Bow")).refusal == G::Refusal::WrongKind, "the Templar draws no bow");
    Check(place(Templar, Base("onehand", "Fist Weapon")).refusal == G::Refusal::WrongKind, "no Monk weapon on the Templar");
    Check(place(Scoundrel, Base("twohand", "Bow")).slot == G::Slot::MainHand, "the Scoundrel draws a bow");
    Check(place(Scoundrel, Base("twohand", "Crossbow")).refusal == G::Refusal::None, "the Scoundrel fires a crossbow");
    Check(place(Scoundrel, Base("onehand", "Hand Crossbow")).refusal == G::Refusal::WrongKind, "never a hand crossbow");
    Check(place(Scoundrel, Base("onehand", "Sword")).refusal == G::Refusal::WrongKind, "the Scoundrel swings no sword");
    Check(place(Scoundrel, Base("offhand", "Shield")).refusal == G::Refusal::WrongKind, "the Scoundrel has no off-hand");
    Check(place(Enchantress, Base("twohand", "Staff")).slot == G::Slot::MainHand, "the Enchantress wields a staff");
    Check(place(Enchantress, Base("twohand", "Two-Handed Mace")).refusal == G::Refusal::None, "and a two-handed mace");
    Check(place(Enchantress, Base("onehand", "Dagger")).refusal == G::Refusal::None, "and a one-handed dagger (R1a)");
    Check(place(Enchantress, Base("twohand", "Polearm")).refusal == G::Refusal::WrongKind, "never a polearm");
    Check(place(Enchantress, Base("offhand", "Shield")).refusal == G::Refusal::WrongKind, "the Enchantress has no off-hand");
    Check(place(Enchantress, Base("twohand", "Bow")).refusal == G::Refusal::WrongKind, "the Enchantress draws no bow");

    // Armour: every follower wears the open kinds, none of a class's own.
    for (unsigned follower : {Templar, Scoundrel, Enchantress})
    {
        Check(place(follower, Base("head", "Helm")).slot == G::Slot::Head, "a helm goes on the head");
        Check(place(follower, Base("head", "Wizard Hat")).refusal == G::Refusal::WrongKind, "not a Wizard Hat");
        Check(place(follower, Base("head", "Voodoo Mask")).refusal == G::Refusal::WrongKind, "not a Voodoo Mask");
        Check(place(follower, Base("head", "Spirit Stone")).refusal == G::Refusal::WrongKind, "not a Spirit Stone");
        Check(place(follower, Base("waist", "Mighty Belt")).refusal == G::Refusal::WrongKind, "not a Mighty Belt");
        Check(place(follower, Base("torso", "Cloak")).refusal == G::Refusal::WrongKind, "not a Cloak");
        Check(place(follower, Base("torso", "Chest Armor")).slot == G::Slot::Chest, "chest armour goes on the chest");
        Check(place(follower, Base("hands", "Gloves")).slot == G::Slot::Gloves, "gloves");
        Check(place(follower, Base("wrists", "Bracers")).slot == G::Slot::Bracers, "bracers");
        Check(place(follower, Base("waist", "Belt")).slot == G::Slot::Belt, "a belt");
        Check(place(follower, Base("legs", "Pants")).slot == G::Slot::Pants, "pants");
        Check(place(follower, Base("feet", "Boots")).slot == G::Slot::Boots, "boots");
        Check(place(follower, Base("shoulders", "Shoulders")).slot == G::Slot::Shoulders, "shoulders");
        Check(place(follower, Base("neck", "Amulet")).slot == G::Slot::Neck, "an amulet goes on the neck");
        G::Offered classLegendary = Base("feet", "Boots");
        classLegendary.classBound = true;
        Check(place(follower, classLegendary).refusal == G::Refusal::ClassItem, "an item of a class's own is refused");
    }
    // Two rings: the first free, then the second; both full replaces the first; a named slot is kept.
    {
        G::Offered ring = Base("finger", "Ring");
        Check(place(Templar, ring).slot == G::Slot::Ring1, "the first ring goes in the first ring slot");
        Check(place(Templar, ring, std::nullopt, G::Held{G::Bit(G::Slot::Ring1), false}).slot == G::Slot::Ring2,
              "the second ring goes in the second");
        Check(place(Templar, ring, std::nullopt, G::Held{G::Bit(G::Slot::Ring1) | G::Bit(G::Slot::Ring2), false}).slot == G::Slot::Ring1,
              "with both full the first is replaced");
        Check(place(Templar, ring, G::Slot::Ring2).slot == G::Slot::Ring2, "a ring dropped on the second slot stays there");
        Check(place(Templar, ring, G::Slot::Head).refusal == G::Refusal::WrongKind, "a ring does not go on the head");
    }
    // Relics: the relic slot, the item's own follower only.
    Check(place(Templar, Relic(Templar)).slot == G::Slot::Relic, "a Templar relic goes in the relic slot");
    Check(place(Scoundrel, Relic(Templar)).refusal == G::Refusal::WrongFollower, "a relic of another follower is refused");
    Check(place(Enchantress, Relic(Enchantress), G::Slot::Head).refusal == G::Refusal::WrongKind, "a relic fits no other slot");
    // Hands: a two-hander wants the off-hand empty, a shield wants no two-hander in the main hand.
    Check(place(Enchantress, Base("twohand", "Staff"), std::nullopt, G::Held{G::Bit(G::Slot::OffHand), false}).refusal == G::Refusal::HandBusy,
          "a two-hander with a full off-hand is refused");
    Check(place(Templar, Base("offhand", "Shield"), std::nullopt, G::Held{G::Bit(G::Slot::MainHand), true}).refusal == G::Refusal::HandBusy,
          "a shield with a two-hander in the main hand is refused");

    // The follower's sheet: gear counts its attribute points 2.5 times, takes none from the player, and caps crit damage.
    BaseStats base;
    base.level = 70;
    base.baseLife = 9000;
    base.lifePerVitality = 100;
    base.classDRPct = 0;
    base.allResPerInt = numeric.at("all_res_per_int");
    base.mainStat = Stat::Strength;
    {
        Check(G::OnFollower(Gear(Stat::Strength, 100), rules) == 100 * rules.mainStatMultiplier, "strength counts the multiplier");
        Check(G::OnFollower(Gear(Stat::Dexterity, 100), rules) == 100 * rules.mainStatMultiplier, "dexterity counts the multiplier");
        Check(G::OnFollower(Gear(Stat::Intelligence, 100), rules) == 100 * rules.mainStatMultiplier, "intelligence counts the multiplier");
        Check(G::OnFollower(Gear(Stat::Vitality, 100), rules) == 100 * rules.mainStatMultiplier, "vitality counts the multiplier");
        Check(G::OnFollower(Gear(Stat::Strength, 10, Bucket::Percent), rules) == 10, "a percent bonus to strength is not points");
        Check(G::OnFollower(Gear(Stat::CritChance, 5), rules) == 5, "crit chance counts as rolled");
        Check(G::OnFollower(Gear(Stat::Armor, 700), rules) == 700, "armor counts as rolled");

        StatSheet empty = G::Sheet(base, {}, rules, Calc);
        Check(empty[Stat::Strength] == 0 && empty[Stat::Vitality] == 0, "a follower with no gear has no attributes of its own");
        Check(empty.maxLife == 9000, "and its stock life");

        StatSheet sheet = G::Sheet(base, {Gear(Stat::Strength, 1000), Gear(Stat::Vitality, 400, Bucket::Flat, 2), Gear(Stat::Armor, 300, Bucket::Flat, 3)}, rules, Calc);
        Check(Near(sheet[Stat::Strength], 1000 * rules.mainStatMultiplier, 1e-9), "1000 strength on gear is 2.5 times on the sheet");
        Check(Near(sheet.maxLife, std::floor(9000 + 400 * rules.mainStatMultiplier * 100), 1e-9), "vitality makes life at the player's rate per point");
        Check(Near(sheet[Stat::Armor], 300 + 1000 * rules.mainStatMultiplier, 1e-9), "strength makes armor as it does for a player");

        StatSheet over = G::Sheet(base, {Gear(Stat::CritDamage, 500)}, rules, Calc);
        Check(over[Stat::CritDamage] == rules.critDamageCap, "crit damage stops at the cap");
        StatSheet under = G::Sheet(base, {Gear(Stat::CritDamage, 20)}, rules, Calc);
        Check(Near(under[Stat::CritDamage], numeric.at("crit_damage_pct") + 20, 1e-9) && under[Stat::CritDamage] < rules.critDamageCap,
              "below the cap it is the sheet's");
        StatSheet intelligent = G::Sheet(base, {Gear(Stat::Intelligence, 400)}, rules, Calc);
        Check(Near(intelligent[Stat::AllResistance], 400 * rules.mainStatMultiplier * base.allResPerInt, 1e-9),
              "intelligence makes resistance to all");
    }
    Check(G::Shared(500, rules) == 500 * rules.playerSharePct / 100.0, "a share of the follower's find stats");

    // The creature: the core's armor and resistance give the sheet's reductions; one swing; the period.
    {
        StatSheet sheet = G::Sheet(base, {Gear(Stat::Strength, 400), Gear(Stat::Armor, 5000), Gear(Stat::Intelligence, 200),
                                          Gear(Stat::Vitality, 300), Gear(Stat::WeaponFlatDamage, 40, Bucket::Flat, 7),
                                          Gear(Stat::WeaponFlatDamageDelta, 20, Bucket::Flat, 8), Gear(Stat::WeaponAPS, 1.4, Bucket::Flat, 9), Gear(Stat::AttackSpeed, 20, Bucket::Flat, 10)},
                                   rules, Calc);
        G::Weapon sword;
        sword.present = true;
        sword.min = 100;
        sword.max = 200;
        sword.delayMs = 1000 / 1.4;
        G::CreaturePlan plan = G::Plan(sheet, Stat::Strength, 70, sword);
        Check(plan.maxHealth == std::uint32_t(sheet.maxLife), "the creature takes the sheet's life");
        double const armorConstant = G::CoreArmorConstant(70);
        Check(Near(plan.armor / (plan.armor + armorConstant), sheet.armorDR, 1e-4), "the core's armor gives the sheet's reduction");
        Check(Near(armorConstant, 85.0 * (70 + 4.5 * 11) + 400, 1e-9), "the core's armor constant at level 70");
        double const resistConstant = G::CoreResistConstant(70);
        Check(Near(resistConstant, 175, 1e-9), "the core's resistance constant at level 70");
        Check(plan.resistance[0] == 0, "physical is armor, not a resistance");
        for (unsigned element = 1; element < ElementCount; ++element)
        {
            unsigned const school = G::SchoolOfElement[element];
            double const got = plan.resistance[school] / (plan.resistance[school] + resistConstant);
            Check(Near(got, sheet.resistanceDR[element], 1e-4), "the core's resistance gives the sheet's reduction in each school");
        }
        Check(plan.resistance[2] == plan.resistance[3] && plan.resistance[4] == plan.resistance[5], "all resistance lands on every school");
        Check(plan.swings, "a weapon makes a swing");
        double const main = 1 + sheet[Stat::Strength] / 100.0;
        Check(Near(plan.swingMin, (100 + 40) * main, 1e-6), "a swing's low end is the weapon plus flat damage, times the main stat");
        Check(Near(plan.swingMax, (200 + 40 + 20) * main, 1e-6), "and its high end adds the flat delta");
        Check(Near(sheet.attacksPerSecond, 1.4 * 1.2, 1e-9), "attack speed from gear quickens the weapon");
        Check(plan.attackTimeMs == std::uint32_t(std::lround(1000.0 / sheet.attacksPerSecond)), "the period is the sheet's attacks per second");
        Check(Near(G::CoreWeaponDamage(plan.swingMin, plan.attackTimeMs) * plan.attackTimeMs / 1000.0, plan.swingMin, 1e-6),
              "the core's weapon damage times the period is one swing");
        G::CreaturePlan bare = G::Plan(sheet, Stat::Strength, 70, G::Weapon{});
        Check(!bare.swings, "with no weapon the creature keeps its own damage");
        // The cap: a huge armor does not give the core more than three quarters.
        StatSheet armoured = G::Sheet(base, {Gear(Stat::Armor, 1e9)}, rules, Calc);
        G::CreaturePlan capped = G::Plan(armoured, Stat::Strength, 70, G::Weapon{});
        Check(Near(capped.armor / (capped.armor + armorConstant), G::CoreReductionCap, 1e-4), "the core's reduction stops at three quarters");
    }
    // A relic that keeps the follower from dying takes no damage.
    Check(G::Taken(true, 5000) == 0 && G::Taken(false, 5000) == 5000, "cannot die: no damage; otherwise all of it");
    Check(G::PowerCannotDie == "cannot_die" && G::PowerAllSkills == "all_skills" && G::PowerCooldownHalf == "cooldown_half", "the relic power names");
    return failures ? 1 : 0;
}
