# Schema compiler fixture contract

The compiler tests build isolated repositories under pytest's temporary directory
from the SQL fragments in `test_schema_compiler.py`. This directory is the stable
home for larger regression fixtures when a production DDL form needs reproduction.
