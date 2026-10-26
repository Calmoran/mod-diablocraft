/*
 * World of DiabloCraft - rift progress and the Greater Rift timer.
 *
 * The one bar of both rift types, in D3's units (monster-spawning.md 3.9.4): hundredths of a progress point,
 * 65,000 filling it.
 *   progress by monster       - the kill hook asks KillUnits; a monster adds its own D3 points from
 *                               dc_monster_progress (warpath's table through the roster), a monster with no
 *                               row the default (rifts/monster_progress_default_points); a pack member, an
 *                               elite and a normal monster are the same
 *   progress orbs             - when a promoted pack's orbs fall (Gr::OrbsFall), DropGreaterOrbs summons the
 *                               mode's count (champion or rare) of GENERIC gameobjects round the body, purple
 *                               in a Greater Rift and orange in a Nephalem Rift; the map's own update
 *                               (GreaterTick) hands one to the run member who walks within the pickup radius
 *                               and adds its points to the run, once
 *   the clock                 - the run's deadline is dc_rift.deadline; GreaterTick marks the
 *                               run expired the second it passes with no result, and the Guardian
 *                               still spawns at 100% afterwards (nothing here gates SpawnGuardian)
 *   beaten or failed          - RecordGuardianResult writes dc_rift.outcome and time_left at the
 *                               Guardian's death (09-rifts 7.4: only a kill before 0:00 beats the rift),
 *                               before its rewards settle, so a retried payout cannot expire a run
 *   unlocks                   - an in-time result also raises every enrolled member's Greater Rift numbers
 *                               (GrantGreaterUnlocks; the chart and the store are dc_gr_unlock.h and dc_gr_level.cpp)
 * Everything the decisions need is dc_gr_progress.h, which the test compiles. The clock, the Guardian's result
 * and the unlocks are Greater Rift only; the bar and the orbs are both modes'.
 */

#include "dc_gr_progress.h"

#include "dc_gr_complete.h"
#include "dc_rift_text.h"
#include "dc_gr_level.h"
#include "../monsters/dc_monster_ai.h"
#include "../monsters/dc_family_ai.h"
#include "dc_rift_quests.h"
#include "dc_rifts_internal.h"
#include "../common/dc_bridge.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "GameTime.h"
#include "GridDefines.h"
#include "Log.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "WorldSession.h"

#include <cmath>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Rifts
{
    namespace
    {
        // Constants: the progress orbs' gameobject entries, purple for a Greater Rift and orange for a Nephalem
        // Rift. generate_rifts.py ORB_ENTRY and NR_ORB_ENTRY write their templates (rifts_0016_gr_orb.sql,
        // rifts_0020_nr_orb.sql, which rifts_0031_nr_orb_look.sql re-ships with the Flame Sphere look).
        constexpr std::uint32_t ORB_ENTRY = 910060, NR_ORB_ENTRY = 910062;

        double Number(char const* name)
        {
            return Tunables::Get("rifts", name);
        }

        // The live rift (either mode) this map is a floor of, as a copy seen from this floor. False for any other
        // map and for a run that has closed.
        bool RunOf(Map const* map, Rift& out)
        {
            if (!map || !map->IsDungeon() || !map->GetInstanceId())
                return false;
            std::lock_guard<std::mutex> lock(riftMutex);
            Rift seen;
            if (!live.View(map->GetInstanceId(), map->GetId(), seen) || seen.state == "closed")
                return false;
            out = seen;
            return true;
        }

        struct Orb
        {
            ObjectGuid object;
            float x = 0, y = 0, z = 0;
            unsigned hundredths = 0; // what taking it adds to the bar
        };

        // The orbs lying in each rift, by instance id. Written by the pack-death hook and
        // the map update of the same map, so it is short and guarded.
        std::mutex orbMutex;
        std::map<std::uint32_t, std::vector<Orb>> orbs;

        void StoreResult(Rift const& rift, char const* outcome, unsigned timeLeft)
        {
            // Synchronous like PersistNow: the tracker reads this row, and the unlock reads it
            // too. `outcome='pending'` makes the first writer the only one.
            CharacterDatabase.DirectExecute(
                "UPDATE dc_rift SET outcome='{}', time_left={} WHERE id={} AND outcome='pending'", outcome, timeLeft,
                rift.id);
        }

        std::string Clock(unsigned seconds)
        {
            return std::to_string(seconds / 60) + ":" + (seconds % 60 < 10 ? "0" : "") + std::to_string(seconds % 60);
        }

        // D3's centre-screen line to every run member still enrolled and online, at the in-time Guardian kill: the words and the colour
        // of each part over the DCRIFTTEXT channel (docs/contracts/rift-centre-text.md), which the client draws in the middle of the screen.
        void ShowComplete(Rift const& rift)
        {
            std::vector<std::string> const fields =
                Text::Fields(Text::GreaterRiftComplete, Gr::CompleteParts(rift.timeLeft));
            for (ObjectGuid const& guid : EnrolledGuids(rift.id))
                if (Player* member = ObjectAccessor::FindPlayer(guid); member && member->GetSession())
                    Bridge::Push(member, Text::Prefix, fields);
        }

        // The clock reached 0:00 with the Guardian alive: the run is failed from here on.
        void Expire(Rift const& seen)
        {
            Rift rift;
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                Rift* run = live.Find(seen.id);
                if (!run || run->outcome != "pending")
                    return;
                run->outcome = Gr::OutcomeName(false);
                run->timeLeft = 0;
                rift = *run;
            }
            StoreResult(rift, rift.outcome.c_str(), 0);
            Announce(rift, "The Greater Rift timer has run out. Its Guardian can still be killed, "
                           "but this Greater Rift can no longer be beaten.");
        }

        void Take(Map* map, Orb const& orb)
        {
            if (GameObject* object = map->GetGameObject(orb.object))
                object->Delete();
        }
    } // namespace

    namespace
    {
        // Each roster monster's points in hundredths, by its creature entry (dc_monster_progress). Read at
        // startup and by `.dc rift spawn`; a monster with no row is the default.
        std::mutex progressMutex;
        std::unordered_map<std::uint32_t, unsigned> monsterHundredths;
    } // namespace

    bool LoadMonsterProgress(std::string& error)
    {
        QueryResult rows = WorldDatabase.Query("SELECT entry, hundredths FROM dc_monster_progress");
        if (!rows)
        {
            error = "dc_monster_progress is missing or empty; apply spawn_sheets_0002_progress.sql";
            return false;
        }
        std::unordered_map<std::uint32_t, unsigned> loaded;
        do
        {
            Field* f = rows->Fetch();
            loaded[f[0].Get<uint32>()] = f[1].Get<uint32>();
        } while (rows->NextRow());
        std::lock_guard<std::mutex> lock(progressMutex);
        monsterHundredths = std::move(loaded);
        return true;
    }

    // What this kill adds, in hundredths of a point: its monster's own points. A champion or rare is a clone of
    // a roster monster (CHAMPION_BASE and RARE_BASE above its entry), a minion is the monster itself.
    unsigned KillUnits(Creature* killed, Rift const&)
    {
        unsigned const fallback = Gr::Hundredths(Number("monster_progress_default_points"));
        if (!killed)
            return fallback;
        std::lock_guard<std::mutex> lock(progressMutex);
        auto const found = monsterHundredths.find(Family::BaseEntry(killed->GetEntry()));
        return Gr::KillHundredths(found != monsterHundredths.end(), found != monsterHundredths.end() ? found->second : 0,
                                  fallback);
    }

    void DropGreaterOrbs(Creature* dead)
    {
        EliteState* pack = dead ? dead->CustomData.Get<EliteState>("DCRiftElite") : nullptr;
        if (!pack)
            return;
        Map* map = dead->GetMap();
        Rift rift;
        bool const inRun = RunOf(map, rift);
        // Every pack death is counted, in a run or not, so the head count stays true.
        if (!Gr::OrbsFall(*pack->life) || !inRun ||
            !Gr::OrbsWanted(rift.state == "open", rift.progress, rift.requiredUnits))
            return;
        bool const greater = rift.mode == "gr";
        char const* const mode = greater ? "gr" : "nr";
        Gr::Orbs const kind =
            Gr::OrbsFor(pack->rare, Number((std::string(mode) + "_orb_champion_count").c_str()),
                        Number((std::string(mode) + "_orb_rare_count").c_str()),
                        Number((std::string(mode) + "_orb_points").c_str()));
        std::uint32_t const entry = greater ? ORB_ENTRY : NR_ORB_ENTRY;
        std::shared_ptr<AffixNumbers const> const numbers = Numbers();
        float const spread = numbers ? numbers->minionSpread : 0.0f;
        // The Nephalem orb is a bare sphere centred on its model's origin, so it floats nr_orb_lift_yards above the
        // ground; the Greater orb is a floor aura and sits on it.
        float const lift = greater ? 0.0f : static_cast<float>(Number("nr_orb_lift_yards"));
        std::vector<Orb> placed;
        for (unsigned index = 0; index < kind.count; ++index)
        {
            Gr::Spot const spot = Gr::OrbSpot(index, kind.count, dead->GetPositionX(), dead->GetPositionY(), spread);
            float z = map->GetHeight(dead->GetPhaseMask(), spot.x, spot.y, dead->GetPositionZ() + 2.0f);
            if (z <= INVALID_HEIGHT)
                z = dead->GetPositionZ();
            if (GameObject* object = map->SummonGameObject(entry, spot.x, spot.y, z + lift, dead->GetOrientation(), 0, 0,
                                                           std::sin(dead->GetOrientation() / 2),
                                                           std::cos(dead->GetOrientation() / 2), 0))
                placed.push_back({object->GetGUID(), spot.x, spot.y, z, kind.hundredths});
        }
        // The orbs and their pickup were silent, so a dev run could not say whether they dropped at all:
        // a pack's drop, and a drop that made nothing, now show in the log.
        if (placed.empty())
        {
            if (kind.count)
                LOG_ERROR("server", "[DC rifts] rift {}: a pack died but none of its {} progress orbs (gameobject {}) could be summoned",
                          rift.id, kind.count, entry);
            return;
        }
        LOG_INFO("server", "[DC rifts] rift {}: a {} pack died; {} progress orbs lie at {:.1f},{:.1f},{:.1f}", rift.id,
                 pack->rare ? "rare" : "champion", placed.size(), dead->GetPositionX(), dead->GetPositionY(),
                 dead->GetPositionZ());
        std::lock_guard<std::mutex> lock(orbMutex);
        auto& mine = orbs[rift.instanceId];
        mine.insert(mine.end(), placed.begin(), placed.end());
    }

    void GreaterTick(Map* map)
    {
        Rift rift;
        if (!RunOf(map, rift))
            return;
        // The clock, Urshi and the Guardian's floor are Greater Rift only; the orbs below are both modes'.
        if (rift.mode == "gr" && Gr::ExpiryDue(rift.outcome == "pending", GameTime::GetGameTime().count(), rift.deadline))
            Expire(rift);
        if (rift.mode == "gr")
            UrshiTick(map);

        // While the Guardian is up or just dead nothing else may be on the map: a grid that loads late
        // or a spawn that comes back is cleared at once. The hostility test needs a
        // player to ask against, so an empty map is skipped (no one is there to load anything).
        // ponytail: a sweep of the map's creatures every tick; throttle it if a big map shows in a profile.
        // Only on the floor the Guardian spawned on: the other floors of the run keep their monsters (rift floors 6.9).
        if (rift.mode == "gr")
        {
            if ((rift.state == "guardian" || rift.state == "complete") && map->GetInstanceId() == rift.guardianInstance)
            {
                Player* reference = nullptr;
                map->DoForAllPlayers([&](Player* player) { reference = reference ? reference : player; });
                if (reference)
                    ClearGreaterRift(map, rift, reference);
            }
        }

        std::vector<Orb> lying;
        {
            std::lock_guard<std::mutex> lock(orbMutex);
            auto found = orbs.find(rift.instanceId);
            if (found == orbs.end())
                return;
            lying = found->second;
        }
        bool const wanted = Gr::OrbsWanted(rift.state == "open", rift.progress, rift.requiredUnits);
        double const radius = Number("gr_orb_pickup_radius_yards");
        std::vector<Orb> kept;
        for (Orb const& orb : lying)
        {
            if (!map->GetGameObject(orb.object))
                continue; // gone with the map's own cleanup
            Player* taker = nullptr;
            if (wanted)
                map->DoForAllPlayers(
                    [&](Player* player)
                    {
                        if (!taker && player && player->IsAlive() &&
                            Gr::WithinPickup(player->GetExactDist(orb.x, orb.y, orb.z), radius))
                            taker = player;
                    });
            if (taker)
            {
                // Once: the orb leaves the list and the world before progress moves.
                Take(map, orb);
                AddProgress(taker, rift.id, orb.hundredths, 0);
                LOG_INFO("server", "[DC rifts] rift {}: {} took a progress orb, +{} of {} hundredths of a point", rift.id,
                         taker->GetName(), orb.hundredths, rift.requiredUnits);
                // An orb is taken the moment a player stands at the corpse, so the bar alone gave no sign that
                // it had paid.
                if (taker->GetSession() && rift.requiredUnits)
                {
                    std::ostringstream pct;
                    pct.precision(3);
                    pct << 100.0 * orb.hundredths / rift.requiredUnits;
                    ChatHandler(taker->GetSession())
                        .SendSysMessage("Progress orb: +" + pct.str() + "% of the " +
                                        (rift.mode == "gr" ? "Greater" : "Nephalem") + " Rift.");
                }
                continue;
            }
            if (!wanted)
            {
                Take(map, orb); // the bar is full or the Guardian is up: nothing left to take
                continue;
            }
            kept.push_back(orb);
        }
        std::lock_guard<std::mutex> lock(orbMutex);
        if (kept.empty())
            orbs.erase(rift.instanceId);
        else
            orbs[rift.instanceId] = kept;
    }

    void RecordGuardianResult(Rift& rift)
    {
        if (rift.mode != "gr")
            return;
        if (rift.outcome == "pending")
        {
            if (rift.deadline <= 0)
                LOG_ERROR("server",
                          "[DC rifts] Greater Rift {} has no deadline; its Guardian kill is recorded as failed",
                          rift.id);
            std::int64_t const now = GameTime::GetGameTime().count();
            bool const beaten = Gr::InTime(now, rift.deadline);
            rift.outcome = Gr::OutcomeName(beaten);
            rift.timeLeft = Gr::TimeLeft(now, rift.deadline);
            {
                std::lock_guard<std::mutex> lock(riftMutex);
                if (Rift* run = live.Find(rift.id))
                {
                    run->outcome = rift.outcome;
                    run->timeLeft = rift.timeLeft;
                }
            }
            StoreResult(rift, rift.outcome.c_str(), rift.timeLeft);
            if (beaten)
                GrantGreaterUnlocks(rift);
            if (beaten)
                ShowComplete(rift);
        }
        if (rift.outcome == Gr::OutcomeName(true))
            Announce(rift, "Greater Rift " + std::to_string(rift.grRank) + " beaten with " + Clock(rift.timeLeft) +
                               " left on the clock.");
        else
            Announce(rift, "The Guardian fell after the clock ran out. Greater Rift " + std::to_string(rift.grRank) +
                               " is not beaten.");
    }

    void GrantGreaterUnlocks(Rift const& rift)
    {
        if (rift.mode != "gr" || rift.outcome != Gr::OutcomeName(true))
            return; // a failed run unlocks nothing
        // Every member still enrolled at the Guardian's death, online or not, on their own character;
        // a member who left the party (a failed abandon, 09-rifts 7.9.2) is no longer enrolled. Solo is
        // the headcount the run opened with, which a Greater Rift never rescales.
        bool const solo = rift.players == 1;
        for (ObjectGuid const& guid : EnrolledGuids(rift.id))
        {
            GrUnlock const done = RecordGreaterRiftBeaten(guid.GetCounter(), rift.grRank, rift.timeLeft, solo);
            if (done.after.unlocked <= done.before.unlocked)
                continue;
            if (Player* player = ObjectAccessor::FindPlayer(guid); player && player->GetSession())
                ChatHandler(player->GetSession())
                    .SendSysMessage("You can now open Greater Rift " + std::to_string(done.after.unlocked) + ".");
        }
    }

    void ForgetGreaterOrbs(std::uint32_t instanceId)
    {
        std::lock_guard<std::mutex> lock(orbMutex);
        orbs.erase(instanceId);
    }
} // namespace DC::Rifts
