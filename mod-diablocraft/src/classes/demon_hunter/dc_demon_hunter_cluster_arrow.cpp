/*
 * Cluster Arrow and its five runes. The cast is the engine's ground cast (a record, its Hatred cost and the sheet's
 * numbers): the explosion at the impact, Loaded for Bear's bigger one and Dazzling Arrow's Lightning are the record's
 * own hit; here: the grenades that land round the impact, Shooting Stars' and Maelstrom's rockets, Cluster Bombs' line
 * of bombs, Dazzling Arrow's stun.
 */

#include "dc_demon_hunter_cluster_arrow.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "Unit.h"

#include <chrono>

namespace DC::Combat::DemonHunter::ClusterArrow
{
    namespace
    {
        constexpr std::string_view Skill = "Cluster Arrow";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The strikes of the grenades land through the engine's hit too: they alone may stun.
        thread_local bool grenading = false;

        double Roll()
        {
            return frand(0.0f, 1.0f);
        }

        // One explosion at `at`: every enemy within the grenades' radius takes `pct`. Grenadier makes the explosion wider and the
        // grenade harder (the power file's SF_32 and SF_28); the impact and the rockets are not grenades and do not ask.
        void Explode(Player* player, std::uint32_t spellId, Position const& at, double pct)
        {
            for (Unit* enemy : Combat::Enemies(player, spellId, at,
                                               Passive::GrenadeRadius(player, spellId, Tune("cluster_arrow_grenade_radius_yards"))))
                Combat::Strike(player, enemy, spellId, pct * Passive::GrenadierFactor(player));
        }

        // "a series of {projectile_count} additional grenades that each explode for {damage_pct:grenade} weapon
        // damage": each lands round the impact and explodes there.
        void Grenades(Player* player, std::uint32_t spellId, Position const& center)
        {
            Scope scope(grenading);
            for (unsigned i = 0, count = unsigned(Numbers::Num(spellId, "projectile_count")); i < count; ++i)
            {
                Spot const landing = GrenadeLanding(center.GetPositionX(), center.GetPositionY(), Roll(), Roll(),
                                                    Tune("cluster_arrow_grenade_offset_min_yards"),
                                                    Tune("cluster_arrow_grenade_offset_delta_yards"));
                Explode(player, spellId, Position(float(landing.x), float(landing.y), center.GetPositionZ()),
                        Numbers::Num(spellId, "damage_pct", "grenade"));
            }
        }

        // "release up to {max_count} rockets at nearby enemies that each deal {damage_pct} weapon damage": at the
        // nearest enemies to the impact, each arriving after the delay; Maelstrom's heal {heal_pct} Life per enemy hit.
        void Rockets(Player* player, std::uint32_t spellId, Position const& center)
        {
            auto const enemies = Combat::Enemies(player, spellId, center, Tune("cluster_arrow_rocket_range_yards"));
            std::vector<double> distances;
            for (Unit* enemy : enemies)
                distances.push_back(enemy->GetExactDist(&center));
            for (std::size_t place : NearestFirst(distances, std::size_t(Numbers::Num(spellId, "max_count"))))
                player->m_Events.AddEventAtOffset(
                    [player, spellId, guid = enemies[place]->GetGUID()]
                    {
                        Unit* target = ObjectAccessor::GetUnit(*player, guid);
                        if (!player->IsAlive() || !target || !target->IsAlive())
                            return;
                        if (Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(player)) &&
                            RuneAt(spellId) == Rune::Maelstrom)
                            Heal(player, spellId, Healed(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct")));
                    },
                    std::chrono::milliseconds(
                        std::uint32_t(Tune("cluster_arrow_rocket_delay_seconds") * 1000.0 + 0.5)));
        }

        // "Launch a cluster through the air, dropping grenades in a straight line that each explode for {damage_pct}
        // weapon damage": a fixed distance from the Demon Hunter toward the aim, a bomb every spawn interval.
        void Bombs(Player* player, std::uint32_t spellId, Position const& center)
        {
            Position const start = player->GetPosition();
            double const heading = start.GetAbsoluteAngle(&center);
            unsigned const count = unsigned(Tune("cluster_arrow_bombs_count"));
            for (unsigned i = 0; i < count; ++i)
            {
                Spot const landing = BombLanding(start.GetPositionX(), start.GetPositionY(), heading, i, count,
                                                 Tune("cluster_arrow_bombs_distance_yards"), Roll(),
                                                 Tune("cluster_arrow_bomb_spread_yards"));
                Position const at(float(landing.x), float(landing.y), start.GetPositionZ());
                player->m_Events.AddEventAtOffset(
                    [player, spellId, at]
                    {
                        if (player->IsAlive() && player->IsInWorld())
                            Explode(player, spellId, at, Numbers::Num(spellId, "damage_pct"));
                    },
                    std::chrono::milliseconds(BombDelayMs(i, Tune("cluster_arrow_bomb_interval_seconds"))));
            }
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        switch (RuneAt(spellId))
        {
            case Rune::LoadedForBear:
                return Numbers::Num(spellId, "damage_pct");
            case Rune::ClusterBombs:
                return 0.0;
            case Rune::None:
                return Is(spellId) ? std::optional<double>(Numbers::Num(spellId, "damage_pct", "impact"))
                                   : std::nullopt;
            default:
                // The rockets' number is the rune's own; the impact is the skill's.
                return Numbers::Num(BaseId(Skill), "damage_pct", "impact");
        }
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::ShootingStars:
            case Rune::Maelstrom:
                Rockets(player, spellId, center);
                break;
            case Rune::ClusterBombs:
                Bombs(player, spellId, center);
                break;
            default:
                Grenades(player, spellId, center);
                break;
        }
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        // "Enemies hit by the grenades have a {proc_chance_pct} chance to be stunned for {stun_duration_seconds}
        // seconds."
        if (!player || !target || !grenading || RuneAt(spellId) != Rune::DazzlingArrow)
            return;
        if (Stuns(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct")))
            Stun(player, target, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
    }
} // namespace DC::Combat::DemonHunter::ClusterArrow
