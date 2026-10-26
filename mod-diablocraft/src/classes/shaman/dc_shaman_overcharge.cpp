/*
 * World of DiabloCraft - the Shaman's Overcharge: the Maelstrom that did not fit is banked as stacks, the buff bar
 * shows them, and the next Secondary skill spends every stack for damage (dc_shaman_overcharge.h has the rule).
 */

#include "dc_shaman_common.h"
#include "dc_shaman_overcharge.h"
#include "../../combat/dc_passives.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::Shaman::Overcharge
{
    namespace
    {
        // What a Secondary cast took: the skill it was and the stacks it spent. The hits of that cast, which land after
        // the cast began, read it; the next Secondary replaces it.
        struct Carried
        {
            std::uint32_t skill = 0;
            unsigned stacks = 0;
        };
        struct State
        {
            Bank bank;
            Carried carried;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        // Five stacks, or the Storm Surge passive's maximum for a Shaman who has it.
        unsigned CapOf(Player* player)
        {
            std::uint32_t const surge = PassiveId("Storm Surge");
            unsigned const raised = surge ? unsigned(Numbers::Num(surge, "max_count")) : 0;
            return Cap(unsigned(Tunable("overcharge_base_max_stacks")), Passives::Has(player, "Storm Surge"), raised);
        }

        std::uint64_t Lasts()
        {
            return std::uint64_t(Tunable("overcharge_seconds") * 1000.0);
        }

        void Show(Player* player, unsigned stacks, double seconds)
        {
            BuffValues::Show(player, BuffId("Overcharge - buff"), stacks, seconds);
        }
    } // namespace

    void Overflow(Player* player, double overflow)
    {
        if (!IsShaman(player) || overflow <= 0)
            return;
        unsigned const cap = CapOf(player);
        unsigned stacks;
        double seconds;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Bank& bank = states[Key(player)].bank;
            stacks = Add(bank, Now(), overflow, Tunable("overcharge_points_per_stack"), cap, Lasts());
            seconds = SecondsLeft(bank, Now());
        }
        Show(player, stacks, seconds);
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!IsShaman(player) || !Shells::FindAbility(spellId) || Classes::CategoryOf(spellId) != "Secondary")
            return;
        unsigned const cap = CapOf(player);
        {
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[Key(player)];
            state.carried = {Classes::SkillIdOf(spellId), Take(state.bank, Now(), cap)};
        }
        Show(player, 0, 0);
    }

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!IsShaman(player))
            return;
        unsigned stacks = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(Key(player));
            if (found != states.end() && found->second.carried.stacks &&
                found->second.carried.skill == Classes::SkillIdOf(spellId))
                stacks = found->second.carried.stacks;
        }
        if (stacks)
            AddFactor(out, "Overcharge", DamagePct(stacks, Tunable("overcharge_damage_per_stack_pct")));
    }

    unsigned Stacks(Player* player)
    {
        if (!IsShaman(player))
            return 0;
        unsigned const cap = CapOf(player);
        std::lock_guard<std::mutex> guard(mutex);
        auto found = states.find(Key(player));
        return found == states.end() ? 0 : Held(found->second.bank, Now(), cap);
    }

    void Upkeep(Player* player)
    {
        if (!IsShaman(player))
            return;
        unsigned const cap = CapOf(player);
        unsigned stacks = 0;
        double seconds = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = states.find(Key(player));
            if (found != states.end())
            {
                stacks = Held(found->second.bank, Now(), cap);
                seconds = SecondsLeft(found->second.bank, Now());
            }
        }
        Show(player, stacks, seconds);
    }

    void Forget(Player* player)
    {
        std::lock_guard<std::mutex> guard(mutex);
        states.erase(Key(player));
    }
} // namespace DC::Combat::Shaman::Overcharge
