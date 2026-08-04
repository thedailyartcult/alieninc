#![allow(unused_imports)]
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::error::Error;
use std::process::{Command, Stdio};
use tokio::process::Command as AsyncCommand;

#[derive(Debug, Deserialize, Serialize)]
struct AlphaZeroResult {
    output: String,
    exit_code: i32,
}

impl AlphaZeroResult {
    async fn run_command(cmd: &str, input: Option<&str>) -> Result<Self, Box<dyn Error>> {
        let mut command = AsyncCommand::new("bash");
        command.arg("-c").arg(cmd);
        
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;
        
        if let Some(input_data) = input {
            if let Some(stdin) = child.stdin.as_mut() {
                stdin.write_all(input_data.as_bytes()).await?;
            }
        }
        
        let stdout = child.wait_with_output().await?;
        
        Ok(Self {
            output: String::from_utf8_lossy(&stdout.stdout).to_string(),
            exit_code: stdout.status.code().unwrap_or(1) as i32,
        })
    }
}

async fn rust_forecast_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let initial_value = params.get("initial_value").and_then(|v| v.as_f64()).unwrap_or(100000.0);
    let years = params.get("years").and_then(|v| v.as_i64()).unwrap_or(10);
    let paths = params.get("paths").and_then(|v| v.as_i64()).unwrap_or(1000);
    let seed = params.get("seed").and_then(|v| v.as_i64()).unwrap_or(42);
    
    let input_json = json!({
        "initial_value": initial_value,
        "years": years,
        "paths": paths,
        "seed": seed,
    });
    
    let result = AlphaZeroResult::run_command(
        "cd /home/alieninc/alphazero/alpha-zero-engine/core && ./bin/alphacore forecast",
        Some(&serde_json::to_string(&input_json)?),
    ).await?;
    
    let forecast_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(forecast_data)
}

async fn rust_compare_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let initial_value = params.get("initial_value").and_then(|v| v.as_f64()).unwrap_or(100000.0);
    let years = params.get("years").and_then(|v| v.as_i64()).unwrap_or(10);
    let market_returns = params.get("market_returns").and_then(|v| v.as_array()).unwrap_or(&vec![]);
    let strategies = params.get("strategies").and_then(|v| v.as_array()).unwrap_or(&vec![]);
    let seed = params.get("seed").and_then(|v| v.as_i64()).unwrap_or(42);
    
    let market_returns_vec: Vec<f64> = market_returns.iter().filter_map(|v| v.as_f64()).collect();
    let mut strategies_vec = Vec::new();
    
    for strat in strategies.iter().filter_map(|v| v.as_object()) {
        let mut spec = serde_json::Map::new();
        
        if let Some(name) = strat.get("name").and_then(|v| v.as_str()) {
            spec.insert("name".to_string(), serde_json::Value::String(name.to_string()));
        }
        if let Some(display_name) = strat.get("display_name").and_then(|v| v.as_str()) {
            spec.insert("display_name".to_string(), serde_json::Value::String(display_name.to_string()));
        }
        if let Some(allocations) = strat.get("allocations").and_then(|v| v.as_object()) {
            let mut alloc_map = serde_json::Map::new();
            for (k, v) in allocations {
                if let Some(val) = v.as_f64() {
                    alloc_map.insert(k.clone(), serde_json::Value::Number(val.into()));
                }
            }
            spec.insert("allocations".to_string(), serde_json::Value::Object(alloc_map));
        }
        if let Some(expected_ret) = strat.get("expected_return").and_then(|v| v.as_f64()) {
            spec.insert("expected_return".to_string(), serde_json::Value::Number(expected_ret.into()));
        }
        if let Some(volatility) = strat.get("volatility").and_then(|v| v.as_f64()) {
            spec.insert("volatility".to_string(), serde_json::Value::Number(volatility.into()));
        }
        if let Some(sharpe) = strat.get("sharpe_target").and_then(|v| v.as_f64()) {
            spec.insert("sharpe_target".to_string(), serde_json::Value::Number(sharpe.into()));
        }
        
        strategies_vec.push(serde_json::Value::Object(spec));
    }
    
    let input_json = json!({
        "initial_value": initial_value,
        "years": years,
        "market_returns": market_returns_vec,
        "strategies": strategies_vec,
        "seed": seed,
    });
    
    let result = AlphaZeroResult::run_command(
        "cd /home/alieninc/alphazero/alpha-zero-engine/core && ./bin/alphacore compare",
        Some(&serde_json::to_string(&input_json)?),
    ).await?;
    
    let compare_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(compare_data)
}

pub async fn handle_command(command: &str, params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    match command {
        "forecast" => rust_forecast_handler(params).await,
        "market" => {
            let result = AlphaZeroResult::run_command(
                "cd /home/alieninc/alphazero/alpha-zero-engine/core && ./bin/alphacore market",
                None,
            ).await?;
            let market_data: serde_json::Value = serde_json::from_str(&result.output)?;
            Ok(market_data)
        },
        "compare" => rust_compare_handler(params).await,
        "stress" => {
            let result = AlphaZeroResult::run_command(
                "cd /home/alieninc/alphazero/alpha-zero-engine/core && ./bin/alphacore stress",
                None,
            ).await?;
            let stress_data: serde_json::Value = serde_json::from_str(&result.output)?;
            Ok(stress_data)
        },
        "benchmark" => {
            let input_json = serde_json::to_string(&params)?;
            let result = AlphaZeroResult::run_command(
                "cd /home/alieninc/alphazero/alpha-zero-engine/core && ./bin/alphacore benchmark",
                Some(&input_json),
            ).await?;
            let benchmark_data: serde_json::Value = serde_json::from_str(&result.output)?;
            Ok(benchmark_data)
        },
        _ => Err(format!("Unknown command: {}", command).into()),
    }
}