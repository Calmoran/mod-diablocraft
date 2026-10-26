/*
 * Spirit Walk and its five runes: the walk in the spirit realm (unhindered, faster), the body left behind that Umbral
 * Shock erupts, the Mana and Life the other runes return, and the cooldown that starts after the walk. The dispatch is
 * in dc_witch_doctor.cpp.
 */

#include "dc_witch_doctor_spirit_walk.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_mana.h"
#include "dc_witch_doctor_sheet_buffs.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_control_immunity.h"
#include "../../combat/dc_damage_buckets.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"

#include <chrono>

namespace DC::Combat::WitchDoctor::SpiritWalk
{
    namespace
    {
        constexpr std::string_view Skill = "Spirit Walk";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The creature of witch_doctor_body_summons.csv.
        constexpr std::uint32_t BodyEntry = 900175;
        // The body stands for the walk's seconds; set by Cast, which asks for the kind at once.
        struct WalkCast
        {
            double seconds = 0;
        } walkCast;

        // The body Spirit Walk leaves behind: a copy of the Witch Doctor (its model and gear) with the power file's share of its Life
        // ('Dummy Health'), standing where the walk began until it ends. It follows no one and strikes no one.
        Minions::Kind Body(Player*)
        {
            Minions::Kind kind;
            kind.group = "spirit_walk_body";
            kind.entry = BodyEntry;
            kind.record = BaseId(Skill);
            kind.lifeMs = std::uint32_t(walkCast.seconds * 1000.0 + 0.5);
            kind.lifeToCopyPct = Tune("spirit_walk_body_life_pct");
            kind.cap = 1;
            kind.staysPut = true;
            return kind;
        }

        // Umbral Shock: "your physical body erupts for {damage_pct} weapon damage as Fire to all enemies within
        // {radius_yards} yards" where the body was left.
        void Erupt(Player* player, std::uint32_t spellId, Position const& body)
        {
            if (!player->IsInWorld() || !player->IsAlive())
                return;
            for (Unit* enemy : Enemies(player, spellId, body, Numbers::Num(spellId, "radius_yards")))
                Strike(player, enemy, spellId, Numbers::Own(spellId, "damage_pct"));
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
        double const seconds = Numbers::Num(spellId, "duration_seconds");
        auto const ms = std::chrono::milliseconds(CooldownDelayMs(seconds));

        // "Leave your physical body": the body stands where the walk began, and a second walk takes the first one's place.
        walkCast.seconds = seconds;
        Minions::Raise(player, "spirit_walk_body", player->GetPosition(), 0, true);
        walkCast = {};

        // "While in the spirit realm, your movement is unhindered": immune to every control impairing effect, the slows
        // included, for the walk.
        ControlImmunity::Set(player, spellId, true);
        // "enter the spirit realm": nothing in the world can hurt the Witch Doctor for the walk (an absorb of everything).
        Invulnerable(player, seconds);
        player->m_Events.AddEventAtOffset([player, spellId] { ControlImmunity::Set(player, spellId, false); }, ms);

        // The power file's 'Run Speed Increase' for every walk, and Severance's additional movement speed on top.
        SheetBuffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped,
                          RunSpeedPct(rune, Tune("spirit_walk_run_speed_pct"), Numbers::Own(spellId, "movement_speed_pct").value_or(0.0)),
                          1, seconds);

        switch (rune)
        {
            case Rune::UmbralShock:
                player->m_Events.AddEventAtOffset([player, spellId, body = player->GetPosition()]
                                                  { Erupt(player, spellId, body); }, ms);
                break;
            case Rune::HonoredGuest:
                Gain(player, Classes::ClassIdOf(player), spellId,
                     ShareOf(Resources::Max(player, Resources::Mana), Numbers::Num(spellId, "gain_pct")), 1);
                break;
            case Rune::HealingJourney:
                Heal(player, spellId, ShareOf(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct")));
                break;
            default:
                break;
        }

        // The cooldown the core just installed is pushed back by the walk, on every rune (they share it).
        for (auto const& ability : Shells::Abilities)
            if (Skill == ability.skill && player->GetSpellCooldownDelay(ability.id))
                player->ModifySpellCooldown(ability.id, int32(CooldownDelayMs(seconds)));
    }

    void Register()
    {
        Minions::Define("spirit_walk_body", Body);
    }
} // namespace DC::Combat::WitchDoctor::SpiritWalk
