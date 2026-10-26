/*
 * Bone Spikes and its five runes. The engine hits every enemy on the area for the skill's weapon damage; here: Sudden
 * Impact stuns them (an enemy it stunned is not stunned by it again for its internal cooldown), Path of Bones lays a line instead, Bone Pillars strikes the nearest enemy and two around it instead,
 * Frost Spikes slows them (the record's Cold is its damage), Blood Spikes makes them bleed and heals the Necromancer.
 */

#include "dc_necromancer_bone_spikes.h"
#include "dc_necromancer_bone_spikes_math.h"
#include "dc_necromancer_common.h"
#include "../../combat/dc_item_powers.h"

#include "GameTime.h"
#include "ObjectAccessor.h"

#include <algorithm>
#include <chrono>
#include <iterator>
#include <map>
#include <mutex>
#include <tuple>

namespace DC::Combat::Necromancer::BoneSpikes
{
    namespace
    {
        constexpr std::string_view Skill = "Bone Spikes";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The running bleeds: a new bleed takes a new stamp, and the ticks of the old one find their stamp gone and stop.
        using Key = std::tuple<std::uint64_t, std::uint64_t, std::uint32_t>;
        std::mutex mutex;
        std::map<Key, std::uint64_t> bleeds;
        std::uint64_t stamps = 0;

        // When Sudden Impact last stunned each enemy for each Necromancer, for its internal cooldown. Entries past the
        // cooldown are swept when the map grows.
        std::map<std::pair<std::uint64_t, std::uint64_t>, std::uint64_t> stuns;
        constexpr std::size_t StunsSweptAt = 256;

        // Whether Sudden Impact may stun this enemy now (its internal cooldown has passed), and if it may, the stun is
        // recorded.
        bool TakeStun(Player* player, Unit* enemy)
        {
            auto const now = std::uint64_t(GameTime::GetGameTimeMS().count());
            auto const icdMs = std::uint64_t(std::max(0.0, Tune("sudden_impact_icd_seconds")) * 1000 + 0.5);
            std::pair<std::uint64_t, std::uint64_t> const key{player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue()};
            std::lock_guard<std::mutex> guard(mutex);
            auto found = stuns.find(key);
            if (!StunReady(found != stuns.end(), found != stuns.end() ? found->second : 0, now, icdMs))
                return false;
            if (stuns.size() >= StunsSweptAt)
                for (auto it = stuns.begin(); it != stuns.end();)
                    it = StunReady(true, it->second, now, icdMs) ? stuns.erase(it) : std::next(it);
            stuns[key] = now;
            return true;
        }

        void Tick(Player* player, ObjectGuid enemy, std::uint32_t spellId, std::uint64_t stamp, unsigned left, double pct,
                  double heal, std::uint32_t intervalMs)
        {
            Key const key{player->GetGUID().GetRawValue(), enemy.GetRawValue(), spellId};
            Unit* target = ObjectAccessor::GetUnit(*player, enemy);
            bool const alive = target && target->IsAlive() && player->IsAlive();
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = bleeds.find(key);
                if (found == bleeds.end() || found->second != stamp)
                    return;
                if (!alive || left == 0)
                {
                    bleeds.erase(found);
                    return;
                }
            }
            Combat::Strike(player, target, spellId, pct, true);
            Heal(player, spellId, heal);
            if (left > 1)
                player->m_Events.AddEventAtOffset([player, enemy, spellId, stamp, left, pct, heal, intervalMs]
                                                  { Tick(player, enemy, spellId, stamp, left - 1, pct, heal, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
            else
            {
                std::lock_guard<std::mutex> guard(mutex);
                bleeds.erase(key);
            }
        }

        // Blood Spikes: `totalPct` of weapon damage over `seconds` in ticks of `tickSeconds`, and the Necromancer healed
        // `healPct` of its maximum Life over the same ticks; one bleed running per Necromancer, enemy and spell.
        void Bleed(Player* player, Unit* enemy, std::uint32_t spellId, double totalPct, double seconds, double tickSeconds,
                   double healPct)
        {
            unsigned const ticks = Ticks(seconds, tickSeconds);
            if (!player || !enemy || !ticks)
                return;
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                stamp = ++stamps;
                bleeds[{player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue(), spellId}] = stamp;
            }
            auto const interval = std::uint32_t(tickSeconds * 1000 + 0.5);
            double const pct = TickShare(totalPct, ticks);
            double const heal = HealPerTick(player->GetMaxHealth(), healPct, ticks);
            player->m_Events.AddEventAtOffset([player, guid = enemy->GetGUID(), spellId, stamp, ticks, pct, heal, interval]
                                              { Tick(player, guid, spellId, stamp, ticks, pct, heal, interval); },
                                              std::chrono::milliseconds(interval));
        }

        // Path of Bones: "a line of spikes that deals {damage_pct} weapon damage ... increased by up to {max_bonus_pct}
        // for those further away": from the Necromancer toward the aimed point, the length of the cast's reach.
        void Line(Player* player, std::uint32_t spellId, Position const& center)
        {
            double const length = Tune("path_of_bones_length_yards");
            double const width = Tune("path_of_bones_width_yards");
            if (length <= 0)
                return;
            double dx = center.GetPositionX() - player->GetPositionX(), dy = center.GetPositionY() - player->GetPositionY();
            double const reach = std::sqrt(dx * dx + dy * dy);
            if (reach < 0.01)
            {
                dx = std::cos(player->GetOrientation());
                dy = std::sin(player->GetOrientation());
            }
            else
            {
                dx /= reach;
                dy /= reach;
            }
            Position const middle(player->GetPositionX() + dx * length / 2.0, player->GetPositionY() + dy * length / 2.0,
                                  player->GetPositionZ());
            double const basePct = Numbers::Num(spellId, "damage_pct"), bonus = Numbers::Num(spellId, "max_bonus_pct");
            unsigned hit = 0;
            for (Unit* enemy : Combat::Enemies(player, spellId, middle, length / 2.0 + width))
            {
                double const along = AlongTheLine(player->GetPositionX(), player->GetPositionY(), dx, dy,
                                                  enemy->GetPositionX(), enemy->GetPositionY(), length, width);
                if (along >= 0 && Combat::Strike(player, enemy, spellId, PathPct(basePct, bonus, along, length)))
                    ++hit;
            }
            if (hit)
                Combat::Connected(player, spellId, hit);
        }

        // Bone Pillars: "strikes the target and up to two nearby enemies with large bone pillars for {damage_pct} weapon
        // damage per second": the enemy nearest the aimed point and the nearest around it, each for the power's Damage
        // Scalar of a hit (the tooltip's second is the hits a second).
        void Pillars(Player* player, std::uint32_t spellId, Position const& center)
        {
            std::vector<Unit*> under = Combat::Enemies(player, spellId, center, Combat::TargetRadius(spellId));
            if (under.empty())
                return;
            std::vector<double> distances;
            for (Unit* enemy : under)
                distances.push_back(center.GetExactDist(enemy));
            Unit* primary = under[Nearest(distances, Combat::TargetRadius(spellId), 1).front()];
            std::vector<Unit*> around;
            distances.clear();
            for (Unit* enemy : Combat::Enemies(player, spellId, primary->GetPosition(), Tune("bone_pillars_reach_yards")))
                if (enemy != primary)
                {
                    around.push_back(enemy);
                    distances.push_back(primary->GetExactDist(enemy));
                }
            std::vector<Unit*> struck{primary};
            // "strikes the target and up to two nearby enemies": the rune text's number of enemies besides the target.
            std::size_t const besides = std::size_t(std::max(0.0, Tune("bone_pillars_extra_enemies")));
            for (std::size_t index : Nearest(distances, Tune("bone_pillars_reach_yards"), besides))
                struck.push_back(around[index]);
            double const pct = Numbers::Num(spellId, "damage_pct");
            unsigned hit = 0;
            for (Unit* enemy : struck)
                if (Combat::Strike(player, enemy, spellId, pct))
                    ++hit;
            if (hit)
                Combat::Connected(player, spellId, hit);
        }
    } // namespace

    std::optional<double> GeneratedEssence(std::uint32_t spellId)
    {
        // "RUNEB: Essence Gained" 30, against the 24 of the skill and its other runes.
        return RuneAt(spellId) == Rune::PathOfBones ? std::optional<double>(Tune("path_of_bones_essence")) : std::nullopt;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!RowOf(spellId, Skill))
            return std::nullopt;
        Rune const rune = RuneAt(spellId);
        if (DealsItsOwnHit(rune))
            return 0.0;
        if (rune == Rune::BloodSpikes)
            return Numbers::Get(BaseId(Skill), "damage_pct");
        return std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::SuddenImpact:
            {
                // "stun enemies for {stun_duration_seconds} second": stretched by the worn stun duration powers.
                double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
                for (Unit* enemy : targets)
                    if (TakeStun(player, enemy))
                        Stun(player, enemy, stun);
                break;
            }
            case Rune::FrostSpikes:
                for (Unit* enemy : targets)
                    Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"));
                break;
            case Rune::BloodSpikes:
                for (Unit* enemy : targets)
                    if (enemy->IsAlive())
                        Bleed(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                              Numbers::Num(spellId, "dot_duration_seconds"), Tune("blood_spikes_tick_seconds"),
                              Numbers::Num(spellId, "heal_pct"));
                break;
            default:
                break;
        }
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::PathOfBones:
                Line(player, spellId, center);
                break;
            case Rune::BonePillars:
                Pillars(player, spellId, center);
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Necromancer::BoneSpikes
