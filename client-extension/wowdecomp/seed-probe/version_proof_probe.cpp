// The version-proof probe: runs the client's own checksum code on this exe as the client runs it on
// WowClient64.exe (ChecksumExecutables: IOsVersionChecksum with no path, loaded) and writes every byte
// it hashes to the file named on the command line. check_proof.py then compares those bytes with
// version_seed.py's walk over this exe's file: equal, the seed from the file holds for an exe built
// with the series, wherever ASLR loaded it.
//
// Exit 0: the walk ran. Exit 1: bad arguments or the output file. Exit 2: the walk returned 0.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <windows.h>
#include "Engine/Source/Os/OsFile.h"
#include "Engine/Source/Os/OsVersionHash.h"
#include "Engine/Source/Storm/H/storm.h"

// The Storm and Os calls OsVersionHash.cpp links against. Memory goes to the CRT; the file and UTF-8
// calls serve only the path given (DLL or file) branches, which the probe does not take.
void* STORMAPI SMemAlloc(size_t bytes, const char*, int32_t, uint32_t) {
    return malloc(bytes ? bytes : 1);
}

int32_t STORMAPI SMemFree(void* ptr, const char*, int32_t, uint32_t) {
    free(ptr);
    return 1;
}

void* STORMAPI SMemReAlloc(void* ptr, size_t bytes, const char*, int32_t, uint32_t flags) {
    if (flags & SMEM_FLAG_NOREALLOC) {
        return nullptr;
    }
    return realloc(ptr, bytes ? bytes : 1);
}

int32_t STORMAPI SUniConvertUTF8to16(uint16_t*, uint32_t, const char*, uint32_t, uint32_t*, uint32_t*) {
    return 0;
}

int32_t STORMAPI SUniConvertUTF8to16Len(const char*, uint32_t, uint32_t*) {
    return 0;
}

HOSFILE OsCreateFile(const char*, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) {
    return reinterpret_cast<HOSFILE>(INVALID_HANDLE_VALUE);
}

uint64_t OsGetFileSize(HOSFILE) {
    return 0;
}

int32_t OsReadFile(HOSFILE, void*, uint32_t, uint32_t*) {
    return 0;
}

bool OsCloseFile(HOSFILE) {
    return false;
}

class StreamWriter : public IOsVersionHashCallback {
    public:
    FILE* m_file;
    uint64_t m_total = 0;

    explicit StreamWriter(FILE* file) : m_file(file) {
    }

    void Process(const void* data, uint32_t size) override {
        fwrite(data, 1, size, m_file);
        m_total += size;
    }
};

int main(int argc, char** argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: version_proof_probe <stream out>\n");
        return 1;
    }

    FILE* out = fopen(argv[1], "wb");
    if (!out) {
        return 1;
    }

    const uint8_t* loaded = reinterpret_cast<const uint8_t*>(GetModuleHandleW(nullptr));
    const IMAGE_NT_HEADERS64* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(loaded + reinterpret_cast<const IMAGE_DOS_HEADER*>(loaded)->e_lfanew);

    StreamWriter writer(out);
    int32_t result = IOsVersionChecksum(writer, nullptr, 1);
    fclose(out);

    printf("loaded_at=0x%llx header_image_base=0x%llx dll_characteristics=0x%04x walk=%d hashed=%llu bytes\n",
           static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(loaded)),
           static_cast<unsigned long long>(nt->OptionalHeader.ImageBase), nt->OptionalHeader.DllCharacteristics, result,
           static_cast<unsigned long long>(writer.m_total));

    return result ? 0 : 2;
}
