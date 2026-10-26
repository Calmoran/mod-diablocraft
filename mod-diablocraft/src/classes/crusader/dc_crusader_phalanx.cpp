/*
 * Phalanx and its five runes: the avatars of the order the Crusader summons, and what each rune has them do. The line
 * the charge hits is the cast path's (skill_targeting.csv: 60 yards, 20 wide); what is here is the avatars themselves,
 * the stuns of Stampede, the bash of Shield Charge, the shots of the Bowmen, the place the Shield Bearers hold, the
 * blows of the Bodyguard, and the cost and cooldown the three gated runes owe. The creatures are crusader_summons.csv.
 * The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_phalanx.h"
#include "dc_crusader_common.h"
#include "../../combat/dc_item_powers.h"
#include "Creature.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "PetDefines.h"
#include "Random.h"
#include "ScriptedCreature.h"
#include "ScriptMgr.h"
#include "TemporarySummon.h"

#include <cmath>
#include <memory>

namespace DC::Combat::Crusader::Phalanx
{
    namespace
    {
        constexpr std::string_view Skill = "Phalanx";
        // crusader_summons.csv: the Avatar of the Order and the Warhorse of the Order Stampede runs the charge on.
        constexpr std::uint32_t AvatarEntry = 900140, HorseEntry = 900141;
        // The least the Shield Bearers' look at their enemies can be. The tunable has no number yet, and 0 must not
        // make the look run on every update; this is a guard against 0, not a tuning number.
        constexpr double CheckFloorSeconds = 0.1;
        // How far apart avatars stand side by side, and how long past the run a charging avatar is kept if it never
        // arrives: guards on how it looks and on a stuck one, not game numbers.
        constexpr double AbreastYards = 2.0;
        // How far past the edge the Shield Bearers' place keeps its eye on an enemy: far more than one look lets any enemy
        // move, so none can arrive on the other side unseen. A guard on the search, not a tuning number.
        constexpr double WatchMarginYards = 10.0;
        constexpr std::uint32_t StuckGraceMs = 3000;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        std::uint32_t IdOf(std::string_view rune)
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && rune == row.rune)
                    return row.id;
            return 0;
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(std::llround(std::max(0.0, seconds) * 1000.0));
        }

        // One shield bash for the whole charge: the first avatar to arrive deals it.
        struct Arrival
        {
            bool bashed = false;
        };

        // --- the avatar ------------------------------------------------------------------------------------------

        class AvatarAI final : public ScriptedAI
        {
        public:
            explicit AvatarAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            // Belongs to `player` and fights on its side; no enemy can hurt it, and it takes no part in a fight of its
            // own.
            void Configure(Player* player, std::uint32_t spellId, Behavior how)
            {
                owner = player->GetGUID();
                record = spellId;
                behavior = how;
                me->SetOwnerGUID(owner);
                me->SetCreatorGUID(owner);
                me->SetFaction(player->GetFaction());
                me->SetLevel(player->GetLevel());
                me->SetReactState(REACT_PASSIVE);
                me->SetImmuneToAll(true);
            }

            // Charge: runs to `end` at `rate` times its own speed, and bashes there for Shield Charge.
            void Run(Position const& end, float rate, std::shared_ptr<Arrival> arrival)
            {
                stop = end;
                shared = std::move(arrival);
                me->SetSpeedRate(MOVE_RUN, rate);
                me->GetMotionMaster()->MovePoint(1, end);
            }

            void Follow(unsigned index)
            {
                place = index;
                if (Player* player = ObjectAccessor::GetPlayer(*me, owner))
                    me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE + float(index));
            }

            void MovementInform(uint32 type, uint32 id) override
            {
                if (behavior != Behavior::Charge || type != POINT_MOTION_TYPE || id != 1)
                    return;
                Player* player = ObjectAccessor::GetPlayer(*me, owner);
                if (player && shared && !shared->bashed && RuneAt(record) == Rune::ShieldCharge)
                {
                    shared->bashed = true;
                    // "perform a shield bash, dealing an additional {damage_pct} weapon damage to enemies at that
                    // location."
                    Combat::StrikeArea(player, record, stop, Tune("phalanx_shield_charge_bash_radius_yards"),
                                       Numbers::Own(record, "damage_pct"));
                }
                me->DespawnOrUnsummon(Milliseconds(500));
            }

            void UpdateAI(uint32 diff) override
            {
                Player* player = ObjectAccessor::GetPlayer(*me, owner);
                if (!player || !player->IsAlive() || !player->IsInMap(me) || !player->InSamePhase(me))
                {
                    me->DespawnOrUnsummon();
                    return;
                }
                if (behavior == Behavior::Follow || behavior == Behavior::Fight)
                    Attend(player, diff);
            }

        private:
            ObjectGuid owner;
            std::uint32_t record = 0;
            Behavior behavior = Behavior::Charge;
            unsigned place = 0;
            double clock = 0;
            Position stop;
            std::shared_ptr<Arrival> shared;

            // The Crusader's target as the Ancients pick it: what it attacks, else its selection while it fights.
            Unit* Aim(Player* player) const
            {
                Unit* victim = player->GetVictim();
                Unit* selected = player->GetSelectedUnit();
                auto usable = [player](Unit* unit)
                { return unit && unit->IsAlive() && player->IsValidAttackTarget(unit); };
                return usable(victim) ? victim : player->IsInCombat() && usable(selected) ? selected : nullptr;
            }

            // Bowmen: "wield bows and attack enemies, dealing {damage_pct} weapon damage", a shot each fire rate.
            // Bodyguard: "Each Avatar will attack for {damage_pct} of your weapon damage", a blow at the Crusader's
            // attacks per second, in melee range.
            void Attend(Player* player, uint32 diff)
            {
                Unit* target = Aim(player);
                if (!target)
                {
                    if (me->GetVictim())
                        me->AttackStop();
                    if (me->GetMotionMaster()->GetCurrentMovementGeneratorType() != FOLLOW_MOTION_TYPE)
                        Follow(place);
                    return;
                }
                clock += diff;
                if (behavior == Behavior::Follow)
                {
                    if (!ShotDue(clock, Tune("phalanx_bowmen_fire_seconds")))
                        return;
                    clock = 0;
                    me->SetFacingToObject(target);
                    Combat::Strike(player, target, record, Numbers::Own(record, "damage_pct"));
                    return;
                }
                if (me->GetVictim() != target)
                    AttackStart(target);
                double const aps = Combat::AttacksPerSecond(player) * Combat::ItemPowers::PetSpeedFactor(player);
                if (aps <= 0 || clock < 1000 / aps || !me->IsWithinMeleeRange(target))
                    return;
                clock = 0;
                Combat::Strike(player, target, record, Numbers::Own(record, "damage_pct"));
            }
        };

        class Script final : public CreatureScript
        {
        public:
            Script()
                : CreatureScript("dc_crusader_avatar")
            {
            }
            CreatureAI* GetAI(Creature* creature) const override
            {
                return new AvatarAI(creature);
            }
        };

        AvatarAI* Mind(Creature* creature)
        {
            return creature ? dynamic_cast<AvatarAI*>(creature->AI()) : nullptr;
        }

        // An avatar of `entry` for `player` at `at`, for `ms`; nullptr when the creature or its AI is not ours.
        AvatarAI* Call(Player* player, std::uint32_t entry, std::uint32_t spellId, Behavior how, Position const& at,
                       std::uint32_t ms)
        {
            TempSummon* summon = player->SummonCreature(entry, at, TEMPSUMMON_TIMED_DESPAWN, ms);
            if (!summon)
                return nullptr;
            AvatarAI* mind = Mind(summon);
            if (!mind || !summon->IsInWorld())
            {
                summon->DespawnOrUnsummon();
                return nullptr;
            }
            mind->Configure(player, spellId, how);
            return mind;
        }

        // --- the place the Shield Bearers hold -------------------------------------------------------------------

        // Where an enemy was last seen to be allowed: the side of the place it stood on and the spot.
        struct Side
        {
            bool inside = false;
            Position good;
        };

        std::chrono::milliseconds CheckEvery()
        {
            return std::chrono::milliseconds(
                std::uint64_t(std::max(CheckFloorSeconds, Tune("phalanx_shield_bearers_check_seconds")) * 1000));
        }

        // "blocking all enemies from moving through": an enemy now on the other side of the edge from where it was seen
        // is put back where it was seen.
        void Hold(Player* player, std::uint32_t spellId, Position center, double radius, std::uint64_t until,
                  std::shared_ptr<std::unordered_map<std::uint64_t, Side>> sides)
        {
            if (!player->IsInWorld() || Now() >= until)
                return;
            for (Unit* enemy : Combat::Enemies(player, spellId, center, radius + WatchMarginYards))
            {
                double const distance = center.GetExactDist2d(enemy);
                auto seen = sides->find(enemy->GetGUID().GetRawValue());
                if (seen == sides->end())
                    (*sides)[enemy->GetGUID().GetRawValue()] = {Consecration::OnGround(distance, radius),
                                                                enemy->GetPosition()};
                else if (Consecration::Crossed(seen->second.inside, distance, radius))
                    enemy->NearTeleportTo(seen->second.good.GetPositionX(), seen->second.good.GetPositionY(),
                                          seen->second.good.GetPositionZ(), enemy->GetOrientation());
                else
                    seen->second.good = enemy->GetPosition();
            }
            player->m_Events.AddEventAtOffset([player, spellId, center, radius, until, sides]
                                              { Hold(player, spellId, center, radius, until, sides); }, CheckEvery());
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return HitsTheLine(RuneAt(spellId)) ? Numbers::Own(BaseId(Skill), "damage_pct").value_or(0.0) : 0.0;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        // "a {proc_chance_pct} chance to Stun enemies for {stun_duration_seconds} seconds."
        if (rune == Rune::Stampede)
            for (Unit* enemy : targets)
                if (enemy->IsAlive() && Stuns(rune, rand_chance(), Numbers::Num(spellId, "proc_chance_pct")))
                    Stun(player, enemy,
                         Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
        // "can only be summoned once every {internal_cooldown_seconds} seconds": the gated runes cost nothing (their
        // records carry no cost); the cooldown is theirs to start.
        if (double const cooldown = CooldownSeconds(rune, Numbers::Num(spellId, "internal_cooldown_seconds")))
            SendSkillCooldown(player, spellId, std::uint32_t(Millis(cooldown)));
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        Behavior const how = BehaviorOf(rune);
        // "you summon {pet_count} Avatars of the Order": the sheet's one count of avatars, the charge's too.
        unsigned const count = unsigned(Numbers::Num(IdOf("Bodyguard"), "pet_count"));
        Position const origin = player->GetPosition();
        double const reach = Tune("phalanx_charge_distance_yards");
        double const share = RunShare(origin.GetExactDist2d(center), reach);
        float const facing = origin.GetAbsoluteAngle(&center);
        auto const across = [facing](Position const& at, double offset)
        {
            Position out = at;
            out.Relocate(at.GetPositionX() + float(std::cos(facing + M_PI / 2) * offset),
                         at.GetPositionY() + float(std::sin(facing + M_PI / 2) * offset), at.GetPositionZ());
            return out;
        };
        Position end = origin;
        end.Relocate(origin.GetPositionX() + (center.GetPositionX() - origin.GetPositionX()) * float(share),
                     origin.GetPositionY() + (center.GetPositionY() - origin.GetPositionY()) * float(share),
                     center.GetPositionZ());
        auto arrival = std::make_shared<Arrival>();
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        for (unsigned i = 0; i < count; ++i)
        {
            double const side = Abreast(i, count, AbreastYards);
            AvatarAI* mind = nullptr;
            switch (how)
            {
                case Behavior::Charge:
                {
                    // The plain charge runs at the sheet's yards a second; Shield Charge and Stampede run faster in the
                    // power file's ratio.
                    double const yps = Tune("phalanx_charge_speed_yards_per_second");
                    double const ratio =
                        SpeedRatio(rune, Tune("phalanx_charge_speed_base"), Tune("phalanx_shield_charge_speed_bonus"),
                                   Tune("phalanx_stampede_speed_bonus"));
                    float const rate = float(RunRate(yps, baseMoveSpeed[MOVE_RUN], ratio));
                    double const run = origin.GetExactDist2d(end) / std::max(1.0, double(baseMoveSpeed[MOVE_RUN]) * rate);
                    mind = Call(player, rune == Rune::Stampede ? HorseEntry : AvatarEntry, spellId, how,
                                across(origin, side), std::uint32_t(Millis(run)) + StuckGraceMs);
                    if (mind)
                        mind->Run(across(end, side), rate, arrival);
                    break;
                }
                case Behavior::Follow:
                case Behavior::Fight:
                    mind =
                        Call(player, AvatarEntry, spellId, how, across(origin, side), std::uint32_t(Millis(seconds)));
                    if (mind)
                        mind->Follow(i);
                    break;
                case Behavior::Stand:
                    Call(player, AvatarEntry, spellId, how, across(end, side),
                         std::uint32_t(Millis(Tune("phalanx_shield_bearers_seconds"))));
                    break;
            }
        }
        // "blocking all enemies from moving through": the place the avatars hold, for as long as they stand.
        if (rune == Rune::ShieldBearers)
        {
            double const hold = Tune("phalanx_shield_bearers_seconds");
            Hold(player, spellId, end, Tune("phalanx_shield_bearers_radius_yards"), Now() + Millis(hold),
                 std::make_shared<std::unordered_map<std::uint64_t, Side>>());
        }
    }

    void Fighters(Player* player, std::uint32_t spellId, unsigned count, double seconds, Position const& origin)
    {
        if (!player)
            return;
        float const facing = player->GetOrientation();
        for (unsigned i = 0; i < count; ++i)
        {
            double const side = Abreast(i, count, AbreastYards);
            Position at = origin;
            at.Relocate(origin.GetPositionX() + float(std::cos(facing + M_PI / 2) * side),
                        origin.GetPositionY() + float(std::sin(facing + M_PI / 2) * side), origin.GetPositionZ());
            if (AvatarAI* mind = Call(player, AvatarEntry, spellId, Behavior::Fight, at, std::uint32_t(Millis(seconds))))
                mind->Follow(i);
        }
    }

    void RegisterScripts()
    {
        new Script();
    }
} // namespace DC::Combat::Crusader::Phalanx
