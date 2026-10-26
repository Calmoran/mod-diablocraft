/*
 * Purge and its five runes. The skill is the engine's single-target cast (a record and the sheet's numbers) that hits
 * one enemy; here: the empowered states it takes off an elite before the hit lands (Rifts::PurgeEmpowered), the
 * Maelstrom each removal pays, and each rune's part (Wind Shear's interrupt and stun, Greater Purge's weakened elite,
 * Cleanse Spirit's cleansed Shaman, Consuming Purge's burn, Earthen Purge's cone, which is the cast's targets).
 */

#include "dc_shaman_purge.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_control_immunity.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../rifts/dc_rifts.h"
#include "Creature.h"
#include "SpellAuraDefines.h"

#include <algorithm>
#include <mutex>
#include <set>
#include <unordered_map>

namespace DC::Combat::Shaman::Purge
{
    namespace
    {
        constexpr std::string_view Skill = "Purge";

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        bool IsBoss(Unit const* enemy)
        {
            Creature const* creature = enemy ? enemy->ToCreature() : nullptr;
            return creature && (creature->isWorldBoss() || creature->IsDungeonBoss() ||
                                DC::Rifts::IsGuardianEntry(creature->GetEntry()));
        }

        // The enemies of this cast that lost an empowered state, from the aim to the landing (Consuming Purge's burn).
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::set<std::uint64_t>> purged;

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        auto const* row = RowOf(spellId);
        // Consuming Purge's `damage_pct` is its burn's, and Greater Purge's `duration_seconds` would make the loader wait on a damage that never
        // comes: both rune records keep the skill's hit.
        if (row && ClaimsHit(RuneOf(row->rune)))
            return Numbers::Num(BaseId(), "damage_pct");
        return std::nullopt;
    }

    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        auto const* row = RowOf(spellId);
        if (!player || !row)
            return;
        Rune const rune = RuneOf(row->rune);
        if (rune == Rune::CleanseSpirit)
        {
            // "Also removes all control effects and damage-over-time effects from you."
            ControlImmunity::Strip(player);
            for (AuraType type :
                 {SPELL_AURA_PERIODIC_DAMAGE, SPELL_AURA_PERIODIC_DAMAGE_PERCENT, SPELL_AURA_PERIODIC_LEECH})
                player->RemoveAurasByType(type);
        }
        // A stun is stretched by the worn powers that lengthen stuns, as at every other class's stun site.
        double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
        unsigned removedAll = 0;
        std::set<std::uint64_t> burned;
        for (Unit* enemy : targets)
        {
            if (!enemy->IsAlive())
                continue;
            unsigned const removed = DC::Rifts::PurgeEmpowered(enemy->ToCreature());
            removedAll += removed;
            Effect const effect = EffectOf(rune, removed, Shaman::IsElite(enemy), IsBoss(enemy));
            if (effect.interrupt)
                enemy->InterruptNonMeleeSpells(false);
            if (effect.stun)
                Shaman::Stun(player, enemy, stun);
            if (effect.weaken)
                EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"),
                                     Numbers::Num(spellId, "duration_seconds"));
            if (effect.burn)
                burned.insert(enemy->GetGUID().GetRawValue());
        }
        // "Removing an effect generates {gain_resource} Maelstrom."
        Gain(player, spellId, Maelstrom(removedAll, Numbers::Num(spellId, "gain_resource")));
        std::lock_guard<std::mutex> guard(mutex);
        purged[Key(player)] = std::move(burned);
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        auto const* row = RowOf(spellId);
        if (!player || !row)
            return;
        std::set<std::uint64_t> burned;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = purged.find(Key(player));
            if (found == purged.end())
                return;
            burned = std::move(found->second);
            purged.erase(found);
        }
        // Consuming Purge: "If an effect is removed, the target burns for {damage_pct} weapon damage as Fire over
        // {dot_duration_seconds} seconds."
        for (Unit* enemy : targets)
            if (enemy->IsAlive() && burned.count(enemy->GetGUID().GetRawValue()))
                PeriodicStrike::Start(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"),
                                      Numbers::Num(spellId, "dot_duration_seconds"),
                                      Tunable("purge_burn_tick_seconds"));
    }

    void Forget(Player* player)
    {
        std::lock_guard<std::mutex> guard(mutex);
        purged.erase(Key(player));
    }
} // namespace DC::Combat::Shaman::Purge
