/*
 * World of DiabloCraft - mod-diablocraft
 *
 * Module entry point. The core's generated ModulesLoader.cpp forward-declares
 * and calls Addmod_diablocraftScripts(); the name is derived from the module
 * directory name and must not change.
 */

#include "Log.h"
#include "ScriptMgr.h"
#include "classes/dc_classes.h"
#include "combat/dc_combat.h"
#include "items/dc_inventory.h"
#include "items/dc_items.h"
#include "items/dc_identify.h"
#include "items/dc_stash.h"
#include "loot/dc_loot.h"
#include "rifts/dc_orb_pick.h"
#include "rifts/dc_rifts.h"
#include "bounties/dc_bounties.h"
#include "campaign/dc_campaign.h"
#include "stats/dc_stats.h"
#include "difficulty/dc_difficulty.h"
#include "common/dc_bridge.h"
#include "common/dc_lua_error_drop.h"
#include "common/dc_tunables.h"
#include "common/dc_version.h"
#include "common/dc_world_areas.h"
#include "common/dc_world.h"
#include "common/dc_economy.h"
#include "crafting/dc_crafting.h"
#include "hardcore/dc_hardcore.h"
#include "paragon/dc_paragon.h"

namespace
{
    class diablocraft_world : public WorldScript
    {
    public:
        diablocraft_world()
            : WorldScript("diablocraft_world", {WORLDHOOK_ON_STARTUP})
        {
        }

        void OnStartup() override
        {
            LOG_INFO("server.loading", "mod-diablocraft loaded");
        }
    };
} // namespace

void AddSC_diablocraft_world()
{
    new diablocraft_world();
}

void Addmod_diablocraftScripts()
{
    AddSC_diablocraft_world();
    DC::Tunables::RegisterScripts();
    DC::Bridge::RegisterScripts();
    DC::LuaErrorDrop::RegisterScripts();
    DC::Version::RegisterScripts();
    DC::Stats::RegisterScripts();
    DC::Areas::RegisterScripts();
    DC::Difficulty::RegisterScripts();
    DC::Items::RegisterScripts();
    DC::Identify::RegisterScripts();
    DC::Stash::RegisterScripts();
    DC::Inventory::RegisterScripts();
    DC::Combat::RegisterScripts();
    DC::Classes::RegisterScripts();
    DC::Loot::RegisterScripts();
    DC::Rifts::RegisterScripts();
    DC::Bounties::RegisterScripts();
    DC::Campaign::RegisterScripts();
    DC::Hardcore::RegisterScripts();
    DC::World::RegisterScripts();
    DC::OrbPick::RegisterScripts();
    DC::Economy::RegisterScripts();
    DC::Crafting::RegisterScripts();
    DC::Paragon::RegisterScripts();
}
