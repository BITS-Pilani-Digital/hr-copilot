"""HR Policy Copilot - Streamlit chat UI.   Run:  streamlit run app.py"""
import streamlit as st

from copilot import config
from copilot.agent import HRCopilot
from copilot.guardrails import check_input
from copilot.hr_store import HRStore
from copilot.ingest import ensure_index, get_embedder
from copilot.retriever import Retriever

st.set_page_config(page_title="HR Policy Copilot", page_icon="🤖", layout="wide")

EXAMPLES = [
    "How many days of annual leave can I carry forward?",
    "What's my leave balance?",
    "Do I need a medical certificate for 3 days of sick leave?",
    "Apply for annual leave from 15 to 19 December 2026 for a family trip.",
]


@st.cache_resource(show_spinner="Indexing policy documents...")
def load_retriever() -> Retriever:
    embedder = get_embedder()
    ensure_index(embedder)
    return Retriever.load(embedder)


def render_details(sources: list[dict], actions: list[dict]) -> None:
    if sources:
        with st.expander(f"📄 Sources ({len(sources)})"):
            for s in sources:
                st.markdown(f"**{s['source']} - page {s['page']}** · similarity {s['score']}")
                st.caption(s["text"][:600] + ("..." if len(s["text"]) > 600 else ""))
    if actions:
        with st.expander(f"🛠️ Actions ({len(actions)})"):
            for a in actions:
                st.markdown(f"`{a['tool']}` {a['args']}")
                if a["tool"] != "search_hr_policies":
                    st.code(str(a["result"])[:800], language="json")


store = HRStore()
employees = store.list_employees()

with st.sidebar:
    st.header("🤖 HR Policy Copilot")
    st.caption(f"{config.COMPANY_NAME} (fictional demo)")
    employee_id = st.selectbox("Signed in as (demo SSO)", list(employees),
                               format_func=lambda e: f"{employees[e]} ({e})")
    balance = store.get_balance(employee_id)
    st.subheader("My leave")
    cols = st.columns(3)
    for col, (leave_type, b) in zip(cols, balance.items()):
        col.metric(leave_type.title(), b["available"])
    pending = [f"{t} {b['pending']}d" for t, b in balance.items() if b["pending"]]
    if pending:
        st.caption("Pending approval: " + ", ".join(pending))
    requests = store.list_requests(employee_id)
    if requests:
        st.subheader("My requests")
        for r in reversed(requests[-5:]):
            st.caption(f"**{r['request_id']}** · {r['leave_type']} · {r['start_date']} → {r['end_date']} "
                       f"({r['days']}d) · {r['status']}")
    st.divider()
    st.caption(f"Model: `{config.CHAT_MODEL}` · Embeddings: `{config.EMBEDDING_MODEL}`")
    if st.button("Clear chat"):
        st.session_state.pop("chat", None)
        st.rerun()

if not config.OPENAI_API_KEY:
    st.error("OPENAI_API_KEY is not set. Add it to a .env file (see .env.example) or your environment, then restart.")
    st.stop()

if st.session_state.get("employee_id") != employee_id:
    st.session_state.employee_id = employee_id
    st.session_state.chat = []
    st.session_state.copilot = HRCopilot(load_retriever(), store, employee_id)
st.session_state.setdefault("chat", [])

st.title("Ask HR anything")
st.caption("Answers come from company policy PDFs with citations. I can also check your leave and raise requests.")

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        render_details(msg.get("sources", []), msg.get("actions", []))

prompt = st.chat_input("e.g. How many sick days do I get?")
examples = st.empty()
if not st.session_state.chat:
    with examples.container():
        cols = st.columns(2)
        for i, example in enumerate(EXAMPLES):
            if cols[i % 2].button(example, use_container_width=True):
                prompt = example

if prompt:
    examples.empty()
    with st.chat_message("user"):
        st.markdown(prompt)
    allowed, reason = check_input(prompt)
    history = [(m["role"], m["content"]) for m in st.session_state.chat][-10:]
    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("assistant"):
        if not allowed:
            reply = {"role": "assistant", "content": f"⚠️ {reason}"}
            st.markdown(reply["content"])
        else:
            with st.spinner("Thinking..."):
                try:
                    r = st.session_state.copilot.ask(prompt, history)
                    reply = {"role": "assistant", "content": r.answer, "sources": r.sources, "actions": r.actions}
                except Exception as exc:  # surface API/config errors in the demo instead of a stack trace
                    reply = {"role": "assistant", "content": f"⚠️ Something went wrong: `{exc}`"}
            st.markdown(reply["content"])
            render_details(reply.get("sources", []), reply.get("actions", []))
    st.session_state.chat.append(reply)
    if reply.get("actions") and any(a["tool"] == "raise_leave_request" for a in reply["actions"]):
        st.rerun()  # refresh sidebar balances
