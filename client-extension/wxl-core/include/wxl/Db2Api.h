// The wxl-db2 service interface: what wxl-db2 publishes for wxl-adt/wxl-wmo/wxl-m2 (or any other
// extension) to consume via WXL_Api::GetInterface("wxl.db2", WXL_DB2_API_VERSION).
// Copyright (C) 2026 WarcraftXL
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

#ifndef WXL_DB2_API_H
#define WXL_DB2_API_H

#include <stddef.h>
#include <stdint.h>

// A second PluginApi.h-shaped header, published rather than handed out at load: wxl-db2's Table and
// Row are C++ types (a std::vector-backed row store) that cannot cross the boundary by value, so a
// table is an opaque handle and a row is an opaque handle scoped to it. Every field/relation lookup
// stays a call into wxl-db2's own code, which is the one binary whose STL layout can dereference them;
// only the plain values (uint32_t, const char*, counts) they resolve to cross back out. Plain C with
// __cdecl throughout, same reasoning as PluginApi.h.

#ifdef __cplusplus
extern "C" {
#endif

/// Bumped whenever the layout below changes. Independent of WXL_API_VERSION: a consumer records what
/// it compiled against and GetInterface only matches an exact version.
#define WXL_DB2_API_VERSION 1

/// Where a relationship obtains its source key, mirroring wxl::runtime::db2::RelationSource.
#define WXL_DB2_RELATION_FIELD     0
#define WXL_DB2_RELATION_ROW_ID    1
#define WXL_DB2_RELATION_PARENT_ID 2

/// One physical WDC field in file order. Arrays use elements > 1.
typedef struct WXL_Db2Field
{
    const char* name;
    uint16_t    elements;
} WXL_Db2Field;

/// One declared relationship to another table, mirroring wxl::runtime::db2::Relation.
typedef struct WXL_Db2Relation
{
    const char* name;
    uint32_t    source;       ///< one of WXL_DB2_RELATION_*
    const char* sourceField;  ///< used when source == WXL_DB2_RELATION_FIELD
    uint16_t    sourceElement;
    const char* targetTable;
    const char* targetField;  ///< "@id" when the target uses its row id
} WXL_Db2Relation;

/**
 * @brief Immutable declaration of one supported DB2 layout, mirroring wxl::runtime::db2::Definition.
 *
 * The arrays are borrowed for the duration of the Load call only; wxl-db2 copies what it needs.
 */
typedef struct WXL_Db2Definition
{
    const char*            name;
    const char*            filename;
    uint32_t                layoutHash;
    const WXL_Db2Field*    fields;
    uint32_t                fieldCount;
    const WXL_Db2Relation* relations;
    uint32_t                relationCount;
    int                     required;
} WXL_Db2Definition;

typedef struct WXL_Db2Api
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Decodes one table per @p definition.
     * @param definition   layout declaration; not retained past this call.
     * @param errorBuf     receives a failure reason; may be NULL.
     * @param errorBufSize size of @p errorBuf.
     * @return an opaque table handle, owned by wxl-db2, or NULL on failure.
     */
    void*(__cdecl* Load)(const WXL_Db2Definition* definition, char* errorBuf, size_t errorBufSize);

    /// Releases a table handle returned by Load.
    void(__cdecl* Release)(void* table);

    /// Row count and positional/keyed access. RowAt/FindRow return an opaque row handle, or NULL.
    uint32_t(__cdecl* RowCount)(void* table);
    const void*(__cdecl* RowAt)(void* table, uint32_t index);
    const void*(__cdecl* FindRow)(void* table, uint32_t id);

    uint32_t(__cdecl* RowId)(const void* row);
    uint32_t(__cdecl* RowParentId)(const void* row);

    /// Field value by name (as declared in the Definition passed to Load), element 0 for scalars.
    uint32_t(__cdecl* Value)(void* table, const void* row, const char* field, uint32_t element);
    size_t(__cdecl* FieldIndex)(void* table, const char* field);
    size_t(__cdecl* ElementCount)(void* table, const char* field);

    /// Resolves a declared relation's key for one row (a foreign row id, ready for FindRow on the
    /// target table's own handle).
    uint32_t(__cdecl* RelationKey)(void* table, const void* row, const char* relation);

    uint32_t(__cdecl* LayoutHash)(void* table);
    uint32_t(__cdecl* TableHash)(void* table);

    /// Inline string field by name, element 0 for scalars. NULL for a null table, a null row, an
    /// unknown field, a column that is not an inline string, or a row whose section carries no usable
    /// string block -- a TACT-encrypted section is that last case. An empty string is "", not NULL.
    /// Version 2 appends this at the end of the struct: WXL_Db2Api only ever grows there, which is
    /// what structSize measures.
    const char*(__cdecl* String)(void* table, const void* row, const char* field, uint32_t element);
} WXL_Db2Api;

#ifdef __cplusplus
}
#endif

#endif // WXL_DB2_API_H
