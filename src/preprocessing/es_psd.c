/* es_psd: online front-end for EtherSense on the AP.
 * Reads hackrf_transfer cs8 I/Q from stdin, Hann-windowed FFT (radix-2, float), averages |X|^2,
 * and every REPORT seconds of samples prints one line: wall time, samples, processing seconds,
 * full-band power and 1 MHz band powers (digital dB, x/128 scaling, same as the offline analysis).
 * Optionally appends the averaged PSD (float32, fftshifted) to a binary file.
 * Usage: hackrf_transfer -r - ... | es_psd -N 4096 -r 1.0 -s 20000000 [-p psd.bin] > report.txt
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }
static double cpu_s(void) { struct rusage u; getrusage(RUSAGE_SELF, &u); return u.ru_utime.tv_sec + u.ru_utime.tv_usec * 1e-6 + u.ru_stime.tv_sec + u.ru_stime.tv_usec * 1e-6; }

static void fft(float *re, float *im, int n, const float *cw, const float *sw) {
    for (int i = 1, j = 0; i < n; i++) {               /* bit reversal */
        int b = n >> 1; for (; j & b; b >>= 1) j ^= b; j ^= b;
        if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (int len = 2; len <= n; len <<= 1) {
        int step = n / len, h = len >> 1;
        for (int i = 0; i < n; i += len)
            for (int k = 0; k < h; k++) {
                float c = cw[k * step], s = sw[k * step];
                int a = i + k, b = a + h;
                float xr = re[b] * c + im[b] * s, xi = im[b] * c - re[b] * s;   /* e^{-j...} */
                re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
            }
    }
}

int main(int argc, char **argv) {
    int N = 4096; double rep = 1.0, fs = 20e6; const char *psdpath = NULL;
    int o; while ((o = getopt(argc, argv, "N:r:s:p:")) != -1) {
        if (o == 'N') N = atoi(optarg); else if (o == 'r') rep = atof(optarg);
        else if (o == 's') fs = atof(optarg); else if (o == 'p') psdpath = optarg;
        else { fprintf(stderr, "usage: es_psd -N fft -r report_s -s fs [-p psd.bin]\n"); return 1; }
    }
    if (N < 64 || (N & (N - 1))) { fprintf(stderr, "N must be a power of two >= 64\n"); return 1; }
    float *win = malloc(N * sizeof(float)), *cw = malloc(N / 2 * sizeof(float)), *sw = malloc(N / 2 * sizeof(float));
    float *re = malloc(N * sizeof(float)), *im = malloc(N * sizeof(float));
    double *acc = calloc(N, sizeof(double)); int8_t *buf = malloc(2 * N);
    double wss = 0;
    for (int i = 0; i < N; i++) { win[i] = 0.5f - 0.5f * cosf(2 * M_PI * i / N); wss += (double)win[i] * win[i]; }
    for (int k = 0; k < N / 2; k++) { cw[k] = cosf(2 * M_PI * k / N); sw[k] = sinf(2 * M_PI * k / N); }
    double scale = 1.0 / (fs * wss), df = fs / N;
    FILE *pf = psdpath ? fopen(psdpath, "ab") : NULL;
    long per_rep = (long)(rep * fs / N); if (per_rep < 1) per_rep = 1;
    long blocks = 0, total_blocks = 0; double proc = 0, t_start = now(), c_start = cpu_s();
    printf("# es_psd N=%d fs=%.0f report=%.3fs blocks_per_report=%ld\n", N, fs, rep, per_rep);
    printf("# wall_s samples proc_s proc_per_block_us total_db band_db[10..29 MHz offsets -10..+9 MHz]\n");
    fflush(stdout);
    for (;;) {
        size_t got = 0;
        while (got < (size_t)(2 * N)) { size_t r = fread(buf + got, 1, 2 * N - got, stdin); if (!r) break; got += r; }
        if (got < (size_t)(2 * N)) break;
        double t0 = now();
        float mr = 0, mi = 0;
        for (int i = 0; i < N; i++) { re[i] = buf[2 * i] / 128.f; im[i] = buf[2 * i + 1] / 128.f; mr += re[i]; mi += im[i]; }
        mr /= N; mi /= N;
        for (int i = 0; i < N; i++) { re[i] = (re[i] - mr) * win[i]; im[i] = (im[i] - mi) * win[i]; }
        fft(re, im, N, cw, sw);
        for (int i = 0; i < N; i++) acc[i] += (double)re[i] * re[i] + (double)im[i] * im[i];
        proc += now() - t0; blocks++; total_blocks++;
        if (blocks == per_rep) {
            double tot = 0, band[20] = {0};
            for (int i = 0; i < N; i++) {
                double p = acc[i] / blocks * scale; int k = (i + N / 2) % N;   /* fftshift index */
                double f = (k - N / 2) * df; tot += p * df;
                int b = (int)floor((f + fs / 2) / 1e6); if (b >= 0 && b < 20 && fabs(f) > 5000) band[b] += p * df;
            }
            if (pf) { for (int k = 0; k < N; k++) { float v = (float)(acc[(k + N / 2) % N] / blocks * scale); fwrite(&v, 4, 1, pf); } fflush(pf); }
            printf("%.3f %ld %.4f %.1f %.2f", now() - t_start, (long)blocks * N, proc, proc / blocks * 1e6, 10 * log10(tot + 1e-30));
            for (int b = 0; b < 20; b++) printf(" %.2f", 10 * log10(band[b] + 1e-30));
            printf("\n"); fflush(stdout);
            memset(acc, 0, N * sizeof(double)); blocks = 0; proc = 0;
        }
    }
    double wall = now() - t_start, cpu = cpu_s() - c_start;
    struct rusage u; getrusage(RUSAGE_SELF, &u);
    printf("# END blocks=%ld samples=%ld wall_s=%.3f cpu_s=%.3f realtime_ratio=%.3f maxrss_kb=%ld\n",
           total_blocks, total_blocks * (long)N, wall, cpu, total_blocks * (double)N / fs / wall, u.ru_maxrss);
    if (pf) fclose(pf);
    return 0;
}
