"""
fetch_injected_descriptions.py

Pulls REAL, published indirect-prompt-injection (IPI) payload text for the
eval set's `injected / description` surface -- the surface that had zero real
data after the Sept 3 pass (RAGDOLL's content_rewrite/ turned out to be benign
paraphrase, not attack content).

Three real sources, none e-commerce-checkout-native. Each row carries a `notes`
string recording how its threat model differs from this firewall's
(checkout-hijack / payment-data exfiltration), so nothing downstream mistakes a
GitLab-ops or banking IPI for a catalog-checkout attack:

  1. WASP  (facebookresearch/wasp, CC-BY-NC-4.0)
     webarena_prompt_injections/configs/croissant/attacks_in_webarena_format.jsonl
     -> the `instruction` field: real IPI instructions a web agent reads out of
        planted GitLab/Reddit page content. Templated slots ({attacker_domain},
        {ssh_key}, ...) are kept verbatim, same as StakeBench's [original_product].
     LICENSE NOTE: CC BY-NC 4.0 -- non-commercial use only. Fine for a research
     eval set; attribute WASP if the set is redistributed.

  2. InjecAgent  (uiuc-kang-lab/InjecAgent, MIT, (c) 2023 Qiusi Zhan)
     data/attacker_cases_dh.jsonl + data/attacker_cases_ds.jsonl
     -> the `Attacker Instruction` field: real IPI instructions delivered via
        tool-return content (data-harm + data-stealing cases; several are
        Amazon-account / payment-method / address exfiltration, the closest of
        the three to this firewall's threat model).

  3. AgentDojo  (ethz-spylab/agentdojo, MIT)
     src/agentdojo/default_suites/v1/{banking,slack,travel,workspace}/injection_tasks.py
     -> each injection task's GOAL string: real IPI goals for banking / Slack /
        travel / workspace agents. f-string {_CONST} slots are resolved against
        the constants defined in the same class (the benchmark's own values);
        anything left unresolved is dropped rather than guessed.

Sources that were checked and REJECTED for this surface (documented so nobody
re-tries them):
  - RAGDOLL content_rewrite/ and cse-ranking-manipulation dataset.zip: benign
    brand-name-normalized paraphrase, no attack content (verified Sept 3).
  - ChenWu98/agent-attack (VWA adversarial, ICLR 2025): image-perturbation
    attacks only (bim/pgd/clip) -- no reusable text payloads.
  - deepset/prompt-injections, jayavibhav/prompt-injection,
    xTRam1/safe-guard-prompt-injection: real text, but direct-PI / jailbreak
    distribution (roleplay, "ignore previous orders", non-English political
    manipulation), not IPI-in-content. Labeling them injected/description would
    misrepresent both surface and threat model -- same reason StakeBench's DPI
    templates are excluded (plan Section 3, Q6).

Run from the eval/ folder:  python fetch_injected_descriptions.py
Writes: injected_descriptions.json  (list of {text, source, notes})
"""
import json
import re
import time
import urllib.request

OUT_PATH = "injected_descriptions.json"

WASP_URL = (
    "https://raw.githubusercontent.com/facebookresearch/wasp/main/"
    "webarena_prompt_injections/configs/croissant/attacks_in_webarena_format.jsonl"
)
INJECAGENT_URLS = [
    ("dh", "https://raw.githubusercontent.com/uiuc-kang-lab/InjecAgent/main/data/attacker_cases_dh.jsonl"),
    ("ds", "https://raw.githubusercontent.com/uiuc-kang-lab/InjecAgent/main/data/attacker_cases_ds.jsonl"),
]
AGENTDOJO_SUITES = ["banking", "slack", "travel", "workspace"]
AGENTDOJO_URL = (
    "https://raw.githubusercontent.com/ethz-spylab/agentdojo/main/src/agentdojo/"
    "default_suites/v1/{}/injection_tasks.py"
)

MIN_LEN = 20


def fetch(url: str, attempts: int = 5) -> str:
    for i in range(attempts):
        try:
            return urllib.request.urlopen(url, timeout=45).read().decode("utf-8", "ignore")
        except Exception as e:
            if i == attempts - 1:
                raise
            print(f"  retry {i + 1} ({type(e).__name__}) {url}")
            time.sleep(3)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def from_wasp() -> list:
    rows = []
    seen = set()
    for line in fetch(WASP_URL).splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        text = norm(rec.get("instruction", ""))
        if len(text) < MIN_LEN or text in seen:
            continue
        seen.add(text)
        env = rec.get("environment", "?")
        exfil = rec.get("exfil", False)
        rows.append({
            "text": text,
            "source": "wasp",
            "notes": f"WASP web-agent IPI, {env} environment"
                     f"{', exfiltration' if exfil else ''}; not e-commerce. "
                     f"Templated slots kept verbatim. License: CC-BY-NC-4.0.",
        })
    return rows


def from_injecagent() -> list:
    rows = []
    seen = set()
    for tag, url in INJECAGENT_URLS:
        for line in fetch(url).splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            text = norm(rec.get("Attacker Instruction", ""))
            if len(text) < MIN_LEN or text in seen:
                continue
            seen.add(text)
            atype = rec.get("Attack Type", "?")
            kind = "data-harm" if tag == "dh" else "data-stealing"
            rows.append({
                "text": text,
                "source": "injecagent",
                "notes": f"InjecAgent {kind} IPI via tool-return content "
                         f"(Attack Type: {atype}); agent-tool threat model, "
                         f"not catalog-checkout. License: MIT.",
            })
    return rows


def _resolve_fstring(text: str, consts: dict) -> str:
    for k, v in consts.items():
        text = text.replace("{" + k + "}", v)
    return text


def from_agentdojo() -> list:
    rows = []
    seen = set()
    for suite in AGENTDOJO_SUITES:
        src = fetch(AGENTDOJO_URL.format(suite))
        module_consts = dict(re.findall(r'^([A-Z][A-Z0-9_]+)\s*=\s*"([^"]*)"', src, re.M))
        blocks = re.split(r"\n@task_suite\.register_injection_task\n", src)
        for b in blocks[1:]:
            cls = re.search(r"class (InjectionTask\d+)", b)
            if not cls:
                continue
            consts = dict(module_consts)
            consts.update(re.findall(r'^\s+(_?[A-Z][A-Z0-9_]+)\s*=\s*"([^"]*)"', b, re.M))
            # GOAL = f"..." | GOAL = f"""...""" | GOAL = ( "..." "..." )
            m = re.search(r'GOAL\s*=\s*(f?)"""(.*?)"""', b, re.DOTALL) \
                or re.search(r'GOAL\s*=\s*(f?)"([^"]*)"', b) \
                or re.search(r"GOAL\s*=\s*\(\s*((?:\s*f?\"[^\"]*\"\s*)+)\)", b)
            if not m:
                continue
            if m.re.groups == 1:  # parenthesised concatenation
                parts = re.findall(r'f?"([^"]*)"', m.group(1))
                is_f = 'f"' in m.group(1)
                text = "".join(parts)
            else:
                is_f, text = m.group(1), m.group(2)
            if is_f:
                text = _resolve_fstring(text, consts)
            text = norm(text)
            if len(text) < MIN_LEN or "{" in text or text in seen:
                continue
            seen.add(text)
            rows.append({
                "text": text,
                "source": "agentdojo",
                "notes": f"AgentDojo {suite}-suite IPI goal ({cls.group(1)}); "
                         f"cross-domain agent threat model, not e-commerce. License: MIT.",
            })
    return rows


def main():
    all_rows = []
    for name, fn in [("WASP", from_wasp), ("InjecAgent", from_injecagent),
                     ("AgentDojo", from_agentdojo)]:
        rows = fn()
        print(f"{name}: {len(rows)} distinct injected-instruction rows")
        all_rows.extend(rows)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_rows)} real injected-description rows to {OUT_PATH}")
    print("by source:")
    from collections import Counter
    for s, n in Counter(r["source"] for r in all_rows).items():
        print(f"  {s}: {n}")
    print("\nSample:")
    for r in all_rows[:2] + all_rows[-2:]:
        print(f"  [{r['source']}] {r['text'][:110]!r}")


if __name__ == "__main__":
    main()
