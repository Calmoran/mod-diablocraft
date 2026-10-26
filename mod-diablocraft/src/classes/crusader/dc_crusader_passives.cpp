/*
 * The Crusader's passives that need code: Heavenly Strength, Fervor, Vigilant, Righteousness, Insurmountable and
 * Fanaticism; Indestructible, Holy Cause, Wrathful, Divine Fortress, Lord Commander and Hold Your Ground. The numbers
 * are crusader_passive_values.csv (skill = the passive's name), read through each passive's record.
 *
 * A passive is on when it sits in one of the Crusader's passive slots, or a worn item grants it (Passives::Has). Five
 * of them are stat contributions (Fervor, Vigilant, Righteousness' larger pool, Divine Fortress, Hold Your Ground),
 * kept by a small update script that puts them on the sheet when the slots, the weapon or the Block Chance change; the
 * others are read where the hit, the attack speed, the block, the cast, the kill or the fatal damage is worked out.
 */

#include "dc_crusader_passives.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"
#include "../../combat/dc_passives.h"
#include "../../common/dc_numeric_data.h"
#include "../../stats/dc_stats.h"

#include "../../items/dc_items.h"
#include "Item.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <cmath>

namespace DC::Combat::Crusader::Passive
{
    namespace
    {
        // How often the update script looks at the slots, the weapon and the Block Chance (ms).
        constexpr std::uint32_t Period = 250;

        std::uint32_t Id(std::string_view name)
        {
            for (auto const& passive : Shells::Passives)
                if (name == passive.name)
                    return passive.id;
            return 0;
        }

        bool IsCrusader(Player const* player)
        {
            return player && Classes::ClassIdOf(player) == Resources::Find("Crusader", "wrath")->classId;
        }

        bool On(Player* player, char const* name)
        {
            return IsCrusader(player) && Passives::Has(player, name);
        }

        double Num(char const* name, char const* token)
        {
            return Numbers::Num(Id(name), token);
        }

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;
        }

        Wield WieldOf(Player* player)
        {
            Wield wield;
            if (Item const* main = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND))
            {
                InventoryType const type = InventoryType(main->GetTemplate()->InventoryType);
                wield.oneHand = type == INVTYPE_WEAPON || type == INVTYPE_WEAPONMAINHAND;
                wield.twoHand = type == INVTYPE_2HWEAPON;
            }
            if (Item const* off = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_OFFHAND))
                wield.shield = off->GetTemplate()->InventoryType == INVTYPE_SHIELD;
            return wield;
        }

        // The Wrath a cast costs the Crusader, reductions included (the core takes that number): 0 for a spell that is
        // not a Crusader skill or costs no Wrath.
        double WrathSpent(Player* player, Spell* spell)
        {
            if (!player || !spell || spell->GetPowerCost() <= 0 || !Shells::FindAbility(spell->GetSpellInfo()->Id))
                return 0.0;
            auto const& wrath = *Resources::Find("Crusader", "wrath");
            if (Classes::ClassIdOf(player) != wrath.classId || spell->GetSpellInfo()->PowerType != POWER_ENERGY)
                return 0.0;
            return Resources::ToPoints(wrath, spell->GetPowerCost());
        }

        // Per Crusader: the bits and the Block Chance the sheet was last built for (in hundredths of a percent), and
        // Indestructible's save.
        struct State
        {
            unsigned signature = 0;
            std::int64_t blockCenti = 0;
            unsigned gems = 0;
            unsigned level = 0; // the level Vigilant's regeneration was built at
            std::uint32_t clock = 0;
            bool dirty = true;
            Fatal fatal;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        // The gems socketed in the gear the Crusader wears.
        unsigned WornGems(Player* player)
        {
            unsigned gems = 0;
            for (std::uint8_t slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
                if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                    if (std::optional<Items::Instance> instance = Items::Get(item->GetGUID().GetCounter()))
                        for (Items::Affix const& affix : instance->affixes)
                            if (affix.kind == "gem")
                                ++gems;
            return gems;
        }

        double BlockChanceOf(Player* player)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            return sheet ? (*sheet)[Stat::BlockChance] : 0.0;
        }

        // The rows the passives keep on the sheet, taken off and put back whole: Fervor's attack speed and cooldown
        // reduction, Vigilant's Life regeneration and reduction of every element but Physical, Righteousness' larger
        // Wrath pool, Hold Your Ground's Block Chance and Divine Fortress' Armor (read after the Block Chance is on, so
        // it counts Hold Your Ground's). The cooldown reduction is also a core aura, so the gear modifier is rebuilt
        // after it.
        void Refresh(Player* player, unsigned wanted, unsigned gems)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const fervor = Id("Fervor"), vigilant = Id("Vigilant"), righteous = Id("Righteousness"),
                                fortress = Id("Divine Fortress"), ground = Id("Hold Your Ground"), maiden = Id("Iron Maiden"),
                                finery = Id("Finery");
            Stats::RemoveContribution(guid, Source::Passives, Stat::AttackSpeed, fervor);
            Stats::RemoveContribution(guid, Source::Passives, Stat::CooldownReduction, fervor);
            Stats::RemoveContribution(guid, Source::Passives, Stat::LifeRegen, vigilant);
            Stats::RemoveContribution(guid, Source::Passives, Stat::ElementReduction, vigilant);
            Stats::RemoveContribution(guid, Source::Passives, Stat::MaxFury, righteous);
            Stats::RemoveContribution(guid, Source::Passives, Stat::BlockChance, ground);
            Stats::RemoveContribution(guid, Source::Passives, Stat::Armor, fortress);
            Stats::RemoveContribution(guid, Source::Passives, Stat::Thorns, maiden);
            Stats::RemoveContribution(guid, Source::Passives, Stat::Strength, finery);
            if (wanted & IronMaidenBit)
                Stats::AddContribution(guid, {Source::Passives, Stat::Thorns, maiden, Numbers::Num(maiden, "thorns_pct"),
                                              Bucket::Percent});
            if (wanted & FineryBit)
                Stats::AddContribution(guid, {Source::Passives, Stat::Strength, finery,
                                              FineryPct(Numbers::Num(finery, "primary_stat_pct"), gems), Bucket::Percent});
            if (wanted & FervorBit)
            {
                Stats::AddContribution(guid, {Source::Passives, Stat::AttackSpeed, fervor,
                                              Numbers::Num(fervor, "attack_speed_pct"), Bucket::Flat});
                Stats::AddContribution(guid, {Source::Passives, Stat::CooldownReduction, fervor,
                                              CooldownContribution(Numbers::Num(fervor, "cooldown_reduction_pct")),
                                              Bucket::Flat});
            }
            if (wanted & VigilantBit)
            {
                Stats::AddContribution(guid, {Source::Passives, Stat::LifeRegen, vigilant,
                                              Classes::HealAtLevel(Numbers::Num(vigilant, "heal_per_second_life"), player->GetLevel()), Bucket::Flat});
                for (unsigned e = 0; e < ElementCount; ++e)
                    if (VigilantReduces(static_cast<Element>(e)))
                        Stats::AddContribution(guid, {Source::Passives, Stat::ElementReduction, vigilant,
                                                      Numbers::Num(vigilant, "damage_reduction_pct"), Bucket::Flat,
                                                      static_cast<Element>(e)});
            }
            if (wanted & RighteousnessBit)
                Stats::AddContribution(guid, {Source::Passives, Stat::MaxFury, righteous,
                                              Numbers::Num(righteous, "max_pool_resource"), Bucket::Flat});
            if (wanted & HoldGroundBit)
                Stats::AddContribution(guid, {Source::Passives, Stat::BlockChance, ground,
                                              Numbers::Num(ground, "block_pct"), Bucket::Flat});
            Stats::Recompute(player);
            if (wanted & DivineFortressBit)
            {
                Stats::AddContribution(guid, {Source::Passives, Stat::Armor, fortress,
                                              DivineFortressPct(BlockChanceOf(player)), Bucket::Percent});
                Stats::Recompute(player);
            }
            Passives::RefreshModifiers(player);
        }

        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_crusader_passives", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT,
                                                        PLAYERHOOK_ON_MAP_CHANGED, PLAYERHOOK_ON_CREATURE_KILL,
                                                        PLAYERHOOK_CAN_TITAN_GRIP})
            {
            }

            // Heavenly Strength: "You can wield a two-handed weapon in your main hand while bearing a shield": the
            // core asks here wherever its Titan's Grip rule matters (equipping, the off-hand check, a zone change).
            bool OnPlayerCanTitanGrip(Player const* player) override
            {
                bool const crusader = IsCrusader(player);
                return HeavenlyStrengthGrip(crusader, crusader && Passives::Has(const_cast<Player*>(player), "Heavenly Strength"));
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsCrusader(player))
                    return;
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    State& state = states[guid];
                    state.clock += diff;
                    if (state.clock < Period)
                        return;
                    state.clock = 0;
                }
                // Heavenly Strength unpicked (or its right gone) with a two-hander and a shield still worn: the core takes
                // the shield off its own way, to the bags or by mail.
                if (GripBroken(WieldOf(player), On(player, "Heavenly Strength")))
                    player->AutoUnequipOffhandIfNeed();
                // Which of the sheet passives are on; read outside the lock (Passives::Has takes its own).
                unsigned const wanted = (On(player, "Fervor") && FervorOn(WieldOf(player)) ? FervorBit : 0u) |
                                        (On(player, "Vigilant") ? VigilantBit : 0u) |
                                        (On(player, "Righteousness") ? RighteousnessBit : 0u) |
                                        (On(player, "Divine Fortress") ? DivineFortressBit : 0u) |
                                        (On(player, "Hold Your Ground") ? HoldGroundBit : 0u) |
                                        (On(player, "Iron Maiden") ? IronMaidenBit : 0u) |
                                        (On(player, "Finery") ? FineryBit : 0u);
                // Finery follows the gems in the gear, which a socketing can change.
                unsigned const gems = (wanted & FineryBit) ? WornGems(player) : 0;
                // Divine Fortress follows the Block Chance, which gear can move: the Armor is rebuilt when it changes.
                std::int64_t const blockCenti =
                    (wanted & DivineFortressBit) ? std::int64_t(std::llround(BlockChanceOf(player) * 100.0)) : 0;
                unsigned const level = player->GetLevel();
                bool refresh = false;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    State& state = states[guid];
                    // The Block Chance read here has the Armor's own source in it only through Hold Your Ground, which
                    // is stable between looks, so the comparison settles after one rebuild.
                    // Vigilant's regeneration is the Healing table at the level: a level-up rebuilds it too.
                    refresh = state.dirty || state.signature != wanted || state.blockCenti != blockCenti || state.gems != gems ||
                              Classes::BuiltAtOtherLevel(state.level, level);
                    state.level = level;
                    state.signature = wanted;
                    state.blockCenti = blockCenti;
                    state.gems = gems;
                    state.dirty = false;
                }
                if (refresh)
                    Refresh(player, wanted, gems);
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                states.erase(player->GetGUID().GetRawValue());
            }

            void OnPlayerMapChanged(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                states[player->GetGUID().GetRawValue()].dirty = true;
            }

            // Indestructible: "gain {heal_per_hit_life} Life per Kill" while the save lasts.
            void OnPlayerCreatureKill(Player* killer, Creature*) override
            {
                if (!On(killer, "Indestructible"))
                    return;
                bool active;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    active = states[killer->GetGUID().GetRawValue()].fatal.Active(Now());
                }
                if (active)
                    Heal(killer, killer, Id("Indestructible"), Classes::HealAtLevel(Num("Indestructible", "heal_per_hit_life"), killer->GetLevel()));
            }
        };

        class DamageHook final : public UnitScript
        {
        public:
            DamageHook()
                : UnitScript("dc_crusader_passives_damage", true, {UNITHOOK_ON_DAMAGE})
            {
            }

            void OnDamage(Unit* /*attacker*/, Unit* victim, std::uint32_t& damage) override
            {
                if (Player* player = victim ? victim->ToPlayer() : nullptr)
                    Damage(player, damage);
            }
        };

        // The cast of a Crusader skill, after the core has installed its cooldown and taken its cost: Wrathful and Lord
        // Commander.
        class CastHook final : public AllSpellScript
        {
        public:
            CastHook()
                : AllSpellScript("dc_crusader_passives_cast", {ALLSPELLHOOK_ON_CAST})
            {
            }

            void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override
            {
                Player* player = caster ? caster->ToPlayer() : nullptr;
                auto const* row = info ? Shells::FindAbility(info->Id) : nullptr;
                if (!player || !row || spell->IsTriggered() || !IsCrusader(player))
                    return;
                // Wrathful: "Each point of Wrath spent heals you for {heal_per_hit_life} Life." The Health Globe
                // Healing Bonus share adds nothing: Torment has no such stat yet.
                if (double const wrath = WrathSpent(player, spell); wrath > 0 && On(player, "Wrathful"))
                    Heal(player, player, Id("Wrathful"), WrathfulHeal(Classes::HealAtLevel(Num("Wrathful", "heal_per_hit_life"), player->GetLevel()), wrath));
                // Lord Commander: "The cooldown of Steed Charge is reduced by ... and Bombardment by ...", Towering Shield:
                // "Reduce the cooldown of Shield Glare by ...": the cooldown the core installed is shortened by the share, for
                // every rune of the skill.
                double cutPct = 0;
                if (std::string_view const qualifier = LordCommanderQualifier(row->skill);
                    !qualifier.empty() && On(player, "Lord Commander"))
                    cutPct = Numbers::Num(Id("Lord Commander"), "cooldown_reduction_pct", qualifier);
                else if (ToweringCooldownSkill(row->skill) && On(player, "Towering Shield"))
                    cutPct = Num("Towering Shield", "cooldown_reduction_pct");
                if (cutPct > 0)
                    if (std::uint32_t const left = player->GetSpellCooldownDelay(info->Id))
                        if (std::uint32_t const cut = CooldownCut(left, cutPct))
                            Combat::SendSkillCooldown(player, info->Id, left - cut);
            }
        };
    } // namespace

    void Multipliers(Player* player, std::uint32_t spellId, std::vector<std::pair<std::string, double>>& out)
    {
        if (!IsCrusader(player))
            return;
        // Separate multipliers of their own on the hit, as D3's passives are.
        if (Passives::Has(player, "Heavenly Strength"))
            if (double const pct =
                    HeavenlyStrengthPct(WieldOf(player), Num("Heavenly Strength", "damage_dealt_reduction_pct"));
                pct > 0)
                AddFactor(out, "Heavenly Strength", -pct);
        // "The amount of damage dealt by your weapon is increased by {damage_bonus_pct}": every hit of a skill is
        // weapon damage.
        if (Passives::Has(player, "Holy Cause"))
            AddFactor(out, "Holy Cause", Num("Holy Cause", "damage_bonus_pct"));
        if (Passives::Has(player, "Indestructible"))
        {
            bool active;
            {
                std::lock_guard<std::mutex> guard(mutex);
                active = states[player->GetGUID().GetRawValue()].fatal.Active(Now());
            }
            if (active)
                AddFactor(out, "Indestructible", Num("Indestructible", "damage_bonus_pct"));
        }
        if (auto const* row = Shells::FindAbility(spellId); row && BluntSkill(row->skill) && Passives::Has(player, "Blunt"))
            AddFactor(out, "Blunt", Num("Blunt", "damage_bonus_pct"));
        if (auto const* row = Shells::FindAbility(spellId);
            row && ToweringDamageSkill(row->skill) && Passives::Has(player, "Towering Shield"))
            AddFactor(out, "Towering Shield", Num("Towering Shield", "damage_bonus_pct"));
        if (auto const* row = Shells::FindAbility(spellId);
            row && LordCommanderDamage(row->skill) && Passives::Has(player, "Lord Commander"))
            AddFactor(out, "Lord Commander", Num("Lord Commander", "damage_bonus_pct"));
    }

    double AttackSpeed(Player* player, std::uint32_t spellId, double base)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!player || base <= 0 || !row || !FanaticismSkill(row->skill) || !On(player, "Fanaticism"))
            return base;
        auto const sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        if (!sheet)
            return base;
        return FanaticismAps(base, (*sheet)[Stat::AttackSpeed], Num("Fanaticism", "attack_speed_pct"),
                             DC::NumericData::Rule("attack_speed_cap"));
    }

    void Connected(Player* player, std::uint32_t spellId)
    {
        if (!On(player, "Righteousness"))
            return;
        // "Your primary skills generate an additional {generated_resource} Wrath": paid beside the skill's own, through
        // the same factor of the Crusader's items.
        if (double const extra = RighteousnessWrath(Classes::CategoryOf(spellId) == "Primary",
                                                    Num("Righteousness", "generated_resource"));
            extra > 0)
            PayWrath(player, spellId, extra);
    }

    void Blocked(Player* player)
    {
        // "Blocking an attack generates {gain_resource} Wrath."
        if (On(player, "Insurmountable"))
            GainWrath(player, Id("Insurmountable"), InsurmountableWrath(Num("Insurmountable", "gain_resource")));
        // "Whenever you successfully block, you gain {heal_life} Life."
        if (On(player, "Renewal"))
            Heal(player, player, Id("Renewal"), RenewalHeal(Classes::HealAtLevel(Num("Renewal", "heal_life"), player->GetLevel())));
    }

    double LongArmSeconds(Player* player)
    {
        return On(player, "Long Arm of the Law") ? Num("Long Arm of the Law", "duration_seconds") : 0.0;
    }

    void Landed(Player* player, std::uint32_t spellId)
    {
        if (!On(player, "Holy Cause"))
            return;
        // "Whenever you deal Holy damage, you heal up to {heal_pct} of your total Life."
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (info && Shells::FindAbility(spellId))
            Heal(player, player, Id("Holy Cause"),
                 HolyCauseHeal((info->GetSchoolMask() & SPELL_SCHOOL_MASK_HOLY) != 0, player->GetMaxHealth(),
                               Num("Holy Cause", "heal_pct")));
    }

    double DodgeFactor(Unit const* unit)
    {
        Player* player = unit && unit->IsPlayer() ? const_cast<Unit*>(unit)->ToPlayer() : nullptr;
        return Passive::DodgeFactor(On(player, "Hold Your Ground"));
    }

    void Damage(Player* victim, std::uint32_t& damage)
    {
        if (!damage || !IsCrusader(victim))
            return;
        // "When you receive fatal damage, you instead become immune to damage, ...": the hit is dropped, and so is
        // every hit until the time is out; the bonus and the Life per Kill ride the same time.
        std::uint32_t const id = Id("Indestructible");
        bool const has = id && Passives::Has(victim, "Indestructible");
        std::uint64_t const now = Now();
        bool dropped = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Fatal& fatal = states[victim->GetGUID().GetRawValue()].fatal;
            dropped = fatal.Active(now) || (has && fatal.Save(now, damage, victim->GetHealth(),
                                                              Millis(Numbers::Num(id, "internal_cooldown_seconds")),
                                                              Millis(Numbers::Num(id, "duration_seconds"))));
        }
        if (dropped)
            damage = 0;
    }

    void Register()
    {
        new Update();
        new DamageHook();
        new CastHook();
    }
} // namespace DC::Combat::Crusader::Passive
