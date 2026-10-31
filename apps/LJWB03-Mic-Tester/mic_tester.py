"""A small, local microphone tester for the specific LJWB03 board.
Only the Record button starts capture. No flash/reset or PC microphone access.
"""
from __future__ import annotations
import array
import datetime
import hashlib
import json
import math
import os
import pathlib
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import wave
import winsound

KIT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT / 'host-tools'))
import serial
from serial.tools import list_ports
from audio_wire import decode_transfer

HERE = pathlib.Path(__file__).resolve().parent
SERIAL_NUMBER = os.environ.get('LJWB03_SERIAL','')
SECONDS = 8
RATE = 16000
EXPECTED_BYTES = SECONDS * RATE * 2
BG, PANEL, INK, MUTED, ACCENT = '#f4f6f8', '#ffffff', '#182b3a', '#566575', '#087f78'


def find_board():
    ports = [p for p in list_ports.comports() if (p.vid, p.pid) == (0x1a86, 0x55d3) and (not SERIAL_NUMBER or p.serial_number == SERIAL_NUMBER)]
    if len(ports) != 1:
        raise RuntimeError('Board not found. Connect its USB data cable, then click Check connection.')
    return ports[0].device


def open_board(port):
    s = serial.Serial(port=None, baudrate=115200, timeout=0.15, rtscts=False, dsrdtr=False, xonxoff=False)
    s.dtr = False
    s.rts = False
    s.port = port
    s.open()
    s.set_buffer_size(rx_size=65536, tx_size=8192)
    return s


def read_until(s, pattern, seconds, progress=None):
    raw = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        chunk = s.read(8192)
        if chunk:
            raw.extend(chunk)
            if progress:
                progress(bytes(raw))
            if re.search(pattern, raw):
                return bytes(raw)
            if b'ERROR busy/not-ready' in raw or b'ERROR invalid command' in raw:
                raise RuntimeError('The board is busy or rejected the request. Wait a few seconds and try again.')
    raise TimeoutError('The board did not finish in time. Close other serial tools, check the cable, and try again.')


def check_status(s):
    s.reset_input_buffer()
    s.write(b'audio_test status\r\n')
    s.flush()
    raw = read_until(s, rb'STATUS[^\r\n]*autoplay=OFF', 6)
    m = re.search(rb'STATUS mode=(\S+) revision=(\d+) state=(\S+) busy=(\d+) chip_ready=(\d+)', raw)
    if not m or m.groups() != (b'OFFLINE_PCM', b'3', b'READY', b'0', b'1'):
        raise RuntimeError('The board is not ready in audio diagnostic mode. Wait for startup, then check the connection again.')
    return raw


def samples_from_pcm(pcm):
    values = array.array('h')
    values.frombytes(pcm)
    if sys.byteorder != 'little':
        values.byteswap()
    return values


def analyse(pcm):
    values = samples_from_pcm(pcm)
    if not values:
        raise ValueError('The recording contains no audio samples.')
    peak = max(abs(v) for v in values)
    rms = math.sqrt(sum(v*v for v in values) / len(values))
    return {'samples': len(values), 'duration_seconds': len(values) / RATE,
            'peak': peak, 'peak_percent': 100 * peak / 32768,
            'rms': rms, 'rms_dbfs': 20 * math.log10(rms / 32768) if rms else None,
            'clipped_samples': sum(abs(v) >= 32767 for v in values),
            'zero_samples': sum(v == 0 for v in values)}


def write_wav(path, pcm):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    with wave.open(str(path), 'rb') as w:
        if w.readframes(w.getnframes()) != pcm:
            raise ValueError('Saved WAV did not match the verified microphone data.')


def boost_pcm(pcm):
    values = samples_from_pcm(pcm)
    peak = max((abs(v) for v in values), default=0)
    gain = min(100.0, max(1.0, 0.8 * 32767 / peak)) if peak else 1.0
    boosted = array.array('h', (max(-32768, min(32767, round(v * gain))) for v in values))
    if sys.byteorder != 'little':
        boosted.byteswap()
    return boosted.tobytes(), gain


def capture(emit, seconds=SECONDS):
    """Explicit recording operation. Returns only checksum-verified audio."""
    expected = seconds * RATE * 2
    port = find_board()
    dest = HERE / 'captures' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    dest.mkdir(parents=True)
    s = None
    record_log = b''
    try:
        emit('phase', ('Checking board...', 0))
        s = open_board(port)
        record_log = check_status(s)
        s.write(f'audio_test record {seconds}\r\n'.encode('ascii'))
        s.flush()
        start_at = None
        started = time.monotonic()
        data = bytearray()
        deadline = started + seconds + 14
        while time.monotonic() < deadline:
            data.extend(s.read(8192))
            if b'ERROR busy/not-ready' in data or b'ERROR invalid command' in data:
                raise RuntimeError('The board could not start recording. Wait a few seconds, then retry.')
            if start_at is None and re.search(rb'RECORDING seconds=\d+', data):
                start_at = time.monotonic()
            if start_at is not None:
                elapsed = time.monotonic() - start_at
                remaining = max(0, math.ceil(seconds - elapsed))
                emit('phase', (f'Recording board mic... {remaining}s left. Speak or clap now.', min(100, elapsed / seconds * 100)))
            done = re.search(rb'DONE job=' + str(seconds).encode() + rb' result=(\S+) rc=(-?\d+) stop_rc=(-?\d+)', data)
            if done:
                if done.groups() != (b'HOST_OK', b'0', b'0'):
                    raise RuntimeError('The board reported an audio capture error. See the saved serial log.')
                break
        else:
            raise TimeoutError('Recording timed out. The board normally stops automatically; wait and check its connection.')
        record_log += bytes(data)
        (dest / 'serial.log').write_bytes(record_log)
        complete = re.search(rb'SIGNAL[^\r\n]*complete=(\d+)', data)
        size = re.search(rb'CAPTURE bytes=(\d+)', data)
        if not complete or complete.group(1) != b'1' or not size or int(size.group(1)) != expected:
            raise RuntimeError('The board captured only part of the requested recording. Repeat the test; this take is not accepted.')
        drops = re.search(rb'queue_drops=(\d+)', data)
        queue_drops = int(drops.group(1)) if drops else None
        emit('phase', ('Downloading recording... 0%. This can take about a minute.', 0))
        s.write(b'audio_test export\r\n')
        s.flush()
        def progress(raw):
            lines = list(re.finditer(rb'AUDIO_DATA (\d+) ([0-9a-fA-F]+)\r*\n', raw[-16384:]))
            if lines:
                last = lines[-1]
                received = min(expected, int(last.group(1)) + len(last.group(2)) // 2)
                pct = received / expected * 100
                emit('phase', (f'Downloading recording... {pct:.0f}%. Keep the USB cable connected.', pct))
        try:
            transfer = read_until(s, rb'AUDIO_END \d+ [0-9a-fA-F]{8}', 140, progress)
        except Exception:
            raise
        (dest / 'transfer.log').write_bytes(transfer)
        pcm, info = decode_transfer(transfer)
        if len(pcm) != expected:
            raise ValueError('The exported recording has an unexpected length.')
        stats = analyse(pcm)
        (dest / 'microphone.pcm').write_bytes(pcm)
        write_wav(dest / 'microphone.wav', pcm)
        info.update(stats)
        info.update({'port': port, 'usb_serial': SERIAL_NUMBER, 'sha256': hashlib.sha256(pcm).hexdigest(),
                     'queue_drops': queue_drops, 'source': 'LJWB03 board microphone; original unmodified PCM',
                     'transfer_verified': True})
        (dest / 'recording.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
        return {'pcm': pcm, 'stats': stats, 'folder': dest, 'port': port, 'queue_drops': queue_drops}
    except Exception as exc:
        (dest / 'error.txt').write_text(str(exc), encoding='utf-8')
        if record_log:
            (dest / 'serial.log').write_bytes(record_log)
        raise
    finally:
        if s is not None:
            s.close()


class MicTester:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.result = None
        self.play_started = None
        self.root.title('LJWB03 Mic Test')
        self.root.geometry('720x740')
        self.root.minsize(660, 700)
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=INK, font=('Segoe UI', 11))
        style.configure('TButton', font=('Segoe UI', 11), padding=(13, 9))
        style.configure('Record.TButton', foreground='white', background=ACCENT, font=('Segoe UI', 13, 'bold'), padding=(20, 13))
        style.map('Record.TButton', background=[('active', '#096d68'), ('disabled', '#a1b4b4')])
        style.configure('TCheckbutton', background=BG, foreground=INK, font=('Segoe UI', 10))
        style.configure('TProgressbar', background=ACCENT, troughcolor='#e1e7ec', thickness=8)
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text="Test your board's microphone", font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Record → see the waveform → listen on your laptop', foreground=MUTED).pack(anchor='w', pady=(5, 10))
        connection = ttk.Frame(outer)
        connection.pack(fill='x')
        self.connection = tk.StringVar(value='Checking board...')
        ttk.Label(connection, textvariable=self.connection).pack(side='left')
        self.check_button = ttk.Button(connection, text='Check connection', command=self.check)
        self.check_button.pack(side='right')
        self.record_button = ttk.Button(outer, text='Record 8 seconds', style='Record.TButton', command=self.record, state='disabled')
        self.record_button.pack(fill='x', pady=(12, 8))
        ttk.Label(outer, text='Stay quiet for 2 seconds, then talk, clap once, or play music.', foreground=MUTED, wraplength=620).pack(anchor='w')
        self.phase = tk.StringVar(value='No recording starts until you press Record.')
        ttk.Label(outer, textvariable=self.phase, wraplength=620).pack(anchor='w', pady=(12, 6))
        self.progress = ttk.Progressbar(outer, maximum=100)
        self.progress.pack(fill='x', pady=(0, 15))
        self.canvas = tk.Canvas(outer, height=110, bg=PANEL, highlightthickness=1, highlightbackground='#d9e1e7')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda event: self.draw_wave())
        self.scale_label = tk.StringVar(value='The waveform appears after recording downloads. This is not a live feed.')
        ttk.Label(outer, textvariable=self.scale_label, foreground=MUTED, font=('Segoe UI', 9), wraplength=620).pack(anchor='w', pady=(6, 8))
        self.measurements = tk.StringVar(value='Original recording level: —')
        ttk.Label(outer, textvariable=self.measurements).pack(anchor='w')
        self.assessment = tk.StringVar(value='Listen to the recording to judge clarity.')
        ttk.Label(outer, textvariable=self.assessment, foreground=MUTED, wraplength=620).pack(anchor='w', pady=(5, 14))
        controls = ttk.Frame(outer)
        controls.pack(fill='x')
        self.play_button = ttk.Button(controls, text='Play on laptop', command=self.toggle_play, state='disabled')
        self.play_button.pack(side='left')
        self.boost = tk.BooleanVar(value=False)
        self.boost_check = ttk.Checkbutton(controls, text='Boost quiet playback', variable=self.boost, command=self.stop_play)
        self.boost_check.pack(side='left', padx=12)
        self.folder_button = ttk.Button(controls, text='Saved files', command=self.open_folder, state='disabled')
        self.folder_button.pack(side='right')
        self.note = tk.StringVar(value='Uses only the board mic. Original audio is saved unchanged. Start laptop volume low.')
        ttk.Label(outer, textvariable=self.note, font=('Segoe UI', 9), foreground=MUTED, wraplength=620).pack(anchor='w', pady=(13, 0))
        root.after(100, self.poll)
        root.after(250, self.check)

    def emit(self, kind, value):
        self.events.put((kind, value))

    def set_busy(self, busy):
        self.busy = busy
        self.record_button.configure(state='disabled' if busy else 'normal')
        self.check_button.configure(state='disabled' if busy else 'normal')
        self.play_button.configure(state='normal' if self.result and not busy else 'disabled')

    def check(self):
        if self.busy:
            return
        self.set_busy(True)
        self.connection.set('Checking board...')
        def worker():
            try:
                port = find_board()
                with open_board(port) as s:
                    check_status(s)
                self.emit('connected', port)
            except Exception as exc:
                self.emit('connection_error', str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def record(self):
        if self.busy:
            return
        self.stop_play()
        self.set_busy(True)
        self.phase.set('Starting the board microphone...')
        self.progress['value'] = 0
        def worker():
            try:
                self.emit('recorded', capture(self.emit))
            except Exception as exc:
                self.emit('error', str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'phase':
                    self.phase.set(value[0])
                    self.progress['value'] = value[1]
                elif kind == 'connected':
                    self.connection.set(f'Board ready · {value}')
                    self.set_busy(False)
                    self.phase.set('Ready. Press Record, then speak when the countdown starts.')
                elif kind == 'connection_error':
                    self.set_busy(False)
                    self.record_button.configure(state='disabled')
                    self.connection.set('Board not ready')
                    self.phase.set(value)
                elif kind == 'error':
                    self.set_busy(False)
                    self.phase.set('Could not complete the new recording. Any previous waveform is unchanged.')
                    self.progress['value'] = 0
                    messagebox.showerror('Recording problem', value + '\n\nClose any other serial monitor using the board and retry.', parent=self.root)
                elif kind == 'recorded':
                    self.result = value
                    self.boost.set(False)
                    self.set_busy(False)
                    self.folder_button.configure(state='normal')
                    self.progress['value'] = 100
                    self.connection.set(f'Board ready · {value["port"]}')
                    self.phase.set('Recording saved and transfer verified. Press Play on laptop.')
                    st = value['stats']
                    db = f'{st["rms_dbfs"]:.1f} dBFS' if st['rms_dbfs'] is not None else 'silence'
                    self.measurements.set(f'Original recording level: peak {st["peak_percent"]:.2f}% of maximum')
                    self.scale_label.set('Waveform enlarged to show detail. The percentage below is the original level.')
                    if value['queue_drops']:
                        self.assessment.set('The board reported dropped audio frames. Repeat this test.')
                    elif st['peak'] == 0:
                        self.assessment.set('All samples are zero: no sound was captured. Check the microphone path.')
                    elif st['clipped_samples']:
                        self.assessment.set('Clipping detected. Move the sound source farther away or lower its volume.')
                    elif st['peak_percent'] < 1:
                        self.assessment.set('Very quiet signal. Try speaking closer; Boost can help you hear this take.')
                    else:
                        self.assessment.set('Sound was captured. Listen for clear speech/music and compare it with the quiet part.')
                    self.draw_wave()
        except queue.Empty:
            pass
        if self.play_started is not None and self.result:
            elapsed = time.monotonic() - self.play_started
            duration = self.result['stats']['duration_seconds']
            if elapsed >= duration:
                self.stop_play()
            else:
                self.canvas.delete('playhead')
                x = 12 + elapsed / duration * max(1, self.canvas.winfo_width() - 24)
                self.canvas.create_line(x, 8, x, self.canvas.winfo_height()-24, fill='#db6b1a', width=2, tags='playhead')
        self.root.after(70, self.poll)

    def draw_wave(self):
        c = self.canvas
        c.delete('all')
        width, height = max(c.winfo_width(), 100), max(c.winfo_height(), 80)
        center = (height - 20) / 2
        c.create_line(12, center, width-12, center, fill='#d9e1e7')
        if not self.result:
            c.create_text(width/2, center, text='Your recording will appear here', fill=MUTED, font=('Segoe UI', 11))
            return
        values = samples_from_pcm(self.result['pcm'])
        peak = max(self.result['stats']['peak'], 1)
        bins = min(max(1, width-24), len(values))
        scale = (height-45)/2 / peak
        for index in range(bins):
            block = values[index*len(values)//bins:(index+1)*len(values)//bins]
            lo, hi = min(block), max(block)
            x = 12 + index
            c.create_line(x, center-hi*scale, x, center-lo*scale, fill=ACCENT)
        for sec in (0, 2, 4, 6, 8):
            x = 12 + sec/SECONDS*(width-24)
            c.create_text(x, height-11, text=f'{sec}s', anchor='w' if sec==0 else 'e' if sec==8 else 'center', fill=MUTED, font=('Segoe UI', 9))

    def toggle_play(self):
        if self.play_started is not None:
            self.stop_play()
            return
        if not self.result or self.busy:
            return
        try:
            path = self.result['folder'] / 'microphone.wav'
            if self.boost.get():
                pcm, gain = boost_pcm(self.result['pcm'])
                path = self.result['folder'] / 'microphone-boosted.wav'
                write_wav(path, pcm)
                self.note.set(f'Playing with {gain:.1f}× boost on the laptop. Original recording is unchanged.')
            else:
                self.note.set('Playing the original, unmodified recording through your laptop.')
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            self.play_started = time.monotonic()
            self.play_button.configure(text='Stop playback')
        except Exception as exc:
            messagebox.showerror('Playback problem', str(exc), parent=self.root)

    def stop_play(self):
        winsound.PlaySound(None, 0)
        self.play_started = None
        self.play_button.configure(text='Play on laptop')
        self.canvas.delete('playhead')

    def open_folder(self):
        if self.result:
            os.startfile(str(self.result['folder']))

    def close(self):
        if self.busy:
            messagebox.showinfo('Please wait', 'Wait for the connection check or recording download to finish before closing.', parent=self.root)
            return
        self.stop_play()
        self.root.destroy()


def main():
    root = tk.Tk()
    MicTester(root)
    root.mainloop()


if __name__ == '__main__':
    main()


