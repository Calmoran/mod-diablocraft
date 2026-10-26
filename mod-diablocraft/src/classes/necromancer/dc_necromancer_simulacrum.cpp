/*
 * Simulacrum and its five runes. The cast takes a share of the Necromancer's Life and raises the copy (the minions'
 * kind in dc_necromancer_pets.cpp, one per Number of Mirrors; Blood and Bone adds a Simulacrum of Bone). While a copy
 * stands, each Secondary skill the Necromancer casts is cast again by code for each copy, at the same enemy and for
 * nothing; the runes add Reservoir's Essence, Cursed Form's three curses, Blood Debt's cheaper Life and Self
 * Sacrifice's second chance.
 */

#include "dc_necromancer_simulacrum.h"
#include "dc_necromancer_simulacrum_math.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_curses.h"
#include "dc_necromancer_decrepify.h"
#include "dc_necromancer_frailty.h"
#include "dc_necromancer_leech.h"
#include "dc_necromancer_pets.h"
#include "../../combat/dc_minions.h"
#include "../../stats/dc_stats.h"

#include "ObjectAccessor.h"

#include <chrono>
#include <mutex>
#include <string>
#include <unordered_map>

namespace DC::Combat::Necromancer::Simulacrum
{
    namespace
    {
        constexpr std::string_view Skill = "Simulacrum";
        constexpr char const* Copy = "simulacrum";
        constexpr char const* BoneCopy = "simulacrum_bone";
        // The standing default for an aura pulse (1 s): how often Reservoir's Essence is looked at to be taken off.
        constexpr std::chrono::milliseconds WatchEvery{1000};

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // A repeat under way: the cast it makes costs nothing and brings no repeat.
        thread_local bool repeating = false;

        std::mutex mutex;
        // The record cast last, by Necromancer: the rune that is on while a copy stands.
        std::unordered_map<std::uint64_t, std::uint32_t> raised;
        // The Essence Reservoir has added, by Necromancer.
        std::unordered_map<std::uint64_t, double> added;
        std::unordered_map<std::uint64_t, std::uint64_t> watching;
        std::uint64_t stamps = 0;

        unsigned Copies(Player* player)
        {
            return Minions::Alive(player, Copy) + Minions::Alive(player, BoneCopy);
        }

        // The record of the Simulacrum cast while a copy of it stands, 0 when none.
        std::uint32_t Active(Player* player)
        {
            if (!player)
                return 0;
            std::uint32_t record = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = raised.find(player->GetGUID().GetRawValue());
                if (found != raised.end())
                    record = found->second;
            }
            return record && Copies(player) ? record : 0;
        }

        bool CursedForm(Player* player)
        {
            std::uint32_t const record = Active(player);
            return record && RuneAt(record) == Rune::CursedForm;
        }

        // Reservoir: the pool's maximum raised by the rune's share (0 takes it off). `prior` says a copy of the last
        // cast still stands, so its Essence is in the sheet's maximum.
        void Reservoir(Player* player, std::uint32_t spellId, bool on, bool prior)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            double value = 0.0;
            if (on)
            {
                double own = 0.0;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    own = prior ? added[guid] : 0.0;
                }
                auto const sheet = Stats::Get(guid);
                value =
                    EssenceAdded(sheet ? (*sheet)[Stat::MaxFury] - own : 0.0, Numbers::Num(spellId, "max_pool_pct"));
            }
            Buffs::Set(player, BaseId(Skill), Stat::MaxFury, Bucket::Flat, value);
            std::lock_guard<std::mutex> guard(mutex);
            added[guid] = value;
        }

        // While the copies stand Reservoir's Essence stays; a look a second takes it off when the last is gone.
        void Watch(Player* player, std::uint64_t stamp)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = watching.find(guid);
                if (found == watching.end() || found->second != stamp)
                    return;
            }
            if (!player->IsInWorld())
                return;
            if (Active(player))
            {
                player->m_Events.AddEventAtOffset([player, stamp] { Watch(player, stamp); }, WatchEvery);
                return;
            }
            Reservoir(player, 0, false, false);
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = watching.find(guid);
            if (found != watching.end() && found->second == stamp)
                watching.erase(found);
        }

        void StartWatch(Player* player)
        {
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                watching[player->GetGUID().GetRawValue()] = stamp = ++stamps;
            }
            player->m_Events.AddEventAtOffset([player, stamp] { Watch(player, stamp); }, WatchEvery);
        }

        // "Duplicate your Secondary skills": the cast is made again for each copy, by code, at the same enemy. It waits
        // for the next update so the cast that brought it is done.
        void Echo(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
        {
            auto const* row = Shells::FindAbility(spellId);
            unsigned const copies = Copies(player);
            if (!row || repeating || !copies || !IsSecondary(row->skill))
                return;
            ObjectGuid aim;
            if (NeedsTarget(row->skill))
            {
                Unit* target = targets.empty() ? player->GetSelectedUnit() : targets.front();
                if (!target)
                    return;
                aim = target->GetGUID();
            }
            player->m_Events.AddEventAtOffset(
                [player, skill = std::string(row->skill), aim, copies]
                {
                    repeating = true;
                    for (unsigned copy = 0; copy < copies; ++copy)
                        Combat::CastSkill(player, skill, aim ? ObjectAccessor::GetUnit(*player, aim) : nullptr);
                    repeating = false;
                },
                std::chrono::milliseconds(0));
        }
    } // namespace

    void Casting(Player* player, std::uint32_t spellId)
    {
        if (!player || !RowOf(spellId, Skill) || repeating)
            return;
        // "Cost: 25% Health".
        SpendLife(player, Tune("simulacrum_life_cost_pct"));
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player)
            return;
        if (!RowOf(spellId, Skill))
        {
            Echo(player, spellId, targets);
            return;
        }
        bool const prior = Copies(player) > 0;
        Rune const rune = RuneAt(spellId);
        Pets::Simulacrum(player, false);
        // "Now also creates a Simulacrum of Bone".
        if (rune == Rune::BloodAndBone)
            Pets::Simulacrum(player, true);
        {
            std::lock_guard<std::mutex> guard(mutex);
            raised[player->GetGUID().GetRawValue()] = spellId;
        }
        Reservoir(player, spellId, rune == Rune::Reservoir, prior);
        if (rune == Rune::Reservoir)
            StartWatch(player);
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!player || !row || !IsCurse(row->skill) || !CursedForm(player))
            return;
        // "your curse skills now apply all three curses": the other two, of the rune on the bar or the skill's own,
        // where the first fell.
        for (std::string_view other : OtherCurses(row->skill))
        {
            std::uint32_t const record = Slotted(player, other) ? Slotted(player, other) : BaseId(other);
            if (other == "Decrepify")
                Decrepify::Ground(player, record, center);
            else if (other == "Leech")
                Leech::Ground(player, record, center);
            else
                Frailty::Ground(player, record, center);
        }
    }

    double LifeCostShare(Player* player)
    {
        std::uint32_t const record = Active(player);
        return record ? LifeCostShare(RuneAt(record), Numbers::Num(record, "cost_reduction_pct")) : 1.0;
    }

    double Reduce(Unit* victim, double damage)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        std::uint32_t const record = Active(player);
        if (!record || RuneAt(record) != Rune::SelfSacrifice || !Fatal(damage, player->GetHealth()))
            return damage;
        // "If you would die with a Simulacrum active, instead the Simulacrum is destroyed and you are fully healed."
        Minions::Dismiss(player, Copy);
        Minions::Dismiss(player, BoneCopy);
        player->SetHealth(player->GetMaxHealth());
        return 0.0;
    }

    bool Repeating()
    {
        return repeating;
    }

    void RegisterScripts()
    {
        Curses::StandTogether(CursedForm);
    }
} // namespace DC::Combat::Necromancer::Simulacrum
