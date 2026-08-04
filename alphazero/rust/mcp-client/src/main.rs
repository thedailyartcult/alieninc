use std::error::Error;

pub mod handlers;

pub async fn handle_alpha_zero_command(
    command: &str,
    params: serde_json::Value,
) -> Result<serde_json::Value, Box<dyn Error>> {
    handlers::handle_command(command, params).await
}