/*
 * Six Monk passives: Harmony, Combination Strike, Near Death Experience, Unity, Momentum, Mythic Rhythm. A
 * passive is on when it is in one of the Monk's passive slots (Passives::Has, which also answers for the ones a worn
 * item grants). Numbers are monk_passive_values.csv through Numbers::Num; the few the sheet leaves out are monk.csv
 * tunables with the power file's value.
 */

#include "dc_monk_passives_harmony_cast.h"
#include "dc_monk_mantras.h"
#include "dc_monk_passives_harmony.h"
#include "dc_monk_seven_sided_strike.h"
#include "dc_monk_spirit.h"
#include "dc_monk_common.h"
#include "../dc_resources.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_passives.h"
#include "../../stats/dc_stats.h"
#include "Group.h"
#include "ScriptMgr.h"

#include <array>

namespace DC::Combat::Monk::PassivesHarmony
{
    namespace
    {
        // Per Monk: the passives' module state. One mutex; nothing is called outside this file while it is held.
        struct State
        {
            Combination combination;
            Rhythm rhythm;
            Momentum momentum;
            NearDeath nearDeath;
            // Momentum's last sample: where the Monk stood and on which map.
            bool sampled = false;
            float x = 0, y = 0;
            std::uint32_t map = 0;
            std::uint32_t sampleMs = 0;
            // Harmony: the item resistances the contributions were made from, and whether they are on the sheet.
            std::uint32_t harmonyMs = 0;
            bool harmonyChecked = false;
            bool harmonyApplied = false;
            std::array<double, 7> harmonyItems{};
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, State> states;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(seconds * 1000.0 + 0.5);
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint32_t PassiveId(std::string_view name)
        {
            for (auto const& passive : Shells::Passives)
                if (name == passive.name)
                    return passive.id;
            return 0;
        }

        bool Has(Player* player, char const* name)
        {
            return player && Passives::Has(player, name);
        }

        bool IsMonk(Player* player)
        {
            return Classes::ClassIdOf(player) == Resources::Spirit.classId;
        }

        // Spirit Generators are the Primary skills; Spirit Spenders the skills with a Spirit cost that are neither
        // Primary nor a Mantra (whose cost is an activation).
        bool IsGenerator(std::uint32_t spellId)
        {
            return Classes::CategoryOf(spellId) == "Primary";
        }

        bool IsSpender(std::uint32_t spellId)
        {
            std::string const category = Classes::CategoryOf(spellId);
            return !category.empty() && category != "Primary" && category != "Mantras" &&
                   Numbers::Get(spellId, "cost_resource").value_or(0) > 0;
        }

        // The Mantra skill's own spell id (its record without a rune), the key of the shared "only one Mantra" state.
        std::uint32_t BaseMantra(std::string_view skill)
        {
            for (auto const& ability : Shells::Abilities)
                if (skill == ability.skill && !*ability.rune)
                    return ability.id;
            return 0;
        }

        // The Mantra on one of the Monk's skill buttons that is in force (dc_monk_mantras.h: the one cast last, or any
        // slotted one while none is cast); 0 when none.
        std::uint32_t SlottedMantra(Player* player)
        {
            for (Classes::Slot const& slot : Classes::Bar(player))
            {
                auto const* row = Shells::FindAbility(slot.spellId);
                if (row && std::string_view(row->skill).starts_with("Mantra of ") &&
                    Mantras::On(player->GetGUID().GetRawValue(), BaseMantra(row->skill)))
                    return slot.spellId;
            }
            return 0;
        }

        // "Each ally affected by your Mantras": the group members within the Mantra's radius of the Monk, alive.
        unsigned AlliesAffected(Player* monk)
        {
            std::uint32_t const mantra = SlottedMantra(monk);
            Group* group = monk->GetGroup();
            if (!mantra || !group)
                return 0;
            double const radius = Numbers::Num(mantra, "radius_yards");
            unsigned count = 0;
            for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                if (Player* member = ref->GetSource())
                    if (member != monk && member->IsAlive() && monk->IsWithinDistInMap(member, radius))
                        ++count;
            return count;
        }

        // Unity's other side: the group's Monks with Unity whose Mantra reaches this player.
        unsigned UnityMonksOver(Player* player)
        {
            Group* group = player->GetGroup();
            if (!group)
                return 0;
            unsigned count = 0;
            for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                if (Player* member = ref->GetSource())
                    if (member != player && member->IsAlive() && Has(member, "Unity"))
                        if (std::uint32_t mantra = SlottedMantra(member);
                            mantra && member->IsWithinDistInMap(player, Numbers::Num(mantra, "radius_yards")))
                            ++count;
            return count;
        }

        // Harmony: the item resistances in, the contributions out. Called about once a second for a Monk.
        void SyncHarmony(Player* player, State& state, bool has)
        {
            std::uint32_t const id = PassiveId("Harmony");
            if (!id)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            auto remove = [&]
            {
                for (unsigned e = 0; e < ElementCount; ++e)
                    Stats::RemoveContribution(guid, Source::Passives, Stat::SingleResistance, id * ElementCount + e);
                Stats::RemoveContribution(guid, Source::Passives, Stat::AllResistance, id);
                Stats::Recompute(player);
            };
            if (!has)
            {
                // The first look after login also clears what an earlier session saved.
                if (state.harmonyApplied || !state.harmonyChecked)
                    remove();
                state.harmonyApplied = false;
                state.harmonyChecked = true;
                return;
            }
            std::array<double, 7> items{};
            for (unsigned e = 0; e < ElementCount; ++e)
                items[e] = Stats::Sum(guid, Source::Items, Stat::SingleResistance, static_cast<Element>(e));
            if (state.harmonyApplied && items == state.harmonyItems)
                return;
            HarmonyResult const result = Harmony(items, Numbers::Num(id, "resistance_share_pct"));
            for (unsigned e = 0; e < ElementCount; ++e)
                Stats::AddContribution(guid, {Source::Passives, Stat::SingleResistance, id * ElementCount + e,
                                              result.single[e], Bucket::Flat, static_cast<Element>(e)});
            Stats::AddContribution(guid, {Source::Passives, Stat::AllResistance, id, result.all, Bucket::Flat});
            Stats::Recompute(player);
            state.harmonyItems = items;
            state.harmonyApplied = true;
            state.harmonyChecked = true;
        }

        // Momentum: the yards the Monk moved since the last sample.
        void SampleMomentum(Player* player, State& state)
        {
            if (!player->IsAlive() || state.map != player->GetMapId() || !state.sampled)
            {
                state.sampled = player->IsAlive();
                state.map = player->GetMapId();
                state.x = player->GetPositionX();
                state.y = player->GetPositionY();
                return;
            }
            double const moved = player->GetExactDist2d(state.x, state.y);
            state.x = player->GetPositionX();
            state.y = player->GetPositionY();
            std::uint32_t const id = PassiveId("Momentum");
            if (id)
                state.momentum.Moved(moved, Now(), Numbers::Num(id, "distance_yards"),
                                     Millis(Numbers::Num(id, "duration_seconds")));
        }

        // Near Death Experience's immunity: every control mechanic the core knows, as Serenity's (the core's "Immune
        // Movement Impairment and Loss of Control" less the ones that only slow).
        constexpr Mechanics LossOfControl[] = {
            MECHANIC_CHARM,   MECHANIC_DISORIENTED, MECHANIC_FEAR,     MECHANIC_ROOT,      MECHANIC_SLEEP,
            MECHANIC_STUN,    MECHANIC_FREEZE,      MECHANIC_KNOCKOUT, MECHANIC_POLYMORPH, MECHANIC_BANISH,
            MECHANIC_SHACKLE, MECHANIC_TURN,        MECHANIC_HORROR,   MECHANIC_SAPPED};

        void Immunity(Player* player, std::uint32_t key, bool apply)
        {
            for (Mechanics mechanic : LossOfControl)
                player->ApplySpellImmune(key, IMMUNITY_MECHANIC, mechanic, apply);
        }

        // "When receiving fatal damage, you instead restore {heal_pct} Life and {gain_pct} Spirit and are immune to
        // damage and control impairing effects for {duration_seconds} seconds": `damage` becomes 0, then the immunity
        // eats the rest.
        void NearDeathExperience(Player* player, std::uint32_t& damage)
        {
            if (!player || !damage || !IsMonk(player))
                return;
            std::uint32_t const id = PassiveId("Near Death Experience");
            bool const has = id && Has(player, "Near Death Experience");
            std::uint64_t const now = Now();
            bool saved = false;
            {
                std::lock_guard<std::mutex> guard(mutex);
                NearDeath& near = states[player->GetGUID().GetRawValue()].nearDeath;
                if (near.Immune(now))
                {
                    damage = 0;
                    return;
                }
                saved = has && near.Save(now, damage, player->GetHealth(),
                                         Millis(Numbers::Num(id, "internal_cooldown_seconds")),
                                         Millis(Numbers::Num(id, "duration_seconds")));
            }
            if (!saved)
                return;
            damage = 0;
            player->SetHealth(std::uint32_t(
                NearDeathHealth(player->GetHealth(), player->GetMaxHealth(), Numbers::Num(id, "heal_pct"))));
            double const maxSpirit =
                double(Resources::MaxUnits(player, Resources::Spirit)) / Resources::ToUnits(Resources::Spirit, 1.0);
            Resources::Energize(player, Resources::Spirit, id, maxSpirit * Numbers::Num(id, "gain_pct") / 100.0, false);
            Immunity(player, id, true);
            std::uint64_t mask = 0;
            for (Mechanics mechanic : LossOfControl)
                mask |= 1ULL << mechanic;
            player->RemoveAurasWithMechanic(mask);
            // D3's knockback (SF_3 radius 25, SF_4 magnitude 15 yards): the enemies around are knocked back by the ability
            // knockback, as Tempest Rush's are (SF_5 height and SF_6 gravity are its own arc). Next tick, not inside the damage
            // hook.
            player->m_Events.AddEventAtOffset(
                [player, id]
                {
                    if (!player->IsInWorld())
                        return;
                    for (Unit* enemy : Combat::Enemies(player, id, player->GetPosition(),
                                                       Tune("near_death_experience_knockback_radius_yards")))
                        if (enemy->IsAlive())
                            Abilities::Knockback(player, enemy, Tune("near_death_experience_knockback_yards"));
                },
                Milliseconds(1));
            player->m_Events.AddEventAtOffset([player, id] { Immunity(player, id, false); },
                                              Milliseconds(Millis(Numbers::Num(id, "duration_seconds"))));
        }

        class Damage final : public UnitScript
        {
        public:
            Damage()
                : UnitScript("dc_monk_passives_harmony_damage", true, {UNITHOOK_ON_DAMAGE})
            {
            }

            void OnDamage(Unit* /*attacker*/, Unit* victim, std::uint32_t& damage) override
            {
                if (Player* player = victim ? victim->ToPlayer() : nullptr)
                    NearDeathExperience(player, damage);
            }
        };

        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_monk_passives_harmony_update",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, std::uint32_t diff) override
            {
                if (!player || !IsMonk(player))
                    return;
                bool const momentum = Has(player, "Momentum");
                bool const harmony = Has(player, "Harmony");
                std::lock_guard<std::mutex> guard(mutex);
                State& state = states[player->GetGUID().GetRawValue()];
                state.sampleMs += diff;
                state.harmonyMs += diff;
                if (momentum && state.sampleMs >= Millis(Tune("momentum_tick_seconds")))
                {
                    state.sampleMs = 0;
                    SampleMomentum(player, state);
                }
                else if (!momentum)
                    state.sampled = false;
                if (state.harmonyMs >= Millis(Tune("harmony_check_seconds")) || !state.harmonyChecked)
                {
                    state.harmonyMs = 0;
                    SyncHarmony(player, state, harmony);
                }
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                states.erase(player->GetGUID().GetRawValue());
            }

            // A new map: the next sample starts the distance again, so a teleport is not yards moved.
            void OnPlayerMapChanged(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                states[player->GetGUID().GetRawValue()].sampled = false;
            }
        };
    } // namespace

    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!player)
            return;
        // Each is a separate multiplier of its own, as D3's passives are.
        bool const combination = Has(player, "Combination Strike");
        bool const rhythm = Has(player, "Mythic Rhythm") && IsSpender(spellId);
        bool const momentum = Has(player, "Momentum");
        if (combination || rhythm || momentum)
        {
            std::lock_guard<std::mutex> guard(mutex);
            State& state = states[player->GetGUID().GetRawValue()];
            if (combination)
                if (double pct = state.combination.Bonus(Now(), Numbers::Num(PassiveId("Combination Strike"), "damage_bonus_pct")))
                    AddFactor(out, "Combination Strike", pct);
            if (rhythm)
                if (double pct = state.rhythm.Bonus(Numbers::Num(PassiveId("Mythic Rhythm"), "damage_bonus_pct"),
                                                    SevenSided::Is(spellId)))
                    AddFactor(out, "Mythic Rhythm", pct);
            if (momentum && state.momentum.On(Now()))
                AddFactor(out, "Momentum", Numbers::Num(PassiveId("Momentum"), "damage_bonus_pct"));
        }
        if (std::uint32_t const id = PassiveId("Unity"))
        {
            if (Has(player, "Unity"))
                if (double pct = UnitySelf(AlliesAffected(player), Numbers::Num(id, "damage_bonus_pct", "self"),
                                           Numbers::Num(id, "max_bonus_pct")))
                    AddFactor(out, "Unity", pct);
            if (double pct = UnityAlly(UnityMonksOver(player), Numbers::Num(id, "damage_bonus_pct", "ally"),
                                       unsigned(Tune("unity_ally_max_stacks"))))
                AddFactor(out, "Unity (ally)", pct);
        }
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player)
            return;
        bool const generator = IsGenerator(spellId) && Has(player, "Combination Strike");
        bool const spender = IsSpender(spellId) && Has(player, "Mythic Rhythm");
        if (!generator && !spender)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        State& state = states[player->GetGUID().GetRawValue()];
        if (generator)
            state.combination.Use(Classes::SkillIdOf(spellId), Now(),
                                  Millis(Numbers::Num(PassiveId("Combination Strike"), "duration_seconds")));
        // Seven-Sided Strike's strikes come after its cast (Monk::Delayed): they carry what the cast spent.
        if (spender && SevenSided::Is(spellId))
            state.rhythm.Carry();
        else if (spender)
            state.rhythm.Spend();
    }

    void Connected(Player* player, std::uint32_t spellId)
    {
        if (!player || !IsGenerator(spellId) || !Has(player, "Mythic Rhythm"))
            return;
        unsigned const hitCount = unsigned(Tune("mythic_rhythm_generator_hits"));
        std::lock_guard<std::mutex> guard(mutex);
        states[player->GetGUID().GetRawValue()].rhythm.Hit(hitCount);
    }

    void RegisterScripts()
    {
        new Damage();
        new Update();
    }
} // namespace DC::Combat::Monk::PassivesHarmony
