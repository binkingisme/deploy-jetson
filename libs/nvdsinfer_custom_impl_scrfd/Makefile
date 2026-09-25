CUDA_VER ?= 12.6
NVDS_PREFIX ?= /opt/nvidia/deepstream/deepstream-7.1
CXX := g++
INCLUDES := -I$(NVDS_PREFIX)/sources/includes -I/usr/local/cuda-12.6/include

all: libnvdsinfer_custom_impl_scrfd.so

libnvdsinfer_custom_impl_scrfd.so: nvdsparsebbox_scrfd.cpp
	$(CXX) -shared -fPIC -o $@ $< $(INCLUDES) -std=c++17

clean:
	rm -f *.so

.PHONY: all clean
