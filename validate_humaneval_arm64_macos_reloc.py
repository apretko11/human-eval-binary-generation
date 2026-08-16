#!/usr/bin/env python3

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent

OLD = ROOT / "generated_humaneval_arm64_mac"
NEW = ROOT / "generated_humaneval_arm64_mac_reloc"

SPLITS = ["O0", "O2"]
EXPECTED_ROWS = 164

OBJDUMP = ["xcrun", "llvm-objdump"]


def require_file(path):
    if not path.is_file():
        raise RuntimeError(f"MISSING: {path}")

    if path.stat().st_size == 0:
        raise RuntimeError(f"EMPTY: {path}")


def compare_exact(old, new):
    require_file(old)
    require_file(new)

    if old.read_bytes() != new.read_bytes():
        raise RuntimeError(
            "UNEXPECTED BYTE DIFFERENCE:\n"
            f"  old: {old}\n"
            f"  new: {new}"
        )


def fresh_objdump(flags, binary):
    result = subprocess.run(
        [
            *OBJDUMP,
            flags,
            str(binary),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout


def normalize_objdump_path(text):
    """
    Ignore only the input-path difference between the old and
    copied _reloc trees when counting old-vs-new dump changes.
    """

    text = text.replace(
        str(NEW),
        "<GENERATED_ROOT>",
    )

    text = text.replace(
        str(OLD),
        "<GENERATED_ROOT>",
    )

    text = text.replace(
        NEW.name,
        "<GENERATED_ROOT>",
    )

    text = text.replace(
        OLD.name,
        "<GENERATED_ROOT>",
    )

    return text


def main():
    if not OLD.is_dir():
        raise RuntimeError(
            f"Missing old generated directory: {OLD}"
        )

    if not NEW.is_dir():
        raise RuntimeError(
            f"Missing new generated directory: {NEW}"
        )

    grand_total = 0

    print("=" * 72)
    print("arm64_macos HumanEval")
    print("=" * 72)

    for split in SPLITS:
        old_split = OLD / split
        new_split = NEW / split

        old_dirs = sorted(
            p
            for p in old_split.iterdir()
            if p.is_dir()
        )

        new_dirs = sorted(
            p
            for p in new_split.iterdir()
            if p.is_dir()
        )

        if len(old_dirs) != EXPECTED_ROWS:
            raise RuntimeError(
                f"{split}: old expected {EXPECTED_ROWS} task dirs, "
                f"found {len(old_dirs)}"
            )

        if len(new_dirs) != EXPECTED_ROWS:
            raise RuntimeError(
                f"{split}: new expected {EXPECTED_ROWS} task dirs, "
                f"found {len(new_dirs)}"
            )

        old_names = [p.name for p in old_dirs]
        new_names = [p.name for p in new_dirs]

        if old_names != new_names:
            raise RuntimeError(
                f"{split}: old/new task directory names differ"
            )

        changed = {
            "object": 0,
            "dylib": 0,
            "program": 0,
        }

        checked = 0

        for task_name in old_names:
            old = old_split / task_name
            new = new_split / task_name

            # -------------------------------------------------
            # 1. File sets must remain identical.
            # -------------------------------------------------
            old_files = {
                p.relative_to(old)
                for p in old.rglob("*")
                if p.is_file()
            }

            new_files = {
                p.relative_to(new)
                for p in new.rglob("*")
                if p.is_file()
            }

            if old_files != new_files:
                missing = sorted(
                    str(p)
                    for p in old_files - new_files
                )

                extra = sorted(
                    str(p)
                    for p in new_files - old_files
                )

                raise RuntimeError(
                    f"FILE SET DIFFERENCE: {split} {task_name}\n"
                    f"missing: {missing}\n"
                    f"extra: {extra}"
                )

            # -------------------------------------------------
            # 2. Every NON-.objdump artifact must be
            #    byte-for-byte identical.
            #
            # This covers:
            #   source.c
            #   program_source.c
            #   compiler.s
            #   code.o
            #   code.pic.o
            #   code.dylib
            #   code.program
            # -------------------------------------------------
            for relative in sorted(
                old_files,
                key=str,
            ):
                if relative.name.endswith(".objdump"):
                    continue

                compare_exact(
                    old / relative,
                    new / relative,
                )

            obj = new / "code.o"
            dylib = new / "code.dylib"
            program = new / "code.program"

            obj_dump = new / "code.o.objdump"
            dylib_dump = new / "code.dylib.objdump"
            program_dump = new / "code.program.objdump"

            for path in [
                obj,
                dylib,
                program,
                obj_dump,
                dylib_dump,
                program_dump,
            ]:
                require_file(path)

            # -------------------------------------------------
            # 3. Saved new dumps must exactly reproduce the
            #    intended objdump commands.
            # -------------------------------------------------
            expected_obj = fresh_objdump(
                "-dr",
                obj,
            )

            expected_dylib = fresh_objdump(
                "-drR",
                dylib,
            )

            expected_program = fresh_objdump(
                "-drR",
                program,
            )

            actual_obj = obj_dump.read_text(
                errors="replace"
            )

            actual_dylib = dylib_dump.read_text(
                errors="replace"
            )

            actual_program = program_dump.read_text(
                errors="replace"
            )

            if actual_obj != expected_obj:
                raise RuntimeError(
                    f"OBJECT DUMP MISMATCH: "
                    f"{split} {task_name}"
                )

            if actual_dylib != expected_dylib:
                raise RuntimeError(
                    f"DYLIB DUMP MISMATCH: "
                    f"{split} {task_name}"
                )

            if actual_program != expected_program:
                raise RuntimeError(
                    f"PROGRAM DUMP MISMATCH: "
                    f"{split} {task_name}"
                )

            # -------------------------------------------------
            # 4. Verify architecture/file-format text.
            # -------------------------------------------------
            for label, text in [
                ("object", actual_obj),
                ("dylib", actual_dylib),
                ("program", actual_program),
            ]:
                if "mach-o arm64" not in text:
                    raise RuntimeError(
                        f"WRONG FORMAT: "
                        f"{split} {task_name} {label}"
                    )

            # -------------------------------------------------
            # 5. Informational old-vs-new dump change counts.
            #    Normalize only the copied-tree path.
            # -------------------------------------------------
            old_obj = normalize_objdump_path(
                (old / "code.o.objdump").read_text(
                    errors="replace"
                )
            )

            old_dylib = normalize_objdump_path(
                (old / "code.dylib.objdump").read_text(
                    errors="replace"
                )
            )

            old_program = normalize_objdump_path(
                (old / "code.program.objdump").read_text(
                    errors="replace"
                )
            )

            new_obj = normalize_objdump_path(
                actual_obj
            )

            new_dylib = normalize_objdump_path(
                actual_dylib
            )

            new_program = normalize_objdump_path(
                actual_program
            )

            if old_obj != new_obj:
                changed["object"] += 1

            if old_dylib != new_dylib:
                changed["dylib"] += 1

            if old_program != new_program:
                changed["program"] += 1

            checked += 1
            grand_total += 1

        print(
            f"{split}: PASS — "
            f"{checked}/{EXPECTED_ROWS} tasks\n"
            f"    object dumps changed:  "
            f"{changed['object']}/{EXPECTED_ROWS}\n"
            f"    dylib dumps changed:   "
            f"{changed['dylib']}/{EXPECTED_ROWS}\n"
            f"    program dumps changed: "
            f"{changed['program']}/{EXPECTED_ROWS}"
        )

    print()
    print("=" * 72)
    print("BOTH HUMANEVAL MACOS DATASETS PASS")
    print(
        f"Validated task/split instances: "
        f"{grand_total}"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
