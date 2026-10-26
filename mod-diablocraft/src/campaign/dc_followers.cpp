/*
 * World of DiabloCraft - the followers: who a player has hired, and the companion's life beside them.
 *
 * A follower is a permanent companion, not a summon. The hired one (one row in dc_character_follower, kept across
 * logins) stands beside its player whenever the player is alone, on every map: a player's update asks the rules
 * (dc_follower_rules.h Tick) every quarter second whether it should be out, and puts it back at the player's side if it
 * is not (login, a map change, a Town Portal, a rift, a revive). There is no spell, timer or re-summon. The
 * creature's own AI and the hub gossip are dc_follower_creature.cpp. Contract: docs/contracts/followers.md.
 */

#include "dc_follower_internal.h"
#include "../common/dc_world.h"

#include "Creature.h"
#include "DatabaseEnv.h"
#include "Group.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "PetDefines.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "TemporarySummon.h"

#include <array>
#include <list>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Campaign::Followers
{
    static_assert(FollowAngle == PET_FOLLOW_ANGLE, "the companion walks at the stock pet's side");

    namespace
    {
        // How often a player's update asks the rules; the revive and party timers run on the time they were given.
        constexpr std::uint32_t TickMs = 250;

        // The rows dc_follower_rule must hold (data/d3/followers_rules.csv).
        constexpr unsigned RuleCount = 4;

        struct Roster
        {
            std::array<Row, Count> rows;
            Rules rules;
            bool ready = false;
        };

        // Written once at startup, before any player exists, and only read after.
        Roster roster;

        struct State
        {
            Id hired = Id::None;
            Clock clock;
            ObjectGuid companion;
            std::uint32_t sinceTickMs = 0;
        };

        std::mutex stateMutex;
        std::unordered_map<ObjectGuid, State> states;

        bool LoadRules(Rules& rules)
        {
            QueryResult result = WorldDatabase.Query("SELECT rule, value FROM dc_follower_rule");
            if (!result)
                return false;
            double revive = 0, partyLeave = 0, catchUp = 0, yards = 0;
            unsigned found = 0;
            do
            {
                Field* fields = result->Fetch();
                std::string const name = fields[0].Get<std::string>();
                double const value = fields[1].Get<double>();
                if (name == "revive_seconds")
                    revive = value;
                else if (name == "party_leave_seconds")
                    partyLeave = value;
                else if (name == "catch_up_seconds")
                    catchUp = value;
                else if (name == "catch_up_yards")
                    yards = value;
                else
                    continue;
                ++found;
            } while (result->NextRow());
            rules.reviveMs = std::uint32_t(revive * 1000);
            rules.partyLeaveMs = std::uint32_t(partyLeave * 1000);
            rules.catchUpMs = std::uint32_t(catchUp * 1000);
            rules.catchUpYards = float(yards);
            // The party rule may be zero, so a missing row is told from a zero one by the count.
            return found == RuleCount && partyLeave >= 0 && Usable(rules);
        }

        void LoadRoster()
        {
            roster = Roster{};
            QueryResult result =
                WorldDatabase.Query("SELECT follower_id, entry, name FROM dc_follower ORDER BY follower_id");
            if (!result)
            {
                LOG_WARN("server", "[DC followers] dc_follower is empty or missing: followers are off");
                return;
            }
            unsigned seen = 0;
            do
            {
                Field* fields = result->Fetch();
                unsigned const id = fields[0].Get<std::uint8_t>();
                if (!Valid(id) || roster.rows[id - 1].id != Id::None)
                {
                    LOG_ERROR("server",
                              "[DC followers] dc_follower has a bad or repeated follower_id {}: followers are off", id);
                    return;
                }
                roster.rows[id - 1] = {Id(id), fields[1].Get<std::uint32_t>(), fields[2].Get<std::string>()};
                ++seen;
            } while (result->NextRow());
            if (seen != Count)
            {
                LOG_ERROR("server", "[DC followers] dc_follower holds {} of {} followers: followers are off", seen,
                          Count);
                return;
            }
            if (!LoadRules(roster.rules))
            {
                LOG_ERROR("server",
                          "[DC followers] dc_follower_rule is missing a rule or holds a bad one: followers are off");
                return;
            }
            // A roster row whose look is not chosen yet has no creature template (generate_followers.py).
            for (Row const& row : roster.rows)
                if (!sObjectMgr->GetCreatureTemplate(row.entry))
                {
                    LOG_WARN("server",
                             "[DC followers] follower {} (entry {}) has no creature template yet: followers are off",
                             row.name, row.entry);
                    return;
                }
            roster.ready = true;
            LOG_INFO("server", "[DC followers] {} followers ready", Count);
        }

        bool Alone(Player const* player)
        {
            Group const* group = player->GetGroup();
            return !group || group->GetMembersCount() <= 1;
        }

        void Unsummon(Creature* creature)
        {
            if (TempSummon* summon = creature ? creature->ToTempSummon() : nullptr)
                summon->UnSummon();
        }

        // The companion standing now: alive, in this player's map, and of the follower hired.
        Creature* Standing(Player* player, ObjectGuid guid, Id hired)
        {
            Creature* creature = guid ? ObjectAccessor::GetCreature(*player, guid) : nullptr;
            if (!creature || !creature->IsInWorld() || !creature->IsAlive())
                return nullptr;
            Row const* row = ById(hired);
            return row && creature->GetEntry() == row->entry ? creature : nullptr;
        }

        // The hub copy of a follower is shown or hidden per player (OutFor, asked by the creature's CanBeSeen); when the
        // companion appears or goes, the copies near the player are asked to decide again, so the copy leaves the hiring
        // player's view at once and comes back at once.
        void RefreshHub(Player* player)
        {
            std::vector<std::uint32_t> entries;
            for (Row const& row : roster.rows)
                entries.push_back(row.entry);
            std::list<Creature*> copies;
            player->GetCreatureListWithEntryInGrid(copies, entries, player->GetVisibilityRange());
            for (Creature* copy : copies)
                if (!copy->GetOwnerGUID())
                    player->UpdateVisibilityOf(copy);
        }

        // Puts the companion at the player's side, on the flank the stock pet walks on.
        void Appear(Player* player, Row const& row)
        {
            float x, y, z;
            player->GetClosePoint(x, y, z, player->GetCombatReach(), PET_FOLLOW_DIST, FollowAngle);
            SetNextSummonLevel(player->GetLevel());
            TempSummon* summon =
                player->SummonCreature(row.entry, x, y, z, player->GetOrientation(), TEMPSUMMON_CORPSE_DESPAWN, 0);
            SetNextSummonLevel(0);
            if (!summon)
            {
                LOG_ERROR("server", "[DC followers] {} could not be summoned beside {}", row.name, player->GetName());
                return;
            }
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found != states.end())
                    found->second.companion = summon->GetGUID();
            }
            RefreshHub(player);
        }

        // One step for one player; `force` skips the quarter-second wait (a hire or a dismissal shows at once).
        void Step(Player* player, std::uint32_t diff, bool force)
        {
            if (!roster.ready || !player->IsInWorld())
                return;
            Id hired;
            ObjectGuid companion;
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found == states.end())
                    return;
                State& state = found->second;
                state.sinceTickMs += diff;
                if (!force && state.sinceTickMs < TickMs)
                    return;
                diff = state.sinceTickMs;
                state.sinceTickMs = 0;
                hired = state.hired;
                companion = state.companion;
            }
            Creature* current = Standing(player, companion, hired);
            Situation const now{hired != Id::None, Alone(player), player->IsAlive(), current != nullptr};
            bool want;
            {
                std::lock_guard<std::mutex> lock(stateMutex);
                auto found = states.find(player->GetGUID());
                if (found == states.end())
                    return;
                want = Tick(found->second.clock, diff, now, roster.rules);
            }
            if (!want)
            {
                Unsummon(current ? current : (companion ? ObjectAccessor::GetCreature(*player, companion) : nullptr));
                if (companion)
                {
                    // The companion is gone from the player's side (a party, a fall, a dismissal): its hub copy is
                    // theirs to see again, and the removal that is still queued must not count as standing.
                    {
                        std::lock_guard<std::mutex> lock(stateMutex);
                        auto found = states.find(player->GetGUID());
                        if (found != states.end() && found->second.companion == companion)
                            found->second.companion = ObjectGuid::Empty;
                    }
                    RefreshHub(player);
                }
                return;
            }
            if (current || player->IsBeingTeleported() || !player->IsAlive())
                return;
            // A creature left from an older hire, or one that fell (not yet removed): clear it before the new one
            // stands.
            if (companion)
                Unsummon(ObjectAccessor::GetCreature(*player, companion));
            if (Row const* row = ById(hired))
                Appear(player, *row);
        }

        void Save(Player const* player, Id follower)
        {
            std::uint32_t const guid = player->GetGUID().GetCounter();
            if (follower == Id::None)
                CharacterDatabase.Execute("DELETE FROM dc_character_follower WHERE guid={}", guid);
            else
                CharacterDatabase.Execute("REPLACE INTO dc_character_follower (guid, follower) VALUES ({}, {})", guid,
                                          std::uint32_t(follower));
        }

        class Startup final : public WorldScript
        {
        public:
            Startup()
                : WorldScript("dc_follower_startup", {WORLDHOOK_ON_STARTUP})
            {
            }

            void OnStartup() override
            {
                LoadRoster();
            }
        };

        class Players final : public PlayerScript
        {
        public:
            Players()
                : PlayerScript("dc_follower_player", {PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_BEFORE_LOGOUT,
                                                      PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_DELETE_FROM_DB})
            {
            }

            void OnPlayerLogin(Player* player) override
            {
                Id hired = Id::None;
                if (QueryResult row = CharacterDatabase.Query(
                        "SELECT follower FROM dc_character_follower WHERE guid={}", player->GetGUID().GetCounter()))
                {
                    unsigned const raw = (*row)[0].Get<std::uint8_t>();
                    if (Valid(raw))
                        hired = Id(raw);
                }
                std::lock_guard<std::mutex> lock(stateMutex);
                State& state = states[player->GetGUID()];
                state = State{};
                state.hired = hired;
            }

            void OnPlayerBeforeLogout(Player* player) override
            {
                ObjectGuid companion;
                {
                    std::lock_guard<std::mutex> lock(stateMutex);
                    auto found = states.find(player->GetGUID());
                    if (found == states.end())
                        return;
                    companion = found->second.companion;
                    states.erase(found);
                }
                if (companion)
                    Unsummon(ObjectAccessor::GetCreature(*player, companion));
            }

            void OnPlayerUpdate(Player* player, std::uint32_t diff) override
            {
                Step(player, diff, false);
            }

            void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
            {
                trans->Append("DELETE FROM dc_character_follower WHERE guid={}", guid);
            }
        };
    } // namespace

    Row const* ById(Id id)
    {
        return roster.ready && Valid(unsigned(id)) ? &roster.rows[unsigned(id) - 1] : nullptr;
    }

    Row const* ByEntry(std::uint32_t entry)
    {
        if (!roster.ready)
            return nullptr;
        for (Row const& row : roster.rows)
            if (row.entry == entry)
                return &row;
        return nullptr;
    }

    Rules const& CurrentRules()
    {
        return roster.rules;
    }

    bool OutFor(Player const* viewer, std::uint32_t entry)
    {
        ObjectGuid companion;
        Id hired;
        {
            std::lock_guard<std::mutex> lock(stateMutex);
            auto found = states.find(viewer->GetGUID());
            if (found == states.end())
                return false;
            companion = found->second.companion;
            hired = found->second.hired;
        }
        Row const* row = companion ? ById(hired) : nullptr;
        if (!row || row->entry != entry)
            return false;
        Creature const* creature = ObjectAccessor::GetCreature(*viewer, companion);
        return creature && creature->IsInWorld() && creature->GetEntry() == entry;
    }

    bool IsCompanionOf(ObjectGuid owner, ObjectGuid companion)
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        auto found = states.find(owner);
        return found != states.end() && found->second.companion == companion;
    }

    void OnCompanionFell(ObjectGuid owner)
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        auto found = states.find(owner);
        if (found != states.end())
            Fell(found->second.clock, roster.rules);
    }

    std::uint32_t EntryOf(Id follower)
    {
        Row const* row = ById(follower);
        return row ? row->entry : 0;
    }

    Id Hired(Player const* player)
    {
        std::lock_guard<std::mutex> lock(stateMutex);
        auto found = states.find(player->GetGUID());
        return found == states.end() ? Id::None : found->second.hired;
    }

    bool Hire(Player* player, Id follower)
    {
        if (!roster.ready || !ById(follower))
            return false;
        {
            std::lock_guard<std::mutex> lock(stateMutex);
            auto found = states.find(player->GetGUID());
            if (found == states.end())
                return false;
            if (found->second.hired == follower)
                return true;
            found->second.hired = follower;
            found->second.clock = Clock{};
        }
        Save(player, follower);
        Step(player, 0, true);
        return true;
    }

    void Dismiss(Player* player)
    {
        {
            std::lock_guard<std::mutex> lock(stateMutex);
            auto found = states.find(player->GetGUID());
            if (found == states.end() || found->second.hired == Id::None)
                return;
            found->second.hired = Id::None;
            found->second.clock = Clock{};
        }
        Save(player, Id::None);
        Step(player, 0, true);
    }

    Creature* Companion(Player* player)
    {
        ObjectGuid companion;
        Id hired;
        {
            std::lock_guard<std::mutex> lock(stateMutex);
            auto found = states.find(player->GetGUID());
            if (found == states.end())
                return nullptr;
            companion = found->second.companion;
            hired = found->second.hired;
        }
        return Standing(player, companion, hired);
    }
} // namespace DC::Campaign::Followers

namespace DC::Campaign
{
    void RegisterScripts()
    {
        new Followers::Startup();
        new Followers::Players();
        Followers::RegisterCreatureScripts();
    }
} // namespace DC::Campaign
