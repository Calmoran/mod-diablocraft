/*
 * Revive and its five runes. The cast takes up to ten of the Necromancer's corpses within 20 yards of the point aimed
 * at, nearest first, and each rises as a minion wearing the look of the creature that died there
 * (dc_necromancer_pets.cpp). The runes: Oblation costs Life, Personal Army cuts the damage the Necromancer takes for
 * each minion standing, Horrific Return frightens the enemies around each corpse revived.
 */

#include "dc_necromancer_revive.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_pets.h"
#include "dc_necromancer_revive_math.h"
#include "../../combat/dc_corpses.h"
#include "../../combat/dc_minions.h"

#include "ObjectMgr.h"

namespace DC::Combat::Necromancer::CorpseRevive
{
    namespace
    {
        constexpr std::string_view Skill = "Revive";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // "reviving up to {target_count} corpses within {radius_yards} yards".
        float Reach(std::uint32_t spellId)
        {
            return float(Numbers::Num(spellId, "radius_yards"));
        }

        // The look of the creature that died: its first model; 0 (the template's own) for a corpse a skill made.
        std::uint32_t LookOf(std::uint32_t entry)
        {
            if (!entry)
                return 0;
            CreatureTemplate const* info = sObjectMgr->GetCreatureTemplate(entry);
            CreatureModel const* model = info ? info->GetFirstValidModel() : nullptr;
            return model ? model->CreatureDisplayID : 0;
        }
    } // namespace

    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Position const* aim)
    {
        if (!player || !RowOf(spellId, Skill))
            return SPELL_CAST_OK;
        Position const centre = aim ? *aim : player->GetPosition();
        return CanRevive(Corpses::Count(player, centre, Reach(spellId))) ? SPELL_CAST_OK
                                                                         : SPELL_FAILED_NO_VALID_TARGETS;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        auto const taken = Corpses::Consume(
            player, center, Reach(spellId),
            Revived(Corpses::Count(player, center, Reach(spellId)), Numbers::Num(spellId, "target_count")));
        // "each Revive now costs 3% health": the power's Health Cost Per Target, for each corpse revived.
        if (RuneAt(spellId) == Rune::Oblation)
            SpendLife(player, LifeCostPct(Tune("revive_oblation_life_cost_pct"), taken.size()));
        for (Corpses::Spot const& spot : taken)
        {
            Position const where(spot.x, spot.y, spot.z);
            Pets::Revive(player, where, LookOf(spot.entry), spellId, spot.entry);
            if (RuneAt(spellId) == Rune::HorrificReturn)
                // "When you revive a corpse, enemies within {radius_yards} yards run in fear for
                // {fear_duration_seconds} seconds."
                for (Unit* enemy : Combat::Enemies(player, spellId, where, Numbers::Num(spellId, "radius_yards")))
                    Fear(player, enemy, Numbers::Num(spellId, "fear_duration_seconds"));
        }
    }

    double Reduce(Unit* victim, double damage)
    {
        Player* player = victim ? victim->ToPlayer() : nullptr;
        if (!player || damage <= 0)
            return damage;
        std::uint32_t const slotted = Slotted(player, Skill);
        if (!slotted || RuneAt(slotted) != Rune::PersonalArmy)
            return damage;
        // "Damage taken is reduced by {damage_reduction_pct} for each revived minion active."
        return damage * TakenFactor(Numbers::Num(slotted, "damage_reduction_pct"), Minions::Alive(player, "revived"));
    }
} // namespace DC::Combat::Necromancer::CorpseRevive
