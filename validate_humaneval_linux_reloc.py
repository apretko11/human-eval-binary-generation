#!/usr/bin/env python3

import re
import subprocess
from pathlib import Path

from datasets import load_dataset


ROOT = Path(__file__).resolve().parent
OLD_ROOT = ROOT.parent / "HumanEval"

DATASET_ID = "murodbek/humaneval_asm"
SPLITS = ["O0", "O2"]

TARGETS = {
    "x86_linux": {
        "old": OLD_ROOT / "generated_humaneval_x86_linux",
        "new": ROOT / "generated_humaneval_x86_linux_reloc",
        "objdump": "objdump",
        "format": "elf64-x86-64",
    },

    "arm_linux": {
        "old": OLD_ROOT / "generated_humaneval_arm64_linux",
        "new": ROOT / "generated_humaneval_arm64_linux_reloc",
        "objdump": "aarch64-linux-gnu-objdump",
        "format": "elf64-littleaarch64",
    },

    "riscv_linux": {
        "old": OLD_ROOT / "generated_humaneval_riscv64_linux",
        "new": ROOT / "generated_humaneval_riscv64_linux_reloc",
        "objdump": "riscv64-linux-gnu-objdump",
        "format": "elf64-littleriscv",
    },
}


def safe_name(task_name):
    name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        task_name,
    ).strip("_")

    return name or "task"


def require_file(path):
    if not path.is_file():
        raise RuntimeError(f"MISSING: {path}")

    if path.stat().st_size == 0:
        raise RuntimeError(f"EMPTY: {path}")


def fresh_objdump(objdump, flags, binary):
    result = subprocess.run(
        [objdump, flags, str(binary)],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout


def normalize_objdump_header(text):
    """
    Ignore only objdump's filename/file-format header line.

    Old and new files live in different directories, so that header
    naturally differs even when the disassembly is identical.
    """

    return "\n".join(
        line
        for line in text.splitlines()
        if "file format" not in line
    )


def normalize_asm_paths(text, old_dir, new_dir):
    """
    Normalize only build-directory paths in compiler-generated .s.

    This protects against harmless absolute-path differences if the
    compiler records the source location.
    """

    text = text.replace(str(old_dir), "<TASK_DIR>")
    text = text.replace(str(new_dir), "<TASK_DIR>")

    text = text.replace(str(OLD_ROOT), "<ROOT>")
    text = text.replace(str(ROOT), "<ROOT>")

    return text


def compare_compiler_asm(old_file, new_file, old_dir, new_dir):
    require_file(old_file)
    require_file(new_file)

    old_text = old_file.read_text(errors="replace")
    new_text = new_file.read_text(errors="replace")

    old_text = normalize_asm_paths(
        old_text,
        old_dir,
        new_dir,
    )

    new_text = normalize_asm_paths(
        new_text,
        old_dir,
        new_dir,
    )

    if old_text != new_text:
        raise RuntimeError(
            "UNEXPECTED COMPILER ASM DIFFERENCE:\n"
            f"  old: {old_file}\n"
            f"  new: {new_file}"
        )


def compare_disassembly(objdump, old_binary, new_binary):
    """
    Compare executable/code disassembly rather than raw binary bytes.

    This ensures regeneration did not alter the machine-code
    representation while avoiding irrelevant binary metadata.
    """

    require_file(old_binary)
    require_file(new_binary)

    old_text = fresh_objdump(
        objdump,
        "-d",
        old_binary,
    )

    new_text = fresh_objdump(
        objdump,
        "-d",
        new_binary,
    )

    old_text = normalize_objdump_header(old_text)
    new_text = normalize_objdump_header(new_text)

    if old_text != new_text:
        raise RuntimeError(
            "UNEXPECTED DISASSEMBLY DIFFERENCE:\n"
            f"  old: {old_binary}\n"
            f"  new: {new_binary}"
        )


def main():
    print("Loading HumanEval...")

    ds = load_dataset(DATASET_ID)

    if set(ds.keys()) != {"O0", "O2"}:
        raise RuntimeError(
            f"Unexpected splits: {list(ds.keys())}"
        )

    if len(ds["O0"]) != 164:
        raise RuntimeError(
            f"Expected 164 O0 rows, found {len(ds['O0'])}"
        )

    if len(ds["O2"]) != 164:
        raise RuntimeError(
            f"Expected 164 O2 rows, found {len(ds['O2'])}"
        )

    #
    # O0/O2 must represent exactly the same HumanEval programs.
    #
    for i in range(164):
        if (
            ds["O0"][i]["task_name"]
            != ds["O2"][i]["task_name"]
        ):
            raise RuntimeError(
                f"O0/O2 task mismatch at row {i}"
            )

        if (
            ds["O0"][i]["source_code"]
            != ds["O2"][i]["source_code"]
        ):
            raise RuntimeError(
                f"O0/O2 source mismatch at row {i}"
            )

    print("HumanEval source alignment: PASS")
    print("164 rows in O0")
    print("164 rows in O2")

    grand_total = 0

    for target_name, config in TARGETS.items():
        print()
        print("=" * 78)
        print(target_name)
        print("=" * 78)

        if not config["old"].is_dir():
            raise RuntimeError(
                f"Missing old generated root: {config['old']}"
            )

        if not config["new"].is_dir():
            raise RuntimeError(
                f"Missing new generated root: {config['new']}"
            )

        for split in SPLITS:
            checked = 0

            dumps_changed = {
                "object": 0,
                "shared": 0,
                "program": 0,
            }

            #
            # Check that the split contains exactly the expected
            # 164 HumanEval task directories.
            #
            expected_dirs = {
                f"{index:03d}_{safe_name(row['task_name'])}"
                for index, row in enumerate(ds[split])
            }

            actual_dirs = {
                path.name
                for path in (config["new"] / split).iterdir()
                if path.is_dir()
            }

            if actual_dirs != expected_dirs:
                missing = sorted(expected_dirs - actual_dirs)
                extra = sorted(actual_dirs - expected_dirs)

                raise RuntimeError(
                    f"{target_name} {split}: "
                    "task-directory mismatch\n"
                    f"missing: {missing}\n"
                    f"extra: {extra}"
                )

            for index, row in enumerate(ds[split]):
                task_name = row["task_name"]
                source = row["source_code"]

                dirname = (
                    f"{index:03d}_"
                    f"{safe_name(task_name)}"
                )

                old = (
                    config["old"]
                    / split
                    / dirname
                )

                new = (
                    config["new"]
                    / split
                    / dirname
                )

                if not old.is_dir():
                    raise RuntimeError(
                        f"MISSING OLD TASK DIR: {old}"
                    )

                if not new.is_dir():
                    raise RuntimeError(
                        f"MISSING NEW TASK DIR: {new}"
                    )

                # -------------------------------------------------
                # 1. Verify exact source files.
                # -------------------------------------------------
                source_c = new / "source.c"
                program_c = new / "program_source.c"

                require_file(source_c)
                require_file(program_c)

                actual_source = source_c.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                if actual_source != source:
                    raise RuntimeError(
                        f"SOURCE MISMATCH: "
                        f"{target_name} {split} "
                        f"{index} {task_name}"
                    )

                expected_program = (
                    source.rstrip()
                    + "\n\n"
                    + "int main(void)\n"
                    + "{\n"
                    + "    return 0;\n"
                    + "}\n"
                )

                actual_program_source = (
                    program_c.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                )

                if actual_program_source != expected_program:
                    raise RuntimeError(
                        f"PROGRAM SOURCE MISMATCH: "
                        f"{target_name} {split} "
                        f"{index} {task_name}"
                    )

                # -------------------------------------------------
                # 2. Compiler-generated assembly should be the same
                #    except for possible build-directory paths.
                # -------------------------------------------------
                compare_compiler_asm(
                    old / "compiler.s",
                    new / "compiler.s",
                    old,
                    new,
                )

                # -------------------------------------------------
                # 3. Verify all expected binary artifacts exist.
                # -------------------------------------------------
                required_new = [
                    new / "code.o",
                    new / "code.pic.o",
                    new / "code.so",
                    new / "code.program",
                    new / "code.o.objdump",
                    new / "code.so.objdump",
                    new / "code.program.objdump",
                ]

                for path in required_new:
                    require_file(path)

                # -------------------------------------------------
                # 4. Machine-code disassembly must be unchanged from
                #    the original generation.
                # -------------------------------------------------
                compare_disassembly(
                    config["objdump"],
                    old / "code.o",
                    new / "code.o",
                )

                compare_disassembly(
                    config["objdump"],
                    old / "code.so",
                    new / "code.so",
                )

                compare_disassembly(
                    config["objdump"],
                    old / "code.program",
                    new / "code.program",
                )

                # -------------------------------------------------
                # 5. New saved objdump files must EXACTLY equal the
                #    intended relocation-preserving commands.
                # -------------------------------------------------
                expected_obj = fresh_objdump(
                    config["objdump"],
                    "-dr",
                    new / "code.o",
                )

                expected_so = fresh_objdump(
                    config["objdump"],
                    "-drR",
                    new / "code.so",
                )

                expected_program_dump = fresh_objdump(
                    config["objdump"],
                    "-drR",
                    new / "code.program",
                )

                actual_obj = (
                    new / "code.o.objdump"
                ).read_text(errors="replace")

                actual_so = (
                    new / "code.so.objdump"
                ).read_text(errors="replace")

                actual_program_dump = (
                    new / "code.program.objdump"
                ).read_text(errors="replace")

                if actual_obj != expected_obj:
                    raise RuntimeError(
                        f"OBJECT DUMP MISMATCH: "
                        f"{target_name} {split} "
                        f"{index} {task_name}"
                    )

                if actual_so != expected_so:
                    raise RuntimeError(
                        f"SHARED DUMP MISMATCH: "
                        f"{target_name} {split} "
                        f"{index} {task_name}"
                    )

                if (
                    actual_program_dump
                    != expected_program_dump
                ):
                    raise RuntimeError(
                        f"PROGRAM DUMP MISMATCH: "
                        f"{target_name} {split} "
                        f"{index} {task_name}"
                    )

                # -------------------------------------------------
                # 6. Correct ISA / ELF format.
                # -------------------------------------------------
                fmt = config["format"]

                for label, text in [
                    ("object", actual_obj),
                    ("shared", actual_so),
                    ("program", actual_program_dump),
                ]:
                    if fmt not in text:
                        raise RuntimeError(
                            f"WRONG FORMAT: "
                            f"{target_name} {split} "
                            f"{index} {task_name} "
                            f"{label}; expected {fmt}"
                        )

                # -------------------------------------------------
                # 7. Count which textual dumps actually changed.
                #    Informational only.
                # -------------------------------------------------
                old_obj_dump = old / "code.o.objdump"
                old_so_dump = old / "code.so.objdump"
                old_program_dump = (
                    old / "code.program.objdump"
                )

                require_file(old_obj_dump)
                require_file(old_so_dump)
                require_file(old_program_dump)

                old_obj_text = normalize_objdump_header(
                    old_obj_dump.read_text(
                        errors="replace"
                    )
                )

                old_so_text = normalize_objdump_header(
                    old_so_dump.read_text(
                        errors="replace"
                    )
                )

                old_program_text = normalize_objdump_header(
                    old_program_dump.read_text(
                        errors="replace"
                    )
                )

                new_obj_text = normalize_objdump_header(
                    actual_obj
                )

                new_so_text = normalize_objdump_header(
                    actual_so
                )

                new_program_text = normalize_objdump_header(
                    actual_program_dump
                )

                if old_obj_text != new_obj_text:
                    dumps_changed["object"] += 1

                if old_so_text != new_so_text:
                    dumps_changed["shared"] += 1

                if old_program_text != new_program_text:
                    dumps_changed["program"] += 1

                checked += 1
                grand_total += 1

            print(
                f"{split}: PASS — "
                f"{checked}/164 rows\n"
                f"    object dumps changed:  "
                f"{dumps_changed['object']}/164\n"
                f"    shared dumps changed:  "
                f"{dumps_changed['shared']}/164\n"
                f"    program dumps changed: "
                f"{dumps_changed['program']}/164"
            )

    print()
    print("=" * 78)
    print("ALL SIX HUMANEVAL LINUX DATASETS PASS")
    print(
        "Validated target/split rows: "
        f"{grand_total}"
    )
    print("=" * 78)


if __name__ == "__main__":
    main()
