"""
J.A.R.V.I.S. V13 — Background Session Telemetry
=================================================
Çalıştır: python session_telemetry.py
Manuel testler sırasında arka planda çalışır.
Her 30 saniyede bir snapshot alır.
Ctrl+C ile durdur → session_report.json üretir.
"""

import asyncio
import time
import json
import os
import sys
import signal
import threading
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("⚠️  psutil yok — RAM/CPU izleme devre dışı. pip install psutil")

SNAPSHOTS = []
START_TIME = time.time()
RUNNING = True


def take_snapshot(label: str = "auto"):
    snap = {
        "time_s": round(time.time() - START_TIME, 1),
        "label": label,
        "timestamp": datetime.now().isoformat(),
    }

    if HAS_PSUTIL:
        proc = psutil.Process(os.getpid())
        snap["ram_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
        snap["cpu_pct"] = round(proc.cpu_percent(interval=0.1), 1)
        snap["threads"] = proc.num_threads()
        snap["system_ram_pct"] = round(psutil.virtual_memory().percent, 1)

    try:
        from core.event_bus import EventBus
        snap["eventbus_ok"] = True
    except Exception:
        snap["eventbus_ok"] = False

    SNAPSHOTS.append(snap)
    return snap


async def background_monitor(interval_s: int = 30):
    print(f"📊 Telemetry başladı — her {interval_s}s snapshot")
    print("   Ctrl+C ile durdur ve rapor al\n")

    cycle = 0
    while RUNNING:
        snap = take_snapshot(f"cycle_{cycle}")
        ram_str = f"RAM={snap.get('ram_mb', '?')}MB" if HAS_PSUTIL else ""
        cpu_str = f"CPU={snap.get('cpu_pct', '?')}%" if HAS_PSUTIL else ""
        print(f"[{snap['timestamp'][11:19]}] t+{snap['time_s']}s | {ram_str} {cpu_str}")
        cycle += 1
        await asyncio.sleep(interval_s)


def save_report():
    if not SNAPSHOTS:
        return

    total_time = time.time() - START_TIME

    report = {
        "session_duration_s": round(total_time, 1),
        "session_duration_min": round(total_time / 60, 1),
        "snapshot_count": len(SNAPSHOTS),
        "snapshots": SNAPSHOTS,
    }

    if HAS_PSUTIL and len(SNAPSHOTS) > 1:
        ram_vals = [s["ram_mb"] for s in SNAPSHOTS if "ram_mb" in s]
        cpu_vals = [s["cpu_pct"] for s in SNAPSHOTS if "cpu_pct" in s]
        if ram_vals:
            report["ram_analysis"] = {
                "start_mb": ram_vals[0],
                "end_mb": ram_vals[-1],
                "peak_mb": max(ram_vals),
                "growth_mb": round(ram_vals[-1] - ram_vals[0], 1),
                "growth_pct": round((ram_vals[-1] - ram_vals[0]) / max(ram_vals[0], 1) * 100, 1),
            }
        if cpu_vals:
            report["cpu_analysis"] = {
                "avg_pct": round(sum(cpu_vals) / len(cpu_vals), 1),
                "peak_pct": max(cpu_vals),
                "high_cpu_snapshots": sum(1 for c in cpu_vals if c > 50),
            }

    os.makedirs("validation_output", exist_ok=True)
    path = "validation_output/session_telemetry.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n📁 Telemetry kaydedildi: {path}")
    print(f"   Süre: {report['session_duration_min']} dakika")

    if "ram_analysis" in report:
        ra = report["ram_analysis"]
        growth_ok = ra["growth_mb"] < 200
        print(f"   RAM başlangıç: {ra['start_mb']} MB → bitiş: {ra['end_mb']} MB")
        print(f"   Büyüme: {ra['growth_mb']} MB ({'✅ normal' if growth_ok else '⚠️ yüksek'})")

    if "cpu_analysis" in report:
        ca = report["cpu_analysis"]
        print(f"   CPU ort: {ca['avg_pct']}% | pik: {ca['peak_pct']}%")

    return report


def handle_interrupt(sig, frame):
    global RUNNING
    RUNNING = False
    print("\n\n⏹️  Telemetry durduruluyor...")
    save_report()
    sys.exit(0)


async def main():
    signal.signal(signal.SIGINT, handle_interrupt)

    # Start monitoring
    interval = 30
    if len(sys.argv) > 1:
        try:
            interval = int(sys.argv[1])
        except ValueError:
            pass

    take_snapshot("start")
    await background_monitor(interval_s=interval)


if __name__ == "__main__":
    asyncio.run(main())