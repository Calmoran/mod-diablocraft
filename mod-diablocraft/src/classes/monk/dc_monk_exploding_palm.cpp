/*
 * Exploding Palm and its five runes.
 */

#include "dc_monk_exploding_palm_cast.h"
#include "dc_monk_exploding_palm.h"
#include "../dc_resources.h"
#include "dc_monk_common.h"
#include "../../combat/dc_item_powers.h"
#include "ObjectAccessor.h"
#include "ScriptMgr.h"

#include <chrono>
#include <string>

namespace DC::Combat::Monk::ExplodingPalm
{
    namespace
    {
        constexpr std::string_view Skill = "Exploding Palm";
        // The two kinds of run: the bleed (or burn) the palm itself leaves, and Essence Burn's burn from the explosion.
        constexpr unsigned Bleed = 0, Burn = 1;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Row(spellId);
            return row && rune == row->rune;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::mutex mutex;
        Marks marks;
        Runs runs;

        // One tick of a run: the damage, then the next, until the ticks are used, the run is replaced, the palm is gone
        // (the bleed), or the enemy or the Monk is dead.
        void Tick(Player* player, ObjectGuid enemy, std::uint32_t spellId, unsigned kind, std::uint64_t stamp,
                  unsigned left, double pct, std::uint32_t intervalMs)
        {
            auto const caster = player->GetGUID().GetRawValue();
            Unit* target = ObjectAccessor::GetUnit(*player, enemy);
            bool const alive = target && target->IsAlive() && player->IsAlive();
            {
                std::lock_guard<std::mutex> guard(mutex);
                if (!runs.Live(caster, enemy.GetRawValue(), kind, stamp))
                    return;
                if (!alive || left == 0 || (kind == Bleed && !marks.Live(caster, enemy.GetRawValue(), spellId, Now())))
                {
                    runs.End(caster, enemy.GetRawValue(), kind, stamp);
                    return;
                }
            }
            Combat::Strike(player, target, spellId, pct, true);
            if (left > 1)
                player->m_Events.AddEventAtOffset(
                    [player, enemy, spellId, kind, stamp, left, pct, intervalMs]
                    { Tick(player, enemy, spellId, kind, stamp, left - 1, pct, intervalMs); },
                    std::chrono::milliseconds(intervalMs));
            else
            {
                std::lock_guard<std::mutex> guard(mutex);
                runs.End(caster, enemy.GetRawValue(), kind, stamp);
            }
        }

        // `totalPct` of weapon damage spread over `seconds` at `perSecond` ticks a second, on `enemy`.
        void Run(Player* player, Unit* enemy, std::uint32_t spellId, unsigned kind, double totalPct, double seconds,
                 double perSecond)
        {
            unsigned const ticks = Ticks(seconds, perSecond);
            if (!ticks || totalPct <= 0)
                return;
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                stamp = runs.Start(player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue(), kind);
            }
            auto const interval = std::uint32_t(1000.0 / perSecond + 0.5);
            // A copy's run (Rabid Strike) carries the copy's multiplier into every tick.
            double const pct = TickPct(totalPct, ticks) * Combat::CopyFactor();
            player->m_Events.AddEventAtOffset(
                [player, guid = enemy->GetGUID(), spellId, kind, stamp, ticks, pct, interval]
                { Tick(player, guid, spellId, kind, stamp, ticks, pct, interval); },
                std::chrono::milliseconds(interval));
        }

        // How long the palm lasts: Essence Burn states its own ("dot" 9), the others the skill's.
        double PalmSeconds(std::uint32_t spellId)
        {
            return IsRune(spellId, "Essence Burn") ? Numbers::Num(spellId, "dot_duration_seconds", "dot")
                                                   : Numbers::Num(spellId, "dot_duration_seconds");
        }

        void Palm(Player* player, Unit* enemy, std::uint32_t spellId)
        {
            double const seconds = PalmSeconds(spellId);
            if (seconds <= 0 || !enemy->IsAlive())
                return;
            {
                std::lock_guard<std::mutex> guard(mutex);
                marks.Prune(Now());
                marks.Set(player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue(), spellId,
                          Now() + std::uint64_t(seconds * 1000.0));
            }
            // "Cause an enemy to Bleed for {damage_pct:dot} weapon damage ... over {dot_duration_seconds} seconds";
            // Impending Doom "no longer causes the enemy to bleed". D3's DoT ticks once an attack period
            // (Power/Monk_ExplodingPalm.pow SF_5 'Attack Speed'): the total stays the sheet's whatever your attack
            // speed is.
            if (!IsRune(spellId, "Impending Doom"))
                Run(player, enemy, spellId, Bleed, Numbers::Num(spellId, "damage_pct", "dot"), seconds,
                    Combat::AttacksPerSecond(player, spellId));
            // "Enemies hit take {damage_taken_pct} additional damage for {duration_seconds} seconds."
            if (IsRune(spellId, "The Flesh is Weak"))
                Effects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"),
                               Numbers::Num(spellId, "duration_seconds"));
        }

        // The palm's enemy has died: the explosion, around where it fell.
        void Explode(Player* player, Unit* dead, std::uint32_t spellId)
        {
            Position const center = dead->GetPosition();
            double const radius = Tune("exploding_palm_explosion_radius_yards");
            // The `explosion` rows (Gungdo Gear: "Exploding Palm's on-death explosion applies Exploding Palm") fire
            // on each enemy the blast reaches, before its damage, so an enemy the blast kills carries the palm and explodes in turn.
            for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
                if (enemy != dead)
                    ItemPowers::Exploded(player, enemy, std::string(Skill));
            // The Fist of Az'Turrasq: "Exploding Palm's on-death explosion damage is increased by N%." The explosion only, not the bleed.
            double const part = ItemPowers::SkillFactor(player, std::string(Skill), "explosion_damage_pct");
            if (IsRune(spellId, "Essence Burn"))
            {
                // "... it explodes causing all nearby enemies to burn for {damage_pct:explosion} weapon damage as Fire
                // over {dot_duration_seconds:explosion} seconds": ticks every SF_28 0.25 s.
                double const tick = Tune("exploding_palm_burn_tick_seconds");
                for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
                    if (enemy != dead)
                        Run(player, enemy, spellId, Burn, Numbers::Num(spellId, "damage_pct", "explosion") * part,
                            Numbers::Num(spellId, "dot_duration_seconds", "explosion"), tick > 0 ? 1.0 / tick : 0.0);
                return;
            }
            // Impending Doom's explosion is its own row (6305%), the others the skill's "explosion" (2770%).
            auto pct = IsRune(spellId, "Impending Doom") ? Numbers::Own(spellId, "damage_pct")
                                                         : Numbers::Get(spellId, "damage_pct", "explosion");
            if (pct)
                *pct *= part;
            std::size_t caught = 0;
            for (Unit* enemy : Combat::StrikeArea(player, spellId, center, radius, pct))
                if (enemy != dead)
                    ++caught;
            // "If the enemy explodes after bleeding, gain {gain_resource} Spirit for each enemy caught in the blast."
            if (IsRune(spellId, "Strong Spirit") && caught)
                Resources::Energize(player, Resources::Spirit, spellId,
                                    Numbers::Num(spellId, "gain_resource") * caught);
        }

        class dc_monk_exploding_palm_death final : public UnitScript
        {
        public:
            dc_monk_exploding_palm_death()
                : UnitScript("dc_monk_exploding_palm_death", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* unit, Unit*) override
            {
                if (!unit)
                    return;
                std::vector<Mark> palms;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    palms = marks.Take(unit->GetGUID().GetRawValue(), Now());
                }
                for (Mark const& palm : palms)
                {
                    Player* player = ObjectAccessor::FindPlayer(ObjectGuid(palm.caster));
                    if (player && player->IsAlive() && player->IsInWorld() && player->IsInMap(unit))
                        Explode(player, unit, palm.spellId);
                }
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Row(spellId))
            return std::nullopt;
        return 0.0;
    }

    bool Apply(Player* player, Unit* enemy, std::uint32_t spellId)
    {
        if (!player || !enemy || !Row(spellId) || !enemy->IsAlive())
            return false;
        Palm(player, enemy, spellId);
        return true;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Row(spellId) || targets.empty())
            return;
        Unit* primary = targets.front();
        Palm(player, primary, spellId);
        // Shocking Grasp: "arcs up to {radius_yards} yards to another target": the nearest other enemy.
        if (IsRune(spellId, "Shocking Grasp"))
        {
            std::vector<Unit*> others;
            std::vector<double> distances;
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, primary->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                if (enemy != primary)
                {
                    others.push_back(enemy);
                    distances.push_back(primary->GetExactDistSq(enemy));
                }
            int const nearest = Nearest(distances, Numbers::Num(spellId, "radius_yards"));
            if (nearest >= 0)
                Palm(player, others[std::size_t(nearest)], spellId);
        }
    }

    void RegisterScripts()
    {
        new dc_monk_exploding_palm_death();
    }
} // namespace DC::Combat::Monk::ExplodingPalm
