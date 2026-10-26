/*
 * Big Bad Voodoo and its runes. The cast lays the ritual on the ground (one for each Witch Doctor, the next ends the
 * last) and every 'Search Tickrate' it looks for the allies in it, the Witch Doctor and the members of its party: each
 * it finds keeps the ritual's gifts for a moment longer than the look's pause, so one that walks out loses them: the
 * ritual     attack and movement speed on the sheet, and the Witch Doctor's pets quicker (the minions piece's haste);
 *   Slam Dance     more damage on every hit (the hit path's multipliers);
 *   Jungle Drums   the ritual's own duration is longer (the rune's);
 *   Ghost Trance   a share of the maximum Life each second, and less damage taken;
 *   Rain Dance     Mana a second for the Witch Doctors in it, on the sheet's Mana regeneration;
 *   Boogie Man     an enemy that dies in it may rise as a Zombie Dog.
 */

#include "dc_witch_doctor_big_bad_voodoo.h"
#include "dc_witch_doctor_big_bad_voodoo_math.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_passive_common.h"
#include "dc_witch_doctor_pets.h"
#include "dc_witch_doctor_pets_math.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "GameTime.h"
#include "Creature.h"
#include "Group.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <map>
#include <mutex>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace DC::Combat::WitchDoctor::BigBadVoodoo
{
    namespace
    {
        constexpr std::string_view Skill = "Big Bad Voodoo", Origin = "voodoo";

        // One Witch Doctor's ritual: where, until when, and the allies that hold its gifts and until when.
        struct Zone
        {
            std::uint32_t spellId = 0;
            std::uint32_t map = 0, instance = 0;
            float x = 0, y = 0, z = 0;
            double radius = 0;
            std::uint64_t until = 0;
            std::uint64_t serial = 0;
            std::map<ObjectGuid, std::uint64_t> held;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Zone> zones; // by Witch Doctor
        std::uint64_t serials = 0;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill && rune == row->rune;
        }

        double Num(std::uint32_t record, char const* token)
        {
            return Numbers::Num(record, token);
        }

        // The ritual that holds `player` now, its record; 0 when none does. Under the mutex.
        std::uint32_t Holding(Player const* player, std::uint64_t now)
        {
            for (auto const& [owner, zone] : zones)
            {
                auto const held = zone.held.find(player->GetGUID());
                if (held != zone.held.end() && Holds(held->second, now))
                    return zone.spellId;
            }
            return 0;
        }

        // What the ritual puts on an ally's sheet: attack and movement speed, and Rain Dance's Mana for a Witch Doctor.
        // The same stats and keys come off again.
        void Gifts(Player* ally, std::uint32_t spellId, bool give)
        {
            std::uint64_t const guid = ally->GetGUID().GetRawValue();
            std::uint32_t const id = BaseId(Skill);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::AttackSpeed, id);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::MovementSpeed, id);
            Stats::RemoveContribution(guid, Source::Temporary, Stat::ManaRegen, id);
            if (give)
            {
                double const speed = Num(spellId, "movement_speed_pct");
                Stats::AddContribution(guid, {Source::Temporary, Stat::AttackSpeed, id, speed, Bucket::Flat});
                Stats::AddContribution(guid, {Source::Temporary, Stat::MovementSpeed, id, speed, Bucket::Uncapped});
                if (IsRune(spellId, "Rain Dance") && Passive::IsWitchDoctor(ally))
                    Stats::AddContribution(guid, {Source::Temporary, Stat::ManaRegen, id,
                                                  Num(spellId, "regen_per_second_resource"), Bucket::Flat});
            }
            Stats::Recompute(ally);
            Inventory::PushSheet(ally);
        }

        // The Witch Doctor and the members of its party on its map within the ritual.
        std::vector<Player*> Allies(Player* owner, Zone const& zone)
        {
            std::vector<Player*> inside;
            auto consider = [&](Player* player)
            {
                if (player && player->IsInWorld() && player->IsAlive() && player->GetMap() == owner->GetMap() &&
                    Inside(player->GetExactDist2d(zone.x, zone.y), zone.radius))
                    inside.push_back(player);
            };
            if (Group* group = owner->GetGroup())
                for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                    consider(ref->GetSource());
            else
                consider(owner);
            return inside;
        }

        // The ritual ends: its allies lose the gifts. `serial` names the ritual, so one that was replaced does not end
        // the new one.
        void End(Player* owner, std::uint64_t serial)
        {
            std::vector<ObjectGuid> held;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = zones.find(owner->GetGUID().GetRawValue());
                if (found == zones.end() || found->second.serial != serial)
                    return;
                for (auto const& [guid, until] : found->second.held)
                    held.push_back(guid);
                zones.erase(found);
            }
            for (ObjectGuid guid : held)
                if (Player* ally = ObjectAccessor::FindPlayer(guid))
                    Gifts(ally, 0, false);
        }

        void Tick(Player* owner, std::uint64_t serial)
        {
            std::uint64_t const now = Now();
            Zone zone;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = zones.find(owner->GetGUID().GetRawValue());
                if (found == zones.end() || found->second.serial != serial)
                    return;
                zone = found->second;
            }
            if (!owner->IsInWorld() || !owner->IsAlive() || now >= zone.until)
                return End(owner, serial);

            std::uint32_t const id = zone.spellId;
            double const tick = Tune("big_bad_voodoo_tick_seconds"), linger = Tune("big_bad_voodoo_linger_seconds");
            std::uint64_t const gift = GiftMs(tick, linger);
            std::vector<Player*> const inside = Allies(owner, zone);
            std::vector<Player*> fresh;
            std::vector<ObjectGuid> lapsed;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = zones.find(owner->GetGUID().GetRawValue());
                if (found == zones.end() || found->second.serial != serial)
                    return;
                auto& held = found->second.held;
                for (Player* ally : inside)
                {
                    auto const had = held.find(ally->GetGUID());
                    if (had == held.end() || !Holds(had->second, now))
                        fresh.push_back(ally);
                    held[ally->GetGUID()] = now + gift;
                }
                for (auto it = held.begin(); it != held.end();)
                    if (!Holds(it->second, now))
                    {
                        lapsed.push_back(it->first);
                        it = held.erase(it);
                    }
                    else
                        ++it;
            }
            for (Player* ally : fresh)
                Gifts(ally, id, true);
            for (ObjectGuid guid : lapsed)
                if (Player* ally = ObjectAccessor::FindPlayer(guid))
                    Gifts(ally, id, false);

            // Ghost Trance: "heals all nearby allies for {heal_pct} of their maximum Life per second".
            if (IsRune(id, "Ghost Trance"))
                for (Player* ally : inside)
                {
                    double const heal = TickHeal(double(ally->GetMaxHealth()), Num(id, "heal_pct"), tick);
                    HealInfo info(owner, ally, std::uint32_t(std::min(heal, double(UINT32_MAX))),
                                  sSpellMgr->GetSpellInfo(id), SPELL_SCHOOL_MASK_NATURE);
                    owner->HealBySpell(info);
                }

            // The Witch Doctor's own pets are allies too: quicker, and with Slam Dance harder.
            if (std::find(inside.begin(), inside.end(), owner) != inside.end())
            {
                double const speed = Num(id, "movement_speed_pct");
                for (std::string_view group : Pets::PetGroups)
                {
                    Minions::Haste(owner, group, speed, speed, std::uint32_t(gift), Origin);
                    if (IsRune(id, "Slam Dance"))
                        Minions::Boost(owner, group, Num(id, "damage_bonus_pct"), std::uint32_t(gift), Origin);
                }
            }

            owner->m_Events.AddEventAtOffset([owner, serial] { Tick(owner, serial); },
                                             std::chrono::milliseconds(std::uint64_t(tick * 1000.0 + 0.5)));
        }

        class Scripts final : public PlayerScript
        {
        public:
            Scripts()
                : PlayerScript("dc_witch_doctor_big_bad_voodoo", {PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerLogout(Player* player) override
            {
                std::uint64_t serial = 0;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto const found = zones.find(player->GetGUID().GetRawValue());
                    if (found == zones.end())
                        return;
                    serial = found->second.serial;
                }
                End(player, serial);
            }
        };

        // Boogie Man: an enemy that dies in the ritual may rise as a Zombie Dog.
        class Deaths final : public UnitScript
        {
        public:
            Deaths()
                : UnitScript("dc_witch_doctor_boogie_man", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* victim, Unit*) override
            {
                Creature* creature = victim ? victim->ToCreature() : nullptr;
                if (!creature || creature->IsControlledByPlayer())
                    return;
                ObjectGuid owner;
                std::uint32_t id = 0;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    std::uint64_t const now = Now();
                    for (auto const& [guid, zone] : zones)
                        if (IsRune(zone.spellId, "Boogie Man") && now < zone.until &&
                            creature->GetMapId() == zone.map && creature->GetInstanceId() == zone.instance &&
                            Inside(creature->GetExactDist2d(zone.x, zone.y), zone.radius))
                        {
                            owner = ObjectGuid(guid);
                            id = zone.spellId;
                            break;
                        }
                }
                Player* witchDoctor = owner ? ObjectAccessor::FindPlayer(owner) : nullptr;
                if (!witchDoctor || creature->IsFriendlyTo(witchDoctor) ||
                    !Rises(frand(0.0f, 100.0f), Num(id, "proc_chance_pct")))
                    return;
                Position const at = creature->GetPosition();
                witchDoctor->m_Events.AddEventAtOffset([witchDoctor, at] { Pets::RaiseDogAt(witchDoctor, at); },
                                                       std::chrono::milliseconds(100));
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        std::uint64_t old = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = zones.find(guid);
            if (found != zones.end())
                old = found->second.serial;
        }
        if (old)
            End(player, old);
        Zone zone;
        zone.spellId = spellId;
        zone.map = player->GetMapId();
        zone.instance = player->GetInstanceId();
        zone.x = center.GetPositionX();
        zone.y = center.GetPositionY();
        zone.z = center.GetPositionZ();
        zone.radius = Tune("big_bad_voodoo_radius_yards");
        // "Total: Totem Duration": the skill's seconds, Jungle Drums' own.
        zone.until = Now() + std::uint64_t(Num(spellId, "duration_seconds") * 1000.0 + 0.5);
        {
            std::lock_guard<std::mutex> guard(mutex);
            zone.serial = ++serials;
            zones[guid] = zone;
        }
        Tick(player, zone.serial);
    }

    void Multipliers(Player* player, DC::Combat::Factors& out)
    {
        std::uint32_t id = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            if (zones.empty())
                return;
            id = Holding(player, Now());
        }
        if (id && IsRune(id, "Slam Dance"))
            AddFactor(out, "Slam Dance", Num(id, "damage_bonus_pct"));
    }

    double Reduce(Unit* victim, double damage)
    {
        Player const* player = victim ? victim->ToPlayer() : nullptr;
        if (!player || damage <= 0)
            return damage;
        std::uint32_t id = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            if (zones.empty())
                return damage;
            id = Holding(player, Now());
        }
        return id && IsRune(id, "Ghost Trance") ? Taken(damage, Num(id, "damage_reduction_pct")) : damage;
    }

    void RegisterScripts()
    {
        new Scripts();
        new Deaths();
    }
} // namespace DC::Combat::WitchDoctor::BigBadVoodoo
