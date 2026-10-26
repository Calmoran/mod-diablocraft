/*
 * Spirit Barrage and its five runes. The skill is the engine's single-enemy cast (a record and the sheet's numbers)
 * that hits nothing; here: the bolts that land one after another on the enemy aimed at, Phlebotomize's Life and The
 * Spirit Is Willing's Mana for each, Well of Souls' spirits that seek other enemies, Phantasm's spectres (devices of
 * the shared ground-device piece) and Manitou's spectre that hovers over the Witch Doctor and shoots.
 */

#include "dc_witch_doctor_spirit_barrage.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_mana.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_ground_device.h"
#include "../../combat/dc_spell_numbers.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <chrono>
#include <functional>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::WitchDoctor::SpiritBarrage
{
    namespace
    {
        constexpr std::string_view Skill = "Spirit Barrage";

        std::mutex mutex;
        std::unordered_map<std::uint64_t, unsigned> inTheAir; // by Witch Doctor: barrages whose bolts are still to land
        std::unordered_map<std::uint64_t, std::uint32_t> spectres; // by Witch Doctor: the Manitou now hovering

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        void Later(Player* player, std::uint32_t ms, std::function<void()> work)
        {
            if (!ms)
                work();
            else
                player->m_Events.AddEventAtOffset(std::move(work), std::chrono::milliseconds(ms));
        }

        // One bolt landing on `guid`: its damage, then what a hit returns: Phlebotomize's Life, The Spirit Is Willing's
        // Mana.
        void Land(Player* player, std::uint32_t spellId, ObjectGuid guid, double pct)
        {
            Unit* enemy = ObjectAccessor::GetUnit(*player, guid);
            if (!player->IsAlive() || !player->IsInWorld() || !enemy || !enemy->IsAlive())
                return;
            std::uint32_t const base = BaseId(Skill);
            Rune const rune = RuneAt(spellId);
            if (!Combat::Strike(player, enemy, BoltTakesRuneElement(rune) ? spellId : base, pct))
                return;
            // "Gain {heal_per_hit_life} Life each time Spirit Barrage hits."
            if (rune == Rune::Phlebotomize)
                Heal(player, spellId, LevelLife(Numbers::Num(spellId, "heal_per_hit_life"), player->GetLevel()));
            // "Gain {gain_resource} Mana each time Spirit Barrage hits."
            if (rune == Rune::TheSpiritIsWilling)
                Gain(player, Classes::ClassIdOf(player), spellId, Numbers::Num(spellId, "gain_resource"), 1);
        }

        // Well of Souls: "An additional {projectile_count} spirits seek out other enemies": each at a random enemy of
        // the file's search radius round the enemy the barrage is on.
        void Seek(Player* player, std::uint32_t spellId, ObjectGuid guid)
        {
            Unit* aimed = ObjectAccessor::GetUnit(*player, guid);
            if (!player->IsAlive() || !player->IsInWorld() || !aimed)
                return;
            auto const near =
                Combat::Enemies(player, spellId, aimed->GetPosition(), Tune("spirit_barrage_well_search_yards"));
            std::vector<double> distances;
            for (Unit* enemy : near)
                distances.push_back(enemy->GetExactDist(aimed));
            std::size_t const aimedAt = std::find(near.begin(), near.end(), aimed) - near.begin();
            auto const others =
                Others(distances, aimedAt < near.size() ? aimedAt : none, Tune("spirit_barrage_well_search_yards"));
            if (others.empty())
                return;
            Combat::Strike(player, near[others[urand(0, uint32(others.size() - 1))]], spellId,
                           Numbers::Num(spellId, "damage_pct"));
        }

        // Phantasm: "Summon a spectre that deals {damage_pct} weapon damage as Cold over {dot_duration_seconds} seconds
        // to all enemies within {radius_yards} yards": a device where the enemy stands, hitting every tick.
        void Summon(Player* player, std::uint32_t spellId, Position const& at)
        {
            double const seconds = Numbers::Num(spellId, "dot_duration_seconds"),
                         tick = Tune("spirit_barrage_phantasm_tick_seconds");
            double const pct =
                PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), PeriodicStrike::Ticks(seconds, tick));
            GroundDevice::Setup spectre;
            spectre.kind = BaseId(Skill);
            spectre.record = spellId;
            spectre.spec.mode = GroundDevice::Mode::Periodic;
            spectre.spec.radiusYards = Numbers::Num(spellId, "radius_yards");
            spectre.spec.lifetimeMs = seconds * 1000.0;
            spectre.spec.intervalMs = tick * 1000.0;
            spectre.spec.most = std::size_t(Numbers::Num(spellId, "max_count"));
            spectre.fire = [spellId, pct](Player* owner, Position const&, std::vector<Unit*> const& enemies)
            {
                for (Unit* enemy : enemies)
                    Combat::Strike(owner, enemy, spellId, pct);
            };
            GroundDevice::Place(player, spectre, at);
        }

        // Manitou: "Summon a spectre that hovers over you, unleashing spirit bolts at nearby enemies for {damage_pct}
        // weapon damage as Cold over {dot_duration_seconds} seconds": a bolt every tick at a random enemy within the
        // file's search radius of the Witch Doctor, until the time is over or a later Manitou takes its place.
        void Hover(Player* player, std::uint32_t spellId, std::uint32_t serial, unsigned left, double pct)
        {
            if (!left || !player->IsAlive() || !player->IsInWorld())
                return;
            {
                std::lock_guard<std::mutex> guard(mutex);
                if (spectres[player->GetGUID().GetRawValue()] != serial)
                    return;
            }
            auto const enemies =
                Combat::Enemies(player, spellId, player->GetPosition(), Tune("spirit_barrage_manitou_search_yards"));
            if (!enemies.empty())
                Combat::Strike(player, enemies[urand(0, uint32(enemies.size() - 1))], spellId, pct);
            Later(player, std::uint32_t(Tune("spirit_barrage_manitou_tick_seconds") * 1000.0 + 0.5),
                  [player, spellId, serial, left, pct] { Hover(player, spellId, serial, left - 1, pct); });
        }

        // A Witch Doctor who logs out mid-barrage never sees the last bolt land (the player's events go with the session), so the
        // barrages counted in the air and the Manitou on record are cleared with the logout; the next login starts empty.
        class Logouts final : public PlayerScript
        {
        public:
            Logouts() : PlayerScript("dc_witch_doctor_spirit_barrage", {PLAYERHOOK_ON_LOGOUT}) { }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> guard(mutex);
                inTheAir.erase(player->GetGUID().GetRawValue());
                spectres.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Logouts();
    }

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Is(spellId) || targets.empty())
            return;
        Rune const rune = RuneAt(spellId);
        std::uint32_t const base = BaseId(Skill);
        Unit* target = targets.front();
        ObjectGuid const guid = target->GetGUID();
        std::uint64_t const owner = player->GetGUID().GetRawValue();

        // "MAX Active Barrages": the bolts go only while fewer than the file's most are in the air.
        {
            std::lock_guard<std::mutex> guard(mutex);
            if (!MayBombard(inTheAir[owner], unsigned(Tune("spirit_barrage_max_active"))))
                return;
            ++inTheAir[owner];
        }
        unsigned const count = unsigned(Numbers::Num(base, "projectile_count"));
        double const pct = BoltPct(Numbers::Num(base, "damage_pct"), count);
        double const hit = Tune("spirit_barrage_hit_delay_seconds"), gap = Tune("spirit_barrage_bolt_gap_seconds"),
                     delta = Tune("spirit_barrage_bolt_gap_delta_seconds");
        for (unsigned bolt = 0; bolt < count; ++bolt)
        {
            bool const last = bolt + 1 == count;
            Later(player, BoltLandsMs(bolt, hit, gap, delta),
                  [player, spellId, guid, pct, last, owner]
                  {
                      Land(player, spellId, guid, pct);
                      if (last)
                      {
                          std::lock_guard<std::mutex> guard(mutex);
                          if (inTheAir[owner])
                              --inTheAir[owner];
                      }
                  });
        }

        switch (rune)
        {
            case Rune::WellOfSouls:
            {
                // The spirits fly from the barrage's first hit, one every fire rate while the buff lasts.
                unsigned const spirits = WellSpirits(unsigned(Numbers::Num(spellId, "projectile_count")),
                                                     Tune("spirit_barrage_well_duration_seconds"),
                                                     Tune("spirit_barrage_well_fire_rate_seconds"));
                for (unsigned spirit = 0; spirit < spirits; ++spirit)
                    Later(player,
                          BoltLandsMs(0, hit, gap, delta) +
                              WellFliesMs(spirit, Tune("spirit_barrage_well_fire_rate_seconds")),
                          [player, spellId, guid] { Seek(player, spellId, guid); });
                break;
            }
            case Rune::Phantasm:
                Summon(player, spellId, target->GetPosition());
                break;
            case Rune::Manitou:
            {
                double const seconds = Numbers::Num(spellId, "dot_duration_seconds"),
                             tick = Tune("spirit_barrage_manitou_tick_seconds");
                unsigned const bolts = PeriodicStrike::Ticks(seconds, tick);
                std::uint32_t serial;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    serial = ++spectres[owner];
                }
                double const each = SpectreBoltPct(Numbers::Num(spellId, "damage_pct"), seconds, tick);
                Later(player, std::uint32_t(tick * 1000.0 + 0.5),
                      [player, spellId, serial, bolts, each] { Hover(player, spellId, serial, bolts, each); });
                break;
            }
            default:
                break;
        }
    }
} // namespace DC::Combat::WitchDoctor::SpiritBarrage
