import sys
import os

from Backend.config import Config  # Import Config

from uagents import Agent, Context
from uagents.setup import fund_agent_if_low
from Backend.models import UserInput, Schedule
import google.generativeai as genai
from typing import List
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Scheduling Agent
scheduling_agent = Agent(
    name="scheduling_agent",
    seed=Config.SCHEDULING_AGENT_SEED,
    port=Config.SCHEDULING_AGENT_PORT,
    endpoint=[f"http://127.0.0.1:{Config.SCHEDULING_AGENT_PORT}/submit"]
)

# Fund the agent if needed
fund_agent_if_low(scheduling_agent.wallet.address())

async def generate_schedule_with_gemini(user_input: UserInput) -> List[str]:
    prompt = f"""
    Generate a weekly content posting schedule based on the following preferences:
    - Area of interest: {user_input.area_of_interest}
    - Content type: {user_input.content_type}
    - Keywords: {', '.join(user_input.keywords)}
    - Post frequency: {user_input.post_frequency} times per week

    Provide a schedule of {user_input.post_frequency} days of the week (e.g., ["Monday", "Wednesday", "Friday"] for 3 times a week).
    Return only the JSON array of days.
    """
    
    model = genai.GenerativeModel('gemini-pro')
    response = model.generate_content(prompt)
    
    try:
        schedule = json.loads(response.text)
        if isinstance(schedule, list) and len(schedule) == user_input.post_frequency:
            return schedule
        else:
            raise ValueError("Invalid schedule format or incorrect number of days")
    except json.JSONDecodeError:
        raise ValueError("Failed to parse Gemini response as JSON")

@scheduling_agent.on_event("startup")
async def initialize(ctx: Context):
    ctx.logger.info(f"Scheduling Agent started. Address: {scheduling_agent.address}")

@scheduling_agent.on_message(model=UserInput)
async def handle_user_input(ctx: Context, sender: str, msg: UserInput):
    ctx.logger.info(f"Received user input from {sender}: {msg}")
    
    try:
        schedule = await generate_schedule_with_gemini(msg)
        ctx.logger.info(f"Generated schedule: {schedule}")
        
        # Validate the schedule
        if len(schedule) != msg.post_frequency:
            raise ValueError(f"Generated schedule does not match requested frequency. Got {len(schedule)}, expected {msg.post_frequency}")
        
        # Send the generated schedule back to the Main Coordinator Agent
        response = await ctx.send(sender, Schedule(posting_days=schedule))
        ctx.logger.info(f"Sent schedule to {sender}. Response: {response}")
    except Exception as e:
        ctx.logger.error(f"Error generating schedule: {str(e)}")
        # Send an error message back to the Main Coordinator Agent
        error_msg = f"Failed to generate schedule: {str(e)}"
        await ctx.send(sender, {"error": error_msg})

if __name__ == "__main__":
    scheduling_agent.run()