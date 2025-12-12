//! Configuration management for rileyviewer.
//!
//! Configuration is loaded from `~/.config/rileyviewer/config.toml` (or platform equivalent)
//! and can be overridden by CLI flags.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tracing::debug;

/// Default values
pub const DEFAULT_HOST: &str = "127.0.0.1";
pub const DEFAULT_PORT: u16 = 7878;
pub const DEFAULT_HISTORY_LIMIT: usize = 200;

/// The main configuration structure.
///
/// All fields are optional - missing fields use defaults.
/// CLI flags override values from the config file.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    pub server: ServerConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct ServerConfig {
    /// Host to bind the server to
    pub host: String,
    /// Port to bind the server to
    pub port: u16,
    /// Maximum number of plots to keep in history
    pub history_limit: usize,
    /// Whether to open browser automatically on server start
    pub open_browser: bool,
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            host: DEFAULT_HOST.to_string(),
            port: DEFAULT_PORT,
            history_limit: DEFAULT_HISTORY_LIMIT,
            open_browser: true,
        }
    }
}

impl Config {
    /// Load configuration from the default config file location.
    ///
    /// Returns default config if file doesn't exist or can't be parsed.
    pub fn load() -> Self {
        let path = config_file_path();
        Self::load_from(&path).unwrap_or_default()
    }

    /// Load configuration from a specific path.
    pub fn load_from(path: &PathBuf) -> Option<Self> {
        if !path.exists() {
            debug!("Config file not found at {:?}, using defaults", path);
            return None;
        }

        match std::fs::read_to_string(path) {
            Ok(contents) => match toml::from_str(&contents) {
                Ok(config) => {
                    debug!("Loaded config from {:?}", path);
                    Some(config)
                }
                Err(e) => {
                    tracing::warn!("Failed to parse config file {:?}: {}", path, e);
                    None
                }
            },
            Err(e) => {
                tracing::warn!("Failed to read config file {:?}: {}", path, e);
                None
            }
        }
    }

    /// Write a default config file to the default location.
    ///
    /// Creates parent directories if needed. Returns the path written to.
    pub fn write_default() -> std::io::Result<PathBuf> {
        let path = config_file_path();
        Self::write_default_to(&path)?;
        Ok(path)
    }

    /// Write a default config file to a specific path.
    pub fn write_default_to(path: &PathBuf) -> std::io::Result<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let default_config = Self::default();
        let contents = toml::to_string_pretty(&default_config)
            .expect("default config should serialize");

        // Add a header comment
        let with_header = format!(
            "# RileyViewer configuration\n\
             # See https://github.com/rileyleff/rileyviewer for documentation\n\n\
             {contents}"
        );

        std::fs::write(path, with_header)
    }
}

/// Get the platform-appropriate config file path.
///
/// - macOS: `~/Library/Application Support/rileyviewer/config.toml`
/// - Linux: `~/.config/rileyviewer/config.toml`
/// - Windows: `%APPDATA%/rileyviewer/config.toml`
pub fn config_file_path() -> PathBuf {
    config_dir().join("config.toml")
}

/// Get the platform-appropriate config directory.
pub fn config_dir() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("rileyviewer")
}

/// Get the platform-appropriate data directory (for server state, etc).
///
/// - macOS: `~/Library/Application Support/rileyviewer`
/// - Linux: `~/.local/share/rileyviewer`
/// - Windows: `%LOCALAPPDATA%/rileyviewer`
pub fn data_dir() -> PathBuf {
    dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("rileyviewer")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = Config::default();
        assert_eq!(config.server.host, DEFAULT_HOST);
        assert_eq!(config.server.port, DEFAULT_PORT);
        assert_eq!(config.server.history_limit, DEFAULT_HISTORY_LIMIT);
        assert!(config.server.open_browser);
    }

    #[test]
    fn test_parse_partial_config() {
        let toml = r#"
[server]
history_limit = 500
"#;
        let config: Config = toml::from_str(toml).unwrap();
        assert_eq!(config.server.history_limit, 500);
        // Other fields should use defaults
        assert_eq!(config.server.host, DEFAULT_HOST);
        assert_eq!(config.server.port, DEFAULT_PORT);
    }

    #[test]
    fn test_serialize_config() {
        let config = Config::default();
        let serialized = toml::to_string_pretty(&config).unwrap();
        assert!(serialized.contains("host"));
        assert!(serialized.contains("history_limit"));
    }
}
