import glob

for filepath in glob.glob('l:/DOWNLOADS/Devops/opsforge/tests/**/*.py', recursive=True):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if 'secret123' in line or 'password' in line or 'admin' in line:
                    print(f"{filepath}:{i+1}: {line.strip()}")
    except Exception as e:
        pass
