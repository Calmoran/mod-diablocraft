// World of DiabloCraft - the rifts' core hooks and the `.dc rift` commands, and their registration.

#include "dc_rifts.h"
#include "dc_ally.h"
#include "dc_gr_level.h"
#include "../monsters/dc_family_lineup.h"
#include "dc_gr_open.h"
#include "../monsters/dc_monster_ai.h"
#include "../monsters/affixes/dc_affixes.h"
#include "dc_rift_exit.h"
#include "dc_rift_quests.h"
#include "dc_rift_spawner.h"
#include "dc_rifts_internal.h"
#include "dc_rifts_shared.h"
#include "dc_shatter.h"
#include "dc_open_rift.h"
#include "dc_town_portal.h"

#include "../combat/dc_combat.h"
#include "../difficulty/dc_difficulty.h"
#include "../loot/dc_loot.h"
#include "../paragon/dc_paragon.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_world.h"
#include "../common/dc_tunables.h"
#include "../classes/dc_classes.h"

#include "Chat.h"
#include "CombatAI.h"
#include "Creature.h"
#include "GameObjectAI.h"
#include "PassiveAI.h"
#include "ScriptedCreature.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "ThreatManager.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "GameTime.h"
#include "Group.h"
#include "InstanceSaveMgr.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "GridNotifiers.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerEconomy.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "World.h"
#include "WorldSession.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cctype>
#include <cmath>
#include <functional>
#include <list>
#include <memory>
#include <mutex>
#include <random>
#include <sstream>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Rifts
{
    // The AI the core asks. Nothing else is overridden: for the obelisk it must not
    // change a questgiver's behaviour, and for the rest there is no behaviour.
    class RiftHubObjectAI final : public GameObjectAI
    {
    public:
        RiftHubObjectAI(GameObject* go, std::uint64_t run, ObjectGuid owner)
            : GameObjectAI(go)
            , _run(run)
            , _owner(owner)
        {
        }
        bool CanBeSeen(Player const* seer) override
        {
            return CanSeeHubObject(me, _run, _owner, seer);
        }

    private:
        std::uint64_t _run;
        ObjectGuid _owner;
    };

    // The trigger stalker's. NullCreatureAI so it does nothing at all, which is what
    // an invisible one-second stalker should do; the only reason it has an AI is to
    // answer this question. Getting the answer right is what makes the EXPLOSION
    // private too: SMSG_SPELL_GO is delivered only to players who already hold the
    // caster (Spell.cpp:4960 -> MessageDistDeliverer over the visible-players map),
    // so a stalker only the party can see casts a spell only the party can see.
    class RiftHubTriggerAI final : public NullCreatureAI
    {
    public:
        RiftHubTriggerAI(Creature* creature, std::uint64_t run, ObjectGuid owner)
            : NullCreatureAI(creature)
            , _run(run)
            , _owner(owner)
        {
        }
        bool CanBeSeen(Player const* seer) override
        {
            return CanSeeHubObject(nullptr, _run, _owner, seer);
        }

    private:
        std::uint64_t _run;
        ObjectGuid _owner;
    };

    class RiftWorld final : public WorldScript
    {
    public:
        RiftWorld()
            : WorldScript("dc_rift_world", {WORLDHOOK_ON_STARTUP})
        {
        }
        void OnStartup() override
        {
            try
            {
                std::vector<Dungeon> loaded;
                QueryResult result = WorldDatabase.Query(
                    "SELECT dungeon_id, map_id, name, entry_x, entry_y, entry_z, entry_o "
                    "FROM dc_rift_dungeon ORDER BY dungeon_id");
                if (!result)
                    throw std::runtime_error("dc_rift_dungeon is missing; apply rifts_0001_dungeon_pool.sql");
                do
                {
                    Field* f = result->Fetch();
                    Dungeon dungeon;
                    dungeon.dungeonId = f[0].Get<int32>();
                    dungeon.mapId = f[1].Get<int32>();
                    dungeon.name = f[2].Get<std::string>();
                    dungeon.x = static_cast<float>(f[3].Get<double>());
                    dungeon.y = static_cast<float>(f[4].Get<double>());
                    dungeon.z = static_cast<float>(f[5].Get<double>());
                    dungeon.o = static_cast<float>(f[6].Get<double>());
                    loaded.push_back(dungeon);
                } while (result->NextRow());

                // F5 stage 1: the three chosen guardians, on the WoW creatures
                // and abilities rift_guardian_models.csv maps them to. The ids used
                // to be written out here by hand and two of the three were wrong.
                std::vector<Guardian> loadedGuardians;
                QueryResult guardianRows = WorldDatabase.Query(
                    "SELECT guardian, creature_id, ability_1, ability_1_shell, ability_1_behaviour, "
                    "ability_2, ability_2_shell, ability_2_behaviour FROM dc_rift_guardian ORDER BY guardian");
                if (!guardianRows)
                    throw std::runtime_error("dc_rift_guardian is missing; apply rifts_0004_guardians.sql");
                do
                {
                    Field* f = guardianRows->Fetch();
                    Guardian guardian;
                    guardian.name = f[0].Get<std::string>();
                    guardian.creatureId = f[1].Get<int32>();
                    guardian.abilities[0] = {f[2].Get<std::string>(), f[4].Get<std::string>(),
                                             static_cast<std::uint32_t>(f[3].Get<int32>())};
                    guardian.abilities[1] = {f[5].Get<std::string>(), f[7].Get<std::string>(),
                                             static_cast<std::uint32_t>(f[6].Get<int32>())};
                    if (!sObjectMgr->GetCreatureTemplate(guardian.creatureId))
                    {
                        LOG_ERROR("server", "[DC rifts] guardian model {} ({}) is not in creature_template",
                                  guardian.name, guardian.creatureId);
                        continue;
                    }
                    for (Ability const& ability : guardian.abilities)
                        if (!sSpellMgr->GetSpellInfo(ability.shell))
                            throw std::runtime_error("guardian ability shell " + std::to_string(ability.shell) +
                                                     " is missing; apply combat_0001_spell_shells.sql");
                    loadedGuardians.push_back(guardian);
                } while (guardianRows->NextRow());
                if (loadedGuardians.empty())
                    throw std::runtime_error("no guardian creature templates resolved");

                // The entrance portal pool: seventeen stock city-portal
                // looks, one rolled per rift. Read back rather than compiled in, the
                // same rule the guardians and the quest variants follow, so the ids
                // stay in rift_portals.csv. A row whose template is missing is fatal
                // and not skipped: rolling it would summon nothing and the party would
                // have no way into their own rift.
                std::vector<PortalLook> loadedPortals;
                std::set<std::uint32_t> loadedPortalEntries;
                QueryResult portalRows =
                    WorldDatabase.Query("SELECT entry, display_id, name, scale FROM dc_rift_portal ORDER BY entry");
                if (!portalRows)
                    throw std::runtime_error("dc_rift_portal is missing; apply rifts_0011_rift_quests.sql");
                do
                {
                    Field* f = portalRows->Fetch();
                    PortalLook look;
                    look.entry = static_cast<std::uint32_t>(f[0].Get<int32>());
                    look.display = static_cast<std::uint32_t>(f[1].Get<int32>());
                    look.name = f[2].Get<std::string>();
                    look.scale = static_cast<float>(f[3].Get<double>());
                    if (!sObjectMgr->GetGameObjectTemplate(look.entry))
                        throw std::runtime_error("rift portal " + std::to_string(look.entry) +
                                                 " has no gameobject_template; regenerate rifts_0011");
                    loadedPortals.push_back(look);
                    loadedPortalEntries.insert(look.entry);
                } while (portalRows->NextRow());

                // 09 §2 step 2. Every affix goes in the pool; only four do anything
                // in stage 1, and behaviour is what says which.
                std::vector<Affix> loadedAffixes;
                QueryResult affixRows = WorldDatabase.Query(
                    "SELECT affix_name, appears_on, min_tier, min_hero_level, element, behaviour, shell_spell, "
                    "pool, level_60_limited, rollable, minion_inherits "
                    "FROM dc_rift_affix ORDER BY affix_name");
                if (!affixRows)
                    throw std::runtime_error("dc_rift_affix is missing or predates the roll columns; "
                                             "apply rifts_0003_elite_affixes.sql");
                do
                {
                    Field* f = affixRows->Fetch();
                    Affix affix;
                    affix.name = f[0].Get<std::string>();
                    affix.appearsOn = f[1].Get<std::string>();
                    affix.minTier = static_cast<unsigned>(f[2].Get<int32>());
                    affix.minLevel = static_cast<unsigned>(f[3].Get<int32>());
                    affix.element = f[4].Get<std::string>();
                    affix.behaviour = f[5].Get<std::string>();
                    affix.shell = static_cast<std::uint32_t>(f[6].Get<int32>());
                    affix.pool = f[7].Get<std::string>();
                    affix.levelLimited = f[8].Get<int32>() != 0;
                    affix.rollable = f[9].Get<int32>() != 0;
                    // Whether an affix is in the roll pool is ours - an engine
                    // feasibility switch - while its pool membership is D3's
                    // (elite_affix_pools.csv). A tunables row therefore wins over
                    // the generated column where one exists, so Missile Dampening
                    // goes back in the pool with `.dc tunables set affixes
                    // missile_dampening_rollable 1` the day 3.3.5a can carry it.
                    std::string key;
                    for (unsigned char c : affix.name)
                        key += std::isalnum(c) ? static_cast<char>(std::tolower(c)) : '_';
                    key += "_rollable";
                    if (DC::Tunables::Has("affixes", key))
                        affix.rollable = DC::Tunables::Get("affixes", key) != 0;
                    affix.minionInherits = f[10].Get<int32>() != 0;
                    if (affix.shell && !sSpellMgr->GetSpellInfo(affix.shell))
                        throw std::runtime_error("affix shell " + std::to_string(affix.shell) + " is missing");
                    loadedAffixes.push_back(affix);
                } while (affixRows->NextRow());

                // 13-elite-affixes §2. Loaded before the pool is published, so no
                // pack can ever be promoted against a half-built number set.
                std::string tunableError;
                if (!ReloadAffixNumbers(tunableError))
                    throw std::runtime_error(tunableError);

                std::vector<std::pair<unsigned, unsigned>> loadedCounts;
                QueryResult countRows = WorldDatabase.Query(
                    "SELECT hero_level_max, affixes_per_pack FROM dc_elite_affix_count ORDER BY hero_level_max");
                if (!countRows)
                    throw std::runtime_error("dc_elite_affix_count is missing");
                do
                {
                    Field* f = countRows->Fetch();
                    loadedCounts.emplace_back(static_cast<unsigned>(f[0].Get<int64>()),
                                              static_cast<unsigned>(f[1].Get<int64>()));
                } while (countRows->NextRow());

                // The promotion rate lives beside the other loot tunables. It is
                // added to the generated table by rifts_0005_elite_promotion.sql, so
                // a regenerated dc_loot_tuning can take it away again; that is a
                // missing column and no promotion, not a failed startup.
                double promotion = 0;
                if (QueryResult rate =
                        WorldDatabase.Query("SELECT elite_promotion_pct FROM dc_loot_tuning WHERE source='elite'"))
                    promotion = (*rate)[0].Get<double>();
                else
                    LOG_WARN("server", "[DC rifts] dc_loot_tuning has no elite_promotion_pct; "
                                       "rift packs will not be promoted. Apply rifts_0005_elite_promotion.sql.");

                // 03 §5 scale tunables, beside the promotion rate. Same rule: a
                // regenerated dc_loot_tuning that drops the columns leaves the
                // elites unscaled, which is a look regression and not a failure.
                double champion = 1.0, rare = 1.0, minion = 1.0;
                if (QueryResult scales =
                        WorldDatabase.Query("SELECT elite_scale_champion, elite_scale_rare, elite_scale_minion "
                                            "FROM dc_loot_tuning WHERE source='elite'"))
                {
                    Field* f = scales->Fetch();
                    champion = f[0].Get<double>();
                    rare = f[1].Get<double>();
                    minion = f[2].Get<double>();
                }
                else
                    LOG_WARN("server", "[DC rifts] dc_loot_tuning has no elite scale columns; "
                                       "promoted packs keep their native size.");

                // Same rule again: the column is the only home for
                // the pack size, so a table without it leaves the number unset
                // rather than repeating the 3 the table itself carries.
                unsigned packSize = 0;
                if (QueryResult pack =
                        WorldDatabase.Query("SELECT champion_pack_size FROM dc_loot_tuning WHERE source='elite'"))
                    packSize = std::max<unsigned>(1, (*pack)[0].Get<uint32>());
                else
                    LOG_WARN("server", "[DC rifts] dc_loot_tuning has no champion_pack_size; "
                                       "a promoted champion spawns alone. Apply "
                                       "rifts_0009_champion_pack.sql.");

                // 7.3, since monster-spawning S3 one quest per mode, read back rather than compiled in. The
                // Nephalem row is the untimed one; the Greater row exists in the same table, so TimeAllowed
                // tells them apart. Each carries the whole bar as its count (65,000 hundredths of a point).
                auto const loadBar = [&](bool timed, char const* what)
                {
                    BarQuest bar;
                    QueryResult rows = WorldDatabase.Query(
                        "SELECT ID, RequiredNpcOrGoCount1 FROM quest_template "
                        "WHERE RequiredNpcOrGo1={} AND TimeAllowed{} ORDER BY ID",
                        CREDIT_CREATURE, timed ? ">0" : "=0");
                    if (!rows)
                        throw std::runtime_error(std::string("the ") + what +
                                                 " rift quest template is missing; apply rifts_0011_rift_quests.sql and rifts_0019_one_bar.sql");
                    bar.id = (*rows)[0].Get<uint32>();
                    bar.units = (*rows)[1].Get<uint32>();
                    if (rows->GetRowCount() != 1 || !bar.units || bar.units > 65535)
                        throw std::runtime_error(std::string("the ") + what +
                                                 " rift quests are not one row inside the quest counter (65,535); apply rifts_0019_one_bar.sql");
                    return bar;
                };
                BarQuest const loadedQuest = loadBar(false, "Nephalem");
                BarQuest const loadedGreater = loadBar(true, "Greater");
                std::string progressError;
                if (!LoadMonsterProgress(progressError))
                    throw std::runtime_error(progressError);

                // Every template, Greater ones too. Only the Nephalem map above
                // decides what the obelisk OFFERS; this set decides what the sweep,
                // the no-abandon rule and the XP zeroing recognise, and a Greater
                // quest that reached a log has to be cleanable before Phase B.
                std::set<std::uint32_t> loadedAllQuests;
                if (QueryResult allRows =
                        WorldDatabase.Query("SELECT ID FROM quest_template WHERE RequiredNpcOrGo1={}", CREDIT_CREATURE))
                    do
                    {
                        loadedAllQuests.insert((*allRows)[0].Get<uint32>());
                    } while (allRows->NextRow());
                loadedAllQuests.insert(loadedQuest.id);
                loadedAllQuests.insert(loadedGreater.id);

                // ProjectProgress, CompleteRunQuests,
                // RemoveRunQuests and PayClosingReward write quest state and send
                // packets to players on OTHER maps, driven from the instance map's
                // update. That is only safe while the world runs one map thread.
                // It is a latent race, not a live one, and this makes the assumption
                // explicit instead of silent. The proper fix - queue per-player
                // actions and drain them on each player's own map, the pattern this
                // file already uses for elite affix work - is a separate follow-up.
                if (sWorld->getIntConfig(CONFIG_NUMTHREADS) != 1)
                    LOG_ERROR("server",
                              "[DC rifts] MapUpdate.Threads is {}, not 1. Rift quest projection "
                              "touches players on other maps from the instance map's update and is "
                              "only thread-safe at 1. See review item 10, 2026-09-17.",
                              sWorld->getIntConfig(CONFIG_NUMTHREADS));

                if (!CharacterDatabase.Query("SELECT COUNT(party_size) FROM dc_rift"))
                    throw std::runtime_error("dc_rift migration has not been applied");
                if (!CharacterDatabase.Query("SELECT COUNT(progress) FROM dc_rift"))
                    throw std::runtime_error(
                        "dc_rift is missing its Phase A columns; apply rifts_0005_rift_quests.sql");
                if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_rift_member"))
                    throw std::runtime_error("dc_rift_member is missing; apply rifts_0005_rift_quests.sql");
                if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_rift_elite"))
                    throw std::runtime_error("dc_rift_elite migration has not been applied");
                if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_character_gr"))
                    throw std::runtime_error("dc_character_gr is missing; apply rifts_0007_greater_rift_level.sql");
                // Both columns are written by RecordGreaterRiftBeaten's callers; without them the write fails
                // and the whole unlock (unlocked and beaten too) is lost.
                if (!CharacterDatabase.Query("SELECT COUNT(time_left) FROM dc_rift"))
                    throw std::runtime_error("dc_rift.time_left is missing; apply rifts_0008_gr_time_left.sql");
                if (!CharacterDatabase.Query("SELECT COUNT(beaten_solo) FROM dc_character_gr"))
                    throw std::runtime_error(
                        "dc_character_gr.beaten_solo is missing; apply rifts_0009_gr_beaten_solo.sql");
                // Every new run records its floor 1 here (rift floors Part F1); a missing table would fail each open.
                if (!CharacterDatabase.Query("SELECT COUNT(*) FROM dc_rift_floor"))
                    throw std::runtime_error("dc_rift_floor is missing; apply rifts_0011_rift_floor.sql");
                // A rift cannot survive a restart: the instances are gone with it.
                CharacterDatabase.Execute("UPDATE dc_rift SET state='closed' WHERE state<>'closed'");
                CharacterDatabase.Execute("UPDATE dc_rift_floor SET closed_at=NOW() WHERE closed_at IS NULL");
                // ... so nobody is enrolled in one either. The login sweep deletes
                // the stale quest from each character as they come back (7.5).
                CharacterDatabase.Execute(
                    "UPDATE dc_rift_member SET state='detached', departure_reason='closed' WHERE state<>'detached'");
                // ... and neither do the packs that were standing in one.
                CharacterDatabase.Execute("DELETE FROM dc_rift_elite");

                // MIGRATION SAFETY NET, and nothing else any more.
                //
                // Formerly the obelisk was hidden by despawning it with a
                // twelve-hour respawn, which persisted as a `gameobject_respawn` row in
                // the characters database when the hub grid unloaded; if a rift was
                // open when that build was stopped, the row is still there and
                // Map::LoadRespawnTimes would read it back and strand the hub obelisk
                // for twelve hours. The new mechanism never writes such a row - the
                // obelisk is hidden per-seer and stays spawned - so nothing here
                // CREATES work for this to undo.
                //
                // It can be deleted once every characters database this code runs
                // against has started at least once under the new mechanism: after
                // that first clean startup there is no row left for it to find, and
                // there is no longer any code that could write one.
                //
                // Synchronous on purpose - a login can create the hub map immediately -
                // and by spawn id rather than by entry, because gameobject_respawn only
                // knows spawn ids.
                if (QueryResult obeliskRows =
                        WorldDatabase.Query("SELECT guid, map FROM gameobject WHERE id={}", OBELISK_ENTRY))
                {
                    unsigned cleared = 0;
                    do
                    {
                        Field* f = obeliskRows->Fetch();
                        CharacterDatabase.DirectExecute("DELETE FROM gameobject_respawn WHERE guid={} AND mapId={}",
                                                        f[0].Get<uint32>(), f[1].Get<uint16>());
                        ++cleared;
                    } while (obeliskRows->NextRow());
                    LOG_INFO("server.loading",
                             "[DC rifts] migration safety net: cleared any saved respawn for {} hub obelisk "
                             "spawn(s). The obelisk is hidden per-seer now and never despawned, so nothing "
                             "writes these rows any more",
                             cleared);
                }
                else
                    LOG_ERROR("server",
                              "[DC rifts] no gameobject rows for obelisk {}; the hub has no rift "
                              "obelisk and the opening sequence has nothing to hide",
                              OBELISK_ENTRY);

                std::lock_guard<std::mutex> lock(dataMutex);
                pool = std::move(loaded);
                portalPool = std::move(loadedPortals);
                portalEntries = std::move(loadedPortalEntries);
                nephalemQuest = loadedQuest;
                greaterQuest = loadedGreater;
                riftQuests = std::move(loadedAllQuests);
                guardians = std::move(loadedGuardians);
                affixPool = std::move(loadedAffixes);
                affixCounts = std::move(loadedCounts);
                elitePromotionPct = promotion;
                championScale = champion;
                rareScale = rare;
                minionScale = minion;
                championPackSize = packSize;
                dataReady = true;
                unsigned implemented = 0, rollable = 0, inherited = 0;
                for (Affix const& affix : affixPool)
                {
                    if (!affix.behaviour.empty())
                        ++implemented;
                    if (affix.rollable)
                        ++rollable;
                    if (affix.minionInherits)
                        ++inherited;
                }
                LOG_INFO("server.loading",
                         "[DC rifts] Loaded the Nephalem quest {} and the Greater quest {} of {} rift templates; "
                         "{} dungeons, {} guardians and {} elite affixes "
                         "({} with a behaviour, {} rollable, {} inherited by minions); "
                         "{} affix tunables; promotion {}%; scale champion x{} rare x{} minion x{}; "
                         "champion pack {}; {} entrance portal looks ({}-{})",
                         nephalemQuest.id, greaterQuest.id, riftQuests.size(), pool.size(), guardians.size(), affixPool.size(),
                         implemented, rollable, inherited, affixNumbers ? affixNumbers->value.size() : 0,
                         elitePromotionPct, championScale, rareScale, minionScale, championPackSize, portalPool.size(),
                         portalPool.empty() ? 0 : portalPool.front().entry,
                         portalPool.empty() ? 0 : portalPool.back().entry);
            }
            catch (std::exception const& error)
            {
                LOG_ERROR("server", "D3 rift startup failed: {}. Rifts are disabled.", error.what());
            }
        }
    };

    class RiftObelisk final : public AllGameObjectScript
    {
    public:
        RiftObelisk()
            : AllGameObjectScript("dc_rift_obelisk")
        {
        }
        bool CanGameObjectGossipHello(Player* player, GameObject* go) override
        {
            if (!go || !player || !player->GetSession())
                return false;
            ChatHandler handler(player->GetSession());
            std::string error;
            Rift rift;
            if (go->GetEntry() == OBELISK_ENTRY)
            {
                OpenObeliskMenu(player, go);
                return true;
            }
            // Not a switch any more: the entrance is one of seventeen pool entries
            // rather than one constant, and which entry a rift rolled is the rift's
            // business, not this hook's.
            if (IsEntrancePortal(go->GetEntry()))
            {
                UseEntrance(player, go);
                return true;
            }
            // Rift floors Part F2: a floor's exit portal, on a template of its own (dc_rift_exit.cpp).
            if (IsExitPortal(go->GetEntry()))
            {
                Exit::Use(player, go);
                return true;
            }
            return false;
        }

        // The obelisk's menu choices. Only the obelisk's own items are ours.
        bool CanGameObjectGossipSelect(Player* player, GameObject* go, uint32 sender, uint32 action) override
        {
            return player && go && go->GetEntry() == OBELISK_ENTRY && ObeliskSelect(player, go, sender, action, nullptr);
        }
        bool CanGameObjectGossipSelectCode(Player* player, GameObject* go, uint32 sender, uint32 action,
                                           char const* code) override
        {
            return player && go && go->GetEntry() == OBELISK_ENTRY && ObeliskSelect(player, go, sender, action, code);
        }

        // 7.9.8. Called by the core from GameObject::Create for EVERY gameobject in
        // the world, so the cheap tests come first and nothing here reads a mutex or
        // the database on the way past a stranger's object.
        GameObjectAI* GetGameObjectAI(GameObject* go) const override
        {
            if (!go)
                return nullptr;
            // Inside a claim: whatever is being created with no spawn id is the
            // claimant's, and the claim window is one summon call, so nothing else can
            // land in it. A grid load inside that window only creates `gameobject`
            // rows, and those all have spawn ids.
            if (claiming.Active() && !go->GetSpawnId())
                return new RiftHubObjectAI(go, claiming.run, claiming.owner);
            // Outside one: the shared hub obelisk, which needs an AI for the whole
            // life of the server because it is hidden from whichever party is running
            // a rift at any moment. Owned by nobody, which is what makes
            // CanSeeHubObject take its obelisk branch.
            if (go->GetEntry() == OBELISK_ENTRY && go->GetSpawnId())
                return new RiftHubObjectAI(go, 0, ObjectGuid::Empty);
            return nullptr;
        }
    };

    // The same injection for the explosion's stalker. Entry 12999 is a STOCK trigger
    // used all over the game, so this must never claim one that is not ours: the claim
    // being live and the creature having no spawn id are both required, and together
    // they are only true for the one creature our own summon call is building.
    class RiftHubCreature final : public AllCreatureScript
    {
    public:
        RiftHubCreature()
            : AllCreatureScript("dc_rift_hub_creature")
        {
        }

        CreatureAI* GetCreatureAI(Creature* creature) const override
        {
            if (!creature || !claiming.Active() || creature->GetSpawnId())
                return nullptr;
            if (creature->GetEntry() != OPEN_TRIGGER_ENTRY)
                return nullptr;
            return new RiftHubTriggerAI(creature, claiming.run, claiming.owner);
        }
    };

    class RiftMap final : public AllMapScript
    {
    public:
        RiftMap()
            : AllMapScript("dc_rift_map", {ALLMAPHOOK_ON_BEFORE_CREATE_INSTANCE_SCRIPT, ALLMAPHOOK_ON_DESTROY_MAP,
                                           ALLMAPHOOK_ON_MAP_UPDATE, ALLMAPHOOK_IS_INSTANCE_LOADED_ON_DEMAND})
        {
        }

        // Core patch 0026: the rift floor being opened, and an open-zone copy (a whole continent),
        // load each grid and navmesh tile as players reach them, as an open-world map does. The stock full preload ran
        // on the world thread inside the quest accept and passed the freeze detector's limit under load. Asked after
        // OnBeforeCreateInstanceScript, which has given the opening rift its instance id.
        bool IsInstanceLoadedOnDemand(Map* map) override
        {
            return (opening && opening->mapId == map->GetId() && opening->instanceId == map->GetInstanceId()) ||
                   IsOpenZoneMap(map->GetId());
        }

        // Rift-owned work stays on its map's thread: closure, spawn promotion
        // and delayed elite blasts. Town portal objects have their own map hook.
        // A `.dc elite` test pack is not in a rift but queues the same delayed work,
        // so the open-world map it stands on drains it too.
        void OnMapUpdate(Map* map, uint32 diff) override
        {
            if (!map)
                return;
            bool const instance = map->IsDungeon() && map->GetInstanceId();
            unsigned tier = 0, players = 0;
            bool const rift = instance && ScalingContext(map, tier, players);
            if (instance)
            {
                DrainClosures(map);
                GreaterTick(map); // the Greater Rift clock and its progress orbs; nothing else's
            }
            else
            {
                // 7.9.8's rubble and portal steps. The HUB map's work, which is where
                // the objects live; the queue is empty on every other open-world map,
                // so this costs one integer compare there.
                DrainOpenings(map, diff);
            }
            // The elite half of this hook lives in dc_rift_elites.cpp behind one
            // entry point. The hook itself has to stay here
            // because DrainClosures above is the run's, not the elites'; this is
            // the call-through, written on this side so the elite file never needs
            // dc_rifts.cpp opened to change what a tick does.
            DrainEliteWork(map, rift, tier);
            // Monster spawning S2: the floor's first update plans and places what stands on it.
            if (rift)
                Spawner::OpenFloor(map, tier);
            // Rift floors Part F2: the floor's exit portal, once, when it opens.
            if (rift)
                Exit::PlaceExit(map);
            // Pylons and shrines P4: a Nephalem floor's objects when it opens, a Greater Rift's on approach.
            if (rift)
                Pylons::Update(map, diff);
        }

    private:
        // The Keeper's countdown belongs to the run, and every floor's map update advances it: the first one past the
        // end takes the entry out and closes the run, and the call-outs reach every floor at once (Announce).
        void AdvanceClosure(Map* map)
        {
            std::uint64_t runId = 0;
            {
                Rift seen;
                std::lock_guard<std::mutex> lock(riftMutex);
                if (!live.View(map->GetInstanceId(), map->GetId(), seen))
                    return;
                runId = seen.id;
            }
            Rift due, announced;
            bool expired = false;
            uint32 announce = 0;
            {
                std::lock_guard<std::mutex> lock(workMutex);
                auto found = pendingCloses.find(runId);
                if (found == pendingCloses.end())
                    return;
                announced = found->second.rift;
                uint32 elapsed = getMSTimeDiff(found->second.started, getMSTime());
                if (elapsed >= RiftCloseMs())
                {
                    due = found->second.rift;
                    pendingCloses.erase(found);
                    expired = true;
                }
                else
                {
                    uint32 remaining = (RiftCloseMs() - elapsed + 999) / 1000;
                    // tunables:rifts: the first mark
                    // called out, and the mark from which every remaining
                    // second is called out.
                    uint32 const firstMark =
                        static_cast<uint32>(DC::Tunables::Get("rifts", "close_announce_first_seconds"));
                    uint32 const finalMark =
                        static_cast<uint32>(DC::Tunables::Get("rifts", "close_announce_final_seconds"));
                    if ((remaining == firstMark || remaining <= finalMark) &&
                        remaining < found->second.announced)
                        announce = remaining;
                    found->second.announced = remaining;
                }
            }
            if (announce)
                Announce(announced, "Rift closes in " + std::to_string(announce) + " seconds.");
            if (expired)
                QueueClose(due);
        }

        void DrainClosures(Map* map)
        {
            AdvanceClosure(map);
            bool closing = false;
            std::vector<ObjectGuid> members;
            {
                std::lock_guard<std::mutex> lock(workMutex);
                for (auto it = closingRifts.begin(); it != closingRifts.end();)
                    if (it->instanceId == map->GetInstanceId() && it->mapId == map->GetId())
                    {
                        closing = true;
                        it = closingRifts.erase(it);
                    }
                    else
                        ++it;
                if (closing)
                {
                    members = std::move(riftMembers[map->GetInstanceId()]);
                    riftMembers.erase(map->GetInstanceId());
                }
            }
            if (!closing)
            {
                bool reset = false;
                if (!map->HavePlayers())
                {
                    std::lock_guard<std::mutex> lock(workMutex);
                    reset = resetWhenEmpty.erase(map->GetInstanceId()) != 0;
                }
                if (reset)
                    map->ToInstanceMap()->Reset(INSTANCE_RESET_ALL);
                return;
            }
            for (ObjectGuid guid : members)
            {
                auto* bind = sInstanceSaveMgr->PlayerGetBoundInstance(guid, map->GetId(), DUNGEON_DIFFICULTY_NORMAL);
                // A new rift may already have replaced this binding on the same map.
                if (bind && bind->save && bind->save->GetInstanceId() == map->GetInstanceId())
                    sInstanceSaveMgr->PlayerUnbindInstance(guid, map->GetId(), DUNGEON_DIFFICULTY_NORMAL, true);
            }
            WorldLocation destination;
            if (!DC::World::HubLocation(destination))
                return;
            std::vector<Player*> inside;
            map->DoForAllPlayers(
                [&](Player* player)
                {
                    if (player)
                        inside.push_back(player);
                });
            for (Player* player : inside)
            {
                ChatHandler(player->GetSession()).SendSysMessage("The rift closes. Returning you to the hub.");
                ForcedTeleport(player, [&](Player* moved) { moved->TeleportTo(destination); });
            }
            // Teleport acknowledgements arrive later; reset once the map is empty.
            std::lock_guard<std::mutex> lock(workMutex);
            resetWhenEmpty.insert(map->GetInstanceId());
        }

    public:
        void OnBeforeCreateInstanceScript(InstanceMap* map, InstanceScript**, bool load, std::string, uint32) override
        {
            if (!opening || load || opening->mapId != map->GetId())
                return;
            Rift& rift = *opening;
            rift.instanceId = map->GetInstanceId();
            if (rift.id)
            {
                RecordLaterFloor(rift); // rift floors Part F2: the run is recorded already
                return;
            }
            CharacterDatabase.DirectExecute(
                "INSERT INTO dc_rift (instance_id,map_id,dungeon_id,leader_guid,tier,party_size,kills,required,"
                "progress,required_units,mode,gr_rank,state) "
                "VALUES ({},{},{},{},{},{},0,{},0,{},'{}',{},'open')",
                rift.instanceId, rift.mapId, rift.dungeonId, rift.leaderGuid, rift.tier, rift.players, rift.required,
                rift.requiredUnits, rift.mode, rift.mode == "gr" ? std::to_string(rift.grRank) : "NULL");
            // LAST_INSERT_ID is connection-local; sync queries use a connection pool.
            auto row = CharacterDatabase.Query("SELECT id FROM dc_rift WHERE instance_id={} ORDER BY id DESC LIMIT 1",
                                               rift.instanceId);
            if (!row)
                return;
            rift.id = (*row)[0].Get<uint64>();
            // Floor 1 of the run, recorded with it (rift floors Part F1); the later floors add theirs as they open.
            CharacterDatabase.Execute(
                "INSERT INTO dc_rift_floor (run_id,floor,instance_id,map_id,dungeon_id) VALUES ({},1,{},{},{})", rift.id,
                rift.instanceId, rift.mapId, rift.dungeonId);
            std::lock_guard<std::mutex> lock(riftMutex);
            live.Start(rift);
        }
        // A floor's map is gone (a closed run's maps reset one by one, or a floor nobody stood on for
        // Instance.UnloadDelay unloaded). That floor leaves the run and its town portals go with it; the run goes on with
        // the floors it has left, and closes only with its last one (rift floors 5.2, Part F1).
        void OnDestroyMap(Map* map) override
        {
            if (!map->IsDungeon() || !map->GetInstanceId())
                return;
            TownPortal::CloseInstance(map->GetInstanceId());
            Exit::Forget(map->GetInstanceId());
            // Every pack in this instance died with the map, so its queued work and
            // its unit-hook marker go too.
            EraseInstanceWork(map->GetInstanceId());
            ForgetGreaterOrbs(map->GetInstanceId());
            EndUrshi(map->GetInstanceId());
            map->CustomData.Erase("DCRiftAffixMap");
            // Every pack in this instance died with the map, published or not.
            CharacterDatabase.Execute("DELETE FROM dc_rift_elite WHERE instance_id={}", map->GetInstanceId());
            Rift closing;
            Floor floor;
            bool lastFloor = false;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                Floor const* at = live.FloorAt(map->GetInstanceId(), map->GetId());
                if (!at)
                    return;
                floor = *at;
                lastFloor = live.FloorCount(floor.runId) == 1;
                if (lastFloor)
                {
                    Rift* run = live.Find(floor.runId);
                    run->state = "closed";
                    PersistNow(*run);
                    closing = *run;
                }
            }
            CharacterDatabase.Execute("UPDATE dc_rift_floor SET closed_at=NOW() WHERE run_id={} AND floor={}",
                                      floor.runId, floor.number);
            if (lastFloor)
            {
                // Map destruction is a closure path like any other, so it owes the same
                // cleanup: without this the rows stayed `enrolled` and the quests stayed
                // in logs, and EnrolledRun would keep answering with a dead run.
                RemoveRunQuests(closing);
                RemoveEntrance(closing.id);
                std::lock_guard<std::mutex> lock(workMutex);
                pendingCloses.erase(closing.id);
            }
            Spawner::FloorGone(map->GetInstanceId(), floor.runId, lastFloor);
            Pylons::FloorGone(floor.runId, lastFloor);
            std::lock_guard<std::mutex> lock(riftMutex);
            live.Remove(map->GetInstanceId(), map->GetId());
        }
    };

    class RiftCommand final : public CommandScript
    {
    public:
        RiftCommand()
            : CommandScript("dc_rift_command")
        {
        }
        Acore::ChatCommands::ChatCommandTable GetCommands() const override
        {
            using namespace Acore::ChatCommands;
            // Opening and closing change a rift, so both are administrator commands;
            // the obelisk is the way in for a player.
            // Status is read-only and stays SEC_PLAYER. Read-only GM commands stay
            // SEC_GAMEMASTER.
            static ChatCommandTable rift = {
                {"open", HandleOpen, SEC_ADMINISTRATOR, Console::No},
                {"close", HandleClose, SEC_ADMINISTRATOR, Console::No},
                {"status", HandleStatus, SEC_PLAYER, Console::No},
                // 7.9.4's player-accessible fallback for the Greater Rift ready check.
                {"accept", HandleAccept, SEC_PLAYER, Console::No},
                {"decline", HandleDecline, SEC_PLAYER, Console::No},
                {"affixes", HandleAffixes, SEC_GAMEMASTER, Console::No},
                {"affix", HandleForceAffix, SEC_ADMINISTRATOR, Console::No},
                {"abilities", HandleAbilities, SEC_GAMEMASTER, Console::No},
                {"census", HandleCensus, SEC_GAMEMASTER, Console::No},
                // Monster spawning S2: what this floor picked, and the sheets read again.
                {"picks", HandlePicks, SEC_GAMEMASTER, Console::No},
            };
            // The deliberate elite test harness.
            // GM-only throughout: it spawns monsters in the open world.
            static ChatCommandTable elite = {
                {"champion", HandleEliteChampion, SEC_ADMINISTRATOR, Console::No},
                {"rare", HandleEliteRare, SEC_ADMINISTRATOR, Console::No},
                {"affix", HandleEliteAffix, SEC_ADMINISTRATOR, Console::No},
                {"clear", HandleEliteClear, SEC_ADMINISTRATOR, Console::No},
                {"perf", HandleElitePerf, SEC_ADMINISTRATOR, Console::No},
            };
            // 13-elite-affixes §2: tuning without a restart. `.dc affix reload`
            // re-reads dc_affix_tunables and applies it to live packs; `.dc affix
            // set` writes one tuned_value and reloads. Console::Yes on both, so a
            // number can be changed from the worldserver window as well as in game.
            static ChatCommandTable affix = {
                {"reload", HandleAffixReload, SEC_ADMINISTRATOR, Console::Yes},
                {"set", HandleAffixSet, SEC_ADMINISTRATOR, Console::Yes},
                {"show", HandleAffixShow, SEC_GAMEMASTER, Console::Yes},
            };
            static ChatCommandTable dc = {{"rift", rift}, {"elite", elite}, {"affix", affix}};
            static ChatCommandTable root = {{"dc", dc}};
            return root;
        }

        // ---- the affix tunables (13-elite-affixes §2) ---------------------------
        //
        // Tuning is done by fighting a pack with `.dc elite`, changing a number, and
        // fighting it again. Neither command restarts anything.

        static std::string EscapeWorld(std::string value)
        {
            WorldDatabase.EscapeString(value);
            return value;
        }

        // What the server is actually using for one row: the tuned value when one has been
        // set, D3's otherwise.
        static std::string Effective(Field* row)
        {
            auto shown = [](double number)
            {
                std::ostringstream text;
                text << number; // 2.5 rather than 2.500000
                return text.str();
            };
            if (!row[2].IsNull())
                return shown(row[2].Get<double>()) + " (tuned; D3 " +
                       (row[1].IsNull() ? "publishes none" : shown(row[1].Get<double>())) + ")";
            if (!row[1].IsNull())
                return shown(row[1].Get<double>()) + " (D3)";
            return "unset";
        }

        static bool HandleAffixReload(ChatHandler* handler)
        {
            std::string error;
            if (!ReloadAffixNumbers(error))
            {
                handler->PSendSysMessage("Affix tunables NOT reloaded: {}", error);
                handler->SendSysMessage("The previous numbers are still in use.");
                return true;
            }
            handler->SendSysMessage("Affix tunables reloaded; live packs use the new numbers from their next tick.");
            // Fast's speed and Juggernaut's immunity are applied once, when the pack
            // is promoted, so a pack already standing keeps the old ones.
            handler->SendSysMessage(
                "Passives already applied to a standing pack keep their old value - respawn it with `.dc elite`.");
            return true;
        }

        // `.dc affix set <affix> <parameter> <value>`, and `default` in place of the
        // value clears tuned_value so the row falls back to what D3 published. The
        // affix name may contain spaces and may be quoted; the last two words are
        // always the parameter and the value.
        static bool HandleAffixSet(ChatHandler* handler, Acore::ChatCommands::Tail arguments)
        {
            std::vector<std::string> words;
            {
                std::istringstream stream{std::string(arguments)};
                for (std::string word; stream >> word;)
                    words.push_back(word);
            }
            if (words.size() < 3)
            {
                handler->SendSysMessage("Usage: .dc affix set <affix> <parameter> <value|default>");
                handler->SendSysMessage("  .dc affix set Jailer reach 25");
                handler->SendSysMessage("  .dc affix set \"Fire Chains\" chain_width 3");
                handler->SendSysMessage("  .dc affix set Knockback distance default   (back to D3's published figure)");
                return true;
            }
            std::string const wanted = TrimArgument(words.back());
            std::string const parameter = TrimArgument(words[words.size() - 2]);
            std::string affix;
            for (std::size_t index = 0; index + 2 < words.size(); ++index)
                affix += (affix.empty() ? "" : " ") + words[index];
            affix = TrimArgument(affix);

            bool const clearing = wanted == "default" || wanted == "d3" || wanted == "null";
            double value = 0;
            if (!clearing)
            {
                try
                {
                    std::size_t used = 0;
                    value = std::stod(wanted, &used);
                    if (used != wanted.size() || !std::isfinite(value) || value < 0.0)
                        throw std::invalid_argument("trailing text");
                }
                catch (std::exception const&)
                {
                    handler->PSendSysMessage("'{}' is not a number. Use `default` to go back to D3's value.", wanted);
                    return true;
                }
            }

            std::string const escapedAffix = EscapeWorld(affix), escapedParameter = EscapeWorld(parameter);
            if (!WorldDatabase.Query("SELECT parameter FROM dc_affix_tunables "
                                     "WHERE affix_name='{}' AND parameter='{}'",
                                     escapedAffix, escapedParameter))
            {
                handler->PSendSysMessage("dc_affix_tunables has no {} / {}.", affix, parameter);
                handler->PSendSysMessage("`.dc affix show {}` lists what it does have.",
                                         affix.empty() ? "_global" : affix);
                return true;
            }
            // Direct, not queued: the reload on the next line has to see it.
            if (clearing)
                WorldDatabase.DirectExecute("UPDATE dc_affix_tunables SET tuned_value=NULL "
                                            "WHERE affix_name='{}' AND parameter='{}'",
                                            escapedAffix, escapedParameter);
            else
                WorldDatabase.DirectExecute("UPDATE dc_affix_tunables SET tuned_value={} "
                                            "WHERE affix_name='{}' AND parameter='{}'",
                                            value, escapedAffix, escapedParameter);

            std::string error;
            if (!ReloadAffixNumbers(error))
            {
                handler->PSendSysMessage("Written, but NOT reloaded: {}", error);
                return true;
            }
            if (QueryResult row =
                    WorldDatabase.Query("SELECT parameter, d3_value, tuned_value, unit FROM dc_affix_tunables "
                                        "WHERE affix_name='{}' AND parameter='{}'",
                                        escapedAffix, escapedParameter))
                handler->PSendSysMessage("{} / {} is now {} {}", affix, parameter, Effective(row->Fetch()),
                                         (*row)[3].Get<std::string>());
            // elite_affix_parameters.csv is the source of
            // truth, so this is a scratch override for the pack being fought
            // now and the next apply of rifts_0014_affix_round_two.sql takes it
            // back. `default` needs no such line: it asks for the published
            // value, which is what an apply gives it.
            if (!clearing)
                handler->SendSysMessage("(temporary: lasts until the next apply from "
                                        "elite_affix_parameters.csv; put it in the CSV to keep it)");
            return true;
        }

        // Every parameter of one affix, with what the server is using for each.
        // No argument shows the shared values.
        static bool HandleAffixShow(ChatHandler* handler, Acore::ChatCommands::Tail affixName)
        {
            std::string affix = TrimArgument(std::string(affixName));
            if (affix.empty())
                affix = "_global";
            QueryResult rows =
                WorldDatabase.Query("SELECT parameter, d3_value, tuned_value, unit FROM dc_affix_tunables "
                                    "WHERE affix_name='{}' ORDER BY parameter",
                                    EscapeWorld(affix));
            if (!rows)
            {
                handler->PSendSysMessage("dc_affix_tunables has no rows for '{}'.", affix);
                handler->SendSysMessage("Try `_global`, or an affix name as `.dc rift affixes` spells it.");
                return true;
            }
            handler->PSendSysMessage("{}:", affix);
            do
            {
                Field* row = rows->Fetch();
                handler->PSendSysMessage("  {} = {} {}", row[0].Get<std::string>(), Effective(row),
                                         row[3].Get<std::string>());
            } while (rows->NextRow());
            return true;
        }

        // Force one affix onto the selected creature so a tester can see exactly one
        // behaviour at a time. The creature has to be in a live rift; if it is not
        // already a promoted elite it is given the elite state on the spot, which is
        // enough for every behaviour (it keeps its own model and rank).
        static bool HandleForceAffix(ChatHandler* handler, Acore::ChatCommands::Tail affixName)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            std::string const wanted = TrimArgument(std::string(affixName));
            Creature* target = handler->getSelectedCreature();
            if (!target)
            {
                handler->PSendSysMessage("Select the creature first.");
                return true;
            }
            Map* map = target->GetMap();
            unsigned tier = 0, players = 0;
            if (!map || !ScalingContext(map, tier, players))
            {
                handler->PSendSysMessage("That creature is not in a live rift.");
                return true;
            }
            Affix chosen;
            std::string names;
            if (!FindAffix(wanted, chosen, names))
            {
                handler->PSendSysMessage("No affix with a behaviour called '{}'.", wanted);
                handler->PSendSysMessage("Try one of: {}", names);
                return true;
            }
            EliteState* state = target->CustomData.GetDefault<EliteState>("DCRiftElite");
            state->tier = tier;
            state->affixes.assign(1, chosen);
            state->nextTick = 0;
            state->nextCluster = 0;
            state->nextCast = 0;
            state->nextVolley = 0;
            state->nextShield = 0;
            state->shieldUntil = 0;
            state->reflectFrom = 0;
            state->reflectUntil = 0;
            state->illusionsSpawned = false;
            state->shieldHolder.Clear();
            state->nextCastFor.clear();
            ApplyPassiveAffixes(target, *state);
            PublishElite(target, *state, map->GetInstanceId());
            handler->PSendSysMessage("{} now carries {} and nothing else.", target->GetName(), chosen.name);
            return true;
        }

        // ---- the deliberate elite test harness ---
        //
        // `.dc rift affix` rewrites the one creature you have selected and its
        // pack-mates keep whatever they rolled, so no test of a single affix is
        // clean. These four spawn a pack that carries exactly what you asked for and
        // nothing else, in the open world, where you can see it coming.

        static bool HandleEliteChampion(ChatHandler* handler)
        {
            return Spawn(handler, false, {});
        }

        static bool HandleEliteRare(ChatHandler* handler)
        {
            return Spawn(handler, true, {});
        }

        // Replaces the pack rather than editing it: a fresh body cannot carry a
        // stacked Fast or a leftover Juggernaut immunity from the affix before it,
        // and the pack is the same kind, in the same place, as the one it replaces.
        static bool HandleEliteAffix(ChatHandler* handler, Acore::ChatCommands::Tail affixName)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            HarnessPack existing;
            {
                std::lock_guard<std::mutex> lock(harnessMutex);
                auto found = harnessPacks.find(player->GetGUID().GetRawValue());
                if (found == harnessPacks.end())
                {
                    handler->SendSysMessage("No test pack. Spawn one with `.dc elite champion` or `.dc elite rare`.");
                    return true;
                }
                existing = found->second;
            }
            // Checked before anything is despawned, so a typo costs you nothing.
            Affix chosen;
            std::string names;
            std::string const wanted = TrimArgument(std::string(affixName));
            if (!FindAffix(wanted, chosen, names))
            {
                handler->PSendSysMessage("No affix with a behaviour called '{}'.", wanted);
                handler->PSendSysMessage("Try one of: {}", names);
                return true;
            }
            // elite_affixes.csv's own appears_on: a champion-only affix cannot roll
            // on a rare and the other way round, so forcing one would be testing
            // something the game never produces.
            std::string const kind = existing.rare ? "rare" : "champion";
            if (chosen.appearsOn != "both" && chosen.appearsOn != kind)
            {
                handler->PSendSysMessage("{} appears on {} packs only; yours is a {} pack.", chosen.name,
                                         chosen.appearsOn, kind);
                handler->PSendSysMessage("Spawn the other kind with `.dc elite {}` first.",
                                         chosen.appearsOn == "rare" ? "rare" : "champion");
                return true;
            }
            Creature* leader = SpawnHarness(player, existing.rare, {chosen}, &existing.spot);
            if (!leader)
            {
                handler->SendSysMessage("Could not respawn the test pack.");
                return true;
            }
            Describe(handler, leader, chosen.name);
            return true;
        }

        static bool HandleElitePerf(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player || !player->GetMap())
                return false;
            handler->SendSysMessage(AffixPerformance(player->GetMap()).c_str());
            return true;
        }

        static bool HandleEliteClear(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            unsigned const gone = ClearHarness(player);
            if (gone)
                handler->PSendSysMessage("Test pack despawned ({} creature(s)).", gone);
            else
                handler->SendSysMessage("No test pack of yours to despawn.");
            return true;
        }

        static bool Spawn(ChatHandler* handler, bool rare, std::vector<Affix> const& affixes)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            // Open world only: inside a rift the pack would be promoted, scaled and
            // rolled by the rift itself, which is the confound this replaces.
            if (!player->GetMap() || player->GetMap()->Instanceable())
            {
                handler->SendSysMessage("Spawn the test pack in the open world, not in an instance.");
                return true;
            }
            Creature* leader = SpawnHarness(player, rare, affixes, nullptr);
            if (!leader)
            {
                handler->PSendSysMessage("Could not spawn the test pack; is entry {} in the world DB?",
                                         (rare ? RARE_BASE : CHAMPION_BASE) + HARNESS_ENTRY);
                return true;
            }
            Describe(handler, leader, affixes.empty() ? "none" : affixes.front().name);
            return true;
        }

        // What was spawned, with the numbers that say whether the pack size and the
        // tier scaling landed. The Life is already the tier's: the pack inherits the
        // caller's phase at Creature::Create, and patch 0003 hands the creature to
        // the difficulty module during that same call, before the summon returns.
        // So spawning at two tiers and comparing these two figures is a whole test
        // of the scaling on its own.
        static void Describe(ChatHandler* handler, Creature* leader, std::string const& affix)
        {
            EliteState const* state = leader->CustomData.Get<EliteState>("DCRiftElite");
            unsigned const members = state ? static_cast<unsigned>(state->pack.size()) : 0;
            handler->PSendSysMessage("{} {}: {} creature(s), tier {}, phase {}, leader Life {}, affix: {}",
                                     state && state->rare ? "Rare" : "Champion", leader->GetName(), members + 1,
                                     state ? state->tier : 0, leader->GetPhaseMask(), leader->GetMaxHealth(), affix);
            LOG_INFO("server", "[DC rifts] harness pack entry={} rare={} members={} tier={} phase={} life={}",
                     leader->GetEntry(), state && state->rare, members, state ? state->tier : 0, leader->GetPhaseMask(),
                     leader->GetMaxHealth());
        }

        static bool HandleOpen(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            std::string error;
            if (!Open(player, error))
            {
                handler->SendSysMessage(error);
                return false;
            }
            return true;
        }

        static bool Respond(ChatHandler* handler, std::uint64_t proposalId, bool accept)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            RespondGreaterRift(player, proposalId, accept);
            return true;
        }
        static bool HandleAccept(ChatHandler* handler, std::uint64_t proposalId)
        {
            return Respond(handler, proposalId, true);
        }
        static bool HandleDecline(ChatHandler* handler, std::uint64_t proposalId)
        {
            return Respond(handler, proposalId, false);
        }

        static bool HandleClose(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            std::string error;
            if (!Close(player, error))
            {
                handler->SendSysMessage(error);
                return false;
            }
            return true;
        }

        static bool HandleStatus(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            Rift rift;
            if (!Current(player, rift))
            {
                handler->SendSysMessage("Not in a rift.");
                return true;
            }
            // Progress is the bar in both modes (monster spawning S3: hundredths of a D3 progress point, 65,000 the
            // full bar); the kill count and `required` are no longer the bar.
            handler->PSendSysMessage("rift {}: instance {}, map {}, tier {}, players {}, progress {}/{}, state {}",
                                     rift.id, rift.instanceId, rift.mapId, rift.tier, rift.players, rift.progress,
                                     rift.requiredUnits, rift.state);
            // Rift floors Part F2: every floor standing, this one marked, with its exit portal.
            std::vector<Floor> floors;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                floors = live.Floors(rift.id);
            }
            for (Floor const& floor : floors)
            {
                std::string dungeon = "?";
                Dungeon found;
                if (ArrivalOf(floor.dungeonId, found))
                    dungeon = found.name;
                handler->PSendSysMessage("  floor {}{}: {}, instance {}, map {}; {}", floor.number,
                                         floor.number == rift.floor ? " (here)" : "", dungeon, floor.instanceId, floor.mapId,
                                         Exit::Describe(floor.instanceId, floor.mapId));
            }
            if (rift.mode == "gr")
                handler->PSendSysMessage("Greater Rift {}: outcome {}, {} s left at the Guardian's death, "
                                         "deadline in {} s",
                                         rift.grRank, rift.outcome, rift.timeLeft,
                                         std::max<std::int64_t>(0, rift.deadline - GameTime::GetGameTime().count()));
            return true;
        }

        // A 3.3.5a client cannot be told a spawn's affixes: the name is per entry
        // and the nameplate has nowhere to put them. Selecting the elite and asking
        // is how they are read until the AIO bar carries them (stage 2).
        // 09 F2 check: walks the creatures loaded around the caller and reports any
        // that could still cast - a spell slot the strip missed, or an AI that is
        // neither the plain melee one nor the guardian's. An empty report is the
        // pass condition.
        // Bug 2's measurement: how many creatures the instance is holding, alive and
        // dead. Run it, leave through the portal, come back, run it again - the
        // numbers must match.
        static bool HandleCensus(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            Rift rift;
            if (!Current(player, rift))
            {
                handler->SendSysMessage("Stand in a rift to count its creatures.");
                return true;
            }
            // Instance-wide, not a radius: the whole point is to catch creatures
            // disappearing somewhere the player is not standing.
            unsigned alive = 0, dead = 0, elites = 0;
            for (auto const& pair : player->GetMap()->GetCreatureBySpawnIdStore())
                if (Creature* creature = pair.second)
                {
                    if (creature->IsPet() || creature->IsTotem() || creature->IsCritter())
                        continue;
                    creature->IsAlive() ? ++alive : ++dead;
                }
            // Promoted packs are summons and have no spawn id, so they are counted
            // from the row the module keeps for each live one.
            if (QueryResult row =
                    CharacterDatabase.Query("SELECT COUNT(*) FROM dc_rift_elite WHERE instance_id={}", rift.instanceId))
                elites = static_cast<unsigned>((*row)[0].Get<uint64>());
            handler->PSendSysMessage(
                "Rift {} (instance {}): {} spawned creature(s) alive, {} dead, {} promoted elite(s).", rift.id,
                rift.instanceId, alive, dead, elites);
            LOG_INFO("server", "[DC rifts] census instance {}: alive={} dead={} elites={}", rift.instanceId, alive,
                     dead, elites);
            return true;
        }

        static bool HandlePicks(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            std::vector<std::string> lines;
            if (!player || !Spawner::Report(player->GetMap(), lines))
            {
                handler->SendSysMessage("This map has no rift picks (not a rift floor, or nothing was placed on it).");
                return true;
            }
            for (std::string const& line : lines)
                handler->SendSysMessage(line);
            return true;
        }

        static bool HandleAbilities(ChatHandler* handler)
        {
            Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
            if (!player)
                return false;
            Rift rift;
            if (!Current(player, rift))
            {
                handler->SendSysMessage("Stand in a rift to check its creatures.");
                return true;
            }
            std::list<Creature*> found;
            player->GetCreatureListWithEntryInGrid(found, 0, ABILITY_SCAN_RANGE);
            unsigned scanned = 0, withSpells = 0, withScriptedAI = 0;
            std::ostringstream offenders;
            for (Creature* creature : found)
            {
                if (!creature || !creature->IsAlive() || creature->IsPet() || creature->IsTotem() ||
                    creature->IsCritter() || creature->IsGuardian() || creature->IsControlledByPlayer())
                    continue;
                ++scanned;
                bool spells = false;
                for (std::uint8_t slot = 0; slot < MAX_CREATURE_SPELLS; ++slot)
                    spells = spells || creature->m_spells[slot] != 0;
                // The guardian is the one rift creature allowed an AI of its own.
                bool const plain = HasPlainRiftAI(creature);
                if (spells)
                    ++withSpells;
                if (!plain)
                    ++withScriptedAI;
                if ((spells || !plain) && withSpells + withScriptedAI <= 6)
                    offenders << " " << creature->GetName() << "(" << creature->GetEntry() << ")";
            }
            handler->PSendSysMessage(
                "Rift {}: {} creature(s) within {} yd; {} with a spell slot, {} with a scripted AI.", rift.id, scanned,
                static_cast<unsigned>(ABILITY_SCAN_RANGE), withSpells, withScriptedAI);
            if (withSpells || withScriptedAI)
                handler->PSendSysMessage("  still armed:{}", offenders.str());
            else
                handler->SendSysMessage("  all melee only (09 F2).");
            return true;
        }

        static bool HandleAffixes(ChatHandler* handler)
        {
            Creature* target = handler->getSelectedCreature();
            if (!target)
            {
                handler->SendSysMessage("Select a creature first.");
                return true;
            }
            EliteState* state = target->CustomData.Get<EliteState>("DCRiftElite");
            if (!state)
            {
                handler->PSendSysMessage("{} is not a promoted rift elite.", target->GetName());
                return true;
            }
            handler->PSendSysMessage("{} ({}{}), tier {}: {} affix(es)", target->GetName(),
                                     state->rare ? "rare" : "champion", state->member ? " pack member" : " pack leader",
                                     state->tier, state->affixes.size());
            for (Affix const& affix : state->affixes)
                handler->PSendSysMessage("  {} [{}] {} - {}{}{}", affix.name, affix.element,
                                         affix.behaviour.empty() ? "name only" : affix.behaviour, affix.pool,
                                         affix.minionInherits ? ", minions inherit" : ", leader only",
                                         affix.levelLimited ? ", one of the eleven" : "");
            return true;
        }
    };

    void RegisterScripts()
    {
        TownPortal::RegisterScripts();
        new RiftWorld();
        new RiftObelisk();
        new RiftHubCreature();
        new RiftMap();
        RegisterAIScripts();
        RegisterEliteScripts();
        Spawner::RegisterScripts();
        RegisterQuestScripts();
        RegisterGreaterRiftLevelScripts();
        RegisterFamilyLineupScripts();
        RegisterGreaterRiftOpenScripts();
        RegisterGreaterRiftRuleScripts();
        RegisterUrshiScripts();
        Shatter::RegisterScripts();
        OpenRift::RegisterScripts();
        Exit::RegisterScripts();
        Pylons::RegisterScripts();
        Ally::RegisterScripts();
        new RiftCommand();
    }
} // namespace DC::Rifts
