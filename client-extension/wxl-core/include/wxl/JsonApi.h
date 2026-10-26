// The wxl-json service interface: what wxl-json publishes for any other extension to consume via
// WXL_Api::GetInterface("wxl.json", WXL_JSON_API_VERSION).
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

#ifndef WXL_JSON_API_H
#define WXL_JSON_API_H

#include <stddef.h>
#include <stdint.h>

// A parsed document is a tree of std::string and std::vector, which is a type that cannot cross a
// module boundary by value: the memory is allocated by wxl-json's CRT and would be freed by the
// consumer's, and the layout of both containers depends on _ITERATOR_DEBUG_LEVEL and on which CRT
// flavour each binary was linked against. So a document is an OPAQUE HANDLE and a value inside it is
// an INDEX into it; every read stays a call into wxl-json, the one binary whose STL layout can
// dereference the tree, and only plain values (uint32_t, int64_t, const char*, counts) cross back
// out. Plain C with __cdecl throughout, same reasoning as PluginApi.h.

#ifdef __cplusplus
extern "C" {
#endif

/// Bumped whenever the layout below changes. Independent of WXL_API_VERSION: a consumer records what
/// it compiled against and GetInterface only matches an exact version.
#define WXL_JSON_API_VERSION 1

/// One value inside one document, addressed by index rather than by pointer.
///
/// Zero is NO NODE, and it is a legal argument to every call below: the type of node 0 is
/// WXL_JSON_NONE, its counts are 0, its children are node 0, and its scalar reads return the
/// caller's fallback. A lookup that finds nothing therefore chains -- Find(Find(root, "a"), "b") is
/// as safe to write as it looks, and a consumer tests once, where it wants to report the failure.
typedef uint32_t WXL_JsonNode;

/// What one node is. WXL_JSON_NONE belongs to node 0 alone and is what "absent" reads as; a JSON
/// `null` that is really written in the document is WXL_JSON_NULL, so the two stay distinguishable.
#define WXL_JSON_NONE    0
#define WXL_JSON_NULL    1
#define WXL_JSON_BOOL    2
#define WXL_JSON_INTEGER 3
#define WXL_JSON_STRING  4
#define WXL_JSON_ARRAY   5
#define WXL_JSON_OBJECT  6

/// How ParseClientFile ended, reported through its outStatus parameter. The two failures are
/// separate because they are separate mistakes with separate fixes: a file nobody can find, and a
/// file found and malformed.
#define WXL_JSON_OK         0
#define WXL_JSON_UNREADABLE 1
#define WXL_JSON_MALFORMED  2

/// What a file looked like when it was last examined, for the change check below. Opaque to the
/// caller: it is declared, zeroed once, and handed back to FileChanged from then on.
///
/// The size rides along with the write time because a filesystem's write time has a granularity,
/// and two saves inside one tick of it carry the same timestamp.
typedef struct WXL_JsonStamp
{
    uint32_t present;    ///< nonzero when a candidate existed at the last check
    uint64_t writeTime;  ///< last-write time as a FILETIME, high dword first
    uint64_t size;       ///< file size in bytes
} WXL_JsonStamp;

typedef struct WXL_JsonApi
{
    uint32_t structSize;
    uint32_t apiVersion;

    /**
     * @brief Parses one document out of a buffer already in memory.
     * @param data        buffer start; may be NULL only when size is 0. Not retained past this call.
     * @param size        buffer length in bytes. The buffer need not be NUL terminated.
     * @param errorText   on failure, receives what was wrong; may be NULL.
     * @param errorOffset on failure, receives the byte index it applies to, counted from zero so it
     *                    lines up with an editor's "go to byte"; may be NULL.
     * @return an opaque document handle, owned by wxl-json and released with Free, or NULL.
     *
     * The message written to @p errorText is owned by wxl-json and stays valid until the next parse
     * ON THE SAME THREAD.
     *
     * A UTF-8 byte-order mark at the start is skipped. Trailing content after the document is a
     * failure rather than a stop.
     */
    void*(__cdecl* Parse)(const char* data, size_t size, const char** errorText, size_t* errorOffset);

    /**
     * @brief Reads one client file and parses it in a single call.
     * @param fileName       client-relative name, e.g. "JsonFilesClient\\Something.json".
     * @param looseRoots     directories tried in order before the client's own storage; NULL or a
     *                       count of 0 means the client's working directory alone.
     * @param looseRootCount how many entries @p looseRoots holds.
     * @param pathBuf        receives the path the bytes actually came from, NUL terminated and
     *                       truncated to fit: the loose path when one was read, "<fileName>
     *                       (archive)" when the client's storage answered, and @p fileName itself
     *                       when nothing was found. May be NULL.
     * @param pathBufSize    size of @p pathBuf in bytes.
     * @param outStatus      receives one of WXL_JSON_OK / UNREADABLE / MALFORMED; may be NULL.
     * @param errorText      on a malformed file, the parse message; may be NULL.
     * @param errorOffset    on a malformed file, the byte index; may be NULL.
     * @return an opaque document handle, or NULL on either failure.
     *
     * LOOSE FIRST, then the client's storage. The client's storage layer caches what it has opened,
     * so a file read straight off disk is the copy an editor just saved; an archived file is the
     * copy that ships. An empty loose file is a failed save rather than an empty document, and the
     * search moves on to the next candidate.
     */
    void*(__cdecl* ParseClientFile)(const char* fileName, const char* const* looseRoots,
                                    uint32_t looseRootCount, char* pathBuf, size_t pathBufSize,
                                    int* outStatus, const char** errorText, size_t* errorOffset);

    /// Releases a document handle returned by Parse or ParseClientFile, and every string that came
    /// out of it. NULL is accepted and does nothing.
    void(__cdecl* Free)(void* document);

    /// The document's outermost value. Node 0 for a NULL handle.
    WXL_JsonNode(__cdecl* Root)(void* document);

    /// One of WXL_JSON_NONE through WXL_JSON_OBJECT.
    uint32_t(__cdecl* NodeType)(void* document, WXL_JsonNode node);

    /// Object members, in the order the document writes them -- which is what lets a message name a
    /// member the way a reader sees it in the file. 0 and node 0 for anything that is not an object.
    uint32_t(__cdecl* MemberCount)(void* document, WXL_JsonNode node);

    /**
     * @brief The name of member @p index.
     * @param outLength receives the name's length in bytes; may be NULL.
     * @return a NUL-terminated string owned by the document and valid until it is freed, or "" when
     *         the node is not an object or the index is past the end.
     */
    const char*(__cdecl* MemberName)(void* document, WXL_JsonNode node, uint32_t index,
                                     size_t* outLength);

    /// The value of member @p index, or node 0.
    WXL_JsonNode(__cdecl* MemberAt)(void* document, WXL_JsonNode node, uint32_t index);

    /// The member named @p name, or node 0 when the node is not an object or has no such member.
    /// Both answer node 0 because a consumer that separates "absent" from "wrong type" does so by
    /// asking NodeType, and one that does not treats them alike anyway.
    WXL_JsonNode(__cdecl* Find)(void* document, WXL_JsonNode node, const char* name);

    /// Array elements. 0 and node 0 for anything that is not an array.
    uint32_t(__cdecl* ItemCount)(void* document, WXL_JsonNode node);
    WXL_JsonNode(__cdecl* ItemAt)(void* document, WXL_JsonNode node, uint32_t index);

    /// The three scalar reads. Each returns @p fallback when the node is absent or of another type,
    /// so a missing value and a mistyped one have one behaviour the caller chose.
    int(__cdecl* Bool)(void* document, WXL_JsonNode node, int fallback);
    int64_t(__cdecl* Integer)(void* document, WXL_JsonNode node, int64_t fallback);

    /**
     * @brief The payload of a string node.
     * @param outLength receives the length in bytes of what is returned, or 0 when @p fallback is
     *                  returned; may be NULL.
     * @param fallback  returned verbatim when the node is absent or is not a string.
     * @return a NUL-terminated string owned by the document and valid until it is freed.
     */
    const char*(__cdecl* String)(void* document, WXL_JsonNode node, size_t* outLength,
                                 const char* fallback);

    /**
     * @brief Whether the file a reload would read has changed since @p stamp was taken.
     * @param fileName       the same name ParseClientFile is given.
     * @param looseRoots     the same roots, so what is stamped is what would be read.
     * @param looseRootCount how many entries @p looseRoots holds.
     * @param stamp          in/out: compared, then overwritten with what is there now.
     * @return nonzero when the stamp moved, in which case @p stamp now holds the new one.
     *
     * Only the loose copies are stamped: a file inside an archive cannot be edited in place while
     * the client holds it. Absence is itself a stamp, so deleting the loose copy reads as a change.
     *
     * One file-attribute query per loose candidate, against paths the OS has almost certainly
     * cached. A caller on a per-frame path still rate limits it, because nothing about the answer
     * gets more correct by being asked more often.
     */
    int(__cdecl* FileChanged)(const char* fileName, const char* const* looseRoots,
                              uint32_t looseRootCount, WXL_JsonStamp* stamp);
} WXL_JsonApi;

#ifdef __cplusplus
}
#endif

#endif // WXL_JSON_API_H
