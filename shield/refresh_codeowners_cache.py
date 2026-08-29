"""
refresh_codeowners_cache.py
===========================
Fetches CODEOWNERS from UiPath/flow-workbench and UiPath/StudioWeb,
extracts Shield IS-owned paths, derives keyword signals, and writes
codeowners_cache.json. Run weekly via cron.
"""

import os, sys, json, re, subprocess
from datetime import datetime, timezone

CACHE_FILE = os.path.join(os.path.dirname(__file__), "codeowners_cache.json")

# Shield IS GitHub handles (used to identify IS-owned path blocks)
SHIELD_IS_HANDLES = {
    "rahul-katikineni", "mukundbayyaram", "rohitinu", "baishalighosh",
    "ojalkumar-pixel", "charank2127", "shyamgupta52", "pritishkumar-uipath",
    "rohitpunekar-uipath", "mrstark14", "vaibhavs-uipath",
}


def fetch_codeowners(repo, path_in_repo):
    """Fetch raw CODEOWNERS text from a GitHub repo via gh CLI."""
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/UiPath/{repo}/contents/{path_in_repo}", "--jq", ".content"],
            capture_output=True, text=True, timeout=20
        )
        if r.returncode != 0:
            return ""
        import base64
        content_b64 = r.stdout.strip()
        return base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  fetch failed ({repo}/{path_in_repo}): {e}")
        return ""


def parse_shield_paths(codeowners_text, repo_label):
    """Extract paths owned by Shield IS handles."""
    shield_paths = []
    flow_paths   = []
    lines = codeowners_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        path    = parts[0]
        owners  = {o.lstrip("@").split("/")[-1] for o in parts[1:]}
        if owners & SHIELD_IS_HANDLES:
            shield_paths.append(path)
        else:
            # Catch explicit flow-team paths (portal-members, flow-versioning-owners, studioweb-fe)
            flow_team_groups = {"portal-members", "flow-versioning-owners", "studioweb-fe",
                                "marius-bughiu", "liviu-uba", "cosminsandu25", "toxik", "cozmy", "mhagape"}
            if owners & flow_team_groups and not (owners & SHIELD_IS_HANDLES):
                flow_paths.append(path)
    return shield_paths, flow_paths


def derive_keywords_from_paths(paths):
    """Turn CODEOWNERS path patterns into searchable keyword fragments."""
    keywords = set()
    for p in paths:
        # Strip leading /, trailing *, wildcards
        p_clean = p.lstrip("/").rstrip("*").rstrip("/")
        # Take last 2 path segments as keywords
        segments = p_clean.split("/")
        for seg in segments[-2:]:
            seg = seg.strip()
            if len(seg) < 3:
                continue
            # Convert camelCase and PascalCase to lower-kebab
            seg_kebab = re.sub(r"(?<=[a-z])(?=[A-Z])", "-", seg).lower()
            seg_lower = seg.lower()
            if seg_lower not in {"src", "app", "packages", "libs", "components",
                                  "utils", "hooks", "services", "data", "shared"}:
                keywords.add(seg_lower)
                if seg_kebab != seg_lower:
                    keywords.add(seg_kebab)
    return sorted(keywords)


def main():
    print("Fetching CODEOWNERS...")

    fw_raw = fetch_codeowners("flow-workbench", ".github/CODEOWNERS")
    sw_raw = fetch_codeowners("StudioWeb", "CODEOWNERS")

    if not fw_raw and not sw_raw:
        print("ERROR: both fetches failed — aborting, keeping existing cache")
        sys.exit(1)

    fw_shield, fw_flow = parse_shield_paths(fw_raw, "flow-workbench")
    sw_shield, sw_flow = parse_shield_paths(sw_raw, "StudioWeb")

    print(f"flow-workbench: {len(fw_shield)} Shield paths, {len(fw_flow)} Flow paths")
    print(f"StudioWeb:      {len(sw_shield)} Shield paths, {len(sw_flow)} Flow paths")

    # Derive keywords
    all_shield_paths = fw_shield + sw_shield
    all_flow_paths   = fw_flow   + sw_flow

    shield_kw = derive_keywords_from_paths(all_shield_paths)
    flow_kw   = derive_keywords_from_paths(all_flow_paths)

    # Load existing cache to preserve manually-added signals
    existing = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            existing = json.load(f)

    cache = {
        "last_refreshed": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "flow-workbench": "UiPath/flow-workbench/.github/CODEOWNERS",
            "StudioWeb":      "UiPath/StudioWeb/CODEOWNERS"
        },
        "shield_is_paths": {
            "flow-workbench": fw_shield,
            "StudioWeb":      sw_shield,
        },
        "flow_team_paths": {
            "flow-workbench": fw_flow,
            "StudioWeb":      sw_flow,
        },
        "shield_is_owners_github": sorted(SHIELD_IS_HANDLES),
        # Merge CODEOWNERS-derived keywords with any manually added ones from previous cache
        "shield_is_keywords": sorted(set(shield_kw) | set(existing.get("shield_is_keywords_manual", []))),
        "flow_team_keywords":  sorted(set(flow_kw)   | set(existing.get("flow_team_keywords_manual", []))),
        # Preserve manual overrides verbatim
        "shield_is_keywords_manual": existing.get("shield_is_keywords_manual", []),
        "flow_team_keywords_manual":  existing.get("flow_team_keywords_manual",  []),
    }

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"Cache updated. Shield keywords: {len(cache['shield_is_keywords'])}, Flow keywords: {len(cache['flow_team_keywords'])}")
    print(f"Written to: {CACHE_FILE}")


if __name__ == "__main__":
    main()
