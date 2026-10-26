/*
 * Chakram and its five runes. The chakram is the engine's line throw (a spell record and the sheet's numbers) that hits
 * every enemy along its path; here: Twin Chakrams' second chakram on the same path, and Shuriken Cloud, which is no
 * throw at all: a cloud round the Demon Hunter that ticks on the enemies near them until its minutes are up. The shapes
 * of the paths (the loop, the curve, the spiral) are the engine's line.
 */

#include "dc_demon_hunter_chakram.h"
#include "dc_demon_hunter_common.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Chakram
{
    namespace
    {
        constexpr std::string_view Skill = "Chakram";

        // The second chakram's strike lands too; it must not throw a third.
        thread_local bool throwing = false;

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        struct Cloud
        {
            std::uint32_t spellId = 0;
            std::uint64_t endsAt = 0; // game time, ms
            double clock = 0;         // ms since the last tick
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Cloud> clouds;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        class Clouds final : public PlayerScript
        {
        public:
            Clouds()
                : PlayerScript("dc_demon_hunter_chakram",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Cloud cloud;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = clouds.find(player->GetGUID().GetRawValue());
                    if (found == clouds.end())
                        return;
                    cloud = found->second;
                }
                if (!player->IsAlive() || Now() >= cloud.endsAt)
                {
                    Stop(player);
                    return;
                }
                // "dealing {damage_pct} weapon damage per second as Physical to nearby enemies": a tick every half
                // second carries that share, on every enemy within the cloud's area.
                double const tick = Tune("chakram_cloud_tick_seconds");
                unsigned const ticks = Due(cloud.clock, diff, tick * 1000.0);
                double const pct = CloudTickPct(Numbers::Num(cloud.spellId, "damage_pct"), tick);
                for (unsigned i = 0; i < ticks; ++i)
                    for (Unit* enemy : Combat::Enemies(player, cloud.spellId, player->GetPosition(),
                                                       Tune("chakram_cloud_radius_yards")))
                        Combat::Strike(player, enemy, cloud.spellId, pct);
                std::lock_guard<std::mutex> guard(mutex);
                if (auto found = clouds.find(player->GetGUID().GetRawValue()); found != clouds.end())
                    found->second.clock = cloud.clock;
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
                clouds.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The cloud throws nothing; every other rune's path hit is its own sheet damage (the loader's rule).
        return RuneAt(spellId) == Rune::ShurikenCloud ? std::optional<double>(0.0) : std::nullopt;
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        // "A second Chakram mirrors the first. Each Chakram deals {damage_pct} weapon damage as Fire": the second flies
        // the same line, so each enemy on it takes the hit twice.
        if (throwing || !player || !target || RuneAt(spellId) != Rune::TwinChakrams)
            return;
        Scope scope(throwing);
        Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct"));
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || RuneAt(spellId) != Rune::ShurikenCloud)
            return;
        // "Lasts {duration_minutes} minutes"; the power file gives the rune its own cooldown.
        Cloud cloud;
        cloud.spellId = spellId;
        cloud.endsAt = CloudEndsAt(Now(), Numbers::Num(spellId, "duration_minutes"));
        {
            std::lock_guard<std::mutex> guard(mutex);
            clouds[player->GetGUID().GetRawValue()] = cloud;
        }
        player->AddSpellCooldown(spellId, 0, std::uint32_t(Tune("chakram_cloud_cooldown_seconds") * 1000.0), true);
    }

    void RegisterScripts()
    {
        new Clouds();
    }
} // namespace DC::Combat::DemonHunter::Chakram
