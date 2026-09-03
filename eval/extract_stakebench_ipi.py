"""
extract_stakebench_ipi.py

Pulls the 13 real Indirect Prompt Injection (IPI) cases out of StakeBench's
IPI_attack/LLM_judge/*_Real_Bench.json files into one clean JSON file we can
build eval_set.jsonl from later (Step 3).

Source: github.com/StakeBench/SBC (MIT licensed)
We deliberately skip DPI_attack/ entirely -- those simulate the USER typing
something malicious, not a manipulated catalog page, which is a different
threat model from ours.
"""
import json
import glob
import os

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "reference-repos", "stakebench-data")
IPI_GLOB = os.path.join(REPO_ROOT, "IPI_attack", "LLM_judge", "*_Real_Bench.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "stakebench_ipi_cases.json")

def main():
    cases = []
    for path in sorted(glob.glob(IPI_GLOB)):
        data = json.load(open(path, encoding="utf-8"))
        for t in data["templates"]:
            cases.append({
                "template_id": t["template_id"],
                "objective_name": t["objective_name"],
                "attack_surface": t["attack_spec"]["injection_location"],
                "injection_content": t["attack_spec"]["injection_content"],
                "attacker_goal": t["attack_spec"]["attacker_goal"],
                "source_file": os.path.basename(path),
            })

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(cases)} IPI cases -> {OUT_PATH}")
    print()
    print("Objectives covered:")
    for c in cases:
        print(f"  {c['template_id']:6s} | {c['objective_name']}")

if __name__ == "__main__":
    main()
