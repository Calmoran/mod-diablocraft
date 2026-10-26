/*
 * Ascendance and its five runes: the buff on the Shaman (more damage, double Maelstrom generation, a bolt for each
 * Primary cast), each rune's element and extra (Flame Ascendance's free Lava Burst, Storm Ascendance's Chain Lightning
 * jumps, Water Ascendance's heal, Earth Ascendance's damage reduction, Eternal Ascendance's extension by the Maelstrom
 * spent). A buff on the Wrath of the Berserker's shape: the bar stays the same and there is no second bar. The cast is
 * the engine's self spell and deals nothing; the dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_ascendance.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_cost_cut.h"
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

namespace DC::Combat::Shaman::Ascendance
{
    namespace
    {
        constexpr std::string_view Skill = "Ascendance";
        // "Maelstrom generation doubles": a hundred percent more.
        constexpr double DoublesGeneration = 100.0;
        // The source of Flame Ascendance's cut of Lava Burst's cost.
        constexpr std::uint32_t CutKey = 2;

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

        // The buff a Shaman carries: the record of the cast, the rune, until when, how far Eternal Ascendance has
        // extended it and the Maelstrom counted toward its next step, and the stamp its pulses answer to.
        struct Buff
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            std::uint64_t until = 0; // game time, ms
            std::uint64_t extended = 0;
            double carried = 0;
            std::uint64_t stamp = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Buff> buffs; // by the Shaman
        std::uint64_t stamps = 0;

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

        // The sheet numbers of the buff, put on or taken off (`on` false).
        void Put(Player* player, std::uint32_t spellId, Rune rune, bool on)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const id = BaseId();
            Stats::RemoveContribution(guid, Source::Temporary, Stat::MaelstromGeneration, id);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::SpecificReduction, id);
            if (on)
            {
                Stats::AddContribution(
                    guid, {Source::Temporary, Stat::MaelstromGeneration, id, DoublesGeneration, Bucket::Flat});
                // Earth Ascendance: "you take {damage_reduction_pct} less damage".
                if (rune == Rune::EarthAscendance)
                    Stats::AddContribution(guid, {Source::Temporary, Stat::SpecificReduction, id,
                                                  Numbers::Num(spellId, "damage_reduction_pct"), Bucket::Flat});
            }
            // Flame Ascendance: "Lava Burst is free": the whole cost comes off the skill's price while the buff stands.
            CostCut::Stand(player, "Lava Burst", CutKey, on && rune == Rune::FlameAscendance ? 100.0 : 0.0);
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        void Pulse(Player* player, std::uint64_t key, std::uint64_t stamp)
        {
            Buff buff;
            bool over;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = buffs.find(key);
                if (found == buffs.end() || found->second.stamp != stamp)
                    return;
                buff = found->second;
                over = !Holds(Now(), buff.until) || !player->IsInWorld() || !player->IsAlive();
                if (over)
                    buffs.erase(found);
            }
            if (over)
            {
                Put(player, buff.spellId, buff.rune, false);
                return;
            }
            // Water Ascendance: "you heal {life_regen_pct} of maximum Life per second".
            double const tick = Tune("ascendance_tick_seconds");
            if (buff.rune == Rune::WaterAscendance)
                Heal(player, buff.spellId,
                     double(player->GetMaxHealth()) * Numbers::Num(buff.spellId, "life_regen_pct") / 100.0 * tick);
            player->m_Events.AddEventAtOffset([player, key, stamp] { Pulse(player, key, stamp); },
                                              std::chrono::milliseconds(std::uint32_t(tick * 1000.0 + 0.5)));
        }

        void Start(Player* player, std::uint32_t spellId)
        {
            Rune const rune = RuneAt(spellId);
            double const seconds = Combat::ModifiedDurationSeconds(player, spellId,
                                                                   Numbers::Num(BaseId(), "duration_seconds")),
                         tick = Tune("ascendance_tick_seconds");
            if (seconds <= 0 || tick <= 0)
                return;
            std::uint64_t const key = player->GetGUID().GetRawValue();
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                // One buff: a new cast replaces it.
                Buff& buff = buffs[key];
                stamp = buff.stamp = ++stamps;
                buff.spellId = spellId;
                buff.rune = rune;
                buff.until = Now() + std::uint64_t(seconds * 1000.0);
                buff.extended = 0;
                buff.carried = 0;
            }
            Put(player, spellId, rune, true);
            player->m_Events.AddEventAtOffset([player, key, stamp] { Pulse(player, key, stamp); },
                                              std::chrono::milliseconds(std::uint32_t(tick * 1000.0 + 0.5)));
        }

        // The weapon damage percent the cast's own hit of a Primary's record deals.
        double HitPctOf(std::uint32_t spellId)
        {
            return PrimaryBasePct(spellId).value_or(Numbers::Num(spellId, "damage_pct"));
        }

        // "each Primary skill cast also fires an elemental bolt at {target_count} more enemies for {damage_share_pct}
        // of its damage".
        void Bolts(Player* player, std::uint32_t primary, std::vector<Unit*> const& targets)
        {
            if (targets.empty() || !targets.front())
                return;
            Unit* first = targets.front();
            std::vector<Unit*> near =
                Combat::Enemies(player, primary, first->GetPosition(), Tune("ascendance_bolt_radius_yards"));
            near.erase(std::remove_if(near.begin(), near.end(), [&](Unit* enemy)
                                      { return std::find(targets.begin(), targets.end(), enemy) != targets.end(); }),
                       near.end());
            std::sort(near.begin(), near.end(),
                      [first](Unit* a, Unit* b) { return first->GetExactDist(a) < first->GetExactDist(b); });
            auto const count = std::size_t(Numbers::Num(BaseId(), "target_count"));
            if (near.size() > count)
                near.resize(count);
            double const pct = BoltPct(HitPctOf(primary), Numbers::Num(BaseId(), "damage_share_pct"));
            for (Unit* enemy : near)
                Combat::Strike(player, enemy, primary, pct);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!player || Is(spellId) || Classes::CategoryOf(spellId) != "Secondary")
            return;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = buffs.find(player->GetGUID().GetRawValue());
        if (found == buffs.end() || !Holds(Now(), found->second.until))
            return;
        Buff& buff = found->second;
        Extension const more = Extend(buff.rune, buff.carried, Numbers::Get(spellId, "cost_resource").value_or(0.0),
                                      buff.extended, Numbers::Num(buff.spellId, "per_trigger_resource"),
                                      Numbers::Num(buff.spellId, "duration_seconds", "extend"),
                                      Numbers::Num(buff.spellId, "duration_seconds", "cap"));
        buff.carried = more.remainder;
        buff.extended += more.addMs;
        buff.until += more.addMs;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player)
            return;
        if (Is(spellId))
        {
            Start(player, spellId);
            return;
        }
        bool up;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = buffs.find(player->GetGUID().GetRawValue());
            up = found != buffs.end() && Holds(Now(), found->second.until);
        }
        if (Fires(Classes::CategoryOf(spellId), up))
            Bolts(player, spellId, targets);
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!player)
            return;
        Buff buff;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = buffs.find(player->GetGUID().GetRawValue());
            if (found == buffs.end() || !Holds(Now(), found->second.until))
                return;
            buff = found->second;
        }
        // The element the hit actually deals: the blast and Primal Shock deal the Attunement through the element seam.
        char const* dealt = DC::Combat::Shaman::Element(player, spellId);
        std::string_view const element =
            dealt && *dealt ? std::string_view(dealt) : std::string_view(ElementOfSpell(spellId));
        if (double const bonus = Bonus(buff.rune, element, Numbers::Num(BaseId(), "damage_bonus_pct"),
                                       Numbers::Num(buff.spellId, "damage_bonus_pct")))
            AddFactor(out, "Ascendance", bonus);
    }

    unsigned ExtraChainJumps(Player* player)
    {
        if (!player)
            return 0;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = buffs.find(player->GetGUID().GetRawValue());
        if (found == buffs.end() || !Holds(Now(), found->second.until))
            return 0;
        return ExtraJumps(found->second.rune, Numbers::Num(found->second.spellId, "target_count"));
    }
} // namespace DC::Combat::Shaman::Ascendance
