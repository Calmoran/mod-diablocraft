/*
 * Seven-Sided Strike and its five runes.
 */

#include "dc_monk_seven_sided_strike.h"
#include "dc_monk_common.h"
#include "../../combat/dc_item_powers.h"
#include "ObjectAccessor.h"

#include <chrono>
#include <memory>

namespace DC::Combat::Monk::SevenSided
{
    namespace
    {
        constexpr std::string_view Skill = "Seven-Sided Strike";
        // Stock "Ice Blast" (15878), the freeze Fists of Thunder - Wind Blast holds with: Pandemonium's.
        constexpr std::uint32_t FreezeHold = 15878;

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

        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        void Freeze(Player* player, Unit* target, double seconds)
        {
            if (seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(FreezeHold, player->GetGUID());
            if (Aura* hold = player->AddAura(FreezeHold, target))
            {
                hold->SetMaxDuration(int32(seconds * 1000));
                hold->SetDuration(int32(seconds * 1000));
            }
        }

        // The Monk cannot be hit while the strikes run (D3): immune to damage
        // and to every school from the cast to the last strike, owned by the spell so another immunity is left alone.
        void Immune(Player* player, std::uint32_t spellId, bool on)
        {
            player->ApplySpellImmune(spellId, IMMUNITY_DAMAGE, SPELL_SCHOOL_MASK_ALL, on);
            player->ApplySpellImmune(spellId, IMMUNITY_SCHOOL, SPELL_SCHOOL_MASK_ALL, on);
        }

        // Incinerate: "causes enemies to burn for {damage_pct} weapon damage as Fire over {dot_duration_seconds}
        // seconds", a burn of its own for every strike (monk.js:855-864, an unnamed buff each hit). The tick length is
        // in no sheet and not in the power file (SF_24 scalar 6.3, SF_25 duration 3): a tunable (1 s by default),
        // and with it blank the burn is not built.
        void Burn(Player* player, Unit* enemy, std::uint32_t spellId)
        {
            if (!DC::Tunables::Has("monk", "seven_sided_strike_burn_tick_seconds"))
                return;
            double const tick = Tune("seven_sided_strike_burn_tick_seconds");
            unsigned const ticks = BurnTicks(Numbers::Num(spellId, "dot_duration_seconds"), tick);
            double const pct = TickPct(Numbers::Num(spellId, "damage_pct"), ticks);
            for (unsigned i = 1; i <= ticks; ++i)
                player->m_Events.AddEventAtOffset(
                    [player, guid = enemy->GetGUID(), spellId, pct]
                    {
                        if (Unit* target = ObjectAccessor::GetUnit(*player, guid); target && player->IsAlive())
                            Combat::Strike(player, target, spellId, pct, true);
                    },
                    std::chrono::milliseconds(std::uint64_t(i * tick * 1000 + 0.5)));
        }

        // One cast's strikes: the enemies it dashes between and the one struck last.
        struct Series
        {
            std::uint32_t spellId = 0;
            unsigned count = 0;
            std::vector<ObjectGuid> enemies;
            int last = -1;
        };

        void StrikeNext(Player* player, std::shared_ptr<Series> const& series, unsigned i)
        {
            std::uint32_t const id = series->spellId;
            if (player->IsAlive() && player->IsInWorld())
            {
                auto pick = [&]() -> Unit*
                {
                    std::vector<bool> standing;
                    for (ObjectGuid const& guid : series->enemies)
                    {
                        Unit* unit = ObjectAccessor::GetUnit(*player, guid);
                        standing.push_back(unit && unit->IsAlive() && player->IsValidAttackTarget(unit));
                    }
                    int const next = NextTarget(series->last, standing);
                    if (next < 0)
                        return nullptr;
                    series->last = next;
                    return ObjectAccessor::GetUnit(*player, series->enemies[next]);
                };
                Unit* target = pick();
                if (!target)
                {
                    // Everything it was dashing between is down: the nearby enemies now, from where the Monk stands.
                    series->enemies.clear();
                    series->last = -1;
                    for (Unit* enemy : Combat::Enemies(player, id, player->GetPosition(), Combat::TargetRadius(id)))
                        series->enemies.push_back(enemy->GetGUID());
                    target = pick();
                }
                if (target)
                {
                    std::vector<Unit*> struck;
                    // Fulminating Onslaught: "Each strike explodes, dealing {damage_pct} weapon damage as Holy in a
                    // {radius_yards} yard radius around the enemy" - the strike is the explosion (SF_0 = SF_3 x SF_22
                    // at the impact radius SF_13 = 1 + 6; monk.js:903-906, an area of 7 at 8.77).
                    if (IsRune(id, "Fulminating Onslaught"))
                        struck =
                            Combat::StrikeArea(player, id, target->GetPosition(), Numbers::Num(id, "radius_yards"));
                    else if (Combat::Strike(player, target, id))
                    {
                        struck.push_back(target);
                        Combat::Connected(player, id, 1);
                    }
                    for (Unit* enemy : struck)
                    {
                        // Pandemonium: "enemies hit by Seven-Sided Strike are Frozen for {freeze_duration_seconds}
                        // seconds" (SF_7 the chance, 1).
                        if (IsRune(id, "Pandemonium"))
                            Freeze(player, enemy, Numbers::Num(id, "freeze_duration_seconds"));
                        if (IsRune(id, "Incinerate"))
                            Burn(player, enemy, id);
                    }
                }
            }
            // "This ability does not start its cooldown until after its effects expire": the core started it with the
            // cast; the last strike starts it again, whole.
            if (i + 1 == series->count)
            {
                Combat::SendSkillCooldown(player, id, Combat::SkillCooldownMilliseconds(player, id));
                Immune(player, id, false);
            }
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Row(spellId))
            return std::nullopt;
        if (IsRune(spellId, "Fulminating Onslaught"))
            return Numbers::Get(spellId, "damage_pct");
        // Incinerate's own damage_pct is the burn; its strikes are the skill's.
        std::uint32_t const source = IsRune(spellId, "Incinerate") ? BaseId() : spellId;
        return StrikePct(Numbers::Num(source, "damage_pct"), Numbers::Num(spellId, "hit_count"));
    }

    bool CanCast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return true;
        // The skill needs a target (D3's RequiresTarget): an enemy within the
        // sheet's 25 yards, or Sudden Assault's target within its teleport. Refused before the cost and the cooldown.
        if (!Combat::Enemies(player, spellId, player->GetPosition(), Combat::TargetRadius(spellId)).empty())
            return true;
        Unit* selected = player->GetSelectedUnit();
        return IsRune(spellId, "Sudden Assault") && selected && player->IsValidAttackTarget(selected) &&
               player->GetExactDist(selected) <= Tune("seven_sided_strike_teleport_yards");
    }

    bool Start(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Unit* aimed)
    {
        if (!Is(spellId))
            return false;
        if (!player)
            return true;
        // The enemy the cast was aimed at, or the Monk's own target: struck first.
        Unit* aim = aimed && aimed != player && player->IsValidAttackTarget(aimed) ? aimed : nullptr;
        if (!aim)
            if (Unit* selected = player->GetSelectedUnit(); selected && player->IsValidAttackTarget(selected))
                aim = selected;
        std::vector<Unit*> enemies = targets;
        // Sudden Assault: "Teleport to the enemy" up to SF_19 'A: Max Teleport Distance' 50 yards; the strikes then
        // dash between the enemies around it.
        if (IsRune(spellId, "Sudden Assault") && aim &&
            player->GetExactDist(aim) <= Tune("seven_sided_strike_teleport_yards"))
        {
            float x, y, z;
            aim->GetNearPoint(player, x, y, z, player->GetCombatReach(), 0.0f, aim->GetAngle(player));
            Position landing(x, y, z);
            player->NearTeleportTo(x, y, z, landing.GetAngle(aim), true);
            enemies = Combat::Enemies(player, spellId, landing, Combat::TargetRadius(spellId));
        }
        Immune(player, spellId, true);
        auto series = std::make_shared<Series>();
        series->spellId = spellId;
        series->count = Strikes(Numbers::Num(spellId, "hit_count"),
                                ItemPowers::SkillSetTo(player, std::string(Skill), "extra_strikes", 0));
        if (aim && std::find(enemies.begin(), enemies.end(), aim) != enemies.end())
            series->enemies.push_back(aim->GetGUID());
        for (Unit* enemy : enemies)
            if (enemy != aim)
                series->enemies.push_back(enemy->GetGUID());
        // Power/Monk_SevenSidedStrike.pow SF_4 'Attack Delay Initial' 0.1 and the strikes SF_2 1.3 s less SF_16 0.3 s
        // apart over SF_1 7 (monk.js:887-889: tickinitial 6, tickrate 9 frames of 60).
        double const first = Tune("seven_sided_strike_first_strike_seconds") * 1000,
                     interval = Tune("seven_sided_strike_interval_seconds") * 1000;
        for (unsigned i = 0; i < series->count; ++i)
            player->m_Events.AddEventAtOffset([player, series, i] { StrikeNext(player, series, i); },
                                              std::chrono::milliseconds(StrikeAtMs(i, first, interval)));
        return true;
    }
} // namespace DC::Combat::Monk::SevenSided
