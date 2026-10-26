/*
 * Command Skeletons and its five runes. The cast orders the skeletons at the enemy aimed at: they strike it for the skill's
 * bonus until it dies or another is ordered. Freezing Grasp also holds the target; Kill Command, instead of an order, sends
 * every skeleton off to explode on the target's place, each striking the enemies around it.
 */

#include "dc_necromancer_command_skeletons.h"
#include "dc_necromancer_command_skeletons_math.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_pets.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_minions.h"

#include <limits>

namespace DC::Combat::Necromancer::CommandSkeletons
{
    namespace
    {
        constexpr std::string_view Skill = "Command Skeletons";
        // D3 gives the order no time ("Active: Damage Increase Duration" 0, SF_9): it stands until its target dies or the next
        // order replaces it.
        constexpr std::uint32_t UntilTheTargetDies = std::numeric_limits<std::uint32_t>::max() / 2;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // "Now commands your skeletons to explode, dealing {damage_pct} weapon damage as Poison to enemies within
        // {radius_yards} yards": each skeleton strikes every enemy around the target once, and is spent.
        void Explode(Player* player, std::uint32_t spellId, Unit* target)
        {
            unsigned const skeletons = Minions::Alive(player, "skeleton");
            if (!skeletons)
                return;
            double const pct = Numbers::Num(spellId, "damage_pct");
            auto const enemies = Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards"));
            unsigned struck = 0;
            for (unsigned i = 0; i < skeletons; ++i)
                for (Unit* enemy : enemies)
                    if (enemy->IsAlive() && Combat::Strike(player, enemy, spellId, pct))
                        ++struck;
            Minions::Dismiss(player, "skeleton");
            if (struck)
                Combat::Connected(player, spellId, unsigned(enemies.size()));
        }
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !RowOf(spellId, Skill) || targets.empty() || !targets.front() || !targets.front()->IsAlive())
            return;
        Unit* target = targets.front();
        Rune const rune = RuneAt(spellId);
        if (rune == Rune::KillCommand)
        {
            Explode(player, spellId, target);
            return;
        }
        Pets::CommandSkeletons(player, target, UntilTheTargetDies);
        // "The target of your command is frozen for {freeze_duration_seconds} seconds": a stun, stretched by the worn stun
        // powers.
        if (rune == Rune::FreezingGrasp)
            Stun(player, target, Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));
    }
} // namespace DC::Combat::Necromancer::CommandSkeletons
