/* Run under AddressSanitizer/UBSan, independently of the Python interpreter. */
#include <assert.h>
#include "../core/_pkc_native.c"

int main(void)
{
    enum { W = 61, H = 37 };
    uint8_t cur[W * H], prev[W * H];
    for (int i = 0; i < W * H; i++) {
        cur[i] = (uint8_t)(i * 71);
        prev[i] = (uint8_t)(i * 43);
    }
    for (int radius = 0; radius < 10; radius++) {
        pkc_region_t regions[12] = {0};
        for (int j = 0; j < 12; j++) {
            regions[j].x0 = j - 2; regions[j].y0 = j - 1;
            regions[j].x1 = W; regions[j].y1 = H;
            regions[j].mag_limit = j % 2 ? 12 : 28;
            regions[j].noise_k = radius;
            regions[j].count_limit = .01f;
            regions[j].consecutive = 2;
            regions[j].hit_count = 1;
        }
        assert(pkc_detect(cur, prev, W, H, regions, 12) == 12);
        for (int j = 0; j < 12; j++) {
            assert(regions[j].ratio >= 0 && regions[j].ratio <= 1);
            if (regions[j].has_bbox) {
                assert(regions[j].bx0 >= 0 && regions[j].bx1 < W);
                assert(regions[j].by0 >= 0 && regions[j].by1 < H);
            }
        }
    }
    pkc_region_t huge = {0};
    huge.x1 = W; huge.y1 = H; huge.noise_k = INT_MAX;
    huge.count_limit = .1f; huge.consecutive = 1;
    assert(pkc_detect(cur, prev, W, H, &huge, 1) == 1);
    assert(!huge.has_bbox && !huge.hit);

    uint8_t rgb[W * H * 3], gray[W * H];
    for (int i = 0; i < W * H * 3; i++) rgb[i] = (uint8_t)(i * 73);
    pkc_gray_ds(rgb, W, H, W, H, gray);
    uint8_t guarded[48];
    memset(guarded, 77, sizeof(guarded));
    assert(pkc_jpeg(rgb, W, H, 100, guarded, 16) < 0);
    for (int i = 16; i < 48; i++) assert(guarded[i] == 77);
    uint8_t out[W * H * 3 + 65536];
    int length = pkc_jpeg(rgb, W, H, 100, out, sizeof(out));
    assert(length > 0 && length <= (int)sizeof(out));
    assert(out[0] == 255 && out[1] == 216);
    assert(out[length - 2] == 255 && out[length - 1] == 217);
    puts("Native sanitizer checks passed");
    return 0;
}
