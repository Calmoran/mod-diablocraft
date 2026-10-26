/*
 * Land of the Dead and its five runes. The cast opens the land for the skill's seconds: the shared corpses meet every request
 * with corpses made on the spot, so the corpse skills need none. Invigoration opens a window of free abilities, Frozen Lands and
 * Plaguelands act on the enemies around the Necromancer every period while it lasts, and a kill hook heals for Land of Plenty and
 * counts kills for Shallow Graves, which extends the land.
 */

#include "dc_necromancer_land_of_the_dead.h"
#include "dc_necromancer_land_of_the_dead_math.h"
#include "dc_necromancer_common.h"
#include "../../combat/dc_corpses.h"
#include "../../combat/dc_item_powers.h"

#include "GameTime.h"
#include "ScriptMgr.h"

#include <algorithm>
#include <chrono>
#include <map>
#include <mutex>
#include <utility>

namespace DC::Combat::Necromancer::LandOfTheDead
{
    namespace
    {
        constexpr std::string_view Skill = "Land of the Dead";

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

        std::uint32_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint32_t(seconds * 1000.0 + 0.5) : 0;
        }

        // The land a Necromancer has open: its spell, when it ends, the kills in it and how long it has been extended. A new cast
        // takes a new stamp, so the periods of an old land find theirs gone and stop.
        struct Land
        {
            std::uint32_t spellId = 0;
            std::uint64_t until = 0;
            std::uint64_t stamp = 0;
            unsigned kills = 0;
            std::uint64_t extendedMs = 0;
        };
        std::mutex mutex;
        std::map<std::uint64_t, Land> lands;
        std::map<std::pair<std::uint64_t, std::uint64_t>, double> plagued; // what Plaguelands has dealt to each enemy
        std::uint64_t stamps = 0;

        std::size_t Phantoms()
        {
            return std::size_t(std::max(0.0, Tune("land_of_the_dead_corpses")));
        }

        // The land of `guid` if it is open under `stamp` now (0: any stamp).
        bool Open(std::uint64_t guid, std::uint64_t stamp, Land& out)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = lands.find(guid);
            if (found == lands.end() || Now() >= found->second.until || (stamp && found->second.stamp != stamp))
                return false;
            out = found->second;
            return true;
        }

        // Frozen Lands: every period, the enemies around the Necromancer are frozen.
        void Freeze(Player* player, std::uint64_t stamp)
        {
            Land land;
            if (!player->IsInWorld() || !Open(player->GetGUID().GetRawValue(), stamp, land))
                return;
            for (Unit* enemy : Combat::Enemies(player, land.spellId, player->GetPosition(), Tune("frozen_lands_radius_yards")))
                Stun(player, enemy, Tune("frozen_lands_freeze_seconds") * ItemPowers::StunFactor(player));
            player->m_Events.AddEventAtOffset([player, stamp] { Freeze(player, stamp); },
                                              std::chrono::milliseconds(Millis(Tune("frozen_lands_period_seconds"))));
        }

        // Plaguelands: every interval, the nearest enemies around the Necromancer suffer the rune's weapon damage, none more than
        // the rune's maximum in all.
        void Plague(Player* player, std::uint64_t stamp)
        {
            Land land;
            if (!player->IsInWorld() || !player->IsAlive() || !Open(player->GetGUID().GetRawValue(), stamp, land))
                return;
            auto enemies = Combat::Enemies(player, land.spellId, player->GetPosition(), Tune("plaguelands_radius_yards"));
            std::stable_sort(enemies.begin(), enemies.end(),
                             [player](Unit* a, Unit* b) { return player->GetExactDist(a) < player->GetExactDist(b); });
            if (enemies.size() > std::size_t(Tune("plaguelands_targets")))
                enemies.resize(std::size_t(Tune("plaguelands_targets")));
            double const tick = Numbers::Num(land.spellId, "damage_pct", "per_second"),
                         most = Numbers::Num(land.spellId, "damage_pct", "maximum");
            for (Unit* enemy : enemies)
            {
                double pct;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    double& dealt = plagued[{player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue()}];
                    pct = PlagueTick(dealt, tick, most);
                    dealt += pct;
                }
                if (pct > 0)
                    Combat::Strike(player, enemy, land.spellId, pct);
            }
            player->m_Events.AddEventAtOffset([player, stamp] { Plague(player, stamp); },
                                              std::chrono::milliseconds(Millis(Tune("plaguelands_interval_seconds"))));
        }

        // A kill in the land: Land of Plenty heals, Shallow Graves counts it and, on the trigger count, extends the land.
        class Kills final : public UnitScript
        {
        public:
            Kills()
                : UnitScript("dc_necromancer_land_of_the_dead", true, {UNITHOOK_ON_UNIT_DEATH})
            {
            }

            void OnUnitDeath(Unit* victim, Unit* killer) override
            {
                Player* player = killer ? killer->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
                if (!victim || !player || victim == player || victim->IsControlledByPlayer())
                    return;
                Land land;
                if (!Open(player->GetGUID().GetRawValue(), 0, land))
                    return;
                switch (RuneAt(land.spellId))
                {
                    case Rune::LandOfPlenty:
                        Heal(player, land.spellId, KillHeal(player->GetMaxHealth(), Numbers::Num(land.spellId, "heal_pct")));
                        break;
                    case Rune::ShallowGraves:
                    {
                        std::uint64_t until;
                        {
                            std::lock_guard<std::mutex> guard(mutex);
                            Land& held = lands[player->GetGUID().GetRawValue()];
                            ++held.kills;
                            if (!ExtendsOn(held.kills, unsigned(Numbers::Num(held.spellId, "trigger_count"))))
                                return;
                            double const more = ExtensionFor(held.extendedMs / 1000.0, Numbers::Num(held.spellId, "duration_seconds", "extension"),
                                                             Numbers::Num(held.spellId, "duration_seconds", "maximum"));
                            held.extendedMs += Millis(more);
                            held.until += Millis(more);
                            until = held.until;
                        }
                        Corpses::AtWill(player, until, Phantoms());
                        break;
                    }
                    default:
                        break;
                }
            }
        };
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const&)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        std::uint64_t stamp, until;
        {
            std::lock_guard<std::mutex> guard(mutex);
            stamp = ++stamps;
            until = Now() + Millis(seconds);
            lands[player->GetGUID().GetRawValue()] = {spellId, until, stamp, 0, 0};
            for (auto it = plagued.begin(); it != plagued.end();)
                it = it->first.first == player->GetGUID().GetRawValue() ? plagued.erase(it) : std::next(it);
        }
        // "All corpse skills can be used at will": the shared corpses meet a request with corpses made on the spot.
        Corpses::AtWill(player, until, Phantoms());
        switch (RuneAt(spellId))
        {
            case Rune::Invigoration:
                // "Your skills do not cost resources while Land of the Dead is active."
                ItemPowers::FreeAbilities(player, seconds);
                break;
            case Rune::FrozenLands:
                Freeze(player, stamp);
                break;
            case Rune::Plaguelands:
                Plague(player, stamp);
                break;
            default:
                break;
        }
    }

    void RegisterScripts()
    {
        new Kills();
    }
} // namespace DC::Combat::Necromancer::LandOfTheDead
