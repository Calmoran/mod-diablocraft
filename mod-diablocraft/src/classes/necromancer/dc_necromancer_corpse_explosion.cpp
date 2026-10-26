/*
 * Corpse Explosion and its five runes. The cast takes up to five of the Necromancer's corpses nearest the point aimed
 * at and each explodes, striking the enemies within the explosion's radius of it for the skill's weapon damage. The
 * runes: Shrapnel blows the corpses away from the Necromancer in a cone, Final Embrace draws each corpse to the nearest
 * enemy first and costs Life, Close Quarters takes the corpses around the Necromancer, Bloody Mess widens the
 * explosion, Dead Cold freezes what it catches.
 */

#include "dc_necromancer_corpse_explosion.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_corpse_explosion_math.h"
#include "../../combat/dc_corpses.h"
#include "../../combat/dc_item_powers.h"

#include <algorithm>
#include <cmath>

namespace DC::Combat::Necromancer::CorpseExplosion
{
    namespace
    {
        constexpr std::string_view Skill = "Corpse Explosion";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The point corpses are taken around: the aimed point, or the Necromancer.
        Position SearchCentre(Player* player, std::uint32_t spellId, Position const& aim)
        {
            return TakesNearTheNecromancer(RuneAt(spellId)) ? player->GetPosition() : aim;
        }

        // "exploding up to 5 corpses within {radius_yards:corpse_range} yards" of the point.
        float CorpseRange(std::uint32_t spellId)
        {
            // Close Quarters searches further (the power's RUNEC Corpse Search Radius, 14).
            if (RuneAt(spellId) == Rune::CloseQuarters)
                return float(Tune("close_quarters_corpse_range_yards"));
            return float(Numbers::Num(BaseId(Skill), "radius_yards", "corpse_range"));
        }

        // "dealing damage to enemies within {radius_yards:explosion} yards": a rune that states a radius of its own
        // (Close Quarters, Bloody Mess) is that.
        double ExplosionRadius(std::uint32_t spellId)
        {
            // Shrapnel's blast is the length of its cone (the power's SHRAPNEL Radius, 45).
            if (RuneAt(spellId) == Rune::Shrapnel)
                return Tune("shrapnel_cone_yards");
            if (auto own = Numbers::Get(spellId, "radius_yards"))
                return *own;
            return Numbers::Num(spellId, "radius_yards", "explosion");
        }

        std::size_t MostCorpses()
        {
            return std::size_t(Tune("corpse_explosion_max_corpses"));
        }

        // One corpse goes off at `where`.
        unsigned Explode(Player* player, std::uint32_t spellId, Position const& corpse, Position const& where,
                         double radius, std::vector<Unit*>& caught)
        {
            Rune const rune = RuneAt(spellId);
            double const pct = Numbers::Num(spellId, "damage_pct");
            double const away = std::atan2(corpse.GetPositionY() - player->GetPositionY(),
                                           corpse.GetPositionX() - player->GetPositionX());
            unsigned struck = 0;
            for (Unit* enemy : Combat::Enemies(player, spellId, where, radius))
            {
                if (rune == Rune::Shrapnel &&
                    !InCone(where.GetPositionX(), where.GetPositionY(), std::cos(away), std::sin(away),
                            enemy->GetPositionX(), enemy->GetPositionY(), Tune("shrapnel_cone_degrees")))
                    continue;
                if (!Combat::Strike(player, enemy, spellId, pct))
                    continue;
                ++struck;
                if (std::find(caught.begin(), caught.end(), enemy) == caught.end())
                    caught.push_back(enemy);
            }
            return struck;
        }
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Position const* aim)
    {
        if (!player || !RowOf(spellId, Skill))
            return SPELL_CAST_OK;
        Position const centre = aim ? SearchCentre(player, spellId, *aim) : player->GetPosition();
        return Corpses::Count(player, centre, CorpseRange(spellId)) ? SPELL_CAST_OK : SPELL_FAILED_NO_VALID_TARGETS;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        Rune const rune = RuneAt(spellId);
        auto const taken =
            Corpses::Consume(player, SearchCentre(player, spellId, center), CorpseRange(spellId), MostCorpses());
        if (taken.empty())
            return;
        double const radius = ExplosionRadius(spellId);
        std::vector<Unit*> caught;
        unsigned struck = 0;
        for (Corpses::Spot const& spot : taken)
        {
            Position const corpse(spot.x, spot.y, spot.z);
            Position where = corpse;
            if (rune == Rune::FinalEmbrace)
            {
                // "Corpses pull themselves towards the nearest enemy before exploding."
                double const search = Tune("final_embrace_search_yards");
                auto const enemies = Combat::Enemies(player, spellId, corpse, search);
                std::vector<double> distances;
                for (Unit* enemy : enemies)
                    distances.push_back(corpse.GetExactDist(enemy));
                if (std::size_t const nearest = NearestWithin(distances, search); nearest < enemies.size())
                    where = enemies[nearest]->GetPosition();
            }
            struck += Explode(player, spellId, corpse, where, radius, caught);
        }
        if (rune == Rune::FinalEmbrace)
            SpendLife(player, LifeCostPct(Tune("final_embrace_life_cost_pct"), taken.size()));
        if (rune == Rune::DeadCold)
        {
            // "Freeze all enemies caught in the explosion for {freeze_duration_seconds} seconds": a stun, stretched by
            // the worn stun duration powers.
            double const frozen = Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player);
            for (Unit* enemy : caught)
                Stun(player, enemy, frozen);
        }
        if (struck)
            Combat::Connected(player, spellId, unsigned(caught.size()));
    }
} // namespace DC::Combat::Necromancer::CorpseExplosion
