#!/usr/bin/env python3

from datasets import DatasetDict, load_dataset

from upload_humaneval_arm64_macos_hf_reloc import (
    DEST_REPO,
    SOURCE_REPO,
    SPLITS,
    EXPECTED_COLUMNS,
    build_split,
)


EXPECTED_ROWS = 164


def main():
    print("=" * 72)
    print("RECONSTRUCTING LOCAL DATASET")
    print("=" * 72)

    source_ds = load_dataset(SOURCE_REPO)

    if set(source_ds.keys()) != {"O0", "O2"}:
        raise RuntimeError(
            f"Unexpected source splits: {list(source_ds.keys())}"
        )

    local = DatasetDict({
        split: build_split(source_ds, split)
        for split in SPLITS
    })

    print()
    print("=" * 72)
    print("LOADING HUGGING FACE DATASET")
    print(f"-> {DEST_REPO}")
    print("=" * 72)

    remote = load_dataset(DEST_REPO)

    if set(remote.keys()) != {"O0", "O2"}:
        raise RuntimeError(
            f"Unexpected HF splits: {list(remote.keys())}"
        )

    total = 0

    for split in SPLITS:
        local_split = local[split]
        remote_split = remote[split]

        if local_split.num_rows != EXPECTED_ROWS:
            raise RuntimeError(
                f"{split}: local expected {EXPECTED_ROWS} rows, "
                f"found {local_split.num_rows}"
            )

        if remote_split.num_rows != EXPECTED_ROWS:
            raise RuntimeError(
                f"{split}: HF expected {EXPECTED_ROWS} rows, "
                f"found {remote_split.num_rows}"
            )

        if local_split.column_names != EXPECTED_COLUMNS:
            raise RuntimeError(
                f"{split}: wrong local columns\n"
                f"expected: {EXPECTED_COLUMNS}\n"
                f"actual:   {local_split.column_names}"
            )

        if remote_split.column_names != EXPECTED_COLUMNS:
            raise RuntimeError(
                f"{split}: wrong HF columns\n"
                f"expected: {EXPECTED_COLUMNS}\n"
                f"actual:   {remote_split.column_names}"
            )

        for i in range(EXPECTED_ROWS):
            local_row = local_split[i]
            remote_row = remote_split[i]

            for column in EXPECTED_COLUMNS:
                if local_row[column] != remote_row[column]:
                    raise RuntimeError(
                        f"{split}: HF/LOCAL MISMATCH\n"
                        f"row: {i}\n"
                        f"task: {local_row['task_name']}\n"
                        f"column: {column}"
                    )

        print(
            f"{split}: PASS — "
            f"{EXPECTED_ROWS}/{EXPECTED_ROWS} rows exactly match local"
        )

        total += EXPECTED_ROWS

    print()
    print("=" * 72)
    print("BOTH HUMANEVAL MACOS HUGGING FACE DATASETS PASS")
    print(f"Exact rows verified: {total}")
    print("=" * 72)


if __name__ == "__main__":
    main()
