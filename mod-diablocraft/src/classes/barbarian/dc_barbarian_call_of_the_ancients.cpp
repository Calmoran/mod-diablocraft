#include "dc_barbarian_call_of_the_ancients.h"
#include "../dc_level_heal.h"
#include "../dc_resources.h"
#include "../../combat/dc_exact_damage.h"
#include "../../combat/dc_life_commands.h"
#include "../../combat/dc_spell_shells.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_passives.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "CellImpl.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Spell.h"
#include "CreatureAI.h"
#include "DatabaseEnv.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Pet.h"
#include "PetDefines.h"
#include "ScriptMgr.h"
#include "ScriptedCreature.h"
#include "SpellInfo.h"
#include <algorithm>
#include <limits>
#include "SpellScript.h"
#include "SpellAuras.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"
#include <algorithm>
#include <array>
#include <mutex>
#include <unordered_map>
namespace DC::Classes::Ancients
{
    namespace
    {
        using Row = Combat::Shells::Ability;
        struct Pack
        {
            uint32 spell = 0;
            std::array<ObjectGuid, 3> members;
        };
        std::recursive_mutex mutex;
        std::unordered_map<uint64, Pack> packs;
        double lifePct = 0, bonusInterval = 0, chill = 0;
        Row const* Base()
        {
            for (auto const& r : Combat::Shells::Abilities)
                if (std::string(r.skill) == "Call of the Ancients" && !*r.rune)
                    return &r;
            return nullptr;
        }
        bool Rune(Row const* r, char const* name)
        {
            return r && std::string(r->rune) == name;
        }
        // Ancients' Fury's row: the summoning rune when it is Ancients' Fury, else the rune's own row when a power gives it without choosing it
        // (Fury of the Ancients; Abilities' RuneRow for the other skills), else null. Chosen and given, it counts once.
        Row const* FuryRow(Player const* p, Row const* r)
        {
            if (Rune(r, "Ancients' Fury"))
                return r;
            if (!p || !Combat::ItemPowers::GrantsRune(p, "Call of the Ancients", "Ancients' Fury"))
                return nullptr;
            for (auto const& row : Combat::Shells::Abilities)
                if (std::string(row.skill) == "Call of the Ancients" && Rune(&row, "Ancients' Fury"))
                    return &row;
            return nullptr;
        }
        std::vector<Creature*> Living(Player const* p)
        {
            std::vector<Creature*> out;
            auto i = packs.find(p->GetGUID().GetRawValue());
            if (i != packs.end())
                for (auto g : i->second.members)
                    if (auto c = ObjectAccessor::GetCreature(*p, g);
                        c && c->IsAlive() && p->IsInMap(c) && p->InSamePhase(c))
                        out.push_back(c);
            return out;
        }
        void Clear(Player* p)
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            if (auto i = packs.find(p->GetGUID().GetRawValue()); i != packs.end())
                for (auto g : i->second.members)
                    if (auto c = ObjectAccessor::GetCreature(*p, g))
                        if (auto summon = c->ToTempSummon())
                            summon->UnSummon();
            packs.erase(p->GetGUID().GetRawValue());
        }
        void Heal(Player* p, Unit* u, uint32 id, double value)
        {
            if (!u || !u->IsAlive() || value <= 0)
                return;
            HealInfo heal(p, u, uint32(value), sSpellMgr->GetSpellInfo(id), SPELL_SCHOOL_MASK_NORMAL);
            p->HealBySpell(heal);
        }
        class AI final : public ScriptedAI
        {
            ObjectGuid owner;
            uint32 source = 0, index = 0;
            double swing = 0, bonus = 0;
            bool alternate = false;

        public:
            AI(Creature* c)
                : ScriptedAI(c)
            {
            }
            void Configure(Player* p, uint32 spell, uint32 which)
            {
                owner = p->GetGUID();
                source = spell;
                index = which;
                me->SetLevel(p->GetLevel());
                me->SetFaction(p->GetFaction());
                me->SetDisplayId(p->GetNativeDisplayId());
                me->SetCreatorGUID(owner);
                me->SetOwnerGUID(owner);
                // ancients_life_pct_of_owner: a share of the owner's max Life at summon.
                me->SetMaxHealth(std::max<uint32>(1, uint32(std::min(double(std::numeric_limits<uint32>::max()), lifePct / 100.0 * p->GetMaxHealth()))));
                me->SetHealth(me->GetMaxHealth());
            }
            void Hit(Player* p, Unit* target, uint32 spell, bool basic)
            {
                if (!target || !target->IsAlive() || !p->IsValidAttackTarget(target) || !p->InSamePhase(target) ||
                    !me->IsWithinLOSInMap(target))
                    return;
                auto r = Combat::Shells::FindAbility(source);
                auto b = Base();
                if (!r || !b)
                    return;
                // The bonus abilities are cast under their own skills' spells but are the Ancients' damage: Enforcer reads the
                // summoning skill (`r->skill`), not the spell's own.
                Combat::Hit hit;
                if (!Combat::ComputeHit(p, target, spell, hit, std::nullopt, false, r->skill))
                    return;
                if (basic)
                {
                    double pct = Rune(r, "The Council Rises") ? Combat::Numbers::Num(r->id, "damage_pct") : Combat::Numbers::Num(b->id, "damage_pct");
                    hit.total *= pct / 100 / hit.skill;
                    hit.skill = pct / 100;
                }
                if (Rune(r, "The Council Rises"))
                    hit.school = SPELL_SCHOOL_MASK_FIRE;
                if (Rune(r, "Duty to the Clan"))
                    hit.school = SPELL_SCHOOL_MASK_FROST;
                if (Rune(r, "Together as One"))
                    hit.school = SPELL_SCHOOL_MASK_NATURE;
                if(auto sheet=Stats::Get(p->GetGUID().GetRawValue())) {
                Element element=hit.school==SPELL_SCHOOL_MASK_FIRE?Element::Fire:(hit.school==SPELL_SCHOOL_MASK_FROST?Element::Cold:(hit.school==SPELL_SCHOOL_MASK_NATURE?Element::Lightning:Element::Physical));
                double factor=1+sheet->elementalDamage[Index(element)]/100;
                hit.total*=factor/hit.elemental;hit.elemental=factor;
            }
            auto info = sSpellMgr->GetSpellInfo(source);
                if (!info || target->IsImmunedToDamage(me, info))
                    return;
                SpellNonMeleeDamage log(me, target, info, hit.school);
                hit.total = Combat::DevBoost(p, hit.total); // GM dev multiplier
                log.damage = Combat::ExactDamage(hit.total);
                log.cleanDamage = LifeToUInt32(log.damage);
                log.physicalLog = hit.school == SPELL_SCHOOL_MASK_NORMAL;
                if (hit.critical)
                    log.HitInfo |= SPELL_HIT_TYPE_CRIT;
                me->SendSpellNonMeleeDamageLog(&log);
                me->DealSpellDamage(&log, true);
                if (Row const* fury = FuryRow(p, r))
                    Resources::Modify(p, Resources::Fury, Combat::Numbers::Num(fury->id, "gain_resource") * Combat::Passives::GenerationFactor(p));
                if (Rune(r, "Duty to the Clan"))
                    if (auto aura = p->AddAura(81710 + source - 81000, target))
                    {
                        if (chill > 0)
                            if (auto effect = aura->GetEffect(EFFECT_0))
                                effect->ChangeAmount(-int32(chill));
                        aura->SetMaxDuration(int32(Combat::Numbers::Num(r->id, "chill_duration_seconds") * 1000));
                        aura->SetDuration(int32(Combat::Numbers::Num(r->id, "chill_duration_seconds") * 1000));
                    }
            }
            void UpdateAI(uint32 diff) override
            {
                if(auto current=me->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
                   current && current->GetSpellInfo()->Id==81004)
                    me->InterruptSpell(CURRENT_CHANNELED_SPELL);
                auto p = ObjectAccessor::FindConnectedPlayer(owner);
                if (!p || !p->IsAlive() || !p->IsInMap(me) || !p->InSamePhase(me))
                {
                    if (auto s = me->ToTempSummon())
                        s->UnSummon();
                    return;
                }
                // The owner's attack target, or his selection while he fights; nothing to fight
                // means follow him like a pet.
                Unit* victim = p->GetVictim();
                Unit* selected = p->GetSelectedUnit();
                auto usable = [&](Unit* u) { return u && u->IsAlive() && p->IsValidAttackTarget(u); };
                Unit* target = nullptr;
                switch (PickTarget(usable(victim), p->IsInCombat(), usable(selected)))
                {
                    case Pick::Victim:
                        target = victim;
                        break;
                    case Pick::Selected:
                        target = selected;
                        break;
                    case Pick::None:
                        break;
                }
                if (!target)
                {
                    if (me->GetVictim())
                        me->AttackStop();
                    if (me->GetMotionMaster()->GetCurrentMovementGeneratorType() != FOLLOW_MOTION_TYPE)
                        me->GetMotionMaster()->MoveFollow(p, PET_FOLLOW_DIST * 1.5f, FollowAngle(index));
                    return;
                }
                if (me->GetVictim() != target)
                    AttackStart(target);
                swing += diff;
                // Fury of the Ancients: the item powers' summon attack speed (1 when none), on the owner's attacks per second; Tasker and
                // Theo's pet attack speed the same way.
                double aps = Combat::AttacksPerSecond(p) * Combat::ItemPowers::SkillFactor(p, "Call of the Ancients", "summon_attack_speed_pct") *
                             Combat::ItemPowers::PetSpeedFactor(p);
                if (aps > 0 && swing >= 1000 / aps && me->IsWithinMeleeRange(target))
                {
                    swing = 0;
                    Hit(p, target, source, true);
                }
                if (bonusInterval <= 0)
                    return;
                bonus += diff;
                if (bonus < bonusInterval * 1000)
                    return;
                bonus = 0;
                char const* skills[3][2] = {
                    {"Whirlwind", "Leap"}, {"Cleave", "Furious Charge"}, {"Weapon Throw", "Seismic Slam"}};
                for (auto const& r : Combat::Shells::Abilities)
                    if (!*r.rune && std::string(r.skill) == skills[index][alternate ? 1 : 0])
                    {
                        me->CastSpell(target, r.id, true);
                        break;
                    }
                alternate = !alternate;
            }
        };
        class dc_ancient_bonus final : public SpellScript
        {
            PrepareSpellScript(dc_ancient_bonus);
            bool Ancient()
            {
                auto c = GetCaster()->ToCreature();
                return c && IsAncientEntry(c->GetEntry());
            }
            void Suppress()
            {
                if (Ancient())
                    SetHitDamage(0);
            }
            void Landed()
            {
                if (!Ancient() || !GetHitUnit())
                    return;
                auto c = GetCaster()->ToCreature();
                auto p = c->GetOwner() ? c->GetOwner()->ToPlayer() : nullptr;
                if (p && GetSpellInfo()->Id==81004)
                {
                    std::list<Unit*> targets;
                    Acore::AnyUnfriendlyUnitInObjectRangeCheck check(c,c,Combat::Shells::FindAbility(81004)->radius);
                    Acore::UnitListSearcher<Acore::AnyUnfriendlyUnitInObjectRangeCheck> search(c,targets,check);
                    Cell::VisitObjects(c->GetPositionX(),c->GetPositionY(),c->GetMap(),search,Combat::Shells::FindAbility(81004)->radius);
                    if (auto ai = AiAs<AI>(c->AI()))
                        for(auto target:targets)ai->Hit(p,target,81004,false);
                }
                else if (p)
                    if (auto ai = AiAs<AI>(c->AI()))
                        ai->Hit(p, GetHitUnit(), GetSpellInfo()->Id, false);
            }
            void Register() override
            {
                OnHit += SpellHitFn(dc_ancient_bonus::Suppress);
                AfterHit += SpellHitFn(dc_ancient_bonus::Landed);
            }
        };
        class Script final : public CreatureScript
        {
        public:
            Script()
                : CreatureScript("dc_ancient")
            {
            }
            CreatureAI* GetAI(Creature* c) const override
            {
                return new AI(c);
            }
        };
        class World final : public WorldScript
        {
        public:
            World()
                : WorldScript("dc_ancient_tuning", {WORLDHOOK_ON_AFTER_CONFIG_LOAD})
            {
            }
            void OnAfterConfigLoad(bool) override
            {
                std::lock_guard<std::recursive_mutex> guard(mutex);
                if (auto q = WorldDatabase.Query(
                        "SELECT name,tuned_value FROM dc_ability_tuning WHERE name IN "
                        "('ancients_life_pct_of_owner','ancients_bonus_interval_seconds','ancients_duty_chill_pct')"))
                    do
                    {
                        auto f = q->Fetch();
                        auto n = f[0].Get<std::string>();
                        double v = std::max(0.0, f[1].Get<double>());
                        if (n == "ancients_life_pct_of_owner")
                            lifePct = v;
                        if (n == "ancients_bonus_interval_seconds")
                            bonusInterval = v;
                        if (n == "ancients_duty_chill_pct")
                            chill = v;
                    } while (q->NextRow());
            }
        };
        class Cleanup final : public PlayerScript
        {
        public:
            Cleanup()
                : PlayerScript("dc_ancient_cleanup",
                               {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED, PLAYERHOOK_ON_UPDATE})
            {
            }
            void OnPlayerLogout(Player* p) override
            {
                Clear(p);
            }
            void OnPlayerMapChanged(Player* p) override
            {
                Clear(p);
            }
            void OnPlayerUpdate(Player* p, uint32) override
            {
                if (!p->IsAlive())
                    Clear(p);
            }
        };
    } // namespace
    void Summon(Player* p, uint32 id)
    {
        // Immortal King's Call 2-piece: "Call of the Ancients last until they die". Read before this file's lock: the item power table has its own.
        bool const untilDeath = Combat::ItemPowers::SkillSetTo(p, "Call of the Ancients", "lasts_until_death", 0) > 0;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        Clear(p);
        auto b = Base();
        if (!b || lifePct <= 0)
            return;
        Pack pack;
        pack.spell = id;
        for (uint32 i = 0; i < pack.members.size(); ++i)
            if (auto c =
                    p->SummonCreature(900100 + i, p->GetPosition(), untilDeath ? TEMPSUMMON_DEAD_DESPAWN : TEMPSUMMON_TIMED_DESPAWN,
                                      untilDeath ? 0u : uint32(Combat::Numbers::Num(b->id, "duration_seconds") * 1000)))
            {
                pack.members[i] = c->GetGUID();
                // The AI can be another script's (the rift hook
                // swaps it); one that is not ours is despawned, never configured.
                if (auto ai = AiAs<AI>(c->AI()); ai && c->IsInWorld())
                    ai->Configure(p, id, i);
                else
                {
                    pack.members[i] = ObjectGuid::Empty;
                    c->DespawnOrUnsummon();
                }
            }
        packs[p->GetGUID().GetRawValue()] = pack;
    }
    bool Active(Player const* p)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        return p && !Living(p).empty();
    }
    void Spent(Player* p, double fury)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto i = packs.find(p->GetGUID().GetRawValue());
        if (i == packs.end())
            return;
        auto r = Combat::Shells::FindAbility(i->second.spell);
        if (Rune(r, "Ancients' Blessing") && !Living(p).empty())
        {
            Heal(p, p, r->id, fury * Classes::HealAtLevel(Combat::Numbers::Num(r->id, "heal_life"), p->GetLevel()) * Combat::Passives::FuryHealFactor(p));
            for (auto c : Living(p))
                Heal(p, c, r->id, fury * Classes::HealAtLevel(Combat::Numbers::Num(r->id, "heal_life"), p->GetLevel()) * Combat::Passives::FuryHealFactor(p));
        }
    }
    void Redirect(Player* p, uint32& damage)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto i = packs.find(p->GetGUID().GetRawValue());
        if (i == packs.end())
            return;
        auto r = Combat::Shells::FindAbility(i->second.spell);
        auto living = Living(p);
        if (!Rune(r, "Together as One") || living.empty())
            return;
        uint32 split = uint32(damage * Combat::Numbers::Num(r->id, "damage_share_pct") / 100);
        damage -= split;
        uint32 remaining = split;
        for (size_t j = 0; j < living.size(); ++j)
        {
            uint32 share = remaining / uint32(living.size() - j);
            remaining -= share;
            Unit::DealDamage(p, living[j], share, nullptr, DIRECT_DAMAGE, SPELL_SCHOOL_MASK_NATURE, nullptr, false);
        }
    }
    void HealAll(Player* p, uint32 id, double value)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        for (auto c : Living(p))
            Heal(p, c, id, value);
    }
    void RegisterScripts()
    {
        new Script();
        new World();
        new Cleanup();
        RegisterSpellScript(dc_ancient_bonus);
    }
} // namespace DC::Classes::Ancients
