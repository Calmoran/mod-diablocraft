/*
 * Iron Skin and its five runes: the skin that takes damage off for a few seconds, and what each rune does with it, when
 * it is hit and when it ends. The dispatch is in dc_crusader.cpp.
 */

#include "dc_crusader_iron_skin.h"
#include "dc_crusader_common.h"
#include "../../combat/dc_item_powers.h"
#include "Random.h"

namespace DC::Combat::Crusader::IronSkin
{
    namespace
    {
        constexpr std::string_view Skill = "Iron Skin";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The seconds the skin lasts: the skill's, or Steel Skin's.
        double Lasts(std::uint32_t spellId)
        {
            return Seconds(RuneAt(spellId), Numbers::Num(spellId, "absorb_duration_seconds"),
                           Numbers::Num(spellId, "duration_seconds"));
        }

        // Explosive Skin: the skin explodes off when nothing holds it any more.
        void Explode(Player* player, std::uint32_t spellId)
        {
            if (!player->IsInWorld() || !player->IsAlive() ||
                !Expired(Buffs::Stacks(player, spellId, Stat::SpecificReduction)))
                return;
            auto const pct = Numbers::Own(spellId, "damage_pct");
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                Combat::Strike(player, enemy, spellId, pct);
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
        return 0.0;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Is(spellId))
            return;
        double const seconds = Lasts(spellId);
        // "absorbing {absorb_pct} of all incoming damage": the sheet's damage reduction, for the skin's seconds.
        Buffs::Stack(player, spellId, Stat::SpecificReduction, Bucket::Flat, Numbers::Num(spellId, "absorb_pct"), 1,
                     seconds);
        switch (RuneAt(spellId))
        {
            case Rune::ReflectiveSkin:
                // "While active, your Thorns is increased by {thorns_pct}."
                Buffs::Stack(player, spellId, Stat::Thorns, Bucket::Percent, Numbers::Num(spellId, "thorns_pct"), 1,
                             seconds);
                break;
            case Rune::ExplosiveSkin:
                // A little after the sheet's own end, so the skin has come off when the check looks.
                player->m_Events.AddEventAtOffset([player, spellId] { Explode(player, spellId); },
                                                  std::chrono::milliseconds(std::uint64_t(seconds * 1000.0) + 2));
                break;
            default:
                break;
        }
    }

    void Taken(Player* victim)
    {
        if (!victim)
            return;
        std::uint32_t const spellId = Slotted(victim, Skill);
        if (!spellId || !Buffs::Stacks(victim, spellId, Stat::SpecificReduction))
            return;
        switch (RuneAt(spellId))
        {
            case Rune::ChargedUp:
                // "a {proc_chance_pct} chance to Stun enemies within {radius_yards} yards for {stun_duration_seconds}
                // seconds."
                if (Procs(rand_chance(), Numbers::Num(spellId, "proc_chance_pct")))
                {
                    double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(victim);
                    for (Unit* enemy :
                         Combat::Enemies(victim, spellId, victim->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                        Stun(victim, enemy, stun);
                }
                break;
            case Rune::Flash:
                // "your movement speed is increased by {movement_speed_pct} for {duration_seconds} seconds."
                Buffs::Stack(victim, spellId, Stat::MovementSpeed, Bucket::Uncapped,
                             Numbers::Num(spellId, "movement_speed_pct"), 1, Numbers::Num(spellId, "duration_seconds"));
                break;
            default:
                break;
        }
    }
} // namespace DC::Combat::Crusader::IronSkin
