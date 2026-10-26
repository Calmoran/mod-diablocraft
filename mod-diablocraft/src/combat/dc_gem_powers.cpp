#include "dc_gem_powers.h"
#include "dc_buff_values.h"
#include "dc_combat.h"
#include "dc_control_immunity.h"
#include "dc_gem_power_math.h"
#include "dc_item_powers.h"
#include "dc_passives.h"
#include "dc_proc_math.h"
#include "dc_spell_numbers.h"
#include "dc_spell_shells.h"
#include "../classes/dc_classes.h"
#include "../classes/wizard/dc_wizard.h"
#include "../common/dc_tunables.h"
#include "../items/dc_inventory.h"
#include "../items/dc_items.h"
#include "../monsters/dc_monster_ai.h"
#include "../rifts/dc_rifts.h"
#include "../stats/dc_stats.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Item.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "Timer.h"
#include "Unit.h"
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::GemPowers
{
    namespace
    {
        struct State
        {
            std::vector<LegendaryGemItem::Socketed> active;
            GemPower::Powers powers;
        };

        // The buffs that run on a clock, per player; only Gogok's reaches the sheet and so needs the update hook.
        struct Timed
        {
            GemPower::Stacks powerful, taeguk, gogok, invigorating;
            GemPower::StaggerPool stagger;      // Moratorium: damage put off and what it still owes
            std::uint32_t staggerPayAt = 0;     // the next moment the pool is paid
            ObjectGuid staggerFrom;             // whose hit was put off last: the payment is dealt in its name
            std::uint32_t tauntTick = 0;        // Boyarsky: the world tick of the last taunt (one per cast)
            // Group D, the rank-25 bonuses.
            GemPower::Sheeted published;        // what the sheet holds of GemPower::Wanted() now
            unsigned bleeding = 0;              // Blood Frenzy: the enemies in reach with Pain Enhancer's bleed on, as last counted
            std::uint32_t refreshAt = 0;        // the next look at the enemies and the Life (gem_aura_refresh_ms); 0: none yet
            std::uint32_t smiteAt = 0;          // Mirinae: the next smite of its own clock; 0: none yet
            std::uint32_t lastDamageMs = 0;     // Molten Wildebeest: when the player last took damage
            bool shieldArmed = false;           // ... and a damage has been taken since the last shield
            bool immune = false;                // Invigorating Gemstone: the control immunity is on
        };

        // Bane of the Stricken's stacks live on the enemy they are on, one count per attacking player, and go
        // with it; the sheet gives no duration for them (the debuff lasts as long as the enemy does).
        struct StrickenStacks : DataMap::Base
        {
            std::unordered_map<std::uint64_t, unsigned> byPlayer;
        };
        constexpr char const* StrickenKey = "DCGemStricken";

        // True while PayStagger's damage is being dealt (the hooks it reaches run inside the call).
        thread_local bool payingStagger = false;

        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;
        std::unordered_map<std::uint64_t, Timed> timed;

        // Sheet contribution ids: the high bits keep them clear of Items' (itemGuid << 16 | seq).
        constexpr std::uint64_t IdBase = 0x4C47454D00000000ull; // "LGEM"

        bool CarriesLegendaryGem(Items::Instance const& instance)
        {
            for (Items::Affix const& affix : instance.affixes)
                if (affix.kind == "gem" && affix.legendaryRank)
                    return true;
            return false;
        }

        void AddGems(std::vector<LegendaryGemItem::Socketed>& worn, Items::Instance const& instance)
        {
            for (Items::Affix const& affix : instance.affixes)
                if (affix.kind == "gem" && affix.legendaryRank)
                    worn.push_back({affix.affixId, *affix.legendaryRank});
        }

        // What is worn, with the changed item taken out or put in by hand: the equip hooks run before or
        // after the core moves the item, so the slot is never trusted for it. A broken item contributes
        // nothing, the same as its other contributions (Items::Apply).
        std::vector<LegendaryGemItem::Socketed> Worn(Player* player, Item* changed, bool equipping,
                                                     Items::Instance const& instance)
        {
            std::vector<LegendaryGemItem::Socketed> worn;
            for (std::uint8_t slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
                if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot);
                    item && item != changed && !item->IsBroken())
                    if (std::optional<Items::Instance> other = Items::Get(item->GetGUID().GetCounter()))
                        AddGems(worn, *other);
            if (equipping)
                AddGems(worn, instance);
            return worn;
        }

        // The spell shell a gem's power casts or applies (data/legendary_gem_spells.csv); 0 when not listed.
        std::uint32_t ShellOf(char const* gemId)
        {
            return Shells::GemShellFor(gemId);
        }

        // A hit of a gem's own spell never rolls another gem's chance or poisons or chills: a proc does not proc.
        bool IsGemShell(std::uint32_t spellId)
        {
            for (auto const& row : Shells::GemShells)
                if (row.id == spellId)
                    return true;
            return false;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("combat", name);
        }

        // The cached powers of a player; empty when no gem counts.
        GemPower::Powers PowersOf(Player const* player)
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = player ? states.find(player->GetGUID().GetRawValue()) : states.end();
            return found == states.end() ? GemPower::Powers{} : found->second.powers;
        }

        // Legacy of Dreams: the legendary items that count now (ItemPowers keeps the worn ones and the set counter); 0 without the gem.
        unsigned LegacyItems(Player const* player, GemPower::Powers const& powers)
        {
            if (powers.legacyDamagePct <= 0 && powers.legacyReductionPct <= 0)
                return 0;
            ItemPowers::Legendaries const worn = ItemPowers::WornLegendaries(player);
            return GemPower::LegacyItems(powers, worn.items, worn.ancients, worn.setBonusOn);
        }

        // Enforcer's pet list: dc_legendary_gem_pet, generated from data/legendary_gem_pets.csv. Read once. No row, or no
        // table yet, is a list with no pets, and the gem then does nothing.
        GemPower::Pets const& EnforcerPets()
        {
            static GemPower::Pets const pets = []
            {
                GemPower::Pets list;
                if (QueryResult rows = WorldDatabase.Query("SELECT skill, creature_entry FROM dc_legendary_gem_pet WHERE gem_id = '{}'",
                                                           GemPower::Enforcer))
                    do
                    {
                        Field* f = rows->Fetch();
                        GemPower::AddPet(list, f[0].Get<std::string>(),
                                         f[1].IsNull() ? std::nullopt : std::optional<std::uint32_t>(f[1].Get<std::uint32_t>()));
                    } while (rows->NextRow());
                return list;
            }();
            return pets;
        }

        // One of our auras on `target` for `seconds`: the record carries no duration, the gem's rank gives it.
        // Null when the target is gone or immune (the core refuses the aura).
        Aura* Put(Player* player, Unit* target, std::uint32_t shell, double seconds)
        {
            if (!player || !target || !shell || seconds <= 0 || !target->IsAlive())
                return nullptr;
            Aura* aura = player->AddAura(shell, target);
            if (aura)
            {
                int32 const milliseconds = int32(std::llround(seconds * 1000.0));
                aura->SetMaxDuration(milliseconds);
                aura->SetDuration(milliseconds);
            }
            return aura;
        }

        void HealSelf(Player* player, std::uint32_t shell, double amount)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(shell);
            if (!player || !info || !player->IsAlive() || amount < 1)
                return;
            HealInfo heal(player, player, uint32(std::min(amount, double(UINT32_MAX))), info, SPELL_SCHOOL_MASK_HOLY);
            player->HealBySpell(heal);
        }

        // The buff bar's copy of a gem effect (data/legendary_gem_buffs.csv): `stacks` of the gem's buff
        // record for `seconds` more (0 seconds: no timer, it stays until it is taken off). No stacks takes it off, so does
        // the other rank band's record, and the addon is told it is gone. `values` are the addon line's numbers
        // (docs/contracts/buff-values-messages.md); none when the record's own text is the whole tooltip. Never called with
        // `mutex` held: the core's aura hooks run inside AddAura.
        void ShowBuff(Player* player, char const* gem, bool rank25, unsigned stacks, double seconds,
                      std::vector<double> const& values = {})
        {
            if (!player)
                return;
            std::uint32_t const wanted = stacks && player->IsAlive() ? Shells::GemBuffFor(gem, rank25) : 0;
            for (auto const& row : Shells::GemBuffs)
                if (row.id != wanted && Shells::SameGem(row.gem, gem))
                {
                    player->RemoveAurasDueToSpell(row.id);
                    BuffValues::Clear(player, row.id);
                }
            if (!wanted)
                return;
            Aura* aura = player->GetAura(wanted);
            if (!aura)
                aura = player->AddAura(wanted, player);
            if (!aura)
                return;
            std::uint8_t const shown = std::uint8_t(std::min<unsigned>(stacks, std::max<unsigned>(1, aura->GetSpellInfo()->StackAmount)));
            if (aura->GetStackAmount() != shown)
                aura->SetStackAmount(shown);
            if (seconds > 0)
            {
                int32 const milliseconds = int32(std::llround(seconds * 1000.0));
                aura->SetMaxDuration(milliseconds);
                aura->SetDuration(milliseconds);
            }
            if (!values.empty())
                BuffValues::Set(player, wanted, values);
        }

        // Gogok of Swiftness: the rank-25 record also states the Cooldown Reduction per stack. The Dodge per stack depends
        // on the rank, so its total is the addon line.
        void ShowGogok(Player* player, GemPower::Powers const& powers, unsigned stacks, double seconds)
        {
            ShowBuff(player, GemPower::Gogok, powers.gogokCooldownPerStack > 0, stacks, seconds,
                     {GemPower::DodgePct(powers, stacks)});
        }

        // Taeguk: the damage per stack depends on the rank (the addon line); the rank-25 record states the Armor per stack.
        void ShowTaeguk(Player* player, GemPower::Powers const& powers, unsigned stacks, double seconds)
        {
            ShowBuff(player, GemPower::Taeguk, powers.taegukArmorPctPerStack > 0, stacks, seconds,
                     {GemPower::AdditivePct(powers, stacks)});
        }

        void ShowInvigorating(Player* player, GemPower::Powers const& powers, unsigned stacks, double seconds)
        {
            ShowBuff(player, GemPower::Invigorating, false, stacks, seconds, {GemPower::HealingPct(powers, stacks)});
        }

        // Moratorium: on while damage is owed, and what is owed is the addon line.
        void ShowDebt(Player* player, double owed)
        {
            ShowBuff(player, GemPower::Moratorium, false, owed > 0 ? 1 : 0, 0, {owed});
        }

        // Mirinae: "smite a nearby enemy". Which enemy is a random one in `gem_mirinae_smite_range_yards` (no number
        // in the sheet: a tunable, and with none set the smite does not fire).
        void Smite(Player* player, GemPower::Powers const& powers)
        {
            std::uint32_t const shell = ShellOf(GemPower::Mirinae);
            double const range = Tune("gem_mirinae_smite_range_yards");
            if (!shell || range <= 0)
                return;
            std::vector<Unit*> const enemies = Enemies(player, shell, player->GetPosition(), range);
            if (enemies.empty())
                return;
            Unit* const victim = enemies[urand(0, uint32(enemies.size()) - 1)];
            if (Strike(player, victim, shell, powers.mirinaePct))
                HealSelf(player, shell, player->GetMaxHealth() * powers.mirinaeHealPct / 100.0);
        }

        // Efficacious Toxin and Pain Enhancer: the damage-over-time aura on the enemy, lasting the gem's seconds.
        void Dot(Player* player, Unit* target, char const* gemId, double seconds)
        {
            Put(player, target, ShellOf(gemId), seconds);
        }

        // Iceblink: a Chill is a slow aura. 60% (gem_iceblink_chill_slow_pct) plus the gem's additional slow; no
        // duration set (gem_iceblink_chill_seconds) is no Chill.
        void Chill(Player* player, Unit* target, GemPower::Powers const& powers)
        {
            double const seconds = Tune("gem_iceblink_chill_seconds"), base = Tune("gem_iceblink_chill_slow_pct");
            if (base <= 0)
                return;
            if (Aura* aura = Put(player, target, ShellOf(GemPower::Iceblink), seconds))
                if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                    effect->ChangeAmount(-int32(std::lround(base + powers.iceblinkSlowPct)));
        }

        // What a landed hit sets off. `coefficient` is the proc coefficient of the spell that landed it: no
        // coefficient is no chance (dc_proc_math.h), and a hit of a gem's own spell sets nothing off.
        void Procs(Player* player, Unit* target, std::uint32_t spellId, unsigned school, GemPower::Powers const& powers)
        {
            if (!spellId || IsGemShell(spellId))
                return;
            // Simplicity's Strength, rank 25: a Primary skill's hit heals, a killing blow's too.
            if (powers.simplicityHealPct > 0 && Classes::CategoryOf(spellId) == "Primary")
                HealSelf(player, ShellOf(GemPower::Simplicity), player->GetMaxHealth() * powers.simplicityHealPct / 100.0);
            if (!target || !target->IsAlive())
                return;
            if (!school)
                if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
                    school = info->GetSchoolMask();
            std::optional<double> const coefficient = Combat::ProcCoefficient(spellId);
            auto const roll = [](float pct) { return roll_chance_f(pct); };
            if (powers.mirinaePct > 0 && Proc::Rolls(coefficient, powers.mirinaeChancePct, roll))
                Smite(player, powers);
            if (powers.wreathPct > 0 && Proc::Rolls(coefficient, powers.wreathChancePct, roll))
                if (Put(player, player, ShellOf(GemPower::Wreath), powers.wreathSeconds))
                    BuffValues::Set(player, ShellOf(GemPower::Wreath), {powers.wreathPct, powers.wreathMovePct});
            if (powers.toxinPct > 0)
                Dot(player, target, GemPower::Toxin, powers.toxinSeconds);
            if (powers.zeiStunChancePct > 0 && Proc::Rolls(coefficient, powers.zeiStunChancePct, roll))
                Put(player, target, ShellOf(GemPower::Zei), powers.zeiStunSeconds * ItemPowers::StunFactor(player));
            if (powers.iceblinkSlowPct > 0 && (school & SPELL_SCHOOL_MASK_FROST))
                Chill(player, target, powers);
            // "The first enemy hit by your Primary skills": the first hit of this world tick, so one enemy of each
            // cast, not each enemy an area skill reaches.
            if (powers.boyarskyTauntSeconds > 0 && Classes::CategoryOf(spellId) == "Primary")
            {
                std::uint32_t const tick = std::uint32_t(GameTime::GetGameTimeMS().count());
                bool first = false;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    Timed& buffs = timed[player->GetGUID().GetRawValue()];
                    first = buffs.tauntTick != tick;
                    buffs.tauntTick = tick;
                }
                if (first)
                    Put(player, target, ShellOf(GemPower::Boyarsky), powers.boyarskyTauntSeconds);
            }
        }

        void Contribute(std::uint64_t playerGuid, Stat stat, std::uint64_t id, double value, Bucket bucket = Bucket::Flat,
                        Element element = Element::Physical)
        {
            Stats::RemoveContribution(playerGuid, Source::Gems, stat, IdBase + id);
            if (value > 0)
                Stats::AddContribution(playerGuid, {Source::Gems, stat, IdBase + id, value, bucket, element});
        }

        // Esoteric Alteration's five resistances, in GemPower::Dynamic::resistBase's order. RemoveContribution has no
        // element key, so each one is its own contribution id.
        constexpr Element Resisted[5] = {Element::Fire, Element::Cold, Element::Lightning, Element::Poison, Element::Arcane};
        constexpr std::uint64_t ResistId = 160;

        // Bane of the Trapped's aura lasts this many refreshes (gem_aura_refresh_ms): refreshed each time, so an
        // enemy that leaves the radius sheds it within two.
        constexpr double SlowLastsRefreshes = 2.0;

        // The sheet contributions that follow a gem's state and not its rank alone (GemPower::Wanted): Gogok's Attack
        // Speed and Cooldown Reduction, Taeguk's Armor, Blood Frenzy, the Wreath's Movement Speed, the Powerful's elite
        // damage and Esoteric Alteration's resistances. Published when they change and never otherwise, so calling it
        // is cheap. `wreath` says whether the Wreath of Lightning is on the player (-1: ask the unit; an aura handler
        // that runs while the aura is leaving says it).
        void Sync(Player* player, int wreath = -1)
        {
            if (!player)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            GemPower::Powers powers;
            GemPower::Dynamic now;
            GemPower::Sheeted before;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = states.find(guid);
                if (found == states.end())
                    return;
                powers = found->second.powers;
                Timed& buffs = timed[guid];
                std::uint32_t const clock = getMSTime();
                now.gogok = GemPower::Live(buffs.gogok, clock);
                now.taeguk = GemPower::Live(buffs.taeguk, clock);
                now.bleeding = buffs.bleeding;
                before = buffs.published;
            }
            now.wreath = powers.wreathMovePct > 0 && (wreath >= 0 ? wreath > 0 : player->HasAura(ShellOf(GemPower::Wreath)));
            if (powers.esotericResistPct > 0)
            {
                now.belowLife = player->GetHealthPct() < powers.esotericBelowLifePct;
                if (auto const sheet = Stats::Get(guid))
                    for (int i = 0; i < 5; ++i)
                        now.resistBase[i] = std::max(0.0, sheet->resistance[Index(Resisted[i])] - before.resist[i]);
            }
            // Esoteric Alteration's buff follows the Life, not the sheet's change, so it is settled before the early return.
            if (powers.esotericResistPct > 0 || player->HasAura(Shells::GemBuffFor(GemPower::Esoteric, false)))
                ShowBuff(player, GemPower::Esoteric, false, powers.esotericResistPct > 0 && now.belowLife ? 1 : 0, 0);
            GemPower::Sheeted const want = GemPower::Wanted(powers, now);
            if (want == before)
                return;
            {
                std::lock_guard<std::mutex> lock(mutex);
                timed[guid].published = want;
            }
            auto const publish = [&](Stat stat, std::uint64_t id, double was, double is, Bucket bucket = Bucket::Flat,
                                     Element element = Element::Physical)
            {
                if (was != is)
                    Contribute(guid, stat, id, is, bucket, element);
            };
            publish(Stat::AttackSpeed, 8, before.gogokAttackSpeed, want.gogokAttackSpeed);
            publish(Stat::CooldownReduction, 8, before.gogokCooldown, want.gogokCooldown);
            publish(Stat::Armor, 15, before.taegukArmor, want.taegukArmor, Bucket::Percent);
            publish(Stat::AttackSpeed, 6, before.frenzyAttackSpeed, want.frenzyAttackSpeed);
            publish(Stat::MovementSpeed, 4, before.wreathMovement, want.wreathMovement, Bucket::Uncapped);
            publish(Stat::EliteDamage, 1, before.eliteDamage, want.eliteDamage);
            for (int i = 0; i < 5; ++i)
                publish(Stat::SingleResistance, ResistId + i, before.resist[i], want.resist[i], Bucket::Flat, Resisted[i]);
            Stats::Recompute(player);
            // The cooldown is charged by the core's own aura, which is rebuilt from the sheet (Passives::RefreshModifiers).
            if (want.gogokCooldown != before.gogokCooldown)
                Passives::RefreshModifiers(player);
            // An open character screen redraws from the pushed sheet; it asks for one only on its own events, so a
            // gem's change (Esoteric Alteration's resistances) stayed unseen until it was reopened.
            Inventory::PushSheet(player);
        }

        // Invigorating Gemstone, rank 25: "immune from control impairing effects", the shared list (ControlImmunity::Set,
        // under the key 0: the core's own immunity lists, the mechanics Passives counts as control and the aura types that put
        // them on). Held in memory by the unit, so a new login starts without it and the first Refresh puts it back. Turning
        // it on strips what is already on the player.
        void SetControlImmunity(Player* player, bool on)
        {
            bool changed = false;
            {
                std::lock_guard<std::mutex> lock(mutex);
                Timed& buffs = timed[player->GetGUID().GetRawValue()];
                changed = buffs.immune != on;
                buffs.immune = on;
            }
            if (!changed)
                return;
            ControlImmunity::Set(player, 0, on);
        }

        // Molten Wildebeest's Gizzard, rank 25: the shield, an absorb aura whose amount is the gem's. The sheet gives it
        // no duration, so it stays until it is absorbed or the next one replaces it.
        void PutShield(Player* player, double amount)
        {
            std::uint32_t const shell = ShellOf(GemPower::Wildebeest);
            if (!shell || amount < 1)
                return;
            if (Aura* aura = player->AddAura(shell, player))
                if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                {
                    effect->ChangeAmount(int32(std::min(amount * ItemPowers::ShieldFactor(player), double(INT32_MAX))));
                    BuffValues::Set(player, shell, {double(effect->GetAmount())});
                }
        }

        // A damage taken (a monster's hit, or Moratorium's payment of one) restarts the quiet the shield waits for.
        void Hurt(Player* player)
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end() || found->second.powers.wildebeestShieldPct <= 0)
                return;
            Timed& buffs = timed[player->GetGUID().GetRawValue()];
            buffs.lastDamageMs = getMSTime();
            buffs.shieldArmed = true;
        }

        // The rank-25 powers that follow enemies, the Life and the clock, looked at on every update of a gem wearer.
        // Mirinae's own clock and Molten Wildebeest's quiet are cheap and read each time; the searches around the
        // player (Bane of the Trapped's aura, Blood Frenzy's count) and Sync's Life test run every
        // gem_aura_refresh_ms, and nothing runs when that row is blank. The two auras of the player's reach act only in
        // combat: a slow or a smite is for a fight, and neither should pull what has not noticed the player.
        void Upkeep(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            GemPower::Powers powers;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = states.find(guid);
                if (found == states.end())
                    return;
                powers = found->second.powers;
            }
            if (powers.trappedYards <= 0 && powers.painFrenzyPct <= 0 && powers.esotericResistPct <= 0 &&
                powers.wildebeestShieldPct <= 0 && powers.mirinaeEverySeconds <= 0)
                return;
            std::uint32_t const now = getMSTime();
            bool const fighting = player->IsInCombat();
            double const refreshMs = Tune("gem_aura_refresh_ms");
            bool smite = false, shield = false, refresh = false;
            {
                std::lock_guard<std::mutex> lock(mutex);
                Timed& buffs = timed[guid];
                if (powers.mirinaeEverySeconds > 0)
                {
                    // The first smite of a fight is one clock after it begins, never at once.
                    if (!fighting || !buffs.smiteAt)
                        buffs.smiteAt = now + static_cast<std::uint32_t>(std::llround(powers.mirinaeEverySeconds * 1000.0));
                    else if (static_cast<std::int32_t>(now - buffs.smiteAt) >= 0)
                    {
                        buffs.smiteAt = now + static_cast<std::uint32_t>(std::llround(powers.mirinaeEverySeconds * 1000.0));
                        smite = true;
                    }
                }
                if (!player->IsAlive())
                    buffs.shieldArmed = false;
                else if (GemPower::ShieldDue(powers, buffs.shieldArmed, now - buffs.lastDamageMs))
                {
                    buffs.shieldArmed = false;
                    shield = true;
                }
                if (refreshMs > 0 && (!buffs.refreshAt || static_cast<std::int32_t>(now - buffs.refreshAt) >= 0))
                {
                    buffs.refreshAt = now + static_cast<std::uint32_t>(std::llround(refreshMs));
                    refresh = true;
                }
            }
            if (smite)
                Smite(player, powers);
            if (shield)
                if (auto const sheet = Stats::Get(guid))
                    PutShield(player, GemPower::ShieldAmount(powers, (*sheet)[Stat::LifeRegen]));
            if (!refresh)
                return;
            if (powers.trappedYards > 0 && fighting)
            {
                std::uint32_t const shell = ShellOf(GemPower::Trapped);
                for (Unit* enemy : Enemies(player, shell, player->GetPosition(), powers.trappedYards))
                    // an enemy already fighting: the aura is for the fight, and putting a hostile aura on one that has
                    // not noticed the player could pull it
                    if (enemy->IsInCombat())
                        if (Aura* aura = Put(player, enemy, shell, SlowLastsRefreshes * refreshMs / 1000.0))
                            if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                                effect->ChangeAmount(-int32(std::lround(powers.trappedSlowPct)));
            }
            if (powers.painFrenzyPct > 0)
            {
                std::uint32_t const bleed = ShellOf(GemPower::Pain);
                unsigned bleeding = 0;
                for (Unit* enemy : Enemies(player, bleed, player->GetPosition(), powers.painFrenzyYards))
                    if (enemy->HasAura(bleed, player->GetGUID()))
                        ++bleeding;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    timed[guid].bleeding = bleeding;
                }
                // Blood Frenzy: one stack per bleeding enemy (the stack counter is a byte), no timer.
                ShowBuff(player, GemPower::Pain, false, std::min(bleeding, 255u), 0);
            }
            if (powers.wildebeestShieldPct > 0)
            {
                // The shield's amount falls as it absorbs; the buff's addon line follows it, and ends with it.
                std::uint32_t const shell = ShellOf(GemPower::Wildebeest);
                Aura* const shield = player->GetAura(shell);
                if (AuraEffect* effect = shield ? shield->GetEffect(EFFECT_0) : nullptr)
                    BuffValues::Set(player, shell, {double(effect->GetAmount())});
                else
                    BuffValues::Clear(player, shell);
            }
            Sync(player);
        }
    } // namespace

    void Refresh(Player* player, Item* changed, bool equipping, Items::Instance const& instance)
    {
        // Only an item that carries a legendary gem can change which gems count.
        if (!player || !changed || !CarriesLegendaryGem(instance))
            return;
        try
        {
            auto const active = LegendaryGemItem::Counted(Worn(player, changed, equipping, instance));
            GemPower::Powers const powers =
                GemPower::Resolve(active, [](std::string const& id) { return LegendaryGem::Find(id); });
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            {
                std::lock_guard<std::mutex> lock(mutex);
                states[guid] = {active, powers};
                // A gem taken off takes its running buff with it.
                Timed& buffs = timed[guid];
                if (powers.powerfulPct <= 0)
                    buffs.powerful = {};
                if (!powers.taeguk.max)
                    buffs.taeguk = {};
                if (!powers.gogok.max)
                    buffs.gogok = {};
                if (!powers.invigorating.max)
                    buffs.invigorating = {};
                if (powers.painFrenzyPct <= 0)
                    buffs.bleeding = 0;
                if (powers.wildebeestShieldPct <= 0)
                    buffs.shieldArmed = false;
            }
            // The buffs follow the gems: a gem taken off (its stacks were just emptied) or taken to or from rank 25
            // (the other record) changes which aura is on the bar.
            {
                GemPower::Stacks gogok, taeguk, invigorating, powerful;
                unsigned bleeding = 0;
                std::uint32_t const clock = getMSTime();
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    Timed const& buffs = timed[guid];
                    gogok = buffs.gogok;
                    taeguk = buffs.taeguk;
                    invigorating = buffs.invigorating;
                    powerful = buffs.powerful;
                    bleeding = buffs.bleeding;
                }
                auto const left = [clock](GemPower::Stacks const& stacks)
                { return std::max(0, static_cast<std::int32_t>(stacks.untilMs - clock)) / 1000.0; };
                ShowGogok(player, powers, GemPower::Live(gogok, clock), left(gogok));
                ShowTaeguk(player, powers, GemPower::Live(taeguk, clock), left(taeguk));
                ShowInvigorating(player, powers, GemPower::Live(invigorating, clock), left(invigorating));
                ShowBuff(player, GemPower::Powerful, false, GemPower::Live(powerful, clock), left(powerful));
                ShowBuff(player, GemPower::Pain, false, std::min(bleeding, 255u), 0);
            }
            Contribute(guid, Stat::LifeRegen, 17, powers.lifeRegen);
            Contribute(guid, Stat::Thorns, 20, powers.thorns);
            // Attack Speed, Cooldown Reduction, Armor, Movement Speed, elite damage and resistances: GemPower::Wanted.
            Sync(player);
            SetControlImmunity(player, powers.controlImmune);
            if (powers.wildebeestShieldPct <= 0)
                player->RemoveAurasDueToSpell(ShellOf(GemPower::Wildebeest));
            Stats::Recompute(player);
        }
        catch (std::exception const& error)
        {
            LOG_ERROR("module.dc.combat", "[DC gems] powers of {} not refreshed: {}", player->GetName(), error.what());
        }
    }

    std::vector<LegendaryGemItem::Socketed> Active(Player* player)
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto found = player ? states.find(player->GetGUID().GetRawValue()) : states.end();
        return found == states.end() ? std::vector<LegendaryGemItem::Socketed>{} : found->second.active;
    }

    double IncomingFactor(Player* player, unsigned schoolMask, bool melee)
    {
        GemPower::Powers const powers = PowersOf(player);
        return GemPower::IncomingFactor(powers, schoolMask == SPELL_SCHOOL_MASK_NORMAL, melee) *
               GemPower::LegacyIncomingFactor(powers, LegacyItems(player, powers));
    }

    void Multipliers(Player* player, DC::Combat::Factors& out)
    {
        GemPower::Powers const powers = PowersOf(player);
        if (unsigned const items = LegacyItems(player, powers))
            out.emplace_back("Legacy of Dreams", GemPower::LegacyFactor(powers, items));
    }

    double SkillFactor(Player* player, std::uint32_t spellId)
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto found = player ? states.find(player->GetGUID().GetRawValue()) : states.end();
        if (found == states.end() || found->second.powers.primaryDamagePct <= 0)
            return 1.0;
        // Torment's categories are the catalogue's (class_skill_categories.csv): every class's Primary.
        return GemPower::PrimaryFactor(found->second.powers, Classes::CategoryOf(spellId) == "Primary");
    }

    double PetFactor(Player* player, char const* skill)
    {
        GemPower::Powers const powers = PowersOf(player);
        if (powers.petDamagePct <= 0 || !skill)
            return 1.0;
        return GemPower::PetDamageFactor(powers, GemPower::IsPetSkill(EnforcerPets(), skill));
    }

    bool IsPetSkill(char const* skill)
    {
        return skill && GemPower::IsPetSkill(EnforcerPets(), skill);
    }

    void PetIncoming(Unit* victim, std::uint32_t& damage)
    {
        Creature* const pet = victim && damage ? victim->ToCreature() : nullptr;
        Unit* const owner = pet ? pet->GetOwner() : nullptr;
        Player* const player = owner ? owner->ToPlayer() : nullptr;
        if (!player)
            return;
        GemPower::Powers const powers = PowersOf(player);
        if (powers.petDefencePct <= 0)
            return;
        damage = static_cast<std::uint32_t>(
            std::llround(damage * GemPower::PetIncomingFactor(powers, GemPower::IsPetEntry(EnforcerPets(), pet->GetEntry()))));
    }

    void Hit(Player* player, Unit* target, std::uint32_t spellId, unsigned school)
    {
        if (!player || !target)
            return;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        std::uint32_t const now = getMSTime();
        GemPower::Powers powers;
        bool gogokChanged = false;
        unsigned gogokStacks = 0, invigoratingStacks = 0;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = states.find(guid);
            if (found == states.end())
                return;
            powers = found->second.powers;
            Timed& buffs = timed[guid];
            if (powers.gogok.max)
            {
                unsigned const before = GemPower::Live(buffs.gogok, now);
                GemPower::AddStack(buffs.gogok, now, powers.gogok.seconds, powers.gogok.max);
                gogokChanged = buffs.gogok.count != before;
                gogokStacks = buffs.gogok.count;
            }
            if (powers.invigorating.max)
            {
                GemPower::AddStack(buffs.invigorating, now, powers.invigorating.seconds, powers.invigorating.max);
                invigoratingStacks = buffs.invigorating.count;
            }
        }
        if (gogokChanged)
            Sync(player);
        // Every hit renews the 4 s and 5 s, so every hit renews the buffs' timers.
        if (gogokStacks)
            ShowGogok(player, powers, gogokStacks, powers.gogok.seconds);
        if (invigoratingStacks)
            ShowInvigorating(player, powers, invigoratingStacks, powers.invigorating.seconds);
        if (powers.strickenPctPerAttack > 0)
            if (Creature* creature = target->ToCreature())
                ++creature->CustomData.GetDefault<StrickenStacks>(StrickenKey)->byPlayer[guid];
        Procs(player, target, spellId, school, powers);
    }

    void Critical(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || !spellId || IsGemShell(spellId))
            return;
        GemPower::Powers const powers = PowersOf(player);
        if (powers.painPct > 0)
            Dot(player, target, GemPower::Pain, powers.painSeconds);
    }

    bool PayingStagger()
    {
        return payingStagger;
    }

    void Incoming(Player* player, Unit* attacker, std::uint32_t& damage)
    {
        if (!player || !damage)
            return;
        GemPower::Powers const mine = PowersOf(player);
        // Who is hitting. A poisoned enemy deals less (Gem of Efficacious Toxin, rank 25: the poisoner's gem, whoever the
        // victim is), and an elite deals less to a wearer of Bane of the Powerful (rank 25).
        double factor = 1.0;
        if (attacker)
        {
            static std::uint32_t const toxin = ShellOf(GemPower::Toxin);
            Aura* const poison = toxin ? attacker->GetAura(toxin) : nullptr;
            Unit* const caster = poison ? poison->GetCaster() : nullptr;
            if (Player* const poisoner = caster ? caster->ToPlayer() : nullptr)
                factor *= GemPower::WeakenedFactor(PowersOf(poisoner));
            if (mine.powerfulEliteDefencePct > 0)
            {
                Creature* const creature = attacker->ToCreature();
                factor *= GemPower::EliteIncomingFactor(mine, creature && (creature->isElite() || DC::Rifts::IsElitePack(creature)));
            }
        }
        if (factor != 1.0)
            damage = static_cast<std::uint32_t>(std::llround(damage * factor));
        if (!damage || (mine.staggerPct <= 0 && mine.wildebeestShieldPct <= 0))
            return;
        double debt = -1; // the whole debt after this hit; -1: the pool did not change
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end())
                return;
            Timed& buffs = timed[player->GetGUID().GetRawValue()];
            if (mine.wildebeestShieldPct > 0)
            {
                buffs.lastDamageMs = getMSTime();
                buffs.shieldArmed = true;
            }
            if (mine.staggerPct <= 0)
                return;
            double owed = 0;
            double const now = GemPower::StaggerSplit(found->second.powers, damage, owed);
            if (buffs.stagger.entries.empty())
                buffs.staggerPayAt = getMSTime(); // the first payment is due as soon as a debt exists
            buffs.stagger.Add(owed, found->second.powers.staggerSeconds, getMSTime());
            if (owed > 0 && attacker)
                buffs.staggerFrom = attacker->GetGUID();
            damage = static_cast<std::uint32_t>(std::llround(now));
            if (owed > 0)
                debt = buffs.stagger.Owed();
        }
        if (debt >= 0)
            ShowDebt(player, debt);
    }

    double ChillBonus(Player const* player)
    {
        return PowersOf(player).iceblinkSlowPct;
    }

    void ChannelSpent(Player* player)
    {
        if (!player)
            return;
        bool armor = false;
        GemPower::Powers powers;
        unsigned count = 0;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = states.find(player->GetGUID().GetRawValue());
            if (found == states.end() || !found->second.powers.taeguk.max)
                return;
            powers = found->second.powers;
            GemPower::StackBuff const& taeguk = powers.taeguk;
            GemPower::Stacks& stacks = timed[player->GetGUID().GetRawValue()].taeguk;
            unsigned const before = GemPower::Live(stacks, getMSTime());
            GemPower::AddStack(stacks, getMSTime(), taeguk.seconds, taeguk.max);
            armor = powers.taegukArmorPctPerStack > 0 && stacks.count != before;
            count = stacks.count;
        }
        if (armor)
            Sync(player); // rank 25: the stack is Armor on the sheet
        ShowTaeguk(player, powers, count, powers.taeguk.seconds);
    }

    double TargetFactor(Player* player, Unit* target)
    {
        if (!player)
            return 1.0;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        GemPower::Powers powers;
        bool powerful = false;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = states.find(guid);
            if (found == states.end())
                return 1.0;
            powers = found->second.powers;
            if (auto buffs = timed.find(guid); buffs != timed.end())
                powerful = GemPower::Live(buffs->second.powerful, getMSTime()) > 0;
        }
        bool trapped = false, boss = false;
        unsigned stricken = 0;
        double yards = 0;
        if (target)
        {
            yards = player->GetExactDist(target);
            // Bane of the Stricken, rank 25: a boss, or a Rift Guardian (the boss test the loot uses, and the rift's own).
            if (Creature* creature = target->ToCreature(); creature && powers.strickenBossPct > 0)
                boss = creature->isWorldBoss() || creature->IsDungeonBoss() || DC::Rifts::IsGuardianEntry(creature->GetEntry());
            trapped = powers.trappedPct > 0 && ControlImmunity::Impaired(target);   // Bane of the Trapped: the control-impairing mechanics, on the enemy hit
            if (Creature* creature = target->ToCreature(); creature && powers.strickenPctPerAttack > 0)
                if (auto* stacks = creature->CustomData.Get<StrickenStacks>(StrickenKey))
                    if (auto mine = stacks->byPlayer.find(guid); mine != stacks->byPlayer.end())
                        stricken = mine->second;
        }
        return GemPower::StandaloneFactor(powers, powerful, trapped, stricken, yards, boss);
    }

    double TargetBonus(Unit* target)
    {
        // "All enemies you poison take 10% increased damage from all sources": whoever hits an enemy that carries a
        // Toxin poison gets the poisoner's number.
        static std::uint32_t const toxin = ShellOf(GemPower::Toxin);
        Aura* const poison = target && toxin ? target->GetAura(toxin) : nullptr;
        Unit* const caster = poison ? poison->GetCaster() : nullptr;
        Player* const poisoner = caster ? caster->ToPlayer() : nullptr;
        return poisoner ? GemPower::VictimTakesMorePct(PowersOf(poisoner)) : 0.0;
    }

    double CritBonus(Player* player, Unit* target)
    {
        // Iceblink, rank 25: an enemy this player's Chill is on (the gem's own, or the Wizard's) is likelier to crit.
        double crit = 0.0;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = player ? states.find(player->GetGUID().GetRawValue()) : states.end();
            if (found == states.end())
                return 0.0;
            crit = found->second.powers.iceblinkCritPct;
        }
        if (crit <= 0 || !target)
            return 0.0;
        bool const chilled = target->HasAura(ShellOf(GemPower::Iceblink), player->GetGUID()) || Wizard::ChilledBy(player, target);
        return chilled ? crit : 0.0;
    }

    double DamageBonus(Player* player)
    {
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player ? player->GetGUID().GetRawValue() : 0;
        auto found = states.find(guid);
        auto buffs = timed.find(guid);
        if (found == states.end() || buffs == timed.end())
            return 0.0;
        return GemPower::AdditivePct(found->second.powers, GemPower::Live(buffs->second.taeguk, getMSTime()));
    }

    double Dodge(Player const* player)
    {
        std::lock_guard<std::mutex> lock(mutex);
        std::uint64_t const guid = player ? player->GetGUID().GetRawValue() : 0;
        auto found = states.find(guid);
        auto buffs = timed.find(guid);
        if (found == states.end() || buffs == timed.end())
            return 0.0;
        return GemPower::DodgePct(found->second.powers, GemPower::Live(buffs->second.gogok, getMSTime()));
    }

    namespace
    {
        // The first Refresh after login (Items::Apply on each worn item) fills the cache; logout empties it.
        // No login hook: its order against Items' own is not ours to rely on.
        class Cache final : public PlayerScript
        {
        public:
            Cache()
                : PlayerScript("dc_gem_powers_cache",
                               {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_CREATURE_KILL})
            {
            }
            void OnPlayerLogout(Player* player) override
            {
                Forget(player);
            }

            void OnPlayerUpdate(Player* player, uint32) override
            {
                PayStagger(player);
                LapseGogok(player);
                Upkeep(player);
            }

            // Moratorium's debt comes due a little at a time (every `period` of its record, the combat.csv
            // gem_moratorium_pay_period_ms), as one damage line of the gem's own spell, dealt to the player in the
            // name of whoever hit last (so a lethal payment is that monster's kill, Hardcore's too, and a Thorns or
            // Revenge reader can tell it from a hit by PayingStagger). The armor, resistance and block were taken
            // before the share was put off; the shields were not, so they are asked here, the way DealMonsterHit asks
            // them. The debt of a player who died is gone.
            static void PayStagger(Player* player)
            {
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                std::uint32_t const shell = ShellOf(GemPower::Moratorium);
                double due = 0, debt = 0; // debt: what is still owed after this payment
                bool died = false;
                ObjectGuid from;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto buffs = timed.find(guid);
                    if (buffs == timed.end() || buffs->second.stagger.entries.empty())
                        return;
                    std::uint32_t const now = getMSTime();
                    if (!player->IsAlive())
                    {
                        buffs->second.stagger = {};
                        died = true;
                    }
                    else
                    {
                        SpellInfo const* info = sSpellMgr->GetSpellInfo(shell);
                        if (!info || static_cast<std::int32_t>(now - buffs->second.staggerPayAt) < 0)
                            return;
                        buffs->second.staggerPayAt = now + std::max<std::uint32_t>(info->Effects[EFFECT_0].Amplitude, 1u);
                        due = buffs->second.stagger.Pay(now);
                        debt = buffs->second.stagger.Owed();
                        from = buffs->second.staggerFrom;
                    }
                }
                // The debt on the buff bar follows the pool: what is left now, and gone when it is paid (or the player is).
                ShowDebt(player, died ? 0 : debt);
                if (died)
                    return;
                SpellInfo const* info = sSpellMgr->GetSpellInfo(shell);
                std::uint32_t const dealt = static_cast<std::uint32_t>(std::llround(due));
                if (!info || !dealt)
                    return;
                // ponytail: a hitter gone from the map (despawned) leaves the payment with no attacker and no log
                // line; Hardcore then reads "something unknown". Keep the name on the pool if that ever shows.
                Unit* source = !from.IsEmpty() ? ObjectAccessor::GetUnit(*player, from) : nullptr;
                // The same absorb call DealMonsterHit makes: Normal school so no resistance roll, every shield absorbs.
                DamageInfo absorbing(source, player, dealt, info, SPELL_SCHOOL_MASK_NORMAL, SPELL_DIRECT_DAMAGE);
                Unit::CalcAbsorbResist(absorbing);
                SpellNonMeleeDamage log(source, player, info, info->GetSchoolMask());
                log.damage = absorbing.GetDamage();
                log.absorb = absorbing.GetAbsorb();
                log.cleanDamage = log.damage;
                log.physicalLog = info->GetSchoolMask() == SPELL_SCHOOL_MASK_NORMAL;
                payingStagger = true;
                if (source)
                {
                    source->SendSpellNonMeleeDamageLog(&log);
                    source->DealSpellDamage(&log, true);
                }
                else
                {
                    CleanDamage clean(log.cleanDamage, log.absorb, BASE_ATTACK, MELEE_HIT_NORMAL);
                    Unit::DealDamage(nullptr, player, log.damage, &clean, SPELL_DIRECT_DAMAGE,
                                     SpellSchoolMask(log.schoolMask), info, true);
                }
                payingStagger = false;
                Hurt(player); // the payment is damage taken: it restarts Molten Wildebeest's quiet
            }

            // Gogok's Attack Speed and Cooldown Reduction and Taeguk's Armor are on the sheet, so they come off when
            // their stacks lapse.
            static void LapseGogok(Player* player)
            {
                std::uint64_t const guid = player->GetGUID().GetRawValue();
                bool lapsed = false, gogok = false, taeguk = false, invigorating = false;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto buffs = timed.find(guid);
                    if (buffs == timed.end())
                        return;
                    std::uint32_t const clock = getMSTime();
                    for (auto const& [stacks, gone] : {std::pair{&buffs->second.gogok, &gogok},
                                                       std::pair{&buffs->second.taeguk, &taeguk},
                                                       std::pair{&buffs->second.invigorating, &invigorating}})
                        if (stacks->count && !GemPower::Live(*stacks, clock))
                        {
                            *stacks = {};
                            *gone = true;
                        }
                    lapsed = gogok || taeguk;
                }
                // The buffs end with their clocks (the core takes the aura off on its own timer; the addon is told).
                if (gogok)
                    ShowBuff(player, GemPower::Gogok, false, 0, 0);
                if (taeguk)
                    ShowBuff(player, GemPower::Taeguk, false, 0, 0);
                if (invigorating)
                    ShowBuff(player, GemPower::Invigorating, false, 0, 0);
                if (lapsed)
                    Sync(player);
            }

            // Bane of the Powerful. An elite kill is the one the loot and the damage formula already call one
            // (a native elite, or a rift champion or rare pack's leader; its members are not).
            void OnPlayerCreatureKill(Player* killer, Creature* killed) override
            {
                if (!killer || !killed)
                    return;
                bool const elite = killed->isElite() || DC::Rifts::IsPromotedElite(killed);
                bool cleared = false, powerful = false;
                double powerfulSeconds = 0;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    std::uint64_t const guid = killer->GetGUID().GetRawValue();
                    auto found = states.find(guid);
                    if (found == states.end())
                        return;
                    GemPower::Powers const& powers = found->second.powers;
                    // Moratorium, rank 25: a chance on a kill (not a skill's hit, so no proc coefficient) to clear the debt.
                    if (GemPower::ChanceHits(powers.moratoriumClearChancePct, rand_chance()))
                    {
                        cleared = !timed[guid].stagger.entries.empty();
                        timed[guid].stagger = {};
                    }
                    if (elite && powers.powerfulPct > 0)
                    {
                        GemPower::AddStack(timed[guid].powerful, getMSTime(), powers.powerfulSeconds, 1);
                        powerful = true;
                        powerfulSeconds = powers.powerfulSeconds;
                    }
                }
                if (cleared)
                    ShowDebt(killer, 0);
                if (powerful)
                    ShowBuff(killer, GemPower::Powerful, false, 1, powerfulSeconds);
            }

        private:
            static void Forget(Player* player)
            {
                std::lock_guard<std::mutex> lock(mutex);
                states.erase(player->GetGUID().GetRawValue());
                timed.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    namespace
    {
        // Invigorating Gemstone: healing received. A player's own Life regeneration, Life on Hit, potions and
        // globes all heal through Unit::HealBySpell with the player as healer and target; the core passes the two
        // units to this hook in opposite orders from its two callers (HealBySpell: healer first; the periodic
        // aura: target first), so only the heal where both are the same player is placed with certainty.
        class Heals final : public UnitScript
        {
        public:
            Heals()
                : UnitScript("dc_gem_powers_heal", true, {UNITHOOK_MODIFY_HEAL_RECEIVED})
            {
            }
            void ModifyHealReceived(Unit* first, Unit* second, uint32& heal, SpellInfo const*) override
            {
                Player* player = first && first == second ? first->ToPlayer() : nullptr;
                if (!player || !heal)
                    return;
                double factor = 1.0;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto found = states.find(player->GetGUID().GetRawValue());
                    auto buffs = timed.find(player->GetGUID().GetRawValue());
                    if (found == states.end() || buffs == timed.end())
                        return;
                    factor = GemPower::HealingFactor(found->second.powers,
                                                     GemPower::Live(buffs->second.invigorating, getMSTime()));
                }
                heal = static_cast<uint32>(std::llround(heal * factor));
            }
        };
    } // namespace

    namespace
    {
        // The tick of the gems that run on a clock: the poison and the bleed on an enemy (the gem's total weapon
        // damage % split into one tick a record period, dealt as an average-crit damage-over-time hit, 02 C11) and
        // Wreath of Lightning's pulse on the player (a hit of the gem's weapon damage % on every enemy within
        // `gem_wreath_radius_yards`, a tunable). Both are the gem's numbers at the moment the aura was
        // first put on (a refresh of a running aura keeps them), so taking the gem off does not cut a poison already
        // on an enemy, and a rank change reaches the next one.
        class dc_gem_tick final : public AuraScript
        {
            PrepareAuraScript(dc_gem_tick);
            double pct = 0;    // weapon damage % of one tick or one pulse
            double radius = 0; // the Wreath's
            bool pulse = false;
            bool valid = false;

            void Snapshot(AuraEffect const* effect, AuraEffectHandleModes)
            {
                valid = false;
                Unit* caster = GetCaster();
                Player* player = caster ? caster->ToPlayer() : nullptr;
                if (!player)
                    return;
                GemPower::Powers const powers = PowersOf(player);
                std::uint32_t const id = GetId();
                double const period = effect->GetAmplitude();
                pulse = id == ShellOf(GemPower::Wreath);
                if (pulse)
                {
                    pct = powers.wreathPct;
                    radius = Tune("gem_wreath_radius_yards");
                }
                else if (id == ShellOf(GemPower::Pain))
                    pct = GemPower::TickPct(powers.painPct, powers.painSeconds, period);
                else if (id == ShellOf(GemPower::Toxin))
                    pct = GemPower::TickPct(powers.toxinPct, powers.toxinSeconds, period);
                valid = pct > 0;
            }

            // Wreath of Lightning, rank 25: the Movement Speed is on while the buff is.
            void Wear(AuraEffect const*, AuraEffectHandleModes)
            {
                if (GetId() == ShellOf(GemPower::Wreath))
                    if (Unit* owner = GetUnitOwner())
                        Sync(owner->ToPlayer(), 1);
            }

            void Doff(AuraEffect const*, AuraEffectHandleModes)
            {
                if (GetId() == ShellOf(GemPower::Wreath))
                    if (Unit* owner = GetUnitOwner())
                    {
                        Sync(owner->ToPlayer(), 0);
                        BuffValues::Clear(owner->ToPlayer(), GetId());
                    }
            }

            void Tick(AuraEffect const*)
            {
                Unit* caster = GetCaster();
                Player* player = caster ? caster->ToPlayer() : nullptr;
                Unit* owner = GetUnitOwner();
                if (!valid || !player || !player->IsAlive() || !owner || !owner->IsAlive())
                    return;
                if (pulse)
                {
                    if (radius > 0)
                        StrikeArea(player, GetId(), player->GetPosition(), radius, pct);
                }
                else
                    Strike(player, owner, GetId(), pct, true);
            }

            void Register() override
            {
                AfterEffectApply += AuraEffectApplyFn(dc_gem_tick::Snapshot, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY,
                                                      AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
                AfterEffectApply += AuraEffectApplyFn(dc_gem_tick::Wear, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY,
                                                      AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
                AfterEffectRemove += AuraEffectApplyFn(dc_gem_tick::Doff, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY,
                                                       AURA_EFFECT_HANDLE_REAL);
                OnEffectPeriodic += AuraEffectPeriodicFn(dc_gem_tick::Tick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Cache();
        new Heals();
        RegisterSpellScript(dc_gem_tick);
    }
} // namespace DC::Combat::GemPowers
