/*
 * The chain-target path, run through the core's own target selection (spell
 * rewrite step 6, Ricochet).
 *
 * Nothing here answers a question itself. The records the first argument
 * carries are turned into `SpellInfo` objects by the core's own constructor
 * lines - including `ChainTarget = spellEntry->EffectChainTarget[effIndex];`,
 * which is how a generated `EffectChainTargets_1` column becomes the number
 * under test - and a cast is `Spell::SelectImplicitTargetObjectTargets` or
 * `Spell::SelectImplicitNearbyTargets` itself, which is what adds the primary
 * before handing over to `Spell::SelectImplicitChainTargets`.
 * `chain_shim.h` says how that is put together and lists every stub.
 *
 *     chain_harness <records.tsv> <cases.tsv>
 *
 * records.tsv, one spell record per line, straight out of the generated
 * spell_shells.sql (plus whatever control rows the driver invents):
 *     id  EffectChainTargets_1  Attributes  AttributesEx2  AttributesEx4
 *         DefenseType  RequiresSpellFocus  JumpDistance
 *
 * DefenseType is the generated column the core reads as `SpellInfo::DmgClass`;
 * JumpDistance is not a DBC column at all and reaches the core from the
 * `spell_jump_distance` world table, so the driver states it here the same way.
 *
 * cases.tsv, one case per line:
 *   chaintarget <spell>
 *       -> what `m_spellInfo->Effects[EFFECT_0].ChainTarget` holds, which is
 *          the record's column after the core's own assignment
 *   cast <spell> <route> <jumpmod> <primaryX> <candidate> <candidate> ...
 *       -> the unit-target list the cast ends up with, as the driver's own
 *          tags in the order `AddUnitTarget` was called: "0" is the primary
 *          and "1".."n" are the candidates in the order they are written
 *          here. "-" means no unit target at all. A tab and
 *          `m_applyMultiplierMask` follow, because the chain branch sets that
 *          before it searches, so it separates "the branch never ran" from
 *          "the branch ran and found nobody".
 *
 * <route> is `object` for Spell::SelectImplicitTargetObjectTargets (an
 * explicit target, which is what a Torment skill cast at an enemy is) or
 * `nearby` for Spell::SelectImplicitNearbyTargets. Both are extracted whole,
 * and both add the primary before they chain - which is the whole point.
 *
 * <jumpmod> is a SPELLMOD_JUMP_TARGETS flat modifier. Zero means the caster
 * has no spell-mod owner at all, so Spell.cpp:1880-1881 is not entered; any
 * other value installs a Player owner carrying that modifier.
 *
 * <primaryX> is the primary's x coordinate, and each <candidate> is
 * "<x>" or "<x>:<los>", where los is 0 to make IsWithinLOSInMap answer false
 * for that unit. Everything sits on the x axis; y and z are 0. The candidate
 * list is what the SearchAreaTargets stub hands the real chain loop, in this
 * order, with the primary at its head.
 */

#include "chain_shim.h"

#include <fstream>
#include <sstream>

namespace
{
    // The records the driver handed over, kept alive for the run.
    std::vector<SpellEntry*> g_entries;

    void LoadRecords(char const* path)
    {
        std::ifstream stream(path);
        std::string line;
        while (std::getline(stream, line))
        {
            if (line.empty())
                continue;
            std::istringstream cells(line);
            auto* entry = new SpellEntry();
            float jumpDistance = 0.0f;
            cells >> entry->Id >> entry->EffectChainTarget[0] >> entry->Attributes >> entry->AttributesEx2 >>
                entry->AttributesEx4 >> entry->DmgClass >> entry->RequiresSpellFocus >> jumpDistance;
            g_entries.push_back(entry);

            // What SpellMgr does with a spell_dbc row: the record becomes a
            // SpellInfo through the core's own constructor lines, and the
            // jump distance is then laid on from its own world table.
            auto* info = new SpellInfo(entry);
            info->JumpDistance = jumpDistance;
            RegisterSpellInfo(info);
        }
    }

    // One cast, on a caster and a world of its own so nothing carries over.
    std::string Cast(uint32 spellId, std::string const& route, int32 jumpMod, float primaryX,
                     std::vector<std::pair<float, bool>> const& candidates)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info)
            return "no-such-record";

        Unit caster;
        caster.DCTestTag = 9999;
        caster.m_positionX = primaryX - 1.0f;

        Player* owner = nullptr;
        if (jumpMod)
        {
            owner = new Player();
            owner->m_spellMods[SPELLMOD_JUMP_TARGETS].insert(
                DCTest::Modifier(SPELLMOD_JUMP_TARGETS, SPELLMOD_FLAT, jumpMod));
            caster.DCTestSpellModOwner = owner;
        }

        auto* primary = new Unit();
        primary->DCTestTag = 0;
        primary->m_positionX = primaryX;

        Spell spell(&caster, info);
        spell.DCTestPrimary = primary;
        uint32 tag = 1;
        for (auto const& candidate : candidates)
        {
            auto* unit = new Unit();
            unit->DCTestTag = tag++;
            unit->m_positionX = candidate.first;
            unit->DCTestHasLineOfSight = candidate.second;
            spell.DCTestCandidates.push_back(unit);
        }

        SpellImplicitTargetInfo targetType;
        if (route == "object")
        {
            spell.m_targets._objectTarget = primary;
            spell.SelectImplicitTargetObjectTargets(EFFECT_0, targetType);
        }
        else if (route == "nearby")
        {
            spell.SelectImplicitNearbyTargets(EFFECT_0, targetType, 1 << EFFECT_0);
        }
        else
        {
            return "unknown-route";
        }

        std::string out;
        for (Unit* hit : spell.DCTestUnitTargets)
        {
            if (!out.empty())
                out += " ";
            out += std::to_string(hit->DCTestTag);
        }
        if (out.empty())
            out = "-";
        // ...and, after a tab, m_applyMultiplierMask. The chain branch sets it
        // before it searches, so it is how a case tells "the branch did not
        // run" apart from "the branch ran and found nobody to jump to".
        return out + "\t" + std::to_string(uint32(spell.m_applyMultiplierMask));
    }
} // namespace

int main(int argc, char** argv)
{
    if (argc != 3)
    {
        std::fprintf(stderr, "usage: chain_harness <records.tsv> <cases.tsv>\n");
        return 2;
    }

    LoadRecords(argv[1]);

    std::ifstream stream(argv[2]);
    std::string line;
    while (std::getline(stream, line))
    {
        if (line.empty())
            continue;
        std::istringstream cells(line);
        std::string kind;
        cells >> kind;
        if (kind == "chaintarget")
        {
            uint32 spellId = 0;
            cells >> spellId;
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info)
            {
                std::fprintf(stderr, "no record %u\n", spellId);
                return 3;
            }
            std::printf("%u\n", info->Effects[EFFECT_0].ChainTarget);
        }
        else if (kind == "cast")
        {
            uint32 spellId = 0;
            std::string route;
            int32 jumpMod = 0;
            float primaryX = 0.0f;
            cells >> spellId >> route >> jumpMod >> primaryX;
            std::vector<std::pair<float, bool>> candidates;
            std::string cell;
            while (cells >> cell)
            {
                std::size_t colon = cell.find(':');
                if (colon == std::string::npos)
                    candidates.emplace_back(std::stof(cell), true);
                else
                    candidates.emplace_back(std::stof(cell.substr(0, colon)), cell.substr(colon + 1) != "0");
            }
            std::printf("%s\n", Cast(spellId, route, jumpMod, primaryX, candidates).c_str());
        }
        else
        {
            std::fprintf(stderr, "unknown case: %s\n", kind.c_str());
            return 2;
        }
    }
    return 0;
}
