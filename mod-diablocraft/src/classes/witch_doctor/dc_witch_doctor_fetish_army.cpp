/*
 * Fetish Army and its runes. The cast raises the daggers on the pets' piece (dc_witch_doctor_pets.cpp: their count,
 * Life, blow and seconds) and the rune adds to them: Fetish Ambush       each dagger appears on an enemy near the Witch
 * Doctor and strikes the enemies round it as it arrives; Legion of Daggers   more daggers (the pets' piece raises
 * them); Tiki Torchers       casters that breathe fire in a cone in front of them; Devoted Following   a shorter
 * cooldown (the rune's record); Head Hunters        hunters that shoot blowdarts in a cone at an enemy. The casters and
 * the hunters are kinds of their own on the shared minions piece, raised on the same ring after the daggers.
 */

#include "dc_witch_doctor_fetish_army.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_fetish_army_math.h"
#include "dc_witch_doctor_pets.h"
#include "dc_witch_doctor_pets_math.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "Creature.h"
#include "Player.h"
#include "Random.h"
#include "Unit.h"

#include <string_view>

namespace DC::Combat::WitchDoctor::FetishArmy
{
    namespace
    {
        constexpr std::string_view Skill = "Fetish Army";

        double Num(std::uint32_t record, char const* token)
        {
            return Numbers::Num(record, token);
        }

        // What a rune states itself: the Fetishes it adds, not the skill's own.
        double Own(std::uint32_t record, char const* token)
        {
            return Numbers::Own(record, token).value_or(0.0);
        }

        std::uint32_t RuneId(std::string_view rune)
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && rune == row.rune)
                    return row.id;
            return 0;
        }

        // The enemies in the arc in front of a caster or a hunter, round the one it struck, are struck as it is.
        void Cone(Player* owner, Creature* fetish, Unit* struck, std::uint32_t record, double pct, double yards,
                  double degrees)
        {
            double const centre = fetish->GetAngle(struck);
            for (Unit* other : Combat::Enemies(owner, record, fetish->GetPosition(), yards))
                if (other != struck && other->IsAlive() &&
                    Pets::InCleave(fetish->GetAngle(other), centre, fetish->GetExactDist(other), yards, degrees))
                    Combat::Strike(owner, other, record, pct);
        }

        // A caster or a hunter: its blow is the rune's, struck at the owner's enemy from `range` yards and over the
        // cone; its first blow is at once.
        Minions::Kind Ranged(char const* group, std::uint32_t id, double swingSeconds, double range, double degrees)
        {
            std::uint32_t const base = BaseId(Skill);
            double const pct = Num(id, "damage_pct");
            Minions::Kind kind;
            kind.group = group;
            kind.entry = Pets::FetishEntry;
            kind.record = id;
            kind.damagePct = pct;
            kind.swingMs = Pets::Millis(swingSeconds);
            kind.rangeYards = range;
            kind.firstSwingAtOnce = true;
            kind.lifeMs = Pets::Millis(Num(base, "duration_seconds"));
            kind.lifeToCopyPct = Tune("fetish_life_pct");
            kind.cap = unsigned(Own(id, "pet_count"));
            kind.struckBy = [id, pct, range, degrees](Player* player, Creature* fetish, Unit* enemy)
            { Cone(player, fetish, enemy, id, pct, range, degrees); };
            return kind;
        }

        // Fetish Ambush: each dagger "apparates" on an enemy within the ring's reach and "deals {damage_pct} weapon
        // damage as Cold to any nearby enemy as it is summoned".
        Pets::Arrival Ambush()
        {
            std::uint32_t const id = RuneId("Fetish Ambush");
            Pets::Arrival arrival;
            arrival.where = [id](Player* player, Position const& ring) -> Position
            {
                if (!Apparates(frand(0.0f, 100.0f), Tune("fetish_ambush_chance_pct")))
                    return ring;
                auto const enemies = Combat::Enemies(player, id, player->GetPosition(), Tune("fetish_ring_max_yards"));
                return enemies.empty() ? ring : enemies[Pick(enemies.size(), rand_norm())]->GetPosition();
            };
            arrival.landed = [id](Player* player, Position const& at)
            {
                for (Unit* enemy : Combat::Enemies(player, id, at, Tune("fetish_ambush_radius_yards")))
                    Combat::Strike(player, enemy, id, Num(id, "damage_pct"));
            };
            return arrival;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        auto const* row = RowOf(spellId, Skill);
        if (!player || !row)
            return;
        std::string_view const rune = row->rune;
        unsigned const daggers = unsigned(Num(BaseId(Skill), "pet_count"));
        if (rune == "Legion of Daggers")
            Pets::RaiseFetishes(player, unsigned(Own(spellId, "pet_count")));
        else if (rune == "Fetish Ambush")
            Pets::RaiseFetishes(player, 0, Ambush());
        else
            Pets::RaiseFetishes(player);
        // The casters and the hunters come after the daggers.
        if (rune == "Tiki Torchers")
            Pets::RaiseOnRing(player, "fetish_caster", unsigned(Own(spellId, "pet_count")), daggers);
        if (rune == "Head Hunters")
            Pets::RaiseOnRing(player, "fetish_hunter", unsigned(Own(spellId, "pet_count")), daggers);
    }

    void RegisterScripts()
    {
        // "Fetish casters who breathe fire in a cone in front of them" and "Hunter Fetishes that shoot blowdarts": the
        // power files of the Shaman and the Hunter give each its pause between blows, its reach and the angle of its
        // cone.
        Minions::Define("fetish_caster",
                        [](Player*)
                        {
                            return Ranged("fetish_caster", RuneId("Tiki Torchers"), Tune("fetish_caster_swing_seconds"),
                                          Tune("fetish_caster_range_yards"), Tune("fetish_caster_cone_degrees"));
                        });
        Minions::Define("fetish_hunter",
                        [](Player*)
                        {
                            return Ranged("fetish_hunter", RuneId("Head Hunters"), Tune("fetish_hunter_swing_seconds"),
                                          Tune("fetish_hunter_range_yards"), Tune("fetish_hunter_cone_degrees"));
                        });
    }
} // namespace DC::Combat::WitchDoctor::FetishArmy
