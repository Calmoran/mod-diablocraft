/*
 * Mass Confusion and its five runes. The cast is the engine's self-centred area cast (a spell record and the sheet's
 * numbers: the cooldown, the radius, each rune's school, Unstable Realm's shorter cooldown); here: the confusion that
 * takes about half the enemies in the area and turns them to fight for the Witch Doctor, and each rune's part:
 * Paranoia's weakness, Mass Hysteria's stun, Mass Hallucination's giant spirit, Devolution's Zombie Dog for a confused
 * enemy that dies.
 */

#include "dc_witch_doctor_mass_confusion.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_pets.h"
#include "../../combat/dc_charm_effect.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_periodic_strike.h"
#include "../../combat/dc_spell_numbers.h"
#include "Creature.h"
#include "GameTime.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <chrono>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <utility>

namespace DC::Combat::WitchDoctor::MassConfusion
{
    namespace
    {
        constexpr std::string_view Skill = "Mass Confusion";

        // Devolution's enemy: the Witch Doctor and the record that confused it, and until when it counts as confused.
        struct Held
        {
            std::uint64_t owner = 0;
            std::uint32_t spellId = 0;
            std::uint64_t until = 0;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Held> confused; // by enemy

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The giant spirit's walk: where it stands now, and the ticks it has left.
        struct Walk
        {
            Spot at;
            float z = 0;
            unsigned left = 0;
        };

        void Rampage(Player* player, std::uint32_t spellId, std::shared_ptr<Walk> walk)
        {
            player->m_Events.AddEventAtOffset(
                [player, spellId, walk]
                {
                    if (!player->IsAlive() || !player->IsInWorld() || walk->left == 0)
                        return;
                    --walk->left;
                    Position here(float(walk->at.x), float(walk->at.y), walk->z);
                    // It walks towards the nearest enemy within the cast's radius, and strikes every enemy within its
                    // own.
                    Unit* nearest = nullptr;
                    for (Unit* enemy : Combat::Enemies(player, spellId, here, Tune("mass_confusion_radius_yards")))
                        if (!nearest || here.GetExactDist(enemy) < here.GetExactDist(nearest))
                            nearest = enemy;
                    double const tick = Tune("mass_confusion_spirit_tick_seconds");
                    if (nearest)
                    {
                        walk->at = Advance(walk->at, {nearest->GetPositionX(), nearest->GetPositionY()},
                                           StepYards(Tune("mass_confusion_spirit_speed_per_frame"), tick));
                        walk->z = nearest->GetPositionZ();
                    }
                    Position there(float(walk->at.x), float(walk->at.y), walk->z);
                    // "dealing {damage_pct} weapon damage per second as Physical to enemies it passes through": a
                    // tick's share.
                    for (Unit* enemy :
                         Combat::Enemies(player, spellId, there, Tune("mass_confusion_spirit_radius_yards")))
                        Combat::Strike(player, enemy, spellId, PerTick(Numbers::Num(spellId, "damage_pct"), tick),
                                       true);
                    Rampage(player, spellId, walk);
                },
                std::chrono::milliseconds(std::uint32_t(Tune("mass_confusion_spirit_tick_seconds") * 1000.0 + 0.5)));
        }

        // Devolution: "Enemies killed while Confused have a {proc_chance_pct} chance to spawn a Zombie Dog": an enemy the
        // confusion took, charmed or confused, rolls once when it dies before the confusion ends.
        class Deaths final : public UnitScript
        {
        public:
            Deaths()
                : UnitScript("dc_witch_doctor_devolution", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* victim, Unit*) override
            {
                Creature* creature = victim ? victim->ToCreature() : nullptr;
                if (!creature)
                    return;
                Held held;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto const found = confused.find(creature->GetGUID().GetRawValue());
                    if (found == confused.end())
                        return;
                    held = found->second;
                    confused.erase(found);
                }
                Player* witchDoctor = ObjectAccessor::FindPlayer(ObjectGuid(held.owner));
                if (!witchDoctor || !Confused(Now(), held.until) ||
                    !Rises(frand(0.0f, 100.0f), Numbers::Num(held.spellId, "proc_chance_pct")))
                    return;
                // Not inside the kill: the dog rises a moment after, on the Witch Doctor's own queue, when it has room.
                Position const at = creature->GetPosition();
                witchDoctor->m_Events.AddEventAtOffset([witchDoctor, at] { Pets::RaiseDogAt(witchDoctor, at); },
                                                       std::chrono::milliseconds(100));
            }
        };

        // `enemy` was taken by the confusion for `seconds`: its death counts until they end.
        void Watch(Player* player, Unit* enemy, std::uint32_t spellId, double seconds)
        {
            std::uint64_t const now = Now();
            std::lock_guard<std::mutex> guard(mutex);
            std::erase_if(confused, [now](auto const& entry) { return !Confused(now, entry.second.until); });
            confused[enemy->GetGUID().GetRawValue()] = {player->GetGUID().GetRawValue(), spellId, now + HeldMs(seconds)};
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        double const seconds = Numbers::Num(BaseId(Skill), "charm_duration_seconds");
        // "Incite paranoia in enemies, confusing them and causing some to be Charmed and fight for you": the proportion
        // of the enemies in the area the confusion takes are charmed for its seconds, or confused where the charm
        // cannot hold.
        std::vector<Unit*> missed;
        for (Unit* enemy : targets)
        {
            if (!Affected(frand(0.0f, 1.0f), Tune("mass_confusion_affected_proportion")))
            {
                missed.push_back(enemy);
                continue;
            }
            if (!CharmEffect::Apply(player, enemy, spellId, seconds))
                Confuse(player, enemy, seconds);
            if (rune == Rune::Devolution)
                Watch(player, enemy, spellId, seconds);
        }
        switch (rune)
        {
            case Rune::Paranoia:
                // "All enemies in the area of Mass Confusion deal {enemy_damage_pct} less damage for {duration_seconds}
                // seconds."
                for (Unit* enemy : targets)
                    EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"),
                                         Numbers::Num(spellId, "duration_seconds"));
                break;
            case Rune::MassHysteria:
                // "Up to {target_count} enemies who are not Confused become Stunned for {stun_duration_seconds}
                // seconds."
                for (unsigned index = 0, stunned = ToStun(unsigned(missed.size()),
                                                          unsigned(Numbers::Num(spellId, "target_count")));
                     index < stunned; ++index)
                    Stun(player, missed[index],
                         Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                break;
            case Rune::MassHallucination:
            {
                // "a giant spirit rampages through enemies": it starts at the Witch Doctor and walks for the
                // confusion's seconds.
                auto walk = std::make_shared<Walk>();
                walk->at = {player->GetPositionX(), player->GetPositionY()};
                walk->z = player->GetPositionZ();
                walk->left = PeriodicStrike::Ticks(seconds, Tune("mass_confusion_spirit_tick_seconds"));
                Rampage(player, spellId, walk);
                break;
            }
            default:
                break;
        }
    }

    void RegisterScripts()
    {
        new Deaths();
    }
} // namespace DC::Combat::WitchDoctor::MassConfusion
