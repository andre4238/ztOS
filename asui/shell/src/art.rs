// SPDX-License-Identifier: GPL-3.0-or-later
//! ASUI's pictures: the default wallpaper ("ASUI Bloom", painted here: no
//! third-party artwork), the blurred copy that glass shows, photos fitted to
//! the screen, wallpaper thumbnails, and the app tiles.

use image::{imageops, RgbaImage};
use resvg::tiny_skia::{
    self as sk, Color, FillRule, GradientStop, LinearGradient, Paint, PathBuilder, Pixmap, Point,
    RadialGradient, Rect, SpreadMode, Stroke, Transform,
};
use slint::{Image, Rgba8Pixel, SharedPixelBuffer};
use std::path::Path;

fn rgba(hex: u32, a: u8) -> Color {
    Color::from_rgba8((hex >> 16) as u8, (hex >> 8) as u8, hex as u8, a)
}

/// The default wallpaper: a sky from deep to pale blue and, low on the right,
/// a bloom of ribbons turning about one point, deep at the heart and light at
/// their tips.
pub fn bloom(w: u32, h: u32) -> RgbaImage {
    let mut pm = Pixmap::new(w, h).expect("wallpaper size");
    let (wf, hf) = (w as f32, h as f32);
    let sky = LinearGradient::new(
        Point::from_xy(0.0, 0.0),
        Point::from_xy(wf * 0.25, hf),
        vec![
            GradientStop::new(0.0, rgba(0x3a78e0, 255)),
            GradientStop::new(0.38, rgba(0x8db9f2, 255)),
            GradientStop::new(0.62, rgba(0xc8ddf8, 255)),
            GradientStop::new(1.0, rgba(0xe8f1fc, 255)),
        ],
        SpreadMode::Pad,
        Transform::identity(),
    )
    .unwrap();
    let mut paint = Paint { shader: sky, anti_alias: true, ..Default::default() };
    pm.fill_rect(Rect::from_xywh(0.0, 0.0, wf, hf).unwrap(), &paint, Transform::identity(), None);

    // a soft light behind the bloom
    let glow = RadialGradient::new(
        Point::from_xy(wf * 0.62, hf * 0.68),
        0.0,
        Point::from_xy(wf * 0.62, hf * 0.68),
        wf * 0.9,
        vec![GradientStop::new(0.0, rgba(0xffffff, 150)), GradientStop::new(1.0, rgba(0xffffff, 0))],
        SpreadMode::Pad,
        Transform::identity(),
    )
    .unwrap();
    paint.shader = glow;
    pm.fill_rect(Rect::from_xywh(0.0, 0.0, wf, hf).unwrap(), &paint, Transform::identity(), None);

    let (cx, cy) = (wf * 0.60, hf * 0.70);
    // rings of ribbons, back to front: (count, length, width, turn, deep, light, alpha)
    let rings: [(usize, f32, f32, f32, u32, u32, u8); 4] = [
        (7, 0.78, 0.30, 8.0, 0x2a6ff0, 0xd6e6ff, 215),
        (7, 0.62, 0.26, 33.0, 0x1857e0, 0xb4d0ff, 225),
        (6, 0.46, 0.22, 12.0, 0x0c43c4, 0x8fb8ff, 235),
        (5, 0.30, 0.17, 40.0, 0x072f9c, 0x5f97ff, 245),
    ];
    for (ring, &(n, len, wid, turn, deep, light, alpha)) in rings.iter().enumerate() {
        for k in 0..n {
            let angle = turn + k as f32 * 360.0 / n as f32 + ring as f32 * 7.0;
            let l = len * wf * (0.92 + 0.16 * (((k * 7 + ring * 3) % 5) as f32 / 4.0));
            let wd = wid * wf;
            // a ribbon from the heart out, curling to one side
            let mut pb = PathBuilder::new();
            pb.move_to(cx, cy);
            pb.cubic_to(cx + l * 0.20, cy - wd * 1.25, cx + l * 0.78, cy - wd * 1.05, cx + l, cy - wd * 0.15);
            pb.cubic_to(cx + l * 0.82, cy + wd * 0.38, cx + l * 0.35, cy + wd * 0.55, cx, cy);
            pb.close();
            let path = pb.finish().unwrap();
            let t = Transform::from_rotate_at(angle, cx, cy);
            let shade = LinearGradient::new(
                Point::from_xy(cx, cy),
                Point::from_xy(cx + l, cy - wd * 0.4),
                vec![
                    GradientStop::new(0.0, rgba(deep, alpha)),
                    GradientStop::new(0.55, rgba(mix(deep, light, 0.55), alpha)),
                    GradientStop::new(1.0, rgba(light, alpha)),
                ],
                SpreadMode::Pad,
                t,
            )
            .unwrap();
            let p = Paint { shader: shade, anti_alias: true, ..Default::default() };
            pm.fill_path(&path, &p, FillRule::Winding, t, None);
            // the light along its upper edge
            let mut edge = PathBuilder::new();
            edge.move_to(cx + l * 0.06, cy - wd * 0.30);
            edge.cubic_to(cx + l * 0.24, cy - wd * 1.12, cx + l * 0.76, cy - wd * 0.98, cx + l * 0.98, cy - wd * 0.18);
            let edge = edge.finish().unwrap();
            let mut ep = Paint::default();
            ep.anti_alias = true;
            ep.set_color(rgba(0xffffff, 95));
            let stroke = Stroke { width: wf * 0.004, ..Default::default() };
            pm.stroke_path(&edge, &ep, &stroke, t, None);
        }
    }
    // the heart
    let heart = RadialGradient::new(
        Point::from_xy(cx, cy),
        0.0,
        Point::from_xy(cx, cy),
        wf * 0.08,
        vec![GradientStop::new(0.0, rgba(0x04205f, 230)), GradientStop::new(1.0, rgba(0x072f9c, 0))],
        SpreadMode::Pad,
        Transform::identity(),
    )
    .unwrap();
    paint.shader = heart;
    pm.fill_rect(Rect::from_xywh(0.0, 0.0, wf, hf).unwrap(), &paint, Transform::identity(), None);
    pixmap_to_rgba(&pm)
}

fn mix(a: u32, b: u32, t: f32) -> u32 {
    let ch = |s: u32| {
        let x = ((a >> s) & 0xff) as f32;
        let y = ((b >> s) & 0xff) as f32;
        ((x + (y - x) * t).round() as u32) << s
    };
    ch(16) | ch(8) | ch(0)
}

fn pixmap_to_rgba(pm: &Pixmap) -> RgbaImage {
    // opaque pictures only: premultiplied is the same as straight
    RgbaImage::from_raw(pm.width(), pm.height(), pm.data().to_vec()).unwrap()
}

/// A photo (or anything `image` reads) fitted to w x h, cut to cover it.
pub fn cover(path: &Path, w: u32, h: u32) -> Option<RgbaImage> {
    let img = image::open(path).ok()?.to_rgba8();
    Some(cover_image(&img, w, h, imageops::FilterType::CatmullRom))
}

fn cover_image(img: &RgbaImage, w: u32, h: u32, filter: imageops::FilterType) -> RgbaImage {
    let (iw, ih) = (img.width() as f32, img.height() as f32);
    let s = (w as f32 / iw).max(h as f32 / ih);
    let (sw, sh) = (((iw * s).round() as u32).max(w), ((ih * s).round() as u32).max(h));
    let scaled = imageops::resize(img, sw, sh, filter);
    imageops::crop_imm(&scaled, (sw - w) / 2, (sh - h) / 2, w, h).to_image()
}

/// A small thumbnail for the wallpaper picker.
pub fn thumbnail(path: &Path, w: u32, h: u32) -> Option<RgbaImage> {
    let img = image::open(path).ok()?;
    // a quick first step down, so a 12-megapixel photo is not filtered whole
    let small = img.thumbnail(w * 3, h * 3).to_rgba8();
    Some(cover_image(&small, w, h, imageops::FilterType::Triangle))
}

/// What glass shows: the picture at an eighth, blurred. Shown stretched to the
/// whole screen it is soft enough to be frosted glass.
pub fn frosted(img: &RgbaImage) -> RgbaImage {
    let w = (img.width() / 8).max(8);
    let h = (img.height() / 8).max(8);
    let small = imageops::resize(img, w, h, imageops::FilterType::Triangle);
    imageops::blur(&small, 5.0)
}

#[allow(dead_code)]
pub fn to_image(img: &RgbaImage) -> Image {
    Image::from_rgba8(SharedPixelBuffer::<Rgba8Pixel>::clone_from_slice(img.as_raw(), img.width(), img.height()))
}

pub fn to_buffer(img: &RgbaImage) -> SharedPixelBuffer<Rgba8Pixel> {
    SharedPixelBuffer::<Rgba8Pixel>::clone_from_slice(img.as_raw(), img.width(), img.height())
}

// ---- app tiles ---------------------------------------------------------------------------------

/// The colours of a tile, light (top left) to deep (bottom right), by what the app is.
pub fn tint_for(key: &str, name: &str) -> (u32, u32) {
    let s = format!("{} {}", key, name).to_lowercase();
    let kinds: [(&[&str], (u32, u32)); 16] = [
        (&["phone", "dialer"], (0x5ee584, 0x1c9a43)),
        (&["messag", "sms"], (0x6cd2ff, 0x1f7ae0)),
        (&["camera"], (0x9aa6bb, 0x465063)),
        (&["superscan", "browser", "web"], (0x56c8ff, 0x1460dc)),
        (&["music", "player", "mpv"], (0xff9a6e, 0xe8364f)),
        (&["contacts", "people"], (0xffc066, 0xf27a0c)),
        (&["files"], (0xffd862, 0xeb9d00)),
        (&["store"], (0x8f9cff, 0x3d4fe0)),
        (&["settings"], (0xa9b1c2, 0x56607a)),
        (&["power", "battery"], (0x7fe39d, 0x1f9e57)),
        (&["sound", "audio"], (0xf59ac0, 0xd2337f)),
        (&["devices"], (0xbaa3ff, 0x6a3fd0)),
        (&["osial"], (0x56d8cf, 0x0f8f86)),
        (&["welcome"], (0xcf9cff, 0x7c3aed)),
        (&["weather"], (0x6fc4ff, 0x2a6ff0)),
        (&["terminal", "vim"], (0x5b6475, 0x1d222c)),
    ];
    for (words, tint) in kinds {
        if words.iter().any(|w| s.contains(w)) {
            return tint;
        }
    }
    const SPARE: [(u32, u32); 6] =
        [(0x6cd2ff, 0x1f7ae0), (0x5ee584, 0x1c9a43), (0xffc066, 0xf27a0c), (0xcf9cff, 0x7c3aed),
         (0x56d8cf, 0x0f8f86), (0xff9a6e, 0xe8364f)];
    let h = s.bytes().fold(7u32, |a, b| a.wrapping_mul(31).wrapping_add(b as u32));
    SPARE[(h % SPARE.len() as u32) as usize]
}

/// A Fluent tile: a rounded square in the app's colours with a sheen, and the
/// app's own symbol in white on it (ASMS's icons are white symbols). Icons
/// that bring their own colours are drawn as they are.
pub fn app_icon(px: u32, icon: Option<&Path>, svg_inline: Option<&str>, tint: (u32, u32), own_symbol: bool) -> RgbaImage {
    let mut pm = Pixmap::new(px, px).unwrap();
    let s = px as f32;
    let symbol = load_icon(icon, svg_inline);
    if own_symbol || symbol.is_none() {
        let r = s * 0.24;
        let rect = rounded_rect(s * 0.02, s * 0.02, s * 0.96, s * 0.96, r);
        let shade = LinearGradient::new(
            Point::from_xy(0.0, 0.0),
            Point::from_xy(s, s),
            vec![GradientStop::new(0.0, rgba(tint.0, 255)), GradientStop::new(1.0, rgba(tint.1, 255))],
            SpreadMode::Pad,
            Transform::identity(),
        )
        .unwrap();
        let p = Paint { shader: shade, anti_alias: true, ..Default::default() };
        pm.fill_path(&rect, &p, FillRule::Winding, Transform::identity(), None);
        let sheen = LinearGradient::new(
            Point::from_xy(0.0, 0.0),
            Point::from_xy(0.0, s),
            vec![
                GradientStop::new(0.0, rgba(0xffffff, 70)),
                GradientStop::new(0.5, rgba(0xffffff, 0)),
                GradientStop::new(1.0, rgba(0x000000, 20)),
            ],
            SpreadMode::Pad,
            Transform::identity(),
        )
        .unwrap();
        let p = Paint { shader: sheen, anti_alias: true, ..Default::default() };
        pm.fill_path(&rect, &p, FillRule::Winding, Transform::identity(), None);
        let mut rim = Paint::default();
        rim.anti_alias = true;
        rim.set_color(rgba(0xffffff, 60));
        pm.stroke_path(&rect, &rim, &Stroke { width: s * 0.012, ..Default::default() }, Transform::identity(), None);
        match symbol {
            Some(sym) => draw_centered(&mut pm, &sym, s * 0.58),
            None => {
                // no symbol at all: a plain mark, a smaller rounded square
                let mark = rounded_rect(s * 0.34, s * 0.34, s * 0.32, s * 0.32, s * 0.08);
                let mut white = Paint::default();
                white.anti_alias = true;
                white.set_color(rgba(0xffffff, 235));
                pm.fill_path(&mark, &white, FillRule::Winding, Transform::identity(), None);
            }
        }
    } else if let Some(sym) = symbol {
        draw_centered(&mut pm, &sym, s * 0.92);
    }
    // tiny-skia keeps premultiplied pixels; Slint takes them as such (see to_premul_image)
    RgbaImage::from_raw(px, px, pm.data().to_vec()).unwrap()
}

pub fn to_premul_image(img: &RgbaImage) -> Image {
    Image::from_rgba8_premultiplied(SharedPixelBuffer::<Rgba8Pixel>::clone_from_slice(
        img.as_raw(),
        img.width(),
        img.height(),
    ))
}

enum Symbol {
    Svg(resvg::usvg::Tree),
    Raster(Pixmap),
}

fn load_icon(path: Option<&Path>, inline: Option<&str>) -> Option<Symbol> {
    let opt = resvg::usvg::Options::default();
    if let Some(svg) = inline {
        return resvg::usvg::Tree::from_str(svg, &opt).ok().map(Symbol::Svg);
    }
    let path = path?;
    let is_svg = path.extension().map(|e| e == "svg" || e == "svgz").unwrap_or(false);
    if is_svg {
        let data = std::fs::read(path).ok()?;
        return resvg::usvg::Tree::from_data(&data, &opt).ok().map(Symbol::Svg);
    }
    let img = image::open(path).ok()?.to_rgba8();
    let mut pm = Pixmap::new(img.width(), img.height())?;
    for (dst, src) in pm.pixels_mut().iter_mut().zip(img.pixels()) {
        let [r, g, b, a] = src.0;
        *dst = sk::ColorU8::from_rgba(r, g, b, a).premultiply();
    }
    Some(Symbol::Raster(pm))
}

fn draw_centered(pm: &mut Pixmap, sym: &Symbol, box_size: f32) {
    let s = pm.width() as f32;
    match sym {
        Symbol::Svg(tree) => {
            let size = tree.size();
            let k = box_size / size.width().max(size.height());
            let t = Transform::from_translate((s - size.width() * k) / 2.0, (s - size.height() * k) / 2.0)
                .pre_scale(k, k);
            resvg::render(tree, t, &mut pm.as_mut());
        }
        Symbol::Raster(src) => {
            let k = box_size / src.width().max(src.height()) as f32;
            let t = Transform::from_translate(
                (s - src.width() as f32 * k) / 2.0,
                (s - src.height() as f32 * k) / 2.0,
            )
            .pre_scale(k, k);
            let paint = sk::PixmapPaint { quality: sk::FilterQuality::Bicubic, ..Default::default() };
            pm.draw_pixmap(0, 0, src.as_ref(), &paint, t, None);
        }
    }
}

fn rounded_rect(x: f32, y: f32, w: f32, h: f32, r: f32) -> sk::Path {
    let k = 0.5523 * r;
    let mut pb = PathBuilder::new();
    pb.move_to(x + r, y);
    pb.line_to(x + w - r, y);
    pb.cubic_to(x + w - r + k, y, x + w, y + r - k, x + w, y + r);
    pb.line_to(x + w, y + h - r);
    pb.cubic_to(x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h);
    pb.line_to(x + r, y + h);
    pb.cubic_to(x + r - k, y + h, x, y + h - r + k, x, y + h - r);
    pb.line_to(x, y + r);
    pb.cubic_to(x, y + r - k, x + r - k, y, x + r, y);
    pb.close();
    pb.finish().unwrap()
}
