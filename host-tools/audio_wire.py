import re

def decode_transfer(raw):
    # ESP-IDF log output bypasses the CLI UART TX ring. Once the worker
    # finishes queuing export bytes, DONE/READY logs can interleave into the
    # final queued headers/hex payload. These unambiguous bracketed log records
    # are not hexadecimal audio data. Remove them, then still require exact
    # offsets, length and the board's whole-take checksum; never fill gaps.
    raw,removed=re.subn(rb'\[\d+\]<[A-Z]>[^\r\n]*\r+\n',b'',raw)
    begins=list(re.finditer(rb'AUDIO_BEGIN (\d+) (\d+) (\d+) (\d+) ([0-9a-fA-F]{8})',raw))
    ends=list(re.finditer(rb'AUDIO_END (\d+) ([0-9a-fA-F]{8})',raw))
    assert len(begins)==1 and len(ends)==1,'Missing/duplicate transfer framing'
    b,e=begins[0],ends[0]
    size,rate,ch,bits=[int(b.group(i)) for i in range(1,5)];expected=int(b.group(5),16)
    assert 0<size<=320000 and (rate,ch,bits)==(16000,1,16) and size%2==0
    assert int(e.group(1))==size and int(e.group(2),16)==expected
    assert b.end()<e.start()
    data=bytearray();chunks=0
    for m in re.finditer(rb'AUDIO_DATA (\d+) ([0-9a-fA-F]+)',raw[b.end():e.start()]):
        offset=int(m.group(1));part=bytes.fromhex(m.group(2).decode('ascii'))
        assert offset==len(data),'Gap/duplicate/out-of-order audio chunk'
        assert 0<len(part)<=96 and len(data)+len(part)<=size
        data.extend(part);chunks+=1
    assert len(data)==size,'Incomplete audio payload'
    fnv=2166136261
    for x in data:fnv=((fnv^x)*16777619)&0xffffffff
    assert fnv==expected,'End-to-end audio checksum mismatch'
    return bytes(data),{'bytes':size,'rate':rate,'channels':ch,'bits':bits,'fnv32':f'{fnv:08x}','chunks':chunks,'interleaved_debug_records_removed':removed}
