import os
import json
import glob
import tkinter as tk
from tkinter import ttk

class ValidationDashboard(tk.Tk):
    def __init__(self, reports_dir="validation_reports"):
        super().__init__()
        self.title("J.A.R.V.I.S. Cognitive Validation Dashboard")
        self.geometry("800x600")
        self.reports_dir = reports_dir
        
        self.setup_ui()
        self.load_data()
        
    def setup_ui(self):
        # Header
        header = tk.Label(self, text="Cognitive Quality & Validation Telemetry", font=("Helvetica", 16, "bold"), pady=10)
        header.pack()
        
        # Stats frame
        self.stats_frame = tk.Frame(self)
        self.stats_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.lbl_total = tk.Label(self.stats_frame, text="Total Reports: 0", font=("Helvetica", 12))
        self.lbl_total.pack(side=tk.LEFT, padx=10)
        
        self.lbl_passed = tk.Label(self.stats_frame, text="Pass Rate: 0%", font=("Helvetica", 12), fg="green")
        self.lbl_passed.pack(side=tk.LEFT, padx=10)
        
        # Table
        columns = ("Test Name", "Status", "Duration (s)", "Memory Growth (MB)", "Errors")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=20)
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=140)
            
        self.tree.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Refresh Button
        btn_refresh = tk.Button(self, text="Refresh Data", command=self.load_data, font=("Helvetica", 10))
        btn_refresh.pack(pady=10)

    def load_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if not os.path.exists(self.reports_dir):
            return
            
        report_files = sorted(glob.glob(os.path.join(self.reports_dir, "report_*.json")), key=os.path.getmtime, reverse=True)
        
        total = 0
        passed = 0
        
        for file in report_files:
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                    
                for result in data:
                    total += 1
                    status = result.get("status", "UNKNOWN")
                    if status == "PASS":
                        passed += 1
                        
                    metrics = result.get("metrics", {})
                    self.tree.insert("", tk.END, values=(
                        result.get("name", ""),
                        status,
                        f"{metrics.get('duration_sec', 0):.2f}",
                        f"{metrics.get('memory_growth_mb', 0):.2f}",
                        len(metrics.get("errors", []))
                    ), tags=(status,))
            except Exception as e:
                print(f"Failed to load {file}: {e}")
                
        self.tree.tag_configure("PASS", foreground="green")
        self.tree.tag_configure("FAIL", foreground="red")
        
        self.lbl_total.config(text=f"Total Test Runs: {total}")
        if total > 0:
            self.lbl_passed.config(text=f"Pass Rate: {(passed/total)*100:.1f}%")

if __name__ == "__main__":
    reports_path = os.path.join(os.path.dirname(__file__), "validation_reports")
    app = ValidationDashboard(reports_dir=reports_path)
    app.mainloop()
