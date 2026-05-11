"""
tune_temperature.py
===================
Sweeps through specialist temperature values, runs the validation
suite N times at each setting, and reports accuracy + SQL consistency.

What it does at each temperature setting:
  1. Writes TEMP_* env vars to backend/.env
  2. Starts a fresh uvicorn on port 8001 (leaves your port 8000 untouched)
  3. Runs the full test suite N times
  4. Measures mean accuracy and SQL consistency across runs
  5. Kills uvicorn, moves to next setting
  6. Prints a comparison table and recommends the best setting

Metrics:
  Accuracy     — % of tests that pass (SQL keywords + result criteria)
  Consistency  — % of tests where the generated SQL is identical across
                 all N runs at the same temperature (higher = more reliable)

Usage:
    python tune_temperature.py
    python tune_temperature.py --runs 3 --port 8001 --output sweep.json

Note: seeds the database once before the sweep starts (requires DATABASE_URL
in backend/.env). Router and approver are kept at 0.0 throughout — only the
specialist nodes (cardholder, merchant, dispute, loyalty) are varied.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


# ── Temperature combinations to sweep ────────────────────────
# router and approver stay deterministic; only specialist is varied.
SWEEP = [
    {"label": "baseline", "specialist": 0.0},
    {"label": "low",      "specialist": 0.1},
    {"label": "medium",   "specialist": 0.3},
    {"label": "high",     "specialist": 0.5},
]

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend" / "files"
ENV_FILE    = BACKEND_DIR / ".env"
VALIDATION_DIR = Path(__file__).resolve().parent


# ── Helpers ───────────────────────────────────────────────────

def write_temperatures(specialist: float) -> None:
    """Patch TEMP_* lines in backend/.env, preserving all other vars."""
    existing = []
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if not line.startswith("TEMP_"):
                existing.append(line)

    existing.extend([
        f"TEMP_ROUTER={0.0}",
        f"TEMP_CARDHOLDER={specialist}",
        f"TEMP_MERCHANT={specialist}",
        f"TEMP_DISPUTE={specialist}",
        f"TEMP_LOYALTY={specialist}",
        f"TEMP_APPROVER={0.0}",
    ])
    ENV_FILE.write_text("\n".join(existing) + "\n")


def start_uvicorn(port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--port", str(port), "--host", "127.0.0.1"],
        cwd=BACKEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_ready(port: int, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run_one(port: int, label: str, run_num: int) -> dict:
    ws_url  = f"ws://127.0.0.1:{port}"
    out_path = VALIDATION_DIR / f"_sweep_{label}_run{run_num}.json"
    subprocess.run(
        [sys.executable, "run_tests.py",
         "--url", ws_url,
         "--temperature", label,
         "--output", str(out_path)],
        cwd=VALIDATION_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if out_path.exists():
        with open(out_path) as f:
            data = json.load(f)
        out_path.unlink()   # clean up temp file
        return data
    return {}


def measure_consistency(run_results: list) -> float:
    """% of tests where generated SQL was identical across all N runs."""
    if len(run_results) < 2:
        return 100.0
    sql_map = {}
    for run in run_results:
        for r in run.get("results", []):
            sql_map.setdefault(r["id"], []).append(r.get("sql") or "")
    if not sql_map:
        return 0.0
    consistent = sum(1 for sqls in sql_map.values() if len(set(sqls)) == 1)
    return round(100 * consistent / len(sql_map), 1)


def seed_once():
    """Run topup.py + demo_seed.py once before the sweep."""
    seed_dir = BACKEND_DIR.parent.parent / "db" / "supabase"
    for script in ["topup.py", "demo_seed.py"]:
        path = seed_dir / script
        if path.exists():
            print(f"  Seeding: {script}...", end=" ", flush=True)
            r = subprocess.run([sys.executable, str(path)],
                               capture_output=True, text=True)
            last = [l for l in r.stdout.strip().splitlines() if l]
            print(last[-1] if last else "done")


# ── Main sweep ────────────────────────────────────────────────

def main(runs: int, port: int, output_file: str, skip_seed: bool):
    print(f"\nTemperature sweep — {len(SWEEP)} settings × {runs} runs each")
    print(f"Backend dir:  {BACKEND_DIR}")
    print(f"Test port:    {port}  (your port 8000 is untouched)")
    print()

    if not skip_seed:
        print("Seeding database (once before sweep)...")
        seed_once()
        print("Seed done. Waiting 2s...\n")
        time.sleep(2)

    all_results = []

    for config in SWEEP:
        label    = config["label"]
        spec     = config["specialist"]
        print(f"[{label}]  router=0.0  specialist={spec}  approver=0.0")

        write_temperatures(spec)

        print("  Starting uvicorn... ", end="", flush=True)
        proc = start_uvicorn(port)
        if not wait_for_ready(port, timeout=30):
            print("TIMEOUT — skipping")
            proc.kill()
            continue
        print("ready")

        run_results  = []
        accuracies   = []

        for run_num in range(1, runs + 1):
            print(f"  Run {run_num}/{runs}... ", end="", flush=True)
            result = run_one(port, label, run_num)
            if result:
                acc = result.get("summary", {}).get("accuracy_pct", 0.0)
                accuracies.append(acc)
                run_results.append(result)
                print(f"{acc:.1f}%")
            else:
                print("ERROR (no output)")

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

        if not accuracies:
            continue

        mean_acc    = round(sum(accuracies) / len(accuracies), 1)
        consistency = measure_consistency(run_results)
        min_acc     = min(accuracies)
        max_acc     = max(accuracies)

        print(f"  → Mean accuracy: {mean_acc}%  "
              f"(range {min_acc}–{max_acc}%)  |  "
              f"SQL consistency: {consistency}%\n")

        all_results.append({
            "label":              label,
            "specialist_temp":    spec,
            "accuracies":         accuracies,
            "mean_accuracy_pct":  mean_acc,
            "min_accuracy_pct":   min_acc,
            "max_accuracy_pct":   max_acc,
            "consistency_pct":    consistency,
        })

    # ── Comparison table ──────────────────────────────────────
    print("=" * 65)
    print("SWEEP RESULTS")
    print("=" * 65)
    print(f"{'Setting':<12} {'Spec temp':>10} {'Mean acc':>10} "
          f"{'Range':>14} {'Consistency':>13}")
    print("-" * 65)
    for r in all_results:
        rng = f"{r['min_accuracy_pct']}–{r['max_accuracy_pct']}%"
        print(f"{r['label']:<12} {r['specialist_temp']:>10.1f} "
              f"{r['mean_accuracy_pct']:>9.1f}% {rng:>14} "
              f"{r['consistency_pct']:>12.1f}%")
    print("=" * 65)

    if all_results:
        # Best = highest accuracy; tie-break on consistency
        best = max(all_results,
                   key=lambda r: (r["mean_accuracy_pct"], r["consistency_pct"]))
        print(f"\nRecommended setting: [{best['label']}]  "
              f"specialist_temp={best['specialist_temp']}")
        print("Set these in backend/files/.env and restart uvicorn:")
        spec = best["specialist_temp"]
        for node in ["CARDHOLDER", "MERCHANT", "DISPUTE", "LOYALTY"]:
            print(f"  TEMP_{node}={spec}")
        print(f"  TEMP_ROUTER=0.0")
        print(f"  TEMP_APPROVER=0.0")

    # Save full report
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nFull report saved to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sweep temperature values and find the best setting"
    )
    parser.add_argument("--runs",       type=int, default=3,
                        help="Runs per temperature setting (default: 3)")
    parser.add_argument("--port",       type=int, default=8001,
                        help="Port for the test uvicorn instance (default: 8001)")
    parser.add_argument("--output",     default="sweep_results.json",
                        help="Output file for the full report")
    parser.add_argument("--skip-seed",  action="store_true",
                        help="Skip DB seeding (use if already seeded)")
    args = parser.parse_args()

    main(args.runs, args.port, args.output, args.skip_seed)
