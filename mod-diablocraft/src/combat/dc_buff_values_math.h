/*
 * World of DiabloCraft - the values a buff's tooltip line shows
 * (contract docs/contracts/buff-values-messages.md).
 *
 * The record of an aura states what is fixed per stack; what depends on a rank or is live (Gogok's Dodge, the debt
 * Moratorium owes) the addon writes under it from the server's numbers. This header is the part with no core
 * dependency: how a record is spelled, and the throttle that decides when it is sent. dc_buff_values.cpp puts it on
 * the wire; scripts/tests/legendaries/test_gem_buffs.py compiles this exact file.
 */

#ifndef DC_BUFF_VALUES_MATH_H
#define DC_BUFF_VALUES_MATH_H

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace DC::Combat::BuffValues
{
    using Values = std::vector<double>;

    // The contract's number: a decimal, at most two decimals, the trailing zeros and the point dropped ("6.12",
    // "1500", "0"). A negative zero is "0".
    inline std::string Number(double value)
    {
        char text[48];
        std::snprintf(text, sizeof text, "%.2f", value);
        std::string out = text;
        while (!out.empty() && out.back() == '0')
            out.pop_back();
        if (!out.empty() && out.back() == '.')
            out.pop_back();
        return out == "-0" ? "0" : out;
    }

    // "V|aura|v1|v2..." (gone == false) or "G|aura".
    inline std::vector<std::string> Fields(std::uint32_t aura, bool gone, Values const& values)
    {
        std::vector<std::string> out{gone ? "G" : "V", std::to_string(aura)};
        if (!gone)
            for (double value : values)
                out.push_back(Number(value));
        return out;
    }

    // The aura's timer is set again when the effect has more time left than the aura (its window was renewed: at once)
    // or the aura has more than this much (milliseconds) beyond what the effect has left. The upkeep that calls Show
    // runs every few hundred milliseconds, so a timer that is merely counting down agrees with it within this much.
    // Two ticks of that upkeep, not a game number.
    inline constexpr std::int32_t DurationSlackMs = 500;

    // `currentMs` is the aura's timer (-1: none, which any time left beats), `wantedMs` what the effect has left (> 0).
    inline bool TimerDiffers(std::int32_t currentMs, std::int32_t wantedMs)
    {
        return wantedMs > currentMs || currentMs - wantedMs > DurationSlackMs;
    }

    struct Record
    {
        std::uint32_t aura = 0;
        bool gone = false;
        Values values;
    };

    // One player's auras: what the addon was last told, and what is waiting for the interval to pass. `nowMs` is the
    // server clock (it wraps; the difference is read signed).
    class Channel
    {
    public:
        // The values `aura` has now. Sent at once when the addon was told nothing yet or its last record is an
        // interval old; otherwise held (the latest wins) for Flush. Values the addon already has send nothing.
        std::optional<Record> Set(std::uint32_t aura, Values const& values, std::uint32_t nowMs,
                                  std::uint32_t intervalMs)
        {
            Entry& entry = entries_[aura];
            std::vector<std::string> const spelled = Fields(aura, false, values);
            if (entry.sent && *entry.sent == spelled)
            {
                entry.held.reset();
                return std::nullopt;
            }
            if (!entry.sent || Due(entry, nowMs, intervalMs))
            {
                entry.sent = spelled;
                entry.sentAtMs = nowMs;
                entry.held.reset();
                return Record{aura, false, values};
            }
            entry.held = Held{values, spelled};
            return std::nullopt;
        }

        // The aura is gone: one G at once if the channel knows it (a Set always sends the first record at once, so a
        // known aura is one the addon was told), nothing otherwise. The next Set is a first record again.
        std::optional<Record> Clear(std::uint32_t aura)
        {
            if (entries_.erase(aura) == 0)
                return std::nullopt;
            return Record{aura, true, {}};
        }

        // The held records whose interval has passed, oldest aura id first.
        std::vector<Record> Flush(std::uint32_t nowMs, std::uint32_t intervalMs)
        {
            std::vector<Record> out;
            for (auto& [aura, entry] : entries_)
                if (entry.held && Due(entry, nowMs, intervalMs))
                {
                    entry.sent = entry.held->spelled;
                    entry.sentAtMs = nowMs;
                    out.push_back(Record{aura, false, entry.held->values});
                    entry.held.reset();
                }
            return out;
        }

        bool Empty() const
        {
            return entries_.empty();
        }

    private:
        struct Held
        {
            Values values;
            std::vector<std::string> spelled;
        };
        struct Entry
        {
            std::optional<std::vector<std::string>> sent;
            std::uint32_t sentAtMs = 0;
            std::optional<Held> held;
        };

        static bool Due(Entry const& entry, std::uint32_t nowMs, std::uint32_t intervalMs)
        {
            return static_cast<std::int32_t>(nowMs - entry.sentAtMs) >= static_cast<std::int32_t>(intervalMs);
        }

        std::map<std::uint32_t, Entry> entries_;
    };
} // namespace DC::Combat::BuffValues

#endif
