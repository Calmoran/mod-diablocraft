/*
 * Bolas and its five runes. The bola is the engine's single-target shot (a spell record and the sheet's numbers) that
 * lands for next to nothing; here: the wrap and the explosion after the fuse, Freezing Strike's three bolas that freeze
 * and do not explode, Bitter Pill's Discipline. Volatile Explosives' radius, Thunder Ball's Hatred and Imminent Doom's
 * damage and fuse are sheet numbers the same code reads.
 */

#include "dc_demon_hunter_bolas.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_seek.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>

namespace DC::Combat::DemonHunter::Bolas
{
    namespace
    {
        constexpr std::string_view Skill = "Bolas";

        // The explosions' strikes are strikes of the same spell and land too; they must not wrap anything.
        thread_local bool exploding = false;
        // The bolas of one volley are started from the first one's landing; their own landings start nothing.
        thread_local bool volley = false;

        // Freezing Strike: "Enemies hit have a {proc_chance_pct} chance to be Frozen for {freeze_duration_seconds}
        // second." A freeze is a stun, stretched by the stun duration items.
        void Freeze(Player* player, Unit* enemy, std::uint32_t spellId)
        {
            if (roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                Stun(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));
        }

        // Bitter Pill: "When the bola explodes, you have a {proc_chance_pct} chance to gain {gain_resource}
        // Discipline."
        void Bite(Player* player, std::uint32_t spellId)
        {
            if (Classes::ClassIdOf(player) == Resources::Discipline.classId &&
                Resources::Displayed(player, Resources::Discipline) &&
                roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                Resources::Energize(player, Resources::Discipline, spellId, Numbers::Num(spellId, "gain_resource"));
        }

        // The bola on an enemy goes off: the enemy takes the primary damage and every other enemy within the radius the
        // other damage; Freezing Strike's bola strikes its enemy alone and may freeze it.
        void Explode(Player* player, std::uint32_t spellId, Rune rune, ObjectGuid enemyGuid, Position last)
        {
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            Unit* primary = ObjectAccessor::GetUnit(*player, enemyGuid);
            if (primary)
                last = primary->GetPosition();
            Scope scope(exploding);
            if (rune == Rune::FreezingStrike)
            {
                if (primary && Combat::Strike(player, primary, spellId, Numbers::Num(spellId, "damage_pct")))
                    Freeze(player, primary, spellId);
            }
            else
            {
                if (primary)
                    Combat::Strike(player, primary, spellId, Numbers::Num(spellId, "damage_pct", "primary"));
                for (Unit* enemy : Combat::Enemies(player, spellId, last, Numbers::Num(spellId, "radius_yards")))
                    if (enemy != primary)
                        Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct", "other"));
            }
            if (rune == Rune::BitterPill)
                Bite(player, spellId);
        }

        void Wrap(Player* player, std::uint32_t spellId, Rune rune, Unit* enemy, double seconds)
        {
            player->m_Events.AddEventAtOffset(
                [player, spellId, rune, guid = enemy->GetGUID(), where = enemy->GetPosition()]
                { Explode(player, spellId, rune, guid, where); },
                std::chrono::milliseconds(std::uint32_t(seconds * 1000 + 0.5)));
        }

        // Freezing Strike: "Shoot {projectile_count} bolas": the one that landed and the nearest other enemies in a
        // cone ahead of the Demon Hunter, one bola each.
        std::vector<Unit*> Volley(Player* player, std::uint32_t spellId, Unit* first)
        {
            double const range = Tune("bolas_travel_yards");
            std::vector<Unit*> around;
            std::vector<double> distances, bearings;
            std::vector<bool> excluded;
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), range))
            {
                around.push_back(enemy);
                distances.push_back(player->GetExactDist(enemy));
                bearings.push_back(player->GetAngle(enemy));
                excluded.push_back(enemy == first);
            }
            std::vector<Unit*> found;
            std::size_t const others = std::size_t(std::max(0.0, Numbers::Num(spellId, "projectile_count") - 1));
            for (std::size_t index : Seek(distances, bearings, excluded, range, player->GetAngle(first),
                                          Tune("bolas_freezing_strike_cone_degrees"), others))
                found.push_back(around[index]);
            return found;
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
        return Tune("bolas_impact_damage_pct");
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId, Skill);
        if (exploding || volley || !player || !target || !row)
            return;
        Scope scope(volley);
        Rune const rune = RuneOf(row->rune);
        // "After {delay_seconds} second, the bola explodes".
        double const fuse = Numbers::Num(spellId, "delay_seconds");
        Wrap(player, spellId, rune, target, fuse);
        if (rune != Rune::FreezingStrike)
            return;
        double const perShot = Tune("bolas_freezing_strike_shot_delay_seconds");
        unsigned index = 1;
        for (Unit* enemy : Volley(player, spellId, target))
            Wrap(player, spellId, rune, enemy, ExplodesAfter(fuse, perShot, index++));
    }
} // namespace DC::Combat::DemonHunter::Bolas
