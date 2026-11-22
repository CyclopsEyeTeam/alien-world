CC ?= cc
PYTHON ?= python3
PYTHON_CONFIG ?= $(PYTHON)-config
PY_INCLUDES := $(shell $(PYTHON_CONFIG) --includes 2>/dev/null)
FAST_CELLS_SO := app/_fast_cells.abi3.so

.PHONY: all build check test demo clean
.DELETE_ON_ERROR:

all: build

build: $(FAST_CELLS_SO)

$(FAST_CELLS_SO): app/_fast_cells.c
	@if [ -n "$(PY_INCLUDES)" ]; then \
		$(CC) -O3 -ffp-contract=off -fPIC -shared -DPy_LIMITED_API=0x030a0000 $(PY_INCLUDES) app/_fast_cells.c -lm -o $(FAST_CELLS_SO) && \
		echo "Built $(FAST_CELLS_SO)"; \
	else \
		echo "$(PYTHON_CONFIG) unavailable; keeping existing $(FAST_CELLS_SO) or pure-Python fallback"; \
	fi

check: build
	$(PYTHON) ./bin/check-setup

test: build
	xvfb-run -a -s "-screen 0 1280x800x24 +extension GLX +extension Composite" \
		env LIBGL_ALWAYS_SOFTWARE=1 GDK_BACKEND=x11 $(PYTHON) -m unittest discover -s tests -v

demo: build
	xvfb-run -a -s "-screen 0 1280x800x24 +extension GLX +extension Composite" \
		env LIBGL_ALWAYS_SOFTWARE=1 GDK_BACKEND=x11 $(PYTHON) -m unittest discover -s tests -v -k LiveHeadlessElectricEyeDemoTest

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.pyc" -delete
