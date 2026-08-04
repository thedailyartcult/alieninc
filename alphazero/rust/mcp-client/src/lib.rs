#![allow(unused_imports)]
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::env;
use std::error::Error;
use std::path::Path;
use std::process::{Command, Stdio};
use tokio::io::AsyncWriteExt;
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

/// Resolve the alphazero repository root in a machine-independent way.
///
/// Priority: $ALPHAZERO_ROOT env var, then common absolute locations.
fn az_root() -> String {
    if let Ok(root) = env::var("ALPHAZERO_ROOT") {
        if !root.is_empty() && Path::new(&root).exists() {
            return root;
        }
    }
    let candidates = [
        "/home/alieninc/alphazero",
        "/home/tablet/alieninc/alphazero",
    ];
    for candidate in candidates {
        if Path::new(candidate).exists() {
            return candidate.to_string();
        }
    }
    // Last resort: current working directory.
    env::current_dir()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| ".".to_string())
}

fn agent_command(script: &str) -> String {
    // PYTHONPATH must include alpha-zero-engine so the ai agents can import
    // the engine package (Character, Gender, social variables).
    format!(
        "cd {} && PYTHONPATH={}/alpha-zero-engine python3 ai/{}",
        az_root(),
        az_root(),
        script
    )
}

// ---------------------------------------------------------------------------
// Phase 6: AI agent handlers — bridge Go alphacore and Python AI agents.
// ---------------------------------------------------------------------------

async fn rust_interview_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let name = params.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let age = params.get("age").and_then(|v| v.as_i64()).unwrap_or(25);
    let gender = params.get("gender").and_then(|v| v.as_str()).unwrap_or("male");
    let initial_text = params.get("initial_interview_text").and_then(|v| v.as_str()).unwrap_or("");

    let input_json = json!({
        "name": name,
        "age": age,
        "gender": gender,
        "interview_text": initial_text,
    });

    let result = AlphaZeroResult::run_command(
        &agent_command("interview_agent.py"),
        Some(&serde_json::to_string(&input_json)?),
    ).await?;

    let profile_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(profile_data)
}

async fn rust_coach_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let character_json = params.get("character_json").and_then(|v| v.as_str()).unwrap_or("{}");
    let situation = params.get("situation").and_then(|v| v.as_str()).unwrap_or("general");
    let session_id = params.get("session_id").and_then(|v| v.as_str()).unwrap_or("");

    let input_json = json!({
        "character_json": character_json,
        "situation": situation,
        "session_id": session_id,
    });

    let result = AlphaZeroResult::run_command(
        &agent_command("life_coach.py"),
        Some(&serde_json::to_string(&input_json)?),
    ).await?;

    let advice_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(advice_data)
}

async fn rust_analyze_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let simulation_results = params.get("simulation_results").cloned().unwrap_or(json!([]));

    let input_json = json!({
        "simulation_results": simulation_results,
    });

    let result = AlphaZeroResult::run_command(
        &agent_command("decision_assistant.py"),
        Some(&serde_json::to_string(&input_json)?),
    ).await?;

    let analysis_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(analysis_data)
}

async fn rust_narrate_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let character_name = params.get("character_name").and_then(|v| v.as_str()).unwrap_or("Unknown");
    let simulation_result = params.get("simulation_result").cloned().unwrap_or(json!({}));

    let input_json = json!({
        "character_name": character_name,
        "simulation_result": simulation_result,
    });

    let result = AlphaZeroResult::run_command(
        &agent_command("storyteller.py"),
        Some(&serde_json::to_string(&input_json)?),
    ).await?;

    let narrative_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(narrative_data)
}

async fn rust_memory_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let operation = params.get("operation").and_then(|v| v.as_str()).unwrap_or("store");
    let data = params.get("data").cloned().unwrap_or(json!({}));
    let query = params.get("query").and_then(|v| v.as_str()).unwrap_or("");
    let session_id = params.get("session_id").and_then(|v| v.as_str()).unwrap_or("");
    let workspace = params.get("workspace").and_then(|v| v.as_str()).unwrap_or("alphazero");

    let input_json = json!({
        "operation": operation,
        "data": data,
        "query": query,
        "session_id": session_id,
        "workspace": workspace,
    });

    let result = AlphaZeroResult::run_command(
        &agent_command("memory_system.py"),
        Some(&serde_json::to_string(&input_json)?),
    ).await?;

    let memory_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(memory_data)
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
        &format!("cd {}/alpha-zero-engine/core && ./bin/alphacore forecast", az_root()),
        Some(&serde_json::to_string(&input_json)?),
    ).await?;

    let forecast_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(forecast_data)
}

async fn rust_compare_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let initial_value = params.get("initial_value").and_then(|v| v.as_f64()).unwrap_or(100000.0);
    let years = params.get("years").and_then(|v| v.as_i64()).unwrap_or(10);
    let market_returns = params.get("market_returns").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    let strategies = params.get("strategies").and_then(|v| v.as_array()).cloned().unwrap_or_default();
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
                    if let Some(num) = serde_json::Number::from_f64(val) {
                        alloc_map.insert(k.clone(), serde_json::Value::Number(num));
                    }
                }
            }
            spec.insert("allocations".to_string(), serde_json::Value::Object(alloc_map));
        }
        if let Some(expected_ret) = strat.get("expected_return").and_then(|v| v.as_f64()) {
            if let Some(num) = serde_json::Number::from_f64(expected_ret) {
                spec.insert("expected_return".to_string(), serde_json::Value::Number(num));
            }
        }
        if let Some(volatility) = strat.get("volatility").and_then(|v| v.as_f64()) {
            if let Some(num) = serde_json::Number::from_f64(volatility) {
                spec.insert("volatility".to_string(), serde_json::Value::Number(num));
            }
        }
        if let Some(sharpe) = strat.get("sharpe_target").and_then(|v| v.as_f64()) {
            if let Some(num) = serde_json::Number::from_f64(sharpe) {
                spec.insert("sharpe_target".to_string(), serde_json::Value::Number(num));
            }
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
        &format!("cd {}/alpha-zero-engine/core && ./bin/alphacore compare", az_root()),
        Some(&serde_json::to_string(&input_json)?),
    ).await?;

    let compare_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(compare_data)
}

pub async fn handle_command(command: &str, params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    match command {
        // Phase 6: AI agent commands
        "interview" => rust_interview_handler(params).await,
        "coach" => rust_coach_handler(params).await,
        "analyze" => rust_analyze_handler(params).await,
        "narrate" => rust_narrate_handler(params).await,
        "memory" => rust_memory_handler(params).await,
        // Native finance commands
        "forecast" => rust_forecast_handler(params).await,
        "market" => {
            let result = AlphaZeroResult::run_command(
                &format!("cd {}/alpha-zero-engine/core && ./bin/alphacore market", az_root()),
                None,
            ).await?;
            let market_data: serde_json::Value = serde_json::from_str(&result.output)?;
            Ok(market_data)
        },
        "compare" => rust_compare_handler(params).await,
        "stress" => {
            let result = AlphaZeroResult::run_command(
                &format!("cd {}/alpha-zero-engine/core && ./bin/alphacore stress", az_root()),
                None,
            ).await?;
            let stress_data: serde_json::Value = serde_json::from_str(&result.output)?;
            Ok(stress_data)
        },
        "benchmark" => {
            let input_json = serde_json::to_string(&params)?;
            let result = AlphaZeroResult::run_command(
                &format!("cd {}/alpha-zero-engine/core && ./bin/alphacore benchmark", az_root()),
                Some(&input_json),
            ).await?;
            let benchmark_data: serde_json::Value = serde_json::from_str(&result.output)?;
            Ok(benchmark_data)
        },
        _ => Err(format!("Unknown command: {}", command).into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn az_root_resolves_existing_path() {
        let root = az_root();
        assert!(!root.is_empty(), "az_root should resolve to a path");
        assert!(Path::new(&root).exists(), "az_root should exist");
    }

    #[tokio::test]
    async fn memory_handler_returns_json() {
        let result = rust_memory_handler(json!({
            "operation": "retrieve",
            "query": "nothing matches this",
            "workspace": "rust_test_ws",
        }))
        .await;
        assert!(result.is_ok(), "memory handler should succeed");
        let value = result.unwrap();
        assert_eq!(value.get("status").and_then(|v| v.as_str()), Some("success"));
    }
}
