/*
 * The Witch Doctor's pets on the shared piece (combat/dc_minions.h): what each kind is made of, from the skills'
 * sheets, the passives' sheets and the tunables, and the calls the skills and the Fetish Sycophants passive make. The
 * creatures are witch_doctor_summons.csv (entries 900170-900173). A pet is owner scaled (its blows are the Witch
 * Doctor's own Strike; its Life a share of theirs), counted as no monster and gone with its owner on logout and floor
 * change (the piece's rules). The runes of each skill are the skill's own bead's (Summon Zombie Dogs' is
 * dc_witch_doctor_zombie_dogs.cpp, which shapes each dog; the Gargantuan's is dc_witch_doctor_gargantuan.cpp).
 */

#include "dc_witch_doctor_pets.h"
#include "dc_witch_doctor_gargantuan.h"
#include "dc_witch_doctor_pets_math.h"
#include "dc_witch_doctor_zombie_dogs.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_minions_math.h"
#include "../../combat/dc_proc_math.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_tunables.h"
#include "Creature.h"
#include "Player.h"
#include "Random.h"

#include <algorithm>
#include <chrono>
#include <string_view>
#include <vector>

namespace DC::Combat::WitchDoctor::Pets
{
    namespace
    {
        constexpr std::string_view DogSkill = "Summon Zombie Dogs", GargantuanSkill = "Gargantuan",
                                   ArmySkill = "Fetish Army", SycophantPassive = "Fetish Sycophants";
        // The creatures of witch_doctor_summons.csv.
        constexpr std::uint32_t DogEntry = 900170, GargantuanEntry = 900171,
                                SycophantEntry = 900173;
        // The passives that let one more Zombie Dog stand, and the ones that raise the pets.
        constexpr std::string_view DogPassives[] = {"Zombie Handler", "Fierce Loyalty", "Midnight Feast"};

        double Tune(char const* name)
        {
            return DC::Tunables::Get("witchdoctor", name);
        }

        double Num(std::uint32_t record, char const* token)
        {
            return Numbers::Num(record, token);
        }

        std::uint32_t BaseId(std::string_view skill)
        {
            for (auto const& row : Shells::Abilities)
                if (skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        std::uint32_t PassiveId(std::string_view name)
        {
            for (auto const& row : Shells::Passives)
                if (name == row.name)
                    return row.id;
            return 0;
        }

        bool IsWitchDoctor(Player const* player)
        {
            return player && Classes::ClassIdOf(player) == Resources::Find("Witch Doctor", "mana")->classId;
        }

        bool Chosen(Player* owner, std::string_view passive)
        {
            for (std::string const& name : Classes::Passives(owner))
                if (name == passive)
                    return true;
            return false;
        }

        // What a passive the Witch Doctor has chosen states for `token`; 0 when it is not chosen.
        double FromPassive(Player* owner, std::string_view passive, char const* token)
        {
            return owner && Chosen(owner, passive) ? Num(PassiveId(passive), token) : 0.0;
        }

        unsigned DogCap(Player* owner)
        {
            double extra = 0;
            for (std::string_view passive : DogPassives)
                extra += FromPassive(owner, passive, "pet_count");
            return Pets::DogCap(Num(BaseId(DogSkill), "pet_count"), extra);
        }

        template<class Act>
        void After(Player* player, double seconds, Act act)
        {
            if (seconds <= 0)
                act();
            else
                player->m_Events.AddEventAtOffset(std::move(act), std::chrono::milliseconds(Millis(seconds)));
        }

        Position Beside(Player* owner, unsigned index)
        {
            return owner->GetNearPosition(2.0f, 1.0f + 0.6f * float(index));
        }

        // The Army's extra Fetishes (a rune's) for the Fetish being raised now; set by RaiseFetishes, which asks for
        // the kind at once.
        struct ArmyCast
        {
            unsigned extra = 0;
        } armyCast;

        // The Gargantuan's attack is a cleave: every other enemy in the arc in front of it, within its reach, is struck
        // as the one it hit is.
        void Cleave(Player* owner, Unit* struck, std::uint32_t record, double blowPct)
        {
            auto const standing = Minions::Standing(owner, "gargantuan");
            if (standing.empty())
                return;
            Creature* pet = standing.front();
            double const yards = Tune("gargantuan_cleave_yards"), degrees = Tune("gargantuan_cleave_degrees");
            double const centre = pet->GetAngle(struck);
            double const pct = Minions::BoostedPct(blowPct, Minions::BoostPercent(owner, "gargantuan"));
            for (Unit* other : Combat::Enemies(owner, record, pet->GetPosition(), yards))
                if (other != struck && other->IsAlive() &&
                    InCleave(pet->GetAngle(other), centre, pet->GetExactDist(other), yards, degrees))
                    Combat::Strike(owner, other, record, pct);
        }

        // Summon Zombie Dogs: "Each dog deals {damage_pct} of your weapon damage as Physical per hit"; the dogs strike
        // what the Witch Doctor strikes at the Witch Doctor's attack speed. Life: 35% of the Witch Doctor's, raised by
        // Zombie Handler; damage raised by Midnight Feast.
        Minions::Kind Dog(Player* owner)
        {
            std::uint32_t const record = BaseId(DogSkill);
            Minions::Kind kind;
            kind.group = "dog";
            kind.entry = DogEntry;
            kind.record = record;
            kind.damagePct =
                BlowPct(Num(record, "damage_pct"), FromPassive(owner, "Midnight Feast", "damage_bonus_pct"));
            kind.cap = DogCap(owner);
            kind.lifeToCopyPct =
                LifePct(Tune("zombie_dog_life_pct"), FromPassive(owner, "Zombie Handler", "pet_life_pct"));
            ZombieDogs::Shape(owner, kind);
            return kind;
        }

        // Gargantuan: "The Gargantuan attacks for {damage_pct} of your weapon damage as Physical": one, with a cleave
        // every few seconds of its own.
        Minions::Kind Gargantuan(Player* owner)
        {
            auto const own = GargantuanRunes::BlowOf(owner);
            std::uint32_t const record = own.record;
            double const feast = FromPassive(owner, "Midnight Feast", "damage_bonus_pct");
            double const blow = BlowPct(own.pct, feast);
            Minions::Kind kind;
            kind.group = "gargantuan";
            kind.entry = GargantuanEntry;
            kind.record = record;
            kind.damagePct = blow;
            kind.cap = 1;
            kind.swingMs = Millis(Tune("gargantuan_swing_seconds"));
            kind.lifeToCopyPct =
                LifePct(Tune("gargantuan_life_pct"), FromPassive(owner, "Zombie Handler", "pet_life_pct"));
            kind.struck = [record, blow](Player* player, Unit* enemy) { Cleave(player, enemy, record, blow); };
            GargantuanRunes::Shape(owner, kind, feast);
            return kind;
        }

        // Fetish Army: "Summon an army of {pet_count} dagger-wielding Fetishes to fight by your side for
        // {duration_seconds} seconds. The Fetishes attack for {damage_pct} of your weapon damage as Physical." The
        // power files state no Life for a Fetish: it is a share of the Witch Doctor's, as the dogs' is.
        Minions::Kind Fetish(Player*)
        {
            std::uint32_t const record = BaseId(ArmySkill);
            Minions::Kind kind;
            kind.group = "fetish";
            kind.entry = FetishEntry;
            kind.record = record;
            kind.damagePct = Num(record, "damage_pct");
            kind.lifeMs = Millis(Num(record, "duration_seconds"));
            kind.lifeToCopyPct = Tune("fetish_life_pct");
            kind.cap = unsigned(Num(record, "pet_count")) + armyCast.extra;
            return kind;
        }

        // Fetish Sycophants: "summon a dagger-wielding Fetish to fight by your side for {duration_seconds} seconds"; it
        // strikes as the Army's dagger does.
        Minions::Kind Sycophant(Player*)
        {
            std::uint32_t const record = BaseId(ArmySkill);
            Minions::Kind kind;
            kind.group = "sycophant";
            kind.entry = SycophantEntry;
            kind.record = record;
            kind.damagePct = Num(record, "damage_pct");
            kind.lifeMs = Millis(Num(PassiveId(SycophantPassive), "duration_seconds"));
            kind.lifeToCopyPct = Tune("fetish_life_pct");
            kind.cap = unsigned(Tune("fetish_sycophants_max"));
            return kind;
        }

        // `count` Fetishes of the kind `key` on the ring round the Witch Doctor, one every spawn interval from the `firstIndex`th; the daggers'
        // cap is raised by `capExtra` (a rune's) while one is being raised.
        unsigned Ring(Player* owner, std::string const& key, unsigned count, unsigned firstIndex, unsigned capExtra,
                      Arrival arrival)
        {
            if (!owner || !owner->IsInWorld() || !owner->IsAlive())
                return 0;
            double const interval = Tune("fetish_spawn_interval_seconds");
            double const low = Tune("fetish_ring_min_yards"), high = Tune("fetish_ring_max_yards");
            Position const centre = owner->GetPosition();
            for (unsigned i = 0; i < count; ++i)
            {
                Offset const offset = RingPoint(low, high, rand_norm(), rand_norm());
                After(owner, (firstIndex + i) * interval,
                      [owner, centre, offset, capExtra, key, arrival]
                      {
                          if (!owner->IsInWorld() || !owner->IsAlive())
                              return;
                          float x = centre.GetPositionX() + float(offset.x), y = centre.GetPositionY() + float(offset.y),
                                z = centre.GetPositionZ();
                          owner->UpdateGroundPositionZ(x, y, z);
                          Position at(x, y, z, centre.GetOrientation());
                          if (arrival.where)
                              at = arrival.where(owner, at);
                          armyCast.extra = capExtra;
                          Minions::Raise(owner, key, at);
                          armyCast = {};
                          if (arrival.landed)
                              arrival.landed(owner, at);
                      });
            }
            return count;
        }

        // A spell of the pets' own skills is not one the Witch Doctor hits with: their blows are the pets'.
        bool IsPetSkill(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && (DogSkill == row->skill || GargantuanSkill == row->skill || ArmySkill == row->skill);
        }
    } // namespace

    unsigned SummonDogs(Player* owner)
    {
        if (!owner || !owner->IsInWorld() || !owner->IsAlive())
            return 0;
        unsigned const cap = DogCap(owner);
        unsigned const standing = Minions::Alive(owner, "dog");
        unsigned raised = 0;
        while (standing + raised < cap && Minions::Raise(owner, "zombie_dog", Beside(owner, standing + raised)))
            ++raised;
        return raised;
    }

    Creature* RaiseDogAt(Player* owner, Position const& at)
    {
        if (!owner || !owner->IsInWorld() || !owner->IsAlive() || Minions::Alive(owner, "dog") >= DogCap(owner))
            return nullptr;
        return Minions::Raise(owner, "zombie_dog", at);
    }

    Creature* RaiseGargantuan(Player* owner, Position const& at)
    {
        if (!owner)
            return nullptr;
        Minions::Dismiss(owner, "gargantuan");
        return Minions::Raise(owner, "gargantuan", at);
    }

    unsigned RaiseFetishes(Player* owner, unsigned extra, Arrival arrival)
    {
        return Ring(owner, "fetish", unsigned(Num(BaseId(ArmySkill), "pet_count")) + extra, 0, extra, std::move(arrival));
    }

    unsigned RaiseOnRing(Player* owner, std::string const& key, unsigned count, unsigned firstIndex)
    {
        return Ring(owner, key, count, firstIndex, 0, {});
    }

    bool HasDog(Player* owner)
    {
        return owner && Minions::Alive(owner, "dog") > 0;
    }

    std::optional<Position> SacrificeDog(Player* owner)
    {
        return Minions::DismissOldest(owner, "dog");
    }

    void Landed(Player* owner, Unit*, std::uint32_t spellId)
    {
        if (!IsWitchDoctor(owner) || !Chosen(owner, SycophantPassive) || IsPetSkill(spellId))
            return;
        if (!MaySummonSycophant(Minions::Alive(owner, "sycophant"), unsigned(Tune("fetish_sycophants_max"))))
            return;
        // "When you hit enemies with your spells, you have up to a {proc_chance_pct} chance": scaled by the spell's
        // proc coefficient; a spell that states none never summons.
        if (!Proc::Rolls(Numbers::Get(spellId, "proc_coefficient"),
                         FromPassive(owner, SycophantPassive, "proc_chance_pct"),
                         [](float pct) { return roll_chance_f(pct); }))
            return;
        Minions::Raise(owner, "fetish_sycophant", Beside(owner, 0));
    }

    void RegisterScripts()
    {
        Minions::Define("zombie_dog", Dog);
        Minions::Define("gargantuan", Gargantuan);
        Minions::Define("fetish", Fetish);
        Minions::Define("fetish_sycophant", Sycophant);
    }
} // namespace DC::Combat::WitchDoctor::Pets
