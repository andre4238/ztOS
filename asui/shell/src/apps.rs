// SPDX-License-Identifier: GPL-3.0-or-later
//! The apps: every .desktop file that is meant to be shown, plus Settings
//! (ztsettings has no .desktop file of its own).

use std::collections::HashSet;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug)]
pub struct App {
    pub key: String,      // the .desktop file's name, or the built-in's
    pub name: String,
    pub command: String,
    pub icon: Option<PathBuf>,
    pub inline_svg: Option<&'static str>,
    /// a white symbol from A-SYSTEMS OS's own icons: drawn on a coloured tile
    pub own_symbol: bool,
}

const GEAR: &str = r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><path fill="#fff" fill-rule="evenodd" d="M20.5 4h7l1.2 5.3a15 15 0 0 1 3.9 2.2l5.1-1.7 3.5 6.1-4 3.6a15 15 0 0 1 0 4.5l4 3.6-3.5 6.1-5.1-1.7a15 15 0 0 1-3.9 2.2L27.5 44h-7l-1.2-5.3a15 15 0 0 1-3.9-2.2l-5.1 1.7-3.5-6.1 4-3.6a15 15 0 0 1 0-4.5l-4-3.6 3.5-6.1 5.1 1.7a15 15 0 0 1 3.9-2.2zM24 17a7 7 0 1 0 0 14 7 7 0 0 0 0-14z"/></svg>"##;

fn dirs() -> Vec<PathBuf> {
    let mut v = Vec::new();
    if let Some(home) = std::env::var_os("HOME") {
        v.push(Path::new(&home).join(".local/share/applications"));
    }
    v.push("/usr/local/share/applications".into());
    v.push("/usr/share/applications".into());
    v
}

/// When anything in the application folders changed last: to look again.
pub fn stamp() -> u64 {
    dirs()
        .iter()
        .filter_map(|d| std::fs::metadata(d).ok()?.modified().ok())
        .filter_map(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs())
        .max()
        .unwrap_or(0)
}

pub fn scan() -> Vec<App> {
    let mut seen = HashSet::new();
    let mut apps = Vec::new();
    for dir in dirs() {
        let Ok(rd) = std::fs::read_dir(&dir) else { continue };
        let mut files: Vec<PathBuf> = rd.filter_map(|e| e.ok().map(|e| e.path())).collect();
        files.sort();
        for path in files {
            if path.extension().map(|e| e != "desktop").unwrap_or(true) {
                continue;
            }
            let key = path.file_name().unwrap().to_string_lossy().to_string();
            if !seen.insert(key.clone()) {
                continue; // the user's copy, or /usr/local's, wins
            }
            if let Some(app) = parse(&path, key) {
                apps.push(app);
            }
        }
    }
    if !apps.iter().any(|a| a.command.split_whitespace().next() == Some("ztsettings")) {
        apps.push(App {
            key: "ztsettings".into(),
            name: "Settings".into(),
            command: "ztsettings".into(),
            icon: None,
            inline_svg: Some(GEAR),
            own_symbol: true,
        });
    }
    apps.sort_by_key(|a| a.name.to_lowercase());
    apps
}

fn parse(path: &Path, key: String) -> Option<App> {
    let text = std::fs::read_to_string(path).ok()?;
    let mut in_entry = false;
    let (mut name, mut exec, mut icon) = (None, None, None);
    let mut hidden = false;
    let mut is_app = true;
    for line in text.lines() {
        let line = line.trim();
        if line.starts_with('[') {
            in_entry = line == "[Desktop Entry]";
            continue;
        }
        if !in_entry {
            continue;
        }
        let Some((k, v)) = line.split_once('=') else { continue };
        match k.trim() {
            "Name" => name = Some(v.trim().to_string()),
            "Exec" => exec = Some(v.trim().to_string()),
            "Icon" => icon = Some(v.trim().to_string()),
            "NoDisplay" | "Hidden" => hidden |= v.trim() == "true",
            "Terminal" => hidden |= v.trim() == "true",
            "Type" => is_app = v.trim() == "Application",
            _ => {}
        }
    }
    if hidden || !is_app {
        return None;
    }
    let command = strip_field_codes(&exec?);
    if command.is_empty() {
        return None;
    }
    let icon_path = icon.as_deref().and_then(find_icon);
    let own_symbol = icon_path
        .as_ref()
        .map(|p| p.starts_with("/usr/local/share/icons") && p.extension().map(|e| e == "svg").unwrap_or(false))
        .unwrap_or(false);
    Some(App { key, name: name?, command, icon: icon_path, inline_svg: None, own_symbol })
}

/// %u, %F and the like go: the shell opens apps without files.
fn strip_field_codes(exec: &str) -> String {
    exec.split_whitespace()
        .filter(|w| !(w.len() == 2 && w.starts_with('%') && w != &"%%"))
        .map(|w| w.replace("%%", "%"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn find_icon(name: &str) -> Option<PathBuf> {
    let p = Path::new(name);
    if p.is_absolute() {
        return p.exists().then(|| p.to_path_buf());
    }
    const SIZES: [&str; 9] =
        ["scalable", "512x512", "256x256", "192x192", "128x128", "96x96", "64x64", "48x48", "32x32"];
    for base in ["/usr/local/share/icons/hicolor", "/usr/share/icons/hicolor"] {
        for size in SIZES {
            for ext in ["svg", "png"] {
                let f = Path::new(base).join(size).join("apps").join(format!("{name}.{ext}"));
                if f.exists() {
                    return Some(f);
                }
            }
        }
    }
    for ext in ["svg", "png"] {
        let f = Path::new("/usr/share/pixmaps").join(format!("{name}.{ext}"));
        if f.exists() {
            return Some(f);
        }
    }
    None
}
