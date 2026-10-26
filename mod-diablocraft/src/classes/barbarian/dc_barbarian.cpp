#include "dc_barbarian.h"
#include "dc_barbarian_internal.h"
#include "../follower/dc_follower_skills.h"
#include "dc_barbarian_rend.h"
#include "dc_barbarian_hammer_of_the_ancients.h"
#include "dc_barbarian_ancient_spear.h"
#include "dc_barbarian_seismic_slam.h"
#include "dc_barbarian_leap.h"
#include "dc_barbarian_ground_stomp.h"
#include "dc_barbarian_zones.h"
#include "dc_barbarian_earthquake.h"
#include "dc_barbarian_whirlwind.h"
#include "dc_barbarian_avalanche.h"
#include "dc_barbarian_furious_charge.h"
#include "dc_barbarian_revenge.h"
#include "dc_barbarian_overpower.h"
#include "dc_barbarian_wrath_of_the_berserker.h"
#include "dc_barbarian_threatening_shout.h"
#include "dc_barbarian_battle_rage.h"
#include "dc_barbarian_war_cry.h"
#include "dc_barbarian_collisions.h"
#include "dc_barbarian_ignore_pain.h"
#include "dc_barbarian_sprint.h"
#include "../../combat/dc_buff_values.h"
#include "../../combat/dc_gem_powers.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_proc_math.h"
#include "../../combat/dc_passives.h"
#include "../../combat/dc_combat.h"
#include "../dc_classes.h"
#include "dc_barbarian_call_of_the_ancients.h"
#include "../dc_resources.h"
#include "../../stats/dc_stats.h"
#include "CellImpl.h"
#include "Chat.h"
#include "DatabaseEnv.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Log.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Pet.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellScript.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Timer.h"
#include "WorldSession.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <mutex>
#include <string>
#include <unordered_map>

namespace DC::Combat::Abilities
{
    using namespace Shared;
    namespace Shared
    {
        void Refresh(Player* p)
        {
            // Keys are private to the marker block; item/paragon contributions survive.
            for (auto const& row : Shells::Abilities)
            {
                if (!HasMarker(row))
                    continue;
                for (unsigned e = 0; e < ElementCount; ++e)
                    Stats::RemoveContribution(p->GetGUID().GetRawValue(), Source::Temporary, Stat::SingleResistance,
                                              uint64(AuraId(row.id)) * ElementCount + e);
                for (Stat stat : {Stat::CritChance, Stat::AttackSpeed, Stat::MovementSpeed, Stat::Armor,
                                  Stat::AllResistance, Stat::LifePercent, Stat::LifeRegen, Stat::SpecificReduction})
                    Stats::RemoveContribution(p->GetGUID().GetRawValue(), Source::Temporary, stat, AuraId(row.id));
            }
            Stats::Recompute(p);
            auto baseline = Stats::Get(p->GetGUID().GetRawValue());
            Sprint::OnRefresh(p);
            IgnorePain::OnRefresh(p);
            // Buff icons build 2 (data/class_buffs.csv): the seconds Hardened Wrath's extra Armor has left, and the
            // enemies Into the Fray counts; each is the buff the player wears for it.
            double wrathSeconds = 0;
            std::size_t frayEnemies = 0;
            WarCry::OnRefresh(p, baseline, wrathSeconds);
            BattleRage::OnRefresh(p, frayEnemies);
            BuffValues::Show(p, WrathBuff(), wrathSeconds > 0 ? 1 : 0, wrathSeconds);
            BuffValues::Show(p, FrayBuff(), unsigned(frayEnemies));
            Wrath::OnRefresh(p);
            Leap::OnRefresh(p);
            Overpower::OnRefresh(p);
            Revenge::OnRefresh(p);
            Sprint::OnRefreshAllied(p);
            Stats::Recompute(p);
        }
    } // namespace Shared


    void ReduceSkillCooldown(Player* p, char const* skill, double milliseconds)
    {
        Reduce(p, skill, milliseconds);
    }

    void ApplySkillBleed(Player* p, Unit* target, char const* skill)
    {
        auto r = Active(p, skill);
        if (!r)
            r = Base(skill);
        if (!r || !target || !Combat::ApplySkillBleed(p, target, r->id))
            return;
        HitEffects(p, target, r->id);
    }

    bool CutRunningCooldown(Player* p, double milliseconds)
    {
        std::vector<std::string> running;
        for (auto const& r : Shells::Abilities)
        {
            if (!p->GetSpellCooldownDelay(r.id) || Classes::CategoryOf(r.id) == "Primary")
                continue;
            SpellInfo const* info = sSpellMgr->GetSpellInfo(r.id);
            if (info && (info->RecoveryTime || info->CategoryRecoveryTime) &&
                std::find(running.begin(), running.end(), r.skill) == running.end())
                running.push_back(r.skill);
        }
        if (running.empty())
            return false;
        Reduce(p, running[urand(0, running.size() - 1)].c_str(), milliseconds);
        return true;
    }

    void InvalidateBar(Player* p)
    {
        std::lock_guard<std::recursive_mutex> lock(mutex);
        bars.erase(p->GetGUID().GetRawValue());
        Passives::Invalidate(p);
    }

    double DamageBonus(Player* p)
    {
        double result = 0;
        BattleRage::OnDamageBonus(p, result);
        return result;
    }
    void Multipliers(Player* p, DC::Combat::Factors& out)
    {
        Wrath::OnMultipliers(p, out);
    }
    double TargetBonus(Unit* u)
    {
        double bonus = ThreateningShout::OnTargetBonus(u);
        Rend::OnTargetBonus(u, bonus);
        return bonus;
    }
    double DodgeChance(Player const* p)
    {
        double chance = 0;
        Sprint::OnDodge(p, chance);
        WarCry::OnDodge(p, chance);
        Wrath::OnDodge(p, chance);
        return std::clamp(chance + GemPowers::Dodge(p), 0.0, 100.0);
    }
    void ReflectMelee(Player* p, Unit* attacker, uint32& damage)
    {
        if (!p || !attacker || !damage)
            return;
        Overpower::OnReflect(p, attacker, damage);
    }
    double IncomingFactor(Unit* attacker)
    {
        return ThreateningShout::OnIncomingFactor(attacker);
    }
    bool Ready(Player* p, uint32 id)
    {
        auto r = Shells::FindAbility(id);
        if (!r)
            return true;
        std::lock_guard<std::recursive_mutex> lock(mutex);
        auto& s = states[p->GetGUID().GetRawValue()];
        if (std::string(r->skill) == "Avalanche" && Rune(*r, "Tectonic Rift") && !s.avalanche.initialized)
        {
            s.avalanche.count = unsigned(Numbers::Num(r->id, "charge_count"));
            s.avalanche.initialized = true;
        }
        if (std::string(r->skill) == "Revenge")
            return s.revenge.count > 0;
        if (std::string(r->skill) == "Furious Charge")
            return s.charge.count > 0;
        if (std::string(r->skill) == "Avalanche" && Rune(*r, "Tectonic Rift"))
            return s.avalanche.count > 0;
        return true;
    }
    bool UsesCharges(uint32 id)
    {
        auto r = Shells::FindAbility(id);
        if (!r)
            return false;
        std::string const skill = r->skill;
        return skill == "Revenge" || skill == "Furious Charge" || (skill == "Avalanche" && Rune(*r, "Tectonic Rift"));
    }
    // `skills_active` (Remorseless): Call of the Ancients is active while its Ancients live; any other skill while its buff is on the player.
    bool SkillActive(Player const* p, std::string const& skill)
    {
        if (!p)
            return false;
        if (skill == "Call of the Ancients")
            return Classes::Ancients::Active(p);
        return Buff(p, skill.c_str()) != nullptr;
    }

    void Cast(Player* p, uint32 id, std::vector<Unit*> const& targets, Position const* center, double extraDamage)
    {
        auto r = Shells::FindAbility(id);
        if (!r)
            return;
        auto b = Base(r->skill);
        Passives::Cast(p,id);
        std::string skill = r->skill;
        std::lock_guard<std::recursive_mutex> lock(mutex);
        auto& s = states[p->GetGUID().GetRawValue()];
        if (skill == "Sprint")
            Sprint::OnCast(p, r, b);
        else if (skill == "Ignore Pain")
            IgnorePain::OnCast(p, id, r, b);
        else if (skill == "War Cry")
            WarCry::OnCast(p, id, r, b, targets);
        else if (skill == "Battle Rage")
            BattleRage::OnCast(p, id, r, b);
        else if (skill == "Threatening Shout")
            ThreateningShout::OnCast(p, id, r, b, targets);
        else if (skill == "Call of the Ancients")
            Classes::Ancients::Summon(p, id);
        else if (skill == "Wrath of the Berserker")
            Wrath::OnCast(p, r, b);
        else if (skill == "Overpower")
            Overpower::OnCast(p, id, r, targets);
        else if (skill == "Revenge")
            Revenge::OnCast(p, id, r, b, targets, s);
        else if (skill == "Furious Charge")
            FuriousCharge::OnCast(p, id, r, b, targets, s);
        else if (skill == "Avalanche")
            Avalanche::OnCast(p, id, r, b, targets, center, s);
        else if (skill == "Earthquake" && center)
            Earthquake::OnCast(p, r, b, center);
        else if (skill == "Ground Stomp")
            GroundStomp::OnCast(p, r, b, targets);
        else if (skill == "Leap")
            Leap::OnCast(p, r, targets);
        else if (skill == "Seismic Slam")
            SeismicSlam::OnCast(p, id, r, targets, center, extraDamage, s);
        Refresh(p);
    }
    void HitEffects(Player* p, Unit* target, uint32 id)
    {
        auto r = Shells::FindAbility(id);
        if (!r)
            return;
        auto b = Base(r->skill);
        std::string skill = r->skill;
        if (skill == "Leap")
            Leap::OnHit(p, target, r, b);
        if (skill == "Ancient Spear")
            AncientSpear::OnHit(p, target, r);
        if (skill == "Seismic Slam")
            SeismicSlam::OnHit(p, target, r);
        if (skill == "Hammer of the Ancients")
            Hammer::OnHit(p, target, r);
        if (skill == "Rend")
            Rend::OnHit(p, target, r, b);
    }
    void LaunchEffects(Player* p, uint32 id)
    {
        Leap::OnLaunch(p, id);
    }
    void RendTick(Player* p, uint32 id)
    {
        Rend::OnTick(p, id);
    }
    void Spent(Player* p, double fury)
    {
        Stats::FurySpent(p, fury); // Life per Fury Spent, from the sheet
        Classes::Ancients::Spent(p, fury);
        Passives::Spent(p, fury);
        ItemPowers::Spent(p, fury);
        if (fury <= 0)
            return;
        std::lock_guard<std::recursive_mutex> lock(mutex);
        auto& s = states[p->GetGUID().GetRawValue()];
        Avalanche::OnSpent(p, s, fury);
        IgnorePain::OnSpent(p, fury);
        Wrath::OnSpent(p, fury);
    }
    void CriticalHit(Player* p, Unit* target, uint32 spellId, double damage)
    {
        CriticalResource(p, spellId); // Arcane Power on Critical Hit, from the sheet
        GemPowers::Critical(p, target, spellId); // Pain Enhancer, before this file's own lock is taken
        std::lock_guard<std::recursive_mutex> lock(mutex);
        Overpower::OnCritical(p, spellId);
        Hammer::OnCritical(p, spellId);
        BattleRage::OnCritical(p, damage);
        Wrath::OnCritical(p, target, spellId);
        Classes::Follower::Critical(p); // the Scoundrel's Hysteria
    }
    void Taken(Player* p, Unit* attacker, uint32 damage)
    {
        Revenge::OnTaken(p, attacker, damage);
    }
    double CritBonus(std::string const& skill, double fury)
    {
        return Hammer::OnCritBonus(skill, fury);
    }
    bool BurstsAtFirstImpact(std::string const& skill, std::string const& rune)
    {
        return AncientSpear::BurstsAtFirstImpact(skill, rune);
    }
    void Begin(std::string const& skill, std::string const& rune, uint32 id, double fury, double cost, double& damagePct, double& extraDamage)
    {
        SeismicSlam::OnBegin(skill, rune, id, fury, cost, extraDamage);
        AncientSpear::OnBegin(skill, rune, id, fury, damagePct);
    }
    bool SpendsEveryPoint(std::string const& skill, std::string const& rune)
    {
        return SeismicSlam::SpendsEveryPoint(skill, rune) ||
               AncientSpear::SpendsEveryPoint(skill, rune);
    }
    bool LaunchesNoHit(std::string const& skill)
    {
        return Earthquake::LaunchesNoHit(skill);
    }
    bool DamageOverTime(std::string const& skill)
    {
        return Earthquake::DamageOverTime(skill) ||
               Rend::DamageOverTime(skill);
    }
    bool Toggle(Player* p, uint32 id)
    {
        return Whirlwind::OnToggle(p, id);
    }
    bool KeepsSheetDamage(std::string const& skill, std::string const& rune)
    {
        return Whirlwind::KeepsSheetDamage(skill, rune) ||
               Earthquake::KeepsSheetDamage(skill, rune) ||
               SeismicSlam::KeepsSheetDamage(skill, rune);
    }
    bool PaysByTick(std::string const& skill)
    {
        return Whirlwind::PaysByTick(skill);
    }
    std::optional<bool> Resolve(Player* player, Unit* target, std::uint32_t spellId, std::string const& skill, std::string const& rune)
    {
        if (auto own = Rend::OnResolve(player, target, spellId, skill))
            return own;
        return Avalanche::OnResolve(skill, rune);
    }
    bool Bleed(Player* player, Unit* target, std::uint32_t spellId, std::string const& skill, bool keepRunning)
    {
        return Rend::Apply(player, target, spellId, skill, keepRunning);
    }
    namespace
    {
        class Command final : public CommandScript
        {
        public:
            Command()
                : CommandScript("dc_abilities_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable abilities = {{"abilities", Report, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable root = {{"dc", abilities}};
                return root;
            }
            static bool Report(ChatHandler* handler)
            {
                auto p = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!p)
                    return false;
                std::lock_guard<std::recursive_mutex> lock(mutex);
                auto& state = states[p->GetGUID().GetRawValue()];
                Factors multipliers;
                Multipliers(p, multipliers);
                handler->PSendSysMessage("Ability buffs: damage +{}% x{}, dodge {}%; Revenge charges {}; Furious Charge "
                                         "charges {}; Avalanche charges {}",
                                         DamageBonus(p), Product(multipliers), DodgeChance(p), state.revenge.count, state.charge.count,
                                         state.avalanche.count);
                for (auto const& [name, value] : tuning)
                    handler->PSendSysMessage("{} = {} (tunable)", name, value);
                return true;
            }
        };
        class World final : public WorldScript
        {
        public:
            World()
                : WorldScript("dc_abilities_world", {WORLDHOOK_ON_STARTUP,WORLDHOOK_ON_AFTER_CONFIG_LOAD})
            {
            }
            void OnAfterConfigLoad(bool reload)override{if(reload)OnStartup();}
            void OnStartup() override
            {
                std::lock_guard<std::recursive_mutex>guard(mutex);
                if (auto rows = WorldDatabase.Query("SELECT name,tuned_value FROM dc_ability_tuning"))
                    do
                    {
                        auto f = rows->Fetch();
                        tuning[f[0].Get<std::string>()] = f[1].Get<double>();
                    } while (rows->NextRow());
                else
                    LOG_ERROR("server", "Missing dc_ability_tuning; proc chances fail closed at zero");
            }
        };
        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_abilities_update",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }
            void OnPlayerUpdate(Player* p, uint32 diff) override
            {
                if (p->getClass() != CLASS_WARRIOR)
                    return;
                std::lock_guard<std::recursive_mutex> lock(mutex);
                auto& s = states[p->GetGUID().GetRawValue()];
                p->SetFloatValue(PLAYER_DODGE_PERCENTAGE, float(DodgeChance(p)));
                FuriousCharge::OnUpdate(p, s, diff);
                Avalanche::OnUpdate(p, s, diff);
                BattleRage::OnUpdate(p, s, diff);
                if (!p->IsAlive())
                {
                    StopWhirlwind(p);
                    s.devils.clear();
                    s.zones.clear();
                    s.collisions.clear();
                    s.criticals.clear();
                    return;
                }
                Whirlwind::OnUpdate(p, s, diff);
                Sprint::OnUpdate(p, s, diff);
                Collisions::OnUpdate(p, s);
                Zones::OnUpdate(p, s, diff);
                // Refresh on aura transitions and dynamic effects; avoid recalculating an
                // unchanged sheet every frame. Expiry is owned by the core aura clock.

                uint64 signature = 0;
                for (auto const& row : Shells::Abilities)
                    if (auto aura = HasMarker(row) ? p->GetAura(AuraId(row.id)) : nullptr)
                        signature = signature * 131 + row.id;
                WarCry::OnSignature(p, signature);
                BattleRage::OnSignature(p, signature);
                auto key = p->GetGUID().GetRawValue();
                auto sheet = Stats::Get(key);
                bool changed =
                    sheet && (lastSheets.find(key) == lastSheets.end() || lastSheets[key].values != sheet->values ||
                              lastSheets[key].resistance != sheet->resistance);
                if (signatures[key] != signature || changed)
                {
                    signatures[key] = signature;
                    Refresh(p);
                    if (auto refreshed = Stats::Get(key))
                        lastSheets[key] = *refreshed;
                }
            }
            void OnPlayerLogout(Player* p) override
            {
                // The core saves an aura with the character; these two have no marker to bring them back.
                BuffValues::Show(p, WrathBuff(), 0);
                BuffValues::Show(p, FrayBuff(), 0);
                Clear(p);
            }
            void OnPlayerMapChanged(Player* p) override
            {
                std::lock_guard<std::recursive_mutex> lock(mutex);
                auto& state = states[p->GetGUID().GetRawValue()];
                StopWhirlwind(p);
                state.devils.clear();
                state.zones.clear();
                state.collisions.clear();
                state.criticals.clear();
            }

        private:
            std::unordered_map<uint64, uint64> signatures;
            std::unordered_map<uint64, StatSheet> lastSheets;
            void Clear(Player* p)
            {
                std::lock_guard<std::recursive_mutex> lock(mutex);
                StopWhirlwind(p);
                states.erase(p->GetGUID().GetRawValue());
                bars.erase(p->GetGUID().GetRawValue());
        Passives::Invalidate(p);
                signatures.erase(p->GetGUID().GetRawValue());
                lastSheets.erase(p->GetGUID().GetRawValue());
                for (auto const& r : Shells::Abilities)
                    if (HasMarker(r))
                        p->RemoveAurasDueToSpell(AuraId(r.id));
                Refresh(p);
            }
        };
    } // namespace
    void RegisterScripts()
    {
        new World();
        new Update();
        new Command();
        Overpower::RegisterScripts();
        Rend::RegisterScripts();
    }
} // namespace DC::Combat::Abilities
