import os

# Ayarlar: Hangi klasörleri ve dosya uzantılarını dahil edeceğiz
INCLUDE_DIRS = ['core', 'memory', 'tools', 'gui', 'tests', 'validation', 'audio']
INCLUDE_EXTS = ['.py', '.txt', '.md', '.json']
EXCLUDE_FILES = ['Jarvis_Project_Full_Code.txt', 'tree.txt', 'debug.log', '.env']

# Proje ana dizini
ROOT_DIR = r'c:\Users\proog\OneDrive\Masaüstü\Projeler\My_Jarvis_Project'
OUTPUT_FILE = os.path.join(ROOT_DIR, 'Jarvis_Project_Full_Code.txt')

def collect_code():
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        # Ana dizindeki önemli dosyalar
        for file in os.listdir(ROOT_DIR):
            if any(file.endswith(ext) for ext in INCLUDE_EXTS) and file not in EXCLUDE_FILES:
                file_path = os.path.join(ROOT_DIR, file)
                if os.path.isfile(file_path):
                    write_file_to_out(file_path, ROOT_DIR, outfile)

        # Alt dizinlerdeki dosyalar
        for subdir in INCLUDE_DIRS:
            dir_path = os.path.join(ROOT_DIR, subdir)
            if not os.path.exists(dir_path):
                continue
            
            for root, dirs, files in os.walk(dir_path):
                # Gereksiz klasörleri atla
                if '__pycache__' in root:
                    continue
                
                for file in files:
                    if any(file.endswith(ext) for ext in INCLUDE_EXTS):
                        file_path = os.path.join(root, file)
                        write_file_to_out(file_path, ROOT_DIR, outfile)

def write_file_to_out(file_path, root_dir, outfile):
    relative_path = os.path.relpath(file_path, root_dir)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            outfile.write(f"\n{'='*50}\n")
            outfile.write(f"FILE: {relative_path}\n")
            outfile.write(f"{'='*50}\n\n")
            outfile.write(content)
            outfile.write("\n\n")
    except Exception as e:
        outfile.write(f"\nERROR READING {relative_path}: {str(e)}\n")

if __name__ == "__main__":
    collect_code()
    print(f"Bütün kodlar şurada toplandı: {OUTPUT_FILE}")
