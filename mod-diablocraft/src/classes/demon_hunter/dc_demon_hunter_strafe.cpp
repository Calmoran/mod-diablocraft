/*
 * Strafe and its five runes. The record is a real channel (the core holds it until the Demon Hunter lets go or does
 * something else) with no hit and no cost of its own; here: a shot at a random enemy near the Demon Hunter at the
 * cadence attack speed gives, the Hatred of each shot, the slowed run while it lasts, and the rune's part: Demolition's
 * grenades, Icy Trail's patches, Rocket Storm's rockets, Stinging Steel's extra on a critical hit. Drifting Shadow's
 * speed is the sheet's number read by the same code.
 */

#include "dc_demon_hunter_strafe.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "Unit.h"

#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Strafe
{
    namespace
    {
        constexpr std::string_view Skill = "Strafe";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The extra strike of a critical hit lands through the engine too and must not add another.
        thread_local bool adding = false;

        struct Channel
        {
            std::uint32_t spellId = 0;
            double shotClock = 0;   // ms since the last shot
            double rocketClock = 0; // ms since the last rocket
            double warmup = 0;      // ms before the first rocket
            double slowClock = 0;   // ms since the slow was last put on
            bool dropped = false;   // Icy Trail has dropped a patch
            Position lastPatch;
        };

        // A patch of ice, burning until its seconds are up (it stays when the channel ends).
        struct Patch
        {
            std::uint32_t spellId = 0;
            Position center;
            double left = 0;  // ms
            double clock = 0; // ms since the last tick
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Channel> channels;
        std::unordered_map<std::uint64_t, std::vector<Patch>> patches;

        double ShotsPer(std::uint32_t spellId)
        {
            return ShotsPerAttack(RuneAt(spellId), Tune("strafe_shots_per_attack"),
                                  Tune("strafe_demolition_shot_fraction"));
        }

        // The weapon damage for a second of attack speed: Demolition's own, the skill's for every other rune.
        double Total(std::uint32_t spellId)
        {
            return RuneAt(spellId) == Rune::Demolition ? Numbers::Num(spellId, "damage_pct")
                                                       : Numbers::Num(BaseId(Skill), "damage_pct");
        }

        // "Shoot at random nearby enemies": one of those within `range` of the Demon Hunter.
        Unit* RandomEnemy(Player* player, std::uint32_t spellId, double range)
        {
            auto const enemies = Combat::Enemies(player, spellId, player->GetPosition(), range);
            return enemies.empty() ? nullptr : enemies[PickAt(frand(0.0f, 1.0f), enemies.size())];
        }

        // One shot: its Hatred, then its damage; false when the Hatred is not there, which ends the channel.
        bool Shoot(Player* player, Channel const& channel)
        {
            std::uint32_t const spellId = channel.spellId;
            double const shots = ShotsPer(spellId),
                         cost = RapidFire::ShotCost(Numbers::Num(spellId, "cost_resource"), shots),
                         pct = RapidFire::ShotPct(Total(spellId), shots);
            if (Resources::Get(player, Resources::Hatred) < cost)
                return false;
            Resources::SpendUnits(player, Resources::Hatred,
                                  int32(std::lround(Resources::ToUnits(Resources::Hatred, cost))));
            Unit* target = RandomEnemy(player, spellId, Tune("strafe_seek_range_yards"));
            if (!target)
                return true;
            if (RuneAt(spellId) == Rune::Demolition)
            {
                // "Throw out bouncy grenades that explode for {damage_pct} weapon damage as Fire to enemies within
                // {radius_yards} yards."
                // Grenadier's larger explosion; its damage rides the record (Demolition is a grenade).
                for (Unit* enemy : Combat::Enemies(player, spellId, target->GetPosition(),
                                                   Passive::GrenadeRadius(player, spellId, Numbers::Num(spellId, "radius_yards"))))
                    Combat::Strike(player, enemy, spellId, pct);
            }
            else
                Combat::Strike(player, target, spellId, pct);
            Combat::Connected(player, spellId, 1);
            return true;
        }

        // Rocket Storm: "In addition to regular shots, shoot off homing rockets": at a random enemy within the file's
        // search radius.
        void Rocket(Player* player, std::uint32_t spellId)
        {
            if (Unit* target = RandomEnemy(player, spellId, Tune("strafe_rocket_range_yards")))
                Combat::Strike(
                    player, target, spellId,
                    RapidFire::ShotPct(Numbers::Num(spellId, "damage_pct"), Tune("strafe_rockets_per_attack")) * Passive::RocketFactor(player));
        }

        // "while moving at {movement_speed_pct} of normal movement speed": a slow put on again before it lapses, taken
        // off when the channel ends.
        void KeepSlow(Player* player, std::uint32_t spellId)
        {
            Slow(player, player, SlowPct(Numbers::Num(spellId, "movement_speed_pct")),
                 HoldSeconds(Tune("strafe_slow_refresh_seconds")));
        }

        // Icy Trail: a patch where the Demon Hunter stands, once they have moved far enough from the last one.
        void DropPatch(Player* player, Channel& channel)
        {
            Position const here = player->GetPosition();
            if (channel.dropped &&
                !DropsPatch(player->GetExactDist(&channel.lastPatch), Tune("strafe_trail_drop_yards")))
                return;
            Patch patch;
            patch.spellId = channel.spellId;
            patch.center = here;
            patch.left = Numbers::Num(channel.spellId, "dot_duration_seconds") * 1000.0;
            channel.dropped = true;
            channel.lastPatch = here;
            std::lock_guard<std::mutex> guard(mutex);
            patches[player->GetGUID().GetRawValue()].push_back(patch);
        }

        // One tick of a patch: "deals {damage_pct} weapon damage as Cold over {dot_duration_seconds} seconds and Chills
        // enemies for {chill_duration_seconds} seconds" to the enemies standing in it.
        void Freeze(Player* player, Patch const& patch, unsigned ticks)
        {
            double const pct =
                PatchTickPct(Numbers::Num(patch.spellId, "damage_pct"),
                             Numbers::Num(patch.spellId, "dot_duration_seconds"), Tune("strafe_trail_tick_seconds"));
            for (unsigned i = 0; i < ticks; ++i)
                for (Unit* enemy :
                     Combat::Enemies(player, patch.spellId, patch.center, Tune("strafe_trail_radius_yards")))
                {
                    Combat::Strike(player, enemy, patch.spellId, pct, true);
                    Slow(player, enemy, Tune("strafe_trail_chill_pct"),
                         Numbers::Num(patch.spellId, "chill_duration_seconds"));
                }
        }

        class Channels final : public PlayerScript
        {
        public:
            Channels()
                : PlayerScript("dc_demon_hunter_strafe",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                if (!player->IsAlive())
                {
                    Stop(player);
                    std::lock_guard<std::mutex> guard(mutex);
                    patches.erase(guid);
                    return;
                }
                Tick(player, diff);
                Burn(player, diff);
            }

            void OnPlayerLogout(Player* player) override
            {
                Stop(player);
                std::lock_guard<std::mutex> guard(mutex);
                patches.erase(player->GetGUID().GetRawValue());
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Stop(player);
                std::lock_guard<std::mutex> guard(mutex);
                patches.erase(player->GetGUID().GetRawValue());
            }

            static void Stop(Player* player)
            {
                bool had;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    had = channels.erase(player->GetGUID().GetRawValue()) > 0;
                }
                if (had)
                    Unslow(player, player);
            }

        private:
            // The channel's shots, rockets, patches and slow.
            static void Tick(Player* player, uint32 diff)
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
                if (!current || current->GetSpellInfo()->Id != channel.spellId)
                {
                    Stop(player);
                    return;
                }
                std::uint32_t const spellId = channel.spellId;
                unsigned const shots =
                    Due(channel.shotClock, diff,
                        RapidFire::ShotSeconds(ShotsPer(spellId), Combat::AttacksPerSecond(player, spellId)) * 1000.0);
                for (unsigned i = 0; i < shots; ++i)
                    if (!Shoot(player, channel))
                    {
                        // Out of Hatred: the channel is over.
                        player->InterruptSpell(CURRENT_CHANNELED_SPELL);
                        Stop(player);
                        return;
                    }
                Rune const rune = RuneAt(spellId);
                if (rune == Rune::RocketStorm)
                {
                    channel.warmup = std::max(0.0, channel.warmup - diff);
                    if (channel.warmup <= 0)
                        for (unsigned i = 0, rockets = Due(
                                                 channel.rocketClock, diff,
                                                 RapidFire::RocketSeconds(Tune("strafe_rockets_per_attack") *
                                                                          Combat::AttacksPerSecond(player, spellId)) *
                                                     1000.0);
                             i < rockets; ++i)
                            Rocket(player, spellId);
                }
                if (rune == Rune::IcyTrail)
                    DropPatch(player, channel);
                if (Due(channel.slowClock, diff, Tune("strafe_slow_refresh_seconds") * 1000.0))
                    KeepSlow(player, spellId);
                std::lock_guard<std::mutex> guard(mutex);
                if (auto found = channels.find(player->GetGUID().GetRawValue()); found != channels.end())
                    found->second = channel;
            }

            // The patches left behind, burning whether or not the channel goes on.
            static void Burn(Player* player, uint32 diff)
            {
                std::vector<Patch> mine;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = patches.find(player->GetGUID().GetRawValue());
                    if (found == patches.end())
                        return;
                    mine = found->second;
                }
                std::vector<Patch> kept;
                for (Patch& patch : mine)
                {
                    Freeze(player, patch, Due(patch.clock, diff, Tune("strafe_trail_tick_seconds") * 1000.0));
                    patch.left -= diff;
                    if (patch.left > 0)
                        kept.push_back(patch);
                }
                std::lock_guard<std::mutex> guard(mutex);
                auto found = patches.find(player->GetGUID().GetRawValue());
                if (found == patches.end())
                    return;
                // Patches dropped during this update were added to the stored list; keep them with what still burns.
                for (std::size_t i = mine.size(); i < found->second.size(); ++i)
                    kept.push_back(found->second[i]);
                found->second = std::move(kept);
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

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId))
            return;
        Channel channel;
        channel.spellId = spellId;
        channel.warmup = Tune("strafe_rocket_warmup_seconds") * 1000.0;
        // The first shot fires with the cast.
        if (!Shoot(player, channel))
        {
            player->InterruptSpell(CURRENT_CHANNELED_SPELL);
            return;
        }
        if (RuneAt(spellId) == Rune::IcyTrail)
            DropPatch(player, channel);
        KeepSlow(player, spellId);
        std::lock_guard<std::mutex> guard(mutex);
        channels[player->GetGUID().GetRawValue()] = channel;
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        // "Throw out knives rather than arrows that deal an extra {damage_bonus_pct} damage on Critical Hits": a strike
        // of its own worth that share of the shot.
        if (!player || !target || !critical || adding || RuneAt(spellId) != Rune::StingingSteel)
            return;
        Scope scope(adding);
        double const shot = RapidFire::ShotPct(Total(spellId), ShotsPer(spellId));
        Combat::Strike(player, target, spellId, CritExtraPct(shot, Numbers::Num(spellId, "damage_bonus_pct")));
    }

    void RegisterScripts()
    {
        new Channels();
    }
} // namespace DC::Combat::DemonHunter::Strafe
