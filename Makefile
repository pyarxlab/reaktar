# ==============================================================================
# Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
# Part of the Pyarx project: https://github.com/pyarxlab/reaktar
#
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Pyarx Lab
# ==============================================================================

ARXML ?= arxml/vehicle_system.arxml
PASS_BY ?= const_ref
PYTHON ?= python3
BUILD_DIR ?= build

.PHONY: all generate build test package clean help

all: build

help:
	@echo "Available targets:"
	@echo "  make bootstrap  - Check Python >= 3.10 and install required Python packages (requirements.txt)"
	@echo "  make generate  - Generate C++ Actor and TestBench headers from ARXML"
	@echo "                   Usage: make generate [ARXML=arxml/vehicle_system.arxml] [PASS_BY=const_ref|value]"
	@echo "  make build     - Configure and build all C++ targets (Release)"
	@echo "  make test      - Run all smoke test suites via CTest"
	@echo "  make package   - Build portable package containing only ReaktAR & generated headers"
	@echo "                   Usage: make package [ARXML=arxml/vehicle_system.arxml] [OUTPUT=dist]"
	@echo "  make clean     - Remove build artifacts and package archives"

bootstrap:
	@echo "==> Verifying Python version (>= 3.10)..."
	@$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 10), f"Python 3.10+ required, found {sys.version}"'
	@echo "==> Installing Python dependencies from requirements.txt..."
	@$(PYTHON) -m pip install -r requirements.txt

generate:
	@echo "==> Generating C++ Actor & TestBench headers from $(ARXML) (pass-by: $(PASS_BY))..."
	@$(PYTHON) scripts/generate_actor.py $(ARXML) --pass-by $(PASS_BY)

$(BUILD_DIR)/CMakeCache.txt: CMakeLists.txt
	@cmake -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=Release

build: $(BUILD_DIR)/CMakeCache.txt
	@echo "==> Building ReaktAR..."
	@cmake --build $(BUILD_DIR)

test: build
	@echo "==> Running CTest smoke test suites..."
	@ctest --test-dir $(BUILD_DIR) --output-on-failure

package:
	@echo "==> Packaging ReaktAR framework..."
	@$(PYTHON) scripts/package_reactar.py $(ARXML) $(if $(OUTPUT),-o $(OUTPUT),)

clean:
	@echo "==> Cleaning build artifacts..."
	@rm -rf $(BUILD_DIR) dist
