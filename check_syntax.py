import py_compile, os, sys

errors = []
count = 0
for root, dirs, files in os.walk("backend"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            count += 1
            try:
                py_compile.compile(path, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(str(e))

if errors:
    print(f"SYNTAX ERRORS ({len(errors)}):")
    for e in errors:
        print(" ", e)
    sys.exit(1)
else:
    print(f"All Python syntax OK — {count} files checked")
