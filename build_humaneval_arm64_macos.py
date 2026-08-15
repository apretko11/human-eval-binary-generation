#!/usr/bin/env python3

import re
import subprocess
from pathlib import Path

from datasets import load_dataset


REPO = Path(__file__).resolve().parent
OUTPUT_ROOT = REPO / "generated_humaneval_arm64_mac"

DATASET_ID = "murodbek/humaneval_asm"
SPLITS = ["O0", "O2"]


def run(cmd, *, stdout_path=None):
    if stdout_path is None:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Command failed:\n"
                + " ".join(map(str, cmd))
                + "\n\nSTDOUT:\n"
                + result.stdout
                + "\n\nSTDERR:\n"
                + result.stderr
            )

        return result

    with stdout_path.open("w", encoding="utf-8") as f:
        result = subprocess.run(
            cmd,
            text=True,
            stdout=f,
            stderr=subprocess.PIPE,
        )

    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(map(str, cmd))
            + "\n\nSTDERR:\n"
            + result.stderr
        )

    return result


def safe_name(task_name):
    name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        task_name,
    ).strip("_")

    return name or "task"


def build_one(row, split, index):
    opt = "-O0" if split == "O0" else "-O2"

    task_name = row["task_name"]
    source = row["source_code"]

    task_dir = (
        OUTPUT_ROOT
        / split
        / f"{index:03d}_{safe_name(task_name)}"
    )

    task_dir.mkdir(parents=True, exist_ok=True)

    source_c = task_dir / "source.c"
    program_c = task_dir / "program_source.c"

    compiler_s = task_dir / "compiler.s"

    object_file = task_dir / "code.o"
    object_disasm = task_dir / "code.o.objdump"

    pic_object = task_dir / "code.pic.o"

    dylib_file = task_dir / "code.dylib"
    dylib_disasm = task_dir / "code.dylib.objdump"

    program_file = task_dir / "code.program"
    program_disasm = task_dir / "code.program.objdump"

    #
    # Preserve the original HumanEval source exactly.
    #
    source_c.write_text(
        source,
        encoding="utf-8",
    )

    #
    # Synthetic main exists ONLY for executable construction.
    #
    program_source = (
        source.rstrip()
        + "\n\n"
        + "int main(void)\n"
        + "{\n"
        + "    return 0;\n"
        + "}\n"
    )

    program_c.write_text(
        program_source,
        encoding="utf-8",
    )

    #
    # 1. Compiler-generated assembly
    #
    run([
        "xcrun",
        "clang",
        "-arch",
        "arm64",
        opt,
        "-S",
        str(source_c),
        "-o",
        str(compiler_s),
    ])

    #
    # 2. Normal relocatable object
    #
    run([
        "xcrun",
        "clang",
        "-arch",
        "arm64",
        opt,
        "-c",
        str(source_c),
        "-o",
        str(object_file),
    ])

    run(
        [
            "xcrun",
            "llvm-objdump",
            "-d",
            str(object_file),
        ],
        stdout_path=object_disasm,
    )

    #
    # 3. PIC object -> dylib
    #
    run([
        "xcrun",
        "clang",
        "-arch",
        "arm64",
        opt,
        "-fPIC",
        "-c",
        str(source_c),
        "-o",
        str(pic_object),
    ])

    run([
        "xcrun",
        "clang",
        "-arch",
        "arm64",
        "-dynamiclib",
        str(pic_object),
        "-o",
        str(dylib_file),
    ])

    run(
        [
            "xcrun",
            "llvm-objdump",
            "-d",
            str(dylib_file),
        ],
        stdout_path=dylib_disasm,
    )

    #
    # 4. Linked executable
    #
    run([
        "xcrun",
        "clang",
        "-arch",
        "arm64",
        opt,
        str(program_c),
        "-o",
        str(program_file),
    ])

    run(
        [
            "xcrun",
            "llvm-objdump",
            "-d",
            str(program_file),
        ],
        stdout_path=program_disasm,
    )

    print(
        f"PASS {split} "
        f"{index:03d}/163 "
        f"{task_name}"
    )


def main():
    ds = load_dataset(DATASET_ID)

    assert set(ds.keys()) == {"O0", "O2"}
    assert len(ds["O0"]) == 164
    assert len(ds["O2"]) == 164

    #
    # Ensure O0/O2 represent the same source programs.
    #
    for i in range(164):
        assert (
            ds["O0"][i]["task_name"]
            == ds["O2"][i]["task_name"]
        )

        assert (
            ds["O0"][i]["source_code"]
            == ds["O2"][i]["source_code"]
        )

    print("HumanEval source alignment: PASS")
    print("164 rows in O0")
    print("164 rows in O2")

    for split in SPLITS:
        print()
        print("=" * 72)
        print(f"BUILDING {split}")
        print("=" * 72)

        for index, row in enumerate(ds[split]):
            build_one(
                row,
                split,
                index,
            )

    print()
    print("=" * 72)
    print("COMPLETE")
    print("=" * 72)
    print(f"Output: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
