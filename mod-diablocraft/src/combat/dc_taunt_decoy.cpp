/*
 * A decoy that taunts and then explodes (dc_taunt_decoy.h). The decoy stands where it was put (the legendary allies'
 * pawn AI only holds still); the enemies near it are engaged with it and taunted by the core's own taunt aura cast from
 * it; the explosion is the owner's hit on every enemy in its radius, dealt from the owner's event queue at the spot, so
 * the decoy being killed before the delay does not cancel it.
 */

#include "dc_taunt_decoy.h"
#include "dc_taunt_decoy_math.h"
#include "dc_combat.h"
#include "Creature.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellAuras.h"
#include "TemporarySummon.h"

#include <chrono>
#include <vector>

namespace DC::Combat::TauntDecoy
{
    namespace
    {
        // Stock "Taunt" (355): one SPELL_AURA_MOD_TAUNT effect, which makes the enemy attack its caster; here the decoy
        // casts it.
        constexpr std::uint32_t Taunt = 355;
        // How long past the explosion the decoy stays if nothing removes it first.
        constexpr std::uint32_t GraceMs = 2000;

        // Every enemy within the taunt radius is engaged with the decoy and taunted by it for the delay.
        void Hold(Player* owner, TempSummon* decoy, Spec const& spec, std::uint32_t ms)
        {
            for (Unit* enemy : Combat::Enemies(owner, spec.spellId, decoy->GetPosition(), spec.tauntRadius))
            {
                if (!Within(decoy->GetExactDist(enemy), spec.tauntRadius))
                    continue;
                enemy->EngageWithTarget(decoy);
                enemy->GetThreatMgr().AddThreat(decoy, 1.0f);
                if (Aura* taunt = decoy->AddAura(Taunt, enemy))
                {
                    taunt->SetMaxDuration(int32(ms));
                    taunt->SetDuration(int32(ms));
                }
            }
        }

        // The explosion: the owner's hit on every enemy within the blast radius of the spot, then the decoy goes.
        void Explode(Player* owner, ObjectGuid decoy, Position where, Spec spec)
        {
            if (owner->IsAlive() && owner->IsInWorld())
                if (double const pct = spec.blastPct ? spec.blastPct() : 0.0; pct > 0)
                    for (Unit* enemy : Combat::Enemies(owner, spec.spellId, where, spec.blastRadius))
                        if (Within(where.GetExactDist(enemy), spec.blastRadius))
                            Combat::Strike(owner, enemy, spec.spellId, pct, true);
            if (Creature* gone = ObjectAccessor::GetCreature(*owner, decoy))
                gone->DespawnOrUnsummon();
        }
    } // namespace

    bool Place(Player* owner, Position const& where, Spec const& spec)
    {
        if (!owner || !owner->IsInWorld() || !spec.entry || !spec.blastPct ||
            !Built(spec.tauntRadius, spec.delaySeconds, spec.blastRadius))
            return false;
        auto const ms = Millis(spec.delaySeconds);
        TempSummon* decoy = owner->SummonCreature(spec.entry, where, TEMPSUMMON_TIMED_DESPAWN, ms + GraceMs);
        if (!decoy)
            return false;
        Hold(owner, decoy, spec, ms);
        owner->m_Events.AddEventAtOffset([owner, guid = decoy->GetGUID(), where, spec]
                                         { Explode(owner, guid, where, spec); }, std::chrono::milliseconds(ms));
        return true;
    }
} // namespace DC::Combat::TauntDecoy
