/*
 * Marked for Death and its five runes. The cast is the engine's single-enemy spell (a record, its Discipline cost, the
 * sheet's numbers); here: the mark on the enemy ("takes {damage_bonus_pct} additional damage" from every attacker, the
 * shared enemy effect), Grim Reaper's share of the damage it takes, Contagion's spread when it dies, Valley of Death's
 * marked area, Mortal Enemy's Hatred and Death Toll's heal for the attacks that land on it.
 */

#include "dc_demon_hunter_marked_for_death.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_proc_math.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "ObjectAccessor.h"
#include "ObjectGuid.h"
#include "Player.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::MarkedForDeath
{
    namespace
    {
        constexpr std::string_view Skill = "Marked for Death";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        struct Mark
        {
            ObjectGuid owner;
            std::uint32_t spellId = 0;
            std::uint64_t endsAt = 0; // game time, ms
        };

        // Valley of Death's marked ground.
        struct Area
        {
            std::uint32_t spellId = 0;
            Position center;
            double left = 0;  // ms
            double clock = 0; // ms since the last tick
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Mark> marks;              // by the marked enemy
        std::unordered_map<std::uint64_t, std::vector<Area>> areas; // by the Demon Hunter

        // Splashed damage lands through the engine too and must not be shared again.
        thread_local bool sharing = false;

        // The mark an enemy carries now, if any.
        std::optional<Mark> MarkOn(Unit const* enemy)
        {
            if (!enemy)
                return std::nullopt;
            std::lock_guard<std::mutex> guard(mutex);
            auto found = marks.find(enemy->GetGUID().GetRawValue());
            if (found == marks.end() || !On(found->second.endsAt, Now()))
                return std::nullopt;
            return found->second;
        }

        // "Mark an enemy. The marked enemy takes {damage_bonus_pct} additional damage for the next {duration_seconds}
        // seconds": from every attacker. Marking it again restarts it. Custom Engineering lengthens it (the power file's SF_17).
        void MarkEnemy(Player* owner, Unit* enemy, std::uint32_t spellId)
        {
            double const seconds = Numbers::Num(spellId, "duration_seconds") * Passive::DurationFactor(owner, "Marked for Death");
            std::uint64_t const now = Now();
            {
                std::lock_guard<std::mutex> guard(mutex);
                std::erase_if(marks, [now](auto const& entry) { return !On(entry.second.endsAt, now); });
                marks[enemy->GetGUID().GetRawValue()] = {owner->GetGUID(), spellId, EndsAt(now, seconds)};
            }
            EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_bonus_pct"), seconds);
        }

        // The enemy died: "the mark spreads to the closest {target_count} enemies within {radius_yards} yards. This
        // effect can chain repeatedly" (each new mark spreads again when its enemy dies).
        void Spread(Player* owner, Unit* dead, Mark const& mark)
        {
            std::vector<Unit*> near;
            for (Unit* enemy :
                 Combat::Enemies(owner, mark.spellId, dead->GetPosition(), Numbers::Num(mark.spellId, "radius_yards")))
                if (enemy != dead)
                    near.push_back(enemy);
            std::vector<double> distances;
            for (Unit* enemy : near)
                distances.push_back(dead->GetExactDist(enemy));
            for (std::size_t place : Nearest(distances, std::size_t(Numbers::Num(mark.spellId, "target_count"))))
                MarkEnemy(owner, near[place], mark.spellId);
        }

        class Marks final : public UnitScript
        {
        public:
            Marks()
                : UnitScript("dc_demon_hunter_marked_for_death", true, {UNITHOOK_ON_DAMAGE, UNITHOOK_ON_UNIT_DEATH})
            {
            }

            // Grim Reaper: a share of what the marked enemy takes, from whoever deals it.
            void OnDamage(Unit* /*attacker*/, Unit* victim, uint32& damage) override
            {
                if (sharing || !damage)
                    return;
                auto const mark = MarkOn(victim);
                if (!mark || RuneAt(mark->spellId) != Rune::GrimReaper)
                    return;
                Player* owner = ObjectAccessor::FindConnectedPlayer(mark->owner);
                if (!owner || !owner->IsAlive())
                    return;
                std::vector<Unit*> others;
                for (Unit* enemy : Combat::Enemies(owner, mark->spellId, victim->GetPosition(),
                                                   Numbers::Num(mark->spellId, "radius_yards")))
                    if (enemy != victim)
                        others.push_back(enemy);
                Combat::Hit hit;
                hit.total = SharePerEnemy(damage, Numbers::Num(mark->spellId, "damage_share_pct"), others.size());
                if (hit.total <= 0)
                    return;
                Scope scope(sharing);
                for (Unit* enemy : others)
                    Combat::DealHit(owner, enemy, mark->spellId, hit, true);
            }

            void OnUnitDeath(Unit* unit, Unit* /*killer*/) override
            {
                if (!unit)
                    return;
                std::optional<Mark> mark;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = marks.find(unit->GetGUID().GetRawValue());
                    if (found == marks.end())
                        return;
                    if (On(found->second.endsAt, Now()))
                        mark = found->second;
                    marks.erase(found);
                }
                if (!mark || RuneAt(mark->spellId) != Rune::Contagion)
                    return;
                Player* owner = ObjectAccessor::FindConnectedPlayer(mark->owner);
                if (owner && owner->IsAlive())
                    Spread(owner, unit, *mark);
            }
        };

        // Valley of Death: every tick the enemies in an area are marked for the buff's seconds, so the mark holds while
        // they stand there and lapses soon after they leave.
        class Areas final : public PlayerScript
        {
        public:
            Areas()
                : PlayerScript("dc_demon_hunter_marked_for_death_areas",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                std::vector<Area> mine;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = areas.find(player->GetGUID().GetRawValue());
                    if (found == areas.end())
                        return;
                    mine = found->second;
                }
                if (!player->IsAlive())
                {
                    Stop(player);
                    return;
                }
                std::vector<Area> kept;
                for (Area& area : mine)
                {
                    unsigned const ticks = Due(area.clock, diff, Tune("marked_for_death_area_tick_seconds") * 1000.0);
                    for (unsigned i = 0; i < ticks; ++i)
                        for (Unit* enemy : Combat::Enemies(player, area.spellId, area.center,
                                                           Numbers::Num(area.spellId, "radius_yards")))
                            EnemyEffects::Taken(enemy, area.spellId, Numbers::Num(area.spellId, "damage_bonus_pct"),
                                                Tune("marked_for_death_area_buff_seconds"));
                    area.left -= diff;
                    if (area.left > 0)
                        kept.push_back(area);
                }
                std::lock_guard<std::mutex> guard(mutex);
                auto found = areas.find(player->GetGUID().GetRawValue());
                if (found == areas.end())
                    return;
                // Areas marked during this update were added to the stored list; keep them with what still stands.
                for (std::size_t i = mine.size(); i < found->second.size(); ++i)
                    kept.push_back(found->second[i]);
                found->second = std::move(kept);
            }

            void OnPlayerLogout(Player* player) override
            {
                Stop(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Stop(player);
            }

            static void Stop(Player* player)
            {
                std::lock_guard<std::mutex> guard(mutex);
                areas.erase(player->GetGUID().GetRawValue());
            }
        };
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
        if (RuneAt(spellId) == Rune::ValleyOfDeath)
        {
            // "Mark an area on the ground ... for {duration_seconds} seconds": where the enemy aimed at stands. Custom Engineering
            // lengthens it (the power file's SF_18); the buff the area re-applies is not.
            if (targets.empty())
                return;
            Area area;
            area.spellId = spellId;
            area.center = targets.front()->GetPosition();
            area.left = Numbers::Num(spellId, "duration_seconds") * Passive::DurationFactor(player, "Marked for Death") * 1000.0;
            std::lock_guard<std::mutex> guard(mutex);
            areas[player->GetGUID().GetRawValue()].push_back(area);
            return;
        }
        for (Unit* enemy : targets)
            MarkEnemy(player, enemy, spellId);
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        auto const mark = MarkOn(target);
        if (!player || !mark)
            return;
        // Both effects scale with the proc coefficient of the attack that landed (D3's rule for what a hit pays or heals).
        auto const coefficient = Numbers::Get(spellId, "proc_coefficient");
        switch (RuneAt(mark->spellId))
        {
            case Rune::MortalEnemy:
                // "Attacks you make against the marked enemy generate {gain_resource} Hatred."
                if (player->GetGUID() == mark->owner)
                    if (double const gain = Proc::Scaled(coefficient, Numbers::Num(mark->spellId, "gain_resource")); gain > 0)
                        Resources::Energize(player, Resources::Hatred, mark->spellId, gain);
                break;
            case Rune::DeathToll:
                // "Attackers heal for up to {heal_pct} of their maximum Life when damaging the marked enemy."
                if (double const heal = Proc::Scaled(coefficient, LifeBack(player->GetMaxHealth(), Numbers::Num(mark->spellId, "heal_pct")));
                    heal > 0)
                    Heal(player, mark->spellId, heal);
                break;
            default:
                break;
        }
    }

    void RegisterScripts()
    {
        new Marks();
        new Areas();
    }
} // namespace DC::Combat::DemonHunter::MarkedForDeath
