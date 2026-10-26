/*
 * Poison Dart and its five runes. The cast is the engine's single-enemy shot (a spell record and the sheet's numbers:
 * free to cast, the hit's damage, each rune's school); here: the poison every dart leaves, Flaming Dart's fire,
 * Splinters' other darts, Numbing Dart's slow, Snake to the Face's stun. Spined Dart's Mana is paid by the class's
 * Connected seam.
 */

#include "dc_witch_doctor_poison_dart.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Random.h"
#include "Unit.h"

#include <chrono>

namespace DC::Combat::WitchDoctor::PoisonDart
{
    namespace
    {
        constexpr std::string_view Skill = "Poison Dart";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
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
        // Splinters states its darts' damage as its own; every other rune hits for the skill's.
        return RuneAt(spellId) == Rune::Splinters ? Numbers::Num(spellId, "damage_pct")
                                                  : Numbers::Num(BaseId(Skill), "damage_pct", "hit");
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || targets.empty() || RuneAt(spellId) != Rune::Splinters)
            return;
        // "Shoot {projectile_count} Poison Darts that deal {damage_pct} weapon damage as Poison each": the cast is the
        // first, the others follow at the shot delay, at the same enemy while it lives.
        ObjectGuid const aim = targets.front()->GetGUID();
        for (unsigned index = 1, count = unsigned(Numbers::Num(spellId, "projectile_count")); index < count; ++index)
            player->m_Events.AddEventAtOffset(
                [player, spellId, aim]
                {
                    Unit* target = ObjectAccessor::GetUnit(*player, aim);
                    if (player->IsAlive() && target && target->IsAlive())
                        Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct"));
                },
                std::chrono::milliseconds(DartDelayMs(index, Tune("poison_dart_shot_delay_seconds"))));
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        if (rune == Rune::Splinters)
            return;
        // "and an additional {damage_pct:dot} weapon damage as Poison over {dot_duration_seconds} seconds": every dart
        // but Splinters' leaves it.
        PeriodicStrike::Start(player, target, spellId, Numbers::Num(spellId, "damage_pct", "dot"),
                              Numbers::Num(BaseId(Skill), "dot_duration_seconds"), Tune("poison_dart_tick_seconds"));
        switch (rune)
        {
            case Rune::FlamingDart:
                // "Ignite the dart, dealing {damage_pct} weapon damage as Fire over {dot_duration_seconds} seconds."
                PeriodicStrike::Start(player, target, spellId, Numbers::Num(spellId, "damage_pct"),
                                      Numbers::Num(spellId, "dot_duration_seconds"), Tune("poison_dart_tick_seconds"),
                                      1);
                break;
            case Rune::NumbingDart:
                Slow(player, target, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"));
                break;
            case Rune::SnakeToTheFace:
                if (Stuns(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct")))
                    Stun(player, target,
                         Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::WitchDoctor::PoisonDart
