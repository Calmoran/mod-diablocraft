#include "dc_ground_device.h"
#include "dc_combat.h"
#include "../common/dc_tunables.h"
#include "Creature.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "TemporarySummon.h"
#include <algorithm>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::GroundDevice
{
    namespace
    {
        // The stock World Invisible Trigger holds a device's display, and faction 35 is friendly to everyone (the
        // trigger ships hostile); identifiers.
        constexpr std::uint32_t HolderEntry = 12999;
        constexpr std::uint32_t HolderFaction = 35;
        // A holder of a device with no life of its own is left no longer than this if it is not taken away, ms.
        constexpr std::uint32_t HolderMostMs = 600000;

        struct Device
        {
            std::uint32_t serial = 0;
            Setup setup;
            Position at;
            State state;
            ObjectGuid holder;
        };

        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::vector<Device>> devices;
        std::uint32_t nextSerial = 0;

        double LookEveryMs()
        {
            return DC::Tunables::Get("combat", "ground_device_look_seconds") * 1000.0;
        }

        void Show(Player* player, Device& device)
        {
            if (!device.setup.display)
                return;
            std::uint32_t const ms = device.setup.spec.lifetimeMs > 0
                                         ? static_cast<std::uint32_t>(device.setup.spec.lifetimeMs)
                                         : HolderMostMs;
            if (TempSummon* holder = player->SummonCreature(HolderEntry, device.at.GetPositionX(),
                                                            device.at.GetPositionY(), device.at.GetPositionZ(),
                                                            device.at.GetOrientation(), TEMPSUMMON_TIMED_DESPAWN, ms))
            {
                holder->SetDisplayId(device.setup.display);
                holder->SetFaction(HolderFaction);
                holder->SetImmuneToAll(true);
                device.holder = holder->GetGUID();
            }
        }

        void Hide(Player* player, ObjectGuid holder)
        {
            if (!holder)
                return;
            if (Creature* creature = ObjectAccessor::GetCreature(*player, holder))
                creature->DespawnOrUnsummon();
        }

        // What a firing does, outside the lock: the callback is the class's own.
        void Discharge(Player* player, Device const& device, std::vector<Unit*> const& enemies)
        {
            if (device.setup.fire)
                device.setup.fire(player, device.at, enemies);
        }

        std::vector<Unit*> Near(Player* player, Device const& device)
        {
            return Combat::Enemies(player, device.setup.record, device.at, device.setup.spec.radiusYards);
        }

        class Devices final : public PlayerScript
        {
        public:
            Devices()
                : PlayerScript("dc_ground_device",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                std::vector<Device> mine;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = devices.find(player->GetGUID().GetRawValue());
                    if (found == devices.end())
                        return;
                    mine = found->second;
                }
                if (!player->IsAlive())
                {
                    Clear(player);
                    return;
                }
                std::vector<Device> stepped;
                std::vector<std::uint32_t> gone;
                for (Device& device : mine)
                {
                    std::vector<Unit*> enemies;
                    bool looked = false;
                    Outcome const outcome = Advance(device.state, device.setup.spec, diff, LookEveryMs(),
                                                    [&]
                                                    {
                                                        enemies = Near(player, device);
                                                        looked = true;
                                                        return !enemies.empty();
                                                    });
                    for (unsigned i = 0; i < outcome.fires; ++i)
                        Discharge(player, device, looked ? enemies : Near(player, device));
                    if (outcome.gone)
                    {
                        Hide(player, device.holder);
                        gone.push_back(device.serial);
                    }
                    else
                        stepped.push_back(device);
                }
                std::lock_guard<std::mutex> guard(mutex);
                auto found = devices.find(player->GetGUID().GetRawValue());
                if (found == devices.end())
                    return;
                // Each stored device takes its new state; devices laid or taken away during this update are left as
                // they are.
                for (Device& stored : found->second)
                {
                    auto updated = std::find_if(stepped.begin(), stepped.end(),
                                                [&](Device const& d) { return d.serial == stored.serial; });
                    if (updated != stepped.end())
                        stored.state = updated->state;
                }
                std::erase_if(found->second, [&](Device const& d)
                              { return std::find(gone.begin(), gone.end(), d.serial) != gone.end(); });
            }

            void OnPlayerLogout(Player* player) override
            {
                Clear(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Clear(player);
            }
        };
    } // namespace

    void Place(Player* player, Setup const& setup, Position const& at)
    {
        if (!player)
            return;
        Device device;
        device.setup = setup;
        device.at = at;
        std::vector<ObjectGuid> away;
        {
            std::lock_guard<std::mutex> guard(mutex);
            device.serial = ++nextSerial;
            auto& laid = devices[player->GetGUID().GetRawValue()];
            // The oldest of the kind give way.
            std::size_t const of = static_cast<std::size_t>(
                std::count_if(laid.begin(), laid.end(), [&](Device const& d) { return d.setup.kind == setup.kind; }));
            for (std::size_t give = Overflow(of, setup.spec.most); give > 0; --give)
            {
                auto oldest =
                    std::find_if(laid.begin(), laid.end(), [&](Device const& d) { return d.setup.kind == setup.kind; });
                away.push_back(oldest->holder);
                laid.erase(oldest);
            }
            Show(player, device);
            laid.push_back(device);
        }
        for (ObjectGuid holder : away)
            Hide(player, holder);
    }

    unsigned Detonate(Player* player, std::uint32_t kind)
    {
        if (!player || !player->IsAlive())
            return 0;
        std::vector<Device> firing;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = devices.find(player->GetGUID().GetRawValue());
            if (found == devices.end())
                return 0;
            auto& laid = found->second;
            for (Device const& device : laid)
                if (device.setup.kind == kind && Detonable(device.state, device.setup.spec))
                    firing.push_back(device);
            std::erase_if(laid,
                          [&](Device const& d) { return d.setup.kind == kind && Detonable(d.state, d.setup.spec); });
        }
        for (Device const& device : firing)
        {
            Discharge(player, device, Near(player, device));
            Hide(player, device.holder);
        }
        return static_cast<unsigned>(firing.size());
    }

    std::size_t Count(Player const* player, std::uint32_t kind)
    {
        if (!player)
            return 0;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = devices.find(player->GetGUID().GetRawValue());
        if (found == devices.end())
            return 0;
        return static_cast<std::size_t>(std::count_if(found->second.begin(), found->second.end(),
                                                      [&](Device const& d) { return d.setup.kind == kind; }));
    }

    std::vector<Position> Places(Player const* player, std::uint32_t kind)
    {
        std::vector<Position> places;
        if (!player)
            return places;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = devices.find(player->GetGUID().GetRawValue());
        if (found == devices.end())
            return places;
        for (Device const& device : found->second)
            if (device.setup.kind == kind)
                places.push_back(device.at);
        return places;
    }

    void Clear(Player* player)
    {
        if (!player)
            return;
        std::vector<Device> removed;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = devices.find(player->GetGUID().GetRawValue());
            if (found == devices.end())
                return;
            removed = std::move(found->second);
            devices.erase(found);
        }
        for (Device const& device : removed)
            Hide(player, device.holder);
    }

    void RegisterScripts()
    {
        new Devices();
    }
} // namespace DC::Combat::GroundDevice
