/*
 * Preparation and its five runes. The cast is the engine's self spell (a record, its cooldown, the sheet's numbers);
 * here: the Discipline it restores, Punishment's Hatred, Focused Mind's Discipline over time, Battle Scars' Life,
 * Backup Plan's chance the cooldown is not kept, and Invigoration's higher Discipline maximum while that rune stands on
 * the bar.
 */

#include "dc_demon_hunter_preparation.h"
#include "dc_demon_hunter_common.h"
#include "dc_demon_hunter_effects.h"
#include "../dc_classes.h"
#include "../dc_resource_pool.h"
#include "../dc_resources.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../stats/dc_stats.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "Unit.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::DemonHunter::Preparation
{
    namespace
    {
        constexpr std::string_view Skill = "Preparation";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // Focused Mind's Discipline still to come.
        struct Regen
        {
            std::uint32_t spellId = 0;
            double left = 0;    // ms
            double clock = 0;   // ms since the last tick
            double perTick = 0; // points
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Regen> regens;

        class Regens final : public PlayerScript
        {
        public:
            Regens()
                : PlayerScript("dc_demon_hunter_preparation", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Regen regen;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = regens.find(player->GetGUID().GetRawValue());
                    if (found == regens.end())
                        return;
                    regen = found->second;
                }
                if (!player->IsAlive())
                {
                    Stop(player);
                    return;
                }
                unsigned const ticks = Due(regen.clock, diff, Tune("preparation_regen_tick_seconds") * 1000.0);
                for (unsigned i = 0; i < ticks; ++i)
                    Resources::Energize(player, Resources::Discipline, regen.spellId, regen.perTick);
                regen.left -= diff;
                std::lock_guard<std::mutex> guard(mutex);
                auto found = regens.find(player->GetGUID().GetRawValue());
                if (found == regens.end() || found->second.spellId != regen.spellId)
                    return;
                if (regen.left <= 0)
                    regens.erase(found);
                else
                    found->second = regen;
            }

            void OnPlayerLogout(Player* player) override
            {
                Stop(player);
                Resources::Pool::Clear(player->GetGUID().GetRawValue());
            }

            static void Stop(Player* player)
            {
                std::lock_guard<std::mutex> guard(mutex);
                regens.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !Is(spellId) || Classes::ClassIdOf(player) != Resources::Discipline.classId)
            return;
        Rune const rune = RuneAt(spellId);
        // "Instantly restore {gain_resource} Discipline" is the skill's number; a rune that states its own is
        // Punishment's Hatred and Focused Mind's Discipline over time.
        Restore const restore =
            RestoreOf(rune, Numbers::Num(BaseId(Skill), "gain_resource"), Numbers::Num(spellId, "gain_resource"));
        if (restore.disciplineNow > 0)
            Resources::Energize(player, Resources::Discipline, spellId, restore.disciplineNow);
        if (restore.hatredNow > 0)
            Resources::Energize(player, Resources::Hatred, spellId, restore.hatredNow);
        switch (rune)
        {
            case Rune::FocusedMind:
            {
                double const seconds = Numbers::Num(spellId, "dot_duration_seconds");
                Regen regen;
                regen.spellId = spellId;
                regen.left = seconds * 1000.0;
                regen.perTick = RegenTick(restore.disciplineOver, seconds, Tune("preparation_regen_tick_seconds"));
                std::lock_guard<std::mutex> guard(mutex);
                regens[player->GetGUID().GetRawValue()] = regen;
                break;
            }
            case Rune::BattleScars:
                Heal(player, spellId, HealOf(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct")));
                break;
            case Rune::BackupPlan:
                // The core put the record's cooldown on the button; the chance takes it off again.
                if (CooldownSkipped(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct")))
                    Combat::SendSkillCooldown(player, spellId, 0);
                break;
            default:
                break;
        }
    }

    void BarWritten(Player* player, std::vector<DC::Classes::Slot> const& bar)
    {
        if (!player || Classes::ClassIdOf(player) != Resources::Discipline.classId)
            return;
        // "Passive: Permanently increase maximum Discipline by {max_pool_resource}": while the rune stands in a slot. The skill is the
        // one source, so a rune put in its place or taken off changes the same entry.
        double points = 0;
        for (Classes::Slot const& slot : bar)
            if (RuneAt(slot.spellId) == Rune::Invigoration)
                points = Numbers::Num(slot.spellId, "max_pool_resource");
        if (Resources::Pool::Set(player->GetGUID().GetRawValue(), BaseId(Skill), points))
            Stats::Recompute(player);
    }

    void RegisterScripts()
    {
        new Regens();
    }
} // namespace DC::Combat::DemonHunter::Preparation
