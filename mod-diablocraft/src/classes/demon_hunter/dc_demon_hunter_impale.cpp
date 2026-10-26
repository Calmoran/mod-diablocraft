/*
 * Impale and its five runes. The knife is the engine's single-target throw (a spell record and the sheet's numbers);
 * here: Overpenetration's pierce along the line, Impact's knockback and stun, Chemical Burn's burn, Ricochet's bounces
 * to the nearest enemies, Grievous Wounds' extra damage on a critical hit.
 */

#include "dc_demon_hunter_impale.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_dot.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_seek.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>

namespace DC::Combat::DemonHunter::Impale
{
    namespace
    {
        constexpr std::string_view Skill = "Impale";

        // The pierce and the bounces are strikes of the same spell and land too; they must not start a chain of their
        // own.
        thread_local bool chaining = false;
        // The extra damage of a critical hit lands as a strike too; it adds nothing more.
        thread_local bool adding = false;

        // Overpenetration: "The knife pierces through all enemies in a straight line": every other enemy on the line
        // from the Demon Hunter through the one hit, as far as the knife flies, takes the knife's hit.
        void Pierce(Player* player, std::uint32_t spellId, Unit* first)
        {
            double const length = Tune("impale_pierce_length_yards"), width = Tune("impale_pierce_width_yards"),
                         heading = player->GetAngle(first);
            Position const from = player->GetPosition();
            for (Unit* enemy : Combat::Enemies(player, spellId, from, length))
                if (enemy != first && OnLine(enemy->GetPositionX() - from.GetPositionX(),
                                             enemy->GetPositionY() - from.GetPositionY(), heading, length, width))
                    Combat::Strike(player, enemy, spellId);
        }

        // Ricochet: "The knife ricochets to {target_count} additional nearby enemies within {radius_yards} yards of
        // each other": from each enemy struck, the nearest enemy not struck yet.
        void Ricochet(Player* player, std::uint32_t spellId, Unit* first)
        {
            double const radius = Numbers::Num(spellId, "radius_yards"),
                         base = Numbers::Num(BaseId(Skill), "damage_pct"),
                         factor = Tune("impale_ricochet_damage_factor");
            std::vector<Unit*> struck{first};
            for (unsigned bounce = 1, most = unsigned(Numbers::Num(spellId, "target_count")); bounce <= most; ++bounce)
            {
                Unit* last = struck.back();
                std::vector<Unit*> around;
                std::vector<double> distances, bearings;
                std::vector<bool> flags;
                for (Unit* enemy : Combat::Enemies(player, spellId, last->GetPosition(), radius))
                {
                    around.push_back(enemy);
                    distances.push_back(last->GetExactDist(enemy));
                    bearings.push_back(0.0);
                    flags.push_back(std::find(struck.begin(), struck.end(), enemy) != struck.end());
                }
                auto const next = Seek(distances, bearings, flags, radius, 0.0, 360.0, 1);
                if (next.empty() ||
                    !Combat::Strike(player, around[next.front()], spellId, BouncePct(base, factor, bounce)))
                    return;
                struck.push_back(around[next.front()]);
            }
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
        return Numbers::Get(BaseId(Skill), "damage_pct");
    }

    bool Impact(Player* player, Unit* target, Unit* aimed, std::uint32_t spellId)
    {
        // The record carries Ricochet's count in the core's chain slot: the core would hit the enemies it chains to with the
        // knife's whole hit, besides the bounces, so only the enemy thrown at is left to the engine.
        auto const* row = RowOf(spellId, Skill);
        return player && target && aimed && row && target != aimed && RuneOf(row->rune) == Rune::Ricochet;
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        auto const* row = RowOf(spellId, Skill);
        if (!player || !target || !row)
            return;
        Rune const rune = RuneOf(row->rune);
        // "Critical Hits deal {damage_bonus_pct} additional damage": additional weapon damage, a strike of its own.
        if (rune == Rune::GrievousWounds && critical && !adding)
        {
            Scope scope(adding);
            Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_bonus_pct"));
        }
        if (chaining || adding)
            return;
        Scope scope(chaining);
        switch (rune)
        {
            case Rune::Overpenetration:
                Pierce(player, spellId, target);
                break;
            case Rune::Ricochet:
                Ricochet(player, spellId, target);
                break;
            case Rune::Impact:
                // "The impact causes Knockback and has a {proc_chance_pct} chance to Stun for {stun_duration_seconds}
                // seconds."
                Abilities::Knockback(player, target, Tune("impale_impact_knockback_yards"));
                if (roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                    Stun(player, target,
                         Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                break;
            case Rune::ChemicalBurn:
                // "The enemy also burns for {damage_pct} weapon damage as Fire over {dot_duration_seconds} seconds."
                Dot::Start(player, target, spellId, Numbers::Num(spellId, "damage_pct"),
                           Numbers::Num(spellId, "dot_duration_seconds"), Tune("impale_chemical_burn_tick_seconds"));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::DemonHunter::Impale
