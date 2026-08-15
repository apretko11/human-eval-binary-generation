#!/usr/bin/env python3

import subprocess
import tempfile
from pathlib import Path

from datasets import load_dataset


ds = load_dataset("murodbek/humaneval_asm")

failures = []

for split in ["O0", "O2"]:
    opt = "-O0" if split == "O0" else "-O2"

    print()
    print("=" * 70)
    print(split)
    print("=" * 70)

    for i, row in enumerate(ds[split]):
        source = row["source_code"]

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            original_c = tmp / "code.c"
            program_c = tmp / "code_program.c"

            original_c.write_text(source)

            program_c.write_text(
                source
                + "\n\n"
                + "int main(void)\n"
                + "{\n"
                + "    return 0;\n"
                + "}\n"
            )

            commands = {
                "compiler_asm": [
                    "clang",
                    "-arch", "arm64",
                    opt,
                    "-S",
                    str(original_c),
                    "-o", str(tmp / "code.s"),
                ],

                "object": [
                    "clang",
                    "-arch", "arm64",
                    opt,
                    "-c",
                    str(original_c),
                    "-o", str(tmp / "code.o"),
                ],

                "shared": [
                    "clang",
                    "-arch", "arm64",
                    opt,
                    "-fPIC",
                    "-dynamiclib",
                    str(original_c),
                    "-o", str(tmp / "code.dylib"),
                ],

                "program": [
                    "clang",
                    "-arch", "arm64",
                    opt,
                    str(program_c),
                    "-o", str(tmp / "code.program"),
                ],
            }

            ok = True

            for artifact, cmd in commands.items():
                result = subprocess.run(
                    cmd,
                    text=True,
                    capture_output=True,
                )

                if result.returncode != 0:
                    ok = False

                    failures.append({
                        "split": split,
                        "index": i,
                        "artifact": artifact,
                        "stderr": result.stderr,
                    })

                    print(
                        f"FAIL {split} row={i} artifact={artifact}"
                    )

            if ok:
                print(f"PASS {split} row={i}")

print()
print("=" * 70)
print("RESULT")
print("=" * 70)

print("Failures:", len(failures))

for failure in failures:
    print()
    print(
        failure["split"],
        "row",
        failure["index"],
        failure["artifact"],
    )
    print(failure["stderr"])
