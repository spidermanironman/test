# Makefile for vmscan_timing_module

obj-m += vmscan_timing_module.o

KDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

load:
	sudo insmod vmscan_timing_module.ko

unload:
	sudo rmmod vmscan_timing_module

logs:
	dmesg | grep mm_vmscan_direct_reclaim | tail -20

.PHONY: all clean load unload logs
