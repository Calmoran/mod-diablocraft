#pragma once
// Hex's rules that need no core type, header-only so tests/witch_doctor_hex compiles this exact code: which rune is
// which, what the Fetish Shaman does each cycle, when the one chain of cycles of a cast runs next and when it ends with its
// Shaman, the heal Hedge Magic gives at a level,
// the Toad's poison ticks, the Angry Chicken's explosion (on the next press or when its time is over, once), and the
// enemies Unstable Form remembers as hexed. The production half is dc_witch_doctor_hex.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iterator>
#include <optional>
#include <string_view>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::Hex
{
    enum class Rune
    {
        None,
        ToadOfHugeness, // a giant toad pulls the group in, swallows it and spits it out poisoned, slowed and softened
        AngryChicken,   // the Witch Doctor is the chicken, and it explodes
        UnstableForm,   // hexed enemies explode when killed
        HedgeMagic,     // the Shaman heals allies
        Jinx            // hexed enemies take more damage
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Toad of Hugeness")
            return Rune::ToadOfHugeness;
        if (rune == "Angry Chicken")
            return Rune::AngryChicken;
        if (rune == "Unstable Form")
            return Rune::UnstableForm;
        if (rune == "Hedge Magic")
            return Rune::HedgeMagic;
        if (rune == "Jinx")
            return Rune::Jinx;
        return Rune::None;
    }

    // "Summon a Fetish Shaman ... that will hex groups of enemies": every rune but the Angry Chicken, which is the
    // Witch Doctor turned into the chicken, has the Shaman.
    inline bool RaisesShaman(Rune rune)
    {
        return rune != Rune::AngryChicken;
    }

    // What the Shaman does in a cycle to the group it picks: it hexes the group, except for the Toad, whose toad pulls
    // it in and spits it out instead.
    inline bool Hexes(Rune rune)
    {
        return RaisesShaman(rune) && rune != Rune::ToadOfHugeness;
    }

    // The Shaman acts once at the start and then every `cycleMs` for as long as it stands (`lifeMs`): the cycle after the one
    // at `elapsedMs` of its life, when it begins before the Shaman is gone; nothing when it would not. A cast starts the first
    // cycle and each cycle asks for the next, so a cast has one chain and never two.
    inline std::optional<std::uint64_t> NextCycle(std::uint64_t elapsedMs, std::uint64_t cycleMs, std::uint64_t lifeMs)
    {
        if (cycleMs == 0)
            return std::nullopt;
        std::uint64_t const next = elapsedMs + cycleMs;
        return next < lifeMs ? std::optional<std::uint64_t>(next) : std::nullopt;
    }

    // A chain (the cycles, Hedge Magic's heals) belongs to the Shaman its cast raised and ends with it: it goes on only while
    // the Shaman standing for the owner is that one. A second cast sends the first Shaman away and raises another, and the
    // first cast's chains must not run on in the new one.
    inline bool ChainStands(std::uint64_t chainShaman, std::uint64_t standingShaman)
    {
        return chainShaman != 0 && chainShaman == standingShaman;
    }

    // An enemy is in the group the Shaman picked when it is within the group's radius of the enemy it picked.
    inline bool InGroup(double distance, double radius)
    {
        return radius > 0 && distance <= radius;
    }

    // Hedge Magic: "heal allies for {heal_life} Life": the sheet's number is the heal at level 70; a lower level heals
    // the share of it that D3's Healing table gives that level.
    inline double HedgeHeal(double sheetHeal, double tableAtLevel, double tableAtSheetLevel)
    {
        return sheetHeal > 0 && tableAtLevel > 0 && tableAtSheetLevel > 0 ? sheetHeal * tableAtLevel / tableAtSheetLevel
                                                                          : 0.0;
    }

    // The Toad's poison: `totalPct` of weapon damage over `seconds`, a tick every `tickSeconds`: how many ticks and the
    // share of the total each one deals.
    inline unsigned PoisonTicks(double seconds, double tickSeconds)
    {
        return seconds > 0 && tickSeconds > 0 ? unsigned(std::floor(seconds / tickSeconds + 1e-9)) : 0u;
    }

    inline double PoisonTickPct(double totalPct, unsigned ticks)
    {
        return ticks && totalPct > 0 ? totalPct / ticks : 0.0;
    }

    // The Angry Chicken: it explodes once, on the next press of Hex while it lasts or when its time is over, whichever
    // comes first.
    struct Chicken
    {
        std::uint64_t until = 0; // ms: the chicken is over from this moment on
        bool live = false;

        void Start(std::uint64_t now, std::uint64_t ms)
        {
            until = now + ms;
            live = ms > 0;
        }

        // A press at `now`: true when it sets the explosion off.
        bool Press(std::uint64_t now)
        {
            if (!live || now >= until)
                return false;
            live = false;
            return true;
        }

        // The look at `now`: true once, when the time ran out with no press.
        bool Expired(std::uint64_t now)
        {
            if (!live || now < until)
                return false;
            live = false;
            return true;
        }
    };

    // Unstable Form: the enemies one Witch Doctor has hexed and until when; an enemy that dies while hexed explodes
    // once.
    struct Hexed
    {
        std::unordered_map<std::uint64_t, std::uint64_t> until; // enemy -> ms the hex is over from

        void Mark(std::uint64_t enemy, std::uint64_t now, std::uint64_t ms)
        {
            // an enemy whose hex ran out without its dying is forgotten here, so the list stays the size of the hexed
            for (auto it = until.begin(); it != until.end();)
                it = it->second <= now ? until.erase(it) : std::next(it);
            auto& end = until[enemy];
            end = std::max(end, now + ms);
        }

        // The enemy died at `now`: true when it was hexed, and it is forgotten.
        bool Died(std::uint64_t enemy, std::uint64_t now)
        {
            auto found = until.find(enemy);
            if (found == until.end())
                return false;
            bool const hexed = found->second > now;
            until.erase(found);
            return hexed;
        }
    };
} // namespace DC::Combat::WitchDoctor::Hex
