---
paths:
  - "**/*.cpp"
  - "**/*.hpp"
  - "**/*.cc"
  - "**/*.hh"
  - "**/*.cxx"
  - "**/*.h"
  - "**/CMakeLists.txt"
---
<!-- ecc:rules/cpp/testing.md@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# C++ Testing

> This file extends [common/testing.md](../common/testing.md) with C++ specific content.

## Framework

Use **GoogleTest** (gtest/gmock) with **CMake/CTest**.

## Running Tests

```bash
cmake --build build && ctest --test-dir build --output-on-failure
```

## Coverage

```bash
cmake -DCMAKE_CXX_FLAGS="--coverage" -DCMAKE_EXE_LINKER_FLAGS="--coverage" ..
cmake --build .
ctest --output-on-failure
lcov --capture --directory . --output-file coverage.info
```

## Sanitizers

Always run tests with sanitizers in CI:

```bash
cmake -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined" ..
```

## Reference

See skill: `cpp-testing` for detailed C++ testing patterns, TDD workflow, and GoogleTest/GMock usage.
