/*
 * World of DiabloCraft - the Shaman's dispatch (dc_shaman.h) and the upkeep that keeps the Overcharge and Attunement
 * buffs on the bar.
 */

#include "dc_shaman.h"
#include "dc_shaman_common.h"
#include "dc_shaman_earthbind_totem.h"
#include "dc_shaman_elemental_shield.h"
#include "dc_shaman_elemental_weapon.h"
#include "dc_shaman_ghost_wolf.h"
#include "dc_shaman_purge.h"
#include "dc_shaman_spirit_link.h"
#include "dc_shaman_healing_stream_totem.h"
#include "dc_shaman_searing_totem.h"
#include "dc_shaman_spirit_wolves.h"
#include "dc_shaman_thunderstorm.h"
#include "dc_shaman_totems.h"
#include "ScriptMgr.h"
#include "dc_shaman_chain_lightning.h"
#include "dc_shaman_earth_elemental.h"
#include "dc_shaman_earthquake.h"
#include "dc_shaman_ascendance.h"
#include "dc_shaman_bloodlust.h"
#include "dc_shaman_damage_mark.h"
#include "dc_shaman_elemental_blast.h"
#include "dc_shaman_fire_elemental.h"
#include "dc_shaman_elemental_lash.h"
#include "dc_shaman_flame_shock.h"
#include "dc_shaman_lava_burst.h"
#include "dc_shaman_frost_lance.h"
#include "dc_shaman_lightning_bolt.h"
#include "dc_shaman_passives.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::Shaman
{
    void Launched(Player* player, std::uint32_t spellId, bool triggered)
    {
        Passive::Launched(player, spellId, triggered);
    }

    bool FreeCast()
    {
        return Passive::FreeCasting();
    }

    bool FreeCast(bool on)
    {
        return Passive::FreeCasting(on);
    }

    void Casting(Player* player, std::uint32_t spellId)
    {
        // A free cast of Lightning Overload's is no cast the Shaman makes: it spends no Overcharge, moves no Attunement and counts for nothing.
        if (!IsShaman(player) || Passive::FreeCasting())
            return;
        // The Overcharge a Secondary spends is read first: the same cast moves the Attunement.
        Overcharge::Cast(player, spellId);
        Attunement::Cast(player, spellId);
        // The Defensive skills that put something on the Shaman as they begin.
        ElementalShield::Casting(player, spellId);
        Ascendance::Casting(player, spellId);
        Passive::Casting(player, spellId);
        GhostWolf::Casting(player, spellId);
        Totems::Cast(player, spellId);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        if (!IsShaman(player))
            return;
        LightningBolt::Landed(player, target, spellId, critical);
        FlameShock::Landed(player, target, spellId);
        ElementalLash::Landed(player, target, spellId);
        FrostLance::Landed(player, target, spellId);
        ChainLightning::Landed(player, target, spellId);
        Passive::Landed(player, target, spellId, critical);
        LavaBurst::Landed(player, target, spellId);
        ElementalBlast::Landed(player, target, spellId);
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        Overcharge::Multipliers(player, spellId, out);
        Attunement::Multipliers(player, out);
        if (IsShaman(player))
        {
            LightningBolt::Multipliers(player, target, spellId, out);
            FlameShock::Multipliers(player, target, spellId, out);
            FrostLance::Multipliers(player, spellId, out);
            LavaBurst::Multipliers(player, target, spellId, out);
            Earthquake::Multipliers(player, target, spellId, out);
            ElementalBlast::Multipliers(player, spellId, out);
            Ascendance::Multipliers(player, spellId, out);
            Passive::Multipliers(player, target, spellId, out);
            DamageMark::Multipliers(player, target, out);
            Searing::Multipliers(player, target, spellId, out);
            ElementalWeapon::Multipliers(player, spellId, out);
            Earthbind::Multipliers(player, target, spellId, out);
        }
    }

    std::optional<double> PrimaryBasePct(std::uint32_t spellId)
    {
        if (auto lightningBolt = LightningBolt::BasePct(spellId))
            return lightningBolt;
        if (auto flameShock = FlameShock::BasePct(spellId))
            return flameShock;
        if (auto elementalLash = ElementalLash::BasePct(spellId))
            return elementalLash;
        if (auto frostLance = FrostLance::BasePct(spellId))
            return frostLance;
        if (auto chainLightning = ChainLightning::BasePct(spellId))
            return chainLightning;
        if (auto lavaBurst = LavaBurst::BasePct(spellId))
            return lavaBurst;
        return ElementalBlast::BasePct(spellId);
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (IsShaman(player))
        {
            Earthquake::Ground(player, spellId, center);
            EarthElemental::Ground(player, spellId, center);
        }
    }

    char const* Element(Player* player, std::uint32_t spellId)
    {
        if (!IsShaman(player))
            return nullptr;
        if (char const* element = FlameShock::Element(player, spellId))
            return element;
        return ElementalBlast::Element(player, spellId);
    }

    void Fatal(Player* player, std::uint32_t& damage)
    {
        HealingStream::Fatal(player, damage);
    }

    double TakenFactor(Unit* victim)
    {
        return Searing::TakenFactor(victim);
    }

    unsigned OverchargeStacks(Player* player)
    {
        return Overcharge::Stacks(player);
    }

    // ---- Each skill's file answers for its own records.

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (auto const ghostWolf = GhostWolf::BasePct(spellId))
            return ghostWolf;
        if (auto const purge = Purge::BasePct(spellId))
            return purge;
        if (auto const link = SpiritLink::BasePct(spellId))
            return link;
        if (auto const weapon = ElementalWeapon::BasePct(spellId))
            return weapon;
        if (auto const wolves = SpiritWolves::BasePct(spellId))
            return wolves;
        return Thunderstorm::BasePct(spellId);
    }

    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        Purge::Aim(player, spellId, targets);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        LavaBurst::Cast(player, spellId);
        ElementalBlast::Cast(player, spellId);
        Bloodlust::Cast(player, spellId, targets);
        FireElemental::Cast(player, spellId, targets);
        Ascendance::Cast(player, spellId, targets);
        Thunderstorm::Cast(player, spellId, targets);
        GhostWolf::Cast(player, spellId);
        Purge::Cast(player, spellId, targets);
        SpiritLink::Cast(player, spellId, targets);
        ElementalWeapon::Cast(player, spellId);
        SpiritWolves::Cast(player, spellId, targets);
    }

    double MissChance(Unit const* attacker)
    {
        return Thunderstorm::MissChance(attacker);
    }

    double Reduce(Unit* victim, Unit* attacker, double damage)
    {
        return Passive::Reduce(victim, ElementalShield::Reduce(victim, attacker, damage));
    }

    void Dealt(Player* player, Unit* target, std::uint32_t spellId, unsigned school, bool critical, double damage)
    {
        SpiritLink::Dealt(player, target, spellId, school, critical, damage);
    }

    void Damaged(Unit* attacker, Unit* victim, std::uint32_t damage)
    {
        ElementalShield::Damaged(attacker, victim, damage);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        ElementalShield::Landed(player, spellId);
        ElementalWeapon::Landed(player, target, spellId);
    }

    namespace
    {
        constexpr std::uint32_t UpkeepMs = 250;

        class UpkeepScript final : public PlayerScript
        {
        public:
            UpkeepScript()
                : PlayerScript("dc_shaman_upkeep", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsShaman(player))
                    return;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    std::uint32_t& waited = clock[player->GetGUID().GetRawValue()];
                    waited += diff;
                    if (waited < UpkeepMs)
                        return;
                    waited = 0;
                }
                Overcharge::Upkeep(player);
                Attunement::Upkeep(player);
                Earthbind::Upkeep(player);
                HealingStream::Upkeep(player);
                ElementalShield::Upkeep(player);
                GhostWolf::Upkeep(player);
                SpiritLink::Upkeep(player);
                ElementalWeapon::Upkeep(player);
                Passive::Upkeep(player, UpkeepMs);
            }

            void OnPlayerLogout(Player* player) override
            {
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    clock.erase(player->GetGUID().GetRawValue());
                }
                Overcharge::Forget(player);
                Attunement::Forget(player);
                ElementalShield::Forget(player);
                GhostWolf::Forget(player);
                Purge::Forget(player);
                SpiritLink::Forget(player);
                ElementalWeapon::Forget(player);
                Searing::Forget(player);
                Earthbind::Forget(player);
                HealingStream::Forget(player);
                Passive::Forget(player);
            }

        private:
            std::mutex mutex;
            std::unordered_map<std::uint64_t, std::uint32_t> clock;
        };
    } // namespace

    void RegisterScripts()
    {
        new UpkeepScript();
        Totems::RegisterScripts();
        Bloodlust::RegisterScripts();
        FireElemental::RegisterScripts();
        EarthElemental::RegisterScripts();
    }
} // namespace DC::Combat::Shaman
