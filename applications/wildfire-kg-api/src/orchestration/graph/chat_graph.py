from typing import Dict, List, Any, Annotated, TypedDict, Literal
import logging
from langgraph.graph import StateGraph, END
from ..state.conversation_state import ConversationState, Message
from ..agents.router_agent import create_router_agent
from ..agents.response_agent import create_response_agent
from ..tools.kg_tool import KnowledgeGraphTool
from ..tools.rag_tool import RAGTool

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_chat_graph():
    """Create the LangGraph workflow for the chat application."""
    # Initialize the tools
    kg_tool = KnowledgeGraphTool()
    rag_tool = RAGTool()

    # Initialize the agents
    router = create_router_agent()
    response_generator = create_response_agent()

    # Define the nodes in the graph
    def route_query(
        state: ConversationState,
    ) -> Literal["kg_query", "rag_query", "both", "direct_response"]:
        """Route the query to the appropriate node based on the router's decision."""
        query = state.get("user_query", "")
        result = router(query)
        action = result.get("action")

        # Log the routing decision
        logger.info(
            f"Routing query '{query}' to {action} based on reasoning: {result.get('reasoning')}"
        )

        # Add the routing decision to the state metadata
        metadata = state.get("metadata", {})
        metadata["routing"] = result
        state["metadata"] = metadata

        return action

    def query_knowledge_graph(state: ConversationState) -> ConversationState:
        """Query the knowledge graph and update the state."""
        query = state.get("user_query", "")

        # Execute the knowledge graph query
        result = kg_tool._run(query)

        # Update the state with the results
        state["kg_results"] = result

        return state

    def query_rag(state: ConversationState) -> ConversationState:
        """Query external sources using RAG and update the state."""
        query = state.get("user_query", "")

        # Execute the RAG query
        result = rag_tool._run(query)

        # Update the state with the results
        state["rag_results"] = result

        return state

    def generate_response(state: ConversationState) -> ConversationState:
        """Generate the final response and update the state."""
        # Generate the response
        response_text = response_generator(state)

        # Update the state with the response
        state["response"] = response_text

        # Add the response to the messages
        messages = state.get("messages", [])
        messages.append(Message(content=response_text, role="ai"))
        state["messages"] = messages

        return state

    # Create the graph
    workflow = StateGraph(ConversationState)

    # Add the nodes
    workflow.add_node("route", route_query)
    workflow.add_node("kg_query", query_knowledge_graph)
    workflow.add_node("rag_query", query_rag)
    workflow.add_node("both", lambda state: state)  # Placeholder for the "both" path
    workflow.add_node(
        "direct_response", lambda state: state
    )  # Placeholder for direct response
    workflow.add_node("generate_response", generate_response)

    # Add the edges
    workflow.add_edge("route", "kg_query")
    workflow.add_edge("route", "rag_query")
    workflow.add_edge("route", "both")
    workflow.add_edge("route", "direct_response")

    # From kg_query, go to generate_response
    workflow.add_edge("kg_query", "generate_response")

    # From rag_query, go to generate_response
    workflow.add_edge("rag_query", "generate_response")

    # From both, execute both kg_query and rag_query in parallel
    workflow.add_edge("both", "kg_query")
    workflow.add_edge("both", "rag_query")

    # From direct_response, go straight to generate_response
    workflow.add_edge("direct_response", "generate_response")

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
