import os
import re

ver = (os.environ.get("GITHUB_REF_NAME") or "").lstrip("v") or "0.1.0"
path = "file_manager.py"
with open(path, encoding="utf-8") as f:
    content = f.read()
content, n = re.subn(r'^VERSION = ".*"', f'VERSION = "{ver}"', content, flags=re.M)
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
# plik wersji bundlowany do binarki / instalatora
with open("version.txt", "w", encoding="utf-8") as f:
    f.write(ver)
print(f"Set VERSION = {ver!r} (replacements={n})")
