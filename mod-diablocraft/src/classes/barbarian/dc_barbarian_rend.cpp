#include "dc_barbarian_rend.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_exact_damage.h"
#include "../../combat/dc_life_commands.h"
#include "../../combat/dc_item_power_math.h"
#include "../../combat/dc_combat.h"
#include "Log.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellScript.h"

namespace DC::Combat::Abilities::Rend
{
    using namespace Shared;

namespace
    {
        // Separate unlearned auras keep the visible bleed and its lifetime in the core
        // aura engine. Their PERIODIC_DAMAGE effects tick natively (log, DOT
        // delivery, periodic procs, stock absorb); RendPeriodicProvider below
        // replaces the tick's number with the D3 snapshot (core patch 0016,
        // the final periodic damage hook).
        constexpr uint32 REND_BLEED_FIRST = 81157, REND_BLEED_LAST = 81162;

        class dc_rend_bleed final : public AuraScript
        {
            PrepareAuraScript(dc_rend_bleed);
            Hit snapshot; // the newest bleed's: its school, crit and buckets; the totals are in `stacks`
            uint32 sourceSpell = 0;
            uint32 baseTicks = 0; // the ticks of the aura's own length: the snapshot's total is for these
            double ownSeconds = 0; // the aura's own length, before a power changes it
            bool valid = false;
            // The bleeds this one aura carries (Lamentation lets Rend stack: one per application, each with its own snapshot and
            // length; without a stacking power there is one). They tick on the aura's clock.
            std::vector<ItemPower::BleedStack> stacks;

            // A bleed of a snapshot taken now, beginning after the aura's tick `start`: lasting as long as the powers make Rend last
            // (Wrath of the Wastes 2-piece) and paid out over as few seconds as they say (Ambo's Pride).
            ItemPower::BleedStack Fresh(Player* player, Hit const& hit, unsigned start) const
            {
                unsigned const length = ItemPower::Ticks(ItemPowers::SkillSetTo(player, "Rend", "dot_duration_seconds", ownSeconds));
                unsigned const pay =
                    std::min(length, ItemPower::Ticks(ItemPowers::SkillLowest(player, "Rend", "dot_payout_seconds", length)));
                return {hit.total, baseTicks, length, pay, start};
            }

            // The aura lasts until its last bleed ends: set once on the real apply (shortened or lengthened), and extended by a new bleed.
            void Fit(Aura* aura)
            {
                int32 const wanted = static_cast<int32>(ItemPower::BleedEnd(stacks) * 1000u);
                int32 const elapsed = aura->GetMaxDuration() - aura->GetDuration();
                if (wanted == aura->GetMaxDuration())
                    return;
                aura->SetMaxDuration(wanted);
                aura->SetDuration(wanted - elapsed);
            }

            void Snapshot(AuraEffect const* effect, AuraEffectHandleModes mode)
            {
                Unit* caster = GetCaster();
                sourceSpell = GetId() == REND_BLEED_FIRST ? 81008 : 81063 + GetId() - REND_BLEED_FIRST - 1;
                valid = caster && caster->ToPlayer() &&
                        ComputeHit(caster->ToPlayer(), GetUnitOwner(), sourceSpell, snapshot);
                // A power that lengthens the bleed (Wrath of the Wastes 2-piece) sets the aura's length once, on the real
                // apply; the damage per second stays the snapshot's, so the bleed pays more ticks of the same size. One that
                // deals the whole damage in less time (Ambo's Pride) shortens it the same way.
                if (valid && (mode & AURA_EFFECT_HANDLE_REAL))
                {
                    Aura* aura = GetAura();
                    baseTicks = effect->GetTotalTicks();
                    ownSeconds = aura->GetMaxDuration() / 1000.0;
                    stacks = {Fresh(caster->ToPlayer(), snapshot, 0)};
                    Fit(aura);
                }
                else if (valid && !stacks.empty())
                    stacks.front().total = snapshot.total;
                if (valid)
                    LOG_DEBUG("module.dc.combat", "[DC Rend] applied caster={} target={} total={} duration={}ms",
                             caster->GetName(), GetUnitOwner()->GetGUID().ToString(), snapshot.total, GetAura()->GetMaxDuration());
            }

            // Runs before the native tick. Damage is the provider's; this keeps
            // the rune's per-tick side effect (Blood Lust) on the tick cadence.
            void Tick(AuraEffect const* effect)
            {
                Unit* caster = GetCaster();
                uint32 const number = effect->GetTickNumber();
                if (!valid || !caster || !caster->ToPlayer() || !GetUnitOwner()->IsAlive() || number < 1 ||
                    number > uint32(effect->GetTotalTicks()))
                    return;
                Abilities::RendTick(caster->ToPlayer(), sourceSpell);
            }

        public:
            unsigned Count() const
            {
                return static_cast<unsigned>(stacks.size());
            }

            // Another application of Rend beside this running bleed (a power lets Rend stack, up to `cap`): its own snapshot taken now, its
            // own length; at the cap it replaces the oldest. The aura lasts until the last of them ends.
            bool AddStack(Player* player, unsigned cap)
            {
                Hit fresh;
                AuraEffect const* effect = GetAura() ? GetAura()->GetEffect(EFFECT_0) : nullptr;
                if (!valid || !effect || !ComputeHit(player, GetUnitOwner(), sourceSpell, fresh))
                    return false;
                ItemPower::AddStack(stacks, Fresh(player, fresh, effect->GetTickNumber()), cap);
                snapshot = fresh;
                Fit(GetAura());
                LOG_DEBUG("module.dc.combat", "[DC Rend] stack {}/{} caster={} target={} total={}", Count(), cap, player->GetName(),
                         GetUnitOwner()->GetGUID().ToString(), fresh.total);
                return true;
            }

            // C11: the snapshot's total (for the aura's own length) already includes average crit. No
            // stat/weapon reads here; split rounding so the ticks sum to the total of the bleed's length.
            bool FinalTick(AuraEffect const* effect, Unit* caster, Unit* target, uint64& damage, bool& critical)
            {
                Player* player = caster ? caster->ToPlayer() : nullptr;
                uint32 const number = effect->GetTickNumber();
                if (!valid || !player || stacks.empty() || number < 1 || number > uint32(effect->GetTotalTicks()))
                {
                    damage = 0;             // claimed: a Rend tick never falls back to Warrior math
                    return true;
                }
                Hit tick = snapshot;
                tick.total = ItemPower::BleedDamage(stacks, number);
                tick.areaDamage = 0;
                double const adjusted = DevBoost(player, VictimAdjustedTotal(player, target, tick));
                damage = ExactDamage(adjusted);
                critical = tick.critical;
                // The same receipt DealHit leaves for OnDamage consumers (rift elites). The module
                // has no hook after this tick's delivery: the consumer takes it, or OnDamage below drops it.
                RecordPreCritHit(player, target, tick.crit > 0.0 ? adjusted / tick.crit : 0.0, tick.school);
                LOG_DEBUG("module.dc.combat", "[DC Rend] tick={}/{} caster={} target={} damage={}", number, effect->GetTotalTicks(),
                         player->GetName(), target->GetGUID().ToString(), damage);
                return true;
            }

            void Register() override
            {
                AfterEffectApply += AuraEffectApplyFn(dc_rend_bleed::Snapshot, EFFECT_0, SPELL_AURA_PERIODIC_DAMAGE,
                                                      AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
                OnEffectPeriodic += AuraEffectPeriodicFn(dc_rend_bleed::Tick, EFFECT_0, SPELL_AURA_PERIODIC_DAMAGE);
            }
        };

        // Core patch 0016's opt-in provider, claimed for the Rend bleeds alone:
        // every other periodic aura keeps the stock tick.
        class RendPeriodicProvider final : public UnitScript
        {
        public:
            RendPeriodicProvider()
                : UnitScript("dc_rend_periodic_provider", true,
                             {UNITHOOK_PROVIDE_FINAL_PERIODIC_DAMAGE, UNITHOOK_ON_DAMAGE})
            {
            }

            bool ProvideFinalPeriodicDamage(AuraEffect const* aura, Unit* caster, Unit* target, uint64& damage64,
                                            bool& critical) override
            {
                if (!aura || !target || aura->GetId() < REND_BLEED_FIRST || aura->GetId() > REND_BLEED_LAST)
                    return false;
                uint64& damage = damage64; // the core hands the tick over in 64 bits and takes the exact tick back
                auto* bleed = aura->GetBase()->GetScript<dc_rend_bleed>("dc_rend_bleed");
                if (!bleed)
                {
                    damage = 0;
                    return true;
                }
                return bleed->FinalTick(aura, caster, target, damage, critical);
            }

            // FinalTick records the tick's receipt before the core absorbs and delivers it,
            // and the module has no hook after delivery. A tick the absorb ate whole reaches DealDamage
            // as zero, and the rift-elite OnDamage returns on zero before it takes the
            // receipt, so it would wait for the next hit on that elite (GitHub #74). The
            // consumer never takes a receipt at zero, so dropping it here cannot beat the
            // consumer to it, whichever of the two scripts the core calls first.
            void OnDamage(Unit* attacker, Unit*, uint32& damage) override
            {
                if (!damage && attacker)
                    ClearPreCritHit(attacker->ToPlayer());
            }
        };
    }

    void OnTargetBonus(Unit* u, double& bonus)
    {
        if (auto rend = Buff(u, "Rend"); rend && Rune(*rend, "Mutilate"))
            bonus += Numbers::Num(rend->id, "damage_bonus_pct");
    }

    void OnHit(Player* p, Unit* target, Row const* r, Row const* b)
    {
        if (Rune(*r, "Mutilate"))
            // The mark lasts as long as the bleed it marks, which a power may lengthen (Wrath of the Wastes 2-piece).
            Mark(p, target, *r,
                 ItemPowers::SkillLowest(p, "Rend", "dot_payout_seconds",
                                         ItemPowers::SkillSetTo(p, "Rend", "dot_duration_seconds", Numbers::Num(b->id, "dot_duration_seconds"))));
    }

    void OnTick(Player* p, uint32 id)
    {
        auto r = Shells::FindAbility(id);
        if (r && Rune(*r, "Blood Lust"))
            Heal(p, p, id, p->GetMaxHealth() * Numbers::Num(r->id, "heal_pct") / 100);
    }

    // Rend's bleed on `unit`. A power can let it stack (Lamentation, `dot_max_stacks`): a new application beside a running bleed of the
    // same rune is another bleed of that aura, until the cap, and replaces the oldest at it. Otherwise it replaces the running bleed.
    // `keepRunning` (a bleed applied by another skill's hit, Ambo's Pride) applies only while the enemy carries fewer bleeds of
    // yours than the cap: a restart would drop the running one before it paid.
    bool Apply(Player* player, Unit* unit, uint32 spellId, std::string const& skill, bool keepRunning)
    {
        if (skill != "Rend")
            return false;
        uint32 const marker =
            spellId == 81008 ? REND_BLEED_FIRST : REND_BLEED_FIRST + 1 + spellId - 81063;
        unsigned const cap = static_cast<unsigned>(ItemPowers::SkillSetTo(player, "Rend", "dot_max_stacks", 1));
        unsigned running = 0;
        for (uint32 old = REND_BLEED_FIRST; old <= REND_BLEED_LAST; ++old)
            if (Aura* aura = unit->GetAura(old, player->GetGUID()))
            {
                auto* bleed = aura->GetScript<dc_rend_bleed>("dc_rend_bleed");
                running += bleed ? bleed->Count() : 1;
            }
        if (keepRunning && running >= cap)
            return false;
        if (cap > 1)
            if (Aura* same = unit->GetAura(marker, player->GetGUID()))
                if (auto* bleed = same->GetScript<dc_rend_bleed>("dc_rend_bleed"); bleed && bleed->AddStack(player, cap))
                    return true;
        for (uint32 old = REND_BLEED_FIRST; old <= REND_BLEED_LAST; ++old)
            unit->RemoveAurasDueToSpell(old, player->GetGUID());
        return player->AddAura(marker, unit) != nullptr;
    }

    std::optional<bool> OnResolve(Player* player, Unit* target, uint32 spellId, std::string const& skill)
    {
        if (skill == "Rend")
        {
            HitEffects(player, target, spellId);
            return Apply(player, target, spellId, skill);
        }
        return std::nullopt;
    }

    void RegisterScripts()
    {
        RegisterSpellScript(dc_rend_bleed);
        new RendPeriodicProvider();
    }

    bool DamageOverTime(std::string const& skill)
    {
        return skill == "Rend";
    }
} // namespace DC::Combat::Abilities::Rend
