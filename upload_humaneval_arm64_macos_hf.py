#!/usr/bin/env python3

import re
from pathlib import Path

from datasets import Dataset, DatasetDict, load_dataset


ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated_humaneval_arm64_mac"

SOURCE_REPO = "murodbek/humaneval_asm"
DEST_REPO = "adpretko/humaneval_arm_mac"

SPLITS = ["O0", "O2"]

EXPECTED_COLUMNS = [
    "task_name",
    "source_code",
    "compiler_asm",
    "object_asm",
    "shared_asm",
    "program_asm",
]


def safe_name(task_name):
    name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        task_name,
    ).strip("_")

    return name or "task"


def read_text(path):
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(errors="replace")

    if not text:
        raise RuntimeError(f"Empty file: {path}")

    return text


def build_split(source_ds, split):
    rows = []

    for index, original_row in enumerate(source_ds[split]):
        task_name = original_row["task_name"]

        task_dir = (
            GENERATED
            / split
            / f"{index:03d}_{safe_name(task_name)}"
        )

        if not task_dir.is_dir():
            raise FileNotFoundError(task_dir)

        source_code = read_text(
            task_dir / "source.c"
        )

        #
        # Make sure the source stored locally is EXACTLY
        # the original HumanEval source.
        #
        if source_code != original_row["source_code"]:
            raise RuntimeError(
                f"{split} {task_name}: source_code mismatch"
            )

        row = {
            "task_name": task_name,
            "source_code": source_code,
            "compiler_asm": read_text(
                task_dir / "compiler.s"
            ),
            "object_asm": read_text(
                task_dir / "code.o.objdump"
            ),
            "shared_asm": read_text(
                task_dir / "code.dylib.objdump"
            ),
            "program_asm": read_text(
                task_dir / "code.program.objdump"
            ),
        }

        rows.append(row)

    return Dataset.from_list(rows)


def validate(ds):
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
                        f"{split} "
                        f"{row['task_name']}: "
                        f"empty {column}"
                    )

        print(f"{split}: PASS")
        print(f"  rows: {d.num_rows}")

    #
    # O0 and O2 must contain exactly the same programs
    # in exactly the same order.
    #
    assert (
        ds["O0"]["task_name"]
        == ds["O2"]["task_name"]
    )

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
            if ds["O0"][i][column] == ds["O2"][i][column]:
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
    print("Loading original HumanEval dataset...")

    source_ds = load_dataset(SOURCE_REPO)

    assert len(source_ds["O0"]) == 164
    assert len(source_ds["O2"]) == 164

    print()
    print("Building O0 dataset...")
    o0 = build_split(source_ds, "O0")

    print("Building O2 dataset...")
    o2 = build_split(source_ds, "O2")

    ds = DatasetDict({
        "O0": o0,
        "O2": o2,
    })

    print()
    print("=" * 72)
    print("VALIDATING")
    print("=" * 72)

    validate(ds)

    print()
    print(ds)

    print()
    print("=" * 72)
    print(f"UPLOADING -> {DEST_REPO}")
    print("=" * 72)

    ds.push_to_hub(DEST_REPO)

    print()
    print("=" * 72)
    print("UPLOAD COMPLETE")
    print("=" * 72)
    print(DEST_REPO)


if __name__ == "__main__":
    main()
