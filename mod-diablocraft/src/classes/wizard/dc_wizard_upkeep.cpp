#include "dc_wizard_upkeep.h"
#include "dc_wizard_buffs.h"
#include "dc_wizard_frost_nova.h"
#include "dc_wizard_armors.h"
#include "dc_wizard_passives.h"
#include "dc_wizard_slow_time.h"
#include "dc_wizard_spectral_blade.h"
#include "dc_wizard_teleport.h"
#include "../../combat/dc_item_powers.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "ScriptMgr.h"
#include <algorithm>

namespace DC::Combat::Wizard::Upkeep
{
    using namespace Shared;

    namespace
    {
        class World final : public WorldScript
        {
        public:
            World()
                : WorldScript("dc_wizard_tuning", {WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_AFTER_CONFIG_LOAD})
            {
            }

            void OnAfterConfigLoad(bool reload) override
            {
                if (reload)
                    OnStartup();
            }

            void OnStartup() override
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                tuning.clear();
                if (auto rows = WorldDatabase.Query("SELECT name,tuned_value FROM dc_ability_tuning"))
                    do
                    {
                        auto field = rows->Fetch();
                        tuning[field[0].Get<std::string>()] = field[1].Get<double>();
                    } while (rows->NextRow());
                else
                    LOG_ERROR("server", "Missing dc_ability_tuning; the Wizard's placeholders read zero");
            }
        };

        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_wizard_update", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT,
                                                    PLAYERHOOK_ON_MAP_CHANGED, PLAYERHOOK_ON_CREATURE_KILL})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (player->getClass() != CLASS_MAGE)
                    return;
                uint64 const now = Now();
                std::vector<Timer> due;
                bool refresh = false;
                {
                    std::lock_guard<std::recursive_mutex> guard(mutex);
                    State& state = StateOf(player);
                    for (auto it = state.timers.begin(); it != state.timers.end();)
                        if (it->at <= now)
                        {
                            due.push_back(std::move(*it));
                            it = state.timers.erase(it);
                        }
                        else
                            ++it;
                    // Unwavering Will: "Standing still for {duration_seconds}".
                    if (player->GetExactDist(&state.lastPosition) > 0.1f)
                        state.still = 0;
                    else
                        state.still += diff;
                    state.lastPosition = player->GetPosition();
                    if (now >= state.refreshAt)
                    {
                        state.refreshAt = now + 250;
                        refresh = true;
                    }
                }
                SpectralBlade::SyncFlameBlades(player);
                if (player->IsAlive())
                    for (Timer& timer : due)
                        timer.run(player);
                else
                    Teleport::ReversalEnd(player);
                if (!refresh)
                    return;
                // Crown of the Primus: Slow Time follows only while the hat is worn.
                if (SlowTime::Following(player) && ItemPowers::SkillSetTo(player, "Slow Time", "follow_caster", 0) <= 0)
                    SlowTime::RemoveFollow(player);
                Passive::Evocation(player);
                Passive::GalvanizingWard(player, now);
                Armors::ChillingAura(player, now);
                Buffs::Refresh(player);
            }

            void OnPlayerCreatureKill(Player* player, Creature* killed) override
            {
                if (!player || !killed || player->getClass() != CLASS_MAGE)
                    return;
                bool frozen = false;
                {
                    std::lock_guard<std::recursive_mutex> guard(mutex);
                    State& state = StateOf(player);
                    // "Each enemy killed while in Archon form increases your
                    // damage" (wizard.js:1017-1021).
                    if (BuffOf(player, "Archon"))
                        ++state.archonStacks;
                    frozen = FrozenMark(player, killed);
                    state.marks.erase(killed->GetGUID().GetRawValue());
                }
                Passive::Dominance(player);
                if (frozen)
                    FrostNova::Shatter(player, killed);
            }

            void OnPlayerLogout(Player* player) override
            {
                SlowTime::RemoveFollow(player);
                Teleport::ReversalEnd(player);
                Clear(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                SlowTime::RemoveFollow(player);
                Teleport::ReversalEnd(player);
                ClearSummons(player);
                std::lock_guard<std::recursive_mutex> guard(mutex);
                StateOf(player).timers.clear();
                StateOf(player).marks.clear();
            }

        private:
            static void Clear(Player* player)
            {
                ClearSummons(player);
                std::lock_guard<std::recursive_mutex> guard(mutex);
                states.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new World();
        new Update();
    }
} // namespace DC::Combat::Wizard::Upkeep
