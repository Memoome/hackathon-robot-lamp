"""Transport and image routines reused from the verified camera-only viewer."""
import os
import struct
import zlib
import serial
from serial.tools import list_ports

def select_port():
    """Select one matching board without opening or resetting any device."""
    wanted_serial = os.environ.get('LJWB03_SERIAL', '').strip()
    ports = [p for p in list_ports.comports() if
             (p.vid, p.pid) == (0x1A86, 0x55D3) and
             (not wanted_serial or p.serial_number == wanted_serial)]
    if len(ports) != 1:
        raise RuntimeError('需要唯一一块 CH343 开发板 (VID 1A86 / PID 55D3)；多板时请设置 LJWB03_SERIAL')
    return ports[0].device

def connect():
    port = select_port()
    s = serial.Serial()
    s.port, s.baudrate, s.timeout, s.write_timeout = port, 921600, 0.2, 2
    s.dtr = s.rts = False
    s.open()
    return s

def fnv(data):
    h = 2166136261
    for b in data:
        h = ((h ^ b) * 16777619) & 0xffffffff
    return h

def decode_uyvy(data, w, h):
    if w % 2 or len(data) != w*h*2:
        raise ValueError('UYVY length mismatch')
    rgb = bytearray()
    for i in range(0, len(data), 4):
        u, y0, v, y1 = data[i:i+4]
        d, e = u-128, v-128
        for y in (y0, y1):
            c = max(0, y-16)
            rgb.extend(max(0, min(255, a >> 8)) for a in
                       (298*c+409*e+128, 298*c-100*d-208*e+128, 298*c+516*d+128))
    return bytes(rgb)

def png(rgb, w, h):
    def chunk(t, b):
        return struct.pack('>I', len(b))+t+b+struct.pack('>I', zlib.crc32(t+b)&0xffffffff)
    rows = b''.join(b'\0'+rgb[y*w*3:(y+1)*w*3] for y in range(h))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', w,h,8,2,0,0,0))
            +chunk(b'IDAT', zlib.compress(rows))+chunk(b'IEND', b''))

def rotate_rgb(rgb,w,h):
    out=bytearray(len(rgb))
    for y in range(h):
        for x in range(w):
            start=(y*w+x)*3
            dest=(x*h+(h-1-y))*3
            out[dest:dest+3]=rgb[start:start+3]
    return bytes(out),h,w
