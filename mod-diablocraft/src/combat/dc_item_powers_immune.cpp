#include "dc_item_powers_internal.h"

// The item powers' `immune` kind: the controls the wearer cannot be put under.

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // The key the item powers' immunities are kept under on the unit: not 0, which the core keeps once per type and Invigorating
        // Gemstone uses (dc_gem_powers.cpp SetControlImmunity), so turning one off never takes the other's away.
        constexpr std::uint32_t ImmuneKey = 1;

        // Torment's freeze on a player: the Frozen elite's hold, dc_rift_elites.cpp FREEZE_HOLD (stock "Ice Blast", one MOD_STUN effect,
        // mechanic STUN), so the Freeze mechanic alone does not refuse it, and Stun would refuse every stun. Refused by its id
        // (Unit::IsImmunedToSpell checks IMMUNITY_ID first); test_item_power_math holds the two numbers equal.
        constexpr std::uint32_t FreezeHold = 15878;
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // One control the wearer of an `immune` row cannot be put under, through the core's spell immunity (Ice Climbers): `freeze` is the
        // Freeze mechanic and Torment's freeze hold, `root` (D3's Immobilize) the Root mechanic and any root aura. Going on removes such an
        // aura already on the player.
        void Immunize(Player* player, std::string const& control, bool on)
        {
            if (control == "ground_effects") // World's mark, set on every refresh below
                return;
            Mechanics const mechanic = control == "freeze" ? MECHANIC_FREEZE : MECHANIC_ROOT;
            player->ApplySpellImmune(ImmuneKey, IMMUNITY_MECHANIC, mechanic, on);
            if (control == "freeze")
                player->ApplySpellImmune(ImmuneKey, IMMUNITY_ID, FreezeHold, on);
            else
                player->ApplySpellImmune(ImmuneKey, IMMUNITY_STATE, SPELL_AURA_MOD_ROOT, on);
            if (!on)
                return;
            player->RemoveAurasWithMechanic(1 << mechanic);
            if (control == "freeze")
                player->RemoveAurasDueToSpell(FreezeHold);
            else
                player->RemoveAurasByType(SPELL_AURA_MOD_ROOT);
        }

        // Puts on or takes off the immunities whose `immune` rows changed (Refresh, after the worn items or the set counts did).
        void Immunize(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::set<std::string> now, before;
            {
                std::lock_guard<std::mutex> lock(mutex);
                now = ItemPower::Immunities(Data().rows, CountsOf(guid), SituationOf(guid));
                before = immune[guid];
                immune[guid] = now;
            }
            for (std::string const& control : before)
                if (!now.count(control))
                    Immunize(player, control, false);
            for (std::string const& control : now)
                if (!before.count(control))
                    Immunize(player, control, true);
            // Blackthorne's Battlegear 4-piece: World's N-BLACKTHORNE mark, put on or taken off on every refresh
            // (docs/contracts/legendary-world-pieces.md), so a mark left from before a logout is cleared by the next login's refresh.
            DC::Rifts::SetGroundEffectImmune(player, now.count("ground_effects") > 0);
        }
    } // namespace Detail
} // namespace DC::Combat
