/*
 * World of DiabloCraft - followers' gear: what each of a character's three followers wears, and the stats it makes.
 *
 * A follower's gear is parked, not worn: the item leaves the bags (its character_inventory row goes) and a row of
 * dc_character_follower_gear holds it by (character, follower, slot), the item_instance row and its rolled rows staying
 * as they were with the character as owner. Each follower keeps its own set; hiring another touches none of them. The
 * equip rule (which kinds go in which of the 14 slots) is dc_follower_gear_rule.h on the rows of dc_follower_gear_kind.
 * A follower takes none of its player's stats: its sheet is the affixes of its own gear on a base with no attributes,
 * the main stats counted 2.5 times, and its creature takes that sheet's life, armor, resistances and swing. A worn
 * relic that keeps it from dying takes the damage it would take. Contract: docs/contracts/followers.md.
 */

#include "dc_items_internal.h"
#include "dc_follower_gear_rule.h"
#include "dc_follower_window.h"
#include "dc_granted_passive_rule.h"

#include "../campaign/dc_campaign.h"
#include "../classes/follower/dc_follower_skills.h"
#include "../common/dc_bridge.h"
#include "../common/dc_numeric_data.h"
#include "../common/dc_world.h"

#include "Bag.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <map>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Items::FollowerGear
{
    namespace
    {
        using Campaign::Followers::Id;
        using Detail::Mappings;

        constexpr unsigned FollowerCount = Campaign::Followers::Count;
        // The find stats a follower shares with its player sit on the player's sheet under ids above every item's.
        constexpr std::uint64_t ShareIdBase = 1ull << 62;
        // A follower's sheet is its own and holds one weapon speed.
        constexpr std::uint64_t WeaponSpeedId = 1, FlatDamageId = 2, FlatDeltaId = 3;
        constexpr std::uint32_t CheckMs = 1000;

        struct Relic
        {
            unsigned follower = 0;
            std::string power;
        };

        struct Data
        {
            bool ready = false;
            std::vector<Kind> kinds;
            std::unordered_map<std::uint32_t, Relic> relics;
            std::unordered_map<std::string, std::string> treatment; // affix id -> ignored | shared
            std::array<std::string, FollowerCount> keys, mainStat;
            std::map<unsigned, double> lifePerVitality; // by level
            std::array<std::vector<unsigned>, FollowerCount> tierLevels; // the D3 level each skill tier opens at
            StatRules rules;
        };

        // Written once at startup, before any player exists, and only read after.
        Data data;

        struct Worn
        {
            std::uint64_t guid = 0;
            std::uint32_t entry = 0;
        };

        using Set = std::array<Worn, SlotCount>;

        struct Computed
        {
            StatSheet sheet;
            Weapon weapon;
            Stat mainStat = Stat::Strength;
            unsigned level = 1;
            std::vector<Contribution> shared; // the follower's own find stats, before the share
        };

        struct State
        {
            std::array<Set, FollowerCount> worn;
            std::array<std::optional<Computed>, FollowerCount> computed;
            // The find-stat contributions placed on the player's sheet, and the follower and level they were made for.
            std::vector<std::pair<Stat, std::uint64_t>> placed;
            unsigned placedFor = 0, placedLevel = 0;
            std::uint32_t sinceMs = 0;
            bool swept = false;
        };

        std::mutex stateMutex;
        std::unordered_map<ObjectGuid, State> states;

        void Need(bool ok, char const* message)
        {
            if (!ok)
                throw std::runtime_error(message);
        }

        std::optional<unsigned> FollowerOf(std::string text)
        {
            for (char& c : text)
                c = char(std::tolower(static_cast<unsigned char>(c)));
            for (unsigned id = 1; id <= FollowerCount; ++id)
                if (text == data.keys[id - 1] || text == std::to_string(id))
                    return id;
            return std::nullopt;
        }

        Stat MainStatOf(std::string const& name)
        {
            if (name == "dexterity")
                return Stat::Dexterity;
            if (name == "intelligence")
                return Stat::Intelligence;
            return Stat::Strength;
        }

        void LoadData()
        {
            data = Data{};
            QueryResult kinds =
                WorldDatabase.Query("SELECT follower_id, gear_slot, item_slot, item_type FROM dc_follower_gear_kind");
            QueryResult relics = WorldDatabase.Query("SELECT item_entry, follower_id, power FROM dc_follower_relic");
            QueryResult stats = WorldDatabase.Query("SELECT affix_id, treatment FROM dc_follower_stat");
            QueryResult rules = WorldDatabase.Query("SELECT rule, value FROM dc_follower_gear_rule");
            QueryResult followers =
                WorldDatabase.Query("SELECT follower_id, follower_key, main_stat FROM dc_follower_gear_follower");
            QueryResult life =
                WorldDatabase.Query("SELECT level, MIN(life_per_vit) FROM dc_class_base_stats GROUP BY level");
            QueryResult tiers = WorldDatabase.Query("SELECT follower_id, tier, MIN(d3_level) FROM dc_follower_skill "
                                                    "GROUP BY follower_id, tier ORDER BY follower_id, tier");
            if (!kinds || !relics || !stats || !rules || !followers || !life || !tiers)
            {
                LOG_WARN("server",
                         "[DC followers] the follower gear tables are missing or empty: follower gear is off");
                return;
            }
            do
            {
                Field* f = kinds->Fetch();
                auto slot = SlotOf(f[1].Get<std::string>());
                if (!slot || !Campaign::Followers::Valid(f[0].Get<std::uint8_t>()))
                {
                    LOG_ERROR("server", "[DC followers] dc_follower_gear_kind has a bad row: follower gear is off");
                    return;
                }
                data.kinds.push_back(
                    {unsigned(f[0].Get<std::uint8_t>()), *slot, f[2].Get<std::string>(), f[3].Get<std::string>()});
            } while (kinds->NextRow());
            do
            {
                Field* f = relics->Fetch();
                data.relics[f[0].Get<std::uint32_t>()] = {unsigned(f[1].Get<std::uint8_t>()), f[2].Get<std::string>()};
            } while (relics->NextRow());
            do
            {
                Field* f = stats->Fetch();
                data.treatment[f[0].Get<std::string>()] = f[1].Get<std::string>();
            } while (stats->NextRow());
            unsigned found = 0;
            do
            {
                Field* f = rules->Fetch();
                std::string const name = f[0].Get<std::string>();
                double const value = f[1].Get<double>();
                if (name == "main_stat_multiplier")
                    data.rules.mainStatMultiplier = value;
                else if (name == "crit_damage_cap_pct")
                    data.rules.critDamageCap = value;
                else if (name == "player_share_pct")
                    data.rules.playerSharePct = value;
                else
                    continue;
                ++found;
            } while (rules->NextRow());
            if (found != 3 || !Usable(data.rules))
            {
                LOG_ERROR(
                    "server",
                    "[DC followers] dc_follower_gear_rule is missing a rule or holds a bad one: follower gear is off");
                return;
            }
            unsigned seen = 0;
            do
            {
                Field* f = followers->Fetch();
                unsigned const id = f[0].Get<std::uint8_t>();
                if (!Campaign::Followers::Valid(id))
                    continue;
                data.keys[id - 1] = f[1].Get<std::string>();
                data.mainStat[id - 1] = f[2].Get<std::string>();
                ++seen;
            } while (followers->NextRow());
            if (seen != FollowerCount)
            {
                LOG_ERROR(
                    "server",
                    "[DC followers] dc_follower_gear_follower does not hold every follower: follower gear is off");
                return;
            }
            do
            {
                Field* f = life->Fetch();
                data.lifePerVitality[f[0].Get<std::uint32_t>()] = f[1].Get<double>();
            } while (life->NextRow());
            do
            {
                Field* f = tiers->Fetch();
                unsigned const id = f[0].Get<std::uint8_t>(), tier = f[1].Get<std::uint8_t>();
                if (!Campaign::Followers::Valid(id) || tier != data.tierLevels[id - 1].size() + 1)
                {
                    LOG_ERROR("server",
                              "[DC followers] dc_follower_skill has tiers out of order: follower gear is off");
                    return;
                }
                data.tierLevels[id - 1].push_back(f[2].Get<std::uint8_t>());
            } while (tiers->NextRow());
            data.ready = true;
            LOG_INFO("server", "[DC followers] follower gear ready: {} kinds, {} relics", data.kinds.size(),
                     data.relics.size());
        }

        // ------------------------------------------------------------------------------------ the follower's sheet

        struct Build
        {
            std::vector<Contribution> gear, shared;
            double flatLow = 0, flatHigh = 0;
        };

        Contribution Make(Source source, Stat stat, std::uint64_t id, double value, Bucket bucket = Bucket::Flat,
                          Element element = Element::Physical)
        {
            Contribution contribution;
            contribution.source = source;
            contribution.stat = stat;
            contribution.id = id;
            contribution.value = value;
            contribution.bucket = bucket;
            contribution.element = element;
            return contribution;
        }

        // One rolled affix of a worn item, onto the follower's sheet as it would be onto a player's (Items::Apply),
        // minus what a follower does not use: a player's skill bonuses, class resources, the affixes of
        // followers_stats.csv and legendary gems.
        void AddAffix(Build& build, Affix const& affix, Instance const& instance, std::uint64_t itemGuid, bool mainHand,
                      bool weapon)
        {
            if (affix.kind == "socket" || affix.kind == "power" || affix.kind == DC::GrantedPassive::Kind)
                return;
            std::string statId = affix.affixId;
            double value = affix.value;
            Source source = Source::Items;
            if (affix.kind == "gem")
            {
                if (affix.legendaryRank)
                    return;
                std::lock_guard<std::mutex> lock(Detail::dataMutex);
                auto base = Detail::baseItems.find(instance.baseItem);
                if (base == Detail::baseItems.end())
                    return;
                std::string const slot = base->second.slot == "head"                                          ? "head"
                                         : (base->second.slot == "onehand" || base->second.slot == "twohand") ? "weapon"
                                                                                                              : "other";
                auto gem = Detail::gemEffects.find(affix.gemEntry);
                if (gem == Detail::gemEffects.end() || !gem->second.count(slot))
                    return;
                auto const& effect = gem->second.at(slot);
                statId = effect.stat;
                value = effect.value;
                source = Source::Gems;
                if (statId == "wpnphy")
                {
                    build.flatLow += value;
                    build.flatHigh += value;
                    return;
                }
            }
            // A weapon's elemental range joins the swing's range.
            if (affix.kind != "gem" && affix.value2 > 0 && weapon && Detail::WeaponDamageAffix(affix.affixId))
            {
                build.flatLow += affix.value;
                build.flatHigh += affix.value2;
                return;
            }
            {
                std::lock_guard<std::mutex> lock(Detail::dataMutex);
                if (Detail::skillAffixes.count(affix.affixId))
                    return;
            }
            auto mapping = Mappings().find(statId);
            if (mapping == Mappings().end() || mapping->second.resource)
                return;
            auto treated = data.treatment.find(statId);
            if (treated != data.treatment.end() && treated->second == "ignored")
                return;
            // A weapon's own speed is the main hand's.
            if (mapping->second.bucket == Bucket::WeaponLocal && !mainHand)
                return;
            std::uint64_t const id = Detail::ContributionId(itemGuid, affix.seq);
            Contribution contribution = Make(source, mapping->second.stat, id, Detail::Signed(mapping->second, value),
                                             mapping->second.bucket, mapping->second.element);
            build.gear.push_back(contribution);
            if (treated != data.treatment.end() && treated->second == "shared")
                build.shared.push_back(contribution);
            // Jewelry's +X-Y Physical Damage: X to the flat damage, Y - X to its delta.
            if (mapping->second.stat == Stat::WeaponFlatDamage && affix.value2 > 0)
                build.gear.push_back(Make(source, Stat::WeaponFlatDamageDelta, id, affix.value2 - affix.value,
                                          mapping->second.bucket, mapping->second.element));
        }

        double StockHealth(unsigned follower, unsigned level)
        {
            CreatureTemplate const* info = sObjectMgr->GetCreatureTemplate(Campaign::Followers::EntryOf(Id(follower)));
            if (!info)
                return 1;
            CreatureBaseStats const* stats = sObjectMgr->GetCreatureBaseStats(level, info->unit_class);
            return std::max<double>(1, stats->GenerateHealth(info));
        }

        Computed Compute(Player const* player, unsigned follower, Set const& set)
        {
            Computed out;
            out.level = std::clamp<unsigned>(player->GetLevel(), 1, NumericData::MaximumLevel());
            out.mainStat = MainStatOf(data.mainStat[follower - 1]);
            Build build;
            for (unsigned index = 0; index < SlotCount; ++index)
            {
                Worn const& worn = set[index];
                if (!worn.guid)
                    continue;
                std::optional<Instance> instance = Detail::Load(worn.guid);
                if (!instance)
                    continue;
                ItemTemplate const* proto = sObjectMgr->GetItemTemplate(worn.entry);
                bool const mainHand = Slot(index) == Slot::MainHand;
                bool const weapon = proto && proto->Class == ITEM_CLASS_WEAPON;
                if (mainHand && weapon)
                {
                    out.weapon.present = true;
                    out.weapon.min = proto->Damage[0].DamageMin;
                    out.weapon.max = proto->Damage[0].DamageMax;
                    out.weapon.delayMs = proto->Delay;
                }
                for (Affix const& affix : instance->affixes)
                    AddAffix(build, affix, *instance, worn.guid, mainHand, weapon);
            }
            if (build.flatLow > 0 || build.flatHigh > 0)
            {
                build.gear.push_back(Make(Source::Items, Stat::WeaponFlatDamage, FlatDamageId, build.flatLow));
                build.gear.push_back(
                    Make(Source::Items, Stat::WeaponFlatDamageDelta, FlatDeltaId, build.flatHigh - build.flatLow));
            }
            if (out.weapon.present && out.weapon.delayMs > 0)
                build.gear.push_back(Make(Source::Items, Stat::WeaponAPS, WeaponSpeedId, 1000.0 / out.weapon.delayMs));
            BaseStats base;
            base.level = out.level;
            base.baseLife = StockHealth(follower, out.level);
            auto life = data.lifePerVitality.find(out.level);
            base.lifePerVitality = life == data.lifePerVitality.end() ? 0 : life->second;
            // A follower has no class: no innate reduction, and the rule every class shares for Intelligence.
            base.classDRPct = 0;
            base.allResPerInt = NumericData::Rule("all_res_per_int");
            base.mainStat = out.mainStat;
            out.sheet = Sheet(base, build.gear, data.rules, [](BaseStats const& b, std::vector<Contribution> const& c)
                              { return DC::Calculate(b, c); });
            out.shared = std::move(build.shared);
            return out;
        }

        // The follower's sheet now, from its gear (cached until the gear or the player's level changes).
        Computed Current(Player const* player, unsigned follower)
        {
            Set set;
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found == states.end())
                    return Computed{};
                auto const& cached = found->second.computed[follower - 1];
                if (cached && cached->level == std::min<unsigned>(player->GetLevel(), NumericData::MaximumLevel()))
                    return *cached;
                set = found->second.worn[follower - 1];
            }
            Computed computed = Compute(player, follower, set);
            std::lock_guard<std::mutex> lock(stateMutex);
            auto found = states.find(player->GetGUID());
            if (found != states.end())
                found->second.computed[follower - 1] = computed;
            return computed;
        }

        // ------------------------------------------------------------------------------------ the creature

        void ApplyTo(Creature* creature, Computed const& computed, bool full)
        {
            CreaturePlan const plan = Plan(computed.sheet, computed.mainStat, computed.level, computed.weapon);
            float const share =
                creature->GetMaxHealth() ? float(creature->GetHealth()) / float(creature->GetMaxHealth()) : 1.0f;
            creature->SetStatFlatModifier(UNIT_MOD_HEALTH, BASE_VALUE, float(plan.maxHealth));
            creature->UpdateMaxHealth();
            creature->SetHealth(full ? creature->GetMaxHealth()
                                     : std::max<std::uint32_t>(1, std::uint32_t(share * creature->GetMaxHealth())));
            creature->SetStatFlatModifier(UNIT_MOD_ARMOR, BASE_VALUE, float(plan.armor));
            creature->UpdateArmor();
            for (unsigned school = SPELL_SCHOOL_HOLY; school <= SPELL_SCHOOL_ARCANE; ++school)
            {
                creature->SetStatFlatModifier(UnitMods(UNIT_MOD_RESISTANCE_START + school), BASE_VALUE,
                                              float(plan.resistance[school]));
                creature->UpdateResistances(school);
            }
            if (plan.swings)
            {
                creature->SetAttackTime(BASE_ATTACK, plan.attackTimeMs);
                creature->SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE,
                                              float(CoreWeaponDamage(plan.swingMin, plan.attackTimeMs)));
                creature->SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE,
                                              float(CoreWeaponDamage(plan.swingMax, plan.attackTimeMs)));
                creature->SetStatFlatModifier(UNIT_MOD_ATTACK_POWER, BASE_VALUE, 0.0f);
                creature->SetStatFlatModifier(UNIT_MOD_DAMAGE_MAINHAND, BASE_VALUE, 0.0f);
                creature->UpdateAttackPowerAndDamage();
            }
        }

        // The find stats the hired follower shares with its player, placed on the player's sheet (and taken off when
        // another follower is hired, or none).
        void RefreshShare(Player* player, bool force)
        {
            if (!data.ready)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            if (!Stats::Get(guid))
                return;
            unsigned const hired = unsigned(Campaign::Followers::Hired(player));
            unsigned const level = player->GetLevel();
            std::vector<std::pair<Stat, std::uint64_t>> had;
            bool sweep;
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found == states.end())
                    return;
                State& state = found->second;
                if (!force && state.swept && state.placedFor == hired && state.placedLevel == level)
                    return;
                sweep = !state.swept;
                had = state.placed;
            }
            // The first look since the login: the saved sheet may hold shares of a follower no longer hired.
            if (sweep)
                for (Contribution const& saved : Stats::Contributions(guid))
                    if (saved.source == Source::Items && (saved.id & ShareIdBase))
                        had.push_back({saved.stat, saved.id});
            std::map<std::pair<Stat, Bucket>, double> totals;
            if (hired)
                for (Contribution const& own : Current(player, hired).shared)
                    totals[{own.stat, own.bucket}] += own.value;
            bool changed = false;
            for (auto const& [stat, id] : had)
                changed = Stats::RemoveContribution(guid, Source::Items, stat, id) || changed;
            std::vector<std::pair<Stat, std::uint64_t>> placed;
            for (auto const& [key, total] : totals)
            {
                std::uint64_t const id = ShareIdBase | (std::uint64_t(key.first) << 8) | std::uint64_t(key.second);
                changed = Stats::AddContribution(
                              guid, Make(Source::Items, key.first, id, Shared(total, data.rules), key.second)) ||
                          changed;
                placed.push_back({key.first, id});
            }
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found == states.end())
                    return;
                found->second.placed = placed;
                found->second.placedFor = hired;
                found->second.placedLevel = level;
                found->second.swept = true;
            }
            if (changed)
                Stats::Recompute(player);
        }

        // Gear of `follower` changed: forget its sheet, and show the change on the companion and on the player's
        // shares.
        void Changed(Player* player, unsigned follower)
        {
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found == states.end())
                    return;
                found->second.computed[follower - 1].reset();
            }
            if (unsigned(Campaign::Followers::Hired(player)) == follower)
                if (Creature* companion = Campaign::Followers::Companion(player))
                    ApplyTo(companion, Current(player, follower), false);
            RefreshShare(player, true);
        }

        // ------------------------------------------------------------------------------------ equip and take off

        void CheckHub(Player* player)
        {
            Need(data.ready, "Followers are not available right now.");
            Need(player && player->GetSession(), "No session.");
            Need(player->IsAlive(), "You cannot do that while dead.");
            Need(!player->IsInCombat(), "You cannot do that in combat.");
            Need(World::IsInHub(player), "A follower's gear is changed in the hub.");
        }

        Held HeldBy(Set const& set)
        {
            Held held;
            for (unsigned index = 0; index < SlotCount; ++index)
                if (set[index].guid)
                    held.filled |= Bit(Slot(index));
            if (set[unsigned(Slot::MainHand)].guid)
                if (ItemTemplate const* proto = sObjectMgr->GetItemTemplate(set[unsigned(Slot::MainHand)].entry))
                    held.twoHanded = proto->InventoryType == INVTYPE_2HWEAPON;
            return held;
        }

        // The bag index of the inventory sheet and the stash: container * 100 + slot, 255 the backpack.
        void DecodeBag(std::int32_t index, std::uint8_t& bag, std::uint8_t& slot)
        {
            Need(index >= 0 && index < 25600, "That is not a bag slot.");
            bag = std::uint8_t(index / 100);
            slot = std::uint8_t(index % 100);
            if (bag == INVENTORY_SLOT_BAG_0)
            {
                Need(slot >= INVENTORY_SLOT_ITEM_START && slot < INVENTORY_SLOT_ITEM_END, "That is not a bag slot.");
                return;
            }
            Need(bag >= INVENTORY_SLOT_BAG_START && bag < INVENTORY_SLOT_BAG_END, "That is not a bag slot.");
        }

        // A parked item read back from item_instance as the player's own, not yet in the bags. The caller owns it.
        Item* LoadParked(Player* player, Worn const& worn)
        {
            QueryResult row = CharacterDatabase.Query("SELECT "
                                                      "creatorGuid,giftCreatorGuid,count,duration,charges,flags,"
                                                      "enchantments,randomPropertyId,durability,playedTime,"
                                                      "text FROM item_instance WHERE guid={}",
                                                      worn.guid);
            ItemTemplate const* proto = sObjectMgr->GetItemTemplate(worn.entry);
            Need(row && proto, "That item is gone.");
            Item* item = NewItemOrBag(proto);
            if (!item->LoadFromDB(std::uint32_t(worn.guid), player->GetGUID(), row->Fetch(), worn.entry))
            {
                delete item;
                throw std::runtime_error("That item could not be read.");
            }
            return item;
        }

        void Equip(Player* player, unsigned follower, std::int32_t index, std::optional<Slot> wanted)
        {
            CheckHub(player);
            std::uint8_t bag, position;
            DecodeBag(index, bag, position);
            Item* item = player->GetItemByPos(bag, position);
            Need(item, "There is no item in that slot.");
            Need(!item->IsNotEmptyBag() && !item->IsInTrade() && !item->IsWrapped() && item->GetCount() == 1,
                 "That item cannot be given to a follower.");
            ItemTemplate const* proto = item->GetTemplate();
            Need(proto->RequiredLevel <= player->GetLevel(), "You are too low a level for that item.");
            std::uint64_t const itemGuid = item->GetGUID().GetCounter();
            Offered offered;
            // A relic rolls its affixes like any other item (dc_follower_relic_roll), so it is worn rolled too.
            Need(!GetUnidentified(itemGuid), "Identify it first.");
            std::optional<Instance> instance = Detail::Load(itemGuid);
            Need(instance.has_value(), "A follower wears gear that has been rolled.");
            if (auto relic = data.relics.find(item->GetEntry()); relic != data.relics.end())
            {
                offered.relic = true;
                offered.relicFollower = relic->second.follower;
            }
            else
            {
                std::lock_guard<std::mutex> lock(Detail::dataMutex);
                auto base = Detail::baseItems.find(instance->baseItem);
                Need(base != Detail::baseItems.end(), "A follower cannot wear that.");
                offered.itemSlot = base->second.slot;
                offered.itemType = base->second.type;
                offered.classBound = !base->second.designatedClass.empty();
            }
            Set set;
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                Need(found != states.end(), "Followers are not available right now.");
                set = found->second.worn[follower - 1];
            }
            Placement const placement = Place(follower, offered, data.kinds, wanted, HeldBy(set));
            Need(placement.refusal == Refusal::None, Words(placement.refusal));
            // A filled slot swaps: the old item goes back to the bags, into the place the new one leaves (the core's own
            // swap check), else the first place that takes it, and the swap is refused only when the bags are full.
            Worn const old = set[unsigned(placement.slot)];
            Item* returned = nullptr;
            ItemPosCountVec destination;
            if (old.guid)
            {
                returned = LoadParked(player, old);
                if ((player->CanStoreItem(bag, position, destination, returned, true) != EQUIP_ERR_OK ||
                     destination.size() != 1) &&
                    (player->CanStoreItem(NULL_BAG, NULL_SLOT, destination, returned, false) != EQUIP_ERR_OK ||
                     destination.size() != 1))
                {
                    delete returned;
                    throw std::runtime_error("Your bags are full.");
                }
            }
            CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
            item->DeleteFromInventoryDB(transaction);
            transaction->Append(
                "REPLACE INTO dc_character_follower_gear (guid, follower, slot, item_guid) VALUES ({}, {}, '{}', {})",
                player->GetGUID().GetCounter(), follower, KeyOf(placement.slot), itemGuid);
            std::uint32_t const entry = item->GetEntry();
            if (!returned)
            {
                // The core prepares the inventory statement as async only, so the commit is the async one and waits
                // for its result.
                if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
                {
                    LOG_ERROR("server", "[DC followers] the gear move of item {} for {} was not saved.", itemGuid,
                              player->GetName());
                    throw std::runtime_error("The follower's gear could not be saved. Nothing was moved.");
                }
                player->MoveItemFromInventory(bag, position, true);
                delete item;
            }
            else
            {
                // The bags change first, as in TakeOff, because the returned item's row is the inventory save's to write.
                player->MoveItemFromInventory(bag, position, true);
                delete item;
                if (returned->IsInWorld())
                    returned->RemoveFromWorld();
                player->MoveItemToInventory(destination, returned, true);
                player->SaveInventoryAndGoldToDB(transaction);
                if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
                    LOG_ERROR("server", "[DC followers] the gear swap of item {} for item {} of {} was not saved.",
                              itemGuid, old.guid, player->GetName());
            }
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found != states.end())
                    found->second.worn[follower - 1][unsigned(placement.slot)] = {itemGuid, entry};
            }
            Changed(player, follower);
        }

        void TakeOff(Player* player, unsigned follower, Slot slot)
        {
            CheckHub(player);
            Worn worn;
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                Need(found != states.end(), "Followers are not available right now.");
                worn = found->second.worn[follower - 1][unsigned(slot)];
            }
            Need(worn.guid, "Nothing is worn there.");
            Item* item = LoadParked(player, worn);
            ItemPosCountVec destination;
            if (player->CanStoreItem(NULL_BAG, NULL_SLOT, destination, item, false) != EQUIP_ERR_OK ||
                destination.size() != 1)
            {
                delete item;
                throw std::runtime_error("Your bags are full.");
            }
            if (item->IsInWorld())
                item->RemoveFromWorld();
            player->MoveItemToInventory(destination, item, true);
            CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
            transaction->Append("DELETE FROM dc_character_follower_gear WHERE guid={} AND follower={} AND slot='{}'",
                                player->GetGUID().GetCounter(), follower, KeyOf(slot));
            player->SaveInventoryAndGoldToDB(transaction);
            if (!CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get())
                LOG_ERROR("server", "[DC followers] taking item {} off a follower of {} was not saved.", worn.guid,
                          player->GetName());
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found != states.end())
                    found->second.worn[follower - 1][unsigned(slot)] = Worn{};
            }
            Changed(player, follower);
        }

        // ------------------------------------------------------------------------------------ the Follower window

        // What the window shows of one follower (dc_follower_window.h): its sheet from its own gear, Damage and Toughness by
        // the player sheet's own formula, the slots it wears and can use, and its skill tiers.
        Window::View ViewOf(Player* player, unsigned follower)
        {
            Set set;
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                Need(found != states.end(), "Followers are not available right now.");
                set = found->second.worn[follower - 1];
            }
            Computed const computed = Current(player, follower);
            Window::View view;
            view.follower = follower;
            view.hired = unsigned(Campaign::Followers::Hired(player)) == follower;
            view.hub = World::IsInHub(player);
            view.level = computed.level;
            view.sheet = computed.sheet;
            view.mainStat = computed.mainStat;
            // The follower's weapon is its main hand's template range; with none it swings the bare hand the summary
            // defaults to. The sheet's flat damage is added by the summary itself, as for a player.
            Stats::SummaryInputs inputs;
            inputs.mainStat = computed.mainStat;
            if (computed.weapon.present && computed.weapon.max > 0)
                inputs.averageHit = (computed.weapon.min + computed.weapon.max) / 2;
            view.summary = Stats::SheetSummaryOf(computed.sheet, inputs);
            Held const held = HeldBy(set);
            for (unsigned index = 0; index < SlotCount; ++index)
                view.slots[index] = {set[index].entry, set[index].guid,
                                     SlotUsable(follower, Slot(index), data.kinds, held)};
            unsigned tier = 0;
            for (unsigned level : data.tierLevels[follower - 1])
                view.tiers.push_back({level, Classes::Follower::PickOf(player, follower, ++tier)});
            view.allSkills = HasPower(player, follower, PowerAllSkills);
            return view;
        }

        template<typename Send>
        void SendWindow(Player* player, unsigned follower, Send&& send)
        {
            for (Window::Record const& record : Window::Records(ViewOf(player, follower)))
                send(record);
        }

        // The DCFOLLOWER requests (docs/contracts/followers.md "Messages"). Each action is the call the command of the same
        // name runs; the Need texts those calls throw are the player's words, so they go out as refusals.
        void WindowRequest(Player& player, Bridge::Request const& request, Bridge::Wire<Player> const& wire)
        {
            try
            {
                Need(data.ready, "Followers are not available right now.");
                auto verb = request.Token(0, 8);
                auto follower = request.Uint(1, 1, FollowerCount);
                if (!verb || !follower)
                    throw Bridge::Refusal(Bridge::TextMalformed);
                // Hiring is the NPC's talk option in the hub, not the window's.
                if (std::string_view const refused = Window::Refusal(*verb); !refused.empty())
                    throw Bridge::Refusal(std::string(refused));
                if (*verb == "equip")
                {
                    auto index = request.Uint(2, 0, 0x7fffffffu);
                    auto key = request.Token(3, 12);
                    if (!index || !key)
                        throw Bridge::Refusal(Bridge::TextMalformed);
                    std::optional<Slot> wanted;
                    if (*key != "0")
                    {
                        wanted = SlotOf(*key);
                        Need(wanted.has_value(), "That is not a follower slot.");
                    }
                    Equip(&player, *follower, std::int32_t(*index), wanted);
                }
                else if (*verb == "unequip")
                {
                    auto key = request.Token(2, 12);
                    if (!key)
                        throw Bridge::Refusal(Bridge::TextMalformed);
                    auto slot = SlotOf(*key);
                    Need(slot.has_value(), "That is not a follower slot.");
                    TakeOff(&player, *follower, *slot);
                }
                else if (*verb == "dismiss")
                {
                    Need(Campaign::Followers::Hired(&player) == Id(*follower), "That follower is not with you.");
                    Campaign::Followers::Dismiss(&player);
                }
                else if (*verb == "skill")
                {
                    // A skill id keeps its hyphens (crippling-shot), which a bridge Token refuses; F4's Pick matches it
                    // against the follower's own table.
                    auto tier = request.Uint(2, 1, 4);
                    std::string const id = request.Count() > 3 ? request.fields[3] : std::string();
                    bool const plain = !id.empty() && id.size() <= 32 &&
                                       std::all_of(id.begin(), id.end(), [](char c)
                                                   { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-'; });
                    if (!tier || !plain)
                        throw Bridge::Refusal(Bridge::TextMalformed);
                    std::string const refusal = Classes::Follower::PickSkill(&player, *follower, *tier, id);
                    if (!refusal.empty())
                        throw Bridge::Refusal(refusal);
                }
                else if (*verb != "open")
                    throw Bridge::Refusal("Unknown follower action.");
                SendWindow(&player, *follower, [&](Window::Record const& record) { wire.Record(record); });
            }
            catch (std::runtime_error const& error)
            {
                throw Bridge::Refusal(error.what());
            }
        }

        // ------------------------------------------------------------------------------------ the commands

        class Commands final : public CommandScript
        {
        public:
            Commands()
                : CommandScript("dc_follower_gear_commands")
            {
            }

            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // What the Follower window's bridge runs through Player:RunCommand, as the stash and the artisans do.
                static ChatCommandTable follower = {{"gear", HandleGear, SEC_PLAYER, Console::No},
                                                    {"equip", HandleEquip, SEC_PLAYER, Console::No},
                                                    {"unequip", HandleUnequip, SEC_PLAYER, Console::No},
                                                    {"sheet", HandleSheet, SEC_PLAYER, Console::No}};
                static ChatCommandTable dc = {{"follower", follower}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            template<typename Run>
            static bool Guarded(ChatHandler* handler, Run run)
            {
                try
                {
                    Need(data.ready, "Followers are not available right now.");
                    run(handler->GetSession()->GetPlayer());
                    return true;
                }
                catch (std::exception const& error)
                {
                    handler->SendErrorMessage(error.what());
                    return false;
                }
            }

            static unsigned Which(std::string const& text)
            {
                auto follower = FollowerOf(text);
                Need(follower.has_value(), "Name a follower: 1, 2, 3 or its name.");
                return *follower;
            }

            static bool HandleGear(ChatHandler* handler, std::string who)
            {
                return Guarded(handler,
                               [&](Player* player)
                               {
                                   unsigned const follower = Which(who);
                                   Set set;
                                   {
                                       std::lock_guard<std::mutex> lock(stateMutex);
                                       auto found = states.find(player->GetGUID());
                                       Need(found != states.end(), "Followers are not available right now.");
                                       set = found->second.worn[follower - 1];
                                   }
                                   handler->PSendSysMessage("{} wears:", data.keys[follower - 1]);
                                   for (unsigned index = 0; index < SlotCount; ++index)
                                       if (set[index].guid)
                                       {
                                           ItemTemplate const* proto = sObjectMgr->GetItemTemplate(set[index].entry);
                                           handler->PSendSysMessage("  {}: {} (item {})", KeyOf(Slot(index)),
                                                                    proto ? proto->Name1 : "?", set[index].guid);
                                       }
                               });
            }

            static bool HandleEquip(ChatHandler* handler, std::string who, int32 index, Optional<std::string> slot)
            {
                return Guarded(handler,
                               [&](Player* player)
                               {
                                   std::optional<Slot> wanted;
                                   if (slot)
                                   {
                                       wanted = SlotOf(*slot);
                                       Need(wanted.has_value(), "That is not a follower slot.");
                                   }
                                   Equip(player, Which(who), index, wanted);
                                   handler->SendSysMessage("Done.");
                               });
            }

            static bool HandleUnequip(ChatHandler* handler, std::string who, std::string slot)
            {
                return Guarded(handler,
                               [&](Player* player)
                               {
                                   auto parsed = SlotOf(slot);
                                   Need(parsed.has_value(), "That is not a follower slot.");
                                   TakeOff(player, Which(who), *parsed);
                                   handler->SendSysMessage("Done.");
                               });
            }

            static bool HandleSheet(ChatHandler* handler, std::string who)
            {
                return Guarded(
                    handler,
                    [&](Player* player)
                    {
                        unsigned const follower = Which(who);
                        Computed const computed = Current(player, follower);
                        StatSheet const& sheet = computed.sheet;
                        CreaturePlan const plan = Plan(sheet, computed.mainStat, computed.level, computed.weapon);
                        handler->PSendSysMessage("{} level {}: Str {:.0f} Dex {:.0f} Int {:.0f} Vit {:.0f}",
                                                 data.keys[follower - 1], computed.level, sheet[Stat::Strength],
                                                 sheet[Stat::Dexterity], sheet[Stat::Intelligence],
                                                 sheet[Stat::Vitality]);
                        handler->PSendSysMessage(
                            "  Life {:.0f}  Armor {:.0f} ({:.1f}% less damage)  All Resistance {:.0f}", sheet.maxLife,
                            sheet[Stat::Armor], sheet.armorDR * 100, sheet[Stat::AllResistance]);
                        handler->PSendSysMessage("  Crit {:.1f}%  Crit Damage {:.0f}%  Attacks {:.2f} a second",
                                                 sheet[Stat::CritChance], sheet[Stat::CritDamage],
                                                 sheet.attacksPerSecond);
                        if (plan.swings)
                            handler->PSendSysMessage("  One swing: {:.0f} to {:.0f}", plan.swingMin, plan.swingMax);
                    });
            }
        };

        class Players final : public PlayerScript
        {
        public:
            Players()
                : PlayerScript("dc_follower_gear_player", {PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_BEFORE_LOGOUT,
                                                           PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_DELETE_FROM_DB})
            {
            }

            void OnPlayerLogin(Player* player) override
            {
                State state;
                if (QueryResult rows = CharacterDatabase.Query("SELECT g.follower, g.slot, g.item_guid, i.itemEntry "
                                                               "FROM dc_character_follower_gear g JOIN item_instance i "
                                                               "ON i.guid=g.item_guid WHERE g.guid={}",
                                                               player->GetGUID().GetCounter()))
                {
                    do
                    {
                        Field* f = rows->Fetch();
                        unsigned const follower = f[0].Get<std::uint8_t>();
                        auto slot = SlotOf(f[1].Get<std::string>());
                        if (Campaign::Followers::Valid(follower) && slot)
                            state.worn[follower - 1][unsigned(*slot)] = {f[2].Get<std::uint32_t>(),
                                                                         f[3].Get<std::uint32_t>()};
                    } while (rows->NextRow());
                }
                std::lock_guard<std::mutex> lock(stateMutex);
                states[player->GetGUID()] = std::move(state);
            }

            void OnPlayerBeforeLogout(Player* player) override
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                states.erase(player->GetGUID());
            }

            void OnPlayerUpdate(Player* player, std::uint32_t diff) override
            {
                {
                    std::lock_guard<std::mutex> lock(stateMutex);
                    auto found = states.find(player->GetGUID());
                    if (found == states.end())
                        return;
                    found->second.sinceMs += diff;
                    if (found->second.sinceMs < CheckMs)
                        return;
                    found->second.sinceMs = 0;
                }
                RefreshShare(player, false);
            }

            void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
            {
                for (std::string const& statement : DeleteCharacterSql(guid))
                    trans->Append(statement);
            }
        };

        class Startup final : public WorldScript
        {
        public:
            Startup()
                : WorldScript("dc_follower_gear_startup", {WORLDHOOK_ON_STARTUP})
            {
            }

            void OnStartup() override
            {
                LoadData();
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Startup();
        new Players();
        new Commands();
        Bridge::Routes().Add("DCFOLLOWER", {"ui", "follower_burst", "follower_per_second"}, WindowRequest);
    }

    void OpenWindow(Player* player, unsigned follower)
    {
        if (!data.ready || !Campaign::Followers::Valid(follower))
            return;
        try
        {
            SendWindow(player, follower,
                       [&](Window::Record const& record) { Bridge::Push(player, "DCFOLLOWER", record); });
        }
        catch (std::runtime_error const& error)
        {
            Bridge::Push(player, "DCFOLLOWER", {"X", error.what()});
        }
    }

    void OnCompanionSummoned(Player* player, Creature* companion, unsigned follower)
    {
        if (!data.ready || !Campaign::Followers::Valid(follower))
            return;
        ApplyTo(companion, Current(player, follower), true);
    }

    bool HasPower(Player const* player, unsigned follower, std::string_view power)
    {
        if (!data.ready || !Campaign::Followers::Valid(follower))
            return false;
        std::uint32_t entry = 0;
        {
            std::lock_guard<std::mutex> lock(stateMutex);
            auto found = states.find(player->GetGUID());
            if (found == states.end())
                return false;
            entry = found->second.worn[follower - 1][unsigned(Slot::Relic)].entry;
        }
        auto relic = data.relics.find(entry);
        return relic != data.relics.end() && relic->second.follower == follower && relic->second.power == power;
    }

    bool CannotDie(Player const* player)
    {
        unsigned const hired = unsigned(Campaign::Followers::Hired(player));
        return hired && HasPower(player, hired, PowerCannotDie);
    }

    bool SkillStatsOf(Player const* player, unsigned follower, SkillStats& out)
    {
        if (!player || !data.ready || !Campaign::Followers::Valid(follower))
            return false;
        Computed const computed = Current(player, follower);
        CreaturePlan const plan = Plan(computed.sheet, computed.mainStat, computed.level, computed.weapon);
        out.mainStat = computed.sheet[computed.mainStat];
        out.level = computed.level;
        out.swingMin = plan.swings ? plan.swingMin : 0.0;
        out.swingMax = plan.swings ? plan.swingMax : 0.0;
        out.critChance = computed.sheet[Stat::CritChance];
        out.critDamage = computed.sheet[Stat::CritDamage];
        return true;
    }
} // namespace DC::Items::FollowerGear
