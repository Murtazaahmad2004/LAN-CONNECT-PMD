import sys

part = sys.argv[1] if len(sys.argv) > 1 else "patch"
major, minor, patch = map(int, open("VERSION").read().strip().split("."))

if part == "major":
    major, minor, patch = major + 1, 0, 0
elif part == "minor":
    minor, patch = minor + 1, 0
else:
    patch += 1

new = f"{major}.{minor}.{patch}"
open("VERSION.txt", "w").write(new + "\n")
print("New version:", new)