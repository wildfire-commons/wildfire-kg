from typing import Dict, List, Any, Annotated, TypedDict, Literal, Tuple
import logging
from langgraph.graph import StateGraph, END
from src.orchestration.state.conversation_state import ConversationState, Message
from src.orchestration.agents.router_agent import create_router_agent
from src.orchestration.agents.response_agent import create_response_agent
from src.orchestration.tools.kg_tool import KnowledgeGraphTool
from src.orchestration.tools.rag_tool import RAGTool
from src.orchestration.tools.weather_tool import WeatherTool

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_chat_graph():
    """Create the LangGraph workflow for the chat application."""
    # Initialize the tools
    kg_tool = KnowledgeGraphTool()
    rag_tool = RAGTool()
    weather_tool = WeatherTool()

    # Initialize the agents
    router = create_router_agent()
    response_generator = create_response_agent()

    # Define the nodes in the graph
    def route_query(
        state: ConversationState,
    ) -> Dict[str, Any]:
        """Route the query to the appropriate node based on the router's decision."""
        query = state.get("user_query", "")
        logger.info(f"🔀 Routing query: '{query}'")

        # Create a new state to update
        new_state = state.copy()

        try:
            # Call the router agent
            logger.info("🧠 Consulting router agent for decision")
            result = router(query)
            action = result.get("action")
            reasoning = result.get("reasoning", "No reasoning provided")

            # Log the routing decision with emojis for better visibility
            action_emoji = {
                "kg_query": "🔍",
                "web_search_query": "🌐",
                "both": "🔍🌐",
                "direct_response": "💬",
            }.get(action, "❓")

            logger.info(f"{action_emoji} Routing to: {action}")
            logger.info(f"📝 Reasoning: {reasoning}")

            # Add the routing decision to the state metadata
            metadata = new_state.get("metadata", {})
            metadata["routing"] = result
            new_state["metadata"] = metadata

            # Set the next node in the state for conditional edges
            logger.info(f"➡️ Setting next node to: {action}")
            return {"next": action, **new_state}

        except Exception as e:
            logger.error(f"❌ Error in router: {str(e)}", exc_info=True)

            # Fallback to 'both' if there's an error
            logger.info("⚠️ Router error - falling back to 'both'")
            metadata = new_state.get("metadata", {})
            metadata["routing"] = {
                "action": "both",
                "reasoning": f"Fallback due to error: {str(e)}",
            }
            new_state["metadata"] = metadata

            return {"next": "both", **new_state}

    def query_knowledge_graph(state: ConversationState) -> ConversationState:
        """Query the knowledge graph and update the state."""
        query = state.get("user_query", "")
        logger.info(f"Executing knowledge graph query: {query}")

        # Execute the knowledge graph query
        result = kg_tool._run(query)

        # Update the state with the results
        state["kg_results"] = result

        return state

    def query_web_search(state: ConversationState) -> ConversationState:
        """Query external sources using web search and update the state."""
        query = state.get("user_query", "")
        logger.info(f"Executing web search query: {query}")

        # Execute the web search query
        result = web_search_tool._run(query)

        # Update the state with the results
        state["web_search_results"] = result

        return state

    def handle_both_queries(state: ConversationState) -> ConversationState:
        """Handle both KG and web search queries in sequence."""
        query = state.get("user_query", "")
        logger.info(
            f"Starting sequential execution of both KG and web search queries for: {query}"
        )

        # Create a new state dictionary to update
        new_state = state.copy()

        # Initialize results containers
        new_state["kg_results"] = {}
        new_state["web_search_results"] = {}

        # Step 1: Execute Knowledge Graph query
        try:
            logger.info("🔍 Executing Knowledge Graph query...")
            kg_result = kg_tool._run(query)
            new_state["kg_results"] = kg_result
            logger.info(
                f"✅ KG query completed with answer length: {len(str(kg_result.get('answer', '')))}"
            )
        except Exception as e:
            logger.error(f"❌ Error in Knowledge Graph query: {str(e)}", exc_info=True)
            new_state["kg_results"] = {"error": f"Error in KG query: {str(e)}"}
            # Add error metadata
            metadata = new_state.get("metadata", {})
            metadata["kg_error"] = str(e)
            new_state["metadata"] = metadata

        # Step 2: Execute web search query
        try:
            logger.info("🌐 Executing web search query...")
            web_search_result = web_search_tool._run(query)
            new_state["web_search_results"] = web_search_result
            doc_count = len(web_search_result.get("documents", []))
            logger.info(
                f"✅ Web search query completed with {doc_count} documents retrieved"
            )
        except Exception as e:
            logger.error(f"❌ Error in web search query: {str(e)}", exc_info=True)
            new_state["web_search_results"] = {
                "error": f"Error in web search query: {str(e)}"
            }
            # Add error metadata
            metadata = new_state.get("metadata", {})
            metadata["web_search_error"] = str(e)
            new_state["metadata"] = metadata

        # Step 3: Add execution metadata
        metadata = new_state.get("metadata", {})
        metadata["both_executed"] = True
        metadata["kg_success"] = "error" not in new_state["kg_results"]
        metadata["web_search_success"] = "error" not in new_state["web_search_results"]
        new_state["metadata"] = metadata

        logger.info(
            "✨ Both queries execution completed - continuing to response generation"
        )
        return new_state

    def handle_all_queries(state: ConversationState) -> ConversationState:
        """Handle execution of all three tools in sequence."""
        query = state.get("user_query", "")
        logger.info(f"Starting execution of all tools for query: {query}")

        # Create a new state to update
        new_state = state.copy()

        # Initialize results containers
        new_state["kg_results"] = {}
        new_state["rag_results"] = {}
        new_state["weather_results"] = {}

        try:
            # Step 1: Execute Weather query
            logger.info("🌤️ Executing Weather query...")
            weather_result = weather_tool._run(query)
            new_state["weather_results"] = weather_result
            logger.info("✅ Weather query completed")

            # Step 2: Execute Knowledge Graph query
            logger.info("🔍 Executing Knowledge Graph query...")
            kg_result = kg_tool._run(query)
            new_state["kg_results"] = kg_result
            logger.info("✅ KG query completed")

            # Step 3: Execute RAG query
            logger.info("📚 Executing RAG query...")
            rag_result = rag_tool._run(query)
            new_state["rag_results"] = rag_result
            logger.info("✅ RAG query completed")

        except Exception as e:
            logger.error(f"❌ Error in all-tools execution: {str(e)}", exc_info=True)
            new_state["error"] = str(e)

        # Add execution metadata
        metadata = new_state.get("metadata", {})
        metadata["all_executed"] = True
        metadata["weather_success"] = "error" not in new_state["weather_results"]
        metadata["kg_success"] = "error" not in new_state["kg_results"]
        metadata["rag_success"] = "error" not in new_state["rag_results"]
        new_state["metadata"] = metadata

        logger.info("✨ All tools execution completed")
        return new_state

    def generate_response(state: ConversationState) -> ConversationState:
        """Generate the final response and update the state."""
        query = state.get("user_query", "")
        metadata = state.get("metadata", {})
        route_info = metadata.get("routing", {})
        action = route_info.get("action", "unknown")

        logger.info(f"🎯 Generating response for query routed to: {action}")

        # Create a new state to update
        new_state = state.copy()

        # Check for errors
        if "error" in state:
            logger.error(f"❌ Error found in state: {state['error']}")
            error_msg = f"I apologize, but an error occurred: {state['error']}"
            new_state["response"] = error_msg
            messages = new_state.get("messages", [])
            messages.append(Message(content=error_msg, role="ai"))
            new_state["messages"] = messages
            return new_state

        # Check for 'both' execution
        both_executed = metadata.get("both_executed", False)
        if both_executed:
            logger.info("📊 Processing results from 'both' node execution")
            kg_success = metadata.get("kg_success", False)
            web_search_success = metadata.get("web_search_success", False)
            logger.info(
                f"KG success: {kg_success}, Web search success: {web_search_success}"
            )

            if not kg_success and not web_search_success:
                logger.warning("⚠️ Both KG and web search queries failed")

        # Generate the response using the response agent
        try:
            logger.info("🤖 Invoking response generator")
            response_text = response_generator(state)
            logger.info(
                f"✅ Response generated successfully (length: {len(response_text)})"
            )

            # Update the state with the response
            new_state["response"] = response_text

            # Add the response to the messages
            messages = new_state.get("messages", [])
            messages.append(Message(content=response_text, role="ai"))
            new_state["messages"] = messages

            logger.info("✨ Response generation complete")
            return new_state

        except Exception as e:
            logger.error(f"❌ Error in response generation: {str(e)}", exc_info=True)
            error_msg = f"I apologize, but I encountered an error while generating a response: {str(e)}. Please try again with a different question."
            new_state["response"] = error_msg
            new_state["error"] = str(e)

            # Add the error response to messages
            messages = new_state.get("messages", [])
            messages.append(Message(content=error_msg, role="ai"))
            new_state["messages"] = messages

            return new_state

    def query_weather(state: ConversationState) -> ConversationState:
        """Process weather queries in the graph."""
        user_query = state.get("user_query", "")

        # Extract location if present
        location = None
        if "in" in user_query:
            location = user_query.split("in")[-1].strip()

        # Execute weather query
        try:
            result = weather_tool._run(query=user_query, location=location)

            # Update state with results
            state["weather_results"] = {
                "query": user_query,
                "location": location or result.get("location"),
                "weather_data": result.get("weather_data"),
                "execution_time": result.get("execution_time"),
            }

        except Exception as e:
            state["weather_results"] = {
                "query": user_query,
                "error": str(e),
                "execution_time": 0,
            }

        return state

    # Create the graph
    workflow = StateGraph(ConversationState)

    # Add the nodes
    workflow.add_node("route", route_query)
    workflow.add_node("kg_query", query_knowledge_graph)
    workflow.add_node("web_search_query", query_web_search)
    workflow.add_node("both", handle_both_queries)
    workflow.add_node("all", handle_all_queries)
    workflow.add_node("weather_query", query_weather)
    workflow.add_node(
        "direct_response", lambda state: state
    )  # Placeholder for direct response
    workflow.add_node("generate_response", generate_response)

    # Define conditional edges based on the 'next' field from the router
    workflow.add_conditional_edges(
        "route",
        lambda state: state.get("next"),
        {
            "kg_query": "kg_query",
            "web_search_query": "web_search_query",
            "both": "both",
            "all": "all",
            "weather_query": "weather_query",
            "direct_response": "direct_response",
        },
    )

    # From kg_query, go to generate_response
    workflow.add_edge("kg_query", "generate_response")

    # From web_search_query, go to generate_response
    workflow.add_edge("web_search_query", "generate_response")

    # From both, go directly to generate_response since it handles both queries internally
    workflow.add_edge("both", "generate_response")

    # From direct_response, go straight to generate_response
    workflow.add_edge("direct_response", "generate_response")

    # From weather_query, go to generate_response
    workflow.add_edge("weather_query", "generate_response")

    # From all, go to generate_response
    workflow.add_edge("all", "generate_response")

    # From generate_response, end the workflow
    workflow.add_edge("generate_response", END)

    # Set the entry point
    workflow.set_entry_point("route")

    # Compile the graph
    return workflow.compile()


def process_user_message(
    user_message: str, conversation_history: List[Message] = None
) -> Dict[str, Any]:
    """Process a user message and return the response."""
    # Initialize the conversation history if not provided
    if conversation_history is None:
        conversation_history = []

    # Truncate very long user messages before processing
    if len(user_message) > 500:
        logger.warning(
            f"User message is very long ({len(user_message)} chars). Truncating to 500 chars."
        )
        user_message = user_message[:500] + "... [Message truncated due to length]"

    # Create the initial state
    state: ConversationState = {
        "user_query": user_message,
        "messages": conversation_history
        + [Message(content=user_message, role="human")],
        "metadata": {},
    }

    # Create the graph
    graph = create_chat_graph()

    # Execute the graph
    try:
        # Run the graph
        result = graph.invoke(state)

        # Return the final state
        return result
    except Exception as e:
        logger.error(f"Error executing chat graph: {str(e)}", exc_info=True)
        # Return an error state
        return {
            "error": str(e),
            "user_query": user_message,
            "messages": conversation_history
            + [
                Message(content=user_message, role="human"),
                Message(
                    content=f"I'm sorry, but an error occurred: {str(e)}", role="ai"
                ),
            ],
        }
