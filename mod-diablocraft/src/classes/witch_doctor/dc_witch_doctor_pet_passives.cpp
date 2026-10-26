/*
 * The Witch Doctor's passive that is about the pets and needs code of its own. Fierce Loyalty: "While you have a Gargantuan, Zombie
 * Dog, or Fetish summoned, your movement speed is increased", more while one of them is not in combat. The pets are the shared minions
 * piece's (Minions::Standing) and the speed is a number on the sheet, kept by a small update script. What the other pet passives give the
 * pets (Life, damage, the extra dogs, the Fetish Sycophants' Fetishes) is read by the pets' piece (dc_witch_doctor_pets.cpp).
 */

#include "dc_witch_doctor_pet_passives.h"
#include "dc_witch_doctor_passive_common.h"
#include "dc_witch_doctor_passive_rules.h"
#include "dc_witch_doctor_pets_math.h"
#include "../../combat/dc_minions.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "GameTime.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <algorithm>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::WitchDoctor::Passive::Pets
{
    namespace
    {
        // Fierce Loyalty's speed for one Witch Doctor: the percent last found, until when it holds, the percent on the
        // sheet and the clock of the next look.
        struct Speed
        {
            double found = 0;
            std::uint64_t until = 0;
            double published = 0;
            double clock = 0;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Speed> speeds; // by Witch Doctor

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The Witch Doctor's pets: the Zombie Dogs, the Gargantuan, the Army's Fetishes and the Sycophants' Fetishes.
        std::vector<Creature*> StandingPets(Player* player)
        {
            std::vector<Creature*> pets;
            for (std::string_view group : WitchDoctor::Pets::PetGroups)
                for (Creature* pet : Minions::Standing(player, group))
                    pets.push_back(pet);
            return pets;
        }

        // Fierce Loyalty: "your movement speed is increased by {movement_speed_pct:base} ... increased to
        // {movement_speed_pct:out_of_combat} while a Gargantuan, Zombie Dog, or Fetish is not in combat": looked at
        // every 'Refresh Rate' and held for the file's seconds after a look that found a pet.
        void Look(Player* player, Speed& speed)
        {
            std::vector<Creature*> const pets = StandingPets(player);
            double found = 0.0;
            if (On(player, "Fierce Loyalty"))
                found = Rules::FierceSpeed(
                    !pets.empty(), std::any_of(pets.begin(), pets.end(), [](Creature* pet) { return !pet->IsInCombat(); }),
                    Num("Fierce Loyalty", "movement_speed_pct", "base"), Num("Fierce Loyalty", "movement_speed_pct", "out_of_combat"));
            std::uint64_t const now = Now();
            if (found > 0)
            {
                speed.found = found;
                speed.until = now + std::uint64_t(Tune("fierce_loyalty_hold_seconds") * 1000.0 + 0.5);
            }
            double const wanted = Rules::Open(0, now, speed.until) ? speed.found : 0.0;
            if (wanted == speed.published)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const id = Id("Fierce Loyalty");
            Stats::RemoveContribution(guid, Source::Passives, Stat::MovementSpeed, id);
            if (wanted > 0)
                Stats::AddContribution(guid, {Source::Passives, Stat::MovementSpeed, id, wanted, Bucket::Uncapped});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
            speed.published = wanted;
        }

        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_witch_doctor_pet_passives", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsWitchDoctor(player))
                    return;
                Speed speed;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    Speed& mine = speeds[player->GetGUID().GetRawValue()];
                    mine.clock += diff;
                    if (mine.clock < Tune("fierce_loyalty_check_seconds") * 1000.0)
                        return;
                    mine.clock = 0;
                    speed = mine;
                }
                Look(player, speed);
                std::lock_guard<std::mutex> guard(mutex);
                Speed& mine = speeds[player->GetGUID().GetRawValue()];
                mine.found = speed.found;
                mine.until = speed.until;
                mine.published = speed.published;
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                speeds.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    void Register()
    {
        new Update();
    }
} // namespace DC::Combat::WitchDoctor::Passive::Pets
