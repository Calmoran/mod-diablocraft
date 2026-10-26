// A stand-in for the core's Player, just wide enough for dc_resources.h and
// the HEAD expressions it replaced (diablocraft-resource-registry harness).
// SetPower, SetMaxPower and ModifyPower copy the pinned core's arithmetic
// (Unit.cpp:11030-11060, 12438-12515); every write is logged so the harness
// compares the call sequence, not only the end state.
#pragma once
#include <algorithm>
#include <cstdint>
#include <sstream>
#include <string>

using int32 = std::int32_t;
using uint32 = std::uint32_t;

enum Powers : int8_t
{
    POWER_MANA = 0,
    POWER_RAGE = 1,
    POWER_FOCUS = 2,
    POWER_ENERGY = 3,
    POWER_HAPPINESS = 4,
    POWER_RUNE = 5,
    POWER_RUNIC_POWER = 6,
    MAX_POWERS = 7
};

class Player
{
public:
    uint32 power[MAX_POWERS] = {};
    uint32 maxPower[MAX_POWERS] = {};
    Powers display = POWER_RAGE;
    std::ostringstream log;

    Powers getPowerType() const
    {
        return display;
    }
    uint32 GetPower(Powers p) const
    {
        return power[p];
    }
    uint32 GetMaxPower(Powers p) const
    {
        return maxPower[p];
    }

    void SetPower(Powers p, uint32 val, bool = true, bool = false)
    {
        uint32 const max = GetMaxPower(p);
        if (max < val)
            val = max;
        log << "Set(" << int(p) << "," << val << ");";
        power[p] = val;
    }

    void SetMaxPower(Powers p, uint32 val)
    {
        log << "SetMax(" << int(p) << "," << val << ");";
        uint32 const cur = GetPower(p);
        maxPower[p] = val;
        if (val < cur)
            SetPower(p, val);
    }

    int32 ModifyPower(Powers p, int32 dVal, bool = true)
    {
        log << "Modify(" << int(p) << "," << dVal << ");";
        if (dVal == 0)
            return 0;
        int32 const cur = int32(GetPower(p));
        int32 const val = dVal + cur;
        if (val <= 0)
        {
            SetPower(p, 0);
            return -cur;
        }
        int32 const max = int32(GetMaxPower(p));
        if (val < max)
        {
            SetPower(p, val);
            return val - cur;
        }
        if (cur != max)
        {
            SetPower(p, max);
            return max - cur;
        }
        return 0;
    }

    void EnergizeBySpell(Player*, uint32 spellId, uint32 amount, Powers p)
    {
        log << "Energize(" << spellId << "," << amount << "," << int(p) << ");";
        ModifyPower(p, int32(amount));
    }

    std::string State() const
    {
        std::ostringstream out;
        for (int i = 0; i < MAX_POWERS; ++i)
            out << power[i] << "/" << maxPower[i] << " ";
        return out.str() + "| " + log.str();
    }
};
