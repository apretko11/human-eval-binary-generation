#!/usr/bin/env python3
import argparse
from pathlib import Path
from datasets import Dataset, DatasetDict, load_dataset

ROOT = Path(__file__).resolve().parent
GEN = ROOT / "generated_humaneval_arm64_mac_reloc"
REPO = "adpretko/humaneval_arm_mac_reloc"
SPLITS = ("O0", "O2")
N = 164

OLD = [
    "task_name",
    "source_code",
    "compiler_asm",
    "object_asm",
    "shared_asm",
    "program_asm",
]
FINAL = OLD + ["compiler_pic_asm", "pic_object_asm"]

FILES = {
    "source_code": "source.c",
    "compiler_asm": "compiler.s",
    "object_asm": "code.o.objdump",
    "shared_asm": "code.dylib.objdump",
    "program_asm": "code.program.objdump",
    "compiler_pic_asm": "compiler.pic.s",
    "pic_object_asm": "code.pic.o.objdump",
}

def read_nonempty(path):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(f"Missing file: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text:
        raise RuntimeError(f"Empty file: {path}")
    return text

def local_index(split):
    root = GEN / split
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    if len(dirs) != N:
        raise RuntimeError(f"{split}: expected {N} task dirs, found {len(dirs)}")

    out = {}
    for d in dirs:
        if "_" not in d.name:
            raise RuntimeError(f"Unexpected task dir: {d}")
        task = d.name.split("_", 1)[1]
        if task in out:
            raise RuntimeError(f"Duplicate task {task} in {split}")
        for filename in FILES.values():
            read_nonempty(d / filename)
        out[task] = d
    return out

def enrich(split, live):
    if live.num_rows != N:
        raise RuntimeError(f"{split}: expected {N} HF rows, got {live.num_rows}")
    if live.column_names != OLD:
        raise RuntimeError(
            f"{split}: unexpected existing columns\n"
            f"expected={OLD}\nactual={live.column_names}"
        )

    idx = local_index(split)
    hf_names = list(live["task_name"])
    if len(set(hf_names)) != N:
        raise RuntimeError(f"{split}: duplicate task_name in HF dataset")
    if set(hf_names) != set(idx):
        raise RuntimeError(f"{split}: local/HF task sets differ")

    cols = {c: [] for c in FINAL}

    for i, row in enumerate(live):
        task = row["task_name"]
        d = idx[task]

        # Prove the current live six-column row matches the local artifact tree.
        for col in OLD[1:]:
            local_text = read_nonempty(d / FILES[col])
            if row[col] != local_text:
                raise RuntimeError(
                    f"{split} row {i} ({task}): "
                    f"HF {col} != local {FILES[col]}"
                )

        for col in OLD:
            cols[col].append(row[col])

        cols["compiler_pic_asm"].append(
            read_nonempty(d / FILES["compiler_pic_asm"])
        )
        cols["pic_object_asm"].append(
            read_nonempty(d / FILES["pic_object_asm"])
        )

    ds = Dataset.from_dict(cols)
    if ds.column_names != FINAL:
        raise RuntimeError(f"{split}: final column order mismatch")
    if ds.num_rows != N:
        raise RuntimeError(f"{split}: final row count mismatch")
    return ds

def verify_live():
    print("\nReloading live HF dataset...")
    ds = load_dataset(REPO, download_mode="force_redownload")
    for split in SPLITS:
        d = ds[split]
        print(f"{split}: {d.num_rows} rows")
        print(f"{split}: {d.column_names}")
        if d.num_rows != N or d.column_names != FINAL:
            raise RuntimeError(f"{split}: live verification failed")
        if any(not x.strip() for x in d["compiler_pic_asm"]):
            raise RuntimeError(f"{split}: empty compiler_pic_asm")
        if any(not x.strip() for x in d["pic_object_asm"]):
            raise RuntimeError(f"{split}: empty pic_object_asm")
    print("LIVE HF VERIFICATION: PASS")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--verify-live", action="store_true")
    args = ap.parse_args()

    if args.verify_live:
        verify_live()
        return

    if not GEN.is_dir():
        raise SystemExit(f"Missing dataset root: {GEN}")

    print(f"Loading current live dataset: {REPO}")
    live = load_dataset(REPO)

    built = {}
    for split in SPLITS:
        print(f"\n=== {split} ===")
        built[split] = enrich(split, live[split])
        print(f"{split}: {built[split].num_rows} rows")
        print(f"{split}: {built[split].column_names}")
        print(f"{split}: PASS")

    out = DatasetDict(built)
    print("\nLOCAL VALIDATION: PASS")
    print("Final columns:", FINAL)

    if args.validate_only:
        print("No upload performed (--validate-only).")
        return

    print(f"\nUploading to {REPO} ...")
    out.push_to_hub(REPO)
    print("UPLOAD COMPLETE")
    verify_live()

if __name__ == "__main__":
    main()
