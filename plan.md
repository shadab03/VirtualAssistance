Project Antigravity: AI Job Search & Automation
An intelligent, semi-automated bot that monitors job postings, filters them using AI against a professional profile, and generates tailored resumes via Telegram.

📌 Project Overview
Target Roles: SAP Consultancy (ABAP/HANA, MM, EWM), Solution Architecture.

Primary Stack: Python 3.11+, PostgreSQL, OpenAI/Anthropic, Telegram API.

Deployment: Docker + Railway.app / DigitalOcean.

🛠 Tech Stack & Architecture
Language: Python (Asyncio)

Bot Framework: python-telegram-bot

Database: SQLModel (SQLAlchemy + Pydantic)

AI Engine: LangChain + OpenAI GPT-4o

Document Engine: Jinja2 (HTML Templates) + pdfkit (PDF Generation)

Hosting: PostgreSQL (Supabase/Railway) + Docker

📅 Roadmap: 5-Phase Execution
Phase 1: Foundation & "The Brain" (Current)
[ ] Env Setup: Initialize Git, VirtualEnv, and .env file.

[ ] The Master Profile: Create data/master_profile.md (detailed 10-year history).

[ ] AI Matcher: Build a Python module to:

Accept a Job Description.

Compare against the Master Profile.

Return a JSON "Suitability Report" (Score 1-10, Gap Analysis, Keyword suggestions).

Phase 2: The Watchman (Scraper & DB)
[ ] DB Schema: Setup Job and Applied tables using SQLModel.

[ ] The Scraper: Implement a scheduled task using SerpApi (Google Jobs) or RSS feeds.

[ ] Deduplication: Ensure logic to skip jobs already present in the database.

[ ] Notification Logic: If a job matches > 7/10, trigger a Telegram notification.

Phase 3: The Command Center (Telegram UI)
[ ] Alerts: Send job summaries to Telegram with Inline Buttons:

[✅ Draft Resume] [❌ Ignore] [📝 View Details]

[ ] Interactive Chat: Implement /stats (daily finds) and /update_profile commands.

[ ] Async Processing: Ensure the bot handles multiple requests without hanging.

Phase 4: Document Factory (Automation)
[ ] Templating: Design a professional LaTeX or HTML/CSS resume template.

[ ] Tailoring: AI-generate a "Summary" and "Key Projects" section specific to the job post.

[ ] Generation: Convert the tailored content into a PDF.

[ ] Delivery: Bot sends the finished .pdf and .docx directly to the Telegram chat.

Phase 5: Cloud Deployment (Production)
[ ] Containerization: Write a Dockerfile for the application.

[ ] CI/CD: Setup GitHub Actions to deploy to Railway.app on every push.

[ ] Monitoring: Implement basic logging to track bot uptime and API usage