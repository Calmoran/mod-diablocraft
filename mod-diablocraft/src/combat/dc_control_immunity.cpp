#include "dc_control_immunity.h"

#include "Player.h"
#include "Unit.h"
#include "SpellDefines.h"

namespace DC::Combat::ControlImmunity
{
    namespace
    {
        // The control-impairing mechanics: the list Invigorating Gemstone's immunity, Temple of Protection and Limited Immunity give, and
        // Bane of the Trapped looks for.
        constexpr std::uint64_t ControlImpairing =
            (1ull << MECHANIC_CHARM) | (1ull << MECHANIC_DISORIENTED) | (1ull << MECHANIC_FEAR) | (1ull << MECHANIC_ROOT) |
            (1ull << MECHANIC_SILENCE) | (1ull << MECHANIC_SLEEP) | (1ull << MECHANIC_SNARE) | (1ull << MECHANIC_STUN) |
            (1ull << MECHANIC_FREEZE) | (1ull << MECHANIC_KNOCKOUT) | (1ull << MECHANIC_POLYMORPH) | (1ull << MECHANIC_HORROR) |
            (1ull << MECHANIC_DAZE) | (1ull << MECHANIC_SAPPED);
    } // namespace

    void Strip(Player* player)
    {
        if (player)
            player->RemoveAurasWithMechanic(ControlImpairing);
    }

    void Set(Player* player, std::uint32_t key, bool on)
    {
        if (!player)
            return;
        for (unsigned mechanic = 1; mechanic < MAX_MECHANIC; ++mechanic)
            if (ControlImpairing & (1ull << mechanic))
                player->ApplySpellImmune(key, IMMUNITY_MECHANIC, mechanic, on);
        for (AuraType aura : {SPELL_AURA_MOD_STUN, SPELL_AURA_MOD_ROOT, SPELL_AURA_MOD_FEAR, SPELL_AURA_MOD_CONFUSE,
                              SPELL_AURA_MOD_DECREASE_SPEED})
            player->ApplySpellImmune(key, IMMUNITY_STATE, aura, on);
        if (on)
            Strip(player);
    }

    void SetFearCharmStun(Player* player, std::uint32_t key, bool on)
    {
        if (player == nullptr)
            return;
        constexpr std::uint64_t Mechanics = (1ull << MECHANIC_CHARM) | (1ull << MECHANIC_FEAR) | (1ull << MECHANIC_STUN);
        for (unsigned kind : {unsigned(MECHANIC_CHARM), unsigned(MECHANIC_FEAR), unsigned(MECHANIC_STUN)})
            player->ApplySpellImmune(key, IMMUNITY_MECHANIC, kind, on);
        for (AuraType state : {SPELL_AURA_MOD_STUN, SPELL_AURA_MOD_FEAR, SPELL_AURA_MOD_CHARM})
            player->ApplySpellImmune(key, IMMUNITY_STATE, state, on);
        if (on)
            player->RemoveAurasWithMechanic(Mechanics);
    }

    bool Impaired(Unit const* unit)
    {
        return unit && unit->HasAuraWithMechanic(ControlImpairing);
    }

    bool ImpairedBesidesSlow(Unit const* unit)
    {
        return unit && unit->HasAuraWithMechanic(ControlImpairing & ~(1ull << MECHANIC_SNARE));
    }
} // namespace DC::Combat::ControlImmunity
