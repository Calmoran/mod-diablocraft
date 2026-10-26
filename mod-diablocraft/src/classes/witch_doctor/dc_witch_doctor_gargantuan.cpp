/*
 * The Gargantuan and its runes. The cast raises the Gargantuan on the pets' piece (dc_witch_doctor_pets.cpp: its Life,
 * its blow and its cleave) at the ground it was aimed at, and the rune on the bar shapes it: Restless Giant      it
 * enrages near an elite or a crowd, for a time, once in a while: more damage, attack speed and run speed; Humongoid its
 * blow is the rune's, Cold (BlowOf); Big Stinker         a cloud of Poison round it, a pulse every second; Wrathful
 * Protector  a stronger Gargantuan for a time: its blow is the rune's Fire and a smash that lifts the enemies round the
 * one it hit; Bruiser             it slams the enemies round it, Fire and a stun.
 */

#include "dc_witch_doctor_gargantuan.h"
#include "dc_witch_doctor_bar.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_gargantuan_math.h"
#include "dc_witch_doctor_pets.h"
#include "dc_witch_doctor_pets_math.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "Creature.h"
#include "Player.h"
#include "Position.h"
#include "Unit.h"

#include <algorithm>
#include <mutex>
#include <string_view>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::GargantuanRunes
{
    namespace
    {
        constexpr std::string_view Skill = "Gargantuan", Group = "gargantuan";

        enum class Rune
        {
            None,
            RestlessGiant,
            Humongoid,
            BigStinker,
            WrathfulProtector,
            Bruiser
        };

        Rune RuneOf(std::string_view name)
        {
            if (name == "Restless Giant")
                return Rune::RestlessGiant;
            if (name == "Humongoid")
                return Rune::Humongoid;
            if (name == "Big Stinker")
                return Rune::BigStinker;
            if (name == "Wrathful Protector")
                return Rune::WrathfulProtector;
            if (name == "Bruiser")
                return Rune::Bruiser;
            return Rune::None;
        }

        double Num(std::uint32_t record, char const* token)
        {
            return Numbers::Num(record, token);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::uint64_t> enraged; // by Witch Doctor: when the last enrage began

        // "Elite enemies include champions, rares, bosses, and other players."
        bool Elite(Unit* unit)
        {
            return unit->IsPlayer() || !Combat::IsLesser(unit);
        }

        // Restless Giant: looked at every 'Periodic Check Tickrate' (the minions piece's watch).
        void Enrage(Player* owner, std::uint32_t id)
        {
            auto const standing = Minions::Standing(owner, Group);
            if (standing.empty())
                return;
            std::uint64_t const now = Now(), cooldown = Pets::Millis(Num(id, "internal_cooldown_seconds"));
            std::uint64_t const guid = owner->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const last = enraged.find(guid);
                if (!OffCooldown(last == enraged.end() ? std::nullopt : std::optional<std::uint64_t>(last->second), now,
                                 cooldown))
                    return;
            }
            auto const enemies =
                Combat::Enemies(owner, id, standing.front()->GetPosition(), Tune("restless_giant_check_yards"));
            if (!Enraged(unsigned(enemies.size()), unsigned(Num(id, "nearby_enemy_count")),
                         std::any_of(enemies.begin(), enemies.end(), Elite)))
                return;
            {
                std::lock_guard<std::mutex> guard(mutex);
                enraged[guid] = now;
            }
            std::uint32_t const ms = Pets::Millis(Num(id, "duration_seconds"));
            Minions::Boost(owner, Group, Num(id, "damage_bonus_pct"), ms);
            Minions::Haste(owner, Group, Num(id, "attack_speed_pct"), Num(id, "movement_speed_pct"), ms);
        }

        // Wrathful Protector: "knocking enemies into the air".
        void LiftUp(Unit* enemy, double heightYards)
        {
            Lift const lift = LiftSpeeds(heightYards);
            if (lift.z > 0 && enemy->IsAlive() && !enemy->HasUnitState(UNIT_STATE_ROOT))
                enemy->KnockbackFrom(enemy->GetPositionX(), enemy->GetPositionY(), float(lift.xy), float(lift.z));
        }

        // Wrathful Protector's blow: the enemy it hit and every enemy within the smash's radius of it are struck and
        // lifted.
        void Smash(Player* owner, Unit* struck, std::uint32_t id, double blowPct)
        {
            double const height = Tune("wrathful_protector_lift_yards");
            for (Unit* other :
                 Combat::Enemies(owner, id, struck->GetPosition(), Tune("wrathful_protector_smash_radius_yards")))
                if (other != struck)
                {
                    Combat::Strike(owner, other, id, blowPct);
                    LiftUp(other, height);
                }
            LiftUp(struck, height);
        }

        // Bruiser: the enemies within the slam's reach are struck and stunned, while the Gargantuan fights.
        void Slam(Player* owner, Creature* giant, std::uint32_t id, double blowPct)
        {
            if (!giant->GetVictim())
                return;
            double const stun = Num(id, "stun_duration_seconds") * ItemPowers::StunFactor(owner);
            for (Unit* enemy : Combat::Enemies(owner, id, giant->GetPosition(), Tune("bruiser_slam_yards")))
            {
                Combat::Strike(owner, enemy, id, blowPct);
                Stun(owner, enemy, stun);
            }
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Pets::RaiseGargantuan(player, center);
    }

    Blow BlowOf(Player* owner)
    {
        Slotted const slot = OnBar(owner, Skill);
        Rune const rune = RuneOf(slot.rune);
        if (rune == Rune::Humongoid || rune == Rune::WrathfulProtector)
            return {slot.id, Num(slot.id, "damage_pct")};
        std::uint32_t const base = BaseId(Skill);
        return {base, Num(base, "damage_pct")};
    }

    void Shape(Player* owner, Minions::Kind& kind, double feastPct)
    {
        Slotted const slot = OnBar(owner, Skill);
        std::uint32_t const id = slot.id;
        switch (RuneOf(slot.rune))
        {
            case Rune::RestlessGiant:
                kind.watchEveryMs = Pets::Millis(Tune("restless_giant_check_seconds"));
                kind.watch = [id](Player* player, Creature*) { Enrage(player, id); };
                break;
            case Rune::BigStinker:
            {
                // "The Gargantuan is surrounded by a poison cloud that deals {damage_pct} weapon damage as Poison per
                // second to nearby enemies."
                double const tick = Tune("big_stinker_tick_seconds");
                kind.auraRadius = Tune("big_stinker_radius_yards");
                kind.auraRecord = id;
                kind.auraEveryMs = Pets::Millis(tick);
                kind.auraPct = PulsePct(Pets::BlowPct(Num(id, "damage_pct"), feastPct), tick);
                break;
            }
            case Rune::WrathfulProtector:
            {
                // "Summon a more powerful Gargantuan to fight for you for {duration_seconds} seconds."
                double const blow = kind.damagePct;
                kind.lifeMs = Pets::Millis(Num(id, "duration_seconds"));
                kind.swingMs = Quickened(kind.swingMs, Tune("wrathful_protector_attack_speed_factor"));
                kind.struck = [id, blow](Player* player, Unit* enemy) { Smash(player, enemy, id, blow); };
                break;
            }
            case Rune::Bruiser:
            {
                // "periodically slam enemies, dealing {damage_pct} of your weapon damage as Fire and stunning them".
                double const blow = Pets::BlowPct(Num(id, "damage_pct"), feastPct);
                kind.watchEveryMs = Pets::Millis(Tune("bruiser_slam_cooldown_seconds"));
                kind.watch = [id, blow](Player* player, Creature* giant) { Slam(player, giant, id, blow); };
                break;
            }
            default:
                break;
        }
    }
} // namespace DC::Combat::WitchDoctor::GargantuanRunes
