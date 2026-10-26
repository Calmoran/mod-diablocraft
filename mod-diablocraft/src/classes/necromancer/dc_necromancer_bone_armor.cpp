/*
 * Bone Armor and its five runes. The engine strikes the enemies around the Necromancer; here: the armor that cuts the damage taken for
 * each enemy hit (up to the power's most) for the skill's seconds, replaced by the next cast. Limited Immunity absorbs everything and
 * grants immunity to control for its seconds; Dislocation stuns the enemies hit; Thy Flesh Sustained costs Life and raises Life
 * regeneration for each enemy hit; Harvest of Anguish raises movement speed for each. The last two end with the armor.
 */

#include "dc_necromancer_bone_armor.h"
#include "dc_necromancer_bone_armor_math.h"
#include "dc_necromancer_common.h"
#include "../../combat/dc_control_immunity.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_passives.h"

#include "GameTime.h"

#include <chrono>
#include <map>
#include <mutex>

namespace DC::Combat::Necromancer::BoneArmor
{
    namespace
    {
        constexpr std::string_view Skill = "Bone Armor";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The armor a Necromancer wears: the record cast, what it takes off the damage, when it ends. A new cast takes a new stamp, so the
        // end of an old one finds its own gone and leaves the new alone.
        struct Armor
        {
            std::uint32_t spellId = 0;
            double reductionPct = 0;
            std::uint64_t until = 0;
            std::uint64_t stamp = 0;
        };
        std::mutex mutex;
        std::map<std::uint64_t, Armor> worn;
        std::uint64_t stamps = 0;

        // What the rune of `spellId` put on the sheet or the player comes off.
        void Take(Player* player, std::uint32_t spellId)
        {
            switch (RuneAt(spellId))
            {
                case Rune::LimitedImmunity:
                    ControlImmunity::Set(player, spellId, false);
                    break;
                case Rune::ThyFleshSustained:
                    Buffs::Set(player, spellId, Stat::LifeRegen, Bucket::Percent, 0);
                    break;
                case Rune::HarvestOfAnguish:
                    Buffs::Set(player, spellId, Stat::MovementSpeed, Bucket::Flat, 0);
                    break;
                default:
                    break;
            }
        }

        void End(Player* player, std::uint64_t stamp)
        {
            Armor old;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = worn.find(player->GetGUID().GetRawValue());
                if (found == worn.end() || found->second.stamp != stamp)
                    return;
                old = found->second;
                worn.erase(found);
            }
            Take(player, old.spellId);
        }
    } // namespace

    void Casting(Player* player, std::uint32_t spellId)
    {
        // "Cost: 20% Health" (Thy Flesh Sustained).
        if (player && RuneAt(spellId) == Rune::ThyFleshSustained)
            SpendLife(player, Tune("thy_flesh_sustained_life_cost_pct"));
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        Rune const rune = RuneAt(spellId);
        unsigned const most = unsigned(Numbers::Num(spellId, "target_count"));
        unsigned const hit = unsigned(targets.size());
        double const seconds = Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(spellId, "duration_seconds"));
        std::uint64_t stamp;
        Armor old;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Armor& held = worn[player->GetGUID().GetRawValue()];
            old = held;
            held = {spellId, PerEnemy(hit, Numbers::Num(spellId, "damage_reduction_pct"), most),
                    Now() + std::uint64_t(seconds * 1000.0 + 0.5), stamp = ++stamps};
        }
        // The old armor's rune comes off (a new cast of the same record puts its own back at once).
        if (old.stamp)
            Take(player, old.spellId);
        switch (rune)
        {
            case Rune::LimitedImmunity:
                // "Your armor absorbs all incoming damage and grants immunity to all control impairing effects."
                ControlImmunity::Set(player, spellId, true);
                break;
            case Rune::Dislocation:
                for (Unit* enemy : targets)
                    Stun(player, enemy, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
                break;
            case Rune::ThyFleshSustained:
                // "Increases your Life per Second by {life_regen_pct} per target hit."
                Buffs::Set(player, spellId, Stat::LifeRegen, Bucket::Percent, PerEnemy(hit, Numbers::Num(spellId, "life_regen_pct"), most));
                break;
            case Rune::HarvestOfAnguish:
                // "Bone Armor also increases your movement speed by {movement_speed_pct} for each enemy hit."
                Buffs::Set(player, spellId, Stat::MovementSpeed, Bucket::Flat, PerEnemy(hit, Numbers::Num(spellId, "movement_speed_pct"), most));
                break;
            default:
                break;
        }
        player->m_Events.AddEventAtOffset([player, stamp] { End(player, stamp); },
                                          std::chrono::milliseconds(std::uint32_t(seconds * 1000.0 + 0.5) + 1));
    }

    double Reduce(Unit* victim, double damage)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (!player || damage <= 0)
            return damage;
        Armor armor;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = worn.find(player->GetGUID().GetRawValue());
            if (found == worn.end() || Now() >= found->second.until)
                return damage;
            armor = found->second;
        }
        return AbsorbsAll(RuneAt(armor.spellId)) ? 0.0 : damage * TakenFactor(armor.reductionPct);
    }
} // namespace DC::Combat::Necromancer::BoneArmor
