/*
 * pikrellcam-lite 原生加速内核（版本号见 pkc_native_version()）
 *
 * 三个内核，把采集帧处理链路里最耗时的三段从 Python/numpy 挪进 C：
 *
 *   1. pkc_gray_ds()  RGB888 -> 降采样灰度图
 *      旧实现先算 1280x720 的 float32 全图灰度再降采样（36.7ms/帧），
 *      新实现只在降采样后的目标像素上算（320x180），一次遍历、零临时数组。
 *
 *   2. pkc_detect()   帧差分运动检测全流水线
 *      旧实现用 numpy 做 int16 差分 -> 布尔 mask -> 两次 cumsum 积分图 ->
 *      花式索引切片 -> 子区域 sum（22ms/帧）。
 *      新实现在 C 里一次遍历完成双算法的差分、密度滤波、区域占比、bbox。
 *
 *   3. pkc_jpeg()     RGB888 -> JPEG（libjpeg-turbo）
 *      绕开 Python 层的数组转换与中间拷贝，直接用 libjpeg 压缩。
 *
 * 通过 ctypes 以 C ABI 调用；不依赖 numpy C API，任何平台都能编。
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <setjmp.h>
#include <math.h>
#include <jpeglib.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ====================================================================
 * 1. RGB888 -> 降采样灰度
 *
 * 与 Python 版语义一致：gray_full[::sh, ::sw][:th, :tw]，
 * 灰度权重 0.299 / 0.587 / 0.114，截断取整。
 * ================================================================== */
void pkc_gray_ds(const uint8_t *rgb, int w, int h,
                 int tw, int th, uint8_t *out)
{
    if (!rgb || !out || w <= 0 || h <= 0 || tw <= 0 || th <= 0) return;

    int sh = h / th; if (sh < 1) sh = 1;
    int sw = w / tw; if (sw < 1) sw = 1;

    for (int i = 0; i < th; i++) {
        int sy = i * sh; if (sy >= h) sy = h - 1;
        const uint8_t *row = rgb + (size_t)sy * (size_t)w * 3;
        uint8_t *o = out + (size_t)i * (size_t)tw;
        for (int j = 0; j < tw; j++) {
            int sx = j * sw; if (sx >= w) sx = w - 1;
            const uint8_t *p = row + (size_t)sx * 3;
            double v = 0.299 * (double)p[0]
                     + 0.587 * (double)p[1]
                     + 0.114 * (double)p[2];
            o[j] = (uint8_t)v;
        }
    }
}

/* ====================================================================
 * 2. 运动检测
 * ================================================================== */
typedef struct {
    /* --- 输入 --- */
    int x0, y0, x1, y1;      /* 区域像素范围（左闭右开） */
    int mag_limit;           /* 差值二值化阈值 */
    int noise_k;             /* 邻域半径，0 = 不做密度滤波 */
    float count_limit;       /* 区域占比阈值 */
    int consecutive;         /* 连续命中帧数 */
    int hit_count;           /* 连续命中计数（输入=上一帧值，输出=本帧值） */

    /* --- 输出 --- */
    int hit;                 /* 1 = 判定为移动 */
    float ratio;             /* 区域有效变化像素占比 */
    int bx0, by0, bx1, by1;   /* 有效变化像素包围盒（区域绝对坐标） */
    int has_bbox;
} pkc_region_t;

/* 复用的积分图 scratch，按需增长，避免每帧 malloc */
static int32_t *g_integral = NULL;
static int      g_integral_cap = 0;

static int32_t *integral_ensure(int need)
{
    if (g_integral_cap < need) {
        int32_t *p = (int32_t *)realloc(g_integral, (size_t)need * sizeof(int32_t));
        if (!p) { g_integral_cap = 0; return NULL; }
        g_integral = p;
        g_integral_cap = need;
    }
    return g_integral;
}

/*
 * 对单个区域做检测。返回 1 成功。
 *
 * 密度滤波（noise_k > 0）语义与 Python 版 _box_sum 一致：
 *   k = noise_k*2+1，窗口在图像边界处收缩（clip，不是补零），
 *   邻域内变化像素数 >= max(1, k*k*0.25) 才算"有效变化"。
 */
static int detect_one(const uint8_t *cur, const uint8_t *prev,
                      int w, int h, pkc_region_t *rg)
{
    int x0 = rg->x0, y0 = rg->y0, x1 = rg->x1, y1 = rg->y1;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > w) x1 = w;
    if (y1 > h) y1 = h;
    if (x1 <= x0 || y1 <= y0) {
        rg->ratio = 0.0f; rg->hit = 0; rg->hit_count = 0; rg->has_bbox = 0;
        return 0;
    }

    int r = rg->noise_k;
    int mag = rg->mag_limit;

    int bw = x1 - x0, bh = y1 - y0;
    long long total = 0;
    int bx0 = 0, by0 = 0, bx1 = 0, by1 = 0;
    int has_bbox = 0;

    if (r > 0) {
        /* 在区域外扩 r 的范围内建局部积分图 */
        int ex0 = x0 - r; if (ex0 < 0) ex0 = 0;
        int ey0 = y0 - r; if (ey0 < 0) ey0 = 0;
        int ex1 = x1 + r; if (ex1 > w) ex1 = w;
        int ey1 = y1 + r; if (ey1 > h) ey1 = h;
        int ew = ex1 - ex0, eh = ey1 - ey0;

        int32_t *ii = integral_ensure((ew + 1) * (eh + 1));
        if (!ii) {
            rg->ratio = 0.0f; rg->hit = 0; rg->hit_count = 0; rg->has_bbox = 0;
            return 0;
        }
        /* ii 的第 0 行/列保持为 0 */
        for (int i = 0; i <= ew; i++) ii[i] = 0;
        for (int yy = 0; yy < eh; yy++) {
            const uint8_t *c = cur  + (size_t)(ey0 + yy) * (size_t)w;
            const uint8_t *p = prev + (size_t)(ey0 + yy) * (size_t)w;
            int32_t *prev_row = ii + (size_t)yy * (ew + 1);
            int32_t *cur_row  = ii + (size_t)(yy + 1) * (ew + 1);
            cur_row[0] = 0;
            int32_t row_sum = 0;
            for (int xx = 0; xx < ew; xx++) {
                int d = (int)c[ex0 + xx] - (int)p[ex0 + xx];
                if (d < 0) d = -d;
                row_sum += (d > mag) ? 1 : 0;
                cur_row[xx + 1] = prev_row[xx + 1] + row_sum;
            }
        }

        int k = r * 2 + 1;
        /* Python 版是 density >= max(1.0, k*k*0.25) 的浮点比较，
           等价于整数阈值 ceil(k*k*0.25)，且至少为 1。 */
        int need = (int)ceil((double)k * (double)k * 0.25);
        if (need < 1) need = 1;

        for (int yy = y0; yy < y1; yy++) {
            /* 窗口上下边界（相对扩展区） */
            int wy0 = yy - r - ey0; if (wy0 < 0) wy0 = 0;
            int wy1 = yy + r + 1 - ey0; if (wy1 > eh) wy1 = eh;
            for (int xx = x0; xx < x1; xx++) {
                /* 注意：Python 版语义是"邻域内变化像素够多即算有效变化"，
                   中心像素本身不必变化，因此这里不能用中心像素做前置过滤。 */
                int wx0 = xx - r - ex0; if (wx0 < 0) wx0 = 0;
                int wx1 = xx + r + 1 - ex0; if (wx1 > ew) wx1 = ew;
                int cnt = ii[(size_t)wy1 * (ew + 1) + wx1]
                        - ii[(size_t)wy0 * (ew + 1) + wx1]
                        - ii[(size_t)wy1 * (ew + 1) + wx0]
                        + ii[(size_t)wy0 * (ew + 1) + wx0];
                if (cnt < need) continue;

                total++;
                if (!has_bbox) {
                    bx0 = xx; bx1 = xx; by0 = yy; by1 = yy; has_bbox = 1;
                } else {
                    if (xx < bx0) bx0 = xx;
                    if (xx > bx1) bx1 = xx;
                    if (yy < by0) by0 = yy;
                    if (yy > by1) by1 = yy;
                }
            }
        }
    } else {
        for (int yy = y0; yy < y1; yy++) {
            const uint8_t *c = cur  + (size_t)yy * (size_t)w;
            const uint8_t *p = prev + (size_t)yy * (size_t)w;
            for (int xx = x0; xx < x1; xx++) {
                int d = (int)c[xx] - (int)p[xx];
                if (d < 0) d = -d;
                if (d <= mag) continue;
                total++;
                if (!has_bbox) {
                    bx0 = xx; bx1 = xx; by0 = yy; by1 = yy; has_bbox = 1;
                } else {
                    if (xx < bx0) bx0 = xx;
                    if (xx > bx1) bx1 = xx;
                    if (yy < by0) by0 = yy;
                    if (yy > by1) by1 = yy;
                }
            }
        }
    }

    rg->ratio = (float)((double)total / (double)(bw * bh));
    if (rg->ratio >= rg->count_limit) rg->hit_count += 1;
    else rg->hit_count = 0;
    rg->hit = (rg->hit_count >= rg->consecutive) ? 1 : 0;

    rg->bx0 = bx0; rg->by0 = by0; rg->bx1 = bx1; rg->by1 = by1;
    rg->has_bbox = has_bbox;
    return 1;
}

/*
 * 批量检测。
 *   cur/prev  : th*tw 的 uint8 灰度图（行优先）
 *   regions    : 区域数组，命中状态写回同一结构体
 * 返回处理的区域数，<0 表示失败。
 */
int pkc_detect(const uint8_t *cur, const uint8_t *prev, int w, int h,
               pkc_region_t *regions, int nregions)
{
    if (!cur || !prev || !regions || nregions < 0 || w <= 0 || h <= 0) return -1;
    for (int i = 0; i < nregions; i++) {
        if (!detect_one(cur, prev, w, h, &regions[i])) return -1;
    }
    return nregions;
}

/* ====================================================================
 * 3. RGB888 -> JPEG（libjpeg-turbo）
 * ================================================================== */
struct pkc_jpeg_err {
    struct jpeg_error_mgr pub;
    jmp_buf jmp;
};

static void pkc_jpeg_error_exit(j_common_ptr cinfo)
{
    struct pkc_jpeg_err *e = (struct pkc_jpeg_err *)cinfo->err;
    longjmp(e->jmp, 1);
}

/*
 * 把 RGB888 压缩成 JPEG 写入 out。
 * 返回编码后字节数；<0 表示失败。
 * cap 建议 >= w*h*3/2 + 1024。
 */
int pkc_jpeg(const uint8_t *rgb, int w, int h, int quality,
             uint8_t *out, int cap)
{
    if (!rgb || !out || w <= 0 || h <= 0 || cap <= 0) return -1;
    if (quality < 1) quality = 1;
    if (quality > 100) quality = 100;

    struct jpeg_compress_struct cinfo;
    struct pkc_jpeg_err jerr;
    unsigned char *buf = out;
    unsigned long size = (unsigned long)cap;

    cinfo.err = jpeg_std_error(&jerr.pub);
    jerr.pub.error_exit = pkc_jpeg_error_exit;
    if (setjmp(jerr.jmp)) {
        jpeg_destroy_compress(&cinfo);
        return -1;
    }

    jpeg_create_compress(&cinfo);
    jpeg_mem_dest(&cinfo, &buf, &size);

    cinfo.image_width      = w;
    cinfo.image_height     = h;
    cinfo.input_components = 3;
    cinfo.in_color_space   = JCS_RGB;

    jpeg_set_defaults(&cinfo);
    jpeg_set_quality(&cinfo, quality, TRUE);
    /* 4:2:0 采样，与 PIL 默认一致 */
    cinfo.comp_info[0].h_samp_factor = 2;
    cinfo.comp_info[0].v_samp_factor = 2;

    jpeg_start_compress(&cinfo, TRUE);
    while (cinfo.next_scanline < (unsigned int)cinfo.image_height) {
        JSAMPROW row[1];
        row[0] = (JSAMPROW)(rgb + (size_t)cinfo.next_scanline * (size_t)w * 3);
        jpeg_write_scanlines(&cinfo, row, 1);
    }
    jpeg_finish_compress(&cinfo);
    jpeg_destroy_compress(&cinfo);

    return (int)size;
}

/* 库版本信息，便于排查 */
const char *pkc_native_version(void)
{
#ifdef PKC_VERSION_STR
    return PKC_VERSION_STR;
#else
    return "pikrellcam-lite native";
#endif
}

#ifdef __cplusplus
}
#endif
