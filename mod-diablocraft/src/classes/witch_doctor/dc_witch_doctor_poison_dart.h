#pragma once
// Poison Dart's rules that need no core type, header-only so tests/witch_doctor_poison_dart compiles this exact code:
// which rune is which, when each of Splinters' darts leaves, the chance of Snake to the Face's stun. The production
// half is dc_witch_doctor_poison_dart.cpp.
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::PoisonDart
{
    enum class Rune
    {
        None,
        FlamingDart,   // a Fire damage over time besides the poison, Fire
        Splinters,     // three darts in place of one hit with its poison
        NumbingDart,   // the enemy is slowed, Cold
        SpinedDart,    // Mana for each hit (the class's Connected), Physical
        SnakeToTheFace // a chance to stun
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Flaming Dart")
            return Rune::FlamingDart;
        if (name == "Splinters")
            return Rune::Splinters;
        if (name == "Numbing Dart")
            return Rune::NumbingDart;
        if (name == "Spined Dart")
            return Rune::SpinedDart;
        if (name == "Snake to the Face")
            return Rune::SnakeToTheFace;
        return Rune::None;
    }

    // "Shoot {projectile_count} Poison Darts": the milliseconds after the cast the `index`th dart leaves, the first
    // with the cast and the rest a shot delay apart.
    inline std::uint32_t DartDelayMs(unsigned index, double shotDelaySeconds)
    {
        return std::uint32_t((shotDelaySeconds > 0 ? shotDelaySeconds : 0.0) * 1000.0 * index + 0.5);
    }

    // "has a {proc_chance_pct} chance to Stun": whether a roll of 0 to 100 stuns.
    inline bool Stuns(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // The production half (dc_witch_doctor_poison_dart.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The dart's own hit: the skill's `hit` number for every rune but Splinters, whose darts each deal the rune's own.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets`: Splinters' other darts.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // A dart landed on `target`: the poison, Flaming Dart's fire, Numbing Dart's slow, Snake to the Face's stun.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::WitchDoctor::PoisonDart
