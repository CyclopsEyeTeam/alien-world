CC ?= cc
PYTHON ?= python3
PY_INCLUDES := $(shell python3-config --includes 2>/dev/null)
FAST_CELLS_SO := app/_fast_cells.abi3.so

.PHONY: all build check test demo clean

all: build

build: $(FAST_CELLS_SO)

$(FAST_CELLS_SO): app/_fast_cells.c
	@if [ -n "$(PY_INCLUDES)" ]; then \
		$(CC) -O3 -ffp-contract=off -fPIC -shared -DPy_LIMITED_API=0x030a0000 $(PY_INCLUDES) app/_fast_cells.c -lm -o $(FAST_CELLS_SO); \
		echo "Built $(FAST_CELLS_SO)"; \
	else \
		echo "python3-config not found; keeping existing $(FAST_CELLS_SO) or pure-Python fallback"; \
	fi

check: build
	$(PYTHON) ./bin/check-setup

test: build
	$(PYTHON) -m unittest discover -s tests -v

demo: build
	xvfb-run -a -s "-screen 0 1280x800x24 +extension GLX +extension Composite" \
		env LIBGL_ALWAYS_SOFTWARE=1 $(PYTHON) -m unittest tests.test_alien_world_smoke.LiveHeadlessElectricEyeDemoTest -v

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.pyc" -delete
