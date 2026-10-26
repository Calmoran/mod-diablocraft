/*
 * Vengeance and its five runes. The cast is the engine's self spell (a record and the sheet's numbers) that does no
 * damage; here: the form that lasts its seconds, the damage it adds to every hit, and, on every attack that connects,
 * the side guns' piercing shots and the second weapon (the homing rockets, or a rune's shadow allies, grenades or none,
 * the guns becoming cannons), Dark Heart's damage reduction and Seethe's Hatred.
 */

#include "dc_demon_hunter_vengeance.h"
#include "dc_demon_hunter_clock.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_hatred.h"
#include "dc_demon_hunter_passives.h"
#include "dc_demon_hunter_seek.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Unit.h"
#include "Util.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Vengeance
{
    namespace
    {
        constexpr std::string_view Skill = "Vengeance";
        constexpr double Pi = 3.14159265358979323846;

        // The strikes of the guns and the second weapon land through the engine's hooks too; they are no attack of
        // their own.
        thread_local bool firing = false;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        struct Form
        {
            std::uint32_t spellId = 0;
            std::uint64_t endsAt = 0;     // game time, ms
            std::uint64_t lastGuns = 0;   // when the guns last fired
            std::uint64_t lastVolley = 0; // when the second weapon last fired
            double seethe = 0;            // ms since Seethe last paid
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Form> forms;
        // From the Shadows freezes an enemy once in its cooldown: when each enemy may be frozen again, for each Demon
        // Hunter.
        std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, std::uint64_t>> frozen;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::optional<Form> Active(Player* player)
        {
            if (!player)
                return std::nullopt;
            std::lock_guard<std::mutex> guard(mutex);
            auto found = forms.find(player->GetGUID().GetRawValue());
            if (found == forms.end() || Now() >= found->second.endsAt)
                return std::nullopt;
            return found->second;
        }

        void Stamp(Player* player, std::uint64_t Form::*field, std::uint64_t now)
        {
            std::lock_guard<std::mutex> guard(mutex);
            if (auto found = forms.find(player->GetGUID().GetRawValue()); found != forms.end())
                found->second.*field = now;
        }

        std::vector<double> DistancesOf(Player* player, std::vector<Unit*> const& enemies)
        {
            std::vector<double> distances;
            for (Unit* enemy : enemies)
                distances.push_back(player->GetExactDist(enemy));
            return distances;
        }

        // The side guns: each fires a piercing shot along a line from beside the Demon Hunter, toward the enemy aimed
        // at, with the file's spread; Side Cannons' heavier shots heal for each enemy they hit.
        void FireGuns(Player* player, Form const& form, Rune rune)
        {
            double const range = Tune("vengeance_split_shot_range_yards");
            auto const enemies = Combat::Enemies(player, form.spellId, player->GetPosition(), range);
            if (enemies.empty())
                return;
            Unit* aimed = player->GetSelectedUnit();
            if (!aimed || std::find(enemies.begin(), enemies.end(), aimed) == enemies.end())
            {
                aimed = enemies.front();
                for (Unit* enemy : enemies)
                    if (player->GetExactDist(enemy) < player->GetExactDist(aimed))
                        aimed = enemy;
            }
            bool const cannons = rune == Rune::SideCannons;
            unsigned const count =
                GunCount(rune, Numbers::Num(form.spellId, "projectile_count", "side_guns"),
                         Tune("vengeance_split_shot_multiplier"), Tune("vengeance_side_cannon_multiplier"));
            double const pct = cannons ? Numbers::Num(form.spellId, "damage_pct")
                                       : Numbers::Num(form.spellId, "damage_pct", "side_guns");
            double const aim = player->GetAngle(aimed), offset = Tune("vengeance_split_shot_offset_yards"),
                         width = Tune("vengeance_split_shot_width_yards");
            for (unsigned shot = 0; shot < count; ++shot)
            {
                // The guns sit one each side in turn.
                double const side = shot % 2 == 0 ? Pi / 2 : -Pi / 2;
                double const originX = player->GetPositionX() + std::cos(aim + side) * offset,
                             originY = player->GetPositionY() + std::sin(aim + side) * offset;
                double const heading = aim + Spread(Tune("vengeance_split_shot_spread_min_degrees"),
                                                    Tune("vengeance_split_shot_spread_degrees"), frand(0.0f, 1.0f)) *
                                                 Pi / 180.0;
                for (Unit* enemy : enemies)
                    if (OnLine(enemy->GetPositionX() - originX, enemy->GetPositionY() - originY, heading, range,
                               width) &&
                        Combat::Strike(player, enemy, form.spellId, pct) && cannons)
                        Heal(player, form.spellId,
                             player->GetMaxHealth() * Numbers::Num(form.spellId, "heal_pct") / 100.0);
            }
        }

        // Homing Rockets: each rocket homes on the nearest enemy not yet taken, within the file's search radius.
        void FireRockets(Player* player, Form const& form)
        {
            auto const enemies =
                Combat::Enemies(player, form.spellId, player->GetPosition(), Tune("vengeance_missile_search_yards"));
            for (std::size_t index : Nearest(DistancesOf(player, enemies), Tune("vengeance_missile_search_yards"),
                                             unsigned(Numbers::Num(form.spellId, "projectile_count", "rockets"))))
                Combat::Strike(player, enemies[index], form.spellId,
                               Numbers::Num(form.spellId, "damage_pct", "rockets") * Passive::RocketFactor(player));
        }

        // From the Shadows: instead of the rockets an ally comes out of the shadows beside each enemy picked, within
        // the file's radius, and strikes it, freezing it unless it was frozen within the cooldown.
        void SummonAllies(Player* player, Form const& form)
        {
            double const within = Tune("vengeance_shadow_ally_range_yards");
            auto const enemies = Combat::Enemies(player, form.spellId, player->GetPosition(), within);
            std::uint64_t const now = Now();
            for (std::size_t index : Nearest(DistancesOf(player, enemies), within,
                                             unsigned(Numbers::Num(form.spellId, "projectile_count", "rockets"))))
            {
                Unit* enemy = enemies[index];
                if (!Combat::Strike(player, enemy, form.spellId, Numbers::Num(form.spellId, "damage_pct")))
                    continue;
                bool freeze = false;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    std::uint64_t& readyAt = frozen[player->GetGUID().GetRawValue()][enemy->GetGUID().GetRawValue()];
                    freeze = FreezeReady(readyAt, now);
                    if (freeze)
                        readyAt = now + std::uint64_t(Tune("vengeance_shadow_ally_freeze_cooldown_seconds") * 1000.0);
                }
                if (freeze)
                    Stun(player, enemy,
                         Numbers::Num(form.spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));
            }
        }

        // Personal Mortar: instead of the rockets, grenades at random enemies outside melee range, each bursting over
        // the enemy it fell on.
        void LaunchGrenades(Player* player, Form const& form)
        {
            auto const enemies =
                Combat::Enemies(player, form.spellId, player->GetPosition(), Tune("vengeance_mortar_max_range_yards"));
            auto const band = InBand(DistancesOf(player, enemies), Tune("vengeance_mortar_min_range_yards"),
                                     Tune("vengeance_mortar_max_range_yards"));
            if (band.empty())
                return;
            for (unsigned grenade = 0, count = unsigned(Numbers::Num(form.spellId, "projectile_count"));
                 grenade < count; ++grenade)
            {
                Unit* fell = enemies[band[urand(0, uint32(band.size() - 1))]];
                for (Unit* enemy :
                     Combat::Enemies(player, form.spellId, fell->GetPosition(),
                                     Passive::GrenadeRadius(player, form.spellId, Tune("vengeance_mortar_radius_yards"))))
                    Combat::Strike(player, enemy, form.spellId, Numbers::Num(form.spellId, "damage_pct"));
            }
        }

        class Forms final : public PlayerScript
        {
        public:
            Forms()
                : PlayerScript("dc_demon_hunter_vengeance",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Form form;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = forms.find(player->GetGUID().GetRawValue());
                    if (found == forms.end())
                        return;
                    form = found->second;
                }
                if (!player->IsAlive() || Now() >= form.endsAt)
                {
                    Stop(player);
                    return;
                }
                // Seethe: "Gain {regen_per_second_resource} Hatred per second", a tick at a time.
                if (RuneAt(form.spellId) == Rune::Seethe)
                {
                    double const tick = Tune("vengeance_seethe_tick_seconds");
                    unsigned const ticks = Due(form.seethe, diff, tick * 1000.0);
                    double const points = SeethePerTick(Numbers::Num(form.spellId, "regen_per_second_resource"), tick);
                    for (unsigned i = 0; i < ticks; ++i)
                        Generate(player, Classes::ClassIdOf(player), form.spellId, points);
                    std::lock_guard<std::mutex> guard(mutex);
                    if (auto found = forms.find(player->GetGUID().GetRawValue()); found != forms.end())
                        found->second.seethe = form.seethe;
                }
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
                forms.erase(player->GetGUID().GetRawValue());
                frozen.erase(player->GetGUID().GetRawValue());
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

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return;
        // "Turn into the physical embodiment of Vengeance for {duration_seconds} seconds."
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        Form form;
        form.spellId = spellId;
        form.endsAt = Now() + std::uint64_t(seconds > 0 ? seconds * 1000.0 : 0.0);
        {
            std::lock_guard<std::mutex> guard(mutex);
            forms[player->GetGUID().GetRawValue()] = form;
            frozen.erase(player->GetGUID().GetRawValue());
        }
        // Dark Heart: "reducing all damage taken by {damage_reduction_pct}".
        if (RuneAt(spellId) == Rune::DarkHeart)
            Buffs::Stack(player, spellId, Stat::SpecificReduction, Bucket::Flat,
                         Numbers::Num(spellId, "damage_reduction_pct"), 1, seconds);
    }

    void Attack(Player* player, std::uint32_t spellId)
    {
        if (firing || !player || Is(spellId))
            return;
        auto form = Active(player);
        if (!form)
            return;
        Scope scope(firing);
        Rune const rune = RuneAt(form->spellId);
        double const attacks = Combat::AttacksPerSecond(player, form->spellId);
        std::uint64_t const now = Now();
        // "Gain {projectile_count:side_guns} additional piercing shots ... on every attack."
        if (Ready(form->lastGuns, now, GunCooldownSeconds(Tune("vengeance_split_shot_cooldown_attacks"), attacks)))
        {
            Stamp(player, &Form::lastGuns, now);
            FireGuns(player, *form, rune);
        }
        // The second weapon, one volley for each attack: the rockets, or the rune's instead (Side Cannons has none).
        if (rune != Rune::SideCannons && Ready(form->lastVolley, now, VolleySeconds(attacks)))
        {
            Stamp(player, &Form::lastVolley, now);
            if (rune == Rune::FromTheShadows)
                SummonAllies(player, *form);
            else if (rune == Rune::PersonalMortar)
                LaunchGrenades(player, *form);
            else
                FireRockets(player, *form);
        }
    }

    void Multipliers(Player* player, DC::Combat::Factors& out)
    {
        // "Vengeance: Gain {damage_bonus_pct} increased damage."
        if (auto form = Active(player))
            AddFactor(out, "Vengeance", Numbers::Num(form->spellId, "damage_bonus_pct"));
    }

    void RegisterScripts()
    {
        new Forms();
    }
} // namespace DC::Combat::DemonHunter::Vengeance
