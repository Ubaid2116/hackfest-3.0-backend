import os
import json
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
import requests
from collections import deque
import uuid
from contextlib import asynccontextmanager
from agents import Agent, handoff, Runner, RunConfig, OpenAIChatCompletionsModel, function_tool, AsyncOpenAI

load_dotenv()

def make_filter(keyword: str):
    """
    Returns a function that checks if the keyword appears in the user input (case-insensitive).
    """
    lower_keyword = keyword.lower()
    return lambda text: lower_keyword in text.lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
JOBSTORE_DB_URL = os.getenv("JOBSTORE_DB_URL", "sqlite:///jobs.sqlite")
ULTRAMSG_TOKEN = os.getenv("ULTRAMSG_TOKEN")
ULTRAMSG_INSTANCE_ID = os.getenv("ULTRAMSG_INSTANCE_ID")

if not ULTRAMSG_TOKEN or not ULTRAMSG_INSTANCE_ID:
    raise RuntimeError("Missing ULTRAMSG_TOKEN or ULTRAMSG_INSTANCE_ID in .env")

# Scheduler setup
scheduler = BackgroundScheduler(
    jobstores={'default': SQLAlchemyJobStore(url=JOBSTORE_DB_URL)}
)
scheduler.start()

# OpenAI/Gemini client setup
external_client = AsyncOpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)
model = OpenAIChatCompletionsModel(
    model="gemini-2.0-flash",
    openai_client=external_client
)
config = RunConfig(
    model=model,
    model_provider=external_client,
    tracing_disabled=True
)

@function_tool
def send_whatsapp_reminder(to_phone: str, medicine: str):
    msg = f"💊 Reminder: Time to take your {medicine}!"
    try:
        url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
        payload = {"token": ULTRAMSG_TOKEN, "to": to_phone, "body": msg}
        resp = requests.post(url, data=payload)
        resp.raise_for_status()
        return {"method": "whatsapp", "response": resp.json()}
    except requests.RequestException as e:
        print(f"Error sending WhatsApp reminder: {e}")
        return {"method": "mock", "message": msg, "error": str(e)}

@function_tool
def schedule_whatsapp_reminder(to_phone: str, medicine: str, time_str: str):
    try:
        hour, minute = map(int, time_str.split(':'))
        assert 0 <= hour < 24 and 0 <= minute < 60
    except Exception:
        raise ValueError("Time must be in HH:MM (24-hour) format")

    job_id = f"whatsapp-{to_phone}-{medicine}-{time_str}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        send_whatsapp_reminder,
        trigger='cron',
        args=[to_phone, medicine],
        hour=hour,
        minute=minute,
        id=job_id,
        replace_existing=True
    )

@function_tool
def _trigger_emergency_alert(patient_name: str, condition: str):
    msg = (
        f"🚨 Emergency Alert!\n"
        f"Patient: {patient_name}\n"
        f"Condition: {condition}\n"
        "Please respond urgently!"
    )
    try:
        url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
        payload = {"token": ULTRAMSG_TOKEN, "to": "+923412583056", "body": msg}
        resp = requests.post(url, data=payload)
        resp.raise_for_status()
        return {"method": "whatsapp", "response": resp.json()}
    except requests.RequestException as e:
        print(f"Error sending WhatsApp message: {e}")
        return {"method": "mock", "message": msg, "error": str(e)}

# Agent definitions
welcome_agent = Agent(name="Welcome Agent", instructions="""
You are the first point of contact for users seeking healthcare services.
1. Greet the user.
2. List services:
   - General Checkup
   - Emergency Services
   - COVID-19 Information
   - Medicine Reminders
   - Dietary Advice
   - Mental Health Support
3. Ask how you can assist today.
""")

health_agent = Agent(
    name="Health Check Agent",
    instructions="""
You are a Health Check Agent. Your role is to analyze user-described symptoms and identify possible common health issues.

- First, politely ask the user for their **name** and **age** before analyzing any symptoms.
  Example: "Before we begin, may I have your name and age?"

- After collecting the user's name and age, proceed to analyze the described symptoms.

- If the symptoms indicate a **life-threatening or emergency condition**, immediately trigger the emergency alert using the appropriate tool and return the following message:
  "Your condition appears to be an emergency. I have sent a message to the emergency department."

- If it is **not an emergency**, identify the most appropriate **type of doctor or specialist** based on the symptoms.
  Then respond with a message like:
  "Based on your symptoms, it is recommended to consult a [specialist]. For your safety, please book an appointment with a nearby [specialist]."

⚠️ Do not provide medical diagnoses. Only identify symptom patterns and recommend a relevant medical specialist when appropriate.
""",
    tools=[_trigger_emergency_alert]
)

mental_health_agent = Agent(name="Mental Health Agent", instructions="""
Provide mental health support and guidance.
- Offer coping strategies
- Suggest professional help when needed
- Be empathetic and non-judgmental
""")

covid_agent = Agent(name="COVID-19 Agent", instructions="""
Share COVID-19 info on vaccines, symptoms, isolation, precautions, testing.
""")

emergency_agent = Agent(
    name="Emergency Agent",
    instructions="""
You are an Emergency Response Agent. Your role is to handle life-threatening or critical medical situations.

1. When a user sends a message, check if both of the following are provided:
   - **Patient Name**
   - **Condition or medical issue**

2. If either is missing, politely ask:
   - "Please provide the patient's name."
   - Or: "Please describe the patient's condition."

3. Once both the patient's name and condition are received, trigger the emergency alert using the provided tool.

4. Respond to the user with:
   "Your emergency has been reported to the concerned department. Help is on the way."

Do not request any specific message format.
Do not provide medical advice. Focus only on detecting emergencies and triggering alerts.
""",
    tools=[_trigger_emergency_alert]
)

medicine_agent = Agent(
    name="Medicine Reminder Agent",
    instructions="""
You are a Medicine Reminder Agent. Your job is to collect the following information from the user:

- **Phone number** (e.g. +923001112233)
- **Medicine name** (e.g. Paracetamol, Ibuprofen)
- **Reminder time** in 24-hour format (HH:MM) — e.g. 08:00, 14:30

Once you collect all three fields:
1. Use the `schedule_whatsapp_reminder` tool to schedule a daily WhatsApp reminder.
2. Confirm to the user with a message like:
   "✅ Your reminder for [medicine] has been successfully scheduled at [time_str] daily via WhatsApp."

Important:
- Ensure the phone number is in international format (e.g., +923001112233).
- Ensure the time format is valid (HH:MM in 24-hour format).
- Do **not** allow incomplete or invalid input to proceed.

You do not provide medical advice. Your role is strictly to schedule medication reminders via WhatsApp.
""",
    tools=[schedule_whatsapp_reminder, send_whatsapp_reminder]
)

diet_agent = Agent(name="Diet Agent", instructions="""
Provide dietary advice based on:
- Health conditions
- Nutritional needs
- Dietary restrictions
- Always recommend consulting a nutritionist for personalized plans
""")

registration_agent = Agent(name="Registration Agent", instructions="""
Collect name, email, age, desired service and hand off accordingly.
""")

registration_agent.handoffs = [
    handoff(health_agent, input_filter=make_filter("health")),
    handoff(mental_health_agent, input_filter=make_filter("mental")),
    handoff(covid_agent, input_filter=make_filter("covid")),
    handoff(emergency_agent, input_filter=make_filter("emergency")),
    handoff(medicine_agent, input_filter=make_filter("reminder")),
    handoff(diet_agent, input_filter=make_filter("diet")),
]

SHORT_TERM_MEMORY_TURNS = 10
short_memory = {}

def get_memory_deque(session_id: str):
    if session_id not in short_memory:
        short_memory[session_id] = deque(maxlen=SHORT_TERM_MEMORY_TURNS)
    return short_memory[session_id]

# FastAPI app setup with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    await Runner.run(welcome_agent, input="Hello", run_config=config)
    yield
    scheduler.shutdown()

app = FastAPI(title="NeuroNestAI Healthcare API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    agent: str = "Welcome Agent"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

agents = {
    "Welcome Agent": welcome_agent,
    "Health Check Agent": health_agent,
    "Mental Health Agent": mental_health_agent,
    "COVID-19 Agent": covid_agent,
    "Emergency Agent": emergency_agent,
    "Medicine Reminder Agent": medicine_agent,
    "Diet Agent": diet_agent,
    "Registration Agent": registration_agent,
}

def parse_emergency_input(message: str) -> tuple[str, str]:
    patient_name = "Unknown"
    condition = "unspecified"
    
    name_match = re.search(r"Patient:\s*([^\n,]+)", message, re.IGNORECASE)
    condition_match = re.search(r"Condition:\s*([^\n]+)", message, re.IGNORECASE)
    
    if name_match:
        patient_name = name_match.group(1).strip()
    if condition_match:
        condition = condition_match.group(1).strip()
        
    return patient_name, condition

@app.post("/api/chat")
async def chat_with_agent(chat: ChatRequest):
    agent = agents.get(chat.agent)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    mem = get_memory_deque(chat.session_id)
    mem.append({"role": "user", "message": chat.message})

    context = "\n".join(f"{t['role']}: {t['message']}" for t in mem)
    prompt = context + "\nassistant:"

    try:
        result = await Runner.run(agent, input=prompt, run_config=config)
        output = result.final_output.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

    mem.append({"role": "assistant", "message": output})

    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {"response": output}

    action = payload.get("action")
    if action == "schedule_reminder":
        phone = payload["phone"]
        medicine = payload["medicine_name"]
        time_ = payload["reminder_time"]
        schedule_whatsapp_reminder(phone, medicine, time_)
        return {"response": f"✅ Reminder set for {medicine} at {time_} via WhatsApp to {phone}."}

    if action == "emergency_alert":
        name = payload.get("patient_name", "Unknown")
        condition = payload.get("condition", "unspecified")
        _trigger_emergency_alert(name, condition)
        return {"response": f"🚨 Emergency alert sent to the emergency department via WhatsApp for {name} with condition: {condition}."}

    return {"response": output}

@app.get("/api/agents")
async def list_agents():
    return {"agents": list(agents.keys())}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)