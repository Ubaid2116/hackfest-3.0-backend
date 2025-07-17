## MediMate Healthcare API

A FastAPI-based backend service to power a healthcare chatbot system with:

* **AI agents** for welcoming, health checks, COVID-19 info, emergency guidance, medicine reminders, diet advice, and mental health support.
* **WhatsApp integration** via Twilio for sending scheduled medicine reminders and emergency alerts.
* **Scheduler** for daily medicine reminders.
* **Frontend-ready** REST endpoints for easy integration by your frontend team.

---

### 📂 Repository Structure

```
├── main.py               # Main Agent & FastAPI application
├── requirements.txt     # List of dependencies (no versions)
├── .env.example         # Sample environment variables file
├── README.md            # Project documentation (this file)
```

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/medimate-backend.git
cd medimate-backend
```

### 2. Setup Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```
GEMINI_API_KEY=your_gemini_api_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+1234567890
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Application

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

---

## 📑 API Endpoints

Below is a quick reference of all REST endpoints available. Your frontend team can use these directly:

| Method | Endpoint                 | Description                                           |
| ------ | ------------------------ | ----------------------------------------------------- |
| POST   | `/api/register`          | Register a new patient and route to the proper agent. |
| POST   | `/api/query`             | Send a message to a specific agent.                   |
| POST   | `/api/emergency`         | Trigger an emergency alert via WhatsApp Web.          |
| POST   | `/api/medicine-reminder` | Schedule a daily medicine reminder.                   |
| GET    | `/api/services`          | List all available services.                          |

> **Note:** If your frontend is served under a different base path, adjust `/api/*` accordingly.

### 1. Register Patient

* **URL:** `/api/register`
* **Method:** `POST`
* **Request Body:**

  ```json
  {
    "name": "John Doe",
    "phone": "923001234567",
    "age": 30,
    "service": "health"
  }
  ```
* **Response:**

  ```json
  {
    "response": "<agent reply>",
    "next_agent": "Health Check Agent"
  }
  ```

### 2. Agent Query

* **URL:** `/api/query`
* **Method:** `POST`
* **Request Body:**

  ```json
  {
    "agent_name": "Health Check Agent",
    "message": "I have a headache"
  }
  ```
* **Response:**

  ```json
  {
    "response": "For headaches, you can take ..."
  }
  ```

### 3. Emergency Alert

* **URL:** `/api/emergency`
* **Method:** `POST`
* **Request Body:**

  ```json
  {
    "patient_name": "John Doe",
    "condition": "Severe chest pain"
  }
  ```
* **Behavior:** Opens WhatsApp Web in the default browser prefilled to your configured hospital number.
* **Response:**

  ```json
  { "status": "Emergency message opened in WhatsApp Web" }
  ```

### 4. Medicine Reminder

* **URL:** `/api/medicine-reminder`
* **Method:** `POST`
* **Request Body:**

  ```json
  {
    "phone": "923001234567",
    "medicine_name": "Panadol 500mg",
    "reminder_time": "14:00"
  }
  ```
* **Response:**

  ```json
  {
    "status": "Reminder scheduled successfully",
    "phone": "923001234567",
    "medicine": "Panadol 500mg",
    "time": "14:00"
  }
  ```

### 5. List Services

* **URL:** `/api/services`
* **Method:** `GET`
* **Response:**

  ```json
  {
    "services": [
      "General Checkup",
      "Emergency Services",
      "COVID-19 Information",
      "Medicine Reminders",
      "Dietary Advice",
      "Mental Health Support"
    ]
  }
  ```

---

## 🤝 Frontend Integration Tips

* **Base URL:** Ensure your frontend points to `http://<backend-host>:8000` (or your deployed domain).
* **Error Handling:** All validation errors return HTTP 400 with a JSON `detail` message. Display `detail` to end users.
* **CORS:** Already enabled for `*` origins, so you can test locally without issues.
* **WhatsApp Web:** The `/api/emergency` endpoint opens a browser window. You may want to invoke it via a button click in your UI.

---

## 🛠️ Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/foo`)
3. Commit your changes (`git commit -am 'Add foo'`)
4. Push to the branch (`git push origin feature/foo`)
5. Open a Pull Request

---

*Powered by Python, FastAPI, and Gemini AI agents.*
