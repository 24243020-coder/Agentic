from pathlib import Path
import chromadb

CHROMA_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"
POLICIES = [
    ("p1","Emergency requests should be prioritized using the urgency level recorded by the hospital. Staff should verify clinical details before release."),
    ("p2","Donor eligibility must be checked by trained blood-bank personnel. The AI can locate candidates but must not make the final medical eligibility decision."),
    ("p3","Displayed inventory is an operational estimate. Staff should verify physical stock, expiry dates, storage conditions and cross-matching requirements before issue."),
    ("p4","Patient information should be handled confidentially. Only authorized blood-bank staff should access identifying information."),
    ("p5","When requested blood is low, staff may contact eligible and available donors of the same group according to local donor-management policy."),
    ("p6","The agent may create a pending blood request, but approval and blood release require authorized human review.")
]

def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection("blood_bank_policies")

def init_knowledge_base():
    c = get_collection()
    c.upsert(ids=[x[0] for x in POLICIES], documents=[x[1] for x in POLICIES])

def search_policies(query, n=3):
    r = get_collection().query(query_texts=[query], n_results=n)
    return r.get("documents",[[]])[0]
