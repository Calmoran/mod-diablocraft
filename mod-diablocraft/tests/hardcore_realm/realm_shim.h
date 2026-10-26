/*
 * Doubles for the hardcore realm writer (11 H4, 2026-09-21).
 *
 * Nothing here models the module's own logic: `RealmMode` and `EnsureMode` are
 * extracted from src/hardcore/dc_hardcore.cpp and compiled as they are, beside
 * the `Name`/`Parse`/`Load`/`Forget` helpers they call. What this file supplies
 * is the world around them - a config that answers one key, a characters
 * database that accepts exactly the two statement shapes the module sends, and
 * a player that has a guid and a name.
 *
 * The database double is deliberately strict. It refuses any statement it does
 * not recognise, so a writer that started using REPLACE, or an UPDATE, would
 * fail the suite rather than quietly pass it: the permanence of the row (H4) is
 * the thing being tested, and INSERT IGNORE is how it is kept.
 */

#ifndef DC_HARDCORE_REALM_SHIM_H
#define DC_HARDCORE_REALM_SHIM_H

#include <cassert>
#include <cstdint>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#define LOG_INFO(...) ((void)0)
#define LOG_ERROR(...) ((void)0)

using uint8 = std::uint8_t;

// The enum is the header's, repeated rather than included: dc_hardcore.h drags
// in Player and the whole core with it.
enum class Mode { Unchosen, Normal, Hardcore };

// --- the query result the module reads ------------------------------------

struct Field
{
    std::string value;
    template <class T> T Get() const;
};
template <> inline std::string Field::Get<std::string>() const { return value; }
template <> inline uint8 Field::Get<uint8>() const { return value.empty() ? uint8(0) : uint8(value[0] - '0'); }

struct Row
{
    std::vector<Field> fields;
    Field const& operator[](std::size_t index) const { return fields[index]; }
};
using QueryResult = std::shared_ptr<Row>;

// --- the module's {} formatting -------------------------------------------

inline void Append(std::ostringstream& out, std::string const& value) { out << value; }
inline void Append(std::ostringstream& out, char const* value) { out << value; }
inline void Append(std::ostringstream& out, std::uint32_t value) { out << value; }

inline std::string Format(std::string const& text) { return text; }

template <class First, class... Rest>
std::string Format(std::string const& text, First const& first, Rest const&... rest)
{
    std::size_t const at = text.find("{}");
    assert(at != std::string::npos && "more arguments than placeholders");
    std::ostringstream out;
    out << text.substr(0, at);
    Append(out, first);
    return Format(out.str() + text.substr(at + 2), rest...);
}

// --- the characters database ----------------------------------------------

inline std::uint32_t NumberAfter(std::string const& text, std::string const& marker)
{
    std::size_t at = text.find(marker);
    assert(at != std::string::npos);
    at += marker.size();
    std::uint32_t value = 0;
    while (at < text.size() && text[at] >= '0' && text[at] <= '9')
        value = value * 10 + std::uint32_t(text[at++] - '0');
    return value;
}

struct Database
{
    // guid -> the mode column, which is the whole row this suite cares about.
    std::unordered_map<std::uint32_t, std::string> rows;
    // Every statement the module sent, in order, so a test can count writes.
    std::vector<std::string> statements;
    // A write that never lands: the DB is down, or the row was refused.
    bool accepts = true;

    template <class... Args>
    QueryResult Query(std::string const& text, Args const&... args)
    {
        std::string const sql = Format(text, args...);
        statements.push_back(sql);
        assert(sql.rfind("SELECT mode FROM dc_character_mode WHERE guid=", 0) == 0 &&
               "the module read something this double does not answer");
        auto found = rows.find(NumberAfter(sql, "guid="));
        if (found == rows.end())
            return QueryResult();
        return std::make_shared<Row>(Row{{Field{found->second}}});
    }

    template <class... Args>
    void DirectExecute(std::string const& text, Args const&... args)
    {
        std::string const sql = Format(text, args...);
        statements.push_back(sql);
        assert(sql.rfind("INSERT IGNORE INTO dc_character_mode", 0) == 0 &&
               "the mode row may only ever be inserted, never rewritten (11 H4)");
        if (!accepts)
            return;
        std::size_t const quote = sql.find('\'');
        assert(quote != std::string::npos);
        std::string const mode = sql.substr(quote + 1, sql.find('\'', quote + 1) - quote - 1);
        // IGNORE: an existing row wins, which is what makes the choice permanent.
        rows.emplace(NumberAfter(sql, "VALUES ("), mode);
    }

    void EscapeString(std::string&) const { }

    unsigned Writes() const
    {
        unsigned count = 0;
        for (auto const& sql : statements)
            if (sql.rfind("INSERT", 0) == 0)
                ++count;
        return count;
    }
};

inline Database CharacterDatabase;

// --- the realm's config ----------------------------------------------------

struct ConfigMgr
{
    bool hardcore = false;
    unsigned reads = 0;

    template <class T>
    T GetOption(std::string const& name, T fallback) const
    {
        assert(name == "Diablocraft.Hardcore.Enable" && "the realm setting is one named key");
        (void)fallback;
        const_cast<ConfigMgr*>(this)->reads++;
        return T(hardcore);
    }
};

inline ConfigMgr configMgr;
inline ConfigMgr* sConfigMgr = &configMgr;

// --- the player ------------------------------------------------------------

struct Guid
{
    std::uint32_t counter = 0;
    std::uint32_t GetCounter() const { return counter; }
};

// The core's flag and its pinned value (Player.h:592). The core clears it at
// CharacterHandler.cpp:1139 - after every OnPlayerLogin hook at :1136 and
// before OnPlayerFirstLogin at :1141 - which is what StartOwed reads.
enum AtLoginFlags { AT_LOGIN_FIRST = 0x20 };

struct Player
{
    Guid guid;
    std::uint32_t account = 1;
    std::uint64_t money = 0;
    unsigned atLogin = AT_LOGIN_FIRST;
    Guid GetGUID() const { return guid; }
    char const* GetName() const { return "Test"; }
    bool HasAtLoginFlag(AtLoginFlags flag) const { return (atLogin & unsigned(flag)) != 0; }
};

// The file-local state the extracted helpers share.
inline std::mutex dataMutex;
inline std::unordered_map<std::uint32_t, Mode> modes;

#endif // DC_HARDCORE_REALM_SHIM_H
