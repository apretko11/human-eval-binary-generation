#!/usr/bin/env python3

import re
import shutil
import subprocess
from pathlib import Path

from datasets import load_dataset


ROOT = Path(__file__).resolve().parent
DATASET_ID = "murodbek/humaneval_asm"
SPLITS = ["O0", "O2"]

TARGETS = {
    "x86_linux": {
        "cc": "gcc",
        "objdump": "objdump",
        "flags": ["-march=x86-64"],
        "output": ROOT / "generated_humaneval_x86_linux",
    },

    "arm_linux": {
        "cc": "aarch64-linux-gnu-gcc",
        "objdump": "aarch64-linux-gnu-objdump",
        "flags": ["-march=armv8-a"],
        "output": ROOT / "generated_humaneval_arm64_linux",
    },

    "riscv_linux": {
        "cc": "riscv64-linux-gnu-gcc",
        "objdump": "riscv64-linux-gnu-objdump",
        "flags": [
            "-march=rv64gc",
            "-mabi=lp64d",
        ],
        "output": ROOT / "generated_humaneval_riscv64_linux",
    },
}


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

        return

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


def safe_name(task_name):
    name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        task_name,
    ).strip("_")

    return name or "task"


def check_tools():
    print("Checking toolchains...")

    for target_name, config in TARGETS.items():
        cc = shutil.which(config["cc"])
        objdump = shutil.which(config["objdump"])

        if cc is None:
            raise RuntimeError(
                f"{target_name}: missing compiler {config['cc']}"
            )

        if objdump is None:
            raise RuntimeError(
                f"{target_name}: missing objdump {config['objdump']}"
            )

        print(f"{target_name}:")
        print(f"  compiler: {cc}")
        print(f"  objdump:  {objdump}")

    print("Toolchain check: PASS")


def build_one(target_name, config, row, split, index):
    opt = "-O0" if split == "O0" else "-O2"

    task_name = row["task_name"]
    source = row["source_code"]

    task_dir = (
        config["output"]
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

    shared_file = task_dir / "code.so"
    shared_disasm = task_dir / "code.so.objdump"

    program_file = task_dir / "code.program"
    program_disasm = task_dir / "code.program.objdump"

    cc = config["cc"]
    objdump = config["objdump"]
    target_flags = config["flags"]

    #
    # Exact original HumanEval source.
    #
    source_c.write_text(
        source,
        encoding="utf-8",
    )

    #
    # Synthetic main used ONLY for executable construction.
    #
    program_c.write_text(
        source.rstrip()
        + "\n\n"
        + "int main(void)\n"
        + "{\n"
        + "    return 0;\n"
        + "}\n",
        encoding="utf-8",
    )

    #
    # 1. Compiler-generated assembly
    #
    run([
        cc,
        *target_flags,
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
        cc,
        *target_flags,
        opt,
        "-c",
        str(source_c),
        "-o",
        str(object_file),
    ])

    run(
        [
            objdump,
            "-d",
            str(object_file),
        ],
        stdout_path=object_disasm,
    )

    #
    # 3. PIC object -> shared library
    #
    run([
        cc,
        *target_flags,
        opt,
        "-fPIC",
        "-c",
        str(source_c),
        "-o",
        str(pic_object),
    ])

    run([
        cc,
        *target_flags,
        "-shared",
        str(pic_object),
        "-o",
        str(shared_file),
        "-lm",
    ])

    run(
        [
            objdump,
            "-d",
            str(shared_file),
        ],
        stdout_path=shared_disasm,
    )

    #
    # 4. Linked executable
    #
    run([
        cc,
        *target_flags,
        opt,
        str(program_c),
        "-o",
        str(program_file),
        "-lm",
    ])

    run(
        [
            objdump,
            "-d",
            str(program_file),
        ],
        stdout_path=program_disasm,
    )

    print(
        f"PASS {target_name} "
        f"{split} "
        f"{index:03d}/163 "
        f"{task_name}"
    )


def main():
    check_tools()

    print()
    print("Loading HumanEval...")
    ds = load_dataset(DATASET_ID)

    assert set(ds.keys()) == {"O0", "O2"}
    assert len(ds["O0"]) == 164
    assert len(ds["O2"]) == 164

    #
    # Make sure O0/O2 are exactly the same source programs.
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

    #
    # Build one complete architecture at a time.
    #
    for target_name, config in TARGETS.items():
        print()
        print("=" * 78)
        print(f"BUILDING {target_name}")
        print("=" * 78)

        for split in SPLITS:
            print()
            print("-" * 78)
            print(split)
            print("-" * 78)

            for index, row in enumerate(ds[split]):
                build_one(
                    target_name,
                    config,
                    row,
                    split,
                    index,
                )

        print()
        print(f"{target_name}: COMPLETE")

    print()
    print("=" * 78)
    print("ALL THREE LINUX TARGETS COMPLETE")
    print("=" * 78)

    for target_name, config in TARGETS.items():
        print(
            f"{target_name}: {config['output']}"
        )


if __name__ == "__main__":
    main()
