import os

ignore_dirs = {'.git', '__pycache__', '.pytest_cache', 'test_db', 'test_db_2', 'validation_output', 'validation_reports', 'logs', 'assets'}
ignore_files = {'Jarvis_Project_Full_Code.txt', 'diff.txt', 'diff_utf8.txt', '.coverage', '.env'}
allowed_exts = {'.py', '.json', '.txt', '.md', '.bat', '.pyw'}

workspace = r"c:\Users\proog\OneDrive\Masaüstü\Projeler\My_Jarvis_Project"
output_file = os.path.join(workspace, "Jarvis_Project_Full_Code.txt")

print(f"Updating {output_file}...")
count = 0

with open(output_file, 'w', encoding='utf-8') as outfile:
    for root, dirs, files in os.walk(workspace):
        # Ignore dirs
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for file in files:
            if file in ignore_files:
                continue
            ext = os.path.splitext(file)[1]
            if ext not in allowed_exts:
                continue
                
            filepath = os.path.join(root, file)
            relpath = os.path.relpath(filepath, workspace)
            
            # Read and write
            try:
                with open(filepath, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    
                outfile.write("\n" + "="*50 + "\n")
                outfile.write(f"FILE: {relpath}\n")
                outfile.write("="*50 + "\n\n")
                outfile.write(content)
                outfile.write("\n")
                count += 1
            except Exception as e:
                print(f"Error reading {relpath}: {e}")

print(f"Successfully updated {output_file} with {count} files.")
