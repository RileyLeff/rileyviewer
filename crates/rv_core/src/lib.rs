use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum PlotContent {
    Png(String),   // base64-encoded PNG
    Svg(String),   // raw SVG
    Plotly(String), // JSON payload
    Vega(String),  // JSON payload (Vega/Vega-Lite)
    Html(String),  // raw HTML fallback
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlotMessage {
    pub id: String,
    /// Unix timestamp in milliseconds (safe for JavaScript Number)
    pub timestamp: u64,
    pub content: PlotContent,
}

impl PlotMessage {
    pub fn new(content: PlotContent) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            timestamp: (OffsetDateTime::now_utc().unix_timestamp_nanos() / 1_000_000) as u64,
            content,
        }
    }
}
