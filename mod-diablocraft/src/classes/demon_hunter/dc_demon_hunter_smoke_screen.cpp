/*
 * Smoke Screen and its five runes. The cast is the engine's self-cast spell (a record and the sheet's numbers) with no
 * hit; here: the invisibility for its seconds, the movement speed gained while it lasts (Displacement's is larger),
 * Healing Vapors' Life and the cooldown that starts only when the invisibility is over. Vanishing Powder's missing cost
 * and longer cooldown, Lingering Fog's longer invisibility and Special Recipe's cheaper cast are sheet numbers the same
 * code reads.
 */

#include "dc_demon_hunter_smoke_screen.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_dot.h"
#include "dc_demon_hunter_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "Player.h"
#include "Unit.h"

#include <chrono>

namespace DC::Combat::DemonHunter::SmokeScreen
{
    namespace
    {
        constexpr std::string_view Skill = "Smoke Screen";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        void Regen(Player* player, std::uint32_t spellId, unsigned left, double life, double tickSeconds)
        {
            if (!left || !player->IsAlive() || !player->IsInWorld())
                return;
            Heal(player, spellId, life);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, left, life, tickSeconds]
                                                  { Regen(player, spellId, left - 1, life, tickSeconds); },
                                                  std::chrono::milliseconds(std::uint32_t(tickSeconds * 1000.0)));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId))
            return;
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        Rune const rune = RuneAt(spellId);
        // "becoming momentarily invisible for {duration_seconds} second".
        Vanish(player, seconds);
        // "Gain {movement_speed_pct} movement speed while invisible": the power file gives every rune 15%, Displacement
        // 100%.
        Buffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped,
                     SpeedPct(rune, rune == Rune::Displacement ? Numbers::Num(spellId, "movement_speed_pct") : 0.0,
                              Tune("smoke_screen_movement_speed_pct")),
                     1, seconds);
        // Healing Vapors: "Regenerate {life_regen_pct}% Life while invisible", given in shares a tick apart.
        if (rune == Rune::HealingVapors)
        {
            double const tick = Tune("smoke_screen_regen_tick_seconds");
            if (unsigned const ticks = Dot::Ticks(seconds, tick))
                Regen(player, spellId, ticks,
                      RegenPerTick(player->GetMaxHealth(), Numbers::Num(spellId, "life_regen_pct"), tick), tick);
        }
        // "This ability does not start its cooldown until after its effects expire": the cooldown the core just
        // installed is pushed back by the invisibility's seconds, on every rune (they share it).
        for (auto const& ability : Shells::Abilities)
            if (Skill == ability.skill && player->GetSpellCooldownDelay(ability.id))
                player->ModifySpellCooldown(ability.id, std::int32_t(CooldownDelayMs(seconds)));
    }
} // namespace DC::Combat::DemonHunter::SmokeScreen
