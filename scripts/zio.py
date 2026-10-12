# Interactive MS-50G MIDI helpers used to check MIDISTOMP on a pedal (python3 -i scripts/zio.py).
# Sends PC/CC/clock, reads the program (SysEx 33) and patch (29) back. Needs: pip install mido python-rtmidi
# Set PC_START to the pedal's PROG CH START NO. and BACKUP to a file of "index F0..F7 hex" lines.
import os, time, mido
Z = [0x52, 0x00, 0x58]
inp = mido.open_input("ZOOM MS Series"); out = mido.open_output("ZOOM MS Series")
def drain(): time.sleep(0.05); list(inp.iter_pending())
def xfer(body, t=0.6):
    drain(); out.send(mido.Message("sysex", data=Z + body)); time.sleep(t)
    return [list(m.data) for m in inp.iter_pending() if m.type == "sysex"]
def send(msg, t=0.4): out.send(msg); time.sleep(t)
def prog():
    drain(); out.send(mido.Message("sysex", data=Z + [0x33])); time.sleep(0.3)
    for m in inp.iter_pending():
        if m.type == "program_change": return m.program
    return -1
def patch():
    for r in xfer([0x29]):
        if r[:4] == Z + [0x28]: return r
def name(p): return bytes(c for c in p[131:144] if 32 <= c < 127).decode()
def pc(n, ch=0): send(mido.Message("program_change", program=n, channel=ch))
def cc(n, v, ch=0, t=0.3): send(mido.Message("control_change", control=n, value=v, channel=ch), t)
def editor(on=True): xfer([0x50 if on else 0x51], 0.3)
def unpack(p):  # p = mido data incl. 52 00 58 xx; 7-bit groups from index 4, MSB bit (6-j) -> data j
    d = p[4:]; o = []
    for i in range(0, len(d), 8):
        g = d[i:i+8]
        for j, b in enumerate(g[1:]): o.append(b | (0x80 if g[0] & (1 << (6 - j)) else 0))
    return o
def tempo(p):
    hi = p[124] & 4; d129 = p[129] | (0x80 if hi else 0)
    return (p[130] << 3) | (d129 >> 5)
def clock(bpm, secs):
    dt = 60 / bpm / 24; t = time.perf_counter()
    for _ in range(int(secs / dt)):
        t += dt
        while time.perf_counter() < t: pass
        out.send(mido.Message("clock"))
    time.sleep(0.3)
PC_START = 0
BACKUP = os.path.join(os.path.dirname(__file__), "..", "firmware", "backups", "ms50g-patches-2026-10-10.txt")
BK = {int(r.split()[0]): [int(x,16) for x in r.split()[1:]][1:-1] for r in open(BACKUP)} if os.path.exists(BACKUP) else {}
def verify_all(fix=False):
    bad = []
    for i in range(50):
        pc(i + PC_START); p = patch()
        if p != BK[i]:
            bad.append((i, name(BK[i])))
            if fix:
                out.send(mido.Message("sysex", data=BK[i])); time.sleep(0.5)
                xfer([0x32, 0x01, 0x00, 0x00, i, 0, 0, 0, 0, 0], 1.0)
    return bad
