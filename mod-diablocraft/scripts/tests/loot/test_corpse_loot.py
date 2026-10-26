#!/usr/bin/env python3
"""Corpse loot (diablocraft-corpse-loot-rows / -window): decisions executed, wiring read.

  * The DECISIONS are the production header src/loot/dc_corpse_rules.h, compiled into
    scripts/tests/loot/corpse_tests.cpp and run. Every rule has a mutation that must turn
    the harness red.
  * The WIRING - that dc_loot.cpp and dc_corpse_loot.cpp call those decisions and the
    kill, claim and window paths behave as the proposal says - is checked by reading the
    code with comments removed. Each wiring check has a mutation of the code that must
    make it fail. It is not executed: that needs a Player; the GM script is
    docs/test-diablocraft-corpse-loot.md.
  * The migration and the switch are checked as text.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import unittest

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import loot_source

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

MODULE = pathlib.Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
SRC = MODULE / "src" / "loot"
RULES = SRC / "dc_corpse_rules.h"
HARNESS = MODULE / "scripts" / "tests/loot" / "corpse_tests.cpp"
SCRATCH = ROOT / ("azerothcore" + "-wotlk") / "build" / "_agent-scratch" / "corpse_loot"


def code(text):
    """Source with comments removed."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def squash(text):
    return re.sub(r"\s+", " ", text)


def mutate(raw, old, new):
    """`raw` with comments out and the first whitespace-tolerant `old` replaced by `new`; None if absent."""
    plain = code(raw)
    pattern = r"\s*".join(re.escape(token) for token in squash(old).split(" "))
    found = re.search(pattern, plain)
    return None if found is None else plain[:found.start()] + new + plain[found.end():]


def build(include_dir, name, strict=True):
    compiler = shutil.which("c++") or shutil.which("g++")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = SCRATCH / name
    flags = ["-Wall", "-Wextra", "-Werror"] if strict else []
    built = subprocess.run([compiler, "-std=c++17", "-O1", *flags, "-I", str(include_dir), str(HARNESS), "-o", str(binary)],
                           capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the harness did not compile:\n" + built.stderr[-4000:])
    return binary


def run(binary):
    return harness_env.run([str(binary)], capture_output=True, text=True)


RULE_MUTATIONS = [
    ("an untagged corpse holds rows", "return ready && dead && hasLootRecipient && lootMode > 0;",
     "return ready && dead && lootMode > 0;"),
    ("the page is 17 rows", "PageRows = 16;", "PageRows = 17;"),
    ("the page is not cut", "return {owned.begin(), owned.begin() + std::min(owned.size(), pageRows)};",
     "return owned;"),
    ("money is left to the stock handler", "case Packet::Money: return windowOpen;", "case Packet::Money: return false;"),
    ("a release is not swallowed for an open window", "case Packet::Release: return tracked || windowOpen;",
     "case Packet::Release: return tracked;"),
    ("a pickup is taken without a window", "case Packet::Pickup: return windowOpen;", "case Packet::Pickup: return true;"),
    ("a store refusal reads as already looted", "return storeError != StoreOk ? PickupError::StoreFailed : PickupError::AlreadyLooted;",
     "return PickupError::AlreadyLooted;"),
    ("a corpse outside the corpse state keeps its rows", "return found && isCorpseState && (!inRift || riftLive);",
     "return found && (!inRift || riftLive);"),
    ("a closed rift's corpse keeps its rows", "return found && isCorpseState && (!inRift || riftLive);",
     "return found && isCorpseState;"),
    ("a corpse that left the map keeps its rows", "return found && isCorpseState && (!inRift || riftLive);",
     "return isCorpseState && (!inRift || riftLive);"),
    ("a range below the floor is used as it is", "return std::clamp(yards, MinAoeRange, MaxAoeRange);", "return std::min(yards, MaxAoeRange);"),
    ("a range above the ceiling is used as it is", "return std::clamp(yards, MinAoeRange, MaxAoeRange);", "return std::max(yards, MinAoeRange);"),
    ("rarity does not lead the window order", "if (a.rank != b.rank) return a.rank > b.rank;", "if (a.rank != b.rank) return a.rank < b.rank;"),
    ("distance does not break rank ties", "return a.distance < b.distance;", "return a.distance > b.distance;"),
    ("set ranks below legendary", 'if (rarity == "legendary" || rarity == "set") return 4;', 'if (rarity == "legendary") return 4;'),
    ("a corpse just past the range is in", "return distance <= range;", "return distance <= range + 1;"),
    ("a far window stays open", "distance <= interactionDistance * ReleaseDistanceFactor", "true"),
    ("an owed player does not keep the corpse open", "return rowsLeft == 0 && owedLeft == 0;", "return rowsLeft == 0;"),
    ("rows left do not keep the corpse open", "return rowsLeft == 0 && owedLeft == 0;", "return owedLeft == 0;"),
    ("a member the kill already paid is owed again", "if (std::find(paid.begin(), paid.end(), guid) == paid.end() &&",
     "if (true &&"),
    ("a member listed twice is owed twice", "std::find(owed.begin(), owed.end(), guid) == owed.end())", "true)"),
    ("the owed are not the party but the paid", "for (std::uint64_t const guid : party)", "for (std::uint64_t const guid : paid)"),
    ("the legendary beam value moves", "BeamLegendary = 6", "BeamLegendary = 5"),
    ("an Ancient beams red", 'if (quality == "primal") return BeamPrimal;', 'if (quality != "normal") return BeamPrimal;'),
    ("a rare beams", 'if (rarity != "legendary" && rarity != "set") return BeamNone;',
     'if (rarity != "legendary" && rarity != "set" && rarity != "rare") return BeamNone;'),
    ("a set item beams orange", 'return rarity == "set" ? BeamSet : BeamLegendary;', "return BeamLegendary;"),
    ("a set does not outrank a legendary", "if (counts[BeamSet - BeamLegendary]) return BeamSet;", ""),
    ("a Primal does not outrank a set", "if (counts[BeamPrimal - BeamLegendary]) return BeamPrimal;", ""),
    ("a take clears every row of its tier", "--counts[tier - BeamLegendary];", "counts[tier - BeamLegendary] = 0;"),
    ("a take with nothing left wraps", "if (Beams(tier) && counts[tier - BeamLegendary]) --counts", "if (Beams(tier)) --counts"),
    ("a row of no tier is counted", "return tier >= BeamLegendary && tier <= BeamPrimal;", "return tier <= BeamPrimal;"),
]


class Decisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which("c++") or shutil.which("g++")):
            raise unittest.SkipTest("no C++ compiler")

    def test_the_production_header_passes(self):
        result = run(build(SRC, "real"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS a window page is 16 rows", result.stdout)

    def test_every_rule_mutation_fails(self):
        for index, (label, old, new) in enumerate(RULE_MUTATIONS):
            with self.subTest(mutation=label):
                # The formatter re-wraps this header, so the target is found whitespace-tolerantly.
                mutated = mutate(RULES.read_text(encoding="utf-8"), old, new)
                self.assertIsNotNone(mutated, "mutation target moved: " + old)
                folder = SCRATCH / ("mutant_%d" % index)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "dc_corpse_rules.h").write_text(mutated, encoding="utf-8")
                result = run(build(folder, "mutant", strict=False))
                self.assertNotEqual(result.returncode, 0, label + " was not caught:\n" + result.stdout)


RAW = {"loot": loot_source.source(),   # R4: dc_loot.cpp and dc_loot_delivery.cpp
       "window": (SRC / "dc_corpse_loot.cpp").read_text(encoding="utf-8"),
       "ground": (SRC / "dc_ground_loot.cpp").read_text(encoding="utf-8")}


def has(text, *needles):
    return all(needle in text for needle in needles)


# (what must be true, which source, predicate on the comment-free whitespace-squashed text,
#  (old, new): a revert of the code that must make the predicate false; old is matched on squashed text)
RESTART_DELETE = 'CharacterDatabase.DirectExecute("DELETE FROM dc_loot_buffer WHERE kind=\'corpse\'");'

WIRING = [
    ("M1: RollLoot writes corpse rows when the corpse can hold them and ground delivery is off", "loot",
     lambda t: has(t, "bool const corpse = !ground && source != Source::Chest && deathSource && CorpseCanHold(deathSource);",
                   "if (corpse) { std::string corpseRarity"),
     ("!ground && source != Source::Chest && deathSource && CorpseCanHold(deathSource)", "false")),
    ("M1: a corpse drop that cannot be written fails the reward, as a ground drop does", "loot",
     lambda t: re.search(r"if \(!DropCorpseLoot\(player,deathSource,base[^;{}]*?\)\) \{ PlayerEconomy::Fail\(\); result.ok = false;", t) is not None,
     ("PlayerEconomy::Fail(); result.ok = false; LOG_ERROR(\"server\", \"[DC loot] Corpse row refused",
      "LOG_ERROR(\"server\", \"[DC loot] Corpse row refused")),
    ("M1: the guardian's materials go on the corpse too", "loot",
     lambda t: has(t, "bool const granted = corpse ? DropCorpseLoot(player,deathSource,material.first"),
     ("bool const granted = corpse ? DropCorpseLoot(", "bool const granted = false ? DropCorpseLoot(")),
    ("M1: gems go on the corpse (the one gem helper)", "loot",
     lambda t: has(t, "if (corpse) { if (!DropCorpseLoot(player,deathSource,gem"),
     ("if (corpse) { if (!DropCorpseLoot(player,deathSource,gem", "if (false) { if (!DropCorpseLoot(player,deathSource,gem")),
    # Two calls: the gem the roll gave and the Broken Crown's extra gem of the helm's colour (diablocraft-w9zv8).
    ("M1: the kill hook's gems ask whether the corpse holds them", "loot",
     lambda t: t.count("DeliverGemDrop(member, gem, level, Name(source), tier, killed, CorpseDelivery(killed),") == 1
     and t.count("DeliverGemDrop(member, extra, level, Name(source), tier, killed, CorpseDelivery(killed),") == 1
     and t.count("tier, killed, CorpseDelivery(killed),") == 2,
     ("tier, killed, CorpseDelivery(killed),", "tier, killed, false,")),
    ("M1: the first-kill legendary goes on the corpse", "loot",
     lambda t: has(t, "if (CorpseDelivery(deathSource)) {", "DropCorpseLoot(player,deathSource,base,monsterLevel,rarity"),
     ("if (CorpseDelivery(deathSource)) {", "if (false) {")),
    ("M1: corpse delivery is off whenever ground delivery is on (the rollback)", "loot",
     lambda t: has(t, "return deathSource && !GroundDeliveryEnabled() && CorpseCanHold(deathSource);"),
     ("!GroundDeliveryEnabled() && CorpseCanHold", "CorpseCanHold")),
    ("M1: the death hook keeps the placeholder of a corpse that holds rows", "loot",
     lambda t: has(t, "if (CorpseHoldsRows(creature)) { KeepCorpseLootable(creature); return; }"),
     ("if (CorpseHoldsRows(creature)) { KeepCorpseLootable(creature); return; }", "")),
    ("M1: automatic delivery never touches corpse rows", "loot",
     lambda t: t.count("kind NOT IN ('ground','corpse')") == 2,
     ("kind NOT IN ('ground','corpse')", "kind<>'ground'")),
    ("M2: a corpse pickup does not unsummon the corpse", "loot",
     lambda t: has(t, 'bool const retire = kind == "ground";', "if (retire && carrier)"),
     ("if (retire && carrier)", "if (carrier)")),
    ("M2: ClaimBufferedRow has one declarator and it takes the store-error byte", "loot",
     lambda t: t.count("bool ClaimBufferedRow(") == 1
     and "bool ClaimBufferedRow(Player* player, uint64 id, Creature* carrier = nullptr, std::uint8_t* storeError = nullptr)"
         in t,
     ("bool ClaimBufferedRow(Player* player, uint64 id, Creature* carrier = nullptr, std::uint8_t* storeError = nullptr)",
      "bool ClaimBufferedRow(Player* player, uint64 id, Creature* carrier = nullptr, bool* bagsFull = nullptr);\n"
      "bool ClaimBufferedRow(Player* player, uint64 id, Creature* carrier = nullptr, std::uint8_t* storeError = nullptr)")),
    ("M2: a corpse row claims through the pay-once path with the bag-full flag", "loot",
     lambda t: has(t, "return ClaimBufferedRow(player, rowId, corpse, &storeError);"),
     ("return ClaimBufferedRow(player, rowId, corpse, &storeError);", "return false;")),
    ("M2: the window shows the shell for a legendary or set row", "loot",
     lambda t: has(t, 'return contentKind == "rolled" && ShellFor(baseItem, rarity, shell) ? shell : baseItem;'),
     ('contentKind == "rolled" && ShellFor(baseItem, rarity, shell) ? shell : baseItem', "baseItem")),
    ("M2: both pickup paths send the core's own store error, never a guessed one", "window",
     lambda t: has(t, "case Corpse::PickupError::StoreFailed: player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr); return;"),
     ("case Corpse::PickupError::StoreFailed: player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr);",
      "case Corpse::PickupError::StoreFailed: player->SendEquipError(EQUIP_ERR_INVENTORY_FULL, nullptr, nullptr);")),
    ("M2: the ground label click and the carrier right-click forward it too", "ground",
     lambda t: t.count("player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr);") == 2,
     ("else if (!taken && storeError) player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr);",
      "else if (!taken && storeError) player->SendEquipError(EQUIP_ERR_INVENTORY_FULL, nullptr, nullptr);")),
    ("M2: CMSG_LOOT_MONEY is swallowed while a window is open", "window",
     lambda t: has(t, "if (opcode == CMSG_LOOT_MONEY) return !Corpse::Answers(Corpse::Packet::Money, false, windowOpen);"),
     ("return !Corpse::Answers(Corpse::Packet::Money, false, windowOpen);", "return true;")),
    ("M2: CMSG_LOOT_RELEASE is swallowed, not passed to the stock release", "window",
     lambda t: has(t, "Corpse::Answers(Corpse::Packet::Release, tracked, windowOpen)", "ReleaseWindow(player, true); return false;"),
     ("ReleaseWindow(player, true); return false;", "ReleaseWindow(player, true); return true;")),
    ("M2: the window is built from the looter's own rows only", "window",
     lambda t: has(t, "WHERE guid={} AND kind='corpse' AND map_id={} AND instance_id={}"),
     ("WHERE guid={} AND kind='corpse' AND map_id={} AND instance_id={}", "WHERE kind='corpse' AND map_id={} AND instance_id={}")),
    ("M2: the window pages at the rules' page size", "window",
     lambda t: has(t, "Corpse::Page(Corpse::Order(candidates))"),
     ("Corpse::Page(Corpse::Order(candidates))", "Corpse::Order(candidates)")),
    ("M2: a pickup is ours only with a window open", "window",
     lambda t: has(t, "if (!Corpse::Answers(Corpse::Packet::Pickup, false, windowOpen)) return true;"),
     ("if (!Corpse::Answers(Corpse::Packet::Pickup, false, windowOpen)) return true;", "")),
    ("M2: a full bag keeps the row and the slot", "window",
     lambda t: has(t, "case Corpse::PickupError::StoreFailed: player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr); return;"),
     ("player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr); return;",
      "player->SendEquipError(static_cast<InventoryResult>(storeError), nullptr, nullptr); break;")),
    ("M2: the last row of a corpse clears the placeholder and the sparkle", "window",
     lambda t: has(t, "corpse->RemoveDynamicFlag(UNIT_DYNFLAG_LOOTABLE);", "corpse->AllLootRemovedFromCorpse();"),
     ("corpse->RemoveDynamicFlag(UNIT_DYNFLAG_LOOTABLE);", "")),
    ("M2: a window releases on logout, map change and death", "window",
     lambda t: has(t, "void OnPlayerLogout(Player* player) override { ReleaseWindow(player, false); DropOwnerRows(player); }",
                   "void OnPlayerMapChanged(Player* player) override { ReleaseWindow(player, true); }",
                   "void OnPlayerJustDied(Player* player) override { ReleaseWindow(player, true); }"),
     ("void OnPlayerJustDied(Player* player) override { ReleaseWindow(player, true); }", "void OnPlayerJustDied(Player*) override { }")),
    ("M2: a window closes when the corpse is gone or the looter walks off", "window",
     lambda t: has(t, "if (!Corpse::KeepWindow(IsCorpse(corpse),") and "ReleaseWindow(player, true);" in t,
     ("if (!Corpse::KeepWindow(IsCorpse(corpse),", "if (false && !Corpse::KeepWindow(IsCorpse(corpse),")),
    ("M6: the window reads its range from the loot/aoe_range_yards tunable and clamps it", "window",
     lambda t: t.count('Corpse::ClampRange(DC::Tunables::Get("loot", "aoe_range_yards"))') == 2,
     ('double const range = Corpse::ClampRange(DC::Tunables::Get("loot", "aoe_range_yards"));', "double const range = 30.0;")),
    ("M6: the window gathers the looter's rows from every reachable corpse, not just the clicked one", "window",
     lambda t: has(t, "AND phase_mask={} AND expires_at>NOW() AND carrier_guid IN ({})", "Corpse::InAoeRange(distance, range)"),
     ("AND phase_mask={} AND expires_at>NOW() AND carrier_guid IN ({})", "AND phase_mask={} AND expires_at>NOW() AND carrier_guid={}")),
    ("M6: the window is sorted by rank then distance", "window",
     lambda t: has(t, "Corpse::Page(Corpse::Order(candidates))"),
     ("Corpse::Page(Corpse::Order(candidates))", "Corpse::Page(ids)")),
    ("M6: each slot resolves to its own corpse", "window",
     lambda t: has(t, "window.slots.push_back({row.id, row.corpse, false, row.beam});"),
     ("window.slots.push_back({row.id, row.corpse, false, row.beam});", "window.slots.push_back({row.id, clicked->GetGUID(), false, row.beam});")),
    ("M6: a pickup needs its own corpse in range, not the clicked one", "window",
     lambda t: has(t, 'if (!IsCorpse(corpse) || !player->IsAlive() || !Corpse::InAoeRange(player->GetDistance(corpse), Corpse::ClampRange(DC::Tunables::Get("loot", "aoe_range_yards"))))'),
     ("!Corpse::InAoeRange(player->GetDistance(corpse), Corpse::ClampRange(DC::Tunables::Get(\"loot\", \"aoe_range_yards\")))", "false")),
    ("M6: a corpse is finished when its last row is taken, whichever corpse the window was opened on", "window",
     lambda t: has(t, "if (claimed) RowTaken(corpse, player->GetGUID(), slot.beam);"),
     ("if (claimed) RowTaken(corpse, player->GetGUID(), slot.beam);",
      "if (claimed) RowTaken(player->GetMap()->GetCreature(window_corpse), player->GetGUID(), slot.beam);")),
    ("M3: the round-robin looter is cleared whenever a corpse is made lootable, so every group method works", "window",
     lambda t: re.search(r"void Prepare\(Creature\* corpse\) \{ corpse->loot.gold = 1; corpse->loot.roundRobinPlayer.Clear\(\); corpse->SetDynamicFlag\(UNIT_DYNFLAG_LOOTABLE\);", t) is not None,
     ("corpse->loot.roundRobinPlayer.Clear();", "")),
    ("M3: the death hook re-makes the corpse lootable, which clears the looter again", "loot",
     lambda t: has(t, "if (CorpseHoldsRows(creature)) { KeepCorpseLootable(creature); return; }"),
     ("KeepCorpseLootable(creature); return;", "return;")),
    ("M4: the map tick drops the rows of a corpse that is gone, decayed or of a closed rift", "window",
     lambda t: has(t, "!Corpse::KeepRows(corpse != nullptr, IsCorpse(corpse), it->second.rift, live)", "DeleteRows(map->GetId(), map->GetInstanceId(), dead);"),
     ("DeleteRows(map->GetId(), map->GetInstanceId(), dead);", "")),
    ("M4: a rift corpse's row knows its rift is live", "window",
     lambda t: has(t, "DC::Rifts::IsLiveInstance(it->second.mapId, it->second.instanceId)", "entry.rift = inRift;"),
     ("entry.rift = inRift;", "")),
    ("M4: a destroyed map deletes its corpse rows", "window",
     lambda t: has(t, "void OnDestroyMap(Map* map) override", "DeleteRows(map->GetId(), map->GetInstanceId(), {});"),
     ("DeleteRows(map->GetId(), map->GetInstanceId(), {});", "")),
    ("M4: the owner's logout deletes their rows", "window",
     lambda t: has(t, "ReleaseWindow(player, false); DropOwnerRows(player);", "DELETE FROM dc_loot_buffer WHERE guid={} AND kind='corpse'"),
     ("DropOwnerRows(player);", "")),
    ("M4: a corpse left with no rows is finished on its map's tick", "window",
     lambda t: has(t, "for (ObjectGuid const& guid : emptied) if (Creature* corpse = map->GetCreature(guid); IsCorpse(corpse)) FinishCorpse(corpse);"),
     ("for (ObjectGuid const& guid : emptied)", "for (ObjectGuid const& guid : std::vector<ObjectGuid>{})")),
    ("M4: the window reads the corpse state, not just 'not alive'", "window",
     lambda t: has(t, "if (!IsCorpse(corpse) || !player->IsAlive())", "Corpse::KeepWindow(IsCorpse(corpse),"),
     ("Corpse::KeepWindow(IsCorpse(corpse),", "Corpse::KeepWindow(corpse != nullptr,")),
    ("M4: nothing from a released corpse goes to the bags or the mail", "window",
     lambda t: not any(word in t for word in ("DeliverBuffered", "Buffer(", "SendMail", "MailDraft", "AddItem(", "StoreNewItem")),
     (RESTART_DELETE, RESTART_DELETE + " MailDraft")),
    ("M4: a rift corpse uses the normal decay timer (one timer call, not gated by the rift)", "window",
     lambda t: t.count("SetCorpseRemoveTime(") == 1 and "SetCorpseRemoveTime(corpse->GetCorpseDelay())" in t,
     ("corpse->SetCorpseRemoveTime(corpse->GetCorpseDelay());", "corpse->SetCorpseRemoveTime(corpse->GetCorpseDelay()); corpse->SetCorpseRemoveTime(99999);")),
    ("M2: a corpse that holds rows decays on the normal timer", "window",
     lambda t: has(t, "corpse->SetCorpseRemoveTime(corpse->GetCorpseDelay());"),
     ("corpse->SetCorpseRemoveTime(corpse->GetCorpseDelay());", "")),
    ("M2: corpse rows are written in the economy transaction and shown after its commit", "window",
     lambda t: has(t, "PlayerEconomy::BeginTransaction()", "PlayerEconomy::AfterCommit(publish);", "NeverExpires"),
     ("PlayerEconomy::AfterCommit(publish);", "publish();")),
    ("M2: corpse delivery stays off until the unique key is dropped", "window",
     lambda t: has(t, "non_unique=0", "ready = true;"),
     ("ready = true;", "ready = false;")),
    ("M2: corpse rows die with a restart", "window",
     lambda t: has(t, RESTART_DELETE),
     (RESTART_DELETE, "")),
    ("F7: an owed player is paid when they open the corpse, before the window is built", "window",
     lambda t: has(t, "PayOwed(player, corpse); OpenWindow(player, corpse); return false;"),
     ("PayOwed(player, corpse); OpenWindow(player, corpse);", "OpenWindow(player, corpse);")),
    ("F7: the open pays the player who opens it, and only if the corpse owes them", "window",
     lambda t: has(t, "!entry->second.owed.erase(player->GetGUID())", "pay = entry->second.pay;"),
     ("!entry->second.owed.erase(player->GetGUID())", "!entry->second.owed.count(player->GetGUID())")),
    ("F7: a pay that did not commit leaves the player owed, so the next open retries", "window",
     lambda t: has(t, "if (!paid) entry->second.owed.insert(player->GetGUID());"),
     ("if (!paid) entry->second.owed.insert(player->GetGUID());", "if (!paid) { }")),
    ("F7: the pay runs outside the corpse lock (it writes rows, which take it)", "window",
     lambda t: has(t, "} bool const paid = pay && pay(player, corpse);"),
     ("} bool const paid = pay && pay(player, corpse);", "bool const paid = pay && pay(player, corpse); }")),
    ("F7: the last row taken does not finish a corpse somebody is still owed on", "window",
     lambda t: has(t, "empty = Corpse::CorpseEmpty(left, static_cast<std::uint32_t>(entry->second.owed.size()));"),
     ("empty = Corpse::CorpseEmpty(left, static_cast<std::uint32_t>(entry->second.owed.size()));", "empty = Corpse::CorpseEmpty(left);")),
    ("F7: the map tick does not sweep a corpse somebody is still owed on", "window",
     lambda t: has(t, "if (Corpse::CorpseEmpty(it->second.rows, static_cast<std::uint32_t>(it->second.owed.size()))) emptied.push_back(it->first);"),
     ("if (Corpse::CorpseEmpty(it->second.rows, static_cast<std::uint32_t>(it->second.owed.size()))) emptied", "if (it->second.rows == 0) emptied")),
    ("F7: a corpse is finished once the last owed player is paid and nothing is left on it", "window",
     lambda t: has(t, "else if (Corpse::CorpseEmpty(entry->second.rows, static_cast<std::uint32_t>(entry->second.owed.size()))) {"),
     ("else if (Corpse::CorpseEmpty(entry->second.rows, static_cast<std::uint32_t>(entry->second.owed.size()))) {", "else if (false) {")),
    ("F7: owing a corpse makes it lootable and gives it the normal decay timer", "window",
     lambda t: has(t, "entry.owed.insert(owed.begin(), owed.end());", "} Prepare(corpse); if (first) RestoreDecay(corpse); return true;"),
     ("} Prepare(corpse); if (first) RestoreDecay(corpse); return true;", "} return true;")),
    ("F7: an owed corpse is tracked, so a rift corpse dies with its rift and the stock open does not take it", "window",
     lambda t: has(t, "entry.owed.insert(owed.begin(), owed.end());", "entry.rift = DC::Rifts::IsLiveInstance(map->GetId(), map->GetInstanceId());"),
     ("entry.rift = DC::Rifts::IsLiveInstance(map->GetId(), map->GetInstanceId());", "entry.rift = false;")),
    ("F7: only a corpse that can hold loot can be owed", "window",
     lambda t: has(t, "if (!corpse || owed.empty() || !pay || !CorpseCanHold(corpse) || !corpse->GetMap()) return false;"),
     ("!pay || !CorpseCanHold(corpse) ||", "!pay ||")),
    ("F7: rows added after an owed entry do not restart the decay timer", "window",
     lambda t: has(t, "first = entry.rows == 0 && entry.owed.empty(); ++entry.rows;"),
     ("first = entry.rows == 0 && entry.owed.empty(); ++entry.rows;", "first = entry.rows == 0; ++entry.rows;")),
    ("C7: a dropped row's beam tier comes from its rarity and quality, counted for its owner", "window",
     lambda t: has(t, "std::uint32_t const beam = Corpse::BeamTier(rarity, DC::Quality::Clean(quality));",
                   "AddRow(map, corpseGuid, inRift, ownerGuid, beam);"),
     ("std::uint32_t const beam = Corpse::BeamTier(rarity, DC::Quality::Clean(quality));",
      "std::uint32_t const beam = Corpse::BeamNone;")),
    ("C7: a row adds to its owner's count on the corpse", "window",
     lambda t: has(t, "Corpse::AddBeam(entry.beams[owner], beam);"),
     ("Corpse::AddBeam(entry.beams[owner], beam);", "")),
    ("C7: the window reads each row's tier from its rarity and quality", "window",
     lambda t: has(t, "SELECT id,carrier_guid,base_item,content_kind,drop_count,rarity,quality_tier FROM dc_loot_buffer",
                   "Corpse::BeamTier(f[5].Get<std::string>(), f[6].Get<std::string>())"),
     ("Corpse::BeamTier(f[5].Get<std::string>(), f[6].Get<std::string>())", "Corpse::BeamNone")),
    ("C7: a pickup takes its row's tier off the looter's count", "window",
     lambda t: has(t, "Corpse::TakeBeam(entry->second.beams[owner], beam);"),
     ("Corpse::TakeBeam(entry->second.beams[owner], beam);", "")),
    ("C7: a tier change is sent again to every viewer, and the shared value says whether anyone has one", "window",
     lambda t: has(t, "corpse->SetUInt32Value(UNIT_FIELD_PADDING, any ? 1 : 0); corpse->ForceValuesUpdateAtIndex(UNIT_FIELD_PADDING);"),
     ("corpse->ForceValuesUpdateAtIndex(UNIT_FIELD_PADDING);", "")),
    ("C7: a finished corpse clears the field", "window",
     lambda t: has(t, "corpse->AllLootRemovedFromCorpse(); corpse->SetUInt32Value(UNIT_FIELD_PADDING, 0);"),
     ("corpse->AllLootRemovedFromCorpse(); corpse->SetUInt32Value(UNIT_FIELD_PADDING, 0);", "corpse->AllLootRemovedFromCorpse();")),
    ("C7: a player who leaves takes their tiers with them", "window",
     lambda t: has(t, "entry.beams.erase(player->GetGUID());"),
     ("entry.beams.erase(player->GetGUID());", "")),
    ("C7: the field's place is tracked only on a creature", "window",
     lambda t: has(t, "return index == UNIT_FIELD_PADDING && unit->IsCreature();"),
     ("return index == UNIT_FIELD_PADDING && unit->IsCreature();", "return false;")),
    ("C7: each viewer is sent their own tier", "window",
     lambda t: has(t, "buf.put(found->second, BeamFor(unit->GetMap(), unit->GetGUID(), target->GetGUID()));"),
     ("BeamFor(unit->GetMap(), unit->GetGUID(), target->GetGUID())", "std::uint32_t(1)")),
    ("C7: the field is public, so the core sends it at all", "window",
     lambda t: has(t, "UnitUpdateFieldFlags[UNIT_FIELD_PADDING] = UF_FLAG_PUBLIC;"),
     ("UnitUpdateFieldFlags[UNIT_FIELD_PADDING] = UF_FLAG_PUBLIC;", "")),
    ("C7: the beam script is registered", "window",
     lambda t: has(t, "new CorpseBeam();"),
     ("new CorpseBeam();", "")),
    ("M2: the spike's .dc corpsetest command is gone", "window",
     lambda t: "corpsetest" not in t and "CommandScript" not in t,
     ("new CorpseWorld();", "new CorpseWorld(); new CorpseCommand(); // corpsetest CommandScript")),
]


# Checks whose mutation target is in the code twice (the revert takes the first).
TWICE = {"M1: automatic delivery never touches corpse rows", "M1: the kill hook's gems ask whether the corpse holds them"}


class Wiring(unittest.TestCase):
    def test_every_wiring_check_holds_and_fails_when_its_code_is_reverted(self):
        for label, which, holds, (old, new) in WIRING:
            with self.subTest(check=label):
                squashed = squash(code(RAW[which]))
                self.assertTrue(holds(squashed), "does not hold on the real code: " + label)
                self.assertEqual(squashed.count(squash(old)), 2 if label in TWICE else 1,
                                 "mutation target moved or repeats: " + old)
                # The revert is applied to the squashed text; it is the same text the predicate reads.
                mutated = squashed.replace(squash(old), squash(new), 1)
                if label == "M2: the spike's .dc corpsetest command is gone":
                    mutated = squash(RAW[which].replace("new CorpseWorld();", "new CorpseWorld(); new CorpseCommand(); CommandScript corpsetest;", 1))
                self.assertFalse(holds(mutated), "check survives the revert: " + label)


class AoeTunable(unittest.TestCase):
    def test_the_range_is_thirty_yards_on_the_loot_sheet_and_in_the_generated_table(self):
        sheet = (MODULE / "data/tunables/loot.csv").read_text(encoding="utf-8")
        self.assertRegex(sheet, r"(?m)^aoe_range_yards,,30,yards,")
        self.assertIsNone(re.search(r"(?m)^aoe_range_yards,,30,yards,", sheet.replace("aoe_range_yards,,30", "aoe_range_yards,,55")))
        table = (MODULE / "data/generated/tunables_0004.sql").read_text(encoding="utf-8")
        self.assertRegex(table, r"'loot', 'aoe_range_yards', NULL, 30\.0, 'yards'")


class MigrationAndSwitch(unittest.TestCase):
    def test_migration_drops_the_unique_carrier_key_and_adds_a_plain_index(self):
        text = (MODULE / "data/sql/db-characters/updates/loot_0009_corpse_rows.sql").read_text(encoding="utf-8")
        self.assertIn("index_name='dc_ground_carrier' AND non_unique=0", text)
        self.assertIn("DROP INDEX dc_ground_carrier", text)
        self.assertRegex(text, r"ADD KEY dc_loot_carrier\(map_id,instance_id,carrier_guid,guid\)")
        self.assertNotIn("UNIQUE", text.replace("non_unique", ""))

    def test_the_switch_is_off_in_the_sheet_and_ships_as_a_migration(self):
        sheet = (MODULE / "data/tunables/ground_loot_parameters.csv").read_text(encoding="utf-8")
        self.assertRegex(sheet, r"(?m)^ground_delivery_enabled,,0,boolean,")
        self.assertIsNone(re.search(r"(?m)^ground_delivery_enabled,,0,boolean,", sheet.replace(",,0,boolean,", ",,1,boolean,")))
        migration = (MODULE / "data/sql/db-world/updates/loot_0010_ground_delivery_switch.sql").read_text(encoding="utf-8")
        self.assertIn("UPDATE dc_ground_loot_parameter SET tuned_value=0 WHERE parameter='ground_delivery_enabled';", migration)


if __name__ == "__main__":
    unittest.main()
