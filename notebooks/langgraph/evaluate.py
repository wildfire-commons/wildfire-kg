# %% [markdown]
# # Wildfire Knowledge Graph Evaluation
#
# This notebook evaluates the performance of a wildfire knowledge graph agent by testing it on a variety of questions and comparing responses to expected outputs. The evaluation uses LangSmith to track performance metrics including response accuracy and tool usage.

# %%
import json
import pandas as pd
from typing import Dict, List, Any, Optional
from wildfire_kg_api.orchestration.agent import create_wildfire_react_agent
from wildfire_kg_api.orchestration.state import State
from langsmith import Client
from langsmith.schemas import Example, Run, ExampleCreate
import asyncio
from dotenv import load_dotenv
import nest_asyncio
from datetime import datetime
from langchain_core.runnables.config import RunnableConfig
from collections import Counter
from wildfire_kg_api.orchestration.models import (
    AVAILABLE_MODELS,
    LITELLM_MODELS,
    OPENAI_MODELS,
    AGENT_COMPATIBLE_MODELS,
    is_agent_compatible,
    get_default_temperature,
)
import os
import logging
import pathlib

# Load environment variables
load_dotenv(dotenv_path="../../applications/wildfire-kg-api/.env")

# Initialize LangSmith client
client = Client()

# Data paths
DATA_PATH = "../../data/evaluation"

# ============================================================================
# CONFIGURATION INPUTS
# ============================================================================
# Models that can be used as agents (must support ReAct pattern)
# AGENT_MODELS_TO_TEST = AGENT_COMPATIBLE_MODELS
AGENT_MODELS_TO_TEST = ["llama3-sdsc"]

# Models that can be used for knowledge graph tools (don't need ReAct pattern)
# KG_MODELS_TO_TEST = AVAILABLE_MODELS  # All models can be used for KG tools
KG_MODELS_TO_TEST = ["DeepSeek-R1-Distill-Qwen-32B"]

# Temperatures to test
# TEMPERATURES_TO_TEST = [0.0, 0.1, 0.2]
TEMPERATURES_TO_TEST = [0.2]


# ============================================================================
# GENERATE ACTIVE EXPERIMENT CONFIGURATIONS
# ============================================================================
active_experiment_configs: List[Dict[str, Any]] = []

# Define a list of temperatures to iterate over for configurable models.
# If TEMPERATURES_TO_TEST is empty, use [None] to signify one run using model defaults or fixed behavior.
effective_temps_for_iteration = TEMPERATURES_TO_TEST if TEMPERATURES_TO_TEST else [None]

print("Generating experiment configurations...")
for agent_model in AGENT_MODELS_TO_TEST:
    is_agent_temp_configurable = get_default_temperature(agent_model) is not None
    # Temps to loop for the current agent model:
    # - If configurable, use all effective_temps_for_iteration.
    # - If not configurable, use only [None] to represent a single, non-varied setting.
    agent_model_temps_to_loop = (
        effective_temps_for_iteration if is_agent_temp_configurable else [None]
    )

    for agent_temp_setting in agent_model_temps_to_loop:
        for kg_model in KG_MODELS_TO_TEST:
            if not KG_MODELS_TO_TEST:
                print(
                    f"Warning: KG_MODELS_TO_TEST is empty. Skipping KG model loop for agent {agent_model}."
                )
                continue

            is_kg_temp_configurable = get_default_temperature(kg_model) is not None
            # Temps to loop for the current KG model:
            kg_model_temps_to_loop = (
                effective_temps_for_iteration if is_kg_temp_configurable else [None]
            )

            for kg_temp_setting in kg_model_temps_to_loop:
                config_entry = {
                    "agent_model": agent_model,
                    "agent_temperature_config": agent_temp_setting,
                    "kg_model": kg_model,
                    "kg_temperature_config": kg_temp_setting,
                }
                active_experiment_configs.append(config_entry)

print(
    f"Generated {len(active_experiment_configs)} experiment configurations to run (all combinations of agent/KG models with independent temperatures where applicable):"
)
for i, cfg in enumerate(active_experiment_configs):
    agent_temp_display = (
        cfg["agent_temperature_config"]
        if cfg["agent_temperature_config"] is not None
        else "N/A"
    )
    kg_temp_display = (
        cfg["kg_temperature_config"]
        if cfg["kg_temperature_config"] is not None
        else "N/A"
    )
    print(
        f"  {i+1}. Agent: {cfg['agent_model']} (Temp: {agent_temp_display}), KG: {cfg['kg_model']} (Temp: {kg_temp_display})"
    )

if not active_experiment_configs and any([AGENT_MODELS_TO_TEST, KG_MODELS_TO_TEST]):
    print(
        "Warning: No experiment configurations were generated. This might be due to empty TEMPERATURES_TO_TEST list when it was expected to have values, or other logic issues. Evaluation will not run."
    )
elif not active_experiment_configs:
    print(
        "Warning: No experiment configurations generated as AGENT_MODELS_TO_TEST or KG_MODELS_TO_TEST might be empty. Evaluation will not run."
    )

# %% [markdown]
# ## Dataset Configuration
#
# Define the datasets to be used for evaluation. Each dataset should have:
# - A unique name
# - A description
# - A path to the data file
# - Expected tools and tags

# %%

# Dataset configuration
datasets = [
    # {
    #     "name": "tree-shrub-metrics",
    #     "description": "Knowledge graph tree shrub metrics evaluation dataset",
    #     "data_path": f"{DATA_PATH}/kg/tree_shrub_metrics.jsonl",
    # },
    # {
    #     "name": "fire-behavior-metrics",
    #     "description": "Knowledge graph fire behavior metrics evaluation dataset",
    #     "data_path": f"{DATA_PATH}/kg/fire_behavior_metrics.jsonl",
    # },
    # {
    #     "name": "vegetation-metrics",
    #     "description": "Knowledge graph vegetation metrics evaluation dataset",
    #     "data_path": f"{DATA_PATH}/kg/vegetation_metrics.jsonl",
    # },
    # {
    #     "name": "basic-web-search",
    #     "description": "Basic web search evaluation dataset",
    #     "data_path": f"{DATA_PATH}/web_search/basic_web_search.jsonl",
    # },
    {
        "name": "weather-metrics",
        "description": "Weather metrics evaluation dataset",
        "data_path": f"{DATA_PATH}/kg/weather_metrics.jsonl",
    },
    # {
    #     "name": "quick-test",
    #     "description": "Quick test dataset",
    #     "data_path": f"{DATA_PATH}/test/quick_test.jsonl",
    # },
]

# %% [markdown]
# ## Evaluation Setup
#
# We'll use the following components for evaluation:
#
# 1. **Data Loading**: Load test cases from JSONL files containing questions and expected responses
# 2. **LangSmith Integration**: Track runs and evaluate responses with LangSmith
# 3. **Evaluators**: Custom evaluators to check response accuracy and tool usage
# 4. **Agent Execution**: Run the wildfire knowledge graph agent on each test case


# %%
# Load evaluation data
def load_evaluation_data(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, "r") as f:
        return [json.loads(line) for line in f]


# Convert evaluation data to LangSmith examples
def create_langsmith_examples(
    eval_data: List[Dict[str, Any]],
    dataset_config: Dict[str, Any],
    agent_model_name: str,
    temperature_to_test: float,
    kg_model_name: str = None,
) -> List[ExampleCreate]:
    """
    Create LangSmith examples for evaluation.

    Args:
        eval_data: List of evaluation data items
        dataset_config: Dataset configuration
        agent_model_name: Name of the agent model to test
        temperature_to_test: Temperature setting to test
        kg_model_name: Name of the KG model to test (defaults to agent_model_name if None)

    Returns:
        List of LangSmith examples
    """
    # If kg_model_name not specified, use agent_model_name
    if kg_model_name is None:
        kg_model_name = agent_model_name

    examples = []
    for item in eval_data:
        examples.append(
            ExampleCreate(
                inputs={
                    "question": item["user_query"],
                    "agent_model": agent_model_name,
                    "kg_model": kg_model_name,
                    "temperature": temperature_to_test,
                },
                outputs={"expected_response": item["expected_response_contains"]},
                metadata={
                    "tags": item["tags"],
                    "expected_tools": item["expected_tools"],
                },
            )
        )
    return examples


# %% [markdown]
# ## Evaluation Functions
#
# We use two main evaluators:
#
# 1. **Response Content Evaluator**: Uses an LLM to determine if responses contain all expected information
# 2. **Tool Usage Evaluator**: Checks if the agent used the correct tools during its execution


# %%
# Create evaluation functions
def evaluate_response_contains(run: Run, example: Example) -> Dict[str, Any]:
    """Evaluate if the response contains the expected information using an LLM as judge."""
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
    )  # Added for type checking

    # Extract the response from messages
    messages = run.outputs.get("messages", [])
    if not messages:
        return {
            "key": "response_contains",
            "score": 0.0,
            "comment": "No messages found in output",
        }

    # Get the last message (usually the assistant's response)
    last_message_raw = messages[-1]
    actual_response = ""

    # Handle different message formats (direct content, AIMessage, dict)
    if isinstance(last_message_raw, str):
        actual_response = last_message_raw
    elif hasattr(last_message_raw, "content"):  # Covers AIMessage, HumanMessage etc.
        actual_response = last_message_raw.content
    elif isinstance(last_message_raw, dict) and "content" in last_message_raw:
        actual_response = last_message_raw["content"]
    else:  # Fallback if structure is unexpected
        actual_response = str(last_message_raw)

    # Get expected information
    expected_info = example.outputs.get("expected_response", [])
    if not expected_info or not isinstance(expected_info, list):
        return {
            "key": "response_contains",
            "score": 0.0,
            "comment": "No expected response defined",
        }

    # Format expected info for the prompt
    expected_str = ", ".join([str(item) for item in expected_info])

    # Create LLM for evaluation
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

    # Create prompt for the LLM judgment
    template = """You are an evaluator assessing response accuracy.

You will be given EXPECTED INFORMATION and an ACTUAL RESPONSE.

Here is the evaluation criteria to follow:
(1) Evaluate the actual response based ONLY on whether it contains the expected information
(2) It is OK if the actual response contains more information than expected, as long as it includes ALL the required information
(3) The response should not contain any statements that contradict the expected information

Expected Information: {expected_info}

Actual Response: {actual_response}

First, analyze if the actual response contains ALL the expected information. 
Then provide a score between 0.0 and 1.0, where:
- 1.0 means the response completely contains all the expected information
- 0.0 means the response contains none of the expected information
- Values in between represent partial matches

Your response must be in the following format:
Analysis: <your detailed analysis>
Score: <a number between 0.0 and 1.0>
Explanation: <short explanation for the score>
"""

    prompt = ChatPromptTemplate.from_template(template)

    # Get evaluation from LLM
    result = llm.invoke(
        prompt.format(expected_info=expected_str, actual_response=actual_response)
    )
    response_text = result.content

    # Parse the LLM response to extract the score and explanation
    score = 0.0
    explanation = "Unable to parse LLM response"

    try:
        # Try to extract score using regex
        import re

        score_match = re.search(r"Score:\s*(0\.\d+|1\.0|1|0)", response_text)
        if score_match:
            score = float(score_match.group(1))

        # Extract explanation
        explanation_match = re.search(
            r"Explanation:\s*(.*?)($|\n\n)", response_text, re.DOTALL
        )
        if explanation_match:
            explanation = explanation_match.group(1).strip()
        else:
            # If no specific explanation section, use the whole response
            explanation = response_text
    except Exception as e:
        explanation = f"Error parsing LLM response: {str(e)}"

    return {
        "key": "response_contains",
        "score": score,
        "comment": explanation,
        "metadata": {"expected_info": expected_str, "llm_full_response": response_text},
    }


def evaluate_tool_usage(run: Run, example: Example) -> Dict[str, Any]:
    """Evaluate tool usage based on expected tools, penalizing missing, overuse, and unexpected calls."""
    expected_tools_list = example.metadata.get("expected_tools", [])
    expected_set = set(expected_tools_list)

    all_actual_invocations = []
    messages = run.outputs.get("messages", [])

    # Iterate through messages to find tool calls proposed by the AI
    for msg in messages:
        # LangChain AIMessage objects (and their dict representations)
        # often store tool calls in `tool_calls` or `additional_kwargs.tool_calls`

        current_msg_tool_calls = []

        # 1. Check `tool_calls` attribute directly on the message object
        # These are typically parsed from the model's output directly.
        if hasattr(msg, "tool_calls") and isinstance(msg.tool_calls, list):
            for tool_call in msg.tool_calls:
                if isinstance(tool_call, dict) and "name" in tool_call:
                    current_msg_tool_calls.append(str(tool_call["name"]))
                # Handle cases where tool_call might be an object with a 'name' attribute
                elif hasattr(tool_call, "name") and getattr(tool_call, "name", None):
                    current_msg_tool_calls.append(str(tool_call.name))

        # 2. Check `additional_kwargs` for tool_calls (common for OpenAI models)
        # This is often where the raw tool call requests from the LLM are stored.
        elif hasattr(msg, "additional_kwargs") and isinstance(
            msg.additional_kwargs, dict
        ):
            additional_kwargs = msg.additional_kwargs
            if "tool_calls" in additional_kwargs and isinstance(
                additional_kwargs["tool_calls"], list
            ):
                for tool_call_item in additional_kwargs["tool_calls"]:
                    # OpenAI format: tool_calls -> [ { "function": { "name": "..." } } ]
                    if (
                        isinstance(tool_call_item, dict)
                        and "function" in tool_call_item
                    ):
                        function_dict = tool_call_item["function"]
                        if isinstance(function_dict, dict) and "name" in function_dict:
                            current_msg_tool_calls.append(str(function_dict["name"]))
                    # Simpler format sometimes seen: tool_calls -> [ { "name": "..." } ]
                    elif isinstance(tool_call_item, dict) and "name" in tool_call_item:
                        current_msg_tool_calls.append(str(tool_call_item["name"]))

        # 3. Handle direct dictionary representation of messages (e.g. from serialization)
        elif isinstance(msg, dict):
            if "tool_calls" in msg and isinstance(msg["tool_calls"], list):
                for tool_call_dict in msg["tool_calls"]:
                    if isinstance(tool_call_dict, dict) and "name" in tool_call_dict:
                        current_msg_tool_calls.append(str(tool_call_dict["name"]))
            elif "additional_kwargs" in msg and isinstance(
                msg["additional_kwargs"], dict
            ):
                additional_kwargs_dict = msg["additional_kwargs"]
                if "tool_calls" in additional_kwargs_dict and isinstance(
                    additional_kwargs_dict["tool_calls"], list
                ):
                    for tool_call_item_dict in additional_kwargs_dict["tool_calls"]:
                        if (
                            isinstance(tool_call_item_dict, dict)
                            and "function" in tool_call_item_dict
                        ):
                            function_item_dict = tool_call_item_dict["function"]
                            if (
                                isinstance(function_item_dict, dict)
                                and "name" in function_item_dict
                            ):
                                current_msg_tool_calls.append(
                                    str(function_item_dict["name"])
                                )
                        elif (
                            isinstance(tool_call_item_dict, dict)
                            and "name" in tool_call_item_dict
                        ):
                            current_msg_tool_calls.append(
                                str(tool_call_item_dict["name"])
                            )

        # Add all tool calls found in this message to the main list.
        # This structure assumes one message contains all tool calls for a given step.
        all_actual_invocations.extend(current_msg_tool_calls)

    actual_counts = Counter(all_actual_invocations)

    score = 1.0
    # Define penalties
    penalty_for_missing_expected_tool = (
        0.5  # Penalty if an expected tool is not called at all
    )
    penalty_per_unique_unexpected_tool = (
        0.25  # Penalty for each type of unexpected tool used
    )
    penalty_per_extra_invocation_of_any_tool = (
        0.1  # Penalty for each call beyond the first, for ANY tool
    )
    min_score_if_any_expected_called = (
        0.3  # Floor if at least one expected tool was called
    )

    comments = []
    any_expected_tool_called_flag = False

    # 1. Evaluate expected tools (missing, and overuse of expected tools)
    for tool_name in expected_set:
        call_count = actual_counts.get(tool_name, 0)
        if call_count > 0:
            any_expected_tool_called_flag = True
            if call_count > 1:
                score -= (call_count - 1) * penalty_per_extra_invocation_of_any_tool
                comments.append(
                    f"Expected tool '{tool_name}' called {call_count} times (expected once)"
                )
        else:  # Expected tool was not called
            score -= penalty_for_missing_expected_tool
            comments.append(f"Missing expected tool: {tool_name}")

    # 2. Evaluate unexpected tools (penalty for each unique unexpected tool + overuse of unexpected tools)
    unique_unexpected_tools_called = []
    for tool_name, call_count in actual_counts.items():
        if tool_name not in expected_set:
            if (
                tool_name not in unique_unexpected_tools_called
            ):  # Apply unique penalty only once per tool type
                score -= penalty_per_unique_unexpected_tool
                unique_unexpected_tools_called.append(tool_name)

            # Now, penalize overuse for this unexpected tool if called more than once
            if call_count > 1:
                score -= (call_count - 1) * penalty_per_extra_invocation_of_any_tool

            # Consolidate comments for unexpected tools later or add more detail here if needed

    if unique_unexpected_tools_called:
        unexpected_details = []
        for tool_name in unique_unexpected_tools_called:
            count = actual_counts[tool_name]
            detail = f"'{tool_name}' (called {count} times)"
            unexpected_details.append(detail)
        comments.append(f"Used unexpected tools: {(', '.join(unexpected_details))}")

    # Apply minimum score rule and cap
    if any_expected_tool_called_flag and score < min_score_if_any_expected_called:
        score = min_score_if_any_expected_called

    final_score = max(0.0, min(1.0, score))

    if (
        not comments
        and final_score == 1.0
        and not expected_set
        and not all_actual_invocations
    ):
        comment_str = "No tools were expected, and no tools were used."
    elif not comments and final_score == 1.0:
        comment_str = f"Used exactly the expected tools: {', '.join(sorted(list(expected_set)))} (each once)."
    elif not comments:  # Should ideally not happen if score is not 1.0
        comment_str = "Tool usage evaluation resulted in a score change, but no specific comments generated."
    else:
        comment_str = "; ".join(comments)

    return {
        "key": "tool_usage",
        "score": final_score,
        "comment": comment_str,
        "metadata": {
            "expected_tools": expected_tools_list,
            "actual_tool_invocations": all_actual_invocations,
            "actual_tool_counts": dict(actual_counts),
        },
    }


# %% [markdown]
# ## Run Evaluation
#
# Now we'll load the test data, create LangSmith datasets, and run the evaluation on our agent.


# Run evaluation for all datasets
async def run_experiments():
    if not active_experiment_configs:
        print("No active experiment configurations. Skipping evaluation runs.")
        return []

    print(f"Testing with {len(active_experiment_configs)} generated configurations.")

    all_experiment_results_summary = (
        []
    )  # To store high-level results from each experiment run

    # Generate timestamp for this evaluation run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create a single dataset with examples that don't include model-specific parameters
    print("\n=== Creating shared evaluation dataset ===")
    dataset_examples = []

    # Load examples from all datasets
    for dataset_file_config in datasets:
        print(f"Loading dataset: {dataset_file_config['name']}")
        eval_data = load_evaluation_data(dataset_file_config["data_path"])

        # Create examples without model-specific parameters
        for item in eval_data:
            dataset_examples.append(
                ExampleCreate(
                    inputs={"question": item["user_query"]},
                    outputs={"expected_response": item["expected_response_contains"]},
                    metadata={
                        "tags": item.get("tags", []),
                        "expected_tools": item.get("expected_tools", []),
                    },
                )
            )

        print(f"  Added {len(eval_data)} examples from {dataset_file_config['name']}")

    # Create the shared dataset
    shared_dataset_name = f"wildfire-kg-eval-{timestamp}"
    print(f"\nCreating dataset: {shared_dataset_name}")
    shared_dataset = client.create_dataset(
        dataset_name=shared_dataset_name,
        description=f"Wildfire KG evaluation dataset for multiple model configurations",
    )

    # Add examples to the dataset
    client.create_examples(
        dataset_id=shared_dataset.id,
        examples=dataset_examples,
    )
    print(f"Created dataset with {len(dataset_examples)} examples")

    # Run experiments for different model configurations
    for exp_config in active_experiment_configs:
        agent_model = exp_config["agent_model"]
        kg_model = exp_config["kg_model"]
        agent_temp_config_val = exp_config["agent_temperature_config"]
        kg_temp_config_val = exp_config["kg_temperature_config"]

        # These checks are now primarily for clear logging; actual config handled by `None` values passed to get_llm_params
        is_agent_temp_configurable = get_default_temperature(agent_model) is not None
        is_kg_temp_configurable = get_default_temperature(kg_model) is not None

        agent_temp_display_log = (
            agent_temp_config_val if agent_temp_config_val is not None else "N/A"
        )
        kg_temp_display_log = (
            kg_temp_config_val if kg_temp_config_val is not None else "N/A"
        )

        print(
            f"\n{'='*80}\n"
            f"Evaluating with (from pre-generated config):\n"
            f"  Agent Model: {agent_model} (Configurable Temp: {is_agent_temp_configurable}, Setting: {agent_temp_display_log})\n"
            f"  KG Model: {kg_model} (Configurable Temp: {is_kg_temp_configurable}, Setting: {kg_temp_display_log})\n"
            f"{'='*80}"
        )

        run_config = RunnableConfig(
            configurable={
                "agent_model_name": agent_model,
                "agent_temperature": agent_temp_config_val,  # Pass agent temp; LLM setup will handle applicability
                "kg_model_name": kg_model,
                "kg_temperature": kg_temp_config_val,  # Pass KG temp; LLM setup will handle applicability
                "verbose": True,
            },
        )

        agent_temp_str_for_prefix = (
            str(agent_temp_config_val).replace(".", "_")
            if agent_temp_config_val is not None
            else "N/A"
        )
        kg_temp_str_for_prefix = (
            str(kg_temp_config_val).replace(".", "_")
            if kg_temp_config_val is not None
            else "N/A"
        )

        experiment_prefix = f"AGT:{agent_model.replace('/', '_')}-{agent_temp_str_for_prefix}_KG:{kg_model.replace('/', '_')}-{kg_temp_str_for_prefix}-{timestamp}"
        print(f"Running experiment: {experiment_prefix}")

        agent_graph = create_wildfire_react_agent(config=run_config)

        async def target_func(inputs):
            question = inputs.get("question", "")
            from langchain_core.messages import HumanMessage

            result = await agent_graph.ainvoke(
                {"messages": [HumanMessage(content=question)]},
                config=run_config,
            )
            return result

        experiment_run_details = await client.aevaluate(
            target_func,
            data=shared_dataset_name,
            evaluators=[evaluate_response_contains, evaluate_tool_usage],
            experiment_prefix=experiment_prefix,
            metadata={
                "agent_model": agent_model,
                "kg_model": kg_model,
                "agent_temperature_config": agent_temp_config_val,
                "kg_temperature_config": kg_temp_config_val,
            },
            num_repetitions=2,
            max_concurrency=4,
        )
        print(
            f"Evaluation complete for agent={agent_model} (temp_cfg={agent_temp_config_val}), kg={kg_model} (temp_cfg={kg_temp_config_val})"
        )

        results_df = experiment_run_details.to_pandas()

        response_accuracy = float("nan")
        if "feedback.response_contains" in results_df.columns:
            response_scores = results_df["feedback.response_contains"].dropna().tolist()
            if response_scores:
                response_accuracy = sum(response_scores) / len(response_scores)

        tool_accuracy = float("nan")
        if "feedback.tool_usage" in results_df.columns:
            tool_scores = results_df["feedback.tool_usage"].dropna().tolist()
            if tool_scores:
                tool_accuracy = sum(tool_scores) / len(tool_scores)

        print(f"\nResults Summary:")
        print(f"{'='*50}")
        print(
            f"Response Accuracy: {response_accuracy:.2%}"
            if not pd.isna(response_accuracy)
            else "Response Accuracy: N/A"
        )
        print(
            f"Tool Usage Accuracy: {tool_accuracy:.2%}"
            if not pd.isna(tool_accuracy)
            else "Tool Usage Accuracy: N/A"
        )
        print(f"{'='*50}")

        all_experiment_results_summary.append(
            {
                "model_name": agent_model,
                "kg_model_name": kg_model,
                "agent_temperature_config": agent_temp_config_val,
                "kg_temperature_config": kg_temp_config_val,
                "dataset_name": shared_dataset_name,
                "results_dataframe": results_df,
                "response_accuracy": response_accuracy,
                "tool_accuracy": tool_accuracy,
                "total_examples": len(dataset_examples),
            }
        )

    print("\n" + "=" * 80)
    print("ALL EVALUATIONS COMPLETE")
    print("=" * 80)

    # Create a summary table of all results
    summary_data = []
    for summary in all_experiment_results_summary:
        summary_data.append(
            {
                "Agent Model": summary["model_name"],
                "KG Model": summary["kg_model_name"],
                "Agent Temperature": summary["agent_temperature_config"],
                "KG Temperature": summary["kg_temperature_config"],
                "Response Accuracy": (
                    f"{summary['response_accuracy']:.2%}"
                    if not pd.isna(summary["response_accuracy"])
                    else "N/A"
                ),
                "Tool Usage Accuracy": (
                    f"{summary['tool_accuracy']:.2%}"
                    if not pd.isna(summary["tool_accuracy"])
                    else "N/A"
                ),
                "Examples": summary["total_examples"],
                "Dataset": summary["dataset_name"],
            }
        )

    summary_df = pd.DataFrame(summary_data)
    print("\nOverall Results Summary:")
    print("=" * 80)
    display(summary_df)
    print("=" * 80)

    print("Evaluation complete - view detailed results in the LangSmith UI")

    return all_experiment_results_summary


# For Jupyter notebook execution
try:
    nest_asyncio.apply()
    print("Running evaluations...")
    # 'results' will now be a list of summaries, one for each model/temp configuration
    all_results_summary = asyncio.get_event_loop().run_until_complete(run_experiments())
    print("All evaluations complete!")

    # Display results for each dataset
    print("\n\n--- Overall Summary of Evaluation Runs ---")
    for summary in all_results_summary:
        print(
            f"\nModel: {summary['model_name']}, KG Model: {summary['kg_model_name']}, Temperature: {summary['agent_temperature_config']}, {summary['kg_temperature_config']}"
        )
        print(
            f"  Response Accuracy: {summary['response_accuracy']:.2%}"
            if not pd.isna(summary["response_accuracy"])
            else "  Response Accuracy: N/A"
        )
        print(
            f"  Tool Usage Accuracy: {summary['tool_accuracy']:.2%}"
            if not pd.isna(summary["tool_accuracy"])
            else "  Tool Usage Accuracy: N/A"
        )
        print("  Detailed results table:")
        display(
            summary["results_dataframe"]
        )  # Display the pandas DataFrame for this run

except Exception as e:
    print(f"Error running evaluations: {e}")
    import traceback

    traceback.print_exc()
