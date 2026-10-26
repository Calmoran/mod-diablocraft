#pragma once
// The rules of Leech's runes that need no core type, header-only so tests/necromancer_leech compiles this exact code: which rune is
// which, and what each heal is worth. The production half is dc_necromancer_leech.cpp.
#include <algorithm>
#include <string_view>

namespace DC::Combat::Necromancer::Leech
{
    enum class Rune
    {
        None,
        Osmosis,
        Transmittable,
        SanguineEnd,
        CursedGround,
        BloodFlask
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Osmosis")
            return Rune::Osmosis;
        if (name == "Transmittable")
            return Rune::Transmittable;
        if (name == "Sanguine End")
            return Rune::SanguineEnd;
        if (name == "Cursed Ground")
            return Rune::CursedGround;
        if (name == "Blood Flask")
            return Rune::BloodFlask;
        return Rune::None;
    }

    // Every rune but Cursed Ground leaves the skill's own curse: a cursed enemy that is struck heals the attacker.
    inline bool HealsWhenStruck(Rune rune)
    {
        return rune != Rune::CursedGround;
    }

    // The curse on the enemies themselves; Cursed Ground curses the ground instead.
    inline bool CursesEnemies(Rune rune)
    {
        return rune != Rune::CursedGround;
    }

    // "heal the attacker for {heal_pct} of their total health": the Life of one struck hit.
    inline double StruckHeal(double maxLife, double healPct)
    {
        return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 : 0.0;
    }

    // Osmosis: the Life per second one cursed enemy gives. The power scales it with the level, `share` of D3's Healing table at the
    // Necromancer's level (`healing`): 0.0014 of the table's 536421 at level 70 is the tooltip's 751.
    inline double OsmosisPerEnemy(double share, double healing)
    {
        return std::max(0.0, share) * std::max(0.0, healing);
    }

    // Osmosis: "increases your life regeneration by {heal_per_second_life} per second" for each cursed enemy, up to `most` enemies.
    inline double OsmosisRegen(unsigned cursed, double perEnemy, unsigned most)
    {
        return std::min(cursed, most) * std::max(0.0, perEnemy);
    }

    // Cursed Ground: "healing you for {heal_pct} of your maximum life every second for each enemy in the cursed area".
    inline double GroundHeal(double maxLife, double healPct, unsigned enemies)
    {
        return StruckHeal(maxLife, healPct) * enemies;
    }

    // Sanguine End: "healed for {life_per_kill_share_pct} of your Life per Kill".
    inline double KillHeal(double lifePerKill, double sharePct)
    {
        return lifePerKill > 0 && sharePct > 0 ? lifePerKill * sharePct / 100.0 : 0.0;
    }
} // namespace DC::Combat::Necromancer::Leech
