/*
 * The Witch Doctor's timed sheet numbers: put on the sheet when a skill or rune gives them, taken off when their time
 * runs out.
 */

#include "dc_witch_doctor_sheet_buffs.h"
#include "dc_witch_doctor_buffs.h"
#include "../../items/dc_inventory.h"
#include "../../stats/dc_stats.h"
#include "GameTime.h"
#include "Player.h"

#include <chrono>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::SheetBuffs
{
    namespace
    {
        struct Key
        {
            std::uint64_t guid;
            std::uint32_t id;
            Stat stat;
            bool operator==(Key const& other) const
            {
                return guid == other.guid && id == other.id && stat == other.stat;
            }
        };
        struct KeyHash
        {
            std::size_t operator()(Key const& key) const
            {
                return std::hash<std::uint64_t>()(key.guid) ^ (std::hash<std::uint32_t>()(key.id) << 1) ^
                       (std::hash<unsigned>()(unsigned(key.stat)) << 7);
            }
        };
        struct Entry
        {
            Buffs::Held held;
            double perStack = 0;
        };

        std::mutex mutex;
        std::unordered_map<Key, Entry, KeyHash> entries;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The sheet takes the number as it is now (0 takes it off) and the client is told.
        void Sheet(Player* player, Key const& key, Bucket bucket, double value)
        {
            if (value != 0)
                Stats::AddContribution(key.guid, {Source::Temporary, key.stat, key.id, value, bucket});
            else
                Stats::RemoveContribution(key.guid, Source::Temporary, key.stat, key.id);
            Stats::Recompute(player);
            Inventory::PushSheet(player);
        }

        // The end of one cast's time: the number comes off unless a later cast moved the end (its own event closes it).
        void Lapse(Player* player, Key const& key, Bucket bucket)
        {
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = entries.find(key);
                if (found == entries.end() || !Buffs::Over(found->second.held, Now()))
                    return;
                entries.erase(found);
            }
            Sheet(player, key, bucket, 0);
        }
    } // namespace

    unsigned Stack(Player* player, std::uint32_t id, Stat stat, Bucket bucket, double perStack, unsigned maxStacks,
                   double seconds, unsigned adds)
    {
        if (!player || seconds <= 0 || perStack == 0 || adds == 0)
            return 0;
        Key const key{player->GetGUID().GetRawValue(), id, stat};
        std::uint64_t const ms = std::uint64_t(seconds * 1000.0);
        double worth;
        unsigned stacks;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Entry& entry = entries[key];
            entry.perStack = perStack;
            stacks = Buffs::Add(entry.held, Now(), ms, maxStacks, adds);
            worth = Buffs::Worth(entry.held, Now(), perStack);
        }
        Sheet(player, key, bucket, worth);
        player->m_Events.AddEventAtOffset([player, key, bucket] { Lapse(player, key, bucket); },
                                          std::chrono::milliseconds(ms + 1));
        return stacks;
    }

    double Current(Player* player, std::uint32_t id, Stat stat)
    {
        if (!player)
            return 0;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = entries.find(Key{player->GetGUID().GetRawValue(), id, stat});
        return found == entries.end() ? 0.0 : Buffs::Worth(found->second.held, Now(), found->second.perStack);
    }
} // namespace DC::Combat::WitchDoctor::SheetBuffs
