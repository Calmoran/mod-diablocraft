"""Reverse and replay the numbered core patches from 0010 up in memory, preserving the live build tree.

It used to replay 0010-0012 only. A later patch (0014, 0016...) edits the same files, so
reversing 0012 alone no longer matched its hunks (diablocraft-lx43). The whole stack from
0010 is reversed newest first and replayed oldest first, which is the order it was applied
in; hunks for new files and for files outside src/server/game are not part of this check.
"""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
PATCHES=sorted(p for p in (ROOT/'core-patches').glob('[0-9][0-9][0-9][0-9]-*.patch') if int(p.name[:4])>=10)

def apply(buffers, patch, reverse=False):
    lines=patch.read_text(encoding='utf-8').splitlines(True)
    path=None;i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('--- '):
            path=line[6:].strip() if line.startswith('--- a/') else None
            assert path is None or '..' not in path
            if path is not None and not path.startswith('src/server/game/'):path=None
            if path is not None:buffers.setdefault(path,(ROOT/'azerothcore-wotlk'/path).read_text(encoding='utf-8').splitlines(True))
        elif line.startswith('@@') and path is None:
            i+=1
            while i<len(lines) and not lines[i].startswith(('@@','--- ','diff ')):i+=1
            continue
        elif line.startswith('@@'):
            counts=re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@',line)
            assert counts,line
            old=[];new=[];i+=1
            while i<len(lines) and not lines[i].startswith(('@@','--- ','diff ')):
                current=lines[i]
                assert current[0] in ' +-'
                if current[0] in ' -':old.append(current[1:])
                if current[0] in ' +':new.append(current[1:])
                i+=1
            assert len(old)==int(counts[2]) and len(new)==int(counts[4]), (patch,path)
            if reverse:old,new=new,old
            content=buffers[path]
            matches=[n for n in range(len(content)-len(old)+1) if content[n:n+len(old)]==old]
            assert matches,(patch.name,path,reverse)
            expected=int(counts[3] if reverse else counts[1])-1
            matches.sort(key=lambda n:abs(n-expected))
            assert len(matches)==1 or abs(matches[0]-expected)<abs(matches[1]-expected), (patch.name,path,'ambiguous hunk')
            start=matches[0];content[start:start+len(old)]=new
            continue
        i+=1

def main():
    buffers={}
    for patch in reversed(PATCHES):apply(buffers,patch,True)
    for patch in PATCHES:apply(buffers,patch)
    for path,lines in buffers.items():
        assert ''.join(lines)==(ROOT/'azerothcore-wotlk'/path).read_text(encoding='utf-8'),path
    print(f'PASS {len(PATCHES)} numbered patches reverse/replay exactly across {len(buffers)} core files; no core files written.')

if __name__=='__main__':main()
