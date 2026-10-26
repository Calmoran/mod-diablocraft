/*
 * Inner Sanctuary and its five runes.
 */

#include "dc_monk_inner_sanctuary.h"
#include "../dc_level_heal.h"
#include "dc_monk_common.h"
#include "../../combat/dc_control_immunity.h"
#include "../../combat/dc_movement_effects.h"
#include "../../stats/dc_stats.h"
#include "Group.h"
#include "SharedDefines.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"

#include <chrono>
#include <unordered_set>

namespace DC::Combat::Monk::Sanctuary
{
    namespace
    {
        constexpr std::string_view Skill = "Inner Sanctuary";
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, the slow Hand of Ytar rides;
        // Forbidden Palace sets its amount to the rune's.
        constexpr std::uint32_t SlowCarrier = 50259;
        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Row(spellId);
            return row && rune == row->rune;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        struct Shield
        {
            double left = 0;
            std::uint64_t until = 0;
        };

        std::mutex mutex;
        std::vector<Zone> zones;
        std::unordered_map<std::uint64_t, Shield> shields;
        std::unordered_set<std::uint64_t> immune; // the allies Temple of Protection holds now

        // An ally of the circle: the Monk, or a member of the Monk's party or raid.
        bool Ally(Zone const& zone, Player const* player)
        {
            if (player->GetGUID().GetRawValue() == zone.owner)
                return true;
            Group const* group = player->GetGroup();
            return group && group->IsMember(ObjectGuid(zone.owner));
        }

        // The first live circle (of `rune`, any when empty) that holds `player` as an ally. Under the mutex.
        Zone const* Covering(Player const* player, std::uint64_t now, std::string_view rune = {})
        {
            for (Zone const& zone : zones)
                if ((rune.empty() || IsRune(zone.spellId, rune)) && Ally(zone, player) &&
                    Covers(zone, player->GetMapId(), player->GetInstanceId(), player->GetPositionX(),
                           player->GetPositionY(), now))
                    return &zone;
            return nullptr;
        }

        // The living allies in the circle: the Monk alone, or every member of the group on its map.
        std::vector<Player*> Allies(Player* owner, Zone const& zone, std::uint64_t now)
        {
            std::vector<Player*> inside;
            auto consider = [&](Player* player)
            {
                if (player && player->IsInWorld() && player->IsAlive() && player->GetMap() == owner->GetMap() &&
                    Covers(zone, player->GetMapId(), player->GetInstanceId(), player->GetPositionX(),
                           player->GetPositionY(), now))
                    inside.push_back(player);
            };
            if (Group* group = owner->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    consider(ref->GetSource());
            else
                consider(owner);
            return inside;
        }

        // The ally's own queue takes the immunity off once no Temple of Protection circle holds it, so a Monk who logs
        // out or leaves never leaves it on anyone.
        void Watch(Player* ally, std::uint32_t key, std::uint32_t tickMs)
        {
            ally->m_Events.AddEventAtOffset(
                [ally, key, tickMs]
                {
                    bool inside;
                    {
                        std::lock_guard<std::mutex> lock(mutex);
                        inside = ally->IsAlive() && Covering(ally, Now(), "Temple of Protection");
                        if (!inside)
                            immune.erase(ally->GetGUID().GetRawValue());
                    }
                    if (inside)
                        return Watch(ally, key, tickMs);
                    ControlImmunity::Set(ally, key, false);
                },
                std::chrono::milliseconds(tickMs));
        }

        void Tick(Player* owner, Zone const& zone, double tickSeconds)
        {
            if (!owner->IsInWorld() || owner->GetMapId() != zone.map || owner->GetInstanceId() != zone.instance)
                return;
            std::uint64_t const now = Now();
            std::uint32_t const id = zone.spellId;
            std::uint32_t const tickMs = std::uint32_t(tickSeconds * 1000 + 0.5);
            Position const center(float(zone.x), float(zone.y), float(zone.z));

            // Safe Haven: "Allies inside Inner Sanctuary are healed for {heal_per_second_life} every second", plus
            // {life_per_second_share_pct} of the Monk's Life per Second.
            if (IsRune(id, "Safe Haven"))
            {
                double lifePerSecond = 0;
                if (auto const sheet = Stats::Get(owner->GetGUID().GetRawValue()))
                    lifePerSecond = (*sheet)[Stat::LifeRegen];
                double const heal = HealPerTick(Classes::HealAtLevel(Numbers::Num(id, "heal_per_second_life"), owner->GetLevel()), lifePerSecond,
                                                Numbers::Num(id, "life_per_second_share_pct"), tickSeconds);
                for (Player* ally : Allies(owner, zone, now))
                {
                    HealInfo info(owner, ally, std::uint32_t(std::min(heal, double(UINT32_MAX))),
                                  sSpellMgr->GetSpellInfo(id), SPELL_SCHOOL_MASK_HOLY);
                    owner->HealBySpell(info);
                }
            }

            // Temple of Protection: "Allies inside Inner Sanctuary are also immune to control impairing effects."
            if (IsRune(id, "Temple of Protection"))
                for (Player* ally : Allies(owner, zone, now))
                {
                    bool fresh;
                    {
                        std::lock_guard<std::mutex> lock(mutex);
                        fresh = immune.insert(ally->GetGUID().GetRawValue()).second;
                    }
                    if (!fresh)
                        continue;
                    ControlImmunity::Set(ally, id, true);
                    Watch(ally, id, tickMs);
                }

            // Forbidden Palace: "Enemies inside Inner Sanctuary have their movement speed reduced by {slow_pct}."
            // ponytail: the slow lasts two ticks and each tick renews it, so an enemy that walks out keeps it up to
            // 0.6 s; a leave check per enemy if that shows.
            if (IsRune(id, "Forbidden Palace"))
                for (Unit* enemy : Combat::Enemies(owner, id, center, zone.radius))
                {
                    enemy->RemoveAurasDueToSpell(SlowCarrier, owner->GetGUID());
                    if (Aura* slow = owner->AddAura(SlowCarrier, enemy))
                    {
                        slow->SetMaxDuration(int32(2 * tickMs));
                        slow->SetDuration(int32(2 * tickMs));
                        if (AuraEffect* effect = slow->GetEffect(EFFECT_0))
                            effect->ChangeAmount(-int32(Numbers::Num(id, "slow_pct")));
                    }
                }

            // Sanctified Ground: "cannot be passed by enemies": an enemy inside is put back on the edge.
            // ponytail: the stock knockback pushes away from the Monk, who cast the circle where it stands; a push from
            // the centre if the Monk walking off it shows.
            if (IsRune(id, "Sanctified Ground"))
                for (Unit* enemy : Combat::Enemies(owner, id, center, zone.radius))
                    Abilities::Knockback(owner, enemy, PushYards(enemy->GetExactDist2d(zone.x, zone.y), zone.radius));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        auto const* row = Row(spellId);
        if (!player || !row)
            return;
        std::uint64_t const now = Now();
        // "Create a runic circle of protection on the ground for {duration_seconds} seconds" (Sanctified Ground's
        // own 8), at the Monk (skill_targeting.csv SELF), the radius the sheet gives (power file SF_1 11). Intervene's record is a
        // ground point instead: the cast resolves when the dash lands, so "at the Monk" is where it landed.
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        Zone zone;
        zone.owner = player->GetGUID().GetRawValue();
        zone.spellId = spellId;
        zone.map = player->GetMapId();
        zone.instance = player->GetInstanceId();
        zone.x = player->GetPositionX();
        zone.y = player->GetPositionY();
        zone.z = player->GetPositionZ();
        zone.radius = row->radius;
        zone.until = now + std::uint64_t(seconds * 1000 + 0.5);
        {
            std::lock_guard<std::mutex> lock(mutex);
            std::erase_if(zones, [now](Zone const& z) { return z.until <= now; });
            zones.push_back(zone);
            // Intervene: "granting a shield that absorbs up to {absorb_life} damage for {absorb_duration_seconds}
            // seconds to allies within {radius_yards} yards".
            if (IsRune(spellId, "Intervene"))
            {
                Zone reach = zone;
                reach.radius = Numbers::Num(spellId, "radius_yards");
                for (Player* ally : Allies(player, reach, now))
                    shields[ally->GetGUID().GetRawValue()] = {
                        Classes::HealAtLevel(Numbers::Num(spellId, "absorb_life"), player->GetLevel()),
                        now + std::uint64_t(Numbers::Num(spellId, "absorb_duration_seconds") * 1000 + 0.5)};
            }
        }
        // What the runes do to whoever stands in it, every tick of the power file (SF_6 'Tick Interval').
        double const tick = Tune("inner_sanctuary_tick_seconds");
        unsigned const ticks = Ticks(seconds, tick);
        for (unsigned i = 0; i < ticks; ++i)
            player->m_Events.AddEventAtOffset([player, zone, tick] { Tick(player, zone, tick); },
                                              std::chrono::milliseconds(std::uint64_t(i * tick * 1000 + 0.5)));
    }
} // namespace DC::Combat::Monk::Sanctuary

namespace DC::Combat::Monk
{
    double TakenFactor(Unit* victim)
    {
        Player const* player = victim ? victim->ToPlayer() : nullptr;
        if (!player)
            return 1.0;
        std::lock_guard<std::mutex> lock(Sanctuary::mutex);
        Sanctuary::Zone const* zone = Sanctuary::Covering(player, Sanctuary::Now());
        return zone ? Sanctuary::TakenFactor(Numbers::Num(zone->spellId, "damage_reduction_pct")) : 1.0;
    }

    double Absorb(Unit* victim, double damage)
    {
        if (!victim || damage <= 0)
            return damage;
        std::lock_guard<std::mutex> lock(Sanctuary::mutex);
        auto found = Sanctuary::shields.find(victim->GetGUID().GetRawValue());
        if (found == Sanctuary::shields.end())
            return damage;
        if (found->second.until <= Sanctuary::Now())
        {
            Sanctuary::shields.erase(found);
            return damage;
        }
        damage = Sanctuary::Absorb(damage, found->second.left);
        if (found->second.left <= 0)
            Sanctuary::shields.erase(found);
        return damage;
    }
} // namespace DC::Combat::Monk
