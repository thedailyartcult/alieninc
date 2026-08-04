use alphazero_mcp_client::handle_command;
use std::error::Error;

pub async fn handle_alpha_zero_command(
    command: &str,
    params: serde_json::Value,
) -> Result<serde_json::Value, Box<dyn Error>> {
    handle_command(command, params).await
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    use std::io::{self, Read};

    let args: Vec<String> = std::env::args().collect();
    let command = if args.len() > 1 {
        args[1].clone()
    } else {
        "forecast".to_string()
    };

    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let params: serde_json::Value = if raw.trim().is_empty() {
        serde_json::json!({})
    } else {
        serde_json::from_str(&raw)?
    };

    let result = handle_command(&command, params).await?;
    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}
