import time
import uuid
import psutil
import threading
import json
import os
import logging
from typing import Dict, List, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validation")

@dataclass
class ValidationMetrics:
    memory_growth_mb: float = 0.0
    cpu_usage_avg: float = 0.0
    duration_sec: float = 0.0
    custom_metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

class ValidationResult:
    def __init__(self, name: str, status: str, metrics: ValidationMetrics):
        self.name = name
        self.status = status
        self.metrics = metrics
        
    def to_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "metrics": {
                "memory_growth_mb": self.metrics.memory_growth_mb,
                "cpu_usage_avg": self.metrics.cpu_usage_avg,
                "duration_sec": self.metrics.duration_sec,
                "custom": self.metrics.custom_metrics,
                "errors": self.metrics.errors
            }
        }

class ValidationFramework:
    def __init__(self, output_dir: str = "validation_reports"):
        self.results: List[ValidationResult] = []
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def measure(self, test_name: str, func: Callable, *args, **kwargs) -> ValidationResult:
        logger.info(f"Starting test: {test_name}")
        
        process = psutil.Process(os.getpid())
        start_mem = process.memory_info().rss / (1024 * 1024) # MB
        
        start_time = time.time()
        cpu_samples = []
        
        stop_sampling = False
        def sample_cpu():
            while not stop_sampling:
                cpu_samples.append(process.cpu_percent(interval=0.1))
                time.sleep(0.1)
                
        t = threading.Thread(target=sample_cpu, daemon=True)
        t.start()
        
        status = "PASS"
        metrics = ValidationMetrics()
        
        try:
            custom_metrics = func(*args, **kwargs)
            if custom_metrics:
                metrics.custom_metrics = custom_metrics
        except Exception as e:
            logger.error(f"Test {test_name} failed: {e}", exc_info=True)
            status = "FAIL"
            metrics.errors.append(str(e))
            
        stop_sampling = True
        t.join(timeout=1.0)
        
        end_time = time.time()
        end_mem = process.memory_info().rss / (1024 * 1024)
        
        metrics.duration_sec = end_time - start_time
        metrics.memory_growth_mb = end_mem - start_mem
        if cpu_samples:
            metrics.cpu_usage_avg = sum(cpu_samples) / len(cpu_samples)
            
        result = ValidationResult(test_name, status, metrics)
        self.results.append(result)
        logger.info(f"Finished test: {test_name} - Status: {status} - Duration: {metrics.duration_sec:.2f}s")
        return result

    def generate_report(self):
        report_id = str(uuid.uuid4())[:8]
        filepath = os.path.join(self.output_dir, f"report_{report_id}.json")
        with open(filepath, "w") as f:
            json.dump([r.to_dict() for r in self.results], f, indent=4)
        logger.info(f"Report generated: {filepath}")
        
        # Also print markdown summary
        print(f"\n# Validation Report ({datetime.now().isoformat()})")
        print("| Test Name | Status | Duration (s) | Mem Growth (MB) | Errors |")
        print("|-----------|--------|--------------|-----------------|--------|")
        for r in self.results:
            err_count = len(r.metrics.errors)
            print(f"| {r.name} | {r.status} | {r.metrics.duration_sec:.2f} | {r.metrics.memory_growth_mb:.2f} | {err_count} |")
