import sys
import os
import glob
import subprocess
import time
import json
from datetime import datetime

def run_all_validations():
    print("==================================================")
    print("  J.A.R.V.I.S. AUTOMATED COGNITIVE VALIDATION SUITE")
    print("==================================================")
    print(f"Started at: {datetime.now().isoformat()}")
    print("Looking for validation tests...")
    
    # Run from the project root
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    validation_dir = os.path.join(root_dir, "validation")
    
    test_files = sorted(glob.glob(os.path.join(validation_dir, "test_*.py")))
    
    passed = 0
    failed = 0
    
    results = []
    
    for test_file in test_files:
        test_name = os.path.basename(test_file)
        print(f"\n>> Running {test_name}...")
        
        start = time.time()
        try:
            # Run the test file as a subprocess
            result = subprocess.run(
                [sys.executable, test_file],
                cwd=root_dir,
                capture_output=True,
                text=True,
                timeout=120  # Max 2 minutes per standard test (Long session has its own runner params)
            )
            
            duration = time.time() - start
            
            if result.returncode == 0:
                print(f"[PASS] ({duration:.2f}s)")
                passed += 1
                results.append({"test": test_name, "status": "PASS", "duration": duration})
            else:
                print(f"[FAIL] ({duration:.2f}s)")
                print("--- Error Output ---")
                print(result.stderr.strip())
                print("--------------------")
                failed += 1
                results.append({"test": test_name, "status": "FAIL", "duration": duration, "error": result.stderr.strip()})
                
        except subprocess.TimeoutExpired:
            print(f"[TIMEOUT] (120s+)")
            failed += 1
            results.append({"test": test_name, "status": "TIMEOUT", "duration": 120.0})
            
    print("\n==================================================")
    print("  VALIDATION SUMMARY")
    print("==================================================")
    print(f"Total Tests: {len(test_files)}")
    print(f"Passed:      {passed}")
    print(f"Failed:      {failed}")
    
    # Save master report
    reports_dir = os.path.join(validation_dir, "validation_reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, f"master_report_{int(time.time())}.json")
    
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "passed": passed,
            "failed": failed,
            "total": len(test_files),
            "results": results
        }, f, indent=4)
        
    print(f"\nMaster report saved to: {report_path}")

if __name__ == "__main__":
    run_all_validations()
