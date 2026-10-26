/*
 * Fire Elemental and its five runes: the aura that burns the enemies around the Shaman every tick for its seconds, the
 * echo of each Secondary cast, Meteor Call's crash when it is summoned, Storm Elemental's chain and attack speed, Water
 * Elemental's chill and heal and Magma Elemental's boulder. The elemental is skill damage of the Shaman, not a
 * creature: one at a time, a new cast replaces it. The cast is the engine's summon spell and deals nothing at once (the
 * record states a duration); the dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_fire_elemental.h"
#include "dc_shaman_chill.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "dc_shaman_passives.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_minions.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "Map.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Shaman::FireElemental
{
    namespace
    {
        constexpr std::string_view Skill = "Fire Elemental";
        // The creature the elemental shows as (data/d3/shaman_elemental_summons.csv): untargetable, it follows the Shaman and deals
        // nothing itself.
        constexpr std::uint32_t Entry = 900190;
        constexpr char const* Group = "fire_elemental";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? RuneOf(row->rune) : Rune::None;
        }

        // The record of the skill itself: the numbers a rune takes from it are stated there.
        std::uint32_t BaseId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        double Tune(char const* name)
        {
            return Tunables::Get("combat", name);
        }

        // The Fire Elemental a Shaman has up: the record of the cast, until when, and the stamp its ticks answer to (a
        // new cast takes a new stamp and the old ticks find theirs gone and stop).
        struct Standing
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            std::uint64_t until = 0; // game time, ms
            std::uint64_t stamp = 0;
            Map const* map = nullptr;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Standing> standing; // by the Shaman
        std::uint64_t stamps = 0;

        // Storm Elemental's attack speed, put on the sheet and taken off.
        void PutSpeed(Player* player, double pct)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            Stats::RemoveContribution(guid, Source::Temporary, Stat::AttackSpeed, BaseId());
            if (pct > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::AttackSpeed, BaseId(), pct, Bucket::Flat});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        void End(Player* player, std::uint64_t key, std::uint64_t stamp)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = standing.find(key);
                if (found == standing.end() || found->second.stamp != stamp)
                    return;
                standing.erase(found);
            }
            PutSpeed(player, 0);
            Minions::Dismiss(player, Group);
        }

        // "The echo chains to {target_count} more enemies at {damage_share_pct} damage."
        void Chain(Player* player, Unit* from, std::uint32_t spellId, double echoPct)
        {
            std::vector<Unit*> near =
                Combat::Enemies(player, spellId, from->GetPosition(), Tune("fire_elemental_chain_radius_yards"));
            near.erase(std::remove(near.begin(), near.end(), from), near.end());
            std::sort(near.begin(), near.end(),
                      [from](Unit* a, Unit* b) { return from->GetExactDist(a) < from->GetExactDist(b); });
            auto const count = std::size_t(Numbers::Num(spellId, "target_count"));
            if (near.size() > count)
                near.resize(count);
            for (Unit* enemy : near)
                Combat::Strike(player, enemy, spellId, ChainedPct(echoPct, Numbers::Num(spellId, "damage_share_pct")));
        }

        // "Each time you cast a Secondary skill, it echoes the cast with a Fire Blast at your target."
        void Echo(Player* player, Standing const& elemental, Unit* target)
        {
            std::uint32_t const spellId = elemental.spellId;
            double const pct = Numbers::Num(spellId, "damage_pct", "echo");
            switch (elemental.rune)
            {
                case Rune::MagmaElemental:
                    // "The echo is a falling boulder that Knocks Down enemies within {radius_yards} yards for
                    // {duration_seconds} second."
                    for (Unit* enemy :
                         Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                    {
                        Combat::Strike(player, enemy, spellId, pct);
                        if (enemy->IsAlive())
                            Stun(player, enemy, Numbers::Num(spellId, "duration_seconds"));
                    }
                    break;
                case Rune::StormElemental:
                    Combat::Strike(player, target, spellId, pct);
                    Chain(player, target, spellId, pct);
                    break;
                default:
                    Combat::Strike(player, target, spellId, pct);
                    break;
            }
        }

        void Tick(Player* player, std::uint64_t key, std::uint64_t stamp, unsigned left, double pct,
                  std::uint32_t intervalMs)
        {
            Standing elemental;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = standing.find(key);
                if (found == standing.end() || found->second.stamp != stamp)
                    return;
                elemental = found->second;
            }
            // The Shaman is gone, dead or on another floor: the elemental ends.
            if (!player->IsInWorld() || !player->IsAlive() || player->GetMap() != elemental.map)
            {
                End(player, key, stamp);
                return;
            }
            std::uint32_t const spellId = elemental.spellId;
            // "It burns enemies within {radius_yards} yards of you for {damage_pct:aura} weapon damage as Fire per
            // second."
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
            {
                Combat::Strike(player, enemy, spellId, pct, true);
                // Water Elemental: "The aura Chills by {chill_pct}".
                if (elemental.rune == Rune::WaterElemental && enemy->IsAlive())
                    Chill(player, enemy, Numbers::Num(spellId, "chill_pct"), ChillSeconds(intervalMs / 1000.0));
            }
            // Water Elemental: "you heal {life_regen_pct} of maximum Life per second".
            if (elemental.rune == Rune::WaterElemental)
                Heal(player, spellId,
                     HealPerTick(double(player->GetMaxHealth()), Numbers::Num(spellId, "life_regen_pct"),
                                 intervalMs / 1000.0));
            if (left > 1)
            {
                player->m_Events.AddEventAtOffset([player, key, stamp, left, pct, intervalMs]
                                                  { Tick(player, key, stamp, left - 1, pct, intervalMs); },
                                                  std::chrono::milliseconds(intervalMs));
                return;
            }
            End(player, key, stamp);
        }

        // "When summoned, it crashes into the target location for {damage_pct} weapon damage as Fire": the place of the
        // Shaman's target, or the Shaman's own when they have none.
        void Crash(Player* player, std::uint32_t spellId)
        {
            Unit* selected = player->GetSelectedUnit();
            Position const at = selected && selected->IsAlive() ? selected->GetPosition() : player->GetPosition();
            for (Unit* enemy : Combat::Enemies(player, spellId, at, Numbers::Num(spellId, "radius_yards")))
                Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));
        }

        void Start(Player* player, std::uint32_t spellId)
        {
            Rune const rune = RuneAt(spellId);
            double const seconds =
                             Passive::ElementalLasts(player, Skill,
                                                     Combat::ModifiedDurationSeconds(player, spellId,
                                                                                     Lifetime(rune, Numbers::Num(spellId, "duration_seconds"),
                                                                                              Numbers::Num(BaseId(), "duration_seconds")))),
                         tick = Tune("fire_elemental_tick_seconds");
            unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);
            if (!ticks)
                return;
            double const pct = AuraPerTick(Numbers::Num(spellId, "damage_pct", "aura"), tick);
            std::uint64_t const key = player->GetGUID().GetRawValue();
            std::uint64_t stamp;
            {
                std::lock_guard<std::mutex> guard(mutex);
                // One at a time: a new cast replaces the one that stood.
                Standing& elemental = standing[key];
                stamp = elemental.stamp = ++stamps;
                elemental.spellId = spellId;
                elemental.rune = rune;
                elemental.until = Now() + std::uint64_t(seconds * 1000.0);
                elemental.map = player->GetMap();
            }
            // The look: one at a time, as the damage is.
            Minions::Dismiss(player, Group);
            Minions::Raise(player, Group, player->GetPosition());
            // Storm Elemental: "You gain +{attack_speed_pct} attack speed."
            PutSpeed(player, rune == Rune::StormElemental ? Numbers::Num(spellId, "attack_speed_pct") : 0.0);
            if (rune == Rune::MeteorCall)
                Crash(player, spellId);
            auto const interval = std::uint32_t(tick * 1000.0 + 0.5);
            player->m_Events.AddEventAtOffset([player, key, stamp, ticks, pct, interval]
                                              { Tick(player, key, stamp, ticks, pct, interval); },
                                              std::chrono::milliseconds(interval));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player)
            return;
        if (Is(spellId))
        {
            Start(player, spellId);
            return;
        }
        Standing elemental;
        bool up = false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = standing.find(player->GetGUID().GetRawValue());
            if (found != standing.end() && Holds(Now(), found->second.until))
            {
                elemental = found->second;
                up = true;
            }
        }
        if (!Echoes(Classes::CategoryOf(spellId), up) || targets.empty())
            return;
        Unit* target = targets.front();
        if (target && target != player && target->IsAlive())
            Echo(player, elemental, target);
    }

    void RegisterScripts()
    {
        // "It hovers at your side as an extension of your will. It follows your lead, stays untargetable, and scales with your skill
        // damage": the creature is the look; the burn and the echo are the Shaman's own strikes.
        Minions::Define(Group,
                        [](Player*)
                        {
                            Minions::Kind kind;
                            kind.group = Group;
                            kind.entry = Entry;
                            kind.record = BaseId();
                            kind.cap = 1;
                            return kind;
                        });
    }
} // namespace DC::Combat::Shaman::FireElemental
