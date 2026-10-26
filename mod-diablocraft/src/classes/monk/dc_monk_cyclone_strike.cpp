/*
 * Cyclone Strike. The sheets: monk_skills.csv, monk_runes.csv, monk_skill_values.csv; the pull's landing and
 * the blast's radius are Power/Monk_CycloneStrike.pow. The record is a self_aoe of the pull radius (24), so the cast
 * would hit everything within 24 yards at the skill's damage; Aim replaces that list with the enemies the blast reaches
 * once the pull is done.
 */

#include "dc_monk_cyclone_strike.h"
#include "../dc_level_heal.h"
#include "dc_monk_cyclone_strike_cast.h"
#include "dc_monk_common.h"
#include "Group.h"
#include "GroupReference.h"
#include "SpellMgr.h"
#include "Util.h"

namespace DC::Combat::Monk::CycloneStrike
{
    namespace
    {
        constexpr std::string_view Skill = "Cyclone Strike";
        // Stock "Ice Blast": one instant MOD_STUN effect, mechanic STUN (the hold Wind Blast freezes with).
        constexpr std::uint32_t FreezeHold = 15878;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        Point PointOf(Position const& position)
        {
            return {position.GetPositionX(), position.GetPositionY()};
        }

        void Freeze(Player* player, Unit* target, double seconds)
        {
            if (seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(FreezeHold, player->GetGUID());
            if (Aura* hold = player->AddAura(FreezeHold, target))
            {
                hold->SetMaxDuration(int32(seconds * 1000));
                hold->SetDuration(int32(seconds * 1000));
            }
        }

        void Heal(Player* player, Unit* target, std::uint32_t spellId, double amount)
        {
            auto const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info || !target || !target->IsAlive() || amount <= 0)
                return;
            HealInfo heal(player, target, uint32(std::min(amount, double(UINT32_MAX))), info,
                          SPELL_SCHOOL_MASK_HOLY);
            player->HealBySpell(heal);
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*>& targets)
    {
        auto const* row = Row(spellId);
        if (!player || !row)
            return;
        // "Pull up to {target_count} enemies within {radius_yards} yards towards you": the nearest, the radius the
        // rune's (Implosion 34). The cast's own list is only the record's 24.
        Point const monk = PointOf(player->GetPosition());
        std::vector<Unit*> found =
            Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards"));
        std::vector<double> distances;
        for (Unit* enemy : found)
            distances.push_back(player->GetExactDist(enemy));
        std::vector<Unit*> pulled;
        for (std::size_t index : Nearest(distances, unsigned(Numbers::Num(spellId, "target_count"))))
            pulled.push_back(found[index]);

        for (Unit* enemy : pulled)
        {
            // Each lands between SF_0 and SF_0 + SF_6 yards from the Monk, on the line it came along. Moved at once
            // (the power's staggered flight, SF_7/SF_8, is not built), so the blast below finds it in place.
            Point const land = Landing(monk, PointOf(enemy->GetPosition()),
                                       LandingYards(Tune("cyclone_strike_pull_land_min_yards"),
                                                    Tune("cyclone_strike_pull_land_spread_yards"), frand(0.0f, 1.0f)));
            float z = player->GetPositionZ();
            enemy->UpdateGroundPositionZ(float(land.x), float(land.y), z);
            enemy->NearTeleportTo(float(land.x), float(land.y), z, enemy->GetOrientation());
        }
        if (row->rune == std::string_view("Wall of Wind"))
            for (Unit* enemy : pulled)
                Freeze(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds"));

        // The blast: SF_3 around the Monk, on whoever is there now, the pulled included.
        double const radius = Tune("cyclone_strike_blast_radius_yards");
        std::vector<Unit*> blast = Combat::Enemies(player, spellId, player->GetPosition(), radius);
        for (Unit* enemy : pulled)
            if (enemy->IsAlive() && InBlast(monk, radius, PointOf(enemy->GetPosition())) &&
                std::find(blast.begin(), blast.end(), enemy) == blast.end())
                blast.push_back(enemy);
        targets = std::move(blast);
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        auto const* row = Row(spellId);
        if (!player || !row || row->rune != std::string_view("Soothing Breeze"))
            return;
        // "Cyclone Strike heals you and all allies within {radius_yards} yards for {heal_life} Life." The Health Globe
        // Healing Bonus share (healing_bonus_share_pct) waits on health globes, which the game does not have yet.
        double const radius = Numbers::Num(spellId, "radius_yards"), amount = Classes::HealAtLevel(Numbers::Num(spellId, "heal_life"), player->GetLevel());
        Heal(player, player, spellId, amount);
        if (Group* group = player->GetGroup())
            for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                if (Player* member = ref->GetSource();
                    member && member != player && player->IsWithinDistInMap(member, radius))
                    Heal(player, member, spellId, amount);
    }
} // namespace DC::Combat::Monk::CycloneStrike
