/*
 * Hungering Arrow and its five runes. The arrow is the engine's single-target shot (a spell record and the sheet's
 * numbers); here: the chance to pierce through to the next enemy and Devouring Arrow's growing hit, Shatter Shot's
 * split of the first pierce into three arrows, Spray of Teeth's burst on a critical hit. Puncturing Arrow's larger
 * chance and Serrated Arrow's Hatred are sheet numbers the same code reads.
 */

#include "dc_demon_hunter_hungering_arrow.h"
#include "dc_demon_hunter_common.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_tunables.h"
#include "Player.h"
#include "Unit.h"
#include "Util.h"

namespace DC::Combat::DemonHunter::HungeringArrow
{
    namespace
    {
        constexpr std::string_view Skill = "Hungering Arrow";

        // The pierces and the split are strikes of the same spell and land too; they must not start a chain of their
        // own.
        thread_local bool chaining = false;
        // The burst's strikes land too; they neither burst again nor pierce.
        thread_local bool bursting = false;

        // The nearest `count` enemies around `last` that the arrow has not struck, inside `radius` and the cone centred
        // on `heading`. An enemy farther from the Demon Hunter than the arrow travels is not reached.
        std::vector<Unit*> Next(Player* player, std::uint32_t spellId, Unit* last, std::vector<Unit*> const& struck,
                                double radius, double heading, double cone, std::size_t count)
        {
            std::vector<Unit*> around;
            std::vector<double> distances, bearings;
            std::vector<bool> flags;
            double const travel = Tune("hungering_arrow_travel_yards");
            for (Unit* enemy : Combat::Enemies(player, spellId, last->GetPosition(), radius))
            {
                if (!Reachable(player->GetExactDist(enemy), travel))
                    continue;
                around.push_back(enemy);
                distances.push_back(last->GetExactDist(enemy));
                bearings.push_back(last->GetAngle(enemy));
                flags.push_back(std::find(struck.begin(), struck.end(), enemy) != struck.end());
            }
            std::vector<Unit*> found;
            for (std::size_t index : Seek(distances, bearings, flags, radius, heading, cone, count))
                found.push_back(around[index]);
            return found;
        }

        // "has a {proc_chance_pct} chance to pierce through them": after each enemy struck the arrow rolls, and a
        // pierce flies on to the nearest enemy it has not struck inside the seek radius, with the damage the pierces so
        // far make it. Devouring Arrow: "Each consecutive pierce increases the damage of the arrow by
        // {damage_bonus_pct}".
        void Pierce(Player* player, std::uint32_t spellId, Rune rune, Unit* first)
        {
            double const chance = Numbers::Num(spellId, "proc_chance_pct"),
                         damage = Numbers::Num(BaseId(Skill), "damage_pct"),
                         bonus = rune == Rune::DevouringArrow ? Numbers::Num(spellId, "damage_bonus_pct") : 0.0,
                         seek = Tune("hungering_arrow_seek_after_pierce_yards");
            std::vector<Unit*> struck{first};
            for (unsigned pierces = 1;; ++pierces)
            {
                if (!roll_chance_f(float(chance)))
                    return;
                auto const next = Next(player, spellId, struck.back(), struck, seek, 0.0, 360.0, 1);
                if (next.empty() ||
                    !Combat::Strike(player, next.front(), spellId, PiercedDamagePct(damage, bonus, pierces)))
                    return;
                struck.push_back(next.front());
            }
        }

        // Shatter Shot: "If the arrow successfully pierces the first enemy, the arrow splits into {projectile_count}
        // arrows": the arrows go to the nearest enemies not struck yet inside the cone behind the enemy, each for the
        // arrow's hit.
        void Split(Player* player, std::uint32_t spellId, Unit* first)
        {
            if (!roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                return;
            std::vector<Unit*> const struck{first};
            // The power file's cone is the one behind the enemy, measured from the way the arrow was flying.
            for (Unit* enemy : Next(player, spellId, first, struck, Tune("hungering_arrow_shatter_seek_yards"),
                                    player->GetAngle(first), Tune("hungering_arrow_shatter_cone_degrees"),
                                    std::size_t(Numbers::Num(spellId, "projectile_count"))))
                Combat::Strike(player, enemy, spellId);
        }

        // Spray of Teeth: "Critical Hits cause a burst of bone to explode from the enemy, dealing {damage_pct} weapon
        // damage to enemies within {radius_yards} yards."
        void Burst(Player* player, std::uint32_t spellId, Unit* target)
        {
            auto const pct = Numbers::Own(spellId, "damage_pct");
            Scope scope(bursting);
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                Combat::Strike(player, enemy, spellId, pct);
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

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        auto const* row = RowOf(spellId, Skill);
        if (bursting || !player || !target || !row)
            return;
        Rune const rune = RuneOf(row->rune);
        if (!chaining)
        {
            Scope scope(chaining);
            if (rune == Rune::ShatterShot)
                Split(player, spellId, target);
            else
                Pierce(player, spellId, rune, target);
        }
        if (rune == Rune::SprayOfTeeth && critical)
            Burst(player, spellId, target);
    }
} // namespace DC::Combat::DemonHunter::HungeringArrow
