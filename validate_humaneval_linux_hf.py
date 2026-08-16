#!/usr/bin/env python3

from datasets import load_dataset

from upload_humaneval_linux_hf_reloc import (
    TARGETS,
    SPLITS,
    EXPECTED_COLUMNS,
    build_split,
)


def main():
    total = 0

    for target_name, config in TARGETS.items():
        repo_id = config["repo_id"]

        print()
        print("=" * 78)
        print(f"VERIFYING {target_name}")
        print(f"HF repo: {repo_id}")
        print("=" * 78)

        remote = load_dataset(repo_id)

        if set(remote.keys()) != {"O0", "O2"}:
            raise RuntimeError(
                f"{repo_id}: unexpected splits: {list(remote.keys())}"
            )

        for split in SPLITS:
            #
            # Reconstruct exactly what we uploaded locally.
            #
            local = build_split(
                config["generated"],
                split,
            )

            hf = remote[split]

            if local.num_rows != 164:
                raise RuntimeError(
                    f"{target_name} {split}: "
                    f"local expected 164 rows, "
                    f"found {local.num_rows}"
                )

            if hf.num_rows != 164:
                raise RuntimeError(
                    f"{repo_id} {split}: "
                    f"HF expected 164 rows, "
                    f"found {hf.num_rows}"
                )

            if hf.column_names != EXPECTED_COLUMNS:
                raise RuntimeError(
                    f"{repo_id} {split}: wrong columns\n"
                    f"expected: {EXPECTED_COLUMNS}\n"
                    f"actual:   {hf.column_names}"
                )

            #
            # Exact row-by-row, field-by-field comparison.
            #
            for i in range(164):
                local_row = local[i]
                hf_row = hf[i]

                for column in EXPECTED_COLUMNS:
                    if not hf_row[column]:
                        raise RuntimeError(
                            f"{repo_id} {split}: EMPTY FIELD\n"
                            f"row: {i}\n"
                            f"task: {local_row['task_name']}\n"
                            f"column: {column}"
                        )

                    if local_row[column] != hf_row[column]:
                        raise RuntimeError(
                            f"{repo_id} {split}: MISMATCH\n"
                            f"row: {i}\n"
                            f"task: {local_row['task_name']}\n"
                            f"column: {column}"
                        )

            print(
                f"{split}: PASS — "
                f"164/164 rows exactly match local"
            )

            total += 164

    print()
    print("=" * 78)
    print("ALL SIX HUMANEVAL HUGGING FACE DATASETS PASS")
    print(f"Exact rows verified: {total}")
    print("=" * 78)


if __name__ == "__main__":
    main()
