#  Mentally Swasth

**Mentally Swasth** is a mental wellness web platform built with **Flask** that helps users track emotions, connect with others, and reflect on their mental health journey.

The application combines **mood tracking, real-time community chat, and secure OTP authentication** in a clean, responsive interface.

---

## ✨ Features

* 🔐 **Email OTP Authentication** (secure password-less login)
* 😊 **Mood Tracking System** with personal notes and history
* 💬 **Real-time Community Chat** using WebSockets
* 📊 **Mood Visualization** with interactive charts
* 🌗 **Dark / Light Theme** with persistent preference
* 📱 **Fully Responsive UI**

---

## 🛠 Tech Stack

### Backend

* **Python 3.12** — Core programming language
* **Flask** — Lightweight web framework for building the application
* **Flask-SQLAlchemy** — ORM for database modeling and queries
* **Flask-SocketIO** — Enables real-time communication for community chat
* **Flask-Mail** — Handles OTP email delivery for authentication

### Database

* **SQLite** — Lightweight relational database used for storing users, moods, chat messages, and ratings

### Frontend

* **HTML5** — Page structure and layout
* **CSS3** — Custom styling with modern UI design (glassmorphism + responsive layout)
* **JavaScript (Vanilla)** — Client-side interactions and API communication
* **Socket.IO Client** — Real-time messaging with the backend
* **Chart.js** — Mood visualization and analytics charts

### UI & Design

* **Font Awesome** — Icon system
* **Google Fonts (Poppins)** — Typography
* **CSS Variables** — Dynamic theme support (Dark / Light mode)

### Development & Tools

* **Git & GitHub** — Version control and repository management
* **VS Code** — Development environment
* **Virtual Environment (venv)** — Dependency isolation
* **pip** — Python package manager


---

## 🚀 Run Locally

Clone the repository:

```bash
git clone https://github.com/nidhiless/mentally-swasth.git
cd mentally-swasth
```

Create virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python app.py
```

Open in browser:

```
http://127.0.0.1:5000
```

---

## 📁 Project Structure

```
mentally-swasth
│
├── app.py
├── models.py
├── init_db.py
├── requirements.txt
│
├── templates
├── static
└── instance
```

---

## 👩‍💻 Author

**Nidhi Patel**

GitHub:
https://github.com/nidhiless
Mail:
nidhi.patel.builds@gmail.com

