#include "dc_combat_internal.h"
#include "../classes/follower/dc_follower_skills.h"
#include "dc_item_block_math.h"
#include "dc_damage_boost.h"
#include "dc_ground_device.h"
#include "dc_cost_cut.h"
#include "dc_movement_effects.h"
#include "dc_weapon_flat.h"

namespace DC::Combat
{
    namespace Follower = Classes::Follower; // the engine asks the followers' skills as it asks the classes'
}


// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// RAGE_PER_FURY (10) moved: Rage units per Fury point is the class resource registry's storage_scale (data/tunables/class_resources.csv, dc_resources.h).
// Constant (0.0001): tolerance on the "enough Fury" comparison; Floating-point epsilon, not a game value.
// The Rend bleed tick count (5) moved: the bleed's ticks follow its aura's length (one a second), the base length is read when it is applied.
// Constant (2000): fallback weapon delay in ms when a template has none, .dc weapon diagnostic; Engine's 2.0 s default swing; diagnostic output only.
// Constant (81000, 81156): FIRST_SHELL, LAST_SHELL, the Barbarian block the shell manifest loads; Identifiers; the manifest is the source and the ids must not be renumbered. The active-skill upper bound is gone: the generated Shells::Abilities is the authority.

namespace DC::Combat
{
    bool SkillIsActive(Player const* player, std::string const& skill)
    {
        return Abilities::SkillActive(player, skill) || Monk::SkillActive(player, skill);
    }


    // What the player's own SPELLMOD_COOLDOWN auras make of a duration, asked
    // of the core itself: this is the very call
    // Player::AddSpellAndCategoryCooldowns makes on RecoveryTime
    // (Player.cpp:11139-11146 at the pin), so a number the module has to
    // schedule itself - a charge recharge - is reduced by exactly what the
    // core would have reduced the cooldown by. Flat seconds land before the
    // percentage, because core-patches/0014 gives SPELLMOD_COOLDOWN the
    // flat-first combine D3 uses (skilldata.js:636-642).
    std::uint32_t ReducedCooldownMilliseconds(Player* player, std::uint32_t spellId,
                                              std::uint32_t milliseconds)
    {
        if (!player || !milliseconds)
            return milliseconds;
        int32 value = int32(milliseconds);
        player->ApplySpellMod(spellId, SPELLMOD_COOLDOWN, value);
        return value > 0 ? uint32(value) : 0;
    }

    // Step 8: what the player's own SPELLMOD_DURATION auras make of a duration
    // the module applies itself. Inspiring Presence doubles the duration of the
    // shouts, and doubling a duration is the core's own SPELLMOD_DURATION, so
    // the module asks rather than multiplies: Aura::CalcMaxDuration makes this
    // same ApplySpellMod call on a record's own duration (SpellAuras.cpp at the
    // pin), and SPELLMOD_DURATION was already in the flat-first branch of
    // Player::ApplySpellMod before core-patches/0014 touched it.
    //
    // Milliseconds, because that is the unit the core rounds in; seconds in and
    // seconds out is only the module's own unit at the two ends.
    double ModifiedDurationSeconds(Player* player, std::uint32_t spellId, double seconds)
    {
        if (!player || seconds <= 0)
            return seconds;
        int32 value = int32(seconds * 1000.0);
        player->ApplySpellMod(spellId, SPELLMOD_DURATION, value);
        return value > 0 ? value / 1000.0 : 0.0;
    }

    // The percentage those auras take off a cooldown, for the character sheet.
    // The probe record carries every skill's mask bit, so the one percentage
    // aura the module keeps in step with the sheet reaches it; the flat
    // modifiers name their own skills and do not. The duration asked about is
    // the module's own probe and not that record's cooldown, because the core
    // reduces to a whole millisecond and the sheet is showing the modifiers
    // rather than one skill's rounding.
    double CooldownReductionPercent(Player* player, std::uint32_t probeSpell)
    {
        if (!player)
            return 0;
        return 100.0 * (1.0 - double(ReducedCooldownMilliseconds(player, probeSpell,
                                                                 CostMath::COOLDOWN_PROBE)) /
                                  CostMath::COOLDOWN_PROBE);
    }

    // What the player's next cast of this skill will be held for. A skill's
    // own cooldown is the record's and the core installs it; this reads the
    // same fields the core reads, in the core's own order
    // (`recTime = rec ? rec : catrecTime`), and is what the GM readout prints.
    // A primary is the exception the module still owns: its recovery is one
    // swing at the attack speed of the hand that swung (C7),
    // which no record field can hold.
    std::uint32_t SkillCooldownMilliseconds(Player* player, std::uint32_t spellId, bool offhand)
    {
        // Shells::FindAbility is every playable class's skill and rune shell
        // (generated from the catalogue). The range guard this replaced was
        // what turned a Wizard id away (#72); FindShell holds every class.
        auto shell = Shells::FindAbility(spellId);
        if (!player || !shell)
            return 0;
        if (PrimaryData::Find(spellId))
        {
            double const aps = HandAttacksPerSecond(player, spellId, offhand);
            return uint32(std::clamp(std::ceil((aps > 0 ? 1.0 / aps : 0) * 1000), 0.0,
                                     double(UINT32_MAX)));
        }
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info)
            return 0;
        uint32 const base = info->RecoveryTime ? info->RecoveryTime : info->CategoryRecoveryTime;
        // Gesture of Orpheus (N-CD): the worn items' `cooldown_reduction_pct` on the skill, after the sheet's
        // reduction; ItemPowers::Cast cuts the cooldown the core installs by the same factor. Not in ReducedCooldownMilliseconds: a
        // module send that Cast's cut follows (Crown of the Primus's Time Shell cooldown) would take it twice.
        return uint32(std::lround(ReducedCooldownMilliseconds(player, spellId, base) * ItemPowers::CooldownFactor(player, shell->skill)));
    }

    // C1: every skill WITHOUT a stated
    // cooldown gets its own recovery of one swing, 1 / attacks per second of the
    // hand that swung, and no skill shares it with another. "Stated" means the
    // cast record carries one: RecoveryTime, or the CategoryRecoveryTime its runes
    // share (the field the core installs from). A skill that states one keeps
    // exactly that and gets no swing added. The charge skills keep the charge
    // system and nothing else: a charge is the limiter, and the charge code
    // already clears the swirl while one is left (SendSkillCooldown(..., 0)), so a
    // swing between charges would fight it (Furious Charge, Revenge, Avalanche -
    // Tectonic Rift). Eligibility reads the record and the catalogue, never a
    // class: the Wizard and the Barbarian are two sets of rows to it.
    // An ability shell is a catalogue skill's rune shell, or a shell of its own with no catalogue row
    // (the generated form-ability table: each such ability is its own skill, no runes). Both obey the rule.
    bool IsStandaloneAbility(std::uint32_t spellId)
    {
        for (auto const& ability : Shells::ArchonAbilities)
            if (ability.id == spellId)
                return true;
        return false;
    }

    bool SwingEligible(std::uint32_t spellId)
    {
        if ((!Shells::FindAbility(spellId) && !IsStandaloneAbility(spellId)) || PrimaryData::Find(spellId))
            return false;
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info || info->RecoveryTime || info->CategoryRecoveryTime)
            return false;
        return !Abilities::UsesCharges(spellId);
    }

    // One swing at the attack speed of the hand asked for. Cooldown Reduction does
    // not shorten it (it is not a cooldown the record states), the same as the
    // primaries' today; no attack speed at all means no rate, so no recovery.
    std::uint32_t SwingRecoveryMilliseconds(Player* player, std::uint32_t spellId, bool offhand)
    {
        double const aps = HandAttacksPerSecond(player, spellId, offhand);
        if (aps <= 0)
            return 0;
        return uint32(std::clamp(std::ceil(1.0 / aps * 1000), 0.0, double(UINT32_MAX)));
    }

    // On the skill's own shells only, through the same packet the primaries use,
    // so the stock button swirls and the client drops the next press. Two different
    // skills never touch each other's timer.
    void StartSwingRecovery(Player* player, std::uint32_t spellId, bool offhand)
    {
        if (!player || !SwingEligible(spellId))
            return;
        std::uint32_t const milliseconds = SwingRecoveryMilliseconds(player, spellId, offhand);
        if (!milliseconds)
            return;
        // The skill's own shells: a catalogue skill's rune family, or the ability alone. A sibling shell that
        // STATES a cooldown keeps it: swapping to a rune with no cooldown out of combat must
        // not replace the stated rune's remaining time with a swing.
        auto const own = Shells::FindAbility(spellId);
        PacketCooldowns cooldowns;
        for (auto const& row : Shells::Abilities)
            if (own && std::string(row.skill) == own->skill && SwingEligible(row.id))
            {
                player->AddSpellCooldown(row.id, 0, milliseconds, true);
                cooldowns[row.id] = milliseconds;
            }
        if (!own)
        {
            player->AddSpellCooldown(spellId, 0, milliseconds, true);
            cooldowns[spellId] = milliseconds;
        }
        if (!cooldowns.empty())
        {
            WorldPacket packet;
            player->BuildCooldownPacket(packet, SPELL_COOLDOWN_FLAG_NONE, cooldowns);
            player->SendDirectMessage(&packet);
        }
    }

    // What a finished, player-pressed cast owes. A channel is held for its own
    // length and its swing starts when it ends (EndChannel, StopWhirlwind), so
    // letting go and pressing again cannot beat the rate; a triggered cast is not
    // a press.
    void AbilityCast(Player* player, std::uint32_t spellId, bool triggered, bool channel)
    {
        if (triggered || channel)
            return;
        StartSwingRecovery(player, spellId);
    }

    // The module installs one cooldown now, and it is the primaries' swing
    // recovery (the named exception above). Every skill's own cooldown is
    // installed by Player::AddSpellAndCategoryCooldowns from the record before
    // AfterCast ever runs, and the rune family shares it through the record's
    // Category rather than through a loop here.
    void StartSkillCooldown(Player* player, std::uint32_t spellId, bool offhand)
    {
        if (!player || !Shells::FindAbility(spellId) || !PrimaryData::Find(spellId))
            return;
        SendSkillCooldown(player, spellId, SkillCooldownMilliseconds(player, spellId, offhand));
    }

    void SendSkillCooldown(Player* player, std::uint32_t spellId, std::uint32_t milliseconds)
    {
        auto shell = Shells::FindAbility(spellId);
        if (!player || !shell)
            return;
        PacketCooldowns cooldowns;
        for (auto const& row : Shells::Abilities)
            if (std::string(row.skill) == shell->skill)
            {
                if (milliseconds)
                {
                    // end_time is a relative millisecond duration in this core.
                    player->AddSpellCooldown(row.id, 0, milliseconds, true);
                    cooldowns[row.id] = milliseconds;
                }
                else
                    player->RemoveSpellCooldown(row.id, true);
            }
        if (!cooldowns.empty())
        {
            WorldPacket packet;
            player->BuildCooldownPacket(packet, SPELL_COOLDOWN_FLAG_NONE, cooldowns);
            player->SendDirectMessage(&packet);
        }
    }

    // Whirlwind is the one skill the module still pays for:
    // a channel charges per tick, and D3's cost for that tick is
    // speed-dependent, which no stock field can hold - ManaPerSecond is a
    // single static number. Its records carry no ManaCost, so the core charges
    // nothing at launch or on the ticks, and these two are the whole model.
    //
    // The numbers are the values sheet's, sourced to the accepted research
    // (docs/research/d3-cost-cooldown-math.md, quoting d3planner
    // simulator/barbarian.js:377-384 and cast.js:136-147):
    //
    //     cost = 7 / weapon_speed + 3          a Fury-per-SECOND rate
    //     cost *= channeling / 60              channeling = 40 frames
    //
    // so a tick charges 40/60 of a second at that rate. The reduction is
    // applied to the rate BEFORE that scaling, which is the order the
    // simulator uses, and it is the core's own SPELLMOD_COST arithmetic
    // rather than a copy of it.
    //
    // The cadence is a second number and not that one:
    // d3planner's simulator sets the channel's tick rate to
    // `Math.floor(channeling / info.speed)` frames and recomputes it on every
    // tick (simulator/cast.js:504 and :508), which is why this is read fresh
    // rather than cached. The
    // interval shortens as attack speed rises while a tick keeps charging
    // the unrounded 40/60 share, so a tick does NOT cover the time until the
    // next one at any speed but 1.0, and the channel's drain rises with
    // attack speed: 10 Fury a second at 1.0 attacks, about 11.8 at 1.5. That
    // is deliberate - the cadence rounds, the cost does not.
    // Both are read fresh, so a weapon swap or a buff moves the next tick.
    //
    // Without an attack speed there is no rate and no cadence: the tick costs
    // nothing and the loop never runs, so the channel holds its slot doing
    // nothing until it is stopped. A sheet that cannot answer is a broken
    // sheet, and this neither guesses a number nor charges for one.
    double CostReductionFactor(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return 1.0;
        int32 probe = CostMath::COST_PROBE;
        player->ApplySpellMod(spellId, SPELLMOD_COST, probe);
        return CostMath::Factor(probe);
    }

    bool IsLesser(Unit const* unit)
    {
        Creature const* creature = unit ? unit->ToCreature() : nullptr;
        return ItemPower::IsLesser(creature != nullptr, IsElite(unit),
                                   creature && (creature->isWorldBoss() || creature->IsDungeonBoss() ||
                                                DC::Rifts::IsGuardianEntry(creature->GetEntry())));
    }

    double WhirlwindTickSeconds(Player* player, std::uint32_t spellId, bool offhand)
    {
        return CostMath::ScheduleSeconds(Numbers::Num(spellId, "channel_tick_frames_count"),
                                         HandAttacksPerSecond(player, spellId, offhand),
                                         Numbers::Num(spellId, "channel_frames_per_second_count"));
    }

    // The attacks per second both numbers use is one hand's, with every
    // attack-speed bonus on it - base speed, the weapon's own IAS
    // (stats_full.js:331), the global IAS including dual wield's +15 %
    // (stats_full.js:663 and :670), capped at 5 (stats_full.js:664). That is
    // the simulator's `info[weapon].speed`, the number both its Whirlwind
    // cost (barbarian.js:382) and its channel rate (cast.js:438-440) read,
    // and while dual wielding it alternates hands (cast.js:391-397): the
    // channel ticks main, off, main, so the cadence and the cost of a tick
    // are the hand that swings it. The tooltip
    // data file's blended `info.aps` (skill_barbarian.js:336) is a display
    // number and governs nothing here.
    double WhirlwindTickCost(Player* player, std::uint32_t spellId, bool offhand = false)
    {
        double const rate = CostMath::ChannelRate(
            Numbers::Num(spellId, "channel_cost_speed_term_resource"),
            Numbers::Num(spellId, "channel_cost_flat_resource"),
            HandAttacksPerSecond(player, spellId, offhand));
        if (rate <= 0)
            return 0.0;
        // The reduction applies to the per-second rate BEFORE the channel
        // scaling, which is the order the simulator uses. The scaling is the
        // sheet's own frame count, not the rounded interval the tick is
        // scheduled at. The pool is integer Rage, one unit a point: the debit
        // takes the whole units and carries the rest (Resources::WholeUnits).
        return rate * CostReductionFactor(player, spellId) *
               CostMath::CostScaleSeconds(Numbers::Num(spellId, "channel_tick_frames_count"),
                                          Numbers::Num(spellId, "channel_frames_per_second_count"));
    }

    namespace
    {
        std::mutex critResourceMutex;
        // Arcane Power a player is owed for critical hits, less than a whole point (a low proc coefficient pays a part).
        std::unordered_map<uint64, double> critResourceCarry;
    } // namespace

    // Arcane Power on Critical Hit (d3planner apoc, Resource_On_Crit#Arcanum): a Wizard's critical hit pays the sheet's
    // points scaled by the hit's skill proc coefficient (Stats::Readers::CritResource), the part under a point carried.
    void CriticalResource(Player* player, std::uint32_t spellId)
    {
        if (!player || !spellId || Classes::ClassIdOf(player) != Resources::ArcanePower.classId)
            return;
        auto const sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        if (!sheet || (*sheet)[Stat::ResourceOnCrit] <= 0)
            return;
        std::uint32_t points;
        {
            std::lock_guard<std::mutex> lock(critResourceMutex);
            double& carry = critResourceCarry[player->GetGUID().GetRawValue()];
            points = Stats::Readers::CritResource(*sheet, Numbers::Get(spellId, "proc_coefficient"), carry);
            if (carry == 0)
                critResourceCarry.erase(player->GetGUID().GetRawValue());
        }
        GainArcanePower(player, spellId, points);
    }

    // Taeguk's stack: resource spent on a channelled skill. A channelled skill is one the sheet
    // gives a channel tick, whichever class it is, so Whirlwind's Fury and the Wizard's Arcane Power both reach here.
    void ChannelSpent(Player* player, std::uint32_t spellId)
    {
        if (Numbers::Has(spellId, "channel_tick_frames_count"))
            GemPowers::ChannelSpent(player);
    }

    // The payment itself, the first exception to the core charging the cost:
    // the module charges the channel, the core
    // charges nothing, and the tick's Fury is the model above.
    bool PayWhirlwindTick(Player* player, std::uint32_t spellId, bool offhand)
    {
        Shell shell;
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            auto found = shells.find(spellId);
            if (found == shells.end() || !Abilities::PaysByTick(found->second.skill)) return false;
            shell = found->second;
        }
        double const cost = WhirlwindTickCost(player, spellId, offhand);
        if (CurrentFury(player) + 0.0001 < cost)
            return false;
        if (!Abilities::Ready(player, spellId))
            return false;
        ChangeFury(player, -cost);
        if (cost > 0)
            ChannelSpent(player, spellId);
        AfterPayment(player, shell, cost);
        return true;
    }

    // A Wizard channel tick's Arcane Power:
    // d3planner simulator/cast.js:136-147 at the pin takes the cost, applies
    // the percentage reduction, and scales it by channeling / 60 - the sheet's
    // frame count, not the rounded interval the tick lands on. Unlike
    // Whirlwind's the rate does not depend on attack speed; the cadence does.
    double ChannelTickCost(Player* player, std::uint32_t spellId)
    {
        return CostMath::ChannelTickCost(Numbers::Num(spellId, "cost_resource"), CostReductionFactor(player, spellId),
                                         Numbers::Num(spellId, "channel_tick_frames_count"),
                                         Numbers::Num(spellId, "channel_frames_per_second_count"));
    }

    // 02 §3 lives on the sheet now: DC::Stats::RefreshWeapon feeds the equipped
    // weapon's base speed and the dual-wield +15% in as contributions, and
    // dc_common.cpp's Calculate does base x (1 + weapon IAS) x (1 + sheet IAS)
    // capped at 5.0. Reading the cached number here keeps the animation-time scale
    // and the character sheet on the same value.
    double AttacksPerSecond(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return 0;
        auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        return sheet ? WitchDoctor::AttackSpeed(player, spellId, Necromancer::AttackSpeed(player, spellId, Crusader::AttackSpeed(player, spellId, Primaries::AttackSpeed(player, spellId, Monk::AttackSpeed(player, spellId, sheet->attacksPerSecond))))) * ItemPowers::AttackSpeedFactor(player) : 0;
    }

    bool DualWielding(Player* player)
    {
        if (!player)
            return false;
        auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        return sheet && sheet->offhandAttacksPerSecond > 0;
    }

    // One hand's attacks per second. The sheet holds a speed for each hand,
    // built the same way from that hand's own base speed
    // (dc_common.cpp's Calculate, after D3's stats_full.js:673-675), and a
    // skill's own speed rule applies to whichever hand is swinging.
    double HandAttacksPerSecond(Player* player, std::uint32_t spellId, bool offhand)
    {
        if (!player)
            return 0;
        auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        if (!sheet)
            return 0;
        double const hand = offhand && sheet->offhandAttacksPerSecond > 0
                                ? sheet->offhandAttacksPerSecond
                                : sheet->attacksPerSecond;
        // A skill's own attack speed from the item powers (Bracers of the First Men: Hammer of the Ancients attacks 50% faster).
        auto const ability = Shells::FindAbility(spellId);
        return WitchDoctor::AttackSpeed(player, spellId, Necromancer::AttackSpeed(player, spellId, Crusader::AttackSpeed(player, spellId, Primaries::AttackSpeed(player, spellId, Monk::AttackSpeed(player, spellId, hand))))) *
               (ability ? ItemPowers::SkillFactor(player, ability->skill, "attack_speed_pct") : 1.0) * ItemPowers::AttackSpeedFactor(player);
    }

    // G1: one swing's weapon range before the sheet's flat damage - the template's damage plus the
    // socketed gem's flat damage and the weapon's rolled elemental range (every endpoint, from the
    // per-item cache, never the database). The hit's school stays the skill's.
    std::pair<double, double> WeaponRange(Player* player, bool offHand)
    {
        double low = 1, high = 2;
        if (Item* weapon = player->GetWeaponForAttack(offHand ? OFF_ATTACK : BASE_ATTACK, true))
        {
            ItemTemplate const* proto = weapon->GetTemplate();
            low = proto->Damage[0].DamageMin;
            high = proto->Damage[0].DamageMax;
            if (high <= 0)
            {
                low = 1;
                high = 2;
            }
            DC::Items::WeaponExtraDamage const extra =
                DC::Items::WeaponExtraDamageOf(player->GetGUID().GetRawValue(), weapon->GetGUID().GetCounter());
            low += extra.low;
            high += extra.high;
        }
        return {low, high};
    }

    // The catalogue skill id of a summoning skill named by `petSkill` (the base shell, no rune).
    std::uint32_t PetSkillId(char const* petSkill)
    {
        for (auto const& row : Shells::Abilities)
            if (!*row.rune && std::string(row.skill) == petSkill)
                return Classes::SkillIdOf(row.id);
        return 0;
    }

    bool ComputeHit(Player* player, Unit* target, std::uint32_t spellId, Hit& hit, std::optional<double> skillPct,
                    bool periodic, char const* petSkill)
    {
        // Every other field is assigned; factors are appended, and the Rend bleed recomputes into one Hit on REAPPLY.
        hit.factors.clear();
        if (!HitsThroughCombat(player))
            return false;
        std::optional<Stat> const mainStat = MainStat(player);
        if (!mainStat)
            return false;
        Shell shell;
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            if (!dataReady)
                return false;
            auto found = shells.find(spellId);
            if (found == shells.end())
                return false;
            shell = found->second;
        }
        auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        if (!sheet)
            return false;

        hit.skillName = shell.rune.empty() ? shell.skill : shell.skill + " - " + shell.rune;
        // Archon's runes turn its abilities' damage Cold, Lightning or Fire
        // (wizard_runes.csv, d3planner simulator/wizard.js:1039).
        if (auto element = Wizard::Element(player, shell.spellId))
            shell.element = *element;
        if (char const* element = Shaman::Element(player, shell.spellId))
            shell.element = element;
        hit.school = SchoolOf(shell.element);

        // Step 1: weapon damage of the swinging hand. C7 alternates hands; the
        // caller flips hit.offHand, we just read that weapon (WeaponRange adds the
        // socketed gem's flat damage and the weapon's rolled elemental range, G1).
        // Step 1: equipped flat affixes contribute to either swinging hand, their minimum to the low end and
        // their maximum to the high end (dc_weapon_flat.h).
        auto const weaponRange = WithFlatDamage(WeaponRange(player, hit.offHand), *sheet);
        double const low = weaponRange.first, high = weaponRange.second;
        hit.weapon = low + Roll() * (high - low);

        // Steps 2-8.
        hit.mainstat = 1.0 + (*sheet)[*mainStat] / 100.0;
        // A channel tick's percentage is the tick's own share of the ramping
        // per-second number, which only the channel loop knows.
        hit.skill = (skillPct ? *skillPct : shell.damagePct) / 100.0 * Wizard::SkillFactor(player, shell.spellId);
        hit.targetBonus = Primaries::TargetBonus(target) + Abilities::TargetBonus(target) +
                          Wizard::TargetBonus(player, target, hit.school) + Monk::TargetBonus(player, target) +
                          GemPowers::TargetBonus(target);
        // K5: the affix names the base skill by id, so a runed shell resolves
        // to its skill and every rune of it gets the bonus.
        // A pet skill's rolled affix is its own multiplier (below), not a share of the pool.
        std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;
        bool const petHit = GemPowers::IsPetSkill(petName.c_str());
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        hit.additive = Additive(
            (GemPowers::IsPetSkill(shell.skill.c_str()) ? 0 : DC::Items::SkillDamageBonus(guid, Classes::SkillIdOf(shell.spellId))) +
            Primaries::DamageBonus(player) + Abilities::DamageBonus(player) + Passives::DamageBonus(player) +
            Wizard::DamageBonus(player, target, shell.spellId) + Monk::DamageBonus(player, target, shell.spellId) +
            GemPowers::DamageBonus(player) + ItemPowers::DamageBonus(player) + hit.targetBonus);
        // Magefist and every `element` power: added to the same bonus (the additive:elemental bucket, legendary_powers.csv).
        hit.elemental = 1.0 + (sheet->elementalDamage[Index(ElementEnum(shell.element))] +
                               Wizard::ElementalBonus(player, hit.school) + ItemPowers::ElementBonus(player, shell.element)) / 100.0;
        // Step 6: Elite Damage against an elite, and Damage to Beasts, Demons or Undead against that kind; the two multiply
        // (damage_formula.csv step 6).
        hit.elite = (1.0 + (IsElite(target) ? (*sheet)[Stat::EliteDamage] / 100.0 : 0.0)) *
                    Stats::Readers::MonsterTypeFactor(*sheet, KindOf(target));
        // Item and set powers: each is a multiplier of its own on its skill (legendary_powers.csv, damage_increase_pct); Starfire's is one of
        // its own by the yards to the target (damage_per_distance_pct).
        hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct") * ItemPowers::DealtFactor(player) * CopyFactor();
        hit.legendary *= ItemPowers::StackedSkillFactor(player, petName); // Fleshrake: the stacks of Dashing Strike's buff
        // A row that names one rune ("Ancient Spear - Boulder Toss", Skular's Salvation) is a multiplier of its own beside the skill's.
        if (!shell.rune.empty())
            hit.legendary *= ItemPowers::SkillFactor(player, hit.skillName, "damage_increase_pct");
        hit.legendary *= ItemPowers::DistanceFactor(player, target, shell.element);
        hit.legendary *= ItemPowers::TargetFactor(player, target, petName); // Fjord Cutter: by the target's state (N-TCTRL)
        hit.legendary *= ItemPowers::ImpairedFactor(player, target); // Krysbin's Sentence: by the target's slow or other control (N-TCTRL)
        hit.legendary *= ItemPowers::MissingResourceFactor(player, petName); // Dishonored Legacy: by the Fury missing now
        hit.legendary *= ItemPowers::SpentFactor(player, petName, hit.spent); // Blade of the Warlord: by the Fury the cast took
        hit.legendary *= ItemPowers::DerivedFactor(player, petName, *sheet); // Standoff: by the bonus movement speed (N-DERIVED)
        hit.legendary *= ItemPowers::PerStackFactor(player, petName, "damage_by_wind_stacks_pct", Monk::WindStacks(player)); // Monkey King's Garb 6-piece (N-COUNTREAD)
        hit.legendary *= ItemPowers::PerStackFactor(player, petName, "damage_per_enemy_hit_pct", ItemPowers::EnemyStacks(player, petName)); // Saffron Wrap: the enemies the last Overpower hit (N-NEXT)
        hit.legendary *= ItemPowers::MarkFactor(player, target, petName, shell.rune == "Fire Ally"); // Bindings of the Lesser Gods: the enemy's mark
        if (!periodic && !petSkill)
            hit.legendary *= ItemPowers::NextAttackFactor(player, shell.skill); // Blood Brother: the attack after a block (N-BLOCK)
        // Step 8, the multiplicative bucket d3planner calls dmgmul: Archon form,
        // its kill stacks, Power Hungry, Audacity and Arcane Dynamo are this
        // bucket (simulator/wizard.js:1011, :1024, :1206, :1296, :1280), and so
        // are the legendary gems (Simplicity's Strength, the three Banes and Zei's; Taeguk is step 4's).
        // The damage buckets' own multipliers (damage-buckets.md 6a): each is a D3 category of its own, whoever the class, and `.dc hit` names each.
        if (petHit)
            AddFactor(hit.factors, "Pet skill damage",
                      DC::Items::SkillDamageBonus(guid, petSkill ? PetSkillId(petSkill) : Classes::SkillIdOf(shell.spellId)));
        Passives::Multipliers(player, target, shell.skill, hit.factors);
        Abilities::Multipliers(player, hit.factors);
        Pylons::Multipliers(player, hit.factors);   // Power Pylon, a separate multiplier of its own (pylons.md 4.3)
        DamageBoost::Multipliers(player, hit.factors); // a timed boost to the damage a player deals, one multiplier of its own each
        GemPowers::Multipliers(player, hit.factors); // Legacy of Dreams, a legendary gem's multiplier of its own
        Wizard::Multipliers(player, shell.spellId, hit.factors);
        Monk::Multipliers(player, target, shell.spellId, hit.factors);
        Crusader::Multipliers(player, shell.spellId, hit.factors);
        Necromancer::Multipliers(player, target, shell.spellId, hit.factors);
        DemonHunter::Multipliers(player, target, shell.spellId, hit.factors);
        WitchDoctor::Multipliers(player, target, shell.spellId, hit.factors);
        Shaman::Multipliers(player, target, shell.spellId, hit.factors);
        hit.targetFactor = Wizard::TargetFactor(player, target, hit.factors);
        hit.standalone = Wizard::Standalone(player, target, shell.spellId) * GemPowers::SkillFactor(player, shell.spellId) *
                         GemPowers::TargetFactor(player, target) *
                         GemPowers::PetFactor(player, petName.c_str()) * Product(hit.factors);

        double const skillCrit = Abilities::CritBonus(shell.skill, CurrentFury(player));
        double const chc = std::clamp(((*sheet)[Stat::CritChance] + Primaries::CritBonus(target)+skillCrit+(target?target->GetTotalAuraModifier(SPELL_AURA_MOD_ATTACKER_SPELL_AND_WEAPON_CRIT_CHANCE):0)+Wizard::CritBonus(player, target, shell.spellId)+Crusader::CritBonus(player, target, shell.spellId)+Necromancer::CritBonus(player, target)+DemonHunter::CritBonus(player, target, shell.spellId)+GemPowers::CritBonus(player, target)+ItemPowers::CritBonus(player, target)+Follower::CritBonus(player, target)) / 100.0, 0.0, 1.0);
        double const chd = (*sheet)[Stat::CritDamage] / 100.0;
        if (shell.dot || periodic)
        {
            // C11: a DoT never rolls; every tick carries average crit.
            hit.crit = 1.0 + chc * chd;
            hit.critical = false;
        }
        else
        {
            hit.critical = Roll() < chc;
            hit.crit = hit.critical ? 1.0 + chd : 1.0;
        }

        hit.total = Total(hit.weapon, hit.mainstat, hit.skill, hit.additive, hit.elemental, hit.elite, hit.legendary,
                          hit.standalone, hit.crit);

        // Step 11: 20% chance for Area Damage; never chains, no Life on Hit.
        double const areaPct = (*sheet)[Stat::AreaDamage] / 100.0;
        hit.areaDamage = (areaPct > 0 && Roll() < AREA_DAMAGE_CHANCE) ? hit.total * areaPct : 0.0;
        (void) target;
        return true;
    }

    std::string Hit::Describe() const
    {
        std::ostringstream out;
        out.imbue(std::locale::classic());
        out << std::fixed << std::setprecision(2);
        out << skillName << (offHand ? " [off-hand]" : " [main-hand]") << " weapon=" << weapon
            << " x mainstat=" << mainstat << " x skill=" << skill << " x additive=" << additive
            << " x elemental=" << elemental << " x elite=" << elite << " x legendary=" << legendary
            << " x standalone=" << standalone;
        for (auto const& [name, factor] : factors)
            out << " [" << name << " x" << factor << "]";
        out << " x crit=" << crit << (critical ? " (CRIT)" : "") << " = "
            << std::setprecision(0) << total;
        if (areaDamage > 0)
            out << " | area damage " << areaDamage;
        return out.str();
    }

    bool CastShell(Player* player, Unit* target, std::uint32_t spellId, Hit& hit, std::string& error)
    {
        if (player && !Slotted(player, spellId))
        {
            error = "That shell is not in one of your six slots.";
            return false;
        }
        if (!HitsThroughCombat(player))
        {
            error = "Not a class with a skill catalogue.";
            return false;
        }
        Shell shell;
        {
            std::lock_guard<std::mutex> lock(dataMutex);
            auto found = shells.find(spellId);
            if (found == shells.end())
            {
                error = "Not a shell.";
                return false;
            }
            shell = found->second;
        }
        if (shell.passive)
        {
            error = "That is a passive.";
            return false;
        }
        auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        if (!sheet)
        {
            error = "No stat sheet.";
            return false;
        }

        if (!ComputeHit(player, target, spellId, hit))
        {
            error = "Could not resolve the hit.";
            return false;
        }
        return true;
    }

    namespace
    {
        struct HitReceipt { uint64 target = 0; PreCritHit hit; };
        thread_local std::unordered_map<uint64, HitReceipt> preCritHits;
    }
    void RecordPreCritHit(Player* player, Unit* target, double damage, unsigned school)
    {
        if (player && target)
            preCritHits[player->GetGUID().GetRawValue()] = {target->GetGUID().GetRawValue(), {damage, school}};
    }
    void ClearPreCritHit(Player* player)
    {
        if (player)
            preCritHits.erase(player->GetGUID().GetRawValue());
    }
    std::optional<PreCritHit> ConsumePreCritHit(Player* player, Unit* target)
    {
        if (!player || !target)
            return std::nullopt;
        auto found = preCritHits.find(player->GetGUID().GetRawValue());
        if (found == preCritHits.end() || found->second.target != target->GetGUID().GetRawValue())
            return std::nullopt;
        PreCritHit const hit = found->second.hit;
        preCritHits.erase(found);
        return hit;
    }

    // Re-evaluate only the victim debuff for periodic snapshots and splash
    // retargeting. Caster buffs remain snapshotted; Thorns starts at additive=1.
    // Rend's periodic provider reads the same number, so a tick and a direct hit
    // cannot drift apart.
    double VictimAdjustedTotal(Player* player, Unit* target, Hit const& hit)
    {
        return hit.total * (hit.additive + (Primaries::TargetBonus(target) + Abilities::TargetBonus(target) +
                                            Wizard::TargetBonus(player, target, hit.school) + Monk::TargetBonus(player, target) +
                                            GemPowers::TargetBonus(target) -
                                            hit.targetBonus) / 100) /
               hit.additive * Wizard::TargetFactor(player, target) / hit.targetFactor;
    }

    void DealHit(Player* player, Unit* target, std::uint32_t spellId, Hit const& hit, bool fixed)
    {
        if (!player || !target || !target->IsAlive() || hit.total <= 0)
            return;
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info)
            return;
        // C8: monsters have no armor or resistance, so absorb and resist stay zero
        // and the number the client shows is exactly what the formula produced.
        SpellNonMeleeDamage log(player, target, info, hit.school);
        double const adjusted = DevBoost(player, fixed ? hit.total : VictimAdjustedTotal(player, target, hit)); // GM dev multiplier
        log.damage = ExactDamage(adjusted); // the whole hit, in 64 bits: the core carries it to the Life and the combat log
        log.cleanDamage = LifeToUInt32(log.damage);
        log.physicalLog = hit.school == SPELL_SCHOOL_MASK_NORMAL;
        // C5: our roll decides the crit, not the core's.
        if (hit.critical)
            log.HitInfo |= SPELL_HIT_TYPE_CRIT;
        RecordPreCritHit(player, target, hit.crit > 0.0 ? adjusted / hit.crit : 0.0, hit.school);
        player->SendSpellNonMeleeDamageLog(&log);
        player->DealSpellDamage(&log, true);
        ClearPreCritHit(player);
        Shaman::Dealt(player, target, spellId, hit.school, hit.critical, adjusted); // a Spirit Link shares the hit; a share is not shared again
    }

    namespace
    {
        // The victim's cached sheet, or empty when this victim's defence is still
        // the core's to compute: not a player, or a player whose stats never
        // loaded. Every mitigation path below starts here.
        std::optional<StatSheet> SheetOf(Unit* victim)
        {
            Player* player = victim ? victim->ToPlayer() : nullptr;
            if (!player)
                return std::nullopt;
            return DC::Stats::Get(player->GetGUID().GetRawValue());
        }

        // 01-stats §3: armor, resistance and the class reduction are already folded
        // into one per-element factor on the sheet, so the whole of the player's
        // percentage mitigation is this one number.
        double FactorOf(StatSheet const& sheet, unsigned schoolMask)
        {
            return sheet.damageTaken[Index(ElementEnum(ElementOfSchool(schoolMask)))];
        }
    } // namespace

    std::optional<double> DamageTakenFactor(Unit* victim, unsigned schoolMask, bool melee)
    {
        auto sheet = SheetOf(victim);
        if (!sheet)
            return std::nullopt;
        return FactorOf(*sheet, schoolMask)*Passives::IncomingFactor(victim->ToPlayer(),schoolMask)*GemPowers::IncomingFactor(victim->ToPlayer(),schoolMask,melee)*Follower::TakenFactor(victim->ToPlayer(),melee)*ItemPowers::IncomingFactor(victim->ToPlayer())*Monk::TakenFactor(victim)*Shaman::TakenFactor(victim);
    }

    std::optional<double> Mitigate(Unit* victim, unsigned schoolMask, double damage, bool* blocked, bool melee, Unit* attacker)
    {
        if (blocked)
            *blocked = false;
        auto sheet = SheetOf(victim);
        if (!sheet)
            return std::nullopt;
        StatSheet const& s = *sheet;
        double result = damage * FactorOf(s, schoolMask) * Passives::IncomingFactor(victim->ToPlayer(),schoolMask) *
                        GemPowers::IncomingFactor(victim->ToPlayer(), schoolMask, melee) *
                        Follower::TakenFactor(victim->ToPlayer(), melee) *
                        ItemPowers::IncomingFactor(victim->ToPlayer()) * Monk::TakenFactor(victim) * Shaman::TakenFactor(victim);
        // Elite Damage Reduction (d3planner edef): a percentage layer like the rest, so before Shield Block.
        if (IsElite(attacker))
            result *= 1 - s[Stat::EliteReduction] / 100;
        if (result > 0)
            ItemPowers::Hurt(victim->ToPlayer());
        // mitigation.csv Shield Block, docs/research/block.md §2: a chance to remove
        // a FLAT Block Amount, rolled inside the shield's own range, after every
        // percentage layer. It is not an avoid and never WoW's block - that one is
        // held at zero, because our generated shield templates leave item_template
        // .Block at 0 and Unit::GetUnitBlockChance returns 0 without it.
        // N-BLOCK: the worn items' Block Chance (Blood Brother) joins the sheet's under the same total cap, a blocked hit is cut by the
        // items' share of it, and the block is an event the items listen to (`block`).
        Player* const wearer = victim->ToPlayer();
        double const bonus = ItemPowers::BlockBonus(wearer);
        double const chance = ItemBlock::Chance(s[Stat::BlockChance], bonus, bonus > 0 ? NumericData::Block().totalChanceCap : 0.0);
        if (result > 0 && chance > 0 && Roll() * 100 < chance)
        {
            double const low = s[Stat::BlockAmountMin], high = s[Stat::BlockAmountMax];
            double const amount = high > low ? std::uniform_real_distribution<double>(low, high)(Engine()) : low;
            result = ItemBlock::Blocked(result, amount, ItemPowers::BlockedFactor(wearer));
            Crusader::Blocked(victim, attacker);
            if (blocked)
                *blocked = true;
            ItemPowers::Blocked(wearer, attacker);
        }
        result = Monk::Absorb(victim, result);
        result = Crusader::Redirect(victim, result);
        result = Necromancer::Reduce(victim, result);
        result = WitchDoctor::Reduce(victim, result);
        result = Shaman::Reduce(victim, attacker, result);
        return result;
    }

    void DealMonsterHit(Unit* attacker, Player* victim, std::uint32_t spellId, double baseDamage, unsigned schoolOverride)
    {
        if (!attacker || !victim || !victim->IsAlive() || baseDamage <= 0)
            return;
        // Shield Pylon: this is the path of every rift ability, affix and hazard hit, and none asks the core's immunity.
        if (Pylons::Shielded(victim))
            return;
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info)
            return;
        unsigned const school = schoolOverride ? schoolOverride : unsigned(info->SchoolMask);
        double damage = baseDamage * DC::Rifts::EliteDamageMultiplier(attacker) * Abilities::IncomingFactor(attacker) * Wizard::IncomingFactor(attacker) * Monk::IncomingFactor(attacker) * (1 + (Primaries::TargetBonus(victim) + Abilities::TargetBonus(victim)) / 100);
        damage = Mitigate(victim, school, damage, nullptr, info->DmgClass == SPELL_DAMAGE_CLASS_MELEE, attacker).value_or(damage);
        if(damage>0)Passives::Taken(victim,school,false,damage);
        if(damage>0)Monk::Taken(victim,attacker);
        if(damage>0)Crusader::Taken(victim,attacker,damage);
        if (damage <= 0)
            return;
        uint32 dealt = static_cast<uint32>(std::min<double>(damage, std::numeric_limits<uint32>::max()));
        Wizard::Incoming(victim, attacker, dealt, Wizard::Attack::Spell);
        GemPowers::Incoming(victim, attacker, dealt); // Moratorium: its share of this hit is put off

        // This hit never reaches the core's
        // damage pipeline, so the victim's stock absorbs - Diamond Skin, the
        // passive shields - are asked here with the core's own
        // Unit::CalcAbsorbResist. The school handed to it is Normal so that
        // it runs no resistance roll: the D3 resistances are already in
        // Mitigate, and every shield of ours absorbs all schools.
        DamageInfo absorbing(attacker, victim, dealt, info, SPELL_SCHOOL_MASK_NORMAL, SPELL_DIRECT_DAMAGE);
        Unit::CalcAbsorbResist(absorbing);
        SpellNonMeleeDamage log(attacker, victim, info, school);
        log.damage = absorbing.GetDamage();
        log.absorb = absorbing.GetAbsorb();
        log.cleanDamage = log.damage;
        log.physicalLog = school == SPELL_SCHOOL_MASK_NORMAL;
        attacker->SendSpellNonMeleeDamageLog(&log);
        attacker->DealSpellDamage(&log, true);
    }

    namespace
    {
        class CombatWorld final : public WorldScript
        {
        public:
            CombatWorld()
                : WorldScript("dc_combat_world", {WORLDHOOK_ON_STARTUP})
            {
            }
            void OnStartup() override
            {
                try
                {
                    // The shell manifest is the generator's own output table; skills and
                    // runes come from the dc_ tables generate_sql.py produced.
                    std::unordered_map<std::uint32_t, Shell> loaded;
                    std::unordered_map<uint32, Targeting> targeting;
                    if (QueryResult rows = WorldDatabase.Query(
                            "SELECT spell_id,target_type,range_kind,range_yards,radius_yards,width_yards "
                            "FROM dc_spell_targeting"))
                        do
                        {
                            Field* f = rows->Fetch();
                            targeting[f[0].Get<uint32>()] = {f[1].Get<std::string>(), f[2].Get<std::string>(),
                                                             f[3].Get<float>(), f[4].Get<float>(), f[5].Get<float>()};
                        } while (rows->NextRow());
                    else
                        LOG_ERROR("server", "Ability targeting data missing; apply combat_0005_ability_targeting.sql");
                    QueryResult skills =
                        WorldDatabase.Query("SELECT skill_name, fury_cost, fury_generation, cooldown_seconds, "
                                            "damage_pct_weapon_damage FROM dc_barbarian_skills");
                    if (!skills)
                        throw std::runtime_error("dc_barbarian_skills is missing");
                    struct SkillRow
                    {
                        // fury_cost and cooldown_seconds are read and not
                        // kept: the spell record carries both now, the core
                        // charges one and installs the other.
                        double gen = 0.0, dmg = 0.0;
                    };
                    std::unordered_map<std::string, SkillRow> byName;
                    do
                    {
                        Field* f = skills->Fetch();
                        SkillRow row;
                        row.gen = f[2].IsNull() ? 0 : f[2].Get<double>();
                        row.dmg = f[4].IsNull() ? 0 : f[4].Get<double>();
                        byName[f[0].Get<std::string>()] = row;
                    } while (skills->NextRow());

                    // Every rune's modifiers, parsed once. This used to be a single
                    // hand-written case for Rend/Lacerate; the grammar covers all 115.
                    QueryResult runes = WorldDatabase.Query(
                        "SELECT skill_name, rune_name, modified_cost_cooldown_damage FROM dc_barbarian_runes");
                    std::unordered_map<std::string, RuneModifiers> runeMods;
                    if (runes)
                        do
                        {
                            Field* f = runes->Fetch();
                            runeMods[f[0].Get<std::string>() + "|" + f[1].Get<std::string>()] =
                                ParseRuneModifiers(f[2].Get<std::string>());
                        } while (runes->NextRow());

                    QueryResult manifest = WorldDatabase.Query(
                        "SELECT ID, Name_Lang_enUS, SchoolMask FROM spell_dbc WHERE ID BETWEEN {} AND {} ORDER BY ID",
                        FIRST_SHELL, LAST_SHELL);
                    if (!manifest)
                        throw std::runtime_error("spell shells are missing; apply combat_0001_spell_shells.sql");
                    do
                    {
                        Field* f = manifest->Fetch();
                        Shell shell;
                        shell.spellId = f[0].Get<uint32>();
                        if (auto geometry = targeting.find(shell.spellId); geometry != targeting.end())
                            shell.targeting = geometry->second;
                        std::string const name = f[1].Get<std::string>();
                        std::size_t const split = name.find(" - ");
                        shell.skill = split == std::string::npos ? name : name.substr(0, split);
                        shell.rune = split == std::string::npos ? "" : name.substr(split + 3);
                        auto row = byName.find(shell.skill);
                        if (row == byName.end())
                        {
                            shell.passive = true; // a passive aura, not a skill
                            loaded[shell.spellId] = shell;
                            continue;
                        }
                        // The parent skill's numbers, then the rune's own where
                        // it states one, which is now only its damage. Neither
                        // the Fury cost nor the cooldown is here any more: both
                        // are fields on the spell record and the core reads them.
                        shell.damagePct = row->second.dmg;
                        shell.furyGeneration = row->second.gen;
                        if (!shell.rune.empty())
                        {
                            auto found = runeMods.find(shell.skill + "|" + shell.rune);
                            if (found == runeMods.end())
                                throw std::runtime_error("No rune row for " + shell.skill + " - " + shell.rune);
                            RuneModifiers const& mods = found->second;
                            if (mods.hasDamage && !Abilities::KeepsSheetDamage(shell.skill, shell.rune))
                                shell.damagePct = mods.damagePct;
                        }
                        if (auto primary = PrimaryData::Find(shell.spellId))
                        {
                            shell.damagePct = primary->damage;
                            shell.furyGeneration = primary->fury;
                        }
                        // Audit rows 9 and 10: the tooltip in barbarian_skills.csv says
                        // "over 5 seconds" and "over 8 seconds", and the generator wrote
                        // both into the skill's own spell record. Read the number back
                        // from there rather than keeping a second copy here. The base
                        // row - the one with no rune - is the one that holds the length,
                        // so a runed shell still reads its skill's, as it always did.
                        shell.dot = Abilities::DamageOverTime(shell.skill);
                        shell.dotSeconds = 0;
                        if (shell.dot)
                            for (auto const& base : Shells::Abilities)
                                if (shell.skill == base.skill && !*base.rune)
                                {
                                    shell.dotSeconds = Numbers::Num(base.id, "dot_duration_seconds");
                                    break;
                                }
                        // The generator resolved the element into the shell's SchoolMask
                        // already, so read it back rather than repeating the lookup and
                        // risking a server/client disagreement.
                        shell.element = ElementOfSchool(f[2].Get<uint32>());
                        loaded[shell.spellId] = shell;
                    } while (manifest->NextRow());

                    // Every other class's skills and runes:
                    // the rows of Shells::Abilities outside the
                    // Barbarian's block, loaded from the records alone. Their
                    // names are the header's, their element the record's
                    // school and their damage the record's own damage_pct -
                    // no dc_<class>_skills table and no class named here.
                    //
                    // Only a plain direct hit carries a damage number now. A
                    // record whose damage ramps (a channel), is spread over a
                    // window, or waits on a duration, summon or armour is a
                    // mechanic of the class's own that a later task builds; it
                    // loads with no damage, so it casts and plays its donor's
                    // visual and hits nothing. A Wizard hit also needs the
                    // class's stat sheet, which
                    // ComputeHit already refuses without.
                    for (auto const& ability : Shells::Abilities)
                    {
                        if (loaded.count(ability.id))
                            continue;
                        SpellInfo const* info = sSpellMgr->GetSpellInfo(ability.id);
                        if (!info)
                            throw std::runtime_error("spell shell " + std::to_string(ability.id) +
                                                     " is missing; apply the spell records migration");
                        Shell shell;
                        shell.spellId = ability.id;
                        shell.skill = ability.skill;
                        shell.rune = ability.rune;
                        shell.element = ElementOfSchool(info->SchoolMask);
                        if (auto geometry = targeting.find(shell.spellId); geometry != targeting.end())
                            shell.targeting = geometry->second;
                        if (auto monk = Monk::BasePct(ability.id))
                            shell.damagePct = *monk;
                        else if (auto crusader = Crusader::BasePct(ability.id))
                            shell.damagePct = *crusader;
                        else if (auto necromancer = Necromancer::BasePct(ability.id))
                            shell.damagePct = *necromancer;
                        else if (auto demonHunter = DemonHunter::BasePct(ability.id))
                            shell.damagePct = *demonHunter;
                        else if (auto shamanPrimary = Shaman::PrimaryBasePct(ability.id))
                            shell.damagePct = *shamanPrimary;
                        else if (auto witchDoctor = WitchDoctor::BasePct(ability.id))
                            shell.damagePct = *witchDoctor;
                        else if (auto shaman = Shaman::BasePct(ability.id))
                            shell.damagePct = *shaman;
                        else if (!DamageWaits(ability.id) && Numbers::Has(ability.id, "damage_pct"))
                            shell.damagePct = Numbers::Num(ability.id, "damage_pct");
                        loaded[shell.spellId] = shell;
                    }
                    // Archon form's five abilities:
                    // not catalogue skills, so not in Abilities,
                    // but shells like any other - the record's school, the
                    // targeting row, and the sourced damage in
                    // wizard_archon_values.csv. Disintegration Wave is a
                    // channel and deals its ticks through the channel loop.
                    for (auto const& ability : Shells::ArchonAbilities)
                    {
                        SpellInfo const* info = sSpellMgr->GetSpellInfo(ability.id);
                        if (!info)
                            throw std::runtime_error("Archon form ability " + std::to_string(ability.id) +
                                                     " is missing; apply the spell records migration");
                        Shell shell;
                        shell.spellId = ability.id;
                        shell.skill = Wizard::ARCHON_FORM;
                        shell.rune = ability.name;
                        shell.element = ElementOfSchool(info->SchoolMask);
                        if (auto geometry = targeting.find(shell.spellId); geometry != targeting.end())
                            shell.targeting = geometry->second;
                        if (Numbers::Has(ability.id, "damage_pct") &&
                            !Numbers::Has(ability.id, "channel_tick_frames_count"))
                            shell.damagePct = Numbers::Num(ability.id, "damage_pct");
                        loaded[shell.spellId] = shell;
                    }
                    for (auto const& passive : Shells::Passives)
                        if (!loaded.count(passive.id))
                        {
                            Shell shell;
                            shell.spellId = passive.id;
                            shell.skill = passive.name;
                            shell.passive = true;
                            loaded[shell.spellId] = shell;
                        }

                    // Legendary gems: the shells a gem's power strikes with. Each is its own skill (the
                    // gem's name), carries no damage of its own - the gem's number is handed to Strike - and takes
                    // its school from the record, so ComputeHit reads the hit as the gem's.
                    for (auto const& gem : Shells::GemShells)
                    {
                        SpellInfo const* info = sSpellMgr->GetSpellInfo(gem.id);
                        if (!info)
                            throw std::runtime_error("gem spell shell " + std::to_string(gem.id) +
                                                     " is missing; apply the spell records migration");
                        Shell shell;
                        shell.spellId = gem.id;
                        shell.skill = info->SpellName[0] ? info->SpellName[0] : "";
                        shell.element = ElementOfSchool(info->SchoolMask);
                        loaded[shell.spellId] = shell;
                    }
                    // The helper records the module strikes with (Grenadier's giant grenade): each its own skill, the record's
                    // school and no damage of its own - the module hands the percentage to Strike.
                    for (char const* name : Shells::StrikeHelpers)
                    {
                        std::uint32_t const helper = Shells::HelperFor(name);
                        SpellInfo const* info = helper ? sSpellMgr->GetSpellInfo(helper) : nullptr;
                        if (!info)
                            throw std::runtime_error(std::string("strike helper shell ") + name +
                                                     " is missing; apply the spell records migration");
                        Shell shell;
                        shell.spellId = helper;
                        shell.skill = name;
                        shell.element = ElementOfSchool(info->SchoolMask);
                        loaded[shell.spellId] = shell;
                    }
                    // Pylons P2: Conduit's strike, a shell of its own with the record's school
                    // (Lightning) and no damage of its own; the module hands the row's percentage to ComputeHit.
                    if (SpellInfo const* info = sSpellMgr->GetSpellInfo(Shells::PylonConduitStrike))
                    {
                        Shell shell;
                        shell.spellId = Shells::PylonConduitStrike;
                        shell.skill = info->SpellName[0] ? info->SpellName[0] : "";
                        shell.element = ElementOfSchool(info->SchoolMask);
                        loaded[shell.spellId] = shell;
                    }
                    else
                        throw std::runtime_error("pylon spell shell " + std::to_string(Shells::PylonConduitStrike) +
                                                 " is missing; apply the spell records migration");
                    // Bovine Bardiche: the cows' hit record, a gem shell's shape (the record's name and school,
                    // no damage of its own); ItemSummons hands the cow's percentage to ComputeHit. No record: the cows deal nothing.
                    if (std::uint32_t const cow = Shells::PowerBuffFor("Unique_Polearm_101_x1", "summon_herd"))
                        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(cow))
                        {
                            Shell shell;
                            shell.spellId = cow;
                            shell.skill = info->SpellName[0] ? info->SpellName[0] : "";
                            shell.element = ElementOfSchool(info->SchoolMask);
                            loaded[shell.spellId] = shell;
                        }

                    // Storm Crow: the fiery ball's hit record, the cows' shape (the record's name and school, no damage of its own);
                    // ItemProc hands the tunable's percentage to ComputeHit. No record: the ball deals nothing.
                    if (std::uint32_t const ball = Shells::PowerBuffFor("Unique_WizardHat_004_x1", "proc_damage"))
                        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(ball))
                        {
                            Shell shell;
                            shell.spellId = ball;
                            shell.skill = info->SpellName[0] ? info->SpellName[0] : "";
                            shell.element = ElementOfSchool(info->SchoolMask);
                            loaded[shell.spellId] = shell;
                        }

                    // Fire Walkers: the burning ground's hit record, the same shape. ItemTrail hands the item's rolled percent to
                    // ComputeHit. No record: the ground deals nothing.
                    if (std::uint32_t const burn = Shells::PowerBuffFor("Unique_Boots_007_p2", "burn_trail"))
                        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(burn))
                        {
                            Shell shell;
                            shell.spellId = burn;
                            shell.skill = info->SpellName[0] ? info->SpellName[0] : "";
                            shell.element = ElementOfSchool(info->SchoolMask);
                            loaded[shell.spellId] = shell;
                        }

                    for (auto const& secondary : Primaries::SecondaryShells())
                    {
                        Shell entry;
                        entry.spellId = secondary.spellId;
                        entry.skill = secondary.skill;
                        entry.rune = secondary.rune;
                        entry.element = secondary.element;
                        entry.damagePct = secondary.damagePct;
                        loaded[entry.spellId] = entry;
                    }
                    std::lock_guard<std::mutex> lock(dataMutex);
                    shells = std::move(loaded);
                    dataReady = true;
                    LOG_INFO("server.loading", "[DC combat] Loaded {} spell shells", shells.size());
                }
                catch (std::exception const& error)
                {
                    LOG_ERROR("server", "D3 combat startup failed: {}. Skill hits are disabled.", error.what());
                }
            }
        };

        // The shells carry a DUMMY effect, so the core lands the cast and does nothing.
        // This is where the cast becomes a hit: resolve the formula, pay and earn Fury,
        // then hand the number to the core so the client draws it.
        class CombatCastCheck final : public AllSpellScript
        {
        public:
            CombatCastCheck()
                : AllSpellScript("dc_combat_cast_check", {ALLSPELLHOOK_ON_SPELL_CHECK_CAST, ALLSPELLHOOK_ON_CAST})
            {
            }
            void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override
            {
                auto player = caster->ToPlayer();
                auto row = Shells::FindAbility(info->Id);
                // Another cast leaves Whirlwind channelling: its record carries
                // SPELL_ATTR5_ALLOW_ACTION_DURING_CHANNEL, and Abilities' update stops the state with the channel.
                // The cast events of the item powers (Band of Might, In-geom's cooldowns): a skill the player pressed, after the core has
                // installed its cooldown.
                if (player && row && !spell->IsTriggered())
                    ItemPowers::Cast(player, info->Id);
            }
            void OnSpellCheckCast(Spell* spell, bool, SpellCastResult& result) override
            {
                Player* player = spell->GetCaster()->ToPlayer();
                if (!HitsThroughCombat(player) || result != SPELL_CAST_OK)
                    return;
                if (!Slotted(player, spell->GetSpellInfo()->Id))
                {
                    result = SPELL_FAILED_NOT_KNOWN;
                    return;
                }
                // Archon form: its abilities only while transformed, and the
                // Wizard's own skills not while they are replaced.
                if (!spell->IsTriggered() && !Wizard::CanCast(player, spell->GetSpellInfo()->Id))
                {
                    result = SPELL_FAILED_NOT_READY;
                    return;
                }
                if (!spell->IsTriggered() && !Monk::CanCast(player, spell->GetSpellInfo()->Id))
                {
                    result = SPELL_FAILED_NO_VALID_TARGETS;
                    return;
                }
                if (!spell->IsTriggered())
                    if (SpellCastResult const refused = Crusader::CanCast(player, spell->GetSpellInfo()->Id);
                        refused != SPELL_CAST_OK)
                    {
                        result = refused;
                        return;
                    }
                if (!spell->IsTriggered())
                    if (SpellCastResult const refused = Necromancer::CanCast(
                            player, spell->GetSpellInfo()->Id,
                            spell->m_targets.HasDst() ? spell->m_targets.GetDstPos() : nullptr,
                            spell->m_targets.GetUnitTarget());
                        refused != SPELL_CAST_OK)
                    {
                        result = refused;
                        return;
                    }
                if (!spell->IsTriggered())
                    if (SpellCastResult const refused = DemonHunter::CanCast(player, spell->GetSpellInfo()->Id);
                        refused != SPELL_CAST_OK)
                    {
                        result = refused;
                        return;
                    }
                if (Abilities::Toggle(player, spell->GetSpellInfo()->Id))
                {
                    result=SPELL_FAILED_DONT_REPORT;
                    return;
                }
                if (!spell->IsTriggered() && Monk::Toggle(player, spell->GetSpellInfo()->Id))
                {
                    result = SPELL_FAILED_DONT_REPORT;
                    return;
                }
                if (!spell->IsTriggered() && WitchDoctor::Toggle(player, spell->GetSpellInfo()->Id))
                {
                    result = SPELL_FAILED_DONT_REPORT;
                    return;
                }
                bool whirlwind = false, channel = false;
                {
                    std::lock_guard<std::mutex> lock(dataMutex);
                    auto found = shells.find(spell->GetSpellInfo()->Id);
                    if (found == shells.end() || found->second.passive)
                        return;
                    if (!PrimaryData::Find(found->first) && !found->second.targeting.Ready())
                    {
                        result = SPELL_FAILED_NOT_READY;
                        return;
                    }
                    whirlwind = Abilities::PaysByTick(found->second.skill);
                    channel = WizardChannel(found->second);
                }
                // Recovery before Fury, for every skill and not just the primaries.
                // The core's own cooldown check runs AFTER this hook (Spell::CheckCast
                // calls OnSpellCheckCast first, then tests HasSpellCooldown), so a
                // press that was both on cooldown and unaffordable used to answer
                // "Not enough Fury" - the Fury was never the reason it was refused.
                // A primary's 1/APS recovery is that same cooldown, installed by its
                // last successful cast; no attack speed at all means there is no rate
                // to cast at. Both are checked before SpellStart and before any Fury
                // or stack change, so a refused press plays nothing and costs nothing.
                if (!spell->IsTriggered() &&
                    (player->HasSpellCooldown(spell->GetSpellInfo()->Id) ||
                     (PrimaryData::Find(spell->GetSpellInfo()->Id) &&
                      AttacksPerSecond(player, spell->GetSpellInfo()->Id) <= 0)))
                {
                    result = SPELL_FAILED_NOT_READY;
                    return;
                }
                // A charge is not a resource the core knows about, and a cast
                // with no charge left must be refused here: once the core has
                // gone past this hook it charges the record's cost.
                if (!Abilities::Ready(player, spell->GetSpellInfo()->Id))
                {
                    result = SPELL_FAILED_NO_POWER;
                    return;
                }
                // Fury itself is the core's check now (Spell::CheckPower, on the
                // record's cost with the player's SPELLMOD_COST auras applied),
                // and it runs right after this hook. Whirlwind is the exception
                // to that: its record carries no cost, so the core
                // would let it start with an empty pool and the first tick
                // would end it. That first tick is checked here instead.
                if (whirlwind && !spell->IsTriggered() &&
                    CurrentFury(player) + 0.0001 < WhirlwindTickCost(player, spell->GetSpellInfo()->Id))
                    result = SPELL_FAILED_NO_POWER;
                // The Wizard's channels have the same shape:
                // no cost on the record, so the first tick - paid
                // the moment the channel starts - is checked here.
                if (channel && !spell->IsTriggered() &&
                    Resources::Units(player, Resources::ArcanePower) + 0.0001 <
                        Resources::ToUnits(Resources::ArcanePower, ChannelTickCost(player, spell->GetSpellInfo()->Id)))
                    result = SPELL_FAILED_NO_POWER;
                // Read-only preflight: nothing here takes Fury or a charge.
                // Reject before the core sends spell-start/go and plays a visual.
            }
        };
    } // namespace

    double& CopyFactor()
    {
        thread_local double factor = 1.0;
        return factor;
    }

    void RegisterScripts()
    {
        Primaries::RegisterScripts();
        Abilities::RegisterScripts();
        Abilities::RegisterMovementScripts();
        Passives::RegisterScripts();
        Pylons::RegisterScripts();
        DamageBoost::RegisterScripts();
        GroundDevice::RegisterScripts();
        CostCut::RegisterScripts();
        BuffValues::RegisterScripts();
        RegisterLifeCommands();
        GemPowers::RegisterScripts();
        ItemPowers::RegisterScripts();
        Classes::Ancients::RegisterScripts();
        Wizard::RegisterScripts();
        Monk::RegisterScripts();
        Crusader::RegisterScripts();
        Necromancer::RegisterScripts();
        DemonHunter::RegisterScripts();
        WitchDoctor::RegisterScripts();
        Shaman::RegisterScripts();
        Corpses::RegisterScripts();
        Minions::RegisterScripts();
        Necromancer::Pets::RegisterScripts();
        WitchDoctor::Pets::RegisterScripts();
        new CombatWorld();
        new CombatCastCheck();
        RegisterResolveScripts();
        RegisterHookScripts();
        RegisterCommandScripts();
    }
} // namespace DC::Combat
