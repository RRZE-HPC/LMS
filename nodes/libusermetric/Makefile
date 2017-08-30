
include config.mk

INCLUDES  += -I.
OBJ       = $(patsubst %.c, %.o,$(wildcard *.c))
Q         ?= @
DEFINES += -D_GNU_SOURCE

ANSI_CFLAGS   =

CFLAGS   = -g -O0 -std=gnu99 -Wno-format -fPIC -pthread
SHARED_CFLAGS = -fPIC
SHARED_LFLAGS = -shared
DYNAMIC_TARGET_LIB = libusermetric.so

all: $(DYNAMIC_TARGET_LIB)

$(DYNAMIC_TARGET_LIB): $(OBJ)
	@echo "===>  Link  $@"
	$(Q)${CC} $(DEFINES) $(INCLUDES) $(SHARED_LFLAGS) $(CFLAGS) $(ANSI_CFLAGS) $(SHARED_CFLAGS) -o $(DYNAMIC_TARGET_LIB) $(OBJ)

%.o:  %.c
	@echo "===>  COMPILE  $@"
	$(Q)$(CC) $(DEFINES) $(INCLUDES) -c $(CFLAGS) $(ANSI_CFLAGS) $(CPPFLAGS) $< -o $@

install: $(DYNAMIC_TARGET_LIB) usermetric.h
	$(Q)make -C scripts
	$(Q)install -m 755 $(DYNAMIC_TARGET_LIB) $(PREFIX)/lib/$(DYNAMIC_TARGET_LIB)
	$(Q)install -m 644 usermetric.h $(PREFIX)/include/usermetric.h
	$(Q)make -C scripts install

uninstall:
	$(Q)rm $(PREFIX)/lib/$(DYNAMIC_TARGET_LIB)
	$(Q)rm $(PREFIX)/include/usermetric.h
	$(Q)make -C scripts uninstall

clean:
	$(Q)make -C scripts clean
	@rm -rf *.o $(DYNAMIC_TARGET_LIB)

.PHONY: clean
