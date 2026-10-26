/*
 * World of DiabloCraft - the resource pulse: every class
 * resource the registry gives the module (paid_by module) regenerates and decays
 * here, a fine step at a time, instead of in the core's 2-second chunks.
 * dc_resource_pulse.h has the arithmetic and why.
 *
 * Every combat.resource_pulse_ms a player's class rows the module pays (read from
 * class_resources.csv through the registry, so no class is named) are paid the
 * class's regen_per_second, the regen auras on the slot, the flows the class's
 * sources handed over (Resources::Flow) and, for a row whose decay is the
 * slot's stock one, the core's own loss while out of combat with no
 * interrupt-regen aura - the core's rule, at the realm's loss rate - and, for a
 * timed one, the row's combat.csv rate once its wait out of combat has passed. The value
 * goes out with SetPower, so the client's power event fires whenever the whole
 * value moves, and the rate goes into the slot's two regeneration fields.
 *
 * The core's tick stays off the slot while the class's mask record is on the
 * player (generate_spells.py REGENERATION_MASK; Player::Regenerate returns at
 * SPELL_AURA_PREVENT_REGENERATE_POWER, Player.cpp:1911). The pulse keeps it on.
 * Where the record is missing (a world without its migration) the core keeps
 * its own tick and the pulse pays only the flows, which no core path pays.
 */

#include "dc_resource_pulse.h"

#include "../classes/dc_classes.h"
#include "../classes/dc_resources.h"
#include "../combat/dc_spell_shells.h"
#include "../common/dc_tunables.h"
#include "dc_stat_readers.h"
#include "dc_stats.h"

#include "Player.h"
#include "SpellAuraEffects.h"
#include "ScriptMgr.h"
#include "SpellMgr.h"
#include "World.h"

#include <map>
#include <mutex>
#include <string>
#include <unordered_map>

namespace DC::Resources
{
    namespace
    {
        struct Owed
        {
            double fraction = 0;
            std::vector<Stats::Pulse::Flow> flows;
        };
        struct State
        {
            double clockMs = 0;
            double outOfCombatMs = 0; // since the player last left combat, for a timed decay
            std::map<Resource const*, Owed> slots;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;
    } // namespace

    void Flow(Player* player, Resource const& r, double points, std::uint32_t overMs)
    {
        if (!player || points <= 0 || Classes::ClassIdOf(player) != r.classId || !Displayed(player, r))
            return;
        std::lock_guard<std::mutex> guard(mutex);
        states[player->GetGUID().GetRawValue()].slots[&r].flows.push_back({ToUnits(r, points), double(overMs)});
    }

    namespace
    {
        // The core's terms for the slot (Player::Regenerate, Player.cpp:1932-1978).
        Stats::Pulse::Rate RateOf(Player const* player, Resource const& r, double outOfCombatMs)
        {
            Powers const slot = Slot(r);
            Stats::Pulse::Inputs in;
            in.row = &r;
            in.auraPerFive = player->GetTotalAuraModifierByMiscValue(SPELL_AURA_MOD_POWER_REGEN, slot);
            in.auraMultiplier = player->GetTotalAuraMultiplierByMiscValue(SPELL_AURA_MOD_POWER_REGEN_PERCENT, slot);
            std::uint32_t const ownRate = Combat::Shells::EnergyRateFor(r.classId);
            in.regenAuraMultiplier = player->GetTotalAuraMultiplier(
                SPELL_AURA_MOD_POWER_REGEN_PERCENT, [slot, ownRate](AuraEffect const* effect)
                { return effect->GetMiscValue() == slot && effect->GetId() != ownRate; });
            in.inCombat = player->IsInCombat();
            in.interrupted = player->HasInterruptRegenAura();
            // The realm's loss rate for the two slots the core decays; no other slot loses by itself.
            if (slot == POWER_RAGE || slot == POWER_RUNIC_POWER)
                in.realmLossRate = sWorld->getRate(slot == POWER_RAGE ? RATE_POWER_RAGE_LOSS : RATE_POWER_RUNICPOWER_LOSS);
            // Resource regeneration from gear (spiritregen, manaregen): the sheet's points a second, for the row whose resource it is.
            if (auto const sheet = Stats::Get(player->GetGUID().GetRawValue()))
                in.sheetPerSecond = Stats::Readers::RegenPerSecond(*sheet, r.key);
            if (r.decay == Data::Decay::Timed)
            {
                std::string const key = r.key;
                in.timedPerSecond = Tunables::Get("combat", key + "_decay_per_second");
                in.timedWaitMs = Tunables::Get("combat", key + "_decay_wait_seconds") * 1000.0;
                in.outOfCombatMs = outOfCombatMs;
            }
            return Stats::Pulse::RateFor(in);
        }

        // The class's mask record on the player, put back when it is not; false
        // when the world has no such record.
        bool Masked(Player* player, std::uint32_t classId)
        {
            std::uint32_t const mask = Combat::Shells::RegenerationMaskFor(classId);
            if (!mask || !sSpellMgr->GetSpellInfo(mask))
                return false;
            if (!player->HasAura(mask))
                player->AddAura(mask, player);
            return player->HasAura(mask);
        }

        void Pay(Player* player, uint32 diff)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            double const every = Tunables::Get("combat", "resource_pulse_ms");
            double elapsed;
            double outOfCombatMs;
            {
                std::lock_guard<std::mutex> guard(mutex);
                State& state = states[guid];
                state.clockMs += diff;
                if (state.clockMs < every)
                    return;
                elapsed = state.clockMs;
                state.clockMs = 0;
                state.outOfCombatMs = Stats::Pulse::OutOfCombatAfter(state.outOfCombatMs, player->IsInCombat(), elapsed);
                outOfCombatMs = state.outOfCombatMs;
            }
            std::uint32_t const classId = Classes::ClassIdOf(player);
            bool const masked = Masked(player, classId);
            for (Resource const& r : Data::Rows)
            {
                if (r.classId != classId || !Stats::Pulse::Pulsed(r))
                    continue;
                double units = 0;
                if (masked)
                {
                    Stats::Pulse::Rate const rate = RateOf(player, r, outOfCombatMs);
                    units = Stats::Pulse::Units(rate, elapsed);
                    float const field = Stats::Pulse::RegenField(r.power, Stats::Pulse::Units(rate, 1000.0));
                    player->SetStatFloatValue(UNIT_FIELD_POWER_REGEN_FLAT_MODIFIER + r.power, field);
                    player->SetStatFloatValue(UNIT_FIELD_POWER_REGEN_INTERRUPTED_FLAT_MODIFIER + r.power, field);
                }
                std::uint32_t next;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    Owed& owed = states[guid].slots[&r];
                    units += Stats::Pulse::Drain(owed.flows, elapsed);
                    next = Stats::Pulse::Step(Units(player, r), MaxUnits(player, r), units, owed.fraction);
                }
                player->SetPower(Slot(r), next);
            }
        }

        class ResourcePulse final : public PlayerScript
        {
        public:
            ResourcePulse()
                : PlayerScript("dc_resource_pulse", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                // The core regenerates only the living (Player::Update, PlayerUpdates.cpp:317).
                if (player->IsAlive() && Classes::Playable(player))
                    Pay(player, diff);
            }

            void OnPlayerLogout(Player* player) override
            {
                ForgetCarry(player);
                std::lock_guard<std::mutex> guard(mutex);
                states.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace
} // namespace DC::Resources

namespace DC::Stats
{
    void RegisterResourcePulseScripts()
    {
        new Resources::ResourcePulse();
    }
} // namespace DC::Stats
