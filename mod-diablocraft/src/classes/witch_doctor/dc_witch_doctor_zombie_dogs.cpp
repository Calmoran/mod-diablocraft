/*
 * Summon Zombie Dogs and its runes. The cast raises the dogs on the pets' piece (dc_witch_doctor_pets.cpp: their count,
 * Life and blow) and the rune on the bar shapes each dog it raises: Burning Dogs      an aura of Fire round each dog, a
 * pulse every half second for the rune's weapon damage a second; Life Link         the dogs take a share of the damage
 * done to the Witch Doctor (Reduce); Rabid Dogs        every bite leaves a Poison damage over time, one running for
 * each dog; Chilled to the Bone  a slow on the enemy a dog bites and on the enemy that bites a dog; Leeching Beasts
 * every bite heals the Witch Doctor for a share of their Life on Hit. A dog keeps the rune it was raised with; a cast
 * with another rune on the bar sends the standing dogs away and raises them anew.
 */

#include "dc_witch_doctor_zombie_dogs.h"
#include "dc_witch_doctor_bar.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_pets.h"
#include "dc_witch_doctor_pets_math.h"
#include "dc_witch_doctor_zombie_dogs_math.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <mutex>
#include <string_view>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::ZombieDogs
{
    namespace
    {
        constexpr std::string_view Skill = "Summon Zombie Dogs", Group = "dog";

        enum class Rune
        {
            None,
            BurningDogs,
            LifeLink,
            RabidDogs,
            ChilledToTheBone,
            LeechingBeasts
        };

        Rune RuneOf(std::string_view name)
        {
            if (name == "Burning Dogs")
                return Rune::BurningDogs;
            if (name == "Life Link")
                return Rune::LifeLink;
            if (name == "Rabid Dogs")
                return Rune::RabidDogs;
            if (name == "Chilled to the Bone")
                return Rune::ChilledToTheBone;
            if (name == "Leeching Beasts")
                return Rune::LeechingBeasts;
            return Rune::None;
        }

        // The skill or rune of Summon Zombie Dogs on the Witch Doctor's bar: its record and rune. The skill's own
        // record with no rune, nothing when it is not on the bar.
        struct Slotted
        {
            std::uint32_t id = 0;
            Rune rune = Rune::None;
        };

        Slotted OnBar(Player* owner)
        {
            auto const slot = WitchDoctor::OnBar(owner, Skill);
            return {slot.id, RuneOf(slot.rune)};
        }

        std::uint32_t RecordOf(Slotted const& slot)
        {
            return slot.id ? slot.id : BaseId(Skill);
        }

        double Num(std::uint32_t record, char const* token)
        {
            return Numbers::Num(record, token);
        }

        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::uint32_t>
            raisedWith; // by Witch Doctor: the record of the rune its dogs were raised with
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId))
            return;
        std::uint32_t const record = RecordOf(OnBar(player));
        bool keep = true;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = raisedWith.find(player->GetGUID().GetRawValue());
            keep = found == raisedWith.end() || KeepsDogs(found->second, record);
        }
        if (!keep)
            Minions::Dismiss(player, Group);
        Pets::SummonDogs(player);
    }

    void Shape(Player* owner, Minions::Kind& kind)
    {
        Slotted const slot = OnBar(owner);
        std::uint32_t const id = RecordOf(slot);
        {
            std::lock_guard<std::mutex> guard(mutex);
            raisedWith[owner->GetGUID().GetRawValue()] = id;
        }
        // Midnight Feast raises the dogs' blow; a rune's own damage is raised by the same factor.
        double const base = Num(BaseId(Skill), "damage_pct"), blow = kind.damagePct;
        switch (slot.rune)
        {
            case Rune::BurningDogs:
            {
                // "burning nearby enemies for {damage_pct} of your weapon damage as Fire every second": a pulse every
                // tick, each a share of that second's.
                double const tick = Tune("burning_dogs_tick_seconds");
                kind.auraRadius = Tune("burning_dogs_radius_yards");
                kind.auraRecord = id;
                kind.auraEveryMs = Pets::Millis(tick);
                kind.auraPct = PulsePct(Raised(Num(id, "damage_pct"), base, blow), tick);
                break;
            }
            case Rune::RabidDogs:
            {
                // "an infectious bite that deals {damage_pct} of your weapon damage as Poison over
                // {dot_duration_seconds} seconds".
                double const pct = Raised(Num(id, "damage_pct"), base, blow),
                             seconds = Num(id, "dot_duration_seconds"), tick = Tune("rabid_dogs_tick_seconds");
                kind.struckBy = [id, pct, seconds, tick](Player* player, Creature* dog, Unit* enemy) {
                    PeriodicStrike::Start(player, enemy, id, pct, seconds, tick,
                                          std::uint32_t(dog->GetGUID().GetCounter()));
                };
                break;
            }
            case Rune::ChilledToTheBone:
            {
                // "Enemies who hit or are hit by your Zombie Dogs are Chilled for {chill_duration_seconds} seconds."
                double const chill = Tune("chilled_to_the_bone_chill_pct"), seconds = Num(id, "chill_duration_seconds");
                kind.struckBy = [chill, seconds](Player* player, Creature*, Unit* enemy)
                { Slow(player, enemy, chill, seconds); };
                kind.hurt = [chill, seconds](Player* player, Unit* enemy) { Slow(player, enemy, chill, seconds); };
                break;
            }
            case Rune::LeechingBeasts:
            {
                // "heal you for {life_per_hit_share_pct} of your Life On Hit with every attack".
                double const share = Num(id, "life_per_hit_share_pct");
                kind.struckBy = [id, share](Player* player, Creature*, Unit*)
                {
                    if (auto const sheet = DC::Stats::Get(player->GetGUID().GetRawValue()))
                        Heal(player, id, Leeched((*sheet)[Stat::LifePerHit], share));
                };
                break;
            }
            default:
                break;
        }
    }

    double Reduce(Unit* victim, double damage)
    {
        Player* owner = victim ? victim->ToPlayer() : nullptr;
        if (!owner || damage <= 0)
            return damage;
        auto const dogs = Minions::Standing(owner, Group);
        if (dogs.empty())
            return damage;
        Slotted const slot = OnBar(owner);
        if (slot.rune != Rune::LifeLink)
            return damage;
        // "Your Zombie Dogs absorb {absorb_pct} of all damage done to you": they take it between them.
        double const share = LinkedShare(damage, Num(slot.id, "absorb_pct"));
        double const each = PerDog(share, unsigned(dogs.size()));
        if (each < 1.0)
            return damage;
        for (Creature* dog : dogs)
            Unit::DealDamage(nullptr, dog,
                             std::uint32_t(std::min(each, double(std::numeric_limits<std::uint32_t>::max()))), nullptr,
                             DIRECT_DAMAGE, SPELL_SCHOOL_MASK_NORMAL, nullptr, false);
        return damage - share;
    }
} // namespace DC::Combat::WitchDoctor::ZombieDogs
