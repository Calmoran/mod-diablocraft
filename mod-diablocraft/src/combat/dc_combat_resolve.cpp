// Combat: a cast's targets and hits, the Rend bleeds, the Wizard's ground effects and channels, and the skill spell script.
#include "dc_combat_internal.h"
#include "dc_proc_math.h"
#include "dc_ground_missile_math.h"

namespace DC::Combat
{
    namespace
    {
        bool ValidTarget(Player* player, Unit* target, SpellInfo const* info, bool friendly)
        {
            if (!target || !target->IsAlive() || !target->IsInWorld() || !player->IsInMap(target) ||
                !player->InSamePhase(target) || !player->IsWithinLOSInMap(target) ||
                info->CheckTarget(player, target) != SPELL_CAST_OK)
                return false;
            return friendly ? player->IsValidAssistTarget(target)
                            : player->IsValidAttackTarget(target) && !target->IsImmunedToDamage(player, info);
        }

        // One area search for self, allies, destinations, landing and splash.
        struct AreaTargets
        {
            Player* player = nullptr;
            SpellInfo const* info = nullptr;
            Position center;
            float radius = 0.0f;
            bool friendly = false;
            bool operator()(Unit* unit) const
            {
                return center.GetExactDist(unit) <= radius && ValidTarget(player, unit, info, friendly);
            }
        };

        std::vector<Unit*> AreaList(Player* player, SpellInfo const* info, Position const& center, float radius,
                                    bool friendly = false)
        {
            std::list<Unit*> found;
            AreaTargets check{player, info, center, radius, friendly};
            Acore::UnitListSearcher<AreaTargets> searcher(player, found, check);
            Cell::VisitObjects(center.GetPositionX(), center.GetPositionY(), player->GetMap(), searcher, radius);
            if (friendly && check(player))
                found.push_back(player);
            std::unordered_set<uint64> seen;
            std::vector<Unit*> out;
            for (Unit* unit : found)
                if (seen.insert(unit->GetGUID().GetRawValue()).second)
                    out.push_back(unit);
            return out;
        }

        // The enemies in the cone of a cast, searched from where the caster stands now, facing the way it faces now: the
        // core's own cone (Spell::SelectImplicitConeTargets: 60 degrees, the table's or the 24/54/104 target's) for a cast
        // whose caster moved after the core had chosen.
        std::vector<ObjectGuid> ConeFrom(Player* player, SpellInfo const* info, float radius)
        {
            float angle = G3D::toRadians(60.0f);
            if (SpellCone const* cone = sSpellMgr->GetSpellCone(info->Id))
                angle = G3D::toRadians(static_cast<float>(cone->cone_degrees));
            else
                switch (info->Effects[EFFECT_0].TargetA.GetTarget())
                {
                    case TARGET_UNIT_CONE_ENEMY_24:
                        angle = G3D::toRadians(24.0f);
                        break;
                    case TARGET_UNIT_CONE_ENEMY_54:
                        angle = G3D::toRadians(54.0f);
                        break;
                    case TARGET_UNIT_CONE_ENEMY_104:
                        angle = G3D::toRadians(104.0f);
                        break;
                    default:
                        break;
                }
            std::list<Unit*> found;
            Acore::WorldObjectSpellConeTargetCheck check(angle, radius, player, info, TARGET_CHECK_ENEMY, nullptr);
            Acore::UnitListSearcher<Acore::WorldObjectSpellConeTargetCheck> searcher(player, found, check);
            Cell::VisitObjects(player->GetPositionX(), player->GetPositionY(), player->GetMap(), searcher, radius);
            std::vector<ObjectGuid> out;
            for (Unit* unit : found)
                out.push_back(unit->GetGUID());
            return out;
        }

        bool LineGeometry(Spell* spell, Targeting const& row, Position& origin, float& direction, float& length,
                          float& width)
        {
            // Spell::GetCaster() is a WorldObject since upstream fe6913668; the line hook only fires for units
            Unit* caster = spell->GetCaster()->ToUnit();
            if (!caster)
                return false;
            origin = caster->GetPosition();
            Position end;
            if (row.type == "line_to_point")
            {
                if (!spell->m_targets.HasDst())
                    return false;
                end = *spell->m_targets.GetDstPos();
                length = std::min(row.range, origin.GetExactDist2d(end));
            }
            else
            {
                Unit* aim = spell->m_targets.GetUnitTarget();
                if (!aim)
                    return false;
                end = aim->GetPosition();
                length = row.range;
            }
            direction = origin.GetAbsoluteAngle(&end);
            width = row.width; // full width, never the cone length/radius
            return length > 0 && width > 0;
        }

        std::vector<Unit*> ResolveTargets(Player* player, SpellInfo const* info, Targeting const& row,
                                          Position const& center, std::vector<ObjectGuid> const& native,
                                          Unit* explicitTarget)
        {
            if (row.type == "self" || row.type == "self_summon")
                return {player};
            if (row.type == "self_allies")
                return AreaList(player, info, player->GetPosition(), row.radius, true);
            if (row.type == "single_enemy")
            {
                bool const inRange =
                    explicitTarget && (row.rangeKind == "MELEE" ? player->IsWithinMeleeRange(explicitTarget)
                                                                : player->GetExactDist(explicitTarget) <= row.range);
                if (!inRange || !ValidTarget(player, explicitTarget, info, false))
                    return {};
                // Electrocute's jumps: the enemies the bolt jumped to after it, in order (dc_ability_targets::Chain);
                // each is a hit of its own.
                std::vector<Unit*> out{explicitTarget};
                for (ObjectGuid guid : native)
                    if (Unit* unit = ObjectAccessor::GetUnit(*player, guid); unit && ValidTarget(player, unit, info, false))
                        out.push_back(unit);
                return out;
            }
            if (row.type == "cone_enemies" || row.Line())
            {
                // Native cone selection / approved 0011 owns angle and line geometry.
                std::vector<Unit*> out;
                std::unordered_set<uint64> seen;
                for (ObjectGuid guid : native)
                    if (Unit* unit = ObjectAccessor::GetUnit(*player, guid))
                        if (seen.insert(guid.GetRawValue()).second && ValidTarget(player, unit, info, false) &&
                            (row.Line() || center.GetExactDist(unit) <= row.radius))
                            out.push_back(unit);
                return out;
            }
            return AreaList(player, info, center, row.radius);
        }

        bool ResolveHit(Player* player, Unit* target, Shell const& shell, SpellInfo const* info)
        {
            Hit hit;
            std::string error;
            if (!CastShell(player, target, shell.spellId, hit, error))
                return false;
            if(auto original=FindShell(shell.spellId);original&&original->damagePct>0&&shell.damagePct!=original->damagePct) {hit.total*=shell.damagePct/original->damagePct;hit.areaDamage*=shell.damagePct/original->damagePct;hit.skill=shell.damagePct/100;}
            LOG_DEBUG("module.dc.combat", "[DC target] spell={} unit={}", shell.spellId, target->GetGUID().ToString());
            // Friendly/summon types resolve recipients, never damage those recipients.
            if (shell.targeting.Friendly())
                return false;
            if (auto own = Abilities::Resolve(player, target, shell.spellId, shell.skill, shell.rune))
                return *own;
            if (Wizard::Afflict(player, target, shell.spellId))
                return true;
            DealHit(player, target, shell.spellId, hit);
            if (hit.total > 0)
            {
                GainPerEnemyHit(player, shell.spellId);
                Wizard::Landed(player, target, shell.spellId, hit, false);
                Monk::Landed(player, target, shell.spellId);
                Crusader::Landed(player, target, shell.spellId);
                Necromancer::Landed(player, target, shell.spellId);
                DemonHunter::Landed(player, target, shell.spellId, hit.critical);
                WitchDoctor::Landed(player, target, shell.spellId);
                Shaman::Landed(player, target, shell.spellId, hit.critical);
                WitchDoctor::Pets::Landed(player, target, shell.spellId);
                // A hit that deals nothing procs nothing: the gems', the item powers' and the passives' on-hit effects wait for damage.
                Passives::Hit(player,target,shell.spellId,hit.school);
            }
            Abilities::HitEffects(player,target,shell.spellId);
            if (hit.critical && hit.total>0) Abilities::CriticalHit(player,target,shell.spellId,hit.total);
            if (hit.critical && hit.total>0) Monk::Critical(player, shell.spellId);
            if (hit.areaDamage > 0)
            {
                Hit splash = hit;
                splash.total = hit.areaDamage;
                splash.areaDamage = 0;
                // damage_formula.csv step 11: 10 yards, never chain or pay LoH.
                for (Unit* nearby : AreaList(player, info, target->GetPosition(), 10.0f))
                    if (nearby != target)
                        DealHit(player, nearby, shell.spellId, splash);
            }
            return hit.total > 0;
        }

        // --- the Wizard's ground damage over time --------------------
        // Blizzard and Meteor's molten ground run on the stock carrier
        // (stock first): the record is a
        // persistent area aura at the cast point (Spell::EffectPersistentAA,
        // SpellEffects.cpp:1853) whose dynamic object applies it to every
        // enemy inside its radius (DynObjAura::FillTargetMap,
        // SpellAuras.cpp:2901) and whose PERIODIC_DUMMY effect ticks each of
        // them (AuraEffect::Update, SpellAuraEffects.cpp:926-951) through the
        // AuraScript periodic hook - the shape Rend's bleed uses above. The
        // period is the sheet's interval_seconds and the life its
        // dot_duration_seconds, so the stock tick count is D3's (6 s / 0.25 s
        // = 24 for Blizzard, 3 s / 1 s = 3 for the molten ground; d3planner
        // simulator/wizard.js:744-756 and :678-694 at the pin). One deviation:
        // D3's first tick lands at once (tickinitial: 1) and the stock one a
        // period later, so the last lands at the end of the life instead.
        // Each tick is damage_pct / ticks with average crit (02 C11) and pays
        // no Life per Hit. Meteor's impact (damage_pct:impact) is one ordinary
        // hit on everything in the radius when the cast resolves.
        std::optional<double> GroundTotal(std::uint32_t id)
        {
            for (char const* qualifier : {"mist", "molten", "dot", ""})
                if (auto value = Numbers::Get(id, "damage_pct", qualifier))
                    return value;
            return std::nullopt;
        }

        // Meteor - Meteor Shower is seven spread meteors with a ground each
        // (wizard.js:681-682, :718-721). Wizard::Delayed owns every Meteor
        // cast now, so this is only the guard that keeps GroundImpact from
        // ever dealing the Shower as one impact.
        bool WizardGround(Shell const& shell)
        {
            std::uint32_t const id = shell.spellId;
            return shell.targeting.Destination() && Numbers::Has(id, "interval_seconds") &&
                   Numbers::Has(id, "dot_duration_seconds");
        }

        bool GroundBlocked(Shell const& shell)
        {
            return Wizard::LandsApart(shell.skill, shell.rune);
        }

        void GroundImpact(Player* player, Shell const& shell, Position const& center)
        {
            std::uint32_t const id = shell.spellId;
            SpellInfo const* info = sSpellMgr->GetSpellInfo(id);
            auto impact = Numbers::Get(id, "damage_pct", "impact");
            if (!info || !impact || GroundBlocked(shell))
                return;
            bool connected = false;
            for (Unit* target : AreaList(player, info, center, shell.targeting.radius))
            {
                Hit hit;
                if (!ComputeHit(player, target, id, hit, *impact))
                    continue;
                DealHit(player, target, id, hit);
                if (hit.total <= 0)
                    continue;
                connected = true;
                if (hit.critical)
                    Abilities::CriticalHit(player, target, id, hit.total);
            }
            if (connected)
                Connected(player, id);
        }

        class dc_wizard_ground final : public AuraScript
        {
            PrepareAuraScript(dc_wizard_ground);

            void Tick(AuraEffect const* effect)
            {
                PreventDefaultAction();
                Unit* caster = GetCaster();
                Player* player = caster ? caster->ToPlayer() : nullptr;
                Unit* target = GetTarget();
                int32 const ticks = effect->GetTotalTicks();
                // A Meteor's molten ground is a helper record of its own:
                // it deals its skill's numbers.
                std::uint32_t const source = Wizard::GroundSource(GetId());
                auto total = GroundTotal(source);
                if (!player || !player->IsAlive() || !target || !target->IsAlive() || ticks <= 0 || !total)
                    return;
                Hit hit;
                if (ComputeHit(player, target, source, hit, *total / ticks, true))
                {
                    DealHit(player, target, source, hit);
                    if (hit.total > 0)
                        Wizard::Landed(player, target, source, hit, true);
                }
            }

            void Register() override
            {
                OnEffectPeriodic += AuraEffectPeriodicFn(dc_wizard_ground::Tick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
            }
        };

        void ResolveCast(Player* player, Shell const& shell, Position const& launched,
                         std::vector<ObjectGuid> const& native = {}, Unit* explicitTarget = nullptr,
                         Position const* origin = nullptr)
        {
            Position center = launched;
            SpellInfo const* info = sSpellMgr->GetSpellInfo(shell.spellId);
            if (!info || !player->IsAlive())
                return;
            if (Abilities::LaunchesNoHit(shell.skill))
            {
                // No launch damage: the zone distributes this cast's total over its CSV life.
                Abilities::Cast(player, shell.spellId, {}, &center);
                return;
            }
            // Meteor falls and Explosive Blast has a fuse: the damage waits
            // for the sheet's delay_seconds or duration_seconds and lands
            // where it lands, so the module
            // owns it.
            if (Wizard::Delayed(player, shell.spellId, center))
                return;
            if (WizardGround(shell))
            {
                GroundImpact(player, shell, center);
                Abilities::Cast(player, shell.spellId, {}, &center, shell.extraDamage);
                Wizard::Cast(player, shell.spellId, AreaList(player, info, center, shell.targeting.radius), center,
                             explicitTarget);
                return;
            }
            // A skill that charges (Shield Bash) closes on its enemy before the hits.
            Crusader::Approach(player, shell.spellId, explicitTarget);
            // Epiphany (D3's 'melee attacks dash to your target'): a cast at a selected enemy beyond the
            // skill's own reach dashes to it first and resolves where the Monk lands: the cone is searched again from there,
            // and a melee skill's reach is measured from there.
            std::vector<ObjectGuid> reached = native;
            if (explicitTarget && ValidTarget(player, explicitTarget, info, false) &&
                Monk::Approach(player, shell.spellId, explicitTarget))
            {
                center = player->GetPosition();
                if (shell.targeting.type == "cone_enemies")
                    reached = ConeFrom(player, info, shell.targeting.radius);
            }
            auto targets = ResolveTargets(player, info, shell.targeting, center, reached, explicitTarget);
            LOG_DEBUG("module.dc.combat", "[DC targets] spell={} type={} count={} center=({},{},{})", shell.spellId,
                     shell.targeting.type, targets.size(), center.GetPositionX(), center.GetPositionY(),
                     center.GetPositionZ());
            if (Monk::Delayed(player, shell.spellId, targets, explicitTarget))
                return;
            unsigned connected = 0;
            Monk::Aim(player, shell.spellId, targets, explicitTarget);
            Shaman::Aim(player, shell.spellId, targets);
            auto const punch = Monk::Begin(player, shell.spellId, targets.empty() ? nullptr : targets.front());
            Shell punched = shell;
            if (punch.pct)
                punched.damagePct = *punch.pct;
            // N-NHIT: each target's hit is computed knowing its place among the cast's targets, nearest the centre first (a
            // `first_hits` or `per_prior_hit` row reads it) and how many the cast hits in all (a `cast_enemies_at_most` row reads it); the loop keeps its own
            // order, and both are put back after.
            // A line's places count from where it starts (the caster's feet, the order a charge meets its enemies in), not from
            // the point it ends at, which is its `center`.
            Position const& from = origin && shell.targeting.Line() ? *origin : center;
            // A Monk skill that strikes past the core's list (Lashing Tail Kick's half circle) has those enemies counted in too: the
            // places and the enemy count are over both, and Monk::Cast strikes them with the same counts.
            std::vector<double> distances;
            for (Unit* target : targets)
                distances.push_back(from.GetExactDist(target));
            for (Unit* target : Monk::Beside(player, shell.spellId, targets))
                distances.push_back(from.GetExactDist(target));
            unsigned& place = ItemPowers::HitPlace();
            unsigned const outer = place;
            unsigned& enemies = ItemPowers::CastEnemies();
            unsigned const outerEnemies = enemies;
            enemies = distances.size();
            std::size_t index = 0;
            for (Unit* target : targets)
            {
                place = ItemPower::NearestPlace(distances, index++);
                connected += ResolveHit(player, target, punch.pct ? punched : shell, info) ? 1 : 0;
            }
            place = outer;
            enemies = outerEnemies;
            Abilities::Cast(player, shell.spellId, targets, &center,shell.extraDamage);
            Wizard::Cast(player, shell.spellId, targets, center, explicitTarget);
            Monk::Cast(player, shell.spellId, targets, punch);
            Crusader::Cast(player, shell.spellId, targets);
            Necromancer::Cast(player, shell.spellId, targets);
            DemonHunter::Cast(player, shell.spellId, targets);
            WitchDoctor::Cast(player, shell.spellId, targets);
            Shaman::Cast(player, shell.spellId, targets);
            Monk::Ground(player, shell.spellId, center);
            Crusader::Ground(player, shell.spellId, center);
            Necromancer::Ground(player, shell.spellId, center);
            DemonHunter::Ground(player, shell.spellId, center);
            WitchDoctor::Ground(player, shell.spellId, center);
            Shaman::Ground(player, shell.spellId, center);
            if (connected)
                Connected(player, shell.spellId, connected);
        }

        // --- the Wizard's channels ----------------
        // The third named
        // module-paid exception, in Whirlwind's shape.
        // The core runs the channel; the module pays
        // and deals every tick, following d3planner's simulator at the pin
        // (d07RiV/d3planner@898918b):
        //   cadence  floor(channeling / aps) frames of 60, read fresh every
        //            tick, the first at once (cast.js:491-495, :504, :506-512,
        //            tickinitial: 1);
        //   cost     ChannelTickCost above (cast.js:136-147);
        //   damage   base + min(whole seconds, 2) x ramp - which is the sheet's
        //            max for every one of them - then x aps x tick frames / 60
        //            for Ray of Frost and Disintegrate (wizard.js:168-175,
        //            :335-338) and x channeling / 60 for Arcane Torrent
        //            (wizard.js:274-276, :323-326).
        // The channel stops when a tick cannot be paid: the empty pool.
        struct Channel
        {
            std::uint32_t spellId = 0;
            ObjectGuid aim;         // the unit a beam was cast at
            Position center;        // Arcane Torrent's point
            float direction = 0;    // a beam's heading once its unit is gone
            double clock = 0;       // ms since the last tick
            double elapsed = 0;     // ms since the channel began
            double owed = 0;        // Mana below one whole point, carried
        };
        std::mutex channelMutex;
        std::unordered_map<uint64, Channel> channels;

        double ChannelTickSeconds(Player* player, std::uint32_t spellId)
        {
            return CostMath::ScheduleSeconds(Numbers::Num(spellId, "channel_tick_frames_count"),
                                             AttacksPerSecond(player, spellId),
                                             Numbers::Num(spellId, "channel_frames_per_second_count"));
        }

        // Pay one tick; false when the pool cannot, which ends the channel.
        // Mana is whole points, so a fraction of a point is carried to the next
        // tick rather than rounded away.
        bool PayChannelTick(Player* player, Channel& channel)
        {
            auto const debit = CostMath::PayWhole(
                Resources::Units(player, Resources::ArcanePower),
                Resources::ToUnits(Resources::ArcanePower, ChannelTickCost(player, channel.spellId)) + channel.owed);
            if (!debit.paid)
                return false;
            channel.owed = debit.owed;
            if (debit.whole > 0)
            {
                Resources::SpendUnits(player, Resources::ArcanePower, debit.whole);
                ChannelSpent(player, channel.spellId);
            }
            return true;
        }

        // The weapon-damage percentage one tick carries.
        double ChannelTickPct(Player* player, Channel const& channel, Shell const& shell)
        {
            std::uint32_t const id = channel.spellId;
            // Arcane Mines lays mines rather than hitting (wizard.js:279-290,
            // :316-318); ChannelTick hands the tick to Wizard::ChannelTick.
            if (shell.rune == "Arcane Mines")
                return 0;
            // Archon form's Disintegration Wave does not ramp: its flat
            // damage_pct x aps x tick frames / 60 (wizard.js:1083), the same
            // share Disintegrate's ramped number takes.
            if (!Numbers::Has(id, "damage_pct", "base") && Numbers::Has(id, "damage_pct") &&
                shell.skill == Wizard::ARCHON_FORM)
                return CostMath::ChannelTickShare(Numbers::Num(id, "damage_pct"),
                                                  Numbers::Num(id, "channel_tick_frames_count"),
                                                  Numbers::Num(id, "channel_frames_per_second_count"),
                                                  AttacksPerSecond(player, id), false);
            if (!Numbers::Has(id, "damage_pct", "base") || !Numbers::Has(id, "damage_pct", "ramp"))
                return 0;
            if (!Numbers::Has(id, "damage_pct", "max"))
                return 0;
            double const pct = CostMath::ChannelRamp(Numbers::Num(id, "damage_pct", "base"),
                                                     Numbers::Num(id, "damage_pct", "ramp"),
                                                     Numbers::Num(id, "damage_pct", "max"), channel.elapsed / 1000.0);
            return CostMath::ChannelTickShare(pct, Numbers::Num(id, "channel_tick_frames_count"),
                                              Numbers::Num(id, "channel_frames_per_second_count"),
                                              AttacksPerSecond(player, id), Wizard::ChannelsByDuration(shell.skill));
        }

        std::vector<Unit*> ChannelTargets(Player* player, SpellInfo const* info, Shell const& shell,
                                          Channel& channel)
        {
            auto const& row = shell.targeting;
            Unit* aim = channel.aim ? ObjectAccessor::GetUnit(*player, channel.aim) : nullptr;
            if (row.type == "single_enemy")
            {
                // Ray of Frost: "blasts enemies within 5 yards of the first
                // enemy hit" (skill_targeting.csv).
                if (!aim || player->GetExactDist(aim) > row.range || !ValidTarget(player, aim, info, false))
                    return {};
                std::vector<Unit*> out = row.radius > 0 ? AreaList(player, info, aim->GetPosition(), row.radius)
                                                         : std::vector<Unit*>{};
                if (std::find(out.begin(), out.end(), aim) == out.end())
                    out.push_back(aim);
                // Light of Grace: the beam also hits every enemy on its line through the aimed one, as wide as the
                // tunable (4 yd, borrowed from Disintegrate's beam); blank or 0 leaves it off. Sleet Storm has no beam.
                if (shell.rune != "Sleet Storm" && ItemPowers::SkillSetTo(player, shell.skill, "pierces", 0) > 0 &&
                    Tunables::Has("wizard", "ray_of_frost_pierce_width_yards") &&
                    Tunables::Get("wizard", "ray_of_frost_pierce_width_yards") > 0)
                {
                    Position const origin = player->GetPosition();
                    Acore::WorldObjectSpellLineTargetCheck check(
                        origin, origin.GetAbsoluteAngle(aim->GetPositionX(), aim->GetPositionY()), row.range,
                        static_cast<float>(Tunables::Get("wizard", "ray_of_frost_pierce_width_yards")), player, info,
                        TARGET_CHECK_ENEMY, nullptr);
                    for (Unit* unit : AreaList(player, info, origin, row.range))
                        if (check(unit) && std::find(out.begin(), out.end(), unit) == out.end())
                            out.push_back(unit);
                }
                return out;
            }
            if (row.Line())
            {
                // Disintegrate's beam follows its unit while it lives, then
                // keeps the last heading.
                Position const origin = player->GetPosition();
                if (aim && aim->IsAlive() && aim->IsInMap(player))
                    channel.direction = origin.GetAbsoluteAngle(aim->GetPositionX(), aim->GetPositionY());
                Acore::WorldObjectSpellLineTargetCheck check(origin, channel.direction, row.range, row.width, player,
                                                             info, TARGET_CHECK_ENEMY, nullptr);
                std::vector<Unit*> out;
                for (Unit* unit : AreaList(player, info, origin, row.range))
                    if (check(unit))
                        out.push_back(unit);
                return out;
            }
            return AreaList(player, info, channel.center, row.radius);
        }

        // One tick: pay it, then hit. False when it could not be paid.
        bool ChannelTick(Player* player, Channel& channel)
        {
            auto shell = FindShell(channel.spellId);
            SpellInfo const* info = sSpellMgr->GetSpellInfo(channel.spellId);
            if (!shell || !info || !PayChannelTick(player, channel))
                return false;
            // Arcane Mines lays a mine each tick (wizard.js:316, :281-290).
            if (shell->rune == "Arcane Mines")
            {
                Wizard::ChannelTick(player, channel.spellId, channel.center);
                return true;
            }
            double const pct = ChannelTickPct(player, channel, *shell);
            if (pct <= 0)
                return true;
            bool connected = false;
            for (Unit* target : ChannelTargets(player, info, *shell, channel))
            {
                Hit hit;
                if (!ComputeHit(player, target, channel.spellId, hit, pct))
                    continue;
                DealHit(player, target, channel.spellId, hit);
                if (hit.total <= 0)
                    continue;
                connected = true;
                Wizard::Landed(player, target, channel.spellId, hit, false);
                Passives::Hit(player, target, channel.spellId, hit.school);
                Abilities::HitEffects(player, target, channel.spellId);
                if (hit.critical)
                    Abilities::CriticalHit(player, target, channel.spellId, hit.total);
                if (hit.areaDamage > 0)
                {
                    Hit splash = hit;
                    splash.total = hit.areaDamage;
                    splash.areaDamage = 0;
                    // damage_formula.csv step 11: 10 yards.
                    for (Unit* nearby : AreaList(player, info, target->GetPosition(), 10.0f))
                        if (nearby != target)
                            DealHit(player, nearby, channel.spellId, splash);
                }
            }
            if (connected)
                Connected(player, channel.spellId);
            return true;
        }

        // `recover` is a channel that ended while the player was still there to press
        // again (let go, interrupted, out of Arcane Power): its one swing starts now.
        // Logout and a map change end it too, and owe nothing.
        void StopChannel(Player* player, bool recover = false)
        {
            std::uint32_t ended = 0;
            {
                std::lock_guard<std::mutex> lock(channelMutex);
                auto found = channels.find(player->GetGUID().GetRawValue());
                if (found != channels.end())
                {
                    ended = found->second.spellId;
                    channels.erase(found);
                }
            }
            if (ended)
                if (auto row = Shells::FindAbility(ended))
                    ItemPowers::ChannelEnded(player, row->skill);
            if (recover && ended && player->IsAlive())
                StartSwingRecovery(player, ended);
        }

        void StartChannel(Player* player, Shell const& shell, Position const& center, Unit* aim)
        {
            Channel channel;
            channel.spellId = shell.spellId;
            channel.center = center;
            if (aim)
            {
                channel.aim = aim->GetGUID();
                channel.direction = player->GetAbsoluteAngle(aim->GetPositionX(), aim->GetPositionY());
            }
            else
                channel.direction = player->GetOrientation();
            // A channel this one replaces is over: the core interrupted it without StopChannel, so its span ends here, or a condition
            // that holds while it is channelled (Mantle of Channeling) would hold for good.
            std::uint32_t replaced = 0;
            {
                std::lock_guard<std::mutex> lock(channelMutex);
                auto found = channels.find(player->GetGUID().GetRawValue());
                if (found != channels.end())
                    replaced = found->second.spellId;
            }
            if (replaced)
                if (auto row = Shells::FindAbility(replaced))
                    ItemPowers::ChannelEnded(player, row->skill);
            // The first tick lands at once (cast.js:510, tickinitial: 1).
            if (!ChannelTick(player, channel))
            {
                player->InterruptSpell(CURRENT_CHANNELED_SPELL);
                return;
            }
            ItemPowers::ChannelStarted(player, shell.skill);
            std::lock_guard<std::mutex> lock(channelMutex);
            channels[player->GetGUID().GetRawValue()] = channel;
        }

        class WizardChannels final : public PlayerScript
        {
        public:
            WizardChannels()
                : PlayerScript("dc_wizard_channels", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT,
                                                      PLAYERHOOK_ON_MAP_CHANGED})
            {
            }
            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Channel channel;
                {
                    std::lock_guard<std::mutex> lock(channelMutex);
                    auto found = channels.find(player->GetGUID().GetRawValue());
                    if (found == channels.end())
                        return;
                    channel = found->second;
                }
                // The player let go - moved, cast something else, was
                // interrupted - or died: the core ended the channel.
                Spell* current = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
                if (!player->IsAlive() || !current || current->GetSpellInfo()->Id != channel.spellId)
                {
                    StopChannel(player, true);
                    return;
                }
                channel.clock += diff;
                channel.elapsed += diff;
                // Read every update, so an attack-speed change moves the next
                // tick; no attack speed means no cadence and no tick at all.
                double interval = ChannelTickSeconds(player, channel.spellId);
                while (interval > 0 && channel.clock >= interval * 1000)
                {
                    channel.clock -= interval * 1000;
                    if (!ChannelTick(player, channel))
                    {
                        StopChannel(player, true);
                        player->InterruptSpell(CURRENT_CHANNELED_SPELL);
                        return;
                    }
                    interval = ChannelTickSeconds(player, channel.spellId);
                }
                std::lock_guard<std::mutex> lock(channelMutex);
                if (auto found = channels.find(player->GetGUID().GetRawValue()); found != channels.end())
                    found->second = channel;
            }
            void OnPlayerLogout(Player* player) override
            {
                StopChannel(player);
            }
            void OnPlayerMapChanged(Player* player) override
            {
                StopChannel(player);
            }
        };

        struct AbilityLanding
        {
            Shell shell;
            Position center;
            uint32 spline = 0, map = 0, instance = 0, phase = 0;
        };
        std::mutex landingMutex;
        std::unordered_map<uint64, AbilityLanding> abilityLandings;

        void ClearLanding(Unit* unit)
        {
            std::lock_guard<std::mutex> lock(landingMutex);
            abilityLandings.erase(unit->GetGUID().GetRawValue());
        }

        class AbilityGeometry final : public UnitScript
        {
        public:
            AbilityGeometry()
                : UnitScript("dc_ability_geometry", true,
                             {UNITHOOK_PROVIDE_SPELL_LINE_GEOMETRY, UNITHOOK_ON_EFFECT_MOVEMENT_FINALIZED,
                              UNITHOOK_ON_UNIT_DEATH})
            {
            }

            bool ProvideSpellLineGeometry(Spell* spell, uint8 effect, Unit*, Position& origin, float& direction,
                                          float& length, float& width) override
            {
                auto shell = FindShell(spell->GetSpellInfo()->Id);
                if (effect != EFFECT_0 || !shell || !shell->targeting.Line())
                    return false;
                // A claimed but invalid line must fail closed, not fall back to a cone.
                if (!LineGeometry(spell, shell->targeting, origin, direction, length, width))
                    length = width = 0;
                return true;
            }

            void OnEffectMovementFinalized(Unit* unit, uint32, uint32 spline, bool completed) override
            {
                AbilityLanding pending;
                {
                    std::lock_guard<std::mutex> lock(landingMutex);
                    auto it = abilityLandings.find(unit->GetGUID().GetRawValue());
                    if (it == abilityLandings.end() || it->second.spline != spline)
                        return;
                    pending = it->second;
                    abilityLandings.erase(it);
                }
                Player* player = unit->ToPlayer();
                if (completed && player && player->IsAlive() && player->IsInWorld() &&
                    player->GetMapId() == pending.map && player->GetInstanceId() == pending.instance &&
                    player->GetPhaseMask() == pending.phase)
                {
                    ResolveCast(player, pending.shell, pending.center);
                    ItemPowers::Landed(player, pending.shell.spellId); // Might of the Earth 4-piece: an Earthquake where Leap lands
                }
            }
            void OnUnitDeath(Unit* unit, Unit*) override
            {
                ClearLanding(unit);
            }
        };

        class AbilityCleanup final : public PlayerScript
        {
        public:
            AbilityCleanup()
                : PlayerScript("dc_ability_cleanup", {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }
            void OnPlayerLogout(Player* player) override
            {
                ClearLanding(player);
            }
            void OnPlayerMapChanged(Player* player) override
            {
                ClearLanding(player);
            }
        };

        class dc_ability_targets final : public SpellScript
        {
            PrepareSpellScript(dc_ability_targets);
            Shell shell;
            std::vector<ObjectGuid> native;
            Position center;
            Position origin; // where the caster stood when the cast began (`center` is the point a destination cast ends at)
            bool paid = false;
            // The cast is a free one Lightning Overload made: its projectile's impacts, long after the cast returned, are marked as its hits.
            bool freeCast = false;
            // What the module drained itself (the spend-all runes) and the pool
            // it left for the core, so the Fury the passives are told about is
            // measured rather than assumed. See Charged().
            double drained = 0, poolBeforeCore = 0;
            bool charged = false;
            bool connected = false;
            std::unordered_set<uint64> impacted;
            uint32 launchMap = 0, launchInstance = 0, launchPhase = 0;
            uint32 previousSpline = 0;

            bool Projectile()
            {
                return GetSpellInfo()->Speed > 0 && !GetSpellInfo()->IsChanneled();
            }

            // Whether any effect of the record aims at a unit other than the caster: only then does the core deliver an impact (AfterHit) to
            // resolve. A ground-point record has a destination and nothing else, so no impact ever comes for it.
            bool AimsAtAUnit()
            {
                for (SpellEffectInfo const& effect : GetSpellInfo()->Effects)
                    if (effect.IsEffect())
                        for (SpellImplicitTargetInfo const& aim : {effect.TargetA, effect.TargetB})
                            if (aim.GetObjectType() == TARGET_OBJECT_TYPE_UNIT && aim.GetTarget() != TARGET_UNIT_CASTER)
                                return true;
                return false;
            }

            // A missile aimed at a ground point: it flies for the distance at the record's Speed and resolves where it lands, as the
            // cast it would have been with no missile, unless the caster has left the map or died meanwhile.
            void LandAtPoint(Player* player)
            {
                Unit* aim = GetExplTargetUnit();
                player->m_Events.AddEventAtOffset(
                    [player, shell = shell, center = center, origin = origin, aimed = aim ? aim->GetGUID() : ObjectGuid::Empty,
                     map = launchMap, instance = launchInstance, phase = launchPhase]
                    {
                        if (!player->IsAlive() || !player->IsInWorld() || player->GetMapId() != map ||
                            player->GetInstanceId() != instance || player->GetPhaseMask() != phase)
                            return;
                        ResolveCast(player, shell, center, {}, aimed ? ObjectAccessor::GetUnit(*player, aimed) : nullptr, &origin);
                    },
                    std::chrono::milliseconds(GroundMissile::ArrivalMs(player->GetExactDist(center), GetSpellInfo()->Speed)));
            }

            SpellCastResult Check()
            {
                Player* player = GetCaster()->ToPlayer();
                auto creature=GetCaster()->ToCreature();
                if(creature && creature->GetOwner() && creature->GetOwner()->ToPlayer() &&
                   creature->GetEntry()>=900100 && creature->GetEntry()<=900102)
                    return SPELL_CAST_OK;
                auto found = FindShell(GetSpellInfo()->Id);
                if (!HitsThroughCombat(player) || !found || !found->targeting.Ready())
                    return SPELL_FAILED_NOT_READY;
                shell = *found;
                auto const& row = shell.targeting;
                if (row.Destination())
                {
                    if (!GetSpell()->m_targets.HasDst())
                        return SPELL_FAILED_BAD_TARGETS;
                    auto dst = GetExplTargetDest();
                    if (!dst || !dst->IsPositionValid() || player->GetExactDist(dst) > row.range)
                        return SPELL_FAILED_OUT_OF_RANGE;
                    if (!player->IsWithinLOS(dst->GetPositionX(), dst->GetPositionY(), dst->GetPositionZ()))
                        return SPELL_FAILED_LINE_OF_SIGHT;
                }
                if (row.type == "line_pierce")
                {
                    Unit* aim = GetExplTargetUnit();
                    if (!aim || !ValidTarget(player, aim, GetSpellInfo(), false))
                        return SPELL_FAILED_BAD_TARGETS;
                    if (player->GetExactDist(aim) > row.range)
                        return SPELL_FAILED_OUT_OF_RANGE;
                }
                if (!Abilities::Ready(player,shell.spellId)) return SPELL_FAILED_NOT_READY;
                return SPELL_CAST_OK;
            }

            void Collect(std::list<WorldObject*>& targets)
            {
                native.clear();
                auto row = FindShell(GetSpellInfo()->Id);
                if (!row)
                {
                    targets.clear();
                    return;
                }
                Position origin;
                float direction = 0, length = 0, width = 0;
                bool const line = row->targeting.Line();
                if (line && !LineGeometry(GetSpell(), row->targeting, origin, direction, length, width))
                {
                    targets.clear();
                    return;
                }
                // TargetB's explicit aim may also be selected by the core; keep only
                // the area walk's valid finite segment, with no hit beyond its endpoint.
                targets.remove_if(
                    [&](WorldObject* object)
                    {
                        Unit* unit = object->ToUnit();
                        if (!unit)
                            return true;
                        if (line)
                        {
                            Acore::WorldObjectSpellLineTargetCheck check(origin, direction, length, width, GetCaster(),
                                                                         GetSpellInfo(), TARGET_CHECK_ENEMY, nullptr);
                            if (!check(unit))
                                return true;
                        }
                        else if (GetCaster()->GetExactDist(unit) > row->targeting.radius)
                            return true;
                        native.push_back(unit->GetGUID());
                        return false;
                    });
            }

            // Electrocute's jumps: the core's chain list becomes the module's walk (Wizard::Jumps), so the arcs the client
            // draws are the enemies the bolt hits; `native` keeps them in order, a re-hit included.
            void Chain(std::list<WorldObject*>& targets)
            {
                native.clear();
                targets.clear();
                Player* player = GetCaster()->ToPlayer();
                for (Unit* unit : Wizard::Jumps(player, GetSpellInfo()->Id, GetExplTargetUnit()))
                {
                    native.push_back(unit->GetGUID());
                    if (std::find(targets.begin(), targets.end(), unit) == targets.end())
                        targets.push_back(unit);
                }
            }

            void Begin()
            {
                auto found = FindShell(GetSpellInfo()->Id);
                Player* player = GetCaster()->ToPlayer();
                if (!found || !HitsThroughCombat(player) || !found->targeting.Ready())
                    return;
                shell = *found;
                center = player->GetPosition();
                origin = center;
                if (shell.targeting.Destination())
                {
                    if (!GetSpell()->m_targets.HasDst() || !GetExplTargetDest())
                    {
                        FinishCast(SPELL_FAILED_BAD_TARGETS);
                        return;
                    }
                    center = *GetExplTargetDest();
                    DemonHunter::Aim(player, shell.spellId, center);
                }
                previousSpline = player->movespline->GetId();
                launchMap = player->GetMapId();
                launchInstance = player->GetInstanceId();
                launchPhase = player->GetPhaseMask();
                // OnCast runs before Spell::TakePower, so the pool these two
                // runes turn into damage is still whole here, exactly as it was
                // when the module did the charging. GetPowerCost() is what the
                // core is about to take: the record's cost with the player's
                // SPELLMOD_COST auras already applied.
                if(auto metadata=Shells::FindAbility(shell.spellId)) {
                    Abilities::Begin(shell.skill, shell.rune, metadata->id, CurrentFury(player),
                                     Resources::ToPoints(Resources::Fury, GetSpell()->GetPowerCost()), shell.damagePct, shell.extraDamage);
                }
                // The core charges the record's cost between this hook and
                // AfterCast, and the cast reached here, so it is paid.
                // GetPowerCost() is that number, reductions included.
                if (SpendsEveryPoint(shell))
                {
                    // The core takes the base cost; the module takes the rest
                    // of the pool, which is the part no record field can say.
                    drained = std::max(0.0, CurrentFury(player) -
                                                Resources::ToPoints(Resources::Fury, GetSpell()->GetPowerCost()));
                    ChangeFury(player, -drained);
                }
                paid = true;
                Wizard::Begin(player, shell.spellId, GetExplTargetUnit());
                Monk::Casting(player, shell.spellId);
                Necromancer::Casting(player, shell.spellId);
                DemonHunter::Casting(player, shell.spellId);
                freeCast = Shaman::FreeCast();
                Shaman::Casting(player, shell.spellId);
                Passives::Begin(player,shell.spellId);
                Abilities::LaunchEffects(player,shell.spellId);
                // The core takes its part next; Charged() reads how much.
                poolBeforeCore = CurrentFury(player);
            }

            // Spell::cast runs OnCast, then TakePower, then the launch phase
            // (Spell.cpp: CallScriptOnCastHandlers, TakePower, HandleLaunchPhase),
            // and nothing of ours runs in between - so this is the first moment
            // the Fury the core actually took can be read, and the last one
            // before any on-hit effect can give Fury back.
            //
            // It is measured rather than taken from GetPowerCost() because the
            // nominal cost is not always what is paid: Spell::TakePower returns
            // early for an item cast, an aura-triggered cast and .cheat power,
            // and for a Rage cost it takes only irand(0, cost / 4) when the
            // target's miss condition is not NONE, BLOCK, ABSORB or REFLECT.
            // SPELL_ATTR3_ALWAYS_HIT rules out miss, dodge and parry
            // (Unit::MeleeSpellHitResult), but Unit::SpellHitResult's Spell
            // overload can still answer IMMUNE or EVADE, so that branch is
            // reachable for our shells.
            void Charged(SpellEffIndex)
            {
                Player* player = GetCaster()->ToPlayer();
                if (charged || !paid || !player || Abilities::PaysByTick(shell.skill))
                    return;
                charged = true;
                double const taken = std::max(0.0, poolBeforeCore - CurrentFury(player));
                AfterPayment(player, shell, drained + taken);
            }

            void Finish()
            {
                Player* player = GetCaster()->ToPlayer();
                if (!paid || !player)
                    return;
                AbilityCast(player, shell.spellId, GetSpell()->IsTriggered(),
                            Abilities::PaysByTick(shell.skill) || WizardChannel(shell));
                Shaman::Launched(player, shell.spellId, GetSpell()->IsTriggered());
                // The cooldown is the core's: it read RecoveryTime and the
                // shared Category off the record and installed both before
                // this hook ran. Landing and projectile waits below
                // do not delay recovery, which is why nothing here touches it.
                if (Abilities::PaysByTick(shell.skill))
                {
                    Abilities::StartWhirlwind(player, shell.spellId);
                    return;
                }
                if (WizardChannel(shell))
                {
                    StartChannel(player, shell, center, GetExplTargetUnit());
                    return;
                }
                if (shell.targeting.type == "ground_point_aoe")
                {
                    uint32 const spline = player->movespline->GetId();
                    if (spline != previousSpline && !player->movespline->Finalized())
                    {
                        std::lock_guard<std::mutex> lock(landingMutex);
                        abilityLandings[player->GetGUID().GetRawValue()] = {
                            shell, center, spline, player->GetMapId(), player->GetInstanceId(), player->GetPhaseMask()};
                    }
                    return;
                }
                // AfterCast runs at launch, even for SPELL_STATE_DELAYED. Let the
                // native per-target missile clock deliver these hits in Impact.
                switch (GroundMissile::PathOf(GetSpellInfo()->Speed, GetSpellInfo()->IsChanneled(), AimsAtAUnit()))
                {
                    case GroundMissile::Path::AtCast:
                        ResolveCast(player, shell, center, native, GetExplTargetUnit(), &origin);
                        break;
                    case GroundMissile::Path::OnArrival:
                        LandAtPoint(player);
                        break;
                    case GroundMissile::Path::OnImpact:
                        break;
                }
            }

            // The enemies this cast hits, for the Gavel of Judgment's `enemies_hit_at_most`: Impact lands one
            // target per AfterHit, so the count is read at the first connect from the launch's cone or line, the listed enemies still
            // valid just before that hit lands (the enemy it kills counts); a projectile with no list hits its one target.
            // ponytail: a listed enemy that dies or leaves before its own impact still counts; exact needs a hook after the last impact.
            unsigned Struck(Player* player)
            {
                if (native.empty())
                    return 1;
                unsigned count = 0;
                for (ObjectGuid const& guid : native)
                    count += ValidTarget(player, ObjectAccessor::GetUnit(*player, guid), GetSpellInfo(), shell.targeting.Friendly()) ? 1 : 0;
                return count;
            }

            void Impact()
            {
                Shaman::FreeHits free(freeCast);
                Player* player = GetCaster()->ToPlayer();
                Unit* target = GetHitUnit();
                if (!paid || !Projectile() || !player || !player->IsAlive() || !player->IsInWorld() ||
                    player->GetMapId() != launchMap || player->GetInstanceId() != launchInstance ||
                    player->GetPhaseMask() != launchPhase || shell.targeting.type == "ground_point_aoe" ||
                    !ValidTarget(player, target, GetSpellInfo(), shell.targeting.Friendly()))
                    return;
                // Keep the launch-selected finite line/cone. TargetB's explicit
                // aim is not permission to hit outside that list. Do not re-aim
                // the projectile if the caster turns while it is in flight.
                if ((shell.targeting.Line() || shell.targeting.type == "cone_enemies") &&
                    std::find(native.begin(), native.end(), target->GetGUID()) == native.end())
                    return;
                if (Abilities::BurstsAtFirstImpact(shell.skill, shell.rune))
                {
                    if (target != GetExplTargetUnit() || !impacted.empty())
                        return;
                    impacted.insert(target->GetGUID().GetRawValue());
                    unsigned hit = 0;
                    // N-NHIT: each hit of the burst is computed knowing how many enemies the burst hits in all (a `cast_enemies_at_most`
                    // row reads it); put back after.
                    auto const area = AreaList(player, GetSpellInfo(), target->GetPosition(), shell.targeting.radius);
                    unsigned& enemies = ItemPowers::CastEnemies();
                    unsigned const outer = enemies;
                    enemies = area.size();
                    for (Unit* u : area)
                        hit += ResolveHit(player, u, shell, GetSpellInfo()) ? 1 : 0;
                    enemies = outer;
                    if (hit)
                        Connected(player, shell.spellId, hit);
                    return;
                }
                if (!impacted.insert(target->GetGUID().GetRawValue()).second)
                    return;
                if (Necromancer::Impact(player, target, shell.spellId, unsigned(impacted.size()) - 1))
                    return;
                if (DemonHunter::Impact(player, target, GetExplTargetUnit(), native, shell.spellId))
                    return;
                // Counted before the hit lands: a killing blow leaves the target dead, and ValidTarget would drop it.
                unsigned const struck = connected ? 0 : Struck(player);
                if (ResolveHit(player, target, shell, GetSpellInfo()) && !connected)
                {
                    connected = true;
                    Connected(player, shell.spellId, struck);
                }
            }

            void Register() override
            {
                OnCheckCast += SpellCheckCastFn(dc_ability_targets::Check);
                OnCast += SpellCastFn(dc_ability_targets::Begin);
                OnEffectLaunch += SpellEffectFn(dc_ability_targets::Charged, EFFECT_0, SPELL_EFFECT_ANY);
                AfterCast += SpellCastFn(dc_ability_targets::Finish);
                AfterHit += SpellHitFn(dc_ability_targets::Impact);
                auto info = sSpellMgr->GetSpellInfo(m_scriptSpellId);
                if (info && info->Effects[EFFECT_0].TargetA.GetTarget() == TARGET_UNIT_CONE_ENEMY_104)
                    OnObjectAreaTargetSelect += SpellObjectAreaTargetSelectFn(dc_ability_targets::Collect, EFFECT_0,
                                                                              TARGET_UNIT_CONE_ENEMY_104);
                if (Wizard::Chains(m_scriptSpellId) && info && info->Effects[EFFECT_0].TargetA.GetTarget() == TARGET_UNIT_TARGET_ENEMY)
                    OnObjectAreaTargetSelect += SpellObjectAreaTargetSelectFn(dc_ability_targets::Chain, EFFECT_0,
                                                                              TARGET_UNIT_TARGET_ENEMY);
            }
        };
    } // namespace

    double DamageBonus(Player* player) { return Primaries::DamageBonus(player)+Abilities::DamageBonus(player)+Passives::DamageBonus(player); }

    double DamageFactor(Player* player)
    {
        Factors factors;
        Abilities::Multipliers(player, factors);
        return Product(factors);
    }

    std::vector<Unit*> Enemies(Player* player, std::uint32_t spellId, Position const& center, double radius)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!player || !info || radius <= 0)
            return {};
        return AreaList(player, info, center, float(radius));
    }

    namespace
    {
        // A pet's blow on this thread: whether one stands and the coefficient of the pet's own attack.
        thread_local bool petBlow = false;
        thread_local std::optional<double> petCoefficient;
    } // namespace

    PetBlow::PetBlow(std::optional<double> coefficient)
    {
        petBlow = true;
        petCoefficient = coefficient;
    }

    PetBlow::~PetBlow()
    {
        petBlow = false;
        petCoefficient.reset();
    }

    std::optional<double> ProcCoefficient(std::uint32_t spellId)
    {
        return Proc::Landing(petBlow, petCoefficient, Numbers::Get(spellId, "proc_coefficient"));
    }

    bool Strike(Player* player, Unit* target, std::uint32_t spellId, std::optional<double> pct, bool periodic)
    {
        if (!player || !target || !target->IsAlive())
            return false;
        Hit hit;
        if (!ComputeHit(player, target, spellId, hit, pct, periodic))
            return false;
        // A module-owned strike pays no Area Damage: the class's own area is
        // already the area (damage_formula.csv step 11 is a skill's splash).
        hit.areaDamage = 0;
        DealHit(player, target, spellId, hit);
        if (hit.total <= 0)
            return false;
        Wizard::Landed(player, target, spellId, hit, periodic);
        if (!periodic)
        {
            Monk::Landed(player, target, spellId);
            Crusader::Landed(player, target, spellId);
            Necromancer::Landed(player, target, spellId);
            DemonHunter::Landed(player, target, spellId, hit.critical);
            WitchDoctor::Landed(player, target, spellId);
            Shaman::Landed(player, target, spellId, hit.critical);
            WitchDoctor::Pets::Landed(player, target, spellId);
            Shaman::Landed(player, target, spellId);
            Passives::Hit(player, target, spellId, hit.school);
        }
        if (hit.critical)
            Abilities::CriticalHit(player, target, spellId, hit.total);
        if (hit.critical) Monk::Critical(player, spellId);
        return true;
    }

    std::vector<Unit*> StrikeArea(Player* player, std::uint32_t spellId, Position const& center, double radius,
                                  std::optional<double> pct, bool periodic)
    {
        std::vector<Unit*> hit;
        auto const area = Enemies(player, spellId, center, radius);
        // N-NHIT: each hit of the burst is computed knowing how many enemies the burst holds in all (a `cast_enemies_at_most` row reads it);
        // put back after. A tick (`periodic`) is no burst and counts none.
        unsigned& enemies = ItemPowers::CastEnemies();
        unsigned const outer = enemies;
        if (!periodic)
            enemies = area.size();
        for (Unit* target : area)
            if (Strike(player, target, spellId, pct, periodic))
                hit.push_back(target);
        enemies = outer;
        if (!hit.empty() && !periodic)
            Connected(player, spellId, static_cast<unsigned>(hit.size()));
        return hit;
    }

    bool CastSkill(Player* player, std::string const& skill, Unit* target)
    {
        if (!player || !player->IsAlive())
            return false;
        for (Classes::Slot const& slot : Classes::Bar(player))
            if (auto shell = Shells::FindAbility(slot.spellId); shell && skill == shell->skill)
                return player->CastSpell(target ? target : player, slot.spellId, TRIGGERED_FULL_MASK) == SPELL_CAST_OK;
        return false;
    }

    void Connected(Player* player, std::uint32_t spellId, unsigned enemies)
    {
        Stats::SkillHit(player);
        ItemPowers::Attack(player, spellId, enemies);
        Monk::Connected(player, spellId);
        Crusader::Connected(player, spellId, enemies);
        Necromancer::Connected(player, spellId, enemies);
        DemonHunter::Connected(player, spellId);
        WitchDoctor::Connected(player, spellId, enemies);
        Shaman::Connected(player, spellId, enemies);
    }

    void BarWritten(Player* player, std::vector<Classes::Slot> const& bar)
    {
        DemonHunter::BarWritten(player, bar);
    }

    double TargetRadius(std::uint32_t spellId)
    {
        auto shell = FindShell(spellId);
        return shell ? shell->targeting.radius : 0.0;
    }

    double TargetRange(std::uint32_t spellId)
    {
        auto shell = FindShell(spellId);
        return shell ? shell->targeting.range : 0.0;
    }

    void GainResource(Player* player, std::uint32_t spellId, double points)
    {
        GainArcanePower(player, spellId, points);
    }

    bool ApplySkillBleed(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (player && target && Monk::Apply(player, target, spellId))
            return true;
        auto shell = FindShell(spellId);
        return shell && player && target && target->IsAlive() && Abilities::Bleed(player, target, shell->spellId, shell->skill, true);
    }

    void RegisterResolveScripts()
    {
        RegisterSpellScript(dc_wizard_ground);
        RegisterSpellScript(dc_ability_targets);
        new AbilityGeometry();
        new AbilityCleanup();
        new WizardChannels();
    }
} // namespace DC::Combat
