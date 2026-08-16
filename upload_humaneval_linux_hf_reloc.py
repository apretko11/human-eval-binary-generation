#!/usr/bin/env python3

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

EXPECTED_COLUMNS = [
    "task_name",
    "source_code",
    "compiler_asm",
    "object_asm",
    "shared_asm",
    "program_asm",
]


def read_text(path):
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(errors="replace")

    if not text:
        raise RuntimeError(f"Empty file: {path}")

    return text


def task_name_from_dir(task_dir):
    #
    # Example:
    #   000_problem17 -> problem17
    #
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
            f"expected 164 task directories, "
            f"found {len(task_dirs)}"
        )

    rows = []

    for task_dir in task_dirs:
        task_name = task_name_from_dir(task_dir)

        row = {
            "task_name": task_name,

            "source_code": read_text(
                task_dir / "source.c"
            ),

            "compiler_asm": read_text(
                task_dir / "compiler.s"
            ),

            "object_asm": read_text(
                task_dir / "code.o.objdump"
            ),

            "shared_asm": read_text(
                task_dir / "code.so.objdump"
            ),

            "program_asm": read_text(
                task_dir / "code.program.objdump"
            ),
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
                        f"{target_name} "
                        f"{split} "
                        f"{row['task_name']}: "
                        f"empty {column}"
                    )

        print(f"{split}: PASS")
        print(f"  rows: {d.num_rows}")

    #
    # Same tasks, same order.
    #
    assert (
        ds["O0"]["task_name"]
        == ds["O2"]["task_name"]
    )

    #
    # Original C source must be identical across optimization levels.
    #
    assert (
        ds["O0"]["source_code"]
        == ds["O2"]["source_code"]
    )

    print("O0/O2 task ordering: PASS")
    print("O0/O2 source_code identity: PASS")

    #
    # Optimization sanity check.
    #
    for column in [
        "compiler_asm",
        "object_asm",
        "shared_asm",
        "program_asm",
    ]:
        identical = []

        for i in range(164):
            if (
                ds["O0"][i][column]
                == ds["O2"][i][column]
            ):
                identical.append(
                    ds["O0"][i]["task_name"]
                )

        print(
            f"{column}: "
            f"{164 - len(identical)} differ, "
            f"{len(identical)} identical"
        )

        if identical:
            print(
                "  identical:",
                ", ".join(identical)
            )


def main():
    datasets_to_upload = {}

    #
    # Build and validate ALL THREE before uploading anything.
    #
    for target_name, config in TARGETS.items():
        print()
        print("=" * 78)
        print(f"BUILDING DATASET: {target_name}")
        print("=" * 78)

        ds = DatasetDict({
            "O0": build_split(
                config["generated"],
                "O0",
            ),
            "O2": build_split(
                config["generated"],
                "O2",
            ),
        })

        validate(
            target_name,
            ds,
        )

        print()
        print(ds)

        datasets_to_upload[target_name] = ds

    print()
    print("=" * 78)
    print("ALL THREE LOCAL DATASETS VALIDATED")
    print("=" * 78)

    #
    # Upload only after all three pass.
    #
    for target_name, config in TARGETS.items():
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
    print("ALL THREE UPLOADS COMPLETE")
    print("=" * 78)


if __name__ == "__main__":
    main()
