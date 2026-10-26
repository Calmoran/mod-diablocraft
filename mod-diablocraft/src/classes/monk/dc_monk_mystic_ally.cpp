/*
 * Mystic Ally. The sheets: monk_skills.csv, monk_runes.csv, monk_skill_values.csv, monk_summons.csv (the
 * creatures) and monk.csv (the power file's numbers the sheets lack); the power file Power/X1_Monk_MysticAlly_v2.pow.
 *
 * The carrier is the Wizard's summon path (a generated creature template per ally, its AI here) with the Hydra's
 * damage: every hit of the ally is Combat::Strike, the Monk's own formula at the sheet's percentage. The Passive is the
 * ally itself: it is there while the skill is on the bar, reborn 5 seconds after it dies, and its rune's bonus holds
 * while it lives. The Active is the record's cast, on its own cooldown.
 */

#include "dc_monk_common.h"
#include "../dc_level_heal.h"
#include "dc_monk_mystic_ally.h"
#include "dc_monk_spirit.h"
#include "../../combat/dc_item_powers.h"
#include "../../stats/dc_resource_pulse.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "PetDefines.h"
#include "ScriptMgr.h"
#include "ScriptedCreature.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"

#include <unordered_set>

namespace DC::Combat::Monk::MysticAlly
{
    namespace
    {
        constexpr std::string_view Skill = "Mystic Ally";
        // Stock "Ice Blast" (15878), the freeze Fists of Thunder - Wind Blast holds an enemy with (dc_monk.cpp
        // FreezeHold).
        constexpr std::uint32_t FreezeHold = 15878;
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, the slow Crippling Wave's daze uses; its amount is set
        // to the sheet's slow_pct.
        constexpr std::uint32_t Slow = 50259;
        // How often a Monk's bar is looked at for the ally (not a game number: how soon a slotted ally appears).
        constexpr std::uint64_t PollMs = 250;

        std::recursive_mutex mutex;

        // One ally of the Monk: the first is the skill's own, the rest are The Crudest Boots's (`summon_count_add`).
        struct Slot
        {
            ObjectGuid ally;
            std::uint32_t summoned = 0; // the record the living ally is for; 0 when there is none
            std::uint64_t rebornAt = 0; // ms the dead or spent ally comes back
        };

        struct State
        {
            std::vector<Slot> slots = std::vector<Slot>(1);
            std::uint64_t nextPoll = 0;
            std::uint32_t applied = 0; // the record whose Passive bonus is on the sheet now
            unsigned builtLevel = 0;   // the level Enduring Ally's regeneration on the sheet was built at
            std::uint64_t spiritClock = 0;
            std::uint64_t empoweredUntil = 0; // the base Active: the ally's damage +50% until then
        };
        std::unordered_map<std::uint64_t, State> states;

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(std::llround(std::max(0.0, seconds) * 1000.0));
        }

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        std::uint32_t IdOf(std::string_view rune)
        {
            for (auto const& ability : Shells::Abilities)
                if (Skill == ability.skill && rune == ability.rune)
                    return ability.id;
            return 0;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Row(spellId);
            return row && rune == row->rune;
        }

        // The Mystic Ally record on the player's skill buttons (as Classes::WriteActionBar puts them), 0 when none.
        std::uint32_t Slotted(Player* player)
        {
            for (unsigned slot = 0; slot < Classes::ActiveSlots(); ++slot)
                if (ActionButton const* button = player->GetActionButton(uint8(slot)))
                    if (button->GetType() == ACTION_BUTTON_SPELL && Row(button->GetAction()))
                        return button->GetAction();
            return 0;
        }

        // monk_summons.csv: the creature of each record (the rune's own row, else the skill's).
        std::uint32_t EntryOf(std::uint32_t spellId)
        {
            auto const* row = Row(spellId);
            if (!row)
                return 0;
            std::string_view const rune = row->rune;
            if (rune == "Fire Ally")
                return 900131;
            if (rune == "Water Ally")
                return 900132;
            if (rune == "Earth Ally")
                return 900133;
            if (rune == "Air Ally")
                return 900134;
            if (rune == "Enduring Ally")
                return 900135;
            return 900130;
        }

        Creature* AllyOf(Player* player, Slot const& slot)
        {
            Creature* creature = slot.ally ? ObjectAccessor::GetCreature(*player, slot.ally) : nullptr;
            return creature && creature->IsAlive() ? creature : nullptr;
        }

        // The record the Monk's allies are for: the first slot that has one (0 when none lives).
        std::uint32_t Summoned(State const& state)
        {
            for (Slot const& slot : state.slots)
                if (slot.summoned)
                    return slot.summoned;
            return 0;
        }

        // The Crudest Boots, asked before any lock of ours (the item powers keep a lock of their own).
        unsigned ExtraAllies(Player* player)
        {
            return unsigned(Combat::ItemPowers::SkillSetTo(player, std::string(Skill), "summon_count_add", 0));
        }

        // "able to attack with their active forms longer": the seconds of an active form, a percent longer when the Boots are worn.
        // The percent is the tunable monk.mystic_ally_boots_form_duration_pct.
        double FormSeconds(Player* player, double seconds)
        {
            return MysticAlly::FormSeconds(seconds, ExtraAllies(player) > 0, Tune("mystic_ally_boots_form_duration_pct"));
        }

        void Send(Creature* creature)
        {
            if (TempSummon* summon = creature ? creature->ToTempSummon() : nullptr)
                summon->UnSummon();
        }

        void Hold(Player* player, Unit* target, std::uint32_t aura, int amount, double seconds)
        {
            if (seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(aura, player->GetGUID());
            if (Aura* held = player->AddAura(aura, target))
            {
                held->SetMaxDuration(int32(seconds * 1000));
                held->SetDuration(int32(seconds * 1000));
                if (amount)
                    if (AuraEffect* effect = held->GetEffect(EFFECT_0))
                        effect->ChangeAmount(amount);
            }
        }

        // The Passive bonuses that sit on the stat sheet: Earth Ally's Life and Enduring Ally's Life per Second, under
        // the rune's id while that ally lives. Enduring's "heal amount is increased by {life_per_second_share_pct} of
        // your Life per Second" reads the sheet without its own row.
        void Sheet(Player* player, std::uint32_t applied)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const earth = IdOf("Earth Ally"), enduring = IdOf("Enduring Ally");
            Stats::RemoveContribution(guid, Source::Temporary, Stat::LifePercent, earth);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::LifeRegen, enduring);
            Stats::Recompute(player);
            if (applied && applied == earth)
                Stats::AddContribution(guid, {Source::Temporary, Stat::LifePercent, earth,
                                              Numbers::Num(earth, "max_life_pct"), Bucket::Flat});
            if (applied && applied == enduring)
            {
                auto const sheet = Stats::Get(guid);
                double const regen = sheet ? (*sheet)[Stat::LifeRegen] : 0;
                Stats::AddContribution(guid, {Source::Temporary, Stat::LifeRegen, enduring,
                                              Classes::HealAtLevel(Numbers::Num(enduring, "heal_per_second_life"), player->GetLevel()) +
                                                  regen * Numbers::Num(enduring, "life_per_second_share_pct") / 100,
                                              Bucket::Flat});
            }
            if (applied == earth || applied == enduring)
                Stats::Recompute(player);
        }

        void Spent(Player*, Slot& slot)
        {
            slot.summoned = 0;
            slot.ally.Clear();
            slot.rebornAt = Now() + Millis(Numbers::Num(IdOf(""), "duration_seconds", "respawn"));
        }

        // --- the ally ------------------------------------------------------------------------------------------------

        class AllyAI final : public ScriptedAI
        {
        public:
            enum class Mode
            {
                Fight,   // the Passive's ally: follows, fights the Monk's target
                Boulder, // Earth Ally's Active
                Bomb,    // one of Fire Ally's exploding allies
            };

            explicit AllyAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            void Configure(Player* player, std::uint32_t spellId, Mode mode, unsigned index)
            {
                owner = player->GetGUID();
                record = spellId;
                this->mode = mode;
                me->SetOwnerGUID(owner);
                me->SetCreatorGUID(owner);
                me->SetFaction(player->GetFaction());
                me->SetLevel(player->GetLevel());
                me->SetReactState(REACT_PASSIVE);
                me->SetMaxHealth(std::max<uint32>(
                    1, uint32(std::min(double(UINT32_MAX),
                                       player->GetMaxHealth() * Tune("mystic_ally_life_pct") / 100.0))));
                me->SetHealth(me->GetMaxHealth());
                me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE + float(index));
            }

            // Earth Ally's Active: a boulder for the rune's seconds.
            void Roll(double seconds)
            {
                mode = Mode::Boulder;
                left = Millis(seconds);
                clock = 0;
                knocked.clear();
                baseRate = me->GetSpeedRate(MOVE_RUN);
                me->AttackStop();
                me->SetSpeedRate(MOVE_RUN,
                                 float(Tune("mystic_ally_earth_speed_yards_per_second") / baseMoveSpeed[MOVE_RUN]));
            }

            // Fire Ally's exploding ally: runs at an enemy and explodes, or explodes where it is when its time is up.
            void Arm(double seconds)
            {
                mode = Mode::Bomb;
                left = Millis(seconds);
            }

            // The ally (fighting or rolling) is reborn after the respawn time; a Fire bomb is only gone.
            void JustDied(Unit*) override
            {
                if (mode != Mode::Bomb)
                    if (Player* player = ObjectAccessor::FindConnectedPlayer(owner))
                    {
                        std::lock_guard<std::recursive_mutex> guard(mutex);
                        for (Slot& slot : states[player->GetGUID().GetRawValue()].slots)
                            if (slot.ally == me->GetGUID())
                                Spent(player, slot);
                    }
                Send(me);
            }

            void UpdateAI(uint32 diff) override
            {
                Player* player = ObjectAccessor::FindConnectedPlayer(owner);
                if (!player || !player->IsAlive() || !player->IsInMap(me) || !player->InSamePhase(me))
                {
                    Send(me);
                    return;
                }
                switch (mode)
                {
                    case Mode::Fight:
                        Fight(player, diff);
                        break;
                    case Mode::Boulder:
                        Boulder(player, diff);
                        break;
                    case Mode::Bomb:
                        Bomb(player, diff);
                        break;
                }
            }

        private:
            ObjectGuid owner;
            std::uint32_t record = 0;
            Mode mode = Mode::Fight;
            std::uint64_t left = 0;
            double clock = 0;
            float baseRate = 1;
            std::unordered_set<std::uint64_t> knocked;
            bool exploded = false;

            // "The ally deals {damage_pct} of your weapon damage as Physical per swing", at the Monk's attacks per
            // second (power file SF_53 'Attack Speed' = Attacks_Per_Second_Total; Tasker and Theo's pet speed as on
            // every pet). The target is the Ancients' pick: the Monk's attack target, else his selection while he
            // fights.
            void Fight(Player* player, uint32 diff)
            {
                Unit* victim = player->GetVictim();
                Unit* selected = player->GetSelectedUnit();
                auto usable = [player](Unit* unit)
                { return unit && unit->IsAlive() && player->IsValidAttackTarget(unit); };
                Unit* target = usable(victim) ? victim : player->IsInCombat() && usable(selected) ? selected : nullptr;
                if (!target)
                {
                    if (me->GetVictim())
                        me->AttackStop();
                    if (me->GetMotionMaster()->GetCurrentMovementGeneratorType() != FOLLOW_MOTION_TYPE)
                        me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE);
                    return;
                }
                if (me->GetVictim() != target)
                    AttackStart(target);
                clock += diff;
                double const aps = Combat::AttacksPerSecond(player) * Combat::ItemPowers::PetSpeedFactor(player);
                if (aps <= 0 || clock < 1000 / aps || !me->IsWithinMeleeRange(target))
                    return;
                clock = 0;
                std::uint32_t const skill = IdOf("");
                double pct = Numbers::Own(skill, "damage_pct").value_or(0);
                {
                    // "Active: Your mystic ally has its damage increased by {damage_bonus_pct} for
                    // {duration_seconds:active} seconds."
                    std::lock_guard<std::recursive_mutex> guard(mutex);
                    if (Now() < states[player->GetGUID().GetRawValue()].empoweredUntil)
                        pct *= 1 + Numbers::Own(skill, "damage_bonus_pct").value_or(0) / 100;
                }
                Combat::Strike(player, target, skill, pct);
            }

            // "turns into a boulder for {duration_seconds} seconds. The boulder deals {damage_pct} weapon damage as
            // Physical every second and rolls toward nearby enemies, knocking them up."
            void Boulder(Player* player, uint32 diff)
            {
                if (left <= diff)
                {
                    me->SetSpeedRate(MOVE_RUN, baseRate);
                    mode = Mode::Fight;
                    me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE);
                    return;
                }
                left -= diff;
                clock += diff;
                double const tick = Tune("mystic_ally_earth_tick_seconds");
                if (tick <= 0 || clock < tick * 1000)
                    return;
                clock = 0;
                auto enemies = Combat::Enemies(player, record, player->GetPosition(),
                                               Tune("mystic_ally_earth_search_radius_yards"));
                if (!enemies.empty())
                {
                    Unit* nearest = *std::min_element(enemies.begin(), enemies.end(), [this](Unit* a, Unit* b)
                                                      { return me->GetExactDist(a) < me->GetExactDist(b); });
                    me->GetMotionMaster()->MovePoint(0, nearest->GetPosition());
                }
                Knock const knock =
                    KnockUp(Tune("mystic_ally_earth_knockup_height_yards"), Tune("mystic_ally_earth_knockback_yards"));
                for (Unit* enemy :
                     Combat::StrikeArea(player, record, me->GetPosition(), Tune("mystic_ally_earth_radius_yards"),
                                        Numbers::Num(record, "damage_pct") * tick))
                    if (knock.z > 0 && knocked.insert(enemy->GetGUID().GetRawValue()).second && enemy->IsAlive())
                        enemy->KnockbackFrom(me->GetPositionX(), me->GetPositionY(), float(knock.xy), float(knock.z));
            }

            // "Your mystic ally splits into {pet_count} allies that explode for {damage_pct} weapon damage as Fire."
            void Bomb(Player* player, uint32 diff)
            {
                if (exploded)
                    return;
                double const radius = Tune("mystic_ally_fire_explosion_radius_yards");
                auto enemies =
                    Combat::Enemies(player, record, me->GetPosition(), Tune("mystic_ally_fire_search_radius_yards"));
                Unit* nearest = enemies.empty()
                                    ? nullptr
                                    : *std::min_element(enemies.begin(), enemies.end(), [this](Unit* a, Unit* b)
                                                        { return me->GetExactDist(a) < me->GetExactDist(b); });
                bool const there = nearest && me->GetExactDist(nearest) <= radius;
                if (!there && left > diff)
                {
                    left -= diff;
                    if (nearest && me->GetMotionMaster()->GetCurrentMovementGeneratorType() != POINT_MOTION_TYPE)
                        me->GetMotionMaster()->MovePoint(0, nearest->GetPosition());
                    return;
                }
                Combat::StrikeArea(player, record, me->GetPosition(), radius, Numbers::Num(record, "damage_pct"));
                exploded = true;
                Send(me);
            }
        };

        AllyAI* Mind(Creature* creature)
        {
            return creature ? dynamic_cast<AllyAI*>(creature->AI()) : nullptr;
        }

        TempSummon* Call(Player* player, std::uint32_t spellId, Position const& at, AllyAI::Mode mode, unsigned index,
                         TempSummonType type, uint32 ms)
        {
            TempSummon* summon = player->SummonCreature(EntryOf(spellId), at, type, ms);
            if (!summon)
                return nullptr;
            // The AI can be another script's (the rift hook swaps it): never
            // configure one that is not ours.
            AllyAI* mind = Mind(summon);
            if (!mind || !summon->IsInWorld())
            {
                summon->DespawnOrUnsummon();
                return nullptr;
            }
            mind->Configure(player, spellId, mode, index);
            return summon;
        }

        // One look at a player: the ally follows the bar, the Passive follows the ally, Air Ally pays its Spirit.
        void Upkeep(Player* player, uint32 diff)
        {
            std::uint64_t const now = Now();
            std::uint32_t applied = 0, previous = 0, air = 0;
            unsigned seconds = 0, level = player->GetLevel();
            bool due = false, stale = false;
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                due = now >= states[player->GetGUID().GetRawValue()].nextPoll;
            }
            // The Crudest Boots's extra allies, asked outside our lock and only on the poll.
            unsigned const extra = due ? ExtraAllies(player) : 0;
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                State& state = states[player->GetGUID().GetRawValue()];
                previous = applied = state.applied;
                if (applied && applied == IdOf("Air Ally"))
                    seconds = Seconds(state.spiritClock, diff);
                if (now >= state.nextPoll)
                {
                    state.nextPoll = now + PollMs;
                    std::uint32_t const slotted = player->IsAlive() ? Slotted(player) : 0;
                    unsigned const wanted = slotted ? AllyCount(extra) : 0;
                    if (state.slots.size() < wanted)
                        state.slots.resize(wanted);
                    for (unsigned i = 0; i < state.slots.size(); ++i)
                    {
                        Slot& slot = state.slots[i];
                        Creature* ally = AllyOf(player, slot);
                        if (!ally && slot.summoned)
                            Spent(player, slot); // gone without dying here (unsummoned, a map's clean-up)
                        std::uint32_t const bar = i < wanted ? slotted : 0; // the slots past the count are sent away
                        switch (Decide(bar, slot.summoned, slot.rebornAt, now))
                        {
                            case Act::Keep:
                                break;
                            case Act::Despawn:
                                Send(ally);
                                slot.ally.Clear();
                                slot.summoned = 0;
                                slot.rebornAt = 0;
                                break;
                            case Act::Replace:
                                Send(ally);
                                [[fallthrough]];
                            case Act::Summon:
                                slot.ally.Clear();
                                slot.summoned = 0;
                                if (TempSummon* summon = Call(player, bar, player->GetPosition(), AllyAI::Mode::Fight, i,
                                                              TEMPSUMMON_MANUAL_DESPAWN, 0))
                                {
                                    slot.ally = summon->GetGUID();
                                    slot.summoned = bar;
                                    slot.rebornAt = 0;
                                }
                                break;
                        }
                    }
                    // the slots past the count that hold nothing any more go; the first always stays
                    while (state.slots.size() > std::max<std::size_t>(1, wanted) && !state.slots.back().summoned)
                        state.slots.pop_back();
                    applied = state.applied = Summoned(state);
                    if (applied != previous)
                        state.spiritClock = 0;
                }
                // Enduring Ally's Life per Second is the Healing table at the level: a level-up rebuilds it.
                stale = applied && applied == IdOf("Enduring Ally") && Classes::BuiltAtOtherLevel(state.builtLevel, level);
                if (applied != previous || stale)
                    state.builtLevel = level;
                air = applied && applied == IdOf("Air Ally") ? applied : 0;
            }
            if (applied != previous || stale)
                Sheet(player, applied);
            // "increases your Spirit Regeneration by {regen_per_second_resource}", as a flow over the seconds it is
            // for.
            if (air && seconds)
                Resources::Flow(player, Resources::Spirit, Numbers::Num(air, "regen_per_second_resource") * seconds,
                                seconds * 1000);
        }

        void Leave(Player* player)
        {
            std::uint32_t applied = 0;
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                auto found = states.find(player->GetGUID().GetRawValue());
                if (found == states.end())
                    return;
                for (Slot const& slot : found->second.slots)
                    Send(AllyOf(player, slot));
                applied = found->second.applied;
                states.erase(found);
            }
            if (applied)
                Sheet(player, 0);
        }

        class Script final : public CreatureScript
        {
        public:
            Script()
                : CreatureScript("dc_monk_ally")
            {
            }
            CreatureAI* GetAI(Creature* creature) const override
            {
                return new AllyAI(creature);
            }
        };

        class Keeper final : public PlayerScript
        {
        public:
            Keeper()
                : PlayerScript("dc_monk_mystic_ally",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }
            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Upkeep(player, diff);
            }
            void OnPlayerLogout(Player* player) override
            {
                Leave(player);
            }
            // The ally stays behind on the old map; the next look brings a new one at once.
            void OnPlayerMapChanged(Player* player) override
            {
                Leave(player);
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    // The records hit nothing themselves: every number of theirs is the ally's or the Active's (the loader would give
    // Fire Ally's record its 1920% and Water Ally's its 625% as a hit on the cast).
    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Row(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Row(spellId))
            return;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        // The Crudest Boots: the Active is every ally's, and their active forms last longer.
        double const window = FormSeconds(player, IsRune(spellId, "") ? Numbers::Num(spellId, "duration_seconds", "active") : 0);
        std::vector<Creature*> allies;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = states[guid];
            for (Slot const& slot : state.slots)
                if (slot.summoned == spellId)
                    if (Creature* living = AllyOf(player, slot))
                        allies.push_back(living);
            if (IsRune(spellId, ""))
                state.empoweredUntil = Now() + Millis(window);
        }
        // "Active: You gain {gain_resource} Spirit."
        if (IsRune(spellId, "Air Ally"))
            Generate(player, Classes::ClassIdOf(player), spellId, Numbers::Num(spellId, "gain_resource"));
        // The other runes' Actives are the ally's: with no ally of this rune alive (reborn in a moment), nothing
        // happens.
        if (allies.empty())
            return;
        if (IsRune(spellId, "Enduring Ally"))
        {
            // "Your mystic ally sacrifices itself to heal you for {heal_pct} of your maximum Life." Each living ally of the
            // rune sacrifices itself and pays the heal once per press: two allies heal twice. Every ally is spent.
            for (std::size_t paid = 0; paid < allies.size(); ++paid)
            {
                HealInfo heal(player, player, uint32(player->GetMaxHealth() * Numbers::Num(spellId, "heal_pct") / 100),
                              sSpellMgr->GetSpellInfo(spellId), SPELL_SCHOOL_MASK_NORMAL);
                player->HealBySpell(heal);
            }
        }
        else if (IsRune(spellId, "Fire Ally"))
        {
            unsigned const count = unsigned(Numbers::Num(spellId, "pet_count"));
            double const seconds = FormSeconds(player, Tune("mystic_ally_fire_max_seconds"));
            unsigned index = 0;
            for (Creature* ally : allies)
                for (unsigned i = 0; i < count; ++i, ++index)
                    if (TempSummon* bomb = Call(player, spellId, ally->GetPosition(), AllyAI::Mode::Fight, index,
                                                TEMPSUMMON_TIMED_DESPAWN, uint32(Millis(seconds) + 1000)))
                        if (AllyAI* mind = Mind(bomb))
                            mind->Arm(seconds);
        }
        else if (IsRune(spellId, "Earth Ally"))
        {
            for (Creature* ally : allies)
                if (AllyAI* mind = Mind(ally))
                    mind->Roll(FormSeconds(player, Numbers::Num(spellId, "duration_seconds")));
            return;
        }
        else if (IsRune(spellId, "Water Ally"))
        {
            // "performs {hit_count} wave attacks in quick succession, each dealing {damage_pct} weapon damage as Cold
            // and Freezing enemies for {freeze_duration_seconds} seconds": each wave a strip ahead of the ally, toward
            // what it fights (else where it faces).
            unsigned const waves = unsigned(Numbers::Num(spellId, "hit_count"));
            std::uint64_t const every = Millis(Tune("mystic_ally_water_wave_interval_seconds"));
            for (Creature* ally : allies)
                for (unsigned i = 0; i < waves; ++i)
                {
                    ObjectGuid const allyGuid = ally->GetGUID();
                    player->m_Events.AddEventAtOffset(
                    [player, allyGuid, spellId]
                    {
                        Creature* from = ObjectAccessor::GetCreature(*player, allyGuid);
                        if (!from || !from->IsAlive() || !player->IsAlive())
                            return;
                        Unit* aim = from->GetVictim();
                        float const facing = aim ? from->GetAngle(aim) : from->GetOrientation();
                        double const length = Tune("mystic_ally_water_wave_length_yards");
                        double const radius = Tune("mystic_ally_water_wave_radius_yards");
                        Point const origin{from->GetPositionX(), from->GetPositionY()};
                        for (Unit* enemy :
                             Combat::Enemies(player, spellId, from->GetPosition(), std::hypot(length, radius)))
                            if (InWave(origin, facing, length, radius,
                                       {enemy->GetPositionX(), enemy->GetPositionY()}) &&
                                Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct")))
                                Hold(player, enemy, FreezeHold, 0, Numbers::Num(spellId, "freeze_duration_seconds"));
                    },
                    Milliseconds(every * i));
                }
            return;
        }
        else
            return; // the base Active and Air Ally's touch no ally
        // Fire and Enduring spend the allies: each is reborn after the respawn time, and the Passive is off until one is.
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            for (Slot& slot : states[guid].slots)
                if (slot.summoned == spellId)
                    Spent(player, slot);
        }
        for (Creature* ally : allies)
            Send(ally);
    }

    // Water Ally's Passive: "infuses your attacks to Slow enemies by {slow_pct} for {slow_duration_seconds} seconds".
    // The ally's own hits are its, not the Monk's attacks.
    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || Row(spellId))
            return;
        std::uint32_t const water = IdOf("Water Ally");
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end() || !water || found->second.applied != water)
                return;
        }
        Hold(player, target, Slow, -int(Numbers::Num(water, "slow_pct")), Numbers::Num(water, "slow_duration_seconds"));
    }

    // Fire Ally's Passive: "increases your damage by {damage_bonus_pct}", in the damage_bonus_pct bucket.
    double DamageBonus(Player* player)
    {
        std::uint32_t const fire = IdOf("Fire Ally");
        if (!player || !fire)
            return 0;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto found = states.find(player->GetGUID().GetRawValue());
        return found != states.end() && found->second.applied == fire
                   ? Numbers::Own(fire, "damage_bonus_pct").value_or(0)
                   : 0;
    }

    void RegisterScripts()
    {
        new Script();
        new Keeper();
    }
} // namespace DC::Combat::Monk::MysticAlly
