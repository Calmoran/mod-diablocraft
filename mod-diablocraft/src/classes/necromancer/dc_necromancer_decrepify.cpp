/*
 * Decrepify and its five runes. The cast puts the curse on every enemy within the power's radius of the place aimed at: a slow and
 * less damage dealt for the skill's seconds (Wither slows nothing and weakens more), Enfeeblement's slow decaying from its start. The
 * Necromancer gains speed (Opportunist) or cooldown reduction (Borrowed Time) for the enemies it has cursed, kept up while any
 * remain; Dizzying Curse stuns a cursed enemy that is hit. The newest curse on an enemy replaces the old (dc_necromancer_curses.h).
 */

#include "dc_necromancer_decrepify.h"
#include "dc_necromancer_decrepify_math.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_curses.h"
#include "dc_necromancer_passives.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_passives.h"

#include "Random.h"

#include <chrono>
#include <utility>

namespace DC::Combat::Necromancer::Decrepify
{
    namespace
    {
        constexpr std::string_view Skill = "Decrepify";
        // The power's slow reduction is "per/second" (SF_12).
        constexpr double StepSeconds = 1.0;

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint32_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint32_t(seconds * 1000.0 + 0.5) : 0;
        }

        // Opportunist's movement speed or Borrowed Time's cooldown reduction for `cursed` enemies, on the sheet (0 takes it off).
        void Apply(Player* player, std::uint32_t spellId, unsigned cursed)
        {
            bool const speed = RuneAt(spellId) == Rune::Opportunist;
            double const per = speed ? Numbers::Num(spellId, "movement_speed_pct") : Numbers::Num(spellId, "cooldown_reduction_pct");
            double const value = StackBonus(cursed, per, Numbers::Num(spellId, "max_bonus_pct"));
            if (speed)
                Buffs::Set(player, spellId, Stat::MovementSpeed, Bucket::Flat, value);
            else
            {
                Buffs::Set(player, spellId, Stat::CooldownReduction, Bucket::Flat, value);
                Passives::RefreshModifiers(player);
            }
        }

        // Enfeeblement: the slow decays from its start to the normal over the rune's seconds, a step at a time while the curse stands.
        void Decay(Player* player, Unit* enemy, std::uint32_t spellId, double seconds)
        {
            double const start = Numbers::Num(spellId, "slow_pct"), base = Numbers::Num(BaseId(Skill), "slow_pct"),
                         perSecond = Tune("decrepify_slow_decay_pct_per_second");
            for (unsigned step = 1; step <= Steps(Numbers::Num(spellId, "duration_seconds"), StepSeconds); ++step)
                player->m_Events.AddEventAtOffset(
                    [player, guid = enemy->GetGUID(), spellId, start, base, perSecond, seconds, step]
                    {
                        Unit* target = ObjectAccessor::GetUnit(*player, guid);
                        if (!target || !target->IsAlive() || Curses::On(player, target, Skill) != spellId)
                            return;
                        Slow(player, target, DecayedSlow(start, base, perSecond, step * StepSeconds),
                             seconds - step * StepSeconds);
                    },
                    std::chrono::milliseconds(Millis(step * StepSeconds)));
        }

        // A curse of Decrepify taken off before its time: the slow and the weakness end.
        void Lift(Player* player, Unit* enemy, std::uint32_t spellId)
        {
            Unslow(player, enemy);
            EnemyEffects::Remove(enemy, spellId);
        }
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        Rune const rune = RuneAt(spellId);
        // "reduces ... for {duration_seconds} seconds": the skill's own, the rune's duration being its slow's decay.
        double const seconds = Passive::CurseSeconds(
            player, Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(Skill), "duration_seconds")));
        for (Unit* enemy : Combat::Enemies(player, spellId, center, Tune("decrepify_radius_yards")))
        {
            Curses::Put(player, enemy, spellId, seconds);
            // Wither "no longer reduces movement speed".
            if (rune != Rune::Wither)
                Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), seconds);
            EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), seconds);
            if (rune == Rune::Enfeeblement)
                Decay(player, enemy, spellId, seconds);
        }
        // The enemies cursed give the Necromancer a number for as long as they stand cursed; another rune takes it off.
        if (rune == Rune::Opportunist || rune == Rune::BorrowedTime)
            Curses::Follow(player, Skill, spellId, Apply);
        else
            Curses::Unfollow(player, Skill);
    }

    void Landed(Player* player, Unit* target, std::uint32_t)
    {
        std::uint32_t const curse = Curses::On(player, target, Skill);
        if (!curse || RuneAt(curse) != Rune::DizzyingCurse)
            return;
        // "Cursed enemies have a {proc_chance_pct} chance to be stunned for {stun_duration_seconds} seconds when hit", stretched by
        // the worn stun powers.
        if (Procs(rand_chance(), Numbers::Num(curse, "proc_chance_pct")))
            Stun(player, target, Numbers::Num(curse, "stun_duration_seconds") * ItemPowers::StunFactor(player));
    }

    void RegisterScripts()
    {
        Curses::Define(Skill, Lift);
    }
} // namespace DC::Combat::Necromancer::Decrepify
