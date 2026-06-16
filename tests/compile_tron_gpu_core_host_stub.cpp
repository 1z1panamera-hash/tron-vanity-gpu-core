// Syntax-only host compile check for tron_gpu_core.cu when nvcc is unavailable.
// This does not compile CUDA kernels for GPU execution and does not benchmark.

#define __device__
#define __global__
#define __host__

struct FakeCudaIndex {
    int x;
};

FakeCudaIndex threadIdx{0};
FakeCudaIndex blockIdx{0};
FakeCudaIndex blockDim{1};
FakeCudaIndex gridDim{1};

unsigned long long atomicAdd(unsigned long long* target, unsigned long long value) {
    unsigned long long previous = *target;
    *target += value;
    return previous;
}

int atomicCAS(int* target, int compare, int value) {
    int previous = *target;
    if (previous == compare) {
        *target = value;
    }
    return previous;
}

#include "../src/tron_gpu_core.cu"
