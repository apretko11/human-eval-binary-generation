# HumanEval Binary Generation

This repository contains the scripts used to generate HumanEval binary-derived assembly datasets for:

- x86-64 Linux
- ARM64 Linux
- RISC-V64 Linux
- ARM64 macOS

There are 164 HumanEval tasks in each optimization split (`O0` and `O2`).

## Final dataset schema

The existing `_reloc` datasets are preserved as the validated eight-column base representation. The newer `_reloc_v2` datasets retain those eight columns unchanged and append `program_asm_v2` as a ninth column.

For each HumanEval task and optimization level, the `_reloc_v2` datasets contain:

- `task_name` - HumanEval task identifier
- `source_code` - original C source
- `compiler_asm` - compiler-generated assembly from the normal, non-PIC compilation path
- `object_asm` - relocation-preserving disassembly of the normal relocatable object
- `shared_asm` - relocation-preserving disassembly of the linked shared library
- `program_asm` - relocation-preserving disassembly of the linked executable
- `compiler_pic_asm` - compiler-generated assembly from the PIC compilation path using `-fPIC -S`
- `pic_object_asm` - relocation-preserving disassembly of the PIC relocatable object
- `program_asm_v2` - additive semantic-data-augmented linked-program representation containing the existing `program_asm` verbatim plus semantic data-section contents and metadata

The original six assembly representations belong to two distinct compilation-provenance families. `program_asm_v2` is an additive enrichment of the normal linked-program representation:

```text
NORMAL
compiler_asm
    -> object_asm
    -> program_asm

PIC
compiler_pic_asm
    -> pic_object_asm
    -> shared_asm
```

This distinction is important.

The linked shared library is built from separately compiled position-independent (`-fPIC`) objects. Therefore, `shared_asm` belongs to the PIC compilation lineage and should be compared against `compiler_pic_asm` and `pic_object_asm`, rather than against the normal `compiler_asm` and `object_asm` lineage.

The validated eight-column `_reloc` base datasets are published at:

```text
adpretko/humaneval_x86_linux_reloc
adpretko/humaneval_arm_linux_reloc
adpretko/humaneval_riscv_linux_reloc
adpretko/humaneval_arm_mac_reloc
```

The additive nine-column `_reloc_v2` datasets are:

```text
adpretko/humaneval_x86_linux_reloc_v2
adpretko/humaneval_arm_linux_reloc_v2
adpretko/humaneval_riscv_linux_reloc_v2
adpretko/humaneval_arm_mac_reloc_v2
```

## Relocation-preserving disassembly

The final datasets preserve relocation information in binary-derived assembly.

For relocatable objects:

```text
objdump -dr
```

or, on macOS:

```text
xcrun llvm-objdump -dr
```

For linked shared libraries and executables:

```text
objdump -drR
```

or, on macOS:

```text
xcrun llvm-objdump -drR
```

The relocation flags are important because plain `objdump -d` omits relocation records that are still present in relocatable object files.

## Source and executable construction

HumanEval entries contain function-level C source rather than complete standalone programs with their own `main()`.

The original HumanEval source is preserved unchanged for:

- `source_code`
- normal compiler-generated assembly
- PIC compiler-generated assembly
- normal relocatable object construction
- PIC relocatable object construction
- shared-library construction

A synthetic `main()` is appended only to a temporary executable source file so that a linked executable can be produced.

The synthetic entry point is:

```c
int main(void)
{
    return 0;
}
```

It is used only to make executable construction possible. It does not execute or test the HumanEval function.

## `program_asm_v2`: semantic-data-augmented linked-program representation

The original `program_asm` representation is retained unchanged. It is the
relocation-preserving disassembly of the linked executable and remains useful
for code and control-flow analysis.

For whole-program translation, however, disassembly alone is not always
sufficient. Program behavior can also depend on initialized data
stored outside the executable code section, including string literals, lookup
tables, initialized globals, and floating-point constants.

The additive `program_asm_v2` representation therefore reuses the exact
already-validated executable and embeds the existing validated `program_asm`
verbatim. It does **not** rebuild, recompile, or relink the program.

On Linux, `program_asm_v2` contains:

```text
semantic section layout / metadata

existing validated program_asm verbatim

initialized semantic section contents:
    .rodata
    .data
    .data.rel.ro    when present

semantic data symbols

.bss layout / symbol metadata only
```

`.bss` is zero-fill storage, so no synthetic raw zero-byte dump is added.

Linker/runtime-only sections are not added as semantic raw-data blocks.

Generate the Linux `program_asm_v2` sidecars with:

```bash
python make_program_asm_v2_linux.py
```

The generated sidecars and provenance manifest are written beneath:

```text
program_asm_v2_full/
```

The `_reloc_v2` Hugging Face datasets are additive extensions of the existing
`_reloc` datasets. Every existing field is preserved unchanged and
`program_asm_v2` is appended as a ninth column.


## Linux

### `build_humaneval_linux.py`

Original Linux generation script.

It compiles the HumanEval source for the supported Linux targets and generates:

- compiler assembly
- relocatable objects
- shared libraries
- linked executables
- binary-derived disassembly

The original binary disassembly used plain `-d`.

This script is retained for reproducibility of the original generation workflow.

### `build_humaneval_linux_reloc.py`

Relocation-preserving Linux generation script.

It produces the corrected relocation-preserving output trees and uses:

```text
normal relocatable object -> objdump -dr
shared library            -> objdump -drR
executable                -> objdump -drR
```

The relocation-preserving outputs are stored separately from the original generated datasets.

The builder also produces the PIC object used for shared-library construction.

### `validate_humaneval_linux_reloc.py`

Validates the locally generated relocation-preserving Linux datasets.

The validation checks include:

- all 164 tasks are present in both `O0` and `O2`
- task names and source code are preserved
- compiler-generated assembly is consistent with the expected generation
- the underlying instruction disassembly has not unexpectedly changed
- saved objdump output matches fresh relocation-preserving disassembly
- generated binaries have the expected target formats

### `add_pic_references_humaneval_linux.py`

Adds the explicit PIC-reference artifacts needed by the validated eight-column `_reloc` base dataset.

For every task in both optimization splits it creates:

```text
compiler.pic.s
code.pic.o.objdump
```

`compiler.pic.s` is generated from the original source using the same target and optimization level as the existing PIC object, but with:

```text
-fPIC -S
```

instead of object generation.

`code.pic.o.objdump` is generated by disassembling the existing PIC relocatable object with:

```text
objdump -dr
```

The script intentionally reuses the already generated `code.pic.o`.

It does not rebuild the existing:

- normal relocatable object
- PIC relocatable object
- shared library
- executable

This preserves the exact PIC object that was already used to construct the shared library.

### `make_program_asm_v2_linux.py`

Builds the additive `program_asm_v2` representation from the already-validated linked Linux executables and their existing `program_asm` text.

It does not recompile or relink the binaries. It preserves the existing `program_asm` verbatim, adds selected semantic section layout/content and symbols, and records `.bss` as metadata without synthesizing raw zero bytes.

Outputs are written under:

```text
program_asm_v2_full/
```

### `upload_humaneval_linux_hf.py`

Uploads the original Linux HumanEval datasets.

This script belongs to the original generation workflow and is retained for reproducibility.

### `upload_humaneval_linux_hf_reloc.py`

Builds and uploads the earlier relocation-preserving dataset representation.

This script predates the addition of the explicit PIC compiler and PIC object reference columns.

It is retained for reproducibility.

### `upload_humaneval_linux_hf_with_pic.py`

Packages the validated Linux `_reloc` base datasets with the eight-column schema:

```text
task_name
source_code
compiler_asm
object_asm
shared_asm
program_asm
compiler_pic_asm
pic_object_asm
```

It supports all three Linux targets:

```text
x86_linux
arm_linux
riscv_linux
```

which correspond to:

```text
adpretko/humaneval_x86_linux_reloc
adpretko/humaneval_arm_linux_reloc
adpretko/humaneval_riscv_linux_reloc
```

The script validates the expected row count, schema, task ordering, source-code identity, and non-empty assembly fields before upload.

To validate locally without uploading:

```bash
python upload_humaneval_linux_hf_with_pic.py --validate-only
```

To build, validate, and upload all Linux targets:

```bash
python upload_humaneval_linux_hf_with_pic.py
```

### `validate_humaneval_linux_hf.py`

Validation utility for the earlier relocation-preserving Hugging Face workflow.

It is retained alongside the original upload scripts for reproducibility.

The PIC-aware base-dataset packaging and schema checks are performed by `upload_humaneval_linux_hf_with_pic.py`.

## ARM64 macOS

### `build_humaneval_arm64_macos.py`

Original ARM64 macOS generation script.

For each HumanEval task it produces:

```text
source.c
program_source.c
compiler.s
code.o
code.o.objdump
code.pic.o
code.dylib
code.dylib.objdump
code.program
code.program.objdump
```

`source.c` contains the original HumanEval source exactly.

`program_source.c` contains the same source plus the synthetic `main()` used only for executable linking.

`code.pic.o` is the position-independent object used to construct `code.dylib`.

### `probe_humaneval_macos.py`

Auxiliary probe script for the HumanEval macOS generation workflow.

It is kept alongside the generation scripts as a utility for checking the macOS toolchain and generation setup.

### Why macOS uses a refresh workflow

The corrected macOS dataset is intentionally not rebuilt into a differently named output directory.

Mach-O dynamic libraries contain an `LC_ID_DYLIB` load command. Rebuilding a dylib under a longer `_reloc` path can change the embedded dylib path, increase the size of the load command, and shift the linked Mach-O layout.

That would cause the newly built binary to differ from the original even when the C source, compiler options, and intended code generation were otherwise unchanged.

To ensure that the corrected dataset uses the same original binary artifacts, the macOS relocation-preserving workflow is:

1. Copy the original generated directory byte-for-byte to a `_reloc` directory.
2. Leave the source files, compiler assembly, objects, dylibs, and executables unchanged.
3. Regenerate only the `.objdump` files using relocation-preserving flags.
4. Validate that the non-objdump artifacts remain byte-for-byte identical.

This isolates the original correction to the binary-to-text disassembly step.

### `refresh_humaneval_arm64_macos_objdump_reloc.py`

Regenerates the objdump text from the copied original binaries using relocation-preserving flags:

```text
code.o       -> xcrun llvm-objdump -dr
code.dylib   -> xcrun llvm-objdump -drR
code.program -> xcrun llvm-objdump -drR
```

All other existing artifacts remain untouched.

### `validate_humaneval_arm64_macos_reloc.py`

Performs local validation of the relocation-preserving macOS dataset.

It verifies that:

- both `O0` and `O2` contain all 164 HumanEval tasks
- old and new directory/file layouts match
- non-objdump artifacts remain byte-for-byte identical where expected
- refreshed objdump files match fresh invocations of the intended commands
- the binary format is ARM64 Mach-O

This covers 328 task/split instances:

```text
164 O0 + 164 O2 = 328
```

### `add_pic_references_humaneval_arm64_macos.py`

Adds the two explicit PIC-reference artifacts needed by the final macOS dataset:

```text
compiler.pic.s
code.pic.o.objdump
```

`compiler.pic.s` is generated from the original source using:

```text
xcrun clang -arch arm64 -O0/-O2 -fPIC -S
```

`code.pic.o.objdump` is generated from the existing PIC object using:

```text
xcrun llvm-objdump -dr code.pic.o
```

The script deliberately reuses the existing `code.pic.o` that was already used to construct `code.dylib`.

It does not rebuild the existing:

- `code.pic.o`
- `code.dylib`
- `code.o`
- `code.program`

This preserves the provenance between:

```text
compiler_pic_asm
    -> pic_object_asm
    -> shared_asm
```

### `upload_humaneval_arm64_macos_hf.py`

Builds and uploads the original ARM64 macOS HumanEval dataset.

It is retained for reproducibility of the original workflow.

### `upload_humaneval_arm64_macos_hf_reloc.py`

Builds and uploads the earlier relocation-preserving ARM64 macOS dataset.

It predates the addition of the explicit PIC reference columns and is retained for reproducibility.

### `upload_humaneval_arm64_macos_hf_with_pic.py`

Produces the validated ARM64 macOS `_reloc` base dataset with the eight-column schema:

```text
task_name
source_code
compiler_asm
object_asm
shared_asm
program_asm
compiler_pic_asm
pic_object_asm
```

Target repository:

```text
adpretko/humaneval_arm_mac_reloc
```

The script first loads the current live Hugging Face dataset and verifies that the existing dataset fields correspond to the local relocation-preserving artifact tree.

It then adds:

```text
compiler_pic_asm
pic_object_asm
```

from:

```text
compiler.pic.s
code.pic.o.objdump
```

The script supports local validation without upload:

```bash
python3 upload_humaneval_arm64_macos_hf_with_pic.py --validate-only
```

It can also reload and verify the final live Hugging Face dataset:

```bash
python3 upload_humaneval_arm64_macos_hf_with_pic.py --verify-live
```

### `validate_humaneval_arm64_macos_hf.py`

Validation utility for the earlier relocation-preserving macOS Hugging Face workflow.

It is retained for reproducibility.

The live PIC-aware eight-column base dataset can additionally be verified directly with:

```bash
python3 upload_humaneval_arm64_macos_hf_with_pic.py --verify-live
```

## Final provenance model

The important methodological distinction in the final datasets is:

```text
                 NORMAL COMPILATION

source_code
    |
    +--> compiler_asm
            |
            +--> object_asm
                    |
                    +--> linked executable
                            |
                            +--> program_asm
                            |
                            +--> program_asm_v2
                                 (program_asm verbatim + semantic data from the same executable)


                   PIC COMPILATION

source_code
    |
    +--> compiler_pic_asm
            |
            +--> pic_object_asm
                    |
                    +--> shared_asm
```

The two families originate from the same C source and optimization level, but they are not required to produce identical assembly.

In particular, optimized PIC and non-PIC compilation can legitimately differ because position-independent code generation changes how addresses, globals, calls, and other operations are represented.

For that reason, downstream analysis should preserve the two provenance families rather than treating all six representations as one linear compilation chain.

## Recommended workflow

### Linux

Generate the relocation-preserving binaries:

```bash
python build_humaneval_linux_reloc.py
```

Validate them:

```bash
python validate_humaneval_linux_reloc.py
```

Generate the explicit PIC compiler/object references:

```bash
python add_pic_references_humaneval_linux.py
```

Validate final Hugging Face packaging without uploading:

```bash
python upload_humaneval_linux_hf_with_pic.py --validate-only
```

Upload the validated eight-column base datasets:

```bash
python upload_humaneval_linux_hf_with_pic.py
```


Generate the semantic-data-augmented linked-program sidecars from the
already-validated Linux executables:

```bash
python make_program_asm_v2_linux.py
```

The resulting `program_asm_v2` text is published additively in the
`_reloc_v2` Hugging Face datasets. The original `_reloc` datasets and all
eight of their existing columns remain unchanged.


### ARM64 macOS

Start from the original generated macOS dataset and create the relocation-preserving copy:

```text
generated_humaneval_arm64_mac
    ->
generated_humaneval_arm64_mac_reloc
```

Refresh the binary disassembly:

```bash
python3 refresh_humaneval_arm64_macos_objdump_reloc.py
```

Validate the relocation-preserving copy:

```bash
python3 validate_humaneval_arm64_macos_reloc.py
```

Generate the explicit PIC compiler/object references:

```bash
python3 add_pic_references_humaneval_arm64_macos.py
```

Validate final dataset packaging without uploading:

```bash
python3 upload_humaneval_arm64_macos_hf_with_pic.py --validate-only
```

Upload the validated eight-column base dataset:

```bash
python3 upload_humaneval_arm64_macos_hf_with_pic.py
```

Verify the live eight-column base Hugging Face dataset:

```bash
python3 upload_humaneval_arm64_macos_hf_with_pic.py --verify-live
```

## Reproducibility note

The original generation, upload, and validation scripts are intentionally retained.

They document the progression from:

```text
original binary disassembly
        ->
relocation-preserving disassembly
        ->
explicit normal/PIC provenance
        ->
semantic-data-augmented program_asm_v2
```

The `_reloc` Hugging Face datasets retain the validated eight-column representation for reproducibility. The newer `_reloc_v2` datasets append `program_asm_v2` and should be used when whole-program translation requires semantic data in addition to disassembly and relocations.
