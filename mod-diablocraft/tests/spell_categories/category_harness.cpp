/*
 * The shared-cooldown path, run through the core's own category store (spell
 * rewrite step 6, PM correction).
 *
 * Nothing here answers a question itself. The file the first argument names is
 * loaded by the core's `DBCStorage<SpellCategoryEntry>` through the core's own
 * DBC parser; the records the second argument carries are turned into
 * `SpellInfo` objects by the core's own constructor lines and indexed by the
 * core's own `sSpellsByCategoryStore` loop; and a cast is
 * `Player::AddSpellAndCategoryCooldowns` itself. `category_shim.h` says how
 * that is put together and lists every stub.
 *
 *     category_harness <SpellCategory.dbc> <records.tsv> <cases.tsv> [overlay.tsv]
 *
 * overlay.tsv is optional and is how the server's own copy of the eleven rows
 * arrives: "id <tab> flags" per line, installed into the already-loaded store
 * through the core's own `DBCStorage::SetEntry` before any record is read.
 * The server does not get the generated file; it gets these rows from the
 * stock `spellcategory_dbc` world table on top of whatever SpellCategory.dbc
 * it found, which is what argument one is for in that run.
 *
 * records.tsv, one spell record per line, straight out of the generated
 * spell_shells.sql (plus whatever control rows the driver invents):
 *     id  Category  RecoveryTime  CategoryRecoveryTime  SpellFamilyName
 *         Attributes  AttributesEx2  AttributesEx6  AttributesCu
 *
 * cases.tsv, one case per line:
 *   rows                              -> the index table size the store loaded
 *   lookup   <category>               -> "<found> <flags>", the real
 *                                        sSpellCategoryStore.LookupEntry
 *   category <spell>                  -> what SpellInfo::GetCategory() answers
 *   siblings <category>               -> every spell id the extracted
 *                                        DBCStores.cpp loop filed under it
 *   cast     <spell> <flat> <percent> -> every cooldown the player holds
 *                                        afterwards, as
 *                                        "<spell>:<remaining>:<maxduration>:<category>",
 *                                        lowest spell id first, or "-" for none
 *
 * <flat> is a SPELLMOD_COOLDOWN milliseconds modifier and <percent> a
 * SPELLMOD_COOLDOWN percentage one; either is left off the player when it is
 * zero, so a plain cast carries no modifier at all.
 */

#include "category_shim.h"

#include <algorithm>
#include <fstream>
#include <sstream>

namespace
{
    // The records the driver handed over, kept alive for the run: the store
    // and the SpellInfo objects both point into them.
    std::vector<SpellEntry*> g_entries;

    // The world table's rows, laid over the index table the file produced.
    // DBCStorage::SetEntry is the core's own, out of DBCStore.h; only the ids
    // above the file's highest are ever installed this way, so the slot it
    // replaces is always an empty one.
    void LoadOverlay(char const* path)
    {
        std::ifstream stream(path);
        std::string line;
        while (std::getline(stream, line))
        {
            if (line.empty())
                continue;
            std::istringstream cells(line);
            uint32 identifier = 0, flags = 0;
            cells >> identifier >> flags;
            auto* row = new SpellCategoryEntry();
            row->Id = identifier;
            row->Flags = flags;
            sSpellCategoryStore.SetEntry(identifier, row);
        }
    }

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
            uint32 attributesCu = 0;
            cells >> entry->Id >> entry->Category >> entry->RecoveryTime >> entry->CategoryRecoveryTime >>
                entry->SpellFamilyName >> entry->Attributes >> entry->AttributesEx2 >> entry->AttributesEx6 >>
                attributesCu;
            g_entries.push_back(entry);

            // What DBCStores.cpp's LOAD_DBC does with the spell_dbc rows: the
            // record goes into the store, and SpellMgr then builds a SpellInfo
            // from it.
            sSpellStore.SetEntry(entry->Id, entry);
            auto* info = new SpellInfo(entry);
            info->AttributesCu = attributesCu;
            RegisterSpellInfo(info);
        }
    }

    // One cast, on a player of its own so nothing carries over.
    std::string Cast(uint32 spellId, int32 flat, int32 percent)
    {
        Player player;
        if (flat)
            player.m_spellMods[SPELLMOD_COOLDOWN].insert(DCTest::Modifier(SPELLMOD_COOLDOWN, SPELLMOD_FLAT, flat));
        if (percent)
            player.m_spellMods[SPELLMOD_COOLDOWN].insert(DCTest::Modifier(SPELLMOD_COOLDOWN, SPELLMOD_PCT, percent));

        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info)
            return "no-such-record";
        player.AddSpellAndCategoryCooldowns(info, 0);

        std::string out;
        for (auto const& held : player.m_spellCooldowns) // std::map: id order
        {
            char cell[128];
            std::snprintf(cell, sizeof(cell), "%u:%lld:%u:%u", held.first,
                          static_cast<long long>(held.second.end) - DC_TEST_FROZEN_NOW_MS, held.second.maxduration,
                          uint32(held.second.category));
            if (!out.empty())
                out += " ";
            out += cell;
        }
        return out.empty() ? "-" : out;
    }
} // namespace

int main(int argc, char** argv)
{
    if (argc != 4 && argc != 5)
    {
        std::fprintf(stderr, "usage: category_harness <SpellCategory.dbc> <records.tsv> <cases.tsv> [overlay.tsv]\n");
        return 2;
    }

    // The real store, the real parser, the generated file.
    if (!sSpellCategoryStore.Load(argv[1]))
    {
        std::fprintf(stderr, "the core's DBC loader refused %s\n", argv[1]);
        return 3;
    }

    // ...and then the world table's rows, if this run is the server's route,
    // before a single record is turned into a SpellInfo: the constructor
    // resolves Category once and keeps the pointer.
    if (argc == 5)
        LoadOverlay(argv[4]);

    LoadRecords(argv[2]);
    // ...and then the core's own loop over the spell store, which is the only
    // thing that makes a category mean "these spells".
    BuildSpellsByCategory();

    std::ifstream stream(argv[3]);
    std::string line;
    while (std::getline(stream, line))
    {
        if (line.empty())
            continue;
        std::istringstream cells(line);
        std::string kind;
        cells >> kind;
        if (kind == "rows")
        {
            std::printf("%u\n", sSpellCategoryStore.GetNumRows());
        }
        else if (kind == "lookup")
        {
            uint32 category = 0;
            cells >> category;
            SpellCategoryEntry const* entry = sSpellCategoryStore.LookupEntry(category);
            std::printf("%d %u\n", entry ? 1 : 0, entry ? entry->Flags : 0);
        }
        else if (kind == "category")
        {
            uint32 spellId = 0;
            cells >> spellId;
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info)
            {
                std::fprintf(stderr, "no record %u\n", spellId);
                return 3;
            }
            std::printf("%u\n", info->GetCategory());
        }
        else if (kind == "siblings")
        {
            uint32 category = 0;
            cells >> category;
            std::string out;
            SpellCategoryStore::const_iterator found = sSpellsByCategoryStore.find(category);
            if (found != sSpellsByCategoryStore.end())
            {
                std::vector<uint32> ids;
                for (auto const& member : found->second)
                    ids.push_back(member.second);
                std::sort(ids.begin(), ids.end());
                for (uint32 id : ids)
                {
                    if (!out.empty())
                        out += " ";
                    out += std::to_string(id);
                }
            }
            std::printf("%s\n", out.empty() ? "-" : out.c_str());
        }
        else if (kind == "cast")
        {
            uint32 spellId = 0;
            int32 flat = 0, percent = 0;
            cells >> spellId >> flat >> percent;
            std::printf("%s\n", Cast(spellId, flat, percent).c_str());
        }
        else
        {
            std::fprintf(stderr, "unknown case: %s\n", kind.c_str());
            return 2;
        }
    }
    return 0;
}
