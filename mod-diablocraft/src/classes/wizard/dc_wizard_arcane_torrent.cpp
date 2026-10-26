#include "dc_wizard_internal.h"
#include "SpellAuraEffects.h"
#include <algorithm>
#include <cmath>

namespace DC::Combat::Wizard
{
    using namespace Shared;

    void ChannelTick(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !IsRune(spellId, "Arcane Mines"))
            return;
        uint32 const id = spellId;
        uint64 const now = Now();
        // "Lay Arcane mines that arm after {duration_seconds} seconds. These
        // mines explode when an enemy approaches". The simulator arms each
        // mine duration_seconds after it is laid and explodes it then, over
        // radius_yards after delay_seconds, at most max_count at a time
        // (wizard.js:279-290). "Approaches" has no sourced distance, so a
        // mine with no enemy in its explosion when it goes off hits nothing.
        double const fuse = Num(id, "duration_seconds") + Num(id, "delay_seconds");
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = StateOf(player);
            std::erase_if(state.mines, [now](uint64 at) { return at <= now; });
            if (state.mines.size() >= std::size_t(Num(id, "max_count")))
                return;
            state.mines.push_back(now + uint64(fuse * 1000));
        }
        After(player, fuse,
              [id, center](Player* p)
              {
                  double const pct = Num(id, "slow_pct"), seconds = Num(id, "slow_duration_seconds");
                  for (Unit* hit : Combat::StrikeArea(p, id, center, Num(id, "radius_yards")))
                  {
                      // "their movement and attack speeds reduced by {slow_pct}".
                      Slow(p, hit, pct, seconds);
                      if (Aura* aura = Apply(p, hit, "Wizard - Slowed attacks", seconds))
                          if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                              effect->ChangeAmount(-int32(std::lround(pct)));
                  }
              });
    }

    bool ChannelsByDuration(std::string const& skill)
    {
        return skill == "Arcane Torrent";
    }
} // namespace DC::Combat::Wizard
