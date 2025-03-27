from langsmith import evaluate, Client
from src.orchestration.graph.graph_factory import get_graph

# 1. Create and/or select your dataset
client = Client()
dataset_name = "Baseline"

# Option 1: Load the dataset and filter examples
dataset = client.read_dataset(dataset_name=dataset_name)
examples = list(client.list_examples(dataset_id=dataset.id))

# Option 2: Filter examples by specific criteria
filtered_examples = examples[:1]  # Just use the first example


# 2. Define an evaluator
def exact_match(outputs: dict, reference_outputs: dict) -> bool:
    return outputs == reference_outputs


# 3. Run an evaluation on the filtered subset
# Get the graph instance
graph = get_graph()

evaluate(
    graph.invoke,  # Use the graph's invoke method directly
    data=filtered_examples,  # Use the filtered subset instead of the full dataset
    evaluators=[exact_match],
    experiment_prefix="Wildfire KG Graph Evaluation - Subset",
)

# If you want to evaluate on a specific split:
# evaluate(
#     graph.invoke,
#     data=test_examples,  # Use only the test split
#     evaluators=[exact_match],
#     experiment_prefix="Wildfire KG Graph Evaluation - Test Split",
# )
