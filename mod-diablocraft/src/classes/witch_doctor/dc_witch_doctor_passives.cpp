/*
 * The Witch Doctor's passives that need code: Jungle Fortitude, Circle of Life, Spiritual Attunement, Gruesome Feast,
 * Blood Ritual and Bad Medicine. The numbers are witch_doctor_passive_values.csv (skill = the passive's name) and the
 * passives' power files, read through each passive's record.
 *
 * A passive is on when it sits in one of the Witch Doctor's passive slots, or a worn item grants it (Passives::Has).
 * Jungle Fortitude rides the damage taken (Reduce, and the damage a minion takes); Circle of Life hears the deaths
 * around the Witch Doctor; Spiritual Attunement and Blood Ritual's regeneration are numbers on the sheet that a small
 * update script keeps; Gruesome Feast waits for the health globes (GlobePicked has no caller yet); Blood Ritual rides
 * the cast whose Mana cost it takes back; Bad Medicine rides the hit (Landed).
 */

#include "dc_witch_doctor_passives.h"
#include "dc_witch_doctor_passives_math.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_mana.h"
#include "dc_witch_doctor_pets.h"
#include "dc_witch_doctor_sheet_buffs.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_enemy_effects.h"
#include "../../combat/dc_passives.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../stats/dc_stats.h"

#include "Creature.h"
#include "Map.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellMgr.h"
#include "SpellInfo.h"

#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::Passive
{
    namespace
    {
        // The sheet is looked at every passive_poll_seconds: the numbers it keeps follow the maximum Mana and the maximum
        // Life.
        std::uint32_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint32_t(std::llround(seconds * 1000.0)) : 0;
        }

        std::uint32_t Id(std::string_view name)
        {
            for (auto const& passive : Shells::Passives)
                if (name == passive.name)
                    return passive.id;
            return 0;
        }

        bool IsWitchDoctor(Player const* player)
        {
            return player && Classes::ClassIdOf(player) == Resources::Mana.classId;
        }

        bool On(Player* player, char const* name)
        {
            return IsWitchDoctor(player) && Passives::Has(player, name);
        }

        double Num(char const* name, char const* token)
        {
            return Numbers::Num(Id(name), token);
        }

        // What the update script has put on one Witch Doctor's sheet.
        struct Kept
        {
            std::uint32_t clock = 0;
            double maxMana = 0;   // Spiritual Attunement's added maximum Mana
            double manaRegen = 0; // and its Mana a second
            double lifeRegen = 0; // Blood Ritual's Life a second
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Kept> kept;

        // One number of one passive on the sheet: taken off when it changed or the passive is gone, put on when it is
        // wanted. True when the sheet moved.
        bool Keep(std::uint64_t guid, std::uint32_t id, Stat stat, double& applied, double wanted)
        {
            if (std::abs(wanted - applied) < 0.01)
                return false;
            Stats::RemoveContribution(guid, Source::Passives, stat, id);
            if (wanted > 0)
                Stats::AddContribution(guid, {Source::Passives, stat, id, wanted, Bucket::Flat});
            applied = wanted;
            return true;
        }

        void Maintain(Player* player)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            auto const sheet = DC::Stats::Get(guid);
            if (!sheet)
                return;
            bool moved = false;
            std::lock_guard<std::mutex> guard(mutex);
            Kept& now = kept[guid];
            // Spiritual Attunement: "Maximum Mana is increased by {max_pool_pct}. Regenerate {regen_pool_share_pct} of
            // your maximum Mana per second." The sheet's maximum Mana has no percent bucket, so the passive adds the
            // share of the pool without it; the regeneration is the sheet's Mana regeneration, which the resource pulse
            // pays smoothly.
            bool const attuned = On(player, "Spiritual Attunement");
            std::uint32_t const attunement = Id("Spiritual Attunement");
            double const base = (*sheet)[Stat::MaxFury] - now.maxMana;
            double const bonus =
                attuned ? PoolBonus((*sheet)[Stat::MaxFury], now.maxMana, Num("Spiritual Attunement", "max_pool_pct"))
                        : 0.0;
            moved |= Keep(guid, attunement, Stat::MaxFury, now.maxMana, bonus);
            moved |= Keep(guid, attunement, Stat::ManaRegen, now.manaRegen,
                          attuned ? Share(base + bonus, Num("Spiritual Attunement", "regen_pool_share_pct")) : 0.0);
            // Blood Ritual: "In addition, you regenerate {life_regen_pct} of your maximum Life per second."
            moved |=
                Keep(guid, Id("Blood Ritual"), Stat::LifeRegen, now.lifeRegen,
                     On(player, "Blood Ritual") ? Share(player->GetMaxHealth(), Num("Blood Ritual", "life_regen_pct"))
                                                : 0.0);
            if (moved)
                Stats::Recompute(player);
        }

        class Update final : public PlayerScript
        {
        public:
            Update()
                : PlayerScript("dc_witch_doctor_passives", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (!IsWitchDoctor(player))
                    return;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    std::uint32_t& clock = kept[player->GetGUID().GetRawValue()].clock;
                    if ((clock += diff) < Millis(Tune("passive_poll_seconds")))
                        return;
                    clock = 0;
                }
                Maintain(player);
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                kept.erase(player->GetGUID().GetRawValue());
            }
        };

        // Jungle Fortitude's pets: the damage a Witch Doctor's minion takes is cut by the passive's share; and Circle
        // of Life's deaths.
        class World final : public UnitScript
        {
        public:
            World()
                : UnitScript("dc_witch_doctor_passives_world", true, {UNITHOOK_ON_DAMAGE, UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnDamage(Unit* /*attacker*/, Unit* victim, std::uint32_t& damage) override
            {
                Creature* minion = victim ? victim->ToCreature() : nullptr;
                Player* owner = minion && minion->GetOwner() ? minion->GetOwner()->ToPlayer() : nullptr;
                if (!damage || !owner || minion->GetScriptName() != "dc_minion" || !On(owner, "Jungle Fortitude"))
                    return;
                damage = std::uint32_t(std::llround(Reduced(damage, Num("Jungle Fortitude", "damage_reduction_pct"))));
            }

            // Circle of Life: "When an enemy dies within {radius_yards} yards, there is a {proc_chance_pct} chance that
            // a Zombie Dog will automatically emerge. The range of this effect is increased by your gold pickup
            // radius."
            void OnUnitDeath(Unit* unit, Unit* /*killer*/) override
            {
                Creature* dead = unit ? unit->ToCreature() : nullptr;
                Map* map = dead ? dead->GetMap() : nullptr;
                if (!map || dead->IsControlledByPlayer() || dead->GetScriptName() == "dc_minion")
                    return;
                for (auto const& ref : map->GetPlayers())
                {
                    Player* player = ref.GetSource();
                    if (!On(player, "Circle of Life") || !player->IsAlive() || !player->IsHostileTo(dead))
                        continue;
                    auto const sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
                    if (InRange(player->GetExactDist(dead), Num("Circle of Life", "radius_yards"),
                                sheet ? (*sheet)[Stat::GoldPickupRange] : 0.0) &&
                        Procs(frand(0.0f, 100.0f), Num("Circle of Life", "proc_chance_pct")))
                        DogEmerges(player, dead->GetPosition());
                }
            }
        };

        // Blood Ritual: "{resource_cost_share_pct} of Mana costs are paid with Life": after the core has taken the
        // cost, the share of it comes back as Mana and is taken as Life instead.
        class CastHook final : public AllSpellScript
        {
        public:
            CastHook()
                : AllSpellScript("dc_witch_doctor_passives_cast", {ALLSPELLHOOK_ON_CAST})
            {
            }

            void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override
            {
                Player* player = caster ? caster->ToPlayer() : nullptr;
                if (!player || !info || spell->IsTriggered() || !On(player, "Blood Ritual") ||
                    Powers(info->PowerType) != Resources::Slot(Resources::Mana))
                    return;
                Payment const paid =
                    Sacrifice(Resources::ToPoints(Resources::Mana, spell->GetPowerCost()),
                              Num("Blood Ritual", "resource_cost_share_pct"), Resources::Max(player, Resources::Mana),
                              player->GetMaxHealth(), Tune("blood_ritual_life_scale"), player->GetHealth());
                if (paid.life >= 1.0)
                    player->ModifyHealth(-std::int32_t(paid.life));
                if (paid.manaBack > 0)
                    Resources::Energize(player, Resources::Mana, info->Id, paid.manaBack);
            }
        };
    } // namespace

    void Landed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !target || !On(player, "Bad Medicine"))
            return;
        // "When you deal Poison damage to an enemy, its damage is reduced by {enemy_damage_pct} for {duration_seconds}
        // seconds."
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId); info && PoisonMask(info->GetSchoolMask()))
            if (std::uint32_t const id = Id("Bad Medicine"))
                EnemyEffects::Weaken(target, id, Num("Bad Medicine", "enemy_damage_pct"),
                                     Num("Bad Medicine", "duration_seconds"));
    }

    double Reduce(Unit* victim, double damage)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (damage <= 0 || !On(player, "Jungle Fortitude"))
            return damage;
        // "Reduce all damage taken by you and your pets by {damage_reduction_pct}."
        return Reduced(damage, Num("Jungle Fortitude", "damage_reduction_pct"));
    }

    void GlobePicked(Player* player)
    {
        if (!On(player, "Gruesome Feast"))
            return;
        // "When you are healed by a health globe, gain {gain_pct} of your maximum Mana and {primary_stat_pct}
        // Intelligence for {duration_seconds} seconds. The Intelligence bonus stacks up to {max_stacks_count} times."
        std::uint32_t const id = Id("Gruesome Feast");
        Gain(player, Classes::ClassIdOf(player), id,
             Share(Resources::Max(player, Resources::Mana), Num("Gruesome Feast", "gain_pct")), 1);
        SheetBuffs::Stack(player, id, Stat::Intelligence, Bucket::Percent, Num("Gruesome Feast", "primary_stat_pct"),
                          unsigned(Num("Gruesome Feast", "max_stacks_count")), Num("Gruesome Feast", "duration_seconds"));
    }

    void DogEmerges(Player* player, Position const& where)
    {
        // The Zombie Dog is the pets' (Summon Zombie Dogs' kind on the shared minions piece): it comes up where the
        // enemy died, while the Witch Doctor stands short of the dogs they may have.
        Pets::RaiseDogAt(player, where);
    }

    void Register()
    {
        new Update();
        new World();
        new CastHook();
    }
} // namespace DC::Combat::WitchDoctor::Passive
