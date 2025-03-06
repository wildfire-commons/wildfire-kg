#!/usr/bin/env python
"""
Performance testing script for the LangGraph application.
This script runs a series of test queries and measures their performance.
"""

import time
import argparse
import json
import statistics
from pathlib import Path
import sys
import logging
from typing import List, Dict, Any

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent.parent))
from tests.utils.test_config_manager import TestConfigManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("performance_test_results.log"),
    ],
)
logger = logging.getLogger(__name__)


class PerformanceTest:
    """
    A class to run performance tests on the LangGraph application.
    Uses saved test configurations and measures response times.
    """

    def __init__(
        self, config_dir: str = None, studio_url: str = "http://127.0.0.1:2024"
    ):
        """Initialize the performance test with a configuration directory."""
        self.config_manager = TestConfigManager(config_dir)
        self.studio_url = studio_url
        self.results = {}

    def run_test(self, config_name: str, iterations: int = 3) -> Dict[str, Any]:
        """
        Run a test with the specified configuration multiple times.

        Args:
            config_name: The name of the saved configuration to use
            iterations: Number of times to run the test

        Returns:
            A dictionary with test results
        """
        config = self.config_manager.load_config(config_name)
        if not config:
            logger.error(f"Configuration '{config_name}' not found.")
            return {}

        query = config.get("query", "")
        logger.info(f"Running performance test for: {config_name}")
        logger.info(f"Query: {query}")

        # Record results for each iteration
        times = []
        errors = 0

        for i in range(iterations):
            logger.info(f"Iteration {i+1}/{iterations}")

            try:
                # Measure time to complete the query
                start_time = time.time()

                # Send the query to the LangGraph Studio
                self.config_manager.send_to_studio(config_name, self.studio_url)

                end_time = time.time()
                elapsed_time = end_time - start_time
                times.append(elapsed_time)

                logger.info(f"Completed in {elapsed_time:.2f} seconds")

                # Add a small delay between iterations
                if i < iterations - 1:
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Error in iteration {i+1}: {e}")
                errors += 1

        # Calculate statistics
        if times:
            avg_time = statistics.mean(times)
            median_time = statistics.median(times)
            min_time = min(times)
            max_time = max(times)

            if len(times) > 1:
                stdev = statistics.stdev(times)
            else:
                stdev = 0

            result = {
                "config_name": config_name,
                "query": query,
                "iterations": iterations,
                "successful_iterations": iterations - errors,
                "errors": errors,
                "average_time": avg_time,
                "median_time": median_time,
                "min_time": min_time,
                "max_time": max_time,
                "stdev": stdev,
                "raw_times": times,
            }

            self.results[config_name] = result
            return result
        else:
            logger.error("No successful iterations to report.")
            return {
                "config_name": config_name,
                "query": query,
                "iterations": iterations,
                "successful_iterations": 0,
                "errors": errors,
            }

    def run_all_tests(self, iterations: int = 3) -> Dict[str, Dict[str, Any]]:
        """
        Run tests for all saved configurations.

        Args:
            iterations: Number of times to run each test

        Returns:
            A dictionary of test results keyed by configuration name
        """
        configs = self.config_manager.list_configs()
        if not configs:
            logger.error("No saved configurations found.")
            return {}

        logger.info(f"Running performance tests for {len(configs)} configurations")

        for config_name in configs:
            self.run_test(config_name, iterations)

        return self.results

    def run_specific_tests(
        self, config_names: List[str], iterations: int = 3
    ) -> Dict[str, Dict[str, Any]]:
        """
        Run tests for specific configurations.

        Args:
            config_names: List of configuration names to test
            iterations: Number of times to run each test

        Returns:
            A dictionary of test results keyed by configuration name
        """
        logger.info(f"Running performance tests for {len(config_names)} configurations")

        for config_name in config_names:
            self.run_test(config_name, iterations)

        return self.results

    def save_results(self, output_file: str = "performance_test_results.json"):
        """Save the test results to a JSON file."""
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {output_file}")

    def print_summary(self):
        """Print a summary of the test results."""
        if not self.results:
            logger.error("No results to summarize.")
            return

        logger.info("Performance Test Summary:")
        logger.info("=" * 50)

        for config_name, result in self.results.items():
            logger.info(f"Configuration: {config_name}")
            logger.info(f"Query: {result.get('query', 'N/A')}")
            logger.info(f"Iterations: {result.get('iterations', 0)}")
            logger.info(f"Successful: {result.get('successful_iterations', 0)}")
            logger.info(f"Errors: {result.get('errors', 0)}")

            if "average_time" in result:
                logger.info(f"Average Time: {result['average_time']:.2f}s")
                logger.info(f"Median Time: {result['median_time']:.2f}s")
                logger.info(
                    f"Min/Max: {result['min_time']:.2f}s / {result['max_time']:.2f}s"
                )

            logger.info("-" * 50)

        logger.info("=" * 50)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Run performance tests for LangGraph application"
    )
    parser.add_argument("--config-dir", help="Directory containing test configurations")
    parser.add_argument(
        "--studio-url",
        help="URL of the LangGraph Studio API",
        default="http://127.0.0.1:2024",
    )
    parser.add_argument(
        "--iterations", type=int, help="Number of iterations for each test", default=3
    )
    parser.add_argument(
        "--output",
        help="Output file for test results",
        default="performance_test_results.json",
    )
    parser.add_argument("--configs", nargs="+", help="Specific configurations to test")

    args = parser.parse_args()

    # Create and run the performance tests
    perf_test = PerformanceTest(args.config_dir, args.studio_url)

    if args.configs:
        perf_test.run_specific_tests(args.configs, args.iterations)
    else:
        perf_test.run_all_tests(args.iterations)

    # Print and save the results
    perf_test.print_summary()
    perf_test.save_results(args.output)


if __name__ == "__main__":
    main()
