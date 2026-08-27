#!/usr/bin/env python3

import csv
import hashlib
from pathlib import Path


DATASETS = {
    "bringup": {
        "base": Path("BuB/bringup-bench"),
        "expected": 648,
    },
    "humaneval": {
        "base": Path("HE/human-eval-binary-generation"),
        "expected": 984,
    },
    "mceval": {
        "base": Path("McE/mceval-binary-generation"),
        "expected": 300,
    },
}


DISASM_HEADER = (
    "================================================================\n"
    "DISASSEMBLY + RELOCATIONS\n"
    "================================================================\n\n"
)

RODATA_HEADER = (
    "\n================================================================\n"
    "SECTION CONTENTS: .rodata\n"
    "================================================================\n\n"
)


def sha256_file(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


errors = []
grand_total = 0


for benchmark, spec in DATASETS.items():
    base = spec["base"]
    expected = spec["expected"]

    output_root = (
        base / "program_asm_v2_full"
    )

    manifest = (
        output_root / "manifest.tsv"
    )

    files = sorted(
        output_root.rglob(
            "*.program_asm_v2.txt"
        )
    )

    if len(files) != expected:
        errors.append(
            f"{benchmark}: expected "
            f"{expected} v2 files, "
            f"found {len(files)}"
        )

    with manifest.open() as f:
        rows = list(
            csv.DictReader(
                f,
                delimiter="\t",
            )
        )

    if len(rows) != expected:
        errors.append(
            f"{benchmark}: expected "
            f"{expected} manifest rows, "
            f"found {len(rows)}"
        )

    for row in rows:
        program = base / row["binary"]
        output = base / row["output"]

        old_objdump = Path(
            str(program) + ".objdump"
        )

        if not program.exists():
            errors.append(
                f"{benchmark}: missing binary: "
                f"{program}"
            )
            continue

        if not old_objdump.exists():
            errors.append(
                f"{benchmark}: missing old "
                f"objdump: {old_objdump}"
            )
            continue

        if not output.exists():
            errors.append(
                f"{benchmark}: missing v2: "
                f"{output}"
            )
            continue

        text = output.read_text(
            errors="replace"
        )

        if not text.strip():
            errors.append(
                f"{benchmark}: empty v2: "
                f"{output}"
            )
            continue

        # Required major blocks.
        for required in [
            "SEMANTIC SECTION LAYOUT",
            "DISASSEMBLY + RELOCATIONS",
            "SECTION CONTENTS: .rodata",
            "SECTION CONTENTS: .data",
            "SEMANTIC DATA SYMBOLS",
        ]:
            if required not in text:
                errors.append(
                    f"{benchmark}: "
                    f"{output}: missing "
                    f"{required}"
                )

        # .bss must not be raw-dumped.
        if "SECTION CONTENTS: .bss" in text:
            errors.append(
                f"{benchmark}: "
                f"{output}: raw .bss dump "
                f"should not exist"
            )

        # Old validated objdump must be embedded
        # verbatim.
        try:
            start = (
                text.index(DISASM_HEADER)
                + len(DISASM_HEADER)
            )

            end = text.index(
                RODATA_HEADER,
                start,
            )

            embedded_disasm = text[
                start:end
            ]

            old_disasm = (
                old_objdump.read_text(
                    errors="replace"
                )
            )

            if embedded_disasm != old_disasm:
                errors.append(
                    f"{benchmark}: "
                    f"{output}: embedded "
                    f"program_asm differs "
                    f"from old validated "
                    f"objdump"
                )

        except ValueError:
            errors.append(
                f"{benchmark}: "
                f"{output}: could not parse "
                f"disassembly block"
            )

        # Conditional .data.rel.ro policy.
        listed_sections = set(
            row["semantic_sections"].split(",")
        )

        has_relro = (
            ".data.rel.ro"
            in listed_sections
        )

        text_has_relro_contents = (
            "SECTION CONTENTS: .data.rel.ro"
            in text
        )

        if (
            has_relro
            != text_has_relro_contents
        ):
            errors.append(
                f"{benchmark}: "
                f"{output}: .data.rel.ro "
                f"manifest/content mismatch"
            )

        # Recheck binary hash.
        current_hash = sha256_file(
            program
        )

        if (
            current_hash
            != row["binary_sha256"]
        ):
            errors.append(
                f"{benchmark}: "
                f"{program}: binary SHA-256 "
                f"changed"
            )

    grand_total += len(rows)

    print(
        f"{benchmark:10s}: "
        f"{len(rows)} rows checked"
    )


print()
print(
    "========================================"
)
print("VALIDATION SUMMARY")
print(
    "========================================"
)
print(
    f"Total rows checked: {grand_total}"
)
print(
    f"Errors: {len(errors)}"
)

if errors:
    print()

    for error in errors[:100]:
        print(
            f"ERROR: {error}"
        )

    raise SystemExit(1)

print()
print(
    "PASS: all Linux program_asm_v2 "
    "artifacts validated"
)
