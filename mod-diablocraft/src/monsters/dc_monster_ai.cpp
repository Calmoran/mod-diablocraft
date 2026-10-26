/*
 * World of DiabloCraft - rift AI (09-rifts F2, F5).
 *
 * Split out of dc_rifts.cpp; targeting is done with
 * short scored commitments (02-combat monster targeting). Guardian mechanics
 * and the spawn/reward paths remain independent of target selection.
 *
 * Internal to the rifts folder; other modules include dc_rifts.h.
 */

#include "dc_monster_ai.h"
#include "../rifts/dc_charm.h"
#include "dc_family_ai.h"
#include "../rifts/dc_monster_targeting.h"

#include "../rifts/dc_rifts.h"
#include "affixes/dc_affixes.h"
#include "../rifts/dc_rift_spawner.h"
#include "../rifts/dc_gr_rewards.h"
#include "../rifts/dc_rift_quests.h"
#include "../rifts/dc_rifts_internal.h"
#include "../classes/barbarian/dc_barbarian_call_of_the_ancients.h"
#include "../combat/dc_charm_effect.h"
#include "../combat/dc_combat.h"
#include "../difficulty/dc_difficulty.h"
#include "../loot/dc_corpse_loot.h"
#include "../loot/dc_corpse_rules.h"
#include "../loot/dc_loot.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_blood_shards.h"
#include "../common/dc_world.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "CombatAI.h"
#include "Creature.h"
#include "CombatManager.h"
#include "PathGenerator.h"
#include "SpellAuraEffects.h"
#include "ScriptedCreature.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "ThreatManager.h"
#include "DatabaseEnv.h"
#include "GridNotifiers.h"
#include "Group.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "World.h"
#include "WorldSession.h"

#include <algorithm>
#include <chrono>
#include <functional>
#include <stdexcept>
#include <unordered_map>
#include <cmath>
#include <memory>
#include <mutex>
#include <random>
#include <string>
#include <vector>

namespace DC::Rifts
{
// Moved with the guardian code in the split; nothing here is
// referenced outside this file any more.
// F5 / 09 §4. The guardian is not an affix and its numbers are not in
// 13-elite-affixes, so they stay here: a multiple of the guardian's own average
// swing, and its two ability timers.
// The guardian's numbers now live in dc_tunables, category `rifts`, and are
// read per use rather than compiled in: `.dc tunables set rifts <name> <n>`
// changes them without a restart. Audit rows 65 and 67-72; the rows carry each
// one's origin.
inline float GuardianSpawnRangeYards()
{
    return static_cast<float>(DC::Tunables::Get("rifts", "guardian_spawn_range_yards"));
}
inline double GuardianNovaDamage()
{
    return DC::Tunables::Get("rifts", "guardian_nova_damage_multiplier");
}
inline double GuardianLeapDamage()
{
    return DC::Tunables::Get("rifts", "guardian_leap_damage_multiplier");
}
inline float GuardianNovaRadiusYards()
{
    return static_cast<float>(DC::Tunables::Get("rifts", "guardian_nova_radius_yards"));
}
inline std::uint32_t GuardianFirstMs()
{
    return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "guardian_first_ability_ms"));
}
inline std::uint32_t GuardianRepeatMs()
{
    return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "guardian_ability_repeat_ms"));
}
// Stored as a percent, which is what the aura wants; the code used to hold the
// fraction and multiply by 100. D3 publishes 50 (Bloodmaw, literal-audit-sources-2
// row 72); the literal here was 30.
inline float GuardianFrenzyHastePct()
{
    return static_cast<float>(DC::Tunables::Get("rifts", "guardian_frenzy_haste_pct"));
}

    namespace
    {
        std::mutex targetingMutex;
        std::unordered_map<std::string, Targeting::Profile> targetingProfiles;

        bool LoadTargetingProfiles()
        {
            QueryResult rows = WorldDatabase.Query(
                "SELECT profile,lock_seconds,jitter_percent,recency_weight,proximity_weight,reachability_weight,"
                "recency_window_seconds,recency_max_yards,candidate_max_yards,unreachable_penalty,switch_margin "
                "FROM dc_monster_targeting");
            std::unordered_map<std::string, Targeting::Profile> loaded;
            if (rows)
                do
                {
                    Field* f = rows->Fetch();
                    std::string name = f[0].Get<std::string>();
                    Targeting::Profile p{f[1].Get<double>(), f[2].Get<double>(), f[3].Get<double>(), f[4].Get<double>(),
                                         f[5].Get<double>(), f[6].Get<double>(), f[7].Get<double>(), f[8].Get<double>(),
                                         f[9].Get<double>(), f[10].Get<double>()};
                    if ((name != "normal" && name != "elite" && name != "guardian") || !Targeting::Valid(p) ||
                        !loaded.emplace(name, p).second)
                    {
                        LOG_ERROR("server", "[DC targeting] invalid or duplicate profile {}; cache unchanged", name);
                        return false;
                    }
                } while (rows->NextRow());
            if (loaded.size() != 3 || loaded.at("guardian").lockSeconds <= loaded.at("normal").lockSeconds ||
                loaded.at("guardian").switchMargin <= loaded.at("normal").switchMargin)
            {
                LOG_ERROR("server", "[DC targeting] missing profiles or guardian is not stricter; apply "
                                    "rifts_0012/0013; cache unchanged");
                return false;
            }
            {
                std::lock_guard<std::mutex> lock(targetingMutex);
                targetingProfiles = std::move(loaded);
            }
            LOG_INFO("server", "[DC targeting] loaded normal, elite and guardian tunable profiles");
            return true;
        }

        double TargetingNow()
        {
            return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
        }
    } // namespace

    // One authority for aggro, core victim selection, damage locks and native taunts.
    // The list remains a COMBAT relationship list, not a damage/healing scoreboard.
    class RiftTargetAI : public AggressorAI
    {
    public:
        explicit RiftTargetAI(Creature* creature, bool guardian = false)
            : AggressorAI(creature)
            , _guardian(guardian)
        {
        }

        std::string ProfileName() const
        {
            return _guardian ? "guardian" : (IsPromotedElite(me) ? "elite" : "normal");
        }

        Targeting::Profile Profile() const
        {
            std::lock_guard<std::mutex> lock(targetingMutex);
            return targetingProfiles.at(ProfileName());
        }

        bool CanAIAttack(Unit const* target) const override
        {
            // SelectVictim also runs outside UpdateAI. Mark all other references
            // offline so an unavailable fixate cannot fall back to accumulated threat
            // or an assist/formation target while the commitment still holds.
            return target && _policy.Current() && target->GetGUID().GetRawValue() == _policy.Current();
        }

        void AttackStart(Unit* requested) override
        {
            if (_busy)
                return;
            // A core aggro/assist request starts the first commitment, but cannot
            // switch an existing one. Immediate damage locks are in DamageTaken.
            if (!_policy.Current() && ValidTarget(requested))
            {
                auto p = Profile();
                if (IsActor(requested) && me->GetExactDist(requested) <= p.candidateMaxYards && Reachable(requested))
                {
                    Targeting::Candidate c{requested->GetGUID().GetRawValue(), me->GetExactDist(requested), true};
                    _policy.Choose({c}, TargetingNow(), p, Jitter());
                    ApplyChoice(requested);
                }
            }
            else if (Unit* selected = Selected())
                AggressorAI::AttackStart(selected);
        }

        void DamageTaken(Unit* attacker, uint32& damage, DamageEffectType, SpellSchoolMask) override
        {
            if (!damage || _busy || !attacker)
                return;
            // Owned pets/Ancients contribute recency to their player, not a second
            // aggro actor. A charmed monster is its own actor: the pack answers it, not its charmer.
            // Healing and damage amounts never enter this state.
            Unit* player = IsCharmedMonster(attacker->ToCreature()) ? attacker
                                                                     : attacker->GetCharmerOrOwnerPlayerOrPlayerItself();
            if (!ValidTarget(player))
                return;
            double now = TargetingNow();
            _hits[player->GetGUID().GetRawValue()] = now;
            if (NativeTaunter())
            {
                Tick();
                return;
            }
            _policy.ReleaseTaunt(now);
            if (_policy.Current() && !ValidTarget(Selected()))
                _policy.Clear();
            auto p = Profile();
            Targeting::Candidate c{player->GetGUID().GetRawValue(), me->GetExactDist(player), false, 0};
            // No path calculations for hits during a commitment, and no extension
            // of its deadline. The next release scores the recorded damage.
            if (!_policy.Taunted() && _policy.Remaining(now) <= 0 && c.distance <= p.recencyMaxYards)
            {
                c.reachable = Reachable(player);
                if (_policy.Hit(c, now, p, Jitter()))
                    ApplyChoice(player);
            }
        }

        void Tick()
        {
            if (_busy || !me->IsAlive() || !me->IsInWorld())
                return;
            auto p = Profile();
            double now = TargetingNow();
            Unit* taunt = NativeTaunter();
            if (taunt)
            {
                _policy.Choose({}, now, p, Jitter(), taunt->GetGUID().GetRawValue());
                if (me->GetThreatMgr().GetFixateTarget() != taunt || me->GetVictim() != taunt || !IsEngaged())
                    ApplyChoice(taunt);
                me->GetThreatMgr().ResetAllThreat();
                return;
            }
            Unit* current = Selected();
            if (!_policy.Taunted() && ValidTarget(current) && _policy.Remaining(now) > 0)
            {
                // Leave path/reachability alone during a lock; a moving target does
                // not break a commitment. Death/logout/GM/phase changes do.
                me->GetThreatMgr().ResetAllThreat();
                if (!IsEngaged() || me->GetThreatMgr().GetFixateTarget() != current)
                    ApplyChoice(current);
                return;
            }
            std::vector<Targeting::Candidate> candidates;
            // The actors are the players and the monsters they have charmed.
            if (IsEngaged() || me->IsInCombat() || _guardian)
                me->GetMap()->DoForAllPlayers(
                    [&](Player* player)
                    {
                        for (Unit* actor : ActorsOf(player))
                        {
                            if (!ValidTarget(actor) || me->GetExactDist(actor) > p.candidateMaxYards)
                                continue;
                            auto it = _hits.find(actor->GetGUID().GetRawValue());
                            double age = it == _hits.end() ? std::numeric_limits<double>::infinity() : now - it->second;
                            candidates.push_back(Evaluate(actor, age));
                        }
                    });
            else
                me->GetMap()->DoForAllPlayers(
                    [&](Player* player)
                    {
                        for (Unit* actor : ActorsOf(player))
                            // Native idle aggro distance and LOS remain intact. Range zero
                            // in SelectNearestTarget is VISIBILITY range, not aggro range.
                            if (me->HasReactState(REACT_AGGRESSIVE) && ValidTarget(actor) && me->IsHostileTo(actor) &&
                                me->GetExactDist(actor) <=
                                    std::min(p.candidateMaxYards, double(me->GetAttackDistance(actor))) &&
                                me->IsWithinLOSInMap(actor))
                                candidates.push_back(Evaluate(actor));
                    });
            _policy.Choose(candidates, now, p, Jitter());
            // Bound damage history to this profile's recency window.
            for (auto it = _hits.begin(); it != _hits.end();)
                if (now - it->second > p.recencyWindowSeconds)
                    it = _hits.erase(it);
                else
                    ++it;
            if (Unit* selected = Selected())
                ApplyChoice(selected);
            else
                Park();
        }

        // The core parks this AI for the length of a charm (Unit::UpdateCharmAI swaps in PetAI and keeps this object) and
        // calls this on it as the charm lands. Nothing here runs while parked, so what the fight held is dropped now:
        // when the AI comes back the monster picks afresh (the core has already pointed it at its charmer, and no
        // commitment of ours stands in the way).
        void OnCharmed(bool apply) override
        {
            if (apply)
            {
                _policy.Clear();
                _hits.clear();
                _busy = false;
                CharmStarted();
            }
            AggressorAI::OnCharmed(apply);
        }

        void EnterEvadeMode(EvadeReason) override
        {
            Tick();
            if (Unit* selected = Selected())
            {
                me->SetHomePosition(me->GetPositionX(), me->GetPositionY(), me->GetPositionZ(), me->GetOrientation());
                ApplyChoice(selected); // Respect dwell/margin; never nearest-target bypass.
            }
            else
                Park();
        }

        void Engage(Unit* requested)
        {
            AttackStart(requested);
            Tick(); // Existing combat after AIM_Initialize is restored in ApplyChoice.
        }

        // For an AI that holds more fight state than the commitment above (the family brain).
        virtual void CharmStarted() { }

        // 0 chases into melee; the family AI asks a caster with no swing to stop short (dc_family_ai.h).
        virtual float ChaseDistance() const
        {
            return 0.f;
        }

        // A unit this monster may pick and fight: everyone, except for a bounty's monster (OwnedMonsterAI, its party only).
        virtual bool Owns(Unit const* /*unit*/) const
        {
            return true;
        }

        void Report(ChatHandler* handler)
        {
            auto p = Profile();
            Unit* selected = Selected();
            handler->PSendSysMessage(
                "Targeting: profile={} target={} lock={:.2f}s native_taunt={} lock_seconds={} switch_margin={}",
                ProfileName(), selected ? selected->GetName() : "none", _policy.Remaining(TargetingNow()),
                _policy.Taunted() ? "yes" : "no", p.lockSeconds, p.switchMargin);
            me->GetMap()->DoForAllPlayers(
                [&](Player* player)
                {
                    if (!ValidTarget(player) || me->GetExactDist(player) > p.candidateMaxYards)
                        return;
                    auto it = _hits.find(player->GetGUID().GetRawValue());
                    auto c = Evaluate(player, it == _hits.end() ? std::numeric_limits<double>::infinity()
                                                                : TargetingNow() - it->second);
                    handler->PSendSysMessage("  {}: distance={:.1f} reachable={} route_efficiency={:.3f} score={:.3f}",
                                             player->GetName(), c.distance, c.reachable ? "yes" : "no",
                                             c.routeEfficiency, Targeting::Score(c, p));
                });
        }

    private:
        // D3: "the other enemies will see the victim as a hostile target" (docs/research/charm-d3-rules.md 2), so a monster
        // a player has charmed is an aggro actor beside the players; their pets and Ancients are still not. A player's
        // actors are the player and every monster charmed for them: the core's one charm and each the shared charm holds
        // (combat/dc_charm_effect.h).
        static std::vector<Unit*> ActorsOf(Player* player)
        {
            std::vector<Unit*> actors{player};
            Unit* charm = player->GetCharm();
            if (Creature* monster = charm ? charm->ToCreature() : nullptr; IsCharmedMonster(monster))
                actors.push_back(monster);
            for (Creature* monster : DC::Combat::CharmEffect::CharmedBy(player))
                if (IsCharmedMonster(monster))
                    actors.push_back(monster);
            return actors;
        }
        static bool IsActor(Unit const* unit)
        {
            return unit && (unit->IsPlayer() || IsCharmedMonster(unit->ToCreature()));
        }
        static double Jitter()
        {
            return Roll() * 2.0 - 1.0;
        }
        bool ValidTarget(Unit const* target) const
        {
            return target && target->IsAlive() && target->IsInWorld() && me->IsInMap(target) &&
                   me->InSamePhase(target) && me->CanSeeOrDetect(target) && me->IsValidAttackTarget(target) &&
                   CombatManager::CanBeginCombat(me, target) && Owns(target);
        }
        Targeting::Candidate Evaluate(Unit* target, double age = std::numeric_limits<double>::infinity()) const
        {
            Targeting::Candidate candidate{target->GetGUID().GetRawValue(), me->GetExactDist(target), false, age};
            PathGenerator path(me);
            if (!path.CalculatePath(target->GetPositionX(), target->GetPositionY(), target->GetPositionZ()) ||
                path.IsInvalidDestinationZ(target))
                return candidate;
            auto type = path.GetPathType();
            if (!(type & PATHFIND_NORMAL) ||
                (type & (PATHFIND_NOPATH | PATHFIND_INCOMPLETE | PATHFIND_SHORT | PATHFIND_FARFROMPOLY |
                         PATHFIND_SHORTCUT | PATHFIND_NOT_USING_PATH)))
                return candidate;
            // Route geometry, not another balancing constant. This makes the
            // reachability weight useful among complete, eligible paths too.
            candidate.reachable = true;
            double length = 0;
            auto const& points = path.GetPath();
            for (std::size_t i = 1; i < points.size(); ++i)
            {
                double dx = points[i].x - points[i - 1].x;
                double dy = points[i].y - points[i - 1].y;
                double dz = points[i].z - points[i - 1].z;
                length += std::sqrt(dx * dx + dy * dy + dz * dz);
            }
            candidate.routeEfficiency = length > 0 ? std::clamp(candidate.distance / length, 0.0, 1.0) : 1.0;
            return candidate;
        }
        bool Reachable(Unit* target) const
        {
            return Evaluate(target).reachable;
        }
        Unit* NativeTaunter() const
        {
            auto const& effects = me->GetAuraEffectsByType(SPELL_AURA_MOD_TAUNT);
            // Match ThreatManager::TauntUpdate's newest active taunt priority.
            for (auto it = effects.rbegin(); it != effects.rend(); ++it)
                if (Unit* caster = (*it)->GetCaster())
                    if (ValidTarget(caster))
                        return caster;
            return nullptr;
        }
        Unit* Selected() const
        {
            return _policy.Current() ? ObjectAccessor::GetUnit(*me, ObjectGuid(_policy.Current())) : nullptr;
        }
        void ApplyChoice(Unit* target)
        {
            if (_busy || !ValidTarget(target))
                return;
            _busy = true;
            auto& threats = me->GetThreatMgr();
            // Zero is an engine relationship marker, not a balancing value. Ignore
            // native modifiers/redirects; no damage/heal accumulator makes decisions.
            threats.ResetAllThreat();
            threats.AddThreat(target, 0.0f, nullptr, true, true);
            if (!me->IsInCombatWith(target) || !me->IsEngagedBy(target))
            {
                _policy.Clear();
                _busy = false;
                return; // Never synthesize engagement after a rejected combat relationship.
            }
            threats.FixateTarget(target);
            threats.TauntUpdate(); // Public synchronous victim refresh, includes suppression.
            if (!IsEngaged() && me->IsInCombatWith(target) && me->IsEngagedBy(target))
                EngagementStart(target);
            if (IsEngaged())
            {
                bool changed = me->GetVictim() != target;
                AggressorAI::AttackStart(target);
                // Unit::Attack returns false for an unchanged victim. An evade or
                // replaced AI still needs the chase restarted in that case.
                if (!changed)
                    me->GetMotionMaster()->MoveChase(target);
                if (float const standoff = ChaseDistance(); standoff > 0.f)
                    me->GetMotionMaster()->MoveChase(target, standoff);
            }
            _busy = false;
        }
        void Park()
        {
            if (_busy)
                return;
            _busy = true;
            _policy.Clear();
            if (IsEngaged() || me->IsInCombat() || me->GetVictim())
            {
                me->SetHomePosition(me->GetPositionX(), me->GetPositionY(), me->GetPositionZ(), me->GetOrientation());
                me->GetMotionMaster()->MoveIdle();
                me->CombatStop(true);
                me->GetThreatMgr().ClearAllThreat();
                if (IsEngaged())
                    EngagementOver();
                me->SetRegeneratingHealth(false);
            }
            _busy = false;
        }
        bool _guardian;
        bool _busy = false;
        Targeting::Policy _policy;
        std::unordered_map<std::uint64_t, double> _hits;
    };

    class TargetingWorld final : public WorldScript
    {
    public:
        TargetingWorld()
            : WorldScript("dc_monster_targeting_world", {WORLDHOOK_ON_STARTUP})
        {
        }
        void OnStartup() override
        {
            if (!LoadTargetingProfiles())
                throw std::runtime_error("DC monster targeting profiles missing/invalid; apply world rifts_0012/0013");
        }
    };

    class TargetingUnits final : public UnitScript
    {
    public:
        TargetingUnits()
            : UnitScript("dc_monster_targeting_units", true,
                         {UNITHOOK_ON_UNIT_UPDATE, UNITHOOK_ON_AURA_APPLY, UNITHOOK_ON_AURA_REMOVE})
        {
        }
        void OnUnitUpdate(Unit* unit, uint32) override
        {
            Refresh(unit);
        }
        void OnAuraApply(Unit* unit, Aura* aura) override
        {
            if (aura->GetSpellInfo()->HasAura(SPELL_AURA_MOD_TAUNT))
                Refresh(unit);
        }
        void OnAuraRemove(Unit* unit, AuraApplication* app, AuraRemoveMode) override
        {
            if (app->GetBase()->GetSpellInfo()->HasAura(SPELL_AURA_MOD_TAUNT))
                Refresh(unit);
        }

    private:
        static void Refresh(Unit* unit)
        {
            if (Creature* creature = unit->ToCreature())
                if (auto* ai = dynamic_cast<RiftTargetAI*>(creature->AI()))
                    ai->Tick();
        }
    };

    class TargetingCommands final : public CommandScript
    {
    public:
        TargetingCommands()
            : CommandScript("dc_monster_targeting_commands")
        {
        }
        Acore::ChatCommands::ChatCommandTable GetCommands() const override
        {
            using namespace Acore::ChatCommands;
            static ChatCommandTable targeting = {{"reload", Reload, SEC_ADMINISTRATOR, Console::Yes},
                                                 {"status", Status, SEC_GAMEMASTER, Console::No}};
            static ChatCommandTable dc = {{"targeting", targeting}};
            static ChatCommandTable root = {{"dc", dc}};
            return root;
        }

    private:
        static bool Reload(ChatHandler* handler)
        {
            bool loaded = LoadTargetingProfiles();
            handler->SendSysMessage(
                loaded ? "Targeting profiles reloaded; existing locks finish at their original deadline."
                       : "Targeting reload rejected; existing cache retained. Check server log.");
            return loaded;
        }
        static bool Status(ChatHandler* handler)
        {
            Creature* creature = handler->getSelectedCreature();
            auto* ai = creature ? dynamic_cast<RiftTargetAI*>(creature->AI()) : nullptr;
            if (!ai)
            {
                handler->SendSysMessage("Select a Diablocraft rift monster first.");
                return false;
            }
            ai->Report(handler);
            return true;
        }
    };


// F5 / 09 §4. The guardian's abilities on top of an ordinary aggressive creature
// AI: RiftTargetAI supplies aggro, commitments, chase and melee, and this adds the two
// abilities rift_guardian_models.csv maps it to, on their own timers. Attached
// with AIM_Initialize on the summon, so Baron Geddon and Icehowl keep their own
// scripts everywhere else in the world - and those scripts never run here
// anyway, because their GetAI is an instance helper that returns null outside
// Molten Core, ToC and ICC, none of which is a rift dungeon.
class GuardianAI final : public RiftTargetAI
{
public:
    GuardianAI(Creature* creature, Guardian definition)
        : RiftTargetAI(creature, true), _definition(std::move(definition))
    {
        StopRegenerating();
        // A Guardian is not charmable (docs/contracts/legendary-world-pieces.md): by mechanic, and by aura for a charm
        // spell that carries none.
        me->ApplySpellImmune(0, IMMUNITY_MECHANIC, MECHANIC_CHARM, true);
        me->ApplySpellImmune(0, IMMUNITY_STATE, SPELL_AURA_MOD_CHARM, true);
        me->ApplySpellImmune(0, IMMUNITY_STATE, SPELL_AURA_AOE_CHARM, true);
        // Frenzy is a once-per-guardian buff, not a once-per-pull one: it is
        // cleared here rather than in Reset, because Reset runs on every engage
        // and a guardian that survives a wipe engages again. Clearing it there
        // let the second pull cast Frenzy a second time and stack another
        // haste step (AddPace) on top of the first, which is never undone.
        _frenzied = false;
    }

    void Reset() override
    {
        _timers[0] = GuardianFirstMs();
        _timers[1] = GuardianFirstMs() + GuardianRepeatMs() / 2;
        StopRegenerating();
    }

    void JustEngagedWith(Unit*) override { Reset(); }

    // Shared targeting owns evade and engagement restoration. Guardian Life,
    // position, frenzy and ability timers keep their existing lifecycle.

    void UpdateAI(uint32 diff) override
    {
        Tick();
        if (!UpdateVictim())
            return;
        for (unsigned index = 0; index < 2; ++index)
        {
            if (_timers[index] > diff)
            {
                _timers[index] -= diff;
                continue;
            }
            _timers[index] = GuardianRepeatMs();
            Use(_definition.abilities[index]);
        }
        DoMeleeAttackIfReady();
    }

private:
    // The one core path that would hand a wiping party a full-Life guardian.
    // Creature::Update calls RegenerateHealth every CREATURE_REGEN_INTERVAL
    // while the creature is out of combat (Creature.cpp:896-900) and again in
    // combat when it cannot reach its target (901-912), and
    // Creature::RegenerateHealth adds max/3 a tick (Creature.cpp:1037-1071), so
    // a guardian left alone is back to full inside a few seconds. Both callers
    // go through RegenerateHealth, and RegenerateHealth's first line is
    // isRegeneratingHealth(), so this one flag closes every one of them.
    //
    // It is the only one. The rest of the evade path was read against the
    // pinned core and none of it touches health:
    //   * CreatureAI::_EnterEvadeMode (CreatureAI.cpp:383-437) - auras, combat,
    //     loot recipient, threat. No health.
    //   * CreatureAI::EnterEvadeMode (CreatureAI.cpp:235-277) - MoveTargetedHome
    //     and Reset. No health.
    //   * HomeMovementGenerator<Creature>::DoFinalize - clears the evade state
    //     and calls JustReachedHome. No health.
    //   * UnitAI::EvadeTimerExpired (UnitAI.cpp:395-449) - teleports, or calls
    //     ContinueEvadeRegen, which only moves a timer, or calls back into this
    //     EnterEvadeMode. No health.
    //   * Creature::SetFullHealth is reached only from DeathState::JustRespawned
    //     (Creature.cpp:1998-2000), which needs the guardian to have died first.
    //
    // Set in the constructor and again in Reset, because Creature::UpdateEntry
    // reloads m_regenHealth from the template (Creature.cpp:588) and a later
    // AIM_Initialize would arrive after it.
    void StopRegenerating() { me->SetRegeneratingHealth(false); }

    void Use(Ability const& ability)
    {
        if (!ability.shell)
            return;
        Unit* victim = me->GetVictim();
        if (ability.behaviour == "nova")
        {
            // The shell is cast on the guardian itself: the ring is ours to
            // resolve, exactly as a skill shell's area is.
            me->CastSpell(me, ability.shell, true);
            BlastPlayers(me, me->GetMap(), me->GetPositionX(), me->GetPositionY(),
                         me->GetPositionZ(), GuardianNovaRadiusYards(), ability.shell,
                         SwingDamage(me) * GuardianNovaDamage());
        }
        else if (ability.behaviour == "leap")
        {
            if (!victim)
                return;
            me->CastSpell(victim, ability.shell, true);
            me->NearTeleportTo(victim->GetPositionX(), victim->GetPositionY(),
                               victim->GetPositionZ(), me->GetOrientation());
            if (Player* player = victim->ToPlayer())
                DC::Combat::DealMonsterHit(me, player, ability.shell, SwingDamage(me) * GuardianLeapDamage());
        }
        else if (ability.behaviour == "frenzy" && !_frenzied)
        {
            // Frenzy is a self buff, so there is nothing to blast: it swings
            // faster for the rest of the fight.
            _frenzied = true;
            me->CastSpell(me, ability.shell, true);
            AddPace(me, 1.0, 1.0 + GuardianFrenzyHastePct() / 100.0);
        }
    }

    Guardian _definition;
    std::uint32_t _timers[2] = {GuardianFirstMs(), GuardianFirstMs()};
    bool _frenzied = false;
};

// F5. Where the guardian may stand. GetClosePoint only guarantees line of sight
// and a valid Z: a point 15 yards out can be across a railing, on a ledge or on
// the far side of a wall, and a boss summoned there cannot path to the player,
// which is one of the two ways it ends up motionless and immune. This walks the
// nav mesh from the player to the offered point and returns the last position
// that is genuinely reachable, refusing collisions and unwalkable slopes; if
// nothing works it falls back to the player's own feet, which are by definition
// standing on the mesh.
Position WalkableSpawnPoint(Player* killer)
{
    float x = 0, y = 0, z = 0;
    killer->GetClosePoint(x, y, z, killer->GetObjectSize(), GuardianSpawnRangeYards() * 0.5f);
    Map* map = killer->FindMap();
    if (!map)
        return Position(killer->GetPositionX(), killer->GetPositionY(), killer->GetPositionZ(),
                        killer->GetOrientation());
    // Failing on collisions and slopes is the point: a partial path still hands
    // back the last good coordinates, which is the nearest walkable spot.
    if (!map->CanReachPositionAndGetValidCoords(killer, x, y, z, true, true) ||
        !Acore::IsValidMapCoord(x, y, z))
    {
        LOG_INFO("server", "[DC rifts] guardian spawn point {:.1f},{:.1f},{:.1f} was not reachable; "
                           "snapped to the nearest walkable position", x, y, z);
        if (!Acore::IsValidMapCoord(x, y, z))
            return Position(killer->GetPositionX(), killer->GetPositionY(), killer->GetPositionZ(),
                            killer->GetOrientation());
    }
    return Position(x, y, z, killer->GetOrientation());
}

// F5. A guardian is a real WoW boss template, and a boss template carries the
// flags its own encounter script clears when the encounter starts. Icehowl's
// creature_template has unit_flags 32770, which includes UNIT_FLAG_NON_ATTACKABLE
// (0x2): with that set, Unit::_IsValidAttackTarget is false in both directions,
// so the guardian can never aggro - it never moves - and no player attack can
// ever land on it. Nothing clears it here, because the encounter script that
// would is an instance helper that returns null outside its own raid. So this
// does, and it starts the fight rather than waiting for an aggro sweep that a
// summon standing inside the player's bubble may never get.
void PrepareGuardian(Creature* boss, Player* killer)
{
    boss->RemoveUnitFlag(static_cast<UnitFlags>(
        UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_NOT_ATTACKABLE_1 | UNIT_FLAG_NON_ATTACKABLE_2 |
        UNIT_FLAG_NOT_SELECTABLE | UNIT_FLAG_IMMUNE_TO_PC | UNIT_FLAG_IMMUNE_TO_NPC |
        UNIT_FLAG_PACIFIED | UNIT_FLAG_DISABLE_MOVE));
    boss->SetImmuneToAll(false);
    boss->SetReactState(REACT_AGGRESSIVE);
    // Before AttackStart: Creature::SetCombatMovement does nothing once the
    // creature is already in combat (its own header says so).
    boss->SetCombatMovement(true);
    // Home is where it was summoned. A boss whose home is still its template's
    // own spawn row, on another map, leashes and evades on the first step.
    boss->SetHomePosition(boss->GetPositionX(), boss->GetPositionY(), boss->GetPositionZ(),
                          boss->GetOrientation());
    // Populate combat relationships for the closed instance; shared targeting
    // zeros amounts and fixes the selected victim before any AI tick.
    boss->SetInCombatWithZone();
    if (auto* ai = dynamic_cast<GuardianAI*>(boss->AI()))
        ai->Engage(killer);
}

// 09 §4 / bug 3. Reports the Life the guardian ended up with and the four
// inputs the formula names, so the number can be checked against the doc without
// guessing. Read-only: nothing here changes tuning.
void LogGuardianLife(Creature* boss, Rift const& rift)
{
    CreatureTemplate const* info = boss->GetCreatureTemplate();
    if (rift.mode == "gr")
    {
        // A Greater Rift's Life is the level's (dc_difficulty.cpp GreaterScaling), not the opener's tier.
        LOG_INFO("server", "[DC rifts] guardian Life: entry={} level={} rank={} | Greater Rift {} with {} players | "
                           "final Life {}",
                 boss->GetEntry(), boss->GetLevel(), info ? static_cast<unsigned>(info->rank) : 0u, rift.grRank,
                 rift.players, boss->GetMaxHealth());
        return;
    }
    double tierHealth = 1.0, partyHealth = 1.0;
    if (QueryResult row = WorldDatabase.Query(
            "SELECT t.monster_health_multiplier_pct FROM dc_tier_phase p "
            "JOIN dc_difficulty_tiers t ON t.tier=p.tier_name WHERE p.tier_id={}", rift.tier))
        tierHealth = (*row)[0].Get<int64>() / 100.0;
    if (QueryResult row = WorldDatabase.Query(
            "SELECT monster_life_multiplier_pct FROM dc_party_scaling WHERE players={} AND context='open_world'", rift.players))
        partyHealth = (*row)[0].Get<double>() / 100.0;
    std::uint64_t const life = boss->GetMaxHealth();
    double const combined = tierHealth * partyHealth;
    LOG_INFO("server",
             "[DC rifts] guardian Life: entry={} level={} HealthModifier={} rank={} | tier {} x{:.2f} | "
             "party {} x{:.2f} | boss multiplier: 03 D8 placeholder, none applied here | final Life {} "
             "(tier x party alone = x{:.2f}, so template Life ~{:.0f})",
             boss->GetEntry(), boss->GetLevel(), info ? info->ModHealth : 0.0,
             info ? static_cast<unsigned>(info->rank) : 0u, rift.tier, tierHealth,
             rift.players, partyHealth, life, combined, combined > 0 ? life / combined : 0.0);
}

Charm::Body CharmBodyOf(Creature const* creature)
{
    Charm::Body body;
    body.pet = creature->IsPet();
    body.totem = creature->IsTotem();
    body.critter = creature->IsCritter();
    body.guardian = creature->IsGuardian();
    body.trigger = creature->IsTrigger();
    body.controlledByPlayer = creature->IsControlledByPlayer();
    body.charmed = creature->IsCharmed();
    return body;
}

bool IsCharmedMonster(Creature const* creature)
{
    return creature && Charm::IsCharmedMonster(CharmBodyOf(creature));
}

bool IsRiftTrash(Creature const* creature)
{
    // A player's own pet, guardian, totem or vanity critter is not rift trash. A monster the player has charmed still
    // is: it is controlled by the player for the charm's length.
    if (creature->IsPet() || creature->IsTotem() || creature->IsCritter() ||
        creature->IsGuardian() || Charm::PlayerOwned(CharmBodyOf(creature)) || creature->IsTrigger())
        return false;
    // A creature of ours that runs its own scripted AI is not either: Call of the Ancients' summons
    // (Summon casts to that AI right after the summon; replacing it crashed the worldserver),
    // the Wizard's image, familiar and hydra, the ground-loot
    // carriers. Rift trash is stock creatures, so none of them carries a dc_ ScriptName.
    return !(Classes::Ancients::IsAncientEntry(creature->GetEntry()) ||
             creature->GetScriptName().rfind("dc_", 0) == 0);
}

// Greater Rift: when the Guardian is up, every other monster in the rift is gone (D3's rule).
// Gone is a despawn, not a death: no kill hook, so no loot, XP, progress or credit.
// Kept: the Guardian and what it summoned, a player's pets and summons, our own scripted
// creatures, triggers, and anything not hostile to the reference player (friendly NPCs).
bool ClearedByGuardian(Creature const* creature, Unit const* reference)
{
    if (!creature->IsAlive() || IsGuardianEntry(creature->GetEntry()) || !IsRiftTrash(creature))
        return false;
    if (TempSummon const* summon = creature->ToTempSummon())
        if (Unit const* summoner = summon->GetSummonerUnit())
            if (summoner->IsCreature() && IsGuardianEntry(summoner->GetEntry()))
                return false;
    return Charm::ClearedByGuardian(creature->IsHostileTo(reference), CharmBodyOf(creature));
}

// Every creature on the map, collected first: despawning edits the store being walked.
struct CollectCreatures
{
    std::vector<Creature*>& out;
    void Visit(std::unordered_map<ObjectGuid, Creature*>& creatures)
    {
        for (auto const& entry : creatures)
            out.push_back(entry.second);
    }
    template <class T>
    void Visit(std::unordered_map<ObjectGuid, T*>&) { }
};

std::vector<Creature*> CreaturesOf(Map* map)
{
    std::vector<Creature*> all;
    CollectCreatures collect{all};
    TypeContainerVisitor<CollectCreatures, MapStoredObjectTypesContainer> visitor(collect);
    visitor.Visit(map->GetObjectsStore());
    return all;
}

// Who a charmed elite's affixes may hurt. A charmed monster has the player's faction, so the monsters
// of the map that `source` may attack are its former allies, and its charmer's side (players, their pets, the other
// charmed monster) is not among them.
std::vector<Unit*> AffixFoesOf(Unit* source)
{
    std::vector<Unit*> foes;
    Map* map = source ? source->GetMap() : nullptr;
    if (!map)
        return foes;
    // ponytail: walks every creature of the map for each call; a charmed elite lives seconds, so it is rare. Cache per
    // map update if a profile ever shows it.
    for (Creature* creature : CreaturesOf(map))
        if (creature != source && creature->IsAlive() && source->IsValidAttackTarget(creature))
            foes.push_back(creature);
    return foes;
}

// False for a Nephalem Rift, which is left as it was. The long respawn is so a native spawn
// does not come back (and no pool refills) for the rest of the run.
bool ClearGreaterRift(Map* map, Rift const& rift, Unit const* reference)
{
    if (rift.mode != "gr")
        return false;
    for (Creature* creature : CreaturesOf(map))
        if (ClearedByGuardian(creature, reference))
            creature->DespawnOrUnsummon(0ms, Seconds(GONE_FOR_THE_RUN));
    return true;
}

// F5. At 100% the guardian spawns near whoever landed the last kill. In a
// Greater Rift every other monster is cleared first; a Nephalem Rift is not.
void SpawnGuardian(Player* killer, Rift& rift)
{
    Guardian guardian;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        if (guardians.empty())
            return;
        guardian = guardians[std::uniform_int_distribution<std::size_t>(0, guardians.size() - 1)(Engine())];
    }
    Map* map = killer->FindMap();
    if (!map)
        return;

    // The clear is Greater Rift only: in a Nephalem Rift nothing despawns.
    ClearGreaterRift(map, rift, killer);

    Position const spot = WalkableSpawnPoint(killer);
    if (Creature* boss = killer->SummonCreature(guardian.creatureId, spot.GetPositionX(), spot.GetPositionY(),
                                                spot.GetPositionZ(), killer->GetOrientation(),
                                                TEMPSUMMON_MANUAL_DESPAWN))
    {
        // Guardian mechanics remain on top of the shared targeting AI.
        boss->AIM_Initialize(new GuardianAI(boss, guardian));
        PrepareGuardian(boss, killer);
        rift.state = "guardian";
        // The floor where the bar filled is the Guardian's (rift floors 4.8, 6.9): the Greater Rift sweep is its alone.
        rift.guardianInstance = map->GetInstanceId();
        PersistNow(rift);
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            live.Store(rift);
        }
        Announce(rift, guardian.name + " tears through the rift!");
        // 09 §4 inputs, for the record. The multipliers themselves are applied by
        // 03's autobalance path before this line runs, so the final Life is the
        // product; this prints what went into it and changes nothing.
        LogGuardianLife(boss, rift);
        LOG_INFO("server", "[DC rifts] guardian {} spawned in instance {} at {:.1f},{:.1f},{:.1f} "
                           "({:.1f} yd from {}) with {} and {}; unit_flags {} react {} attackable {}",
                 guardian.name, rift.instanceId, boss->GetPositionX(), boss->GetPositionY(),
                 boss->GetPositionZ(), boss->GetDistance(killer), killer->GetName(),
                 guardian.abilities[0].name, guardian.abilities[1].name,
                 static_cast<std::uint32_t>(boss->GetUnitFlags()), static_cast<int>(boss->GetReactState()),
                 killer->IsValidAttackTarget(boss) ? "yes" : "NO");
    }
}

// One member's whole Guardian reward: the 06 roller (which already gives the guaranteed legendary, the gold and
// Death's Breath), the Keystone and the Blood Shards, in one account operation under one receipt per run and
// character. A Greater Rift's Guardian pays by the run's level instead. True when it committed.
// Called at the kill for the members on the Guardian's floor, and, for every other member of the party, the first
// time they open its corpse (rift floors F7); the receipts keep a retried payout from paying twice.
bool PayGuardianMember(Player* member, Creature* guardian, Rift const& rift)
{
    // ONE stable per-run, per-character receipt for the WHOLE reward: RollLoot
    // skips a run whose receipt already committed and the keystone shares the
    // same id, so drops, gold, Death's Breath and the keystone are paid together
    // or not at all. A retried or replayed completion credits nothing twice.
    std::string const run = "rift:" + std::to_string(rift.id) + ":guardian:reward:";
    PlayerEconomy::Scope rewards(member);
    // A Greater Rift Guardian pays by the run's level (no guaranteed legendary; the curve's,
    // the level's gold, one legendary gem). A Nephalem Rift's reward is as it was.
    DC::Loot::GreaterReward greater;
    if (rift.mode == "gr")
        greater = GuardianReward(member, rift);
    DC::Loot::RollLoot(member, DC::Loot::Source::RiftGuardian, guardian->GetLevel(), rift.tier, true,
                       run + std::to_string(member->GetGUID().GetCounter()), guardian, nullptr,
                       rift.mode == "gr" ? &greater : nullptr);
    // The keystone is unused until Greater Rifts (F6); it only accumulates.
    if (!DC::Loot::GrantMaterial(member, KEYSTONE_ITEM, 1,
                                 run + std::to_string(member->GetGUID().GetCounter())))
        PlayerEconomy::Fail();
    // Cain's Destiny 3-piece: a chance of one extra Keystone, its own receipt so a replay of the reward never pays the first
    // Keystone's receipt a different amount (a receipt reused for another payload is refused).
    if (unsigned const extra = DC::Loot::ExtraKeystones(member))
        if (!DC::Loot::GrantMaterial(member, KEYSTONE_ITEM, extra,
                                     run + "keystone-extra:" + std::to_string(member->GetGUID().GetCounter())))
            PlayerEconomy::Fail();
    // Blood Shards (kadala.md 4.3 to 4.5): a ledger credit in the same operation, under its own
    // receipt (the Keystone's is taken; a receipt reused for another payload is refused). The cap
    // cuts what does not fit and says how much; the chat line waits for the commit.
    std::uint64_t const shards = DC::AccountEconomy::Enabled() ? GuardianShards(rift) : 0;
    std::uint64_t shardsLost = 0;
    if (shards && !DC::AccountEconomy::CreditMaterial(member, DC::BloodShards::Entry, shards,
                                                      run + "shards:" + std::to_string(member->GetGUID().GetCounter()),
                                                      &shardsLost))
        PlayerEconomy::Fail();
    if (!rewards.Finish())
    {
        LOG_ERROR("server", "[DC rifts] guardian reward for {} in rift {} did not commit; "
                            "completion not published", member->GetName(), rift.id);
        return false;
    }
    if (shards)
        ChatHandler(member->GetSession()).SendSysMessage(Gr::ShardLine(shards, shardsLost));
    return true;
}

// F7. Guardian rewards: the party members on the Guardian's floor within group reward distance are paid here, at
// the kill (L12). Every other enrolled member of the run, on any floor or in town, is OWED: the corpse stays open
// for them and each is paid when they first open it (lootable by anyone in the rift party,
// regardless of what floor they are on; eligibility, not a hand-out).
// The run is the durable source for all of it: every member's drops, gold,
// material and keystone share one account operation, and the completion is
// published only once that operation has committed (0007).
bool RewardGuardian(Player* killer, Creature* guardian, Rift& rift)
{
    // Claim the run before anything is paid. Both the player-kill hook and the
    // creature's own death reach this, and only one of them may reward. The
    // claim is in memory; the durable "complete" row waits for the commit.
    {
        std::lock_guard<std::mutex> lock(riftMutex);
        Rift* run = live.Find(rift.id);
        if (!run || run->state != "guardian")
            return false;
        run->state = "complete";
    }
    std::vector<Player*> members;
    if (Group* group = killer->GetGroup())
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            if (Player* member = itr->GetSource())
                if (member->IsInMap(guardian) && member->IsAtGroupRewardDistance(guardian))
                    members.push_back(member);
    }
    else
        members.push_back(killer);

    bool committed = true;
    std::vector<std::uint64_t> paid;
    for (Player* member : members)
    {
        paid.push_back(member->GetGUID().GetRawValue());
        if (!PayGuardianMember(member, guardian, rift))
            committed = false;
    }
    // The claim stays, so nothing is paid twice, but a run whose rewards did not
    // commit is never written down as complete. The receipts make an operator
    // retry safe once the affected session has reconnected.
    if (!committed)
        return false;

    // Everyone else in the run's party is owed; their roll waits until they stand on this floor and open the body.
    {
        std::vector<std::uint64_t> party;
        for (ObjectGuid const& guid : EnrolledGuids(rift.id))
            party.push_back(guid.GetRawValue());
        std::vector<ObjectGuid> owed;
        for (std::uint64_t const guid : DC::Loot::Corpse::OwedAfterPayout(party, paid))
            owed.push_back(ObjectGuid(guid));
        Rift const copy = rift;
        if (!owed.empty() &&
            !DC::Loot::OweCorpse(guardian, owed, [copy](Player* member, Creature* body)
                                 { return PayGuardianMember(member, body, copy); }))
            LOG_WARN("server", "[DC rifts] guardian of rift {} cannot hold loot; {} party members elsewhere are not paid",
                     rift.id, owed.size());
    }

    rift.state = "complete";
    PersistNow(rift);
    // The clear time for the website leaderboard: written once, here, where the
    // run becomes complete. The IS NULL guard means nothing later can move it.
    CharacterDatabase.DirectExecute(
        "UPDATE dc_rift SET guardian_killed_at=NOW() WHERE id={} AND guardian_killed_at IS NULL", rift.id);
    {
        std::lock_guard<std::mutex> lock(riftMutex);
        live.Store(rift);
    }
    Announce(rift, "The rift guardian falls. Close the rift at the obelisk or with .dc rift close.");
    return true;
}

bool IsGuardianEntry(std::uint32_t entry)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    return std::any_of(guardians.begin(), guardians.end(),
                       [&](Guardian const& g) { return g.creatureId == entry; });
}

// F5/F7. Completing the run must not depend on who landed the last blow. The
// player-kill hook is the normal path and credits the killer; this is the same
// step reached from the creature's own death, for a guardian finished off by a
// pet, by a bleed after the player went down, or by anything else that is not a
// direct player kill. Both check the rift's state first, and RewardGuardian
// publishes "complete" before it returns, so whichever arrives second does
// nothing.
bool CompleteGuardianKill(Creature* dead, Unit* killer)
{
    if (!dead || !IsGuardianEntry(dead->GetEntry()))
        return false;
    Map* map = dead->GetMap();
    if (!map)
        return false;
    Rift rift;
    {
        // Seen from the floor the Guardian died on, which is the map its kill is credited on.
        std::lock_guard<std::mutex> lock(riftMutex);
        if (!live.View(map->GetInstanceId(), map->GetId(), rift) || rift.state != "guardian")
            return false;
    }
    // Credit the killer when there is one, otherwise anyone still in the rift:
    // the rewards are per party member in range anyway (06 L12).
    Player* credit = killer ? killer->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
    if (!credit || !credit->IsInMap(dead))
        map->DoForAllPlayers([&](Player* player)
        {
            if (!credit && player && player->IsAlive())
                credit = player;
        });
    if (!credit)
    {
        LOG_WARN("server", "[DC rifts] guardian died in instance {} with no player to credit; "
                           "rift left at guardian state", rift.instanceId);
        return false;
    }
    // The kill is compared with the clock now, at the Guardian's death, and written
    // before any reward settles; a payout that retries later cannot turn a beaten run into an
    // expired one. A Nephalem Rift passes through untouched.
    RecordGuardianResult(rift);
    // An in-time kill brings Urshi to where it fell (once per run; a retried payout comes back here).
    BeginUrshi(dead, rift);
    if (!RewardGuardian(credit, dead, rift))
        return false;
    // 7.4: guardian death is what opens the quest. Every still-enrolled member
    // completes now, wherever they are - the veto above has been holding them
    // at full N/M until this moment. The run's own state is the only source of
    // that fact; a quest callback never decides it.
    CompleteRunQuests(rift.id);
    LOG_INFO("server", "[DC rifts] guardian {} killed in instance {}; rift {} complete, credited to {}",
             dead->GetName(), rift.instanceId, rift.id, credit->GetName());
    return true;
}

// 09 §2 step 2. Decides promotion the moment a native spawn enters a rift, and
// hands the swap to the map's own update.
// 09 F2 stage 1: a rift monster is a body and a stat block. It swings, and if it
// was promoted it carries our affixes; nothing else. Three things can make a WoW
// creature cast, and all three have to go on every rift spawn:
//
//   1. creature_template.spell1-8, which the core copies into Creature::m_spells
//      and which CombatAI and SmartAI both draw from;
//   2. SmartAI, which reads its casts out of smart_scripts at runtime;
//   3. a C++ CreatureScript AI, which casts from its own UpdateAI.
//
// 2 and 3 are the same fix - the AI object is replaced with RiftTargetAI, the
// plain melee AI with module-owned target commitments and core chase underneath.
// Model, faction, level, stats, loot and tier scaling live outside that AI.
//
// The elite affixes are not affected: they are driven by RiftAffixes, a
// UnitScript on the creature's update, not by its AI. Nor is the guardian, whose
// own AI is installed after the summon returns, which is after this hook.
//
// Runs on every creature added to a live rift, clones and summons included, and
// only there: nothing outside a rift instance is touched.
// 09 F2's melee AI, plus one thing the plain one does not do: it evades without
// despawning. CreatureAI::EnterEvadeMode ends with
//
//     if (cInfo->HasFlagsExtra(CREATURE_FLAG_EXTRA_HARD_RESET)) me->DespawnOnEvade();
//
// and DespawnOnEvade UnSummons a TempSummon outright. 10 of the 776 creature
// templates that spawn in the rift dungeon pool carry that flag, so anything
// that makes a rift creature evade - a player going invisible, town-portalling
// out, dying, or simply running past its leash - permanently removed those from
// the run. A rift is a closed instance that exists for one run: its monsters
// reset, they do not despawn. Everything else about the evade is the core's own.
class RiftMeleeAI : public RiftTargetAI
{
public:
    explicit RiftMeleeAI(Creature* creature) : RiftTargetAI(creature)
    {
        // A rift monster could evade, heal to full and walk home
        // mid-fight. Regeneration is half of that - Creature::Update
        // regenerates out of combat AND on the unreachable-target path
        // (Creature.cpp:896-907), checking this flag first (:1037-1053).
        me->SetRegeneratingHealth(false);
    }

    // RiftTargetAI provides the shared no-reset evade and targeting policy.

    // A cluster of the spawner fights as one (monster-spawning.md 3.9.3): the rest of its members take this target.
    void JustEngagedWith(Unit* who) override { Spawner::MemberEngaged(me, who); }
};

// A family monster is rift trash plus its ability rows (dc_family_ai.cpp): the brain picks, winds up
// and strikes, and this class only hands it the AI hooks. Outside a rift it is the same, so a `.npc add` or a lineup
// monster fights with its abilities on dev.
class FamilyAI final : public RiftMeleeAI
{
public:
    explicit FamilyAI(Creature* creature) : RiftMeleeAI(creature), _brain(creature) { }

    Family::Brain& GetBrain() { return _brain; }

    float ChaseDistance() const override { return _brain.ChaseDistance(); }

    // A wind-up, channel or flight in progress ends with the charm (the core stops the cast and the movement); the
    // brain starts over, as for a new fight, so it does not strike from a stale phase when the AI comes back.
    void CharmStarted() override { _brain.Engage(); }

    void JustEngagedWith(Unit* who) override
    {
        RiftMeleeAI::JustEngagedWith(who);
        _brain.Engage();
    }

    void UpdateAI(uint32 diff) override
    {
        // RiftTargetAI::Tick already runs from the unit-update hook (TargetingUnits), as for every rift monster.
        if (!UpdateVictim())
            return;
        _brain.Update(diff);
        if (!_brain.Busy() && _brain.CanSwing())
            DoMeleeAttackIfReady();
    }

    void JustDied(Unit*) override { _brain.OnDeath(); }
    // Called from Unit::DealDamage once the swing is rolled and has damage; DIRECT_DAMAGE is the melee swing (a spell is
    // SPELL_DIRECT_DAMAGE), which is what "on melee hit" abilities ride.
    void DamageDealt(Unit* victim, uint32& damage, DamageEffectType type, SpellSchoolMask) override
    {
        _brain.OnDamageDealt(victim, damage, type == DIRECT_DAMAGE);
    }
    void OnSpellCast(SpellInfo const* spell) override { _brain.OnSpellCast(spell); }
    void OnSpellFailed(SpellInfo const* spell) override { _brain.OnSpellFailed(spell); }
    void OnChannelFinished(SpellInfo const* spell) override { _brain.OnChannelFinished(spell); }
    void MovementInform(uint32 type, uint32 id) override { _brain.OnMovement(type, id); }

private:
    Family::Brain _brain;
};

// Bounties (docs/research/bounties.md 5.6): a bounty's named Unique or a Click objective's guard.
// Rift trash for its party only; dc_rifts.h NewOwnedMonsterAI says what each override is for.
class OwnedMonsterAI final : public RiftMeleeAI
{
public:
    OwnedMonsterAI(Creature* creature, std::function<bool(Unit const*)> owns, std::function<void(Unit*)> died)
        : RiftMeleeAI(creature), _owns(std::move(owns)), _died(std::move(died))
    {
    }

    bool Owns(Unit const* unit) const override { return unit && _owns && _owns(unit); }
    bool CanBeSeen(Player const* seer) override { return !seer || Owns(seer); }
    // A stranger's area damage, or anything of no party's, never lands; the world's own (a fall, lava) does.
    void DamageTaken(Unit* attacker, uint32& damage, DamageEffectType type, SpellSchoolMask school) override
    {
        if (attacker && attacker != me && !Owns(attacker))
        {
            damage = 0;
            return;
        }
        RiftMeleeAI::DamageTaken(attacker, damage, type, school);
    }
    void JustDied(Unit* killer) override
    {
        if (_died)
            _died(killer);
    }

private:
    std::function<bool(Unit const*)> _owns;
    std::function<void(Unit*)> _died;
};

CreatureAI* NewOwnedMonsterAI(Creature* creature, std::function<bool(Unit const*)> owns, std::function<void(Unit*)> died)
{
    return new OwnedMonsterAI(creature, std::move(owns), std::move(died));
}

void StripNativeAbilities(Creature* creature)
{
    if (!IsRiftTrash(creature))
        return;
    // A bounty's monster keeps the AI its claim installed: on a rift floor's copy this hook runs
    // after that AI, and replacing it loses CanBeSeen, the party filter and the kill credit. Its AI is its mark.
    if (dynamic_cast<OwnedMonsterAI*>(creature->AI()))
        return;

    for (std::uint8_t slot = 0; slot < MAX_CREATURE_SPELLS; ++slot)
        creature->m_spells[slot] = 0;

    // Creature::AddToWorld calls AIM_Initialize before it calls this hook, so
    // this replaces the AI the core just chose rather than being overwritten by
    // it. AIM_Initialize deletes the old AI and re-runs Motion_Initialize.
    if (Family::IsFamilyEntry(creature->GetEntry()))
        creature->AIM_Initialize(new FamilyAI(creature));
    else
        creature->AIM_Initialize(new RiftMeleeAI(creature));
}

class RiftCreatures final : public AllCreatureScript
{
public:
    RiftCreatures() : AllCreatureScript("dc_rift_creatures") { }
    void OnCreatureAddWorld(Creature* creature) override
    {
        if (!creature)
            return;
        Map* map = creature->GetMap();
        unsigned tier = 0, players = 0;
        if (!ScalingContext(map, tier, players))
        {
            // Not a live rift: leave the world alone, except a family monster, which fights with its abilities
            // wherever it stands (a dev lineup, `.npc add`).
            if (Family::IsFamilyEntry(creature->GetEntry()))
                StripNativeAbilities(creature);
            return;
        }
        // Every rift spawn loses its abilities, including the promoted clones
        // and the pack minions, which are summons and skip the promotion roll.
        // StripNativeAbilities also installs RiftMeleeAI, whose constructor
        // turns regeneration off - so trash, clones and minions all arrive with
        // no reset, no heal and no walk home. Set here as well because a
        // creature whose AI is replaced again later would otherwise get the
        // template's flag back.
        StripNativeAbilities(creature);
        creature->SetRegeneratingHealth(false);
        // A family monster's template is friendly (faction 35, so a lineup or `.npc add` does not fight: monsters_0004); in a rift
        // it is a rift monster. Clones of it are family entries as well (BaseEntry).
        if (Family::IsFamilyEntry(creature->GetEntry()))
            creature->SetFaction(FACTION_MONSTER);

        if (creature->GetEntry() >= CHAMPION_BASE)
            return;                            // already a clone
        if (!creature->GetSpawnId())
            return;                            // a summon: minions and guardians
        if (creature->IsPet() || creature->IsTotem() || creature->IsCritter())
            return;
        double rate = 0;
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            rate = elitePromotionPct;
        }
        if (rate <= 0 || Roll() * 100.0 >= rate)
            return;
        Promotion promotion;
        promotion.instanceId = map->GetInstanceId();
        promotion.mapId = map->GetId();
        promotion.guid = creature->GetGUID();
        // D3 packs are champion or rare; nothing published splits them, so the share is a tunable (rifts.csv
        // elite_champion_pct, seeded at the even coin flip this line used to be).
        promotion.rare = Roll() * 100.0 >= DC::Tunables::Get("rifts", "elite_champion_pct");
        std::lock_guard<std::mutex> lock(workMutex);
        promotions.push_back(promotion);
    }
};


// The `.dc rift abilities` sweep asks this rather than naming the AI types,
// which are private to this file since the split. Same test as
// before: a plain melee AI, or the guardian's own.
bool HasPlainRiftAI(Creature const* creature)
{
    if (!creature || !creature->AI())
        return false;
    return dynamic_cast<AggressorAI const*>(creature->AI()) != nullptr ||
           dynamic_cast<GuardianAI const*>(creature->AI()) != nullptr;
}

float AffixTargetReach()
{
    std::lock_guard<std::mutex> lock(targetingMutex);
    auto found = targetingProfiles.find("elite");
    return found == targetingProfiles.end() ? 0.0f : static_cast<float>(found->second.candidateMaxYards);
}

namespace Family
{
Brain* BrainOf(Creature* creature)
{
    auto* ai = creature ? dynamic_cast<FamilyAI*>(creature->AI()) : nullptr;
    return ai ? &ai->GetBrain() : nullptr;
}
}

void RegisterAIScripts()
{
    Family::RegisterFamilyAiScripts();
    new TargetingWorld();
    new TargetingUnits();
    new TargetingCommands();
    new RiftCreatures();
}
}
