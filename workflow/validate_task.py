"""Task 2 of the ``policy_time_machine_regeneration`` job: validate.

Equivalent to `python -m generator.validate --out /Volumes/workspace/policy_time_machine/raw`,
invoked in-process for the same reason, and with the same ``--bundle-root``
``sys.path`` bootstrap, as ``generate_task.py`` (see its docstring for the
``__file__``-is-undefined quirk on serverless spark_python_task).

Spec 08 section 2: generator validation runs after generation and before the
pipeline, and answers "is the signal the one we declared?" — effect sizes
within +/-15% relative, the category ranking exact, every severity band
populated, scenario populations at their declared sizes, the guaranteed
activity tail populated through anchor-120d, and identifier lexical
reservation holding.

The non-zero exit code on failure is the gate: ``generator.validate.main``
returns 1 when any check fails, this script propagates that via
``sys.exit``, and a non-zero exit fails the Databricks task, which — because
this task sits between "generate" and "load_source_tables" in the dependency
chain — stops a drifted regeneration before it ever reaches the source
tables or the pipeline.
"""

from __future__ import annotations

import sys


def _bundle_root_from_argv() -> str:
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--bundle-root" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--bundle-root="):
            return arg.split("=", 1)[1]
    raise SystemExit(
        "--bundle-root is required (the job task passes ${workspace.file_path})"
    )


_BUNDLE_ROOT = _bundle_root_from_argv()
if _BUNDLE_ROOT not in sys.path:
    sys.path.insert(0, _BUNDLE_ROOT)

from generator.validate import main as validate_main  # noqa: E402

OUT_DIR = "/Volumes/workspace/policy_time_machine/raw"


def main() -> int:
    print(f"[validate] out={OUT_DIR} bundle-root={_BUNDLE_ROOT}")
    return validate_main(["--out", OUT_DIR])


if __name__ == "__main__":
    # Quirk (Databricks Free Edition, serverless spark_python_task): the exec
    # wrapper treats any raised SystemExit — even code 0 — as an uncaught
    # exception and fails the task, so sys.exit is only called on an actual
    # non-zero result. That is still the gate spec 08 section 2 requires: a
    # non-zero validate result reaches sys.exit here and fails this task,
    # which stops load_source_tables and refresh_pipeline from running.
    _exit_code = main()
    if _exit_code:
        sys.exit(_exit_code)
