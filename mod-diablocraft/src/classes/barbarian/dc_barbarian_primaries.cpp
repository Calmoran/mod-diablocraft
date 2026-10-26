#include "dc_barbarian_primaries.h"
#include "dc_barbarian.h"
#include "../../combat/dc_exact_damage.h"
#include "../../combat/dc_life_commands.h"
#include "../../combat/dc_charm_effect.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_buff_values.h"
#include "../../combat/dc_passives.h"
#include "dc_barbarian_primary_data.h"
#include "../../combat/dc_spell_shells.h"
#include "../../combat/dc_combat.h"
#include "../../stats/dc_stats.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "CellImpl.h"
#include "CharmInfo.h"
#include "Creature.h"
#include "CreatureAI.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Log.h"
#include "MotionMaster.h"
#include "MoveSpline.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellScript.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <limits>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Primaries
{
    namespace
    {
        namespace D = PrimaryData;
        using B = D::Behavior;
        struct Buffs
        {
            unsigned frenzy = 0;
            uint32 frenzyAt = 0;
            // Echoing Fury's stacks (GrantFrenzy) and when they were granted: D3's Frenzy buff, so they speed every attack, where
            // Frenzy's own swings speed Frenzy only (barbarian_skills.csv: "Frenzy's attack speed increases").
            unsigned granted = 0;
            uint32 grantedAt = 0;
            uint32 frenzyRune = 0;
            bool nextOff = false;
        };
        struct Cast
        {
            uint64 serial = 0;
            bool off = false, connected = false, valid = false, paid = false;
            double spent = 0; // Fury the cast took for Blade of the Warlord (the secondary shells carry their cast's)
            uint32 hits = 0;
            std::unordered_map<uint64, Hit> results;
        };
        std::mutex mutex;
        std::unordered_map<uint64, Buffs> buffs;
        std::unordered_map<Spell*, Cast> casts;
        std::atomic<uint64> serial{0};
        thread_local bool secondaryOffHand = false; // inherited through synchronous triggered Rupture launch
        thread_local double secondarySpent = 0;     // the Fury the launching cast took, inherited by its Pulverize shockwave
        struct LineLaunch
        {
            uint32 spellId = 0;
            Position origin;
            float direction = 0;
            ObjectGuid exclude;
        };
        thread_local LineLaunch lineLaunch;
        struct Landing
        {
            ObjectGuid caster;
            uint32 spline = 0;
            bool off = false;
        };
        std::unordered_map<uint64, Landing> landings;
        bool Secondary(uint32 id)
        {
            return id == D::RUPTURE || id == D::PULVERIZE || id == D::SIDEARM || id == D::SCATTERING;
        }
        bool Alive(uint32 start, uint32 duration)
        {
            return start && getMSTimeDiff(start, getMSTime()) < duration;
        }
        // A Frenzy rune a power gives the player without choosing it (kind `rune`: The Undisputed Champion). The base skill has no rune: `all` would grant it.
        bool Given(Player const* player, D::Row const& row)
        {
            Shells::Ability const* shell = Shells::FindAbility(row.id);
            return player && shell && *shell->rune && ItemPowers::GrantsRune(player, shell->skill, shell->rune);
        }
        // The row a swing reads for one rune effect: the swing's own when that is the behavior, else the Frenzy rune of that behavior when a power gives it,
        // else null. Chosen and given, it is the one row, so it counts once.
        D::Row const* Effect(Player const* player, D::Row const& active, B behavior)
        {
            if (active.behavior == behavior)
                return &active;
            if (std::string(active.skill) != "Frenzy")
                return nullptr;
            for (auto const& row : D::Rows)
                if (row.behavior == behavior && std::string(row.skill) == "Frenzy" && Given(player, row))
                    return &row;
            return nullptr;
        }
        // The Fury a swing earns: its own row's, or the higher number of a Frenzy rune a power gives (Berserk's).
        double FuryGain(Player const* player, D::Row const& active)
        {
            double fury = active.fury;
            if (std::string(active.skill) == "Frenzy")
                for (auto const& row : D::Rows)
                    if (std::string(row.skill) == "Frenzy" && row.fury > fury && Given(player, row))
                        fury = row.fury;
            return fury;
        }
        void Fury(Player* player, double amount)
        {
            Resources::Add(player, Resources::Fury, amount * Passives::GenerationFactor(player));
        }
        // Frenzy's stack limit: its own, or a worn power's higher one (Bastion's Revered). Read before `mutex` is taken: the item powers keep a lock of their own.
        unsigned MaxStacks(Player* player)
        {
            return static_cast<unsigned>(ItemPowers::SkillSetTo(player, "Frenzy", "buff_max_stacks", D::frenzy_max_stacks));
        }
        // Frenzy - Vanguard: `amount` is the sheet's Movement Speed (per stack times `stacks`). The buff the player
        // wears states the per-stack number and stacks with Frenzy, so the client shows the total (buff icons build 2).
        void Movement(Player* player, double amount, unsigned stacks = 0)
        {
            auto guid = player->GetGUID().GetRawValue();
            if (amount)
                Stats::AddContribution(
                    guid, {Source::Temporary, Stat::MovementSpeed, D::Find(81025)->id, amount, Bucket::Uncapped});
            else
                Stats::RemoveContribution(guid, Source::Temporary, Stat::MovementSpeed, D::Find(81025)->id);
            Stats::Recompute(player);
            BuffValues::Show(player, D::VANGUARD, amount ? stacks : 0, D::frenzy_duration_ms / 1000.0);
        }
        // Frenzy's buff as the player sees it: a real aura with the stacks and a fresh timer.
        void ShowFrenzy(Player* player, unsigned stacks)
        {
            Aura* aura = player->GetAura(D::FRENZY_BUFF);
            if (!aura)
                aura = player->AddAura(D::FRENZY_BUFF, player);
            if (aura)
            {
                aura->SetStackAmount(uint8(stacks));
                aura->SetMaxDuration(int32(D::frenzy_duration_ms));
                aura->SetDuration(int32(D::frenzy_duration_ms));
            }
        }
        // GitHub #44: Bash - Punish's buff is a real aura (generated helper
        // record "Punish"), so the player sees it, its stacks and its timer,
        // and the damage bonus is read back from it: what the buff bar shows
        // is what the hit uses, and the aura's own expiry ends the bonus.
        uint32 PunishAura()
        {
            static uint32 const id = Shells::HelperFor("Punish");
            return id;
        }
        D::Row const* PunishRow()
        {
            for (auto const& row : D::Rows)
                if (row.behavior == B::punish)
                    return &row;
            return nullptr;
        }
        void Punish(Player* player, D::Row const& row)
        {
            uint32 const id = PunishAura();
            if (!id)
                return;
            Aura* aura = player->GetAura(id);
            unsigned const stacks = aura ? std::min(unsigned(aura->GetStackAmount()) + 1, row.cap) : 1;
            if (!aura)
                aura = player->AddAura(id, player);
            if (!aura)
                return;
            aura->SetStackAmount(uint8(stacks));
            aura->SetMaxDuration(int32(row.duration));
            aura->SetDuration(int32(row.duration));
        }
        std::list<Unit*> Enemies(Player* player, Unit* origin, float radius)
        {
            std::list<Unit*> units;
            Acore::AnyUnfriendlyUnitInObjectRangeCheck check(origin, player, radius);
            Acore::UnitListSearcher<Acore::AnyUnfriendlyUnitInObjectRangeCheck> searcher(origin, units, check);
            Cell::VisitObjects(origin->GetPositionX(), origin->GetPositionY(), origin->GetMap(), searcher, radius);
            units.remove_if([&](Unit* unit) { return !unit->IsAlive() || !player->IsValidAttackTarget(unit); });
            return units;
        }
        // Bastion's Revered: after a Frenzy swing lands, Frenzy hits again once for each stack its buff holds (ItemPower::ExtraHits). Each extra hit
        // is rolled anew (weapon and crit) in the swing's hand, and its damage is shared equally by the target and the enemies within `chain_yards`
        // of it (ItemPower::ChainShare), whoever is alive at that hit. Damage only: no Fury, proc or critical-hit effect, and it never chains again.
        void FrenzyChain(Player* player, Unit* target, D::Row const& row, Hit const& hit)
        {
            double const perStack = ItemPowers::SkillSetTo(player, "Frenzy", "extra_hits_per_stack", 0);
            if (perStack <= 0)
                return;
            float const yards = static_cast<float>(ItemPowers::SkillSetTo(player, "Frenzy", "chain_yards", 0));
            unsigned stacks = 0;
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto found = buffs.find(player->GetGUID().GetRawValue());
                if (found != buffs.end() && Alive(found->second.frenzyAt, uint32(D::frenzy_duration_ms)))
                    stacks = found->second.frenzy;
            }
            for (unsigned left = ItemPower::ExtraHits(perStack, stacks); left; --left)
            {
                Hit extra;
                extra.offHand = hit.offHand;
                if (!ComputeHit(player, target, row.id, extra))
                    return;
                std::list<Unit*> victims = yards > 0 ? Enemies(player, target, yards) : std::list<Unit*>();
                if (target->IsAlive() && std::find(victims.begin(), victims.end(), target) == victims.end())
                    victims.push_front(target);
                if (victims.empty())
                    return; // the target and everything near it are dead
                Hit share = extra;
                share.total = ItemPower::ChainShare(extra.total, static_cast<unsigned>(victims.size()));
                share.areaDamage = 0;
                for (Unit* victim : victims)
                    DealHit(player, victim, row.id, share);
            }
        }
    } // namespace

    double DamageBonus(Player* player)
    {
        double bonus = 0;
        if (auto punish = PunishRow())
            if (Aura const* aura = player->GetAura(PunishAura()))
                bonus += aura->GetStackAmount() * punish->magnitude;
        uint32 rune;
        unsigned stacks;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = buffs.find(player->GetGUID().GetRawValue());
            if (found == buffs.end() || !Alive(found->second.frenzyAt, uint32(D::frenzy_duration_ms)))
                return bonus;
            rune = found->second.frenzyRune;
            stacks = found->second.frenzy;
        }
        // Outside the lock: the item power table has its own.
        auto row = D::Find(rune);
        if (row)
            if (auto maniac = Effect(player, *row, B::maniac))
                bonus += stacks * maniac->magnitude;
        return bonus;
    }

    double CritBonus(Unit* target)
    {
        if (!target || !target->HasAura(D::ONSLAUGHT))
            return 0;
        for (auto const& row : D::Rows)
            if (row.behavior == B::onslaught)
                return row.magnitude;
        return 0;
    }

    double TargetBonus(Unit* target)
    {
        return target && target->HasAura(D::GATHERING) ? D::Find(81039)->magnitude : 0;
    }

    double AttackSpeed(Player* player, uint32 spellId, double base)
    {
        auto row = D::Find(spellId);
        bool const frenzy = row && std::string(row->skill) == "Frenzy";
        std::lock_guard<std::mutex> lock(mutex);
        auto found = buffs.find(player->GetGUID().GetRawValue());
        if (found == buffs.end())
            return base;
        // Frenzy reads its whole buff (its swings' stacks and Echoing Fury's together); every other attack only Echoing Fury's.
        unsigned const stacks = frenzy ? (Alive(found->second.frenzyAt, uint32(D::frenzy_duration_ms)) ? found->second.frenzy : 0)
                                       : (Alive(found->second.grantedAt, uint32(D::frenzy_duration_ms)) ? found->second.granted : 0);
        if (!stacks)
            return base;
        return std::min(D::aps_cap, base * (1 + stacks * D::frenzy_ias_pct / 100));
    }

    void GrantFrenzy(Player* player, unsigned stacks)
    {
        if (!player || !stacks)
            return;
        unsigned shown;
        unsigned const cap = MaxStacks(player);
        uint32 rune;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto& buff = buffs[player->GetGUID().GetRawValue()];
            unsigned const held = Alive(buff.frenzyAt, uint32(D::frenzy_duration_ms)) ? buff.frenzy : 0;
            buff.frenzy = std::min(std::max(held, stacks), cap);
            buff.frenzyAt = getMSTime();
            unsigned const granted = Alive(buff.grantedAt, uint32(D::frenzy_duration_ms)) ? buff.granted : 0;
            buff.granted = std::min(std::max(granted, stacks), cap);
            buff.grantedAt = buff.frenzyAt;
            shown = buff.frenzy;
            rune = buff.frenzyRune;
        }
        // The rune the last swing used keeps its movement (a given Vanguard too); a player who never swung has none.
        auto row = D::Find(rune);
        auto vanguard = row ? Effect(player, *row, B::vanguard) : nullptr;
        double const movement = vanguard ? shown * vanguard->magnitude : 0;
        Movement(player, movement, shown);
        ShowFrenzy(player, shown);
    }

    std::vector<SecondaryShell> SecondaryShells()
    {
        return {{D::RUPTURE, "Cleave", "Rupture Explosion", "fire", D::rupture_damage_pct},
                {D::PULVERIZE, "Bash", "Pulverize Shockwave", "fire", D::pulverize_damage_pct},
                {D::SIDEARM, "Frenzy", "Sidearm Axe", "cold", D::sidearm_damage_pct},
                {D::SCATTERING, "Cleave", "Scattering Blast Landing", "physical", D::scattering_damage_pct}};
    }

    namespace
    {
        class dc_primary_spell final : public SpellScript
        {
            PrepareSpellScript(dc_primary_spell);
            Spell* identity = nullptr;
            SpellCastResult Check()
            {
                Player* player = GetCaster()->ToPlayer();
                if (!player) {
                    auto creature=GetCaster()->ToCreature();
                    if(creature&&creature->GetEntry()>=900100&&creature->GetEntry()<=900102&&creature->GetOwner()&&creature->GetOwner()->ToPlayer())return SPELL_CAST_OK;
                    return SPELL_FAILED_BAD_TARGETS;
                }
                if(player->getClass()!=CLASS_WARRIOR)return SPELL_FAILED_BAD_TARGETS;
                if (!Stats::Get(player->GetGUID().GetRawValue()))
                    return SPELL_FAILED_NOT_READY;
                return SPELL_CAST_OK;
            }
            void Begin()
            {
                Player* player = GetCaster()->ToPlayer();
                if (!player)
                    return;
                identity = GetSpell();
                auto row = D::Find(GetSpellInfo()->Id);
                unsigned const cap = row && std::string(row->skill) == "Frenzy" ? MaxStacks(player) : 0u;
                double movement = -1;
                unsigned frenzyStacks = 0;
                bool frenzy = false;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    Cast state;
                    state.serial = ++serial;
                    state.valid = true;
                    auto& buff = buffs[player->GetGUID().GetRawValue()];
                    state.off = row ? buff.nextOff && player->GetWeaponForAttack(OFF_ATTACK, true) : secondaryOffHand;
                    state.spent = row ? 0 : secondarySpent;
                    if (row)
                    {
                        buff.nextOff = !state.off && player->GetWeaponForAttack(OFF_ATTACK, true);
                        if (std::string(row->skill) == "Frenzy")
                        {
                            if (!Alive(buff.frenzyAt, uint32(D::frenzy_duration_ms)))
                                buff.frenzy = 0;
                            buff.frenzy = std::min(buff.frenzy + 1, cap);
                            buff.frenzyAt = getMSTime();
                            buff.frenzyRune = row->id;
                            frenzyStacks = buff.frenzy;
                            frenzy = true;
                        }
                    }
                    casts.emplace(identity, std::move(state));
                }
                if (frenzy)
                {
                    auto vanguard = Effect(player, *row, B::vanguard);
                    movement = vanguard ? frenzyStacks * vanguard->magnitude : 0;
                }
                if (movement >= 0)
                    Movement(player, movement, frenzyStacks);
                if (row && row->behavior == B::punish)
                    Punish(player, *row); // "after using Bash" (barbarian_runes.csv): on the cast
                if (frenzyStacks)
                    ShowFrenzy(player, frenzyStacks);
                LOG_DEBUG("module.dc.combat", "[DC Primary cast] spell={} caster={} aps={} secondary={}",
                         GetSpellInfo()->Id, player->GetGUID().ToString(), AttacksPerSecond(player, GetSpellInfo()->Id),
                         !row);
            }
            void Seed(SpellEffIndex)
            {
                // Native weapon-percent effects own target selection/launch but may
                // round their provisional number to zero. Keep every qualifying target
                // on the direct-damage path; the opt-in provider owns the actual number.
                SetHitDamage(1);
            }
            void Landed()
            {
                ClearPreCritHit(GetCaster()->ToPlayer());
                Player* player = GetCaster()->ToPlayer();
                Unit* target = GetHitUnit();
                if (!player || !target)
                    return;
                Hit hit;
                uint64 id;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto cast = casts.find(identity);
                    if (cast == casts.end())
                        return;
                    auto result = cast->second.results.find(target->GetGUID().GetRawValue());
                    if (result == cast->second.results.end())
                        return; // immune/miss: no provider
                    hit = result->second;
                    id = cast->second.serial;
                }
                LOG_DEBUG("module.dc.combat", "[DC Primary landed] cast={} spell={} target={} damage={} alive={}", id,
                         GetSpellInfo()->Id, target->GetGUID().ToString(), GetHitDamage(), target->IsAlive());
                auto row = D::Find(GetSpellInfo()->Id);
                if (!row)
                    return; // secondary cannot recurse or proc sustain/Area Damage
                if(GetHitDamage()>0)Passives::Hit(player,target,GetSpellInfo()->Id,hit.school);
                if (hit.critical && GetHitDamage()>0) Abilities::CriticalHit(player,target,GetSpellInfo()->Id,GetHitDamage());
                auto const sidearm = Effect(player, *row, B::sidearm);
                if (row->behavior == B::pulverize || (sidearm && roll_chance_f(float(sidearm->chance))))
                {
                    Unit* aim = target;
                    if (sidearm)
                    {
                        auto enemies = Enemies(player, target, float(D::sidearm_selection_yards));
                        // The sourced selection radius is measured from the original
                        // victim, independent of the axe's five-yard piercing path.
                        enemies.remove_if([&](Unit* enemy)
                                          { return target->GetExactDist(enemy) > D::sidearm_selection_yards; });
                        if (enemies.empty())
                            aim = nullptr;
                        else
                        {
                            auto it = enemies.begin();
                            std::advance(it, urand(0, uint32(enemies.size() - 1)));
                            aim = *it;
                        }
                    }
                    if (aim)
                    {
                        auto previousLine = lineLaunch;
                        bool const previousHand = secondaryOffHand;
                        double const previousSpent = secondarySpent;
                        lineLaunch.spellId = row->behavior == B::pulverize ? D::PULVERIZE : D::SIDEARM;
                        lineLaunch.origin =
                            row->behavior == B::pulverize ? target->GetPosition() : player->GetPosition();
                        lineLaunch.direction = player->GetAngle(aim);
                        lineLaunch.exclude = row->behavior == B::pulverize ? target->GetGUID() : ObjectGuid::Empty;
                        secondaryOffHand = hit.offHand;
                        secondarySpent = hit.spent;
                        player->CastSpell(aim, lineLaunch.spellId, true);
                        secondaryOffHand = previousHand;
                        secondarySpent = previousSpent;
                        lineLaunch = previousLine;
                    }
                }
                if (row->behavior == B::rupture && !target->IsAlive())
                {
                    bool const previous = secondaryOffHand;
                    secondaryOffHand = hit.offHand;
                    player->CastSpell(target->GetPositionX(), target->GetPositionY(), target->GetPositionZ(),
                                      D::RUPTURE, true);
                    secondaryOffHand = previous;
                }
                if (target->IsAlive())
                {
                    if (row->behavior == B::scattering && hit.critical)
                    {
                        bool const previous = secondaryOffHand;
                        secondaryOffHand = hit.offHand;
                        player->CastSpell(target, D::KNOCKUP, true);
                        secondaryOffHand = previous;
                    }
                    if (row->behavior == B::onslaught)
                        player->CastSpell(target, D::ONSLAUGHT, true);
                    if (row->behavior == B::gathering)
                        player->CastSpell(target, D::GATHERING, true);
                    if (row->behavior == B::frostbite && !target->HasAura(D::FROST_LOCKOUT))
                    {
                        player->CastSpell(target, D::FROSTBITE, true);
                        if (target->HasAura(D::FROSTBITE))
                            player->CastSpell(target, D::FROST_LOCKOUT, true);
                    }
                    if (auto smite = Effect(player, *row, B::smite); smite && roll_chance_f(float(smite->chance)))
                        player->CastSpell(target, D::SMITE, true);
                    if (roll_chance_f(float(row->chance)))
                    {
                        if (row->behavior == B::hammer)
                            player->CastSpell(target, D::HAMMER, true);
                        if (row->behavior == B::stupefy)
                        {
                            // The shared charm holds the monster for the row's seconds and sends it at the nearest enemy.
                            // It is turned on another enemy only when there is one in sight, so no charm is wasted on a
                            // monster alone; a Juggernaut, a boss or a charmed monster refuses it there.
                            auto others = Enemies(player, target, target->GetVisibilityRange());
                            others.remove(target);
                            if (!others.empty())
                                CharmEffect::Apply(player, target, row->id, row->duration / 1000.0);
                        }
                    }
                }
                if (hit.areaDamage > 0)
                {
                    Hit splash = hit;
                    splash.total = hit.areaDamage;
                    splash.areaDamage = 0;
                    for (Unit* unit : Enemies(player, target, 10.0f)) // damage_formula.csv step 11
                        if (unit != target)
                            DealHit(player, unit, row->id, splash);
                }
                if (std::string(row->skill) == "Frenzy")
                    FrenzyChain(player, target, *row, hit);
            }
            void Finish()
            {
                auto player = GetCaster()->ToPlayer();
                if (!player || !D::Find(GetSpellInfo()->Id) || GetSpell()->IsTriggered())
                    return;
                // C7: the recovery is one swing of the hand Begin chose for this cast.
                bool offhand = false;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto cast = casts.find(identity);
                    offhand = cast != casts.end() && cast->second.off;
                }
                StartSkillCooldown(player, GetSpellInfo()->Id, offhand);
            }
            void Register() override
            {
                OnCheckCast += SpellCheckCastFn(dc_primary_spell::Check);
                AfterCast += SpellCastFn(dc_primary_spell::Finish);
                OnCast += SpellCastFn(dc_primary_spell::Begin);
                OnEffectHitTarget += SpellEffectFn(dc_primary_spell::Seed, EFFECT_0, SPELL_EFFECT_ANY);
                AfterHit += SpellHitFn(dc_primary_spell::Landed);
            }

        public:
            ~dc_primary_spell() override
            {
                if (identity)
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    casts.erase(identity);
                }
            }
        };

        class dc_pulverize_line final : public SpellScript
        {
            PrepareSpellScript(dc_pulverize_line);
            void Filter(std::list<WorldObject*>& targets)
            {
                if (lineLaunch.spellId == D::PULVERIZE)
                    targets.remove_if([](WorldObject* target) { return target->GetGUID() == lineLaunch.exclude; });
            }
            void Register() override
            {
                OnObjectAreaTargetSelect += SpellObjectAreaTargetSelectFn(dc_pulverize_line::Filter, EFFECT_0, TARGET_UNIT_CONE_ENEMY_104);
            }
        };

        class Provider final : public UnitScript
        {
        public:
            Provider()
                : UnitScript("dc_primary_provider", true, {UNITHOOK_PROVIDE_FINAL_SPELL_DAMAGE})
            {
            }
            bool ProvideFinalSpellDamage(Spell* spell, Unit* attacker, Unit* target, SpellInfo const* info, uint8 mask,
                                         uint64& damage64, bool& critical) override
            {
                uint64& damage = damage64; // the core hands the hit over in 64 bits and takes the exact hit back
                auto row = D::Find(info->Id);
                if (!row && !Secondary(info->Id))
                    return false;
                damage = 0;
                critical = false; // claimed shells fail closed if their script/data is absent
                Player* player = attacker->ToPlayer();
                if (!player || !(mask & 1))
                    return true;
                Hit hit;
                uint64 id;
                bool takes;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto found = casts.find(spell);
                    if (found == casts.end() || !found->second.valid)
                        return true;
                    hit.offHand = found->second.off;
                    hit.spent = found->second.spent;
                    takes = row && !spell->IsTriggered() && !found->second.paid; // a pressed cast pays once, for its first hit
                    id = found->second.serial;
                }
                if (takes) // Blade of the Warlord: the Fury the hit is worth, taken once the hit is worked out
                    hit.spent = ItemPowers::ResourceSpend(player, row->skill, Resources::Get(player, Resources::Fury));
                if (!ComputeHit(player, target, info->Id, hit))
                    return true;
                hit.total = DevBoost(player, hit.total); // GM dev multiplier
                damage = ExactDamage(hit.total);
                critical = hit.critical;
                RecordPreCritHit(player, target, hit.crit > 0.0 ? hit.total / hit.crit : 0.0, hit.school);
                bool first, newTarget;
                uint32 count;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto& state = casts.at(spell);
                    state.paid |= takes;
                    state.spent = hit.spent;
                    newTarget = state.results.find(target->GetGUID().GetRawValue()) == state.results.end();
                    first = !state.connected && damage > 0;
                    state.connected |= damage > 0;
                    count = ++state.hits;
                    state.results[target->GetGUID().GetRawValue()] = hit;
                }
                if (takes && hit.spent > 0)
                {
                    Resources::Add(player, Resources::Fury, -hit.spent);
                    Abilities::Spent(player, hit.spent);
                }
                uint32 const furyBefore = Resources::Units(player, Resources::Fury);
                double grant = 0;
                if (row && damage > 0 && newTarget)
                {
                    if (first)
                    {
                        grant = FuryGain(player, *row);
                        Connected(player, info->Id);
                    }
                    else if (row->behavior == B::reaping)
                        grant = row->magnitude;
                    Fury(player, grant);
                }
                LOG_DEBUG("module.dc.combat",
                         "[DC Primary Fury] cast={} spell={} target={} new={} grant={} before={} after={} cap={} "
                         "(native Rage units)",
                         id, info->Id, target->GetGUID().ToString(), newTarget, grant, furyBefore,
                         Resources::Units(player, Resources::Fury), Resources::MaxUnits(player, Resources::Fury));
                LOG_DEBUG("module.dc.combat",
                         "[DC Primary provider] cast={} spell={} school={} target={} mask={} hit={} damage={} crit={} first={} "
                         "secondary={} {}",
                         id, info->Id, uint32(info->SchoolMask), target->GetGUID().ToString(), uint32(mask), count, damage, critical, first, !row,
                         hit.Describe());
                return true;
            }
        };

        class GeometryAndControl final : public UnitScript
        {
        public:
            GeometryAndControl()
                : UnitScript("dc_primary_geometry_control", true,
                             {UNITHOOK_PROVIDE_SPELL_LINE_GEOMETRY, UNITHOOK_IS_SPELL_DIMINISHING_EXEMPT,
                              UNITHOOK_ON_EFFECT_MOVEMENT_FINALIZED, UNITHOOK_ON_UNIT_DEATH})
            {
            }
            bool IsSpellDiminishingExempt(Spell*, Unit*, Unit*, SpellInfo const* info) override
            {
                return ((info->Id >= 81000 && info->Id <= D::KNOCKUP) || (info->Id >= 81710 && info->Id <= 81847)) && info->HasAura(SPELL_AURA_MOD_STUN);
            }
            bool ProvideSpellLineGeometry(Spell* spell, uint8 effect, Unit*, Position& origin, float& direction,
                                          float& length, float& width) override
            {
                uint32 const id = spell->GetSpellInfo()->Id;
                if (effect || (id != D::PULVERIZE && id != D::SIDEARM))
                    return false;
                length = width = 0; // claimed without launch context selects nothing
                if (lineLaunch.spellId != id)
                    return true;
                origin = lineLaunch.origin;
                direction = lineLaunch.direction;
                length = float(id == D::PULVERIZE ? D::pulverize_length_yards : D::sidearm_length_yards);
                width = float(id == D::PULVERIZE ? D::pulverize_width_yards : D::sidearm_width_yards);
                LOG_DEBUG("module.dc.combat",
                         "[DC Primary line] spell={} origin=({},{},{}) direction={} length={} width={}", id,
                         origin.GetPositionX(), origin.GetPositionY(), origin.GetPositionZ(), direction, length, width);
                return true;
            }
            void OnEffectMovementFinalized(Unit* unit, uint32 effectId, uint32 splineId, bool completed) override
            {
                if (effectId != D::KNOCKUP)
                    return;
                Landing landing;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto it = landings.find(unit->GetGUID().GetRawValue());
                    if (it == landings.end() || it->second.spline != splineId)
                        return;
                    landing = it->second;
                    landings.erase(it);
                }
                LOG_DEBUG("module.dc.combat",
                         "[DC Scattering landing] target={} spline={} completed={} alive={} position=({},{},{})",
                         unit->GetGUID().ToString(), splineId, completed, unit->IsAlive(), unit->GetPositionX(),
                         unit->GetPositionY(), unit->GetPositionZ());
                if (!completed || !unit->IsAlive() || !unit->IsInWorld())
                    return;
                Player* player = ObjectAccessor::GetPlayer(*unit, landing.caster);
                if (!player || !player->IsAlive() || !player->InSamePhase(unit))
                    return;
                bool const previous = secondaryOffHand;
                secondaryOffHand = landing.off;
                player->CastSpell(unit->GetPositionX(), unit->GetPositionY(), unit->GetPositionZ(), D::SCATTERING,
                                  true);
                secondaryOffHand = previous;
            }
            void OnUnitDeath(Unit* unit, Unit*) override
            {
                std::lock_guard<std::mutex> lock(mutex);
                landings.erase(unit->GetGUID().GetRawValue());
            }
        };

        class dc_scattering_knockup final : public SpellScript
        {
            PrepareSpellScript(dc_scattering_knockup);
            void Launch(SpellEffIndex index)
            {
                PreventHitDefaultEffect(index);
                Creature* target = GetHitCreature();
                Player* player = GetCaster()->ToPlayer();
                if (!target || !player || !target->IsAlive() || target->IsClientControlled() || target->isWorldBoss() ||
                    target->IsDungeonBoss() || target->IsImmuneToKnockback() ||
                    target->GetCreatureType() == CREATURE_TYPE_GIANT || target->GetVehicle() ||
                    (target->IsVehicle() && target->GetCreatureType() != CREATURE_TYPE_BEAST) ||
                    target->HasUnitState(UNIT_STATE_ROOT))
                    return;
                target->InterruptNonMeleeSpells(true);
                uint32 const oldSpline = target->movespline->GetId();
                target->GetMotionMaster()->MoveVerticalKnockback(float(D::scattering_height_yards), D::KNOCKUP);
                uint32 const spline = target->movespline->GetId();
                if (spline == oldSpline || target->movespline->Finalized())
                    return;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    landings[target->GetGUID().GetRawValue()] = {player->GetGUID(), spline, secondaryOffHand};
                }
                LOG_DEBUG("module.dc.combat", "[DC Scattering launch] target={} spline={} height={} duration={}",
                         target->GetGUID().ToString(), spline, D::scattering_height_yards,
                         target->movespline->Duration());
            }
            void Register() override
            {
                OnEffectHitTarget += SpellEffectFn(dc_scattering_knockup::Launch, EFFECT_0, SPELL_EFFECT_KNOCK_BACK);
            }
        };

        class CreatureCleanup final : public AllCreatureScript
        {
        public:
            CreatureCleanup()
                : AllCreatureScript("dc_primary_creature_cleanup")
            {
            }
            void OnCreatureRemoveWorld(Creature* creature) override
            {
                std::lock_guard<std::mutex> lock(mutex);
                landings.erase(creature->GetGUID().GetRawValue());
            }
        };

        class Ticker final : public PlayerScript
        {
        public:
            Ticker()
                : PlayerScript("dc_primary_state", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_LOGIN})
            {
            }
            void OnPlayerLogin(Player* player) override
            {
                if (player->getClass() == CLASS_WARRIOR)
                {
                    Movement(player, 0);
                    player->RemoveAurasDueToSpell(D::FRENZY_BUFF);
                }
            }
            void OnPlayerUpdate(Player* player, uint32) override
            {
                bool expired = false;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto found = buffs.find(player->GetGUID().GetRawValue());
                    if (found == buffs.end())
                        return;
                    auto& state = found->second;
                    if (state.frenzy && (!player->IsAlive() || !Alive(state.frenzyAt, uint32(D::frenzy_duration_ms))))
                    {
                        state.frenzy = 0;
                        expired = true;
                    }
                }
                if (expired)
                {
                    Movement(player, 0);
                    player->RemoveAurasDueToSpell(D::FRENZY_BUFF);
                }
            }
            void OnPlayerLogout(Player* player) override
            {
                if (player->getClass() == CLASS_WARRIOR)
                {
                    Movement(player, 0);
                    player->RemoveAurasDueToSpell(D::FRENZY_BUFF);
                }
                std::lock_guard<std::mutex> lock(mutex);
                buffs.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace
    void RegisterScripts()
    {
        RegisterSpellScript(dc_primary_spell);
        RegisterSpellScript(dc_scattering_knockup);
        RegisterSpellScript(dc_pulverize_line);
        new Provider();
        new GeometryAndControl();
        new CreatureCleanup();
        new Ticker();
    }
} // namespace DC::Combat::Primaries
