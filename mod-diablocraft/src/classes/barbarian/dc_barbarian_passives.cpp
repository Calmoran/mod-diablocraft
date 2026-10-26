// The Barbarian's passives that need code: the contributions and buffs they keep up while slotted, what they do on
// a cast, a hit, a kill or fatal damage, and the skills each of them names. Numbers: barbarian_passive_values.csv,
// through each passive's record.
#include "dc_barbarian_passives.h"
#include "../dc_level_heal.h"
#include "dc_barbarian.h"
#include "../dc_resources.h"
#include "../../combat/dc_passives.h"
#include "../../combat/dc_buff_values.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_combat.h"
#include "../../common/dc_tunables.h"
#include "../../stats/dc_stats.h"
#include "../../items/dc_items.h"
#include "CellImpl.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Item.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Timer.h"
#include <algorithm>
#include <cmath>
#include <mutex>
#include <set>
#include <unordered_map>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (82300–82304): passive helper aura ids; Identifiers.
namespace DC::Combat::Passives
{
    namespace
    {
        using Row = Shells::Passive;
        std::recursive_mutex mutex;
        struct State
        {
            bool dirty = true;
            uint32 clock = 0;
            // The upkeep of the buffs the passives wear (ShowConditions).
            uint32 buffClock = 0;
            uint64 signature = 0;
            // drApplied undoes the sheet's own copy of the damage reductions
            // for the live read below. There is no rcrApplied: the core pays
            // every cost and nothing here does, so nothing has to correct for
            // the sheet carrying the same percentage twice.
            double drApplied = 1;
            std::vector<std::pair<uint32, ObjectGuid>> controls;
        };
        std::unordered_map<uint64, State> states;
        std::unordered_map<uint64, std::set<uint64>> contributors;
        std::unordered_map<uint32, std::string> weaponTypes;
        std::unordered_map<std::string, double> tunes;
        std::unordered_map<uint64, uint32> allyClock;
        Row const* RowFor(char const* name)
        {
            for (auto const& r : Shells::Passives)
                if (std::string(r.name) == name)
                    return &r;
            return nullptr;
        }
        double Tune(char const* key)
        {
            auto i = tunes.find(key);
            return i == tunes.end() ? 0 : std::clamp(i->second, 0.0, 100.0);
        }
        bool Low(Player* p)
        {
            auto r = RowFor("Relentless");
            return p && r && Has(p, r->name) && p->GetHealthPct() < Numbers::Num(r->id, "life_threshold_pct");
        }
        bool Shield(Player* p)
        {
            auto i = p->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_OFFHAND);
            return i && i->GetTemplate()->InventoryType == INVTYPE_SHIELD;
        }
        std::string Weapon(Player* p)
        {
            auto item = p->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND);
            if (!item)
                return {};
            auto rolled = Items::Get(item->GetGUID().GetCounter());
            auto i = weaponTypes.find(rolled ? rolled->baseItem : item->GetEntry());
            if (i != weaponTypes.end())
                return i->second;
            auto proto = item->GetTemplate();
            if (proto->Class != ITEM_CLASS_WEAPON)
                return {};
            switch (proto->SubClass)
            {
                case ITEM_SUBCLASS_WEAPON_SWORD:
                case ITEM_SUBCLASS_WEAPON_SWORD2:
                    return "Sword";
                case ITEM_SUBCLASS_WEAPON_DAGGER:
                    return "Dagger";
                case ITEM_SUBCLASS_WEAPON_MACE:
                case ITEM_SUBCLASS_WEAPON_MACE2:
                    return "Mace";
                case ITEM_SUBCLASS_WEAPON_AXE:
                case ITEM_SUBCLASS_WEAPON_AXE2:
                    return "Axe";
                case ITEM_SUBCLASS_WEAPON_POLEARM:
                    return "Polearm";
                case ITEM_SUBCLASS_WEAPON_SPEAR:
                    return "Spear";
                default:
                    return {};
            }
        }
        void Heal(Player* p, uint32 id, double n)
        {
            if (n <= 0 || !p->IsAlive())
                return;
            HealInfo h(p, p, uint32(std::min(n, double(UINT32_MAX))), sSpellMgr->GetSpellInfo(id),
                       SPELL_SCHOOL_MASK_HOLY);
            p->HealBySpell(h);
        }
        void Gain(Player* p, double n)
        {
            Resources::Add(p, Resources::Fury, n * GenerationFactor(p));
        }
        struct Check
        {
            Player* p;
            double radius;
            bool friendly;
            bool operator()(Unit* u) const
            {
                return u && u->IsAlive() && p->IsInMap(u) && p->InSamePhase(u) && p->GetExactDist(u) <= radius &&
                       p->IsWithinLOSInMap(u) && (friendly ? p->IsValidAssistTarget(u) : p->IsValidAttackTarget(u));
            }
        };
        std::vector<Unit*> Nearby(Player* p, double radius, bool friendly = false)
        {
            std::list<Unit*> units;
            Check check{p, radius, friendly};
            Acore::UnitListSearcher<Check> searcher(p, units, check);
            Cell::VisitObjects(p, searcher, float(radius));
            if (friendly && std::find(units.begin(), units.end(), p) == units.end())
                units.push_back(p);
            return {units.begin(), units.end()};
        }
        // Berserker Rage and Brawler hold on a condition the damage reads at every hit and the buff icon shows
        // alike: one test each, so what the icon says is what the hit uses.
        bool BerserkerRageOn(Player* p)
        {
            double const threshold = Tune("berserker_rage_min_fury_pct");
            return Has(p, "Berserker Rage") && threshold > 0 &&
                   Resources::Units(p, Resources::Fury) >= Resources::MaxUnits(p, Resources::Fury) * threshold / 100;
        }
        bool BrawlerOn(Player* p)
        {
            auto r = RowFor("Brawler");
            return r && Has(p, "Brawler") &&
                   Nearby(p, Numbers::Num(r->id, "radius_yards")).size() >= Numbers::Num(r->id, "nearby_enemy_count");
        }
        // Buff icons build 2 (data/class_buffs.csv): Relentless, Berserker Rage and Brawler wear a buff while their
        // condition holds, looked at every combat.class_buff_refresh_ms (Brawler counts the enemies around).
        void ShowConditions(Player* p, State& s, uint32 diff)
        {
            double const interval = DC::Tunables::Get("combat", "class_buff_refresh_ms");
            s.buffClock += diff;
            if (s.buffClock < interval)
                return;
            s.buffClock = 0;
            static uint32 const relentless = Shells::HelperFor("Relentless - buff");
            static uint32 const berserker = Shells::HelperFor("Berserker Rage - buff");
            static uint32 const brawler = Shells::HelperFor("Brawler - buff");
            BuffValues::Show(p, relentless, Low(p) ? 1 : 0);
            BuffValues::Show(p, berserker, BerserkerRageOn(p) ? 1 : 0);
            BuffValues::Show(p, brawler, BrawlerOn(p) ? 1 : 0);
        }
        void Marker(Player* p, Unit* u, uint32 id, double seconds)
        {
            if (auto a = p->AddAura(id, u))
            {
                a->SetMaxDuration(int32(seconds * 1000));
                a->SetDuration(int32(seconds * 1000));
            }
        }
        // Every Fury cost is paid by the
        // core, so every reduction is a SPELLMOD_COST aura on the player and
        // the core applies them in its own order. Two of them are the passives,
        // whose percentage their record already carries, so they are only
        // switched on and off. The third is one hidden aura that stands
        // for the stat sheet's item and paragon Resource Cost Reduction, cast
        // in as its amount. A spell modifier's amount is whole percent, so a
        // fractional sheet number is rounded to the nearest - an accepted
        // deviation of at most half a percent of a cost, measured by
        // scripts/test_cost_math.py.
        //
        // The character sheet keeps showing a Resource Cost Reduction, but it
        // is now derived from those modifiers rather than from a parallel set
        // of sheet contributions: the module hands the core a probe cost and
        // reads back what the player's own modifiers did to it, so the number
        // on the sheet is the one the modifiers charge with, whatever the
        // core's stacking does. RefreshModifiers below is that one rebuild,
        // and everything that can change a cost reduction calls it.
        void CostModifiers(Player* p, bool relentless, bool swordAndBoard)
        {
            auto toggle = [&](char const* owner, bool live)
            {
                uint32 const id = Shells::CostModifierFor(owner);
                if (!id)
                    return;
                if (live && !p->HasAura(id))
                    p->AddAura(id, p);
                else if (!live && p->HasAura(id))
                    p->RemoveAurasDueToSpell(id);
            };
            toggle("Relentless", relentless);
            toggle("Sword and Board", swordAndBoard);
            RefreshModifiers(p);
        }

        // Boon of Bul-Kathos is a permanent
        // flat reduction in D3 and not a refund, so it is what the core calls
        // one - a SPELLMOD_COOLDOWN aura that names the skills it shortens -
        // and not a subtraction from a timer the module has already started.
        // It is two records because a spell modifier carries one amount and
        // the passive takes 15 s off Earthquake and 30 off the other two; each
        // record's mask names its own skills, so both are simply on together.
        void CooldownModifiers(Player* p, bool boon)
        {
            for (auto const& row : Shells::CooldownModifiers)
            {
                if (std::string(row.owner) != "Boon of Bul-Kathos")
                    continue;
                if (boon && !p->HasAura(row.id))
                    p->AddAura(row.id, p);
                else if (!boon && p->HasAura(row.id))
                    p->RemoveAurasDueToSpell(row.id);
            }
        }

        // "The duration of your shouts is doubled" is a
        // SPELLMOD_DURATION of +100% over the three skills the passive's own
        // sentence names, so the record carries the percentage and the mask and
        // the module only switches it on. Before this the three shouts each
        // multiplied their own duration by two in dc_abilities, which no
        // tooltip and no other duration could see.
        void DurationModifiers(Player* p, bool inspiring)
        {
            for (auto const& row : Shells::DurationModifiers)
            {
                if (std::string(row.owner) != "Inspiring Presence")
                    continue;
                if (inspiring && !p->HasAura(row.id))
                    p->AddAura(row.id, p);
                else if (!inspiring && p->HasAura(row.id))
                    p->RemoveAurasDueToSpell(row.id);
            }
        }
    } // namespace

    namespace
    {

        void Refresh(Player* p)
        {
            auto guid = p->GetGUID().GetRawValue();
            for (auto const& r : Shells::Passives)
                for (auto st : {Stat::CritChance, Stat::AttackSpeed, Stat::Armor, Stat::Thorns, Stat::MaxFury,
                                Stat::Strength, Stat::ResourceCostReduction, Stat::SpecificReduction})
                    Stats::RemoveContribution(guid, Source::Passives, st, r.id);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, 82300);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, 82304);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::MovementSpeed, 82304);
            auto add = [&](Row const* r, Stat st, double n, Bucket bucket = Bucket::Flat)
            { Stats::AddContribution(guid, {Source::Passives, st, r->id, n, bucket}); };
            auto& state = states[guid];
            state.drApplied = 1;
            // The core pays every Fury cost,
            // so each reduction is a SPELLMOD_COST aura it can apply, and the
            // character sheet's Resource Cost Reduction is derived from those
            // modifiers in CostModifiers below. Neither passive contributes its
            // percentage to the sheet: a parallel sheet copy would count it
            // twice, and nothing reads one for a payment.
            bool const relentless = Low(p);
            bool const swordAndBoard = Has(p, "Sword and Board") && Shield(p);
            if (relentless)
            {
                auto r = RowFor("Relentless");
                add(r, Stat::SpecificReduction, Numbers::Num(r->id, "damage_taken_pct"));
                state.drApplied *= 1 - Numbers::Num(r->id, "damage_taken_pct") / 100;
            }
            if (swordAndBoard)
            {
                auto r = RowFor("Sword and Board");
                add(r, Stat::SpecificReduction, Numbers::Num(r->id, "damage_reduction_pct"));
                state.drApplied *= 1 - Numbers::Num(r->id, "damage_reduction_pct") / 100;
            }
            if (p->HasAura(82301))
            {
                auto r = RowFor("Nerves of Steel");
                add(r, Stat::SpecificReduction, Numbers::Num(r->id, "damage_taken_pct"));
                state.drApplied *= 1 - Numbers::Num(r->id, "damage_taken_pct") / 100;
            }
            if (Has(p, "Animosity"))
            {
                auto r = RowFor("Animosity");
                add(r, Stat::MaxFury, Numbers::Num(r->id, "max_pool_resource"));
            }
            if (Has(p, "Tough as Nails"))
            {
                auto r = RowFor("Tough as Nails");
                add(r, Stat::Armor, Numbers::Num(r->id, "armor_pct"), Bucket::Percent);
                add(r, Stat::Thorns, Numbers::Num(r->id, "thorns_pct"), Bucket::Percent);
            }
            if (Has(p, "Weapons Master"))
            {
                auto r = RowFor("Weapons Master");
                auto w = Weapon(p);
                if (w.find("Mighty") == std::string::npos)
                {
                    if (w.find("Mace") != std::string::npos || w.find("Axe") != std::string::npos)
                        add(r, Stat::CritChance, Numbers::Num(r->id, "crit_chance_pct"));
                    if (w.find("Polearm") != std::string::npos || w.find("Spear") != std::string::npos)
                        add(r, Stat::AttackSpeed, Numbers::Num(r->id, "attack_speed_pct"));
                }
            }
            if (Has(p, "Rampage"))
                if (auto a = p->GetAura(82303))
                    add(RowFor("Rampage"), Stat::Strength, Numbers::Num(RowFor("Rampage")->id, "primary_stat_pct") * a->GetStackAmount(),
                        Bucket::Percent);
            if (p->HasAura(82300))
                Stats::AddContribution(guid, {Source::Temporary, Stat::LifeRegen, 82300,
                                              p->GetMaxHealth() * Numbers::Num(RowFor("Inspiring Presence")->id, "life_regen_pct") / 100});
            if (Has(p, "Pound of Flesh"))
                if (auto a = p->GetAura(82304))
                {
                    auto r = RowFor("Pound of Flesh");
                    Stats::AddContribution(guid, {Source::Temporary, Stat::LifeRegen, 82304,
                                                  p->GetMaxHealth() * Numbers::Num(r->id, "life_regen_pct") / 100 * a->GetStackAmount()});
                    Stats::AddContribution(guid, {Source::Temporary, Stat::MovementSpeed, 82304,
                                                  Numbers::Num(r->id, "movement_speed_pct") * a->GetStackAmount(), Bucket::Uncapped});
                }
            if (Has(p, "Unforgiving"))
            {
                if (!p->HasAura(82302))
                    p->AddAura(82302, p);
            }
            else
                p->RemoveAurasDueToSpell(82302);
            Stats::Recompute(p);
            CooldownModifiers(p, Has(p, "Boon of Bul-Kathos"));
            DurationModifiers(p, Has(p, "Inspiring Presence"));
            CostModifiers(p, relentless, swordAndBoard);
            states[guid].dirty = false;
        }
        void Rampage(Player* p)
        {
            if (!Has(p, "Rampage") || !p->IsAlive())
                return;
            auto r = RowFor("Rampage");
            Marker(p, p, 82303, Numbers::Num(r->id, "duration_seconds"));
            states[p->GetGUID().GetRawValue()].dirty = true;
            Refresh(p);
        }
        class World final : public WorldScript
        {
        public:
            World()
                : WorldScript("dc_barbarian_passives_world", {WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_AFTER_CONFIG_LOAD})
            {
            }
            void OnAfterConfigLoad(bool reload) override
            {
                if (reload)
                    OnStartup();
            }
            void OnStartup() override
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                if (auto q = WorldDatabase.Query("SELECT entry,type FROM dc_base_item"))
                    do
                    {
                        auto f = q->Fetch();
                        weaponTypes[f[0].Get<uint32>()] = f[1].Get<std::string>();
                    } while (q->NextRow());
                if (auto q = WorldDatabase.Query("SELECT name,tuned_value FROM dc_ability_tuning"))
                    do
                    {
                        auto f = q->Fetch();
                        tunes[f[0].Get<std::string>()] = f[1].Get<double>();
                    } while (q->NextRow());
            }
        };
        class Events final : public UnitScript
        {
        public:
            Events()
                : UnitScript("dc_barbarian_passive_events", true,
                             {UNITHOOK_ON_DAMAGE, UNITHOOK_ON_UNIT_DEATH, UNITHOOK_ON_AURA_APPLY,
                              UNITHOOK_ON_AURA_REMOVE, UNITHOOK_CAN_REWARD_RAGE, UNITHOOK_ON_UNIT_UPDATE})
            {
            }
            bool CanRewardRage(Unit* u, uint32, uint32, bool, float&) override
            {
                return !(u && u->ToPlayer() && u->ToPlayer()->getClass() == CLASS_WARRIOR);
            }
            void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                if (damage && attacker && victim)
                    if (auto p = attacker->GetCharmerOrOwnerPlayerOrPlayerItself())
                        contributors[victim->GetGUID().GetRawValue()].insert(p->GetGUID().GetRawValue());
            }
            void OnUnitDeath(Unit* u, Unit*) override
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                auto i = contributors.find(u->GetGUID().GetRawValue());
                if (i == contributors.end())
                    return;
                auto who = std::move(i->second);
                contributors.erase(i);
                for (auto guid : who)
                    if (auto p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(guid));
                        p && p->IsInMap(u) && p->InSamePhase(u))
                        Rampage(p);
            }
            void OnAuraApply(Unit* u, Aura* a) override
            {
                auto p = u ? u->ToPlayer() : nullptr;
                if (!p || !a || p->getClass() != CLASS_WARRIOR)
                    return;
                std::lock_guard<std::recursive_mutex> guard(mutex);
                states[p->GetGUID().GetRawValue()].dirty = true;
                // A legendary power's own buff or slow (Stone Gauntlets) is the item's, on the item's one timer: not a control put on the
                // player, so Juggernaut neither shortens it nor heals from it.
                if (!Has(p, "Juggernaut") || a->GetId() == 82301 ||
                    std::any_of(std::begin(Shells::PowerBuffs), std::end(Shells::PowerBuffs),
                                [&](Shells::PowerBuff const& buff) { return buff.id == a->GetId(); }))
                    return;
                auto mask = a->GetSpellInfo()->GetAllEffectsMechanicMask();
                for (auto const& effect : a->GetSpellInfo()->Effects)
                {
                    switch (effect.ApplyAuraName)
                    {
                        case SPELL_AURA_MOD_CONFUSE:
                            mask |= 1u << MECHANIC_DISORIENTED;
                            break;
                        case SPELL_AURA_MOD_CHARM:
                            mask |= 1u << MECHANIC_CHARM;
                            break;
                        case SPELL_AURA_MOD_FEAR:
                            mask |= 1u << MECHANIC_FEAR;
                            break;
                        case SPELL_AURA_MOD_ROOT:
                            mask |= 1u << MECHANIC_ROOT;
                            break;
                        case SPELL_AURA_MOD_SILENCE:
                            mask |= 1u << MECHANIC_SILENCE;
                            break;
                        case SPELL_AURA_MOD_DECREASE_SPEED:
                            mask |= 1u << MECHANIC_SNARE;
                            break;
                        case SPELL_AURA_MOD_STUN:
                            mask |= 1u << MECHANIC_STUN;
                            break;
                        default:
                            break;
                    }
                }
                uint32 controls = (1u << MECHANIC_CHARM) | (1u << MECHANIC_DISORIENTED) | (1u << MECHANIC_FEAR) |
                                  (1u << MECHANIC_ROOT) | (1u << MECHANIC_SILENCE) | (1u << MECHANIC_SLEEP) |
                                  (1u << MECHANIC_SNARE) | (1u << MECHANIC_STUN) | (1u << MECHANIC_FREEZE) |
                                  (1u << MECHANIC_KNOCKOUT) | (1u << MECHANIC_POLYMORPH) | (1u << MECHANIC_HORROR) |
                                  (1u << MECHANIC_DAZE) | (1u << MECHANIC_SAPPED);
                auto r = RowFor("Juggernaut");
                if (mask & controls)
                    states[p->GetGUID().GetRawValue()].controls.emplace_back(a->GetId(), a->GetCasterGUID());
                uint32 healMask =
                    (1u << MECHANIC_STUN) | (1u << MECHANIC_FREEZE) | (1u << MECHANIC_FEAR) | (1u << MECHANIC_ROOT);
                if (mask & healMask && roll_chance_f(float(Tune("juggernaut_heal_proc_chance_pct"))))
                    Heal(p, r->id, p->GetMaxHealth() * Numbers::Num(r->id, "heal_pct") / 100);
            }
            void OnAuraRemove(Unit* u, AuraApplication* a, AuraRemoveMode) override
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                if (u && a && a->GetBase()->GetId() == 82300)
                    allyClock.erase(u->GetGUID().GetRawValue());
                if (auto p = u ? u->ToPlayer() : nullptr; p && p->getClass() == CLASS_WARRIOR)
                {
                    std::lock_guard<std::recursive_mutex> guard(mutex);
                    states[p->GetGUID().GetRawValue()].dirty = true;
                }
            }
            void OnUnitUpdate(Unit* u, uint32 diff) override
            {
                if (!u || (u->ToPlayer() && u->ToPlayer()->getClass() == CLASS_WARRIOR) || !u->IsAlive())
                    return;
                auto a = u->GetAura(82300);
                if (!a)
                    return;
                std::lock_guard<std::recursive_mutex> guard(mutex);
                auto& clock = allyClock[u->GetGUID().GetRawValue()];
                clock += diff;
                uint32 ticks = clock / 1000;
                clock %= 1000;
                if (ticks)
                    if (auto p = ObjectAccessor::FindConnectedPlayer(a->GetCasterGUID()); p && p->IsInMap(u))
                    {
                        HealInfo h(p, u, uint32(u->GetMaxHealth() * Numbers::Num(RowFor("Inspiring Presence")->id, "life_regen_pct") / 100 * ticks),
                                   sSpellMgr->GetSpellInfo(82300), SPELL_SCHOOL_MASK_HOLY);
                        p->HealBySpell(h);
                    }
            }
        };
        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_barbarian_passives_update", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }
            void OnPlayerUpdate(Player* p, uint32 diff) override
            {
                if (p->getClass() != CLASS_WARRIOR)
                    return;
                std::lock_guard<std::recursive_mutex> guard(mutex);
                auto& s = states[p->GetGUID().GetRawValue()];
                uint64 sig = p->GetMaxHealth();
                sig ^= uint64(Low(p)) << 49;
                sig ^= uint64(Shield(p)) << 50;
                sig ^= uint64(p->HasAura(82301)) << 51;
                if (auto i = p->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_OFFHAND))
                    sig ^= i->GetGUID().GetRawValue() << 1;
                auto pending = std::move(s.controls);
                s.controls.clear();
                for (auto const& [id, caster] : pending)
                    if (auto aura = p->GetAura(id, caster); aura && aura->GetDuration() > 0)
                    {
                        double factor = 1 - Numbers::Num(RowFor("Juggernaut")->id, "cc_duration_reduction_pct") / 100;
                        aura->SetMaxDuration(int32(aura->GetMaxDuration() * factor));
                        aura->SetDuration(int32(aura->GetDuration() * factor));
                    }
                if (auto item = p->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND))
                    sig ^= item->GetGUID().GetRawValue();
                if (auto a = p->GetAura(82303))
                    sig ^= uint64(a->GetStackAmount()) << 32;
                if (p->HasAura(82300))
                    sig ^= uint64(1) << 48;
                if (auto a = p->GetAura(82304))
                    sig ^= uint64(a->GetStackAmount()) << 40;
                if (sig != s.signature || s.dirty)
                {
                    s.signature = sig;
                    Refresh(p);
                }
                ShowConditions(p, s, diff);
                if (!p->IsAlive())
                {
                    s.clock = 0;
                    return;
                }
                if (Has(p, "Unforgiving"))
                {
                    auto r = RowFor("Unforgiving");
                    s.clock += diff;
                    uint32 period = uint32(Numbers::Num(r->id, "interval_seconds") * 1000);
                    if (period && s.clock >= period)
                    {
                        uint32 ticks = s.clock / period;
                        s.clock %= period;
                        Gain(p, Numbers::Num(r->id, "gain_resource") * ticks);
                    }
                }
                else
                    s.clock = 0;
            }
            void OnPlayerLogout(Player* p) override
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                states.erase(p->GetGUID().GetRawValue());
                for (auto& [victim, who] : contributors)
                    who.erase(p->GetGUID().GetRawValue());
            }
        };
    } // namespace
    double DamageBonus(Player* p)
    {
        if (!p)
            return 0;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        double bonus = 0;
        if (Has(p, "Weapons Master"))
        {
            auto w = Weapon(p);
            if (w.find("Sword") != std::string::npos || w.find("Dagger") != std::string::npos)
                bonus += Numbers::Num(RowFor("Weapons Master")->id, "damage_bonus_pct");
        }
        if (BerserkerRageOn(p))
            bonus += Numbers::Num(RowFor("Berserker Rage")->id, "damage_bonus_pct");
        if (BrawlerOn(p))
            bonus += Numbers::Num(RowFor("Brawler")->id, "damage_bonus_pct");
        return bonus;
    }
    void Multipliers(Player* p, Unit* target, std::string const& skill, DC::Combat::Factors& out)
    {
        if (!p || !target)
            return;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        if (Has(p, "Ruthless"))
        {
            auto r = RowFor("Ruthless");
            if (target->GetHealthPct() < Numbers::Num(r->id, "life_threshold_pct"))
                AddFactor(out, "Ruthless", Numbers::Num(r->id, "damage_bonus_pct"));
        }
        if (Has(p, "No Escape") && Abilities::NoEscapeSkill(skill))
        {
            auto r = RowFor("No Escape");
            if (p->GetExactDist(target) > Numbers::Num(r->id, "radius_yards"))
                AddFactor(out, "No Escape", Numbers::Num(r->id, "damage_bonus_pct"));
        }
    }
    double GenerationFactor(Player* p)
    {
        // Every Fury gain of the Barbarian's skills passes here: Animosity's, what a source outside the class scales it by (Inspire),
        // and the item powers that raise resource generation.
        return (Has(p, "Animosity") ? 1 + Numbers::Num(RowFor("Animosity")->id, "regen_pct") / 100 : 1) *
               Resources::Generated(p, Resources::Fury, 1.0) * ItemPowers::GenerationFactor(p);
    }
    double FuryHealFactor(Player* p)
    {
        return Low(p) ? 2 : 1; /* CSV: Life per Fury Spent is doubled. */
    }
    double IncomingFactor(Player* p, unsigned school)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        if (!p)
            return 1;
        double factor = 1;
        if (Has(p, "Superstition") && school != SPELL_SCHOOL_MASK_NORMAL)
            factor *= 1 - Numbers::Num(RowFor("Superstition")->id, "damage_bonus_pct") / 100;
        if (Low(p))
            factor *= 1 - Numbers::Num(RowFor("Relentless")->id, "damage_taken_pct") / 100;
        if (Has(p, "Sword and Board") && Shield(p))
            factor *= 1 - Numbers::Num(RowFor("Sword and Board")->id, "damage_reduction_pct") / 100;
        if (p->HasAura(82301))
            factor *= 1 - Numbers::Num(RowFor("Nerves of Steel")->id, "damage_taken_pct") / 100;
        return factor / states[p->GetGUID().GetRawValue()].drApplied;
    }
    void Spent(Player* p, double fury)
    {
        if (Has(p, "Bloodthirst"))
            Heal(p, RowFor("Bloodthirst")->id, fury * Classes::HealAtLevel(Numbers::Num(RowFor("Bloodthirst")->id, "heal_life"), p->GetLevel()) * FuryHealFactor(p));
    }
    void Begin(Player* p, uint32 id)
    {
        auto row = Shells::FindAbility(id);
        if (!row)
            return;
        if (Has(p, "Earthen Might") && Abilities::EarthenMightSkill(row->skill))
            Gain(p, Numbers::Num(RowFor("Earthen Might")->id, "gain_resource"));
    }
    void Cast(Player* p, uint32 id)
    {
        auto row = Shells::FindAbility(id);
        if (!row)
            return;
        if (Has(p, "Inspiring Presence") && Abilities::ShoutSkill(row->skill))
        {
            auto r = RowFor("Inspiring Presence");
            for (auto u : Nearby(p, Numbers::Num(r->id, "radius_yards"), true))
                Marker(p, u, 82300, Numbers::Num(r->id, "duration_seconds"));
        }
    }
    void Fatal(Player* p, uint32& damage)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        if (!p || p->getClass() != CLASS_WARRIOR || damage < p->GetHealth() || !Has(p, "Nerves of Steel"))
            return;
        auto r = RowFor("Nerves of Steel");
        if (p->HasSpellCooldown(r->id))
            return;
        // Issue #49: end_time is a relative millisecond duration in this core
        // (Player::_AddSpellCooldown adds it to GameTime::GetGameTimeMS), not
        // an epoch time, so the sheet's seconds go in as milliseconds.
        p->AddSpellCooldown(r->id, 0, uint32(std::llround(Numbers::Num(r->id, "internal_cooldown_seconds") * 1000)),
                            true);
        p->SetHealth(uint32(p->GetMaxHealth() * Numbers::Num(r->id, "life_floor_pct") / 100));
        damage = 0;
        Marker(p, p, 82301, Numbers::Num(r->id, "duration_seconds"));
        // The control immunity is 82301's own record (aura 147 and 77, the PURGES attribute): applying it above refuses
        // new holds and strips the ones already on (aura review row 5).
    }

    void Globe(Player* p)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        if (Has(p, "Pound of Flesh"))
        {
            Marker(p, p, 82304, Numbers::Num(RowFor("Pound of Flesh")->id, "duration_seconds"));
            states[p->GetGUID().GetRawValue()].dirty = true;
        }
    }

    namespace Barbarian
    {
        void RegisterScripts()
        {
            new World();
            new Events();
            new Update();
        }
        void Changed(Player* p)
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            states[p->GetGUID().GetRawValue()].dirty = true;
        }
        void Hit(Player* p, Unit* target)
        {
            if (target && Has(p, "Weapons Master") && Weapon(p).find("Mighty") != std::string::npos)
                Gain(p, Numbers::Num(RowFor("Weapons Master")->id, "gain_resource"));
        }
        void Taken(Player* p, unsigned school, bool ranged)
        {
            if (p && Has(p, "Superstition") && (ranged || school != SPELL_SCHOOL_MASK_NORMAL) &&
                roll_chance_f(float(Tune("superstition_fury_proc_chance_pct"))))
                Gain(p, Numbers::Num(RowFor("Superstition")->id, "gain_resource"));
        }
    } // namespace Barbarian
} // namespace DC::Combat::Passives

namespace DC::Combat::Abilities
{
    bool NoEscapeSkill(std::string const& skill)
    {
        return skill == "Weapon Throw" || skill == "Seismic Slam" || skill == "Ancient Spear" || skill == "Avalanche";
    }

    bool EarthenMightSkill(std::string const& skill)
    {
        return skill == "Avalanche" || skill == "Earthquake";
    }

    bool ShoutSkill(std::string const& skill)
    {
        return skill == "War Cry" || skill == "Battle Rage" || skill == "Threatening Shout";
    }
} // namespace DC::Combat::Abilities
