/*
 * The Searing Totem and its five runes. The cast and the totem itself are the totem seam's (dc_shaman_totems.cpp); here
 * is what a standing Searing Totem does: it shoots the nearest enemy within the skill's radius_yards every
 * interval_seconds of the skill and strikes as the Shaman. Magma Totem pulses on its own interval to every enemy within
 * its radius_yards of the totem; Searing Flames stacks a debuff that makes the target take more damage from the
 * Shaman's Fire skills; Capacitor Totem chains its bolts and stuns around itself; Frostflame Totem chills with its
 * bolts and freezes with every Nth; Stoneclaw Totem pulls the enemies around it in and takes damage off the Shaman
 * while it stands.
 */

#include "dc_shaman_searing_totem.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "dc_shaman_searing_totem_math.h"
#include "dc_shaman_totems_math.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_movement_effects.h"
#include "Creature.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <mutex>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Shaman::Searing
{
    namespace
    {
        constexpr std::string_view Skill = "Searing Totem";

        std::mutex mutex;
        // The Searing Flames on each enemy, by Shaman and then enemy.
        std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, Flames>> flames;

        std::string_view RuneOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? std::string_view(row->rune) : std::string_view();
        }

        // The record of one of the skill's runes.
        std::uint32_t RuneId(std::string_view rune)
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && rune == row.rune)
                    return row.id;
            return 0;
        }

        // The hit of a bolt or a pulse: the record's damage_pct (a rune's own, or the skill's it inherits), given to the Strike. The record is NOT
        // claimed for the shell loader (Shaman::BasePct): the placement cast is a ground area of the shell's size, and a shell that loads a hit
        // strikes every enemy in range the moment the totem is placed.
        double HitPct(std::uint32_t source)
        {
            return Numbers::Num(source, "damage_pct");
        }

        // "Each bolt adds a stack of Searing Flames to the target, up to {max_stacks_count}."
        void AddFlame(Player* player, Unit* target, std::uint32_t source)
        {
            std::uint64_t const now = Now();
            std::lock_guard<std::mutex> guard(mutex);
            auto& mine = flames[player->GetGUID().GetRawValue()];
            for (auto it = mine.begin(); it != mine.end();)
                it = Live(it->second, now) ? std::next(it) : mine.erase(it);
            Flames& on = mine[target->GetGUID().GetRawValue()];
            on = Stack(on, now, unsigned(Numbers::Num(source, "max_stacks_count")), Tunable("searing_flames_seconds"));
        }

        // Capacitor Totem: "Bolts chain to {target_count} more enemies."
        void Chain(Player* player, Unit* first, std::uint32_t source)
        {
            double const reach = Tunable("totem_chain_yards");
            for (Unit* enemy : Walk(
                     first, unsigned(Numbers::Num(source, "target_count")),
                     [&](Unit* on) { return Combat::Enemies(player, source, on->GetPosition(), reach); },
                     [](Unit* a, Unit* b) { return double(a->GetExactDist(b)); }))
                Combat::Strike(player, enemy, source, HitPct(source));
        }

        // One bolt at the nearest enemy within the skill's range, and the rune's part of it.
        void Bolt(Player* player, Creature* totem, std::uint32_t source, Totems::State& state)
        {
            auto const enemies =
                Combat::Enemies(player, source, totem->GetPosition(), Numbers::Num(BaseId(Skill), "radius_yards"));
            std::vector<double> distances;
            for (Unit* enemy : enemies)
                distances.push_back(totem->GetExactDist(enemy));
            std::size_t const nearest = Totems::Nearest(distances);
            if (nearest == Totems::None)
                return;
            Unit* target = enemies[nearest];
            totem->SetFacingToObject(target);
            if (!Combat::Strike(player, target, source, HitPct(source)))
                return;
            std::string_view const rune = RuneOf(source);
            if (rune == "Searing Flames")
                AddFlame(player, target, source);
            else if (rune == "Capacitor Totem")
                Chain(player, target, source);
            else if (rune == "Frostflame Totem")
            {
                // "Bolts Chill by {chill_pct}. Every {trigger_count}th bolt Freezes for {freeze_duration_seconds}
                // second."
                Slow(player, target, Numbers::Num(source, "chill_pct"), Tunable("frostflame_chill_seconds"));
                if (Freezes(state.bolts, unsigned(Numbers::Num(source, "trigger_count"))))
                    Freeze(player, target, Numbers::Num(source, "freeze_duration_seconds"));
            }
        }
    } // namespace

    void Update(Player* player, Creature* totem, std::uint32_t source, Totems::State& state, std::uint32_t diff)
    {
        std::string_view const rune = RuneOf(source);
        // Magma Totem: its pulse replaces the bolt, every enemy within its radius_yards of the totem.
        if (rune == "Magma Totem")
        {
            for (unsigned due = Totems::Pulses(state.clock[0], diff, Numbers::Num(source, "interval_seconds")); due;
                 --due)
                Combat::StrikeArea(player, source, totem->GetPosition(), Numbers::Num(source, "radius_yards"), HitPct(source));
            return;
        }
        for (unsigned due = Totems::Pulses(state.clock[0], diff, Numbers::Num(BaseId(Skill), "interval_seconds")); due;
             --due)
            Bolt(player, totem, source, state);
        // The runes with a second pulse of their own: its interval_seconds and radius_yards are the rune's.
        if (rune != "Capacitor Totem" && rune != "Stoneclaw Totem")
            return;
        for (unsigned due = Totems::Pulses(state.clock[1], diff, Numbers::Num(source, "interval_seconds")); due; --due)
            for (Unit* enemy :
                 Combat::Enemies(player, source, totem->GetPosition(), Numbers::Num(source, "radius_yards")))
            {
                // Capacitor Totem stuns around itself; Stoneclaw Totem pulls the enemies around it to it.
                if (rune == "Capacitor Totem")
                    Stun(player, enemy, Numbers::Num(source, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                else
                    Combat::Abilities::Pull(enemy, totem->GetPosition());
            }
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        SpellInfo const* info = target ? sSpellMgr->GetSpellInfo(spellId) : nullptr;
        if (!info || !(info->SchoolMask & SPELL_SCHOOL_MASK_FIRE))
            return;
        unsigned stacks = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto mine = flames.find(player->GetGUID().GetRawValue());
            if (mine == flames.end())
                return;
            auto on = mine->second.find(target->GetGUID().GetRawValue());
            if (on != mine->second.end())
                stacks = Live(on->second, Now());
        }
        if (double const pct = MorePct(stacks, Numbers::Num(RuneId("Searing Flames"), "damage_taken_pct")))
            AddFactor(out, "Searing Flames", pct);
    }

    double TakenFactor(Unit* victim)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (!IsShaman(player))
            return 1.0;
        // "While it is active, you take {damage_reduction_pct} less damage."
        std::uint32_t const standing = Totems::Standing(player, Totems::FireSlot);
        return standing && RuneOf(standing) == "Stoneclaw Totem"
                   ? TakenFactorOf(Numbers::Num(standing, "damage_reduction_pct"))
                   : 1.0;
    }

    void Forget(Player* player)
    {
        std::lock_guard<std::mutex> guard(mutex);
        flames.erase(player->GetGUID().GetRawValue());
    }
} // namespace DC::Combat::Shaman::Searing
