/*
 * Doubles for the core's database types, for the Mystic crafting harness (diablocraft-xw2m return).
 * src/items/dc_items.h includes "DatabaseEnv.h"; this one is found first by the harness's include path.
 * Nothing of the module is restated: the harness compiles the module's own text against these.
 *
 *   CharacterDatabaseTransaction   records every statement Append()ed, with the {} filled in, in order
 *   CharacterDatabase.Query        answers the dc_enchant_offer read from the harness's own table
 *   WorldDatabase.Query            answers from the harness's own rows (the socket slot cap)
 */
#ifndef MYSTIC_SHIM_DATABASEENV_H
#define MYSTIC_SHIM_DATABASEENV_H

#include <algorithm>
#include <cstdint>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

using uint8 = std::uint8_t;
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

class Field
{
public:
    Field(std::string v = "", bool null = false) : v_(std::move(v)), null_(null) {}
    template <class T>
    T Get() const
    {
        std::istringstream in(v_);
        double d = 0;
        in >> d;
        return static_cast<T>(d);
    }
    bool IsNull() const { return null_; }

private:
    std::string v_;
    bool null_;
};
template <>
inline std::string Field::Get<std::string>() const
{
    return v_;
}

class ResultSet
{
public:
    std::vector<std::vector<Field>> rows;
    std::size_t at = 0;
    Field* Fetch() { return rows[at].data(); }
    Field& operator[](std::size_t i) { return rows[at][i]; }
    bool NextRow() { return ++at < rows.size(); }
};
using QueryResult = std::shared_ptr<ResultSet>;

inline std::string Fill(std::string text)
{
    return text;
}
template <class A, class... R>
std::string Fill(std::string text, A const& a, R const&... rest)
{
    auto at = text.find("{}");
    if (at == std::string::npos)
        return text;
    std::ostringstream out;
    out << a;
    text.replace(at, 2, out.str());
    return Fill(text, rest...);
}

struct Transaction
{
    std::vector<std::string> statements;
    template <class... A>
    void Append(char const* text, A const&... a)
    {
        statements.push_back(Fill(text, a...));
    }
};
using CharacterDatabaseTransaction = std::shared_ptr<Transaction>;

// The harness owns these.
extern std::vector<std::vector<Field>> g_offerTable;
extern std::vector<std::vector<Field>> g_worldRows;

inline QueryResult Rows(std::vector<std::vector<Field>> const& table)
{
    if (table.empty())
        return nullptr;
    auto result = std::make_shared<ResultSet>();
    result->rows = table;
    return result;
}

struct CharDb
{
    template <class... A>
    QueryResult Query(char const* text, A const&...)
    {
        std::string const sql = text;
        if (sql.find("FROM dc_enchant_offer") == std::string::npos)
            return nullptr;
        // The last field of a row is its choice_id, which the module never selects: it is what ORDER BY sorts by.
        auto rows = g_offerTable;
        auto key = [](std::vector<Field> const& row) { return row.back().Get<int>(); };
        if (sql.find("ORDER BY choice_id DESC") != std::string::npos)
            std::stable_sort(rows.begin(), rows.end(), [&](auto const& a, auto const& b) { return key(a) > key(b); });
        else if (sql.find("ORDER BY choice_id") != std::string::npos)
            std::stable_sort(rows.begin(), rows.end(), [&](auto const& a, auto const& b) { return key(a) < key(b); });
        return Rows(rows);
    }
    void EscapeString(std::string&) {}
};
struct WorldDb
{
    template <class... A>
    QueryResult Query(char const*, A const&...)
    {
        return Rows(g_worldRows);
    }
};
inline CharDb CharacterDatabase;
inline WorldDb WorldDatabase;

#endif
