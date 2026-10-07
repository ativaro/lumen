"""Read-only Linux measurements. No argv, environment or persistent history."""
from collections import deque
import json
import os
from pathlib import Path
import time


def read(path):
    try: return path.read_text(errors='replace')
    except OSError: return ''


def cpu_usage(before, after):
    if not before or not after or len(after) < 5 or len(before) < 5: return None
    delta = sum(after[:8]) - sum(before[:8])  # guest time is already in user/nice
    idle = after[3] + after[4] - before[3] - before[4]
    if delta <= 0 or idle < 0 or idle > delta: return None
    return round(100 * (delta - idle) / delta, 1)


def process_stat(text):
    """comm can contain spaces and closing parentheses. Key by PID + start ticks."""
    end = text.rfind(')'); start = text.find('(')
    fields = text[end + 2:].split()
    if start < 0 or end < start or len(fields) < 22: raise ValueError('Incomplete stat')
    return dict(pid=int(text[:start]), name=text[start + 1:end][:80],
                ticks=int(fields[11]) + int(fields[12]), start=int(fields[19]),
                rss=max(0, int(fields[21])) * os.sysconf('SC_PAGE_SIZE'))


class Sampler:
    def __init__(self, proc=Path('/proc'), sysfs=Path('/sys'), uid=None):
        self.proc, self.sysfs = proc, sysfs
        self.uid = os.getuid() if uid is None else uid
        self.previous = None
        self.hz = os.sysconf('SC_CLK_TCK')
        self.cpu_name = next((line.split(':', 1)[1].strip() for line in read(proc / 'cpuinfo').splitlines()
                              if line.startswith('model name')), 'CPU')

    def counters(self):
        cpu, memory, network, processes = None, {}, {}, {}
        try: cpu = [int(v) for v in read(self.proc / 'stat').splitlines()[0].split()[1:]]
        except (ValueError, IndexError): pass
        for line in read(self.proc / 'meminfo').splitlines():
            key, _, value = line.partition(':')
            try: memory[key] = int(value.split()[0]) * 1024
            except (ValueError, IndexError): pass
        for line in read(self.proc / 'net/dev').splitlines()[2:]:
            name, _, values = line.partition(':'); name = name.strip()
            if not name or name == 'lo': continue
            try:
                values = values.split(); network[name] = (int(values[0]), int(values[8]))
            except (ValueError, IndexError): pass
        try: entries = list(self.proc.iterdir())
        except OSError: entries = []
        for path in entries[:32768]:
            if not path.name.isdecimal(): continue
            try:
                if path.stat().st_uid != self.uid: continue
                item = process_stat(read(path / 'stat')); processes[(item['pid'], item['start'])] = item
            except (OSError, ValueError): continue
        return dict(cpu=cpu, memory=memory, network=network, processes=processes, clock=time.monotonic())

    def sample(self):
        raw = self.counters(); old = self.previous; self.previous = raw
        elapsed = raw['clock'] - old['clock'] if old else 0
        cpu = cpu_usage(old['cpu'], raw['cpu']) if old else None
        memory = raw['memory']; total = memory.get('MemTotal'); available = memory.get('MemAvailable')
        used = max(0, total - available) if total and available is not None else None
        processes = []
        for key, item in raw['processes'].items():
            prior = old['processes'].get(key) if old else None
            ticks = item['ticks'] - prior['ticks'] if prior else -1
            percent = round(100 * ticks / self.hz / elapsed, 1) if elapsed > 0 and ticks >= 0 else None
            processes.append(dict(pid=item['pid'], name=item['name'], cpu=percent, memory=item['rss']))
        processes.sort(key=lambda p: (p['cpu'] or 0, p['memory']), reverse=True)
        rates = []
        if old and elapsed > 0:
            for name, counters in raw['network'].items():
                prior = old['network'].get(name)
                if prior and all(a >= b for a, b in zip(counters, prior)):
                    rates.append([(a - b) / elapsed for a, b in zip(counters, prior)])
        network = dict(receive=sum(r[0] for r in rates), send=sum(r[1] for r in rates)) if rates else None
        try:
            stat = os.statvfs('/')
            disk = dict(total=stat.f_blocks * stat.f_frsize,
                        used=(stat.f_blocks - stat.f_bfree) * stat.f_frsize,
                        available=stat.f_bavail * stat.f_frsize, path='/')
        except OSError: disk = None
        gpus = []
        for path in sorted(self.sysfs.glob('class/drm/card[0-9]*')):
            if '-' in path.name: continue
            value = read(path / 'device/gpu_busy_percent').strip()
            try:
                percent = float(value)
                if 0 <= percent <= 100: gpus.append(dict(name=('AMD Radeon · ' if read(path / 'device/vendor').strip() == '0x1002' else '') + path.name, usage=percent))
            except ValueError: pass
        return dict(measured=time.time(), cpu=cpu, cpuName=self.cpu_name,
                    cores=os.cpu_count() or 1, memory=dict(total=total, used=used,
                    percent=round(100 * used / total, 1) if used is not None else None),
                    disk=disk, network=network, processes=list({p['pid']: p for p in processes[:80] + sorted(processes, key=lambda p: p['memory'], reverse=True)[:80]}.values()), gpus=gpus)


class History:
    """Bounded, timestamped session history and measured crossings, never diagnoses."""
    def __init__(self):
        self.points = deque(maxlen=1801); self.events = deque(maxlen=60)

    def append(self, sample):
        gpu = sample.get('gpus', [])
        point = dict(time=sample['measured'], cpu=sample.get('cpu'),
                     gpu=gpu[0]['usage'] if gpu else None,
                     memory=sample.get('memory', {}).get('percent'),
                     network=sum(sample['network'].values()) if sample.get('network') else None)
        previous = self.points[-1] if self.points else None
        if previous:
            for key, limit in [('cpu', 80), ('gpu', 90), ('memory', 90)]:
                value, before = point[key], previous[key]
                if value is not None and before is not None and value >= limit > before:
                    self.events.append(dict(time=point['time'], metric=key, value=value))
        self.points.append(point)
        cutoff = point['time'] - 3600
        while self.points and self.points[0]['time'] < cutoff: self.points.popleft()
        while self.events and self.events[0]['time'] < cutoff: self.events.popleft()

    def series(self, seconds):
        if not self.points: return []
        cutoff = self.points[-1]['time'] - seconds
        return [p for p in self.points if p['time'] >= cutoff]


def add_gpu_sensors(sample):
    from lumen_i18n import tr
    hardware = sample.get('hardware', {})
    if time.time() - hardware.get('measured', 0) > 25: return
    gpus = [dict(name=row['device'], usage=row['value']) for row in hardware.get('sensors', [])
            if row['name'] == tr('Auslastung') and row['unit'] == '%']
    sample['gpus'] = gpus + sample.get('gpus', [])


def snapshot():
    from lumen_hardware import snapshot as hardware_snapshot
    sampler = Sampler(); sampler.sample(); time.sleep(.25)
    result = sampler.sample(); result['hardware'] = hardware_snapshot(include_activity=False); add_gpu_sensors(result)
    result['processes'] = result['processes'][:12]
    return result


def worker():
    # Optional tools run off the sampling loop too, so a sleeping sensor cannot
    # stall CPU/process measurements. The GUI owns and terminates this process.
    from concurrent.futures import ThreadPoolExecutor
    from lumen_hardware import snapshot
    sampler = Sampler(); sensors = {}; next_sensor = 0; pending = None
    executor = ThreadPoolExecutor(max_workers=1)
    while True:
        start = time.monotonic()
        if pending and pending.done():
            try: sensors = pending.result()
            except Exception: sensors = {'sensors': [], 'unavailable': ['Sensor read failed']}
            pending = None
        if pending is None and start >= next_sensor:
            pending = executor.submit(snapshot, include_activity=False); next_sensor = start + 10
        sample = sampler.sample(); sample['hardware'] = sensors
        add_gpu_sensors(sample)
        print(json.dumps(sample, allow_nan=False), flush=True)
        time.sleep(max(.1, 2 - (time.monotonic() - start)))


if __name__ == '__main__': worker()
