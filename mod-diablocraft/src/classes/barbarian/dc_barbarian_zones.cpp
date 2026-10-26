#include "dc_barbarian_zones.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "SpellMgr.h"

namespace DC::Combat::Abilities::Zones
{
    using namespace Shared;

    void OnUpdate(Player* p, State& s, uint32 diff)
    {
        for (auto& zone : s.zones)
        {
            double previous = zone.elapsed;
            zone.elapsed = std::min(zone.duration, zone.elapsed + diff);
            Hit tick = zone.snapshot;
            tick.total = ZoneDamage(zone.snapshot.total, previous, zone.elapsed, zone.duration);
            auto row = Shells::FindAbility(zone.spell);
            if (row && std::string(row->skill) == "Earthquake" && Rune(*row, "Giant's Stride"))
                for (unsigned due = TremorsDue(previous, zone.elapsed, zone.duration, unsigned(Numbers::Num(row->id, "hit_count")));
                     due > 0; --due)
                    Eruption(p, p, row->id, Numbers::Num(row->id, "damage_pct"), Tune("earthquake_tremor_radius_yards"));
            if (tick.total > 0)
                for (auto u : At(p, zone.center, zone.radius))
                {
                    auto info = sSpellMgr->GetSpellInfo(zone.spell);
                    if (!info || u->IsImmunedToDamage(p, info))
                        continue;
                    if (!zone.selected.empty() && std::find(zone.selected.begin(), zone.selected.end(),
                                                            u->GetGUID()) == zone.selected.end())
                        continue;
                    if (zone.slowOnly)
                    {
                        if (auto row = Shells::FindAbility(zone.spell))
                            Control(p, u, *row, (zone.duration - zone.elapsed) / 1000);
                        continue;
                    }
                    if (row && std::string(row->skill) == "Earthquake" && Rune(*row, "Chilling Earth"))
                        Control(p, u, *row, Tune("earthquake_chilling_freeze_seconds"));
                    DealHit(p, u, zone.spell, tick);
                    if (!zone.connected)
                    {
                        zone.connected = true;
                        Connected(p, zone.spell);
                    }
                }
        }
        std::erase_if(s.zones, [](auto const& z) { return z.elapsed >= z.duration; });
    }
} // namespace DC::Combat::Abilities::Zones
