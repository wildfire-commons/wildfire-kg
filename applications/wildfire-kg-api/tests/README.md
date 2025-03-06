# LangGraph Testing Tools

This directory contains tools and utilities for testing your LangGraph applications, particularly the Wildfire KG API.

## Directory Structure

```
tests/
├── streamlit/           # Streamlit app directory
│   └── app.py           # Main Streamlit application
├── utils/               # Shared utility modules
│   └── test_config_manager.py  # Configuration management utilities
├── performance/         # Performance testing utilities
│   └── run_performance_tests.py  # Script for running performance tests
├── test_configs/        # Directory for saved test configurations
└── README.md            # This file
```

> [!NOTE]
> Typically, if we had our LangGraph deployed to the LangGraph Platform, we would use the LangSmith UI to save and load configurations.

### Quick Start

#### Streamlit UI
After running the setup script, you can start the Streamlit UI with the following command:
```bash
# Using the CLI command (recommended)
wkg-api ui
```

The Streamlit app provides a user-friendly interface for managing test configurations and interacting with the LangGraph server. Key features include:

- **Saved Configurations**: View, edit, and delete your saved test configurations
- **Create New Configuration**: Create and save new test configurations
- **Send to Studio**: Send configurations directly to the LangGraph Studio
- **LangGraph Server Status**: Check the status of your LangGraph server and view available assistants

#### Command Line Interface

The test configuration manager also provides a command-line interface:

```bash
# List all saved configurations
python -m tests.utils.test_config_manager list

# Save a new configuration
python -m tests.utils.test_config_manager save my_test_query --query "What wildfires occurred in California in 2023?" --assistant-id "your-assistant-id"

# Load a configuration
python -m tests.utils.test_config_manager load my_test_query

# Send a configuration to the LangGraph Studio
python -m tests.utils.test_config_manager send my_test_query
```

### Standard Test Queries

Here are some standard test queries to get you started:

1. **KG Query Examples**:
   ```
   What ignition data is available for the sedgwick prescriptive fire?
   ```

2. **RAG Query Examples**:
   ```
   What are the main causes of wildfires?
   ```

3. **Combined KG & RAG Query Examples**:
   ```
   What factors and weather conditions contributed to the fire spread of the sedgwick prescriptive fire?
   ```

### Troubleshooting

- **API Errors**: If you're getting API errors when sending configurations, make sure the LangGraph server is running at the specified URL (default: `http://127.0.0.1:2024`).
  
- **Missing Configurations**: Configurations are stored in the `tests/test_configs` directory by default. You can specify a different directory using the `--config-dir` parameter.

- **Assistant ID**: If you're using a specific assistant ID, make sure it's correctly specified in the configuration.

## Running Automated Tests

In addition to the manual testing tools, you may also run automated tests:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_kg_tool.py

# Run with verbose output
pytest -v
```

## Performance Testing

For performance testing of your LangGraph application, you can use the test configuration manager to send multiple queries in sequence and measure response times.

Example:
```bash
# Save performance test queries
python -m tests.utils.test_config_manager save perf_test1 --query "List wildfires in California in 2020"
python -m tests.utils.test_config_manager save perf_test2 --query "What is the relationship between temperature and wildfire spread?"

# Run performance tests
python tests/performance/run_performance_tests.py
``` 