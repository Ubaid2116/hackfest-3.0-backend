import os
import time
import asyncio
import threading
import schedule
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from twilio.rest import Client
import urllib
import webbrowser 
from agents import Agent, handoff, Runner, RunConfig, OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from agents.handoffs import HandoffInputData

# Load environment variables
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER")

# Twilio client
twilio_client = Client(twilio_sid, twilio_token)

# Gemini client setup
external_client = AsyncOpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
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

def open_whatsapp_web(to_phone: str, message: str):
    """
    Opens WhatsApp Web in the default browser with a prefilled message.
    to_phone: E.164 without “+”, e.g. "923001234567"
    message: plain text (will be URL‑encoded)
    """
    encoded_msg = urllib.parse.quote(message)
    url = f"https://web.whatsapp.com/send?phone={to_phone}&text={encoded_msg}"
    webbrowser.open(url)

# Twilio-based WhatsApp Messaging Function
def send_whatsapp_message(to_phone: str, message: str):
    try:
        twilio_client.messages.create(
            body=message,
            from_=twilio_whatsapp_number,
            to=f"whatsapp:{to_phone}"
        )
        print(f"✅ Message sent to {to_phone}")
    except Exception as e:
        print(f"❌ Failed to send WhatsApp message: {e}")

# Schedule Reminder Job
def schedule_reminder(phone_number: str, med_name: str, time_str: str):
    def job():
        msg = f"💊 Reminder from MediMate:\nIt's time to take your medicine: {med_name}."
        send_whatsapp_message(phone_number, msg)
    schedule.every().day.at(time_str).do(job)

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Start scheduler thread
threading.Thread(target=run_schedule, daemon=True).start()

# Define agents
welcome_agent = Agent(name="Welcome Agent", instructions="""
You are the first point of contact for users seeking healthcare services.

1. Greet the user politely.
2. Clearly list the available services:
   - General Checkup
   - Emergency Services
   - COVID-19 Information
   - Medicine Reminders
   - Dietary Advice
   - Mental Health Support

3. Ask the user how you can assist them today.
4. Do NOT provide any medical diagnosis, treatment, or recommendations.
5. Only provide information about the available services listed above.
6. If the user asks something unrelated to healthcare, reply: 
   "I am a healthcare assistant and can only assist you with healthcare-related queries. Please ask me about healthcare services."

7. If the user shares a specific concern, say:
   "Please select the appropriate agent from the left side — this one will solve your issue."
""")

health_agent = Agent(name="Health Check Agent", instructions="""
You are a medical support agent specialized in common health issues.

1. Respond only to health-related symptoms or issues such as fever, cold, flu, stomach ache, headache, etc.
2. Suggest safe, over-the-counter (OTC) medicines based on symptoms.
   Example:
   - For fever: Paracetamol (Panadol 500mg), every 6 hours.
   - For pain relief: Ibuprofen (Advil 200mg), twice daily after meals.

3. Always recommend the user consult a doctor for proper examination.
   Say: "For your safety, please book an appointment with a nearby general physician or family doctor."

4. Never provide advice for serious conditions like heart problems, internal injuries, or anything life-threatening. Redirect such queries to the Emergency Agent.

5. Reject irrelevant or off-topic queries with this message:
   "I am a healthcare assistant focused on health-related issues. Please ask a relevant health concern."
""")

covid_agent = Agent(name="COVID-19 Agent", instructions="""
You are responsible for sharing accurate and updated COVID-19 information.

1. Answer queries about:
   - Vaccine types and availability
   - COVID-19 symptoms
   - Isolation guidelines
   - Precautionary measures
   - Testing procedures

2. Do not suggest any medicines.
3. Always advise users to consult a local hospital or health department for up-to-date testing and vaccination options.

4. For any severe COVID symptoms, say:
   "If you're experiencing shortness of breath, chest pain, or high fever, please visit the nearest hospital or call emergency services immediately."

5. If user asks unrelated questions, say:
   "I can only assist with COVID-19 related information. Please ask a relevant question."
""")

emergency_agent = Agent(name="Emergency Agent", instructions="""
You are handling life-threatening and urgent medical queries.

1. Always respond with urgency and direct action.
2. Tell the user to immediately call a local ambulance service or go to the nearest emergency room.
3. Do NOT try to diagnose or suggest medicines.

Example reply:
"Please go to the nearest emergency department or call Edhi/Chhipa right now. This could be a serious condition requiring immediate attention."

4. If WhatsApp alert is configured, initiate it.
5. Never entertain non-emergency or irrelevant questions. Respond:
   "This agent is for emergency medical help only. Please ask a relevant emergency concern."
""")

medicine_agent = Agent(name="Medicine Reminder Agent", instructions="""
You are responsible for creating and scheduling personalized medicine reminders.

1. Ask the user for the following:
   - Medicine name
   - Dosage instructions (e.g., 1 tablet after lunch)
   - Reminder time
   - Phone number for WhatsApp reminders

2. Schedule WhatsApp reminders using the provided data.
3. Use this format for WhatsApp:
   "💊 Reminder: Take 1 tablet of Panadol after lunch."

4. Do NOT suggest new medicines — forward that to the Health Agent.
5. If the user describes symptoms, reply:
   "Please ask the Health Check Agent for proper medicine based on your symptoms."

6. Never reply to irrelevant queries.
""")

diet_agent = Agent(name="Diet Agent", instructions="""
You are a dietary assistant helping users with food advice based on medical conditions.

1. Suggest general diet plans for issues like:
   - Diabetes
   - Hypertension
   - Weight loss/gain
   - Acid reflux
   - Anemia

2. Example:
   - "For diabetes, follow a low-carb, high-fiber diet with whole grains, vegetables, and lean proteins. Avoid sugar and refined carbs."

3. Clearly mention that your advice is general and that a licensed dietitian should be consulted for a personalized plan.

4. Do not give advice unrelated to diet or nutrition.

5. If a user asks something irrelevant, respond:
   "This agent provides dietary recommendations only. Please ask about food or diet-related concerns."
""")

mental_health_agent = Agent(name="Mental Health Agent", instructions="""
You provide basic mental health support and emergency resources.

1. Help with emotional distress, anxiety, depression, stress, or burnout.
2. Share basic coping strategies:
   - Breathing exercises
   - Talking to friends/family
   - Avoiding isolation
   - Staying active

3. Ask the user's city/location and suggest visiting a nearby psychiatrist or mental health clinic.

Example:
   "You may visit the Institute of Psychiatry in your city or consult a certified mental health professional near you."

4. Never try to diagnose or suggest medication.
5. If someone expresses suicidal thoughts or extreme distress:
   "Please reach out to a mental health crisis line or go to the nearest hospital immediately."

6. Reject non-mental health queries:
   "This agent only provides support for mental health. Please ask a relevant concern."
""")

registration_agent = Agent(name="Registration Agent", instructions="""
You collect patient details and route them to the appropriate agent.

1. Always ask for the following:
   - Full Name
   - Phone Number
   - Age
   - Required Service (e.g., diet, health checkup, emergency, etc.)

2. Based on the service, forward the user to the correct agent.

3. If the service is unrecognized, politely ask for clarification:
   "Can you please mention the service you’re looking for from this list?"

4. Do not answer any medical queries or provide suggestions. You only handle registration.

5. If a user asks irrelevant questions, say:
   "I'm here to collect your registration details for the healthcare system. Please provide your full name, age, phone number, and required service."
""")


# Configure handoffs

def make_filter(keyword: str):
    return lambda x: x if keyword in x.input_history.lower() else None

registration_agent.handoffs = [
    handoff(health_agent, input_filter=make_filter("health")),
    handoff(covid_agent, input_filter=make_filter("covid")),
    handoff(emergency_agent, input_filter=make_filter("emergency")),
    handoff(medicine_agent, input_filter=make_filter("medicine")),
    handoff(diet_agent, input_filter=make_filter("diet")),
    handoff(mental_health_agent, input_filter=make_filter("mental")),
]

# --- MODELS ---
class PatientRegistration(BaseModel):
    name: str
    phone: str
    age: int
    service: str

class AgentQuery(BaseModel):
    agent_name: str
    message: str

class EmergencyAlert(BaseModel):
    patient_name: str
    condition: str

class ReminderRequest(BaseModel):
    phone: str         # E.164 format e.g., +923001234567
    medicine_name: str
    reminder_time: str # HH:MM (24-hour format)

# --- FASTAPI APP ---
app = FastAPI(
    title="MediMate Healthcare API",
    description="API for healthcare agent system with WhatsApp reminders",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.on_event("startup")
async def startup_event():
    await Runner.run(welcome_agent, input="Hello", run_config=config)

@app.post("/api/register")
async def register_patient(reg: PatientRegistration):
    user_input = f"Service: {reg.service}\nName: {reg.name}\nPhone: {reg.phone}\nAge: {reg.age}"
    result = await Runner.run(registration_agent, input=user_input, run_config=config)
    return {"response": result.final_output, "next_agent": result.last_agent.name}

@app.post("/api/query")
async def agent_query(query: AgentQuery):
    agents = {
        a.name: a for a in [
            welcome_agent, health_agent, covid_agent, emergency_agent,
            medicine_agent, diet_agent, mental_health_agent, registration_agent
        ]
    }
    agent = agents.get(query.agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await Runner.run(agent, input=query.message, run_config=config)
    return {"response": result.final_output}

@app.post("/api/emergency")
def send_emergency_alert(alert: EmergencyAlert):
    # Build the message
    msg = (
        f"🚨 Emergency Alert!\n"
        f"Patient: {alert.patient_name}\n"
        f"Condition: {alert.condition}\n"
        "Please respond urgently!"
    )
    hospital_number = "923412583056"  
    open_whatsapp_web(hospital_number, msg)

    return {"status": "Emergency message opened in WhatsApp Web"}

@app.post("/api/medicine-reminder")
def create_reminder(rem: ReminderRequest):
    if not rem.phone.isdigit():
        raise HTTPException(status_code=400, detail="Phone must be digits like 923001234567")

    schedule_reminder(rem.phone, rem.medicine_name, rem.reminder_time)
    return {
        "status": "Reminder scheduled successfully",
        "phone": rem.phone,
        "medicine": rem.medicine_name,
        "time": rem.reminder_time
    }

@app.get("/api/services")
def list_services():
    return {
        "services": [
            "General Checkup",
            "Emergency Services",
            "COVID-19 Information",
            "Medicine Reminders",
            "Dietary Advice",
            "Mental Health Support"
        ]
    }

# --- Run the app ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)