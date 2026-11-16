// SPDX-License-Identifier: GPL-3.0-or-later
//! asui-shell: ASUI's home screen, app list, dock, lock screen and status bar.
//!
//! Two windows (ui/asui.slint): "ASUI Home" under every app and "ASUI Bar"
//! over them; the compositor (asui) knows them by their titles. It is told
//! what to open, and tells what happens, over $XDG_RUNTIME_DIR/asui.sock:
//!
//!   to it:    launch KEY COMMAND | home | sleep
//!   from it:  home | app KEY | apps KEY... | blank 0|1 | volume up|down
//!
//! ~/.config/asui/config (key = value, all optional):
//!
//!   wallpaper = /path/to/photo.jpg      (empty: ASUI Bloom, painted here)
//!   dock = ztphone.desktop, superscan.desktop, ztmessages.desktop, ztcamera.desktop
//!   lock = on

slint::include_modules!();

mod apps;
mod art;

use slint::{ComponentHandle, Model, ModelRc, Timer, TimerMode, VecModel};
use std::cell::RefCell;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::{Arc, Mutex};
use std::time::Duration;

const ICON_PX: u32 = 192;
const DOCK_DEFAULT: [&str; 4] = ["ztphone.desktop", "superscan.desktop", "ztmessages.desktop", "ztcamera.desktop"];

fn log(msg: impl AsRef<str>) {
    eprintln!("asui-shell: {}", msg.as_ref());
}

// ---- config ---------------------------------------------------------------------------------

#[derive(Clone)]
struct Config {
    wallpaper: String,
    dock: Vec<String>,
    lock: bool,
}

fn config_dir() -> PathBuf {
    std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| Path::new(&std::env::var_os("HOME").unwrap_or_default()).join(".config"))
}

fn config_path() -> PathBuf {
    config_dir().join("asui/config")
}

impl Config {
    fn load() -> Config {
        let mut c = Config { wallpaper: String::new(), dock: DOCK_DEFAULT.iter().map(|s| s.to_string()).collect(), lock: true };
        if let Ok(text) = std::fs::read_to_string(config_path()) {
            for line in text.lines() {
                let Some((k, v)) = line.split_once('=') else { continue };
                let v = v.trim();
                match k.trim() {
                    "wallpaper" => c.wallpaper = v.to_string(),
                    "dock" => c.dock = v.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect(),
                    "lock" => c.lock = v != "off",
                    _ => {}
                }
            }
        }
        c
    }

    fn save(&self) {
        let path = config_path();
        let _ = std::fs::create_dir_all(path.parent().unwrap());
        let text = format!(
            "# ASUI, written by the shell\nwallpaper = {}\ndock = {}\nlock = {}\n",
            self.wallpaper,
            self.dock.join(", "),
            if self.lock { "on" } else { "off" }
        );
        let tmp = path.with_extension("new");
        if std::fs::write(&tmp, text).is_ok() {
            let _ = std::fs::rename(tmp, path);
        }
    }
}

// ---- the compositor's socket ----------------------------------------------------------------------

#[derive(Clone, Default)]
struct Link {
    out: Arc<Mutex<Option<UnixStream>>>,
}

impl Link {
    fn start(&self) {
        let out = self.out.clone();
        std::thread::spawn(move || loop {
            let path = Path::new(&std::env::var_os("XDG_RUNTIME_DIR").unwrap_or_else(|| "/tmp".into())).join("asui.sock");
            match UnixStream::connect(&path) {
                Ok(stream) => {
                    log("linked to the compositor");
                    *out.lock().unwrap() = stream.try_clone().ok();
                    for line in BufReader::new(stream).lines() {
                        let Ok(line) = line else { break };
                        let _ = slint::invoke_from_event_loop(move || with_shell(|sh| sh.heard(&line)));
                    }
                    *out.lock().unwrap() = None;
                    log("the compositor went");
                }
                Err(_) => {}
            }
            std::thread::sleep(Duration::from_secs(1));
        });
    }

    fn send(&self, line: &str) {
        if let Some(s) = self.out.lock().unwrap().as_mut() {
            let _ = s.write_all(format!("{line}\n").as_bytes());
        }
    }
}

// ---- the time, the battery, the radio ----------------------------------------------------------------

const DAYS: [&str; 7] = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS: [&str; 12] = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

fn now() -> libc::tm {
    unsafe {
        let t = libc::time(std::ptr::null_mut());
        let mut tm: libc::tm = std::mem::zeroed();
        libc::localtime_r(&t, &mut tm);
        tm
    }
}

fn read(path: impl AsRef<Path>) -> String {
    std::fs::read_to_string(path).map(|s| s.trim().to_string()).unwrap_or_default()
}

/// (battery %, charging)
fn battery() -> (i32, bool) {
    let mut cap = -1;
    let mut charging = false;
    if let Ok(rd) = std::fs::read_dir("/sys/class/power_supply") {
        for e in rd.flatten() {
            let p = e.path();
            if read(p.join("type")) == "Battery" {
                if cap < 0 {
                    cap = read(p.join("capacity")).parse().unwrap_or(-1);
                }
            } else if read(p.join("online")) == "1" {
                charging = true;
            }
        }
    }
    (if cap < 0 { 100 } else { cap.clamp(0, 100) }, charging)
}

/// Wi-Fi bars from /proc/net/wireless: -1 none, 0 not connected, 1..3
fn wifi() -> i32 {
    let text = read("/proc/net/wireless");
    for line in text.lines().skip(2) {
        let mut f = line.split_whitespace();
        let Some(iface) = f.next() else { continue };
        let iface = iface.trim_end_matches(':');
        if read(format!("/sys/class/net/{iface}/operstate")) != "up" {
            return 0;
        }
        let level: f32 = f.nth(2).map(|s| s.trim_end_matches('.')).and_then(|s| s.parse().ok()).unwrap_or(-100.0);
        return if level >= -60.0 { 3 } else if level >= -72.0 { 2 } else if level > -100.0 { 1 } else { 0 };
    }
    -1
}

/// the panel's size in pixels (the wallpaper is made for it)
fn screen_px() -> (u32, u32) {
    if let Ok(rd) = std::fs::read_dir("/sys/class/drm") {
        for e in rd.flatten() {
            let modes = read(e.path().join("modes"));
            if let Some((w, h)) = modes.lines().next().and_then(|l| l.split_once('x')) {
                if let (Ok(w), Ok(h)) = (w.parse(), h.trim_end_matches(|c: char| !c.is_ascii_digit()).parse()) {
                    return (w, h);
                }
            }
        }
    }
    (1440, 3040)
}

// ---- wallpapers ---------------------------------------------------------------------------------------

fn wallpaper_files() -> Vec<PathBuf> {
    let mut roots: Vec<PathBuf> = vec!["/usr/local/share/backgrounds".into(), "/usr/share/backgrounds".into()];
    if let Some(home) = std::env::var_os("HOME") {
        roots.push(Path::new(&home).join("Pictures"));
    }
    let mut out = Vec::new();
    fn walk(dir: &Path, out: &mut Vec<PathBuf>, depth: u32) {
        if depth > 3 || out.len() >= 90 {
            return;
        }
        let Ok(rd) = std::fs::read_dir(dir) else { return };
        let mut entries: Vec<PathBuf> = rd.flatten().map(|e| e.path()).collect();
        entries.sort();
        for p in entries {
            if p.is_dir() {
                walk(&p, out, depth + 1);
            } else if let Some(ext) = p.extension().and_then(|e| e.to_str()) {
                if matches!(ext.to_lowercase().as_str(), "jpg" | "jpeg" | "png") {
                    out.push(p);
                }
            }
        }
    }
    for r in roots {
        walk(&r, &mut out, 0);
    }
    out
}

fn wall_name(path: &Path) -> String {
    let mut stem = path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    for ext in [".jpg", ".jpeg", ".png", ".JPG", ".PNG"] {
        if let Some(s) = stem.strip_suffix(ext) {
            stem = s.to_string();
        }
    }
    let dir = path.parent().and_then(|p| p.file_name()).map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    if stem.to_lowercase().starts_with("background_") || stem.to_lowercase().starts_with("wallpaper_") {
        format!("{dir} {}", stem.rsplit('_').next().unwrap_or(""))
    } else {
        stem
    }
}

/// The wallpaper and its frosted copy, made off the event loop.
fn load_wallpaper(photo: Option<PathBuf>, (w, h): (u32, u32)) {
    std::thread::spawn(move || {
        let t = std::time::Instant::now();
        let sharp = photo
            .as_deref()
            .and_then(|p| art::cover(p, w, h))
            // ASUI Bloom is smooth: painted at half size, it looks the same
            .unwrap_or_else(|| art::bloom(w / 2, h / 2));
        let soft = art::frosted(&sharp);
        let (a, b) = (art::to_buffer(&sharp), art::to_buffer(&soft));
        log(format!("wallpaper {}x{} in {:.2} s", sharp.width(), sharp.height(), t.elapsed().as_secs_f32()));
        let _ = slint::invoke_from_event_loop(move || {
            with_shell(|sh| {
                sh.home.set_wallpaper(slint::Image::from_rgba8(a));
                sh.home.set_wallpaper_blur(slint::Image::from_rgba8(b));
            })
        });
    });
}

// ---- the shell ------------------------------------------------------------------------------------------

struct Shell {
    home: HomeWindow,
    bar: BarWindow,
    link: Link,
    cfg: RefCell<Config>,
    apps: RefCell<Vec<apps::App>>,
    icons: RefCell<HashMap<String, slint::Image>>,
    apps_stamp: RefCell<u64>,
    query: RefCell<String>,
    apps_model: Rc<VecModel<AppItem>>,
    dock_model: Rc<VecModel<AppItem>>,
    walls_model: Rc<VecModel<WallItem>>,
    wall_paths: RefCell<Vec<Option<PathBuf>>>,
    screen: (u32, u32),
    shown: RefCell<(String, String, String, i32, bool, i32)>, // what the windows show now
}

thread_local! {
    static SHELL: RefCell<Option<Rc<Shell>>> = const { RefCell::new(None) };
}

fn with_shell(f: impl FnOnce(&Rc<Shell>)) {
    let sh = SHELL.with(|s| s.borrow().clone());
    if let Some(sh) = sh {
        f(&sh);
    }
}

impl Shell {
    fn item(&self, a: &apps::App) -> AppItem {
        let mut icons = self.icons.borrow_mut();
        let icon = icons
            .entry(a.key.clone())
            .or_insert_with(|| {
                let img = art::app_icon(ICON_PX, a.icon.as_deref(), a.inline_svg, art::tint_for(&a.key, &a.name), a.own_symbol);
                art::to_premul_image(&img)
            })
            .clone();
        AppItem { key: a.key.clone().into(), name: a.name.clone().into(), icon }
    }

    fn load_apps(&self, force: bool) {
        let stamp = apps::stamp();
        if !force && stamp == *self.apps_stamp.borrow() {
            return;
        }
        *self.apps_stamp.borrow_mut() = stamp;
        let t = std::time::Instant::now();
        *self.apps.borrow_mut() = apps::scan();
        self.refresh_apps();
        self.refresh_dock();
        log(format!("{} apps, icons in {:.2} s", self.apps.borrow().len(), t.elapsed().as_secs_f32()));
    }

    fn refresh_apps(&self) {
        let q = self.query.borrow().to_lowercase();
        let items: Vec<AppItem> = self
            .apps
            .borrow()
            .iter()
            .filter(|a| q.is_empty() || a.name.to_lowercase().contains(q.trim()))
            .map(|a| self.item(a))
            .collect();
        self.apps_model.set_vec(items);
    }

    fn refresh_dock(&self) {
        let apps = self.apps.borrow();
        let cfg = self.cfg.borrow();
        let items: Vec<AppItem> = cfg
            .dock
            .iter()
            .filter_map(|k| apps.iter().find(|a| &a.key == k))
            .take(4)
            .map(|a| self.item(a))
            .collect();
        self.dock_model.set_vec(items);
    }

    fn tick(&self) {
        let tm = now();
        let hours = format!("{:02}", tm.tm_hour);
        let minutes = format!("{:02}", tm.tm_min);
        let date = format!("{}, {} {}", DAYS[tm.tm_wday as usize % 7], MONTHS[tm.tm_mon as usize % 12], tm.tm_mday);
        let mut shown = self.shown.borrow_mut();
        if shown.0 != hours || shown.1 != minutes || shown.2 != date {
            self.home.set_hours(hours.clone().into());
            self.home.set_minutes(minutes.clone().into());
            self.home.set_date(date.clone().into());
            self.bar.set_time(format!("{hours}:{minutes}").into());
            shown.0 = hours;
            shown.1 = minutes;
            shown.2 = date;
        }
    }

    fn poll_status(&self) {
        let (cap, charging) = battery();
        let w = wifi();
        let mut shown = self.shown.borrow_mut();
        if (shown.3, shown.4, shown.5) != (cap, charging, w) {
            self.home.set_battery(cap);
            self.home.set_charging(charging);
            self.home.set_wifi(w);
            self.bar.set_battery(cap);
            self.bar.set_charging(charging);
            self.bar.set_wifi(w);
            shown.3 = cap;
            shown.4 = charging;
            shown.5 = w;
        }
    }

    fn heard(&self, line: &str) {
        let (word, rest) = line.split_once(' ').unwrap_or((line, ""));
        match word {
            "home" => {
                self.home.set_drawer(false);
                self.home.set_searching(false);
                self.home.set_personalize(false);
            }
            "blank" => {
                if rest == "1" {
                    self.home.set_drawer(false);
                    self.home.set_searching(false);
                    self.home.set_personalize(false);
                    if self.cfg.borrow().lock {
                        self.home.set_locked(true);
                    }
                } else {
                    self.tick();
                    self.poll_status();
                }
            }
            _ => {}
        }
    }

    fn launch(&self, key: &str) {
        let apps = self.apps.borrow();
        if let Some(a) = apps.iter().find(|a| a.key == key) {
            log(format!("open {} - {}", a.name, a.command));
            self.link.send(&format!("launch {} {}", a.key, a.command));
        }
    }

    fn set_query(&self, q: String) {
        self.home.set_query(q.clone().into());
        *self.query.borrow_mut() = q;
        self.refresh_apps();
    }

    fn pin(&self, key: &str) {
        let mut cfg = self.cfg.borrow_mut();
        if cfg.dock.iter().any(|k| k == key) {
            return;
        }
        // keep only what is shown, so the newest of four is never hidden
        let present: Vec<String> = self.dock_model.iter().map(|i| i.key.to_string()).collect();
        cfg.dock = present;
        if cfg.dock.len() >= 4 {
            cfg.dock.pop();
        }
        cfg.dock.push(key.to_string());
        cfg.save();
        drop(cfg);
        self.refresh_dock();
    }

    fn unpin(&self, key: &str) {
        let mut cfg = self.cfg.borrow_mut();
        cfg.dock.retain(|k| k != key);
        cfg.save();
        drop(cfg);
        self.refresh_dock();
    }

    /// the picker: ASUI Bloom first, then the pictures found, thumbnails as they come
    fn want_walls(&self) {
        if self.walls_model.row_count() > 0 {
            return;
        }
        let current = self.cfg.borrow().wallpaper.clone();
        let files = wallpaper_files();
        let mut paths = vec![None];
        paths.extend(files.iter().cloned().map(Some));
        *self.wall_paths.borrow_mut() = paths;
        let blank = slint::Image::default();
        self.walls_model.push(WallItem { name: "ASUI Bloom".into(), thumb: blank.clone(), current: current.is_empty() });
        for f in &files {
            self.walls_model.push(WallItem {
                name: wall_name(f).into(),
                thumb: blank.clone(),
                current: f.to_string_lossy() == current,
            });
        }
        self.home.set_walls_loading(true);
        std::thread::spawn(move || {
            let (tw, th) = (180, 300);
            let bloom = art::bloom(tw, th);
            let buf = art::to_buffer(&bloom);
            let _ = slint::invoke_from_event_loop(move || with_shell(|sh| sh.set_thumb(0, buf)));
            for (i, f) in files.iter().enumerate() {
                if let Some(img) = art::thumbnail(f, tw, th) {
                    let buf = art::to_buffer(&img);
                    let _ = slint::invoke_from_event_loop(move || with_shell(|sh| sh.set_thumb(i + 1, buf)));
                }
            }
            let _ = slint::invoke_from_event_loop(|| with_shell(|sh| sh.home.set_walls_loading(false)));
        });
    }

    fn set_thumb(&self, i: usize, buf: slint::SharedPixelBuffer<slint::Rgba8Pixel>) {
        if let Some(mut item) = self.walls_model.row_data(i) {
            item.thumb = slint::Image::from_rgba8(buf);
            self.walls_model.set_row_data(i, item);
        }
    }

    fn choose_wall(&self, i: usize) {
        let Some(path) = self.wall_paths.borrow().get(i).cloned() else { return };
        let value = path.as_ref().map(|p| p.to_string_lossy().to_string()).unwrap_or_default();
        {
            let mut cfg = self.cfg.borrow_mut();
            cfg.wallpaper = value;
            cfg.save();
        }
        for row in 0..self.walls_model.row_count() {
            if let Some(mut item) = self.walls_model.row_data(row) {
                if item.current != (row == i) {
                    item.current = row == i;
                    self.walls_model.set_row_data(row, item);
                }
            }
        }
        load_wallpaper(path, self.screen);
    }
}

fn switch_to_asms() {
    let dir = config_dir().join("ztos");
    let _ = std::fs::create_dir_all(&dir);
    let _ = std::fs::write(dir.join("shell"), "asms\n");
    log("switching to ASMS: the session ends and starts again in it");
    // the compositor going ends the session; greetd starts ztos-session, which reads the choice
    let _ = std::process::Command::new("pkill").args(["-x", "asui"]).status();
}

fn main() -> Result<(), slint::PlatformError> {
    let home = HomeWindow::new()?;
    let bar = BarWindow::new()?;
    let link = Link::default();
    let cfg = Config::load();
    let shell = Rc::new(Shell {
        home: home.clone_strong(),
        bar: bar.clone_strong(),
        link: link.clone(),
        cfg: RefCell::new(cfg.clone()),
        apps: RefCell::new(Vec::new()),
        icons: RefCell::new(HashMap::new()),
        apps_stamp: RefCell::new(0),
        query: RefCell::new(String::new()),
        apps_model: Rc::new(VecModel::default()),
        dock_model: Rc::new(VecModel::default()),
        walls_model: Rc::new(VecModel::default()),
        wall_paths: RefCell::new(Vec::new()),
        screen: screen_px(),
        shown: RefCell::new((String::new(), String::new(), String::new(), -2, false, -2)),
    });
    SHELL.with(|s| *s.borrow_mut() = Some(shell.clone()));

    home.set_apps(ModelRc::from(shell.apps_model.clone()));
    home.set_dock(ModelRc::from(shell.dock_model.clone()));
    home.set_walls(ModelRc::from(shell.walls_model.clone()));
    home.set_locked(cfg.lock);

    let photo = (!cfg.wallpaper.is_empty()).then(|| PathBuf::from(&cfg.wallpaper)).filter(|p| p.exists());
    load_wallpaper(photo, shell.screen);
    shell.load_apps(true);
    shell.tick();
    shell.poll_status();

    home.on_launch(|key| with_shell(|sh| sh.launch(&key)));
    home.on_key(|k| {
        with_shell(|sh| {
            let q = format!("{}{}", sh.query.borrow(), k);
            sh.set_query(q);
        })
    });
    home.on_backspace(|| {
        with_shell(|sh| {
            let mut q = sh.query.borrow().clone();
            q.pop();
            sh.set_query(q);
        })
    });
    home.on_clear_query(|| with_shell(|sh| sh.set_query(String::new())));
    home.on_pin(|key| with_shell(|sh| sh.pin(&key)));
    home.on_unpin(|key| with_shell(|sh| sh.unpin(&key)));
    home.on_want_walls(|| with_shell(|sh| sh.want_walls()));
    home.on_choose_wall(|i| with_shell(|sh| sh.choose_wall(i.max(0) as usize)));
    home.on_switch_to_asms(switch_to_asms);

    let clock = Timer::default();
    clock.start(TimerMode::Repeated, Duration::from_secs(1), || with_shell(|sh| sh.tick()));
    let status = Timer::default();
    status.start(TimerMode::Repeated, Duration::from_secs(20), || with_shell(|sh| sh.poll_status()));
    let rescan = Timer::default();
    rescan.start(TimerMode::Repeated, Duration::from_secs(30), || with_shell(|sh| sh.load_apps(false)));

    // what the windows really got (scale, size), once they are up
    let report = Timer::default();
    report.start(TimerMode::SingleShot, Duration::from_secs(4), || {
        with_shell(|sh| {
            let w = sh.home.window();
            log(format!("home: {}x{} px at scale {}", w.size().width, w.size().height, w.scale_factor()));
            let b = sh.bar.window();
            log(format!("bar: {}x{} px at scale {}", b.size().width, b.size().height, b.scale_factor()));
        })
    });
    link.start();
    bar.show()?;
    home.show()?;
    slint::run_event_loop()
}
