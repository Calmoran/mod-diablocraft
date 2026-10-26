#pragma once
// Spirit Barrage's rules that need no core type, header-only so tests/witch_doctor_spirit_barrage compiles this exact
// code: which rune is which, when each bolt lands, what a bolt deals, the Life Phlebotomize returns at a level, when
// Well of Souls' spirits fly, what a Phantasm tick and a Manitou bolt deal and how many barrages may be in the air. The
// production half is dc_witch_doctor_spirit_barrage.cpp.
#include "../../combat/dc_healing_table.h"
#include "../../combat/dc_periodic_strike.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::SpiritBarrage
{
    enum class Rune
    {
        None,
        Phlebotomize,       // Life for each hit, Cold
        WellOfSouls,        // more spirits that seek other enemies, Fire
        Phantasm,           // a spectre that burns the enemies about it, Cold
        TheSpiritIsWilling, // Mana for each hit, Cold
        Manitou             // a spectre that hovers over you and shoots, Cold
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Phlebotomize")
            return Rune::Phlebotomize;
        if (name == "Well of Souls")
            return Rune::WellOfSouls;
        if (name == "Phantasm")
            return Rune::Phantasm;
        if (name == "The Spirit Is Willing")
            return Rune::TheSpiritIsWilling;
        if (name == "Manitou")
            return Rune::Manitou;
        return Rune::None;
    }

    // Well of Souls names Fire for its extra spirits alone: the barrage's own bolts keep the skill's Cold.
    inline bool BoltTakesRuneElement(Rune rune)
    {
        return rune != Rune::WellOfSouls;
    }

    // "Base: Damage Scalar = Base Total Damage / Barrage Count": the percent each of the `count` bolts deals.
    inline double BoltPct(double totalPct, unsigned count)
    {
        return count ? totalPct / count : 0.0;
    }

    // The milliseconds after the cast the `index`th bolt (0 first) lands: the delay until a hit, and before each later
    // bolt the base gap, longer by `delta` for each bolt before it ("Delay Between Barrages Base" and "Delta").
    inline std::uint32_t BoltLandsMs(unsigned index, double hitDelaySeconds, double gapSeconds, double deltaSeconds)
    {
        double seconds = hitDelaySeconds;
        for (unsigned bolt = 0; bolt < index; ++bolt)
            seconds += gapSeconds + deltaSeconds * bolt;
        return std::uint32_t(std::max(0.0, seconds) * 1000.0 + 0.5);
    }

    // The sheet's Life at level 70 ("{heal_per_hit_life}", D3's 1.2% of the Healing table) at `level`.
    inline double LevelLife(double sheetLife, unsigned level)
    {
        return sheetLife * Healing::At(level) / Healing::At(70);
    }

    // Well of Souls: "An additional {projectile_count} spirits": released every `rateSeconds` while the missile buff of
    // `buffSeconds` lasts, never more than the sheet's count.
    inline unsigned WellSpirits(unsigned count, double buffSeconds, double rateSeconds)
    {
        if (rateSeconds <= 0)
            return 0;
        return std::min(count, unsigned(std::floor(buffSeconds / rateSeconds + 1e-9)) + 1);
    }

    // The milliseconds after the barrage's first hit the `index`th spirit (0 first) flies.
    inline std::uint32_t WellFliesMs(unsigned index, double rateSeconds)
    {
        return std::uint32_t(index * rateSeconds * 1000.0 + 0.5);
    }

    // Manitou: "{damage_pct} weapon damage ... over {dot_duration_seconds} seconds" in bolts every `tickSeconds`: the
    // percent of one bolt. No tick, none.
    inline double SpectreBoltPct(double totalPct, double seconds, double tickSeconds)
    {
        return PeriodicStrike::TickPct(totalPct, PeriodicStrike::Ticks(seconds, tickSeconds));
    }

    // "MAX Active Barrages": a cast may send its bolts while fewer than `most` are in the air; no limit stated, no
    // refusal.
    inline bool MayBombard(unsigned inTheAir, unsigned most)
    {
        return most == 0 || inTheAir < most;
    }

    // No enemy.
    constexpr std::size_t none = std::size_t(-1);
    // The enemies other than the one at `aimed` (an index into the distances, or none): the indices of those within
    // `within` yards, in the order given.
    inline std::vector<std::size_t> Others(std::vector<double> const& distances, std::size_t aimed, double within)
    {
        std::vector<std::size_t> others;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (i != aimed && distances[i] <= within)
                others.push_back(i);
        return others;
    }

    // The production half (dc_witch_doctor_spirit_barrage.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The cast's own hit: none; the bolts strike for themselves.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets`: the bolts, the rune's part.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The scripts: a logout clears the barrages counted in the air and the Manitou on record.
    void RegisterScripts();
} // namespace DC::Combat::WitchDoctor::SpiritBarrage
