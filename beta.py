# /// script
# requires-python = ">=3.10"
# ///
"""Alaska's presidential elasticity (beta): fit Alaska's D-minus-R margin
against the national margin. Slope = beta, intercept = Alaska's lean when the
nation is tied. Source: Wikipedia, presidential elections in Alaska, and list
of presidential elections by popular vote margin (fetched 5 Nov 2026)."""

# year: (alaska_dem, alaska_rep, national_margin_dem_minus_rep)
DATA = {
    1976: (35.65, 57.90, 2.06),
    1980: (26.41, 54.35, -9.74),
    1984: (29.87, 66.65, -18.21),
    1988: (36.27, 59.59, -7.72),
    1992: (30.29, 39.46, 5.56),
    1996: (33.27, 50.80, 8.51),
    2000: (27.67, 58.62, 0.51),
    2004: (35.52, 61.07, -2.46),
    2008: (37.89, 59.42, 7.27),
    2012: (40.81, 54.80, 3.86),
    2016: (36.55, 51.28, 2.09),
    2020: (42.77, 52.83, 4.45),
    2024: (41.41, 54.54, -1.48),
}


def fit(years):
    xs = [DATA[y][2] for y in years]
    ys = [DATA[y][0] - DATA[y][1] for y in years]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = {y: (DATA[y][0] - DATA[y][1]) - (intercept + slope * DATA[y][2]) for y in years}
    rmse = (sum(r * r for r in resid.values()) / n) ** 0.5
    return slope, intercept, resid, rmse


print("year  alaska_margin  national_margin  gap(alaska-national)")
for y, (d, r, nat) in DATA.items():
    print(f"{y}  {d - r:+7.2f}        {nat:+7.2f}          {d - r - nat:+7.2f}")

windows = {
    "2000-2024": [y for y in DATA if y >= 2000],
    "2000-2024 without 2008 (Palin)": [y for y in DATA if y >= 2000 and y != 2008],
    "2012-2024": [y for y in DATA if y >= 2012],
    "1976-2024": list(DATA),
    "1976-2024 without 1992 (Perot) and 2008": [y for y in DATA if y not in (1992, 2008)],
}
for name, years in windows.items():
    slope, intercept, resid, rmse = fit(years)
    print(f"\n{name}: beta {slope:.2f}, lean at national tie {intercept:+.2f}, rmse {rmse:.2f}")
    print("  residuals: " + ", ".join(f"{y} {v:+.1f}" for y, v in resid.items()))


def fit_trend(years):
    """Margin = lean_2000 + beta * national + drift * (cycles since 2000), by least squares."""
    rows = [(1.0, DATA[y][2], (y - 2000) / 4) for y in years]
    ys = [DATA[y][0] - DATA[y][1] for y in years]
    # normal equations, 3x3
    A = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    b = [sum(r[i] * yv for r, yv in zip(rows, ys)) for i in range(3)]
    for i in range(3):  # Gauss-Jordan
        p = A[i][i]
        A[i] = [v / p for v in A[i]]; b[i] /= p
        for k in range(3):
            if k != i:
                f = A[k][i]
                A[k] = [vk - f * vi for vk, vi in zip(A[k], A[i])]; b[k] -= f * b[i]
    lean, beta, drift = b
    resid = {y: yv - (lean + beta * r[1] + drift * r[2]) for y, r, yv in zip(years, rows, ys)}
    rmse = (sum(v * v for v in resid.values()) / len(years)) ** 0.5
    return lean, beta, drift, resid, rmse


print("\nWith a lean drift term (points per presidential cycle):")
for name, years in windows.items():
    lean, beta, drift, resid, rmse = fit_trend(years)
    print(f"\n{name}: beta {beta:.2f}, lean in 2000 {lean:+.2f}, drift {drift:+.2f}/cycle, "
          f"lean in 2024 {lean + 6 * drift:+.2f}, rmse {rmse:.2f}")
    print("  residuals: " + ", ".join(f"{y} {v:+.1f}" for y, v in resid.items()))
