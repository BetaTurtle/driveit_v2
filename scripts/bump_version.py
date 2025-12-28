
import re
import sys
import os

FILE_PATH = 'landing.html'

def bump_version():
    if not os.path.exists(FILE_PATH):
        print(f"Error: {FILE_PATH} not found.")
        sys.exit(1)

    with open(FILE_PATH, 'r') as f:
        content = f.read()

    # Regex to find version pattern like >v1.0.1<
    # We look for the specific span class or just the format vX.Y.Z inside a tag
    pattern = r'(>v)(\d+)\.(\d+)\.(\d+)(<)'
    
    match = re.search(pattern, content)
    if not match:
        print("Warning: No version number found in landing.html (format >vX.Y.Z<). Skipping bump.")
        sys.exit(0)

    major, minor, patch = map(int, match.group(2, 3, 4))
    new_patch = patch + 1
    new_version_str = f"{match.group(1)}{major}.{minor}.{new_patch}{match.group(5)}"
    
    new_content = content[:match.start()] + new_version_str + content[match.end():]
    
    with open(FILE_PATH, 'w') as f:
        f.write(new_content)
    
    print(f"Bumped landing.html version to v{major}.{minor}.{new_patch}")

if __name__ == "__main__":
    bump_version()
