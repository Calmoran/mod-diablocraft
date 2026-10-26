/*
 * World of DiabloCraft - hardcore (11-hardcore §2-§4).
 *
 * The mode is one row in dc_character_mode, written once and never rewritten:
 * H4 makes it permanent, so every path that could change it is a bug.
 * Everything else in this file follows from that row.
 *
 * Who writes it: Normal and Hardcore are separate
 * REALMS, so the row is no longer something the player answers. EnsureMode
 * writes it from Diablocraft.Hardcore.Enable on the character's first login,
 * in the same call that hands out the 08 §5 kit, and there is no prompt. Every
 * reader of the row is unchanged; only the writer is.
 */

#include "dc_hardcore.h"

#include "../common/dc_world.h"
#include "../common/dc_account_economy.h"
#include "../common/dc_bridge.h"
#include "../common/dc_tunables.h"
#include "../difficulty/dc_difficulty.h"
#include "../rifts/dc_rifts.h"
#include "../rifts/dc_town_portal.h"

#include "CharacterCache.h"
#include "CharacterPackets.h"
#include "Chat.h"
#include "Config.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Log.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "World.h"
#include "WorldSession.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (12): NAME_LIMIT, characters the dead-marker rename may use; Schema fact.
// Constant (20): seconds subtracted to force an instant logout; Engine value.
// Constant: SPREAD_POOL, SPREAD_STEP, SPREAD_EYE below; points kept and probe heights of the
// town spread, Engine values (the one tunable is the radius, combat/revive_town_spread_yards).

namespace DC::Hardcore
{
    namespace
    {
        // 11 §3's marker. The 3.3.5a client cannot grey a character out without a client
        // patch (11 §5 keeps that open), so a dead one is renamed instead. U+2020
        // DAGGER, spelled in bytes so this file's own encoding cannot change what
        // reaches the database.
        constexpr char const* DEAD_MARKER = "\xE2\x80\xA0";
        // characters.name is varchar(12); MySQL counts characters there, not bytes, so
        // the marker costs exactly one of the twelve.
        constexpr std::size_t NAME_LIMIT = 12;

        std::mutex dataMutex;
        // guid -> mode, so the paragon pool question (10 P3) costs no query per kill.
        // Filled on login and on the choice, dropped on logout and on delete.
        std::unordered_map<std::uint32_t, Mode> modes;

        // What a death still has to do once the core has finished killing the player.
        // Unit::Kill calls setDeathState (which is OnPlayerJustDied) before it calls the
        // killer hooks, and neither resurrecting nor logging a player out inside that
        // call is something the core expects, so both wait for the next player update.
        struct Pending
        {
            bool hardcore = false;
            bool releaseRequested = false;
            std::string killer = "something unknown";
            bool haveKiller = false;
        };
        std::mutex pendingMutex;
        std::unordered_map<std::uint64_t, Pending> pending;

        char const* Name(Mode mode)
        {
            return mode == Mode::Hardcore ? "hardcore" : mode == Mode::Normal ? "normal" : "unchosen";
        }

        Mode Parse(std::string const& text)
        {
            if (text == "hardcore")
                return Mode::Hardcore;
            if (text == "normal")
                return Mode::Normal;
            return Mode::Unchosen;
        }

        Mode Load(std::uint32_t guid)
        {
            {
                std::lock_guard<std::mutex> lock(dataMutex);
                auto found = modes.find(guid);
                if (found != modes.end())
                    return found->second;
            }
            Mode mode = Mode::Unchosen;
            if (QueryResult row = CharacterDatabase.Query("SELECT mode FROM dc_character_mode WHERE guid={}", guid))
                mode = Parse((*row)[0].Get<std::string>());
            std::lock_guard<std::mutex> lock(dataMutex);
            modes[guid] = mode;
            return mode;
        }

        void Forget(std::uint32_t guid)
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            modes.erase(guid);
        }

        std::string Escape(std::string value)
        {
            CharacterDatabase.EscapeString(value);
            return value;
        }

        // Counts characters rather than bytes, so a multi-byte name is never cut in half.
        std::string TrimToLimit(std::string const& name, std::size_t limit)
        {
            std::size_t characters = 0, index = 0;
            while (index < name.size() && characters < limit)
            {
                unsigned char const lead = static_cast<unsigned char>(name[index]);
                index += lead < 0x80 ? 1 : lead < 0xE0 ? 2 : lead < 0xF0 ? 3 : 4;
                ++characters;
            }
            return name.substr(0, std::min(index, name.size()));
        }

        bool AlreadyMarked(std::string const& name)
        {
            return name.rfind(DEAD_MARKER, 0) == 0;
        }

        std::string MarkedName(std::string const& name)
        {
            if (AlreadyMarked(name))
                return name;
            return std::string(DEAD_MARKER) + TrimToLimit(name, NAME_LIMIT - 1);
        }

        std::string UnmarkedName(std::string const& name)
        {
            return AlreadyMarked(name) ? name.substr(std::string(DEAD_MARKER).size()) : name;
        }

        void Rename(Player* player, std::uint32_t guid, std::string const& name)
        {
            if (player)
            {
                // Set it on the live object too: the logout save writes GetName(), and a
                // database-only rename would be overwritten by it.
                player->SetName(name);
                sCharacterCache->UpdateCharacterData(player->GetGUID(), name);
            }
            else
                sCharacterCache->UpdateCharacterData(ObjectGuid(HighGuid::Player, guid), name);
            CharacterDatabase.DirectExecute("UPDATE characters SET name='{}' WHERE guid={}", Escape(name), guid);
        }

        // Where the character died, in words, for killed_by and the log.
        std::string Circumstances(Player const* player)
        {
            DC::Rifts::Rift rift;
            if (DC::Rifts::Current(player, rift))
                return "rift " + std::to_string(rift.id) + ", tier " + std::to_string(rift.tier);
            return "tier " + std::to_string(DC::Difficulty::CurrentTier(player));
        }

        // H1. The character keeps everything it had; only the ability to play it goes.
        void Lock(Player* player, std::string const& killer)
        {
            std::uint32_t const guid = player->GetGUID().GetCounter();
            std::string const where = Circumstances(player);
            CharacterDatabase.DirectExecute(
                "UPDATE dc_character_mode SET dead=1, died_at=NOW(), killed_by='{}' WHERE guid={}",
                Escape(TrimToLimit(killer + " in " + where, 100)), guid);
            // The core's own per-character ban is what actually refuses the next login
            // (Player::LoadFromDB returns false on an active row). The login guard below
            // is the second lock, for the case where that row is lifted by hand.
            CharacterDatabase.DirectExecute(
                "INSERT INTO character_banned (guid,bandate,unbandate,bannedby,banreason,active) "
                "VALUES ({},UNIX_TIMESTAMP(),0,'Diablocraft','Hardcore death',1) "
                "ON DUPLICATE KEY UPDATE active=1",
                guid);
            LOG_INFO("server", "[DC hardcore] {} (guid {}) died to {} in {}; character locked", player->GetName(), guid,
                     killer, where);
            Rename(player, guid, MarkedName(player->GetName()));
            Forget(guid);
            player->SaveToDB(false, false);
        }

        // Revive choices (11 §3, docs/contracts/revive-choices-messages.md): the three places a Normal
        // character can come back to.
        enum class Choice
        {
            Here,
            Town,
            Checkpoint
        };

        struct Destination
        {
            Choice done = Choice::Here; // what the server does; Here whenever it cannot do more
            WorldLocation at;
            bool wayBack = false; // Town from inside an open rift: open the Town Portal pair where it fell first
        };

        char const* Name(Choice choice)
        {
            return choice == Choice::Town ? "town" : choice == Choice::Checkpoint ? "checkpoint" : "here";
        }

        // Town arrivals spread round the hub's spawn: a point of the disc of radius
        // combat/revive_town_spread_yards round it, on dry ground the spawn can see and whose height is near the
        // spawn's. The terrain is read ONLY by the hub map's own thread (HubSpread::OnMapUpdate, one candidate a
        // tick until SPREAD_POOL points are kept); a revive, a release or a kick, which run on whatever map the
        // character is leaving, draw one kept point and touch no map (Map::GetGridTerrainData creates grids, which
        // only the map's own thread may do). A blank or zero row, a pool not filled yet (the hub
        // has been empty) or filled for another radius or spawn leaves the spawn itself.
        constexpr std::size_t SPREAD_POOL = 256;
        constexpr float SPREAD_STEP = 3.0f; // yards the ground may differ in height from the spawn
        constexpr float SPREAD_EYE = 2.0f;  // lift of both ends of the sight line

        std::mutex spreadMutex;
        std::vector<WorldLocation> spreadPoints;
        float spreadRadius = 0.0f;
        WorldLocation spreadCenter;

        bool SameSpot(WorldLocation const& a, WorldLocation const& b)
        {
            return a.GetMapId() == b.GetMapId() && a.GetPositionX() == b.GetPositionX() &&
                   a.GetPositionY() == b.GetPositionY() && a.GetPositionZ() == b.GetPositionZ();
        }

        // One try at a point round `center`; only on the thread of the map `map` is.
        bool SpreadCandidate(Map* map, WorldLocation const& center, float radius, WorldLocation& out)
        {
            float const angle = static_cast<float>(rand_norm() * 2.0 * M_PI);
            float const distance = radius * static_cast<float>(std::sqrt(rand_norm())); // even over the disc
            float const x = center.GetPositionX() + distance * std::cos(angle);
            float const y = center.GetPositionY() + distance * std::sin(angle);
            float const z = map->GetHeight(PHASEMASK_NORMAL, x, y, center.GetPositionZ() + SPREAD_STEP, true,
                                           2 * SPREAD_STEP);
            // No ground at all is INVALID_HEIGHT, far outside the step.
            if (std::fabs(z - center.GetPositionZ()) > SPREAD_STEP ||
                map->IsInWater(PHASEMASK_NORMAL, x, y, z, DEFAULT_COLLISION_HEIGHT) ||
                !map->isInLineOfSight(center.GetPositionX(), center.GetPositionY(), center.GetPositionZ() + SPREAD_EYE,
                                      x, y, z + SPREAD_EYE, PHASEMASK_NORMAL, LINEOFSIGHT_ALL_CHECKS,
                                      VMAP::ModelIgnoreFlags::Nothing))
                return false;
            out = center;
            out.Relocate(x, y, z);
            return true;
        }

        // The hub map's own thread, once a tick: keep the pool for the row and the spawn as they are now.
        void RefreshSpread(Map* map)
        {
            WorldLocation center;
            if (!DC::World::HubLocation(center) || map->GetId() != center.GetMapId())
                return;
            float const radius = static_cast<float>(DC::Tunables::Get("combat", "revive_town_spread_yards"));
            {
                std::lock_guard<std::mutex> lock(spreadMutex);
                if (spreadRadius != radius || !SameSpot(spreadCenter, center))
                {
                    spreadPoints.clear();
                    spreadRadius = radius;
                    spreadCenter = center;
                }
                if (radius <= 0.0f || spreadPoints.size() >= SPREAD_POOL)
                    return;
            }
            WorldLocation point;
            if (!SpreadCandidate(map, center, radius, point))
                return;
            std::lock_guard<std::mutex> lock(spreadMutex);
            if (spreadRadius == radius && spreadPoints.size() < SPREAD_POOL)
                spreadPoints.push_back(point);
        }

        // Any thread, no map read: one of the kept points, when they are for this row and this spawn.
        void SpreadAround(WorldLocation& at)
        {
            float const radius = static_cast<float>(DC::Tunables::Get("combat", "revive_town_spread_yards"));
            std::lock_guard<std::mutex> lock(spreadMutex);
            if (spreadPoints.empty() || spreadRadius != radius || !SameSpot(spreadCenter, at))
                return;
            at = spreadPoints[std::min(spreadPoints.size() - 1,
                                       static_cast<std::size_t>(rand_norm() * static_cast<double>(spreadPoints.size())))];
        }

        // Where a character arrives in town: the hub's spawn, spread. False before the hub row is loaded.
        bool TownArrival(WorldLocation& at)
        {
            if (!DC::World::HubLocation(at))
                return false;
            SpreadAround(at);
            return true;
        }

        // A living player the core would send to a graveyard (the 60 second kick from an instance, an instance reset,
        // a declined instance bind, a logout from an invalid one, `.unstuck graveyard`) goes to town instead; nobody
        // goes to a graveyard in Torment. True when it is dealt with and the core must not
        // move it; false before the hub row is loaded, when the core's own move stands.
        bool SendToTown(Player* player)
        {
            WorldLocation town;
            if (!TownArrival(town))
                return false;
            if (!player->IsBeingTeleported())
                player->TeleportTo(town);
            return true;
        }

        // D3 patch 2.0.1: at most combat/revive_body_limit revives at the body in a
        // row outside a Greater Rift, then the checkpoint or town. Per character, in memory: a restart clears it,
        // a logout does not, and only a revive somewhere else (or deleting the character) resets it. Blank or
        // zero is no limit.
        std::mutex bodyMutex;
        std::unordered_map<std::uint32_t, unsigned> bodyRevives;

        bool InGreaterRift(Player const* player)
        {
            DC::Rifts::Rift rift;
            return DC::Rifts::Current(player, rift) && rift.mode == "gr";
        }

        unsigned BodyLimit()
        {
            return static_cast<unsigned>(DC::Tunables::Get("combat", "revive_body_limit"));
        }

        bool BodyLimitReached(Player const* player)
        {
            unsigned const limit = BodyLimit();
            if (!limit || InGreaterRift(player))
                return false;
            std::lock_guard<std::mutex> lock(bodyMutex);
            auto found = bodyRevives.find(player->GetGUID().GetCounter());
            return found != bodyRevives.end() && found->second >= limit;
        }

        void NoteRevive(Player const* player, Choice done)
        {
            bool const free = done == Choice::Here && InGreaterRift(player); // the body is free there, and breaks no run
            std::lock_guard<std::mutex> lock(bodyMutex);
            if (done != Choice::Here)
                bodyRevives.erase(player->GetGUID().GetCounter());
            else if (!free)
                ++bodyRevives[player->GetGUID().GetCounter()];
        }

        // A body under the map's lowest point is a fall into the void (MovementHandler kills for it, as
        // DAMAGE_FALL_TO_VOID): reviving there would kill the character again. The core's own test.
        bool DiedBelowTheMap(Player const* player)
        {
            return player->GetPositionZ() < player->GetMap()->GetMinHeight(player->GetPositionX(), player->GetPositionY());
        }

        // Why `choice` does not work for this dead character right now; empty when it does. The `O` record and
        // every request ask here, so a greyed button and a refusal cannot disagree. The Greater Rift wait is not
        // part of it: it ends by itself, and a record read once would grey a button that has since opened.
        std::string Unavailable(Player* player, Choice choice)
        {
            WorldLocation place;
            if (choice == Choice::Here)
            {
                if (DiedBelowTheMap(player))
                    return "Your body is below the world.";
                if (BodyLimitReached(player))
                    return "You can revive at your body only " + std::to_string(BodyLimit()) + " times in a row.";
            }
            else if (choice == Choice::Checkpoint)
            {
                if (!DC::Rifts::EntryPosition(player, place))
                    return DC::World::IsInHub(player) ? "There is no checkpoint in town." : "There is no checkpoint here.";
            }
            else // Choice::Town
            {
                if (DC::Rifts::GreaterRiftTownReviveRefused(player))
                    return "You cannot revive in town inside a Greater Rift.";
                if (!DC::World::HubLocation(place))
                    return "Town is not available right now.";
            }
            return "";
        }

        // The server's own answer, for a choice Unavailable has passed. A request only names a choice; the place
        // is read here, and never the core's graveyard.
        Destination Resolve(Player* player, Choice asked)
        {
            Destination to;
            if (asked == Choice::Town && TownArrival(to.at))
            {
                to.done = Choice::Town;
                DC::Rifts::Rift rift;
                to.wayBack = DC::Rifts::Current(player, rift);
            }
            else if (asked == Choice::Checkpoint && DC::Rifts::EntryPosition(player, to.at))
                to.done = Choice::Checkpoint;
            return to;
        }

        // What Release, the automatic release timer and a login while dead mean: the body when that works, else
        // the checkpoint, else town. Nothing working (no hub loaded, a fall into the void) leaves it where it
        // fell rather than dead for good.
        Choice ReleaseChoice(Player* player)
        {
            for (Choice choice : {Choice::Here, Choice::Checkpoint, Choice::Town})
                if (Unavailable(player, choice).empty())
                    return choice;
            return Choice::Here;
        }

        // 11 §3: a Normal character revives with full health and no corpse run, where `to` says. A place the
        // core will not take leaves it where it fell (`to.done` says so). False when another module vetoed
        // the resurrection.
        bool Respawn(Player* player, Destination& to)
        {
            player->ResurrectPlayer(1.0f);
            if (!player->IsAlive())
                return false;
            player->SpawnCorpseBones(); // no corpse, so nothing to run back to
            player->SetHealth(player->GetMaxHealth());
            ChatHandler chat(player->GetSession());
            if (to.done != Choice::Here)
            {
                // The pair is opened where it fell, so it comes before the move.
                if (to.wayBack && !DC::Rifts::TownPortal::OpenPair(player))
                    chat.SendSysMessage("Town Portal could not open, so there is no way back to where you fell.");
                if (!player->TeleportTo(to.at))
                    to.done = Choice::Here;
            }
            NoteRevive(player, to.done);
            // Unit::Kill already took RATE_DURABILITY_LOSS_ON_DEATH; skipping the corpse
            // run is exactly what keeps that the only cost.
            if (to.done == Choice::Here)
                chat.SendSysMessage("Revived where you fell. Death costs durability only.");
            else if (to.done == Choice::Town)
                chat.SendSysMessage("Revived in town. Death costs durability only.");
            else
                chat.SendSysMessage("Revived at the checkpoint. Death costs durability only.");
            LOG_INFO("server", "[DC respawn] {} revived ({}) from map={} instance={} x={} y={} z={}", player->GetName(),
                     Name(to.done), player->GetMapId(), player->GetInstanceId(), player->GetPositionX(),
                     player->GetPositionY(), player->GetPositionZ());
            return true;
        }

        // DCREVIVE. Every rule is checked here; the message names a choice and nothing else.
        void Choose(Player& player, DC::Bridge::Request const& request, DC::Bridge::Wire<Player> const& wire)
        {
            auto const verb = request.Token(0, 10);
            if (!verb || request.Count() != 1)
                throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
            bool const options = *verb == "options";
            Choice asked = Choice::Here;
            if (*verb == "town")
                asked = Choice::Town;
            else if (*verb == "checkpoint")
                asked = Choice::Checkpoint;
            else if (*verb != "here" && !options)
                throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
            if (player.IsAlive())
                throw DC::Bridge::Refusal("You are not dead.");
            if (Load(player.GetGUID().GetCounter()) == Mode::Hardcore)
                throw DC::Bridge::Refusal("Hardcore deaths are final.");
            if (options)
            {
                // Per button, in the window's order: "1" when it works now, else the reason it does not.
                std::string const corpse = Unavailable(&player, Choice::Here);
                std::string const checkpoint = Unavailable(&player, Choice::Checkpoint);
                std::string const town = Unavailable(&player, Choice::Town);
                wire.Record({"O", corpse.empty() ? "1" : corpse, checkpoint.empty() ? "1" : checkpoint,
                             town.empty() ? "1" : town});
                return;
            }
            if (player.IsBeingTeleported())
                throw DC::Bridge::Refusal("Try again in a moment.");
            // The core's own release handler does the same: a death it has not processed yet finishes first.
            if (player.getDeathState() == DeathState::JustDied)
                player.KillPlayer();
            // Greater Rift rule 5: no revive in town there, and every revive waits, longer
            // with each death. `here` and `checkpoint` (the floor's start) are the two a Greater Rift keeps.
            if (std::string const why = Unavailable(&player, asked); !why.empty())
                throw DC::Bridge::Refusal(why);
            if (unsigned const wait = DC::Rifts::GreaterRiftReviveWaitLeft(&player))
                throw DC::Bridge::Refusal("You can revive in " + std::to_string(wait) + " seconds.");
            Destination to = Resolve(&player, asked);
            if (!Respawn(&player, to))
                throw DC::Bridge::Refusal("You could not be revived.");
            wire.Record({"R", *verb, Name(to.done)});
        }

        void QueueLogout(Player* player)
        {
            // Match HandleLogoutRequestOpcode's successful instant-logout response.
            // Setting the timer alone skips this packet and only sends LogoutComplete,
            // leaving the client without the normal start of the logout transition.
            WorldPackets::Character::LogoutResponse response;
            response.LogoutResult = 0;
            response.Instant = true;
            player->GetSession()->SendPacket(response.Write());
            // LogoutPlayer deletes Player; defer it to World::UpdateSessions, using
            // the same game clock and 20-second timer as the core logout handler.
            player->GetSession()->SetLogoutStartTime(GameTime::GetGameTime().count() - 20);
            LOG_INFO("server", "[DC hardcore] Logout response sent; queued character-select return for guid {}",
                     player->GetGUID().GetCounter());
        }

        void Eject(Player* player, std::string const& killer)
        {
            ChatHandler handler(player->GetSession());
            handler.PSendSysMessage("Your Hardcore character has fallen to {}. It can no longer be played.", killer);
            handler.SendSysMessage(
                "It keeps its gear and its Paragon allocation. You can delete it whenever you want.");
            QueueLogout(player);
        }

        class HardcorePlayer final : public PlayerScript
        {
        public:
            HardcorePlayer()
                : PlayerScript("dc_hardcore_player",
                               {PLAYERHOOK_ON_PLAYER_JUST_DIED, PLAYERHOOK_ON_PLAYER_KILLED_BY_CREATURE,
                                PLAYERHOOK_ON_PVP_KILL, PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_DELETE,
                                PLAYERHOOK_ON_UPDATE, PLAYERHOOK_CAN_REPOP_AT_GRAVEYARD})
            {
            }

            void OnPlayerJustDied(Player* player) override
            {
                if (!player)
                    return;
                Pending entry;
                entry.hardcore = Load(player->GetGUID().GetCounter()) == Mode::Hardcore;
                std::lock_guard<std::mutex> lock(pendingMutex);
                pending[player->GetGUID().GetRawValue()] = entry;
            }

            void OnPlayerKilledByCreature(Creature* killer, Player* killed) override
            {
                if (killer && killed)
                    RememberKiller(killed, killer->GetName());
            }

            void OnPlayerPVPKill(Player* killer, Player* killed) override
            {
                if (killer && killed)
                    RememberKiller(killed, killer->GetName());
            }

            bool OnPlayerCanRepopAtGraveyard(Player* player) override
            {
                if (!player)
                    return true;
                if (player->IsAlive())
                    return !SendToTown(player);
                bool const hardcore = Load(player->GetGUID().GetCounter()) == Mode::Hardcore;
                std::lock_guard<std::mutex> lock(pendingMutex);
                // Also covers a dead character loaded after a logout/server restart.
                auto& entry = pending[player->GetGUID().GetRawValue()];
                entry.hardcore = hardcore;
                entry.releaseRequested = true;
                return false; // BuildPlayerRepop has run; never leave the death map/instance.
            }

            // Unit::Kill has returned and the killer hook has filled in the name.
            // Normal deaths wait for Release (or the core's automatic release timer).
            void OnPlayerUpdate(Player* player, uint32) override
            {
                if (!player)
                    return;
                Pending entry;
                {
                    std::lock_guard<std::mutex> lock(pendingMutex);
                    auto found = pending.find(player->GetGUID().GetRawValue());
                    if (found == pending.end())
                        return;
                    if (player->IsAlive())
                    {
                        pending.erase(found); // A GM/spell resurrected the player first.
                        return;
                    }
                    if (!found->second.hardcore && !found->second.releaseRequested)
                        return;
                    // Greater Rift rule 5: a release inside the wait revives when the wait is over.
                    if (!found->second.hardcore && DC::Rifts::GreaterRiftReviveWaitLeft(player))
                        return;
                    entry = found->second;
                    pending.erase(found);
                }
                if (entry.hardcore)
                {
                    Lock(player, entry.killer);
                    Eject(player, entry.killer);
                }
                else
                {
                    // Release, the automatic release timer, and a login while dead: the body, else the
                    // checkpoint, else town.
                    Destination to = Resolve(player, ReleaseChoice(player));
                    Respawn(player, to);
                }
            }

            void OnPlayerLogin(Player* player) override
            {
                std::uint32_t const guid = player->GetGUID().GetCounter();
                Load(guid);
                if (!IsHardcore(player) && !player->IsAlive() && player->HasPlayerFlag(PLAYER_FLAGS_GHOST))
                    OnPlayerCanRepopAtGraveyard(player);
                if (!IsLocked(guid))
                    return;
                // Only reachable when the ban row has been lifted by hand: the character
                // is still dead, so it still cannot be played.
                ChatHandler(player->GetSession())
                    .SendSysMessage("This Hardcore character is dead and cannot be played.");
                QueueLogout(player);
            }

            void OnPlayerLogout(Player* player) override
            {
                Forget(player->GetGUID().GetCounter());
                std::lock_guard<std::mutex> lock(pendingMutex);
                pending.erase(player->GetGUID().GetRawValue());
            }

            void OnPlayerDelete(ObjectGuid guid, uint32) override
            {
                std::uint32_t const low = guid.GetCounter();
                // H1: delete is WoW's own. The mode row and our death ban go with it, so
                // a recycled guid can never inherit a dead character's lock.
                CharacterDatabase.Execute("DELETE FROM dc_character_mode WHERE guid={}", low);
                CharacterDatabase.Execute("DELETE FROM character_banned WHERE guid={} AND bannedby='Diablocraft'", low);
                Forget(low);
                std::lock_guard<std::mutex> lock(bodyMutex);
                bodyRevives.erase(low);
            }

        private:
            static void RememberKiller(Player const* killed, std::string const& killer)
            {
                std::lock_guard<std::mutex> lock(pendingMutex);
                auto found = pending.find(killed->GetGUID().GetRawValue());
                if (found != pending.end() && !found->second.haveKiller)
                {
                    found->second.killer = killer;
                    found->second.haveKiller = true;
                }
            }
        };

        // The hub map's own thread fills the town spread (SpreadAround).
        class HubSpread final : public AllMapScript
        {
        public:
            HubSpread()
                : AllMapScript("dc_hub_spread", {ALLMAPHOOK_ON_MAP_UPDATE})
            {
            }

            void OnMapUpdate(Map* map, uint32) override
            {
                RefreshSpread(map);
            }
        };

        class HardcoreCommand final : public CommandScript
        {
        public:
            HardcoreCommand()
                : CommandScript("dc_hardcore_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // Since the mode became the realm's, `choose` is no longer
                // anybody's answer: it is the GM repair for a character that has no row
                // - a start interrupted before EnsureMode wrote one, or a character made
                // before this change. It still refuses once a mode exists, and that is
                // what keeps H4 permanent. All three are GM tools now.
                static ChatCommandTable mode = {
                    {"choose", HandleChoose, SEC_ADMINISTRATOR, Console::No},
                    {"revive", HandleRevive, SEC_ADMINISTRATOR, Console::Yes},
                    {"", HandleStatus, SEC_GAMEMASTER, Console::No},
                };
                static ChatCommandTable dcMode = {{"mode", mode}};
                static ChatCommandTable root = {{"dc", dcMode}};
                return root;
            }

            // Acts on the selected character, or on the GM's own when nothing is
            // selected, which is what `.dc mode` already does.
            static bool HandleChoose(ChatHandler* handler, std::string choice)
            {
                Player* player = handler->getSelectedPlayerOrSelf();
                if (!player)
                    return false;
                Mode const wanted = Parse(choice);
                if (wanted == Mode::Unchosen)
                {
                    handler->SendSysMessage("Usage: .dc mode choose <normal|hardcore>");
                    return false;
                }
                std::uint32_t const guid = player->GetGUID().GetCounter();
                if (Mode const already = Load(guid); already != Mode::Unchosen)
                {
                    handler->PSendSysMessage("This character is already {}. The choice is permanent (11 H4).",
                                             Name(already));
                    return true;
                }
                // INSERT IGNORE rather than REPLACE: two prompts answered at once must
                // not be able to overwrite each other's mode.
                CharacterDatabase.DirectExecute("INSERT IGNORE INTO dc_character_mode (guid,mode) VALUES ({},'{}')",
                                                guid, Name(wanted));
                Forget(guid);
                Mode const stored = Load(guid);
                handler->PSendSysMessage("Mode set to {}. This cannot be changed.", Name(stored));
                LOG_INFO("server", "[DC hardcore] GM set guid {} ({}) to {}", guid, player->GetName(), Name(stored));
                // 08 §5: a character repaired this way still has no kit.
                if (!DC::AccountEconomy::ResolvePending(player))
                {
                    handler->SendSysMessage(
                        "Account migration could not finish. Reconnect before receiving the starter kit.");
                    return false;
                }
                DC::World::StartCharacter(player);
                return true;
            }

            static bool HandleStatus(ChatHandler* handler, Optional<std::string> name)
            {
                std::uint32_t guid = 0;
                std::string label;
                if (name && !name->empty())
                {
                    ObjectGuid const found = sCharacterCache->GetCharacterGuidByName(*name);
                    if (!found)
                    {
                        handler->PSendSysMessage("No character named {}.", *name);
                        return false;
                    }
                    guid = found.GetCounter();
                    label = *name;
                }
                else if (Player* target = handler->getSelectedPlayerOrSelf())
                {
                    guid = target->GetGUID().GetCounter();
                    label = target->GetName();
                }
                else
                {
                    handler->SendSysMessage("Usage: .dc mode [name]");
                    return false;
                }
                QueryResult row = CharacterDatabase.Query(
                    "SELECT mode, dead, IFNULL(died_at,''), killed_by FROM dc_character_mode WHERE guid={}", guid);
                if (!row)
                {
                    handler->PSendSysMessage(
                        "{} (guid {}): no mode row yet; its first login writes the realm's (11 H4).", label, guid);
                    return true;
                }
                Field* fields = row->Fetch();
                bool const dead = fields[1].Get<uint8>() != 0;
                handler->PSendSysMessage("{} (guid {}): mode={} dead={}", label, guid, fields[0].Get<std::string>(),
                                         dead ? "yes" : "no");
                if (dead)
                    handler->PSendSysMessage("  died {} to {}", fields[2].Get<std::string>(),
                                             fields[3].Get<std::string>());
                handler->PSendSysMessage(
                    "  login ban row: {}",
                    CharacterDatabase.Query("SELECT 1 FROM character_banned WHERE guid={} AND active=1", guid)
                        ? "active"
                        : "none");
                return true;
            }

            // Testing only. 11 H1 has no revive: a dead hardcore character stays dead.
            static bool HandleRevive(ChatHandler* handler, std::string name)
            {
                ObjectGuid found = sCharacterCache->GetCharacterGuidByName(name);
                if (!found)
                    found = sCharacterCache->GetCharacterGuidByName(MarkedName(name));
                if (!found)
                {
                    handler->PSendSysMessage("No character named {}.", name);
                    return false;
                }
                std::uint32_t const guid = found.GetCounter();
                if (!CharacterDatabase.Query("SELECT 1 FROM dc_character_mode WHERE guid={} AND dead=1", guid))
                {
                    handler->PSendSysMessage("{} is not marked dead.", name);
                    return true;
                }
                CharacterDatabase.DirectExecute(
                    "UPDATE dc_character_mode SET dead=0, died_at=NULL, killed_by='' WHERE guid={}", guid);
                CharacterDatabase.DirectExecute("DELETE FROM character_banned WHERE guid={} AND bannedby='Diablocraft'",
                                                guid);
                std::string storedName;
                sCharacterCache->GetCharacterNameByGuid(found, storedName);
                std::string const restored = UnmarkedName(storedName);
                if (restored != storedName)
                    Rename(nullptr, guid, restored);
                Forget(guid);
                handler->PSendSysMessage(
                    "{} revived for testing; name restored to {}. This is not a game rule (11 H1).", name, restored);
                LOG_INFO("server", "[DC hardcore] GM revived guid {} ({} -> {})", guid, name, restored);
                return true;
            }
        };

        class HardcoreLogin final : public ServerScript
        {
        public:
            HardcoreLogin()
                : ServerScript("dc_hardcore_login", {SERVERHOOK_CAN_PACKET_RECEIVE})
            {
            }

            bool CanPacketReceive(WorldSession* session, WorldPacket const& packet) override
            {
                if (!session || packet.GetOpcode() != CMSG_PLAYER_LOGIN || session->PlayerLoading() ||
                    session->GetPlayer())
                    return true;
                // Leave malformed requests and ownership violations to the core. Read
                // a copy so an allowed request reaches its handler with its cursor intact.
                if (packet.size() - packet.rpos() < sizeof(uint64))
                    return true;
                WorldPacket copy(packet);
                ObjectGuid guid;
                copy >> guid;
                if (!guid.IsPlayer())
                    return true;
                if (!CharacterDatabase.Query("SELECT 1 FROM dc_character_mode m JOIN characters c ON c.guid=m.guid "
                                             "WHERE m.guid={} AND c.account={} AND m.mode='hardcore' AND m.dead=1",
                                             guid.GetCounter(), session->GetAccountId()))
                    return true;
                // Reject before LoadFromDB: its ban/failure path kicks the account.
                // This standard login failure leaves the client on character select.
                session->SendCharLoginFailed(LoginFailureReason::Disabled);
                LOG_INFO("server",
                         "[DC hardcore] Refused locked guid {} at character select; account {} stays connected",
                         guid.GetCounter(), session->GetAccountId());
                return false;
            }
        };
    } // namespace

    Mode ModeOf(std::uint32_t guid)
    {
        return Load(guid);
    }
    Mode ModeOf(Player const* player)
    {
        return player ? Load(player->GetGUID().GetCounter()) : Mode::Unchosen;
    }
    bool IsHardcore(Player const* player)
    {
        return ModeOf(player) == Mode::Hardcore;
    }

    // 11 H4. Read from the config every time rather than cached at
    // startup: a realm is what its worldserver.conf says it is right now, and a
    // static copy is one more thing that could disagree with the row it writes.
    Mode RealmMode()
    {
        return sConfigMgr->GetOption<bool>("Diablocraft.Hardcore.Enable", false) ? Mode::Hardcore : Mode::Normal;
    }

    // The writer every character goes through, called from DC::World::Start on its
    // first login - the same point that used to show the prompt. The GM repair
    // below is the only other INSERT of this row, and it is the same statement. It
    // answers the 08 §5 question the prompt used to answer: may the kit be handed
    // out now. A write that does not land leaves the character modeless and keeps
    // the kit, which is what the prompt's unanswered case did too.
    bool EnsureMode(Player* player)
    {
        if (!player)
            return false;
        std::uint32_t const guid = player->GetGUID().GetCounter();
        if (Load(guid) != Mode::Unchosen)
            return true;
        Mode const realm = RealmMode();
        // INSERT IGNORE, not REPLACE: a row already on disk is the permanent one,
        // whatever this realm is set to now. H4 outlives a config edit.
        CharacterDatabase.DirectExecute("INSERT IGNORE INTO dc_character_mode (guid,mode) VALUES ({},'{}')", guid,
                                        Name(realm));
        Forget(guid);
        Mode const stored = Load(guid);
        LOG_INFO("server", "[DC hardcore] {} (guid {}) starts {}: the realm's setting", player->GetName(), guid,
                 Name(stored));
        return stored != Mode::Unchosen;
    }

    // A8. Reads the same map OnPlayerJustDied fills, so the answer is true from the
    // instant the core killed the character, not from the update that writes it.
    bool DeathPending(Player const* player)
    {
        if (!player)
            return false;
        std::lock_guard<std::mutex> lock(pendingMutex);
        auto found = pending.find(player->GetGUID().GetRawValue());
        return found != pending.end() && found->second.hardcore;
    }

    bool IsLocked(std::uint32_t guid)
    {
        return bool(CharacterDatabase.Query("SELECT 1 FROM dc_character_mode WHERE guid={} AND dead=1", guid));
    }

    void RegisterScripts()
    {
        new HardcorePlayer();
        new HardcoreCommand();
        new HardcoreLogin();
        new HubSpread();
        DC::Bridge::Routes().Add("DCREVIVE", {"combat", "revive_burst", "revive_per_second"}, Choose);
    }
} // namespace DC::Hardcore
