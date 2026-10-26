/*
 * Rapid Fire and its five runes. The record is a real channel (the core holds it until the Demon Hunter lets go or does
 * something else) with no hit and no cost of its own; here: the start's Hatred, a shot at the targeted enemy at the
 * cadence attack speed gives, the Hatred of each shot, and the rune's part: Bombardment's grenades, High Velocity's
 * pierce, Fire Support's rockets, Frost Shots' chill. Withering Fire's cheaper start is a sheet number the same code
 * reads.
 */

#include "dc_demon_hunter_rapid_fire.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "dc_demon_hunter_seek.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "Util.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::RapidFire
{
    namespace
    {
        constexpr std::string_view Skill = "Rapid Fire";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        struct Channel
        {
            std::uint32_t spellId = 0;
            ObjectGuid aim;
            double shotClock = 0;   // ms since the last shot
            double rocketClock = 0; // ms since the last rocket
            double warmup = 0;      // ms before the first rocket
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Channel> channels;

        // Shots in a second of attack speed: Bombardment's grenades are slower than the arrows.
        double ShotsPer(std::uint32_t spellId)
        {
            return RuneAt(spellId) == Rune::Bombardment ? Tune("rapid_fire_bombardment_shots_per_attack")
                                                        : Tune("rapid_fire_shots_per_attack");
        }

        // The weapon damage for a second of attack speed: Bombardment's own, the skill's for every other rune.
        double Total(std::uint32_t spellId)
        {
            return RuneAt(spellId) == Rune::Bombardment ? Numbers::Num(spellId, "damage_pct")
                                                        : Numbers::Num(BaseId(Skill), "damage_pct");
        }

        double Initial(std::uint32_t spellId)
        {
            return Numbers::Num(spellId, "cost_resource", "initial");
        }

        // High Velocity: "arrows that have a {proc_chance_pct} chance to pierce through enemies": after each enemy
        // struck the arrow rolls, and a pierce goes on to the next enemy on the line beyond it.
        void Pierce(Player* player, std::uint32_t spellId, Unit* first, double pct)
        {
            double const length = Tune("rapid_fire_pierce_length_yards"), width = Tune("rapid_fire_pierce_width_yards"),
                         heading = player->GetAngle(first), reached = player->GetExactDist(first);
            Position const from = player->GetPosition();
            std::vector<Unit*> behind;
            for (Unit* enemy : Combat::Enemies(player, spellId, from, length))
                if (enemy != first && player->GetExactDist(enemy) > reached &&
                    OnLine(enemy->GetPositionX() - from.GetPositionX(), enemy->GetPositionY() - from.GetPositionY(),
                           heading, length, width))
                    behind.push_back(enemy);
            std::sort(behind.begin(), behind.end(),
                      [player](Unit* a, Unit* b) { return player->GetExactDist(a) < player->GetExactDist(b); });
            for (Unit* enemy : behind)
            {
                if (!roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                    return;
                Combat::Strike(player, enemy, spellId, pct);
            }
        }

        // One shot at `target`: its Hatred, then its damage; false when the Hatred is not there, which ends the
        // channel.
        bool Shoot(Player* player, Unit* target, Channel const& channel)
        {
            std::uint32_t const spellId = channel.spellId;
            double const shots = ShotsPer(spellId),
                         cost = ShotCost(Numbers::Num(spellId, "cost_resource", "channel"), shots),
                         pct = ShotPct(Total(spellId), shots);
            if (Resources::Get(player, Resources::Hatred) < cost)
                return false;
            Resources::SpendUnits(player, Resources::Hatred,
                                  int32(std::lround(Resources::ToUnits(Resources::Hatred, cost))));
            switch (RuneAt(spellId))
            {
                case Rune::Bombardment:
                    // "Rapidly fire grenades that explode for {damage_pct} weapon damage as Fire to all enemies within
                    // a {radius_yards} yard radius": a grenade goes no farther than the file's range.
                    if (player->GetExactDist(target) <= Tune("rapid_fire_grenade_range_yards"))
                        for (Unit* enemy : Combat::Enemies(player, spellId, target->GetPosition(),
                                                           Passive::GrenadeRadius(player, spellId, Numbers::Num(spellId, "radius_yards"))))
                            Combat::Strike(player, enemy, spellId, pct);
                    break;
                case Rune::HighVelocity:
                    if (Combat::Strike(player, target, spellId, pct))
                        Pierce(player, spellId, target, pct);
                    break;
                case Rune::FrostShots:
                    // "Enemies hit by Rapid Fire are Chilled by {chill_pct} for {chill_duration_seconds} seconds."
                    if (Combat::Strike(player, target, spellId, pct))
                        Slow(player, target, Numbers::Num(spellId, "chill_pct"),
                             Numbers::Num(spellId, "chill_duration_seconds"));
                    break;
                default:
                    Combat::Strike(player, target, spellId, pct);
                    break;
            }
            Combat::Connected(player, spellId, 1);
            return true;
        }

        // Fire Support: "launch {projectile_count} homing rockets every second. Each rocket deals {damage_pct} weapon
        // damage": a rocket homes on the nearest enemy to the Demon Hunter within the file's search radius.
        void Rocket(Player* player, std::uint32_t spellId)
        {
            Unit* nearest = nullptr;
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Tune("rapid_fire_rocket_range_yards")))
                if (!nearest || player->GetExactDist(enemy) < player->GetExactDist(nearest))
                    nearest = enemy;
            if (nearest)
                Combat::Strike(player, nearest, spellId, Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(player));
        }

        class Channels final : public PlayerScript
        {
        public:
            Channels()
                : PlayerScript("dc_demon_hunter_rapid_fire",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Channel channel;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = channels.find(player->GetGUID().GetRawValue());
                    if (found == channels.end())
                        return;
                    channel = found->second;
                }
                // The player let go - cast something else, was interrupted - or died: the core ended the channel.
                Spell* current = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
                Unit* target = ObjectAccessor::GetUnit(*player, channel.aim);
                if (!player->IsAlive() || !current || current->GetSpellInfo()->Id != channel.spellId || !target ||
                    !target->IsAlive())
                {
                    if (current && current->GetSpellInfo()->Id == channel.spellId)
                        player->InterruptSpell(CURRENT_CHANNELED_SPELL);
                    Stop(player);
                    return;
                }
                std::uint32_t const spellId = channel.spellId;
                unsigned const shots =
                    Due(channel.shotClock, diff,
                        ShotSeconds(ShotsPer(spellId), Combat::AttacksPerSecond(player, spellId)) * 1000.0);
                for (unsigned i = 0; i < shots && target->IsAlive(); ++i)
                    if (!Shoot(player, target, channel))
                    {
                        // Out of Hatred: the channel is over.
                        player->InterruptSpell(CURRENT_CHANNELED_SPELL);
                        Stop(player);
                        return;
                    }
                if (RuneAt(spellId) == Rune::FireSupport)
                {
                    channel.warmup = std::max(0.0, channel.warmup - diff);
                    if (channel.warmup <= 0)
                        for (unsigned i = 0,
                                      rockets = Due(channel.rocketClock, diff,
                                                    RocketSeconds(Numbers::Num(spellId, "projectile_count")) * 1000.0);
                             i < rockets; ++i)
                            Rocket(player, spellId);
                }
                std::lock_guard<std::mutex> guard(mutex);
                if (auto found = channels.find(player->GetGUID().GetRawValue()); found != channels.end())
                    found->second = channel;
            }

            void OnPlayerLogout(Player* player) override
            {
                Stop(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Stop(player);
            }

            static void Stop(Player* player)
            {
                std::lock_guard<std::mutex> guard(mutex);
                channels.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    bool Affordable(Player* player, std::uint32_t spellId)
    {
        return !Is(spellId) || !player || Resources::Get(player, Resources::Hatred) >= Initial(spellId);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId) || targets.empty())
            return;
        // "Cost: {cost_resource:initial} Hatred initially": the record carries no cost, the start is paid here.
        double const initial = Initial(spellId);
        if (Resources::Get(player, Resources::Hatred) < initial)
        {
            player->InterruptSpell(CURRENT_CHANNELED_SPELL);
            return;
        }
        Resources::SpendUnits(player, Resources::Hatred,
                              int32(std::lround(Resources::ToUnits(Resources::Hatred, initial))));
        Channel channel;
        channel.spellId = spellId;
        channel.aim = targets.front()->GetGUID();
        channel.warmup = Tune("rapid_fire_rocket_warmup_seconds") * 1000.0;
        // The first shot fires with the cast.
        if (!Shoot(player, targets.front(), channel))
        {
            player->InterruptSpell(CURRENT_CHANNELED_SPELL);
            return;
        }
        std::lock_guard<std::mutex> guard(mutex);
        channels[player->GetGUID().GetRawValue()] = channel;
    }

    void RegisterScripts()
    {
        new Channels();
    }
} // namespace DC::Combat::DemonHunter::RapidFire
