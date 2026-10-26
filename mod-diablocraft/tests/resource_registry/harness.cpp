// diablocraft-resource-registry: before/after harness.
//
// Every "Old" function below is the HEAD expression the registry replaced,
// copied verbatim apart from its name (the file:line it came from is on each).
// The "New" side is the real dc_resources.h over the generated
// dc_resource_data.h and the real dc_cost_math.h. Both run on a shim Player
// that logs every power write, over a sweep of pools, maxima, amounts and
// generation factors, and the harness fails on the first case whose end state
// or write sequence differs. Class powers P2 stored Fury and Spirit one slot
// unit a point: the Old side keeps HEAD's expressions at that scale, and a
// change below a whole unit, which HEAD rounded and dc_resources.h now carries
// (WholeUnits), is checked against the carry rule instead, and over a run of
// changes against the exact sum. scripts/tests/classes/test_resource_registry.py compiles and
// runs it, and plants mutations to prove a difference is caught.
#include "classes/dc_resources.h"
#include "combat/dc_cost_math.h"

#include <cstdio>
#include <functional>
#include <string>
#include <vector>

namespace Old
{
    namespace SpellValues
    {
        inline constexpr double RagePerFury = 1.0;        // dc_spell_values.h:15 (10 before class powers P2)
        inline constexpr double ManaPerArcanePower = 1.0; // dc_spell_values.h:17
    } // namespace SpellValues
    constexpr int32 RAGE_PER_FURY = 1; // dc_combat.cpp:313 (10 before class powers P2)
    // diablocraft-resource-rollout-a item 4 moved Arcane Power from Mana to
    // Energy. The Arcane Power expressions below are HEAD's with only the slot
    // changed, so the harness proves the arithmetic did not move with it.
    constexpr Powers ArcanePowerSlot = POWER_ENERGY;

    // dc_abilities.cpp:145, dc_barbarian_primaries.cpp:84, dc_passives.cpp:121 (same shape)
    void FuryGain(Player* p, double amount, double factor)
    {
        p->SetPower(POWER_RAGE, std::clamp(int32(p->GetPower(POWER_RAGE)) + int32(std::llround(amount * factor * RAGE_PER_FURY)),
                                           0, int32(p->GetMaxPower(POWER_RAGE))));
    }
    // dc_combat.cpp:328-336
    void ChangeFury(Player* player, double fury, double factor)
    {
        if (!player || fury == 0)
            return;
        int32 const current = player->GetPower(POWER_RAGE);
        int32 const wanted = current + static_cast<int32>(std::llround(fury * (fury > 0 ? factor : 1) * RAGE_PER_FURY));
        int32 const cap = static_cast<int32>(player->GetMaxPower(POWER_RAGE));
        player->SetPower(POWER_RAGE, std::clamp(wanted, 0, cap));
    }
    // dc_combat.cpp:340
    double CurrentFury(Player* player)
    {
        return player ? player->GetPower(POWER_RAGE) / double(RAGE_PER_FURY) : 0.0;
    }
    // dc_barbarian_call_of_the_ancients.cpp:147
    void AncientsFury(Player* p, double gain, double factor)
    {
        p->ModifyPower(POWER_RAGE, int32(std::llround(gain * factor * RAGE_PER_FURY)));
    }
    // dc_combat.cpp:2112, 2121-2123: the spend-all runes after the core's cost
    double SeismicExtra(Player* player, int32 powerCost)
    {
        return std::max(0.0, CurrentFury(player) - powerCost / double(RAGE_PER_FURY));
    }
    void SpendAll(Player* player, int32 powerCost, double factor)
    {
        double drained = std::max(0.0, CurrentFury(player) - powerCost / double(RAGE_PER_FURY));
        ChangeFury(player, -drained, factor);
    }
    // dc_passives.cpp:673
    bool Berserker(Player* p, double threshold)
    {
        return p->GetPower(POWER_RAGE) >= p->GetMaxPower(POWER_RAGE) * threshold / 100;
    }
    // dc_combat.cpp:2582-2584 (.dc fury's three numbers)
    std::string FuryReport(Player* player)
    {
        return std::to_string(CurrentFury(player)) + " " +
               std::to_string(player->GetMaxPower(POWER_RAGE) / double(RAGE_PER_FURY)) + " " +
               std::to_string(player->GetPower(POWER_RAGE)) + " " + std::to_string(player->GetMaxPower(POWER_RAGE));
    }
    // dc_stats.cpp:210-212 (Recompute) with the class's power and unitsPerPoint
    void SetMax(Player* player, Powers power, double unitsPerPoint, double maxFury)
    {
        auto rounded = [](double value) { return static_cast<int32>(std::llround(value)); };
        player->SetMaxPower(power, rounded(maxFury * unitsPerPoint));
        if (player->GetPower(power) > player->GetMaxPower(power))
            player->SetPower(power, player->GetMaxPower(power));
    }
    // dc_stats.cpp:512-513 (OnPlayerAfterUpdateMaxPower)
    float HookMax(double maxFury, double unitsPerPoint)
    {
        return static_cast<float>(maxFury * unitsPerPoint);
    }
    // dc_combat.cpp:393-396
    void GainArcanePower(Player* player, uint32 spellId, double points)
    {
        if (!player || points <= 0 || player->getPowerType() != ArcanePowerSlot)
            return;
        player->EnergizeBySpell(player, spellId, uint32(std::llround(points * SpellValues::ManaPerArcanePower)),
                                ArcanePowerSlot);
    }
    // dc_combat.cpp:1330-1332 (channel first-tick preflight)
    bool ChannelRefused(Player* player, double tickCost)
    {
        return player->GetPower(ArcanePowerSlot) + 0.0001 < tickCost * SpellValues::ManaPerArcanePower;
    }
    // dc_combat.cpp:1710-1721 (PayChannelTick)
    bool PayChannelTick(Player* player, double tickCost, double& owed)
    {
        auto const debit = DC::Combat::CostMath::PayWhole(player->GetPower(ArcanePowerSlot),
                                                          tickCost * SpellValues::ManaPerArcanePower + owed);
        if (!debit.paid)
            return false;
        owed = debit.owed;
        if (debit.whole > 0)
            player->ModifyPower(ArcanePowerSlot, -debit.whole);
        return true;
    }
    // dc_wizard.cpp:967-971 (Star Pact)
    double StarPact(Player* player)
    {
        if (player->getPowerType() == ArcanePowerSlot)
        {
            double const extra = player->GetPower(ArcanePowerSlot) / SpellValues::ManaPerArcanePower;
            player->SetPower(ArcanePowerSlot, 0);
            return extra;
        }
        return -1;
    }
    // dc_wizard.cpp:1385-1387 (Prism cost reduction amount)
    int32 PrismAmount(double reduction)
    {
        return -int32(std::lround(reduction * SpellValues::ManaPerArcanePower));
    }
    // dc_spell_numbers.cpp:174-176 (Source::Cost)
    // diablocraft-1cuvw: the Monk's Spirit is stored in the Runic Power slot (decisions.md 2026-09-23 Q1=1A), one
    // unit a point since class powers P2, so that slot reads like Rage; every other slot is HEAD's.
    constexpr double RunicPerSpirit = 1.0;
    double CostRead(uint32 manaCost, uint32 powerType)
    {
        if (powerType == POWER_RAGE)
            return manaCost / SpellValues::RagePerFury;
        if (powerType == POWER_RUNIC_POWER)
            return manaCost / RunicPerSpirit;
        return manaCost / SpellValues::ManaPerArcanePower;
    }
    // dc_cost_math.h:29-37 at HEAD
    int32 CostRage(double fury)
    {
        return int32(std::llround(fury * SpellValues::RagePerFury));
    }
    double CostFury(int32 rage)
    {
        return std::max(0, rage) / SpellValues::RagePerFury;
    }
} // namespace Old

namespace New
{
    namespace R = DC::Resources;
    void FuryGain(Player* p, double amount, double factor)
    {
        R::Add(p, R::Fury, amount * factor);
    }
    void ChangeFury(Player* player, double fury, double factor)
    {
        if (!player || fury == 0)
            return;
        R::Add(player, R::Fury, fury * (fury > 0 ? factor : 1));
    }
    double CurrentFury(Player* player)
    {
        return player ? R::Get(player, R::Fury) : 0.0;
    }
    void AncientsFury(Player* p, double gain, double factor)
    {
        R::Modify(p, R::Fury, gain * factor);
    }
    double SeismicExtra(Player* player, int32 powerCost)
    {
        return std::max(0.0, CurrentFury(player) - R::ToPoints(R::Fury, powerCost));
    }
    void SpendAll(Player* player, int32 powerCost, double factor)
    {
        double drained = std::max(0.0, CurrentFury(player) - R::ToPoints(R::Fury, powerCost));
        ChangeFury(player, -drained, factor);
    }
    bool Berserker(Player* p, double threshold)
    {
        return R::Units(p, R::Fury) >= R::MaxUnits(p, R::Fury) * threshold / 100;
    }
    std::string FuryReport(Player* player)
    {
        return std::to_string(CurrentFury(player)) + " " + std::to_string(R::Max(player, R::Fury)) + " " +
               std::to_string(R::Units(player, R::Fury)) + " " + std::to_string(R::MaxUnits(player, R::Fury));
    }
    void SetMax(Player* player, R::Resource const& r, double maxFury)
    {
        R::SetMax(player, r, maxFury);
        R::ClampToMax(player, r);
    }
    float HookMax(R::Resource const& r, double maxFury)
    {
        return static_cast<float>(R::ToUnits(r, maxFury));
    }
    void GainArcanePower(Player* player, uint32 spellId, double points)
    {
        if (!player || points <= 0 || !R::Displayed(player, R::ArcanePower))
            return;
        R::Energize(player, R::ArcanePower, spellId, points);
    }
    bool ChannelRefused(Player* player, double tickCost)
    {
        return R::Units(player, R::ArcanePower) + 0.0001 < R::ToUnits(R::ArcanePower, tickCost);
    }
    bool PayChannelTick(Player* player, double tickCost, double& owed)
    {
        auto const debit = DC::Combat::CostMath::PayWhole(R::Units(player, R::ArcanePower),
                                                          R::ToUnits(R::ArcanePower, tickCost) + owed);
        if (!debit.paid)
            return false;
        owed = debit.owed;
        if (debit.whole > 0)
            R::SpendUnits(player, R::ArcanePower, debit.whole);
        return true;
    }
    double StarPact(Player* player)
    {
        if (R::Displayed(player, R::ArcanePower))
        {
            double const extra = R::Get(player, R::ArcanePower);
            R::Empty(player, R::ArcanePower);
            return extra;
        }
        return -1;
    }
    int32 PrismAmount(double reduction)
    {
        return -int32(std::lround(R::ToUnits(R::ArcanePower, reduction)));
    }
    double CostRead(uint32 manaCost, uint32 classId, uint32 powerType)
    {
        return manaCost / R::Data::ScaleOf(classId, powerType);
    }
} // namespace New

namespace
{
    int cases = 0, failures = 0;

    template<typename A, typename B>
    void Same(std::string const& what, A const& a, B const& b)
    {
        ++cases;
        if (!(a == b))
        {
            if (++failures <= 10)
                std::printf("DIFF %s\n", what.c_str());
        }
    }

    bool Whole(double units)
    {
        return std::fabs(units - std::round(units)) < 1e-9;
    }

    // The carry rule for one change from a player who owes nothing: its whole units toward its sign, clamped.
    uint32 Carried(uint32 current, uint32 maximum, double units)
    {
        double const whole = units > 0 ? std::floor(units + 1e-9) : -std::floor(-units + 1e-9);
        return uint32(std::clamp(double(current) + whole, 0.0, double(maximum)));
    }

    // Two identical players, one per side.
    struct Pair
    {
        Player a, b;
        Pair(Powers display, uint32 rage, uint32 maxRage, uint32 mana, uint32 maxMana)
        {
            for (Player* p : {&a, &b})
            {
                p->display = display;
                p->power[POWER_RAGE] = rage;
                p->maxPower[POWER_RAGE] = maxRage;
                p->power[POWER_MANA] = mana;
                p->maxPower[POWER_MANA] = maxMana;
                p->power[POWER_ENERGY] = mana;
                p->maxPower[POWER_ENERGY] = maxMana;
            }
        }
        void Check(std::string const& what)
        {
            Same(what, a.State(), b.State());
        }
    };
} // namespace

int main()
{
    namespace R = DC::Resources;
    // The registry rows are today's behaviour.
    Same("Fury slot", R::Slot(R::Fury), POWER_RAGE);
    Same("Fury scale", R::Fury.scale, Old::SpellValues::RagePerFury);
    Same("Fury decay", R::Fury.decay == R::Data::Decay::Stock, true);
    Same("Fury regen", R::Fury.regenPerSecond, 0.0);
    Same("Arcane Power slot", R::Slot(R::ArcanePower), POWER_ENERGY);
    Same("Arcane Power scale", R::ArcanePower.scale, Old::SpellValues::ManaPerArcanePower);
    Same("Arcane Power decay", R::ArcanePower.decay == R::Data::Decay::None, true);
    Same("Arcane Power regen", R::ArcanePower.regenPerSecond, 10.0);
    Same("Barbarian primary", R::Of(1), &R::Fury);
    Same("Wizard primary", R::Of(2), &R::ArcanePower);
    // A class with no resource on Mana keeps Mana's maximum at 0 (item 4).
    Same("Barbarian Mana maximum 0", R::ZeroMaximum(1, POWER_MANA), true);
    Same("Wizard Mana maximum 0", R::ZeroMaximum(2, POWER_MANA), true);
    Same("Wizard Energy maximum kept", R::ZeroMaximum(2, POWER_ENERGY), false);
    Same("Barbarian Rage maximum kept", R::ZeroMaximum(1, POWER_RAGE), false);
    Same("Wizard display power in the registry", R::ArcanePower.power, uint8_t(POWER_ENERGY));
    Same("RagePerFury in cost math", DC::Combat::CostMath::RagePerFury, Old::SpellValues::RagePerFury);

    std::vector<uint32> pools = {0, 1, 5, 9, 10, 11, 99, 100, 250, 499, 500, 999, 1000, 1500};
    std::vector<uint32> maxima = {0, 100, 1000, 1500};
    std::vector<double> amounts = {0,    0.04, 0.05, 0.06, 0.15, 0.25,  0.5,  1,     1.5,   2.5,
                                   4,    6,    9,    15,   20,   50,    100,  -0.04, -0.05, -0.5,
                                   -1.5, -7.3, -25,  -100, 3.35, 12.45, 0.95, 7.65,  -3.35, -12.45};
    std::vector<double> factors = {1, 1.1, 1.2, 1.21, 0.9};

    for (uint32 max : maxima)
        for (uint32 pool : pools)
        {
            uint32 const cur = std::min(pool, max);
            for (double amount : amounts)
                for (double factor : factors)
                {
                    std::string const tag = std::to_string(cur) + "/" + std::to_string(max) + " " +
                                            std::to_string(amount) + " x" + std::to_string(factor);
                    // HEAD rounded every change to a whole unit; the carry moves the whole units now and keeps the
                    // rest, so a change of a whole number of units is HEAD's, and any other moves its whole part
                    // toward its sign (a fresh player owes nothing).
                    double const gained = amount * factor * R::Fury.scale;
                    double const changed = amount * (amount > 0 ? factor : 1) * R::Fury.scale;
                    {
                        Pair p(POWER_RAGE, cur, max, cur, max);
                        R::ForgetCarry(&p.b);
                        Old::FuryGain(&p.a, amount, factor);
                        New::FuryGain(&p.b, amount, factor);
                        if (Whole(gained))
                            p.Check("Fury gain " + tag);
                        else
                            Same("Fury gain carried " + tag, p.b.power[POWER_RAGE], Carried(cur, max, gained));
                    }
                    {
                        Pair p(POWER_RAGE, cur, max, cur, max);
                        R::ForgetCarry(&p.b);
                        Old::ChangeFury(&p.a, amount, factor);
                        New::ChangeFury(&p.b, amount, factor);
                        if (Whole(changed))
                        {
                            p.Check("ChangeFury " + tag);
                            Same("CurrentFury " + tag, Old::CurrentFury(&p.a), New::CurrentFury(&p.b));
                        }
                        else
                            Same("ChangeFury carried " + tag, p.b.power[POWER_RAGE], Carried(cur, max, changed));
                    }
                    {
                        Pair p(POWER_RAGE, cur, max, cur, max);
                        R::ForgetCarry(&p.b);
                        Old::AncientsFury(&p.a, amount, factor);
                        New::AncientsFury(&p.b, amount, factor);
                        if (Whole(gained))
                            p.Check("Ancients' Fury " + tag);
                        else
                            Same("Ancients' Fury carried " + tag, p.b.power[POWER_RAGE], Carried(cur, max, gained));
                    }
                    if (amount != 0)
                    {
                        // A run of the same change carries: twenty of them move the exact sum's whole units, as
                        // long as no bound is reached (a pool of 100000 units, from its middle).
                        Pair p(POWER_RAGE, 50000, 100000, 0, 0);
                        R::ForgetCarry(&p.b);
                        for (int i = 0; i < 20; ++i)
                            New::ChangeFury(&p.b, amount, factor);
                        double const exact = 20 * changed;
                        long const moved = long(p.b.power[POWER_RAGE]) - 50000;
                        long const wanted = exact > 0 ? long(std::floor(exact + 1e-6)) : -long(std::floor(-exact + 1e-6));
                        Same("a run carries " + tag, moved, wanted);
                    }
                    {
                        Pair p(POWER_RAGE, cur, max, cur, max);
                        int32 const cost = int32(std::llround(std::abs(amount) * R::Fury.scale));
                        Same("Seismic extra " + tag, Old::SeismicExtra(&p.a, cost), New::SeismicExtra(&p.b, cost));
                        Old::SpendAll(&p.a, cost, factor);
                        New::SpendAll(&p.b, cost, factor);
                        p.Check("spend-all " + tag);
                    }
                    {
                        Pair p(POWER_RAGE, cur, max, cur, max);
                        double const threshold = std::abs(amount);
                        Same("Berserker " + tag, Old::Berserker(&p.a, threshold), New::Berserker(&p.b, threshold));
                        Same(".dc fury " + tag, Old::FuryReport(&p.a), New::FuryReport(&p.b));
                    }
                    for (Powers display : {POWER_ENERGY, POWER_MANA, POWER_RAGE})
                    {
                        Pair p(display, cur, max, cur, max);
                        R::ForgetCarry(&p.b);
                        Old::GainArcanePower(&p.a, 83100, amount * factor);
                        New::GainArcanePower(&p.b, 83100, amount * factor);
                        double const ap = amount * factor * R::ArcanePower.scale;
                        if (Whole(ap) || ap <= 0 || display != POWER_ENERGY)
                        {
                            p.Check("Arcane Power gain " + tag);
                            Same("Star Pact " + tag, Old::StarPact(&p.a), New::StarPact(&p.b));
                            p.Check("Star Pact state " + tag);
                        }
                        else
                        {
                            uint32 const carried = Carried(cur, max, ap);
                            Same("Arcane Power gain carried " + tag, p.b.power[POWER_ENERGY], carried);
                            Same("Star Pact after a carry " + tag, New::StarPact(&p.b), double(carried));
                        }
                    }
                    {
                        // A channel run: tick until the pool refuses, carrying
                        // the fraction owed, exactly as PayChannelTick does.
                        Pair p(POWER_ENERGY, cur, max, cur, max);
                        double const tick = std::abs(amount) * factor;
                        Same("channel preflight " + tag, Old::ChannelRefused(&p.a, tick),
                             New::ChannelRefused(&p.b, tick));
                        double owedA = 0, owedB = 0;
                        for (int t = 0; t < 40; ++t)
                        {
                            bool const a = Old::PayChannelTick(&p.a, tick, owedA);
                            bool const b = New::PayChannelTick(&p.b, tick, owedB);
                            Same("channel tick " + tag, a, b);
                            Same("channel owed " + tag, owedA, owedB);
                            if (!a || !b)
                                break;
                        }
                        p.Check("channel state " + tag);
                    }
                }
        }

    // Max Fury and max Arcane Power: Recompute's write and the max-power hook,
    // for every sheet maximum a character can plausibly carry, fractions too.
    for (double sheetMax = 0; sheetMax <= 400; sheetMax += 0.25)
        for (uint32 cur : {0u, 50u, 100u, 999u, 1000u, 4000u})
        {
            std::string const tag = std::to_string(sheetMax) + " cur " + std::to_string(cur);
            {
                Pair p(POWER_RAGE, cur, 1000, cur, 1000);
                Old::SetMax(&p.a, POWER_RAGE, Old::SpellValues::RagePerFury, sheetMax);
                New::SetMax(&p.b, R::Fury, sheetMax);
                p.Check("max Fury " + tag);
                Same("max Fury hook " + tag, Old::HookMax(sheetMax, Old::SpellValues::RagePerFury),
                     New::HookMax(R::Fury, sheetMax));
            }
            {
                Pair p(POWER_ENERGY, cur, 1000, cur, 1000);
                Old::SetMax(&p.a, Old::ArcanePowerSlot, Old::SpellValues::ManaPerArcanePower, sheetMax);
                New::SetMax(&p.b, R::ArcanePower, sheetMax);
                p.Check("max Arcane Power " + tag);
                Same("max Arcane Power hook " + tag, Old::HookMax(sheetMax, Old::SpellValues::ManaPerArcanePower),
                     New::HookMax(R::ArcanePower, sheetMax));
            }
            Same("Prism " + tag, Old::PrismAmount(sheetMax / 7), New::PrismAmount(sheetMax / 7));
            Same("cost math Rage " + tag, Old::CostRage(sheetMax / 3), DC::Combat::CostMath::Rage(sheetMax / 3));
            Same("cost math Fury " + tag, Old::CostFury(int32(sheetMax * 4) - 50),
                 DC::Combat::CostMath::Fury(int32(sheetMax * 4) - 50));
        }

    // Paragon Maximum Resource (diablocraft-resource-rollout-a item 5): the
    // per-point value is the resource's, paid in whole points, so +0.5 is +1
    // per two points and +1 is +1 per point, for every count up to the cap.
    Same("Fury paragon per point", R::Fury.paragonPerPoint, 1.0);
    Same("Arcane Power paragon per point", R::ArcanePower.paragonPerPoint, 0.5);
    for (uint32 points = 0; points <= 50; ++points)
    {
        Same("paragon Fury " + std::to_string(points), R::ParagonMaximum(R::Fury, points), double(points));
        Same("paragon Arcane Power " + std::to_string(points), R::ParagonMaximum(R::ArcanePower, points),
             double(points / 2));
        R::Resource mana = R::Fury;
        mana.paragonPerPoint = 4.0;
        Same("paragon Mana " + std::to_string(points), R::ParagonMaximum(mana, points), 4.0 * points);
        mana.paragonPerPoint = 0.0;
        Same("paragon Discipline " + std::to_string(points), R::ParagonMaximum(mana, points), 0.0);
    }

    // The cost read for every slot a record can name, by the class whose records the old read served (Rage the
    // Barbarian's, Runic Power the Monk's, every other slot the Wizard's).
    for (uint32 manaCost : {0u, 1u, 5u, 16u, 25u, 150u, 250u, 1000u})
        for (uint32 slot = 0; slot < 7; ++slot)
        {
            uint32 const classId = slot == POWER_RAGE ? 1 : slot == POWER_RUNIC_POWER ? 3 : 2;
            Same("cost read " + std::to_string(manaCost) + " slot " + std::to_string(slot),
                 Old::CostRead(manaCost, slot), New::CostRead(manaCost, classId, slot));
        }
    // Class powers P2: the Necromancer's Essence shares Runic Power with the Monk's Spirit at one unit a point, so its
    // record's cost reads whole (Bone Spear's ManaCost 20 is 20 Essence), and a record of no class reads one a unit.
    for (uint32 manaCost : {0u, 10u, 20u, 25u, 40u, 50u})
    {
        Same("Essence cost read " + std::to_string(manaCost), New::CostRead(manaCost, 5, POWER_RUNIC_POWER),
             double(manaCost));
        Same("classless cost read " + std::to_string(manaCost), New::CostRead(manaCost, 0, POWER_RUNIC_POWER),
             double(manaCost));
    }

    // The carry's edges: reaching the maximum drops a gain's carry, as the core's m_powerFraction does; a loss owes
    // its own and a whole spend between two Whirlwind ticks takes exactly its units.
    {
        Pair p(POWER_RAGE, 95, 100, 0, 0);
        R::ForgetCarry(&p.b);
        New::ChangeFury(&p.b, 5.6, 1);
        Same("a gain stops at the maximum", p.b.power[POWER_RAGE], 100u);
        p.b.power[POWER_RAGE] = 50;
        New::ChangeFury(&p.b, 0.6, 1);
        Same("and its carry is dropped", p.b.power[POWER_RAGE], 50u);
        R::ForgetCarry(&p.b);
        p.b.power[POWER_RAGE] = 50;
        for (int tick = 0; tick < 3; ++tick)
            New::ChangeFury(&p.b, -16.0 / 3.0, 1);
        Same("three 5.33 ticks take 16", p.b.power[POWER_RAGE], 34u);
        New::ChangeFury(&p.b, -10, 1);
        Same("a whole spend takes its units", p.b.power[POWER_RAGE], 24u);
        New::ChangeFury(&p.b, 0.5, 1);
        New::ChangeFury(&p.b, 0.5, 1);
        Same("two half gains make a unit", p.b.power[POWER_RAGE], 25u);
        New::ChangeFury(&p.b, -0.5, 1);
        New::ChangeFury(&p.b, 0.5, 1);
        Same("a loss's carry is not a gain's", p.b.power[POWER_RAGE], 25u);
        R::ForgetCarry(&p.b);
        New::ChangeFury(&p.b, 0.5, 1);
        Same("a forgotten player owes nothing", p.b.power[POWER_RAGE], 25u);
    }

    // A cast's cost keeps its fraction: the core charges 17 of 25 Fury at 30% off, the dropped half carries, and the
    // second cast takes the whole unit the halves make, 35 for two. The float's own noise is read away: 0.7f x 25 is
    // 17.4999996 as a float and still drops a half.
    {
        namespace C = DC::Resources::Carry;
        Same("a half dropped", C::Dropped(17.5, 17), 0.5);
        Same("float noise read away", C::Dropped(double(25 * 0.7f) - 4e-7, 17), 0.5);
        Same("nothing dropped from a whole cost", C::Dropped(17.0, 17), 0.0);
        Same("a charge above the exact drops nothing", C::Dropped(16.9, 17), 0.0);
        Pair p(POWER_RAGE, 100, 100, 0, 0);
        R::ForgetCarry(&p.b);
        int32 taken = 0;
        for (int cast = 0; cast < 2; ++cast)
        {
            R::SpendUnits(&p.b, R::Fury, 17);
            int32 const owed = R::CostOwed(&p.b, R::Fury, 17.5, 17);
            R::SpendUnits(&p.b, R::Fury, owed);
            taken += 17 + owed;
        }
        Same("two casts of 17.5 take 35", taken, 35);
        Same("and the pool shows it", p.b.power[POWER_RAGE], 65u);
        Same("a whole cost owes nothing", R::CostOwed(&p.b, R::Fury, 20.0, 20), 0);
    }

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
