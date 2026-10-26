/*
 * Hex and its five runes. The Shaman is a minion of the shared piece (combat/dc_minions.h) that acts in cycles: it
 * picks the nearest enemy within its search radius and hexes the group round it (or, for the Toad, pulls the group in
 * and poisons it). The Angry Chicken has no Shaman: the Witch Doctor is the chicken, and the chicken explodes. The
 * dispatch is in dc_witch_doctor.cpp.
 */

#include "dc_witch_doctor_hex.h"
#include "dc_witch_doctor_hex_math.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_sheet_buffs.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_damage_buckets.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_healing_table.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_numbers.h"
#include "Creature.h"
#include "Group.h"
#include "GroupReference.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "GameTime.h"

#include <chrono>
#include <mutex>
#include <vector>

namespace DC::Combat::WitchDoctor::Hex
{
    namespace
    {
        constexpr std::string_view Skill = "Hex";
        constexpr std::string_view ShamanGroup = "shaman";
        // The level the sheet's Hedge Magic number is for.
        constexpr unsigned SheetLevel = 70;
        // The creature of witch_doctor_hex_summons.csv.
        constexpr std::uint32_t ShamanEntry = 900174;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::chrono::milliseconds Ms(double seconds)
        {
            return std::chrono::milliseconds(std::uint64_t(std::max(0.0, seconds) * 1000.0 + 0.5));
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // What one Witch Doctor's Hex is doing: the rune cast last, the Angry Chicken's clock, the enemies hexed
        // (Unstable Form).
        struct State
        {
            std::uint32_t spellId = 0;
            Chicken chicken;
            Hexed hexed;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        Minions::Kind Shaman(Player*)
        {
            std::uint32_t const record = BaseId(Skill);
            Minions::Kind kind;
            kind.group = std::string(ShamanGroup);
            kind.entry = ShamanEntry;
            kind.record = record;
            kind.lifeMs = std::uint32_t(Ms(Numbers::Num(record, "duration_seconds")).count());
            kind.lifeToCopyPct = Tune("fetish_life_pct");
            kind.cap = 1;
            return kind;
        }

        // The Shaman standing for the owner when it is the one `chain` belongs to (its guid), else nothing: a chain ends with
        // the Shaman its cast raised.
        Creature* ShamanOf(Player* owner, std::uint64_t chain)
        {
            auto const standing = Minions::Standing(owner, ShamanGroup);
            if (standing.empty() || !ChainStands(chain, standing.front()->GetGUID().GetRawValue()))
                return nullptr;
            return standing.front();
        }

        // The Toad: the group is pulled in to the point, held for the swallow, then spat out with its poison, its slow
        // and the damage it takes.
        void Toad(Player* owner, std::uint32_t spellId, Position const& point, std::vector<Unit*> const& group)
        {
            std::vector<ObjectGuid> guids;
            for (Unit* enemy : group)
            {
                Abilities::Pull(enemy, point);
                guids.push_back(enemy->GetGUID());
            }
            double const dot = Numbers::Num(spellId, "dot_duration_seconds");
            double const tick = Tune("hex_toad_tick_seconds");
            unsigned const ticks = PoisonTicks(dot, tick);
            double const pct = PoisonTickPct(Numbers::Num(spellId, "damage_pct"), ticks);
            owner->m_Events.AddEventAtOffset(
                [owner, spellId, guids, dot, tick, ticks, pct]
                {
                    if (!owner->IsInWorld())
                        return;
                    for (ObjectGuid const guid : guids)
                    {
                        Unit* enemy = ObjectAccessor::GetUnit(*owner, guid);
                        if (!enemy || !enemy->IsAlive())
                            continue;
                        // "spits them back out with a layer of goo that deals {damage_pct} weapon damage as Poison over
                        // {dot_duration_seconds} seconds, Slows them, and increases their damage taken by
                        // {damage_taken_pct}."
                        Slow(owner, enemy, Tune("hex_toad_slow_pct"), dot);
                        EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"), dot);
                        for (unsigned i = 1; i <= ticks; ++i)
                            owner->m_Events.AddEventAtOffset(
                                [owner, spellId, guid, pct]
                                {
                                    Unit* target = owner->IsInWorld() ? ObjectAccessor::GetUnit(*owner, guid) : nullptr;
                                    if (target && target->IsAlive())
                                        Strike(owner, target, spellId, pct, true);
                                },
                                Ms(i * tick));
                    }
                },
                Ms(Tune("hex_toad_swallow_seconds")));
        }

        // Hedge Magic: "The Fetish Shaman will periodically heal allies for {heal_life} Life": the Witch Doctor and its
        // group within reach of the Shaman, every interval while it stands.
        void HealAllies(Player* owner, std::uint32_t spellId, std::uint64_t chain)
        {
            Creature* shaman = ShamanOf(owner, chain);
            if (!shaman || !owner->IsInWorld())
                return;
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info)
                return;
            double const reach = Tune("hex_hedge_magic_yards");
            std::vector<Player*> allies{owner};
            if (Group* group = owner->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    if (Player* member = ref->GetSource(); member && member != owner)
                        allies.push_back(member);
            for (Player* ally : allies)
                if (ally->IsAlive() && shaman->GetExactDist(ally) <= reach)
                {
                    double const amount = HedgeHeal(Numbers::Num(spellId, "heal_life"), Healing::At(ally->GetLevel()),
                                                    Healing::At(SheetLevel));
                    HealInfo heal(owner, ally, std::uint32_t(amount), info, SPELL_SCHOOL_MASK_NORMAL);
                    owner->HealBySpell(heal);
                }
            owner->m_Events.AddEventAtOffset([owner, spellId, chain] { HealAllies(owner, spellId, chain); },
                                             Ms(Tune("hex_hedge_magic_interval_seconds")));
        }

        // One cycle of the Shaman: the nearest enemy within its search radius is the centre, the group within the
        // group's radius of it is hexed (or toaded); the next cycle follows while the Shaman stands. `elapsedMs` is how far
        // into the Shaman's life this cycle falls.
        void Cycle(Player* owner, std::uint32_t spellId, Rune rune, std::uint64_t chain, std::uint64_t elapsedMs)
        {
            Creature* shaman = ShamanOf(owner, chain);
            if (!shaman || !owner->IsInWorld() || !owner->IsAlive())
                return;
            Unit* centre = nullptr;
            for (Unit* enemy : Enemies(owner, spellId, shaman->GetPosition(), Tune("hex_target_search_yards")))
                if (!centre || shaman->GetExactDist(enemy) < shaman->GetExactDist(centre))
                    centre = enemy;
            if (centre)
            {
                std::vector<Unit*> group;
                for (Unit* enemy : Enemies(owner, spellId, centre->GetPosition(), Tune("hex_group_radius_yards")))
                    if (InGroup(centre->GetExactDist(enemy), Tune("hex_group_radius_yards")))
                        group.push_back(enemy);
                if (rune == Rune::ToadOfHugeness)
                    Toad(owner, spellId, centre->GetPosition(), group);
                else
                {
                    double const seconds = Tune("hex_duration_seconds");
                    for (Unit* enemy : group)
                        if (HexEnemy(owner, enemy, seconds))
                        {
                            // "Hexed enemies take {damage_taken_pct} additional damage."
                            if (rune == Rune::Jinx)
                                EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"), seconds);
                            if (rune == Rune::UnstableForm)
                            {
                                std::lock_guard<std::mutex> guard(mutex);
                                states[Key(owner)].hexed.Mark(enemy->GetGUID().GetRawValue(), Now(),
                                                              Ms(seconds).count());
                            }
                        }
                }
            }
            std::uint64_t const cycleMs = std::uint64_t(Ms(Tune("hex_cycle_seconds")).count());
            if (auto const next = NextCycle(elapsedMs, cycleMs, std::uint64_t(Ms(Numbers::Num(spellId, "duration_seconds")).count())))
                owner->m_Events.AddEventAtOffset(
                    [owner, spellId, rune, chain, next] { Cycle(owner, spellId, rune, chain, *next); },
                    std::chrono::milliseconds(cycleMs));
        }

        // The Angry Chicken's explosion: "explode for {damage_pct} weapon damage as Poison to all enemies within
        // {radius_yards} yards".
        void Explode(Player* owner, std::uint32_t spellId)
        {
            EndChicken(owner);
            if (!owner->IsInWorld() || !owner->IsAlive())
                return;
            for (Unit* enemy : Enemies(owner, spellId, owner->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                Strike(owner, enemy, spellId, Numbers::Own(spellId, "damage_pct"));
        }

        // Unstable Form: "Hexed enemies explode when killed, dealing {damage_pct} weapon damage as Fire to all enemies
        // within {radius_yards} yards."
        class Deaths final : public UnitScript
        {
        public:
            Deaths()
                : UnitScript("dc_witch_doctor_hex_deaths", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* unit, Unit* /*killer*/) override
            {
                if (!unit)
                    return;
                struct Blast
                {
                    std::uint64_t owner;
                    std::uint32_t spellId;
                };
                std::vector<Blast> blasts;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    for (auto& [owner, state] : states)
                        if (state.hexed.Died(unit->GetGUID().GetRawValue(), Now()) &&
                            RuneAt(state.spellId) == Rune::UnstableForm)
                            blasts.push_back({owner, state.spellId});
                }
                for (Blast const& blast : blasts)
                    if (Player* owner = ObjectAccessor::FindPlayer(ObjectGuid(blast.owner));
                        owner && owner->IsInWorld())
                        for (Unit* enemy : Enemies(owner, blast.spellId, unit->GetPosition(),
                                                   Numbers::Num(blast.spellId, "radius_yards")))
                            if (enemy != unit)
                                Strike(owner, enemy, blast.spellId, Numbers::Own(blast.spellId, "damage_pct"));
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        {
            std::lock_guard<std::mutex> guard(mutex);
            states[Key(player)].spellId = spellId;
        }
        if (!RaisesShaman(rune))
        {
            // "Transform into an angry chicken for up to {duration_seconds} seconds that can explode": the Witch Doctor
            // is the chicken and runs faster; it explodes on the next press or when the time is over.
            double const seconds = Numbers::Num(spellId, "duration_seconds");
            TurnIntoChicken(player, seconds);
            SheetBuffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped, Tune("hex_angry_chicken_speed_pct"),
                              1, seconds);
            {
                std::lock_guard<std::mutex> guard(mutex);
                states[Key(player)].chicken.Start(Now(), Ms(seconds).count());
            }
            player->m_Events.AddEventAtOffset(
                [player, spellId]
                {
                    bool over;
                    {
                        std::lock_guard<std::mutex> guard(mutex);
                        over = states[Key(player)].chicken.Expired(Now());
                    }
                    if (over)
                        Explode(player, spellId);
                },
                Ms(seconds) + std::chrono::milliseconds(1));
            return;
        }
        Minions::Dismiss(player, ShamanGroup);
        Creature* shaman = Minions::Raise(player, "fetish_shaman", center);
        if (!shaman)
            return;
        // One chain of cycles for this Shaman, the first at once; each cycle starts the next.
        std::uint64_t const chain = shaman->GetGUID().GetRawValue();
        player->m_Events.AddEventAtOffset([player, spellId, rune, chain] { Cycle(player, spellId, rune, chain, 0); },
                                          Ms(0));
        if (rune == Rune::HedgeMagic)
            HealAllies(player, spellId, chain);
    }

    bool Press(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId) || RaisesShaman(RuneAt(spellId)))
            return false;
        bool pressed;
        {
            std::lock_guard<std::mutex> guard(mutex);
            pressed = states[Key(player)].chicken.Press(Now());
        }
        if (pressed)
            Explode(player, spellId);
        return pressed;
    }

    void Register()
    {
        Minions::Define("fetish_shaman", Shaman);
        new Deaths();
    }
} // namespace DC::Combat::WitchDoctor::Hex
