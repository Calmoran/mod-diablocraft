/*
 * World of DiabloCraft - Urshi, the legendary gem upgrader (contract
 * docs/contracts/urshi-messages.md).
 *
 * After an in-time Guardian kill (CompleteGuardianKill -> BeginUrshi) Urshi stands where it fell and every member of
 * the run still enrolled and online gets their own tries: gr_urshi_tries_base, one more if they did not die in the
 * run, a Hardcore character always the one more. She stays while any member has tries (UrshiTick, on the rift map's
 * own update, sends her away). The `DCURSHI` route lists the member's legendary gems (worn, then bags and stash, each
 * by rank highest first) with the chance at the run's level and rolls one upgrade at a time on the gem the client
 * names.
 *
 * Every way of closing the run is refused while a member still has tries (UrshiBlocksClose, asked by Close() and
 * HandleTurnIn); a member who leaves the party, is kicked or logs out loses theirs (UrshiMemberLeft). The tries live in
 * memory with the run. The decisions with no core in them are dc_gr_urshi.h, which the test compiles.
 */

#include "dc_gr_urshi.h"

#include "dc_rift_quests.h"
#include "dc_rifts_internal.h"
#include "../common/dc_bridge.h"
#include "../common/dc_legendary_gem.h"
#include "../hardcore/dc_hardcore.h"
#include "../items/dc_items.h"

#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "SpellAuras.h"
#include "WorldSession.h"

#include <algorithm>
#include <map>
#include <mutex>
#include <string>
#include <vector>

namespace DC::Rifts
{
    namespace
    {
        // Stock 3.3.5 spell 62893 "Blue Skybeam" (Ulduar): a self dummy aura whose only content is a pale blue column of light, put on Urshi while she
        // is up. It ships nothing: the client's own data. Not in the sheets, because it is a look, not a number.
        constexpr std::uint32_t URSHI_BEAM_SPELL = 62893;

        // Constant: Urshi's creature entry. generate_rifts.py URSHI_ENTRY writes its template (rifts_0017_urshi.sql).
        constexpr std::uint32_t URSHI_ENTRY = 910061;
        constexpr char const* PREFIX = "DCURSHI";
        // Constant: the legendary gem item block (legendary-gems.md: entries 103100-103120, append-only inside
        // 103100-103199), the stash query's filter.
        constexpr char const* GEM_ENTRIES = "BETWEEN 103100 AND 103199";

        struct Member
        {
            std::string name;
            unsigned left = 0, total = 0;
        };

        struct Run
        {
            ObjectGuid npc;
            unsigned level = 0;
            bool gone = false;                       // she has left; kept so a retried payout does not spawn her again
            std::map<std::uint32_t, Member> members; // by character guid
        };

        std::mutex urshiMutex;
        std::map<std::uint32_t, Run> runs; // by instance id

        unsigned Count(char const* name)
        {
            return static_cast<unsigned>(Tunables::Get("rifts", name));
        }

        double Yards(char const* name)
        {
            return Tunables::Get("rifts", name);
        }

        // Where she stands: `gr_urshi_spawn_yards` from the Guardian's spot, towards the players (the centre of the run members on the floor) and
        // failing that to either side and last away from them, the first spot the core finds on the ground with line of sight and no great climb;
        // the Guardian's own spot when none fits. She faces the players.
        Position UrshiSpot(Creature* guardian, bool players, double playersX, double playersY)
        {
            Position const home(guardian->GetPositionX(), guardian->GetPositionY(), guardian->GetPositionZ(), guardian->GetOrientation());
            double const wanted = Yards("gr_urshi_spawn_yards");
            double const toward = players ? Gr::FacingAngle(home.GetPositionX(), home.GetPositionY(), playersX, playersY, home.GetOrientation())
                                          : home.GetOrientation();
            for (double angle : Gr::SpawnAngles(toward))
            {
                // The core's walk takes its angle from the Guardian's own facing.
                Position found = guardian->GetFirstCollisionPosition(static_cast<float>(wanted), static_cast<float>(angle - guardian->GetOrientation()));
                if (!Gr::SpotFits(wanted, guardian->GetExactDist2d(found.GetPositionX(), found.GetPositionY()), found.GetPositionZ() - home.GetPositionZ(),
                                  guardian->IsWithinLOS(found.GetPositionX(), found.GetPositionY(), found.GetPositionZ()),
                                  Yards("gr_urshi_spawn_min_share_pct"), Yards("gr_urshi_spawn_max_climb_yards")))
                    continue;
                found.SetOrientation(static_cast<float>(
                    players ? Gr::FacingAngle(found.GetPositionX(), found.GetPositionY(), playersX, playersY, home.GetOrientation()) : home.GetOrientation()));
                return found;
            }
            return home;
        }

        // The blue column over her while she is up: the aura has no end of its own, and goes with her creature.
        void ShowBeam(Creature* urshi)
        {
            if (Aura* beam = urshi->AddAura(URSHI_BEAM_SPELL, urshi))
            {
                beam->SetMaxDuration(-1);
                beam->SetDuration(-1);
            }
        }

        Gr::ChanceTable Chances()
        {
            static char const* const names[Gr::ChanceBands] = {
                "gr_gem_chance_plus_10_or_more", "gr_gem_chance_plus_9",        "gr_gem_chance_plus_8",
                "gr_gem_chance_plus_7",          "gr_gem_chance_plus_0_to_6",   "gr_gem_chance_minus_1",
                "gr_gem_chance_minus_2",         "gr_gem_chance_minus_3",       "gr_gem_chance_minus_4",
                "gr_gem_chance_minus_5",         "gr_gem_chance_minus_6_to_15", "gr_gem_chance_minus_16_or_less"};
            Gr::ChanceTable table{};
            for (std::size_t band = 0; band < Gr::ChanceBands; ++band)
                table[band] = Count(names[band]);
            return table;
        }

        void Send(Player* player, std::vector<std::string> const& fields)
        {
            DC::Bridge::Push(player, PREFIX, fields);
        }

        // --- the gems a character owns, in the places it is read ------------------------------------------

        std::string GemName(std::string const& gemId, std::uint32_t entry)
        {
            if (DC::LegendaryGem::Row const* gem = DC::LegendaryGem::Find(gemId))
                return gem->name;
            if (ItemTemplate const* proto = sObjectMgr->GetItemTemplate(entry))
                return proto->Name1;
            return gemId;
        }

        unsigned MaxRankOf(std::string const& gemId)
        {
            DC::LegendaryGem::Row const* gem = DC::LegendaryGem::Find(gemId);
            return gem && gem->maxRank ? *gem->maxRank : 0;
        }

        // Worn gems (the socket rows of the worn items), then the bags, then the stash, ordered by the contract's rule.
        // Other characters' gems and the bank are not read.
        std::vector<Gr::GemRow> ReadGems(Player* player)
        {
            std::vector<Gr::GemRow> out;
            std::string wornGuids;
            for (std::uint8_t slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
                if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                    wornGuids += (wornGuids.empty() ? "" : ",") + std::to_string(item->GetGUID().GetCounter());
            if (!wornGuids.empty())
                if (QueryResult rows = CharacterDatabase.Query(
                        "SELECT item_guid,seq,affix_id,gem_entry,legendary_rank FROM dc_item_affix "
                        "WHERE kind='gem' AND legendary_rank IS NOT NULL AND item_guid IN (" +
                        wornGuids +
                        ") "
                        "ORDER BY item_guid,seq"))
                    do
                    {
                        Field* fields = rows->Fetch();
                        Gr::GemRow gem;
                        gem.guid = fields[0].Get<std::uint32_t>();
                        gem.seq = fields[1].Get<std::uint32_t>();
                        std::string const gemId = fields[2].Get<std::string>();
                        gem.id = Gr::WornGemId(gem.guid, gem.seq);
                        gem.where = Gr::Where::Worn;
                        gem.entry = fields[3].Get<std::uint32_t>();
                        gem.name = GemName(gemId, gem.entry);
                        gem.rank = fields[4].Get<std::uint32_t>();
                        gem.maxRank = MaxRankOf(gemId);
                        out.push_back(gem);
                    } while (rows->NextRow());

            std::vector<Gr::GemRow> loose; // bags and stash; their ranks are read below in one query
            auto addGem = [&](std::uint64_t guid, std::uint32_t entry, Gr::Where where)
            {
                std::optional<DC::Items::LegendaryGemItem> item = DC::Items::LegendaryGemItemOf(entry);
                if (!item)
                    return;
                Gr::GemRow gem;
                gem.guid = guid;
                gem.id = Gr::BagGemId(guid);
                gem.where = where;
                gem.entry = entry;
                gem.name = GemName(item->gemId, entry);
                gem.maxRank = MaxRankOf(item->gemId);
                loose.push_back(gem);
            };
            auto scan = [&](Item* item)
            {
                if (item)
                    addGem(item->GetGUID().GetCounter(), item->GetEntry(), Gr::Where::Bags);
            };
            for (std::uint8_t slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
                scan(player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));
            for (std::uint8_t container = INVENTORY_SLOT_BAG_START; container < INVENTORY_SLOT_BAG_END; ++container)
                if (Bag* pack = player->GetBagByPos(container))
                    for (std::uint32_t position = 0; position < pack->GetBagSize(); ++position)
                        scan(pack->GetItemByPos(static_cast<std::uint8_t>(position)));
            if (player->GetSession())
                if (QueryResult rows =
                        CharacterDatabase.Query("SELECT s.item_guid,i.itemEntry FROM dc_account_stash_item s "
                                                "JOIN item_instance i ON i.guid=s.item_guid "
                                                "WHERE s.account_id={} AND s.mode='{}' AND i.itemEntry {}",
                                                player->GetSession()->GetAccountId(),
                                                DC::Hardcore::IsHardcore(player) ? "hardcore" : "normal", GEM_ENTRIES))
                    do
                    {
                        Field* fields = rows->Fetch();
                        addGem(fields[0].Get<std::uint32_t>(), fields[1].Get<std::uint32_t>(), Gr::Where::Stash);
                    } while (rows->NextRow());
            if (!loose.empty())
            {
                std::string guids;
                for (Gr::GemRow const& gem : loose)
                    guids += (guids.empty() ? "" : ",") + std::to_string(gem.guid);
                std::map<std::uint64_t, unsigned> ranks;
                if (QueryResult rows = CharacterDatabase.Query(
                        "SELECT item_guid,gem_rank FROM dc_legendary_gem_rank WHERE item_guid IN (" + guids + ")"))
                    do
                        ranks[(*rows)[0].Get<std::uint32_t>()] = (*rows)[1].Get<std::uint32_t>();
                    while (rows->NextRow());
                for (Gr::GemRow& gem : loose) // a gem with no row is rank 0 (legendary-gems.md)
                    if (auto found = ranks.find(gem.guid); found != ranks.end())
                        gem.rank = found->second;
            }
            out.insert(out.end(), loose.begin(), loose.end());
            Gr::OrderGems(out);
            return out;
        }

        // --- a member's window ---------------------------------------------------------------------------------

        struct Seat
        {
            unsigned level = 0, left = 0, total = 0;
        };

        // The character's seat in the Urshi of the map it stands on: she is there, alive and within reach, and the
        // character is one of the run's members. Refuses with the contract's texts; `needTries` also refuses a member
        // with none left.
        Seat SeatOf(Player& player, bool needTries)
        {
            if (!player.IsAlive())
                throw DC::Bridge::Refusal("You cannot do that while dead.");
            Map* map = player.GetMap();
            Seat seat;
            ObjectGuid npcGuid;
            {
                std::lock_guard<std::mutex> lock(urshiMutex);
                auto run = map && map->IsDungeon() ? runs.find(map->GetInstanceId()) : runs.end();
                if (run != runs.end() && !run->second.gone)
                {
                    npcGuid = run->second.npc;
                    seat.level = run->second.level;
                    if (auto member = run->second.members.find(player.GetGUID().GetCounter());
                        member != run->second.members.end())
                    {
                        seat.left = member->second.left;
                        seat.total = member->second.total;
                    }
                }
            }
            Creature* npc = npcGuid ? map->GetCreature(npcGuid) : nullptr;
            if (!npc || !npc->IsAlive() || !player.IsWithinDistInMap(npc, INTERACTION_DISTANCE))
                throw DC::Bridge::Refusal("Urshi is not near you.");
            if (!seat.total || (needTries && !seat.left))
                throw DC::Bridge::Refusal("Urshi has nothing more for you.");
            return seat;
        }

        // W, L, G x n, E: the list reply.
        void SendList(Player& player, Seat const& seat, std::vector<Gr::GemRow> const& gems)
        {
            Gr::ChanceTable const table = Chances();
            Send(&player, {"W", std::to_string(seat.level), std::to_string(seat.left), std::to_string(seat.total)});
            Send(&player, {"L", std::to_string(gems.size())});
            for (Gr::GemRow const& gem : gems)
            {
                bool const full = Gr::AtMaxRank(gem.rank, gem.maxRank);
                Send(&player, {"G", gem.id, std::string(1, static_cast<char>(gem.where)), std::to_string(gem.entry),
                               gem.name, std::to_string(gem.rank), std::to_string(gem.maxRank), full ? "1" : "0",
                               std::to_string(full ? 0u : Gr::UpgradeChance(seat.level, gem.rank, table))});
            }
            Send(&player, {"E", "list"});
        }

        void Upgrade(Player& player, std::string const& id)
        {
            Seat const seat = SeatOf(player, true);
            std::vector<Gr::GemRow> gems = ReadGems(&player);
            auto found = std::find_if(gems.begin(), gems.end(), [&](Gr::GemRow const& gem) { return gem.id == id; });
            if (found == gems.end())
            {
                SendList(player, seat, gems);
                throw DC::Bridge::Refusal("That gem is not there any more.");
            }
            if (Gr::AtMaxRank(found->rank, found->maxRank))
                throw DC::Bridge::Refusal(found->name + " is at its maximum rank.");
            // The try is spent first, so a roll can never be had for free.
            unsigned left = 0;
            {
                std::lock_guard<std::mutex> lock(urshiMutex);
                auto run = runs.find(player.GetMap()->GetInstanceId());
                Member* member = nullptr;
                if (run != runs.end())
                    if (auto mine = run->second.members.find(player.GetGUID().GetCounter());
                        mine != run->second.members.end())
                        member = &mine->second;
                if (!member || !member->left)
                    throw DC::Bridge::Refusal("You have no upgrade attempts left.");
                left = --member->left;
            }
            bool const landed = Gr::Succeeds(Gr::UpgradeChance(seat.level, found->rank, Chances()), Roll());
            if (landed)
            {
                if (found->where == Gr::Where::Worn)
                {
                    // The sheet comes off before the row changes and goes back on after it is written, as socketing
                    // does (Apply() re-reads the rows), so the gem's power follows the new rank at once.
                    Item* host = player.GetItemByGuid(ObjectGuid::Create<HighGuid::Item>(found->guid));
                    DC::Items::RemoveContributions(&player, host);
                    CharacterDatabase.DirectExecute("UPDATE dc_item_affix SET legendary_rank={} WHERE item_guid={} "
                                                    "AND seq={} AND kind='gem' AND legendary_rank IS NOT NULL",
                                                    found->rank + 1, found->guid, found->seq);
                    DC::Items::RefreshContributions(&player, host);
                }
                else
                    CharacterDatabase.DirectExecute("REPLACE INTO dc_legendary_gem_rank(item_guid,gem_rank) "
                                                    "VALUES({},{})",
                                                    found->guid, found->rank + 1);
                ++found->rank;
            }
            Send(&player, {"U", id, landed ? "1" : "0", std::to_string(found->rank), std::to_string(left)});
            Gr::OrderGems(gems);
            Seat after = seat;
            after.left = left;
            SendList(player, after, gems);
        }

        void Handle(Player& player, DC::Bridge::Request const& request, DC::Bridge::Wire<Player> const&)
        {
            std::optional<std::string> const verb = request.Token(0, 8);
            if (verb && *verb == "list" && request.Count() == 1)
            {
                Seat const seat = SeatOf(player, false);
                SendList(player, seat, ReadGems(&player));
                return;
            }
            std::optional<std::string> const id = request.Token(1, 24);
            if (verb && *verb == "upgrade" && request.Count() == 2 && id)
            {
                Upgrade(player, *id);
                return;
            }
            throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
        }

        // Talking to her opens the window: the server pushes W and the list.
        class UrshiCreature final : public CreatureScript
        {
        public:
            UrshiCreature()
                : CreatureScript("dc_urshi")
            {
            }
            bool OnGossipHello(Player* player, Creature*) override
            {
                CloseGossipMenuFor(player);
                try
                {
                    Seat const seat = SeatOf(*player, true);
                    SendList(*player, seat, ReadGems(player));
                }
                catch (DC::Bridge::Refusal const& refusal)
                {
                    if (player->GetSession())
                        ChatHandler(player->GetSession()).SendSysMessage(refusal.what());
                }
                return true;
            }
        };
    } // namespace

    void BeginUrshi(Creature* guardian, Rift const& rift)
    {
        Map* map = guardian ? guardian->GetMap() : nullptr;
        if (!map || rift.mode != "gr" || rift.outcome != Gr::OutcomeName(true))
            return;
        {
            std::lock_guard<std::mutex> lock(urshiMutex);
            if (runs.count(rift.instanceId))
                return; // a retried payout reaches here again (rift is seen from the Guardian's floor: its instance)
        }
        Run run;
        run.level = rift.grRank;
        double playersX = 0, playersY = 0;
        unsigned onFloor = 0;
        for (ObjectGuid const& guid : EnrolledGuids(rift.id))
        {
            Player* member = ObjectAccessor::FindPlayer(guid);
            if (!member || !member->IsInWorld())
                continue;
            if (member->GetMap() == map)
            {
                playersX += member->GetPositionX();
                playersY += member->GetPositionY();
                ++onFloor;
            }
            Member seat;
            seat.name = member->GetName();
            seat.total = seat.left =
                Gr::Tries(Count("gr_urshi_tries_base"), Count("gr_urshi_tries_no_death_bonus"),
                          GreaterRiftDeaths(rift.id, guid.GetCounter()), DC::Hardcore::IsHardcore(member));
            if (seat.total)
                run.members[guid.GetCounter()] = seat;
        }
        if (run.members.empty())
            return;
        Creature* urshi = map->SummonCreature(
            URSHI_ENTRY, UrshiSpot(guardian, onFloor > 0, onFloor ? playersX / onFloor : 0.0, onFloor ? playersY / onFloor : 0.0));
        if (!urshi)
        {
            LOG_ERROR("server", "[DC rifts] Urshi (entry {}) did not spawn for Greater Rift {}; no upgrades this run",
                      URSHI_ENTRY, rift.id);
            return;
        }
        ShowBeam(urshi);
        run.npc = urshi->GetGUID();
        std::lock_guard<std::mutex> lock(urshiMutex);
        runs[rift.instanceId] = run;
    }

    // Urshi stands on the floor the Guardian died on and her state is kept by that floor's instance; the run-wide questions
    // (who holds the close, who left) ask every floor the run has.
    namespace
    {
        std::vector<std::uint32_t> InstancesOf(std::uint64_t runId)
        {
            std::vector<std::uint32_t> out;
            std::lock_guard<std::mutex> lock(riftMutex);
            for (Floor const& floor : live.Floors(runId))
                out.push_back(floor.instanceId);
            return out;
        }
    } // namespace

    std::string UrshiBlocksClose(std::uint64_t runId)
    {
        std::vector<std::uint32_t> const instances = InstancesOf(runId);
        std::vector<std::string> holders;
        {
            std::lock_guard<std::mutex> lock(urshiMutex);
            for (std::uint32_t instanceId : instances)
            {
                auto run = runs.find(instanceId);
                if (run != runs.end() && !run->second.gone)
                    for (auto const& [guid, member] : run->second.members)
                        if (member.left)
                            holders.push_back(member.name);
            }
        }
        return holders.empty() ? std::string() : Gr::CloseRefusal(holders);
    }

    void UrshiMemberLeft(std::uint64_t runId, ObjectGuid member, Player* notify)
    {
        std::vector<std::uint32_t> const instances = InstancesOf(runId);
        bool had = false;
        {
            std::lock_guard<std::mutex> lock(urshiMutex);
            for (std::uint32_t instanceId : instances)
            {
                auto run = runs.find(instanceId);
                if (run != runs.end() && run->second.members.erase(member.GetCounter()))
                    had = true;
            }
        }
        if (!had)
            return;
        if (notify)
            Send(notify, {"C", "You left the party, so Urshi has nothing more for you."});
    }

    // The rift map's own update: when nobody holds a try any more she goes. Her creature belongs to this map, so the
    // despawn happens on this map's thread, whoever used the last try or left.
    void UrshiTick(Map* map)
    {
        ObjectGuid npc;
        {
            std::lock_guard<std::mutex> lock(urshiMutex);
            auto run = runs.find(map->GetInstanceId());
            if (run == runs.end() || run->second.gone)
                return;
            for (auto const& [guid, member] : run->second.members)
                if (member.left)
                    return;
            run->second.gone = true;
            npc = run->second.npc;
        }
        if (Creature* urshi = map->GetCreature(npc))
            urshi->DespawnOrUnsummon();
    }

    void EndUrshi(std::uint32_t instanceId)
    {
        std::lock_guard<std::mutex> lock(urshiMutex);
        runs.erase(instanceId);
    }

    void RegisterUrshiScripts()
    {
        new UrshiCreature();
        DC::Bridge::Routes().Add(PREFIX, {"rifts", "urshi_burst", "urshi_per_second"}, Handle);
    }
} // namespace DC::Rifts
