/*
 * The Healing Stream Totem and its five runes. The cast and the totem itself are the totem seam's
 * (dc_shaman_totems.cpp); here is what a standing Healing Stream Totem does: every healing_stream_tick_seconds it heals
 * the Shaman and the party members within its radius_yards for life_regen_pct of their maximum Life a second. Healing
 * Tide heals at once when the totem is placed; Maelstrom Spring gives the Shaman Maelstrom while in range; Cleansing
 * Stream takes the control effects off and keeps them off for a few seconds; Riptide shoots water bolts at the nearest
 * enemy; Ancestral Protection prevents the Shaman's first death within the radius.
 */

#include "dc_shaman_healing_stream_totem.h"
#include "dc_shaman_common.h"
#include "dc_shaman_healing_stream_totem_math.h"
#include "dc_shaman_totems_math.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_control_immunity.h"
#include "Creature.h"
#include "Group.h"
#include "ObjectAccessor.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <mutex>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Shaman::HealingStream
{
    namespace
    {
        constexpr std::string_view Skill = "Healing Stream Totem";

        // Cleansing Stream's immunity on the Shaman and the allies it was given to: the key it is worn under, when it
        // ends and who wears it.
        struct Cleansing
        {
            std::uint32_t key = 0;
            std::uint64_t untilMs = 0;
            std::vector<ObjectGuid> wearers;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Cleansing> cleansing; // by Shaman
        // The totem that has prevented a death for each Shaman: Ancestral Protection saves once a totem.
        std::unordered_map<std::uint64_t, std::uint64_t> saved;

        std::string_view RuneOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? std::string_view(row->rune) : std::string_view();
        }

        // The Shaman and the Shaman's party members within `radius` of the totem: "you and allies".
        std::vector<Player*> Allies(Player* player, Creature* totem, double radius)
        {
            std::vector<Player*> out;
            if (Within(player->GetExactDist(totem), radius))
                out.push_back(player);
            if (Group* group = player->GetGroup())
                for (GroupReference* it = group->GetFirstMember(); it; it = it->next())
                {
                    Player* member = it->GetSource();
                    if (member && member != player && member->IsAlive() && member->IsInMap(player) &&
                        Within(member->GetExactDist(totem), radius))
                        out.push_back(member);
                }
            return out;
        }

        void HealTarget(Player* caster, Player* target, std::uint32_t source, double amount)
        {
            SpellInfo const* info = amount > 0 && target->IsAlive() ? sSpellMgr->GetSpellInfo(source) : nullptr;
            if (!info)
                return;
            HealInfo heal(caster, target, std::uint32_t(std::min(amount, double(UINT32_MAX))), info,
                          SPELL_SCHOOL_MASK_NORMAL);
            caster->HealBySpell(heal);
        }

        // The totem is placed: Healing Tide's heal and Cleansing Stream's cleanse.
        void Placed(Player* player, Creature* totem, std::uint32_t source)
        {
            std::string_view const rune = RuneOf(source);
            std::vector<Player*> const allies = Allies(player, totem, Numbers::Num(source, "radius_yards"));
            if (rune == "Healing Tide")
                for (Player* ally : allies)
                    HealTarget(player, ally, source,
                               PlacedHeal(ally->GetMaxHealth(), Numbers::Num(source, "heal_pct")));
            if (rune != "Cleansing Stream")
                return;
            // "Removes control effects when placed. While in range, you and allies are immune to control effects for
            // the first {duration_seconds} seconds."
            Cleansing now;
            now.key = source;
            now.untilMs = ImmuneUntil(Now(), Numbers::Num(source, "duration_seconds"));
            for (Player* ally : allies)
            {
                ControlImmunity::Set(ally, source, true);
                now.wearers.push_back(ally->GetGUID());
            }
            std::lock_guard<std::mutex> guard(mutex);
            cleansing[player->GetGUID().GetRawValue()] = std::move(now);
        }

        // One look: the heal, and Maelstrom Spring's gain.
        void Tick(Player* player, Creature* totem, std::uint32_t source, double tick)
        {
            std::vector<Player*> const allies = Allies(player, totem, Numbers::Num(source, "radius_yards"));
            for (Player* ally : allies)
                HealTarget(player, ally, source,
                           TickHeal(ally->GetMaxHealth(), Numbers::Num(source, "life_regen_pct"), tick));
            if (RuneOf(source) == "Maelstrom Spring" && !allies.empty() && allies.front() == player)
                Gain(player, source, TickGain(Numbers::Num(source, "regen_per_second_resource"), tick));
        }

        // Riptide: "The totem also fires a water bolt every {interval_seconds} second for {damage_pct} weapon damage as
        // Cold."
        void Bolt(Player* player, Creature* totem, std::uint32_t source)
        {
            auto const enemies =
                Combat::Enemies(player, source, totem->GetPosition(), Numbers::Num(source, "radius_yards"));
            std::vector<double> distances;
            for (Unit* enemy : enemies)
                distances.push_back(totem->GetExactDist(enemy));
            std::size_t const nearest = Totems::Nearest(distances);
            if (nearest == Totems::None)
                return;
            totem->SetFacingToObject(enemies[nearest]);
            Combat::Strike(player, enemies[nearest], source, Numbers::Get(source, "damage_pct"));
        }

        // The immunity taken off the ones who wear it.
        void Release(Cleansing const& worn)
        {
            for (ObjectGuid const& guid : worn.wearers)
                if (Player* wearer = ObjectAccessor::FindConnectedPlayer(guid))
                    ControlImmunity::Set(wearer, worn.key, false);
        }
    } // namespace

    void Update(Player* player, Creature* totem, std::uint32_t source, Totems::State& state, std::uint32_t diff)
    {
        if (!state.placed)
        {
            state.placed = true;
            Placed(player, totem, source);
        }
        double const tick = Tunable("healing_stream_tick_seconds");
        for (unsigned due = Totems::Pulses(state.clock[0], diff, tick); due; --due)
            Tick(player, totem, source, tick);
        if (RuneOf(source) != "Riptide")
            return;
        for (unsigned due = Totems::Pulses(state.clock[1], diff, Numbers::Num(source, "interval_seconds")); due; --due)
            Bolt(player, totem, source);
    }

    void Upkeep(Player* player)
    {
        Cleansing worn;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = cleansing.find(player->GetGUID().GetRawValue());
            if (found == cleansing.end())
                return;
            // The immunity ends with its seconds, or with the totem that gave it.
            if (Immune(found->second.untilMs, Now()) &&
                Totems::Standing(player, Totems::WaterSlot) == found->second.key)
                return;
            worn = std::move(found->second);
            cleansing.erase(found);
        }
        Release(worn);
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill ? Numbers::Get(spellId, "damage_pct") : std::nullopt;
    }

    void Fatal(Player* player, std::uint32_t& damage)
    {
        if (!IsShaman(player) || !damage)
            return;
        std::uint32_t const standing = Totems::Standing(player, Totems::WaterSlot);
        Creature* totem =
            standing && RuneOf(standing) == "Ancestral Protection" ? Totems::Totem(player, Totems::WaterSlot) : nullptr;
        if (!totem)
            return;
        std::uint64_t const guid = totem->GetGUID().GetRawValue();
        bool already;
        {
            std::lock_guard<std::mutex> guard(mutex);
            already = saved[player->GetGUID().GetRawValue()] == guid;
        }
        // "The first time you would die within its radius, the death is prevented and you are healed to
        // {life_floor_pct} Life."
        if (!Saves(player->GetHealth(), damage,
                   Within(player->GetExactDist(totem), Numbers::Num(standing, "radius_yards")), already))
            return;
        {
            std::lock_guard<std::mutex> guard(mutex);
            saved[player->GetGUID().GetRawValue()] = guid;
        }
        damage = 0;
        player->SetHealth(std::uint32_t(
            SavedHealth(player->GetHealth(), player->GetMaxHealth(), Numbers::Num(standing, "life_floor_pct"))));
    }

    void Forget(Player* player)
    {
        Cleansing worn;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = cleansing.find(player->GetGUID().GetRawValue());
            if (found != cleansing.end())
            {
                worn = std::move(found->second);
                cleansing.erase(found);
            }
            saved.erase(player->GetGUID().GetRawValue());
        }
        Release(worn);
    }
} // namespace DC::Combat::Shaman::HealingStream
