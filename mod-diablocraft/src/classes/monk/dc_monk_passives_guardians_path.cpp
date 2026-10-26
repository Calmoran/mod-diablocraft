/*
 * Six Monk passives: The Guardian's Path, Sixth Sense, Determination, Relentless Assault, Beacon of Ytar,
 * Alacrity. The numbers are monk_passive_values.csv (skill = the passive's name);
 * Power/Monk_Passive_TheGuardiansPath.pow, Monk_Passive_SixthSense.pow, p1_Monk_Passive_RelentlessAssault.pow and
 * Monk_Passive_BeaconOfYtar.pow agree with them (Determination and Alacrity have no power file).
 *
 * A passive is on when it sits in one of the Monk's passive slots (Passives::Has). Two of them are stat contributions
 * (Sixth Sense, Beacon of Ytar), kept by a small update script that puts them on the sheet when the slots change; the
 * other four are read where the hit or the incoming attack is worked out.
 */

#include "dc_monk_common.h"
#include "dc_monk_passives_guardians_path.h"
#include "dc_monk_passives_guardians_path_cast.h"
#include "../dc_resources.h"
#include "../../combat/dc_passives.h"
#include "../../common/dc_numeric_data.h"
#include "../../stats/dc_stats.h"
#include "Item.h"
#include "ScriptMgr.h"
#include "SpellAuraDefines.h"

namespace DC::Combat::Monk::Passives242
{
    namespace
    {
        // How often the update script looks at the slots and counts the enemies Determination counts (ms).
        constexpr std::uint32_t Period = 250;

        // Stock "Dizzy" (9992): one MOD_CONFUSE effect, the blind Blinding Flash puts on an ordinary enemy
        // (dc_monk_blinding_flash.cpp); Relentless Assault counts an enemy wearing it as blind.
        constexpr std::uint32_t Dizzy = 9992;

        std::uint32_t Id(std::string_view name)
        {
            for (auto const& passive : Shells::Passives)
                if (name == passive.name)
                    return passive.id;
            return 0;
        }

        bool IsMonk(Player const* player)
        {
            return player && Classes::ClassIdOf(player) == Resources::Spirit.classId;
        }

        bool On(Player* player, char const* name)
        {
            return IsMonk(player) && Passives::Has(player, name);
        }

        double Num(char const* name, char const* token)
        {
            return Numbers::Num(Id(name), token);
        }

        bool TwoHanded(Player* player)
        {
            Item* main = player->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND);
            return main && main->GetTemplate()->InventoryType == INVTYPE_2HWEAPON;
        }

        // Per Monk: the enemies Determination counted at the last look, and the slots the sheet was last built for.
        struct State
        {
            unsigned enemies = 0;
            std::uint64_t signature = 0;
            std::uint32_t clock = 0;
            bool dirty = true;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        // Sixth Sense's reduction on every element but Physical and Beacon of Ytar's cooldown reduction, taken off and
        // put back on the sheet. The cooldown reduction is also a core aura, so the gear modifier is rebuilt after it.
        void Refresh(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint32_t const sixth = Id("Sixth Sense"), beacon = Id("Beacon of Ytar");
            Stats::RemoveContribution(guid, Source::Passives, Stat::ElementReduction, sixth);
            Stats::RemoveContribution(guid, Source::Passives, Stat::CooldownReduction, beacon);
            if (On(player, "Sixth Sense"))
                for (unsigned e = 0; e < ElementCount; ++e)
                    if (SixthSenseReduces(e == Index(Element::Physical)))
                        Stats::AddContribution(guid, {Source::Passives, Stat::ElementReduction, sixth,
                                                      Numbers::Num(sixth, "damage_reduction_pct"), Bucket::Flat,
                                                      static_cast<Element>(e)});
            if (On(player, "Beacon of Ytar"))
                Stats::AddContribution(guid, {Source::Passives, Stat::CooldownReduction, beacon,
                                              CooldownContribution(Numbers::Num(beacon, "cooldown_reduction_pct")),
                                              Bucket::Flat});
            Stats::Recompute(player);
            Passives::RefreshModifiers(player);
        }

        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_monk_passives_guardians_path",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsMonk(player))
                    return;
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    State& state = states[guid];
                    state.clock += diff;
                    if (state.clock < Period)
                        return;
                    state.clock = 0;
                }
                // Which of the two sheet passives are slotted; read outside the lock (Passives::Has takes its own).
                std::uint64_t const signature =
                    (On(player, "Sixth Sense") ? 1u : 0u) | (On(player, "Beacon of Ytar") ? 2u : 0u);
                bool refresh = false;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    State& state = states[guid];
                    refresh = state.dirty || state.signature != signature;
                    state.signature = signature;
                    state.dirty = false;
                }
                if (refresh)
                    Refresh(player);
                unsigned enemies = 0;
                if (player->IsAlive() && On(player, "Determination"))
                    enemies = unsigned(Combat::Enemies(player, Id("Determination"), player->GetPosition(),
                                                       Num("Determination", "radius_yards"))
                                           .size());
                std::lock_guard<std::mutex> guard(mutex);
                states[guid].enemies = enemies;
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                states.erase(player->GetGUID().GetRawValue());
            }

            void OnPlayerMapChanged(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                states[player->GetGUID().GetRawValue()].dirty = true;
            }
        };
    } // namespace

    double Dodge(Unit const* unit)
    {
        if (!unit || !unit->IsPlayer())
            return 0;
        Player* player = const_cast<Unit*>(unit)->ToPlayer();
        if (!On(player, "The Guardian's Path"))
            return 0;
        return GuardianDodge(Combat::DualWielding(player), Num("The Guardian's Path", "dodge_pct"));
    }

    double GenerationFactor(Player* player)
    {
        if (!On(player, "The Guardian's Path"))
            return 1.0;
        return Passives242::GenerationFactor(TwoHanded(player), Num("The Guardian's Path", "regen_pct"));
    }

    // Determination and Relentless Assault are D3 damage multipliers of their own, not part of the additive pool
    // (separate multipliers, as D3's passives are): each puts one named factor on the hit. `target` is the hit's victim.
    void Multipliers(Player* player, Unit* target, Factors& out)
    {
        if (!IsMonk(player))
            return;
        if (On(player, "Determination"))
        {
            unsigned enemies = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = states.find(player->GetGUID().GetRawValue());
                enemies = found == states.end() ? 0 : found->second.enemies;
            }
            if (double const pct = Determination(enemies, Num("Determination", "damage_bonus_pct"),
                                                 Num("Determination", "max_bonus_pct"));
                pct > 0)
                AddFactor(out, "Determination", pct);
        }
        if (target && On(player, "Relentless Assault"))
        {
            // Blind (Blinding Flash's Dizzy, or any confuse aura or disorientation), Frozen (the freeze mechanic) and
            // Stunned (a stun aura or the stunned state).
            bool const blind = target->HasAura(Dizzy) || target->HasAuraType(SPELL_AURA_MOD_CONFUSE) ||
                               target->HasAuraWithMechanic(1ull << MECHANIC_DISORIENTED);
            bool const frozen = target->HasAuraWithMechanic(1ull << MECHANIC_FREEZE);
            bool const stunned = target->HasUnitState(UNIT_STATE_STUNNED) || target->HasAuraType(SPELL_AURA_MOD_STUN);
            if (double const pct =
                    RelentlessAssault(blind, frozen, stunned, Num("Relentless Assault", "damage_bonus_pct"));
                pct > 0)
                AddFactor(out, "Relentless Assault", pct);
        }
    }
} // namespace DC::Combat::Monk::Passives242

namespace DC::Combat::Monk
{
    double AttackSpeed(Player* player, std::uint32_t spellId, double base)
    {
        if (!player || base <= 0 || !Passives242::On(player, "Alacrity"))
            return base;
        // "Spirit Generators": the skills whose sheet says they generate Spirit (the same row Monk::Connected pays).
        auto const generated = Numbers::Get(spellId, "generated_resource");
        if (!generated || *generated <= 0)
            return base;
        auto const sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        if (!sheet)
            return base;
        return Passives242::AlacrityAps(base, (*sheet)[Stat::AttackSpeed],
                                        Passives242::Num("Alacrity", "attack_speed_pct"),
                                        DC::NumericData::Rule("attack_speed_cap"));
    }

    void RegisterPassiveScripts()
    {
        new Passives242::Update();
    }
} // namespace DC::Combat::Monk
