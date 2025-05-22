# %% [markdown]
# # Wildfire Knowledge Graph Evaluation
#
# This notebook evaluates the performance of a wildfire knowledge graph agent by testing it on a variety of questions and comparing responses to expected outputs. The evaluation uses LangSmith to track performance metrics including response accuracy and tool usage.

# %%
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any
from wildfire_kg_api.orchestration.agent import create_wildfire_react_agent
from wildfire_kg_api.orchestration.state import State
from langsmith import Client
from langsmith.schemas import Example, Run, ExampleCreate
import asyncio
from dotenv import load_dotenv
import uuid
import nest_asyncio
import os
from datetime import datetime

# Load environment variables
load_dotenv(dotenv_path="../../applications/wildfire-kg-api/.env")

# Initialize LangSmith client
client = Client()

# Data paths
DATA_PATH = "../../data/evaluation"

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
    {
        "name": "tree-shrub-metrics",
        "description": "Knowledge graph tree shrub metrics evaluation dataset",
        "data_path": f"{DATA_PATH}/kg/tree_shrub_metrics.jsonl",
    },
    {
        "name": "fire-behavior-metrics",
        "description": "Knowledge graph fire behavior metrics evaluation dataset",
        "data_path": f"{DATA_PATH}/kg/fire_behavior_metrics.jsonl",
    },
    {
        "name": "vegetation-metrics",
        "description": "Knowledge graph vegetation metrics evaluation dataset",
        "data_path": f"{DATA_PATH}/kg/vegetation_metrics.jsonl",
    },
    {
        "name": "weather-metrics",
        "description": "Weather metrics evaluation dataset",
        "data_path": f"{DATA_PATH}/kg/weather_metrics.jsonl",
    },
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
    eval_data: List[Dict[str, Any]], dataset_config: Dict[str, Any]
) -> List[ExampleCreate]:
    examples = []
    for item in eval_data:
        examples.append(
            ExampleCreate(
                inputs={"question": item["user_query"]},
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

    # Extract the response from messages
    messages = run.outputs.get("messages", [])
    if not messages:
        return {
            "key": "response_contains",
            "score": 0.0,
            "comment": "No messages found in output",
        }

    # Get the last message (usually the assistant's response)
    last_message = messages[-1]
    actual_response = (
        last_message.get("content", "")
        if isinstance(last_message, dict)
        else str(last_message)
    )

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
    """Evaluate if the correct tools were used."""
    expected_tools = example.metadata.get("expected_tools", [])

    # Extract tools used from the run's messages
    tools_used = []
    messages = run.outputs.get("messages", [])

    for msg in messages:
        # 1. Check if it's a ToolMessage (direct tool usage)
        if hasattr(msg, "name") and getattr(msg, "name", None):
            tools_used.append(msg.name)

        # 2. Check for tool_calls list directly on the message object
        if hasattr(msg, "tool_calls") and isinstance(msg.tool_calls, list):
            for tool_call in msg.tool_calls:
                if isinstance(tool_call, dict) and "name" in tool_call:
                    tools_used.append(tool_call["name"])

        # 3. Check additional_kwargs for tool_calls
        if hasattr(msg, "additional_kwargs"):
            additional_kwargs = msg.additional_kwargs
            if (
                isinstance(additional_kwargs, dict)
                and "tool_calls" in additional_kwargs
            ):
                for tool_call in additional_kwargs["tool_calls"]:
                    if isinstance(tool_call, dict) and "function" in tool_call:
                        tool_name = tool_call["function"].get("name", "")
                        if tool_name:
                            tools_used.append(tool_name)

        # 4. Handle dictionary messages
        if isinstance(msg, dict):
            # Check for name field (ToolMessage as dict)
            if "name" in msg:
                tools_used.append(msg["name"])

            # Check for tool_calls list
            if "tool_calls" in msg and isinstance(msg["tool_calls"], list):
                for tool_call in msg["tool_calls"]:
                    if isinstance(tool_call, dict) and "name" in tool_call:
                        tools_used.append(tool_call["name"])

            # Check for additional_kwargs
            if "additional_kwargs" in msg and isinstance(
                msg["additional_kwargs"], dict
            ):
                additional_kwargs = msg["additional_kwargs"]
                if "tool_calls" in additional_kwargs:
                    for tool_call in additional_kwargs["tool_calls"]:
                        if isinstance(tool_call, dict) and "function" in tool_call:
                            tool_name = tool_call["function"].get("name", "")
                            if tool_name:
                                tools_used.append(tool_name)

    # Remove duplicates and ensure strings
    tools_used = [str(tool) for tool in tools_used]
    tools_used = list(set(tools_used))

    # Compare tools
    expected_set = set(expected_tools)
    actual_set = set(tools_used)

    # Check if all expected tools were used
    all_expected_used = expected_set.issubset(actual_set)
    score = 1.0 if all_expected_used else 0.0

    # Create a detailed comment
    if all_expected_used:
        if expected_set == actual_set:
            comment = f"Used exactly the expected tools: {', '.join(expected_tools)}"
        else:
            comment = f"Used all expected tools ({', '.join(expected_tools)}) plus additional tools: {', '.join(actual_set - expected_set)}"
    else:
        missing = expected_set - actual_set
        comment = f"Missing expected tools: {', '.join(missing)}"

    return {
        "key": "tool_usage",
        "score": score,
        "comment": comment,
        "metadata": {
            "expected_tools": list(expected_set),
            "actual_tools": list(actual_set),
        },
    }


# %% [markdown]
# ## Run Evaluation
#
# Now we'll load the test data, create LangSmith datasets, and run the evaluation on our agent.

# %%
# Create the agent graph
agent_graph = create_wildfire_react_agent()


# Define the function to evaluate
async def run_evaluation(question: Dict[str, str]) -> Dict[str, Any]:
    # Initialize state
    state = State(messages=[])
    # Extract the question string from the input dictionary
    question_str = question.get("question", "")
    # Add the question as a human message
    state.messages.append({"role": "human", "content": question_str})
    # Run the graph
    result = await agent_graph.ainvoke({"messages": state.messages})
    return result


# Run evaluation for all datasets
async def run_experiments():
    all_examples = []
    dataset_info = {}

    # Load and prepare evaluation data for all datasets
    for dataset_config in datasets:
        print(f"\nProcessing dataset: {dataset_config['name']}")

        # Load evaluation data
        eval_data = load_evaluation_data(dataset_config["data_path"])
        examples = create_langsmith_examples(eval_data, dataset_config)

        # Store dataset info for later reference
        dataset_info[dataset_config["name"]] = {
            "start_idx": len(all_examples),
            "end_idx": len(all_examples) + len(examples),
            "config": dataset_config,
        }

        # Add examples to combined list
        all_examples.extend(examples)

    # Create a single dataset in LangSmith for all examples with version
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_name = f"wildfire-kg-combined-v{timestamp}"

    print("\nCreating combined dataset")
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="Combined evaluation dataset for wildfire knowledge graph",
    )
    print(f"Dataset created with ID: {dataset.id}")

    # Add all examples to the dataset
    response = client.create_examples(
        dataset_id=dataset.id,
        examples=all_examples,
    )
    print(f"Added {len(all_examples)} total examples to the dataset")

    # Run the evaluation
    print("\nStarting evaluation for all datasets")
    experiment_results = await client.aevaluate(
        run_evaluation,
        data=dataset_name,
        evaluators=[evaluate_response_contains, evaluate_tool_usage],
        experiment_prefix=f"wildfire-kg-evaluation-v{timestamp}",
        num_repetitions=1,
        max_concurrency=4,
    )

    # Process results by dataset
    results_by_dataset = {}
    results_df = experiment_results.to_pandas()

    for dataset_name, info in dataset_info.items():
        # Get results for this dataset using indices
        dataset_results = results_df.iloc[info["start_idx"] : info["end_idx"]]

        # Calculate metrics
        response_scores = []
        if "feedback.response_contains" in dataset_results.columns:
            response_scores = (
                dataset_results["feedback.response_contains"].dropna().tolist()
            )

        tool_scores = []
        if "feedback.tool_usage" in dataset_results.columns:
            tool_scores = dataset_results["feedback.tool_usage"].dropna().tolist()

        overall_metrics = {}
        if response_scores:
            overall_metrics["Response Accuracy"] = sum(response_scores) / len(
                response_scores
            )
        if tool_scores:
            overall_metrics["Tool Usage Accuracy"] = sum(tool_scores) / len(tool_scores)

        results_by_dataset[dataset_name] = {
            "results": dataset_results,
            "metrics": overall_metrics,
        }

    return results_by_dataset


# For Jupyter notebook execution
try:
    nest_asyncio.apply()
    print("Running evaluations...")
    results = asyncio.get_event_loop().run_until_complete(run_experiments())
    print("All evaluations complete!")

    # Display results for each dataset
    for dataset_name, dataset_results in results.items():
        print(f"\nResults for {dataset_name}:")
        display(dataset_results["results"])

        print("\nOverall Evaluation Metrics:")
        for metric, value in dataset_results["metrics"].items():
            print(f"{metric}: {value:.2%}")

except Exception as e:
    print(f"Error running evaluations: {e}")
    import traceback

    traceback.print_exc()

# %% [markdown]
# ## Results and Metrics
#
# Display the evaluation results and calculate overall performance metrics for each dataset.

# %%
# Display results for each dataset
for dataset_name, dataset_results in results.items():
    print(f"\nResults for {dataset_name}:")
    results_df = dataset_results["results"]
    display(results_df)

    # Calculate and display overall metrics
    try:
        response_scores = []
        if "feedback.response_contains" in results_df.columns:
            response_scores = results_df["feedback.response_contains"].dropna().tolist()

        tool_scores = []
        if "feedback.tool_usage" in results_df.columns:
            tool_scores = results_df["feedback.tool_usage"].dropna().tolist()

        overall_metrics = {}
        if response_scores:
            overall_metrics["Response Accuracy"] = sum(response_scores) / len(
                response_scores
            )
        if tool_scores:
            overall_metrics["Tool Usage Accuracy"] = sum(tool_scores) / len(tool_scores)

        if overall_metrics:
            print("\nOverall Evaluation Metrics:")
            for metric, value in overall_metrics.items():
                print(f"{metric}: {value:.2%}")
        else:
            print("\nNo evaluation scores found in results")
    except Exception as e:
        print(f"Error calculating metrics: {e}")
        print("\nAvailable columns:", results_df.columns.tolist())
