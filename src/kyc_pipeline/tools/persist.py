from crewai.tools import tool

@tool("save_decision_record")
def save_decision_record(final_decision: str, explanation: str) -> str:
    """
    Save the final KYC decision and its explanation (stub).
    Replace with DB insert or file persistence later.
    """
    return f"record-saved:decision={final_decision};reason={explanation}"