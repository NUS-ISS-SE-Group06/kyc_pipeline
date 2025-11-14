import os, json, datetime

def pytest_sessionfinish(session, exitstatus):
    """Hook to save DeepEval results summary to logs/deepeval_results.json"""
    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "exitstatus": exitstatus,
        "total_tests": session.testscollected,
        "outcome": "passed" if exitstatus == 0 else "failed",
    }

    # resolve path safely relative to pytest rootdir
    project_root = session.config.rootpath or os.getcwd()
    logs_dir = os.path.join(project_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    result_path = os.path.join(logs_dir, "deepeval_results.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n🧠  DeepEval report saved to {result_path}\n")
