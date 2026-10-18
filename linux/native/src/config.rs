use serde::Deserialize;
use std::path::PathBuf;

#[derive(Clone, Debug, Deserialize)]
#[serde(default)]
pub struct LinuxConfig {
    pub hotkey_distraction: String,
    pub hotkey_quick_start: String,
    pub show_tray: bool,
    pub autolaunch: bool,
    pub desktop_integration: bool,
}
impl Default for LinuxConfig {
    fn default() -> Self {
        Self {
            hotkey_distraction: "CTRL+ALT+d".into(),
            hotkey_quick_start: "CTRL+ALT+p".into(),
            show_tray: true,
            autolaunch: true,
            desktop_integration: true,
        }
    }
}
#[derive(Clone, Debug, Deserialize)]
#[serde(default)]
pub struct Config {
    pub session_duration: u32,
    pub idle_timeout: u32,
    pub sound_enabled: bool,
    pub distraction_note_prompt: bool,
    pub linux: LinuxConfig,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            session_duration: 25,
            idle_timeout: 300,
            sound_enabled: true,
            distraction_note_prompt: false,
            linux: LinuxConfig::default(),
        }
    }
}
pub fn dir() -> PathBuf {
    // Match the Python backend rather than assuming it follows XDG_CONFIG_HOME.
    std::env::var_os("POMOCLI_CONFIG_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join(".config/pomocli"))
}
pub fn home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/"))
}
pub fn socket() -> PathBuf {
    std::env::var_os("POMOCLI_SOCKET")
        .map(PathBuf::from)
        .unwrap_or_else(|| dir().join("pomo.sock"))
}
pub fn load() -> Config {
    match std::fs::read_to_string(dir().join("config.toml")) {
        Ok(text) => toml::from_str(&text).unwrap_or_else(|error| {
            eprintln!("Invalid PomoCLI configuration: {error}; using defaults");
            Config::default()
        }),
        Err(_) => Config::default(),
    }
}
pub fn cli() -> PathBuf {
    if let Some(path) = std::env::var_os("POMOCLI_BIN") {
        return path.into();
    }
    let local = home().join(".local/bin/pomo");
    if local.is_file() {
        local
    } else {
        "pomo".into()
    }
}
pub fn dialog() -> PathBuf {
    if let Some(path) = std::env::var_os("POMOCLI_DIALOG_BIN") {
        return path.into();
    }
    if let Ok(exe) = std::env::current_exe() {
        let adjacent = exe.with_file_name("pomo-dialog");
        if adjacent.is_file() {
            return adjacent;
        }
    }
    "pomo-dialog".into()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn legacy_keys_do_not_override_linux_shortcuts() {
        let cfg: Config = toml::from_str(
            "session_duration = 40\nhotkey_distraction = 'cmd+shift+d'\n[linux]\nshow_tray = false",
        )
        .unwrap();
        assert_eq!(cfg.session_duration, 40);
        assert_eq!(cfg.linux.hotkey_distraction, "CTRL+ALT+d");
        assert!(!cfg.linux.show_tray);
        assert!(cfg.sound_enabled);
    }
}
