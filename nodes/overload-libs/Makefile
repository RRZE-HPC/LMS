
INCLUDES := -I/home/rrze/unrz/unrz139/Work/LMS/nodes/libusermetric
LIBPATHS := -L/home/rrze/unrz/unrz139/Work/LMS/nodes/libusermetric
LIBS := -lusermetric

GCC_SRC := $(wildcard *overload.c)
GCC_SRC := $(filter-out iomp_overload.cc,$(GCC_SRC))
ICC_SRC := iomp_overload.cc


GCC_OBJ := $(patsubst %.c, %.so, $(GCC_SRC))
ICC_OBJ := $(patsubst %.cc, %.so, $(ICC_SRC))

TEST_ICC=$(shell which icc 2>/dev/null)


all: $(GCC_OBJ) $(ICC_OBJ)


%.so:  %.c
	@echo "===>  COMPILE with GCC $@"
	gcc -fopenmp -shared -fPIC $(INCLUDES) $(LIBPATHS) $< -o $@ -ldl $(LIBS)

%.so:  %.cc
	@echo "===>  COMPILE with G++ $@"
	g++ -std=c++11 -fpermissive -g -I. -I openmp-4.0.0.src/src/ -I openmp-4.0.0.src/runtime/src/ -fopenmp -shared -fPIC $< -o $@ -ldl -liomp5

clean:
	rm -rf $(GCC_OBJ) $(ICC_OBJ)
distclean: clean
	rm -rf $(GCC_SRC) $(ICC_SRC)

.PHONY: clean
