#pragma once
// The Shaman's passives that need code, first four: Elemental Focus, Call of Flame, Elemental Fury and Ancestral
// Knowledge. The rules need no core type, header-only so tests/shaman_passives compiles this exact code; the state and
// the hooks are dc_shaman_passives.cpp's. A passive is on when it sits in one of the Shaman's passive slots or a worn
// item grants it (Passives::Has).
#include "../../combat/dc_damage_buckets.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::Passive
{
    // Elemental Focus: "After a critical hit, your next Secondary skill costs {cost_reduction_pct} less Maelstrom": the
    // cut that stands while the focus is ready.
    inline double FocusCut(bool ready, double pct)
    {
        return ready && pct > 0 ? pct : 0.0;
    }

    // Whether a Secondary cast number `cast` (counted from the Casting seam) spends a focus armed at cast number
    // `armedAt`: the cast that armed it by its own critical hit does not spend it, the next one does.
    inline bool SpendsFocus(bool ready, std::uint64_t armedAt, std::uint64_t cast)
    {
        return ready && cast > armedAt;
    }

    // Call of Flame: "Fire skills deal {damage_bonus_pct} more damage": the percent a hit of `element` (as the engine
    // names one) adds.
    inline double FireBonus(bool on, std::string_view element, double pct)
    {
        return on && element == "fire" && pct > 0 ? pct : 0.0;
    }

    // Call of Flame: "All your Burning effects last {duration_seconds} seconds longer": the seconds a burn of `seconds`
    // lasts.
    inline double BurnSeconds(bool on, double seconds, double extraSeconds)
    {
        return on && seconds > 0 && extraSeconds > 0 ? seconds + extraSeconds : seconds;
    }

    // The burn's total weapon damage percent when it lasts `longer` instead of `seconds`: the same damage each second
    // for the longer time.
    inline double BurnTotal(double totalPct, double seconds, double longer)
    {
        return seconds > 0 && longer > seconds ? totalPct * longer / seconds : totalPct;
    }

    // Lightning Overload: "Your Lightning Secondary skills have a {proc_chance_pct} chance to cast again for free": a chance of `chancePct`
    // percent that comes up on `roll` (0 to 1).
    inline bool Overloads(double roll, double chancePct)
    {
        return chancePct > 0 && roll * 100.0 < chancePct;
    }

    // Lightning Overload: "... at {damage_share_pct} damage": the percent the free cast adds to a hit, which is below 0 for a share below
    // a hundred (-25 for 75: three quarters of the damage).
    inline double OverloadPct(double sharePct)
    {
        return sharePct > 0 && sharePct < 100 ? sharePct - 100.0 : 0.0;
    }

    // Whether a Secondary cast of `element` (as the engine names one) is a Lightning one that Lightning Overload may cast again.
    inline bool OverloadsElement(std::string_view category, std::string_view element)
    {
        return category == "Secondary" && element == "lightning";
    }

    // Frozen Power: "You deal {damage_bonus_pct} more damage to Chilled or Frozen enemies": the percent a hit on an enemy adds.
    inline double FrozenBonus(bool chilledOrFrozen, double pct)
    {
        return chilledOrFrozen && pct > 0 ? pct : 0.0;
    }

    // Rooted in Earth: the milliseconds the Shaman has stood still after a look of `stepMs`, given `stillMs` before: none while moving.
    inline std::uint64_t StillMs(bool moving, std::uint64_t stillMs, std::uint64_t stepMs)
    {
        return moving ? 0 : stillMs + stepMs;
    }

    // Rooted in Earth: "After you stand still for {duration_seconds} second, take {damage_reduction_pct} less damage until you move": the
    // reduction at `stillMs` of standing still.
    inline double RootedCut(std::uint64_t stillMs, double seconds, double pct)
    {
        return seconds >= 0 && pct > 0 && double(stillMs) >= seconds * 1000.0 && stillMs > 0 ? pct : 0.0;
    }

    // Storm Surge: "Each Overcharge stack also gives +{crit_chance_pct} Critical Hit Chance": what `stacks` of them give.
    inline double SurgeCrit(unsigned stacks, double perStackPct)
    {
        return perStackPct > 0 ? double(stacks) * perStackPct : 0.0;
    }

    // Elemental Harmony: "Your Elemental Attunement bonus is tripled": what the bonus is multiplied by.
    inline constexpr double HarmonyTimes = 3.0;
    inline double HarmonyFactor(bool on)
    {
        return on ? HarmonyTimes : 1.0;
    }

    // Reincarnation: "When you take fatal damage": a blow of `damage` that is at least the `health` left.
    inline bool Fatal(double damage, double health)
    {
        return health > 0 && damage >= health;
    }

    // "Can trigger once every {internal_cooldown_seconds} seconds": whether it may trigger at `nowMs` when it last did at `lastMs` (0 for
    // never).
    inline bool CooledDown(std::uint64_t lastMs, std::uint64_t nowMs, std::uint64_t cooldownMs)
    {
        return lastMs == 0 || nowMs >= lastMs + cooldownMs;
    }

    // "... become immune to damage for {duration_seconds} seconds": whether the window that opened at `openedMs` (0 for none) and lasts `lastsMs`
    // is open at `nowMs`.
    inline bool Immune(std::uint64_t openedMs, std::uint64_t nowMs, std::uint64_t lastsMs)
    {
        return openedMs != 0 && nowMs < openedMs + lastsMs;
    }

    // "... you are restored to {life_floor_pct} Life": the Life to heal a Shaman holding `health` of `maxLife` to the floor, none when it holds more.
    inline double RestoredLife(double health, double maxLife, double floorPct)
    {
        return maxLife > 0 && floorPct > 0 ? std::max(0.0, maxLife * floorPct / 100.0 - health) : 0.0;
    }

    // Primal Wisdom: "Every {per_trigger_resource} Maelstrom you spend lowers the cooldown of your Primal skills by {cooldown_reduction_seconds}
    // second": the steps `spent` points make on top of the `carried` points that did not make one yet, and the points still carried.
    struct Wisdom
    {
        unsigned steps = 0;
        double carried = 0;
    };
    inline Wisdom WisdomSteps(double carried, double spent, double perStep)
    {
        if (perStep <= 0 || spent <= 0)
            return {0, carried};
        double const total = carried + spent;
        unsigned const steps = unsigned(total / perStep);
        return {steps, total - double(steps) * perStep};
    }

    // Ancestral Guidance: "heal you for {heal_pct:per_enemy} of maximum Life per enemy hit, up to {heal_pct:cap} per cast": the percent the next
    // enemy hit heals when `healedPct` percent was healed by the cast already.
    inline double GuidanceHeal(double healedPct, double perEnemyPct, double capPct)
    {
        return perEnemyPct > 0 && capPct > healedPct ? std::min(perEnemyPct, capPct - healedPct) : 0.0;
    }

    // Elemental Oath: "You and allies within {radius_yards:aura} yards gain {crit_chance_pct} Critical Hit Chance": whether a member `distance` yards
    // from the Shaman is in the aura.
    inline bool InOath(double distance, double radius)
    {
        return radius > 0 && distance >= 0 && distance <= radius;
    }

    // Echo of the Elements: "Totem and Primal cooldowns recover {cooldown_reduction_pct} faster": the milliseconds a cooldown with `leftMs` left loses.
    inline double EchoCut(double leftMs, double pct)
    {
        return leftMs > 0 && pct > 0 ? leftMs * std::min(pct, 100.0) / 100.0 : 0.0;
    }

    // The four elements a hit can deal, by the names the engine uses: the slot of each in a list of times, -1 for any other.
    inline int ElementIndex(std::string_view element)
    {
        if (element == "fire")
            return 0;
        if (element == "cold")
            return 1;
        if (element == "lightning")
            return 2;
        return element == "physical" ? 3 : -1;
    }
    using ElementTimes = std::array<std::uint64_t, 4>;

    // How many elements other than `except` (-1 for none) were dealt within `lastsMs` of `nowMs`: a time of 0 is never.
    inline unsigned ElementsWithin(ElementTimes const& at, int except, std::uint64_t nowMs, std::uint64_t lastsMs)
    {
        unsigned count = 0;
        for (int slot = 0; slot < 4; ++slot)
            if (slot != except && at[slot] != 0 && nowMs < at[slot] + lastsMs)
                ++count;
        return count;
    }

    // Elemental Equilibrium: "it takes {damage_taken_pct} more damage from your other three elements for {duration_seconds} seconds (up to
    // {max_bonus_pct})", Natural Harmony: "Each different element you have dealt damage with in the last {duration_seconds} seconds increases your damage by
    // {damage_bonus_pct} (up to {max_bonus_pct})": the percent `elements` of them give.
    inline double ElementsBonus(unsigned elements, double perPct, double maxPct)
    {
        return perPct > 0 && maxPct > 0 ? std::min(double(elements) * perPct, maxPct) : 0.0;
    }

    // Primal Elementalist: "Fire Elemental and Earth Elemental deal {damage_bonus_pct} more damage and last {duration_bonus_pct} longer": whether a hit of
    // the skill named is the elementals', the damage percent it adds, and the seconds an elemental lasts.
    inline bool IsElemental(std::string_view skill)
    {
        return skill == "Fire Elemental" || skill == "Earth Elemental";
    }
    inline double ElementalDamage(bool on, std::string_view skill, double pct)
    {
        return on && IsElemental(skill) && pct > 0 ? pct : 0.0;
    }
    inline double ElementalSeconds(bool on, double seconds, double pct)
    {
        return on && seconds > 0 && pct > 0 ? seconds * (1.0 + pct / 100.0) : seconds;
    }

    // The production half (dc_shaman_passives.cpp), called from dc_shaman.cpp and the Burning file.
    bool On(Player* player, char const* name);
    // The seconds a burn of `seconds` lasts for `player` (Call of Flame).
    double BurnSecondsFor(Player* player, double seconds);
    // The Casting seam: counts the cast.
    void Casting(Player* player, std::uint32_t spellId);
    // A hit of `spellId` landed on `target` (the Landed seam), a critical hit or not: Elemental Focus arms on a critical one, a cast that rolled
    // Lightning Overload is made again at its first hit, and Ancestral Guidance heals for a Secondary hit.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);
    // A cast of `spellId` was paid and launched, by whatever path it reaches its hits (a triggered cast is a free one): a Secondary spends a focus armed
    // before it and rolls Lightning Overload.
    void Launched(Player* player, std::uint32_t spellId, bool triggered);
    // Whether the hits being resolved on this thread are a free cast of Lightning Overload's; and the same set to `on`, giving what it was.
    bool FreeCasting();
    bool FreeCasting(bool on);
    // The seconds an elemental of the skill `skill` lasts for `player` when it would last `seconds` (Primal Elementalist).
    double ElementalLasts(Player* player, std::string_view skill, double seconds);
    // The blow `damage` the Shaman is about to take, after every other layer: what Reincarnation lets through.
    double Reduce(Unit* victim, double damage);
    // What the Attunement's bonus is multiplied by for `player` (Elemental Harmony), 1 for none.
    double HarmonyFor(Player* player);
    // The hit of `spellId` on `target` being computed: Call of Flame's and Frozen Power's damage, the free cast's smaller one.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
    // The Maelstrom Deep Maelstrom adds to what each Primary skill generates.
    double PrimaryGain(Player* player);
    // Keeps the sheet numbers of the passives that change the sheet (Elemental Fury, Ancestral Knowledge, Deep Maelstrom, Storm Surge, Rooted in
    // Earth); at the class's upkeep, `stepMs` after the last look.
    void Upkeep(Player* player, std::uint32_t stepMs);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::Passive
