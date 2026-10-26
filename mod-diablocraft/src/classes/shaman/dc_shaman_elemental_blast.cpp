/*
 * Elemental Blast and its five runes: the Elemental Mastery buff every blast gives, Prismatic Cycle's move of the
 * Attunement, Elemental Echo's effect of the Attunement's element, Unstable Elements' splash, the Elemental Mastery
 * rune's damage and Primal Wellspring's refund. The cast is the engine's single-enemy spell in the element of the
 * Attunement (the element seam) and costs the Maelstrom its row states (the core's); the dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_elemental_blast.h"
#include "dc_shaman_burning.h"
#include "dc_shaman_common.h"
#include "dc_shaman_damage_mark.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "SharedDefines.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Shaman::ElementalBlast
{
    namespace
    {
        constexpr std::string_view Skill = "Elemental Blast";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? RuneOf(row->rune) : Rune::None;
        }

        // The record of the skill itself: the numbers a rune takes from it are stated there.
        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        double Tune(char const* name)
        {
            return Tunables::Get("combat", name);
        }

        // A strike this file starts is itself a hit of the skill and starts nothing.
        thread_local bool striking = false;

        void Strikes(Player* player, Unit* target, std::uint32_t spellId, double pct)
        {
            striking = true;
            Combat::Strike(player, target, spellId, pct);
            striking = false;
        }

        // The Elemental Mastery buff of a Shaman: the rune of the blast that gave it, until when, and the stamp its end
        // answers to.
        struct Mastery
        {
            Rune rune = Rune::None;
            std::uint32_t spellId = 0; // the record of the blast that gave it
            std::uint64_t until = 0;   // game time, ms
            std::uint64_t stamp = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Mastery> masteries; // by the Shaman
        std::uint64_t stamps = 0;

        void PutCrit(Player* player, double pct)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            Stats::RemoveContribution(guid, Source::Temporary, Stat::CritChance, BaseId());
            if (pct > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::CritChance, BaseId(), pct, Bucket::Flat});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // "Elemental Blast grants Elemental Mastery for {duration_seconds} seconds: +{crit_chance_pct} critical hit
        // chance."
        void GiveMastery(Player* player, Rune rune, std::uint32_t spellId)
        {
            double const seconds = Numbers::Num(BaseId(), "duration_seconds");
            std::uint64_t const key = player->GetGUID().GetRawValue(), now = Now();
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                Mastery& mastery = masteries[key];
                stamp = mastery.stamp = ++stamps;
                mastery.rune = rune;
                mastery.spellId = spellId;
                mastery.until = now + std::uint64_t(seconds * 1000.0);
            }
            PutCrit(player, CritBonus(rune, Numbers::Num(BaseId(), "crit_chance_pct")));
            player->m_Events.AddEventAtOffset(
                [player, key, stamp]
                {
                    {
                        std::lock_guard<std::mutex> guard(mutex);
                        auto found = masteries.find(key);
                        if (found == masteries.end() || found->second.stamp != stamp)
                            return;
                        masteries.erase(found);
                    }
                    PutCrit(player, 0);
                },
                std::chrono::milliseconds(std::uint32_t(seconds * 1000.0 + 0.5)));
        }

        // The element of the school a record deals, as the engine names an element.
        char const* ElementOfSpell(std::uint32_t spellId)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            switch (info ? info->GetSchoolMask() : 0u)
            {
                case SPELL_SCHOOL_MASK_FIRE:
                    return "fire";
                case SPELL_SCHOOL_MASK_FROST:
                    return "cold";
                case SPELL_SCHOOL_MASK_NATURE:
                    return "lightning";
                default:
                    return "physical";
            }
        }

        // "Lightning: arcs to {target_count} enemies for {damage_pct:lightning} weapon damage."
        void Arc(Player* player, Unit* from, std::uint32_t spellId)
        {
            std::vector<Unit*> near =
                Combat::Enemies(player, spellId, from->GetPosition(), Tune("elemental_blast_arc_radius_yards"));
            near.erase(std::remove(near.begin(), near.end(), from), near.end());
            std::sort(near.begin(), near.end(),
                      [from](Unit* a, Unit* b) { return from->GetExactDist(a) < from->GetExactDist(b); });
            auto const count = std::size_t(Numbers::Num(spellId, "target_count"));
            if (near.size() > count)
                near.resize(count);
            for (Unit* enemy : near)
                Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct", "lightning"));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The skill states a duration (the buff's) and Elemental Echo damages of its own by element: the loader would
        // give every record no hit, and the blast hits for the skill's.
        if (!Is(spellId))
            return std::nullopt;
        return Numbers::Num(BaseId(), "damage_pct");
    }

    char const* Element(Player* player, std::uint32_t spellId)
    {
        // "Fires a blast of pure elemental energy for {damage_pct} weapon damage in the element of your current
        // Attunement."
        return Is(spellId) ? Attunement::Current(player) : nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        GiveMastery(player, rune, spellId);
        // "After the blast, your Attunement moves to the next element in the order Fire -> Lightning -> Cold ->
        // Physical -> Fire."
        if (rune == Rune::PrismaticCycle)
            if (auto const next = NextElement(Attunement::Current(player)))
                Attunement::MoveTo(player, *next);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (striking || !player || !target || !Is(spellId))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::ElementalEcho:
                switch (EchoOf(Attunement::Current(player)).value_or(Echo::Knock))
                {
                    case Echo::Burn:
                    {
                        // "Fire: burns for {damage_pct:fire} weapon damage over {dot_duration_seconds} seconds."
                        double const seconds = Numbers::Num(spellId, "dot_duration_seconds");
                        Burning::Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct", "fire"), seconds,
                                      Tune("elemental_blast_burn_tick_seconds"));
                        break;
                    }
                    case Echo::Arc:
                        Arc(player, target, spellId);
                        break;
                    case Echo::Freeze:
                        // "Cold: Freezes for {freeze_duration_seconds} second."
                        Freeze(player, target, Numbers::Num(spellId, "freeze_duration_seconds"));
                        break;
                    case Echo::Knock:
                        // "Physical: Knockback plus {damage_taken_pct} damage taken for {duration_seconds} seconds."
                        Abilities::Knockback(player, target, Tune("elemental_blast_knockback_yards"));
                        DamageMark::Set(player, target, Numbers::Num(spellId, "damage_taken_pct"),
                                        Numbers::Num(spellId, "duration_seconds"));
                        break;
                }
                break;
            case Rune::UnstableElements:
                // "Explodes on impact and deals {damage_share_pct} of its damage to all enemies within {radius_yards}
                // yards."
                for (Unit* enemy :
                     Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                    if (enemy != target)
                        Strikes(
                            player, enemy, spellId,
                            SplashPct(Numbers::Num(BaseId(), "damage_pct"), Numbers::Num(spellId, "damage_share_pct")));
                break;
            case Rune::PrimalWellspring:
                // "Refunds {gain_resource} Maelstrom if Elemental Blast kills its target or hits an elite."
                Gain(player, spellId,
                     Refund(!target->IsAlive(), IsElite(target), Numbers::Num(spellId, "gain_resource")));
                break;
            default:
                break;
        }
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!player)
            return;
        Rune rune = Rune::None;
        std::uint32_t gave = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = masteries.find(player->GetGUID().GetRawValue());
            if (found == masteries.end())
                return;
            if (!Holds(Now(), found->second.until))
            {
                masteries.erase(found);
                return;
            }
            rune = found->second.rune;
            gave = found->second.spellId;
        }
        // "Elemental Mastery gives +{damage_bonus_pct} damage of your Attuned element instead of critical hit chance."
        // The element the hit actually deals: the blast deals the Attunement through the element seam, whatever its record's school.
        bool const same = DealtElement(DC::Combat::Shaman::Element(player, spellId), ElementOfSpell(spellId)) == std::string_view(Attunement::Current(player));
        if (double const bonus = DamageBonus(rune, same, Numbers::Num(gave, "damage_bonus_pct")))
            AddFactor(out, "Elemental Mastery", bonus);
    }
} // namespace DC::Combat::Shaman::ElementalBlast
