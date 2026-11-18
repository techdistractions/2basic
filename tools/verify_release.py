#!/usr/bin/env python3
"""Validate OS8088 package headers, 2BR3 assets and FAT12 B: readback."""
from pathlib import Path
from hashlib import sha256
import struct
import sys
import subprocess

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'dist'


def verify_package(name):
    path=DEST/(name+'.O88')
    data=path.read_bytes()
    assert data[:3]==b'O8\x0a', f'{name}: invalid O88 package format'
    assert (data[3]&1)==1, f'{name}: expected embedded icon'
    assert data[12:15]==b'\xff\xd5\xcb',f'{name}: invalid dispatcher'
    assert data[15]==4, f'{name}: wrong worker stack class'
    entry=struct.unpack_from('<H',data,6)[0]
    image,bss=struct.unpack_from('<HH',data,8)
    assert entry>=96 and entry<len(data),f'{name}: entry not after full icon'
    assert image==len(data),f'{name}: invalid image length'
    assert image+bss<=0xfe00,f'{name}: package exceeds 8086 region capacity'
    print(f'{name}: image {image}, BSS {bss}, headroom {0xfe00-image-bss} bytes')
    return data


def fat_next(table,c):
    i=(c*3)//2
    return ((table[i]>>4)|(table[i+1]<<4)) if c&1 else table[i]|((table[i+1]&15)<<8)


def extract(disk):
    assert len(disk)==368640 and disk[510:512]==b'\x55\xaa'
    assert disk[512:1536]==disk[1536:2560], 'FAT copies differ'
    tab=disk[512:1536]
    def chain(c,sz):
        if not sz:return b''
        seen=set();data=bytearray()
        while c<0xff8 and len(data)<sz:
            assert 2<=c<356 and c not in seen,('invalid FAT chain',c)
            seen.add(c)
            off=6144+(c-2)*1024
            data+=disk[off:off+1024]
            c=fat_next(tab,c)
        assert len(data)>=sz,'short FAT data'
        return bytes(data[:sz])
    files={}
    def walk(c,prefix=''):
        ent=disk[2560:2560+112*32] if c==0 else chain(c,1024)
        for pos in range(0,len(ent),32):
            e=ent[pos:pos+32]
            if e[0]==0:break
            if e[0]==0xe5 or e[11]&8:continue
            stem=e[:8].decode('ascii').strip();extension=e[8:11].decode('ascii').strip()
            if stem in ('.','..'):continue
            full=stem+('.'+extension if extension else '')
            cluster=struct.unpack_from('<H',e,26)[0]
            size=struct.unpack_from('<I',e,28)[0]
            if e[11]&0x10:walk(cluster,prefix+full+'/')
            else:
                assert prefix+full not in files
                files[prefix+full]=chain(cluster,size)
    walk(0)
    return files


def main():
    basic=verify_package('2BASIC')
    bres=verify_package('2BRES')
    # The editor uses a fixed 2BR3 runtime footprint; the serializer is host verified.
    for p in (ROOT/'samples/2B99.RES',ROOT/'resources/cards/CARDS.RES',ROOT/'resources/demo/RESDEMO.RES',ROOT/'resources/2bres-demo/MIXED.RES'):
        subprocess.run([sys.executable,str(ROOT/'tools/2br3.py'),'verify',str(p)],check=True)
    files=extract((DEST/'2BASIC-APPS360.IMG').read_bytes())
    assert files['2BASIC.O88']==basic and files['2BRES.O88']==bres
    expected={'BASICS.BAS','DRAWING.BAS','FORMS.BAS','SOUND.BAS','RESDEMO.BAS','RESDEMO.RES'}
    actual={k.split('/',1)[1] for k in files if k.startswith('EXAMPLES/')}
    assert actual==expected, f'Unexpected examples: {actual ^ expected}'
    assert not any(k.startswith('DEMO/') for k in files),'DEMO directory must not be present'
    for name in expected:
        source=(ROOT/'examples'/name) if name.endswith('.BAS') else (ROOT/'resources/demo/RESDEMO.RES')
        assert files['EXAMPLES/'+name]==source.read_bytes(),name
    assert files['README.TXT']==(ROOT/'samples/README.TXT').read_bytes()
    assert files['HELP.TXT']==(ROOT/'samples/HELP.TXT').read_bytes()
    for test in ('AUTOLANG','AUTOR3','AUTOFORM','FORMISO','EVTSCAN','EVENTUI','AUTOGFX','AUTOPRMT'):
        assert files['TESTS/'+test+'.BAS']==(ROOT/'samples'/(test+'.BAS')).read_bytes()
    assert files['GAMES/2B99/2B99.RES']==(ROOT/'samples/2B99.RES').read_bytes()
    assert files['GAMES/BLACKJAK/CARDS.RES']==(ROOT/'resources/cards/CARDS.RES').read_bytes()
    # Headers, offsets and SDK calls are checked by NASM + os88pkg.py in the build script.
    print(f'FAT12: {len(files)} files read back, executables and UAT files verified.')
    print('HOST CHECKS PASS; emulator UAT is still required.')
    return 0
if __name__=='__main__':raise SystemExit(main())
