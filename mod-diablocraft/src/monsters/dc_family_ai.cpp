/*
 * World of DiabloCraft - the family AI. See dc_family_ai.h; the pure rules are in
 * dc_family_ability.h and tested on their own (tests/family_ai/harness.cpp).
 */

#include "dc_family_ai.h"

#include "affixes/dc_affixes.h"
#include "../rifts/dc_rifts_internal.h"
#include "../combat/dc_combat.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "ChatCommand.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "Map.h"
#include "MotionMaster.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"

#include <mutex>
#include <optional>
#include <unordered_map>

namespace DC::Rifts::Family
{
    namespace
    {
        constexpr std::uint32_t FAMILY_FIRST = 950001, FAMILY_LAST = 950999;
        // Ids the movement hooks hand back (any value the stock movement does not use itself).
        constexpr std::uint32_t CHARGE_ID = 0xFA02, LEAP_ID = 0xFA03;
        // A physical stock spell (Slam) whose school and class DealMonsterHit reads for an ability with no donor of its
        // own: the charge, the leap and the summon-less blasts. It is never cast.
        constexpr std::uint32_t PLAIN_STRIKE = 1464;
        constexpr std::uint32_t SCAN_MS = 250, IN_FLIGHT_MS = 3000, CAST_SLACK_MS = 1500;

        // One dc_family_ability row joined to its dc_family_ability_ai row, as stored. Numbers are resolved at engage.
        struct RawAbility
        {
            std::uint32_t seq = 0, spell = 0, summonEntry = 0;
            std::string name, kind, trigger, key;
            std::optional<std::uint32_t> count;
            Layer cells;
        };

        std::mutex registryMutex;
        std::unordered_map<std::uint32_t, std::vector<RawAbility>> registry;

        std::optional<double> Cell(Field const& field)
        {
            if (field.IsNull())
                return std::nullopt;
            return field.Get<double>();
        }

        bool LoadRegistry()
        {
            QueryResult rows = WorldDatabase.Query(
                "SELECT a.entry,a.seq,a.ability,i.kind,i.trigger_code,a.wow_spell,i.summon_entry,i.count,a.cooldown_s,"
                "a.range_min_yd,a.range_max_yd,a.windup_s,a.projectiles,a.tunable_key FROM dc_family_ability a "
                "JOIN dc_family_ability_ai i ON i.entry=a.entry AND i.seq=a.seq WHERE i.built=1 ORDER BY "
                "a.entry,a.seq");
            std::unordered_map<std::uint32_t, std::vector<RawAbility>> loaded;
            std::size_t count = 0;
            if (rows)
                do
                {
                    Field* f = rows->Fetch();
                    RawAbility raw;
                    raw.seq = f[1].Get<std::uint32_t>();
                    raw.name = f[2].Get<std::string>();
                    raw.kind = f[3].Get<std::string>();
                    raw.trigger = f[4].Get<std::string>();
                    raw.spell = f[5].Get<std::uint32_t>();
                    raw.summonEntry = f[6].Get<std::uint32_t>();
                    if (!f[7].IsNull())
                        raw.count = f[7].Get<std::uint32_t>();
                    raw.cells.cooldownS = Cell(f[8]);
                    raw.cells.rangeMinYd = Cell(f[9]);
                    raw.cells.rangeMaxYd = Cell(f[10]);
                    raw.cells.windupS = Cell(f[11]);
                    raw.cells.count = Cell(f[12]);
                    raw.key = f[13].Get<std::string>();
                    loaded[f[0].Get<std::uint32_t>()].push_back(std::move(raw));
                    ++count;
                } while (rows->NextRow());
            std::lock_guard<std::mutex> lock(registryMutex);
            registry = std::move(loaded);
            LOG_INFO("server", "[DC family] {} built abilities for {} monsters (dc_family_ability_ai)", count,
                     registry.size());
            return count > 0;
        }

        // The numbers of one ability, layer by layer (monster-families.md 3.1): the sheet's cell, then the ability's
        // own tunable row, then the kind's default. A blank PLACEHOLDER row is not a number (Has says no).
        std::optional<double> Tunable(std::string const& name)
        {
            return DC::Tunables::Has("monsters", name) ? std::optional<double>(DC::Tunables::Get("monsters", name))
                                                       : std::nullopt;
        }

        Layer TunableLayer(std::string const& key)
        {
            Layer l;
            l.cooldownS = Tunable(key + "_cooldown_s");
            l.rangeMinYd = Tunable(key + "_range_min_yd");
            l.rangeMaxYd = Tunable(key + "_range_max_yd");
            l.windupS = Tunable(key + "_windup_s");
            l.count = Tunable(key + "_projectiles");
            return l;
        }

        Layer DefaultLayer(Kind kind)
        {
            std::string const base = std::string("ability_default_") + KindName(kind) + "_";
            Layer l;
            l.cooldownS = Tunable(base + "cooldown_s");
            l.rangeMinYd = Tunable(base + "range_min_yd");
            l.rangeMaxYd = Tunable(base + "range_max_yd");
            l.areaYd = Tunable(base + "area_yd");
            l.arcDeg = Tunable(base + "arc_deg");
            l.count = Tunable(base + "count");
            l.durationS = Tunable(base + "duration_s");
            l.tickS = Tunable(base + "tick_s");
            l.speedXy = Tunable(base + "speed_xy");
            l.speedZ = Tunable(base + "speed_z");
            return l;
        }

        double Multiplier(Kind kind)
        {
            std::string const name = std::string("ability_damage_") + KindName(kind);
            return DC::Tunables::Has("monsters", name) ? DC::Tunables::Get("monsters", name) : 1.0;
        }

        Donor DonorOf(std::uint32_t spell)
        {
            Donor donor;
            donor.spell = spell;
            if (SpellInfo const* info = spell ? sSpellMgr->GetSpellInfo(spell) : nullptr)
            {
                donor.castMs = info->CalcCastTime();
                donor.rangeMinYd = info->GetMinRange(false);
                donor.rangeMaxYd = info->GetMaxRange(false);
            }
            return donor;
        }

        // Which effects of a donor are damage, so the AI can give them its own number (or none). Weapon-damage effects
        // add the creature's own weapon on top of the base points, which is the monster's swing.
        bool IsDamageEffect(SpellEffectInfo const& effect)
        {
            switch (effect.Effect)
            {
                case SPELL_EFFECT_SCHOOL_DAMAGE:
                case SPELL_EFFECT_HEALTH_LEECH:
                case SPELL_EFFECT_WEAPON_DAMAGE:
                case SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL:
                case SPELL_EFFECT_NORMALIZED_WEAPON_DMG:
                    return true;
                case SPELL_EFFECT_APPLY_AURA:
                case SPELL_EFFECT_PERSISTENT_AREA_AURA:
                case SPELL_EFFECT_APPLY_AREA_AURA_ENEMY:
                    return effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE ||
                           effect.ApplyAuraName == SPELL_AURA_PERIODIC_LEECH ||
                           effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE_PERCENT;
                default:
                    return false;
            }
        }

        bool ValidPlayer(Creature const* me, Player* player)
        {
            return player && player->IsAlive() && player->IsInWorld() && me->IsInMap(player) &&
                   me->InSamePhase(player) && me->IsValidAttackTarget(player);
        }

        // The valid players of `me` in [minYd, maxYd] (maxYd 0 = no limit), optionally in line of sight.
        std::vector<Player*> PlayersIn(Creature* me, float minYd, float maxYd, bool needLos)
        {
            std::vector<Player*> out;
            Map* map = me->GetMap();
            if (!map)
                return out;
            // ponytail: walks every player of the map; a rift or a dev test map is small, an open-world map with a
            // crowd would want a grid search.
            map->DoForAllPlayers(
                [&](Player* player)
                {
                    if (!ValidPlayer(me, player))
                        return;
                    if (!InWindow(me->GetExactDist(player), minYd, maxYd))
                        return;
                    if (needLos && !me->IsWithinLOSInMap(player))
                        return;
                    out.push_back(player);
                });
            return out;
        }

        Player* PickAmong(Creature* me, std::vector<Player*> const& players, Rule rule)
        {
            std::vector<Candidate> candidates;
            Unit* victim = me->GetVictim();
            for (Player* player : players)
                candidates.push_back({player->GetGUID().GetRawValue(), me->GetExactDist(player), player == victim});
            int const index = PickIndex(candidates, rule, Roll());
            return index < 0 ? nullptr : players[static_cast<std::size_t>(index)];
        }

        Rule RuleOf(Trigger trigger)
        {
            switch (trigger)
            {
                case Trigger::Range:
                case Trigger::Gap:
                    return Rule::Random;
                case Trigger::Proximity:
                    return Rule::Nearest;
                default:
                    return Rule::Victim;
            }
        }

        // The window a trigger asks a target to stand in. A proximity ability watches its blast radius when it has no
        // reach of its own.
        void WindowOf(Ability const& a, float& minYd, float& maxYd)
        {
            minYd = a.minYd;
            maxYd = a.maxYd;
            if (a.trigger == Trigger::Proximity && maxYd <= 0)
                maxYd = a.areaYd;
        }

        bool NeedsLos(Ability const& a)
        {
            return a.trigger != Trigger::Melee && a.trigger != Trigger::Proximity;
        }

        // A donor cast with its damage effects given our number (or none) and the kinds of triggered flag that keep the
        // cast bar: an instant one is cast directly, a wind-up keeps the donor's own cast time.
        CastSpellExtraArgs DonorArgs(SpellInfo const* info, bool ourNumber, double damage, bool instant)
        {
            std::uint32_t flags = TRIGGERED_IGNORE_GCD | TRIGGERED_IGNORE_SPELL_AND_CATEGORY_CD |
                                  TRIGGERED_IGNORE_POWER_AND_REAGENT_COST | TRIGGERED_IGNORE_CASTER_AURASTATE;
            if (instant)
                flags |= TRIGGERED_FULL_MASK; // includes CAST_DIRECTLY: no cast time
            CastSpellExtraArgs args{static_cast<TriggerCastFlags>(flags)};
            // A damage effect takes our number or none; any other effect stays the stock spell's own (3.1).
            for (std::uint8_t i = 0; i < 3; ++i)
                if (Carry const carry = CarryOf(IsDamageEffect(info->Effects[i]), ourNumber); carry != Carry::Keep)
                    args.AddSpellMod(static_cast<SpellValueMod>(SPELLVALUE_BASE_POINT0 + i),
                                     carry == Carry::OurNumber ? static_cast<int32>(std::min(damage, 2000000000.0)) : 0);
            return args;
        }

        class SwingScript final : public UnitScript
        {
        public:
            SwingScript()
                : UnitScript("dc_family_swing", true, {UNITHOOK_MODIFY_MELEE_DAMAGE})
            {
            }
            // melee_swing: the plain swing is the monster's own swing times the kind's multiplier (1.0 until a value is
            // set), and nothing else. The hook runs inside CalculateMeleeDamage, before the hit is rolled, so the
            // "on melee hit" abilities do not ride it: they ride the AI's DamageDealt, which the core calls from
            // DealDamage only for a swing that landed (FamilyAI in dc_rift_ai.cpp).
            void ModifyMeleeDamage(Unit*, Unit* attacker, uint32& damage) override
            {
                if (!attacker || !attacker->IsCreature() || !IsFamilyEntry(attacker->GetEntry()))
                    return;
                double const factor = Multiplier(Kind::MeleeSwing);
                if (factor != 1.0)
                    damage = static_cast<uint32>(AbilityDamage(damage, factor));
            }
        };

        class FamilyWorld final : public WorldScript
        {
        public:
            FamilyWorld()
                : WorldScript("dc_family_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                if (!LoadRegistry())
                    LOG_WARN("server",
                             "[DC family] no built abilities: apply world monsters_0005_family_ai.sql; family "
                             "monsters swing and chase only");
            }
        };

        class FamilyCommands final : public CommandScript
        {
        public:
            FamilyCommands()
                : CommandScript("dc_family_commands")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable family = {{"reload", Reload, SEC_ADMINISTRATOR, Console::Yes},
                                                  {"status", Status, SEC_GAMEMASTER, Console::No},
                                                  {"pool", Pool, SEC_ADMINISTRATOR, Console::No}};
                static ChatCommandTable dc = {{"family", family}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

        private:
            static bool Reload(ChatHandler* handler)
            {
                bool const loaded = LoadRegistry();
                handler->SendSysMessage(loaded ? "Family abilities reloaded; a monster takes them, and today's tunable "
                                                 "numbers, when it next engages."
                                               : "No built family abilities found; check dc_family_ability_ai.");
                return loaded;
            }
            // A dev probe for the pool (no monster has one yet): the selected creature puts the kind's default pool at
            // the GM's feet, with its own swing as the damage. Run it on a corpse to see whether a dead caster may hurt.
            static bool Pool(ChatHandler* handler)
            {
                Creature* creature = handler->getSelectedCreature();
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                Layer const kind = DefaultLayer(Kind::GroundHazardDot);
                if (!creature || !player || !kind.areaYd || !kind.durationS || !kind.tickS)
                {
                    handler->SendSysMessage("Select a creature; the ground_hazard_dot defaults (area, duration, tick) must be set.");
                    return false;
                }
                DC::Rifts::GroundEffect effect;
                effect.x = player->GetPositionX();
                effect.y = player->GetPositionY();
                effect.z = player->GetPositionZ();
                effect.radius = static_cast<float>(*kind.areaYd);
                effect.shell = PLAIN_STRIKE;
                effect.damage = AbilityDamage(SwingDamage(creature), Multiplier(Kind::GroundHazardDot));
                effect.tickMs = Ms(kind.tickS);
                effect.durationMs = Ms(kind.durationS);
                SpawnGroundEffect(creature, effect);
                handler->PSendSysMessage("Pool: {:.1f} yd, {} ms ticks, {} ms, {:.0f} a tick.", effect.radius,
                                         effect.tickMs, effect.durationMs, effect.damage);
                return true;
            }
            static bool Status(ChatHandler* handler)
            {
                Creature* creature = handler->getSelectedCreature();
                if (!creature || !IsFamilyEntry(creature->GetEntry()))
                {
                    handler->SendSysMessage("Select a family monster first.");
                    return false;
                }
                if (Brain* brain = BrainOf(creature))
                    brain->Report(handler);
                else
                    handler->SendSysMessage("It has no family brain (it is not under the family AI).");
                return true;
            }
        };
    } // namespace

    std::uint32_t BaseEntry(std::uint32_t entry)
    {
        if (entry >= RARE_BASE)
            return entry - RARE_BASE;
        if (entry >= CHAMPION_BASE)
            return entry - CHAMPION_BASE;
        return entry;
    }

    bool IsFamilyEntry(std::uint32_t entry)
    {
        std::uint32_t const base = BaseEntry(entry);
        return base >= FAMILY_FIRST && base <= FAMILY_LAST;
    }

    Player* PickPlayer(Creature* source, Rule rule, float minYd, float maxYd, bool needLineOfSight)
    {
        if (!source || !source->IsInWorld())
            return nullptr;
        return PickAmong(source, PlayersIn(source, minYd, maxYd, needLineOfSight), rule);
    }

    // ---------------------------------------------------------------------------------------------------------------

    Brain::Brain(Creature* creature)
        : me(creature)
    {
    }

    void Brain::Compile()
    {
        std::vector<RawAbility> raws;
        {
            std::lock_guard<std::mutex> lock(registryMutex);
            auto found = registry.find(BaseEntry(me->GetEntry()));
            if (found != registry.end())
                raws = found->second;
        }
        _abilities.clear();
        _hasSwing = false;
        _standoff = 0;
        float shortestReach = 0;
        for (RawAbility const& raw : raws)
        {
            Kind const kind = ParseKind(raw.kind);
            if (kind == Kind::Held)
                continue;
            Ability a =
                Resolve(raw.seq, raw.name, kind, ParseTrigger(raw.trigger), DonorOf(raw.spell), raw.summonEntry,
                        raw.count, FirstOf(raw.cells, TunableLayer(raw.key), DefaultLayer(kind)), Multiplier(kind));
            if (kind == Kind::MeleeSwing)
                _hasSwing = true;
            else if (a.direct && a.maxYd > 0 && (shortestReach <= 0 || a.maxYd < shortestReach))
                shortestReach = a.maxYd;
            _abilities.push_back(std::move(a));
        }
        // A monster the tables do not know (not applied yet, or a row-less entry) is a plain melee chaser, not a statue.
        if (_abilities.empty())
            _hasSwing = true;
        // A monster with no swing keeps its distance: a fraction of its shortest direct reach, so it can still cast.
        if (!_hasSwing && shortestReach > 0 && DC::Tunables::Has("monsters", "family_caster_standoff_fraction"))
            _standoff =
                shortestReach * static_cast<float>(DC::Tunables::Get("monsters", "family_caster_standoff_fraction"));
        _compiled = true;
    }

    void Brain::Engage()
    {
        Compile();
        _state = State::Idle;
        _active = -1;
        _events.Reset();
        for (std::size_t i = 0; i < _abilities.size(); ++i)
            StartCooldown(_events, i, FirstReadyAt(0, _abilities[i].cooldownMs, Roll()));
        _events.ScheduleEvent(EVENT_SCAN, Milliseconds(SCAN_MS));
    }

    double Brain::Damage(Ability const& ability) const
    {
        return AbilityDamage(SwingDamage(me), ability.damageMultiplier);
    }

    Player* Brain::Active() const
    {
        Player* player = _target ? ObjectAccessor::FindPlayer(_target) : nullptr;
        return ValidPlayer(me, player) ? player : nullptr;
    }

    void Brain::Update(std::uint32_t diff)
    {
        if (!_compiled)
            Engage();
        Tick(_events, diff,
             [&](std::uint32_t id)
             {
                 if (id == EVENT_SCAN)
                 {
                     _events.ScheduleEvent(EVENT_SCAN, Milliseconds(SCAN_MS));
                     if (_state == State::Idle)
                         TryStart();
                 }
                 else if (id == EVENT_PHASE)
                     EndPhase();
             });
    }

    // The deadline of the wind-up, channel or flight has come.
    void Brain::EndPhase()
    {
        switch (_state)
        {
            case State::Winding:
                if (_castless)
                    Strike(); // no cast to wait for: the wind-up ran on the clock
                else
                    Finish(); // the cast never reported back; give up on it
                break;
            case State::Channeling:
                Finish();
                break;
            case State::Moving:
                if (_active >= 0)
                    Land(_abilities[static_cast<std::size_t>(_active)]);
                break;
            case State::Idle:
                break;
        }
    }

    void Brain::TryStart()
    {
        if (_abilities.empty() || !me->GetVictim())
            return;
        Player* pick = nullptr;
        int const index = Choose(_abilities, _events,
                                 [&](Ability const& a)
                                 {
                                     float minYd = 0, maxYd = 0;
                                     WindowOf(a, minYd, maxYd);
                                     std::vector<Player*> players = PlayersIn(me, minYd, maxYd, NeedsLos(a));
                                     if (a.trigger == Trigger::Melee) // "in melee range" is the core's reach, whatever the window says
                                         players.erase(std::remove_if(players.begin(), players.end(),
                                                                      [&](Player* p) { return !me->IsWithinMeleeRange(p); }),
                                                       players.end());
                                     pick = PickAmong(me, players, RuleOf(a.trigger));
                                     return pick != nullptr;
                                 });
        if (index >= 0 && pick)
            Begin(index, pick);
    }

    void Brain::Begin(int index, Player* target)
    {
        Ability const& a = _abilities[static_cast<std::size_t>(index)];
        StartCooldown(_events, static_cast<std::size_t>(index), a.cooldownMs);
        _active = index;
        _target = target->GetGUID();
        _aimX = target->GetPositionX();
        _aimY = target->GetPositionY();
        _aimZ = target->GetPositionZ();
        _state = State::Winding;
        _castless = true;
        _events.RescheduleEvent(EVENT_PHASE, Milliseconds(a.windupMs));
        me->SetFacingToObject(target);
        if (a.spell && a.kind != Kind::ChargeRush && a.kind != Kind::LeapSlam)
        {
            // Every direct kind but the volley puts its damage in the donor cast; the rest cast it for the bar and the
            // look and strike when it lands. A donor that cannot start (out of its reach, no line) leaves the wind-up on
            // the clock and the strike still comes. A charge and a leap are our own movement: their donor is only the
            // school of the hit.
            bool const ours = WindupCarriesOurNumber(a);
            bool started;
            if (a.kind == Kind::GroundDetonation)
                started = CastDonorAt(a, _aimX, _aimY, _aimZ, false, false);
            else
                started = CastDonor(a, CastTargetOf(a, target), ours, false);
            if (started && _state == State::Winding)
            {
                _castless = false;
                _events.RescheduleEvent(EVENT_PHASE, Milliseconds(a.windupMs + CAST_SLACK_MS));
            }
        }
        if (_state == State::Winding && _castless && a.windupMs == 0)
            Strike();
    }

    // Who the donor is cast at: a breath, a slam and a bomb are drawn around the monster, a roar on it, and a donor with
    // no reach of its own (a self-centred spell) can only be cast on it; the rest are cast at the player.
    Unit* Brain::CastTargetOf(Ability const& ability, Player* target) const
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(ability.spell);
        bool const self = ability.kind == Kind::BuffRoar || ability.kind == Kind::ConeBreath ||
                          ability.kind == Kind::MeleeHeavySlam || ability.kind == Kind::SuicideBomb ||
                          (info && info->GetMaxRange(false) <= 0.0f);
        return self ? static_cast<Unit*>(me) : target;
    }

    bool Brain::CastDonorAt(Ability const& ability, float x, float y, float z, bool ourNumber, bool instant)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(ability.spell);
        if (!info)
            return false;
        _firing = instant;
        SpellCastResult const result =
            me->CastSpell(Position(x, y, z), ability.spell, DonorArgs(info, ourNumber, Damage(ability), instant));
        _firing = false;
        return result == SPELL_CAST_OK;
    }

    bool Brain::CastDonor(Ability const& ability, Unit* target, bool ourNumber, bool instant)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(ability.spell);
        if (!info || !target)
            return false;
        _firing = instant;
        SpellCastResult const result =
            me->CastSpell(target, ability.spell, DonorArgs(info, ourNumber, Damage(ability), instant));
        _firing = false;
        return result == SPELL_CAST_OK;
    }

    void Brain::Finish()
    {
        _events.CancelEvent(EVENT_PHASE);
        _state = State::Idle;
        _active = -1;
        _castless = true;
    }

    void Brain::Strike()
    {
        if (_active < 0)
        {
            Finish();
            return;
        }
        int const index = _active;
        Ability const& a = _abilities[static_cast<std::size_t>(index)];
        Player* target = Active();
        bool const castless = _castless;
        Finish();
        switch (a.kind)
        {
            case Kind::RangedBolt:
            case Kind::CrowdControlTrap:
                if (castless && target)
                    HitOne(a, target); // the donor never ran: the strike is the hit
                break;
            case Kind::ChanneledBeam:
            {
                SpellInfo const* info = castless ? nullptr : sSpellMgr->GetSpellInfo(a.spell);
                if (info && info->IsChanneled())
                {
                    _state = State::Channeling;
                    _active = index;
                    _events.RescheduleEvent(EVENT_PHASE,
                                            Milliseconds(std::max<std::int32_t>(info->GetDuration(), 0) + CAST_SLACK_MS));
                }
                else if (castless && target)
                    HitOne(a, target);
                break;
            }
            case Kind::ProjectileVolley:
                FireVolley(a);
                break;
            case Kind::MeleeHeavySlam:
            case Kind::ConeBreath:
                HitCone(a, a.areaYd > 0 ? a.areaYd : a.maxYd);
                break;
            case Kind::GroundDetonation:
                HitPlayers(a, _aimX, _aimY, _aimZ, a.areaYd);
                break;
            case Kind::SuicideBomb:
                HitPlayers(a, me->GetPositionX(), me->GetPositionY(), me->GetPositionZ(), a.areaYd);
                me->KillSelf();
                break;
            case Kind::GroundHazardDot:
                PutGroundEffect(a, _aimX, _aimY, _aimZ);
                break;
            case Kind::SummonMinions:
                Summon(a);
                break;
            case Kind::ChargeRush:
            case Kind::LeapSlam:
            {
                bool const leap = a.kind == Kind::LeapSlam;
                if (!target || (leap && (a.speedXy <= 0 || a.speedZ <= 0)))
                {
                    Land(a);
                    break;
                }
                float const touching = me->GetCombatReach() + target->GetCombatReach();
                Spot const end = ChargeEnd(me->GetPositionX(), me->GetPositionY(), target->GetPositionX(),
                                           target->GetPositionY(), touching);
                _state = State::Moving;
                _active = index;
                _events.RescheduleEvent(EVENT_PHASE, Milliseconds(IN_FLIGHT_MS));
                if (leap)
                    me->GetMotionMaster()->MoveJump(end.x, end.y, target->GetPositionZ(), a.speedXy, a.speedZ, LEAP_ID);
                else
                    me->GetMotionMaster()->MoveCharge(end.x, end.y, target->GetPositionZ(),
                                                      a.speedXy > 0 ? a.speedXy : SPEED_CHARGE, CHARGE_ID, nullptr, true);
                break;
            }
            case Kind::BuffRoar: // the donor cast was the whole ability
            case Kind::MeleeSwing:
            case Kind::Held:
                break;
        }
    }

    void Brain::Land(Ability const& ability)
    {
        Finish();
        HitPlayers(ability, me->GetPositionX(), me->GetPositionY(), me->GetPositionZ(), ability.areaYd);
        ResumeChase();
    }

    void Brain::ResumeChase()
    {
        if (Unit* victim = me->GetVictim())
        {
            if (_standoff > 0)
                me->GetMotionMaster()->MoveChase(victim, _standoff);
            else
                me->GetMotionMaster()->MoveChase(victim);
        }
    }

    void Brain::HitOne(Ability const& ability, Player* player)
    {
        DC::Combat::DealMonsterHit(me, player, ability.spell ? ability.spell : PLAIN_STRIKE, Damage(ability));
    }

    void Brain::HitPlayers(Ability const& ability, float x, float y, float z, float radius)
    {
        BlastPlayers(me, me->GetMap(), x, y, z, radius, ability.spell ? ability.spell : PLAIN_STRIKE, Damage(ability));
    }

    void Brain::HitCone(Ability const& ability, float length)
    {
        Map* map = me->GetMap();
        if (!map)
            return;
        map->DoForAllPlayers(
            [&](Player* player)
            {
                if (ValidPlayer(me, player) &&
                    InCone(me->GetPositionX(), me->GetPositionY(), me->GetOrientation(), player->GetPositionX(),
                           player->GetPositionY(), length, ability.arcRad))
                    HitOne(ability, player);
            });
    }

    // A pool the hazard subsystem keeps: its damage is ours, its look is the donor's own area spell cast without damage.
    void Brain::PutGroundEffect(Ability const& ability, float x, float y, float z)
    {
        if (ability.durationMs == 0 || ability.areaYd <= 0)
            return;
        DC::Rifts::GroundEffect effect;
        effect.x = x;
        effect.y = y;
        effect.z = z;
        effect.radius = ability.areaYd;
        effect.shell = ability.spell ? ability.spell : PLAIN_STRIKE;
        effect.damage = Damage(ability);
        effect.tickMs = ability.tickMs;
        effect.durationMs = ability.durationMs;
        SpawnGroundEffect(me, effect);
        if (ability.spell)
            CastDonorAt(ability, x, y, z, false, true);
    }

    void Brain::FireVolley(Ability const& ability)
    {
        float minYd = 0, maxYd = 0;
        WindowOf(ability, minYd, maxYd);
        std::vector<Player*> const players = PlayersIn(me, minYd, maxYd, true);
        for (std::uint32_t n = 0; n < ability.count; ++n)
        {
            Player* player = PickAmong(me, players, Rule::Random);
            if (!player)
                break;
            if (!(ability.spell && CastDonor(ability, player, true, true)))
                HitOne(ability, player);
        }
    }

    void Brain::Summon(Ability const& ability)
    {
        Unit* victim = me->GetVictim();
        for (std::uint32_t i = 0; i < ability.count; ++i)
        {
            Spot const spot = RingSpot(me->GetPositionX(), me->GetPositionY(), i, ability.count, ability.areaYd,
                                       me->GetOrientation());
            float z = me->GetPositionZ();
            me->UpdateGroundPositionZ(spot.x, spot.y, z);
            TempSummon* minion = me->SummonCreature(ability.summonEntry, spot.x, spot.y, z, me->GetOrientation(),
                                                    TEMPSUMMON_DEAD_DESPAWN, 0);
            if (!minion)
                continue;
            minion->CustomData.GetDefault<IllusionState>("DCRiftIllusion"); // gives no rift progress (3.13)
            if (victim && minion->AI())
                minion->AI()->AttackStart(victim);
        }
    }

    void Brain::OnSpellCast(SpellInfo const* spell)
    {
        if (!_firing && _state == State::Winding && _active >= 0 && spell &&
            spell->Id == _abilities[static_cast<std::size_t>(_active)].spell)
            Strike();
    }

    void Brain::OnSpellFailed(SpellInfo const* spell)
    {
        if (!_firing && _state == State::Winding && _active >= 0 && spell &&
            spell->Id == _abilities[static_cast<std::size_t>(_active)].spell)
            Finish(); // interrupted: no strike, and the cooldown already runs
    }

    void Brain::OnChannelFinished(SpellInfo const* spell)
    {
        if (_state == State::Channeling && _active >= 0 && spell &&
            spell->Id == _abilities[static_cast<std::size_t>(_active)].spell)
            Finish();
    }

    void Brain::OnMovement(std::uint32_t type, std::uint32_t id)
    {
        if (_state == State::Moving && _active >= 0 &&
            ((type == POINT_MOTION_TYPE && id == CHARGE_ID) || (type == EFFECT_MOTION_TYPE && id == LEAP_ID)))
            Land(_abilities[static_cast<std::size_t>(_active)]);
    }

    // "On melee hit" abilities ride a swing that landed: the stock donor on the victim (its own effects), plus a hit of
    // ours for a heavy slam. The AI's DamageDealt calls this from DealDamage, after the outcome is rolled, so a dodged,
    // parried or immune swing (no damage, no DealDamage) and a fully absorbed one (damage 0) fire nothing. The
    // melee_swing multiplier is applied earlier, in SwingScript. `_riding` keeps a rider's own hit from firing the next.
    void Brain::OnDamageDealt(Unit* victim, std::uint32_t damage, bool swing)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (!swing || !damage || _riding || !ValidPlayer(me, player))
            return;
        _riding = true;
        for (std::size_t i = 0; i < _abilities.size(); ++i)
        {
            Ability const& a = _abilities[i];
            if (a.trigger != Trigger::Hit || !IsReady(_events, i))
                continue;
            StartCooldown(_events, i, a.cooldownMs);
            if (a.spell)
                CastDonor(a, player, false, true);
            if (a.kind == Kind::MeleeHeavySlam)
                HitOne(a, player);
        }
        _riding = false;
    }

    void Brain::OnDeath()
    {
        if (!_compiled)
            Compile();
        Finish();
        for (Ability const& a : _abilities)
        {
            if (a.trigger != Trigger::Death)
                continue;
            if (a.kind == Kind::SuicideBomb)
                HitPlayers(a, me->GetPositionX(), me->GetPositionY(), me->GetPositionZ(), a.areaYd);
            else if (a.kind == Kind::SummonMinions)
                Summon(a);
            else if (a.kind == Kind::GroundHazardDot)
                PutGroundEffect(a, me->GetPositionX(), me->GetPositionY(), me->GetPositionZ());
        }
    }

    void Brain::Report(ChatHandler* handler) const
    {
        static char const* const states[] = {"idle", "winding", "channeling", "moving"};
        handler->PSendSysMessage("Family brain: state={} swing={} standoff={:.1f} abilities={}",
                                 states[static_cast<std::size_t>(_state)], _hasSwing ? "yes" : "no", _standoff,
                                 _abilities.size());
        for (std::size_t i = 0; i < _abilities.size(); ++i)
        {
            Ability const& a = _abilities[i];
            handler->PSendSysMessage("  {}. {} [{}/{}] spell={} cd={}ms windup={}ms window={:.1f}-{:.1f}yd area={:.1f} "
                                     "ready_in={}ms",
                                     a.seq, a.name, KindName(a.kind), static_cast<unsigned>(a.trigger), a.spell,
                                     a.cooldownMs, a.windupMs, a.minYd, a.maxYd, a.areaYd,
                                     _events.HasTimeUntilEvent(CooldownEvent(i))
                                         ? static_cast<std::uint32_t>(_events.GetTimeUntilEvent(CooldownEvent(i)).count())
                                         : 0u);
        }
    }

    void RegisterFamilyAiScripts()
    {
        new FamilyWorld();
        new SwingScript();
        new FamilyCommands();
    }
} // namespace DC::Rifts::Family
