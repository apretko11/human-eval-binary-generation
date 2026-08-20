#!/usr/bin/env python3

"""
Add missing PIC-reference artifacts to the EXISTING HumanEval Linux
relocatable outputs without rebuilding existing normal objects, executables,
shared libraries, or PIC objects.

Creates for every task in O0/O2:
  compiler.pic.s        compiler PIC assembly (-fPIC -S)
  code.pic.o.objdump    relocation-aware disassembly of EXISTING code.pic.o (-dr)
"""

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPLITS = ["O0", "O2"]

TARGETS = {
    "x86_linux": {
        "cc": "gcc",
        "objdump": "objdump",
        "flags": ["-march=x86-64"],
        "generated": ROOT / "generated_humaneval_x86_linux_reloc",
        "format": "elf64-x86-64",
    },
    "arm_linux": {
        "cc": "aarch64-linux-gnu-gcc",
        "objdump": "aarch64-linux-gnu-objdump",
        "flags": ["-march=armv8-a"],
        "generated": ROOT / "generated_humaneval_arm64_linux_reloc",
        "format": "elf64-littleaarch64",
    },
    "riscv_linux": {
        "cc": "riscv64-linux-gnu-gcc",
        "objdump": "riscv64-linux-gnu-objdump",
        "flags": ["-march=rv64gc", "-mabi=lp64d"],
        "generated": ROOT / "generated_humaneval_riscv64_linux_reloc",
        "format": "elf64-littleriscv",
    },
}


def run(cmd, *, stdout_path=None):
    cmd = list(map(str, cmd))
    print("+", " ".join(cmd))

    if stdout_path is None:
        result = subprocess.run(cmd, text=True, capture_output=True)
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
        raise RuntimeError(f"MISSING: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"EMPTY: {path}")


def build_one(target_name, config, split, task_dir):
    opt = "-O0" if split == "O0" else "-O2"

    source_c = task_dir / "source.c"
    existing_pic_object = task_dir / "code.pic.o"

    compiler_pic_s = task_dir / "compiler.pic.s"
    pic_object_disasm = task_dir / "code.pic.o.objdump"

    # Existing artifacts: verify we are enriching the already-built reloc set.
    for path in [
        source_c,
        existing_pic_object,
        task_dir / "code.o.objdump",
        task_dir / "code.so.objdump",
        task_dir / "code.program.objdump",
    ]:
        require_nonempty(path)

    # Missing compiler-side PIC reference. Same target + optimization flags
    # as build_humaneval_linux_reloc.py, plus -fPIC -S.
    run([
        config["cc"],
        *config["flags"],
        opt,
        "-fPIC",
        "-S",
        str(source_c),
        "-o",
        str(compiler_pic_s),
    ])
    require_nonempty(compiler_pic_s)

    # Disassemble the EXACT existing PIC object that was used to build code.so.
    # Relocatable object => -dr (disassemble + relocations).
    run(
        [config["objdump"], "-dr", str(existing_pic_object)],
        stdout_path=pic_object_disasm,
    )
    require_nonempty(pic_object_disasm)

    text = pic_object_disasm.read_text(errors="replace")
    if config["format"] not in text:
        raise RuntimeError(
            f"{target_name} {split} {task_dir.name}: wrong PIC object format; "
            f"expected {config['format']}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        action="append",
        choices=sorted(TARGETS),
        help="Repeatable. Default: all three Linux targets.",
    )
    parser.add_argument(
        "--split",
        action="append",
        choices=SPLITS,
        help="Repeatable. Default: O0 and O2.",
    )
    args = parser.parse_args()

    targets = args.target or list(TARGETS)
    splits = args.split or SPLITS

    for target_name in targets:
        config = TARGETS[target_name]
        for tool in [config["cc"], config["objdump"]]:
            if shutil.which(tool) is None:
                raise SystemExit(
                    f"{target_name}: missing required tool: {tool}"
                )
        if not config["generated"].is_dir():
            raise SystemExit(
                f"{target_name}: missing generated root: {config['generated']}"
            )

    failures = []
    completed = 0

    for target_name in targets:
        config = TARGETS[target_name]
        for split in splits:
            split_root = config["generated"] / split
            if not split_root.is_dir():
                raise SystemExit(
                    f"{target_name} {split}: missing split root: {split_root}"
                )

            task_dirs = sorted(p for p in split_root.iterdir() if p.is_dir())
            if len(task_dirs) != 164:
                raise SystemExit(
                    f"{target_name} {split}: expected 164 task directories, "
                    f"found {len(task_dirs)}"
                )

            print()
            print("=" * 78)
            print(f"{target_name} {split}")
            print("=" * 78)

            for i, task_dir in enumerate(task_dirs, 1):
                print(
                    f"\n===== {target_name} {split}: "
                    f"{task_dir.name} ({i}/164) ====="
                )
                try:
                    build_one(target_name, config, split, task_dir)
                    completed += 1
                except Exception as exc:
                    print(f"FAILED: {exc}")
                    failures.append(
                        (target_name, split, task_dir.name, str(exc))
                    )

    expected = len(targets) * len(splits) * 164

    print()
    print("=" * 78)
    print("HUMANEVAL PIC REFERENCE GENERATION SUMMARY")
    print("=" * 78)
    print(f"Expected instances:  {expected}")
    print(f"Completed instances: {completed}")
    print(f"Failures:             {len(failures)}")

    if failures:
        for target_name, split, task_name, error in failures:
            print(f"  {target_name} {split} {task_name}: {error}")
        raise SystemExit(1)

    if completed != expected:
        raise SystemExit(
            f"Expected {expected} completed instances, got {completed}"
        )

    print("OVERALL: PASS")


if __name__ == "__main__":
    main()
