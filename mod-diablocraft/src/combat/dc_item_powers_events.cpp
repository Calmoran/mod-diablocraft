#include "dc_item_powers_internal.h"
#include "dc_chest_open_math.h"

// The item powers' events: what the hit, the cast, the kill, the block and the damage taken tell the rows, and the scripts that listen for them.

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // The first Refresh after login (Items::Apply on each worn item) fills the count; logout empties it. A kill is an event.
        // Dark Mage's Shade: the damage about to be dealt to a player, the moment the `life_below` event is judged (N-LIFEEV).
        class LifeEvents final : public UnitScript
        {
        public:
            LifeEvents() : UnitScript("dc_item_power_life_events", true, {UNITHOOK_ON_DAMAGE}) { }
            void OnDamage(Unit*, Unit* victim, std::uint32_t& damage) override
            {
                if (victim)
                    Damaged(victim->ToPlayer(), damage);
            }
        };

        // N-CHEST (Harrington Waistguard): a player opening a chest is that player's `chest` event, once per opening. The core sets a chest to
        // GO_ACTIVATED with the opener as the user when the loot is generated, and again, with the releasing player, every time a chest that is not yet
        // empty is closed; only the change into GO_ACTIVATED from another state is an opening (ChestOpen::Openings), so a half-looted chest closed
        // and reopened, or closed by a second player, starts nothing. The chest is forgotten when it leaves the world.
        class ChestEvents final : public AllGameObjectScript
        {
        public:
            ChestEvents() : AllGameObjectScript("dc_item_power_chest_events") { }
            void OnGameObjectLootStateChanged(GameObject* go, uint32 state, Unit* user) override
            {
                if (!go || go->GetGoType() != GAMEOBJECT_TYPE_CHEST || !Data().events.count("chest"))
                    return;
                bool opened;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    opened = openings.Changed(KeyOf(go), state == GO_ACTIVATED);
                }
                if (!opened)
                    return;
                if (Player* opener = user ? user->ToPlayer() : nullptr)
                    Fire(opener, "chest", "", 1.0);
            }
            void OnGameObjectRemoveWorld(GameObject* go) override
            {
                if (!go || go->GetGoType() != GAMEOBJECT_TYPE_CHEST)
                    return;
                std::lock_guard<std::mutex> lock(mutex);
                openings.Forget(KeyOf(go));
            }

        private:
            static ChestOpen::Key KeyOf(GameObject const* go)
            {
                return {go->GetMapId(), go->GetInstanceId(), go->GetGUID().GetRawValue()};
            }
            ChestOpen::Openings openings;
        };

        // N-STUN: a control aura a player put on a monster, any skill's or item's (Hellrack's root, a skill's stun and freeze, Blinding Flash's blind),
        // is that player's `control_<kind>` event with the monster as its target (ItemPower::ControlEvent names the kind). The hook runs for a new aura
        // and for one refreshed or stacked again, so each application counts.
        class ControlEvents final : public UnitScript
        {
        public:
            ControlEvents() : UnitScript("dc_item_power_control_events", true, {UNITHOOK_ON_AURA_APPLY}) { }
            void OnAuraApply(Unit* unit, Aura* aura) override
            {
                if (!unit || !aura || !Data().controls || unit->IsPlayer())
                    return;
                Unit* caster = aura->GetCaster();
                Player* player = caster ? caster->ToPlayer() : nullptr;
                if (!player)
                    return;
                SpellInfo const* info = aura->GetSpellInfo();
                bool stun = false, confuse = false, root = false;
                for (SpellEffectInfo const& effect : info->Effects)
                {
                    stun = stun || effect.ApplyAuraName == SPELL_AURA_MOD_STUN;
                    confuse = confuse || effect.ApplyAuraName == SPELL_AURA_MOD_CONFUSE;
                    root = root || effect.ApplyAuraName == SPELL_AURA_MOD_ROOT;
                }
                bool const freeze = (info->GetAllEffectsMechanicMask() & (1u << MECHANIC_FREEZE)) != 0;
                char const* event = ItemPower::ControlEvent(info->Id, stun, freeze, confuse, root);
                if (*event)
                    Fire(player, event, "", 1.0, unit);
            }
        };

        // Dovu Energy Trap: a stun aura the player casts takes its record's duration here (Smite, Throwing Hammer, Death from Above, the stun
        // records of Ground Stomp and Seismic Slam), stretched by StunFactor. A stun is a MOD_STUN aura of mechanic Stun; stock Ice Blast is
        // Torment's freeze hold (mechanic Stun on the record), so it is left out, and Wall of Light, which holds with it as a stun, stretches its
        // own seconds. A site that sets its seconds after AddAura overwrites this, and multiplies by StunFactor itself.
        class StunDurations final : public AllSpellScript
        {
        public:
            StunDurations() : AllSpellScript("dc_item_power_stun_durations", {ALLSPELLHOOK_ON_CALC_MAX_DURATION}) { }
            void OnCalcMaxDuration(Aura const* aura, int32& maxDuration) override
            {
                SpellInfo const* info = aura->GetSpellInfo();
                if (maxDuration <= 0 || info->Id == IceBlastHold || !info->HasAura(SPELL_AURA_MOD_STUN) ||
                    !(info->GetAllEffectsMechanicMask() & (1ULL << MECHANIC_STUN)))
                    return;
                if (Unit* caster = aura->GetCaster(); caster && caster->IsPlayer())
                    maxDuration = ItemPower::StunMilliseconds(maxDuration, StunFactor(caster->ToPlayer()));
            }

        private:
            static constexpr std::uint32_t IceBlastHold = 15878;
        };
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat::ItemPowers
{
    void Blocked(Player* player, Unit* attacker)
    {
        // The enemy that struck is the event's target (Freeze of Deflection freezes it); a block with none fires for the wearer alone.
        Fire(player, "block", "", 1.0, attacker);
    }

    void Hurt(Player const* player)
    {
        if (!player)
            return;
        std::lock_guard<std::mutex> lock(mutex);
        Clock& clock = clocks[player->GetGUID().GetRawValue()];
        clock.hurt = true;
        clock.lastHurt = getMSTime();
    }

    void ChannelStarted(Player const* player, std::string const& skill)
    {
        if (!player)
            return;
        std::lock_guard<std::mutex> lock(mutex);
        ItemPower::Span& span = clocks[player->GetGUID().GetRawValue()].channels[skill];
        span.start = getMSTime();
        span.running = true;
    }

    void ChannelEnded(Player const* player, std::string const& skill)
    {
        if (!player)
            return;
        std::lock_guard<std::mutex> lock(mutex);
        auto mine = clocks.find(player->GetGUID().GetRawValue());
        if (mine == clocks.end())
            return;
        auto span = mine->second.channels.find(skill);
        if (span != mine->second.channels.end() && span->second.running)
        {
            span->second.running = false;
            span->second.end = getMSTime();
        }
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        auto const skill = Shells::FindAbility(spellId);
        if (!player || !skill)
            return;
        EnemyStackPress(player, skill->skill);
        NextAttackPressed(player);
        Fire(player, "cast", skill->skill, 1.0);
        // Lut Socks: a cast the window keeps open has no cooldown, so there is none to cut.
        if (ReuseCast(player, spellId, skill->skill))
            return;
        // In-geom: the skill's cooldown, installed before this hook (Spell::cast sends it first), is shorter by the seconds that are on. Only
        // a cooldown the skill's record states: a primary's swing and a charge are not one.
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info || !(info->RecoveryTime || info->CategoryRecoveryTime) || Classes::CategoryOf(spellId) == "Primary")
            return;
        // Gesture of Orpheus (N-CD): the cooldown the core installed is cut to the factor's share, the same factor
        // Combat::SkillCooldownMilliseconds applies, so the button and every cooldown the module starts agree.
        if (double const factor = CooldownFactor(player, skill->skill); factor < 1.0)
            if (std::uint32_t const left = player->GetSpellCooldownDelay(spellId))
                Abilities::ReduceSkillCooldown(player, skill->skill, left * (1.0 - factor));
        double const cut = CooldownCut(player);
        if (cut > 0)
            Abilities::ReduceSkillCooldown(player, skill->skill, cut * 1000.0);
    }

    // The yards are read the way DistanceFactor reads them, before the lock.
    void StormArmorShock(Player* player, Unit* target)
    {
        if (player && target)
            Fire(player, "storm_armor_shock", "", 1.0, target, 0, player->GetDistance(target));
    }

    void Exploded(Player* player, Unit* enemy, std::string const& skill)
    {
        if (player && enemy)
            Fire(player, "explosion", skill, 1.0, enemy);
    }

    // A skill's number is the spell record's, a rune answers with its skill's (Numbers::Get). A hit that states no proc coefficient cannot
    // proc (dc_proc_math.h): a chance of less than 100 scales by it, a certain effect does not roll.
    // Tal Rasha's Elements: the hit's element is an event of its own, only for the four elements the set reads.
    void HitElement(Player* player, Unit* target, unsigned school)
    {
        if (player && Data().events.count("hit_element"))
            if (char const* element = ElementOfSchool(school))
                Fire(player, "hit_element", element, 1.0, target);
    }

    void Hit(Player* player, Unit* target, std::uint32_t spellId)
    {
        if (!player || !spellId || !Data().events.count("hit"))
            return;
        auto const coefficient = Combat::ProcCoefficient(spellId);
        double const scale = coefficient && *coefficient > 0 ? *coefficient : 0;
        std::string const name = Shells::FindAbility(spellId) ? Shells::FindAbility(spellId)->skill : "";
        Fire(player, "hit", name, scale, target);
    }

    // Once per cast or channel tick that hit (Combat::Connected), not per enemy: the Obsidian Ring of the Zodiac cuts one cooldown a cast
    // however many enemies it reaches. `enemies` is how many it hit, 0 when the caller does not count.
    void Attack(Player* player, std::uint32_t spellId, unsigned enemies)
    {
        if (player)
            NextAttackConnected(player, spellId);
        if (player)
            EnemyStackConnect(player, spellId, enemies);
        if (!player || !spellId || !(Data().events.count("hit_spender") || Data().events.count("hit_generator")))
            return;
        auto const cost = Numbers::Get(spellId, "cost_resource"), generated = Numbers::Get(spellId, "generated_resource"),
                   coefficient = Combat::ProcCoefficient(spellId);
        ItemPower::HitKind const kind =
            ItemPower::HitKinds(Classes::CategoryOf(spellId) == "Primary", cost.value_or(0), generated.value_or(0));
        double const scale = coefficient && *coefficient > 0 ? *coefficient : 0;
        std::string const name = Shells::FindAbility(spellId) ? Shells::FindAbility(spellId)->skill : "";
        if (kind.generator)
            Fire(player, "hit_generator", name, scale, nullptr, enemies);
        if (kind.spender)
            Fire(player, "hit_spender", name, scale, nullptr, enemies);
    }

    void Spent(Player* player, double fury)
    {
        if (!player || fury <= 0 || !Data().events.count("resource_spent"))
            return;
        std::vector<ItemPower::Fired> fired;
        ItemPower::Situation seen = Seen(player);
        {
            std::lock_guard<std::mutex> lock(mutex);
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            if (!clocks.count(guid) && !counts.count(guid))
                return;
            fired = ItemPower::SpentFires(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)), fury, clocks[guid].spentCarry);
        }
        // Outside the lock: the cooldowns are the ability code's. Immortal King's Call 4-piece cuts the named skills (every rune of each).
        for (ItemPower::Fired const& one : fired)
            if (one.stat == "cooldown_cut_named_seconds")
            {
                std::stringstream names(one.skill);
                for (std::string name; std::getline(names, name, ';');)
                    Abilities::ReduceSkillCooldown(player, name.c_str(), one.value * 1000.0);
            }
    }

    void Taken(Player* player)
    {
        // A monster's hit is a proc coefficient of 1 (D3: an on-being-hit chance is not scaled).
        Fire(player, "taken", "", 1.0);
    }

    void TakenElement(Player* player, unsigned school, double damage)
    {
        // Every hit on every player passes here: nothing to look at unless some row waits for an element's damage.
        if (!player || damage <= 0 || !Data().events.count("taken_element"))
            return;
        char const* element = ElementOfSchool(school);
        double const most = static_cast<double>(player->GetMaxHealth());
        if (!element || most <= 0)
            return;
        // The hook runs before the damage is dealt: Life is still the Life before it.
        double const health = static_cast<double>(player->GetHealth());
        Fire(player, "taken_element", element, 1.0, nullptr, 0, 0.0, 100.0 * health / most, 100.0 * (health - std::min(damage, health)) / most);
    }

    void Damaged(Player* player, std::uint32_t damage)
    {
        // Every hit on every player passes here: nothing to look at unless some row waits for Life to fall.
        if (!player || !damage || !Data().events.count("life_below"))
            return;
        // A killing hit leaves no Life to protect. The hook runs before the damage is dealt, so Life is still the Life before it.
        if (damage >= player->GetHealth() || player->GetMaxHealth() == 0)
            return;
        double const most = static_cast<double>(player->GetMaxHealth());
        Fire(player, "life_below", "", 1.0, nullptr, 0, 0.0, 100.0 * player->GetHealth() / most, 100.0 * (player->GetHealth() - damage) / most);
    }

    void Fatal(Player* player, std::uint32_t& damage)
    {
        // Every hit on every player passes here: nothing to look at unless some row waits for a fatal one.
        if (!player || !Data().events.count("fatal") || !ItemPower::IsFatal(damage, player->GetHealth()))
            return;
        Saved() = false;
        Fire(player, "fatal", "", 1.0);
        if (Saved())
        {
            Saved() = false;
            damage = 0;
        }
    }

    void Landed(Player* player, std::uint32_t spellId)
    {
        if (auto const skill = Shells::FindAbility(spellId))
            Fire(player, "land", skill->skill, 1.0);
    }

    void ImageDied(Player* player, Unit* image)
    {
        Fire(player, "image_death", "", 1.0, image);
    }
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        void RegisterEventScripts()
        {
            new LifeEvents();
            new StunDurations();
            new ControlEvents();
            new ChestEvents();
        }
    } // namespace Detail
} // namespace DC::Combat
