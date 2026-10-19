from langchain_groq import ChatGroq
from dotenv import load_dotenv
from app.database import Database
from app.summarizer import update_rolling_summary


load_dotenv()

db = Database("summary_test.db")
conversation_id = db.create_conversation()

# Create 11 completed turns.
for turn in range(1, 12):
    db.save_message(
        conversation_id,
        turn,
        "user",
        f"My message number {turn}",
    )
    db.save_message(
        conversation_id,
        turn,
        "assistant",
        f"Assistant response number {turn}",
    )

model = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.1,
)

result = update_rolling_summary(
    db=db,
    conversation_id=conversation_id,
    model=model,
    recent_window=10,
)

print("Summary updated:", result["updated"])
print("Summary through turn:", result["summary_through_turn"])
print("Summary:", result["summary"])
print("Conversation ID:", conversation_id)
