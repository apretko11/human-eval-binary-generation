#!/usr/bin/env python3

"""
Add the two missing PIC-reference artifacts to the EXISTING HumanEval
ARM64 macOS relocatable dataset:

    compiler.pic.s
    code.pic.o.objdump

Important:
- Operates on generated_humaneval_arm64_mac_reloc
- Reuses the EXISTING code.pic.o that was already used to build code.dylib
- Does NOT rebuild code.pic.o, code.dylib, code.o, or code.program
- Uses the established relocation-preserving Mach-O object dump:
      xcrun llvm-objdump -dr code.pic.o
"""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated_humaneval_arm64_mac_reloc"

SPLITS = ["O0", "O2"]
EXPECTED_ROWS = 164

CLANG = ["xcrun", "clang"]
OBJDUMP = ["xcrun", "llvm-objdump"]


def run(cmd, *, stdout_path=None):
    cmd = [str(x) for x in cmd]
    print("+", " ".join(cmd))

    if stdout_path is None:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
        )
    else:
        with stdout_path.open("w", encoding="utf-8") as f:
            result = subprocess.run(
                cmd,
                text=True,
                stdout=f,
                stderr=subprocess.PIPE,
            )

    if result.returncode != 0:
        stdout = getattr(result, "stdout", "") or ""
        stderr = result.stderr or ""

        raise RuntimeError(
            "Command failed:\n"
            + " ".join(cmd)
            + "\n\nSTDOUT:\n"
            + stdout
            + "\n\nSTDERR:\n"
            + stderr
        )


def require_nonempty(path):
    if not path.is_file():
        raise RuntimeError(f"Missing file: {path}")

    if path.stat().st_size == 0:
        raise RuntimeError(f"Empty file: {path}")


def build_one(split, task_dir):
    opt = "-O0" if split == "O0" else "-O2"

    source_c = task_dir / "source.c"

    # This is the exact PIC object already present in the reloc dataset
    # and already used to build code.dylib.
    pic_object = task_dir / "code.pic.o"

    compiler_pic_s = task_dir / "compiler.pic.s"
    pic_object_disasm = task_dir / "code.pic.o.objdump"

    # Make sure we are enriching the expected existing reloc dataset.
    for path in [
        source_c,
        task_dir / "compiler.s",
        task_dir / "code.o",
        task_dir / "code.o.objdump",
        pic_object,
        task_dir / "code.dylib",
        task_dir / "code.dylib.objdump",
        task_dir / "code.program",
        task_dir / "code.program.objdump",
    ]:
        require_nonempty(path)

    # 1. PIC compiler assembly from the same source and optimization level.
    run([
        *CLANG,
        "-arch",
        "arm64",
        opt,
        "-fPIC",
        "-S",
        source_c,
        "-o",
        compiler_pic_s,
    ])

    require_nonempty(compiler_pic_s)

    # 2. Relocation-preserving disassembly of the EXISTING PIC object.
    run(
        [
            *OBJDUMP,
            "-dr",
            pic_object,
        ],
        stdout_path=pic_object_disasm,
    )

    require_nonempty(pic_object_disasm)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--split",
        action="append",
        choices=SPLITS,
        help="Repeatable. Default: both O0 and O2.",
    )

    args = parser.parse_args()

    splits = args.split or SPLITS

    if not GENERATED.is_dir():
        raise SystemExit(
            f"Missing generated dataset root:\n{GENERATED}"
        )

    completed = 0
    failures = []

    relocation_stats = {}

    for split in splits:
        split_dir = GENERATED / split

        if not split_dir.is_dir():
            raise SystemExit(f"Missing split directory: {split_dir}")

        task_dirs = sorted(
            p for p in split_dir.iterdir()
            if p.is_dir()
        )

        if len(task_dirs) != EXPECTED_ROWS:
            raise SystemExit(
                f"{split}: expected {EXPECTED_ROWS} task directories, "
                f"found {len(task_dirs)}"
            )

        print()
        print("=" * 78)
        print(f"HUMANEVAL ARM64 MACOS PIC REFERENCES: {split}")
        print("=" * 78)

        for i, task_dir in enumerate(task_dirs, 1):
            print(
                f"\n===== {split}: {task_dir.name} "
                f"({i}/{EXPECTED_ROWS}) ====="
            )

            try:
                build_one(split, task_dir)
                completed += 1
            except Exception as exc:
                print(f"FAILED: {exc}")
                failures.append(
                    (split, task_dir.name, str(exc))
                )

        # Dataset-level relocation sanity check.
        rows_with_reloc = 0
        total_reloc_lines = 0

        for task_dir in task_dirs:
            dump = task_dir / "code.pic.o.objdump"

            if not dump.is_file():
                continue

            reloc_lines = [
                line
                for line in dump.read_text(
                    errors="replace"
                ).splitlines()
                if "ARM64_RELOC_" in line
            ]

            if reloc_lines:
                rows_with_reloc += 1
                total_reloc_lines += len(reloc_lines)

        relocation_stats[split] = (
            rows_with_reloc,
            total_reloc_lines,
        )

    expected = len(splits) * EXPECTED_ROWS

    print()
    print("=" * 78)
    print("HUMANEVAL ARM64 MACOS PIC REFERENCE GENERATION SUMMARY")
    print("=" * 78)
    print(f"Expected instances:  {expected}")
    print(f"Completed instances: {completed}")
    print(f"Failures:             {len(failures)}")

    for split in splits:
        rows, lines = relocation_stats[split]
        print(
            f"{split} PIC object relocations: "
            f"{rows}/{EXPECTED_ROWS} rows, "
            f"{lines} ARM64_RELOC_ lines"
        )

    if failures:
        print()
        print("FAILURES:")
        for split, task_name, error in failures:
            print(f"  {split} {task_name}: {error}")
        raise SystemExit(1)

    if completed != expected:
        raise SystemExit(
            f"Expected {expected} completed instances, "
            f"got {completed}"
        )

    print("OVERALL: PASS")


if __name__ == "__main__":
    main()
