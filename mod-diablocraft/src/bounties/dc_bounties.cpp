/*
 * World of DiabloCraft - bounties: the boards, their parties and the window (docs/research/bounties.md 5.1 and 5.4, contract
 * docs/contracts/bounty-messages.md).
 *
 * The catalogue is the world tables dc_bounties / dc_bounties_spot (generate_bounties.py). A board belongs to an owner:
 * a party (groups.guid) or a player (low guid), one row a live cell in the characters table dc_bounties_board. A party
 * plays its leader's board, copied the first time the party needs one (the leader's own join, at the party's creation,
 * which comes inside Group::Create before sGroupMgr->AddGroup, so the hook's Group* names the leader);
 * joins, leaves and leader changes keep it; a disband deletes it. A solo player's board stays as it was while they are
 * in a party and is theirs again when they leave. Every change is saved at once and pushed to every online member of
 * the owner. The rules of the board itself (draw, complete, the reroll gate, the records) are dc_bounty_board.h.
 */

#include "dc_bounties.h"
#include "dc_bounty_board.h"

#include "../common/dc_bridge.h"
#include "../common/dc_tunables.h"
#include "../common/dc_world.h"
#include "../rifts/dc_rifts.h"
#include "../combat/dc_spell_shells.h"

#include "Chat.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupMgr.h"
#include "Log.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "WorldSession.h"

#include <atomic>
#include <cmath>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace DC::Bounties
{
    namespace
    {
        constexpr char const* WINDOW = "DCBOUNTY";
        constexpr char const* TUNABLES = "rifts";

        struct Owner
        {
            std::uint8_t kind = 0; // 0 a player, 1 a party
            std::uint32_t id = 0;
            bool operator<(Owner const& other) const
            {
                return std::make_pair(kind, id) < std::make_pair(other.kind, other.id);
            }
        };

        std::mutex boardMutex; // the catalogue, the boards and their rows
        std::vector<Bounty> catalog;
        std::vector<Target> targets; // the named-target master list (dc_bounties_target)
        std::map<Owner, Board> boards;
        std::atomic<std::uint64_t> epoch{1};          // Epoch(): moved by every save, drop and show
        std::set<std::uint32_t> catalogMaps; // IsBountyMap(): written once at startup with the catalogue, read without the lock

        Owner Solo(ObjectGuid guid)
        {
            return {0, guid.GetCounter()};
        }
        Owner Party(Group const* group)
        {
            return {1, group->GetGUID().GetCounter()};
        }
        Group* PartyGroup(Player const* player)
        {
            Group* group = const_cast<Player*>(player)->GetGroup();
            return group && !group->isBGGroup() && !group->isBFGroup() ? group : nullptr;
        }
        Owner OwnerOf(Player const* player)
        {
            Group* group = PartyGroup(player);
            return group ? Party(group) : Solo(player->GetGUID());
        }
        bool IsLeader(Player* player)
        {
            Group* group = PartyGroup(player);
            return !group || group->GetLeaderGUID() == player->GetGUID();
        }

        unsigned Count(char const* name)
        {
            double value = DC::Tunables::Get(TUNABLES, name);
            return value > 0 && std::isfinite(value) ? static_cast<unsigned>(std::min(value, 4294967295.0)) : 0;
        }
        Rules CurrentRules()
        {
            return {Count("bounty_kill_monster_count"), Count("bounty_click_objectives_min"), Count("bounty_click_objectives_max")};
        }
        std::uint32_t Roll(std::uint32_t lo, std::uint32_t hi)
        {
            return urand(lo, hi);
        }

        // --- rows (boardMutex held) ---

        void SaveLocked(Owner owner, Board const& board)
        {
            CharacterDatabaseTransaction trans = CharacterDatabase.BeginTransaction();
            trans->Append("DELETE FROM dc_bounties_board WHERE owner_kind={} AND owner_id={}", owner.kind, owner.id);
            for (Cell const& c : board)
                trans->Append("INSERT INTO dc_bounties_board "
                              "(owner_kind,owner_id,col,cell,bounty_id,objectives,need,progress,done,target) "
                              "VALUES ({},{},{},{},{},{},{},{},{},{})",
                              owner.kind, owner.id, c.column, c.cell, c.bounty, c.objectives, c.need, c.progress,
                              c.done ? 1 : 0, c.target);
            CharacterDatabase.DirectCommitTransaction(trans);
            ++epoch;
        }

        // `leader`: a party's leader when the caller has the Group* (its creation, before sGroupMgr knows it).
        Board& LoadLocked(Owner owner, ObjectGuid leader = ObjectGuid::Empty)
        {
            if (auto found = boards.find(owner); found != boards.end())
                return found->second;
            Board board;
            if (auto result = CharacterDatabase.Query(
                    "SELECT col,cell,bounty_id,objectives,need,progress,done,target FROM dc_bounties_board "
                    "WHERE owner_kind={} AND owner_id={} ORDER BY col,cell",
                    owner.kind, owner.id))
                do
                {
                    Field* f = result->Fetch();
                    Cell c{f[0].Get<uint8>(),  f[1].Get<uint8>(),  f[2].Get<uint32>(),    f[3].Get<uint32>(),
                           f[4].Get<uint32>(), f[5].Get<uint32>(), f[6].Get<uint8>() != 0, f[7].Get<uint32>()};
                    // A bounty the catalogue dropped leaves its cell, and so does a Kill whose target left the list (or a
                    // board saved before the list, target 0): a board left empty is drawn again.
                    if (Bounty const* b = Find(catalog, c.bounty); b && !CellTitle(c, *b, targets).empty())
                        board.push_back(c);
                } while (result->NextRow());
            if (board.empty())
            {
                if (owner.kind == 0)
                    board = Draw(catalog, targets, CurrentRules(), Roll);
                else
                {
                    if (leader.IsEmpty())
                        if (Group* group = sGroupMgr->GetGroupByGUID(owner.id))
                            leader = group->GetLeaderGUID();
                    if (!leader.IsEmpty())
                        board = LoadLocked(Solo(leader)); // the leader's board, copied
                }
                if (!board.empty())
                    SaveLocked(owner, board);
            }
            return boards[owner] = board;
        }

        void DropLocked(Owner owner)
        {
            boards.erase(owner);
            ++epoch;
            CharacterDatabase.DirectExecute("DELETE FROM dc_bounties_board WHERE owner_kind={} AND owner_id={}",
                                            owner.kind, owner.id);
        }

        // --- the wire ---

        std::vector<Player*> Online(Owner owner)
        {
            std::vector<Player*> out;
            if (owner.kind == 0)
            {
                if (Player* player =
                        ObjectAccessor::FindConnectedPlayer(ObjectGuid::Create<HighGuid::Player>(owner.id)))
                    out.push_back(player);
            }
            else if (Group* group = sGroupMgr->GetGroupByGUID(owner.id))
                for (auto const& slot : group->GetMemberSlots())
                    if (Player* player = ObjectAccessor::FindConnectedPlayer(slot.guid))
                        out.push_back(player);
            return out;
        }

        void Send(Player* player, std::vector<std::vector<std::string>> const& records)
        {
            for (auto const& record : records)
                if (!DC::Bridge::Push(player, WINDOW, record))
                {
                    LOG_ERROR("server", "[DC bounties] {} record for {} was not sent (too long, or no session)",
                              record[0], player->GetName());
                    return;
                }
        }

        // `player` gets the board of `owner`, drawing or copying it first if it has none (`partyLeader` as LoadLocked's).
        void Show(Player* player, Owner owner, bool leader, ObjectGuid partyLeader = ObjectGuid::Empty)
        {
            std::vector<std::vector<std::string>> records;
            {
                std::lock_guard<std::mutex> lock(boardMutex);
                records = Records(LoadLocked(owner, partyLeader), catalog, targets, leader, DC::Rifts::OpenZoneWaypoint);
            }
            ++epoch; // who plays which board may have moved (a join, a leave, a disband): the objectives look again
            Send(player, records);
        }

        void ShowAll(Owner owner, std::string const& line = "")
        {
            for (Player* member : Online(owner))
            {
                if (!line.empty())
                    ChatHandler(member->GetSession()).SendSysMessage(line);
                Show(member, owner, IsLeader(member));
            }
        }

        template<class Step>
        bool Credit(Player* player, std::uint32_t id, Step step)
        {
            Owner const owner = OwnerOf(player);
            Change change;
            std::string title;
            {
                std::lock_guard<std::mutex> lock(boardMutex);
                Board& board = LoadLocked(owner);
                change = step(board);
                if (!change.changed)
                    return false;
                SaveLocked(owner, board);
                for (Cell const& c : board)
                    if (c.bounty == id)
                        if (Bounty const* b = Find(catalog, id))
                            title = CellTitle(c, *b, targets);
            }
            ShowAll(owner, change.completed ? "Bounty complete: " + title + "." : "");
            // W4: a finished column owes every online member its cache, paid on their own update (dc_bounty_cache.cpp).
            if (change.columnDone)
                for (Player* member : Online(owner))
                    OweCache(member, change.column);
            return true;
        }

        // "New bounties": the leader or a solo player, once every live cell is done. "" when the board was drawn again.
        std::string Reroll(Player* player)
        {
            if (!IsLeader(player))
                return "Only the party leader can roll new bounties.";
            Owner const owner = OwnerOf(player);
            {
                std::lock_guard<std::mutex> lock(boardMutex);
                Board& board = LoadLocked(owner);
                if (!Cleared(board))
                    return "Complete every bounty on the board first.";
                board = Draw(catalog, targets, CurrentRules(), Roll);
                SaveLocked(owner, board);
            }
            ShowAll(owner, "New bounties are on the board.");
            return "";
        }

        // Travel: the trip a travel cast carries, by player, until the cast ends.
        struct Trip
        {
            std::string zoneKey;
        };
        std::mutex tripMutex;
        std::map<std::uint64_t, Trip> casting;

        // Where the clicker stands, as the gate reads it.
        Standing StandingOf(Player* player)
        {
            Map const* map = player->GetMap();
            DC::Rifts::Rift rift;
            Standing at;
            at.sanctum = DC::World::IsInHub(player);
            at.rift = DC::Rifts::Current(player, rift);
            at.instanced = map && map->Instanceable();
            at.openZone = DC::Rifts::IsOpenZoneMap(player->GetMapId());
            at.inCombat = player->IsInCombat();
            return at;
        }

        std::string Go(Player* player, Trip const& trip)
        {
            return DC::Rifts::TravelToOpenZone(player, trip.zoneKey, nullptr);
        }

        // Travel (W5): the gate, then one teleport of the clicker into their party's copy of `zoneKey`, at the zone's
        // entrance (its waypoint; a bounty's button lands there too). From the Sanctum the teleport is instant; from the open world (a stock continent
        // or the 751 copy) it is a cast first, Shells::BountyTravel, and the trip waits in `casting` until the cast ends.
        // "" when the teleport ran or the cast began.
        std::string Travel(Player* player, std::string const& zoneKey)
        {
            if (player->IsBeingTeleported())
                return "You are already on your way.";
            Standing const at = StandingOf(player);
            if (char const* why = TravelRefusal(at))
                return why;
            Trip trip;
            trip.zoneKey = zoneKey;
            if (at.sanctum)
                return Go(player, trip);
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> lock(tripMutex);
                casting[guid] = trip;
            }
            if (player->CastSpell(player, DC::Combat::Shells::BountyTravel, false) == SPELL_CAST_OK)
                return "";
            std::lock_guard<std::mutex> lock(tripMutex);
            casting.erase(guid);
            return "You cannot travel right now.";
        }

        // The travel cast ended (an interrupted one never gets here). The trip goes on the player's next update: a
        // teleport from inside the cast's own completion would interrupt that spell while it unwinds (Player::TeleportTo
        // without TELE_TO_SPELL). The gate is asked again then, and a refusal is a chat line.
        void TravelCastDone(Player* player)
        {
            Trip trip;
            {
                std::lock_guard<std::mutex> lock(tripMutex);
                auto found = casting.find(player->GetGUID().GetRawValue());
                if (found == casting.end())
                    return;
                trip = found->second;
                casting.erase(found);
            }
            player->m_Events.AddEventAtOffset(
                [player, trip]
                {
                    char const* why = player->IsBeingTeleported() ? "You are already on your way."
                                                                   : TravelRefusal(StandingOf(player));
                    std::string const said = why ? std::string(why) : Go(player, trip);
                    if (!said.empty())
                        ChatHandler(player->GetSession()).SendSysMessage(said);
                },
                0ms);
        }

        // A bounty's button: its cell on the board the clicker plays, to that zone's waypoint. A cell that board does not hold
        // is refused.
        std::string TravelToCell(Player* player, unsigned column, unsigned cell)
        {
            std::string zoneKey;
            {
                std::lock_guard<std::mutex> lock(boardMutex);
                std::string const* found = CellZone(LoadLocked(OwnerOf(player)), catalog, column, cell);
                if (!found)
                    return "That bounty is not on your board.";
                zoneKey = *found;
            }
            return Travel(player, zoneKey);
        }

        void Window(Player& player, DC::Bridge::Request const& request, DC::Bridge::Wire<Player> const& /*wire*/)
        {
            auto verb = request.Token(0, 8);
            if (!verb)
                throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
            std::string why;
            if (*verb == "list" && request.Count() == 1)
                Show(&player, OwnerOf(&player), IsLeader(&player));
            else if (*verb == "new" && request.Count() == 1)
                why = Reroll(&player);
            else if (*verb == "travel" && request.Count() == 3)
            {
                auto column = request.Uint(1, 1, Columns), cell = request.Uint(2, 1, Cells);
                if (!column || !cell)
                    throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
                why = TravelToCell(&player, *column, *cell);
            }
            else if (*verb == "waypoint" && request.Count() == 2)
            {
                auto zoneKey = request.Token(1, 32);
                if (!zoneKey)
                    throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
                why = Travel(&player, *zoneKey);
            }
            else
                throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
            if (!why.empty())
                throw DC::Bridge::Refusal(why);
        }

        // --- scripts ---

        class BountyWorld final : public WorldScript
        {
        public:
            BountyWorld()
                : WorldScript("dc_bounties_world", {WORLDHOOK_ON_LOAD_CUSTOM_DATABASE_TABLE, WORLDHOOK_ON_STARTUP})
            {
            }
            void OnLoadCustomDatabaseTable() override
            {
                std::vector<Bounty> loaded;
                if (auto result = WorldDatabase.Query(
                        "SELECT bounty_id,col,idx,type,zone_key,zone_name,map_id,zone_id,title "
                        "FROM dc_bounties ORDER BY bounty_id"))
                    do
                    {
                        Field* f = result->Fetch();
                        Bounty b;
                        b.id = f[0].Get<uint32>();
                        b.column = f[1].Get<uint8>();
                        b.index = f[2].Get<uint8>();
                        b.type = f[3].Get<std::string>();
                        b.zoneKey = f[4].Get<std::string>();
                        b.zoneName = f[5].Get<std::string>();
                        b.mapId = f[6].Get<uint32>();
                        b.zoneId = f[7].Get<uint32>();
                        b.title = f[8].Get<std::string>();
                        if (b.column < 1 || b.column > Columns)
                            LOG_ERROR("server", "[DC bounties] bounty {} has column {}; it is left out", b.id,
                                      b.column);
                        else
                            loaded.push_back(b);
                    } while (result->NextRow());
                // W2: a spot's guard pack is the survey's own pack at its anchor (dc_rift_anchor, generate_rift_survey.py).
                if (auto result = WorldDatabase.Query(
                        "SELECT s.bounty_id,s.anchor,s.x,s.y,s.z,s.o,COALESCE(a.native_entry,0),COALESCE(a.pack_size,0) "
                        "FROM dc_bounties_spot s JOIN dc_bounties b ON b.bounty_id=s.bounty_id "
                        "LEFT JOIN dc_rift_anchor a ON a.dungeon=b.zone_name AND a.anchor=s.anchor "
                        "ORDER BY s.bounty_id,s.spot"))
                    do
                    {
                        Field* f = result->Fetch();
                        for (Bounty& b : loaded)
                            if (b.id == f[0].Get<uint32>())
                                b.spots.push_back({f[1].Get<uint32>(), f[2].Get<float>(), f[3].Get<float>(),
                                                   f[4].Get<float>(), f[5].Get<float>(), f[6].Get<uint32>(),
                                                   f[7].Get<uint32>()});
                    } while (result->NextRow());
                if (auto result = WorldDatabase.Query("SELECT bounty_id,go_entry FROM dc_bounties_objective"))
                    do
                    {
                        Field* f = result->Fetch();
                        for (Bounty& b : loaded)
                            if (b.id == f[0].Get<uint32>())
                                b.objectiveEntry = f[1].Get<uint32>();
                    } while (result->NextRow());
                for (Bounty const& b : loaded)
                    if (b.type == "click" && !b.objectiveEntry)
                        LOG_ERROR("server", "[DC bounties] Click bounty {} has no objective object "
                                  "(dc_bounties_objective); its objectives are not put out", b.id);
                std::vector<Target> named;
                if (auto result = WorldDatabase.Query("SELECT entry,title FROM dc_bounties_target ORDER BY entry"))
                    do
                    {
                        Field* f = result->Fetch();
                        named.push_back({f[0].Get<uint32>(), f[1].Get<std::string>()});
                    } while (result->NextRow());
                if (named.empty())
                    LOG_ERROR("server", "[DC bounties] dc_bounties_target is empty; Kill bounties have no target to draw");
                std::lock_guard<std::mutex> lock(boardMutex);
                catalog = std::move(loaded);
                targets = std::move(named);
                boards.clear();
                catalogMaps.clear();
                for (Bounty const& b : catalog)
                    catalogMaps.insert(b.mapId);
                ++epoch;
                LOG_INFO("server.loading", "[DC bounties] {} bounties loaded", catalog.size());
            }
            // A party that ended while the server was down left its board behind.
            void OnStartup() override
            {
                CharacterDatabase.DirectExecute(
                    "DELETE b FROM dc_bounties_board b LEFT JOIN `groups` g ON g.guid=b.owner_id "
                    "WHERE b.owner_kind=1 AND g.guid IS NULL");
            }
        };

        class BountyGroup final : public GroupScript
        {
        public:
            BountyGroup()
                : GroupScript("dc_bounties_group", {GROUPHOOK_ON_ADD_MEMBER, GROUPHOOK_ON_REMOVE_MEMBER,
                                                    GROUPHOOK_ON_CHANGE_LEADER, GROUPHOOK_ON_DISBAND})
            {
            }
            // A joiner plays the party's board; the leader's own join at the party's creation copies the leader's board
            // to it. That join runs before the group is registered, so the leader comes from the Group* in hand.
            void OnAddMember(Group* group, ObjectGuid guid) override
            {
                if (group->isBGGroup() || group->isBFGroup())
                    return;
                if (Player* player = ObjectAccessor::FindConnectedPlayer(guid))
                    Show(player, Party(group), group->GetLeaderGUID() == guid, group->GetLeaderGUID());
            }
            // The party keeps its board; the leaver plays their own again.
            void OnRemoveMember(Group* group, ObjectGuid guid, RemoveMethod, ObjectGuid, char const*) override
            {
                if (group->isBGGroup() || group->isBFGroup())
                    return;
                if (Player* player = ObjectAccessor::FindConnectedPlayer(guid))
                    Show(player, Solo(guid), true);
            }
            // Same board; only who may press "New bounties" moved.
            void OnChangeLeader(Group* group, ObjectGuid newLeader, ObjectGuid) override
            {
                if (group->isBGGroup() || group->isBFGroup())
                    return;
                for (Player* member : Online(Party(group)))
                    Show(member, Party(group), member->GetGUID() == newLeader);
            }
            // Runs before the members are taken out: each plays their own board again.
            void OnDisband(Group* group) override
            {
                if (group->isBGGroup() || group->isBFGroup())
                    return;
                std::vector<Player*> members = Online(Party(group));
                {
                    std::lock_guard<std::mutex> lock(boardMutex);
                    DropLocked(Party(group));
                }
                for (Player* member : members)
                    Show(member, Solo(member->GetGUID()), true);
            }
        };

        class BountyPlayer final : public PlayerScript
        {
        public:
            BountyPlayer()
                : PlayerScript("dc_bounties_player", {PLAYERHOOK_ON_DELETE_FROM_DB, PLAYERHOOK_ON_LOGOUT})
            {
            }
            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> lock(tripMutex);
                casting.erase(player->GetGUID().GetRawValue());
            }
            void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
            {
                {
                    std::lock_guard<std::mutex> lock(boardMutex);
                    boards.erase(Owner{0, guid});
                }
                trans->Append("DELETE FROM dc_bounties_board WHERE owner_kind=0 AND owner_id={}", guid);
            }
        };

        // The travel cast is Town Portal's kind of cast: its length is the tunable (the server's cast time is
        // the one the cast bar shows, from a SpellCastTimes row of that length), and moving, an interrupt or damage stops
        // it; death does, as for any cast.
        class TravelSpellData final : public GlobalScript
        {
        public:
            TravelSpellData()
                : GlobalScript("dc_bounty_travel_data", {GLOBALHOOK_ON_LOAD_SPELL_CUSTOM_ATTR})
            {
            }
            void OnLoadSpellCustomAttr(SpellInfo* info) override
            {
                if (info->Id != DC::Combat::Shells::BountyTravel)
                    return;
                info->InterruptFlags =
                    SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT | SPELL_INTERRUPT_FLAG_ABORT_ON_DMG;
                auto const ms = static_cast<int32>(DC::Tunables::Get("rifts", "bounty_travel_cast_ms"));
                for (uint32 id = 0; id < sSpellCastTimesStore.GetNumRows(); ++id)
                    if (auto* time = sSpellCastTimesStore.LookupEntry(id))
                        if (time->CastTime == ms)
                        {
                            info->CastTimeEntry = time;
                            return;
                        }
                LOG_ERROR("server",
                          "[DC bounties] no cast time of {} ms (rifts bounty_travel_cast_ms); the travel cast keeps its "
                          "spell's",
                          ms);
            }
        };

        class TravelCast final : public AllSpellScript
        {
        public:
            TravelCast()
                : AllSpellScript("dc_bounty_travel_cast", {ALLSPELLHOOK_ON_CAST})
            {
            }
            void OnSpellCast(Spell*, Unit* caster, SpellInfo const* info, bool) override
            {
                if (info->Id == DC::Combat::Shells::BountyTravel && caster)
                    if (Player* player = caster->ToPlayer())
                        TravelCastDone(player);
            }
        };

        // Any damage stops it, the module's own included, which goes around the core's pushback (as Town Portal's).
        class TravelDamage final : public UnitScript
        {
        public:
            TravelDamage()
                : UnitScript("dc_bounty_travel_damage", true, {UNITHOOK_ON_DAMAGE})
            {
            }
            void OnDamage(Unit*, Unit* victim, uint32& damage) override
            {
                if (!victim || !victim->IsPlayer() || !damage)
                    return;
                Spell* cast = victim->GetCurrentSpell(CURRENT_GENERIC_SPELL);
                if (cast && cast->GetSpellInfo()->Id == DC::Combat::Shells::BountyTravel &&
                    cast->getState() == SPELL_STATE_PREPARING)
                    victim->InterruptNonMeleeSpells(false, DC::Combat::Shells::BountyTravel);
            }
        };

        // GM check: the board in chat, a cell completed by hand (W2's objectives are the player's way), and the
        // button.
        class BountyCommand final : public CommandScript
        {
        public:
            BountyCommand()
                : CommandScript("dc_bounties_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable bounty = {{"show", HandleShow, SEC_GAMEMASTER, Console::No},
                                                  {"done", HandleDone, SEC_GAMEMASTER, Console::No},
                                                  {"new", HandleNew, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable dc = {{"bounty", bounty}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
            static bool HandleShow(ChatHandler* handler)
            {
                Player* player = handler->GetSession()->GetPlayer();
                Owner const owner = OwnerOf(player);
                std::lock_guard<std::mutex> lock(boardMutex);
                Board const& board = LoadLocked(owner);
                handler->PSendSysMessage("Bounties ({} board, {} live cells):", owner.kind ? "party" : "solo",
                                         board.size());
                for (unsigned column = 1; column <= Columns; ++column)
                    handler->PSendSysMessage("  column {}: {}", column, StateName(StateOf(board, column)));
                for (Cell const& c : board)
                {
                    Bounty const* b = Find(catalog, c.bounty);
                    handler->PSendSysMessage("  {}.{} bounty {} {} '{}' {}/{}{}", c.column, c.cell, c.bounty,
                                             b ? b->type : "?", b ? CellTitle(c, *b, targets) : "?", c.progress, c.need,
                                             c.done ? " done" : "");
                }
                return true;
            }
            static bool HandleDone(ChatHandler* handler, uint8 column, uint8 cell)
            {
                Player* player = handler->GetSession()->GetPlayer();
                std::uint32_t id = 0;
                {
                    std::lock_guard<std::mutex> lock(boardMutex);
                    for (Cell const& c : LoadLocked(OwnerOf(player)))
                        if (c.column == column && c.cell == cell)
                            id = c.bounty;
                }
                if (!id || !Complete(player, id))
                {
                    handler->PSendSysMessage("No open bounty at column {} cell {}.", column, cell);
                    return true;
                }
                return true;
            }
            static bool HandleNew(ChatHandler* handler)
            {
                if (std::string const why = Reroll(handler->GetSession()->GetPlayer()); !why.empty())
                    handler->SendSysMessage(why);
                return true;
            }
        };
    } // namespace

    bool Complete(Player* player, std::uint32_t id)
    {
        return Credit(player, id, [id](Board& board) { return DC::Bounties::Complete(board, id); });
    }

    bool AddProgress(Player* player, std::uint32_t id, std::uint32_t amount)
    {
        return Credit(player, id, [id, amount](Board& board) { return DC::Bounties::AddProgress(board, id, amount); });
    }

    bool Click(Player* player, std::uint32_t id, unsigned spot)
    {
        return Credit(player, id, [id, spot](Board& board) { return DC::Bounties::Click(board, id, spot); });
    }

    std::uint64_t OwnerKey(Player const* player)
    {
        Owner const owner = OwnerOf(player);
        return std::uint64_t(owner.kind) << 32 | owner.id;
    }

    std::vector<Open> OpenIn(Player* player, std::uint32_t mapId, std::uint32_t zoneId)
    {
        std::vector<Open> out;
        std::lock_guard<std::mutex> lock(boardMutex);
        for (Cell const& c : LoadLocked(OwnerOf(player)))
        {
            Bounty const* b = c.done ? nullptr : Find(catalog, c.bounty);
            if (!b || b->mapId != mapId || b->zoneId != zoneId || b->spots.empty())
                continue;
            Open open{b->id, b->type == "kill" ? c.target : 0, b->objectiveEntry};
            if (open.uniqueEntry)
                open.spots.push_back({0, b->spots.front()});
            else
                for (unsigned spot = 0; spot < b->spots.size() && spot < 32; ++spot)
                    if (c.objectives & (1u << spot))
                        open.spots.push_back({spot, b->spots[spot]});
            if (!open.spots.empty())
                out.push_back(std::move(open));
        }
        return out;
    }

    std::uint64_t Epoch()
    {
        return epoch;
    }

    QuestSync QuestsFor(Player* player, std::vector<QuestRow> const& rows, std::vector<std::uint32_t> const& held, bool here)
    {
        std::lock_guard<std::mutex> lock(boardMutex);
        return SyncQuests(LoadLocked(OwnerOf(player)), catalog, rows, held, here, player->GetMapId(), player->GetZoneId());
    }

    void ExpireBoardsOnLogin(Player* player)
    {
        // characters.logout_time is the last save's (the logout's); this login has not saved yet.
        auto lastOut = [](std::vector<ObjectGuid> const& guids) -> std::uint64_t
        {
            std::string list;
            for (ObjectGuid const& guid : guids)
                list += (list.empty() ? "" : ",") + std::to_string(guid.GetCounter());
            if (QueryResult row = CharacterDatabase.Query("SELECT MAX(logout_time) FROM characters WHERE guid IN ({})", list))
                return (*row)[0].Get<uint64>();
            return 0;
        };
        std::uint64_t const now = GameTime::GetGameTime().count();
        std::uint64_t const grace = DC::Rifts::LogoutGraceSeconds();
        auto away = [now](std::uint64_t at) { return now > at ? now - at : 0; };
        std::vector<Owner> gone;
        if (BoardExpired(false, away(lastOut({player->GetGUID()})), grace))
            gone.push_back(Solo(player->GetGUID()));
        if (Group* group = PartyGroup(player))
        {
            std::vector<ObjectGuid> members;
            bool online = false;
            for (auto const& slot : group->GetMemberSlots())
            {
                members.push_back(slot.guid);
                online = online || (slot.guid != player->GetGUID() && ObjectAccessor::FindConnectedPlayer(slot.guid));
            }
            // Gone for the whole party: every member left more than the grace ago, so their own boards (the next copy's
            // source is the leader's) are gone with it.
            if (BoardExpired(online, away(lastOut(members)), grace))
            {
                gone.push_back(Party(group));
                for (ObjectGuid const& member : members)
                    gone.push_back(Solo(member));
            }
        }
        if (gone.empty())
            return;
        std::lock_guard<std::mutex> lock(boardMutex);
        for (Owner const& owner : gone)
            DropLocked(owner);
        LOG_INFO("server", "[DC bounties] {} logged in after the grace: {} board(s) gone, a new one is drawn",
                 player->GetName(), gone.size());
    }

    bool IsBountyMap(std::uint32_t mapId)
    {
        return catalogMaps.count(mapId) != 0;
    }

    void RegisterScripts()
    {
        new BountyWorld();
        new BountyGroup();
        new BountyPlayer();
        new BountyCommand();
        new TravelSpellData();
        new TravelCast();
        new TravelDamage();
        RegisterObjectiveScripts();
        RegisterCacheScripts();
        RegisterQuestScripts();
        // The window's budget is the artisan windows' rows, as DCRIFTENROLL's (docs/contracts/window-bridge.md,
        // Budget).
        if (!DC::Bridge::Routes().Add(WINDOW, {"crafting", "artisan_burst", "artisan_per_second"}, Window))
            LOG_ERROR("server", "[DC bounties] the {} window route was not registered", WINDOW);
    }
} // namespace DC::Bounties
