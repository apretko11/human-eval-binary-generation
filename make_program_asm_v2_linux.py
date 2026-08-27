#!/usr/bin/env python3

import csv
import hashlib
import re
import subprocess
from pathlib import Path


ARCHES = {
    "x86": {
        "objdump": "objdump",
        "root": Path("generated_humaneval_x86_linux_reloc"),
    },
    "arm64": {
        "objdump": "aarch64-linux-gnu-objdump",
        "root": Path("generated_humaneval_arm64_linux_reloc"),
    },
    "riscv64": {
        "objdump": "riscv64-linux-gnu-objdump",
        "root": Path("generated_humaneval_riscv64_linux_reloc"),
    },
}

OPTS = ["O0", "O2"]

EXPECTED_TASKS = 164

OUTPUT_ROOT = Path("program_asm_v2_full")

CONTENT_SECTIONS = [
    ".rodata",
    ".data",
    ".data.rel.ro",
]

METADATA_SECTIONS = [
    ".rodata",
    ".data",
    ".data.rel.ro",
    ".bss",
]

REQUIRED_SECTIONS = {
    ".rodata",
    ".data",
    ".bss",
}


def run(cmd):
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def sha256_file(path):
    h = hashlib.sha256()

    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def section_names(objdump, program):
    output = run([
        objdump,
        "-h",
        str(program),
    ])

    result = set()

    for line in output.splitlines():
        parts = line.split()

        if (
            len(parts) >= 2
            and parts[0].isdigit()
        ):
            result.add(parts[1])

    return result


def semantic_section_layout(objdump, program):
    output = run([
        objdump,
        "-h",
        str(program),
    ])

    lines = output.splitlines()
    result = []

    for i, line in enumerate(lines):
        parts = line.split()

        if (
            len(parts) >= 2
            and parts[0].isdigit()
            and parts[1] in METADATA_SECTIONS
        ):
            result.append(line)

            # GNU objdump prints section flags on
            # the following line.
            if i + 1 < len(lines):
                result.append(lines[i + 1])

    return "\n".join(result)


def semantic_symbols(objdump, program):
    output = run([
        objdump,
        "-t",
        str(program),
    ])

    result = []

    pattern = re.compile(
        r"\s("
        + "|".join(
            re.escape(section)
            for section in METADATA_SECTIONS
        )
        + r")\s"
    )

    for line in output.splitlines():
        if pattern.search(line):
            result.append(line)

    return "\n".join(result)


def heading(title):
    return (
        "\n"
        "================================================================\n"
        f"{title}\n"
        "================================================================\n\n"
    )


def build_v2(
    arch,
    opt,
    objdump,
    program,
):
    old_objdump = Path(
        str(program) + ".objdump"
    )

    if not old_objdump.exists():
        raise FileNotFoundError(
            f"Missing existing validated objdump: "
            f"{old_objdump}"
        )

    sections = section_names(
        objdump,
        program,
    )

    missing = (
        REQUIRED_SECTIONS - sections
    )

    if missing:
        raise RuntimeError(
            f"{program}: missing required sections: "
            f"{sorted(missing)}"
        )

    parts = []

    parts.append(
        "PROGRAM_ASM_V2\n"
        f"ARCHITECTURE: {arch}\n"
        f"OPTIMIZATION: {opt}\n"
        f"BINARY: {program}\n"
    )

    parts.append(
        heading(
            "SEMANTIC SECTION LAYOUT"
        )
    )

    parts.append(
        semantic_section_layout(
            objdump,
            program,
        )
    )

    parts.append(
        heading(
            "DISASSEMBLY + RELOCATIONS"
        )
    )

    #
    # Preserve the EXISTING validated program_asm
    # exactly rather than silently replacing it with
    # a newly produced disassembly.
    #
    parts.append(
        old_objdump.read_text(
            errors="replace"
        )
    )

    for section in CONTENT_SECTIONS:
        if section not in sections:
            continue

        parts.append(
            heading(
                f"SECTION CONTENTS: {section}"
            )
        )

        parts.append(
            run([
                objdump,
                "-s",
                "-j",
                section,
                str(program),
            ])
        )

    parts.append(
        heading(
            "SEMANTIC DATA SYMBOLS"
        )
    )

    parts.append(
        semantic_symbols(
            objdump,
            program,
        )
    )

    parts.append("\n")

    return "".join(parts), sections


def main():
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path = (
        OUTPUT_ROOT / "manifest.tsv"
    )

    manifest_rows = []

    total_written = 0

    for arch, spec in ARCHES.items():
        objdump = spec["objdump"]
        input_root = spec["root"]

        for opt in OPTS:
            programs = sorted(
                (input_root / opt).glob(
                    "*/*.program"
                )
            )

            if len(programs) != EXPECTED_TASKS:
                raise RuntimeError(
                    f"{arch} {opt}: expected "
                    f"{EXPECTED_TASKS} programs, "
                    f"found {len(programs)}"
                )

            for program in programs:
                task = program.parent.name

                text, sections = build_v2(
                    arch,
                    opt,
                    objdump,
                    program,
                )

                output_dir = (
                    OUTPUT_ROOT
                    / arch
                    / opt
                    / task
                )

                output_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                output_path = (
                    output_dir
                    / f"{task}.program_asm_v2.txt"
                )

                output_path.write_text(
                    text
                )

                old_objdump = Path(
                    str(program) + ".objdump"
                )

                old_bytes = (
                    old_objdump.stat().st_size
                )

                new_bytes = len(
                    text.encode()
                )

                ratio = (
                    new_bytes / old_bytes
                    if old_bytes
                    else 0.0
                )

                manifest_rows.append({
                    "arch": arch,
                    "opt": opt,
                    "task": task,
                    "binary": str(program),
                    "binary_sha256": sha256_file(
                        program
                    ),
                    "output": str(
                        output_path
                    ),
                    "semantic_sections": ",".join(
                        section
                        for section
                        in METADATA_SECTIONS
                        if section in sections
                    ),
                    "old_program_asm_bytes": old_bytes,
                    "program_asm_v2_bytes": new_bytes,
                    "ratio": f"{ratio:.4f}",
                })

                total_written += 1

            print(
                f"{arch} {opt}: "
                f"{len(programs)} / "
                f"{EXPECTED_TASKS} written"
            )

    with manifest_path.open(
        "w",
        newline="",
    ) as fp:
        fieldnames = [
            "arch",
            "opt",
            "task",
            "binary",
            "binary_sha256",
            "output",
            "semantic_sections",
            "old_program_asm_bytes",
            "program_asm_v2_bytes",
            "ratio",
        ]

        writer = csv.DictWriter(
            fp,
            fieldnames=fieldnames,
            delimiter="\t",
        )

        writer.writeheader()
        writer.writerows(
            manifest_rows
        )

    expected_total = (
        len(ARCHES)
        * len(OPTS)
        * EXPECTED_TASKS
    )

    if total_written != expected_total:
        raise RuntimeError(
            f"Expected {expected_total} outputs, "
            f"wrote {total_written}"
        )

    print()
    print(
        "========================================"
    )
    print("COMPLETE")
    print(
        "========================================"
    )
    print(
        f"Program ASM v2 files: "
        f"{total_written}"
    )
    print(
        f"Manifest: {manifest_path}"
    )


if __name__ == "__main__":
    main()
