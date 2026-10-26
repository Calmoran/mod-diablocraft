/*
 * Evasive Fire and its five runes. The bolts are the engine's cone shot (a spell record and the sheet's numbers) that
 * hits every enemy in the cone; here: the bolts that reach only the enemy aimed at and the nearest two beside it, the
 * side bolts' own damage, the backflip (and Hardened's armor and Focus's Hatred instead of it), Parting Gift's bomb.
 * Surge's longer backflip, Focus's Hatred and the runes' elements are sheet numbers the same code reads.
 */

#include "dc_demon_hunter_evasive_fire.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>

namespace DC::Combat::DemonHunter::EvasiveFire
{
    namespace
    {
        constexpr std::string_view Skill = "Evasive Fire";

        // Whether an enemy stands in front of the Demon Hunter, near enough and inside the search angle.
        bool EnemyNear(Player* player, std::uint32_t spellId)
        {
            double const radius = Tune("evasive_fire_flip_search_yards");
            std::vector<double> distances, bearings;
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), radius))
            {
                distances.push_back(player->GetExactDist(enemy));
                bearings.push_back(player->GetAngle(enemy));
            }
            return EnemyInFront(distances, bearings, player->GetOrientation(), radius,
                                Tune("evasive_fire_flip_search_degrees"));
        }

        // The nearest enemies of the cone beside the one aimed at, as many as the bolts reach in all less that one,
        // inside the spread.
        std::vector<Unit*> Beside(Player* player, std::uint32_t spellId, Unit* aimed,
                                  std::vector<ObjectGuid> const& cone)
        {
            std::vector<Unit*> around;
            std::vector<double> distances, bearings;
            std::vector<bool> excluded;
            for (ObjectGuid const& guid : cone)
            {
                Unit* enemy = ObjectAccessor::GetUnit(*player, guid);
                if (!enemy || !enemy->IsAlive())
                    continue;
                around.push_back(enemy);
                distances.push_back(player->GetExactDist(enemy));
                bearings.push_back(player->GetAngle(enemy));
                excluded.push_back(enemy == aimed);
            }
            std::vector<Unit*> found;
            auto const hit = std::size_t(std::max(0.0, Tune("evasive_fire_enemies_hit") - 1));
            for (std::size_t index : Seek(distances, bearings, excluded, Combat::TargetRadius(spellId),
                                          player->GetAngle(aimed), Tune("evasive_fire_spread_degrees"), hit))
                found.push_back(around[index]);
            return found;
        }

        // Parting Gift: "leave a bomb behind that explodes for {damage_pct} weapon damage ... in a {radius_yards} yard
        // radius after {delay_seconds} seconds."
        void LeaveBomb(Player* player, std::uint32_t spellId, Position where)
        {
            player->m_Events.AddEventAtOffset(
                [player, spellId, where]
                {
                    if (!player->IsAlive() || !player->IsInWorld())
                        return;
                    auto const pct = Numbers::Own(spellId, "damage_pct");
                    for (Unit* enemy : Combat::Enemies(player, spellId, where, Numbers::Num(spellId, "radius_yards")))
                        Combat::Strike(player, enemy, spellId, pct);
                },
                std::chrono::milliseconds(std::uint32_t(Numbers::Num(spellId, "delay_seconds") * 1000 + 0.5)));
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
        return Numbers::Get(BaseId(Skill), "damage_pct", "primary");
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId, Skill);
        if (!player || !row || !EnemyNear(player, spellId))
            return;
        Rune const rune = RuneOf(row->rune);
        if (rune == Rune::Hardened)
        {
            // "Instead of backflipping, your Armor is increased by {armor_pct} for {duration_seconds} seconds."
            Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1,
                         Numbers::Num(spellId, "duration_seconds"));
            return;
        }
        if (!Backflips(rune))
            return;
        // "you will backflip away {distance_yards} yards": straight back from where the Demon Hunter faces.
        Position const from = player->GetPosition();
        Position to = from;
        double const back = player->GetOrientation() + M_PI, yards = Numbers::Num(spellId, "distance_yards");
        to.Relocate(from.GetPositionX() + std::cos(back) * yards, from.GetPositionY() + std::sin(back) * yards,
                    from.GetPositionZ());
        Abilities::Pull(player, to);
        Passive::Backflipped(player);
        if (rune == Rune::PartingGift)
            LeaveBomb(player, spellId, from);
    }

    bool Impact(Player* player, Unit* target, Unit* aimed, std::vector<ObjectGuid> const& cone, std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId, Skill);
        if (!player || !target || !aimed || !row || target == aimed)
            return false;
        // "hits the primary enemy for {damage_pct:primary} weapon damage and two additional enemies for
        // {damage_pct:other}"; Covering Fire: "Increase the damage of side bolts to {damage_pct}".
        auto const beside = Beside(player, spellId, aimed, cone);
        if (std::find(beside.begin(), beside.end(), target) != beside.end())
            Combat::Strike(player, target, spellId,
                           RuneOf(row->rune) == Rune::CoveringFire ? Numbers::Num(spellId, "damage_pct")
                                                                   : Numbers::Num(spellId, "damage_pct", "other"));
        return true;
    }
} // namespace DC::Combat::DemonHunter::EvasiveFire
