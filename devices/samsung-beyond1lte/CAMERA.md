# Galaxy S10 cameras on mainline: port plan

Source of the work: the S10e port, [pulpoff/linux-beyond0lte](https://github.com/pulpoff/linux-beyond0lte)
(commit `47d26e62` "S10e: cameras, ...", and its `mobian/docs/CAMERA-SPEC.md`). It runs the
cameras on mainline 7.2 without Samsung's ISP firmware and without secure calls:

```
sensor -> D-PHY (in BLK_DPU) -> CSIS v5.2 -> WDMA ("CSISX4_PDP_DMA") -> DRAM
       -> libcamera simple pipeline + software ISP on the GPU (panfrost)
```

## The S10's cameras (from the stock dtbo of this phone)

| Camera | Sensor | I2C address | S10e driver |
|---|---|---|---|
| rear wide, 12 MP dual pixel | S5K2L4 | 0x20 (S10e: 0x10) | yes (`s5k3p9.c`, `samsung,s5k2l4`) |
| rear ultrawide, 16 MP | S5K3P9 | 0x2D | yes (`samsung,s5k3p9`), **first one to bring up** |
| front, 10 MP | S5K3J1 | 0x10 | yes (`samsung,s5k3j1`) |
| rear tele, 12 MP | S5K3M3 | 0x5A | **no**: S10 only, new tables needed |
| AF | AK737x | 0x0C / 0x0F | `ak7375.c` + 16 lines |

The stock dtbo names the nodes `is_sensor_2l4@20`, `is_sensor_3p9@2D`, `is_sensor_3m3@5A`,
`is_sensor_3j1@10`, `actuator-ak737x`; every pin, bus and rail has to be read from there
for the S10 and not copied from the S10e (the wide sensor's address already differs).

## Ultrawide (S5K3P9): S10 stock dtbo against the S10e DT (checked 2026-11-15)

All nine hardware revisions of the S10's dtbo, resolved through `__fixups__`/`__local_fixups__`:

| | S10e DT (pulpoff) | S10 stock dtbo |
|---|---|---|
| I2C | hsi2c_1, 0x2D | hsi2c_1 (`fragment@19`, `hsi2c1_bus`) on every revision; `hsi2c_2` (`fragment@125`) only on prototypes 0x11-0x15 |
| MCLK | CIS_CLK3, gpc1-7 | `mclk_ch = 3`, `gpio_mclk = <&gpc1 7>` |
| reset | gpg0-3 | `gpio_reset = <&gpg0 3>` |
| PMIC | S2MPB02 0x59 on hsi2c_24 | `s2mpb02_pmic@59` in `fragment@74` (hsi2c_24) |
| rails | buck2 1.3 V, ldo4 1.05 V, ldo8 1.8 V, ldo15 2.8 V | buck2 `VDD_EXT_1P3_PB02` 1.3 V, ldo4 `VDDD_1.05V_WIDESUB` 1.05 V, ldo8 `VDDIO_1.8V_WIDESUB` 1.8 V, ldo15 `VDDA_2.8V_WIDESUB` 2.8 V |

So the S10e's ultrawide DT holds for the S10 as it is. The S10's other S2MPB02 rails are the
tele's (`..._SUB`: ldo3 1.05 V, ldo7 1.8 V, ldo11 2.8 V, ldo12 AF 2.8 V) and OIS (ldo10).

## What the S10e camera commit brings, against our kernel (v7.2.0 + S10Plus_Linux)

`git apply --check` of the 18 kernel files of that commit on our tree:

- applies as is: `drivers/media/platform/samsung/exynos9820-csis/` (CSIS + WDMA capture,
  976 lines), `drivers/media/i2c/s5k3p9.c` + the three table headers, `ak7375.c`,
  `drivers/regulator/s2mpb02-regulator.c`, `s2mpb03-regulator.c` (camera PMICs), Kconfig/Makefile;
- does not apply: `drivers/clk/samsung/clk-exynos9820.c` and the clock IDs header (ours is
  `include/dt-bindings/clock/samsung,exynos9820.h`, the S10Plus_Linux one).
  - The PERIC1 camera I2C clocks are already in ours, named
    `CLK_GOUT_PERIC1_CLK_PERIC1_I2C_CAMn_CLK` / `..._I2C_CAMn_IPCLK` / `..._PCLK`.
  - **CMU_ISPPRE (0x17000000) is missing** and has to be added in our driver's style:
    parent `dout_cmu_isppre_bus` exists in CMU_TOP; mux 0x0100, div 0x1804, 18 gates (bit 21),
    option 0x0800; it sits in `pd_isppre`, which power-cycles, so it registers through
    `exynos_arm64_register_cmu_pm()` like the other platform-device CMUs.
- DT (in the S10e's U-Boot tree, ~750 lines): I2C_CAM0..3, USI08/USI10/USI17_USI, CMGP I2C1,
  `pd_isppre` (PMU 0x15862500, TZPC SMC 0x17010204), SysMMU_ISPPRE, CSIS0-2, WDMA0-2,
  the D-PHYs, S2MPB02 (hsi2c_24, 0x59) and S2MPB03 (hsi2c_42, 0x56), the sensors.

## Order

1. **Done (2026-11-15):** `kernel/0001-…` = the S10e drivers + CMU_ISPPRE in our clock
   driver, built in by `ztos-rescue.config`; the kernel builds. Was: CMU_ISPPRE in our clock driver; the S10e drivers built in (`VIDEO_EXYNOS9820_CSIS`,
   `VIDEO_S5K3P9`, `REGULATOR_S2MPB02/03`).
2. DT for the ultrawide path only (S5K3P9 on its bus, its rails, CSIS1/WDMA1, its PHY), every
   value checked against the S10's stock dtbo.
3. On the phone: WDMA test pattern first (proves CSIS/WDMA without a sensor), then the
   S5K3P9 chip ID over I2C, then a RAW frame.
4. libcamera 0.7.2 + the S10e patch and tuning files; a camera app under ztMETRO.
5. Wide (S5K2L4, PDAF, OIS MCU) and front (S5K3J1); tele (S5K3M3) last.
