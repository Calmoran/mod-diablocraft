/*
 * Wave of Light. The sheets: monk_skills.csv, monk_runes.csv, monk_skill_values.csv; the geometry is
 * Power/Monk_WaveOfLight.pow. The cast resolves to no enemy of its own (the record's ground cursor has no damage
 * radius), so every hit is struck from here at the ground point the cast aimed at.
 */

#include "dc_monk_wave_of_light.h"
#include "dc_monk_wave_of_light_cast.h"
#include "dc_monk_common.h"
#include "../../combat/dc_item_powers.h"

namespace DC::Combat::Monk::WaveOfLight
{
    namespace
    {
        constexpr std::string_view Skill = "Wave of Light";
        // Stock "Ice Blast": one instant MOD_STUN effect, mechanic STUN (the hold Fists of Thunder's Wind Blast uses).
        constexpr std::uint32_t StunHold = 15878;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        std::uint32_t BaseId()
        {
            for (auto const& ability : Shells::Abilities)
                if (Skill == ability.skill && !*ability.rune)
                    return ability.id;
            return 0;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        Point PointOf(Position const& position)
        {
            return {position.GetPositionX(), position.GetPositionY()};
        }

        Position At(Point point, float z)
        {
            return Position(float(point.x), float(point.y), z);
        }

        void Stun(Player* player, Unit* target, double seconds)
        {
            if (seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(StunHold, player->GetGUID());
            if (Aura* hold = player->AddAura(StunHold, target))
            {
                hold->SetMaxDuration(int32(seconds * 1000));
                hold->SetDuration(int32(seconds * 1000));
            }
        }

        // The ticks of a damage that is spread over time (Pillar of the Ancients' damage over time, the bell's three
        // ticks): every tick strikes the enemies who are in the area then ("to enemies who remain in the area"), each
        // for an equal share of the total. `periodic` is a damage-over-time tick (average critical hit); the bell's
        // are ordinary hits. `gapMs` is the time to the next tick.
        void Pulse(Player* player, std::uint32_t spellId, Position where, double radius, double pct, unsigned remaining,
                   bool periodic, std::uint64_t gapMs)
        {
            if (!remaining || !player->IsAlive())
                return;
            for (Unit* enemy : Combat::Enemies(player, spellId, where, radius))
                Combat::Strike(player, enemy, spellId, pct, periodic);
            if (remaining > 1)
                player->m_Events.AddEventAtOffset(
                    [player, spellId, where, radius, pct, remaining, periodic, gapMs]
                    { Pulse(player, spellId, where, radius, pct, remaining - 1, periodic, gapMs); },
                    Milliseconds(gapMs));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, Position const& aimed)
    {
        auto const* row = Row(spellId);
        if (!player || !row)
            return;
        std::string_view const rune = row->rune;
        Point const monk = PointOf(player->GetPosition());
        double const heading = Heading(monk, PointOf(aimed), player->GetOrientation());
        float const z = player->GetPositionZ();
        std::vector<Unit*> struck;
        // Tzo Krin's Gaze (N-CASTAT): "Wave of Light is now cast at your enemy": the bell and the pillar
        // fall where the cast was aimed, not ahead of (or on) the Monk. Asked before any lock, as every item-power reader.
        bool const atEnemy = ItemPowers::SkillSetTo(player, std::string(Skill), "cast_at_enemy", 0) > 0;

        if (rune == "Pillar of the Ancients")
        {
            // "Summon an ancient pillar that deals {damage_pct:hit} weapon damage ..., followed by {damage_pct:dot}
            // weapon damage over {dot_duration_seconds} seconds to enemies who remain in the area": SF_28 ahead,
            // SF_13/26/35 wide.
            Position const where =
                atEnemy ? Position(aimed) : At(Ahead(monk, heading, Tune("wave_of_light_pillar_offset_yards")), z);
            double const radius = Tune("wave_of_light_pillar_radius_yards");
            for (Unit* enemy : Combat::Enemies(player, spellId, where, radius))
                if (Combat::Strike(player, enemy, spellId, Numbers::Own(spellId, "damage_pct", "hit")))
                    struck.push_back(enemy);
            unsigned const ticks =
                Ticks(Numbers::Num(spellId, "dot_duration_seconds"), Tune("wave_of_light_pillar_tick_seconds"));
            std::uint64_t const gap = std::uint64_t(Tune("wave_of_light_pillar_tick_seconds") * 1000.0 + 0.5);
            if (ticks)
                player->m_Events.AddEventAtOffset(
                    [player, spellId, where, radius, pct = TickPct(Numbers::Num(spellId, "damage_pct", "dot"), ticks),
                     ticks, gap] { Pulse(player, spellId, where, radius, pct, ticks, true, gap); },
                    Milliseconds(gap));
        }
        else if (DC::Tunables::Has("monk", "wave_of_light_bell_radius_yards"))
        {
            // The bell: SF_8 ahead of the Monk, on the Monk itself for Explosive Light (SF_8 is 0 for rune B). The
            // sheet's base number is the skill's, Explosive Light's and Empowered Wave's their own.
            bool const explosive = rune == "Explosive Light";
            Position const where = atEnemy     ? Position(aimed)
                                   : explosive ? At(monk, z)
                                               : At(Ahead(monk, heading, Tune("wave_of_light_bell_offset_yards")), z);
            auto const pct = explosive || rune == "Empowered Wave" ? Numbers::Own(spellId, "damage_pct")
                                                                   : Numbers::Get(BaseId(), "damage_pct");
            // "Bell Damage Num Ticks" 3 (SF_11) over "Bell Damage Duration" 1 / attacks per second (SF_10): the sheet's
            // number is the total of the ticks, the first at once. Explosive Light is one burst.
            double const radius = Tune("wave_of_light_bell_radius_yards");
            unsigned const ticks = explosive ? 1 : std::max(1u, unsigned(Tune("wave_of_light_bell_ticks")));
            double const share = TickPct(pct.value_or(0), ticks);
            for (Unit* enemy : Combat::Enemies(player, spellId, where, radius))
                if (Combat::Strike(player, enemy, spellId, share))
                    struck.push_back(enemy);
            if (ticks > 1)
            {
                std::uint64_t const gap = TickGapMs(Combat::AttacksPerSecond(player, spellId), ticks);
                player->m_Events.AddEventAtOffset(
                    [player, spellId, where, radius, share, ticks, gap]
                    { Pulse(player, spellId, where, radius, share, ticks - 1, false, gap); },
                    Milliseconds(gap));
            }
            if (rune == "Wall of Light")
                for (Unit* enemy : struck)
                    Stun(player, enemy, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
        }

        if (rune == "Shattering Light" && DC::Tunables::Has("monk", "wave_of_light_line_width_yards"))
        {
            // "Wave of Light deals an additional {damage_pct} weapon damage as Cold in a line."
            double const start = Tune("wave_of_light_line_start_yards"), end = Tune("wave_of_light_line_end_yards"),
                         width = Tune("wave_of_light_line_width_yards");
            for (Unit* enemy : Combat::Enemies(player, spellId, player->GetPosition(), end))
                if (InLine(monk, heading, start, end, width, PointOf(enemy->GetPosition())))
                    if (Combat::Strike(player, enemy, spellId, Numbers::Own(spellId, "damage_pct")))
                        struck.push_back(enemy);
        }

        // One attack, however many enemies: the existing once-per-cast bookkeeping (Life per Hit, item powers).
        if (!struck.empty())
            Combat::Connected(player, spellId, unsigned(struck.size()));
    }
} // namespace DC::Combat::Monk::WaveOfLight
