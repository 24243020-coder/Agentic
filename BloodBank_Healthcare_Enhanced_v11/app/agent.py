import json
import os
import re
from typing import TypedDict, List, Dict, Any

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from .tools import tool_catalog

load_dotenv()


# ============================================================
# AGENT STATE
# ============================================================

class AgentState(TypedDict, total=False):
    user_input: str
    steps: List[Dict[str, Any]]
    answer: str


# ============================================================
# TOOL CATALOG
# ============================================================

TOOLS = tool_catalog()


# ============================================================
# BLOOD GROUP EXTRACTION
# ============================================================

def extract_group(text):
    """
    Extract blood group such as:
    A+, A-, B+, B-, AB+, AB-, O+, O-
    """

    if not text:
        return None

    m = re.search(
        r"(?<![A-Z0-9])(AB[+-]|A[+-]|B[+-]|O[+-])(?![A-Z0-9])",
        text.upper()
    )

    return m.group(1) if m else None


# ============================================================
# LOCAL PLANNER
# ============================================================

def local_planner(state):

    q = state.get("user_input", "").strip()
    low = q.lower()

    group = extract_group(q)

    steps = []
    answer = ""

    # ========================================================
    # 1. INVENTORY / BLOOD STOCK
    # ========================================================

    if any(
        x in low
        for x in [
            "stock",
            "inventory",
            "units",
            "available blood",
            "blood stock",
            "how much blood"
        ]
    ):

        result = TOOLS["inventory"](group)

        steps.append({
            "tool": "inventory",
            "input": {
                "blood_group": group
            },
            "output": result
        })

        if isinstance(result, dict) and "blood_group" in result:

            answer = (
                f'{result["blood_group"]}: '
                f'{result["units"]} units available.'
            )

        elif isinstance(result, dict):

            answer = result.get(
                "message",
                "No inventory record."
            )

        elif result:

            answer = " | ".join(
                f'{x["blood_group"]}: {x["units"]} units'
                for x in result
            )

        else:

            answer = "No inventory records available."


    # ========================================================
    # 2. DONOR SEARCH
    # ========================================================

    elif any(
        x in low
        for x in [
            "donor",
            "donors",
            "find donor",
            "find donors",
            "match donor",
            "available donor"
        ]
    ):

        if not group:

            result = {
                "message":
                "Please specify a blood group such as O+ or A-."
            }

        else:

            result = TOOLS["donor_search"](group)

        steps.append({
            "tool": "donor_search",
            "input": {
                "blood_group": group
            },
            "output": result
        })

        if isinstance(result, dict):

            answer = result.get(
                "message",
                "No donor information available."
            )

        elif result:

            answer = (
                "Available donors: "
                +
                ", ".join(
                    f'{x["name"]} ({x["city"]})'
                    for x in result
                )
            )

        else:

            answer = (
                "No currently available donor was found."
            )


    # ========================================================
    # 3. POLICY / ELIGIBILITY / EMERGENCY
    # ========================================================

    elif any(
        x in low
        for x in [
            "policy",
            "rule",
            "eligibility",
            "emergency"
        ]
    ):

        result = TOOLS["policy_search"](q)

        steps.append({
            "tool": "policy_search",
            "input": {
                "query": q
            },
            "output": result
        })

        if isinstance(result, list):

            answer = " ".join(
                str(x)
                for x in result
            )

        else:

            answer = str(result)


    # ========================================================
    # 4. FULFILL / PROCESS BLOOD REQUEST
    # ========================================================

    elif any(
        x in low
        for x in [
            "fulfill",
            "fulfil",
            "issue blood",
            "give blood",
            "complete request",
            "process request",
            "process the request",
            "fulfill request",
            "fulfil request"
        ]
    ):

        # ----------------------------------------------------
        # Get pending requests
        # ----------------------------------------------------

        requests = TOOLS["list_requests"]()

        steps.append({
            "tool": "list_requests",
            "input": {
                "status": "Pending"
            },
            "output": requests
        })

        # ----------------------------------------------------
        # Keep only pending requests
        # ----------------------------------------------------

        pending = [
            r for r in requests
            if str(r.get("status", "")).lower() == "pending"
        ]

        target = None

        # ----------------------------------------------------
        # Match request number
        #
        # Examples:
        #   Fulfill request #4
        #   Fulfill #4
        #   Process request 4
        # ----------------------------------------------------

        mid = re.search(
            r"(?:request\s*)?#\s*(\d+)",
            q,
            re.I
        )

        # Also support:
        # "request 4"
        if not mid:

            mid = re.search(
                r"request\s+(\d+)",
                q,
                re.I
            )

        if mid:

            request_id = int(mid.group(1))

            target = next(
                (
                    r for r in pending
                    if int(r["id"]) == request_id
                ),
                None
            )

        # ----------------------------------------------------
        # Match patient name
        # ----------------------------------------------------

        else:

            for r in pending:

                name = str(
                    r.get("patient_name", "")
                ).strip()

                if (
                    name
                    and name.lower() in low
                ):

                    target = r
                    break

        # ----------------------------------------------------
        # If only one pending request exists,
        # automatically select it.
        # ----------------------------------------------------

        if target is None and len(pending) == 1:

            target = pending[0]

        # ----------------------------------------------------
        # No matching request
        # ----------------------------------------------------

        if target is None:

            if not pending:

                result = {
                    "message":
                    "There are no pending blood requests to fulfill."
                }

            elif len(pending) > 1:

                result = {
                    "message":
                    "I found multiple pending blood requests. "
                    "Please tell me the request number or patient name."
                }

            else:

                result = {
                    "message":
                    "I could not identify that blood request."
                }

            answer = result["message"]

        # ----------------------------------------------------
        # Fulfill selected request
        # ----------------------------------------------------

        else:

            request_id = target["id"]

            result = TOOLS["fulfill_request"](
                request_id
            )

            steps.append({
                "tool": "fulfill_request",
                "input": {
                    "request_id": request_id
                },
                "output": result
            })

            answer = result.get(
                "message",
                "Blood request processed."
            )

            # ------------------------------------------------
            # Donor remaining units
            # ------------------------------------------------

            if (
                result.get("ok")
                and result.get("donor_name")
            ):

                donor_name = result["donor_name"]

                remaining = result.get(
                    "donor_remaining_units",
                    0
                )

                if remaining:

                    answer += (
                        f" Donor {donor_name} now has "
                        f"{remaining} unit(s) available."
                    )

                else:

                    answer += (
                        f" Donor {donor_name} is now unavailable."
                    )


    # ========================================================
    # 5. REQUEST / REGISTER / CREATE REQUEST
    # ========================================================

    elif any(
        x in low
        for x in [
            "request",
            "register",
            "create request",
            "new request"
        ]
    ):

        result = {
            "message":
            "Use the Blood Request form to create a request. "
            "The assistant can help with existing requests "
            "when patient or request details are supplied."
        }

        steps.append({
            "tool": "create_request",
            "input": "missing structured fields",
            "output": result
        })

        answer = result["message"]


    # ========================================================
    # 6. DEFAULT
    # ========================================================

    else:

        result = TOOLS["inventory"]()

        steps.append({
            "tool": "inventory",
            "input": {
                "blood_group": None
            },
            "output": result
        })

        answer = (
            "I can help with blood inventory, "
            "donor search, blood requests, "
            "request fulfillment and policy questions."
        )

    # ========================================================
    # SAVE STATE
    # ========================================================

    state["steps"] = steps
    state["answer"] = answer

    return state


# ============================================================
# BUILD AGENT
# ============================================================

def build_agent():

    g = StateGraph(AgentState)

    g.add_node(
        "planner",
        local_planner
    )

    g.set_entry_point(
        "planner"
    )

    g.add_edge(
        "planner",
        END
    )

    return AgentRunner(
        g.compile()
    )


# ============================================================
# AGENT RUNNER
# ============================================================

class AgentRunner:

    def __init__(self, graph):

        self.graph = graph

        self.client = None

        # ----------------------------------------------------
        # Optional OpenAI integration
        # ----------------------------------------------------

        if os.getenv("OPENAI_API_KEY"):

            try:

                from openai import OpenAI

                self.client = OpenAI(
                    api_key=os.getenv(
                        "OPENAI_API_KEY"
                    )
                )

            except Exception:

                self.client = None


    # ========================================================
    # ACTIVITY MESSAGE
    # ========================================================

    def activity_message(
        self,
        user_input,
        result
    ):

        text = user_input.strip()

        group = extract_group(text)

        steps = result.get(
            "steps",
            []
        )

        tool = (
            steps[0].get("tool")
            if steps
            else ""
        )

        if tool == "donor_search":

            return (
                f"Donor search completed — {group}"
                if group
                else
                "Donor search requested"
            )

        if tool == "inventory":

            return (
                f"Blood stock checked — {group}"
                if group
                else
                "Blood inventory checked"
            )

        if tool == "policy_search":

            return "Blood bank policy checked"

        if tool == "create_request":

            return "Blood request information checked"

        if tool == "fulfill_request":

            return "Blood request fulfilled"

        return "Blood Assistant request completed"


    # ========================================================
    # INVOKE AGENT
    # ========================================================

    def invoke(
        self,
        user_input
    ):

        # ----------------------------------------------------
        # IMPORTANT FIX
        #
        # We directly execute the planner instead of:
        #
        # self.graph.invoke(...)
        #
        # This avoids the LangChain callback/debug
        # compatibility issue.
        # ----------------------------------------------------

        state = local_planner({
            "user_input": user_input
        })

        # ----------------------------------------------------
        # Optional OpenAI response polishing
        # ----------------------------------------------------

        if self.client:

            try:

                prompt = f"""
You are BloodLink AI, an agentic blood-bank
operations assistant.

Summarize only the verified tool results.

Never invent:
- donors
- blood inventory
- patient requests
- blood units
- fulfillment results

Use the tool results as the source of truth.

Always state that final clinical decisions
require authorized medical staff.

User:
{user_input}

Tool trace:
{json.dumps(
    state.get("steps", []),
    default=str
)}

Draft:
{state.get("answer", "")}
"""

                response = self.client.chat.completions.create(

                    model=os.getenv(
                        "OPENAI_MODEL",
                        "gpt-4o-mini"
                    ),

                    messages=[
                        {
                            "role": "system",
                            "content":
                            "Be concise and operational."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],

                    temperature=0.2
                )

                state["answer"] = (
                    response
                    .choices[0]
                    .message
                    .content
                )

            except Exception:

                # If OpenAI fails, keep the verified
                # local tool response.
                pass

        return state