/*
 * Falling Sword and its five runes. The leap and the landing are the cast path's (skill_targeting.csv: a ground point
 * 80 yards off, 14 yards of area, struck when the Crusader lands); what is here is what each rune leaves at the landing
 * (Superheated's ground, Part the Clouds' storm, Rise Brothers' avatars, Flurry's swords), Rapid Descent's cut, and the
 * cooldown that starts once the effects are over. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_falling_sword.h"
#include "dc_crusader_common.h"
#include "dc_crusader_phalanx.h"
#include "dc_crusader_zone.h"
#include "../../combat/dc_item_powers.h"
#include "Random.h"

#include <chrono>
#include <cmath>

namespace DC::Combat::Crusader::FallingSword
{
    namespace
    {
        constexpr std::string_view Skill = "Falling Sword";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        std::chrono::milliseconds Millis(double seconds)
        {
            return std::chrono::milliseconds(std::llround(std::max(0.0, seconds) * 1000.0));
        }

        // One strike of the storm: a random enemy under it takes the lightning and is stunned. The strikes left bound
        // the storm by themselves, as a pool's ticks do.
        void Storm(Player* player, std::uint32_t spellId, Position center, unsigned left,
                   std::chrono::milliseconds every)
        {
            if (!player->IsInWorld() || !player->IsAlive() || left == 0)
                return;
            std::vector<Unit*> const under =
                Combat::Enemies(player, spellId, center, Tune("falling_sword_part_the_clouds_radius_yards"));
            if (auto const pick = Pick(under.size(), rand_chance() / 100.0))
            {
                Unit* enemy = under[*pick];
                // "Lightning strikes random enemies under the cloud, dealing {damage_pct} weapon damage as Lightning
                // and Stunning them for {stun_duration_seconds} seconds."
                Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));
                Stun(player, enemy, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
            }
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, spellId, center, left, every]
                                                  { Storm(player, spellId, center, left - 1, every); }, every);
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
        return Numbers::Own(BaseId(Skill), "damage_pct").value_or(0.0);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        // The core installed the cooldown at the cast; it starts again, whole, when the effects are over (or now, when
        // the rune leaves none), cut by Rapid Descent for each enemy the landing hit.
        double const whole = SkillCooldownMilliseconds(player, spellId) / 1000.0;
        double const seconds =
            CooldownSeconds(rune, whole, unsigned(targets.size()), Numbers::Num(spellId, "cooldown_reduction_seconds"),
                            Numbers::Num(spellId, "min_cooldown_seconds"));
        auto const start = std::uint32_t(Millis(seconds).count());
        double const wait = WaitSeconds(rune, Numbers::Num(spellId, "duration_seconds"));
        if (wait <= 0)
        {
            SendSkillCooldown(player, spellId, start);
            return;
        }
        player->m_Events.AddEventAtOffset(
            [player, spellId, start]
            {
                if (player->IsInWorld())
                    SendSkillCooldown(player, spellId, start);
            },
            Millis(wait));
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        switch (RuneAt(spellId))
        {
            case Rune::Superheated:
            {
                // "dealing {damage_pct} weapon damage as Fire per second to all enemies who pass over it."
                double const tick = Tune("falling_sword_superheated_tick_seconds");
                Zone::Lay(player, spellId, center, Tune("falling_sword_superheated_radius_yards"),
                          PctPerTick(Numbers::Num(spellId, "damage_pct"), seconds, tick), seconds, tick);
                break;
            }
            case Rune::PartTheClouds:
            {
                double const every = Tune("falling_sword_part_the_clouds_strike_seconds");
                if (unsigned const strikes = Dot::Ticks(seconds, every))
                    player->m_Events.AddEventAtOffset([player, spellId, center, strikes, ms = Millis(every)]
                                                      { Storm(player, spellId, center, strikes, ms); }, Millis(every));
                break;
            }
            case Rune::RiseBrothers:
                // "{pet_count} Avatars of the Order are summoned forth to fight by your side for {duration_seconds}
                // seconds. Each Avatar attacks for {damage_pct} of your weapon damage."
                Phalanx::Fighters(player, spellId, unsigned(Numbers::Num(spellId, "pet_count")), seconds,
                                  player->GetPosition());
                break;
            case Rune::Flurry:
            {
                // "dealing {damage_pct} weapon damage as Holy, hurling enemies around and incapacitating them for
                // {duration_seconds} seconds": the swords strike the flurry's enemies each tick, and the enemies there
                // when it lands are stunned for as long as it lasts.
                double const radius = Tune("falling_sword_flurry_radius_yards");
                double const tick = Tune("falling_sword_flurry_tick_seconds");
                for (Unit* enemy : Combat::Enemies(player, spellId, center, radius))
                    Stun(player, enemy, seconds * ItemPowers::StunFactor(player));
                Zone::Lay(player, spellId, center, radius,
                          PctPerTick(Numbers::Num(spellId, "damage_pct"), seconds, tick), seconds, tick);
                break;
            }
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::FallingSword
