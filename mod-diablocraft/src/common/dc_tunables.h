/*
 * World of DiabloCraft - shared tunables.
 *
 * One number that is tuned rather than D3's, read from dc_tunables. This is
 * the elite-affix mechanism (13-elite-affixes §2, dc_rift_elites.cpp) widened
 * to every category: one WORLD query builds an immutable snapshot, gameplay
 * reads that snapshot rather than SQL, and `.dc tunables reload` swaps a new
 * one in only when it built.
 *
 * Get() is the whole interface. Once the first snapshot exists it reads memory:
 * no database, no blocking, safe in a combat or tick path. The exception is the
 * very first call, which builds the snapshot itself if it runs before the
 * startup hook did - WorldScript order is the core's, not ours - and that one
 * call does query. It never throws; a name that is not in the table logs once
 * and returns 0, which is a bug in the caller, not a value to design around - a
 * migration must add the row, and code that has to behave when no one has
 * chosen a number yet asks Has() first.
 */
#ifndef DC_TUNABLES_H
#define DC_TUNABLES_H

#include <cstddef>
#include <string>

namespace DC::Tunables
{
    // tuned_value when one is set, d3_value otherwise, 0.0 when the row
    // is missing or has neither. Safe from any thread.
    double Get(std::string const& category, std::string const& name);

    // True when the row exists and has a usable number. For the caller that
    // has something sensible to do while a value is unset.
    bool Has(std::string const& category, std::string const& name);

    // Rebuild the snapshot from dc_tunables. Returns false and fills `error`
    // when the table cannot be read; the previous snapshot stays in use, as
    // ReloadAffixNumbers does. Called at startup and by `.dc tunables reload`.
    bool Reload(std::string& error);

    // How many rows the live snapshot holds; 0 before the first successful
    // load. Used by the command output and the startup log.
    std::size_t Count();

    void RegisterScripts();
} // namespace DC::Tunables

#endif
