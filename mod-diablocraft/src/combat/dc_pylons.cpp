#include "dc_pylons.h"
#include "dc_combat.h"
#include "dc_item_powers.h"
#include "dc_passives.h"
#include "dc_spell_shells.h"
#include "../rifts/dc_rifts.h"
#include "../common/dc_bridge.h"
#include "../common/dc_tunables.h"
#include "../stats/dc_stats.h"
#include "Chat.h"
#include "Creature.h"
#include "GameObject.h"
#include "Group.h"
#include "Map.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellScript.h"
#include "Unit.h"
#include <cmath>
#include <map>
#include <string>
#include <vector>

namespace DC::Combat::Pylons
{
    namespace
    {
        // Per player, in Player::CustomData: which kinds the sheet was last told about, and whether a buff came or
        // went (or the player died or revived) since. `known` is false until the first Reconcile after login.
        struct State : DataMap::Base
        {
            unsigned worn = 0;
            bool known = false;
            bool dirty = true;
        };
        State* StateOf(Player* player)
        {
            return player->CustomData.GetDefault<State>("DCPylon");
        }

        double Tune(std::string const& row)
        {
            return DC::Tunables::Get("combat", row);
        }

        std::uint32_t RecordOf(Kind kind)
        {
            return Shells::PylonBuffFor(Names[static_cast<unsigned>(kind)]);
        }

        std::uint32_t RecordOf(char const* name)
        {
            return Shells::PylonBuffFor(name);
        }

        // P3: the objects standing on a map, in the map's own data (one party's floor: a few objects), and an object's
        // one use. Both are read and written on the map's own update only.
        struct Standing : DataMap::Base
        {
            std::vector<ObjectGuid> objects;
        };
        struct Spent : DataMap::Base
        {
            bool spent = false;
        };

        // docs/contracts/pylon-messages.md.
        constexpr char const* Prefix = "DCPYLON";

        std::string Hex(ObjectGuid guid)
        {
            return Acore::StringFormat("{:016X}", guid.GetRawValue());
        }

        void Tell(Player* player, GameObject* object)
        {
            if (std::optional<Kind> const kind = KindOfObject(object->GetEntry()))
                DC::Bridge::Push(player, Prefix,
                                 {"S", Hex(object->GetGUID()), Names[static_cast<unsigned>(*kind)],
                                  Acore::StringFormat("{:.1f}", object->GetPositionX()),
                                  Acore::StringFormat("{:.1f}", object->GetPositionY())});
        }

        // The whole list of the player's map: C, then an S per object still standing.
        void List(Player* player)
        {
            Map* map = player->FindMap();
            if (!map)
                return;
            DC::Bridge::Push(player, Prefix, {"C"});
            auto& objects = map->CustomData.GetDefault<Standing>("DCPylons")->objects;
            std::erase_if(objects, [&](ObjectGuid guid) {
                GameObject* object = map->GetGameObject(guid);
                if (object)
                    Tell(player, object);
                return !object;
            });
        }

        void Gone(Map* map, ObjectGuid guid)
        {
            std::erase(map->CustomData.GetDefault<Standing>("DCPylons")->objects, guid);
            for (auto const& ref : map->GetPlayers())
                if (Player* player = ref.GetSource())
                    DC::Bridge::Push(player, Prefix, {"U", Hex(guid)});
        }

        // The click (pylons.md 4.2): asked before the core's own type 22 use, which never runs for these entries.
        class Objects final : public AllGameObjectScript
        {
        public:
            Objects() : AllGameObjectScript("dc_pylon_objects")
            {
            }
            bool CanGameObjectGossipHello(Player* player, GameObject* object) override
            {
                std::optional<Kind> const kind = object ? KindOfObject(object->GetEntry()) : std::nullopt;
                if (!kind || !player)
                    return false;
                if (!player->IsAlive())
                    return true;
                std::vector<Player*> members;
                if (Group* group = player->GetGroup())
                {
                    for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                        if (Player* member = ref->GetSource())
                            members.push_back(member);
                }
                else
                    members.push_back(player);
                auto const given = Spend(
                    object->CustomData.GetDefault<Spent>("DCPylon")->spent, *kind, Tune("shrine_share_radius_yards"),
                    members, [player](Player* m) { return m->IsInWorld() && m->IsInMap(player); },
                    [player](Player* m) { return m->GetDistance(player); }, [kind](Player* m) { return Give(m, *kind); });
                if (!given)
                    return true;
                Map* map = object->GetMap();
                Gone(map, object->GetGUID());
                object->Delete();
                return true;
            }
        };

        // The buff comes or goes: the update tick brings the sheet in line (this runs inside the core's aura code).
        class dc_pylon_buff final : public AuraScript
        {
            PrepareAuraScript(dc_pylon_buff);
            void Changed(AuraEffect const*, AuraEffectHandleModes)
            {
                if (Player* owner = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr)
                    StateOf(owner)->dirty = true;
            }
            // P2: Speed's knock-up goes with Speed's buff (cancelled or run out); leaving the rift takes only the
            // knock-up (6.11, P4).
            void Gone(AuraEffect const* effect, AuraEffectHandleModes mode)
            {
                Changed(effect, mode);
                if (GetId() == RecordOf(Kind::Speed))
                    if (Unit* owner = GetUnitOwner())
                        owner->RemoveAurasDueToSpell(Shells::PylonSpeedKnockup);
            }
            void Register() override
            {
                AfterEffectApply += AuraEffectApplyFn(dc_pylon_buff::Changed, EFFECT_0, SPELL_AURA_ANY,
                                                      AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
                AfterEffectRemove += AuraEffectApplyFn(dc_pylon_buff::Gone, EFFECT_0, SPELL_AURA_ANY,
                                                       AURA_EFFECT_HANDLE_REAL);
            }
        };

        // P2 (pylons.md 6.10): Conduit's pulse. Up to the row's count of the monsters round the wearer,
        // none struck by this wearer inside the rehit window (ConduitPick). Outside a Greater Rift a strike is a skill
        // hit (ComputeHit at the row's weapon damage, crits and the sheet's multipliers); in one it is a share of the
        // monster's normal Life, whatever the gear (GreaterStrike). In both a Guardian or a boss takes it times its row
        // (ConduitDamage).
        struct Struck : DataMap::Base
        {
            std::map<ObjectGuid, std::uint32_t> at;
        };

        void ConduitPulse(Player* player)
        {
            std::vector<Unit*> const near = Enemies(player, Shells::PylonConduitStrike, player->GetPosition(),
                                                    Tune("pylon_conduit_radius_yards"));
            std::vector<ObjectGuid> guids;
            for (Unit* unit : near)
                guids.push_back(unit->GetGUID());
            auto const picked = ConduitPick(guids, player->CustomData.GetDefault<Struck>("DCPylonConduit")->at,
                                            getMSTime(), Tune("pylon_conduit_rehit_seconds") * 1000,
                                            Tune("pylon_conduit_targets"));
            bool const greater = DC::Rifts::GreaterRiftLevel(player->FindMap()) > 0;
            for (std::size_t index : picked)
            {
                Unit* target = near[index];
                Creature* creature = target->ToCreature();
                bool const boss = creature && (creature->isWorldBoss() || creature->IsDungeonBoss() ||
                                               DC::Rifts::IsGuardianEntry(creature->GetEntry()));
                Hit hit;
                double share = 0;
                if (greater)
                {
                    hit.school = SPELL_SCHOOL_MASK_NATURE; // the strike's record: Lightning
                    hit.skillName = "Dimensional Conduit";
                    share = GreaterStrike(double(target->GetMaxHealth()), DC::Rifts::EliteLifeFactor(creature),
                                          Tune("pylon_conduit_greater_life_min_pct"),
                                          Tune("pylon_conduit_greater_life_max_pct"), rand_norm());
                }
                else if (!ComputeHit(player, target, Shells::PylonConduitStrike, hit,
                                     Tune("pylon_conduit_weapon_damage_pct")))
                    continue;
                hit.total = ConduitDamage(greater, hit.total, share, boss, Tune("pylon_conduit_boss_factor"));
                DealHit(player, target, Shells::PylonConduitStrike, hit, greater);
            }
        }

        // 6.9 (a): Speed's knock-up. Each monster in reach of the moving wearer gets the stock knockback (which spares
        // bosses, giants, the knockback-immune and the rooted itself); a Guardian never. The damage row starts empty.
        void KnockUp(Player* player)
        {
            bool const moving = player->isMoving();
            if (!moving)
                return;
            bool const damage = DC::Tunables::Has("combat", "pylon_speed_knockup_weapon_damage_pct");
            for (Unit* target : Enemies(player, Shells::PylonSpeedThrow, player->GetPosition(),
                                        Tune("pylon_speed_knockup_reach_yards")))
            {
                Creature* creature = target->ToCreature();
                if (!KnocksUp(moving, creature && DC::Rifts::IsGuardianEntry(creature->GetEntry()),
                              target->HasUnitState(UNIT_STATE_ROOT)))
                    continue;
                player->CastSpell(target, Shells::PylonSpeedThrow, true);
                Hit hit;
                if (damage && ComputeHit(player, target, Shells::PylonSpeedThrow, hit,
                                         Tune("pylon_speed_knockup_weapon_damage_pct")))
                    DealHit(player, target, Shells::PylonSpeedThrow, hit);
            }
        }

        // Conduit's buff and Speed's knock-up aura: the stock periodic dummy, ticking here. Inactive while the wearer is
        // dead (D15: "persist through death, but are inactive while dead").
        class dc_pylon_tick final : public AuraScript
        {
            PrepareAuraScript(dc_pylon_tick);
            void Tick(AuraEffect const*)
            {
                Player* player = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr;
                if (!player || !player->IsAlive())
                    return;
                if (GetId() == Shells::PylonSpeedKnockup)
                    KnockUp(player);
                else
                    ConduitPulse(player);
            }
            void Register() override
            {
                OnEffectPeriodic += AuraEffectPeriodicFn(dc_pylon_tick::Tick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
            }
        };

        class Update final : public PlayerScript
        {
        public:
            Update() : PlayerScript("dc_pylons_update", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_PLAYER_JUST_DIED, PLAYERHOOK_ON_PLAYER_RESURRECT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }
            void OnPlayerUpdate(Player* player, uint32) override
            {
                if (StateOf(player)->dirty)
                    Reconcile(player);
            }
            void OnPlayerJustDied(Player* player) override
            {
                StateOf(player)->dirty = true;
            }
            void OnPlayerResurrect(Player* player, float, bool&) override
            {
                StateOf(player)->dirty = true;
            }
            // P3: a player who arrives on a map hears what stands there (also at login).
            void OnPlayerMapChanged(Player* player) override
            {
                List(player);
            }
        };

        class Command final : public CommandScript
        {
        public:
            Command() : CommandScript("dc_pylons_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable pylon = {{"buff", Buff, SEC_GAMEMASTER, Console::No},
                                                 {"spawn", SpawnHere, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable dc = {{"pylon", pylon}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }
            // "Conduit" for Kind::Conduit, for the success lines.
            static std::string Title(Kind kind)
            {
                std::string name = Names[static_cast<unsigned>(kind)];
                name[0] = char(name[0] - 'a' + 'A');
                return name;
            }
            static std::optional<Kind> KindNamed(ChatHandler* handler, std::string const& kindName)
            {
                auto const kind = Parse(kindName);
                if (!kind)
                {
                    std::string list;
                    for (char const* name : Names)
                        list += std::string(list.empty() ? "" : ", ") + name;
                    handler->PSendSysMessage("Unknown kind '{}'. Kinds: {}", kindName, list);
                }
                return kind;
            }
            // .dc pylon spawn <kind>: the object at the GM's feet, on dev, to pick the looks and try the click (4.6).
            static bool SpawnHere(ChatHandler* handler, std::string kindName)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                auto const kind = KindNamed(handler, kindName);
                if (!kind)
                    return true;
                if (!Spawn(player->GetMap(), *kind, player->GetPosition()))
                    handler->PSendSysMessage("No {} object: gameobject {} is missing (apply combat_0054_pylon_objects.sql).",
                                             kindName, ObjectEntry(*kind));
                else // say so, or on dev it looks as if nothing happened
                    handler->PSendSysMessage("{} spawned at your feet.", Title(*kind));
                return true;
            }
            // .dc pylon buff <kind>: the buff without an object, on dev, to try each kind (4.6).
            static bool Buff(ChatHandler* handler, std::string kindName)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                auto const kind = KindNamed(handler, kindName);
                if (!kind)
                    return true;
                if (!Give(player, *kind))
                    handler->PSendSysMessage("The {} buff was not given (no record, no seconds in its tunable row, or the core refused it).",
                                             kindName);
                else
                    handler->PSendSysMessage("{} buff given ({} s).", Title(*kind), Tune(Row(*kind, "seconds")));
                return true;
            }
        };
    } // namespace

    bool Wearing(Player const* player, Kind kind)
    {
        std::uint32_t const record = RecordOf(kind);
        return player && record && Active(player->IsAlive(), player->HasAura(record));
    }

    bool Shielded(Unit const* unit)
    {
        Player const* player = unit ? unit->ToPlayer() : nullptr;
        return player && Wearing(player, Kind::Shield);
    }

    void Multipliers(Player const* player, Factors& out)
    {
        PowerFactor(Wearing(player, Kind::Power), Tune(Row(Kind::Power, "damage_pct")), out);
    }

    double ExperiencePct(Player const* player)
    {
        return Wearing(player, Kind::Enlightened) ? Tune(Row(Kind::Enlightened, "xp_pct")) : 0.0;
    }

    void Reconcile(Player* player)
    {
        State* state = StateOf(player);
        state->dirty = false;
        unsigned worn = 0;
        for (unsigned i = 0; i < KindCount; ++i)
            if (Wearing(player, static_cast<Kind>(i)))
                worn |= 1u << i;
        if (state->known && worn == state->worn)
            return;
        std::uint64_t const guid = player->GetGUID().GetRawValue();
        bool const modifiers = Settle(
            state->known, state->worn, worn, [](Kind kind) { return RecordOf(kind); },
            [](std::string const& row) { return Tune(row); },
            [guid](Stat stat, std::uint64_t id) { Stats::RemoveContribution(guid, Source::Temporary, stat, id); },
            [guid](Contribution const& contribution) { Stats::AddContribution(guid, contribution); });
        state->worn = worn;
        state->known = true;
        // The class's own cost and cooldown auras are rebuilt from the sheet and recompute it (dc_passives.cpp).
        if (modifiers)
            Passives::RefreshModifiers(player);
        else
            Stats::Recompute(player);
    }

    bool Give(Player* target, Kind kind)
    {
        std::uint32_t const record = RecordOf(kind);
        double const own = Tune(Row(kind, "seconds"));
        if (!target || !record || own <= 0)
            return false;
        // Gloves of Worship: a shrine effect lasts the worn power's seconds when that is more than its own; a pylon keeps its time.
        double const seconds = IsPylon(kind) ? own : ItemPowers::ShrineSeconds(target, own);
        // A shrine's record is not death-persistent: the core would hold it unapplied and put it on at the revive.
        if (!IsPylon(kind) && !target->IsAlive())
            return false;
        // The same kind again restarts its time: take the old one off, put a new one on.
        target->RemoveAurasDueToSpell(record);
        Aura* aura = target->AddAura(record, target);
        if (!aura)
            return false;
        aura->SetMaxDuration(static_cast<int32>(seconds * 1000));
        aura->SetDuration(static_cast<int32>(seconds * 1000));
        if (kind == Kind::Empowered)
            // The record carries the stock percent regeneration aura; its amount follows the row.
            for (unsigned slot = 0; slot < MAX_SPELL_EFFECTS; ++slot)
                if (AuraEffect* effect = aura->GetEffect(slot))
                    if (effect->GetAuraType() == SPELL_AURA_MOD_POWER_REGEN_PERCENT)
                        effect->ChangeAmount(static_cast<int32>(Tune(Row(kind, "regeneration_pct"))));
        if (kind == Kind::Channeling)
            target->RemoveAllSpellCooldown();
        // P2 (6.9): Speed's knock-up is its own aura for the same time (taking Speed off above took the old one).
        if (kind == Kind::Speed)
            if (Aura* knockUp = target->AddAura(Shells::PylonSpeedKnockup, target))
            {
                knockUp->SetMaxDuration(static_cast<int32>(seconds * 1000));
                knockUp->SetDuration(static_cast<int32>(seconds * 1000));
            }
        Reconcile(target);
        return true;
    }

    bool GiveRandomShrine(Player* target, double roll)
    {
        return Give(target, RandomShrine(roll));
    }

    GameObject* Spawn(Map* map, Kind kind, Position const& at)
    {
        if (!map)
            return nullptr;
        float const o = at.GetOrientation();
        GameObject* object = map->SummonGameObject(ObjectEntry(kind), at.GetPositionX(), at.GetPositionY(),
                                                   at.GetPositionZ(), o, 0, 0, std::sin(o / 2), std::cos(o / 2), 0);
        if (!object)
            return nullptr;
        map->CustomData.GetDefault<Standing>("DCPylons")->objects.push_back(object->GetGUID());
        for (auto const& ref : map->GetPlayers())
            if (Player* player = ref.GetSource())
                Tell(player, object);
        return object;
    }

    void RegisterScripts()
    {
        new Update();
        new Command();
        new Objects();
        // The addon asks for the list after a /reload (docs/contracts/pylon-messages.md).
        DC::Bridge::Routes().Add(Prefix, {"combat", "pylon_list_burst", "pylon_list_per_second"},
                                 [](Player& player, DC::Bridge::Request const& request, DC::Bridge::Wire<Player> const&) {
                                     auto const verb = request.Token(0, 1);
                                     if (!verb || *verb != "L" || request.Count() != 1)
                                         throw DC::Bridge::Refusal(DC::Bridge::TextMalformed);
                                     List(&player);
                                 });
        RegisterSpellScript(dc_pylon_buff);
        RegisterSpellScript(dc_pylon_tick);
    }
} // namespace DC::Combat::Pylons
