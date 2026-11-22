/* Exact native cell-grid construction for Alien World.
 *
 * Replicates fast_field.prepare_cell and the RenderAgent._build_cells grid
 * loop with identical IEEE-754 doubles, the same libm sin as CPython's
 * math.sin, the same expression order and the same integer pipeline.
 * Build with -ffp-contract=off and no fast-math so no multiply/add is
 * fused; bit-exactness against the Python path is asserted by
 * benchmark_frame.py before any release selection.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>

#define MAX_COLS 512
#define MAX_ROWS 128
#define MAX_BAND 32
#define MAX_SPARKS 8
#define MAX_CURIOSITIES 32

/* The limited API hides the _GET macros (they peek at private struct
 * layout). PySequence_Fast always returns a list or tuple, so these
 * checked-access wrappers keep the same borrowed-reference semantics. */
static inline Py_ssize_t
fast_size(PyObject *o)
{
    return PyList_CheckExact(o) ? PyList_Size(o) : PyTuple_Size(o);
}

static inline PyObject *
fast_item(PyObject *o, Py_ssize_t i)
{
    return PyList_CheckExact(o) ? PyList_GetItem(o, i) : PyTuple_GetItem(o, i);
}

/* Python float x % 1.0 (result carries the divisor's sign). */
static double
pmod1(double h)
{
    double r = fmod(h, 1.0);
    if (r < 0.0) {
        r += 1.0;
    }
    return r;
}

/* clamp01: clamp(value, 0.0, 1.0) including the shared non-finite midpoint. */
static double
clamp01(double v)
{
    if (v != v || v > 1e9 || v < -1e9) {
        return (0.0 + 1.0) / 2.0;
    }
    if (v < 0.0) {
        return 0.0;
    }
    if (v > 1.0) {
        return 1.0;
    }
    return v;
}

/* hashmix(x, y, z): unsigned arithmetic keeps every Python int's low 32
 * bits exact, whatever its width. */
static double
hashmix(unsigned long long x, unsigned long long y, unsigned long long z)
{
    unsigned long long n = (x * 374761393ULL
                          + y * 668265263ULL
                          + z * 1442695041ULL) & 0xFFFFFFFFULL;
    n ^= n >> 13;
    n = (n * 1274126177ULL) & 0xFFFFFFFFULL;
    return (double)(n & 0xFFFFFFULL) / (double)0xFFFFFFULL;
}

/* hsv_to_rgb: sector if/elif selection, as in the live aura_hive source. */
static void
hsv_to_rgb(int out[3], double h, double s, double v)
{
    h = pmod1(h);
    s = clamp01(s);
    v = clamp01(v);
    int sector = (int)(h * 6.0);
    double frac = h * 6.0 - (double)sector;
    double p = v * (1.0 - s);
    double q = v * (1.0 - frac * s);
    double t = v * (1.0 - (1.0 - frac) * s);
    double r, g, b;
    int pick = sector % 6;
    if (pick == 0) {
        r = v; g = t; b = p;
    } else if (pick == 1) {
        r = q; g = v; b = p;
    } else if (pick == 2) {
        r = p; g = v; b = t;
    } else if (pick == 3) {
        r = p; g = q; b = v;
    } else if (pick == 4) {
        r = t; g = p; b = v;
    } else {
        r = v; g = p; b = q;
    }
    out[0] = (int)(r * 255 + 0.5);
    out[1] = (int)(g * 255 + 0.5);
    out[2] = (int)(b * 255 + 0.5);
}

/* recipe_rgb: Abled's recipe table in place of the HSV wheel, exactly as
 * recipe_palette.recipe_rgb: v * (1 - s * (1 - c)) per channel. */
#define MAX_RECIPE 1024
static void
recipe_rgb(int out[3], const double *table, int n, double h, double s, double v)
{
    h = pmod1(h);
    s = clamp01(s);
    v = clamp01(v);
    int i = (int)(h * (double)n);
    if (i >= n) {
        i = n - 1;
    }
    double r = v * (1.0 - s * (1.0 - table[3 * i]));
    double g = v * (1.0 - s * (1.0 - table[3 * i + 1]));
    double b = v * (1.0 - s * (1.0 - table[3 * i + 2]));
    out[0] = (int)(r * 255 + 0.5);
    out[1] = (int)(g * 255 + 0.5);
    out[2] = (int)(b * 255 + 0.5);
}

/* mix_rgb(a, b, amount): clamp01 then per-channel truncated lerp. */
static void
mix_rgb(int out[3], const int a[3], const int b[3], double amount)
{
    amount = clamp01(amount);
    out[0] = (int)((double)a[0] * (1.0 - amount) + (double)b[0] * amount);
    out[1] = (int)((double)a[1] * (1.0 - amount) + (double)b[1] * amount);
    out[2] = (int)((double)a[2] * (1.0 - amount) + (double)b[2] * amount);
}

PyDoc_STRVAR(build_cells_doc,
"build_cells(cols, rows, t, void, freq, tspeed, tslow, palette, hue0, spread,\n"
"            noise, amp, tick, period, crest, phase, dark_limit, spark_limit,\n"
"            saturation, band, sparks, prepared_x, prepared_y, thin, digit,\n"
"            digit_mix, digit_tick, noise_on, noise_tick, spark_left,\n"
"            fdx, fdy, recipe_table=None)\n"
"\n"
"Whole-grid cell construction. spark_left uses -1 for the Python None.\n"
"Returns the same list[list[tuple[str, tuple[int, int, int]]]] the Python\n"
"loop builds, bit for bit.");

static PyObject *
build_cells(PyObject *Py_UNUSED(self), PyObject *args)
{
    int cols, rows, vr, vg, vb;
    double t, freq, tspeed, tslow, palette, hue0, spread, noise, amp;
    int tick, period, crest;
    double phase, dark_limit, spark_limit, saturation;
    PyObject *band, *sparks, *prepared_x, *prepared_y;
    int thin, digit, digit_tick, noise_on, noise_tick, spark_left;
    double digit_mix, fdx, fdy;
    PyObject *recipe_obj = Py_None;
    PyObject *calm_obj = Py_None;
    PyObject *curiosities_obj = Py_None;
    int calm = 0, cur_tick = 0;
    double shimmer_blend = 0.0, swell_freq = 0.0, swell_shift = 0.0, inv_span = 1.0;
    double hue_drift = 0.0, cur_blend = 0.0;
    static double recipe_table[3 * MAX_RECIPE];
    int recipe_n = 0;

    if (!PyArg_ParseTuple(args,
                          "iid(iii)"
                          "dddddddd"   /* freq tspeed tslow palette hue0 spread noise amp */
                          "iii"        /* tick period crest */
                          "dddd"       /* phase dark_limit spark_limit saturation */
                          "OOOO"       /* band sparks prepared_x prepared_y */
                          "ppdipiidd"  /* thin digit digit_mix digit_tick noise_on noise_tick spark_left fdx fdy */
                          "|OO",       /* recipe_table, calm_args */
                          &cols, &rows, &t, &vr, &vg, &vb,
                          &freq, &tspeed, &tslow, &palette, &hue0, &spread, &noise, &amp,
                          &tick, &period, &crest,
                          &phase, &dark_limit, &spark_limit, &saturation,
                          &band, &sparks, &prepared_x, &prepared_y,
                          &thin, &digit, &digit_mix, &digit_tick, &noise_on, &noise_tick,
                          &spark_left, &fdx, &fdy, &recipe_obj, &calm_obj)) {
        return NULL;
    }
    if (calm_obj != Py_None) {
        if (!PyArg_ParseTuple(calm_obj, "dddddidO",
                              &shimmer_blend, &swell_freq, &swell_shift, &inv_span,
                              &hue_drift, &cur_tick, &cur_blend, &curiosities_obj)) {
            return NULL;
        }
        calm = 1;
    }
    if (recipe_obj != Py_None) {
        Py_ssize_t len = PySequence_Size(recipe_obj);
        if (len < 3 || len % 3 != 0 || len > 3 * MAX_RECIPE) {
            PyErr_SetString(PyExc_ValueError, "recipe_table must hold 1..1024 (r, g, b) triples");
            return NULL;
        }
        for (Py_ssize_t i = 0; i < len; i++) {
            PyObject *item = PySequence_GetItem(recipe_obj, i);
            if (item == NULL) {
                return NULL;
            }
            recipe_table[i] = PyFloat_AsDouble(item);
            Py_DECREF(item);
            if (recipe_table[i] == -1.0 && PyErr_Occurred()) {
                return NULL;
            }
        }
        recipe_n = (int)(len / 3);
    }
    if (cols < 1 || cols > MAX_COLS || rows < 1 || rows > MAX_ROWS) {
        PyErr_Format(PyExc_ValueError, "unsupported grid geometry %dx%d", cols, rows);
        return NULL;
    }

    PyObject *result = NULL;
    PyObject *blank_char = NULL;
    PyObject *band_chars[MAX_BAND] = {0};
    PyObject *spark_chars[MAX_SPARKS] = {0};
    PyObject *cur_chars[MAX_CURIOSITIES] = {0};
    PyObject *digit_chars[10] = {0};
    Py_ssize_t cur_len = 0;
    long px[MAX_COLS], py[MAX_ROWS];
    double xs[MAX_COLS][7], ys[MAX_ROWS][5];
    double x3c = .37 * fdx - .21 * fdy;
    double y3c = .37 * fdy + .21 * fdx;

    Py_ssize_t band_len = PySequence_Size(band);
    Py_ssize_t sparks_len = PySequence_Size(sparks);
    if (band_len < 1 || band_len > MAX_BAND || sparks_len < 1 || sparks_len > MAX_SPARKS) {
        PyErr_SetString(PyExc_ValueError, "unsupported band or sparks length");
        goto done;
    }
    if (calm) {
        cur_len = PySequence_Size(curiosities_obj);
        if (cur_len < 1 || cur_len > MAX_CURIOSITIES) {
            PyErr_SetString(PyExc_ValueError, "unsupported curiosities length");
            goto done;
        }
        for (Py_ssize_t i = 0; i < cur_len; i++) {
            cur_chars[i] = PySequence_GetItem(curiosities_obj, i);
            if (cur_chars[i] == NULL) {
                goto done;
            }
        }
    }
    int band_last = (int)band_len - 1;
    blank_char = PyUnicode_FromOrdinal(32);
    if (blank_char == NULL) {
        goto done;
    }
    for (Py_ssize_t i = 0; i < band_len; i++) {
        band_chars[i] = PySequence_GetItem(band, i);
        if (band_chars[i] == NULL) {
            goto done;
        }
    }
    for (Py_ssize_t i = 0; i < sparks_len; i++) {
        spark_chars[i] = PySequence_GetItem(sparks, i);
        if (spark_chars[i] == NULL) {
            goto done;
        }
    }
    for (int i = 0; i < 10; i++) {
        digit_chars[i] = PyUnicode_FromOrdinal(48 + i);
        if (digit_chars[i] == NULL) {
            goto done;
        }
    }
    if (!PySequence_Check(prepared_x) || PySequence_Size(prepared_x) != cols ||
        !PySequence_Check(prepared_y) || PySequence_Size(prepared_y) != rows) {
        PyErr_SetString(PyExc_ValueError, "prepared axes do not match the grid");
        goto done;
    }
    for (int x = 0; x < cols; x++) {
        PyObject *item = PySequence_GetItem(prepared_x, x);
        if (item == NULL) {
            goto done;
        }
        long value = -1;
        if (item != Py_None) {
            value = PyLong_AsLong(item);
            if (PyErr_Occurred()) {
                Py_DECREF(item);
                goto done;
            }
            if (value < 0 || value >= cols) {
                Py_DECREF(item);
                PyErr_SetString(PyExc_IndexError, "list index out of range");
                goto done;
            }
        }
        px[x] = value;
        Py_DECREF(item);
    }
    for (int y = 0; y < rows; y++) {
        PyObject *item = PySequence_GetItem(prepared_y, y);
        if (item == NULL) {
            goto done;
        }
        long value = -1;
        if (item != Py_None) {
            value = PyLong_AsLong(item);
            if (PyErr_Occurred()) {
                Py_DECREF(item);
                goto done;
            }
            if (value < 0 || value >= rows) {
                Py_DECREF(item);
                PyErr_SetString(PyExc_IndexError, "list index out of range");
                goto done;
            }
        }
        py[y] = value;
        Py_DECREF(item);
    }

    /* Axis tables from prepare_cell; one entry per column/row, same order. */
    unsigned long long tick1 = (unsigned long long)((tick + 1) & 0x3FFFFFFF);
    int cur_tick1 = (cur_tick + 1) & 0x3FFFFFFF;
    if (calm) {
        double hue_origin = hue0 + hue_drift;
        for (int x = 0; x < cols; x++) {
            double fraction = (double)x / (double)cols;
            xs[x][0] = x * freq * fdx;
            xs[x][1] = x * -fdy;
            xs[x][2] = x * x3c;
            xs[x][3] = x * fdx;
            xs[x][4] = .12 * sin(fraction * 6.283 * palette + tslow);
            xs[x][5] = hue_origin + fraction * spread * 1.48 + .10 * sin(fraction * 10.166407384630519 - tslow * .61);
            xs[x][6] = pmod1(hue_origin + fraction * spread * 1.48);
        }
        for (int y = 0; y < rows; y++) {
            double yf = (double)y / (double)rows;
            ys[y][0] = y * freq * fdy;
            ys[y][1] = y * fdx;
            ys[y][2] = y * y3c;
            ys[y][3] = y * fdy;
            ys[y][4] = yf * .44 + .08 * sin(yf * 8.885765876316732 + tslow * .47);
        }
    } else {
        for (int x = 0; x < cols; x++) {
            double fraction = (double)x / (double)cols;
            xs[x][0] = x * freq * fdx;
            xs[x][1] = x * -fdy;
            xs[x][2] = x * x3c;
            xs[x][3] = x * fdx;
            xs[x][4] = .16 * sin(fraction * 6.283 * palette + tslow);
            xs[x][5] = hue0 + fraction * spread * .85;
            xs[x][6] = pmod1(hue0 + fraction * spread);
        }
        for (int y = 0; y < rows; y++) {
            ys[y][0] = y * freq * fdy;
            ys[y][1] = y * fdx;
            ys[y][2] = y * y3c;
            ys[y][3] = y * fdy;
            ys[y][4] = ((double)y / (double)rows) * .05;
        }
    }

    int digit_tone[3], noise_tone[3];
    hsv_to_rgb(digit_tone, pmod1(hue0 + 0.17), 0.35, 0.7);
    hsv_to_rgb(noise_tone, 0.52, 0.2, 1.0);

    result = PyList_New(rows);
    if (result == NULL) {
        goto done;
    }
    for (int y = 0; y < rows; y++) {
        PyObject *row = PyList_New(cols);
        if (row == NULL) {
            Py_DECREF(result);
            result = NULL;
            goto done;
        }
        for (int x = 0; x < cols; x++) {
            Py_INCREF(Py_None);
            if (PyList_SetItem(row, x, Py_None) < 0) {
                Py_DECREF(row);
                Py_DECREF(result);
                result = NULL;
                goto done;
            }
        }
        if (PyList_SetItem(result, y, row) < 0) {
            Py_DECREF(row);
            Py_DECREF(result);
            result = NULL;
            goto done;
        }
        long sy = py[y];
        int sy_valid = sy >= 0;
        for (int x = 0; x < cols; x++) {
            PyObject *ch;
            int fg[3];
            if (thin && ((x + y * 3) % 3) != 0) {
                ch = blank_char;
                fg[0] = vr; fg[1] = vg; fg[2] = vb;
            } else {
                long sx = px[x];
                if (!sy_valid || sx < 0) {
                    ch = blank_char;
                    fg[0] = vr; fg[1] = vg; fg[2] = vb;
                } else if (calm) {
                    double xw = xs[sx][0], xn = xs[sx][1], x3 = xs[sx][2], xp = xs[sx][3];
                    double palette_wave = xs[sx][4], hue_base = xs[sx][5], dark_hue = xs[sx][6];
                    double yw = ys[sy][0], yc = ys[sy][1], y3 = ys[sy][2], yp = ys[sy][3], hue_y = ys[sy][4];
                    double w1 = sin(xw + yw + tspeed);
                    double w2 = sin((xn + yc) * freq * 1.37 - tspeed * .83);
                    double w3 = sin((x3 + y3) * freq * 2.1 + phase);
                    double warp = sin((xw + yw) * .5 + w2 * amp);
                    double value = (w1 * .46 + w2 * .34 + w3 * .22) * (.62 + .38 * warp);
                    value += palette_wave;
                    double n0 = hashmix((unsigned long long)sx, (unsigned long long)sy, (unsigned long long)tick);
                    double n1 = hashmix((unsigned long long)sx, (unsigned long long)sy, tick1);
                    double n = n0 + (n1 - n0) * shimmer_blend;
                    value += (n - .5) * noise * .18;
                    double sw = .5 + .5 * sin(((xp + yp) - swell_shift) * swell_freq);
                    value += .11 * (sw * sw * sw);
                    double light = clamp01(.5 + .5 * value);
                    int sparked = 0;
                    if (light < dark_limit) {
                        double cn0 = hashmix((unsigned long long)sx, (unsigned long long)sy, (unsigned long long)cur_tick);
                        double cn1 = hashmix((unsigned long long)sx, (unsigned long long)sy, (unsigned long long)cur_tick1);
                        double a0 = (cn0 - .875) * 8.0 * (1.0 - cur_blend);
                        double a1 = (cn1 - .875) * 8.0 * cur_blend;
                        double c_raw = a0 >= a1 ? a0 : a1;
                        if (c_raw > 0.0) {
                            int c_slot = a0 >= a1 ? cur_tick : cur_tick1;
                            double c_strength = clamp01(c_raw);
                            int c_idx = (int)(((long)sx * 11L + (long)sy * 23L + (long)(c_slot & 0xFFFF) * 5L) % (long)cur_len);
                            ch = cur_chars[c_idx];
                            double c_hue = pmod1(dark_hue + .37 + .46 * w2 + .22 * w1 + hue_y);
                            double c_sat = .84, c_val = .58 + .42 * c_strength;
                            if (recipe_n) {
                                recipe_rgb(fg, recipe_table, recipe_n, c_hue, c_sat, c_val);
                            } else {
                                hsv_to_rgb(fg, c_hue, c_sat, c_val);
                            }
                        } else {
                            ch = blank_char;
                            hsv_to_rgb(fg, dark_hue, .35, .02);
                        }
                    } else {
                        double reach = clamp01((light - dark_limit) * inv_span);
                        double shaped = reach * (.64 + .36 * reach);
                        int index = (int)(shaped * band_last);
                        if (index < 0) {
                            index = 0;
                        }
                        if (index > band_last) {
                            index = band_last;
                        }
                        ch = band_chars[index];
                        if (n > spark_limit && reach > .26) {
                            ch = spark_chars[(int)((sx * 7 + sy * 13) % (long)sparks_len)];
                            sparked = 1;
                        }
                        double hue = pmod1(hue_base + .34 * value + .24 * warp + .14 * shaped + hue_y);
                        double sat, val;
                        if (sparked) {
                            hue = pmod1(hue + .41);
                            double twinkle = clamp01((n - spark_limit) * 28.0);
                            sat = .72; val = .82 + .18 * twinkle;
                        } else {
                            sat = saturation * (1.0 - .06 * shaped);
                            val = .56 + .43 * (reach * (1.22 - .22 * reach));
                        }
                        if (recipe_n) {
                            recipe_rgb(fg, recipe_table, recipe_n, hue, sat, val);
                        } else {
                            hsv_to_rgb(fg, hue, sat, val);
                        }
                    }
                } else {
                    double xw = xs[sx][0], xn = xs[sx][1], x3 = xs[sx][2], xp = xs[sx][3];
                    double palette_wave = xs[sx][4], hue_base = xs[sx][5], dark_hue = xs[sx][6];
                    double yw = ys[sy][0], yc = ys[sy][1], y3 = ys[sy][2], yp = ys[sy][3], hue_y = ys[sy][4];
                    double w1 = sin(xw + yw + tspeed);
                    double w2 = sin((xn + yc) * freq * 1.37 - tspeed * .83);
                    double w3 = sin((x3 + y3) * freq * 2.1 + phase);
                    double warp = sin((xw + yw) * .5 + w2 * amp);
                    double value = (w1 * .46 + w2 * .34 + w3 * .22) * (.62 + .38 * warp);
                    value += palette_wave;
                    double n = hashmix((unsigned long long)sx, (unsigned long long)sy, (unsigned long long)tick);
                    value += (n - .5) * noise * .95;
                    if (period > 0) {
                        long pcol = (long)(xp + yp);
                        long rem = pcol % period;
                        if (rem < 0) {
                            rem += period;
                        }
                        if (rem == crest) {
                            value += .22;
                        }
                    }
                    double light = clamp01(.5 + .5 * value);
                    int sparked = 0;
                    if (light < dark_limit) {
                        ch = blank_char;
                        hsv_to_rgb(fg, dark_hue, .35, .02);
                    } else {
                        int index = (int)(light * band_last);
                        if (index < 0) {
                            index = 0;
                        }
                        if (index > band_last) {
                            index = band_last;
                        }
                        ch = band_chars[index];
                        if (n > spark_limit && light > .34) {
                            ch = spark_chars[(int)(n * 997) % (int)sparks_len];
                            sparked = 1;
                        }
                        double hue = pmod1(hue_base + .08 * value + hue_y);
                        double sat, val;
                        if (sparked) {
                            hue = pmod1(hue * .35 + .52);
                            sat = .22; val = 1.0;
                        } else {
                            sat = saturation; val = .12 + .88 * light;
                        }
                        if (recipe_n && !sparked) {
                            recipe_rgb(fg, recipe_table, recipe_n, hue, sat, val);
                        } else {
                            hsv_to_rgb(fg, hue, sat, val);
                        }
                    }
                }
                if (digit) {
                    if (hashmix((unsigned long long)x, (unsigned long long)y, (unsigned long long)digit_tick) > 0.94) {
                        ch = digit_chars[(int)(hashmix((unsigned long long)x, (unsigned long long)y, 7ULL) * 10) % 10];
                    }
                    int mixed[3];
                    mix_rgb(mixed, fg, digit_tone, digit_mix);
                    fg[0] = mixed[0]; fg[1] = mixed[1]; fg[2] = mixed[2];
                }
                if (noise_on && hashmix((unsigned long long)x, (unsigned long long)y, (unsigned long long)noise_tick) > 0.86) {
                    if (spark_left < 0 || spark_left > 0) {
                        ch = spark_chars[x % (int)sparks_len];
                        fg[0] = noise_tone[0]; fg[1] = noise_tone[1]; fg[2] = noise_tone[2];
                        if (spark_left > 0) {
                            spark_left--;
                        }
                    }
                }
            }
            PyObject *rgb = PyTuple_New(3);
            PyObject *r0 = rgb == NULL ? NULL : PyLong_FromLong(fg[0]);
            PyObject *r1 = rgb == NULL ? NULL : PyLong_FromLong(fg[1]);
            PyObject *r2 = rgb == NULL ? NULL : PyLong_FromLong(fg[2]);
            if (rgb == NULL || r0 == NULL || r1 == NULL || r2 == NULL) {
                Py_XDECREF(r0); Py_XDECREF(r1); Py_XDECREF(r2);
                Py_XDECREF(rgb);
                Py_DECREF(result);
                result = NULL;
                goto done;
            }
            PyTuple_SetItem(rgb, 0, r0);
            PyTuple_SetItem(rgb, 1, r1);
            PyTuple_SetItem(rgb, 2, r2);
            PyObject *pair = PyTuple_New(2);
            if (pair == NULL) {
                Py_DECREF(rgb);
                Py_DECREF(result);
                result = NULL;
                goto done;
            }
            Py_INCREF(ch);
            PyTuple_SetItem(pair, 0, ch);
            PyTuple_SetItem(pair, 1, rgb);
            if (PyList_SetItem(row, x, pair) < 0) {
                Py_DECREF(pair);
                Py_DECREF(result);
                result = NULL;
                goto done;
            }
        }
    }

done:
    Py_XDECREF(blank_char);
    for (Py_ssize_t i = 0; i < band_len; i++) {
        Py_XDECREF(band_chars[i]);
    }
    for (Py_ssize_t i = 0; i < sparks_len; i++) {
        Py_XDECREF(spark_chars[i]);
    }
    for (Py_ssize_t i = 0; i < cur_len; i++) {
        Py_XDECREF(cur_chars[i]);
    }
    for (int i = 0; i < 10; i++) {
        Py_XDECREF(digit_chars[i]);
    }
    return result;
}

/* ---------- shared helpers for the ripple, post and encode passes ------ */

#include <limits.h>

/* Read `char, fg = cells[y][x]` where fg is a 3-channel int sequence.
 * *fast_out keeps the unpacking alive so *ch stays a valid borrowed ref;
 * the caller must Py_DECREF(*fast_out) when done with *ch. Channel values
 * that overflow C long are saturated far from the 0..255 range so the
 * min(255, ...) lifts still land exactly like Python's unbounded ints. */
static int
cell_read(PyObject *pair, PyObject **ch, PyObject **fast_out, long fg[3])
{
    PyObject *fast = PySequence_Fast(pair, "cell is not iterable");
    if (fast == NULL) {
        return -1;
    }
    Py_ssize_t n = fast_size(fast);
    if (n != 2) {
        Py_ssize_t got = n;
        Py_DECREF(fast);
        if (got > 2) {
            PyErr_SetString(PyExc_ValueError,
                            "too many values to unpack (expected 2)");
        } else {
            PyErr_Format(PyExc_ValueError,
                         "not enough values to unpack (expected 2, got %zd)",
                         got);
        }
        return -1;
    }
    PyObject *rfast = PySequence_Fast(fast_item(fast, 1),
                                    "rgb is not iterable");
    if (rfast == NULL) {
        Py_DECREF(fast);
        return -1;
    }
    if (fast_size(rfast) != 3) {
        Py_DECREF(rfast);
        Py_DECREF(fast);
        PyErr_SetString(PyExc_ValueError, "rgb must hold 3 channels");
        return -1;
    }
    for (int i = 0; i < 3; i++) {
        int of = 0;
        long v = PyLong_AsLongAndOverflow(fast_item(rfast, i),
                                        &of);
        if (v == -1 && PyErr_Occurred()) {
            Py_DECREF(rfast);
            Py_DECREF(fast);
            return -1;
        }
        if (of > 0) {
            v = LONG_MAX - 4096;
        } else if (of < 0) {
            v = LONG_MIN + 4096;
        }
        fg[i] = v;
    }
    Py_DECREF(rfast);
    *ch = fast_item(fast, 0);   /* borrowed, fast kept alive */
    *fast_out = fast;
    return 0;
}

/* cells[y][x] = (char, (r, g, b)). Always consumes the `ch` reference
 * (PyList_SetItem steal / decref semantics included). */
static int
row_store(PyObject *row, Py_ssize_t x, PyObject *ch, const long fg[3])
{
    PyObject *rgb = PyTuple_New(3);
    if (rgb == NULL) {
        Py_DECREF(ch);
        return -1;
    }
    for (int i = 0; i < 3; i++) {
        PyObject *v = PyLong_FromLong(fg[i]);
        if (v == NULL) {
            Py_DECREF(rgb);
            Py_DECREF(ch);
            return -1;
        }
        PyTuple_SetItem(rgb, i, v);
    }
    PyObject *pair = PyTuple_New(2);
    if (pair == NULL) {
        Py_DECREF(rgb);
        Py_DECREF(ch);
        return -1;
    }
    PyTuple_SetItem(pair, 0, ch);
    PyTuple_SetItem(pair, 1, rgb);
    if (PyList_CheckExact(row)) {
        /* steals pair on success; decrefs pair itself on bounds failure */
        return PyList_SetItem(row, x, pair);
    }
    PyObject *ix = PyLong_FromSsize_t(x);
    int rc = -1;
    if (ix != NULL) {
        rc = PyObject_SetItem(row, ix, pair);
        Py_DECREF(ix);
    }
    Py_DECREF(pair);
    return rc;
}

/* cells[y][x][0] as an owned ref, with the same indexing failure modes. */
static PyObject *
cell_char_at(PyObject *cells_fast, Py_ssize_t x, Py_ssize_t y)
{
    PyObject *row = fast_item(cells_fast, y);
    PyObject *rfast = PySequence_Fast(row, "row is not iterable");
    if (rfast == NULL) {
        return NULL;
    }
    if (x < 0 || x >= fast_size(rfast)) {
        Py_DECREF(rfast);
        PyErr_SetString(PyExc_IndexError, "list index out of range");
        return NULL;
    }
    PyObject *pfast = PySequence_Fast(fast_item(rfast, x),
                                    "cell is not iterable");
    Py_DECREF(rfast);
    if (pfast == NULL) {
        return NULL;
    }
    if (fast_size(pfast) < 1) {
        Py_DECREF(pfast);
        PyErr_SetString(PyExc_IndexError, "tuple index out of range");
        return NULL;
    }
    PyObject *ch = Py_NewRef(fast_item(pfast, 0));
    Py_DECREF(pfast);
    return ch;
}

/* rip.get(name, fallback) / rip[name] with dict fast paths and the same
 * KeyError/AttributeError shape the Python attribute access produces. */
static PyObject *
rip_field(PyObject *rip, const char *name, PyObject *fallback)
{
    PyObject *key = PyUnicode_FromString(name);
    if (key == NULL) {
        return NULL;
    }
    PyObject *value;
    if (PyDict_CheckExact(rip)) {
        value = PyDict_GetItemWithError(rip, key);
        if (value == NULL) {
            if (PyErr_Occurred()) {
                Py_DECREF(key);
                return NULL;
            }
            if (fallback == NULL) {
                PyErr_SetObject(PyExc_KeyError, key);
                Py_DECREF(key);
                return NULL;
            }
            Py_DECREF(key);
            return Py_NewRef(fallback);
        }
        Py_DECREF(key);
        return Py_NewRef(value);
    }
    if (fallback == NULL) {
        value = PyObject_GetItem(rip, key);
        Py_DECREF(key);
        return value;
    }
    PyObject *m = PyObject_GetAttrString(rip, "get");
    if (m == NULL) {
        Py_DECREF(key);
        return NULL;
    }
    value = PyObject_CallFunctionObjArgs(m, key, fallback, NULL);
    Py_DECREF(m);
    Py_DECREF(key);
    return value;
}

/* mix_rgb over long channels — same clamp01 + truncated lerp, keeps the
 * saturated huge-int cells on the same int() path as Python. */
static void
mix_rgb_l(long out[3], const long a[3], const long b[3], double amount)
{
    amount = clamp01(amount);
    double keep = 1.0 - amount;
    out[0] = (long)((double)a[0] * keep + (double)b[0] * amount);
    out[1] = (long)((double)a[1] * keep + (double)b[1] * amount);
    out[2] = (long)((double)a[2] * keep + (double)b[2] * amount);
}

/* tuple(min(255, c + d) for c in fg) — upper-bound lift only. */
static void
add_min255(long out[3], const long fg[3], long d)
{
    for (int i = 0; i < 3; i++) {
        long v = fg[i] + d;
        out[i] = v > 255 ? 255 : v;
    }
}

static double
luminance(const long fg[3])
{
    return (0.2126 * (double)fg[0] + 0.7152 * (double)fg[1]
            + 0.0722 * (double)fg[2]) / 255.0;
}

/* ------------------------ paint_ripples ------------------------------- */

typedef struct {
    PyObject *rip;      /* borrowed from the ripples sequence */
    double cx, cy, radius, band, outer, dy;
    int kind;           /* 0 authority, 1 unauthority, 2 residue */
    int cand;
    long glow;          /* interior crest lift; residue keeps 0 */
    double hot;         /* hue the crest pushes toward on bright cells */
} Rip;

typedef struct {
    Py_ssize_t x, y;
    PyObject *ch;       /* owned */
    long fg[3];
} Mark;

static int
mark_push(Mark **arr, Py_ssize_t *n, Py_ssize_t *cap,
          Py_ssize_t x, Py_ssize_t y, PyObject *ch /* steals */,
          const long fg[3])
{
    if (*n == *cap) {
        Py_ssize_t ncap = *cap ? *cap * 2 : 64;
        Mark *narr = PyMem_Realloc(*arr, (size_t)ncap * sizeof(Mark));
        if (narr == NULL) {
            Py_DECREF(ch);
            PyErr_NoMemory();
            return -1;
        }
        *arr = narr;
        *cap = ncap;
    }
    Mark *m = &(*arr)[(*n)++];
    m->x = x;
    m->y = y;
    m->ch = ch;
    m->fg[0] = fg[0];
    m->fg[1] = fg[1];
    m->fg[2] = fg[2];
    return 0;
}

PyDoc_STRVAR(paint_ripples_doc,
"paint_ripples(cells, cols, rows, t, ripples, hue, sparks, blocks, flow_a)\n"
"\n"
"In-place ripple painting identical to fast_ripples' method: prepared\n"
"radii, per-row candidate culling, authority/unauthority/residue\n"
"precedence, then the deferred ghost and residue passes. A finite\n"
"flow_a drifts each ring centre along its own hashed bearing; a\n"
"non-finite flow_a keeps the plain fx/fy centre.");

static PyObject *
paint_ripples(PyObject *Py_UNUSED(self), PyObject *args)
{
    PyObject *cells, *ripples, *sparks, *blocks;
    Py_ssize_t cols, rows;
    double t, hue, flow_a;
    if (!PyArg_ParseTuple(args, "OnndOdOOd",
                          &cells, &cols, &rows, &t, &ripples, &hue,
                          &sparks, &blocks, &flow_a)) {
        return NULL;
    }

    PyObject *cells_fast = NULL, *rips_fast = NULL, *row_fast = NULL;
    PyObject *cellkeep = NULL, *newch = NULL, *middot = NULL, *zero_f = NULL;
    Rip *prepared = NULL;
    Mark *ghosts = NULL, *marks = NULL;
    Py_ssize_t np = 0, n_ghosts = 0, n_marks = 0, cap_ghosts = 0, cap_marks = 0;
    Py_ssize_t sparks_len;
    PyObject *result = NULL;

    middot = PyUnicode_FromString("\xc2\xb7");
    zero_f = PyFloat_FromDouble(0.0);
    if (middot == NULL || zero_f == NULL) {
        goto fail;
    }
    cells_fast = PySequence_Fast(cells, "cells is not a sequence");
    if (cells_fast == NULL) {
        goto fail;
    }
    rips_fast = PySequence_Fast(ripples, "ripples is not a sequence");
    if (rips_fast == NULL) {
        goto fail;
    }
    sparks_len = PySequence_Size(sparks);
    if (sparks_len < 1) {
        PyErr_SetString(PyExc_ValueError, "sparks must be non-empty");
        goto fail;
    }
    Py_ssize_t have_rows = fast_size(cells_fast);
    Py_ssize_t n_rips = fast_size(rips_fast);
    prepared = PyMem_Malloc((size_t)(n_rips ? n_rips : 1) * sizeof(Rip));
    if (prepared == NULL) {
        PyErr_NoMemory();
        goto fail;
    }
    PyObject *ua = PyUnicode_FromString("unauthority");
    PyObject *rs = PyUnicode_FromString("residue");
    if (ua == NULL || rs == NULL) {
        Py_XDECREF(ua);
        Py_XDECREF(rs);
        goto fail;
    }
    for (Py_ssize_t i = 0; i < n_rips; i++) {
        PyObject *rip = fast_item(rips_fast, i);
        PyObject *ro = rip_field(rip, "r", zero_f);
        if (ro == NULL) {
            Py_DECREF(ua); Py_DECREF(rs);
            goto fail;
        }
        double radius = PyFloat_AsDouble(ro);
        Py_DECREF(ro);
        if (radius == -1.0 && PyErr_Occurred()) {
            Py_DECREF(ua); Py_DECREF(rs);
            goto fail;
        }
        if (radius < 0.0) {
            continue;
        }
        PyObject *ko = rip_field(rip, "auth", Py_None);
        if (ko == NULL) {
            Py_DECREF(ua); Py_DECREF(rs);
            goto fail;
        }
        int kind = 0;
        int cmp = PyObject_RichCompareBool(ko, ua, Py_EQ);
        if (cmp < 0) {
            Py_DECREF(ko); Py_DECREF(ua); Py_DECREF(rs);
            goto fail;
        } else if (cmp) {
            kind = 1;
        } else {
            cmp = PyObject_RichCompareBool(ko, rs, Py_EQ);
            if (cmp < 0) {
                Py_DECREF(ko); Py_DECREF(ua); Py_DECREF(rs);
                goto fail;
            } else if (cmp) {
                kind = 2;
            }
        }
        Py_DECREF(ko);
        double band;
        if (kind == 1) {
            band = 1.7;
        } else if (kind == 2) {
            band = 1.25;
        } else {
            PyObject *ao = rip_field(rip, "amp", Py_None);
            if (ao == NULL) {
                Py_DECREF(ua); Py_DECREF(rs);
                goto fail;
            }
            int a = PyObject_IsTrue(ao);
            Py_DECREF(ao);
            if (a < 0) {
                Py_DECREF(ua); Py_DECREF(rs);
                goto fail;
            }
            band = a ? 0.48 : 0.68;
        }
        PyObject *fxo = rip_field(rip, "fx", NULL);
        if (fxo == NULL) {
            Py_DECREF(ua); Py_DECREF(rs);
            goto fail;
        }
        double fx = PyFloat_AsDouble(fxo);
        Py_DECREF(fxo);
        if (fx == -1.0 && PyErr_Occurred()) {
            Py_DECREF(ua); Py_DECREF(rs);
            goto fail;
        }
        PyObject *fyo = rip_field(rip, "fy", NULL);
        if (fyo == NULL) {
            Py_DECREF(ua); Py_DECREF(rs);
            goto fail;
        }
        double fy = PyFloat_AsDouble(fyo);
        Py_DECREF(fyo);
        if (fy == -1.0 && PyErr_Occurred()) {
            Py_DECREF(ua); Py_DECREF(rs);
            goto fail;
        }
        Rip *p = &prepared[np++];
        p->rip = rip;
        p->cx = fx * (double)cols;
        p->cy = fy * (double)rows;
        if (isfinite(flow_a) && isfinite(fx) && isfinite(fy)) {
            double fmx = fmod(fx * 4096.0, 65536.0);
            if (fmx < 0.0) {
                fmx += 65536.0;
            }
            double fmy = fmod(fy * 4096.0, 65536.0);
            if (fmy < 0.0) {
                fmy += 65536.0;
            }
            double h = hashmix((unsigned long long)(long)fmx,
                               (unsigned long long)(long)fmy, 11ULL);
            double da = flow_a + (h - 0.5) * (M_PI * 1.5);
            double rcap = (12.0 < radius) ? 12.0 : radius;
            double drift = rcap * 0.55;
            p->cx += cos(da) * drift;
            p->cy += sin(da) * drift * 0.5;
        }
        p->radius = radius;
        p->kind = kind;
        p->band = band;
        p->outer = nextafter(radius + band, INFINITY);
        p->dy = 0.0;
        p->cand = 0;
        p->glow = 0;
        if (kind != 2) {
            PyObject *lo = rip_field(rip, "life", Py_None);
            if (lo == NULL) {
                goto fail;
            }
            double lv = 0.0;
            int truthy = PyObject_IsTrue(lo);
            if (truthy < 0) {
                Py_DECREF(lo);
                goto fail;
            }
            if (truthy) {
                lv = PyFloat_AsDouble(lo);
                if (lv == -1.0 && PyErr_Occurred()) {
                    Py_DECREF(lo);
                    goto fail;
                }
            }
            Py_DECREF(lo);
            if (kind == 1) {
                p->glow = (long)(42.0 * clamp01((lv - 0.5) / 0.5));
                p->hot = pmod1(hue + 0.62);
            } else {
                p->glow = (long)(85.0 * clamp01((lv - 0.55) / 0.45));
                p->hot = pmod1(hue + 0.10);
            }
        }
    }
    Py_DECREF(ua);
    Py_DECREF(rs);
    if (np == 0) {
        result = Py_None;
        Py_INCREF(result);
        goto done;
    }

    long s17 = (long)(t * 17), s9 = (long)(t * 9);
    for (Py_ssize_t y = 0; y < rows; y++) {
        if (y >= have_rows) {
            PyErr_SetString(PyExc_IndexError, "list index out of range");
            goto fail;
        }
        for (Py_ssize_t i = 0; i < np; i++) {
            Rip *p = &prepared[i];
            p->dy = ((double)y - p->cy) * 2.0;
            p->cand = !isfinite(p->dy) || !isfinite(p->outer)
                      || fabs(p->dy) <= p->outer;
        }
        PyObject *row = fast_item(cells_fast, y);
        row_fast = PySequence_Fast(row, "row is not iterable");
        if (row_fast == NULL) {
            goto fail;
        }
        Py_ssize_t rowlen = fast_size(row_fast);
        for (Py_ssize_t x = 0; x < cols; x++) {
            if (x >= rowlen) {
                PyErr_SetString(PyExc_IndexError, "list index out of range");
                goto fail;
            }
            const Rip *auth = NULL, *ghost = NULL, *resid = NULL;
            long crest = 0;
            double crest_hot = 0.0;
            for (Py_ssize_t i = 0; i < np; i++) {
                const Rip *p = &prepared[i];
                if (!p->cand) {
                    continue;
                }
                double dx = (double)x - p->cx;
                if (isfinite(dx) && isfinite(p->outer) && fabs(dx) > p->outer) {
                    continue;
                }
                double dist = hypot(dx, p->dy);
                if (dist < p->radius && p->radius <= 2.6 && p->glow > crest) {
                    crest = p->glow;
                    crest_hot = p->hot;
                }
                if (fabs(dist - p->radius) < p->band) {
                    if (p->kind == 1) {
                        ghost = p;
                    } else if (p->kind == 2) {
                        resid = p;
                    } else {
                        auth = p;
                    }
                }
            }
            PyObject *cell = fast_item(row_fast, x);
            PyObject *ch;
            long fg[3];
            cellkeep = NULL;
            newch = NULL;
            if (cell_read(cell, &ch, &cellkeep, fg) < 0) {
                goto fail;
            }
            long newfg[3] = {fg[0], fg[1], fg[2]};
            int sparked = 0, changed = 0;
            if (ghost != NULL) {
                PyObject *ro = rip_field(ghost->rip, "r", NULL);
                if (ro == NULL) {
                    goto fail;
                }
                double rv = PyFloat_AsDouble(ro);
                Py_DECREF(ro);
                if (rv == -1.0 && PyErr_Occurred()) {
                    goto fail;
                }
                double flick = hashmix((unsigned long long)x,
                                       (unsigned long long)y,
                                       (unsigned long long)(s17 + (long)(rv * 10)));
                if (flick > 0.3) {
                    PyObject *spark = PySequence_GetItem(
                        sparks, (Py_ssize_t)(flick * 997) % sparks_len);
                    if (spark == NULL) {
                        goto fail;
                    }
                    int gfg[3];
                    hsv_to_rgb(gfg, pmod1(hue + 0.62), 0.14, 0.46);
                    long lgfg[3] = {gfg[0], gfg[1], gfg[2]};
                    if (auth != NULL) {
                        Py_ssize_t gx = x + 1 < cols ? x + 1 : x - 1;
                        if (gx != x) {
                            if (mark_push(&ghosts, &n_ghosts, &cap_ghosts,
                                          gx, y, spark, lgfg) < 0) {
                                goto fail;
                            }
                        } else {
                            Py_DECREF(spark);
                        }
                    } else {
                        newch = spark;
                        newfg[0] = lgfg[0];
                        newfg[1] = lgfg[1];
                        newfg[2] = lgfg[2];
                        sparked = 1;
                        changed = 1;
                        if (flick > 0.8) {
                            PyObject *s2 = PySequence_GetItem(
                                sparks, (Py_ssize_t)(flick * 13) % sparks_len);
                            if (s2 == NULL) {
                                goto fail;
                            }
                            Py_ssize_t gx = x + 1 < cols ? x + 1 : x - 1;
                            if (gx != x) {
                                if (mark_push(&ghosts, &n_ghosts, &cap_ghosts,
                                              gx, y, s2, lgfg) < 0) {
                                    goto fail;
                                }
                            } else {
                                Py_DECREF(s2);
                            }
                        }
                    }
                }
            }
            if (resid != NULL) {
                PyObject *ro = rip_field(resid->rip, "r", NULL);
                if (ro == NULL) {
                    goto fail;
                }
                double rv = PyFloat_AsDouble(ro);
                Py_DECREF(ro);
                if (rv == -1.0 && PyErr_Occurred()) {
                    goto fail;
                }
                double flick = hashmix((unsigned long long)x,
                                       (unsigned long long)y,
                                       (unsigned long long)(s9 + (long)(rv * 6)));
                PyObject *mark;
                if (flick < 0.58) {
                    mark = Py_NewRef(middot);
                } else {
                    mark = PySequence_GetItem(
                        sparks, (Py_ssize_t)(flick * 997) % sparks_len);
                    if (mark == NULL) {
                        goto fail;
                    }
                }
                int rfg[3];
                hsv_to_rgb(rfg, pmod1(hue + 0.48), 0.16, 0.36);
                long lrfg[3] = {rfg[0], rfg[1], rfg[2]};
                if (auth != NULL || sparked) {
                    Py_ssize_t rx = x + 1 < cols ? x + 1 : x - 1;
                    if (rx != x) {
                        if (mark_push(&marks, &n_marks, &cap_marks,
                                      rx, y, mark, lrfg) < 0) {
                            goto fail;
                        }
                    } else {
                        Py_DECREF(mark);
                    }
                } else {
                    Py_XDECREF(newch);
                    newch = mark;
                    newfg[0] = lrfg[0];
                    newfg[1] = lrfg[1];
                    newfg[2] = lrfg[2];
                    changed = 1;
                }
            }
            if (auth != NULL) {
                PyObject *ao = rip_field(auth->rip, "amp", Py_None);
                if (ao == NULL) {
                    goto fail;
                }
                int a = PyObject_IsTrue(ao);
                Py_DECREF(ao);
                if (a < 0) {
                    goto fail;
                }
                long level;
                double sat;
                if (a) {
                    level = 3;
                    sat = 0.95;
                } else {
                    PyObject *lo = rip_field(auth->rip, "life", NULL);
                    if (lo == NULL) {
                        goto fail;
                    }
                    double lv = PyFloat_AsDouble(lo);
                    Py_DECREF(lo);
                    if (lv == -1.0 && PyErr_Occurred()) {
                        goto fail;
                    }
                    level = (long)(clamp01(lv) * 3.99);
                    sat = 0.8;
                }
                long li = level < 0 ? 0 : (level > 3 ? 3 : level);
                Py_XDECREF(newch);
                newch = PySequence_GetItem(blocks, li);
                if (newch == NULL) {
                    goto fail;
                }
                int afg[3];
                hsv_to_rgb(afg, pmod1(hue + 0.04), sat, 1.0);
                newfg[0] = afg[0];
                newfg[1] = afg[1];
                newfg[2] = afg[2];
                changed = 1;
            }
            if (crest > 0) {
                long lum = newfg[0] > newfg[1]
                           ? (newfg[0] > newfg[2] ? newfg[0] : newfg[2])
                           : (newfg[1] > newfg[2] ? newfg[1] : newfg[2]);
                if (lum <= 168) {
                    add_min255(newfg, newfg, crest);
                } else {
                    double w = clamp01(((double)lum - 168.0) / 87.0)
                               * ((double)crest / 85.0);
                    int hoti[3];
                    hsv_to_rgb(hoti, pmod1(crest_hot), 0.95, 1.0);
                    long hotl[3] = {hoti[0], hoti[1], hoti[2]};
                    mix_rgb_l(newfg, newfg, hotl, w);
                }
                changed = 1;
            }
            if (changed) {
                PyObject *cw = newch != NULL ? newch : Py_NewRef(ch);
                newch = NULL;
                if (row_store(row, x, cw, newfg) < 0) {
                    goto fail;
                }
            }
            Py_XDECREF(newch);
            newch = NULL;
            Py_DECREF(cellkeep);
            cellkeep = NULL;
        }
        Py_DECREF(row_fast);
        row_fast = NULL;
    }

    for (Py_ssize_t i = 0; i < n_ghosts; i++) {
        Mark *m = &ghosts[i];
        if (!(0 <= m->x && m->x < cols && 0 <= m->y && m->y < rows)) {
            Py_DECREF(m->ch);
            m->ch = NULL;
            continue;
        }
        PyObject *row = fast_item(cells_fast, m->y);
        PyObject *ch = cell_char_at(cells_fast, m->x, m->y);
        if (ch == NULL) {
            goto fail;
        }
        int inb = PySequence_Contains(blocks, ch);
        Py_DECREF(ch);
        if (inb < 0) {
            goto fail;
        }
        if (inb) {
            Py_ssize_t nxt = m->x + 1 < cols ? m->x + 1 : m->x - 1;
            if (nxt != m->x) {
                PyObject *ch2 = cell_char_at(cells_fast, nxt, m->y);
                if (ch2 == NULL) {
                    goto fail;
                }
                int inb2 = PySequence_Contains(blocks, ch2);
                Py_DECREF(ch2);
                if (inb2 < 0) {
                    goto fail;
                }
                if (!inb2) {
                    m->x = nxt;
                }
            }
        }
        int rc = row_store(row, m->x, m->ch, m->fg);
        m->ch = NULL;
        if (rc < 0) {
            goto fail;
        }
    }
    for (Py_ssize_t i = 0; i < n_marks; i++) {
        Mark *m = &marks[i];
        if (!(0 <= m->x && m->x < cols && 0 <= m->y && m->y < rows)) {
            Py_DECREF(m->ch);
            m->ch = NULL;
            continue;
        }
        PyObject *row = fast_item(cells_fast, m->y);
        PyObject *ch = cell_char_at(cells_fast, m->x, m->y);
        if (ch == NULL) {
            goto fail;
        }
        int inb = PySequence_Contains(blocks, ch);
        Py_DECREF(ch);
        if (inb < 0) {
            goto fail;
        }
        if (inb) {
            Py_ssize_t nxt = m->x + 1 < cols ? m->x + 1 : m->x - 1;
            if (nxt != m->x) {
                PyObject *ch2 = cell_char_at(cells_fast, nxt, m->y);
                if (ch2 == NULL) {
                    goto fail;
                }
                int inb2 = PySequence_Contains(blocks, ch2);
                Py_DECREF(ch2);
                if (inb2 < 0) {
                    goto fail;
                }
                if (!inb2) {
                    m->x = nxt;
                } else {
                    Py_DECREF(m->ch);
                    m->ch = NULL;
                    continue;
                }
            } else {
                Py_DECREF(m->ch);
                m->ch = NULL;
                continue;
            }
        }
        PyObject *ch3 = cell_char_at(cells_fast, m->x, m->y);
        if (ch3 == NULL) {
            goto fail;
        }
        int inb3 = PySequence_Contains(blocks, ch3);
        Py_DECREF(ch3);
        if (inb3 < 0) {
            goto fail;
        }
        if (inb3) {
            Py_DECREF(m->ch);
            m->ch = NULL;
            continue;
        }
        int rc = row_store(row, m->x, m->ch, m->fg);
        m->ch = NULL;
        if (rc < 0) {
            goto fail;
        }
    }
    result = Py_None;
    Py_INCREF(result);
    goto done;

fail:
    Py_XDECREF(cellkeep);
    Py_XDECREF(newch);
    Py_XDECREF(row_fast);
    for (Py_ssize_t i = 0; i < n_ghosts; i++) {
        Py_XDECREF(ghosts[i].ch);
    }
    for (Py_ssize_t i = 0; i < n_marks; i++) {
        Py_XDECREF(marks[i].ch);
    }
done:
    PyMem_Free(prepared);
    PyMem_Free(ghosts);
    PyMem_Free(marks);
    Py_XDECREF(middot);
    Py_XDECREF(zero_f);
    Py_XDECREF(cells_fast);
    Py_XDECREF(rips_fast);
    return result;
}

/* ------------------------ post_cells ---------------------------------- */

PyDoc_STRVAR(post_cells_doc,
"post_cells(cells, cols, rows, scan, veil, veil_y, veil_tick, dream_mix,\n"
"           lift, trans)\n"
"\n"
"Second-pass veil/scan/lift rewrites plus glyph and luminance sampling,\n"
"with a transition trail row lifted behind the scan sweep while the\n"
"visual scale is morphing (trans > 0). Returns (chars, lights) exactly\n"
"like the Python loop; cells is mutated in place. veil is None or an\n"
"(r, g, b) triple.");

static PyObject *
post_cells(PyObject *Py_UNUSED(self), PyObject *args)
{
    PyObject *cells, *veil, *front;
    Py_ssize_t cols, rows, veil_y, lift;
    unsigned long long veil_tick;
    double dream_mix, trans;
    long front_lift = 36;
    if (!PyArg_ParseTuple(args, "OnnOOnKdnd|l",
                          &cells, &cols, &rows, &front, &veil, &veil_y,
                          &veil_tick, &dream_mix, &lift, &trans, &front_lift)) {
        return NULL;
    }
    Py_ssize_t fpos;
    double fdx, fdy, pmin;
    if (!PyArg_ParseTuple(front, "nddd", &fpos, &fdx, &fdy, &pmin)) {
        return NULL;
    }
    Py_ssize_t pspan = (Py_ssize_t)((double)(cols - 1) * fabs(fdx)
                                  + (double)(rows - 1) * fabs(fdy)) + 1;

    PyObject *cells_fast = NULL, *row_fast = NULL, *cellkeep = NULL;
    PyObject *newch = NULL, *space = NULL, *chars = NULL, *lights = NULL;
    PyObject *result = NULL;
    long veil_rgb[3] = {0, 0, 0};
    int have_veil = veil != Py_None;

    if (have_veil) {
        PyObject *vfast = PySequence_Fast(veil, "veil is not iterable");
        if (vfast == NULL) {
            goto fail;
        }
        if (fast_size(vfast) != 3) {
            Py_DECREF(vfast);
            PyErr_SetString(PyExc_ValueError, "veil must hold 3 channels");
            goto fail;
        }
        for (int i = 0; i < 3; i++) {
            int of = 0;
            long v = PyLong_AsLongAndOverflow(
                fast_item(vfast, i), &of);
            if (v == -1 && PyErr_Occurred()) {
                Py_DECREF(vfast);
                goto fail;
            }
            if (of > 0) {
                v = LONG_MAX - 4096;
            } else if (of < 0) {
                v = LONG_MIN + 4096;
            }
            veil_rgb[i] = v;
        }
        Py_DECREF(vfast);
    }

    space = PyUnicode_FromOrdinal(32);
    chars = PyList_New(0);
    lights = PyList_New(0);
    if (space == NULL || chars == NULL || lights == NULL) {
        goto fail;
    }
    cells_fast = PySequence_Fast(cells, "cells is not a sequence");
    if (cells_fast == NULL) {
        goto fail;
    }
    Py_ssize_t have_rows = fast_size(cells_fast);
    long trail_lift = trans > 0.0 ? (long)(54.0 * trans) : 0;
    long trail_lifts[3] = {trail_lift,
                           (long)((double)trail_lift * 0.55),
                           (long)((double)trail_lift * 0.30)};

    for (Py_ssize_t y = 0; y < rows; y++) {
        if (y >= have_rows) {
            PyErr_SetString(PyExc_IndexError, "list index out of range");
            goto fail;
        }
        int veil_row = have_veil && y == veil_y;
        double yfd = (double)y * fdy;
        PyObject *row = fast_item(cells_fast, y);
        row_fast = PySequence_Fast(row, "row is not iterable");
        if (row_fast == NULL) {
            goto fail;
        }
        Py_ssize_t rowlen = fast_size(row_fast);
        for (Py_ssize_t x = 0; x < cols; x++) {
            if (x >= rowlen) {
                PyErr_SetString(PyExc_IndexError, "list index out of range");
                goto fail;
            }
            Py_ssize_t p = (Py_ssize_t)((double)x * fdx + yfd - pmin);
            int front_cell = p == fpos;
            Py_ssize_t behind = ((fpos - p) % pspan + pspan) % pspan;
            long trail_amount = (trail_lift > 0 && behind >= 1 && behind <= 3)
                                ? trail_lifts[behind - 1] : 0;
            PyObject *cell = fast_item(row_fast, x);
            PyObject *ch;
            long fg[3];
            cellkeep = NULL;
            newch = NULL;
            if (cell_read(cell, &ch, &cellkeep, fg) < 0) {
                goto fail;
            }
            long newfg[3] = {fg[0], fg[1], fg[2]};
            int changed = 0;
            if (have_veil) {
                if (hashmix((unsigned long long)x, (unsigned long long)y,
                            veil_tick) > 0.955) {
                    Py_XDECREF(newch);
                    newch = PyUnicode_FromOrdinal(46);
                    if (newch == NULL) {
                        goto fail;
                    }
                }
                long mv[3];
                long a[3] = {newfg[0], newfg[1], newfg[2]};
                mix_rgb_l(mv, a, veil_rgb, dream_mix);
                newfg[0] = mv[0];
                newfg[1] = mv[1];
                newfg[2] = mv[2];
                changed = 1;
                PyObject *cur = newch != NULL ? newch : ch;
                int neq = PyObject_RichCompareBool(cur, space, Py_NE);
                if (neq < 0) {
                    goto fail;
                }
                if (veil_row && neq) {
                    add_min255(newfg, newfg, 28);
                }
            }
            PyObject *cur = newch != NULL ? newch : ch;
            if (front_cell && front_lift > 0) {
                int neq = PyObject_RichCompareBool(cur, space, Py_NE);
                if (neq < 0) {
                    goto fail;
                }
                if (neq) {
                    add_min255(newfg, newfg, front_lift);
                    changed = 1;
                }
            }
            if (trail_amount) {
                int neq = PyObject_RichCompareBool(cur, space, Py_NE);
                if (neq < 0) {
                    goto fail;
                }
                if (neq) {
                    add_min255(newfg, newfg, trail_amount);
                    changed = 1;
                }
            }
            if (lift) {
                add_min255(newfg, newfg, lift);
                changed = 1;
            }
            if (changed) {
                PyObject *cw = newch != NULL ? newch : Py_NewRef(cur);
                newch = NULL;
                if (row_store(row, x, cw, newfg) < 0) {
                    goto fail;
                }
            }
            Py_XDECREF(newch);
            newch = NULL;
            if (((x + y) & 3) == 0) {
                if (PyList_Append(chars, cur) < 0) {
                    goto fail;
                }
                PyObject *lv = PyFloat_FromDouble(luminance(newfg));
                if (lv == NULL) {
                    goto fail;
                }
                int rc = PyList_Append(lights, lv);
                Py_DECREF(lv);
                if (rc < 0) {
                    goto fail;
                }
            }
            Py_DECREF(cellkeep);
            cellkeep = NULL;
        }
        Py_DECREF(row_fast);
        row_fast = NULL;
    }
    result = PyTuple_Pack(2, chars, lights);
    goto done;

fail:
    Py_XDECREF(cellkeep);
    Py_XDECREF(newch);
    Py_XDECREF(row_fast);
done:
    Py_XDECREF(space);
    Py_XDECREF(chars);
    Py_XDECREF(lights);
    Py_XDECREF(cells_fast);
    return result;
}

/* ------------------------ encode_cells -------------------------------- */

PyDoc_STRVAR(encode_cells_doc,
"encode_cells(data, cells, cols, packet_error)\n"
"\n"
"Append every (char, rgb) cell to the bytearray as !IBBB, raising\n"
"packet_error('ragged grid' | 'invalid character' | 'invalid RGB value')\n"
"with the same ordering protocol.encode uses.");

static int
packet_fail(PyObject *err, const char *msg)
{
    PyErr_SetString(err, msg);
    return -1;
}

static PyObject *
encode_cells(PyObject *Py_UNUSED(self), PyObject *args)
{
    PyObject *data, *cells, *err;
    Py_ssize_t cols;
    if (!PyArg_ParseTuple(args, "OOnO", &data, &cells, &cols, &err)) {
        return NULL;
    }
    if (!PyByteArray_Check(data)) {
        PyErr_SetString(PyExc_TypeError, "data must be a bytearray");
        return NULL;
    }
    PyObject *rit = PyObject_GetIter(cells);
    if (rit == NULL) {
        return NULL;
    }
    PyObject *row;
    while ((row = PyIter_Next(rit)) != NULL) {
        Py_ssize_t n = PyObject_Length(row);
        if (n < 0) {
            Py_DECREF(row);
            goto fail;
        }
        if (n != cols) {
            packet_fail(err, "ragged grid");
            Py_DECREF(row);
            goto fail;
        }
        PyObject *cit = PyObject_GetIter(row);
        Py_DECREF(row);
        if (cit == NULL) {
            goto fail;
        }
        PyObject *item;
        while ((item = PyIter_Next(cit)) != NULL) {
            PyObject *ifast = PySequence_Fast(item, "cell is not iterable");
            Py_DECREF(item);
            if (ifast == NULL) {
                Py_DECREF(cit);
                goto fail;
            }
            Py_ssize_t isz = fast_size(ifast);
            if (isz != 2) {
                Py_DECREF(ifast);
                Py_DECREF(cit);
                if (isz > 2) {
                    PyErr_SetString(PyExc_ValueError,
                                    "too many values to unpack (expected 2)");
                } else {
                    PyErr_Format(PyExc_ValueError,
                                 "not enough values to unpack (expected 2, "
                                 "got %zd)", isz);
                }
                goto fail;
            }
            PyObject *ch = fast_item(ifast, 0);
            PyObject *rgb = fast_item(ifast, 1);
            if (!PyUnicode_Check(ch) || PyUnicode_GetLength(ch) != 1) {
                packet_fail(err, "invalid character");
                Py_DECREF(ifast);
                Py_DECREF(cit);
                goto fail;
            }
            Py_UCS4 code = PyUnicode_ReadChar(ch, 0);
            if (0xD800 <= code && code <= 0xDFFF) {
                packet_fail(err, "invalid character");
                Py_DECREF(ifast);
                Py_DECREF(cit);
                goto fail;
            }
            Py_ssize_t rn = PyObject_Length(rgb);
            if (rn < 0) {
                Py_DECREF(ifast);
                Py_DECREF(cit);
                goto fail;
            }
            if (rn != 3) {
                packet_fail(err, "invalid RGB value");
                Py_DECREF(ifast);
                Py_DECREF(cit);
                goto fail;
            }
            long vals[3];
            for (int i = 0; i < 3; i++) {
                PyObject *v;
                PyObject *owned = NULL;
                if (PyTuple_CheckExact(rgb)) {
                    v = PyTuple_GetItem(rgb, i);
                } else if (PyList_CheckExact(rgb)) {
                    v = PyList_GetItem(rgb, i);
                } else {
                    PyObject *ix = PyLong_FromLong(i);
                    if (ix == NULL) {
                        Py_DECREF(ifast);
                        Py_DECREF(cit);
                        goto fail;
                    }
                    owned = PyObject_GetItem(rgb, ix);
                    Py_DECREF(ix);
                    if (owned == NULL) {
                        Py_DECREF(ifast);
                        Py_DECREF(cit);
                        goto fail;
                    }
                    v = owned;
                }
                int ok = 0;
                if (PyLong_CheckExact(v)) {
                    int of = 0;
                    long vv = PyLong_AsLongAndOverflow(v, &of);
                    if (of == 0 && !PyErr_Occurred() && 0 <= vv && vv <= 255) {
                        vals[i] = vv;
                        ok = 1;
                    }
                }
                Py_XDECREF(owned);
                if (!ok) {
                    packet_fail(err, "invalid RGB value");
                    Py_DECREF(ifast);
                    Py_DECREF(cit);
                    goto fail;
                }
            }
            unsigned char buf[7];
            buf[0] = (unsigned char)(code >> 24);
            buf[1] = (unsigned char)(code >> 16);
            buf[2] = (unsigned char)(code >> 8);
            buf[3] = (unsigned char)code;
            buf[4] = (unsigned char)vals[0];
            buf[5] = (unsigned char)vals[1];
            buf[6] = (unsigned char)vals[2];
            Py_ssize_t sz = PyByteArray_Size(data);
            if (PyByteArray_Resize(data, sz + 7) < 0) {
                Py_DECREF(ifast);
                Py_DECREF(cit);
                goto fail;
            }
            memcpy(PyByteArray_AsString(data) + sz, buf, 7);
            Py_DECREF(ifast);
        }
        Py_DECREF(cit);
        if (PyErr_Occurred()) {
            goto fail;
        }
    }
    Py_DECREF(rit);
    if (PyErr_Occurred()) {
        return NULL;
    }
    Py_RETURN_NONE;

fail:
    Py_DECREF(rit);
    return NULL;
}

static PyMethodDef module_methods[] = {
    {"build_cells", build_cells, METH_VARARGS, build_cells_doc},
    {"paint_ripples", paint_ripples, METH_VARARGS, paint_ripples_doc},
    {"post_cells", post_cells, METH_VARARGS, post_cells_doc},
    {"encode_cells", encode_cells, METH_VARARGS, encode_cells_doc},
    {NULL, NULL, 0, NULL}
};

PyDoc_STRVAR(module_doc, "Exact native cell-grid construction for Alien World.");

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_fast_cells",
    module_doc,
    -1,
    module_methods,
    NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC
PyInit__fast_cells(void)
{
    return PyModule_Create(&module_def);
}
