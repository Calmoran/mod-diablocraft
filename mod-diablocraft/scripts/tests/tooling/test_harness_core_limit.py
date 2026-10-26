"""Every test runner that executes a compiled harness must use harness_env.

The mutation harnesses abort() on purpose; with core_pattern a pipe to apport,
each abort filed a /var/crash report (319 of them, 253 from class-parity). The
shared helper sets RLIMIT_CORE to 1 byte, which makes the kernel refuse the core
before apport runs.

This is the guard: a static check that every script which compiles and runs a
binary goes through the helper, a check that the helper really sets the 1-byte
limit, a live probe that runs an abort() program through the helper and
asserts no report appears for it, and OwnRunCheck: the helper refuses a test
script that is not in RUNNERS (or COMPILE_ONLY) on that script's own run, so a
new runner left out of the list fails for its author, not only here.

    python mod-diablocraft/scripts/tests/tooling/test_harness_core_limit.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

HELPER = "mod-diablocraft/scripts/harness_env.py"

# Every script that runs a compiled harness/test binary, including the ones that
# run a deploy/bash child and the restarter's fake command (a Python file that
# segfaults itself), which the compiler scan cannot see; harness_env.run refuses
# a test script that calls it and is not listed here.
RUNNERS = [
    "mod-diablocraft/scripts/tests/classes/test_action_bar.py",
    "mod-diablocraft/scripts/tests/classes/test_level_heals.py",
    "mod-diablocraft/scripts/tests/classes/test_level_heals_rest.py",
    "mod-diablocraft/scripts/tests/monsters/test_affix_budget_tunables.py",
    "mod-diablocraft/scripts/tests/monsters/test_affix_cast_cadence.py",
    "mod-diablocraft/scripts/tests/items/test_ancient_primal.py",
    "mod-diablocraft/scripts/tests/classes/test_ancients_ai.py",
    "mod-diablocraft/scripts/tests/crafting/test_artisan_rules.py",
    "mod-diablocraft/scripts/tests/combat/test_aura_holds.py",
    "mod-diablocraft/scripts/tests/classes/test_barbarian_skills.py",
    "mod-diablocraft/scripts/tests/crafting/test_blacksmith_catalog.py",
    "mod-diablocraft/scripts/tests/crafting/test_blacksmith_tooltips.py",
    "mod-diablocraft/scripts/tests/items/test_blood_shards.py",
    "mod-diablocraft/scripts/tests/bounties/test_bounties.py",
    "mod-diablocraft/scripts/tests/bounties/test_bounty_quests.py",
    "mod-diablocraft/scripts/tests/bounties/test_bounty_cache.py",
    "mod-diablocraft/scripts/tests/items/test_cache_only_legendaries.py",
    "mod-diablocraft/scripts/tests/bounties/test_bounty_travel.py",
    "mod-diablocraft/scripts/tests/items/test_bottomless_potion.py",
    "mod-diablocraft/scripts/tests/legendaries/test_broken_crown.py",
    "mod-diablocraft/scripts/tests/classes/test_cain_destiny.py",
    "mod-diablocraft/scripts/tests/campaign/test_followers.py",
    "mod-diablocraft/scripts/tests/classes/test_follower_skills.py",
    "mod-diablocraft/scripts/tests/items/test_follower_gear.py",
    "mod-diablocraft/scripts/tests/items/test_follower_window.py",
    "mod-diablocraft/scripts/tests/items/test_follower_relics.py",
    "mod-diablocraft/scripts/tests/items/test_rare_relics.py",
    "mod-diablocraft/scripts/tests/combat/test_chain_targets.py",
    "mod-diablocraft/scripts/tests/combat/test_charm.py",
    "mod-diablocraft/scripts/tests/combat/test_exact_damage.py",
    "mod-diablocraft/scripts/tests/combat/test_class_buffs.py",
    "mod-diablocraft/scripts/tests/classes/test_class_eligibility.py",
    "mod-diablocraft/scripts/tests/classes/test_class_parity.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_corpse_lance.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_devour.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_revive.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_corpse_explosion.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_death_nova.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_bone_spear.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_bone_spikes.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_command_skeletons.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_command_golem.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_army_of_the_dead.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_land_of_the_dead.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_decrepify.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_leech.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_frailty.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_bone_armor.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_bone_spirit.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_blood_rush.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_passives.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_simulacrum.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_grim_scythe.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_siphon_blood.py",
    "mod-diablocraft/scripts/tests/classes/test_necromancer_skeletal_mage.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_pets.py",
    "mod-diablocraft/scripts/tests/loot/test_class_roll_rules.py",
    "mod-diablocraft/scripts/tests/classes/test_class_spell_guard.py",
    "mod-diablocraft/scripts/tests/combat/test_combat_conformance.py",
    "mod-diablocraft/scripts/tests/combat/test_minions.py",
    "mod-diablocraft/scripts/tests/combat/test_ground_device.py",
    "mod-diablocraft/scripts/tests/combat/test_proc_scaling.py",
    "mod-diablocraft/scripts/tests/combat/test_damage_boost.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_companion.py",
    "mod-diablocraft/scripts/tests/combat/test_cost_cut.py",
    "mod-diablocraft/scripts/tests/world/test_copy_router.py",
    "mod-diablocraft/scripts/tests/loot/test_corpse_loot.py",
    "mod-diablocraft/scripts/tests/combat/test_cost_math.py",
    "mod-diablocraft/scripts/tests/combat/test_corpses.py",
    "mod-diablocraft/scripts/tests/crafting/test_crafting_window.py",
    "mod-diablocraft/scripts/tests/crafting/test_cube.py",
    "mod-diablocraft/scripts/tests/crafting/test_cube_augment.py",
    "mod-diablocraft/scripts/tests/crafting/test_cube_extract.py",
    "mod-diablocraft/scripts/tests/crafting/test_cube_grid.py",
    "mod-diablocraft/scripts/tests/crafting/test_cube_items.py",
    "mod-diablocraft/scripts/tests/crafting/test_cube_primal.py",
    "mod-diablocraft/scripts/tests/combat/test_damage_buckets.py",
    "mod-diablocraft/scripts/tests/combat/test_element_reduction.py",
    "mod-diablocraft/scripts/tests/combat/test_elemental_affixes.py",
    "mod-diablocraft/scripts/tests/combat/test_revive_choices.py",
    "mod-diablocraft/scripts/tests/paragon/test_paragon_save.py",
    "mod-diablocraft/scripts/tests/combat/test_weapon_flat_delta.py",
    "mod-diablocraft/scripts/tests/monsters/test_elite_affixes_round_two.py",
    "mod-diablocraft/scripts/tests/monsters/test_elite_conformance.py",
    "mod-diablocraft/scripts/tests/monsters/test_elite_damage_reduction.py",
    "mod-diablocraft/scripts/tests/monsters/test_family_ai.py",
    "mod-diablocraft/scripts/tests/monsters/test_family_lineup.py",
    "mod-diablocraft/scripts/tests/classes/test_flame_blades.py",
    "mod-diablocraft/scripts/tests/combat/test_g1_gaps.py",
    "mod-diablocraft/scripts/tests/release/test_game_version.py",
    "mod-diablocraft/scripts/tests/legendaries/test_gem_buffs.py",
    "mod-diablocraft/scripts/tests/legendaries/test_taeguk_hover.py",
    "mod-diablocraft/scripts/tests/classes/test_granted_passive.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_guardian_clear.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_keeper_turnin.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_level.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_logout_quest.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_open.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_progress.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_rewards.py",
    "mod-diablocraft/scripts/tests/items/test_kadala_purchase.py",
    "mod-diablocraft/scripts/tests/rifts/test_open_rift_script.py",
    "mod-diablocraft/scripts/tests/rifts/test_orb_pick.py",
    "mod-diablocraft/scripts/tests/difficulty/test_phase_login.py",
    "mod-diablocraft/scripts/tests/items/test_potion_icons.py",
    "mod-diablocraft/scripts/tests/items/test_slot_vendors.py",
    "mod-diablocraft/scripts/tests/items/test_set_caches.py",
    "mod-diablocraft/scripts/tests/rifts/test_urshi.py",
    "mod-diablocraft/scripts/tests/rifts/test_urshi_spawn.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_rules.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_scaling.py",
    "mod-diablocraft/scripts/tests/rifts/test_gr_unlock.py",
    "mod-diablocraft/scripts/tests/rifts/test_guardian_engagement.py",
    "mod-diablocraft/scripts/tests/hardcore/test_hardcore_realm.py",
    "mod-diablocraft/scripts/tests/crafting/test_jeweler_economy.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_counter.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_events.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_k4.py",
    "mod-diablocraft/scripts/tests/items/test_item_preset_ranges.py",
    "mod-diablocraft/scripts/tests/items/test_resource_affix.py",
    "mod-diablocraft/scripts/tests/items/test_cubed_stats_login_sweep.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_math.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_cindercoat.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_gavel.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_fury.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_stone_gauntlets.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_might_of_the_earth.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_might_of_the_earth_set.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_starfire.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_oathkeeper.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_three_hundredth_spear.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_skull_grasp.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_depth_diggers.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_bastions_revered.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_bindings_lesser_gods.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_blade_of_the_warlord.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_undisputed_champion.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_immortal_kings_call.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_shame_of_delsere.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_hunters_wrath.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_crystal_fist.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_girdle_of_giants.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_deathwish.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_halo_of_karini.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_arreats_law.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_archmages_vicalyke.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_dark_mages_shade.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_vigilance.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_storm_crow.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_boots_of_disregard.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_ahavarion.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_lornelles_sunstone.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_irontoe_mudsputters.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_justice_lantern.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_krysbins_sentence.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_valtheks_rebuke.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_binding_of_the_lost.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_won_khim_lau.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_lefebvres_soliloquy.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_kekegis_unbreakable_spirit.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_eye_of_peshkov.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_pintos_pride.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_dishonored_legacy.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_pride_of_cassius.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_spirit_guards.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_band_of_rue_chambers.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_fist_of_az_turrasq.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_rivera_dancers.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_homing_pads.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_hellrack.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_envious_blade.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_fjord_cutter.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_bul_kathos_wedding_band.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_standoff.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_bovine_bardiche.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_immortal_kings_call_set.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_kyoshiros_soul.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_orb_of_infinite_depth.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_tal_rashas_elements.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_jangs_envelopment.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_ashearas_vestments.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_dovu_energy_trap.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_gungdo_gear.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_madstone.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_mempo_of_twilight.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_light_of_grace.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_tzo_krins_gaze.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_gesture_of_orpheus.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_bracers_of_destruction.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_harrington_waistguard.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_maloths_focus.py",
    "mod-diablocraft/scripts/tests/combat/test_ground_missile.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_scarbringer.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_the_tormentor.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_vambraces_of_sescheron.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_wall_of_man.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_fleshrake.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_ancient_parthan_defenders.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_heart_of_iron.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_hexing_pants_of_mr_yan.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_hergbrashs_binding.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_the_grand_vizier.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_nilfurs_boast.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_prides_fall.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_rogars_huge_stone.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_shi_mizus_haori.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_madawcs_sorrow.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_saffron_wrap.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_fragment_of_destiny.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_kredes_flame.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_butchers_sickle.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_lions_claw.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_monkey_kings_garb.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_countess_julias_cameo.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_hack.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_skulars_salvation.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_vile_ward.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_ancestors_grace.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_fire_walkers.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_blood_brother.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_lut_socks.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_blackthornes_battlegear.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_vengeful_wind.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_crudest_boots.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_the_laws_of_seph.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_cosmic_strand.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_tasker_and_theo.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_primordial_soul.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_ashnagarr.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_cube.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_sage_journey.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_rabid_strike.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_warstaff_of_general_quang.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_flow_of_eternity.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_fury_of_the_vanished_peak.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_incense_torch_of_the_grand_temple.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_gem_enforcer.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_gem_items.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_gem_powers.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_gem_group_b.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_gem_group_c.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_gem_legacy.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_gem_rank25.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_gems.py",
    "mod-diablocraft/scripts/tests/legendaries/test_legendary_summons.py",
    "mod-diablocraft/scripts/tests/items/test_mail_auction_block.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_resources.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_maelstrom.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_thunderstorm.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_elemental_shield.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_ghost_wolf.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_purge.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_spirit_link.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_elemental_weapon.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_spirit_wolves.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_mana.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_lightning_bolt.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_flame_shock.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_elemental_lash.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_frost_lance.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_chain_lightning.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_lava_burst.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_earthquake.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_elemental_blast.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_bloodlust.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_fire_elemental.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_earth_elemental.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_ascendance.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_passives.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_poison_dart.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_corpse_spiders.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_plague_of_toads.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_firebomb.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_horrify.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_hex.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_spirit_walk.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_passives.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_grasp_of_the_dead.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_firebats.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_haunt.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_locust_swarm.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_soul_harvest.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_mass_confusion.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_sacrifice.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_ranged_weapon.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_hungering_arrow.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_entangling_shot.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_bolas.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_evasive_fire.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_grenade.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_impale.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_rapid_fire.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_smoke_screen.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_shadow_power.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_chakram.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_passives.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_vengeance.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_fan_of_knives.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_zombie_charger.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_spirit_barrage.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_acid_cloud.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_wall_of_death.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_piranhas.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_passive_rules.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_zombie_dogs.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_gargantuan.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_big_bad_voodoo.py",
    "mod-diablocraft/scripts/tests/classes/test_witch_doctor_fetish_army.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_elemental_arrow.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_caltrops.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_spike_trap.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_sentry.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_strafe.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_multishot.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_cluster_arrow.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_rain_of_vengeance.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_vault.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_preparation.py",
    "mod-diablocraft/scripts/tests/classes/test_demon_hunter_marked_for_death.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_spirit.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_totems.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_searing_totem.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_earthbind_totem.py",
    "mod-diablocraft/scripts/tests/classes/test_shaman_healing_stream_totem.py",
    "mod-diablocraft/scripts/tests/classes/test_resource_pulse.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_fists.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_mantra_of_retribution.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_mantra_of_healing.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_mantras.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_hundred_fists.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_wave_of_light.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_exploding_palm.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_cyclone_strike.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_blinding_flash.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_serenity.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_effects.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_breath_of_heaven.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_mantra_of_salvation.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_mantra_of_conviction.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_epiphany.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_passives.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_passives_guardians_path.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_deadly_reach.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_tempest_rush.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_dashing_strike.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_crippling_wave.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_lashing_tail_kick.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_sweeping_wind.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_mystic_ally.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_seven_sided_strike.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_inner_sanctuary.py",
    "mod-diablocraft/scripts/tests/classes/test_monk_passives_harmony.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_buffs.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_punish.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_slash.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_smite.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_justice.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_shield_bash.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_sweep_attack.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_blessed_hammer.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_blessed_shield.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_consecration.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_fist_of_the_heavens.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_judgment.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_provoke.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_steed_charge.py",
    "mod-diablocraft/scripts/tests/combat/test_charm_effect.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_phalanx.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_falling_sword.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_akarats_champion.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_heavens_fury.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_bombardment.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_condemn.py",
    "mod-diablocraft/scripts/tests/combat/test_charm_master.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_iron_skin.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_laws_of_valor.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_laws_of_justice.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_laws_of_hope.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_passives.py",
    "mod-diablocraft/scripts/tests/classes/test_crusader_shield_glare.py",
    "mod-diablocraft/scripts/tests/monsters/test_monster_targeting.py",
    "mod-diablocraft/scripts/tests/crafting/test_mystic_crafting.py",
    "mod-diablocraft/scripts/tests/crafting/test_mystic_enchant.py",
    "mod-diablocraft/scripts/tests/world/test_npc_outfits.py",
    "mod-diablocraft/scripts/tests/paragon/test_paragon_pool.py",
    "mod-diablocraft/scripts/tests/items/test_potion.py",
    "mod-diablocraft/scripts/tests/items/test_potion_cooldown.py",
    "mod-diablocraft/scripts/tests/items/test_potion_powers.py",
    "mod-diablocraft/scripts/tests/tooling/test_pre_beta_bugs_a.py",
    "mod-diablocraft/scripts/tests/tooling/test_harness_env_build.py",
    "mod-diablocraft/scripts/tests/classes/test_class_powers.py",
    "mod-diablocraft/scripts/tests/combat/test_proc_coefficients.py",
    "mod-diablocraft/scripts/tests/rifts/test_pylon_buffs.py",
    "mod-diablocraft/scripts/tests/rifts/test_pylon_objects.py",
    "mod-diablocraft/scripts/tests/rifts/test_pylon_conduit_speed.py",
    "mod-diablocraft/scripts/tests/classes/test_rend_receipt.py",
    "mod-diablocraft/scripts/tests/classes/test_resource_registry.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_clear_time.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_entry.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_exit.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_floors.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_keeper.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_patrol.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_pylon.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_quest_slots.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_spawn.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_touchup.py",
    "mod-diablocraft/scripts/tests/rifts/test_rift_way_back.py",
    "mod-diablocraft/scripts/tests/tooling/test_security_fixes_cpp.py",
    "mod-diablocraft/scripts/tests/tooling/test_security_world.py",
    "mod-diablocraft/scripts/tests/tooling/test_server_auto_restart.py",
    "mod-diablocraft/scripts/tests/classes/test_skill_swing_recovery.py",
    "mod-diablocraft/scripts/tests/classes/test_spectral_blade_runes.py",
    "mod-diablocraft/scripts/tests/classes/test_spell_categories.py",
    "mod-diablocraft/scripts/tests/classes/test_spell_numbers.py",
    "mod-diablocraft/scripts/tests/classes/test_start_at_creation.py",
    "mod-diablocraft/scripts/tests/combat/test_stat_readers.py",
    "mod-diablocraft/scripts/tests/stats/test_stats_wiring.py",
    "mod-diablocraft/scripts/tests/stats/test_stats_temporary_dropped.py",
    "mod-diablocraft/scripts/tests/items/test_stash_worn_deposit.py",
    "mod-diablocraft/scripts/tests/rifts/test_open_zone_spots.py",
    "mod-diablocraft/scripts/tests/items/test_stash_moves_runtime.py",
    "mod-diablocraft/scripts/tests/items/test_stash_prices.py",
    "mod-diablocraft/scripts/tests/classes/test_swap_on_cooldown.py",
    "mod-diablocraft/scripts/tests/classes/test_swap_slots.py",
    "mod-diablocraft/scripts/tests/classes/test_teleport_reversal.py",
    "mod-diablocraft/scripts/tests/bounties/test_tester_coffer.py",
    "mod-diablocraft/scripts/tests/difficulty/test_tier_rules.py",
    "mod-diablocraft/scripts/tests/items/test_skill_bonuses.py",
    "mod-diablocraft/scripts/tests/items/test_trade_block.py",
    "mod-diablocraft/scripts/tests/combat/test_victim_adjusted_total.py",
    "mod-diablocraft/scripts/tests/items/test_weapon_elemental_application.py",
    "mod-diablocraft/scripts/tests/items/test_weapon_gem_flat_once.py",
    "mod-diablocraft/scripts/tests/items/test_clear_weapon_gem_flat.py",
    "mod-diablocraft/scripts/tests/items/test_weapon_elemental_damage.py",
    "mod-diablocraft/scripts/tests/items/test_jewelry_damage_range.py",
    "mod-diablocraft/scripts/tests/items/test_preset_stat_mappings.py",
    "mod-diablocraft/scripts/tests/items/test_shaman_maelstrom_lines.py",
    "mod-diablocraft/scripts/tests/stats/test_second_resource_max.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_cooldown_cut_unit.py",
    "mod-diablocraft/scripts/tests/items/test_offhand_damage_range.py",
    "mod-diablocraft/scripts/tests/items/test_quiver_attack_speed.py",
    "mod-diablocraft/scripts/tests/items/test_shaman_class_items.py",
    "mod-diablocraft/scripts/tests/ui/test_window_bridge.py",
    "mod-diablocraft/scripts/tests/classes/test_wizard_electrocute_jumps.py",
    "mod-diablocraft/scripts/tests/tooling/test_lua_error_drop.py",
    "mod-diablocraft/scripts/tests/classes/test_wizard_energy_twister.py",
    "mod-diablocraft/scripts/tests/classes/test_wizard_marks.py",
    "mod-diablocraft/scripts/tests/classes/test_wizard_resource.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_velvet_camaral.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_fazulas_improbable_chain.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_serpents_sparker.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_mykens_ball_of_hate.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_gloves_of_worship.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_aether_walker.py",
    "mod-diablocraft/scripts/tests/legendaries/test_item_power_ranslors_folly.py",
    "core-patches/tests/test_class_limit.py",
    "core-patches/tests/test_class_limit_necromancer.py",
    "core-patches/tests/test_class_limit_witch_doctor.py",
    "core-patches/tests/test_delete_provenance.py",
    "core-patches/tests/test_gobject_editor.py",
    "core-patches/tests/test_mail_trade_readers.py",
    "core-patches/tests/test_outland_copy_liquid.py",
    "core-patches/tests/test_unit_life64.py",
]

# Compiles C++ but never runs the result, so it can never core:
# test_spell_index.py is -fsyntax-only; this file runs no harness itself.
# test_release_build.py puts a recording stub named cmake on PATH and runs no binary.
# test_dev_realm.py puts recording stubs named cmake, herdr, mysql and ss on PATH and runs no binary.
# test_syntax_check.py only runs syntax_check.sh, i.e. `c++ -fsyntax-only`: no binary is produced.
COMPILE_ONLY = {
    "mod-diablocraft/scripts/tests/classes/test_spell_index.py",
    "mod-diablocraft/scripts/tests/tooling/test_harness_core_limit.py",
    "mod-diablocraft/scripts/tests/release/test_release_build.py",
    "mod-diablocraft/scripts/tests/tooling/test_dev_realm.py",
    "mod-diablocraft/scripts/tests/items/test_made_rule.py",
    "mod-diablocraft/scripts/tests/tooling/test_syntax_check.py",
}

COMPILER_RE = re.compile(r"""["'](?:g\+\+|clang\+\+|gcc|c\+\+|cmake|cc)["']|\bharness_env\.build\(""")
SCAN_DIRS = [ROOT / "mod-diablocraft/scripts", ROOT / "core-patches/tests"]
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/harness-core-limit"
PROBE = "core_limit_probe"

# Test scripts for OwnRunCheck. %(scripts)r is the scratch checkout's scripts folder.
RUNNER_BODY = """\
import sys

sys.path.insert(0, %(scripts)r)
import harness_env

sys.exit(harness_env.run([sys.executable, "-c", "pass"]).returncode)
"""
# A registered test that runs a binary in a function, for a test that is not registered to reach.
INNER_BODY = """\
import sys

import harness_env


def go():
    return harness_env.run([sys.executable, "-c", "pass"]).returncode
"""
# The shape of diablocraft-stash-prices-runner: no import of its own, the helper reached
# as `other_test.harness_env.run`.
VIA_ATTRIBUTE_BODY = """\
import sys

sys.path.insert(0, %(scripts)r)
import %(inner)s as inner

sys.exit(inner.harness_env.run([sys.executable, "-c", "pass"]).returncode)
"""
VIA_FUNCTION_BODY = """\
import sys

sys.path.insert(0, %(scripts)r)
import %(inner)s as inner

sys.exit(inner.go())
"""


def rel(path):
    return path.relative_to(ROOT).as_posix()


def first_runner(folder):
    return next(name for name in RUNNERS if name.startswith(folder))


TEST_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(test_\w+)\b", re.M)


def reaches_helper(name, read, runners=None, seen=()):
    """A runner uses the helper itself (imports harness_env and calls run or limit_core) or imports a
    registered runner that does: its binaries then go through that runner's helper (diablocraft-1mq0;
    harness_env.run refuses them unless the calling script is registered, so the registry still lists them)."""
    runners = RUNNERS if runners is None else runners
    text = read(name)
    if "import harness_env" in text and re.search(r"harness_env\.(run|limit_core)\(", text):
        return True
    return any(other in runners and other not in seen and reaches_helper(other, read, runners, seen + (name,))
               for other in (r for module in TEST_IMPORT_RE.findall(text) for r in runners if r.endswith("/%s.py" % module)))


class StaticCheck(unittest.TestCase):
    def test_compiler_using_scripts_all_appear_as_runners(self):
        """A new script that compiles C++ must be added to RUNNERS (or COMPILE_ONLY)."""
        scanned = [path for folder in SCAN_DIRS for path in sorted(folder.rglob("test_*.py"))]
        # The scan once used glob and so read only the top of scripts/ (16 files) after the R5 move into tests/<system>/.
        folders = {rel(p.parent) for p in scanned}
        wanted = {"mod-diablocraft/scripts/tests/" + name for name in ("tooling", "classes", "legendaries")}
        self.assertTrue(wanted <= folders, "the scan no longer reaches the test folders: %s" % sorted(wanted - folders))
        discovered = [rel(path) for path in scanned
                      if rel(path) not in COMPILE_ONLY and COMPILER_RE.search(path.read_text(encoding="utf-8"))]
        missing = sorted(set(discovered) - set(RUNNERS))
        self.assertEqual(missing, [], "compiler-using scripts not in RUNNERS: %s" % missing)

    def test_the_scan_sees_a_script_that_compiles_through_the_cache(self):
        for text in ('binary = harness_env.build([HARNESS], flags=["-O1"])', "harness_env.build(sources)", 'cc = "g++"'):
            with self.subTest(text):
                self.assertTrue(COMPILER_RE.search(text))
        self.assertFalse(COMPILER_RE.search("# harness_env.builder is not a call"))

    def test_every_runner_uses_the_helper(self):
        for name in RUNNERS:
            with self.subTest(name):
                self.assertTrue(reaches_helper(name, lambda n: (ROOT / n).read_text(encoding="utf-8")),
                                "%s neither imports and calls the helper nor imports a registered runner that does" % name)

    def test_helper_sets_one_byte_core_limit(self):
        text = (ROOT / HELPER).read_text(encoding="utf-8")
        self.assertIn("RLIMIT_CORE", text)
        self.assertIn("(CORE_LIMIT_BYTES, CORE_LIMIT_BYTES)", text)
        self.assertEqual(harness_env.CORE_LIMIT_BYTES, 1)


class IndirectRunners(unittest.TestCase):
    """What counts as a runner that uses the helper (diablocraft-1mq0), on made-up scripts."""
    P = "mod-diablocraft/scripts/"
    DIRECT = "import harness_env\nharness_env.run(['x'])\n"
    FILES = {
        P + "test_direct.py": DIRECT,
        P + "test_imports_only.py": "import harness_env\nprint('never calls it')\n",
        P + "test_via.py": "from test_direct import run\n",
        P + "test_via_two.py": "import test_via as v\n",
        P + "test_via_a_stranger.py": "from test_stranger import run\n",
        P + "test_stranger.py": DIRECT,
        P + "test_via_a_dud.py": "from test_imports_only import run\n",
        P + "test_cycle_a.py": "from test_cycle_b import x\n",
        P + "test_cycle_b.py": "from test_cycle_a import x\n",
    }

    def reaches(self, name):
        registered = [n for n in self.FILES if not n.endswith("test_stranger.py")]
        return reaches_helper(self.P + name, self.FILES.__getitem__, registered)

    def test_a_direct_runner_and_a_chain_of_registered_ones_reach_it(self):
        self.assertTrue(self.reaches("test_direct.py"))
        self.assertTrue(self.reaches("test_via.py"))
        self.assertTrue(self.reaches("test_via_two.py"))

    def test_the_others_do_not(self):
        self.assertFalse(self.reaches("test_imports_only.py"), "an import with no call")
        self.assertFalse(self.reaches("test_via_a_stranger.py"), "the module it imports is not a registered runner")
        self.assertFalse(self.reaches("test_via_a_dud.py"), "the runner it imports never calls the helper")
        self.assertFalse(self.reaches("test_cycle_a.py"), "a cycle ends")


@unittest.skipUnless(os.name == "posix", "RLIMIT_CORE is POSIX-only")
class LiveLimit(unittest.TestCase):
    def test_helper_child_reports_a_one_byte_limit(self):
        program = "import resource; print(*resource.getrlimit(resource.RLIMIT_CORE))"
        result = harness_env.run([sys.executable, "-c", program],
                                 capture_output=True, text=True)
        self.assertEqual(result.stdout.split(), ["1", "1"])
        # subprocess.run would report the host's own limit, not ours.
        plain = subprocess.run([sys.executable, "-c", program],
                               capture_output=True, text=True)
        self.assertNotEqual(plain.stdout.split(), ["1", "1"])

    def test_abort_probe_files_no_apport_report(self):
        crash_dir = Path("/var/crash")
        if not crash_dir.is_dir():
            self.skipTest("no /var/crash on this host")
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("no C compiler")
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="probe-", dir=SCRATCH) as folder:
            source = Path(folder) / "probe.c"
            source.write_text("#include <stdlib.h>\nint main(void){abort();}\n", encoding="utf-8")
            binary = Path(folder) / PROBE
            subprocess.run([compiler, str(source), "-o", str(binary)], check=True)
            before = set(os.listdir(crash_dir))
            ran = harness_env.run([str(binary)], capture_output=True, text=True)
            self.assertNotEqual(ran.returncode, 0, "the probe must abort")
            deadline = time.time() + 10
            while time.time() < deadline:
                filed = [n for n in set(os.listdir(crash_dir)) - before if PROBE in n]
                if filed:
                    self.fail("apport filed a report for the helper probe: %s" % filed)
                time.sleep(0.25)


class OwnRunCheck(unittest.TestCase):
    """harness_env.run refuses a test script that is not registered, on that script's own run.

    The glob scan above runs only in this file, so a worker who runs just the tests near
    a change never reached it and a new runner left out of RUNNERS arrived red at the full
    gate (diablocraft-runner-check-per-test). Each case copies the real helper and this
    registry into a scratch checkout and runs a tiny test script there; the repo is not touched.
    """

    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="own-run-", dir=SCRATCH)
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.assertTrue(self.base.is_relative_to(SCRATCH.resolve()))
        self.tree = self.base / "repo"
        self.scripts = self.tree / "mod-diablocraft/scripts"
        self.scripts.mkdir(parents=True)
        for name in ("harness_env.py", "scripts_path.py", "tests/tooling/test_harness_core_limit.py"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            (self.scripts / name).parent.mkdir(parents=True, exist_ok=True)
            (self.scripts / name).write_text(text, encoding="utf-8")

    def write(self, path, body, **fill):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body % dict(fill, scripts=str(self.scripts)), encoding="utf-8")
        return path

    def run_script(self, path):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        return subprocess.run([sys.executable, str(path)], cwd=self.tree, env=env,
                              capture_output=True, text=True)

    def test_an_unregistered_test_is_refused_on_its_own_run(self):
        name = "mod-diablocraft/scripts/test_zz_not_registered.py"
        self.assertNotIn(name, RUNNERS)
        ran = self.run_script(self.write(self.tree / name, RUNNER_BODY))
        self.assertNotEqual(ran.returncode, 0, "an unregistered test ran its binary")
        verdict = ran.stderr.strip().splitlines()[-1]
        self.assertIn(name, verdict)
        self.assertIn("RUNNERS", verdict)

    def test_a_registered_runner_passes(self):
        for name in (first_runner("mod-diablocraft/scripts/"), first_runner("core-patches/tests/")):
            with self.subTest(name):
                ran = self.run_script(self.write(self.tree / name, RUNNER_BODY))
                self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_a_compile_only_script_passes(self):
        name = next(n for n in sorted(COMPILE_ONLY) if n != rel(Path(__file__).resolve()))
        ran = self.run_script(self.write(self.tree / name, RUNNER_BODY))
        self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_a_test_outside_the_checkout_is_not_checked(self):
        """A scratch prototype has no registry entry it could be given."""
        ran = self.run_script(self.write(self.base / "elsewhere/test_zz_scratch.py", RUNNER_BODY))
        self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_a_test_that_reaches_a_registered_one_is_still_checked(self):
        inner = first_runner("mod-diablocraft/scripts/")
        outer = inner.rsplit("/", 1)[0] + "/test_zz_not_registered.py"
        self.write(self.tree / inner, INNER_BODY)
        for label, body in (("through the other module's helper", VIA_ATTRIBUTE_BODY),
                            ("through the other module's function", VIA_FUNCTION_BODY)):
            with self.subTest(label):
                ran = self.run_script(self.write(self.tree / outer, body, inner=Path(inner).stem))
                self.assertNotEqual(ran.returncode, 0, "the unregistered caller ran its binary")
                self.assertIn(outer, ran.stderr.strip().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
