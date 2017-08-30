
include ../config.mk

INCLUDES  += -I. -I.. -I$(PREFIX)/include
LIBDIRS      += -L. -L.. -L$(PREFIX)/lib
LIBS        += -lusermetric
OBJ       = $(patsubst %.c, %.o,$(wildcard *.c))
Q         ?= @
CC = gcc

ANSI_CFLAGS   =
CFLAGS   =  -g -O0 -std=c99 -Wno-format -fPIC
SHARED_LFLAGS = -shared

SUPPLY_METRICS_C = supply_usermetric


all: $(SUPPLY_METRICS_C)

$(SUPPLY_METRICS_C): supply_usermetric.c
	$(Q)${CC} $(INCLUDES) $(LIBDIRS) $(CFLAGS) $(ANSI_CFLAGS) $(SHARED_CFLAGS) supply_usermetric.c -o $(SUPPLY_METRICS_C) $(LIBS)

install: $(SUPPLY_METRICS_C)
	$(Q)install -m 755 $(SUPPLY_METRICS_C) $(PREFIX)/bin/$(SUPPLY_METRICS_C)

uninstall:
	$(Q)rm $(PREFIX)/bin/$(SUPPLY_METRICS_C)
clean:
	$(Q)rm -rf $(SUPPLY_METRICS_C)

.PHONY: clean

