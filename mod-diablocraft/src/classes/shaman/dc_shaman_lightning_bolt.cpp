/*
 * Lightning Bolt and its five runes: Overload's second strike, Hailstone's chill and extra Maelstrom, Earthen Spike's
 * mark and Stormcaller's extra Maelstrom. The bolt is the engine's single-enemy cast and Lava Beam's line its targeting
 * row; the generation is Maelstrom's (dc_shaman_maelstrom.cpp). The dispatch is in dc_shaman.cpp.
 */

#include "dc_shaman_lightning_bolt.h"
#include "dc_shaman_common.h"
#include "dc_shaman_chill.h"
#include "../../combat/dc_combat.h"
#include "ObjectGuid.h"
#include "ObjectMgr.h"
#include "Unit.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Util.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::Shaman::LightningBolt
{
    namespace
    {
        constexpr std::string_view Skill = "Lightning Bolt";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && std::string_view(row->skill) == Skill ? RuneOf(row->rune) : Rune::None;
        }

        // Overload's second strike is itself a hit of the skill and starts nothing.
        thread_local bool striking = false;

        struct Marked
        {
            ObjectGuid owner;
            std::uint64_t until = 0; // game time, ms
            double pct = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Marked> marks; // by the marked enemy

        bool PhysicalHit(std::uint32_t spellId)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            return info && info->GetSchoolMask() == SPELL_SCHOOL_MASK_NORMAL;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        auto const* row = Shells::FindAbility(spellId);
        return row && std::string_view(row->skill) == Skill;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The loader would read Earthen Spike's duration (the mark's seconds) as a damage that waits.
        if (!Is(spellId) || !ClaimsHit(RuneAt(spellId)))
            return std::nullopt;
        return Numbers::Num(spellId, "damage_pct");
    }

    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical)
    {
        if (striking || !player || !target)
            return;
        switch (RuneAt(spellId))
        {
            case Rune::Overload:
                // "Each cast has a {proc_chance_pct} chance to Overload and strike the target again for {damage_pct}
                // weapon damage."
                if (Overloads(frand(0.0f, 1.0f), Numbers::Num(spellId, "proc_chance_pct")))
                {
                    striking = true;
                    Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct"));
                    striking = false;
                }
                break;
            case Rune::Hailstone:
            {
                // "Chills the target ... Generates {gain_resource} extra Maelstrom against Chilled enemies": the chill
                // the enemy already carried counts, not the one this hit gives.
                bool const chilled = Chilled(player, target);
                Chill(player, target, Numbers::Num(spellId, "chill_pct"),
                      Numbers::Num(spellId, "chill_duration_seconds"));
                Gain(player, spellId, ChilledGain(chilled, Numbers::Num(spellId, "gain_resource")));
                break;
            }
            case Rune::EarthenSpike:
            {
                // "The target takes {damage_taken_pct} more Physical damage from you for {duration_seconds} seconds."
                Marked mark;
                mark.owner = player->GetGUID();
                mark.until = Now() + std::uint64_t(Numbers::Num(spellId, "duration_seconds") * 1000.0);
                mark.pct = Numbers::Num(spellId, "damage_taken_pct");
                std::lock_guard<std::mutex> guard(mutex);
                marks[target->GetGUID().GetRawValue()] = mark;
                break;
            }
            case Rune::Stormcaller:
                // "Critical hits generate {gain_resource} more."
                Gain(player, spellId, CriticalGain(critical, Numbers::Num(spellId, "gain_resource")));
                break;
            default:
                break;
        }
    }

    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)
    {
        if (!player || !target)
            return;
        double pct = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = marks.find(target->GetGUID().GetRawValue());
            if (found == marks.end())
                return;
            if (!Holds(Now(), found->second.until))
            {
                marks.erase(found);
                return;
            }
            if (found->second.owner == player->GetGUID())
                pct = found->second.pct;
        }
        if (double const bonus = MarkBonus(pct > 0, PhysicalHit(spellId), pct))
            AddFactor(out, "Earthen Spike", bonus);
    }
} // namespace DC::Combat::Shaman::LightningBolt
