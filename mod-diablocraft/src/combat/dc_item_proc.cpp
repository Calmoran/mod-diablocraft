/*
 * World of DiabloCraft - an item's weapon-damage proc, Combat's side (N-WPROC; Storm Crow's fiery ball). See
 * dc_item_proc.h.
 */

#include "dc_item_proc.h"
#include "dc_combat.h"
#include "dc_item_proc_math.h"
#include "dc_spell_shells.h"
#include "../common/dc_tunables.h"
#include "Player.h"
#include "Random.h"

#include <cstdint>
#include <string>

namespace DC::Combat::ItemProc
{
    namespace
    {
        // Each item whose ball this deals, with the combat tunable that holds its percent of weapon damage.
        struct Ball
        {
            char const* owner;
            char const* tunable;
        };
        constexpr Ball Balls[] = {
            {"Unique_WizardHat_004_x1", "storm_crow_fireball_damage_pct"},
        };

        // A combat tunable; a blank one reads 0.
        double Tune(char const* name)
        {
            return DC::Tunables::Has("combat", name) ? DC::Tunables::Get("combat", name) : 0.0;
        }
    } // namespace

    void Damage(Player* player, Unit* target, std::string const& owner, double chancePct, double coefficient)
    {
        if (!player || !target || !target->IsAlive())
            return;
        for (Ball const& ball : Balls)
        {
            if (owner != ball.owner)
                continue;
            std::uint32_t const record = Shells::PowerBuffFor(owner.c_str(), "proc_damage");
            double const pct = ItemProc::Pct(chancePct, coefficient, Tune(ball.tunable),
                                             [](double chance) { return roll_chance_f(static_cast<float>(chance)); });
            // Dealt as the wearer's: ComputeHit and DealHit and not Strike, so the ball is no hit of a skill and fires
            // no `hit` of its own (it cannot proc itself).
            Hit hit;
            if (record && pct > 0 && ComputeHit(player, target, record, hit, pct))
                DealHit(player, target, record, hit);
            return;
        }
    }
} // namespace DC::Combat::ItemProc
