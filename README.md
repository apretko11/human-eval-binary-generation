# HumanEval Binary Generation

This repository contains the scripts used to generate HumanEval binary-derived assembly datasets for:

- x86-64 Linux
- ARM64 Linux
- RISC-V64 Linux
- ARM64 macOS

For each HumanEval task and optimization level (`O0` and `O2`), the datasets contain:

- `task_name` — HumanEval task identifier
- `source_code` — original C source
- `compiler_asm` — compiler-generated assembly from `clang -S`
- `object_asm` — disassembly of the relocatable object file
- `shared_asm` — disassembly of the linked shared library
- `program_asm` — disassembly of the linked executable

There are 164 HumanEval tasks in each optimization split.

The final relocation-preserving datasets use:

- Relocatable objects: `llvm-objdump -dr`
- Linked shared libraries: `llvm-objdump -drR`
- Linked executables: `llvm-objdump -drR`

The relocation flags are important because plain `objdump -d` omits relocation information that is present in relocatable object files.

## Source and executable construction

HumanEval entries contain function-level C source rather than complete standalone programs with their own `main()`.

The original HumanEval source is preserved unchanged for:

- `source_code`
- compiler-generated assembly
- relocatable object construction
- shared-library construction

A synthetic `main()` is appended only to a temporary executable source file so that a linked executable can be produced.

The synthetic entry point is:

    int main(void)
    {
        return 0;
    }

It is used only to make executable construction possible. It does not execute or test the HumanEval function.

## Linux

### `build_humaneval_linux.py`

Original Linux generation script.

It compiles the HumanEval source for the supported Linux targets and generates:

- compiler assembly;
- relocatable objects;
- shared libraries;
- linked executables;
- binary-derived disassembly.

The original binary disassembly used plain `-d`.

### `build_humaneval_linux_reloc.py`

Relocation-preserving Linux generation script.

It generates corrected Linux outputs using:

- `.o` -> `objdump -dr`
- shared library -> `objdump -drR`
- executable -> `objdump -drR`

The corrected outputs are stored separately from the original generated datasets.

### `validate_humaneval_linux_reloc.py`

Validates the locally generated relocation-preserving Linux datasets.

The validation checks that:

- all 164 tasks are present in both `O0` and `O2`;
- task names and source code are preserved;
- compiler-generated assembly is consistent with the original generation;
- the underlying instruction disassembly has not unexpectedly changed;
- saved objdump output exactly matches fresh `-dr` / `-drR` invocations;
- generated binaries have the expected target formats.

### `upload_humaneval_linux_hf.py`

Uploads the original Linux HumanEval datasets to Hugging Face.

### `upload_humaneval_linux_hf_reloc.py`

Builds Hugging Face `DatasetDict` objects from the relocation-preserving Linux outputs and uploads the corrected datasets.

### `validate_humaneval_linux_hf.py`

Loads the uploaded relocation-preserving Linux datasets back from Hugging Face and verifies that every uploaded row and field exactly matches the corresponding local dataset.

## ARM64 macOS

### `build_humaneval_arm64_macos.py`

Original ARM64 macOS generation script.

For each HumanEval task it produces:

- `source.c`
- `program_source.c`
- `compiler.s`
- `code.o`
- `code.o.objdump`
- `code.pic.o`
- `code.dylib`
- `code.dylib.objdump`
- `code.program`
- `code.program.objdump`

`source.c` contains the original HumanEval source exactly.

`program_source.c` contains the same source plus the synthetic `main()` used only for executable linking.

### `probe_humaneval_macos.py`

Auxiliary probe script for the HumanEval macOS generation workflow.

It is kept alongside the generation scripts as a utility for checking the macOS setup before or during dataset-generation work.

### Why macOS uses a refresh workflow

The corrected macOS dataset is intentionally not rebuilt into a differently named output directory.

Mach-O dynamic libraries contain an `LC_ID_DYLIB` load command. Rebuilding a dylib under a longer `_reloc` path can change the embedded dylib path, increase the size of the load command, and shift the linked Mach-O layout.

That would cause the newly built binary to differ from the original even when the C source, compiler options, and intended code generation were otherwise unchanged.

To ensure that the corrected dataset uses exactly the same original binary artifacts, the macOS correction therefore uses this workflow:

1. Copy the original generated directory byte-for-byte to a `_reloc` directory.
2. Leave all source files, compiler assembly, objects, dylibs, and executables unchanged.
3. Regenerate only the `.objdump` files using relocation-preserving flags.
4. Validate that every non-`.objdump` artifact remains byte-for-byte identical.

This isolates the correction to the binary-to-text disassembly step.

### `refresh_humaneval_arm64_macos_objdump_reloc.py`

Regenerates only the objdump text from the copied original binaries:

- `code.o` -> `llvm-objdump -dr`
- `code.dylib` -> `llvm-objdump -drR`
- `code.program` -> `llvm-objdump -drR`

All other files remain untouched.

### `validate_humaneval_arm64_macos_reloc.py`

Performs local validation of the corrected macOS dataset.

It verifies that:

- both `O0` and `O2` contain all 164 HumanEval tasks;
- old and new directory/file layouts match;
- every non-`.objdump` file is byte-for-byte identical to the original;
- every new `.objdump` file exactly matches a fresh invocation of the intended `-dr` or `-drR` command;
- the binary format is ARM64 Mach-O.

This gives 328 validated task/split instances in total.

### `upload_humaneval_arm64_macos_hf.py`

Builds and uploads the original ARM64 macOS HumanEval `DatasetDict`.

### `upload_humaneval_arm64_macos_hf_reloc.py`

Builds the corrected ARM64 macOS `DatasetDict` from the `_reloc` output directory and uploads it to:

`adpretko/humaneval_arm_mac_reloc`

The uploaded dataset contains:

- 164 `O0` rows
- 164 `O2` rows

with the fields:

- `task_name`
- `source_code`
- `compiler_asm`
- `object_asm`
- `shared_asm`
- `program_asm`

### `validate_humaneval_arm64_macos_hf.py`

Downloads the uploaded relocation-preserving macOS dataset and compares all 328 rows (`164 O0 + 164 O2`) and every field exactly against the locally reconstructed dataset.

## Recommended workflow

### Linux

1. Run `build_humaneval_linux_reloc.py`.
2. Run `validate_humaneval_linux_reloc.py`.
3. Run `upload_humaneval_linux_hf_reloc.py`.
4. Run `validate_humaneval_linux_hf.py`.

### macOS

1. Copy `generated_humaneval_arm64_mac` to `generated_humaneval_arm64_mac_reloc`.
2. Run `refresh_humaneval_arm64_macos_objdump_reloc.py`.
3. Run `validate_humaneval_arm64_macos_reloc.py`.
4. Run `upload_humaneval_arm64_macos_hf_reloc.py`.
5. Run `validate_humaneval_arm64_macos_hf.py`.

The original generation scripts and datasets are retained for reproducibility. The `_reloc` versions are the corrected datasets that preserve relocation information in the binary-derived assembly.
