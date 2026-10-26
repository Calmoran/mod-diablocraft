#pragma once
// The rules of Simulacrum's runes that need no core type, header-only so tests/necromancer_simulacrum compiles this exact code: which
// rune is which, the Life cost Blood Debt cuts, the Essence Reservoir adds, which skills the copies repeat, which curses Cursed Form
// adds to the one cast, and when a blow is the fatal one. The production half is dc_necromancer_simulacrum.cpp.
#include <algorithm>
#include <array>
#include <string_view>

namespace DC::Combat::Necromancer::Simulacrum
{
    enum class Rune
    {
        None,
        Reservoir,
        CursedForm,
        BloodDebt,
        BloodAndBone,
        SelfSacrifice
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Reservoir")
            return Rune::Reservoir;
        if (name == "Cursed Form")
            return Rune::CursedForm;
        if (name == "Blood Debt")
            return Rune::BloodDebt;
        if (name == "Blood and Bone")
            return Rune::BloodAndBone;
        if (name == "Self Sacrifice")
            return Rune::SelfSacrifice;
        return Rune::None;
    }

    // "Duplicate your Secondary skills": the Necromancer's Secondary category (necromancer_skills.csv; the test reads the sheet).
    constexpr std::array<std::string_view, 3> Secondaries = {"Bone Spear", "Skeletal Mage", "Death Nova"};

    inline bool IsSecondary(std::string_view skill)
    {
        return std::find(Secondaries.begin(), Secondaries.end(), skill) != Secondaries.end();
    }

    // A Secondary that is cast at an enemy (the others are cast around the Necromancer).
    inline bool NeedsTarget(std::string_view skill)
    {
        return skill != "Death Nova";
    }

    // The Necromancer's curse category (necromancer_skills.csv).
    constexpr std::array<std::string_view, 3> Curses = {"Decrepify", "Leech", "Frailty"};

    inline bool IsCurse(std::string_view skill)
    {
        return std::find(Curses.begin(), Curses.end(), skill) != Curses.end();
    }

    // "your curse skills now apply all three curses": the two a cast of `skill` adds.
    inline std::array<std::string_view, 2> OtherCurses(std::string_view skill)
    {
        std::array<std::string_view, 2> out = {};
        std::size_t next = 0;
        for (std::string_view curse : Curses)
            if (curse != skill && next < out.size())
                out[next++] = curse;
        return out;
    }

    // "Life costs for skills are reduced by {cost_reduction_pct} while Simulacrum is active": what a Life cost is multiplied by.
    inline double LifeCostShare(Rune activeRune, double reductionPct)
    {
        return activeRune == Rune::BloodDebt ? std::clamp(1.0 - reductionPct / 100.0, 0.0, 1.0) : 1.0;
    }

    // "Your maximum essence is increased by {max_pool_pct}": the points added to a pool of `maximum`.
    inline double EssenceAdded(double maximum, double increasePct)
    {
        return maximum > 0 && increasePct > 0 ? maximum * increasePct / 100.0 : 0.0;
    }

    // "If you would die": the blow takes all the Life that is left.
    inline bool Fatal(double damage, double health)
    {
        return health > 0 && damage >= health;
    }
} // namespace DC::Combat::Necromancer::Simulacrum
