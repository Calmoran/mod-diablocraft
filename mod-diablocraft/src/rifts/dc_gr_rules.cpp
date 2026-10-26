/*
 * World of DiabloCraft - the six Greater Rift rules and the XP split.
 *
 * D3's six rules, each on the stock WoW system that already does the thing:
 *   1 only the Guardian drops loot      - dc_loot.cpp's kill hook asks GreaterRiftNoLoot
 *   2 no treasure goblins               - nothing to refuse yet: no goblin creature exists
 *   3 no shrines, chests or clickables  - AllGameObjectScript::CanGameObjectGossipHello, which
 *                                         GameObject::Use asks before it does anything (here); the town
 *                                         portal and the floors' exit portals are let through
 *   4 no teleport to party or banners   - PlayerScript::OnPlayerBeforeTeleport (here): the one
 *                                         teleport that names a player is accepting a summon
 *                                         (Player::SummonIfPossible). Banners do not exist yet
 *   5 no reviving in town, a growing wait - DCREVIVE and the release path in dc_hardcore.cpp ask
 *                                         GreaterRiftTownReviveRefused / GreaterRiftReviveWaitLeft;
 *                                         the deaths are counted here (OnPlayerJustDied). The town
 *                                         refusal lifts when the Guardian is dead
 *   6 no gear or skill changes          - PlayerScript::OnPlayerCanEquipItem / CanUnequipItem (here)
 *                                         for worn gear, dc_inventory.cpp for the potion slot; the
 *                                         skill bar refuses inside every instance (04 §3,
 *                                         dc_classes.cpp SetSlot and SetPassive) except here once
 *                                         the Guardian is dead (GreaterRiftGuardianDead)
 * Plus D3's XP split, applied where Torment pays kill XP (dc_paragon.cpp).
 *
 * Rules 2 and the banner half of 4 are refusals waiting for content that does not exist yet.
 */

#include "dc_gr_rewards.h"
#include "dc_gr_rules.h"

#include "../monsters/dc_monster_ai.h"
#include "dc_rifts_internal.h"
#include "../combat/dc_pylon_math.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "Creature.h"
#include "GameObject.h"
#include "Map.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Timer.h"
#include "WorldSession.h"

#include <map>
#include <mutex>
#include <string>
#include <utility>

namespace DC::Rifts
{
    namespace
    {
        // The state of the Greater Rift this map is a floor of, and the run's id. False for any other
        // map, including a Nephalem Rift. A run that has closed still answers (state "closed") until
        // its last map is destroyed, so a caller decides for itself what a closed run means.
        bool RunOf(Map const* map, std::string& state, std::uint64_t& runId)
        {
            if (!map || !map->IsDungeon() || !map->GetInstanceId())
                return false;
            std::lock_guard<std::mutex> lock(riftMutex);
            Rift const* run = live.FindByInstance(map->GetInstanceId(), map->GetId());
            if (!run || run->mode != "gr")
                return false;
            state = run->state;
            runId = run->id;
            return true;
        }

        bool LiveRun(Player const* player, std::uint64_t& runId)
        {
            std::string state;
            return player && RunOf(player->GetMap(), state, runId) && state != "closed";
        }

        unsigned Seconds(char const* name)
        {
            return static_cast<unsigned>(Tunables::Get("rifts", name));
        }

        // --- rule 5: the deaths of each character in each run ------------------------------------

        struct Death
        {
            unsigned count = 0;
            std::uint32_t at = 0; // server ms of the latest one
        };

        std::mutex deathMutex;
        std::map<std::pair<std::uint64_t, std::uint32_t>, Death> deaths; // (run id, character guid): one count per run, across its floors

        // A run that is gone from the live map has no wait left to remember.
        void ForgetEnded()
        {
            for (auto it = deaths.begin(); it != deaths.end();)
            {
                bool gone;
                {
                    std::lock_guard<std::mutex> lock(riftMutex);
                    gone = live.Find(it->first.first) == nullptr;
                }
                it = gone ? deaths.erase(it) : std::next(it);
            }
        }

        class GreaterRiftRules final : public PlayerScript
        {
        public:
            GreaterRiftRules()
                : PlayerScript("dc_gr_rules", {PLAYERHOOK_ON_PLAYER_JUST_DIED, PLAYERHOOK_CAN_EQUIP_ITEM,
                                               PLAYERHOOK_CAN_UNEQUIP_ITEM, PLAYERHOOK_ON_BEFORE_TELEPORT})
            {
            }

            void OnPlayerJustDied(Player* player) override
            {
                std::uint64_t run = 0;
                if (!LiveRun(player, run))
                    return;
                std::lock_guard<std::mutex> lock(deathMutex);
                ForgetEnded();
                Death& death = deaths[{run, player->GetGUID().GetCounter()}];
                ++death.count;
                death.at = getMSTime();
            }

            bool OnPlayerCanEquipItem(Player* player, uint8, uint16&, Item*, bool, bool notLoading) override
            {
                if (!notLoading || !GreaterRiftGearLocked(player))
                    return true; // a character loading its worn gear is not changing it
                Refuse(player);
                return false;
            }

            bool OnPlayerCanUnequipItem(Player* player, uint16, bool swap) override
            {
                if (!GreaterRiftGearLocked(player))
                    return true;
                if (!swap) // a swap also asks the equip side, which has already said so
                    Refuse(player);
                return false;
            }

            // Player::SummonIfPossible is the only caller that passes a player as the target of a
            // teleport: the accepted summon of a party member (a meeting stone, a ritual). It is
            // refused when either end is a Greater Rift whose Guardian is alive. The caster's own
            // Town Portal and near teleports pass no target, so they are untouched.
            bool OnPlayerBeforeTeleport(Player* player, uint32, float, float, float, float, uint32,
                                        Unit* target) override
            {
                Player* summoner = target ? target->ToPlayer() : nullptr;
                if (!summoner || !(GreaterRiftGearLocked(player) || GreaterRiftGearLocked(summoner)))
                    return true;
                if (player->GetSession())
                    ChatHandler(player->GetSession())
                        .SendSysMessage("You cannot be summoned to or from a Greater Rift until its Guardian is dead.");
                return false;
            }

        private:
            static void Refuse(Player* player)
            {
                if (player->GetSession())
                    ChatHandler(player->GetSession())
                        .SendSysMessage("You cannot change your gear in a Greater Rift until its Guardian is dead.");
            }
        };

        // Rule 3. GameObject::Use asks this first for every player click; true ends the use.
        class GreaterRiftClickables final : public AllGameObjectScript
        {
        public:
            GreaterRiftClickables()
                : AllGameObjectScript("dc_gr_clickables")
            {
            }

            bool CanGameObjectGossipHello(Player* player, GameObject* go) override
            {
                std::string state;
                std::uint64_t run = 0;
                // Pylons P4: a pylon is the rift's own, not the dungeon's, so it stays usable (a shrine never stands here).
                if (!player || !go || !Gr::ClickableDenied(go->GetGoType()) || Gr::TownPortalEntry(go->GetEntry()) || IsExitPortal(go->GetEntry()) ||
                    DC::Combat::Pylons::IsPylonObject(go->GetEntry()) ||
                    !RunOf(go->FindMap(), state, run) || state == "closed")
                    return false;
                if (player->GetSession())
                    ChatHandler(player->GetSession()).SendSysMessage("Nothing can be used in a Greater Rift.");
                return true;
            }
        };
    } // namespace

    bool GreaterRiftNoLoot(Creature const* creature)
    {
        std::string state;
        std::uint64_t run = 0;
        return creature && RunOf(creature->GetMap(), state, run) && !IsGuardianEntry(creature->GetEntry());
    }

    bool GreaterRiftGearLocked(Player const* player)
    {
        std::string state;
        std::uint64_t run = 0;
        return player && RunOf(player->GetMap(), state, run) && Gr::GuardianAlive(state);
    }

    bool GreaterRiftTownReviveRefused(Player const* player)
    {
        std::string state;
        std::uint64_t run = 0;
        return player && RunOf(player->GetMap(), state, run) && Gr::GuardianAlive(state);
    }

    bool GreaterRiftGuardianDead(Player const* player)
    {
        std::string state;
        std::uint64_t run = 0;
        return player && RunOf(player->GetMap(), state, run) && !Gr::GuardianAlive(state);
    }

    unsigned GreaterRiftReviveWaitLeft(Player const* player)
    {
        std::uint64_t run = 0;
        if (!LiveRun(player, run))
            return 0;
        std::lock_guard<std::mutex> lock(deathMutex);
        auto found = deaths.find({run, player->GetGUID().GetCounter()});
        if (found == deaths.end())
            return 0;
        unsigned const wait = Gr::ReviveWaitSeconds(
            found->second.count, Seconds("gr_revive_wait_first_seconds"),
            Tunables::Has("rifts", "gr_revive_wait_step_seconds") ? Seconds("gr_revive_wait_step_seconds") : 0,
            Seconds("gr_revive_wait_max_seconds"));
        return Gr::WaitLeftSeconds(found->second.at, wait, getMSTime());
    }

    unsigned GreaterRiftDeaths(std::uint64_t runId, std::uint32_t character)
    {
        std::lock_guard<std::mutex> lock(deathMutex);
        auto found = deaths.find({runId, character});
        return found == deaths.end() ? 0 : found->second.count;
    }

    std::uint64_t GreaterRiftXp(Creature const* victim, std::uint64_t amount)
    {
        std::string state;
        std::uint64_t run = 0;
        if (!victim || !RunOf(victim->GetMap(), state, run))
            return amount;
        Gr::XpSplit split;
        split.monsterSet = Tunables::Has("rifts", "gr_monster_xp_pct");
        split.guardianSet = Tunables::Has("rifts", "gr_guardian_xp_multiple");
        split.monsterPct = Tunables::Get("rifts", "gr_monster_xp_pct");
        split.guardianMultiple = Tunables::Get("rifts", "gr_guardian_xp_multiple");
        bool const guardian = IsGuardianEntry(victim->GetEntry());
        std::uint64_t const scaled = Gr::SplitXp(amount, guardian, split);
        if (!guardian)
            return scaled;
        // The Guardian's XP rises with the run's level (greater_rifts.csv xp_gain_per_rank).
        unsigned level = 0;
        {
            std::lock_guard<std::mutex> lock(riftMutex);
            if (Rift const* found = live.Find(run))
                level = found->grRank;
        }
        return Gr::ScaleXp(scaled, GuardianXpFactor(level));
    }

    void RegisterGreaterRiftRuleScripts()
    {
        new GreaterRiftRules();
        new GreaterRiftClickables();
    }
} // namespace DC::Rifts
