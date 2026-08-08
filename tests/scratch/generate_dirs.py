import os

test_dirs = [
    "tests/fixtures",
    "tests/authentication",
    "tests/authorization",
    "tests/ownership",
    "tests/permissions",
    "tests/jwt",
    "tests/pagination",
    "tests/regression",
    "tests/characterization",
    "tests/mutation",
]

for d in test_dirs:
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/__init__.py", "w") as f:
        pass

with open("tests/__init__.py", "w") as f:
    pass

with open("pytest.ini", "w") as f:
    f.write("""[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short
""")

with open(".coveragerc", "w") as f:
    f.write("""[run]
branch = True
source = app
omit =
    app/tests/*
    app/security/bootstrap/*
""")
