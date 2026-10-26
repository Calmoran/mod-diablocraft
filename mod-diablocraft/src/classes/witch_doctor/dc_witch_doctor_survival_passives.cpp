/*
 * The Witch Doctor's passives that keep the Witch Doctor alive. Zombie Handler's Life is a number on the sheet (Life
 * percent) that a small update script keeps while the passive is on, as Swampland Attunement's resistances are (a
 * number for the enemies about, looked at every half second); Spirit Vessel answers the damage a blow would deal: a
 * blow that would be fatal deals nothing and opens a short window in which every blow does nothing, and heals the
 * Witch Doctor, once in the passive's cooldown; Grave Injustice rides the Witch Doctor's kills.
 */

#include "dc_witch_doctor_survival_passives.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_passive_common.h"
#include "dc_witch_doctor_passive_rules.h"
#include "../../combat/dc_combat.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "GameTime.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <mutex>
#include <optional>
#include <unordered_map>
#include <unordered_set>

namespace DC::Combat::WitchDoctor::Passive::Survival
{
    namespace
    {
        struct Vessel
        {
            std::optional<std::uint64_t> last; // when it last saved the Witch Doctor
            std::uint64_t opened = 0;          // when the window it opened began
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Vessel> vessels; // by Witch Doctor
        std::unordered_set<std::uint64_t> handled;         // the Witch Doctors whose sheet holds Zombie Handler's Life
        std::unordered_map<std::uint64_t, double>
            resists; // by Witch Doctor: the points Swampland Attunement has put on
        std::unordered_map<std::uint64_t, double>
            looks; // by Witch Doctor: the clock of its next look at the enemies about

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(seconds * 1000.0 + 0.5);
        }

        // The radius a passive reaches: its own and the gold pickup radius ("The range of this effect is increased by
        // your gold pickup radius").
        double Reach(Player* player, char const* passive)
        {
            auto const sheet = Stats::Get(player->GetGUID().GetRawValue());
            return Num(passive, "radius_yards") + (sheet ? (*sheet)[Stat::GoldPickupRange] : 0.0);
        }

        // Zombie Handler: "Your Life ... increased by {pet_life_pct}", on the sheet while the passive is on.
        void Life(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            bool const wanted = On(player, "Zombie Handler");
            {
                std::lock_guard<std::mutex> guard(mutex);
                if ((handled.count(guid) > 0) == wanted)
                    return;
                if (wanted)
                    handled.insert(guid);
                else
                    handled.erase(guid);
            }
            std::uint32_t const id = Id("Zombie Handler");
            Stats::RemoveContribution(guid, Source::Passives, Stat::LifePercent, id);
            if (wanted)
                Stats::AddContribution(guid, {Source::Passives, Stat::LifePercent, id,
                                              Num("Zombie Handler", "pet_life_pct"), Bucket::Flat});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // Swampland Attunement: "You and your pets gain {resistance_points} Physical, Poison, Fire, and Cold Resistance
        // for every enemy within {radius_yards} yards": the points a level gives for each of up to the file's most
        // enemies.
        void Resist(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            double wanted = 0.0;
            if (On(player, "Swampland Attunement"))
                wanted = Rules::ResistPoints(
                    player->GetLevel(), Tune("swampland_resistance_per_level"),
                    unsigned(Combat::Enemies(player, Id("Swampland Attunement"), player->GetPosition(),
                                             Reach(player, "Swampland Attunement"))
                                 .size()),
                    unsigned(Tune("swampland_most_enemies")));
            {
                std::lock_guard<std::mutex> guard(mutex);
                double& had = resists[guid];
                if (had == wanted)
                    return;
                had = wanted;
            }
            for (Element element : {Element::Physical, Element::Poison, Element::Fire, Element::Cold})
            {
                std::uint64_t const id = std::uint64_t(Id("Swampland Attunement")) * ElementCount + unsigned(element);
                Stats::RemoveContribution(guid, Source::Passives, Stat::SingleResistance, id);
                if (wanted > 0)
                    Stats::AddContribution(
                        guid, {Source::Passives, Stat::SingleResistance, id, wanted, Bucket::Flat, element});
            }
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // Grave Injustice: "Gain {heal_pct} of your maximum Life and Mana and reduce the cooldown of all of your skills
        // by {cooldown_reduction_seconds} second when an enemy dies within {radius_yards} yards."
        void Gather(Player* player, Creature* dead)
        {
            if (!On(player, "Grave Injustice") ||
                !Rules::Near(player->GetExactDist(dead), Num("Grave Injustice", "radius_yards"),
                             Reach(player, "Grave Injustice") - Num("Grave Injustice", "radius_yards")))
                return;
            std::uint32_t const id = Id("Grave Injustice");
            double const pct = Num("Grave Injustice", "heal_pct");
            Heal(player, id, Rules::Share(double(player->GetMaxHealth()), pct));
            Resources::Energize(player, Resources::Mana, id,
                                Rules::Share(Resources::Max(player, Resources::Mana), pct));
            for (Classes::Slot const& slot : Classes::Bar(player))
                if (std::uint32_t const left = player->GetSpellCooldownDelay(slot.spellId))
                    Combat::SendSkillCooldown(
                        player, slot.spellId,
                        Rules::CooledBy(left, Num("Grave Injustice", "cooldown_reduction_seconds")));
        }

        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_witch_doctor_survival_passives",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_CREATURE_KILL})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsWitchDoctor(player))
                    return;
                Life(player);
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    double& clock = looks[player->GetGUID().GetRawValue()];
                    clock += diff;
                    if (clock < Tune("swampland_check_seconds") * 1000.0)
                        return;
                    clock = 0;
                }
                Resist(player);
            }

            void OnPlayerCreatureKill(Player* killer, Creature* killed) override
            {
                if (IsWitchDoctor(killer) && killed)
                    Gather(killer, killed);
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                handled.erase(guid);
                vessels.erase(guid);
                resists.erase(guid);
                looks.erase(guid);
            }
        };
    } // namespace

    double Reduce(Unit* victim, double damage)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (!player || damage <= 0 || !On(player, "Spirit Vessel"))
            return damage;
        std::uint64_t const now = Now(), lasts = Millis(Num("Spirit Vessel", "duration_seconds"));
        {
            std::lock_guard<std::mutex> guard(mutex);
            Vessel& vessel = vessels[player->GetGUID().GetRawValue()];
            // The window the last save opened: every blow in it does nothing.
            if (vessel.last && Rules::Open(vessel.opened, now, lasts))
                return 0.0;
            // "When you receive fatal damage ... This effect may occur once every {internal_cooldown_seconds} seconds."
            if (!Rules::Fatal(damage, double(player->GetHealth())) ||
                !Rules::Ready(vessel.last, now, Millis(Num("Spirit Vessel", "internal_cooldown_seconds"))))
                return damage;
            vessel.last = now;
            vessel.opened = now;
        }
        // "you automatically enter the spirit realm for {duration_seconds} seconds and heal to {heal_pct} of your
        // maximum Life".
        Heal(player, Id("Spirit Vessel"), double(player->GetMaxHealth()) * Num("Spirit Vessel", "heal_pct") / 100.0);
        return 0.0;
    }

    void Register()
    {
        new Update();
    }
} // namespace DC::Combat::WitchDoctor::Passive::Survival
