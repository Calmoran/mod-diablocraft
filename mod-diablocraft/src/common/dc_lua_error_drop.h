// The Lua error drop: BugSack's "send to player" whisper is appended, raw, one stamped line per AceComm chunk, to
// <Diablocraft.LuaErrorDrop.Dir>/<YYYY-MM-DD>/<Character>.txt; scripts/lua_errors.py makes it readable. The wire is
// docs/research/bugsack-wire.md. The rules are here so the harness (test_lua_error_drop.py) compiles them;
// dc_lua_error_drop.cpp is the core glue (options, chat hook, core patch 0025's IsAddonWhisperDrop).
#ifndef DC_LUA_ERROR_DROP_H
#define DC_LUA_ERROR_DROP_H

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <set>
#include <string>
#include <system_error>

namespace DC::LuaErrorDrop
{
    // BugSack's addon prefix (BugSack.lua:503). A split send adds one marker byte to it, \x01 on the first chunk,
    // \x02 on each middle one, \x03 on the last (AceComm-3.0.lua:40-44); the client sends "<prefix>\t<text>".
    inline bool IsBugSack(std::string const& msg)
    {
        static std::string const prefix = "BugSack";
        if (msg.compare(0, prefix.size(), prefix) != 0)
            return false;
        std::size_t tab = prefix.size();
        if (tab < msg.size() && msg[tab] >= '\x01' && msg[tab] <= '\x03')
            ++tab;
        return tab < msg.size() && msg[tab] == '\t';
    }

    // One chunk, one line: "HH:MM:SS <the message as sent>". AceSerializer escapes every control byte, so a line
    // break in the text is not BugSack's; it becomes a space, which the reader's deserializer drops anyway.
    inline std::string Line(std::string const& clock, std::string msg)
    {
        for (char& c : msg)
            if (c == '\n' || c == '\r')
                c = ' ';
        return clock + " " + msg + "\n";
    }

    // <dir>/<YYYY-MM-DD>/<Character>.txt
    inline std::filesystem::path File(std::string const& dir, std::string const& date, std::string const& name)
    {
        return std::filesystem::path(dir) / date / (name + ".txt");
    }

    enum class Outcome
    {
        Written,
        CapReached, // the first line refused for this file: the caller logs it once
        Capped,     // every later one: silent until the next day's file
        Failed
    };

    // Appends under the per-file cap (a file is one character's day). Thread-safe.
    class Drop
    {
    public:
        Outcome Append(std::filesystem::path const& file, std::string const& line, std::uintmax_t cap)
        {
            std::lock_guard<std::mutex> guard(mutex);
            std::error_code ec;
            std::uintmax_t size = std::filesystem::file_size(file, ec);
            if (ec)
                size = 0;
            if (size + line.size() > cap)
                return capped.insert(file.string()).second ? Outcome::CapReached : Outcome::Capped;
            std::filesystem::create_directories(file.parent_path(), ec);
            if (ec)
                return Outcome::Failed;
            std::ofstream out(file, std::ios::binary | std::ios::app);
            out << line;
            return out ? Outcome::Written : Outcome::Failed;
        }

    private:
        std::mutex mutex;
        std::set<std::string> capped;
    };

    // Core patch 0025's question: an addon whisper to the drop name is not delivered and gets no "player not found"
    // notice (one per chunk otherwise). `to` comes normalized (normalizePlayerName), as the option is. Blank: off.
    inline bool IsDropName(std::string const& to, std::string const& name)
    {
        return !name.empty() && to == name;
    }

    void RegisterScripts();
} // namespace DC::LuaErrorDrop

#endif
