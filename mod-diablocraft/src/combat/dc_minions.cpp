/*
 * The minions a class raises (dc_minions.h): the registry of who stands for whom, the AI every minion runs, the keeper
 * that holds a number of them, the order to attack a target, and the GM command that raises one by name. The rules are
 * dc_minions_math.h; a class defines its kinds and numbers.
 */

#include "dc_minions.h"
#include "dc_combat.h"
#include "dc_item_powers.h"
#include "dc_minions_math.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "CommandScript.h"
#include "Creature.h"
#include "GameTime.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "PetDefines.h"
#include "Player.h"
#include "ScriptedCreature.h"
#include "ScriptMgr.h"
#include "TemporarySummon.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Minions
{
    namespace
    {
        // Stock "Clone Me!" (45204): the Mirror Image's copy of its caster's look, cast by the owner on the copy.
        constexpr std::uint32_t CloneMe = 45204;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // Who hears the blows (OnStruck).
        std::vector<StruckListener> struckListeners;

        void Struck(Player* owner, Unit* target)
        {
            for (StruckListener const& listener : struckListeners)
                listener(owner, target);
        }

        struct Entry
        {
            ObjectGuid guid;
            std::string group;
            std::uint64_t bornAt = 0;
        };
        struct Order
        {
            ObjectGuid target;
            std::uint64_t until = 0;
        };
        struct Boosted
        {
            double pct = 0;
            std::uint64_t until = 0;
        };
        struct Hasted
        {
            double attackPct = 0;
            double movePct = 0;
            std::uint64_t until = 0;
        };
        struct Owned
        {
            std::map<std::string, std::map<std::string, Boosted>> boosts; // by group, then source
            std::map<std::string, std::map<std::string, Hasted>> hastes;
            std::vector<Entry> minions;
            std::map<std::string, std::uint64_t> nextAt;   // each group's keeper clock
            std::map<std::string, std::uint64_t> returnMs; // how long a loss keeps the keeper waiting
            std::map<std::string, Order> orders;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Owned> owners;

        std::mutex defsMutex;
        std::map<std::string, std::function<Kind(Player*)>> defs;

        bool Made(std::string const& key, Player* owner, Kind& out)
        {
            std::function<Kind(Player*)> make;
            {
                std::lock_guard<std::mutex> guard(defsMutex);
                auto found = defs.find(key);
                if (found == defs.end())
                    return false;
                make = found->second;
            }
            out = make(owner);
            return out.entry != 0 && !out.group.empty();
        }

        void Forget(std::uint64_t owner, ObjectGuid guid)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = owners.find(owner);
            if (found == owners.end())
                return;
            auto& list = found->second.minions;
            list.erase(std::remove_if(list.begin(), list.end(), [&](Entry const& e) { return e.guid == guid; }),
                       list.end());
        }

        // A minion lost: its group's keeper waits out the return time.
        void Lost(std::uint64_t owner, std::string const& group)
        {
            std::lock_guard<std::mutex> guard(mutex);
            Owned& state = owners[owner];
            std::uint64_t const returnMs = state.returnMs.count(group) ? state.returnMs[group] : 0;
            state.nextAt[group] = NextAfterLoss(Now(), state.nextAt.count(group) ? state.nextAt[group] : 0, returnMs);
        }

        // The percent the owner's minions of `group` deal more now, while the boost stands.
        double BoostOf(std::uint64_t owner, std::string const& group)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = owners.find(owner);
            if (found == owners.end())
                return 0.0;
            auto boosts = found->second.boosts.find(group);
            double total = 0.0;
            if (boosts != found->second.boosts.end())
                for (auto const& [source, boost] : boosts->second)
                    if (Now() < boost.until)
                        total += boost.pct;
            return total;
        }

        // The haste the owner's minions of `group` have now.
        Hasted HasteOf(std::uint64_t owner, std::string const& group)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = owners.find(owner);
            if (found == owners.end())
                return {};
            auto hastes = found->second.hastes.find(group);
            Hasted total;
            if (hastes != found->second.hastes.end())
                for (auto const& [source, haste] : hastes->second)
                    if (Now() < haste.until)
                    {
                        total.attackPct += haste.attackPct;
                        total.movePct += haste.movePct;
                    }
            return total;
        }

        // The target the owner's minions of `group` were ordered at, while the order stands.
        ObjectGuid OrderedAt(std::uint64_t owner, std::string const& group)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = owners.find(owner);
            if (found == owners.end())
                return {};
            auto order = found->second.orders.find(group);
            return order != found->second.orders.end() && Now() < order->second.until ? order->second.target
                                                                                      : ObjectGuid::Empty;
        }

        std::uint32_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint32_t(std::llround(seconds * 1000.0)) : 0;
        }

        class MinionAI final : public ScriptedAI
        {
        public:
            explicit MinionAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            // Belongs to `player` and fights on its side; the core's own target choice is off, the AI picks.
            void Configure(Player* player, Kind const& made, std::uint64_t born)
            {
                owner = player->GetGUID();
                kind = made;
                bornAt = born;
                me->SetOwnerGUID(owner);
                me->SetCreatorGUID(owner);
                me->SetFaction(player->GetFaction());
                me->SetLevel(player->GetLevel());
                me->SetReactState(REACT_PASSIVE);
                baseRun = me->GetSpeedRate(MOVE_RUN);
                if (kind.firstSwingAtOnce)
                    clock = 1e9;
                if (Follows(kind.staysPut))
                    me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE);
            }

            std::string const& Group() const
            {
                return kind.group;
            }

            void DamageTaken(Unit* attacker, uint32& damage, DamageEffectType, SpellSchoolMask) override
            {
                if (kind.hurt && attacker && damage > 0 && attacker != me)
                    if (Player* player = ObjectAccessor::GetPlayer(*me, owner); player && player->IsValidAttackTarget(attacker))
                        kind.hurt(player, attacker);
                // "dies after {hits} hits": the last one takes all that is left.
                if (damage > 0 && hitLimit.Take(kind.hitsToDie))
                    damage = me->GetHealth();
            }

            void JustDied(Unit*) override
            {
                Forget(owner.GetRawValue(), me->GetGUID());
                Lost(owner.GetRawValue(), kind.group);
                if (kind.ended)
                    if (Player* player = ObjectAccessor::GetPlayer(*me, owner))
                        kind.ended(player, me->GetPosition());
            }

            void UpdateAI(uint32 diff) override
            {
                Player* player = ObjectAccessor::GetPlayer(*me, owner);
                if (!player || !player->IsAlive() || !player->IsInMap(me) || !player->InSamePhase(me) ||
                    Expired(Now(), bornAt, kind.lifeMs))
                {
                    // Its time is up, not its owner gone: it leaves what the kind says it leaves.
                    if (kind.ended && player && player->IsAlive() && player->IsInMap(me) && player->InSamePhase(me))
                        kind.ended(player, me->GetPosition());
                    if (kind.timedOut && player && player->IsAlive() && player->IsInMap(me) && player->InSamePhase(me) &&
                        Expired(Now(), bornAt, kind.lifeMs))
                        kind.timedOut(player, me->GetPosition());
                    Forget(owner.GetRawValue(), me->GetGUID());
                    me->DespawnOrUnsummon();
                    return;
                }
                clock += diff;
                Pulse(player, diff);
                if (!Follows(kind.staysPut))
                {
                    // a decoy stands where it was raised: it follows no one and strikes no one
                    if (me->GetVictim())
                        me->AttackStop();
                    return;
                }
                Watch(player, diff);
                Hasted const haste = HasteOf(owner.GetRawValue(), kind.group);
                Run(haste.movePct);
                Unit* target = Aim(player);
                if (!target)
                {
                    if (me->GetVictim())
                        me->AttackStop();
                    if (me->GetMotionMaster()->GetCurrentMovementGeneratorType() != FOLLOW_MOTION_TYPE)
                        me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE);
                    return;
                }
                if (kind.damagePct <= 0)
                    return;
                if (me->GetVictim() != target)
                    AttackStart(target);
                bool const commanded = OrderedAt(owner.GetRawValue(), kind.group) == target->GetGUID();
                double const aps = CommandedRate(Combat::AttacksPerSecond(player) * Combat::ItemPowers::PetSpeedFactor(player),
                                                 commanded, kind.commandSpeedPct);
                double const wait = SwingMs(aps, kind.swingMs) / (1.0 + std::max(0.0, haste.attackPct) / 100.0);
                if (wait <= 0 || clock < wait || !InReach(target))
                    return;
                clock = 0;
                double const against = kind.bonusAgainst ? kind.bonusAgainst(player, target) : 0.0;
                double const share = PerHit(BoostedPct(BoostedPct(BlowPct(kind.damagePct, commanded, kind.commandBonusPct),
                                                                  BoostOf(owner.GetRawValue(), kind.group)),
                                                       against),
                                            kind.hitsPerSwing);
                Combat::PetBlow const blow(MeleeCoefficient());
                for (unsigned i = 0; i < std::max(1u, kind.hitsPerSwing); ++i)
                    if (Combat::Strike(player, target, kind.record, share))
                    {
                        if (kind.struck)
                            kind.struck(player, target);
                        if (kind.struckBy)
                            kind.struckBy(player, me, target);
                        Struck(player, target);
                    }
            }

        private:
            ObjectGuid owner;
            Kind kind;
            std::uint64_t bornAt = 0;
            double clock = 0;
            double auraClock = 0;
            double watchClock = 0;
            float baseRun = 1.0f;
            double runPct = 0;
            HitLimit hitLimit;

            // Whether `target` is near enough to strike: in melee range, or inside the kind's range (which it closes on).
            bool InReach(Unit* target)
            {
                if (kind.rangeYards <= 0)
                    return me->IsWithinMeleeRange(target);
                if (me->GetExactDist(target) > kind.rangeYards)
                {
                    me->GetMotionMaster()->MoveChase(target, kind.rangeYards * 0.8f);
                    return false;
                }
                return true;
            }

            // The kind's own look at its surroundings, every `watchEveryMs`.
            void Watch(Player* player, uint32 diff)
            {
                if (!kind.watch || kind.watchEveryMs == 0)
                    return;
                watchClock += diff;
                if (watchClock < kind.watchEveryMs)
                    return;
                watchClock = 0;
                kind.watch(player, me);
            }

            // Its run speed `pct` percent over what it was raised with.
            void Run(double pct)
            {
                if (pct == runPct)
                    return;
                runPct = pct;
                me->SetSpeedRate(MOVE_RUN, baseRun * float(1.0 + std::max(0.0, pct) / 100.0));
            }

            // The proc coefficient of this creature's own melee attack (the combat tunable pet_proc_coefficient_<entry>, from its power file);
            // none when the attack states none.
            std::optional<double> MeleeCoefficient() const
            {
                std::string const name = "pet_proc_coefficient_" + std::to_string(kind.entry);
                if (!Tunables::Has("combat", name))
                    return std::nullopt;
                return Tunables::Get("combat", name);
            }

            // The aura: every pulse (a second, unless the kind says otherwise), each enemy within the radius is struck for the kind's weapon damage.
            void Pulse(Player* player, uint32 diff)
            {
                if (kind.auraRadius <= 0 || kind.auraPct <= 0)
                    return;
                Combat::PetBlow const blow(MeleeCoefficient());
                auraClock += diff;
                double const every = kind.auraEveryMs ? double(kind.auraEveryMs) : 1000.0;
                std::uint32_t const record = kind.auraRecord ? kind.auraRecord : kind.record;
                while (auraClock >= every)
                {
                    auraClock -= every;
                    for (Unit* enemy : Combat::Enemies(player, record, me->GetPosition(), kind.auraRadius))
                        if (Combat::Strike(player, enemy, record,
                                           BoostedPct(kind.auraPct, kind.bonusAgainst ? kind.bonusAgainst(player, enemy) : 0.0), true))
                            Struck(player, enemy);
                }
            }

            // What the minion attacks: the target its group was ordered at, else the owner's own, else nothing.
            Unit* Aim(Player* player) const
            {
                auto usable = [player](Unit* unit)
                { return unit && unit->IsAlive() && player->IsValidAttackTarget(unit); };
                if (ObjectGuid const ordered = OrderedAt(owner.GetRawValue(), kind.group))
                    if (Unit* unit = ObjectAccessor::GetUnit(*me, ordered); usable(unit))
                        return unit;
                Unit* victim = player->GetVictim();
                Unit* selected = player->GetSelectedUnit();
                return usable(victim) ? victim : player->IsInCombat() && usable(selected) ? selected : nullptr;
            }
        };

        class Script final : public CreatureScript
        {
        public:
            Script()
                : CreatureScript("dc_minion")
            {
            }
            CreatureAI* GetAI(Creature* creature) const override
            {
                return new MinionAI(creature);
            }
        };

        // The owner leaves or changes floor: everything it raised goes with it.
        class Owner final : public PlayerScript
        {
        public:
            Owner()
                : PlayerScript("dc_minions_owner", {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }
            void OnPlayerLogout(Player* player) override
            {
                DismissAll(player);
                std::lock_guard<std::mutex> guard(mutex);
                owners.erase(player->GetGUID().GetRawValue());
            }
            void OnPlayerMapChanged(Player* player) override
            {
                DismissAll(player);
            }
        };

        // .dc minion raise <key> | clear | list: the kinds a class defined, for a GM to try them without the skill.
        bool HandleRaise(ChatHandler* handler, std::string key)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            Position const at = player->GetNearPosition(PET_FOLLOW_DIST, PET_FOLLOW_ANGLE);
            Kind made;
            if (!Made(key, player, made))
            {
                handler->PSendSysMessage("No minion kind '{}' (see .dc minion list).", key);
                return true;
            }
            Creature* minion = Raise(player, key, at, 0, made.lifeToCopyPct > 0);
            handler->PSendSysMessage(minion ? "Raised {} (group {}, {} standing)." : "Could not raise {}.", key,
                                     made.group, Alive(player, made.group));
            return true;
        }

        bool HandleClear(ChatHandler* handler)
        {
            if (Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr)
                DismissAll(player);
            return true;
        }

        bool HandleList(ChatHandler* handler)
        {
            std::lock_guard<std::mutex> guard(defsMutex);
            for (auto const& [key, make] : defs)
                handler->PSendSysMessage("{}", key);
            return true;
        }

        class Commands final : public CommandScript
        {
        public:
            Commands()
                : CommandScript("dc_minions_commands")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable minion = {{"raise", HandleRaise, SEC_GAMEMASTER, Console::No},
                                                  {"clear", HandleClear, SEC_GAMEMASTER, Console::No},
                                                  {"list", HandleList, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable dc = {{"minion", minion}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
        };
    } // namespace

    void OnStruck(StruckListener listener)
    {
        struckListeners.push_back(std::move(listener));
    }

    void Define(std::string key, std::function<Kind(Player*)> make)
    {
        std::lock_guard<std::mutex> guard(defsMutex);
        defs[std::move(key)] = std::move(make);
    }

    unsigned Alive(Player* owner, std::string_view group)
    {
        if (!owner)
            return 0;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = owners.find(owner->GetGUID().GetRawValue());
        if (found == owners.end())
            return 0;
        auto& list = found->second.minions;
        // Only what still stands: a minion unsummoned by the core is dropped here.
        list.erase(std::remove_if(list.begin(), list.end(),
                                  [&](Entry const& e)
                                  {
                                      Creature* creature = ObjectAccessor::GetCreature(*owner, e.guid);
                                      return !creature || !creature->IsAlive() || !creature->IsInWorld();
                                  }),
                   list.end());
        return unsigned(std::count_if(list.begin(), list.end(), [&](Entry const& e) { return e.group == group; }));
    }

    std::vector<Creature*> Standing(Player* owner, std::string_view group)
    {
        std::vector<Creature*> out;
        if (!owner)
            return out;
        std::vector<ObjectGuid> guids;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = owners.find(owner->GetGUID().GetRawValue());
            if (found == owners.end())
                return out;
            for (Entry const& e : found->second.minions)
                if (e.group == group)
                    guids.push_back(e.guid);
        }
        for (ObjectGuid guid : guids)
            if (Creature* creature = ObjectAccessor::GetCreature(*owner, guid);
                creature && creature->IsAlive() && creature->IsInWorld())
                out.push_back(creature);
        return out;
    }

    void Boost(Player* owner, std::string_view group, double pct, std::uint32_t ms, std::string_view source)
    {
        if (!owner)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        owners[owner->GetGUID().GetRawValue()].boosts[std::string(group)][std::string(source)] = {pct, Now() + ms};
    }

    double BoostPercent(Player* owner, std::string_view group)
    {
        return owner ? BoostOf(owner->GetGUID().GetRawValue(), std::string(group)) : 0.0;
    }

    void Haste(Player* owner, std::string_view group, double attackPct, double movePct, std::uint32_t ms,
               std::string_view source)
    {
        if (!owner)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        owners[owner->GetGUID().GetRawValue()].hastes[std::string(group)][std::string(source)] = {attackPct, movePct,
                                                                                                  Now() + ms};
    }

    std::optional<Position> DismissOldest(Player* owner, std::string_view group)
    {
        if (!owner)
            return std::nullopt;
        ObjectGuid oldest;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = owners.find(owner->GetGUID().GetRawValue());
            if (found == owners.end())
                return std::nullopt;
            std::uint64_t bornAt = ~0ull;
            for (Entry const& e : found->second.minions)
                if (e.group == group && e.bornAt < bornAt)
                {
                    bornAt = e.bornAt;
                    oldest = e.guid;
                }
        }
        Creature* creature = oldest ? ObjectAccessor::GetCreature(*owner, oldest) : nullptr;
        if (!creature)
            return std::nullopt;
        Position const where = creature->GetPosition();
        Forget(owner->GetGUID().GetRawValue(), oldest);
        creature->DespawnOrUnsummon();
        return where;
    }

    void Dismiss(Player* owner, std::string_view group, std::uint32_t holdMs)
    {
        if (!owner)
            return;
        std::vector<ObjectGuid> gone;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = owners.find(owner->GetGUID().GetRawValue());
            if (found == owners.end())
                return;
            if (holdMs)
            {
                std::uint64_t& next = found->second.nextAt[std::string(group)];
                next = std::max(next, Now() + holdMs);
            }
            auto& list = found->second.minions;
            for (Entry const& e : list)
                if (e.group == group)
                    gone.push_back(e.guid);
            list.erase(std::remove_if(list.begin(), list.end(), [&](Entry const& e) { return e.group == group; }),
                       list.end());
        }
        for (ObjectGuid guid : gone)
            if (Creature* creature = ObjectAccessor::GetCreature(*owner, guid))
                creature->DespawnOrUnsummon();
    }

    unsigned Count(Player* owner)
    {
        if (!owner)
            return 0;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = owners.find(owner->GetGUID().GetRawValue());
        return found == owners.end() ? 0u : unsigned(found->second.minions.size());
    }

    unsigned DismissAll(Player* owner)
    {
        if (!owner)
            return 0;
        std::vector<ObjectGuid> gone;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = owners.find(owner->GetGUID().GetRawValue());
            if (found == owners.end())
                return 0;
            for (Entry const& e : found->second.minions)
                gone.push_back(e.guid);
            found->second.minions.clear();
            found->second.orders.clear();
        }
        for (ObjectGuid guid : gone)
            if (Creature* creature = ObjectAccessor::GetCreature(*owner, guid))
                creature->DespawnOrUnsummon();
        return unsigned(gone.size());
    }

    void Command(Player* owner, std::string_view group, Unit* target, std::uint32_t ms)
    {
        if (!owner || !target)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        owners[owner->GetGUID().GetRawValue()].orders[std::string(group)] = {target->GetGUID(), Now() + ms};
    }

    bool IsOrdered(Player* owner, std::string_view group, Unit const* target)
    {
        return owner && target && OrderedAt(owner->GetGUID().GetRawValue(), std::string(group)) == target->GetGUID();
    }

    Creature* Raise(Player* owner, std::string const& key, Position const& at, std::uint32_t display, bool copyOwner)
    {
        Kind kind;
        if (!owner || !owner->IsInWorld() || !owner->IsAlive() || !Made(key, owner, kind))
            return nullptr;
        // The group is full: the oldest of it goes to make room.
        if (Admission const admission = Admit(Alive(owner, kind.group), kind.cap); admission.dismissOldest)
        {
            ObjectGuid oldest;
            {
                std::lock_guard<std::mutex> guard(mutex);
                std::uint64_t bornAt = ~0ull;
                for (Entry const& e : owners[owner->GetGUID().GetRawValue()].minions)
                    if (e.group == kind.group && e.bornAt < bornAt)
                    {
                        bornAt = e.bornAt;
                        oldest = e.guid;
                    }
            }
            if (Creature* creature = ObjectAccessor::GetCreature(*owner, oldest))
            {
                Forget(owner->GetGUID().GetRawValue(), oldest);
                creature->DespawnOrUnsummon();
            }
        }
        // The core's own timer on a timed minion runs this much behind the AI's, so the AI sees the end first and can
        // act on it (Kind::ended).
        std::uint32_t const net = Millis(DC::Tunables::Get("combat", "minion_timer_net_seconds"));
        TempSummon* summon = owner->SummonCreature(
            kind.entry, at, kind.lifeMs ? TEMPSUMMON_TIMED_OR_DEAD_DESPAWN : TEMPSUMMON_DEAD_DESPAWN,
            kind.lifeMs + net);
        if (!summon)
            return nullptr;
        MinionAI* mind = dynamic_cast<MinionAI*>(summon->AI());
        if (!mind || !summon->IsInWorld())
        {
            summon->DespawnOrUnsummon();
            return nullptr;
        }
        std::uint64_t const now = Now();
        mind->Configure(owner, kind, now);
        if (display)
            summon->SetDisplayId(display);
        if (copyOwner)
            owner->CastSpell(summon, CloneMe, true);
        if (kind.lifeToCopyPct > 0)
        {
            summon->SetMaxHealth(CopyLife(owner->GetMaxHealth(), kind.lifeToCopyPct));
            summon->SetHealth(summon->GetMaxHealth());
        }
        std::lock_guard<std::mutex> guard(mutex);
        owners[owner->GetGUID().GetRawValue()].minions.push_back({summon->GetGUID(), kind.group, now});
        return summon;
    }

    bool Keep(Player* owner, std::string const& key, unsigned wanted, std::uint32_t intervalMs, std::uint32_t returnMs)
    {
        Kind kind;
        if (!owner || !owner->IsInWorld() || !owner->IsAlive() || !Made(key, owner, kind))
            return false;
        unsigned const alive = Alive(owner, kind.group);
        std::uint64_t const now = Now();
        {
            std::lock_guard<std::mutex> guard(mutex);
            Owned& state = owners[owner->GetGUID().GetRawValue()];
            state.returnMs[kind.group] = returnMs;
            if (!KeeperDue(now, state.nextAt[kind.group], alive, wanted))
                return false;
            state.nextAt[kind.group] = NextAfterRaise(now, intervalMs);
        }
        return Raise(owner, key, owner->GetNearPosition(PET_FOLLOW_DIST, PET_FOLLOW_ANGLE)) != nullptr;
    }

    void RegisterScripts()
    {
        new Script();
        new Owner();
        new Commands();
    }
} // namespace DC::Combat::Minions
