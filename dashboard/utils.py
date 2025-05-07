import os, re, requests
from bs4 import BeautifulSoup

# GitHub API endpoints
GITHUB_API  = "https://api.github.com/repos/{owner}/{repo}"
GITHUB_TREE = "https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
RAW_BASE    = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def extract_owner_repo(url):
    print(f"[DEBUG] extract_owner_repo: raw url = {url!r}")
    m = re.match(r'https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$', url.strip())
    if not m:
        msg = f"Bad GitHub URL: {url!r}"
        print(f"[ERROR] {msg}")
        raise ValueError(msg)
    owner, repo = m.group(1), m.group(2)
    print(f"[DEBUG] extract_owner_repo → owner={owner}, repo={repo}")
    return owner, repo


def download_jacoco_reports(owner, repo, dest_dir):
    """
    Downloads all JaCoCo HTML report files under any htmlReport*/**/*.html into dest_dir.
    If dest_dir already exists with files, skip download and simply return dest_dir.
    """
    print(f"[DEBUG] download_jacoco_reports: owner={owner}, repo={repo}, dest_dir={dest_dir}")

    # === 0) Early exit if we've already downloaded this repo ===
    if os.path.isdir(dest_dir):
        # check for any file in any subdirectory
        has_files = False
        for root, dirs, files in os.walk(dest_dir):
            if files:
                has_files = True
                break
        if has_files:
            print(f"[DEBUG] Reports already present at {dest_dir}, skipping download.")
            return dest_dir
    # else: either dest_dir doesn't exist or is empty → proceed to download

    # === 1) Determine default branch ===
    repo_url = GITHUB_API.format(owner=owner, repo=repo)
    print(f"[DEBUG] GET {repo_url}")
    r = requests.get(repo_url)
    r.raise_for_status()
    branch = r.json().get("default_branch", "main")
    print(f"[DEBUG] Default branch = {branch}")

    # === 2) Fetch repository tree ===
    tree_url = GITHUB_TREE.format(owner=owner, repo=repo, branch=branch)
    print(f"[DEBUG] GET {tree_url}")
    r = requests.get(tree_url)
    r.raise_for_status()
    tree = r.json().get("tree", [])
    print(f"[DEBUG] Repo tree has {len(tree)} entries")

    # === 3) Filter for any htmlReport*/**/*.html paths ===
    patterns = []
    for item in tree:
        path_lower = item["path"].lower()
        if item["type"] == "blob" and "htmlreport" in path_lower and path_lower.endswith(".html"):
            patterns.append(item["path"])
    print(f"[DEBUG] Found {len(patterns)} HTML report files")

    if not patterns:
        raise FileNotFoundError("No JaCoCo HTML reports found in repo tree.")

    # === 4) Download each file to dest_dir ===
    for rel_path in patterns:
        # strip any top‑level JaCoCo_Reports prefix
        local_rel = rel_path.replace("JaCoCo_Reports/", "").replace("JaCoCo Reports/", "")
        save_path = os.path.join(dest_dir, local_rel)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        raw_url = RAW_BASE.format(owner=owner, repo=repo, branch=branch, path=rel_path)
        print(f"[DEBUG] Downloading {raw_url}")
        resp = requests.get(raw_url)
        if resp.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            print(f"[DEBUG] Saved to {save_path}")
        else:
            print(f"[WARN ] Failed to download {raw_url}: {resp.status_code}")

    # === 5) Final directory dump for debug ===
    print(f"[DEBUG] Completed download into {dest_dir}. Contents:")
    for root, dirs, files in os.walk(dest_dir):
        rel = os.path.relpath(root, dest_dir)
        print(f"  [DIR] {rel or '.'}")
        for fn in files:
            print(f"    - {fn}")

    return dest_dir


def list_report_folders(dest_dir):
    """
    Returns a sorted list of htmlReport* folder names under dest_dir.
    """
    print(f"[DEBUG] list_report_folders: scanning {dest_dir}")
    try:
        entries = os.listdir(dest_dir)
    except FileNotFoundError:
        print(f"[ERROR] {dest_dir} does not exist")
        return []

    reports = []
    for e in entries:
        full = os.path.join(dest_dir, e)
        if os.path.isdir(full) and e.lower().startswith("htmlreport"):
            if os.path.isdir(os.path.join(full, "default")):
                reports.append(e)
                print(f"[DEBUG] Found report folder: {e}")
    reports = sorted(reports)
    print(f"[DEBUG] list_report_folders → {reports}")
    return reports


def safe_int(s):
    try:
        return int(s)
    except Exception as e:
        print(f"[WARN] safe_int({s!r}) → 0 ({e})")
        return 0


def safe_pct(s):
    try:
        return float(s.rstrip("%"))
    except Exception as e:
        print(f"[WARN] safe_pct({s!r}) → 0.0 ({e})")
        return 0.0


def parse_jacoco_html(html, context="(unknown)"):
    """
    Parse JaCoCo default/index.html and return:
      {
        'INSTRUCTION': {'covered':…, 'missed':…, 'coverage':…},
        'BRANCH':      {...},
        'LINE':        {...}
      }
    """
    print(f"[DEBUG] parse_jacoco_html(context={context}): HTML length={len(html)}")
    soup = BeautifulSoup(html, "html.parser")

    # 1) Locate the correct summary table by its real ID
    tbl = soup.select_one("table#coveragetable")
    if not tbl:
        raise RuntimeError(f"[ERROR] No <table id='coveragetable'> found for {context}")

    # 2) Get the single <tr> inside its <tfoot>
    tfoot = tbl.find("tfoot")
    if not tfoot:
        raise RuntimeError(f"[ERROR] No <tfoot> in #coveragetable for {context}")
    row = tfoot.find("tr")
    cells = row.find_all("td")
    print(f"[DEBUG] tfoot cells for {context}: {[c.get_text(strip=True) for c in cells]}")

    # 3) Parse INSTRUCTION: missed of total, then pct
    instr_parts = cells[1].get_text(strip=True).split(" of ")
    missed_i = safe_int(instr_parts[0])
    total_i  = safe_int(instr_parts[1]) if len(instr_parts) > 1 else 0
    covered_i = total_i - missed_i
    pct_i     = safe_pct(cells[2].get_text(strip=True))
    print(f"[DEBUG] {context} INSTRUCTION → missed={missed_i}, total={total_i}, covered={covered_i}, pct={pct_i}%")

    # 4) Parse BRANCH: missed of total, then pct
    branch_parts = cells[3].get_text(strip=True).split(" of ")
    missed_b = safe_int(branch_parts[0])
    total_b  = safe_int(branch_parts[1]) if len(branch_parts) > 1 else 0
    covered_b = total_b - missed_b
    pct_b     = safe_pct(cells[4].get_text(strip=True))
    print(f"[DEBUG] {context} BRANCH → missed={missed_b}, total={total_b}, covered={covered_b}, pct={pct_b}%")

    # 5) Parse LINE: missed, covered, then derive pct if needed
    missed_l  = safe_int(cells[7].get_text(strip=True))
    covered_l = safe_int(cells[8].get_text(strip=True))
    pct_l     = (covered_l / (missed_l + covered_l) * 100) if (missed_l + covered_l) else 0.0
    pct_l     = round(pct_l, 2)
    print(f"[DEBUG] {context} LINE → missed={missed_l}, covered={covered_l}, pct={pct_l}%")

    # 6) Build and return the metrics dict
    metrics = {
        "INSTRUCTION": {"covered": covered_i, "missed": missed_i, "coverage": pct_i},
        "BRANCH":      {"covered": covered_b, "missed": missed_b, "coverage": pct_b},
        "LINE":        {"covered": covered_l, "missed": missed_l, "coverage": pct_l},
    }
    print(f"[DEBUG] Parsed summary for {context}: {metrics}")
    return metrics


def parse_all_reports(dest_dir):
    """
    For every htmlReport* folder under dest_dir, parse its default/index.html
    Returns dict: { report_folder_name: parsed_metrics_dict }
    """
    results = {}
    report_folders = list_report_folders(dest_dir)
    for rpt in report_folders:
        idx_path = os.path.join(dest_dir, rpt, "default", "index.html")
        print(f"[DEBUG] parse_all_reports: about to open {idx_path}")
        if not os.path.isfile(idx_path):
            print(f"[ERROR] Missing index.html at {idx_path}")
            continue

        try:
            with open(idx_path, encoding="utf-8") as f:
                html = f.read()
            metrics = parse_jacoco_html(html, context=rpt)
            results[rpt] = metrics
        except Exception as e:
            print(f"[ERROR] Failed to parse {idx_path}: {e}")

    print(f"[DEBUG] parse_all_reports → parsed folders: {list(results.keys())}")
    return results
