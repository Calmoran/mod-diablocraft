/*
 * Smite and its five runes: the chains that break off to the enemies around the one hit, and what each rune does to the
 * enemies they struck. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_smite.h"
#include "../dc_level_heal.h"
#include "dc_crusader_common.h"
#include "../../combat/dc_item_powers.h"
#include "ObjectAccessor.h"
#include "Util.h"

namespace DC::Combat::Crusader::Smite
{
    namespace
    {
        constexpr std::string_view Skill = "Smite";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("crusader", name);
        }

        // Shared Fate: the enemies the chains bound, and how far apart each pair was when bound.
        struct Tie
        {
            std::uint64_t a, b;
            double gap;
            std::uint64_t until;
            double distance; // yards apart that sets the stun off
            double stunSeconds;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::vector<Tie>> ties; // per Crusader
        std::unordered_map<std::uint64_t, bool> watching;         // per Crusader: a check is already scheduled

        Unit* Find(Player* player, std::uint64_t raw)
        {
            Unit* unit = ObjectAccessor::GetUnit(*player, ObjectGuid(raw));
            return unit && unit->IsAlive() ? unit : nullptr;
        }

        // ponytail: the least the look-over interval can be. The tunable has no number yet, and 0 must not make the
        // check run on every tick; this is a guard against 0, not a tuning number.
        constexpr double CheckFloorSeconds = 0.05;

        std::chrono::milliseconds CheckEvery()
        {
            return std::chrono::milliseconds(
                std::uint64_t(std::max(CheckFloorSeconds, Tune("smite_shared_fate_check_seconds")) * 1000));
        }

        // Shatter's explosion around the place `centre` stood when the chains struck it: the enemy's own place if it is
        // still there, else where it was.
        void Explode(Player* player, std::uint32_t spellId, std::uint64_t raw, Position where)
        {
            if (!player->IsInWorld() || !player->IsAlive())
                return;
            if (Unit* centre = ObjectAccessor::GetUnit(*player, ObjectGuid(raw)))
                where = centre->GetPosition();
            auto const pct = Numbers::Get(spellId, "damage_pct");
            for (Unit* enemy : Combat::Enemies(player, spellId, where, Numbers::Num(spellId, "radius_yards")))
                Combat::Strike(player, enemy, spellId, pct);
        }

        // One look at the Crusader's ties: those past their end, or with an enemy gone, are dropped; a pair that has
        // moved apart stuns both and is dropped. The next look is scheduled while any tie is left.
        void Check(Player* player, std::uint64_t guid)
        {
            std::vector<std::pair<std::uint64_t, std::uint64_t>> apart;
            double stun = 0;
            bool more;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = ties[guid];
                std::uint64_t const now = Now();
                std::erase_if(mine,
                              [&](Tie& tie)
                              {
                                  if (!Bound(now, tie.until))
                                      return true;
                                  Unit* one = Find(player, tie.a);
                                  Unit* other = Find(player, tie.b);
                                  if (!one || !other)
                                      return true;
                                  if (!MovedApart(one->GetExactDist(other), tie.gap, tie.distance))
                                      return false;
                                  apart.emplace_back(tie.a, tie.b);
                                  stun = tie.stunSeconds;
                                  return true;
                              });
                more = !mine.empty();
                if (!more)
                {
                    ties.erase(guid);
                    watching.erase(guid);
                }
            }
            for (auto const& pair : apart)
                for (std::uint64_t raw : {pair.first, pair.second})
                    if (Unit* enemy = Find(player, raw))
                        Stun(player, enemy, stun);
            if (more)
                player->m_Events.AddEventAtOffset([player, guid] { Check(player, guid); }, CheckEvery());
        }

        void Bind(Player* player, std::uint32_t spellId, std::vector<Unit*> const& hit)
        {
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::uint64_t const until = Now() + std::uint64_t(Tune("smite_shared_fate_seconds") * 1000);
            double const distance = Numbers::Num(spellId, "distance_yards"),
                         stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);
            bool start = false;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto& mine = ties[guid];
                for (std::size_t i = 0; i < hit.size(); ++i)
                    for (std::size_t j = i + 1; j < hit.size(); ++j)
                        mine.push_back({hit[i]->GetGUID().GetRawValue(), hit[j]->GetGUID().GetRawValue(),
                                        hit[i]->GetExactDist(hit[j]), until, distance, stun});
                start = !mine.empty() && !watching[guid];
                if (start)
                    watching[guid] = true;
            }
            if (start)
                player->m_Events.AddEventAtOffset([player, guid] { Check(player, guid); }, CheckEvery());
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        return Numbers::Get(BaseId(Skill), "damage_pct", "hit");
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId) || targets.empty())
            return;
        Unit* first = targets.front();
        // The chains: the nearest enemies to the one hit, inside the chain radius, up to the record's count.
        double const radius = Numbers::Num(spellId, "radius_yards", "chain");
        std::vector<Unit*> candidates;
        std::vector<double> distances;
        for (Unit* enemy : Combat::Enemies(player, spellId, first->GetPosition(), radius))
            if (enemy != first)
            {
                candidates.push_back(enemy);
                distances.push_back(first->GetExactDist(enemy));
            }
        std::vector<Unit*> hit{first};
        auto const chain = Numbers::Get(spellId, "damage_pct", "chain");
        for (std::size_t index : Chained(distances, radius, std::size_t(Numbers::Num(spellId, "target_count"))))
            if (Combat::Strike(player, candidates[index], spellId, chain))
                hit.push_back(candidates[index]);

        switch (RuneAt(spellId))
        {
            case Rune::SharedFate:
                Bind(player, spellId, hit);
                break;
            case Rune::Shackle:
                for (Unit* enemy : hit)
                    if (roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct"))))
                        Root(player, enemy, Numbers::Num(spellId, "immobilize_duration_seconds"));
                break;
            case Rune::Shatter:
            {
                // "The holy chains explode dealing {damage_pct} weapon damage as Holy to enemies within {radius_yards}
                // yards": around each enemy the chains struck.
                // D3 explodes them half a second later (the power file's SF_10 'c: Expiration Delay'): a tunable, 0 at once.
                double const delay = Tune("smite_shatter_delay_seconds");
                for (Unit* centre : hit)
                {
                    std::uint64_t const raw = centre->GetGUID().GetRawValue();
                    Position const where = centre->GetPosition();
                    if (delay <= 0)
                        Explode(player, spellId, raw, where);
                    else
                        player->m_Events.AddEventAtOffset(
                            [player, spellId, raw, where] { Explode(player, spellId, raw, where); },
                            std::chrono::milliseconds(std::uint64_t(delay * 1000)));
                }
                break;
            }
            case Rune::Reaping:
                Buffs::Stack(player, spellId, Stat::LifeRegen, Bucket::Flat,
                             Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_second_life"), player->GetLevel()),
                             unsigned(Numbers::Num(spellId, "max_stacks_count")),
                             Numbers::Num(spellId, "duration_seconds"), unsigned(hit.size()));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::Smite
