from django.shortcuts import render
import requests
import xml.etree.ElementTree as ET
from django.shortcuts import render
from .forms import RepoURLForm, ReportSelectForm
from .utils import extract_owner_repo, download_jacoco_reports, parse_all_reports, list_report_folders
from django.conf import settings
import os

# Create your views here.


def home(request):
    return render(request, 'dashboard/index.html')


def dashboard(request):
    # --- Initialize ---
    form         = RepoURLForm(request.POST or None)
    report_form  = None
    reports      = []
    metrics      = {}
    coverage_trend = {"labels": [], "data": []}
    repo_name    = ""

    print("[DEBUG] Entering dashboard view")

    # --- Handle POST of GitHub URL or report selection ---
    if request.method == "POST" and form.is_valid():
        repo_url = form.cleaned_data["repo_url"]
        print(f"[DEBUG] Submitted repo_url = {repo_url}")
        try:
            # 1) Extract owner/repo
            owner, repo_name = extract_owner_repo(repo_url)

            # 2) Ensure local download directory
            dest_dir = os.path.join(
                settings.BASE_DIR, "static", "data", repo_name, "reports"
            )
            print(f"[DEBUG] Reports dest_dir = {dest_dir}")

            # 3) Download all htmlReport* files
            download_jacoco_reports(owner, repo_name, dest_dir)

            # 4) Discover all report folders
            reports = list_report_folders(dest_dir)
            print(f"[DEBUG] Discovered reports = {reports}")

            # 5) Parse all of them (for debug and to pick initial)
            all_metrics = parse_all_reports(dest_dir)
            print(f"[DEBUG] all_metrics keys = {list(all_metrics.keys())}")

            # 6) Build report‐selection form
            report_form = ReportSelectForm(request.POST or None)
            report_form.fields["repo_url"].initial = repo_url
            report_form.fields["report"].choices = [(r, r) for r in reports]

            # 7) Determine which report to show
            selected = request.POST.get("report", reports[0] if reports else None)
            report_form.fields["report"].initial = selected
            print(f"[DEBUG] Selected report = {selected}")

            # 8) Pull metrics for that report
            metrics = all_metrics.get(selected, {})
            print(f"[DEBUG] Metrics for {selected} = {metrics}")

            # 9) Build a simple coverage trend (single point)
            cp = metrics.get("LINE", {}).get("coverage", 0)
            coverage_trend = {
                "labels": [selected],
                "data":   [cp],
            }
            print(f"[DEBUG] coverage_trend = {coverage_trend}")

        except Exception as e:
            # Catch everything and show on form
            print(f"[ERROR] dashboard exception: {e}")
            form.add_error("repo_url", str(e))

    print(f'Metrics after processing: {metrics}\n\nCoverage Trend: {coverage_trend}')

    # --- Render template ---
    context = {
        "form":            form,
        "report_form":     report_form,
        "reports":         reports,
        "metrics":         metrics,
        "coverage_trend":  coverage_trend,
        "repo_name":       repo_name,
    }
    print(f"[DEBUG] Rendering dashboard with context keys: {list(context.keys())}")
    return render(request, "dashboard/dashboard.html", context)


# def dashboard(request):
#     xml_data = fetch_jacoco_metrics('example_owner', 'example_repo')
#     if xml_data:
#         metrics = parse_jacoco_xml(xml_data)
#     else:
#         metrics = {'error': 'Unable to fetch data'}
    
#     metrics = {
#         'total_test_cases': 120,
#         'total_lines': 1500,
#         'coverage_percentage': 85.5,
#         'pass_rate': 92,
#         'fail_rate': 8,
#         'passed_tests': 110,
#         'failed_tests': 10
#     }
#     coverage_trend = {
#         'labels': ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
#         'data': [75, 78, 80, 82, 85, 85.5]
#     }

#     context = {
#         'metrics': metrics,
#         'coverage_trend': coverage_trend
#     }

#     return render(request, 'dashboard/dashboard.html', context)


def table(request):
    return render(request, 'dashboard/table.html')


def profile(request):
    return render(request, 'dashboard/profile.html')


# Fetching JaCoCo Data from GitHub
def fetch_jacoco_metrics(repo_owner, repo_name):
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/target/site/jacoco/jacoco.xml"
    response = requests.get(url)

    if response.status_code == 200:
        content = response.json()['content']
        import base64
        xml_data = base64.b64decode(content)
        return xml_data
    else:
        return None


# Parsing JaCoCo XML to extract metrics
def parse_jacoco_xml(xml_data):
    root = ET.fromstring(xml_data)
    
    metrics = {
        'total_lines': 0,
        'covered_lines': 0,
        'coverage_percentage': 0,
    }
    
    for counter in root.findall('.//counter'):
        if counter.attrib['type'] == 'LINE':
            covered = int(counter.attrib['covered'])
            missed = int(counter.attrib['missed'])
            total = covered + missed
            coverage = (covered / total) * 100 if total else 0
            metrics.update({
                'total_lines': total,
                'covered_lines': covered,
                'coverage_percentage': round(coverage, 2),
            })

    return metrics
