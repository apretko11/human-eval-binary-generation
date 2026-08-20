#!/usr/bin/env python3

import argparse
from pathlib import Path

from datasets import Dataset, DatasetDict


ROOT = Path(__file__).resolve().parent

TARGETS = {
    "x86_linux": {
        "generated": ROOT / "generated_humaneval_x86_linux_reloc",
        "repo_id": "adpretko/humaneval_x86_linux_reloc",
    },
    "arm_linux": {
        "generated": ROOT / "generated_humaneval_arm64_linux_reloc",
        "repo_id": "adpretko/humaneval_arm_linux_reloc",
    },
    "riscv_linux": {
        "generated": ROOT / "generated_humaneval_riscv64_linux_reloc",
        "repo_id": "adpretko/humaneval_riscv_linux_reloc",
    },
}

SPLITS = ["O0", "O2"]

# Keep the existing six columns in the same order and append the two new
# PIC-family reference columns.
EXPECTED_COLUMNS = [
    "task_name",
    "source_code",
    "compiler_asm",
    "object_asm",
    "shared_asm",
    "program_asm",
    "compiler_pic_asm",
    "pic_object_asm",
]


def read_text(path):
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(errors="replace")
    if not text:
        raise RuntimeError(f"Empty file: {path}")

    return text


def task_name_from_dir(task_dir):
    # Example: 000_problem17 -> problem17
    parts = task_dir.name.split("_", 1)

    if len(parts) != 2:
        raise RuntimeError(
            f"Unexpected task directory name: {task_dir.name}"
        )

    return parts[1]


def build_split(generated_root, split):
    split_root = generated_root / split

    task_dirs = sorted(
        p for p in split_root.iterdir()
        if p.is_dir()
    )

    if len(task_dirs) != 164:
        raise RuntimeError(
            f"{generated_root.name} {split}: "
            f"expected 164 task directories, found {len(task_dirs)}"
        )

    rows = []

    for task_dir in task_dirs:
        task_name = task_name_from_dir(task_dir)

        row = {
            "task_name": task_name,
            "source_code": read_text(task_dir / "source.c"),
            "compiler_asm": read_text(task_dir / "compiler.s"),
            "object_asm": read_text(task_dir / "code.o.objdump"),
            "shared_asm": read_text(task_dir / "code.so.objdump"),
            "program_asm": read_text(task_dir / "code.program.objdump"),
            "compiler_pic_asm": read_text(task_dir / "compiler.pic.s"),
            "pic_object_asm": read_text(task_dir / "code.pic.o.objdump"),
        }

        rows.append(row)

    return Dataset.from_list(rows)


def validate(target_name, ds):
    assert set(ds.keys()) == {"O0", "O2"}

    for split in SPLITS:
        d = ds[split]

        assert d.num_rows == 164
        assert d.column_names == EXPECTED_COLUMNS

        names = d["task_name"]
        assert len(names) == 164
        assert len(set(names)) == 164

        for row in d:
            for column in EXPECTED_COLUMNS:
                if not row[column]:
                    raise RuntimeError(
                        f"{target_name} {split} {row['task_name']}: "
                        f"empty {column}"
                    )

        print(f"{target_name} {split}: PASS")
        print(f"  rows: {d.num_rows}")
        print(f"  columns: {d.column_names}")

    # Same task ordering and exact same C sources across O0/O2.
    assert ds["O0"]["task_name"] == ds["O2"]["task_name"]
    assert ds["O0"]["source_code"] == ds["O2"]["source_code"]

    print(f"{target_name} O0/O2 task ordering: PASS")
    print(f"{target_name} O0/O2 source_code identity: PASS")

    # Optimization sanity check, including the two new PIC columns.
    for column in [
        "compiler_asm",
        "object_asm",
        "shared_asm",
        "program_asm",
        "compiler_pic_asm",
        "pic_object_asm",
    ]:
        identical = []

        for i in range(164):
            if ds["O0"][i][column] == ds["O2"][i][column]:
                identical.append(ds["O0"][i]["task_name"])

        print(
            f"{target_name} {column}: "
            f"{164 - len(identical)} differ, {len(identical)} identical"
        )

        if identical:
            print("  identical:", ", ".join(identical))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        action="append",
        choices=sorted(TARGETS),
        help=(
            "Target to build/upload. May be repeated. "
            "Default: all three Linux targets."
        ),
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Build and validate locally but do not push to Hugging Face.",
    )
    args = parser.parse_args()

    selected_targets = args.target or list(TARGETS)
    datasets_to_upload = {}

    # Build and validate all selected datasets before uploading anything.
    for target_name in selected_targets:
        config = TARGETS[target_name]

        print()
        print("=" * 78)
        print(f"BUILDING DATASET: {target_name}")
        print("=" * 78)

        ds = DatasetDict({
            "O0": build_split(config["generated"], "O0"),
            "O2": build_split(config["generated"], "O2"),
        })

        validate(target_name, ds)
        print()
        print(ds)

        datasets_to_upload[target_name] = ds

    print()
    print("=" * 78)
    print("ALL SELECTED LOCAL DATASETS VALIDATED")
    print("=" * 78)

    if args.validate_only:
        print("VALIDATE-ONLY requested: nothing uploaded.")
        return

    for target_name in selected_targets:
        config = TARGETS[target_name]
        repo_id = config["repo_id"]
        ds = datasets_to_upload[target_name]

        print()
        print("=" * 78)
        print(f"UPLOADING {target_name}")
        print(f"-> {repo_id}")
        print("=" * 78)

        ds.push_to_hub(repo_id)
        print(f"UPLOAD COMPLETE: {repo_id}")

    print()
    print("=" * 78)
    print("ALL SELECTED UPLOADS COMPLETE")
    print("=" * 78)


if __name__ == "__main__":
    main()
