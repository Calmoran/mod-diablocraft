/*
 * The corpses a kill leaves (dc_corpses.h). One pile per owner, by the owner's guid, in memory only: a corpse is not
 * saved, and the owner's map change and logout empty the pile, so a floor's corpses never reach the next. A corpse is
 * the dead monster's own stock body where it fell: the pile holds the owner's claim on that body, and the body is
 * removed, as the core's own decay removes it, when the last claim on it is taken, expires or is pushed out by the cap;
 * a claim whose body has gone is dropped. The rules are dc_corpses_math.h; this file keeps the piles, reads the two
 * tunables and speaks to the core.
 */

#include "dc_corpses.h"
#include "../common/dc_tunables.h"
#include "../loot/dc_corpse_loot.h"
#include "Chat.h"
#include "Creature.h"
#include "GameTime.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "TemporarySummon.h"
#include "WorldSession.h"

#include <algorithm>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Corpses
{
    namespace
    {
        std::mutex pilesMutex;
        std::unordered_map<std::uint64_t, Pile> piles;
        std::vector<Listener> listeners;

        // The owners whose corpse skills are used at will, and until when, with how many corpses a request is met with.
        struct Window
        {
            std::uint64_t until = 0;
            std::size_t phantoms = 0;
        };
        std::unordered_map<std::uint64_t, Window> windows;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The two combat tunables as the pile reads them: a count and milliseconds. An unset row is 0, which keeps no
        // corpse (Pile::Leave).
        std::size_t Cap()
        {
            double const cap = DC::Tunables::Get("combat", "corpse_cap");
            return cap > 0 ? std::size_t(cap) : 0;
        }

        std::uint64_t LifetimeMs()
        {
            double const seconds = DC::Tunables::Get("combat", "corpse_lifetime_seconds");
            return seconds > 0 ? std::uint64_t(seconds * 1000) : 0;
        }

        // The stand-in creature of a skill-made corpse that names none (the combat tunable skill_corpse_body_entry).
        std::uint32_t StandIn()
        {
            double const entry = DC::Tunables::Get("combat", "skill_corpse_body_entry");
            return entry > 0 ? std::uint32_t(entry) : 0;
        }

        // The dead body being made now; a hook on the death reads it (BodyBeingMade).
        thread_local std::uint64_t making = 0;

        // The look of the creature that died: its first model; 0 (the body template's own) for a corpse that says none.
        std::uint32_t LookOf(std::uint32_t entry)
        {
            if (!entry)
                return 0;
            CreatureTemplate const* info = sObjectMgr->GetCreatureTemplate(entry);
            CreatureModel const* model = info ? info->GetFirstValidModel() : nullptr;
            return model ? model->CreatureDisplayID : 0;
        }

        // A stock dead body of `entry` at `at`, wearing `display` when it is not 0: the creature is summoned, then killed by
        // itself with no loot to give and no credit to hand out. Its guid, 0 when no creature came. `entry` is always a
        // creature with no death behaviour of its own (BodyEntry), never the entry of a monster that died: a dead monster's
        // own entry would run its death abilities and its scripts again.
        std::uint64_t MakeBody(Player* owner, Position const& at, std::uint32_t entry, std::uint32_t display)
        {
            if (!entry)
                return 0;
            TempSummon* body = owner->SummonCreature(entry, at, TEMPSUMMON_MANUAL_DESPAWN);
            if (!body)
                return 0;
            if (display)
            {
                body->SetDisplayId(display);
                body->SetNativeDisplayId(display);
            }
            std::uint64_t const guid = body->GetGUID().GetRawValue();
            making = guid;
            body->KillSelf(false);
            making = 0;
            return guid;
        }

        // A body goes as the core's decay takes a dead monster's, or, for one this piece summoned, is unsummoned.
        void RemoveBody(Creature* body)
        {
            if (TempSummon* summon = body->ToTempSummon())
                summon->UnSummon();
            else
                body->RemoveCorpse(false);
        }

        std::uint64_t Key(Player const* owner)
        {
            return owner->GetGUID().GetRawValue();
        }

        void Forget(Player* player)
        {
            std::lock_guard<std::mutex> lock(pilesMutex);
            piles.erase(Key(player));
            windows.erase(Key(player));
        }

        // The window the owner has open now: its phantoms, 0 with none. Under the lock.
        std::size_t OpenPhantoms(Player const* owner)
        {
            auto const found = windows.find(Key(owner));
            return found != windows.end() && AtWillNow(Now(), found->second.until) ? found->second.phantoms : 0;
        }

        // Whether the dead body a corpse is still lies where it fell: the creature is in the owner's map and is a corpse
        // (just died, or lying), not removed and not alive again.
        bool BodyLies(WorldObject const& context, std::uint64_t body)
        {
            Creature* creature = ObjectAccessor::GetCreature(context, ObjectGuid(body));
            return creature && creature->IsInWorld() &&
                   (creature->getDeathState() == DeathState::Corpse || creature->getDeathState() == DeathState::JustDied);
        }

        // Drops the owner's claims on bodies that are gone (they decayed, or something else removed them).
        void Tidy(Player* owner)
        {
            std::vector<std::uint64_t> bodies;
            {
                std::lock_guard<std::mutex> lock(pilesMutex);
                auto it = piles.find(Key(owner));
                if (it == piles.end())
                    return;
                bodies = it->second.Bodies();
            }
            std::vector<std::uint64_t> gone;
            for (std::uint64_t body : bodies)
                if (!BodyLies(*owner, body))
                    gone.push_back(body);
            if (gone.empty())
                return;
            std::lock_guard<std::mutex> lock(pilesMutex);
            auto it = piles.find(Key(owner));
            if (it != piles.end())
                it->second.Prune([&](Spot const& spot) { return std::find(gone.begin(), gone.end(), spot.body) != gone.end(); });
        }

        // Removes the dead bodies of corpses that left a pile, unless another player's pile still holds a claim on the
        // body, or the body still holds somebody's unlooted drops (they are rows on the body, and go with it). The body
        // goes as the core's decay takes it (Creature::RemoveCorpse without a spawn time), so the respawn clock is the
        // one the death started.
        void RemoveUnclaimed(Player* owner, std::vector<Spot> const& left)
        {
            for (Spot const& spot : left)
            {
                if (spot.body == 0)
                    continue;
                {
                    std::lock_guard<std::mutex> lock(pilesMutex);
                    if (std::any_of(piles.begin(), piles.end(), [&](auto const& entry) { return entry.second.Holds(spot.body); }))
                        continue;
                }
                if (Creature* body = ObjectAccessor::GetCreature(*owner, ObjectGuid(spot.body)))
                    if (body->IsInWorld() && !Loot::CorpseHoldsRows(body))
                        RemoveBody(body);
            }
        }

        // Once a second, the corpses past their lifetime go with their bodies, whether or not anyone asks for a corpse.
        class Sweeper final : public WorldScript
        {
        public:
            Sweeper()
                : WorldScript("dc_corpses_sweep", {WORLDHOOK_ON_UPDATE})
            {
            }

            void OnUpdate(std::uint32_t diff) override
            {
                sinceMs += diff;
                if (sinceMs < SweepMs)
                    return;
                sinceMs = 0;
                std::vector<std::pair<std::uint64_t, std::vector<Spot>>> expired;
                {
                    std::lock_guard<std::mutex> lock(pilesMutex);
                    std::uint64_t const now = Now(), lifetime = LifetimeMs();
                    for (auto& entry : piles)
                    {
                        entry.second.Sweep(now, lifetime);
                        if (auto left = entry.second.Released(); !left.empty())
                            expired.emplace_back(entry.first, std::move(left));
                    }
                }
                for (auto const& [owner, left] : expired)
                    if (Player* player = ObjectAccessor::FindConnectedPlayer(ObjectGuid(owner)); player && player->IsInWorld())
                        RemoveUnclaimed(player, left);
            }

        private:
            static constexpr std::uint32_t SweepMs = 1000;
            std::uint32_t sinceMs = 0;
        };

        class Floors final : public PlayerScript
        {
        public:
            Floors()
                : PlayerScript("dc_corpses", {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerLogout(Player* player) override
            {
                Forget(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Forget(player);
            }
        };

        class Commands final : public CommandScript
        {
        public:
            Commands()
                : CommandScript("dc_corpses_command")
            {
            }

            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable children = {{"corpselist", List, SEC_GAMEMASTER, Console::No},
                                                    {"corpseeat", Eat, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable root = {{"dc", children}};
                return root;
            }

            // `.dc corpselist [radius]`: the GM's corpses within `radius` yards (60 without a word) and the cap and
            // lifetime in force.
            static bool List(ChatHandler* handler, Optional<float> radius)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                float const reach = radius ? *radius : 60.0f;
                handler->PSendSysMessage("Corpses within {} yards: {} (cap {}, lifetime {} ms; 0 keeps none).", reach,
                                         Count(player, player->GetPosition(), reach), Cap(), LifetimeMs());
                return true;
            }

            // `.dc corpseeat [radius [max]]`: takes the nearest corpses within `radius` yards (60), up to `max` (1),
            // and says how far each was.
            static bool Eat(ChatHandler* handler, Optional<float> radius, Optional<std::uint32_t> max)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                Position const here = player->GetPosition();
                auto const taken = Consume(player, here, radius ? *radius : 60.0f, max ? *max : 1);
                for (Spot const& spot : taken)
                    handler->PSendSysMessage("Took the corpse {:.1f} yards away (creature {}).",
                                             GroundDistance(spot, here.GetPositionX(), here.GetPositionY()),
                                             spot.entry);
                if (taken.empty())
                    handler->SendSysMessage("No corpse in reach.");
                return true;
            }
        };
    } // namespace

    bool Leave(Player* owner, Position const& at, std::uint32_t entry, std::uint64_t body)
    {
        if (!owner || !owner->IsInWorld())
            return false;
        Tidy(owner);
        Spot spot;
        spot.x = at.GetPositionX();
        spot.y = at.GetPositionY();
        spot.z = at.GetPositionZ();
        spot.entry = entry;
        spot.body = body;
        bool kept;
        std::vector<Spot> left;
        {
            std::lock_guard<std::mutex> lock(pilesMutex);
            Pile& pile = piles[Key(owner)];
            kept = pile.Leave(spot, Now(), Cap(), LifetimeMs());
            left = pile.Released();
        }
        RemoveUnclaimed(owner, left);
        return kept;
    }

    bool LeaveMade(Player* owner, Position const& at, std::uint32_t entry, std::uint32_t skillBody)
    {
        if (!owner || !owner->IsInWorld())
            return false;
        // The body is the skill's own creature or the stand-in, never `entry`: that is what the corpse says stood there, and
        // only its look is borrowed (when the skill names no body of its own).
        std::uint64_t const body = MakeBody(owner, at, BodyEntry(skillBody, StandIn()), skillBody ? 0 : LookOf(entry));
        if (Leave(owner, at, entry, body))
            return true;
        // Not kept (no cap or no lifetime set): nobody holds a claim on the body, so it goes now.
        if (body)
            if (Creature* made = ObjectAccessor::GetCreature(*owner, ObjectGuid(body)))
                RemoveBody(made);
        return false;
    }

    std::uint64_t BodyBeingMade()
    {
        return making;
    }

    std::size_t Count(Player* owner, Position const& center, float radius)
    {
        if (!owner)
            return 0;
        Tidy(owner);
        std::size_t count = 0;
        std::vector<Spot> left;
        {
            std::lock_guard<std::mutex> lock(pilesMutex);
            auto it = piles.find(Key(owner));
            if (it != piles.end())
            {
                count = it->second.Count(center.GetPositionX(), center.GetPositionY(), radius, Now(), LifetimeMs());
                left = it->second.Released();
            }
            std::size_t const phantoms = OpenPhantoms(owner);
            count = CountAtWill(count, phantoms > 0, phantoms);
        }
        RemoveUnclaimed(owner, left);
        return count;
    }

    std::vector<Spot> Consume(Player* owner, Position const& center, float radius, std::size_t max)
    {
        std::vector<Spot> taken;
        if (!owner)
            return taken;
        Tidy(owner);
        std::vector<Spot> left;
        {
            std::lock_guard<std::mutex> lock(pilesMutex);
            auto it = piles.find(Key(owner));
            if (it != piles.end())
            {
                taken = it->second.Take(center.GetPositionX(), center.GetPositionY(), radius, max, Now(), LifetimeMs());
                left = it->second.Released();
            }
        }
        // The bodies of what was taken, and of what expired on the way, go with their corpses.
        left.insert(left.end(), taken.begin(), taken.end());
        RemoveUnclaimed(owner, left);
        if (!taken.empty())
            for (Listener const& listener : listeners)
                listener(owner, taken);
        std::size_t phantoms;
        {
            std::lock_guard<std::mutex> lock(pilesMutex);
            phantoms = OpenPhantoms(owner);
        }
        // Used at will: the corpses the take found short are made at the centre.
        for (std::size_t i = PhantomsFor(taken.size(), max, phantoms > 0, phantoms); i > 0; --i)
        {
            Spot made;
            made.x = center.GetPositionX();
            made.y = center.GetPositionY();
            made.z = center.GetPositionZ();
            taken.push_back(made);
        }
        return taken;
    }

    void AtWill(Player* owner, std::uint64_t untilMs, std::size_t phantoms)
    {
        if (!owner)
            return;
        std::lock_guard<std::mutex> lock(pilesMutex);
        if (untilMs == 0)
            windows.erase(Key(owner));
        else
            windows[Key(owner)] = {untilMs, phantoms};
    }

    void OnConsumed(Listener listener)
    {
        listeners.push_back(std::move(listener));
    }

    void RegisterScripts()
    {
        new Floors();
        new Sweeper();
        new Commands();
    }
} // namespace DC::Combat::Corpses
