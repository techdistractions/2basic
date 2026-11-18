#!/usr/bin/env python3
"""Create/verify a non-bootable 360K FAT12 B: data disk for 2BASIC.
Root contains the application and help. Programs use real 8.3 subfolders.
No OS8088 system disk is altered or embedded.
"""
from __future__ import annotations
import argparse
import struct
from pathlib import Path
from collections import OrderedDict

SIZE=368640
SECTOR=512
SPC=2
CLUSTER=SECTOR*SPC
RESERVED=1
FATS=2
FATSECT=2
ROOT_ENTRIES=112
ROOT_SECTORS=ROOT_ENTRIES*32//SECTOR
FIRST_DATA_SECTOR=RESERVED+FATS*FATSECT+ROOT_SECTORS
DATA_OFFSET=FIRST_DATA_SECTOR*SECTOR
FAT_OFFSET=RESERVED*SECTOR
ROOT_OFFSET=(RESERVED+FATS*FATSECT)*SECTOR
CLUSTER_COUNT=(SIZE-DATA_OFFSET)//CLUSTER


def name83(s:str) -> bytes:
    s=s.upper()
    if '.' in s:
        parts=s.split('.')
        if len(parts)!=2: raise ValueError('invalid 8.3 path component: '+s)
        a,b=parts
    else: a,b=s,''
    if not a or len(a)>8 or len(b)>3 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in a+b):
        raise ValueError('not 8.3: '+s)
    return (a.ljust(8)+b.ljust(3)).encode('ascii')


def entry(name:str|bytes, attr:int, cluster:int=0, size:int=0) -> bytes:
    b=bytearray(32)
    b[:11]=name if isinstance(name,bytes) else name83(name)
    b[11]=attr
    struct.pack_into('<H',b,26,cluster)
    struct.pack_into('<I',b,28,size)
    return bytes(b)


def put_fat(fat:bytearray,index:int,value:int)->None:
    off=index*3//2
    if index&1:
        fat[off]=(fat[off]&15)|((value&15)<<4)
        fat[off+1]=(value>>4)&255
    else:
        fat[off]=value&255
        fat[off+1]=(fat[off+1]&240)|((value>>8)&15)


def get_fat(fat:bytes,index:int)->int:
    off=index*3//2
    return ((fat[off]>>4)|(fat[off+1]<<4)) if index&1 else (fat[off]|((fat[off+1]&15)<<8))

class Node:
    def __init__(self,name:str,parent:Node|None):
        self.name=name
        self.parent=parent
        self.dirs:dict[str,Node]=OrderedDict()
        self.files:dict[str,bytes]=OrderedDict()
        self.cluster=0
        self.allocation=[]

    def path(self):
        return (self.parent.path()+'/' if self.parent else '/')+self.name if self.parent else ''


def build(output:Path, data:dict[str,bytes]):
    root=Node('',None)
    for path,contents in data.items():
        parts=path.strip('/').replace('\\','/').split('/')
        if not parts or any(not x for x in parts):raise ValueError('invalid path '+path)
        node=root
        for part in parts[:-1]:
            name83(part)
            node=node.dirs.setdefault(part.upper(),Node(part.upper(),node))
        filename=parts[-1].upper()
        name83(filename)
        if filename in node.files:raise ValueError('duplicate '+path)
        node.files[filename]=contents
    flatdirs=[]
    def visit(node):
        for d in node.dirs.values():
            flatdirs.append(d)
            visit(d)
    visit(root)
    nodes=[root]+flatdirs
    for n in nodes:
        need=len(n.dirs)+len(n.files)+(2 if n.parent else 1)
        maxdir=ROOT_ENTRIES if n.parent is None else CLUSTER//32
        if need>maxdir:raise ValueError(f'directory full {n.path()}: {need}>{maxdir}')
    out=bytearray(SIZE)
    boot=bytearray(SECTOR)
    boot[:3]=b'\xEB\x3C\x90'
    boot[3:11]=b'2BASIC  '
    struct.pack_into('<HBHBHHBHHH',boot,11,512,2,1,2,112,720,0xFD,2,9,2)
    boot[43:54]=b'2BASIC     '
    boot[54:62]=b'FAT12   '
    boot[510:512]=b'\x55\xAA'
    out[:SECTOR]=boot
    fat=bytearray(FATSECT*SECTOR)
    fat[:3]=b'\xFD\xFF\xFF'
    nextclus=2
    # Directory clusters allocated first; each leaf directory fits one 1024B block.
    for d in flatdirs:
        d.cluster=nextclus
        put_fat(fat,nextclus,0xFFF)
        nextclus+=1
    chains=[]
    for n in nodes:
        for filename,content in n.files.items():
            count=(len(content)+CLUSTER-1)//CLUSTER
            if count<1:raise ValueError('empty files not supported: '+filename)
            start=nextclus
            for i in range(count):
                c=start+i
                if c-2>=CLUSTER_COUNT:raise ValueError('360K disk full')
                put_fat(fat,c,0xFFF if i==count-1 else c+1)
                offset=DATA_OFFSET+(c-2)*CLUSTER
                out[offset:offset+CLUSTER]=content[i*CLUSTER:(i+1)*CLUSTER].ljust(CLUSTER,b'\0')
            nextclus+=count
            n.allocation.append((filename,start,len(content)))
            chains.append((n.path()+'/'+filename,start,len(content),content))
    if nextclus-2>CLUSTER_COUNT:raise ValueError('too many clusters')
    for n in nodes:
        rows=[]
        if n.parent is None:
            rows.append(entry(b'2BASIC     ',0x08))
        else:
            rows.append(entry(b'.          ',0x10,n.cluster))
            rows.append(entry(b'..         ',0x10,n.parent.cluster))
        for name,d in n.dirs.items():rows.append(entry(name,0x10,d.cluster))
        for name,first,size in n.allocation:rows.append(entry(name,0x20,first,size))
        if n.parent is None:
            pos=ROOT_OFFSET
            capacity=ROOT_ENTRIES*32
        else:
            pos=DATA_OFFSET+(n.cluster-2)*CLUSTER
            capacity=CLUSTER
        content=b''.join(rows)
        if len(content)>capacity:raise ValueError('directory does not fit')
        out[pos:pos+len(content)]=content
    for i in range(FATS):
        p=(RESERVED+i*FATSECT)*SECTOR
        out[p:p+len(fat)]=fat
    if out[SECTOR:SECTOR+len(fat)]!=out[SECTOR+len(fat):SECTOR+2*len(fat)]:
        raise AssertionError('FAT copies differ')
    def read_chain(first,size):
        b=bytearray();seen=set();c=first
        while c<0xFF8:
            if c in seen or c<2 or c-2>=CLUSTER_COUNT:raise AssertionError('invalid FAT chain')
            seen.add(c)
            off=DATA_OFFSET+(c-2)*CLUSTER
            b.extend(out[off:off+CLUSTER])
            c=get_fat(fat,c)
        return bytes(b[:size])
    for path,first,size,content in chains:
        if read_chain(first,size)!=content:raise AssertionError('readback '+path)
    # Recursively verify directory entries, first clusters and parent pointers.
    for n in nodes:
        pos=ROOT_OFFSET if n.parent is None else DATA_OFFSET+(n.cluster-2)*CLUSTER
        raw=out[pos:pos+(ROOT_ENTRIES*32 if n.parent is None else CLUSTER)]
        entries={bytes(raw[i:i+11]):bytes(raw[i:i+32]) for i in range(0,len(raw),32) if raw[i] not in (0x00,0xE5)}
        if n.parent is not None:
            assert struct.unpack_from('<H',entries[b'.          '],26)[0]==n.cluster
            assert struct.unpack_from('<H',entries[b'..         '],26)[0]==n.parent.cluster
        for d in n.dirs.values():
            assert struct.unpack_from('<H',entries[name83(d.name)],26)[0]==d.cluster
        for name,first,size in n.allocation:
            e=entries[name83(name)]
            assert struct.unpack_from('<HI',e,26)==(first,size)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(out)
    assert output.stat().st_size==SIZE
    print(f'B: FAT12 360K verified; {len(flatdirs)} directories, {len(chains)} files; {nextclus-2} clusters used/{CLUSTER_COUNT}')
    for path,first,size,_ in chains:print(f' {path:<32} {size:>6} bytes @ FAT cluster {first}')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--binary',type=Path,required=True)
    ap.add_argument('--bres-binary',type=Path,required=True)
    ap.add_argument('--cards',type=Path,required=True)
    ap.add_argument('--bres-demo',type=Path,required=True)
    ap.add_argument('--samples',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    s=a.samples
    disk=OrderedDict([
        ('2BASIC.O88',a.binary.read_bytes()),
        ('2BRES.O88',a.bres_binary.read_bytes()),
        ('RESGUIDE.TXT',(s/'RESGUIDE.TXT').read_bytes()),
        ('TESTS/AUTOR3.BAS',(s/'AUTOR3.BAS').read_bytes()),
        ('TESTS/RESDEMO.RES',(s.parent/'resources/demo/RESDEMO.RES').read_bytes()),
        ('TESTS/RESINFO.TXT',(s/'RESINFO.TXT').read_bytes()),
        ('TESTS/TARGETS.TXT',(s.parent/'resources/demo/TARGETS.TXT').read_bytes()),
        ('TESTS/MAP.DAT',(s.parent/'resources/demo/MAP.DAT').read_bytes()),
        ('TOOLS/2BRES/EXAMPLE.TXT',(a.bres_demo/'EXAMPLE.TXT').read_bytes()),
        ('GAMES/BLACKJAK/CARDS.MF',(a.cards/'CARDS.MF').read_bytes()),
        ('GAMES/2B99/2B99.MF',(s/'2B99.MF').read_bytes()),
        ('TOOLS/2BRES/SAMPLE.BMP',(a.bres_demo/'SAMPLE.BMP').read_bytes()),
        ('TOOLS/2BRES/COLOR4.BMP',(a.bres_demo/'COLOR4.BMP').read_bytes()),
        ('TOOLS/2BRES/VALUES.TXT',(a.bres_demo/'VALUES.TXT').read_bytes()),
        ('TOOLS/2BRES/MIXED.RES',(a.bres_demo/'MIXED.RES').read_bytes()),
        ('TOOLS/2BRES/NOTES.TXT',(a.bres_demo/'NOTES.TXT').read_bytes()),
        ('TOOLS/2BRES/MAP.DAT',(a.bres_demo/'MAP.DAT').read_bytes()),
        ('HELP.TXT',(s/'HELP.TXT').read_bytes()),
        ('README.TXT',(s/'README.TXT').read_bytes()),
        ('GAMES/2B99/2B99.BAS',(s/'2B99.BAS').read_bytes()),
        ('GAMES/2B99/2B99.RES',(s/'2B99.RES').read_bytes()),
        ('GAMES/2BCHECK/2BCHECK.BAS',(s/'2BCHECK.BAS').read_bytes()),
        ('GAMES/BLACKJAK/BLACKJAK.BAS',(s/'BLACKJAK.BAS').read_bytes()),
        ('GAMES/BLACKJAK/CARDS.RES',(a.cards/'CARDS.RES').read_bytes()),
        ('GAMES/BLACKJAK/2BRES.TXT',(a.cards/'2BRES.TXT').read_bytes()),
        ('EXAMPLES/BASICS.BAS',(s.parent/'examples/BASICS.BAS').read_bytes()),
        ('EXAMPLES/DRAWING.BAS',(s.parent/'examples/DRAWING.BAS').read_bytes()),
        ('EXAMPLES/FORMS.BAS',(s.parent/'examples/FORMS.BAS').read_bytes()),
        ('EXAMPLES/SOUND.BAS',(s.parent/'examples/SOUND.BAS').read_bytes()),
        ('EXAMPLES/RESDEMO.BAS',(s.parent/'examples/RESDEMO.BAS').read_bytes()),
        ('EXAMPLES/RESDEMO.RES',(s.parent/'resources/demo/RESDEMO.RES').read_bytes()),
        ('TESTS/UAT.TXT',(s/'UAT.TXT').read_bytes()),
        ('TESTS/MULTIBAS/ONE.BAS',(s/'UTMULTI-ONE.BAS').read_bytes()),
        ('TESTS/MULTIBAS/TWO.BAS',(s/'UTMULTI-TWO.BAS').read_bytes()),
        ('TESTS/2B99.RES',(s/'2B99.RES').read_bytes()),
        ('TESTS/UTICON.BMP',(s/'UTICON.BMP').read_bytes()),
    ])
    for n in range(4):
        disk[f'GAMES/BLACKJAK/CARDS{n}.BMP']=(a.cards/f'CARDS{n}.BMP').read_bytes()
    for p in ('AUTOLANG','AUTOGFX','AUTOPRMT','UTVIS','UTSTR','UTARRAY','UTCORE','UTGFX','UTBMP','UTFORM','UTINPUT','UTSOUND','UTSTORE','AUTOFORM','EVENTUI','FORMISO','EVTSCAN'):
        disk[f'TESTS/{p}.BAS']=(s/(p+'.BAS')).read_bytes()
    build(a.output,disk)

if __name__=='__main__':main()
