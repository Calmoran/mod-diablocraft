/*
 * Spirit Link and its five runes. The cast links the enemy aimed at and the ones nearest it; here: who is linked and
 * for how long, the damage the link itself deals each second, the share of every hit the Shaman deals to one of them
 * that the others take (a proc-free copy of the final damage, once), and each rune's part (Ancestral Chains' wider
 * link, Searing Link's burn, Frozen Link's chill and freeze, Thunder Link's larger share, Spirit Harvest's Maelstrom
 * and longer link).
 */

#include "dc_shaman_spirit_link.h"
#include "dc_shaman_common.h"
#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "ObjectAccessor.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <map>
#include <mutex>

namespace DC::Combat::Shaman::SpiritLink
{
    namespace
    {
        constexpr std::string_view Skill = "Spirit Link";

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        std::uint32_t Millis(double seconds)
        {
            return std::uint32_t(seconds * 1000.0 + 0.5);
        }

        struct Link
        {
            std::uint32_t spellId = 0;
            Rune rune = Rune::None;
            std::vector<std::uint64_t> members;
            std::uint64_t until = 0;
            double extra = 0; // seconds Spirit Harvest has added
            std::uint64_t stamp = 0;
            bool active = false;
        };
        std::mutex mutex;
        std::map<std::uint64_t, Link> links;
        std::uint64_t stamps = 0;

        // A share dealt to the others is a single copy: while one is being dealt no hit is shared again.
        thread_local bool echoing = false;

        std::uint64_t Key(Player const* player)
        {
            return player->GetGUID().GetRawValue();
        }

        Unit* Find(Player* player, std::uint64_t guid)
        {
            return ObjectAccessor::GetUnit(*player, ObjectGuid(guid));
        }

        // The link's own damage, every tick, to every linked enemy still alive.
        void Tick(Player* player, std::uint64_t stamp)
        {
            std::vector<std::uint64_t> members;
            std::uint32_t spellId;
            Rune rune;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto const found = links.find(Key(player));
                if (found == links.end() || !found->second.active || found->second.stamp != stamp ||
                    found->second.until <= Now())
                    return;
                members = found->second.members;
                spellId = found->second.spellId;
                rune = found->second.rune;
            }
            if (!player->IsAlive() || !player->IsInWorld())
                return;
            double const tick =
                TickSeconds(rune, Tunable("spirit_link_tick_seconds"), Tunable("spirit_link_burn_tick_seconds"));
            // The rune's own `damage_pct` (Searing Link's 150) or the skill's 100: the record answers with the one that applies.
            double const pct = TickPct(Numbers::Num(spellId, "damage_pct"), tick);
            for (std::uint64_t guid : members)
                if (Unit* enemy = Find(player, guid); enemy && enemy->IsAlive())
                    Combat::Strike(player, enemy, spellId, pct, true);
            player->m_Events.AddEventAtOffset([player, stamp] { Tick(player, stamp); },
                                              std::chrono::milliseconds(Millis(tick)));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The cast binds; the link's own damage is dealt each tick with its own percent.
        return RowOf(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        auto const* row = RowOf(spellId);
        if (!player || !row || targets.empty() || !targets.front()->IsAlive())
            return;
        Rune const rune = RuneOf(row->rune);
        Unit* const aimed = targets.front();
        std::vector<Unit*> enemies =
            Combat::Enemies(player, spellId, aimed->GetPosition(), Numbers::Num(spellId, "radius_yards"));
        if (std::find(enemies.begin(), enemies.end(), aimed) == enemies.end())
            enemies.push_back(aimed);
        std::vector<double> distances;
        for (Unit* enemy : enemies)
            distances.push_back(enemy->GetExactDist(aimed));
        std::vector<std::uint64_t> members;
        for (std::size_t index : Members(distances, std::size_t(Numbers::Num(spellId, "target_count"))))
            members.push_back(enemies[index]->GetGUID().GetRawValue());
        double const seconds =
            Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(spellId, "duration_seconds"));
        std::uint64_t stamp;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Link& link = links[Key(player)];
            link = {spellId, rune, members, Now() + Millis(seconds), 0, stamp = ++stamps, true};
        }
        if (rune == Rune::FrozenLink)
            for (std::uint64_t guid : members)
                if (Unit* enemy = Find(player, guid))
                    Shaman::Slow(player, enemy, Numbers::Num(spellId, "chill_pct"), seconds);
        player->m_Events.AddEventAtOffset(
            [player, stamp] { Tick(player, stamp); },
            std::chrono::milliseconds(Millis(
                TickSeconds(rune, Tunable("spirit_link_tick_seconds"), Tunable("spirit_link_burn_tick_seconds")))));
    }

    void Dealt(Player* player, Unit* target, std::uint32_t spellId, unsigned school, bool critical, double damage)
    {
        if (!IsShaman(player) || !target || echoing)
            return;
        std::vector<std::uint64_t> others;
        std::uint32_t linkId;
        Rune rune;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = links.find(Key(player));
            if (found == links.end() || !found->second.active || found->second.until <= Now())
                return;
            Link const& link = found->second;
            if (!Shares(echoing, RowOf(spellId) != nullptr))
                return;
            std::uint64_t const hit = target->GetGUID().GetRawValue();
            if (std::find(link.members.begin(), link.members.end(), hit) == link.members.end())
                return;
            for (std::uint64_t guid : link.members)
                if (guid != hit)
                    others.push_back(guid);
            linkId = link.spellId;
            rune = link.rune;
        }
        double const sharePct = ShareOf(rune, Numbers::Num(linkId, "damage_share_pct"),
                                        Numbers::Get(linkId, "damage_share_pct", "new").value_or(0.0));
        double const elitePct = Tunable("spirit_link_elite_share_pct");
        echoing = true;
        for (std::uint64_t guid : others)
            if (Unit* enemy = Find(player, guid); enemy && enemy->IsAlive())
            {
                Combat::Hit echo;
                echo.total = Shared(damage, sharePct, Shaman::IsElite(enemy), elitePct);
                echo.critical = critical;
                echo.school = school;
                Combat::DealHit(player, enemy, linkId, echo, true);
            }
        echoing = false;
    }

    void Upkeep(Player* player)
    {
        std::uint32_t spellId = 0;
        Rune rune = Rune::None;
        std::vector<std::uint64_t> alive;
        unsigned deaths = 0;
        double extended = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = links.find(Key(player));
            if (found == links.end() || !found->second.active)
                return;
            Link& link = found->second;
            if (link.until <= Now())
            {
                link.active = false;
                return;
            }
            std::vector<std::uint64_t> kept;
            for (std::uint64_t guid : link.members)
            {
                Unit* enemy = Find(player, guid);
                if (enemy && enemy->IsAlive())
                    kept.push_back(guid);
                else
                    ++deaths;
            }
            if (!deaths)
                return;
            link.members = kept;
            spellId = link.spellId;
            rune = link.rune;
            alive = kept;
            if (rune == Rune::SpiritHarvest)
                for (unsigned death = 0; death < deaths; ++death)
                {
                    double const next = Extended(link.extra, Numbers::Num(spellId, "duration_seconds", "extend"),
                                                 Numbers::Num(spellId, "duration_seconds", "cap"));
                    link.until += Millis(next - link.extra);
                    extended += next - link.extra;
                    link.extra = next;
                }
            if (link.members.size() < 2)
                link.active = false;
        }
        // "When a linked enemy dies, the others are Frozen for {freeze_duration_seconds} second."
        if (rune == Rune::FrozenLink)
            for (std::uint64_t guid : alive)
                if (Unit* enemy = Find(player, guid))
                    Shaman::Freeze(player, enemy,
                                   Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));
        // "Each linked enemy that dies generates {gain_resource} Maelstrom."
        if (rune == Rune::SpiritHarvest)
            Gain(player, spellId, deaths * Numbers::Num(spellId, "gain_resource"));
    }

    void Forget(Player* player)
    {
        std::lock_guard<std::mutex> guard(mutex);
        links.erase(Key(player));
    }
} // namespace DC::Combat::Shaman::SpiritLink
