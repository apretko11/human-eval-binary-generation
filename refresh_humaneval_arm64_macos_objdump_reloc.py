#!/usr/bin/env python3

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated_humaneval_arm64_mac_reloc"

SPLITS = ["O0", "O2"]
EXPECTED_ROWS = 164

OBJDUMP = ["xcrun", "llvm-objdump"]


def run_objdump(flags, binary, output):
    print("+", *OBJDUMP, flags, binary, ">", output)

    with output.open("w", encoding="utf-8") as f:
        subprocess.run(
            [*OBJDUMP, flags, str(binary)],
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )


def main():
    if not GENERATED.is_dir():
        raise RuntimeError(
            f"Missing copied output directory: {GENERATED}"
        )

    total = 0

    for split in SPLITS:
        split_dir = GENERATED / split

        task_dirs = sorted(
            p
            for p in split_dir.iterdir()
            if p.is_dir()
        )

        if len(task_dirs) != EXPECTED_ROWS:
            raise RuntimeError(
                f"{split}: expected {EXPECTED_ROWS} task directories, "
                f"found {len(task_dirs)}"
            )

        print()
        print("=" * 72)
        print(split)
        print("=" * 72)

        for task_dir in task_dirs:
            obj = task_dir / "code.o"
            dylib = task_dir / "code.dylib"
            program = task_dir / "code.program"

            for path in [obj, dylib, program]:
                if not path.is_file():
                    raise RuntimeError(
                        f"Missing binary: {path}"
                    )

            run_objdump(
                "-dr",
                obj,
                task_dir / "code.o.objdump",
            )

            run_objdump(
                "-drR",
                dylib,
                task_dir / "code.dylib.objdump",
            )

            run_objdump(
                "-drR",
                program,
                task_dir / "code.program.objdump",
            )

            total += 1

    print()
    print("=" * 72)
    print("RELOCATION-PRESERVING OBJDUMPS COMPLETE")
    print(f"Task/split instances processed: {total}")
    print("=" * 72)


if __name__ == "__main__":
    main()
