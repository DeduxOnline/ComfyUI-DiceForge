# SonarQube Cloud results in GitHub: after the scan (tests.yml), waits until SonarQube Cloud has processed the report, then writes the Quality
# Gate, the main measures, every open issue and every security hotspot to the run's summary page (and to the log), so they can be read on GitHub.
# Only the Python standard library; the token is SONAR_TOKEN. A failed Quality Gate (ERROR) fails the job, after the summary is written; results
# that can't be read (SonarQube Cloud down, a processing that timed out) don't.
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = "https://sonarcloud.io"
TOKEN = os.environ.get("SONAR_TOKEN", "")
MEASURES = [("alert_status", "Quality Gate"), ("bugs", "Bugs"), ("vulnerabilities", "Vulnerabilities"), ("security_hotspots", "Security hotspots"),
            ("code_smells", "Code smells"), ("coverage", "Coverage %"), ("line_coverage", "Line coverage %"), ("branch_coverage", "Branch coverage %"),
            ("duplicated_lines_density", "Duplications %"), ("ncloc", "Lines of code")]


def fetch(path, params):
    url = f"{HOST}/api/{path}?{urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


# A call of the Web API. Asked for a branch by name and refused (403: some plans answer for the main branch only), it asks again without the
# branch; any other failure names the call, so the summary says which part could not be read.
def api(path, **params):
    try:
        return fetch(path, params)
    except urllib.error.HTTPError as error:
        if error.code == 403 and params.get("branch"):
            print(f"{path}: branch {params['branch']} refused (403), reading the main branch instead", file=sys.stderr)
            return fetch(path, {key: value for key, value in params.items() if key != "branch"})
        raise RuntimeError(f"{path}: HTTP {error.code} {error.reason}") from None


def report_task():
    path = os.path.join(".scannerwork", "report-task.txt")
    with open(path, encoding="utf-8") as file:
        return dict(line.strip().split("=", 1) for line in file if "=" in line)


def pull_request():
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return None
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as file:
        return str(json.load(file)["number"])


def wait_for(task_id):
    for _ in range(60): # Up to 5 minutes.
        status = api("ce/task", id=task_id)["task"]["status"]
        if status not in ("PENDING", "IN_PROGRESS"):
            return status
        time.sleep(5)
    return "TIMEOUT"


def all_pages(path, key, **params):
    items, page = [], 1
    while True:
        data = api(path, p=page, ps=500, **params)
        items += data[key]
        total = data.get("paging", {}).get("total", data.get("total", len(items)))
        if len(items) >= total or not data[key] or page >= 20:
            return items
        page += 1


def file_of(component, project):
    return component.removeprefix(f"{project}:")


def main(result):
    task = report_task()
    project, pr = task["projectKey"], pull_request()
    # The branch analysed (main, or the pushed branch): asked by name, since SonarQube Cloud's main branch can have another name (master).
    where = {"pullRequest": pr} if pr else {"branch": os.environ.get("GITHUB_REF_NAME")}
    status = wait_for(task["ceTaskId"])
    lines = [f"## SonarQube Cloud: {project}" + (f" (pull request #{pr})" if pr else ""), "",
             f"[Dashboard]({task.get('dashboardUrl', HOST)}) · analysis {status}", ""]
    if status != "SUCCESS":
        return lines + [f"The analysis was not processed ({status}); see the dashboard."]
    gate = api("qualitygates/project_status", projectKey=project, **where)["projectStatus"]
    result["gate"] = gate["status"]
    lines += [f"**Quality Gate: {gate['status']}**", ""]
    failed = [condition for condition in gate.get("conditions", []) if condition["status"] == "ERROR"]
    for condition in failed:
        lines.append(f"- ❌ {condition['metricKey']}: {condition.get('actualValue')} (needs {condition['comparator']} {condition.get('errorThreshold')})")
    measures = {measure["metric"]: measure.get("value", measure.get("period", {}).get("value"))
                for measure in api("measures/component", component=project, metricKeys=",".join(key for key, _ in MEASURES), **where)["component"]["measures"]}
    lines += ["", "| Measure | Value |", "|---|---|"] + [f"| {name} | {measures.get(key, '—')} |" for key, name in MEASURES]
    issues = all_pages("issues/search", "issues", componentKeys=project, resolved="false", **where)
    lines += ["", f"### Open issues: {len(issues)}", ""]
    if issues:
        lines += ["| Severity | Type | Rule | Where | Message |", "|---|---|---|---|---|"]
        order = {"BLOCKER": 0, "CRITICAL": 1, "MAJOR": 2, "MINOR": 3, "INFO": 4}
        for issue in sorted(issues, key=lambda issue: (order.get(issue.get("severity"), 9), issue["component"], issue.get("line", 0))):
            message = issue["message"].replace("|", "\\|")
            lines.append(f"| {issue.get('severity')} | {issue.get('type')} | {issue['rule']} | `{file_of(issue['component'], project)}:{issue.get('line', '')}` | {message} |")
    hotspots = all_pages("hotspots/search", "hotspots", projectKey=project, **where)
    lines += ["", f"### Security hotspots: {len(hotspots)}", ""]
    if hotspots:
        lines += ["| Probability | Status | Rule | Where | Message |", "|---|---|---|---|---|"]
        for hotspot in hotspots:
            message = hotspot["message"].replace("|", "\\|")
            lines.append(f"| {hotspot.get('vulnerabilityProbability')} | {hotspot.get('status')} | {hotspot.get('ruleKey')} | "
                         f"`{file_of(hotspot['component'], project)}:{hotspot.get('line', '')}` | {message} |")
    return lines


if __name__ == "__main__":
    result = {"gate": None}
    try:
        text = "\n".join(main(result))
    except Exception as error: # noqa: BLE001  (a summary that can't be made never fails the tests)
        text = f"## SonarQube Cloud\n\nCould not read the results: {error!r}"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write(text + "\n")
    if result["gate"] == "ERROR":
        print("The Quality Gate failed: see the conditions and open issues above.", file=sys.stderr)
    sys.exit(1 if result["gate"] == "ERROR" else 0)
