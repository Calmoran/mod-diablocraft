/*
 * The Witch Doctor's passives that give Mana over time: Rush of Essence (a spirit spell starts a stream of Mana that
 * runs for its seconds, any number of streams at once up to the file's most) and Vision Quest (damage by four skills
 * raises the Mana regeneration for a few seconds). Both are points a second on the sheet's Mana regeneration stat, so
 * the class's own resource pulse pays them: there is no tick of their own.
 */

#include "dc_witch_doctor_mana_passives.h"
#include "dc_witch_doctor_passive_common.h"
#include "dc_witch_doctor_passive_rules.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "GameTime.h"
#include "Player.h"
#include "Unit.h"

#include <array>
#include <chrono>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::WitchDoctor::Passive::ManaOverTime
{
    namespace
    {
        // The spirit spells and the skills Vision Quest counts (witch_doctor_passives.csv's tooltips name them).
        constexpr std::array<std::string_view, 6> SpiritSpells = {"Haunt",        "Horrify",        "Mass Confusion",
                                                                  "Soul Harvest", "Spirit Barrage", "Spirit Walk"};
        constexpr std::array<std::string_view, 4> QuestSkills = {"Corpse Spiders", "Firebomb", "Plague of Toads",
                                                                 "Poison Dart"};

        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::vector<std::uint64_t>> streams; // by Witch Doctor: when each stream ends
        std::unordered_map<std::uint64_t, std::uint64_t> questUntil; // by Witch Doctor: when the quest's bonus ends

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(seconds * 1000.0 + 0.5);
        }

        // The Mana regeneration this passive puts on the sheet, a number of points a second (0 takes it off).
        void Publish(Player* player, std::uint32_t id, double pointsPerSecond)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            Stats::RemoveContribution(guid, Source::Temporary, Stat::ManaRegen, id);
            if (pointsPerSecond > 0)
                Stats::AddContribution(guid, {Source::Temporary, Stat::ManaRegen, id, pointsPerSecond, Bucket::Flat});
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // The streams still running: what the sheet pays.
        void Settle(Player* player)
        {
            unsigned running;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& ends = streams[player->GetGUID().GetRawValue()];
                Rules::Prune(ends, Now());
                running = unsigned(ends.size());
            }
            Publish(player, Id("Rush of Essence"),
                    running * Rules::PerSecond(Num("Rush of Essence", "gain_resource"),
                                               Num("Rush of Essence", "duration_seconds")));
        }

        void Lapse(Player* player)
        {
            if (player->IsInWorld())
                Settle(player);
        }

        // The quest's time may have been renewed since this was set: it waits out what is left, else takes the bonus off.
        void QuestLapse(Player* player)
        {
            std::uint64_t left;
            {
                std::lock_guard<std::mutex> guard(mutex);
                std::uint64_t const until = questUntil[player->GetGUID().GetRawValue()], now = Now();
                left = until > now ? until - now : 0;
            }
            if (left)
                player->m_Events.AddEventAtOffset([player] { QuestLapse(player); }, std::chrono::milliseconds(left + 1));
            else if (player->IsInWorld())
                Publish(player, Id("Vision Quest"), 0);
        }
    } // namespace

    void Cast(Player* player, std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!row || !Rules::Listed(SpiritSpells, row->skill) || !On(player, "Rush of Essence"))
            return;
        // "Spirit spells return {gain_resource} Mana over {duration_seconds} seconds."
        std::uint64_t const lasts = Millis(Num("Rush of Essence", "duration_seconds"));
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto& ends = streams[player->GetGUID().GetRawValue()];
            Rules::Prune(ends, Now());
            if (ends.size() >= std::size_t(Tune("rush_of_essence_max_streams")))
                return;
            ends.push_back(Now() + lasts);
        }
        Settle(player);
        player->m_Events.AddEventAtOffset([player] { Lapse(player); }, std::chrono::milliseconds(lasts + 1));
    }

    void Landed(Player* player, Unit*, std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!row || !Rules::Listed(QuestSkills, row->skill) || !On(player, "Vision Quest"))
            return;
        // "your Mana regeneration is increased by {regen_pct} for {duration_seconds} seconds": a hit while it lasts
        // only renews the time.
        std::uint64_t const lasts = Millis(Num("Vision Quest", "duration_seconds")), now = Now();
        bool fresh;
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::uint64_t& until = questUntil[player->GetGUID().GetRawValue()];
            fresh = until <= now;
            until = now + lasts;
        }
        if (!fresh)
            return;
        Publish(player, Id("Vision Quest"), Rules::RegenBonus(Resources::Mana.regenPerSecond, Num("Vision Quest", "regen_pct")));
        player->m_Events.AddEventAtOffset([player] { QuestLapse(player); }, std::chrono::milliseconds(lasts + 1));
    }
} // namespace DC::Combat::WitchDoctor::Passive::ManaOverTime
