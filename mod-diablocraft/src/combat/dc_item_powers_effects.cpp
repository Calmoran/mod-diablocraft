#include "dc_item_powers_internal.h"
#include "dc_charm_effect.h"
#include "dc_movement_effects.h"

// The item powers' `effect` kind: the executor of a fired row and the effects it does that no other kind owns.

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // Arreat's Law: a Weapon Throw hit gives up to `most` points of the primary resource by the yards to the enemy, and may take it
        // past the maximum: the first gain puts the item's `resource_over_cap` points on the sheet's maximum (a Temporary contribution, kept by every
        // recompute); an Ancient Spear hit takes them off, which sends the resource back to its base maximum, then refunds by the same distance.
        void ByDistance(Player* player, Unit* target, ItemPower::Row const& row, double most, bool refund)
        {
            Resources::Resource const* resource = Resources::Of(Classes::ClassIdOf(player));
            if (!resource)
                return;
            double const points = ItemPower::DistanceShare(most, player->GetDistance(target),
                                                           ItemPower::OwnerNumber(Data().rows, row.owner, "player", "resource_distance_yards"));
            double const over = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "resource_over_cap");
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            bool changed;
            {
                std::lock_guard<std::mutex> lock(mutex);
                changed = refund ? raised.erase(guid) != 0 : raised.insert(guid).second;
            }
            if (changed)
            {
                if (refund)
                    Stats::RemoveContribution(guid, Source::Temporary, Stat::MaxFury, OverCapId);
                else
                    Stats::AddContribution(guid, {Source::Temporary, Stat::MaxFury, OverCapId, over, Bucket::Flat});
                Stats::Recompute(player);
            }
            Resources::Add(player, *resource, points);
        }

        // N-STUN (Hellrack): puts the stock control `hold` (ItemPower::ControlSpell) on the enemy for `seconds`, as a skill's holds go
        // on (dc_monk.cpp Freeze): the player's own hold taken off first, so a new fire starts the whole time again and is a fresh application, which the
        // `control_*` events see. An enemy immune to the control refuses it (AddAura answers nothing).
        void Control(Player* player, Unit* target, std::uint32_t hold, double seconds)
        {
            if (!hold || seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(hold, player->GetGUID());
            if (Aura* aura = player->AddAura(hold, target))
            {
                aura->SetMaxDuration(static_cast<std::int32_t>(seconds * 1000.0));
                aura->SetDuration(static_cast<std::int32_t>(seconds * 1000.0));
            }
        }

        // N-HEAL (Vambraces of Sescheron): the `heal_missing_life_pct` row, fired by `hit_generator` of the Primary skills it names. The wearer is healed the item's
        // roll of the Life missing (ItemPower::MissingLifeHeal), as a stock Greater Heal record so the log names a heal.
        constexpr std::uint32_t HealRecord = 2060;

        void HealMissing(Player* player, double pct)
        {
            if (!player->IsAlive())
                return;
            double const amount = ItemPower::MissingLifeHeal(pct, static_cast<double>(player->GetHealth()), static_cast<double>(player->GetMaxHealth()));
            SpellInfo const* info = amount >= 1.0 ? sSpellMgr->GetSpellInfo(HealRecord) : nullptr;
            if (!info)
                return;
            HealInfo healing(player, player, static_cast<std::uint32_t>(amount), info, SpellSchoolMask(info->SchoolMask));
            player->HealBySpell(healing, false);
        }

        // N-ABSGRANT (Wall of Man): the `bone_shield` row, fired on a monster's hit. The item's chance (its roll, scaled by the hit's proc coefficient, Proc::Rolls) puts the
        // item's `damage_reduction_pct` aura on the wearer for `bone_shield_seconds`; while it stands every hit taken is smaller by the item's `buff` row of that stat (one stack,
        // read by IncomingFactor). Then nothing for `bone_shield_cooldown_seconds`, kept here under its own key so a failed roll starts none.
        void BoneShield(Player* player, ItemPower::Row const& row, double chancePct, double coefficient)
        {
            double const seconds = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "bone_shield_seconds");
            double const cooldown = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "bone_shield_cooldown_seconds");
            std::uint32_t const record = Shells::PowerBuffFor(row.owner.c_str(), "damage_reduction_pct");
            if (!player->IsAlive() || !record || seconds <= 0)
                return;
            std::uint32_t const now = getMSTime();
            std::string const key = row.owner + "|shield";
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto& fired = clocks[player->GetGUID().GetRawValue()].fired;
                auto const last = fired.find(key);
                if (!ItemPower::CooldownOver(now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) ||
                    !Proc::Rolls(coefficient, chancePct, [](float pct) { return roll_chance_f(pct); }))
                    return;
                fired[key] = now;
            }
            if (Aura* aura = player->AddAura(record, player))
            {
                aura->SetMaxDuration(static_cast<std::int32_t>(seconds * 1000.0));
                aura->SetDuration(static_cast<std::int32_t>(seconds * 1000.0));
            }
        }

        // N-FEAR (Maloth's Focus): the `fear_enemies` row, fired by the `tick` clock once its cooldown is up. In combat, every enemy within the item's `fear_yards`
        // flees in stock Fear for `seconds` (Control; one that is immune refuses it). With nobody in reach the cooldown is not spent (the row tries again after
        // ItemPower::TriggerCheckSeconds); after a proc that feared someone the next waits up to the item's `fear_cooldown_delta_seconds` more, a fresh draw each time.
        void Frighten(Player* player, ItemPower::Row const& row, double seconds)
        {
            double const yards = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "fear_yards");
            double const delta = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "fear_cooldown_delta_seconds");
            unsigned feared = 0;
            if (yards > 0 && player->IsAlive() && player->IsInCombat())
                for (Unit* enemy : Combat::Enemies(player, ItemPower::FearHold, player->GetPosition(), yards))
                {
                    Control(player, enemy, ItemPower::FearHold, seconds);
                    ++feared;
                }
            std::uint32_t const now = getMSTime();
            std::lock_guard<std::mutex> lock(mutex);
            clocks[player->GetGUID().GetRawValue()].fired[ItemPower::FireKey(row)] =
                feared ? ItemPower::DelayedStamp(now, delta, rand_norm()) : ItemPower::RetryStamp(now, row.icdSeconds, ItemPower::TriggerCheckSeconds);
        }

        // N-PULLFX (The Butcher's Sickle): the `pull_enemy` row, fired on a hit of any skill. If the enemy the hit struck is within the item's `pull_yards` and the
        // item's cooldown (`pull_cooldown_seconds`, kept here under its own key so a failed roll starts none) is over, the item's chance (scaled by the hit's proc
        // coefficient, Proc::Rolls: a hit that states none never procs) drags it to the wearer (Abilities::Pull) and holds it stunned for `pull_stun_seconds`.
        // N-CHARM (The Tormentor): the record the shared charm picks the charmed monster's first enemy by, stock "Gnomish Mind Control Cap" (the charm's own donor).
        constexpr std::uint32_t CharmRecord = 26740;

        constexpr std::uint32_t DragRecord = 49576; // stock "Death Grip": Physical; the log's name and school only

        void Drag(Player* player, Unit* target, ItemPower::Row const& row, double chancePct, double coefficient)
        {
            if (!player->IsAlive() || !target || target == player || !target->IsAlive())
                return;
            double const yards = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "pull_yards");
            double const stun = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "pull_stun_seconds");
            double const cooldown = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "pull_cooldown_seconds");
            double const damage = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "pull_damage");
            double const delta = ItemPower::OwnerNumber(Data().rows, row.owner, "player", "pull_damage_delta");
            std::uint32_t const now = getMSTime();
            std::string const key = row.owner + "|drag";
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto& fired = clocks[player->GetGUID().GetRawValue()].fired;
                auto const last = fired.find(key);
                if (!ItemPower::DragReady(player->GetExactDist(target), yards, now, last != fired.end(), last != fired.end() ? last->second : 0, cooldown) ||
                    !Proc::Rolls(coefficient, chancePct, [](float pct) { return roll_chance_f(pct); }))
                    return;
                fired[key] = now;
            }
            // The hook's damage first, as the wearer's under the stock "Death Grip" record (its name and school in the log; no damage multipliers: the power file's
            // number as it stands), then the drag and the stun on what is left alive.
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(DragRecord))
            {
                Combat::Hit hit;
                hit.skillName = "The Butcher's Sickle";
                hit.school = info->SchoolMask;
                hit.total = ItemPower::DragDamage(damage, delta, rand_norm());
                if (hit.total > 0)
                    Combat::DealHit(player, target, DragRecord, hit, true);
            }
            if (!target->IsAlive())
                return;
            Abilities::Pull(target, player->GetPosition());
            Control(player, target, ItemPower::FreezeHold, stun * ItemPowers::StunFactor(player));   // Torment's stun hold (stock 15878); StunFactor stretches it as at every site that sets its own seconds
        }

        // Bul-Kathos's Wedding Band (N-CLOCK): one pulse of `drain_life`, fired by the `tick` clock. Only in combat, as the gems'
        // auras of the player's reach: a drain is for a fight and should not pull what has not noticed the player. Each enemy within
        // combat.bul_kathos_drain_radius_yards loses `pct` percent of its maximum Life, at most bul_kathos_drain_max_weapon_damage x the
        // main hand's average weapon damage (ItemPower::DrainPulse), dealt as the player's under the stock "Drain Life" record as it stands (no
        // damage multipliers: the share of Life is the number); the player is healed what was drained, at most bul_kathos_drain_max_heal_pct
        // percent of its maximum Life. A blank tunable reads 0: no reach, no cap, no heal.
        constexpr std::uint32_t DrainRecord = 18817; // stock "Drain Life": HEALTH_LEECH, Shadow, no class family; the log's name and school only

        double Tune(char const* name)
        {
            return DC::Tunables::Has("combat", name) ? DC::Tunables::Get("combat", name) : 0.0;
        }

        void Drain(Player* player, double pct)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(DrainRecord);
            double const radius = Tune("bul_kathos_drain_radius_yards");
            if (!info || radius <= 0 || !player->IsAlive() || !player->IsInCombat())
                return;
            std::vector<Unit*> const enemies = Combat::Enemies(player, DrainRecord, player->GetPosition(), radius);
            if (enemies.empty())
                return;
            std::vector<double> most;
            for (Unit* enemy : enemies)
                most.push_back(static_cast<double>(enemy->GetMaxHealth()));
            auto const range = Combat::WeaponRange(player, false);
            double weapon = (range.first + range.second) / 2.0;
            if (auto const sheet = Stats::Get(player->GetGUID().GetRawValue()))
                weapon += (*sheet)[Stat::WeaponFlatDamage];
            ItemPower::Drained const pulse = ItemPower::DrainPulse(most, pct, weapon, Tune("bul_kathos_drain_max_weapon_damage"),
                                                                   static_cast<double>(player->GetMaxHealth()), Tune("bul_kathos_drain_max_heal_pct"));
            for (std::size_t i = 0; i < enemies.size(); ++i)
            {
                Combat::Hit hit;
                hit.skillName = "Drain Life";
                hit.school = info->SchoolMask;
                hit.total = pulse.taken[i];
                Combat::DealHit(player, enemies[i], DrainRecord, hit, true);
            }
            if (std::uint32_t const amount = static_cast<std::uint32_t>(std::llround(pulse.healed)))
            {
                HealInfo heal(player, player, amount, info, SpellSchoolMask(info->SchoolMask));
                player->HealBySpell(heal, false);
            }
        }

        // N-MONSLOW (Jang's Envelopment): slows the enemy by `pct` for `seconds` through the stock snare ItemPower::SlowHold, as a
        // skill's own slows go on: the player's own snare taken off first, so a new hit starts the whole time again, then
        // the aura's amount set to the percent. An enemy immune to snares refuses it (AddAura answers nothing).
        void Slow(Player* player, Unit* target, double pct, double seconds)
        {
            if (seconds <= 0 || pct <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(ItemPower::SlowHold, player->GetGUID());
            if (Aura* aura = player->AddAura(ItemPower::SlowHold, target))
            {
                if (AuraEffect* effect = aura->GetEffect(EFFECT_0))
                    effect->ChangeAmount(ItemPower::SlowAmount(pct));
                aura->SetMaxDuration(static_cast<std::int32_t>(seconds * 1000.0));
                aura->SetDuration(static_cast<std::int32_t>(seconds * 1000.0));
            }
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // N-FATAL: set by Revive when a `revive_full` row saved the player from the hit being judged; ItemPowers::Fatal reads and clears it.
        bool& Saved()
        {
            thread_local bool saved = false;
            return saved;
        }
    } // namespace Detail
} // namespace DC::Combat

namespace DC::Combat::ItemPowers
{
    namespace
    {
        // Ancestors' Grace: the worn, unbroken item that owns the power is destroyed, then Life and every resource of the player's class go to
        // their maximum. The item goes first, so the maximums are the ones without it. A power with no worn item (a Kanai's Cube copy has none to
        // destroy) saves nobody.
        void Revive(Player* player, std::string const& powerId)
        {
            Item* host = nullptr;
            for (std::uint8_t slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END && !host; ++slot)
                if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot); item && !item->IsBroken())
                    if (auto found = Data().owners.find(item->GetEntry()); found != Data().owners.end() && found->second == powerId)
                        host = item;
            if (!host)
                return;
            player->DestroyItem(host->GetBagSlot(), host->GetSlot(), true);
            player->SetFullHealth();
            std::uint32_t const classId = Classes::ClassIdOf(player);
            for (Resources::Data::Row const& resource : Resources::Data::Rows)
                if (resource.classId == classId)
                    player->SetPower(Resources::Slot(resource), static_cast<int32>(Resources::MaxUnits(player, resource)));
            Saved() = true;
        }
    } // namespace
} // namespace DC::Combat::ItemPowers

namespace DC::Combat
{
    namespace Detail
    {
        // N-MARK (Madawc's Sorrow): on a creature, the players who have hit it while an item that marks first hits was worn.
        struct HitBy : DataMap::Base
        {
            std::set<std::uint64_t> players;
        };

        // An event happened to a player: fire the rows of `event`, then do what the `effect` rows say, outside the lock (the effects reach
        // other systems). `scale` is what a chance is multiplied by (ItemPower::Fire).
        void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,
                  double yards, double lifeBefore, double lifeAfter)
        {
            if (!player || !Data().events.count(event))
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            std::vector<ItemPower::Fired> fired;
            std::vector<std::pair<std::uint32_t, std::int32_t>> shown; // a window that opened: its buff record, its milliseconds
            // Won Khim Lau's Cyclone Strike: D3's text states no cooldown, so it is a tunable (monk.won_khim_lau_cooldown_seconds). Read before the lock, as Seen is.
            double const castCooldown = DC::Tunables::Get("monk", "won_khim_lau_cooldown_seconds");
            // N-CTF: the creature type of the enemy the event is about, for the `target_creature_type` rows (a player or no enemy has none).
            Creature* const markable = target ? target->ToCreature() : nullptr;
            Creature const* const enemy = markable;
            std::string const targetType = enemy ? ItemPower::CreatureTypeName(enemy->GetCreatureType()) : std::string();
            ItemPower::Situation seen = Seen(player);
            {
                std::lock_guard<std::mutex> lock(mutex);
                // Nothing worn that owns a power, no set piece: nothing can fire (the hit events run for every hit of every player).
                if (!clocks.count(guid) && !counts.count(guid))
                    return;
                ItemPower::Situation situation = SituationOf(guid, std::move(seen));
                situation.enemiesHit = enemies;
                situation.targetType = targetType;
                // N-MARK: a hit by a player who wears an item that stuns first hits marks the creature; this one is the first when the player was not on its list
                if (markable && std::string_view(event) == "hit" && Data().marks && ItemPower::MarksFirstHits(Data().rows, CountsOf(guid), situation))
                    situation.firstHit = ItemPower::FirstHit(markable->CustomData.GetDefault<HitBy>("DCItemHitBy")->players, guid);
                situation.eventYards = yards;
                situation.lifeBeforePct = lifeBefore;
                situation.lifeAfterPct = lifeAfter;
                situation.castCooldownSeconds = castCooldown;
                fired = ItemPower::Fire(Data().rows, CountsOf(guid), situation, event, skill, scale,
                                        [](double pct) { return roll_chance_f(static_cast<float>(pct)); });
                for (ItemPower::Row const* row : ItemPower::Opened(Data().rows, situation, event))
                    if (std::uint32_t const id = Shells::PowerBuffFor(row->owner.c_str(), row->stat.c_str()))
                        shown.emplace_back(id, static_cast<std::int32_t>(row->arg * 1000.0));
                clocks[guid].fired = std::move(situation.fired);
            }
            // The buff is what the player sees; the window itself is the `triggered` condition, on the same seconds.
            for (auto const& [id, ms] : shown)
            {
                Aura* aura = player->GetAura(id);
                if (!aura)
                    aura = player->AddAura(id, player);
                if (aura)
                {
                    aura->SetMaxDuration(ms);
                    aura->SetDuration(ms);
                }
            }
            for (ItemPower::Fired const& one : fired)
            {
                if (one.stat == "cooldown_cut_seconds")
                    Abilities::CutRunningCooldown(player, one.value * 1000.0); // the row is seconds, the ability code's is milliseconds
                else if (one.stat == "revive_full" && one.row)
                    Revive(player, one.row->owner); // Ancestors' Grace, on the `fatal` event
                else if (one.stat == "frenzy_stacks")
                    Primaries::GrantFrenzy(player, static_cast<unsigned>(one.value));
                else if (one.stat == "apply_skill" && target)
                    Abilities::ApplySkillBleed(player, target, one.skill.c_str());
                else if (one.stat == "stack_buff" && one.row)
                    StackBuff(player, *one.row, one.value);
                else if (one.stat == "mark_enemy" && target && one.row)
                    MarkEnemy(player, target, *one.row, one.value);
                else if (one.stat == "element_resist" && one.row)
                    ElementBuff(player, one.on, &ItemPower::ElementState::resistUntil, Stat::AllResistance, Bucket::Percent, ElementResistId, one.value,
                                static_cast<std::uint32_t>(one.row->stackSeconds * 1000.0));
                else if (one.stat == "element_window" && one.row)
                    ElementWindowHit(player, one.on, *one.row);
                else if (one.stat == "element_meteor")
                    ElementMeteor(player, target, one.on);
                else if (one.stat == "cooldown_cut_named_seconds")
                {
                    std::stringstream names(one.skill);
                    for (std::string name; std::getline(names, name, ';');)
                        Abilities::ReduceSkillCooldown(player, name.c_str(), one.value * 1000.0);
                }
                else if ((one.stat == "resource_by_distance" || one.stat == "resource_refund_by_distance") && target && one.row)
                    ByDistance(player, target, *one.row, one.value, one.stat == "resource_refund_by_distance");
                else if (one.stat == "multiply_image" && target)
                {
                    // Archmage's Vicalyke: the chance is a tunable, wizard.archmages_vicalyke_multiply_chance_pct (default 50; blank: never)
                    double const chance = DC::Tunables::Has("wizard", "archmages_vicalyke_multiply_chance_pct")
                        ? DC::Tunables::Get("wizard", "archmages_vicalyke_multiply_chance_pct") : 0.0;
                    if (ItemPower::ImageMultiplies(chance, [](double pct) { return roll_chance_f(static_cast<float>(pct)); }))
                        Wizard::MultiplyImage(player, target);
                }
                else if (one.stat == "cost_free_seconds")
                    OpenCostFree(player, one.value);
                else if (one.stat == "next_attack_pct" && one.row)
                    ArmNextAttack(player, one.row->owner, one.value); // Blood Brother, on the `block` event
                else if (one.stat == "cast_skill")
                    CastSkill(player, one.skill); // Dark Mage's Shade's Diamond Skin, Might of the Earth's Earthquake: by code, as the rune on the bar
                else if (one.stat == "root_seconds" && target)
                    Control(player, target, ItemPower::ControlSpell(one.stat), one.value); // Hellrack: the root on the enemy the hit struck
                else if (one.stat == "stun_seconds" && target)
                    Control(player, target, ItemPower::ControlSpell(one.stat), one.value * StunFactor(player)); // Madawc's Sorrow: the stun, stretched by the stun-duration powers as at every site that sets its own seconds
                else if (one.stat == "drain_life")
                    Drain(player, one.value); // Bul-Kathos's Wedding Band, on the `tick` clock
                else if (one.stat == "burn_trail" && one.row)
                    // Fire Walkers, on the `tick` clock: the row's icd_seconds is the interval the fire is dropped at
                    ItemTrail::Burn(player, one.row->owner, one.value, one.row->icdSeconds);
                else if (one.stat == "thorns_on_attack_pct" && target)
                {
                    // Hack: the share of the player's own Thorns damage, dealt to the enemy this hit landed on (Stats::ThornsHit)
                    if (auto const sheet = Stats::Get(player->GetGUID().GetRawValue()))
                        Stats::ThornsHit(player, target, ItemPower::ThornsShare((*sheet)[Stat::Thorns], one.value));
                }
                else if (one.stat == "summon_herd")
                    // Bovine Bardiche: the chance (scaled by this hit's proc coefficient), the cooldown and the cows are the summon file's
                    ItemSummons::Herd(player, static_cast<unsigned>(one.value), scale);
                else if (one.stat == "random_shrine")
                {
                    // Ahavarion: the chance is the tunable ahavarion_chance_pct (a blank one reads 0: never), scaled by the event's coefficient
                    // (1 on a kill); each shrine effect is a random one of the shrines, for its own seconds (Pylons::Give)
                    double const chance = DC::Tunables::Has("combat", "ahavarion_chance_pct") ? DC::Tunables::Get("combat", "ahavarion_chance_pct") : 0.0;
                    if (Proc::Rolls(scale, chance, [](double pct) { return roll_chance_f(static_cast<float>(pct)); }))
                        for (unsigned shrine = 0; shrine < static_cast<unsigned>(one.value); ++shrine)
                            Pylons::GiveRandomShrine(player, rand_norm());
                }
                else if (one.stat == "proc_damage" && target && one.row)
                    // Storm Crow: the item's rolled chance (scaled by this hit's proc coefficient) casts its ball at the enemy the hit struck
                    ItemProc::Damage(player, target, one.row->owner, one.value, scale);
                else if (one.stat == "slow_pct" && target && one.row) // Jang's Envelopment: the enemy the hit struck, for the item's own seconds
                    Slow(player, target, one.value, ItemPower::OwnerNumber(Data().rows, one.row->owner, "player", "slow_seconds"));
                else if (one.stat == "fear_enemies" && one.row)
                    Frighten(player, *one.row, one.value);
                else if (one.stat == "charm_seconds" && target)
                    CharmEffect::Apply(player, target, CharmRecord, one.value); // The Tormentor: the enemy the hit struck fights for the wearer
                else if (one.stat == "heal_missing_life_pct")
                    HealMissing(player, one.value); // Vambraces of Sescheron, on a Primary's cast that hit
                else if (one.stat == "bone_shield" && one.row)
                    BoneShield(player, *one.row, one.value, scale); // Wall of Man, on a monster's hit
                else if (one.stat == "pull_enemy" && target && one.row)
                    Drag(player, target, *one.row, one.value, scale); // The Butcher's Sickle: on a hit of any skill
                else if (one.stat == "resource_refund")
                {
                    if (Resources::Resource const* resource = Resources::Of(Classes::ClassIdOf(player)))
                        Resources::Add(player, *resource, one.value);
                }
                else if (one.stat == "resource_per_life_lost_pct") // Krede's Flame: the primary resource for the Life the element's hit took
                {
                    if (Resources::Resource const* resource = Resources::Of(Classes::ClassIdOf(player)))
                        Resources::Add(player, *resource,
                                       ItemPower::ResourceFromLifeLost(one.value, lifeBefore - lifeAfter, Resources::Max(player, *resource)));
                }
            }
        }

        // N-TCTRL (Ancient Parthan Defenders): the update hook's look at the enemies around the wearer, once per the item's `stunned_check_seconds`
        // (ItemPower::ScanDue): how many within its `stunned_radius_yards` carry a stun (a MOD_STUN aura that is not a freeze, ItemPower::StunAura),
        // kept in the clock for the damage taken to read (IncomingFactor). Looked at only when some row wants the count and the player wears the
        // item (an item that is off leaves the radius at 0, which clears the count); the stock "Drain Life" record is only the hostility test of the area.
        void StunScan(Player* player)
        {
            if (!Data().stunned)
                return;
            std::uint64_t const guid = player->GetGUID().GetRawValue();
            double yards, every;
            std::uint32_t const now = getMSTime();
            {
                std::lock_guard<std::mutex> lock(mutex);
                auto mine = clocks.find(guid);
                if (mine == clocks.end())
                    return;
                ItemPower::Situation const situation = SituationOf(guid);
                yards = ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), "stunned_radius_yards", 0.0, situation);
                every = ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), "stunned_check_seconds", 0.0, situation);
                if (yards <= 0 || every <= 0)
                {
                    mine->second.stunnedNear = 0;
                    return;
                }
                if (!ItemPower::ScanDue(mine->second.stunScanAt, now, every))
                    return;
                mine->second.stunScanAt = now;
            }
            unsigned stunned = 0;
            for (Unit* enemy : Combat::Enemies(player, DrainRecord, player->GetPosition(), yards))
                for (AuraEffect const* effect : enemy->GetAuraEffectsByType(SPELL_AURA_MOD_STUN))
                {
                    SpellInfo const* info = effect->GetSpellInfo();
                    if (ItemPower::StunAura(info->Id, (info->GetAllEffectsMechanicMask() & (1u << MECHANIC_FREEZE)) != 0))
                    {
                        ++stunned;
                        break;
                    }
                }
            std::lock_guard<std::mutex> lock(mutex);
            if (auto mine = clocks.find(guid); mine != clocks.end())
                mine->second.stunnedNear = stunned;
        }
    } // namespace Detail
} // namespace DC::Combat
