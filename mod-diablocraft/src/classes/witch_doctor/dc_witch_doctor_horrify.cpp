/*
 * Horrify and its five runes: the mask that frightens and holds still every enemy around the Witch Doctor, and what
 * each rune adds. The dispatch is in dc_witch_doctor.cpp.
 */

#include "dc_witch_doctor_horrify.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_mana.h"
#include "dc_witch_doctor_sheet_buffs.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_damage_buckets.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"

namespace DC::Combat::WitchDoctor::Horrify
{
    namespace
    {
        constexpr std::string_view Skill = "Horrify";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        // The circle is the rune's own: Face of Death states its 24 yards, every other record the skill's 18.
        double const fear = Numbers::Num(spellId, "fear_duration_seconds");
        unsigned horrified = 0;
        for (Unit* enemy : Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
            if (Fear(player, enemy, fear))
            {
                ++horrified;
                if (Immobilizes(rune))
                    Root(player, enemy, fear);
            }

        switch (rune)
        {
            case Rune::FrighteningAspect:
                // "Gain {armor_pct} additional Armor for {duration_seconds} seconds after casting Horrify."
                SheetBuffs::Stack(player, spellId, Stat::Armor, Bucket::Percent, Numbers::Num(spellId, "armor_pct"), 1,
                                 Numbers::Num(spellId, "duration_seconds"));
                break;
            case Rune::Stalker:
                // "Increase movement speed by {movement_speed_pct} for {duration_seconds} seconds after casting
                // Horrify."
                SheetBuffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped,
                                 Numbers::Num(spellId, "movement_speed_pct"), 1,
                                 Numbers::Num(spellId, "duration_seconds"));
                break;
            case Rune::RuthlessTerror:
                // "Gain {gain_resource} Mana for every horrified enemy."
                Gain(player, Classes::ClassIdOf(player), spellId, Numbers::Num(spellId, "gain_resource"), horrified);
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::WitchDoctor::Horrify
