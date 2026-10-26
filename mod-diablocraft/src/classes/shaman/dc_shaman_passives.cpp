/*
 * The Shaman's passives that need code, first four. Elemental Focus rides the critical hit (it arms) and the next
 * Secondary cast (it spends) through the skills' hidden cost auras; Call of Flame rides the hit's multipliers and the
 * Burning effects' seconds; Elemental Fury and Ancestral Knowledge are sheet numbers the class's upkeep keeps. The
 * numbers are shaman_passive_values.csv (skill = the passive's name), read through each passive's record.
 */

#include "dc_shaman_passives.h"
#include "dc_shaman_chill.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_cost_cut.h"
#include "../../combat/dc_passives.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "SharedDefines.h"
#include "ObjectAccessor.h"
#include "Group.h"
#include "GroupReference.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Random.h"
#include "Unit.h"

#include <map>
#include <mutex>
#include <set>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Shaman::Passive
{
    namespace
    {
        double Num(char const* name, char const* token, char const* qualifier = "")
        {
            return Numbers::Num(PassiveId(name), token, qualifier);
        }

        std::uint64_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint64_t(seconds * 1000.0) : 0;
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

        // The element a hit of `spellId` actually deals: the blast and Primal Shock deal the Attunement through the element seam, any other hit its
        // record's school.
        std::string_view ElementDealt(Player* player, std::uint32_t spellId)
        {
            char const* dealt = DC::Combat::Shaman::Element(player, spellId);
            return dealt && *dealt ? std::string_view(dealt) : std::string_view(ElementOfSpell(spellId));
        }

        // What each Shaman has: the casts counted, the cast the focus was armed at (0 for no focus), and the sheet
        // numbers held.
        struct Focus
        {
            std::uint64_t casts = 0;
            std::uint64_t armedAt = 0;
            bool ready = false;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Focus> focus;
        // The milliseconds each Shaman has stood still (Rooted in Earth).
        std::unordered_map<std::uint64_t, std::uint64_t> still;
        // When Reincarnation last saved each Shaman (0 for never): the window of immunity and the internal cooldown both count from it.
        std::unordered_map<std::uint64_t, std::uint64_t> reborn;
        // The Maelstrom each Shaman spent that did not make a step of Primal Wisdom yet.
        std::unordered_map<std::uint64_t, double> wisdom;
        // What one cast of a Secondary skill healed (Ancestral Guidance): the enemies it healed for and the percent of maximum Life so far.
        struct Guided
        {
            std::set<std::uint64_t> enemies;
            double healedPct = 0;
        };
        std::map<std::pair<std::uint64_t, std::uint32_t>, Guided> guidance;
        // The hits being resolved on this thread are a free cast Lightning Overload made: they are smaller and roll nothing again. Set while the
        // free cast is cast and again where its delayed hits land.
        thread_local bool overloading = false;
        // The Lightning Secondary casts that rolled an Overload and have not made it yet: (Shaman, skill).
        std::set<std::pair<std::uint64_t, std::uint32_t>> owed;
        // When each Shaman last dealt a hit of each element (Natural Harmony), and, for each enemy it hit, the same (Elemental Equilibrium).
        std::unordered_map<std::uint64_t, ElementTimes> dealt;
        std::map<std::pair<std::uint64_t, std::uint64_t>, ElementTimes> equilibrium;
        // The holders of Elemental Oath's crit chance (the Shaman and its group in the aura) and when each holding ends, game time in ms.
        std::unordered_map<std::uint64_t, std::uint64_t> sworn;

        // Echo of the Elements: "Totem and Primal cooldowns recover {cooldown_reduction_pct} faster": the cooldown the core installed on a Primal skill, in
        // each rune's record, shortened by that share.
        void Echo(Player* player, char const* skill)
        {
            double const pct = Num("Echo of the Elements", "cooldown_reduction_pct");
            for (auto const& row : Shells::Abilities)
                if (std::string_view(row.skill) == skill)
                    if (std::uint32_t const left = player->GetSpellCooldownDelay(row.id))
                        player->ModifySpellCooldown(row.id, -std::int32_t(EchoCut(double(left), pct)));
        }

        void Lapse(Player* holder, std::uint64_t guid);

        // The crit chance Elemental Oath gives off or on `holder`'s sheet.
        void Swear(Player* holder, bool on)
        {
            std::uint64_t const guid = holder->GetGUID().GetRawValue();
            std::uint32_t const id = PassiveId("Elemental Oath");
            Stats::RemoveContribution(guid, Source::Passives, Stat::CritChance, id);
            if (on)
                Stats::AddContribution(guid, {Source::Passives, Stat::CritChance, id, Num("Elemental Oath", "crit_chance_pct"), Bucket::Flat});
            Stats::Recompute(holder);
            Inventory::PushSheet(holder);
        }

        // The holding ends when no Shaman has renewed it: checked at the time it was to end, put off again when it was renewed since.
        void Lapse(Player* holder, std::uint64_t guid)
        {
            std::uint64_t until = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = sworn.find(guid);
                if (found == sworn.end())
                    return;
                until = found->second;
                if (until <= Now())
                    sworn.erase(found);
            }
            if (until <= Now())
            {
                Swear(holder, false);
                return;
            }
            holder->m_Events.AddEventAtOffset([holder, guid] { Lapse(holder, guid); }, std::chrono::milliseconds(until - Now() + 1));
        }

        // Elemental Oath: "You and allies within {radius_yards:aura} yards gain {crit_chance_pct} Critical Hit Chance." Renewed at every upkeep for the
        // Shaman and each living group member in the aura; one holder holds it once, whoever swore it.
        void Renew(Player* shaman, std::uint32_t stepMs)
        {
            double const radius = Num("Elemental Oath", "radius_yards", "aura");
            std::vector<Player*> holders{shaman};
            if (Group* group = shaman->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource())
                        if (member != shaman && member->IsAlive() && member->IsInWorld() && member->GetMap() == shaman->GetMap() &&
                            InOath(shaman->GetExactDist(member), radius))
                            holders.push_back(member);
            std::uint64_t const until = Now() + 3ull * stepMs;
            for (Player* holder : holders)
            {
                bool fresh;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto [found, added] = sworn.insert({holder->GetGUID().GetRawValue(), until});
                    // A holding that ran out (a holder who logged out never lapsed) is begun again.
                    fresh = added || found->second <= Now();
                    found->second = until;
                }
                if (!fresh)
                    continue;
                Swear(holder, true);
                std::uint64_t const guid = holder->GetGUID().GetRawValue();
                holder->m_Events.AddEventAtOffset([holder, guid] { Lapse(holder, guid); }, std::chrono::milliseconds(until - Now() + 1));
            }
        }

        // Primal Wisdom: `seconds` off the cooldown of every Primal skill that is cooling down (the records of a skill's runes each hold the cooldown
        // the core installed).
        void CutPrimals(Player* player, double seconds)
        {
            for (auto const& row : Shells::Abilities)
                if (std::uint32_t const left = player->GetSpellCooldownDelay(row.id))
                    if (Classes::CategoryOf(row.id) == "Primal")
                        player->ModifySpellCooldown(row.id, -std::int32_t(std::min<std::uint64_t>(left, Millis(seconds))));
        }

        // Ancestral Guidance: a Secondary hit on `target` heals for the percent the cast has left to heal.
        void Guide(Player* player, Unit* target, std::uint32_t spellId)
        {
            double heal = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                Guided& guided = guidance[{player->GetGUID().GetRawValue(), Classes::SkillIdOf(spellId)}];
                if (guided.enemies.insert(target->GetGUID().GetRawValue()).second)
                {
                    heal = GuidanceHeal(guided.healedPct, Num("Ancestral Guidance", "heal_pct", "per_enemy"), Num("Ancestral Guidance", "heal_pct", "cap"));
                    guided.healedPct += heal;
                }
            }
            // "Your Secondary skills heal you for {heal_pct:per_enemy} of maximum Life per enemy hit, up to {heal_pct:cap} per cast."
            if (heal > 0)
                Heal(player, PassiveId("Ancestral Guidance"), double(player->GetMaxHealth()) * heal / 100.0);
        }

        // Natural Harmony and Elemental Equilibrium: the element a hit of the Shaman's dealt, and when.
        void Record(Player* player, Unit* target, std::uint32_t spellId)
        {
            bool const natural = On(player, "Natural Harmony"), balanced = On(player, "Elemental Equilibrium");
            if (!natural && !balanced)
                return;
            int const slot = ElementIndex(ElementDealt(player, spellId));
            if (slot < 0)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue(), now = Now();
            std::lock_guard<std::mutex> guard(mutex);
            if (natural)
                dealt[guid][slot] = now;
            if (balanced && target)
                equilibrium[{guid, target->GetGUID().GetRawValue()}][slot] = now;
        }

        // Lightning Overload: where the first hit of a cast that rolled it lands, the skill is cast again for free (the core's triggered cast: no cost, no
        // cooldown, no cast event) at the target. The free cast is marked while it is cast, so it rolls nothing and its hits take the share.
        void MakeOverload(Player* player, Unit* target, std::uint32_t spellId)
        {
            if (overloading || !IsShaman(player) || Classes::CategoryOf(spellId) != "Secondary")
                return;
            auto const* row = Shells::FindAbility(spellId);
            {
                std::lock_guard<std::mutex> guard(mutex);
                if (!row || owed.erase({player->GetGUID().GetRawValue(), Classes::SkillIdOf(spellId)}) == 0)
                    return;
            }
            bool const before = FreeCasting(true);
            Combat::CastSkill(player, row->skill, target);
            FreeCasting(before);
        }

        // The contribution a passive holds on a sheet: (player, stat, passive's id) -> the value, so a changed value or
        // a passive taken out is put right.
        std::map<std::tuple<std::uint64_t, Stat, std::uint32_t>, double> held;

        // The skills of the Secondary category (the skill's own record, not its runes): each has the hidden cost aura
        // Elemental Focus' cut stands on.
        std::vector<std::string> const& Secondaries()
        {
            static std::vector<std::string> const names = []
            {
                std::vector<std::string> out;
                std::set<std::string> seen;
                for (auto const& row : Shells::Abilities)
                    if (!*row.rune && Classes::CategoryOf(row.id) == "Secondary" && seen.insert(row.skill).second)
                        out.push_back(row.skill);
                return out;
            }();
            return names;
        }

        // Puts the cut on every Secondary skill (`pct`) or takes it off (0).
        void Cut(Player* player, double pct)
        {
            for (std::string const& skill : Secondaries())
                CostCut::Stand(player, skill, PassiveId("Elemental Focus"), pct);
        }

        // A passive's sheet contribution: `wanted` (0 for none) in place of what was held. True when it changed.
        bool Hold(Player* player, Stat stat, Bucket bucket, char const* passive, double wanted)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const id = PassiveId(passive);
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = held.find({guid, stat, id});
                double const had = found == held.end() ? 0.0 : found->second;
                if (had == wanted)
                    return false;
                if (wanted == 0.0)
                    held.erase({guid, stat, id});
                else
                    held[{guid, stat, id}] = wanted;
            }
            Stats::RemoveContribution(guid, Source::Passives, stat, id);
            if (wanted != 0.0)
                Stats::AddContribution(guid, {Source::Passives, stat, id, wanted, bucket});
            return true;
        }
    } // namespace

    bool On(Player* player, char const* name)
    {
        return IsShaman(player) && Passives::Has(player, name);
    }

    double BurnSecondsFor(Player* player, double seconds)
    {
        return BurnSeconds(On(player, "Call of Flame"), seconds, Num("Call of Flame", "duration_seconds"));
    }

    double HarmonyFor(Player* player)
    {
        return HarmonyFactor(On(player, "Elemental Harmony"));
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!IsShaman(player))
            return;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        {
            std::lock_guard<std::mutex> guard(mutex);
            ++focus[guid].casts;
        }
        if (Classes::CategoryOf(spellId) != "Secondary")
            return;
        {
            // A new cast of the skill heals for its enemies again.
            std::lock_guard<std::mutex> guard(mutex);
            guidance.erase({guid, Classes::SkillIdOf(spellId)});
        }
        auto const* row = Shells::FindAbility(spellId);
        if (!row || !On(player, "Primal Wisdom"))
            return;
        // What the cast pays: the sheet's cost less the cuts that stand now (Elemental Focus is spent after the cast starts).
        double const paid = Numbers::Get(spellId, "cost_resource").value_or(0.0) * (1.0 - CostCut::Pct(player, row->skill) / 100.0);
        Wisdom made;
        {
            std::lock_guard<std::mutex> guard(mutex);
            double& carried = wisdom[guid];
            made = WisdomSteps(carried, paid, Num("Primal Wisdom", "per_trigger_resource"));
            carried = made.carried;
        }
        if (made.steps)
            CutPrimals(player, made.steps * Num("Primal Wisdom", "cooldown_reduction_seconds"));
    }

    double Reduce(Unit* victim, double damage)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (damage <= 0 || !On(player, "Reincarnation"))
            return damage;
        std::uint64_t const now = Now();
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::uint64_t& last = reborn[player->GetGUID().GetRawValue()];
            // The window the last save opened: every blow in it does nothing.
            if (Immune(last, now, Millis(Num("Reincarnation", "duration_seconds"))))
                return 0.0;
            // "When you take fatal damage ... Can trigger once every {internal_cooldown_seconds} seconds."
            if (!Fatal(damage, double(player->GetHealth())) || !CooledDown(last, now, Millis(Num("Reincarnation", "internal_cooldown_seconds"))))
                return damage;
            last = now;
        }
        // "you are restored to {life_floor_pct} Life and become immune to damage for {duration_seconds} seconds."
        Heal(player, PassiveId("Reincarnation"), RestoredLife(double(player->GetHealth()), double(player->GetMaxHealth()), Num("Reincarnation", "life_floor_pct")));
        return 0.0;
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        MakeOverload(player, target, spellId);
        Record(player, target, spellId);
        if (target && On(player, "Ancestral Guidance") && Classes::CategoryOf(spellId) == "Secondary")
            Guide(player, target, spellId);
        if (!critical || !On(player, "Elemental Focus"))
            return;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Focus& state = focus[player->GetGUID().GetRawValue()];
            if (state.ready)
                return;
            state.ready = true;
            state.armedAt = state.casts;
        }
        // "After a critical hit, your next Secondary skill costs {cost_reduction_pct} less Maelstrom."
        Cut(player, FocusCut(true, Num("Elemental Focus", "cost_reduction_pct")));
    }

    void Launched(Player* player, std::uint32_t spellId, bool triggered)
    {
        // A free cast (Lightning Overload's, Lava Surge's) pays nothing, spends no focus and rolls no Overload.
        if (!IsShaman(player) || triggered)
            return;
        std::string_view const category = Classes::CategoryOf(spellId);
        if (category == "Primal")
        {
            if (auto const* row = Shells::FindAbility(spellId); row && On(player, "Echo of the Elements"))
                Echo(player, row->skill);
            return;
        }
        if (category != "Secondary")
            return;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        bool spent = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = focus.find(guid);
            if (found != focus.end() && SpendsFocus(found->second.ready, found->second.armedAt, found->second.casts))
            {
                found->second.ready = false;
                spent = true;
            }
        }
        if (spent)
            Cut(player, 0.0);
        // "Your Lightning Secondary skills have a {proc_chance_pct} chance to cast again for free at {damage_share_pct} damage." Rolled once at the
        // launch, whichever way the cast reaches its hits; the free cast is made where the first hit lands (Landed).
        bool const rolled = On(player, "Lightning Overload") && OverloadsElement("Secondary", ElementDealt(player, spellId)) &&
                            Overloads(frand(0.0f, 1.0f), Num("Lightning Overload", "proc_chance_pct"));
        std::lock_guard<std::mutex> guard(mutex);
        if (rolled)
            owed.insert({guid, Classes::SkillIdOf(spellId)});
        else
            owed.erase({guid, Classes::SkillIdOf(spellId)});
    }

    bool FreeCasting()
    {
        return overloading;
    }

    bool FreeCasting(bool on)
    {
        bool const before = overloading;
        overloading = on;
        return before;
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!IsShaman(player))
            return;
        // "Fire skills deal {damage_bonus_pct} more damage": the element the hit actually deals.
        if (double const bonus = FireBonus(On(player, "Call of Flame"), ElementDealt(player, spellId), Num("Call of Flame", "damage_bonus_pct")))
            AddFactor(out, "Call of Flame", bonus);
        // "You deal {damage_bonus_pct} more damage to Chilled or Frozen enemies."
        if (target && On(player, "Frozen Power"))
            if (double const bonus = FrozenBonus(Chilled(player, target) || Held(player, target), Num("Frozen Power", "damage_bonus_pct")))
                AddFactor(out, "Frozen Power", bonus);
        std::uint64_t const now = Now();
        // "it takes {damage_taken_pct} more damage from your other three elements for {duration_seconds} seconds (up to {max_bonus_pct})."
        int const slot = ElementIndex(ElementDealt(player, spellId));
        if (target && slot >= 0 && On(player, "Elemental Equilibrium"))
        {
            unsigned others = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = equilibrium.find({player->GetGUID().GetRawValue(), target->GetGUID().GetRawValue()});
                if (found != equilibrium.end())
                    others = ElementsWithin(found->second, slot, now, Millis(Num("Elemental Equilibrium", "duration_seconds")));
            }
            if (double const bonus = ElementsBonus(others, Num("Elemental Equilibrium", "damage_taken_pct"), Num("Elemental Equilibrium", "max_bonus_pct")))
                AddFactor(out, "Elemental Equilibrium", bonus);
        }
        // "Each different element you have dealt damage with in the last {duration_seconds} seconds increases your damage by {damage_bonus_pct}."
        if (On(player, "Natural Harmony"))
        {
            unsigned elements = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = dealt.find(player->GetGUID().GetRawValue());
                if (found != dealt.end())
                    elements = ElementsWithin(found->second, -1, now, Millis(Num("Natural Harmony", "duration_seconds")));
            }
            if (double const bonus = ElementsBonus(elements, Num("Natural Harmony", "damage_bonus_pct"), Num("Natural Harmony", "max_bonus_pct")))
                AddFactor(out, "Natural Harmony", bonus);
        }
        // "Fire Elemental and Earth Elemental deal {damage_bonus_pct} more damage."
        if (auto const* row = Shells::FindAbility(spellId))
            if (double const bonus = ElementalDamage(On(player, "Primal Elementalist"), row->skill, Num("Primal Elementalist", "damage_bonus_pct")))
                AddFactor(out, "Primal Elementalist", bonus);
        // The free cast Lightning Overload makes deals the share of the damage the sheet states.
        if (overloading)
            if (double const cut = OverloadPct(Num("Lightning Overload", "damage_share_pct")))
                AddFactor(out, "Lightning Overload", cut);
    }

    double ElementalLasts(Player* player, std::string_view skill, double seconds)
    {
        // "Fire Elemental and Earth Elemental ... last {duration_bonus_pct} longer."
        return ElementalSeconds(On(player, "Primal Elementalist") && IsElemental(skill), seconds, Num("Primal Elementalist", "duration_bonus_pct"));
    }

    double PrimaryGain(Player* player)
    {
        // "Your Primary skills generate {gain_resource} more Maelstrom."
        return On(player, "Deep Maelstrom") ? Num("Deep Maelstrom", "gain_resource") : 0.0;
    }

    void Upkeep(Player* player, std::uint32_t stepMs)
    {
        if (!IsShaman(player))
            return;
        bool changed = false;
        // "Critical Hit Damage +{crit_damage_pct}."
        changed |= Hold(player, Stat::CritDamage, Bucket::Flat, "Elemental Fury", On(player, "Elemental Fury") ? Num("Elemental Fury", "crit_damage_pct") : 0.0);
        // "Intelligence +{primary_stat_pct}. Maximum Maelstrom +{max_pool_resource}." / "Maximum Maelstrom +{max_pool_resource}."
        bool const knowing = On(player, "Ancestral Knowledge");
        changed |= Hold(player, Stat::Intelligence, Bucket::Percent, "Ancestral Knowledge", knowing ? Num("Ancestral Knowledge", "primary_stat_pct") : 0.0);
        changed |= Hold(player, Stat::MaxSecond, Bucket::Flat, "Ancestral Knowledge", knowing ? Num("Ancestral Knowledge", "max_pool_resource") : 0.0);
        changed |= Hold(player, Stat::MaxSecond, Bucket::Flat, "Deep Maelstrom", On(player, "Deep Maelstrom") ? Num("Deep Maelstrom", "max_pool_resource") : 0.0);
        // "Each Overcharge stack also gives +{crit_chance_pct} Critical Hit Chance."
        changed |= Hold(player, Stat::CritChance, Bucket::Flat, "Storm Surge",
                        On(player, "Storm Surge") ? SurgeCrit(Overcharge::Stacks(player), Num("Storm Surge", "crit_chance_pct")) : 0.0);
        // "After you stand still for {duration_seconds} second, take {damage_reduction_pct} less damage until you move."
        std::uint64_t stood = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::uint64_t& stillMs = still[player->GetGUID().GetRawValue()];
            stillMs = StillMs(player->isMoving(), stillMs, stepMs);
            stood = stillMs;
        }
        changed |= Hold(player, Stat::SpecificReduction, Bucket::Flat, "Rooted in Earth",
                        On(player, "Rooted in Earth") ? RootedCut(stood, Num("Rooted in Earth", "duration_seconds"), Num("Rooted in Earth", "damage_reduction_pct")) : 0.0);
        if (changed)
        {
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }
        if (On(player, "Elemental Oath"))
            Renew(player, stepMs);
        {
            // What the enemies' marks and the elements dealt hold past their seconds is let go.
            std::uint64_t const guid = player->GetGUID().GetRawValue(), now = Now();
            std::uint64_t const lasts = Millis(std::max(Num("Elemental Equilibrium", "duration_seconds"), Num("Natural Harmony", "duration_seconds")));
            std::lock_guard<std::mutex> guard(mutex);
            for (auto it = equilibrium.lower_bound({guid, 0}); it != equilibrium.end() && it->first.first == guid;)
                it = ElementsWithin(it->second, -1, now, lasts) == 0 ? equilibrium.erase(it) : std::next(it);
        }
        // A focus armed by a passive that was taken out is put away.
        if (!On(player, "Elemental Focus"))
        {
            bool armed = false;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = focus.find(player->GetGUID().GetRawValue());
                armed = found != focus.end() && found->second.ready;
                if (armed)
                    found->second.ready = false;
            }
            if (armed)
                Cut(player, 0.0);
        }
    }

    void Forget(Player* player)
    {
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        std::lock_guard<std::mutex> guard(mutex);
        focus.erase(guid);
        still.erase(guid);
        for (auto it = owed.begin(); it != owed.end();)
            it = it->first == guid ? owed.erase(it) : std::next(it);
        reborn.erase(guid);
        dealt.erase(guid);
        sworn.erase(guid);
        for (auto it = equilibrium.lower_bound({guid, 0}); it != equilibrium.end() && it->first.first == guid;)
            it = equilibrium.erase(it);
        wisdom.erase(guid);
        for (auto it = guidance.begin(); it != guidance.end();)
            it = it->first.first == guid ? guidance.erase(it) : std::next(it);
        for (auto it = held.begin(); it != held.end();)
            it = std::get<0>(it->first) == guid ? held.erase(it) : std::next(it);
    }
} // namespace DC::Combat::Shaman::Passive
