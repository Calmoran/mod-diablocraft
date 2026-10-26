#ifndef DC_SKILL_BONUSES_H
#define DC_SKILL_BONUSES_H

#include <cstdint>
#include <unordered_map>
#include <utility>

namespace DC::Items
{
// Caller owns synchronization. Equip updates are idempotent by item/affix ID.
class SkillBonuses
{
    // K5: keyed by the base skill's spell id, not its English name. An affix
    // that says "+X% Bash damage" names a skill by id now, so renaming Bash
    // cannot detach the bonus and two names cannot collide into one bucket.
    std::unordered_map<std::uint64_t, std::pair<std::uint32_t, double>> rows;
    std::unordered_map<std::uint32_t, double> totals;
public:
    void Remove(std::uint64_t id)
    {
        auto found = rows.find(id);
        if (found == rows.end()) return;
        totals[found->second.first] -= found->second.second;
        rows.erase(found);
    }
    void Set(std::uint64_t id, std::uint32_t skillId, double value)
    {
        Remove(id);
        rows[id] = {skillId, value};
        totals[skillId] += value;
    }
    double Get(std::uint32_t skillId) const
    {
        auto found = totals.find(skillId);
        return found == totals.end() ? 0 : found->second;
    }
};
}
#endif
