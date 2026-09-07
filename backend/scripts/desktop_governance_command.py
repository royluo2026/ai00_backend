"""Trusted caller command: isolated startup, then a fixed Git bootstrap blob.

This constant is used by the release gate and fresh-process tests. It never
imports or executes the working-directory generator or bootstrap file.
"""

BOOTSTRAP_LOADER = (
    "import subprocess; "
    "commit=subprocess.check_output(['git','rev-parse','--verify','HEAD^{commit}'],text=True).strip(); "
    "blob=subprocess.check_output(['git','show',commit+':backend/scripts/desktop_governance_bootstrap.py']); "
    "exec(compile(blob,'<committed-desktop-bootstrap>','exec'),"
    "{'__name__':'__main__','BOOTSTRAP_COMMIT':commit})"
)


def isolated_command(python: str, *args: str) -> list[str]:
    return [python, "-I", "-S", "-c", BOOTSTRAP_LOADER, *args]
