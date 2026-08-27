#!/usr/bin/env python3

import argparse
import csv
import re
from pathlib import Path

from datasets import DatasetDict, load_dataset


ROOT = Path(__file__).resolve().parent

CONFIGS = {
    "bringup_x86_linux": {
        "src_repo": "adpretko/bringup_x86_linux_reloc",
        "dst_repo": "adpretko/bringup_x86_linux_reloc_v2",
        "manifest": ROOT / "BuB/bringup-bench/program_asm_v2_full/manifest.tsv",
        "arch": "x86",
        "expected_rows": 108,
    },
    "bringup_arm_linux": {
        "src_repo": "adpretko/bringup_arm_linux_reloc",
        "dst_repo": "adpretko/bringup_arm_linux_reloc_v2",
        "manifest": ROOT / "BuB/bringup-bench/program_asm_v2_full/manifest.tsv",
        "arch": "arm64",
        "expected_rows": 108,
    },
    "bringup_riscv_linux": {
        "src_repo": "adpretko/bringup_riscv_linux_reloc",
        "dst_repo": "adpretko/bringup_riscv_linux_reloc_v2",
        "manifest": ROOT / "BuB/bringup-bench/program_asm_v2_full/manifest.tsv",
        "arch": "riscv64",
        "expected_rows": 108,
    },

    "humaneval_x86_linux": {
        "src_repo": "adpretko/humaneval_x86_linux_reloc",
        "dst_repo": "adpretko/humaneval_x86_linux_reloc_v2",
        "manifest": ROOT / "HE/human-eval-binary-generation/program_asm_v2_full/manifest.tsv",
        "arch": "x86",
        "expected_rows": 164,
    },
    "humaneval_arm_linux": {
        "src_repo": "adpretko/humaneval_arm_linux_reloc",
        "dst_repo": "adpretko/humaneval_arm_linux_reloc_v2",
        "manifest": ROOT / "HE/human-eval-binary-generation/program_asm_v2_full/manifest.tsv",
        "arch": "arm64",
        "expected_rows": 164,
    },
    "humaneval_riscv_linux": {
        "src_repo": "adpretko/humaneval_riscv_linux_reloc",
        "dst_repo": "adpretko/humaneval_riscv_linux_reloc_v2",
        "manifest": ROOT / "HE/human-eval-binary-generation/program_asm_v2_full/manifest.tsv",
        "arch": "riscv64",
        "expected_rows": 164,
    },

    "mceval_x86_linux": {
        "src_repo": "adpretko/mceval_x86_linux_reloc",
        "dst_repo": "adpretko/mceval_x86_linux_reloc_v2",
        "manifest": ROOT / "McE/mceval-binary-generation/program_asm_v2_full/manifest.tsv",
        "arch": "x86",
        "expected_rows": 50,
    },
    "mceval_arm_linux": {
        "src_repo": "adpretko/mceval_arm_linux_reloc",
        "dst_repo": "adpretko/mceval_arm_linux_reloc_v2",
        "manifest": ROOT / "McE/mceval-binary-generation/program_asm_v2_full/manifest.tsv",
        "arch": "arm64",
        "expected_rows": 50,
    },
    "mceval_riscv_linux": {
        "src_repo": "adpretko/mceval_riscv_linux_reloc",
        "dst_repo": "adpretko/mceval_riscv_linux_reloc_v2",
        "manifest": ROOT / "McE/mceval-binary-generation/program_asm_v2_full/manifest.tsv",
        "arch": "riscv64",
        "expected_rows": 50,
    },
}

SPLITS = ["O0", "O2"]

# These should already be present in the current _reloc repos.
REQUIRED_OLD_COLUMNS = {
    "program_asm",
    "compiler_pic_asm",
    "pic_object_asm",
}


def normalize_task_name(name):
    """
    Local HE/MC-Eval directories may have names such as:
        000_problem17
        000_C_1

    while HF may use:
        problem17
        C_1

    Bringup names are unaffected.
    """
    return re.sub(r"^\d+_", "", name)


def load_manifest(config):
    manifest_path = config["manifest"]

    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)

    mapping = {}

    with manifest_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")

        for row in reader:
            if row["arch"] != config["arch"]:
                continue

            opt = row["opt"]
            task = row["task"]

            output_path = manifest_path.parent.parent / Path(row["output"]).relative_to(
                Path(row["output"]).parts[0]
            )

            # More robustly, the manifest output is normally relative
            # to the benchmark-generation directory.
            if not output_path.exists():
                benchmark_root = manifest_path.parent.parent
                candidate = benchmark_root / row["output"]

                if candidate.exists():
                    output_path = candidate

            if not output_path.exists():
                raise FileNotFoundError(
                    f"Could not locate v2 output for {task}: {row['output']}"
                )

            text = output_path.read_text(errors="replace")

            if not text.strip():
                raise RuntimeError(
                    f"Empty program_asm_v2: {output_path}"
                )

            keys = {
                task,
                normalize_task_name(task),
            }

            for key in keys:
                map_key = (opt, key)

                if map_key in mapping:
                    raise RuntimeError(
                        f"Ambiguous manifest task mapping: {map_key}"
                    )

                mapping[map_key] = text

    return mapping


def identifier_column(split):
    columns = split.column_names

    if "problem_name" in columns:
        return "problem_name"

    if "task_name" in columns:
        return "task_name"

    raise RuntimeError(
        f"Could not find problem_name or task_name in columns: {columns}"
    )


def build_updated_dataset(config):
    print(f"Downloading source: {config['src_repo']}")

    old = load_dataset(config["src_repo"])

    if set(old.keys()) != {"O0", "O2"}:
        raise RuntimeError(
            f"{config['src_repo']}: unexpected splits {list(old.keys())}"
        )

    mapping = load_manifest(config)

    new_splits = {}

    for opt in SPLITS:
        old_split = old[opt]

        if old_split.num_rows != config["expected_rows"]:
            raise RuntimeError(
                f"{config['src_repo']} {opt}: expected "
                f"{config['expected_rows']} rows, found "
                f"{old_split.num_rows}"
            )

        old_columns = list(old_split.column_names)

        missing = REQUIRED_OLD_COLUMNS - set(old_columns)

        if missing:
            raise RuntimeError(
                f"{config['src_repo']} {opt}: current HF repo is missing "
                f"expected existing columns: {sorted(missing)}"
            )

        if "program_asm_v2" in old_columns:
            raise RuntimeError(
                f"{config['src_repo']} already contains program_asm_v2"
            )

        id_col = identifier_column(old_split)

        v2_values = []

        for row in old_split:
            task_id = row[id_col]

            key = (opt, task_id)

            if key not in mapping:
                raise RuntimeError(
                    f"{config['src_repo']} {opt}: "
                    f"no local v2 match for {id_col}={task_id!r}"
                )

            v2_values.append(mapping[key])

        if len(v2_values) != old_split.num_rows:
            raise RuntimeError(
                f"{config['src_repo']} {opt}: v2 count mismatch"
            )

        new_split = old_split.add_column(
            "program_asm_v2",
            v2_values,
        )

        # -------------------------------
        # Critical preservation checks
        # -------------------------------

        if new_split.column_names != old_columns + ["program_asm_v2"]:
            raise RuntimeError(
                f"{config['src_repo']} {opt}: unexpected column order\n"
                f"old={old_columns}\n"
                f"new={new_split.column_names}"
            )

        for i in range(old_split.num_rows):
            old_row = old_split[i]
            new_row = new_split[i]

            for column in old_columns:
                if old_row[column] != new_row[column]:
                    raise RuntimeError(
                        f"{config['src_repo']} {opt} row {i}: "
                        f"existing column changed: {column}"
                    )

            if not new_row["program_asm_v2"]:
                raise RuntimeError(
                    f"{config['src_repo']} {opt} row {i}: "
                    f"empty program_asm_v2"
                )

        new_splits[opt] = new_split

        print(
            f"  {opt}: {old_split.num_rows} rows PASS"
        )
        print(
            f"       old columns: {len(old_columns)}"
        )
        print(
            f"       new columns: {len(new_split.column_names)}"
        )

    return old, DatasetDict(new_splits)


def validate_roundtrip(config, old):
    print()
    print(f"Reloading destination: {config['dst_repo']}")

    uploaded = load_dataset(
        config["dst_repo"],
        download_mode="force_redownload",
    )

    if set(uploaded.keys()) != {"O0", "O2"}:
        raise RuntimeError(
            f"{config['dst_repo']}: unexpected splits "
            f"{list(uploaded.keys())}"
        )

    for opt in SPLITS:
        old_split = old[opt]
        new_split = uploaded[opt]

        if new_split.num_rows != old_split.num_rows:
            raise RuntimeError(
                f"{config['dst_repo']} {opt}: row count changed"
            )

        expected_columns = (
            old_split.column_names
            + ["program_asm_v2"]
        )

        if new_split.column_names != expected_columns:
            raise RuntimeError(
                f"{config['dst_repo']} {opt}: "
                f"unexpected columns: {new_split.column_names}"
            )

        for i in range(old_split.num_rows):
            old_row = old_split[i]
            new_row = new_split[i]

            for column in old_split.column_names:
                if old_row[column] != new_row[column]:
                    raise RuntimeError(
                        f"{config['dst_repo']} {opt} row {i}: "
                        f"round-trip changed existing column {column}"
                    )

            if not new_row["program_asm_v2"]:
                raise RuntimeError(
                    f"{config['dst_repo']} {opt} row {i}: "
                    f"empty uploaded program_asm_v2"
                )

        print(
            f"  {opt}: {new_split.num_rows} rows round-trip PASS"
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--target",
        action="append",
        choices=sorted(CONFIGS),
        help=(
            "Dataset target to process. May be repeated. "
            "Default: all nine Linux datasets."
        ),
    )

    parser.add_argument(
        "--push",
        action="store_true",
        help="Push validated datasets to new *_reloc_v2 HF repos.",
    )

    args = parser.parse_args()

    selected = args.target or list(CONFIGS)

    prepared = {}

    # Validate everything selected before any push.
    for target in selected:
        print()
        print("=" * 80)
        print(target)
        print("=" * 80)

        config = CONFIGS[target]
        old, new = build_updated_dataset(config)

        prepared[target] = (old, new)

    print()
    print("=" * 80)
    print("ALL SELECTED LOCAL MERGES VALIDATED")
    print("=" * 80)

    if not args.push:
        print("No upload performed. Add --push to upload.")
        return

    for target in selected:
        config = CONFIGS[target]
        old, new = prepared[target]

        print()
        print("=" * 80)
        print(f"PUSHING {target}")
        print(f"{config['src_repo']}")
        print(f"    -> {config['dst_repo']}")
        print("=" * 80)

        new.push_to_hub(
            config["dst_repo"]
        )

        print("Upload complete.")

        validate_roundtrip(
            config,
            old,
        )

        print(
            f"ROUND-TRIP VALIDATION PASS: "
            f"{config['dst_repo']}"
        )

    print()
    print("=" * 80)
    print("COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
