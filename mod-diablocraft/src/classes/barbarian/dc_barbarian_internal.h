// What the Barbarian's skill files share: the state kept per player, the lock around it and the small helpers every
// skill's mechanic uses. The helpers are defined in dc_barbarian_helpers.cpp.
#pragma once
#include "dc_barbarian.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_damage_buckets.h"
#include "../../combat/dc_movement_effects.h"
#include "../../combat/dc_spell_shells.h"
#include "../../stats/dc_stats.h"
#include "Position.h"
#include "ObjectGuid.h"
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Abilities
{
    namespace Shared
    {
        using Row = Shells::Ability;
        constexpr uint32 First = 81000, Last = 81137, Marker = 81310;
        struct Charge
        {
            unsigned count = 0;
            double left = 0;
            bool initialized = false;
            double period = 0; // Cast-time CDR snapshot, in milliseconds.
        };
        struct Zone
        {
            uint32 spell = 0;
            Position center;
            Hit snapshot;
            double duration = 0, elapsed = 0, radius = 0;
            bool connected = false;
            bool slowOnly = false;
            std::vector<ObjectGuid> selected;
        };
        struct Devil
        {
            Position center;
            double direction=0, elapsed=0;
            uint32 spell=0;
            Hit snapshot;
            std::vector<ObjectGuid> hit;
        };
        struct State
        {
            Charge revenge, charge{1, 0, true}, avalanche;
            uint32 whirlwind=0;
            // Which hand the next channel tick swings: D3 alternates them
            // while dual wielding (simulator/cast.js:391-397), and a channel
            // always starts on the main hand.
            bool whirlwindOffhand=false;
            double whirlwindClock=0, devilClock=0;
            std::vector<Devil> devils;
            double avalancheSpent = 0, bloodshedClock = 0, tornadoClock = 0;
            uint32 map = 0, instance = 0;
            std::vector<Zone> zones;
            std::vector<std::pair<uint32, double>> criticals;
            std::vector<uint64> collisions;
        };
        extern std::unordered_map<std::string, double> tuning;
        extern std::unordered_map<uint64, State> states;
        extern std::recursive_mutex mutex;
        extern std::unordered_map<uint64, std::vector<Classes::Slot>> bars;
        uint32 AuraId(uint32 id);
        bool HasMarker(Row const& row);
        Row const* Base(std::string const& skill);
        bool Rune(Row const& row, char const* name);
        Row const* RuneRow(Player const* p, Row const& active, char const* rune);
        Row const* Active(Player* p, char const* skill);
        Row const* Buff(Unit const* p, char const* skill);
        double Tune(char const* key);
        void Fury(Player* p, double amount);
        void Heal(Player* owner, Unit* target, uint32 spell, double amount);
        std::vector<Unit*> Nearby(Player* owner, Unit* center, double radius, bool friendly = false);
        std::vector<Unit*> At(Player* p, Position const& center, double radius);
        double ZoneDamage(double total, double previous, double elapsed, double duration);
        unsigned TremorsDue(double previous, double elapsed, double duration, unsigned count);
        void ZoneStart(Player* p, Row const& row, Position const& center, double duration, double radius,
                       double overridePct = 0, bool slowOnly = false);
        void Mark(Player* owner, Unit* target, Row const& row, double seconds);
        void Control(Player* p, Unit* u, Row const& row, double seconds);
        void Add(Player* p, uint32 id, Stat stat, double value, Bucket bucket = Bucket::Flat);
        bool Procs(uint32 spellId);
        uint32 WrathBuff();
        uint32 FrayBuff();
        inline auto Recharger(uint32 diff)
        {
            return [diff](Charge& c, unsigned cap)
            {
                if (c.count >= cap)
                {
                    c.count = cap;
                    c.left = 0;
                    return;
                }
                c.left -= diff;
                while (c.left <= 0 && c.count < cap)
                {
                    ++c.count;
                    c.left += c.period;
                }
                if (c.count == cap)
                    c.left = 0;
            };
        }
        void Refresh(Player* p);
        void Reduce(Player* p, char const* skill, double milliseconds);
        void Eruption(Player* p, Unit* center, uint32 spell, double pct, double radius);
    } // namespace Shared
} // namespace DC::Combat::Abilities
